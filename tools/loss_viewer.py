#!/usr/bin/env python3
# ruff: noqa: E501  (embedded HTML/JS page)
"""Live loss chart for training runs, e.g. on the DGX Spark, shown in a local browser.

Standard library only. The script starts a tiny log follower on the training machine (sent over
ssh via stdin, nothing to install there), streams new log lines back and serves a chart on
http://localhost:8765 that updates every two seconds.

    python3 tools/loss_viewer.py --ssh dienstollama@cst-ai-02 --pattern 'chemie-nodemcu-spark-s*.log'
    python3 tools/loss_viewer.py --local training/runs --pattern '*.log'      # logs on this machine

It reads the lines the training writes (training/src/ultratiny/train.py, cli.py):
  "step   1200  loss 0.0510"  (" (qat)" during quantization-aware fine-tuning)
  "demo: 1.000 (33 prompts)", "heldout: 0.700 (450 prompts)"
one log file per run, e.g. training/runs/<config>-s<seed>.log written by tools/spark/train.sh.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Runs on the training machine: follows every file matching the pattern (also files created
# later, e.g. the next seed) and prints "<file>\t<line>" for each new line, from the beginning.
# A new run with the same config truncates or replaces its log: then it prints "<file>\t\x00RESET"
# and reads the file again from the start.
FOLLOWER = r"""
import glob, os, sys, time
d, pat = os.path.expanduser(sys.argv[1]), sys.argv[2]
pos, buf, ino = {}, {}, {}
sys.stdout.write("\t\x00HELLO " + os.path.join(d, pat) + "\n")
sys.stdout.flush()
while True:
    for f in sorted(glob.glob(os.path.join(d, pat))):
        try:
            st = os.stat(f)
            if f in pos and (st.st_size < pos[f] or st.st_ino != ino.get(f)):
                pos[f], buf[f] = 0, ""
                sys.stdout.write(os.path.basename(f) + "\t\x00RESET\n")
            ino[f] = st.st_ino
            with open(f, "rb") as fh:
                fh.seek(pos.get(f, 0))
                data = fh.read()
                pos[f] = fh.tell()
        except OSError:
            continue
        if not data:
            continue
        text = buf.get(f, "") + data.decode("utf-8", "replace").replace("\r", "\n")
        *lines, buf[f] = text.split("\n")
        for line in lines:
            if line.strip():
                sys.stdout.write(os.path.basename(f) + "\t" + line + "\n")
        sys.stdout.flush()
    time.sleep(1.0)
