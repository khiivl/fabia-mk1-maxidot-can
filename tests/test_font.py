# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

import unittest

from maxidot.font import encode, pad


class FontTests(unittest.TestCase):
    def test_umlauts_have_their_own_cells(self):
        self.assertEqual(encode("ÄÖÜ äöü"), bytes([0x5F, 0x60, 0x61, 0x20, 0x5F, 0x60, 0x61]))

    def test_sharp_s_becomes_ss(self):
        self.assertEqual(encode("Straße"), b"STRASSE")

    def test_czech_accents_are_stripped(self):
        self.assertEqual(encode("ČÁRKY ěščřžýáíé"), b"CARKY ESCRZYAIE")

    def test_lowercase_is_uppercased(self):
        self.assertEqual(encode("hello"), b"HELLO")

    def test_arrows_and_symbols(self):
        self.assertEqual(encode("↑↓←→▲▼"), bytes([0x18, 0x19, 0x1B, 0x1A, 0x1E, 0x1F]))
        self.assertEqual(encode("➔"), bytes([0x68, 0x69]))
        self.assertEqual(encode("°"), bytes([0x6B]))

    def test_underscore_has_its_own_cell(self):
        self.assertEqual(encode("A_B"), bytes([0x41, 0x66, 0x42]))

    def test_missing_characters_become_question_marks(self):
        self.assertEqual(encode("€"), b"?")

    def test_pad(self):
        self.assertEqual(pad(b"AB", 6), b"AB    ")
        self.assertEqual(pad(b"AB", 6, "right"), b"    AB")
        self.assertEqual(pad(b"AB", 6, "center"), b"  AB  ")
        self.assertEqual(pad(b"ABCDEFGH", 4), b"ABCD")


if __name__ == "__main__":
    unittest.main()
