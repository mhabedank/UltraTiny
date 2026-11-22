#!/usr/bin/env python3
# ruff: noqa: E501  (embedded HTML/JS page)
"""Live training dashboard for runs on the DGX Spark (or locally), shown in a local browser.

Standard library only. The script starts a tiny log follower on the training machine (sent over
ssh via stdin, nothing to install there), streams new log lines back and serves a dashboard on
http://localhost:8765 that updates every two seconds.

    python3 tools/loss_viewer.py --ssh dienstollama@cst-ai-02 [--pattern 'chemie-nodemcu-spark-s*.log']
    python3 tools/loss_viewer.py --local training/runs --pattern '*.log'      # logs on this machine

It reads what the pipeline writes (training/src/ultratiny/cli.py, train.py), one log per run,
e.g. training/runs/<config>-s<seed>.log from tools/spark/train.sh:
  "== datagen" / "== train" / "== export" / "== eval ..." / "== golden" / "== budget" (phases)
  "train_examples": N (datagen summary)
  "step   1200  loss 0.0510" (" (qat)" during quantization-aware fine-tuning)
  "quantization check: float 0.912, int8 0.880 (3.2 pp)"
  "demo: 1.000 (33 prompts)", "heldout: 0.700 (450 prompts)", hybrid (specs/006):
  "heldout_family/heldout_combo/kurzarbeit: ...", "refusal rate: ..., wrong facts (all): ...",
  "chemistry held-out: ..., refusal
  rate: ..., false refusals: ...", "wrote ... (601404 bytes)", "ok": true|false, "OK"/"FAILED: ..."
The total number of steps comes from training/configs/<config>.toml next to the runs directory.
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

# Runs on the training machine. Follows every file matching the pattern (also files created later,
# e.g. the next seed) and prints "<file>\t<time>\t<line>" per new line; <time> is 0 for lines that
# already existed when the follower started (history), else the Unix time the line was read.
# Control lines: "\x00HELLO <path>", "\x00RESET" (a new run truncated/replaced the log, read it
# again), "\x00CONF <steps> <qat_steps>" (from configs/<config>.toml, -1 if unknown).
FOLLOWER = r"""
import glob, os, re, sys, time
d, pat = os.path.expanduser(sys.argv[1]), sys.argv[2]
pos, buf, ino, first = {}, {}, {}, True
out = sys.stdout
def emit(f, t, line):
    out.write(f + "\t" + t + "\t" + line + "\n")
def conf(name):
    tag = re.sub(r"-s\d+\.log$", "", name)
    path = os.path.join(d, "..", "configs", tag + ".toml")
    vals = {"steps": -1, "qat_steps": -1}
    try:
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*(steps|qat_steps)\s*=\s*(\d+)", line)
            if m:
                vals[m.group(1)] = int(m.group(2))
    except OSError:
        pass
    return "%d %d" % (vals["steps"], vals["qat_steps"])
emit("", "0", "\x00HELLO " + os.path.join(d, pat))
out.flush()
while True:
    now = "0" if first else "%.1f" % time.time()
    for f in sorted(glob.glob(os.path.join(d, pat))):
        name = os.path.basename(f)
        try:
            st = os.stat(f)
            if f in pos and (st.st_size < pos[f] or st.st_ino != ino.get(f)):
                pos[f], buf[f] = 0, ""
                emit(name, now, "\x00RESET")
            if f not in pos:
                emit(name, now, "\x00CONF " + conf(name))
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
                emit(name, now, line)
    out.flush()
    first = False
    time.sleep(1.0)
