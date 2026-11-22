"""Shared helpers for the on-device scripts (serial console per contracts/serial-console.md).

Requires pyserial for real boards (`uv sync` in training/ installs it as a dev dependency).
Run the scripts from training/ with `uv run python ../tools/<script>.py --port /dev/ttyUSB0 ...`.
Works with the NodeMCU (ESP8266, default board) and the legacy ESP32: both use the same console
protocol and the RTS/DTR auto-reset circuit of the dev boards.
Besides a serial port, a Device can talk to QEMU over TCP (TcpLink) or to a local process such
as `utiny-host --console` (ExecLink).
"""

from __future__ import annotations

import codecs
import re
import select
import socket
import subprocess
import time

PROMPT = "\r\n> "


class SerialLink:
    def __init__(self, port: str, baud: int = 115200):
        import serial  # pyserial

        self.ser = serial.Serial(port, baud, timeout=0.05)

    def read(self) -> bytes:
        return self.ser.read(4096)

    def write(self, data: bytes) -> None:
        self.ser.write(data)
        self.ser.flush()

    def close(self) -> None:
        self.ser.close()


class TcpLink:
    """Serial console exposed on TCP, e.g. QEMU with UT_QEMU_TCP (tools/qemu_run.sh)."""

    def __init__(self, host: str, port: int, connect_timeout: float = 10.0):
        end = time.time() + connect_timeout
        while True:
            try:
                self.sock = socket.create_connection((host, port), timeout=2)
                break
            except OSError:
                if time.time() > end:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(0.05)

    def read(self) -> bytes:
        try:
            data = self.sock.recv(4096)
        except TimeoutError:
            return b""
        if data == b"":
            raise EOFError("connection closed")
        return data

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        self.sock.close()


class ExecLink:
    """Console of a local process on stdin/stdout, e.g. `utiny-host --model M --console`."""

    def __init__(self, cmd: list[str]):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self) -> bytes:
        assert self.proc.stdout is not None
        ready, _, _ = select.select([self.proc.stdout], [], [], 0.05)
        if not ready:
            return b""
        data = self.proc.stdout.read1(4096)
        if data == b"":
            raise EOFError("process exited")
        return data

    def write(self, data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class Device:
    def __init__(self, port: str | None = None, baud: int = 115200, timeout: float = 60.0,
                 link=None):  # fmt: skip
        self.link = link if link is not None else SerialLink(port, baud)
        self.ser = getattr(self.link, "ser", None)  # pyserial object for real boards
        self.timeout = timeout
        self.buf = ""
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def close(self) -> None:
        self.link.close()

    def _read(self) -> str:
        data = self.link.read()
        return self._dec.decode(data) if data else ""

    def read_until(self, marker: str, timeout: float | None = None) -> str:
        end = time.time() + (timeout or self.timeout)
        while marker not in self.buf:
            if time.time() > end:
                raise TimeoutError(f"timeout waiting for {marker!r}; got {self.buf[-200:]!r}")
            self.buf += self._read()
        idx = self.buf.index(marker) + len(marker)
        out, self.buf = self.buf[:idx], self.buf[idx:]
        return out

    def drain(self, seconds: float = 0.3) -> str:
        end = time.time() + seconds
        out = ""
        while time.time() < end:
            out += self._read()
        self.buf = ""
        return out

    def reset(self) -> str:
        """Toggle EN via RTS (standard dev-board auto-reset) and return the boot banner."""
        if self.ser is None:
            raise RuntimeError("reset needs a serial port")
        self.ser.dtr = False
        self.ser.rts = True
        time.sleep(0.1)
        self.ser.rts = False
        self.buf = ""
        return self.read_until(PROMPT, timeout=15)

    def type(self, text: str, char_delay: float = 0.0) -> None:
        if char_delay <= 0:
            self.link.write(text.encode("utf-8"))
            return
        for ch in text:
            self.link.write(ch.encode("utf-8"))
            time.sleep(char_delay)

    def command(self, cmd: str) -> str:
        self.drain(0.1)
        self.type(cmd + "\r")
        return self.read_until(PROMPT)

    def ask(self, question: str, char_delay: float = 0.0) -> str:
        """Type a question, press Enter, return the streamed answer text."""
        self.drain(0.1)
        self.type(question, char_delay)
        self.type("\r")
        raw = self.read_until(PROMPT)
        # raw = echoed question + "\r\n" + answer + "\r\n> "
        answer = raw.split("\r\n", 1)[1] if "\r\n" in raw else raw
        return answer[: -len(PROMPT)] if answer.endswith(PROMPT) else answer

    def info(self) -> dict:
        txt = self.command("/info")
        out: dict = {"raw": txt}
        m = re.search(r"erstes Zeichen nach (\d+) ms, ([\d.]+) Zeichen/s", txt)
        if m:
            out["first_char_ms"] = int(m.group(1))
            out["chars_per_s"] = float(m.group(2))
        m = re.search(r"Freier Heap: (\d+)", txt)
        if m:
            out["free_heap"] = int(m.group(1))
        return out
