<img width="200" height="264" alt="photo_2026-10-21_04-43-45" src="https://github.com/user-attachments/assets/443f4eb5-a254-45ff-86d5-7f82e52edab0" />

# Text CAN communication between the cluster and the radio, reverse-engineered

Put your own text on the centre display of a **Škoda Fabia Mk1 (6Y) MaxiDot** instrument cluster, from a laptop and
a USB CAN adapter. No radio needed: the program assumes the role of the radio.

```
 HELLO
 WORLD             two rows of 10 cells: capitals, Ä Ö Ü, arrows and a few symbols
```

- A small **GUI** (`python -m maxidot`) with a live preview, a palette of every character the font has, alignment,
  and scrolling for text longer than the display.
- A tiny **Python library** (`maxidot.FisLink`) if you want to drive it from your own program, and a speedometer
  example.
- The **protocol, written down**: [docs/PROTOCOL.md](docs/PROTOCOL.md) (CAN ids, the transport, the registration
  handshake, the message format, timing) and [docs/FONT.md](docs/FONT.md) (which byte shows which glyph).

It was reverse-engineered by watching a real Škoda Symphony radio talk to the cluster. The display link turns out to be
a small conversation with the cluster (setup, acknowledged packets, a reply), not a one-way broadcast, which is why
simply replaying captured frames does not work.

## Status

Works on the one cluster it was developed on: **Škoda part 6Y0 920 843 D (facelift MaxiDot), in the car**, with a
CANable adapter (SLCAN firmware) on Windows 11 and Python 3.12. Other clusters, cars and adapters are untested; the
protocol document says exactly what was verified and what is guesswork.

The display refreshes about **4 times a second**; that limit is in the cluster (see PROTOCOL.md, section 5.4).

## What you need

- The cluster, connected to the car OR (untested) powered (ignition +, permanent +, ground on the black 8-pin connector) and its **comfort CAN** wired to
  your adapter: CAN-H and CAN-L on connector T32a pins 9 and 10.
- A CAN adapter that speaks SLCAN, e.g. a CANable, set to 100 kbit/s in normal mode with its 120 Ω termination **off**.
  (The comfort CAN is a low-speed fault-tolerant bus; each module terminates itself.)
- **The real radio unplugged or switched off.** Two radios on one display do not mix.
- Python 3.9+ with Tkinter (included with the python.org installers; on Debian/Ubuntu `sudo apt install python3-tk`).

```
pip install -r requirements.txt
```

## Use

GUI:

```
python -m maxidot
```

Press **Connect** (about 5 seconds: it starts the radio heartbeat and registers with the cluster), type into the two
rows, press **Send**. Closing the program or pressing Disconnect makes the display go blank.

Library:

```python
import time
from maxidot import FisLink

with FisLink() as link:                  # finds a CANable by its USB id; or FisLink(port="COM6")
    link.show_rows("HELLO", "WORLD")     # rows of up to 10 cells; text goes through the font encoder
    time.sleep(5)                        # the text stays while the link is open
```

`encode()` maps text to the display font: it upper-cases, keeps `Ä Ö Ü`, turns `ß` into `SS` and strips other accents
(there is no Czech or Polish lettering in this font). Details in [docs/FONT.md](docs/FONT.md).

Speedometer demo (simulated drive, or real speeds on stdin):

```
python examples/speedo.py
```

## Tests

The tests run without hardware, against a fake cluster that answers like the real one:

```
python -m unittest discover -s tests
```

## Gotchas

- Only one program can open the adapter's serial port at a time (close the GUI before running a script).
- **Do not use python-can's `slcan` interface for this.** On the CANable clone used here, its bitrate setup leaves
  the adapter receiving but never transmitting, with no error. `maxidot/slcan.py` talks SLCAN directly.
- If connecting fails: is the cluster powered, is the real radio off, is the adapter at 100 kbit/s?

## Safety and legal

- This sends frames on a vehicle bus. It only touches the display of the comfort CAN and nothing else, but anything
  that sends CAN frames can have side effects. Use it on the bench or at your own risk, **never while driving**, and do
  not use it on a bus you share with safety-critical systems.
- It does not touch the immobilizer, the odometer or any security feature, and it is not meant for that.
- Not affiliated with or endorsed by Škoda, Volkswagen, VDO/Siemens or any other manufacturer; all names are their
  owners' trademarks and are used only to say which hardware this works with.
- Provided as is, without warranty. See [LICENSE](LICENSE).
- The protocol was worked out by observing hardware its author owns. This is not legal advice: check the rules where
  you live before relying on it.

## License

Copyright (C) 2026 the maxidot-fis contributors.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License ([LICENSE](LICENSE))
for details. The documentation in `docs/` is covered by the same license.