"""

STEP_RE = re.compile(r"step\s+(\d+)\s+loss\s+([0-9.eE+-]+)(\s*\(qat\))?")
EVAL_RE = re.compile(r"^(demo|heldout):\s*([0-9.]+)\s*\((\d+)")
# Hybrid pipeline (specs/006): per-set eval lines and the refusal / wrong-fact summary.
HYB_EVAL_RE = re.compile(
    r"^(trained_sample|heldout_family|heldout_combo|kurzarbeit|heldout_explain):\s*([0-9.]+)\s*\((\d+)"
)
HYB_KEYS = {"trained_sample": "demo", "heldout_family": "chem", "heldout_combo": "combo",
            "kurzarbeit": "kurz", "heldout_explain": "explain"}  # fmt: skip
HYB_REF_RE = re.compile(
    r"^refusal rate:\s*([0-9.]+).*false refusals:\s*([0-9.]+).*wrong facts \(all\):\s*([0-9.]+)"
)
CHEM_RE = re.compile(r"chemistry held-out:\s*([0-9.]+).*refusal rate:\s*([0-9.]+).*false refusals:\s*([0-9.]+)")
QUANT_RE = re.compile(r"quantization check: float ([0-9.]+), int8 ([0-9.]+) \(([-0-9.]+) pp\)")
DATA_RE = re.compile(r'^\s*"(train_examples|heldout|demo|facts|skipped_too_long)":\s*(\d+)')
WROTE_RE = re.compile(r"wrote .*\((\d+) bytes\)")
PHASES = {"datagen": "Daten", "train": "Training", "export": "Export", "eval": "Auswertung",
          "golden": "Golden", "budget": "Budget"}  # fmt: skip


def new_run() -> dict:
    return {"points": [], "qat_from": None, "eval": {}, "data": {}, "quant": None,
            "phase": "wartet", "result": None, "failed": "", "model_bytes": None,
            "budget_ok": None, "steps": None, "qat_steps": None, "last_seen": None}  # fmt: skip


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.runs: dict[str, dict] = {}
        self.status = "starte"
        self.connected = False

    def add(self, run: str, t: float, line: str) -> None:
        with self.lock:
            if line.startswith("\x00HELLO "):
                self.status = "beobachte " + line[7:]
                self.connected = True
                return
            if line == "\x00RESET":  # the log was restarted by a new run
                self.runs.pop(run, None)
                return
            r = self.runs.setdefault(run, new_run())
            if t:
                r["last_seen"] = t
            if line.startswith("\x00CONF "):
                steps, qat = (int(v) for v in line.split()[1:3])
                r["steps"] = steps if steps >= 0 else None
                r["qat_steps"] = qat if qat >= 0 else None
                return
            s = line.strip()
            m = STEP_RE.search(s)
            if m:
                step, loss, qat = int(m.group(1)), float(m.group(2)), bool(m.group(3))
                if qat and r["qat_from"] is None:  # QAT continues the step count
                    r["qat_from"] = len(r["points"])
                    r["phase"] = "QAT"
                r["points"].append([step, loss, t or None])
                return
            if s.startswith("== "):
                key = s[3:].split()[0]
                r["phase"] = PHASES.get(key, key)
                return
            if (m := EVAL_RE.match(s)) and r["phase"] == "Auswertung":
                r["eval"][m.group(1)] = float(m.group(2))
                r["eval"][m.group(1) + "_n"] = int(m.group(3))
            elif (m := HYB_EVAL_RE.match(s)) and r["phase"] == "Auswertung":
                key = HYB_KEYS[m.group(1)]
                r["eval"][key] = float(m.group(2))
                r["eval"][key + "_n"] = int(m.group(3))
            elif m := HYB_REF_RE.search(s):
                r["eval"].update(refusal=float(m.group(1)), false_refusal=float(m.group(2)),
                                 wrong_fact=float(m.group(3)))  # fmt: skip
            elif m := CHEM_RE.search(s):
                r["eval"].update(chem=float(m.group(1)), refusal=float(m.group(2)),
                                 false_refusal=float(m.group(3)))  # fmt: skip
            elif m := QUANT_RE.search(s):
                r["quant"] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            elif (m := DATA_RE.match(s)) and r["phase"] == "Daten":
                r["data"][m.group(1)] = int(m.group(2))
            elif m := WROTE_RE.search(s):
                r["model_bytes"] = int(m.group(1))
            elif r["phase"] == "Budget" and s.startswith('"ok":'):
                r["budget_ok"] = "true" in s
            elif s == "OK":
                r["result"], r["phase"] = "ok", "fertig"
            elif s.startswith("FAILED:"):
                r["result"], r["phase"], r["failed"] = "failed", "fertig", s[7:].strip()
            elif s.startswith("Traceback") or re.match(r"^\w*Error\b", s):
                r["result"], r["failed"] = "error", s[:160]

    def snapshot(self) -> dict:
        with self.lock:
            return {"status": self.status, "connected": self.connected, "now": time.time(),
                    "runs": json.loads(json.dumps(self.runs))}  # fmt: skip


def follow(cmd: list[str], state: State, follower_stdin: bool) -> None:
    """Run the follower, feed its lines into state, reconnect when it ends (e.g. ssh drops)."""
    while True:
        with state.lock:
            state.status = "verbinde: " + " ".join(cmd[:4])
            state.connected = False
            state.runs.clear()  # the follower replays every file from the start
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE if follower_stdin else None,
                                 stdout=subprocess.PIPE, text=True, bufsize=1)  # fmt: skip
            if follower_stdin:
                p.stdin.write(FOLLOWER)
                p.stdin.close()
            for raw in p.stdout:
                run, _, rest = raw.rstrip("\n").partition("\t")
                ts, _, line = rest.partition("\t")
                try:
                    t = float(ts)
                except ValueError:
                    t = 0.0
                state.add(run.removesuffix(".log"), t, line)
            p.wait()
            msg = f"Verbindung beendet (Exit {p.returncode}), neuer Versuch in 5 s"
        except OSError as e:
            msg = f"{cmd[0]} lässt sich nicht starten: {e}; neuer Versuch in 5 s"
        with state.lock:
            state.status, state.connected = msg, False
        print(msg, file=sys.stderr)
        time.sleep(5)


PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>UltraTiny Training</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@78..100,400..800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
/* Caravan palette (mhabedank/caravan docs/_themes/caravan/static/tokens.css). */
:root{color-scheme:light dark;--bg:#EFF2F0;--surface:#FCFCFB;--surface-2:#E4E8E5;--text:#062544;--muted:#4B5450;--border:#CDD4CE;--border-strong:#7A847C;
 --link:#0B4A70;--mark:#CA6A0A;--gain:#1C5E3F;--pain:#8A4310;--s-a:#0B4A70;--s-b:#5F8E8A;--s-c:#A8500C;--s-d:#7A847C;
 --navy:#062544;--cream:#FBEED0;--mint:#A5DBC6;--orange:#ED9B20;--sans:"Archivo",ui-sans-serif,system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#041C33;--surface:#062544;--surface-2:#0B3050;--text:#EFF2F0;--muted:#A3B5AD;--border:#17496F;--border-strong:#6C928C;
 --link:#8FC8E8;--mark:#ED9B20;--gain:#9BD4A6;--pain:#F5C07A;--s-a:#86B6D8;--s-b:#A5DBC6;--s-c:#ED9B20;--s-d:#A3B5AD}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 var(--sans)}
.num,.v,td,.k{font-family:var(--mono);font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px 40px}
.top{background:var(--navy);color:var(--cream);margin-bottom:18px;padding:20px 0 18px;border-bottom:6px solid var(--orange)}
.top-in{display:flex;flex-wrap:wrap;align-items:flex-end;gap:10px 20px;padding-bottom:0}
.eyebrow{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--mint);margin-bottom:6px}
h1{font:800 28px/1.05 var(--sans);font-stretch:85%;margin:0;letter-spacing:-.01em}h1 .o{color:var(--orange)}
h2{font:700 16px/1.2 var(--sans);margin:0 0 10px}
.st{color:#A3B5AD;font:12px var(--mono);display:flex;align-items:center;gap:8px;min-width:0;overflow-wrap:anywhere;margin-left:auto}
.dot{width:9px;height:9px;border-radius:50%;background:#7A847C;flex:none}.dot.on{background:var(--mint);box-shadow:0 0 0 4px rgba(165,219,198,.25)}
.modes{display:inline-flex;border:1px solid rgba(251,238,208,.35);border-radius:999px;overflow:hidden}
.modes button{border:0;background:transparent;color:var(--cream);padding:6px 14px;font:600 13px var(--sans);cursor:pointer}.modes button.on{background:var(--cream);color:var(--navy)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;min-width:0}
.runs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:14px;margin-bottom:14px}
.rh{display:flex;align-items:center;gap:8px;margin-bottom:6px}.sw{width:10px;height:10px;border-radius:3px;flex:none;display:inline-block}
.rn{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{margin-left:auto;font:600 11px var(--mono);letter-spacing:.04em;padding:3px 9px;border-radius:99px;background:var(--surface-2);color:var(--muted);white-space:nowrap}
.badge.ok{background:color-mix(in srgb,var(--gain) 16%,transparent);color:var(--gain)}.badge.bad{background:color-mix(in srgb,var(--mark) 16%,transparent);color:var(--mark)}
.badge.run{background:color-mix(in srgb,var(--link) 16%,transparent);color:var(--link)}
.bar{height:6px;background:var(--surface-2);border-radius:99px;overflow:hidden;margin:8px 0 12px}.bar>i{display:block;height:100%;border-radius:99px}
.kv{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:10px 12px}.kv div{min-width:0}
.k{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.v{font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.down{color:var(--gain)}.up{color:var(--mark)}.flat{color:var(--mark)}
.note{margin-top:10px;font-size:12px;color:var(--muted)}.note.warn,.note.bad{color:var(--mark)}
.tools{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;margin-bottom:10px;font-size:13px;color:var(--muted)}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden}.seg button{border:0;background:transparent;color:var(--text);padding:4px 10px;font:inherit;cursor:pointer}
.seg button.on{background:var(--text);color:var(--surface)}input[type=range]{width:110px;accent-color:var(--link)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:13px}.legend span[data-n]{cursor:pointer;display:inline-flex;align-items:center;gap:6px;user-select:none}.legend .off{opacity:.35}
.chart{position:relative}svg{width:100%;height:auto;display:block}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border-strong);border-radius:8px;padding:7px 10px;font:12px var(--mono);box-shadow:0 6px 18px rgba(6,37,68,.15);display:none;white-space:nowrap}
.grid2{display:grid;grid-template-columns:1fr;gap:14px;margin-top:14px}@media(min-width:900px){.grid2{grid-template-columns:3fr 2fr}}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}
th{position:sticky;top:0;background:var(--surface);color:var(--muted);font:500 12px var(--sans)}th:first-child,td:first-child{text-align:left}td:first-child{font-family:var(--sans)}
.scroll{max-height:360px;overflow:auto}.row{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}
select,.btn,input[type=text]{font:inherit;font-size:13px;color:var(--text);background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:5px 9px;max-width:100%}.btn{cursor:pointer}
.btn.primary{background:var(--navy);color:var(--cream);border-color:var(--navy)}
.empty{color:var(--muted);padding:30px;text-align:center}
#poster-view{display:none}.li #dash-view{display:none}.li #poster-view{display:block}
.pv{display:grid;grid-template-columns:1fr;gap:14px}@media(min-width:960px){.pv{grid-template-columns:minmax(0,640px) 1fr}}
.pv .frame{background:var(--surface-2);border-radius:14px;padding:12px}.pv svg{border-radius:6px;box-shadow:0 10px 30px rgba(6,37,68,.18)}
.form label{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px}.form input[type=text]{width:100%}
.hint{font-size:12px;color:var(--muted);margin-top:12px}
</style></head><body>
<div class="top"><div class="wrap top-in"><div><div class="eyebrow">UltraTiny · Training live</div><h1>Sprachmodell für die NodeMCU<span class="o">.</span></h1></div>
 <span class="modes" id="mode"><button data-v="dash" class="on">Dashboard</button><button data-v="li">LinkedIn-Bild</button></span>
 <div class="st"><span class="dot" id="dot"></span><span id="st"></span></div></div></div>
<div class="wrap"><div id="dash-view">
<div class="runs" id="runs"></div>
<div class="card"><div class="tools">
 <span>Achse <span class="seg" id="scale"><button data-v="log" class="on">log</button><button data-v="lin">linear</button></span></span>
 <span>Bereich <span class="seg" id="range"><button data-v="1" class="on">alles</button><button data-v="0.25">letzte 25 %</button><button data-v="0.1">letzte 10 %</button></span></span>
 <label>Glättung <input type="range" id="smooth" min="0" max="0.98" step="0.02" value="0.6"> <span id="sv" class="num">0.60</span></label>
 <label><input type="checkbox" id="raw" checked> Rohwerte</label>
</div>
<div class="chart"><svg id="c" viewBox="0 0 1000 420" role="img" aria-label="Loss je Schritt"></svg><div class="tip" id="tip"></div></div>
<div class="legend" id="legend"></div></div>
<div class="grid2">
 <div class="card"><div class="row"><h2 style="margin:0">Alle Werte</h2><select id="sel"></select><button class="btn" id="csv">CSV exportieren</button></div>
  <div class="scroll"><table id="vals"></table></div></div>
 <div class="card"><h2>Vergleich der Läufe</h2><div class="scroll"><table id="cmp"></table></div></div>
</div></div>
<div id="poster-view"><div class="pv">
 <div class="frame"><svg id="poster" viewBox="0 0 1080 1080" role="img" aria-label="LinkedIn-Bild"></svg></div>
 <div class="card form"><h2>LinkedIn-Bild (1080 × 1080)</h2>
  <label for="p-title">Titel</label><input type="text" id="p-title" value="Ein Sprachmodell, das in 80 KB RAM passt.">
  <label for="p-sub">Untertitel</label><input type="text" id="p-sub" value="Training auf dem DGX Spark – live, Schritt für Schritt.">
  <label for="p-foot">Fußzeile</label><input type="text" id="p-foot" value="NodeMCU · ESP8266 · 4 × 128 · Kontext 104 · komplett offline">
  <label for="p-run">Lauf</label><select id="p-run"></select>
  <div class="row" style="margin-top:16px"><button class="btn primary" id="png">PNG speichern</button><button class="btn" id="svgdl">SVG speichern</button></div>
  <div class="hint">Das Bild aktualisiert sich mit dem Training. Die Texte sind frei änderbar. Für das PNG nutzt der Browser die Schriften der Seite; falls sie fehlen, eine Systemschrift.</div></div>
</div></div>
</div>
<script>
const COL=["var(--s-a)","var(--s-b)","var(--s-c)","var(--s-d)"];
let D=null,opts={scale:"log",range:1,smooth:0.6,raw:true},hidden=new Set(),sel=null,mode="dash",prun=null;
const $=id=>document.getElementById(id);
const esc=t=>String(t).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const f4=v=>v==null?"–":v.toFixed(4),pc=v=>v==null?"–":(v*100).toFixed(1)+" %";
const kb=v=>v==null?"–":(v/1024).toFixed(0)+" KB",nf=v=>v==null?"–":v.toLocaleString("de");
function dur(s){if(s==null||!isFinite(s))return"–";s=Math.max(0,Math.round(s));const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h?`${h} h ${m} min`:m?`${m} min ${s%60} s`:`${s} s`}
function ema(pts,a){let e=null;return pts.map(p=>(e=e==null?p[1]:a*e+(1-a)*p[1]))}
function rate(pts){const live=pts.filter(p=>p[2]);if(live.length<2)return null;
 const a=live[Math.max(0,live.length-15)],b=live[live.length-1];return b[2]>a[2]?(b[0]-a[0])/(b[2]-a[2]):null}
function trend(pts,sm){if(pts.length<3)return null;const last=pts[pts.length-1][0];let i=pts.length-1;
 while(i>0&&pts[i][0]>last-1000)i--;if(i===pts.length-1)return null;return(sm[sm.length-1]-sm[i])/sm[i]}
function stats(name,r,i){const p=r.points,sm=ema(p,opts.smooth),last=p[p.length-1];
 const total=r.steps?(r.steps+(r.qat_from!=null&&r.qat_steps?r.qat_steps:0)):null;
 const rt=rate(p),step=last?last[0]:0,remain=total&&rt?(total-step)/rt:null;
 const best=p.length?Math.min(...p.map(q=>q[1])):null,tr=trend(p,sm);
 const silent=r.last_seen&&D?D.now-r.last_seen:null;
 const prog=r.result?1:total?Math.min(1,(step+100)/total):null;
 return{name,r,i,last,total,rt,remain,best,tr,sm:sm.length?sm[sm.length-1]:null,silent,prog}}
function badge(s){const r=s.r;if(r.result==="ok")return'<span class="badge ok">fertig · OK</span>';
 if(r.result==="failed")return'<span class="badge bad">Ziele verfehlt</span>';if(r.result==="error")return'<span class="badge bad">Fehler</span>';
 return`<span class="badge run">${esc(r.phase)}</span>`}
function card(s){const r=s.r,c=COL[s.i%COL.length],ev=r.eval;let note="";
 const tr=s.tr==null?"–":`<span class="${s.tr<-0.02?"down":s.tr>0.02?"up":"flat"}">${s.tr<0?"▼":"▲"} ${Math.abs(s.tr*100).toFixed(1)} %</span>`;
 if(r.result==="failed")note=`<div class="note bad">Verfehlt: ${esc(r.failed)}</div>`;
 else if(r.result==="error")note=`<div class="note bad">${esc(r.failed)}</div>`;
 else if(s.silent!=null&&!r.result&&s.silent>Math.max(120,s.rt?300/s.rt:0))note=`<div class="note warn">Seit ${dur(s.silent)} keine neue Zeile – läuft das Training noch?</div>`;
 else if(s.tr!=null&&Math.abs(s.tr)<0.01&&r.phase==="Training")note=`<div class="note warn">Plateau: weniger als 1 % Änderung in 1.000 Schritten.</div>`;
 const evs=ev.demo!=null?`<div><div class="k">demo</div><div class="v">${pc(ev.demo)}</div></div><div><div class="k">held-out</div><div class="v">${pc(ev.chem??ev.heldout)}</div></div>`+
  (ev.kurz!=null?`<div><div class="k">Kurzarbeit</div><div class="v">${pc(ev.kurz)}</div></div>`:ev.refusal!=null?`<div><div class="k">Abweisen</div><div class="v">${pc(ev.refusal)}</div></div>`:`<div><div class="k">Modell</div><div class="v">${kb(r.model_bytes)}</div></div>`):"";
 return`<div class="card"><div class="rh"><span class="sw" style="background:${c}"></span><span class="rn" title="${esc(s.name)}">${esc(s.name)}</span>${badge(s)}</div>
 <div class="bar"><i style="width:${(s.prog??0)*100}%;background:${c}"></i></div>
 <div class="kv"><div><div class="k">Schritt</div><div class="v" title="${s.total?nf(s.total)+" Schritte insgesamt":""}">${s.last?nf(s.last[0]):"–"}${s.total?` <span style="color:var(--muted);font-weight:400">/ ${s.total>=10000?Math.round(s.total/1000)+"k":nf(s.total)}</span>`:""}</div></div>
 <div><div class="k">Tempo</div><div class="v">${s.rt?s.rt.toFixed(1)+" /s":"–"}</div></div><div><div class="k">Rest</div><div class="v">${r.result?"–":dur(s.remain)}</div></div>
 <div><div class="k">Loss</div><div class="v">${f4(s.last&&s.last[1])}</div></div><div><div class="k">geglättet</div><div class="v">${f4(s.sm)}</div></div><div><div class="k">Trend 1k</div><div class="v">${tr}</div></div>
 <div><div class="k">bester</div><div class="v">${f4(s.best)}</div></div><div><div class="k">Beispiele</div><div class="v">${nf(r.data.train_examples)}</div></div>
 <div><div class="k">int8-Verlust</div><div class="v">${r.quant?r.quant[2].toFixed(1)+" pp":"–"}</div></div>${evs}</div>${note}</div>`}
function scaleY(ys,log){const tf=v=>log?Math.log10(Math.max(v,1e-5)):v;let lo=tf(Math.min(...ys)),hi=tf(Math.max(...ys));
 if(log){lo=Math.floor(lo*2)/2;hi=Math.ceil(hi*2)/2}else{lo=0;hi=hi*1.05}if(hi<=lo)hi=lo+1;return{tf,lo,hi}}
function niceStep(span,n){const raw=span/n,mag=10**Math.floor(Math.log10(raw));return[1,2,2.5,5,10].map(m=>m*mag).find(v=>v>=raw)}
function chart(S){const svg=$("c"),W=1000,H=420,L=64,R=18,T=14,B=42;
 const vis=S.filter(s=>!hidden.has(s.name)&&s.r.points.length);
 if(!vis.length){svg.innerHTML='<text x="500" y="210" text-anchor="middle" fill="currentColor" opacity=".6">warte auf Daten …</text>';return}
 const xmax=Math.max(...vis.map(s=>s.r.points[s.r.points.length-1][0]))||1,xmin=opts.range<1?xmax*(1-opts.range):0;
 const series=vis.map(s=>{const pts=s.r.points,sm=ema(pts,opts.smooth);return{s,pts:pts.map((p,j)=>[p[0],p[1],sm[j]]).filter(p=>p[0]>=xmin)}});
 let ys=[];series.forEach(q=>q.pts.forEach(p=>{if(opts.raw)ys.push(p[1]);ys.push(p[2])}));ys=ys.filter(v=>v>0);if(!ys.length)ys=[1];
 const log=opts.scale==="log",{tf,lo,hi}=scaleY(ys,log);
 const X=v=>L+(W-L-R)*(v-xmin)/(xmax-xmin||1),Y=v=>T+(H-T-B)*(hi-tf(v))/(hi-lo);let s="";
 if(log){for(let e=Math.floor(lo);e<=Math.ceil(hi);e++)for(const m of[1,2,5]){const v=m*10**e,y=Math.log10(v);if(y<lo-1e-9||y>hi+1e-9)continue;
  s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--border)"/><text x="${L-8}" y="${Y(v)+4}" text-anchor="end" font-size="11" font-family="var(--mono)" fill="var(--muted)">${+v.toPrecision(2)}</text>`}}
 else for(let i=0;i<=5;i++){const v=lo+(hi-lo)*i/5;s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--border)"/><text x="${L-8}" y="${Y(v)+4}" text-anchor="end" font-size="11" font-family="var(--mono)" fill="var(--muted)">${v.toFixed(2)}</text>`}
 const stp=niceStep(xmax-xmin||1,6);
 for(let v=Math.ceil(xmin/stp)*stp;v<=xmax+1e-9;v+=stp)s+=`<line x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H-B}" stroke="var(--border)" stroke-opacity=".6"/><text x="${X(v)}" y="${H-B+18}" text-anchor="middle" font-size="11" font-family="var(--mono)" fill="var(--muted)">${nf(Math.round(v))}</text>`;
 s+=`<text x="${(W+L)/2}" y="${H-6}" text-anchor="middle" font-size="12" fill="var(--muted)">Schritt</text><text x="14" y="${(H-B)/2}" font-size="12" fill="var(--muted)" transform="rotate(-90 14 ${(H-B)/2})" text-anchor="middle">Loss${log?" (log)":""}</text>`;
 series.forEach(q=>{const c=COL[q.s.i%COL.length],r=q.s.r;
  if(opts.raw&&opts.smooth>0)s+=`<polyline fill="none" stroke="${c}" stroke-opacity=".28" stroke-width="1.2" points="${q.pts.map(p=>X(p[0])+","+Y(p[1])).join(" ")}"/>`;
  s+=`<polyline fill="none" stroke="${c}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" points="${q.pts.map(p=>X(p[0])+","+Y(opts.smooth>0?p[2]:p[1])).join(" ")}"/>`;
  if(r.qat_from!=null&&r.points[r.qat_from]&&r.points[r.qat_from][0]>=xmin){const x=X(r.points[r.qat_from][0]);
   s+=`<line x1="${x}" x2="${x}" y1="${T}" y2="${H-B}" stroke="${c}" stroke-dasharray="4 4"/><text x="${x>W-70?x-5:x+5}" y="${T+12}" font-size="11" fill="${c}" text-anchor="${x>W-70?"end":"start"}">QAT</text>`}});
 s+=`<line id="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="var(--muted)" stroke-opacity=".5" visibility="hidden"/><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent" id="hit"/>`;
 svg.innerHTML=s;const tip=$("tip"),xh=svg.querySelector("#xh"),hit=svg.querySelector("#hit");
 hit.onmousemove=ev=>{const b=svg.getBoundingClientRect(),vx=(ev.clientX-b.left)*W/b.width,step=xmin+(vx-L)/(W-L-R)*(xmax-xmin);
  let rows="",near=null;series.forEach(q=>{let best=null;for(const p of q.pts)if(!best||Math.abs(p[0]-step)<Math.abs(best[0]-step))best=p;
   if(best){near=near??best[0];rows+=`<div><span class="sw" style="background:${COL[q.s.i%COL.length]}"></span> ${esc(q.s.name)}: <b>${best[1].toFixed(4)}</b> <span style="color:var(--muted)">(geglättet ${best[2].toFixed(4)})</span></div>`}});
  if(near==null)return;xh.setAttribute("x1",X(near));xh.setAttribute("x2",X(near));xh.setAttribute("visibility","visible");
  tip.innerHTML=`<div style="color:var(--muted)">Schritt ${nf(near)}</div>`+rows;tip.style.display="block";
  const px=(X(near)/W)*b.width;tip.style.left=Math.max(4,Math.min(px+12,b.width-tip.offsetWidth-4))+"px";tip.style.top="10px"};
 hit.onmouseleave=()=>{tip.style.display="none";xh.setAttribute("visibility","hidden")}}
function legend(S){$("legend").innerHTML=S.map(s=>`<span data-n="${esc(s.name)}" class="${hidden.has(s.name)?"off":""}"><span class="sw" style="background:${COL[s.i%COL.length]}"></span>${esc(s.name)}</span>`).join("")+(S.length>1?'<span style="color:var(--muted)">· Klick blendet aus/ein</span>':"");
 $("legend").querySelectorAll("[data-n]").forEach(e=>e.onclick=()=>{const n=e.dataset.n;hidden.has(n)?hidden.delete(n):hidden.add(n);render()})}
function current(S){return S.find(s=>s.r.last_seen&&!s.r.result)||[...S].reverse().find(s=>s.r.points.length)}
function values(S){const names=S.map(s=>s.name);if(!names.includes(sel)){const cur=current(S);sel=cur?cur.name:names[0]??null}
 $("sel").innerHTML=names.map(n=>`<option ${n===sel?"selected":""}>${esc(n)}</option>`).join("");
 const s=S.find(x=>x.name===sel);if(!s||!s.r.points.length){$("vals").innerHTML='<tr><td class="empty">keine Werte</td></tr>';return}
 const p=s.r.points,sm=ema(p,opts.smooth),q=s.r.qat_from;let t="<tr><th>Schritt</th><th>Loss</th><th>geglättet</th><th>Δ zum Vorwert</th><th>Phase</th></tr>";
 for(let j=p.length-1;j>=0;j--){const d=j?p[j][1]-p[j-1][1]:null;
  t+=`<tr><td style="font-family:var(--mono)">${nf(p[j][0])}</td><td>${p[j][1].toFixed(4)}</td><td>${sm[j].toFixed(4)}</td><td class="${d==null?"":d<0?"down":"up"}">${d==null?"–":(d>0?"+":"")+d.toFixed(4)}</td><td>${q!=null&&j>=q?"QAT":"Training"}</td></tr>`}
 $("vals").innerHTML=t}
function compare(S){if(!S.length){$("cmp").innerHTML='<tr><td class="empty">noch keine Läufe</td></tr>';return}
 const rows=[["Status",s=>s.r.result==="ok"?"OK":s.r.result==="failed"?"Ziele verfehlt":s.r.result==="error"?"Fehler":s.r.phase],
  ["Schritte",s=>s.last?nf(s.last[0]):"–"],["letzter Loss",s=>f4(s.last&&s.last[1])],["bester Loss",s=>f4(s.best)],
  ["float → int8",s=>s.r.quant?`${pc(s.r.quant[0])} → ${pc(s.r.quant[1])}`:"–"],["demo",s=>pc(s.r.eval.demo)],
  ["held-out",s=>pc(s.r.eval.chem??s.r.eval.heldout)],["Kombis (zurückgehalten)",s=>pc(s.r.eval.combo)],
  ["Kurzarbeit",s=>pc(s.r.eval.kurz)],["falsche Fakten",s=>pc(s.r.eval.wrong_fact)],
  ["Abweisen",s=>pc(s.r.eval.refusal)],["falsch abgewiesen",s=>pc(s.r.eval.false_refusal)],
  ["Modell",s=>kb(s.r.model_bytes)],["Budget (Pipeline)",s=>s.r.budget_ok==null?"–":s.r.budget_ok?"OK":"FAIL"],
  ["Beispiele",s=>nf(s.r.data.train_examples)]];
 let t="<tr><th></th>"+S.map(s=>`<th><span class="sw" style="background:${COL[s.i%COL.length]}"></span> ${esc(s.name.replace(/^.*-(s\d+)$/,"$1"))}</th>`).join("")+"</tr>";
 rows.forEach(([k,fn])=>t+=`<tr><td>${k}</td>${S.map(s=>`<td>${fn(s)}</td>`).join("")}</tr>`);$("cmp").innerHTML=t}
/* LinkedIn poster: 1080x1080 SVG in the Caravan screenprint inks (navy ground, cream, mint, orange). */
function wrapText(t,max){const w=t.split(/\s+/),out=[];let l="";for(const x of w){if((l+" "+x).trim().length>max&&l){out.push(l);l=x}else l=(l+" "+x).trim()}if(l)out.push(l);return out}
function poster(S){const names=S.filter(s=>s.r.points.length).map(s=>s.name);
 if(!names.includes(prun)){const c=current(S);prun=c?c.name:null}
 $("p-run").innerHTML=names.map(n=>`<option ${n===prun?"selected":""}>${esc(n)}</option>`).join("");
 const s=S.find(x=>x.name===prun),N="#062544",CR="#FBEED0",MI="#A5DBC6",OR="#ED9B20",MU="#A3B5AD";
 const F="Archivo, 'Helvetica Neue', Arial, sans-serif",M="'JetBrains Mono', Menlo, Consolas, monospace";
 let g=`<rect width="1080" height="1080" fill="${N}"/>`;
 g+=`<text x="72" y="104" font-family="${M}" font-size="22" letter-spacing="3" fill="${MI}">ULTRATINY · LIVE-TRAINING</text>`;
 g+=`<rect x="72" y="126" width="56" height="8" fill="${OR}"/>`;
 const tl=wrapText($("p-title").value,26);tl.slice(0,3).forEach((l,i)=>g+=`<text x="72" y="${208+i*68}" font-family="${F}" font-weight="800" font-size="60" fill="${CR}">${esc(l)}</text>`);
 const sy=208+Math.min(tl.length,3)*68-12;g+=`<text x="72" y="${sy+18}" font-family="${F}" font-size="28" fill="${MU}">${esc($("p-sub").value)}</text>`;
 const cx=72,cw=936,cy=sy+70,ch=380;g+=`<rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" rx="18" fill="#0B3050"/>`;
 if(s){const p=s.r.points,sm=ema(p,0.6),xmax=p[p.length-1][0]||1,ys=sm.filter(v=>v>0),{tf,lo,hi}=scaleY(ys,true);
  const L=cx+70,R=cx+cw-28,T=cy+34,B=cy+ch-52,X=v=>L+(R-L)*v/xmax,Y=v=>T+(B-T)*(hi-tf(v))/(hi-lo);
  for(let e=Math.floor(lo);e<=Math.ceil(hi);e++){const v=10**e;if(e<lo-1e-9||e>hi+1e-9)continue;
   g+=`<line x1="${L}" x2="${R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#17496F"/><text x="${L-12}" y="${Y(v)+7}" text-anchor="end" font-family="${M}" font-size="18" fill="${MU}">${+v.toPrecision(1)}</text>`}
  const stp=niceStep(xmax,4);for(let v=0;v<=xmax+1e-9;v+=stp)g+=`<text x="${X(v)}" y="${B+34}" text-anchor="middle" font-family="${M}" font-size="18" fill="${MU}">${nf(Math.round(v))}</text>`;
  const pts=p.map((q,j)=>[X(q[0]),Y(sm[j])]);
  g+=`<polygon points="${L},${B} ${pts.map(q=>q.join(",")).join(" ")} ${pts[pts.length-1][0]},${B}" fill="${MI}" fill-opacity=".12"/>`;
  g+=`<polyline fill="none" stroke="${MI}" stroke-width="5" stroke-linejoin="round" stroke-linecap="round" points="${pts.map(q=>q.join(",")).join(" ")}"/>`;
  const e=pts[pts.length-1];g+=`<circle cx="${e[0]}" cy="${e[1]}" r="10" fill="${OR}"/><circle cx="${e[0]}" cy="${e[1]}" r="18" fill="none" stroke="${OR}" stroke-opacity=".4" stroke-width="3"/>`;
  g+=`<text x="${L}" y="${cy+26}" font-family="${M}" font-size="17" fill="${MU}">LOSS (LOG) JE TRAININGSSCHRITT</text>`;
  const st=stats(s.name,s.r,s.i),first=p[0][1],ev=s.r.eval;
  const tiles=ev.demo!=null?[["DEMO-FRAGEN",pc(ev.demo)],["UNGESEHENE FRAGEN",pc(ev.chem??ev.heldout)],["LOSS",`${first.toFixed(1).replace(".",",")} → ${(+st.last[1].toPrecision(2)).toString().replace(".",",")}`]]
   :[["LOSS",`${first.toFixed(1).replace(".",",")} → ${(+st.last[1].toPrecision(2)).toString().replace(".",",")}`],["SCHRITTE",st.total?`${nf(st.last[0])} / ${nf(st.total)}`:nf(st.last[0])],["TRAININGSBEISPIELE",nf(s.r.data.train_examples)]];
  const ty=cy+ch+46;tiles.forEach((t,i)=>{const x=72+i*316;
   g+=`<text x="${x}" y="${ty}" font-family="${M}" font-size="17" letter-spacing="1.5" fill="${MU}">${t[0]}</text><text x="${x}" y="${ty+52}" font-family="${F}" font-weight="800" font-size="${Math.min(46,Math.floor(290/(t[1].length*0.6)))}" fill="${i===0?OR:CR}">${esc(t[1])}</text>`})}
 else g+=`<text x="540" y="${cy+ch/2}" text-anchor="middle" font-family="${F}" font-size="28" fill="${MU}">warte auf Daten …</text>`;
 g+=`<line x1="72" x2="1008" y1="1000" y2="1000" stroke="#17496F" stroke-width="2"/><text x="72" y="1040" font-family="${M}" font-size="19" fill="${MI}">${esc($("p-foot").value)}</text>`;
 $("poster").innerHTML=g}
function render(){if(!D)return;$("st").textContent=D.status;$("dot").className="dot"+(D.connected?" on":"");
 let S=Object.entries(D.runs).map(([n,r])=>[n,r]);
 const live=S.some(([n,r])=>r.last_seen&&!r.result);
 /* Hidden: logs that ended in an error before training (nothing to show), and logs of earlier
    attempts that ended in an error while another run is live. */
 S=S.filter(([n,r])=>!(r.result==="error"&&(!r.points.length||(live&&!r.last_seen)))).map(([n,r],i)=>stats(n,r,i));
 if(mode==="li"){poster(S);return}
 $("runs").innerHTML=S.length?S.map(card).join(""):'<div class="card empty">Noch keine Läufe gefunden.</div>';
 chart(S);legend(S);values(S);compare(S)}
function csv(){if(!D)return;let c="run,step,loss,phase\n";Object.entries(D.runs).forEach(([n,r])=>r.points.forEach((p,j)=>c+=`${n},${p[0]},${p[1]},${r.qat_from!=null&&j>=r.qat_from?"qat":"train"}\n`));save(new Blob([c],{type:"text/csv"}),"ultratiny-loss.csv")}
function save(blob,name){const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
function svgText(){return'<?xml version="1.0" encoding="UTF-8"?>'+new XMLSerializer().serializeToString($("poster")).replace("<svg ",'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" ')}
function png(){const img=new Image();img.onload=()=>{const c=document.createElement("canvas");c.width=2160;c.height=2160;const x=c.getContext("2d");x.drawImage(img,0,0,2160,2160);c.toBlob(b=>save(b,"ultratiny-training.png"),"image/png")};
 img.src="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(svgText())}
function seg(id,key,num){$(id).querySelectorAll("button").forEach(b=>b.onclick=()=>{$(id).querySelectorAll("button").forEach(x=>x.classList.remove("on"));b.classList.add("on");opts[key]=num?+b.dataset.v:b.dataset.v;render()})}
seg("scale","scale",false);seg("range","range",true);
$("mode").querySelectorAll("button").forEach(b=>b.onclick=()=>{$("mode").querySelectorAll("button").forEach(x=>x.classList.remove("on"));b.classList.add("on");mode=b.dataset.v;document.body.classList.toggle("li",mode==="li");render()});
$("smooth").oninput=e=>{opts.smooth=+e.target.value;$("sv").textContent=opts.smooth.toFixed(2);render()};
$("raw").onchange=e=>{opts.raw=e.target.checked;render()};$("sel").onchange=e=>{sel=e.target.value;render()};$("csv").onclick=csv;
["p-title","p-sub","p-foot"].forEach(id=>$(id).oninput=render);$("p-run").onchange=e=>{prun=e.target.value;render()};
$("png").onclick=png;$("svgdl").onclick=()=>save(new Blob([svgText()],{type:"image/svg+xml"}),"ultratiny-training.svg");
async function tick(){try{D=await (await fetch("data")).json();render()}catch(e){$("st").textContent="Viewer nicht erreichbar";$("dot").className="dot"}}
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
    print(f"Training-Dashboard: {url}  (Strg-C beendet)")
    threading.Thread(target=follow, args=(cmd, state, stdin), daemon=True).start()
    if not a.no_browser:
        webbrowser.open(url)
    last = ""
    try:
        while True:
            snap = state.snapshot()
            parts = [f"{k}: {r['phase']}, Schritt {r['points'][-1][0]} Loss {r['points'][-1][1]:.4f}"
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
