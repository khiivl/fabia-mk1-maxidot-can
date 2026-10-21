# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""The MaxiDot font: text -> display bytes (see docs/FONT.md for the glyph map)."""
import unicodedata

# Characters that are not plain ASCII but exist in the font, and the byte that shows them.
GLYPHS = {
    "Ä": 0x5F, "Ö": 0x60, "Ü": 0x61, "ä": 0x5F, "ö": 0x60, "ü": 0x61,
    "’": 0x62, "_": 0x66, "✓": 0x67, "°": 0x6B, "▶": 0x70, "ℹ": 0x71,
    "↑": 0x18, "↓": 0x19, "→": 0x1A, "←": 0x1B, "↕": 0x1D, "▲": 0x1E, "▼": 0x1F,
}
LONG_ARROW = "➔"  # two cells: shaft (0x68) + head (0x69)


def encode(text):
    """str -> bytes for the display.

    The font has capitals only: letters are upper-cased, Ä Ö Ü (and ä ö ü) have their own cells, ß becomes SS,
    other accents are stripped (Č -> C), and anything else that is missing becomes '?'.
    """
    out = bytearray()
    for ch in text:
        if ch in GLYPHS:
            out.append(GLYPHS[ch])
        elif ch == "ß":
            out += b"SS"
        elif ch == LONG_ARROW:
            out += bytes([0x68, 0x69])
        else:
            base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)).upper()
            for c in base:
                out.append(ord(c) if 0x20 <= ord(c) <= 0x5E else 0x3F)
    return bytes(out)


# How each byte looks in the GUI preview (approximation of the real glyphs).
DISPLAY_CHARS = {
    0x18: "↑", 0x19: "↓", 0x1A: "→", 0x1B: "←", 0x1C: " ", 0x1D: "↕", 0x1E: "▲", 0x1F: "▼",
    0x5F: "Ä", 0x60: "Ö", 0x61: "Ü", 0x62: "’", 0x63: ".", 0x64: ",", 0x65: " ", 0x66: "_",
    0x67: "✓", 0x68: "─", 0x69: "►", 0x6A: " ", 0x6B: "°", 0x6C: " ", 0x6D: "*", 0x6E: ">",
    0x70: "▶", 0x71: "ℹ",
}


def glyph_char(b):
    if 0x20 <= b <= 0x5E:
        return chr(b)
    return DISPLAY_CHARS.get(b, "?")


def pad(data, width, mode="left"):
    """Cut to width and pad with spaces. mode: left (text starts at the left), center, right."""
    data = bytes(data)[:width]
    if mode == "right":
        return data.rjust(width, b" ")
    if mode == "center":
        return data.center(width, b" ")
    return data.ljust(width, b" ")
