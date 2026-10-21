# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

import queue
import tkinter as tk
import unittest

from maxidot import gui


class FakeLink:
    def __init__(self):
        self.calls = []

    def show_rows(self, top, bottom="", **kw):
        self.calls.append((bytes(top), bytes(bottom)))
        return True


def headless_app():
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest("no display available for Tk")
    root.withdraw()
    return root, gui.App(root)


class GuiTests(unittest.TestCase):
    def test_compose_pads_to_ten_cells_and_warns_about_long_rows(self):
        root, app = headless_app()
        try:
            app.var_top.set("HI")
            app.var_bottom.set("A VERY LONG BOTTOM ROW")
            root.update()
            top, bottom, full_top, full_bottom, warn = app.compose()
            self.assertEqual(top, b"HI        ")
            self.assertEqual(bottom, b"A VERY LON")
            self.assertEqual(len(full_bottom), 22)
            self.assertTrue(any("will scroll" in w for w in warn))
            app.var_align.set("right")
            root.update()
            self.assertEqual(app.compose()[0], b"        HI")
        finally:
            app.close()

    def test_scroll_routing(self):
        root, app = headless_app()
        jobs = []
        app.worker.post_job = lambda *a, **k: jobs.append(a)
        app.connected = True
        try:
            def sent(top, bottom):
                jobs.clear()
                app.var_top.set(top)
                app.var_bottom.set(bottom)
                root.update()
                app.send()
                return jobs[0]

            self.assertEqual(sent("HELLO", "WORLD")[0], "show")
            job = sent("A VERY LONG TOP ROW", "SHORT")
            self.assertEqual(job[0], "scroll")
            self.assertIsNotNone(job[3])
            self.assertIsNone(job[4])
            job = sent("TOP", "A VERY LONG BOTTOM ROW")
            self.assertIsNone(job[3])
            self.assertIsNotNone(job[4])
            job = sent("TOP SCROLLS TOO LONG", "AND BOTTOM SCROLLS TOO")
            self.assertIsNotNone(job[3])
            self.assertIsNotNone(job[4])
            app.var_scroll.set(False)
            self.assertEqual(sent("A VERY LONG TOP ROW", "AND LONG BOTTOM")[0], "show")
        finally:
            app.close()

    def test_worker_scrolls_rows_independently_and_together(self):
        w = gui.Worker(queue.Queue())
        w.link = FakeLink()

        def run(top_scroll, bottom_scroll, steps):
            w.link.calls.clear()
            real = w.link.show_rows

            def counting(top, bottom=""):
                real(top, bottom)
                if len(w.link.calls) >= steps:
                    w.post_job("stop")      # interrupts the scroll loop
                return True

            w.link.show_rows = counting
            w._do_job(("scroll", b"ABCDEFGHIJ", b"STATIC    ", top_scroll, bottom_scroll))
            w.link.show_rows = real
            w.job = None
            return list(w.link.calls)

        calls = run(b"0123456789AB", None, 12)
        self.assertEqual(calls[0][0], b" " * 9 + b"0")          # the first character enters at the right edge
        self.assertEqual(calls[9][0], b"0123456789")
        self.assertTrue(all(c[1] == b"STATIC    " for c in calls))   # the other row stays put

        calls = run(None, b"HELLO WORLD!!", 4)
        self.assertTrue(all(c[0] == b"ABCDEFGHIJ" for c in calls))
        self.assertEqual(calls[0][1], b" " * 9 + b"H")

        calls = run(b"TOPTOPTOP", b"BOTTOMBOTTOM", 3)
        self.assertEqual(calls[0], (b" " * 9 + b"T", b" " * 9 + b"B"))
        self.assertEqual(calls[1], (b" " * 8 + b"TO", b" " * 8 + b"BO"))


if __name__ == "__main__":
    unittest.main()
