# MaxiDot display protocol (Škoda Fabia Mk1 / 6Y, MaxiDot cluster)

How the instrument cluster's centre display (the "MaxiDot", VW's *Zweitdisplay*) is driven over the
comfort CAN bus, worked out by watching a Škoda Symphony radio talk to the cluster and then replacing the
radio with a program. Everything here was tested on **one** cluster; other clusters and cars may differ.

Confidence tags: **[verified]** reproduced on hardware by our own sender, **[observed]** seen in real radio
traffic but not independently tested, **[inferred]** an interpretation that was not tested.

## 1. Test setup

- Cluster: VDO/Siemens MaxiDot, Škoda part 6Y0 920 843 D (facelift), on a bench. Comfort CAN-H / CAN-L are on
  connector T32a pins 9 / 10 (Škoda workshop manual). Power on the black 8-pin connector: pin 5 = ignition +,
  pin 7 = permanent +, pin 8 = ground.
- Radio (captures only): Škoda Symphony, CAN version, coded for a secondary display. Its display/CAN pins are on
  the 20-pin Mini-ISO connector (pin 8 = CAN-H, pin 9 = CAN-L).
- Adapter: CANable with SLCAN firmware (USB 16D0:117E), 100 kbit/s, normal (acknowledging) mode, its 120 Ω
  termination **off**.
- Everything below happens on the comfort CAN with standard 11-bit identifiers.

## 2. The bus

The comfort CAN is 100 kbit/s low-speed *fault-tolerant* CAN (idle: CAN-H ≈ 0 V, CAN-L ≈ 5 V). There is no 120 Ω
termination across the pair; each module terminates itself, so keep the adapter's termination off. With the cluster
alone on the bus it sends about 20 periodic frames (ids 0x151 … 0x659); they are unrelated to the display.

## 3. CAN identifiers used for the display

| ID | sender | purpose |
|---|---|---|
| `0x439` | radio | presence heartbeat (section 4) |
| `0x4D9` | radio | connection setup request |
| `0x2E8` | cluster | connection setup response |
| `0x6B9` | radio | radio's data channel: parameters, data packets, acks, disconnect |
| `0x699` | cluster | cluster's data channel |
| `0x40C` | cluster | byte 0 mirrors whether it sees a radio: `0x19` present, `0x00` absent |

`0x400`, `0x401`, `0x408`, `0x40C` and `0x439` look like network-management frames at "`0x400` + node address";
if so the radio is node `0x39`, which is also the first byte of the setup response, and the cluster is node `0x08`,
the first byte of the setup request **[inferred]**.

## 4. Presence heartbeat **[verified]**

The radio sends `0x439` with data `00 01 00 00 00 00` every ~230 ms for as long as it is "on".

- About a second after it starts, the cluster's `0x40C` byte 0 changes from `00` to `19`.
- Without the heartbeat the cluster rejects display messages, and when the heartbeat stops the display blanks
  shortly after. Text therefore stays on the display purely because the heartbeat keeps running; a real radio sends
  nothing else while idle.
- `00 11 00 00 00 00` was seen while the radio's display was off, probably its standby value **[inferred]**.
- Every test started the heartbeat first; whether registration works without it was not tested.

## 5. Transport **[verified]**

The radio and cluster talk over a connection-oriented transport in the style of VW's TP 2.0 (same opcode family:
`C0`/`D0` setup, `A0`/`A1` parameters, `0`–`3` data opcodes, `B`x acks, `A8` disconnect). It is not literally TP 2.0:
the setup uses the ids above with 3-byte frames, and messages have no length header.

### 5.1 Frames

| Frame | ID | Data | Meaning |
|---|---|---|---|
| setup request | `0x4D9` | `08 C0 B9` | `C0` = request. `B9` is the low byte of the radio's data-channel id (0x6B9) |
| setup response | `0x2E8` | `39 D0 99` | `D0` = accepted. `99` is the low byte of the cluster's id (0x699) |
| parameters | `0x6B9` | `A0 04 82 84 82 B2` | `04` = block size 4 (ack every 4 packets); the rest are timer values (replayed verbatim) |
| parameters response | `0x699` | `A1 04 8A 85 43 94` | |
| data packet | either | `(op<<4 \| seq)` + up to 7 payload bytes | `seq` starts at 0 for every message |
| ack | either | `B0 \| next_seq` | e.g. `B4` after seq 3 |
| disconnect | `0x6B9` | `A8` | |

