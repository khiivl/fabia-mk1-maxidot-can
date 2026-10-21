# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""A fake MaxiDot cluster: answers the transport protocol like the real one so the tests can run offline."""
from maxidot.slcan import FrameBuffer

ID_SETUP_REQUEST, ID_SETUP_RESPONSE, ID_RADIO, ID_CLUSTER = 0x4D9, 0x2E8, 0x6B9, 0x699


class FakeCluster(FrameBuffer):
    def __init__(self, session=0x2A):
        super().__init__()
        self.session = session
        self.sent = []        # every (can_id, data) the program transmitted
        self.messages = []    # every completed transport message received
        self.setups = 0       # connection setups seen
        self._buf = b""

    # --- the adapter interface FisLink uses --------------------------------------------------------------
    def tx(self, can_id, data):
        data = bytes(data)
        self.sent.append((can_id, data))
        if can_id == ID_SETUP_REQUEST and len(data) >= 2 and data[1] == 0xC0:
            self.setups += 1
            self._buf = b""
            self._append(ID_SETUP_RESPONSE, bytes.fromhex("39D099"))
        elif can_id == ID_RADIO and data:
            self._radio_frame(data)

    def close(self):
        pass

    # --- cluster behaviour -------------------------------------------------------------------------------
    def _radio_frame(self, d):
        op, seq = d[0] >> 4, d[0] & 0xF
        if d[0] == 0xA0:
            self._append(ID_CLUSTER, bytes.fromhex("A1048A854394"))
        elif op in (0, 1, 2, 3):
            self._buf += d[1:]
            if op in (0, 1):
                self._append(ID_CLUSTER, bytes([0xB0 | ((seq + 1) & 0xF)]))
            if op == 1:
                msg, self._buf = self._buf, b""
                self.messages.append(msg)
                self._append(ID_CLUSTER, bytes([0x10]) + self._reply(msg))

    def _reply(self, msg):
        if msg == bytes.fromhex("1539000101"):
            return b"\x35"
        if msg.startswith(bytes.fromhex("02803920")):
            return bytes([0x23, self.session, 0x01])
        # Content message: the real cluster rejects it unless the length is 37, the session byte matches and
        # every constant byte is exactly what a real radio sends (57 0F 02 00 00 / 00 00 / 57 0F 03 00 00 0A 00 / 08).
        ok = (
            len(msg) == 37 and msg[0] == 0x09 and msg[1] == self.session
            and msg[2:7] == bytes.fromhex("570F020000") and msg[7:9] == b"\x00\x00"
            and msg[19:26] == bytes.fromhex("570F0300000A00") and msg[36] == 0x08
        )
        return bytes([0x27, self.session, 0x01]) if ok else bytes([0x2B, self.session, 0x03])
