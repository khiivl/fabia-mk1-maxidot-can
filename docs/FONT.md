# MaxiDot font

What each byte in a row shows. Determined by sending every code and photographing the display, so the shapes below
are descriptions of what was seen; the display is a dot-matrix with its own font. `maxidot.font.encode()` does this
mapping for you.

## What is there

| Bytes | Shows |
|---|---|
| `0x20`–`0x5E` | Standard ASCII: space, `! " # $ % & ' ( ) * + , - . / 0-9 : ; < = > ? @ A-Z [ \ ] ^` |
| `0x5F` | **Ä** |
| `0x60` | **Ö** |
| `0x61` | **Ü** |
| `0x62` | `’` (a raised apostrophe/acute mark) |
| `0x63` / `0x64` | `.` / `,` (same as the ASCII ones) |
| `0x66` | `_` underscore (low) |
| `0x67` | a small `v` / check mark `✓` |
| `0x68` + `0x69` | arrow shaft + arrow head: together one long arrow `➔` (two cells) |
| `0x6B` | `°` |
| `0x6D` / `0x6E` | `*` / `>` (same as the ASCII ones) |
| `0x70` | `▶` |
| `0x71` | a lowercase `i` (info) |
| `0x18` `0x19` `0x1A` `0x1B` | `↑` `↓` `→` `←` |
| `0x1D` | a double arrow, up and down |
| `0x1E` / `0x1F` | `▲` / `▼` |

## What is not there

- **No lowercase letters.** The slots where `a`–`z` would be hold Ä Ö Ü and symbols; use capitals.
- **No `ß`, `ä`, `ö`, `ü`, and no Czech, Polish or other accented letters.** There are only the three capitals
  Ä Ö Ü. `encode()` turns `ß` into `SS`, `ä ö ü` into `Ä Ö Ü` and strips other accents (`Č` → `C`).

## Blanks and skipped codes

- **Defined blanks** (take a cell, draw nothing): `0x20`, `0x1C`, `0x65`, `0x6A`, `0x6C`.
- **Undefined codes are skipped entirely**: they take no cell, so the characters after them shift left.
  Seen skipped: `0x01`–`0x17`, `0x72`–`0x7F`. Codes `0x80`–`0xFF` draw nothing (whether they are skipped or blank
  was not checked). `0x00` and `0x6F` were not tested.

Skipping is easy to trip over: if a row has fewer visible characters than cells, an undefined byte in the middle
makes the rest slide left. Stick to the codes in the first table.

## How it was mapped

Eight consecutive codes per screen with a screen number in the top row, photographed; then four codes per screen
separated by `-` (so a blank can't shift the position), photographed. The tool for that is a few lines on top of
`FisLink.show_rows` if you want to repeat it for another cluster.
