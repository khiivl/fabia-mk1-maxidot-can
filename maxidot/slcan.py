# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""Raw SLCAN client for CANable-style USB adapters (slcan firmware).

Why not python-can's ``slcan`` backend? While setting the bitrate it sends a blank command and then a
second "open" command. On the CANable clone this project was developed with, that left the adapter
receiving normally but silently never transmitting. Talking SLCAN directly (close, set bitrate, open)
avoids the problem.
"""
import threading
import time

import serial
from serial.tools import list_ports

CANABLE_VID, CANABLE_PID = 0x16D0, 0x117E

_KEEP, _DROP = 50000, 25000  # rolling buffer: keep at most _KEEP frames, drop the oldest _DROP when full


def find_adapter():
    """Serial port of the first CANable (USB 16D0:117E) found, or None."""
    for p in list_ports.comports():
        if p.vid == CANABLE_VID and p.pid == CANABLE_PID:
            return p.device
    return None


class FrameBuffer:
    """Thread-safe rolling buffer of received (can_id, data) frames, addressed by absolute index."""

    def __init__(self):
        self.lock = threading.Lock()
        self._frames = []
        self._base = 0

    def _append(self, can_id, data):
        with self.lock:
            self._frames.append((can_id, bytes(data)))
            if len(self._frames) > _KEEP:
                del self._frames[:_DROP]
                self._base += _DROP

    def mark(self):
        """Index of the next frame to arrive; pass it to frames_since() / wait_for()."""
        with self.lock:
            return self._base + len(self._frames)

    def frames_since(self, mark):
        """-> (frames received since mark, new mark)."""
        with self.lock:
            start = max(0, mark - self._base)
            return self._frames[start:], self._base + len(self._frames)

    def wait_for(self, mark, can_id, pred, timeout):
        """First frame with this CAN id that satisfies pred(data) received after mark, else None."""
        end = time.perf_counter() + timeout
        pos = mark
        while True:
            new, pos = self.frames_since(pos)
            for cid, data in new:
                if cid == can_id and pred(data):
                    return data
            if time.perf_counter() >= end:
                return None
            time.sleep(0.002)


class Slcan(FrameBuffer):
    """Opens the adapter at 100 kbit/s (SLCAN code S3) in normal mode and collects received frames."""

    def __init__(self, port, bitrate_code="S3", baud=115200, settle=2.0, verbose=False):
        super().__init__()
        self.verbose = verbose
        self.wlock = threading.Lock()
        self.error = None
        self._stop = False
        self.ser = serial.Serial(port, baudrate=baud, timeout=0.02)
        time.sleep(settle)  # some adapters reset when the port opens
        for cmd in ("C", bitrate_code, "O"):
            self.ser.write(cmd.encode() + b"\r")
            self.ser.flush()
            time.sleep(0.05)
            self.ser.read(4096)
        self._thread = threading.Thread(target=self._rx, daemon=True)
        self._thread.start()

    def _rx(self):
        buf = bytearray()
        while not self._stop:
            try:
                # read(1) returns as soon as a byte arrives; in_waiting then picks up the rest. (read(256)
                # would wait for 256 bytes or the timeout and delay every frame by up to 20 ms.)
                chunk = self.ser.read(self.ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                self.error = e
                return
            if not chunk:
                continue
            buf.extend(chunk)
            while b"\r" in buf:
                i = buf.index(b"\r")
                line = bytes(buf[:i]).decode("ascii", "ignore")
                del buf[: i + 1]
                if line.startswith("t") and len(line) >= 5:
                    try:
                        can_id = int(line[1:4], 16)
                        dlc = int(line[4])
                        data = bytes.fromhex(line[5 : 5 + dlc * 2])
                    except ValueError:
                        continue
                    self._append(can_id, data)

    def tx(self, can_id, data):
        """Transmit one standard (11-bit) frame."""
        data = bytes(data)
        line = f"t{can_id:03X}{len(data):X}{data.hex().upper()}\r".encode()
        with self.wlock:
            self.ser.write(line)
            self.ser.flush()
        if self.verbose:
            print(f"TX {can_id:03X}  {data.hex(' ').upper()}")

    def close(self):
        self._stop = True
        time.sleep(0.05)
        try:
            self.ser.write(b"C\r")
        finally:
            self.ser.close()