"""

STEP_RE = re.compile(r"step\s+(\d+)\s+loss\s+([0-9.eE+-]+)(\s*\(qat\))?")
EVAL_RE = re.compile(r"^(demo|heldout|refusal|false_refusal)\S*:\s*([0-9.]+)")


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.runs: dict[str, dict] = {}
        self.status = "starting"

    def add(self, run: str, line: str) -> None:
        with self.lock:
            if line.startswith("\x00HELLO "):
                self.status = "verbunden, beobachte " + line[7:]
                return
            if line == "\x00RESET":  # the log was restarted by a new run
                self.runs.pop(run, None)
                return
            r = self.runs.setdefault(run, {"points": [], "qat_from": None, "eval": {}})
            m = STEP_RE.search(line)
            if m:
                step, loss, qat = int(m.group(1)), float(m.group(2)), bool(m.group(3))
                if qat and r["qat_from"] is None:  # QAT continues the step count
                    r["qat_from"] = len(r["points"])
                r["points"].append([step, loss])
                return
            m = EVAL_RE.match(line.strip())
            if m:
                r["eval"][m.group(1)] = float(m.group(2))

    def snapshot(self) -> dict:
        with self.lock:
            return {"status": self.status, "runs": json.loads(json.dumps(self.runs))}


def follow(cmd: list[str], state: State, follower_stdin: bool) -> None:
    """Run the follower, feed its lines into state, reconnect when it ends (e.g. ssh drops)."""
    while True:
        with state.lock:
            state.status = "verbinde: " + " ".join(cmd[:4])
            state.runs.clear()  # the follower replays every file from the start
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE if follower_stdin else None,
                                 stdout=subprocess.PIPE, text=True, bufsize=1)  # fmt: skip
            if follower_stdin:
                p.stdin.write(FOLLOWER)
                p.stdin.close()
            for raw in p.stdout:
                run, _, line = raw.rstrip("\n").partition("\t")
                state.add(run.removesuffix(".log"), line)
            p.wait()
            msg = f"follower ended (exit {p.returncode}), reconnecting in 5 s"
        except OSError as e:
            msg = f"cannot start {cmd[0]}: {e}; retrying in 5 s"
        with state.lock:
            state.status = msg
        print(msg, file=sys.stderr)
        time.sleep(5)


PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>UltraTiny Loss</title>
<style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--grid:#e3e2dc}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--fg:#ecebe6;--mut:#9b9a94;--grid:#33332f}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
h1{font-size:18px;margin:0 0 4px}#st{color:var(--mut);margin-bottom:12px}
svg{width:100%;height:auto;display:block}table{border-collapse:collapse;margin-top:12px}
td,th{padding:4px 10px;text-align:right;border-bottom:1px solid var(--grid)}th:first-child,td:first-child{text-align:left}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
</style></head><body><h1>Trainings-Loss (live)</h1><div id="st"></div>
<svg id="c" viewBox="0 0 900 420" role="img" aria-label="Loss je Schritt"></svg>
<table id="t"></table>
<script>
const C=["#2a7de1","#e8590c","#2f9e44","#ae3ec9","#f08c00","#0c8599","#c92a2a"];
function draw(d){
 document.getElementById("st").textContent=d.status;
 const runs=Object.entries(d.runs).filter(([k,r])=>r.points.length);
 const W=900,H=420,L=60,R=16,T=12,B=40,svg=document.getElementById("c");
 let xs=[],ys=[];runs.forEach(([k,r])=>r.points.forEach(p=>{xs.push(p[0]);ys.push(p[1])}));
 if(!xs.length){svg.innerHTML='<text x="450" y="210" text-anchor="middle" fill="currentColor">warte auf Daten …</text>';return}
 const x1=Math.max(...xs)||1,lo=Math.log10(Math.max(Math.min(...ys),1e-4)),hi=Math.log10(Math.max(...ys));
 const y0=Math.floor(lo),y1=Math.max(Math.ceil(hi),y0+1);
 const X=v=>L+(W-L-R)*v/x1, Y=v=>T+(H-T-B)*(y1-Math.log10(Math.max(v,1e-4)))/(y1-y0);
 let s="";
 for(let e=y0;e<=y1;e++)for(const m of [1,2,5]){const v=m*10**e;if(Math.log10(v)>y1)continue;
  s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/>`;
  if(m==1)s+=`<text x="${L-6}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="var(--mut)">${v}</text>`}
 for(let i=0;i<=5;i++){const v=Math.round(x1*i/5);s+=`<text x="${X(v)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--mut)">${v}</text>`}
 s+=`<text x="${(W+L)/2}" y="${H-6}" text-anchor="middle" font-size="12" fill="var(--mut)">Schritt</text>`;
 s+=`<text x="14" y="${(H-B)/2}" font-size="12" fill="var(--mut)" transform="rotate(-90 14 ${(H-B)/2})" text-anchor="middle">Loss (log)</text>`;
 runs.forEach(([k,r],i)=>{const c=C[i%C.length];
  s+=`<polyline fill="none" stroke="${c}" stroke-width="2" points="${r.points.map(p=>X(p[0])+","+Y(p[1])).join(" ")}"/>`;
  if(r.qat_from!==null&&r.points[r.qat_from]){const q=X(r.points[r.qat_from][0]);
   s+=`<line x1="${q}" x2="${q}" y1="${T}" y2="${H-B}" stroke="${c}" stroke-dasharray="4 4"/><text x="${q>W-60?q-4:q+4}" y="${T+12}" font-size="11" fill="${c}" text-anchor="${q>W-60?"end":"start"}">QAT</text>`}});
 svg.innerHTML=s;
 let t="<tr><th>Lauf</th><th>Schritt</th><th>Loss</th><th>demo</th><th>held-out</th></tr>";
 runs.forEach(([k,r],i)=>{const p=r.points[r.points.length-1],e=r.eval,f=v=>v===undefined?"–":(v*100).toFixed(1)+" %";
  t+=`<tr><td><span class="sw" style="background:${C[i%C.length]}"></span>${k}</td><td>${p[0]}</td><td>${p[1].toFixed(4)}</td><td>${f(e.demo)}</td><td>${f(e.heldout)}</td></tr>`});
 document.getElementById("t").innerHTML=t}
async function tick(){try{draw(await (await fetch("data")).json())}catch(e){document.getElementById("st").textContent="Viewer nicht erreichbar"}}
tick();setInterval(tick,2000);
</script></body></html>"""


def serve(state: State, port: int) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/data"):
                body, ctype = json.dumps(state.snapshot()).encode(), "application/json"
            else:
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # keep the terminal quiet
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ssh", metavar="HOST", help="training machine, as for ssh (user@host)")
    src.add_argument("--local", metavar="DIR", help="read logs from a local directory")
    ap.add_argument("--remote-dir", default="~/UltraTiny/training/runs",
                    help="log directory on the training machine (default: %(default)s)")  # fmt: skip
    ap.add_argument("--pattern", default="*-s*.log", help="log files to follow (default: %(default)s)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    if a.ssh:
        # ssh joins the remote arguments into one shell command: quote them for the remote shell.
        q = lambda s: "'" + s.replace("'", "'\\''") + "'"  # noqa: E731
        cmd = ["ssh", "-o", "ServerAliveInterval=15", a.ssh,
               "python3 -u - " + q(a.remote_dir) + " " + q(a.pattern)]  # fmt: skip
        stdin = True
    else:
        cmd = [sys.executable, "-u", "-c", FOLLOWER, a.local, a.pattern]
        stdin = False

    state = State()
    serve(state, a.port)
    url = f"http://localhost:{a.port}/"
    print(f"Loss viewer: {url}  (Strg-C beendet)")
    threading.Thread(target=follow, args=(cmd, state, stdin), daemon=True).start()
    if not a.no_browser:
        webbrowser.open(url)
    last = ""
    try:
        while True:
            snap = state.snapshot()
            parts = [f"{k}: Schritt {r['points'][-1][0]} Loss {r['points'][-1][1]:.4f}"
                     for k, r in snap["runs"].items() if r["points"]]  # fmt: skip
            line = " | ".join(parts) or snap["status"]
            if line != last:
                print(line, flush=True)
                last = line
            time.sleep(5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