Data opcodes: `2` = more packets follow, `0` = more follow **and an ack is required** (used on every 4th packet),
`1` = last packet, ack required. A message of 37 bytes is therefore sent as `20 21 22 03 24 15` (packet 3 has
opcode 0 because it ends the block; packet 5 is the last).

### 5.2 One message

1. The radio sends the packets; after packet 3 (opcode 0) the cluster acks `B4`.
2. After the last packet the cluster acks (`B6` for a 37-byte message).
3. About 217 ms later the cluster sends **its own reply message** on `0x699` as a data packet, e.g. `10 27 SS 01`.
4. The radio acks it (`B1`). Only now will the cluster accept the next message.

A session may carry several messages back to back; it is closed with `A8`.

### 5.3 Reply codes

| Reply | Meaning |
|---|---|
| `10 27 SS 01` | content message accepted |
| `10 23 SS 01` | registration message accepted (`SS` = assigned session byte) |
| `10 35` | init message accepted |
| `10 2B SS 03` | **rejected**: stale session byte, no radio heartbeat, a validated byte changed, or wrong length |

The cluster still acks the packets of a rejected message; only the reply tells you.

### 5.4 Timing

Measured on the test cluster (30–80 updates per row, all accepted):

| setup | data phase | cluster reply wait | per update |
|---|---|---|---|
| one session per update, 9 ms packet gap | 94 ms (+64 ms connect) | 211 ms | 399 ms (2.5/s) |
| persistent connection, 9 ms gap | 84 ms | 230 ms | 323 ms (3.0/s) |
| persistent, 3 ms gap | 30 ms | 216 ms | 250 ms (4.0/s) |
| persistent, 1 ms gap | 17 ms | 230 ms | 249 ms (4.0/s) |
| persistent, 0 ms gap | 14 ms | 235 ms | 250 ms (4.0/s) |

**The cluster handles one message per ~250 ms.** Sending faster only makes it wait longer before replying, so the
total stays at 250 ms: the display refreshes at about 4 Hz whatever you do. Pipelining (starting the next message
before the previous reply has been acked) fails: the cluster never acks the second message. A real radio spaces
packets by ~9 ms; 3 ms and even 0 ms are accepted.

### 5.5 Example (a real radio, volume change, session byte `0E`)

```
radio   0x4D9  08 C0 B9                    setup request
cluster 0x2E8  39 D0 99                    setup response
radio   0x6B9  A0 04 82 84 82 B2           parameters
cluster 0x699  A1 04 8A 85 43 94           parameters response
radio   0x6B9  20 09 0E 57 0F 02 00 00     packet 0
radio   0x6B9  21 00 00 20 41 4D 31 20     packet 1
radio   0x6B9  22 20 20 20 20 20 57 0F     packet 2
radio   0x6B9  03 03 00 00 0A 00 20 20     packet 3 (ack required)
cluster 0x699  B4                          ack
radio   0x6B9  24 56 4F 4C 20 20 38 20     packet 4
radio   0x6B9  15 20 08                    packet 5, last
cluster 0x699  B6                          ack
cluster 0x699  10 27 0E 01                 reply: accepted
radio   0x6B9  B1                          ack of the reply
radio   0x6B9  A8                          disconnect
```
The display then shows ` AM1` on the top row and `VOL  8` on the bottom row.

## 6. Registration (the radio's boot sequence) **[verified]**

The cluster only accepts display messages from a radio that has registered since the last time the cluster saw it.

1. Start the heartbeat and wait about a second (we wait 3 s).
2. **Connection 1:** the init message `15 39 00 01 01` (one packet, `10 15 39 00 01 01`). Reply `10 35`. Disconnect.
   Its meaning is unknown.
3. **Connection 2:** the message `02 80 39 20` followed by the ASCII text `Radiodaten` (two packets, `20 …`, `11 …`).
   Reply `10 23 SS 01`: **`SS` is a session byte assigned by the cluster.** It increments with every registration
   (we have seen 06, 09, 0E, 0F, 10, 1E … 26); you cannot choose it.
4. In the same connection: a content message with all-space rows (as a real radio does; we have not tested
   whether it is needed), then disconnect.
5. From now on every content message carries that session byte.

