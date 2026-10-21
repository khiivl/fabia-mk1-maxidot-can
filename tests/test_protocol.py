# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

import unittest

from fake_cluster import FakeCluster
from maxidot import FisLink, content_payload
from maxidot import transport as tp

# A real radio message captured from a Fabia: label " AM1 ", volume shown as " VOL 10 ", session byte 0x0E.
REAL_PAYLOAD = bytes.fromhex(
    "09 0E 57 0F 02 00 00  00 00  20 41 4D 31 20 20 20 20 20 20  57 0F 03 00 00 0A 00  20 20 56 4F 4C 20 31 30 20 20  08"
)
REAL_TOP = b" AM1      "
REAL_BOTTOM = b"  VOL 10  "


class LayoutTests(unittest.TestCase):
    def test_content_payload_matches_a_real_capture(self):
        self.assertEqual(content_payload(0x0E, REAL_TOP, REAL_BOTTOM), REAL_PAYLOAD)
        self.assertEqual(len(REAL_PAYLOAD), 37)

    def test_packet_opcodes_match_the_real_capture(self):
        # real capture of that message: packets 20 21 22 03 24 15 (03 = ack needed at the block boundary)
        frames = tp.chunk_message(REAL_PAYLOAD)
        self.assertEqual([f[2][0] for f in frames], [0x20, 0x21, 0x22, 0x03, 0x24, 0x15])
        self.assertEqual(frames[0][2], bytes.fromhex("20090E570F020000"))
        self.assertEqual(frames[5][2], bytes.fromhex("152008"))

    def test_registration_messages_are_packetised_like_the_radio_does(self):
        self.assertEqual([f[2][0] for f in tp.chunk_message(bytes.fromhex("1539000101"))], [0x10])
        reg = tp.chunk_message(bytes.fromhex("02803920") + b"Radiodaten")
        self.assertEqual([f[2][0] for f in reg], [0x20, 0x11])
        self.assertEqual(reg[0][2], bytes.fromhex("2002803920526164"))


class LinkTests(unittest.TestCase):
    def make(self):
        fake = FakeCluster(session=0x2A)
        return fake, FisLink(adapter=fake, warmup=0, gap=0)

    def test_registration_learns_the_session_and_sends_a_heartbeat(self):
        fake, link = self.make()
        with link:
            self.assertEqual(link.session, 0x2A)
            self.assertTrue(any(cid == tp.ID_HEARTBEAT and d == bytes.fromhex("000100000000") for cid, d in fake.sent))

    def test_show_rows_sends_the_expected_message(self):
        fake, link = self.make()
        with link:
            self.assertTrue(link.show_rows("HELLO", "WORLD"))
            want = content_payload(0x2A, b"HELLO     ", b"WORLD     ")
            self.assertEqual(fake.messages[-1], want)

    def test_streaming_reuses_one_connection(self):
        fake, link = self.make()
        with link:
            before = fake.setups                      # the two registration connections
            for i in range(5):
                self.assertTrue(link.show_rows("N", str(i)))
            self.assertEqual(fake.setups, before + 1)
            link.stream_close()
            self.assertTrue(link.show_rows("N", "X"))
            self.assertEqual(fake.setups, before + 2)

    def test_one_session_per_update_mode(self):
        fake, link = self.make()
        with link:
            before = fake.setups
            self.assertTrue(link.show_rows("A", "1", stream=False))
            self.assertTrue(link.show_rows("A", "2", stream=False))
            self.assertEqual(fake.setups, before + 2)

    def test_cluster_rejection_is_reported(self):
        fake, link = self.make()
        with link:
            bad = bytearray(content_payload(0x2A, b" " * 10, b" " * 10))
            bad[22] = 0x55                            # change a validated constant byte
            self.assertFalse(link.stream_send(bytes(bad)))

    def test_text_is_encoded_with_the_font(self):
        fake, link = self.make()
        with link:
            link.show_rows("Ä", "ß ✓")
            msg = fake.messages[-1]
            self.assertEqual(msg[9], 0x5F)            # top row cell 0 = Ä
            self.assertEqual(msg[26:30], b"SS \x67")  # bottom row starts at byte 26: ß -> SS, space, ✓


if __name__ == "__main__":
    unittest.main()
