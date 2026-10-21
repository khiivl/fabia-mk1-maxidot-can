# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""The transport layer between "radio" and cluster (a VW TP 2.0-style session; see docs/PROTOCOL.md).

``c`` below is any object with ``tx(can_id, data)``, ``mark()`` and ``wait_for(mark, can_id, pred, timeout)``,
normally a :class:`maxidot.slcan.Slcan`.
"""
import time

ID_SETUP_REQUEST = 0x4D9    # radio -> cluster
ID_SETUP_RESPONSE = 0x2E8   # cluster -> radio
ID_RADIO = 0x6B9            # radio's data channel
ID_CLUSTER = 0x699          # cluster's data channel
ID_HEARTBEAT = 0x439        # radio presence heartbeat

SETUP_REQUEST = bytes.fromhex("08C0B9")
PARAMS_REQUEST = bytes.fromhex("A004828482B2")   # channel parameters, block size 4
DEFAULT_GAP = 0.009                              # what a real radio uses between data packets


def chunk_message(payload):
    """Split a message into transport packets. -> [(opcode nibble, sequence, 8-byte-or-shorter frame)].

    Packets carry 7 payload bytes. Opcode 2 = more packets follow, 0 = more follow and an ack is needed
    (every 4th packet = the block size), 1 = last packet, ack needed.
    """
    chunks = [payload[i : i + 7] for i in range(0, len(payload), 7)]
    out = []
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        op = 1 if last else (0 if (i + 1) % 4 == 0 else 2)
        out.append((op, i & 0xF, bytes([(op << 4) | (i & 0xF)]) + chunk))
    return out


def connect(c):
    """Open a session: connection setup, then channel parameters. -> True if the cluster answered both."""
    m = c.mark()
    c.tx(ID_SETUP_REQUEST, SETUP_REQUEST)
    if c.wait_for(m, ID_SETUP_RESPONSE, lambda d: len(d) >= 2 and d[1] == 0xD0, 0.5) is None:
        return False
    time.sleep(0.005)
    m = c.mark()
    c.tx(ID_RADIO, PARAMS_REQUEST)
    return c.wait_for(m, ID_CLUSTER, lambda d: d and d[0] == 0xA1, 0.5) is not None


def disconnect(c, pause=0.03):
    c.tx(ID_RADIO, bytes([0xA8]))
    time.sleep(pause)


def send_data(c, payload, gap=DEFAULT_GAP):
    """Send a message's packets, honouring the cluster's acks.
    -> (mark taken before the last packet, or None on failure, seconds spent)"""
    start = time.perf_counter()
    m_last = None
    for op, seq, frame in chunk_message(payload):
        time.sleep(gap)
        if op in (0, 1):
            m_last = c.mark()
        c.tx(ID_RADIO, frame)
        if op in (0, 1):
            want = 0xB0 | ((seq + 1) & 0xF)
            if c.wait_for(m_last, ID_CLUSTER, lambda d, w=want: d and d[0] == w, 0.5) is None:
                return None, time.perf_counter() - start
    return m_last, time.perf_counter() - start


def wait_reply(c, m_last, gap=DEFAULT_GAP):
    """Wait for the cluster's reply message and ack it. -> (reply payload or None, seconds waited)"""
    start = time.perf_counter()
    reply = c.wait_for(m_last, ID_CLUSTER, lambda d: d and (d[0] >> 4) in (0, 1, 2, 3), 1.5)
    waited = time.perf_counter() - start
    if reply is None:
        return None, waited
    time.sleep(gap)
    c.tx(ID_RADIO, bytes([0xB0 | (((reply[0] & 0xF) + 1) & 0xF)]))
    return reply[1:], waited


def send_message(c, payload, gap=DEFAULT_GAP):
    """Send one message inside an open session and return the cluster's reply payload (or None)."""
    m_last, _ = send_data(c, payload, gap)
    if m_last is None:
        return None
    reply, _ = wait_reply(c, m_last, gap)
    return reply
