# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""Speedometer on the MaxiDot (simulated drive, or real speeds from stdin).

    python examples/speedo.py                  demo drive
    python examples/speedo.py --loop           repeat the demo until Ctrl+C
    python examples/speedo.py --stdin          read speeds in km/h, one number per line, from stdin
    options: --unit kmh|mph   --max 200 (full scale of the bar)   --hold 5 (seconds to keep the last value)

Top row = bar graph (10 cells = full scale, '=' full cell, '-' half cell); bottom row = speed, unit, trend arrow.
The cluster takes ~250 ms per message, so the display refreshes about 4 times a second; the loop always sends
the latest value and only when what is shown has changed.
"""
import math
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from maxidot import FisLink  # noqa: E402

ARGS = sys.argv[1:]


def opt(name, default):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


UNIT = opt("--unit", "kmh").lower()
VMAX = float(opt("--max", 200))
HOLD = float(opt("--hold", 5))
CONV = 0.621371 if UNIT == "mph" else 1.0
UNIT_TXT = "MPH" if UNIT == "mph" else "KM/H"


def render(v, trend):
    """-> (top row, bottom row) as strings for a speed v in display units."""
    cell = (VMAX * CONV) / 10.0
    full = int(v // cell)
    half = (v - full * cell) >= cell / 2
    bar = "=" * min(full, 10) + ("-" if half and full < 10 else "")
    arrow = {1: "▲", -1: "▼"}.get(trend, " ")
    return bar, f"{int(round(v)):>3} {UNIT_TXT.ljust(4)} {arrow}"


class Source:
    """Latest speed in km/h, from a simulated drive or stdin."""

    def __init__(self):
        self.v = 0.0
        self.finished = False

    def start(self):
        threading.Thread(target=self._stdin if "--stdin" in ARGS else self._sim, daemon=True).start()

    def _stdin(self):
        for line in sys.stdin:
            try:
                self.v = max(0.0, float(line.strip()))
            except ValueError:
                pass
        self.finished = True

    def _sim(self):
        targets = [0, 45, 45, 80, 120, 150, 150, 110, 60, 95, 130, 130, 70, 30, 0]
        while True:
            for tgt in targets:
                while abs(self.v - tgt) > 0.5:
                    dt = 0.05
                    accel = 14.0 if tgt > self.v else 22.0     # km/h per second
                    self.v += math.copysign(min(accel * dt, abs(tgt - self.v)), tgt - self.v)
                    self.v = max(0.0, self.v + random.uniform(-0.15, 0.15))
                    time.sleep(dt)
                for _ in range(40):
                    self.v = max(0.0, self.v + random.uniform(-0.2, 0.2))
                    time.sleep(0.05)
            if "--loop" not in ARGS:
                self.finished = True
                return


def main():
    src = Source()
    with FisLink() as link:
        print(f"Registered (session {link.session:02X}). Speedo running ({UNIT_TXT}). Ctrl+C to stop.")
        src.start()
        shown, prev_v, prev_t = None, 0.0, time.time()
        sent = bad = 0
        try:
            while True:
                v = src.v * CONV
                key = (int(round(v)), int(v // ((VMAX * CONV) / 10.0)))
                if key != shown:
                    now = time.time()
                    dv = (v - prev_v) / max(now - prev_t, 0.05)
                    trend = 1 if dv > 3 else (-1 if dv < -3 else 0)
                    top, bottom = render(v, trend)
                    ok = link.show_rows(top, bottom)
                    shown, prev_v, prev_t = key, v, now
                    sent += 1
                    bad += not ok
                    print(f"\r{v:6.1f} {UNIT_TXT}   sent {sent}  rejected {bad}", end="", flush=True)
                elif src.finished:
                    break
                else:
                    time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        if src.finished:
            time.sleep(HOLD)
    print("\nDone.")


if __name__ == "__main__":
    main()
