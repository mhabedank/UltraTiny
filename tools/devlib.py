"""Shared helpers for the on-device scripts (serial console per contracts/serial-console.md).

Requires pyserial (`uv sync` in training/ installs it as a dev dependency). Run the scripts
from training/ with `uv run python ../tools/<script>.py --port /dev/ttyUSB0 ...`.
"""

from __future__ import annotations

import re
import time

PROMPT = "\r\n> "


class Device:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 60.0):
        import serial  # pyserial

        self.ser = serial.Serial(port, baud, timeout=0.05)
        self.timeout = timeout
        self.buf = ""

    def close(self) -> None:
        self.ser.close()

    def _read(self) -> str:
        data = self.ser.read(4096)
        return data.decode("utf-8", errors="replace") if data else ""

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
        self.ser.dtr = False
        self.ser.rts = True
        time.sleep(0.1)
        self.ser.rts = False
        self.buf = ""
        return self.read_until(PROMPT, timeout=15)

    def type(self, text: str, char_delay: float = 0.0) -> None:
        if char_delay <= 0:
            self.ser.write(text.encode("utf-8"))
            return
        for ch in text:
            self.ser.write(ch.encode("utf-8"))
            self.ser.flush()
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
