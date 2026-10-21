# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""FisLink: play the radio toward the MaxiDot cluster and put text on its two rows.

    from maxidot import FisLink

    with FisLink() as link:                    # finds the CANable, runs the heartbeat, registers
        link.show_rows("HELLO", "WORLD")       # two rows of 10 cells
        time.sleep(5)                          # text stays while the link is open

Closing the link stops the heartbeat and the cluster blanks the display. The real radio must be off the bus.
"""
import threading
import time

from . import transport as tp
from .font import encode, pad
from .slcan import Slcan, find_adapter

ROW = 10                                      # cells per row
HEARTBEAT = bytes.fromhex("000100000000")
HEARTBEAT_PERIOD = 0.23
IDLE_CLOSE = 0.6                              # drop an idle connection after this many seconds
INIT_MESSAGE = bytes.fromhex("1539000101")
REGISTER_MESSAGE = bytes.fromhex("02803920") + b"Radiodaten"


def content_payload(session, top, bottom):
    """The 37-byte message that sets the two display rows. top / bottom: exactly 10 bytes each.

    Layout and the meaning of every field: docs/PROTOCOL.md. All other bytes are validated by the cluster.
    """
    assert len(top) == ROW and len(bottom) == ROW
    return (
        bytes([0x09, session, 0x57, 0x0F, 0x02, 0x00, 0x00])
        + b"\x00\x00" + bytes(top)
        + b"\x57\x0f\x03\x00\x00\x0a\x00" + bytes(bottom)
        + b"\x08"
    )


def _row(value):
    return pad(encode(value) if isinstance(value, str) else bytes(value), ROW, "left")


class FisLink:
    def __init__(self, port=None, *, adapter=None, warmup=3.0, gap=0.003, verbose=False):
        """port: serial port of the CANable (default: auto-detect). adapter: inject a ready-made adapter
        object (used by the tests). warmup: seconds of heartbeat before registering. gap: seconds between
        data packets for updates (a real radio uses 0.009; 0.003 works and is as fast as the cluster allows)."""
        if adapter is None:
            port = port or find_adapter()
            if not port:
                raise RuntimeError("No CANable found (USB 16D0:117E). Plug it in or pass port='COM6' / '/dev/ttyACM0'.")
            adapter = Slcan(port, verbose=verbose)
        self.c = adapter
        self.warmup = warmup
        self.gap = gap
        self.session = None
        self._hb_stop = threading.Event()
        self._lock = threading.RLock()
        self._stream_open = False
        self._stream_last = 0.0
        self._hb_thread = None

    # -- lifecycle ---------------------------------------------------------------------------------------
    def __enter__(self):
        self._hb_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._hb_thread.start()
        try:
            time.sleep(self.warmup)  # let the cluster notice the "radio" (its 0x40C byte 0 turns 0x19)
            self._register()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self.stream_close()
        except Exception:
            pass
        self._hb_stop.set()
        time.sleep(0.05)
        self.c.close()

    def _heartbeat(self):
        while not self._hb_stop.is_set():
            self.c.tx(tp.ID_HEARTBEAT, HEARTBEAT)
            if self._lock.acquire(blocking=False):
                try:
                    self.stream_idle_check()
                finally:
                    self._lock.release()
            time.sleep(HEARTBEAT_PERIOD)

    def _register(self):
        """Boot sequence of the radio: init message, then the "Radiodaten" message which hands us a session id."""
        with self._lock:
            if not tp.connect(self.c):
                raise RuntimeError("Cluster did not answer the connection setup (is it powered, is the real radio off?)")
            if tp.send_message(self.c, INIT_MESSAGE) is None:
                raise RuntimeError("Init message was not answered")
            tp.disconnect(self.c)
            if not tp.connect(self.c):
                raise RuntimeError("Second connection setup failed")
            reply = tp.send_message(self.c, REGISTER_MESSAGE)
            if not reply or reply[0] != 0x23:
                raise RuntimeError(f"Registration refused: {reply!r}")
            self.session = reply[1]
            # like the real radio: a blank content message in the same connection, then disconnect
            tp.send_message(self.c, content_payload(self.session, b" " * ROW, b" " * ROW))
            tp.disconnect(self.c)

    # -- display -----------------------------------------------------------------------------------------
    def show_rows(self, top, bottom="", *, stream=True, retries=1):
        """Show two rows of up to 10 cells each (str or bytes; str is run through the font encoder).

        stream=True keeps one connection open between updates (fast, about 4 updates/s);
        stream=False does a full session per update (about 2.5 updates/s). -> True if the cluster accepted it."""
        payload = content_payload(self.session, _row(top), _row(bottom))
        for _ in range(retries + 1):
            if stream:
                if self.stream_send(payload):
                    return True
            elif self._oneshot(payload):
                return True
        return False

    def _oneshot(self, payload):
        with self._lock:
            self.stream_close()
            if not tp.connect(self.c):
                return False
            reply = tp.send_message(self.c, payload, self.gap)
            tp.disconnect(self.c)
            return bool(reply) and reply[0] == 0x27

    def stream_send(self, payload):
        """Send a content payload over a persistent connection. True if the cluster answered 'accepted' (0x27)."""
        with self._lock:
            self.stream_idle_check()
            for _ in range(2):  # one reconnect on any hiccup
                if not self._stream_open:
                    if not tp.connect(self.c):
                        continue
                    self._stream_open = True
                m_last, _ = tp.send_data(self.c, payload, self.gap)
                if m_last is not None:
                    reply, _ = tp.wait_reply(self.c, m_last, self.gap)
                    if reply is not None:
                        self._stream_last = time.time()
                        return reply[0] == 0x27
                self.stream_close()
            return False

    def stream_close(self):
        with self._lock:
            if self._stream_open:
                tp.disconnect(self.c)
                self._stream_open = False

    def stream_idle_check(self):
        with self._lock:
            if self._stream_open and time.time() - self._stream_last > IDLE_CLOSE:
                self.stream_close()