The session byte is checked on every message. A stale value, for example from before the radio was power-cycled,
gets `10 2B SS 03` and nothing is drawn (this cost us hours before we understood it).

## 7. Content message (sets the two rows) **[verified]**

37 bytes, sent as six packets. Offsets are into the message payload (the 7 bytes after each packet's header byte):

| offset | length | field | notes |
|---|---|---|---|
| 0 | 7 | header | `09 SS 57 0F 02 00 00`; `SS` = session byte |
| 7 | 2 | `00 00` | |
| 9 | 10 | **top row** | cells 0–9: label (5) + preset digit (1) + 4 more cells |
| 19 | 2 | `57 0F` | flags (meaning unknown) |
| 21 | 1 | `03` | |
| 22 | 4 | `00 00 0A 00` | |
| 26 | 10 | **bottom row** | cells 0–9: 1 cell + text (8) + 1 cell |
| 36 | 1 | `08` | |

- **Both rows are 10 cells wide** and every cell can be used: we put a different marker in each of the 20 cells
  and all showed. (A real radio only fills the label, the preset digit and the 8-character station text, which is
  why they look like separate fields.)
- Everything except the session byte and the two rows is **validated**: changing any other byte, or sending more
  or fewer than 37 bytes, gets `10 2B SS 03`.
- Each byte is one cell (see [FONT.md](FONT.md)); undefined codes are skipped, not drawn as blanks.
- A real radio uses this one message for everything it shows: label + preset (` FM2 5`), station name
  (`RADIOPSR`), frequency (`  103.6 `), volume (` VOL 10 `), band, and a settings page.

## 8. Minimal sender

```
heartbeat thread: every 230 ms send 0x439 = 00 01 00 00 00 00
sleep 1-3 s

connect()                                   # 0x4D9 08 C0 B9 -> 0x2E8 D0 ; 0x6B9 A0... -> 0x699 A1
send_message(15 39 00 01 01)                # expect reply 35
disconnect()                                # 0x6B9 A8

connect()
reply = send_message(02 80 39 20 "Radiodaten")   # expect reply[0] == 0x23
session = reply[1]
send_message(content(session, blank, blank))
disconnect()

loop:                                       # one open connection, as many messages as you like
    reply = send_message(content(session, top, bottom))   # reply[0] == 0x27 means drawn
    # reconnect on any error; close the connection (A8) when idle for ~0.6 s

send_message(payload):
    for each packet: send; after opcode 0 or 1 wait for the ack B(seq+1)
    wait for the cluster's reply packet on 0x699; ack it with B(its seq + 1)
```

`maxidot/transport.py` and `maxidot/link.py` are this, in about 150 lines of Python.

## 9. What is not known

- What the init message `15 39 00 01 01` and the registration text mean to the cluster.
- The flag bytes (`57 0F`), `00 00 0A 00`, `02 00 00` and `08`. They are validated but never varied in real traffic;
  they may select icons or text attributes.
- Whether other message types exist (CD changer, phone, navigation, traffic announcements, several lines).
- A real radio also sends `0x661` (`00`/`03`, about once a second). It was not needed.
- What happens if a real radio and an emulator share the bus.
- Whether other clusters (other Škoda, VW or Seat models of that era) speak the same dialect.

## 10. Practical notes

- Use a CAN adapter in normal mode at 100 kbit/s, termination off. With only the adapter and the cluster on the
  bus, the cluster must be able to acknowledge your frames.
- **python-can's `slcan` interface did not work for sending** on our CANable clone: its bitrate setup sends a blank
  SLCAN command and a second "open", after which the adapter received normally but never transmitted. Everything
  looked successful (no errors) and nothing reached the bus. The code in this repository talks SLCAN directly
  instead.
- Frames may arrive in batches if your serial reader waits for a full buffer; read what is available.
- Only one program can have the adapter's serial port open at a time.

## 11. How it was found

Captures of a real radio: change the station, band or volume and look at which CAN ids change. One id (`0x6B9`)
carried readable ASCII (`FM1`, `RADIOPSR`, `VOL`) in a burst of packets; the packet opcodes then gave away the
transport, and the cluster's replies on `0x699` / `0x2E8` showed it was a conversation, not a broadcast. Replaying
captured bytes without the conversation does nothing, which is why a plain "record and replay" fails.
