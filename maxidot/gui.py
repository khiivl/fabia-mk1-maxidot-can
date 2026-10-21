# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""MaxiDot Text - a small GUI for putting text on the Škoda Fabia Mk1 MaxiDot display.

    python -m maxidot

The computer plays the radio (heartbeat + registration, see docs/PROTOCOL.md) and sends the two display rows
(10 cells each). Click glyphs in the palette to insert them at the cursor; the preview shows what the cluster
receives. Rows longer than 10 cells scroll. The real radio must be unplugged or off, and no other program
may have the adapter's serial port open.
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .font import encode, glyph_char, pad
from .link import ROW, FisLink
from .slcan import find_adapter

PALETTE = [
    ("Letters", [chr(c) for c in range(0x41, 0x5B)]),
    ("Digits", list("0123456789")),
    ("Punctuation", list(" !\"#$%&'()*+,-./:;<=>?@[\\]^_")),
    ("German Umlauts", ["Ä", "Ö", "Ü"]),
    ("Symbols", ["’", "✓", "°", "▶", "ℹ", "➔"]),
    ("Arrows", ["↑", "↓", "←", "→", "↕", "▲", "▼"]),
]

BLANK = b" " * ROW


class Worker(threading.Thread):
    """Owns the FisLink. The GUI posts commands; only the newest display job is kept."""

    def __init__(self, ui_queue):
        super().__init__(daemon=True)
        self.ui = ui_queue
        self.cv = threading.Condition()
        self.cmd = None
        self.job = None
        self.link = None

    def post_cmd(self, *cmd):
        with self.cv:
            self.cmd = cmd
            self.cv.notify()

    def post_job(self, kind, top=BLANK, bottom=BLANK, scroll_top=None, scroll_bottom=None):
        """kind: show | scroll | stop. For scroll, scroll_top / scroll_bottom hold the full bytes of a row
        that should scroll (None = that row stays static)."""
        with self.cv:
            self.job = (kind, top, bottom, scroll_top, scroll_bottom)
            self.cv.notify()

    def _interrupted(self):
        with self.cv:
            return self.cmd is not None or self.job is not None

    def run(self):
        while True:
            with self.cv:
                if self.cmd is None and self.job is None:
                    self.cv.wait(timeout=0.3)
                cmd, self.cmd = self.cmd, None
                job = None
                if cmd is None:
                    job, self.job = self.job, None
            if cmd is not None:
                if not self._do_cmd(cmd):
                    return
            elif job is not None:
                self._do_job(job)

    def _close_link(self):
        if self.link is not None:
            try:
                self.link.close()
            except Exception:
                pass
            self.link = None

    def _do_cmd(self, cmd):
        if cmd[0] == "connect":
            if self.link is not None:
                return True
            link = None
            try:
                link = FisLink(port=cmd[1] or None)
                link.__enter__()
                self.link = link
                self.ui.put(("connected", link.session))
            except Exception as e:
                if link is not None:
                    try:
                        link.close()
                    except Exception:
                        pass
                self.link = None
                self.ui.put(("failed", f"{type(e).__name__}: {e}"))
        elif cmd[0] == "disconnect":
            self._close_link()
            self.ui.put(("disconnected",))
        elif cmd[0] == "quit":
            self._close_link()
            return False
        return True

    def _pause(self, secs):
        end = time.time() + secs
        while time.time() < end and not self._interrupted():
            time.sleep(0.05)

    def _do_job(self, job):
        kind, top, bottom, scroll_top, scroll_bottom = job
        if kind == "stop":
            return
        if self.link is None:
            self.ui.put(("sent", False, "Not connected"))
            return
        if kind == "show":
            ok = self.link.show_rows(top, bottom)
            self.ui.put(("sent", ok, "Sent - cluster accepted" if ok else "Cluster did not accept it"))
        elif kind == "scroll":
            def stream(b):
                return b" " * (ROW - 1) + b + b" " * (ROW - 1) if b is not None else None

            ts, bs = stream(scroll_top), stream(scroll_bottom)
            n_top = len(ts) - ROW + 1 if ts is not None else 0
            n_bot = len(bs) - ROW + 1 if bs is not None else 0
            self.ui.put(("sent", True, "Scrolling... (press Stop or send something else)"))
            t = 0
            while not self._interrupted():
                row1 = ts[t % n_top : t % n_top + ROW] if ts is not None else top
                row2 = bs[t % n_bot : t % n_bot + ROW] if bs is not None else bottom
                if not self.link.show_rows(row1, row2):
                    self.ui.put(("sent", False, "Cluster stopped answering"))
                    return
                wrapped = (ts is not None and t % n_top == n_top - 1) or (bs is not None and t % n_bot == n_bot - 1)
                t += 1
                if wrapped:
                    self._pause(0.8)


class App:
    def __init__(self, root):
        self.root = root
        root.title("MaxiDot Text")
        root.resizable(False, False)
        self.ui_q = queue.Queue()
        self.worker = Worker(self.ui_q)
        self.worker.start()
        self.connected = False
        self.connecting = False
        self.live_after = None
        self._poll_id = None
        self.target = None

        self.var_port = tk.StringVar(value=find_adapter() or "")
        self.var_top = tk.StringVar(value="HELLO")
        self.var_bottom = tk.StringVar(value="WORLD")
        self.var_raw = tk.StringVar()
        self.var_align = tk.StringVar(value="left")
        self.var_live = tk.BooleanVar(value=False)
        self.var_scroll = tk.BooleanVar(value=True)
        self.var_hint = tk.StringVar(value="Click a glyph to insert it at the cursor.")
        self.var_warn = tk.StringVar()
        self.var_bytes = tk.StringVar()
        self.var_status = tk.StringVar(value="Not connected")

        self._build()
        for v in (self.var_top, self.var_bottom, self.var_raw, self.var_align):
            v.trace_add("write", lambda *a: self.on_change())
        self.redraw()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def _build(self):
        pad8 = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad8)
        ttk.Label(top, text="Adapter port").pack(side="left")
        ttk.Entry(top, textvariable=self.var_port, width=10).pack(side="left", padx=6)
        self.btn_conn = ttk.Button(top, text="Connect", command=self.toggle_connect)
        self.btn_conn.pack(side="left")
        self.lbl_status = tk.Label(top, textvariable=self.var_status, fg="#777777", anchor="w")
        self.lbl_status.pack(side="left", padx=12)

        self.canvas = tk.Canvas(self.root, width=388, height=150, bg="#1b1b1b", highlightthickness=0)
        self.canvas.pack(**pad8)

        form = ttk.Frame(self.root)
        form.pack(fill="x", **pad8)
        ttk.Label(form, text=f"Top row ({ROW})").grid(row=0, column=0, sticky="w")
        self.ent_top = ttk.Entry(form, textvariable=self.var_top, width=34, font=("Consolas", 13))
        self.ent_top.grid(row=0, column=1, sticky="we", padx=6, pady=2)
        ttk.Label(form, text=f"Bottom row ({ROW})").grid(row=1, column=0, sticky="w")
        self.ent_bottom = ttk.Entry(form, textvariable=self.var_bottom, width=34, font=("Consolas", 13))
        self.ent_bottom.grid(row=1, column=1, sticky="we", padx=6, pady=2)
        ttk.Label(form, text="Raw hex (bottom)").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.var_raw, width=34).grid(row=2, column=1, sticky="we", padx=6, pady=2)
        self.target = self.ent_bottom
        self.ent_top.bind("<FocusIn>", lambda e: setattr(self, "target", self.ent_top))
        self.ent_bottom.bind("<FocusIn>", lambda e: setattr(self, "target", self.ent_bottom))
        self.ent_top.bind("<Return>", lambda e: self.send())
        self.ent_bottom.bind("<Return>", lambda e: self.send())

        opts = ttk.Frame(self.root)
        opts.pack(fill="x", **pad8)
        ttk.Label(opts, text="Align").pack(side="left")
        for mode in ("left", "center", "right"):
            ttk.Radiobutton(opts, text=mode, value=mode, variable=self.var_align).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Live (send as I type)", variable=self.var_live).pack(side="left", padx=12)
        ttk.Checkbutton(opts, text=f"Scroll rows longer than {ROW}", variable=self.var_scroll,
                        command=self.redraw).pack(side="left")

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad8)
        ttk.Button(btns, text="Send", command=self.send).pack(side="left")
        ttk.Button(btns, text="Clear display", command=self.clear).pack(side="left", padx=6)
        ttk.Button(btns, text="Stop scroll", command=lambda: self.worker.post_job("stop")).pack(side="left")

        pal = ttk.LabelFrame(self.root, text="Characters the font can show (click to insert)")
        pal.pack(fill="x", **pad8)
        for title, chars in PALETTE:
            row = ttk.Frame(pal)
            row.pack(fill="x", padx=4, pady=2)
            ttk.Label(row, text=title, width=22).pack(side="left")
            holder = ttk.Frame(row)
            holder.pack(side="left")
            for i, ch in enumerate(chars):
                shown = "␣" if ch == " " else ch
                b = tk.Button(holder, text=shown, width=3, font=("Segoe UI Symbol", 11),
                              command=lambda ch=ch: self.insert(ch))
                b.grid(row=i // 14, column=i % 14, padx=1, pady=1)
                b.bind("<Enter>", lambda e, ch=ch: self.hover(ch))

        tk.Label(self.root, textvariable=self.var_hint, anchor="w", fg="#444444").pack(fill="x", padx=10)
        tk.Label(self.root, textvariable=self.var_bytes, anchor="w", fg="#444444", font=("Consolas", 9)).pack(fill="x", padx=10)
        tk.Label(self.root, textvariable=self.var_warn, anchor="w", fg="#b36b00").pack(fill="x", padx=10, pady=(0, 8))

    def hover(self, ch):
        code = " ".join(f"{b:02X}" for b in encode(ch))
        name = "space" if ch == " " else ch
        self.var_hint.set(f"{name}   ->   byte {code}")

    def insert(self, ch):
        w = self.target or self.ent_bottom
        w.insert(w.index(tk.INSERT), ch)
        w.focus_set()

    def compose(self):
        """-> (top row bytes, bottom row bytes, full top bytes, full bottom bytes, warnings)"""
        mode = self.var_align.get()
        full_top = encode(self.var_top.get())
        full_bottom = encode(self.var_bottom.get())
        raw = self.var_raw.get().strip()
        warn = []
        if raw:
            try:
                full_bottom = bytes.fromhex(raw.replace("0x", "").replace(",", " "))
            except ValueError:
                warn.append("raw hex is not valid - ignoring it")
        bad = [ch for ch in self.var_top.get() + self.var_bottom.get() if encode(ch) == b"?" and ch != "?"]
        if bad:
            warn.append("not in the font, shown as ?: " + " ".join(dict.fromkeys(bad)))
        what = "will scroll" if self.var_scroll.get() else "cut off"
        if len(full_top) > ROW:
            warn.append(f"top row longer than {ROW} cells - {what}")
        if len(full_bottom) > ROW:
            warn.append(f"bottom row longer than {ROW} cells - {what}")
        return pad(full_top, ROW, mode), pad(full_bottom, ROW, mode), full_top, full_bottom, warn

    def on_change(self):
        self.redraw()
        if self.var_live.get() and self.connected:
            if self.live_after is not None:
                self.root.after_cancel(self.live_after)
            self.live_after = self.root.after(350, self.send)

    def redraw(self):
        top, bottom, _, _, warn = self.compose()
        c = self.canvas
        c.delete("all")
        c.create_rectangle(8, 8, 380, 142, fill="#3d5a00", outline="#a3c400", width=2)
        cell_w, cell_h, x0 = 34, 46, 20
        for data, y in ((top, 22), (bottom, 80)):
            for i, b in enumerate(data):
                x = x0 + i * cell_w
                c.create_rectangle(x, y, x + cell_w - 2, y + cell_h, outline="#4f7000")
                c.create_text(x + cell_w / 2 - 1, y + cell_h / 2, text=glyph_char(b),
                              font=("Consolas", 24, "bold"), fill="#fff04a")
        self.var_bytes.set("top " + " ".join(f"{b:02X}" for b in top)
                           + "   bottom " + " ".join(f"{b:02X}" for b in bottom))
        self.var_warn.set("   |   ".join(warn))

    def send(self):
        self.live_after = None
        if not self.connected:
            self.var_hint.set("Connect first.")
            return
        top, bottom, full_top, full_bottom, _ = self.compose()
        scroll = self.var_scroll.get()
        st = full_top if scroll and len(full_top) > ROW else None
        sb = full_bottom if scroll and len(full_bottom) > ROW else None
        if st is not None or sb is not None:
            self.worker.post_job("scroll", top, bottom, st, sb)
        else:
            self.worker.post_job("show", top, bottom)

    def clear(self):
        if self.connected:
            self.worker.post_job("show", BLANK, BLANK)

    def toggle_connect(self):
        if self.connecting:
            return
        if self.connected:
            self.worker.post_cmd("disconnect")
        else:
            self.connecting = True
            self.btn_conn.config(state="disabled")
            self.set_status("Connecting... (about 5 s)", "#b36b00")
            self.worker.post_cmd("connect", self.var_port.get().strip())

    def set_status(self, text, color):
        self.var_status.set(text)
        self.lbl_status.config(fg=color)

    def poll(self):
        try:
            while True:
                kind, *rest = self.ui_q.get_nowait()
                if kind == "connected":
                    self.connected, self.connecting = True, False
                    self.btn_conn.config(text="Disconnect", state="normal")
                    self.set_status(f"Connected - session {rest[0]:02X}", "#1a7f1a")
                elif kind == "failed":
                    self.connected, self.connecting = False, False
                    self.btn_conn.config(text="Connect", state="normal")
                    self.set_status("Failed: " + rest[0], "#b00020")
                elif kind == "disconnected":
                    self.connected = False
                    self.btn_conn.config(text="Connect", state="normal")
                    self.set_status("Not connected (display goes blank)", "#777777")
                elif kind == "sent":
                    self.set_status(rest[1], "#1a7f1a" if rest[0] else "#b00020")
        except queue.Empty:
            pass
        self._poll_id = self.root.after(100, self.poll)

    def close(self):
        for after_id in (self._poll_id, self.live_after):
            if after_id is not None:
                self.root.after_cancel(after_id)
        self.worker.post_cmd("quit")
        self.worker.join(timeout=8)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
