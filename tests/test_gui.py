"""Tests for gui.py - the window, driven from code instead of by clicking.

The window is built hidden and its methods are called directly, so these
need nobody at the keyboard. They skip themselves where Tk cannot open a
display at all, which is what keeps them from failing on a headless CI box.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Checked before anything touches Tk. On a Windows build machine there is
# no interactive desktop, and creating a window does not fail there - it
# simply never returns, so the whole suite wedges. That has to be settled
# without opening a window at all, which is why this comes first.
SKIP_GUI = os.environ.get("FOLDERSORTER_SKIP_GUI_TESTS") == "1"

if SKIP_GUI:
    TK_WORKS = False
else:
    try:
        import tkinter as tk

        _probe = tk.Tk()
        _probe.destroy()
        TK_WORKS = True
    except Exception:                                 # pragma: no cover
        TK_WORKS = False

if TK_WORKS:
    import gui

_ROOT = None


def setUpModule():
    """One Tk root for the whole module.

    A root per test is cheap on a desktop but slow elsewhere, so the tests
    share one and take a Toplevel each.
    """
    global _ROOT
    if TK_WORKS:
        _ROOT = tk.Tk()
        _ROOT.withdraw()


def tearDownModule():
    global _ROOT
    if _ROOT is not None:
        _ROOT.destroy()
        _ROOT = None


@unittest.skipUnless(TK_WORKS, "no usable display for tkinter here")
class WindowTest(unittest.TestCase):
    """Base class: a hidden window pointed at a throwaway folder."""

    def setUp(self):
        # Two separate temp folders: one to sort, one to hold the settings
        # file. Keeping them apart matters, because a settings file living
        # in the sorted folder would itself be sorted, as a .json.
        self._sandbox = tempfile.TemporaryDirectory()
        self._config = tempfile.TemporaryDirectory()
        self.folder = Path(self._sandbox.name)

        self.real_settings = gui.SETTINGS_PATH
        gui.SETTINGS_PATH = Path(self._config.name) / "settings.json"

        # The dark title bar is OS chrome with nothing to assert on, and
        # asking for it hides and re-shows the window, which costs seconds
        # once per test. Stub it out so the suite stays quick.
        self.real_titlebar = gui.enable_dark_titlebar
        gui.enable_dark_titlebar = lambda root: None

        self.root = tk.Toplevel(_ROOT)
        self.root.withdraw()
        self.win = gui.SorterWindow(self.root)
        self.win.by_extension.set(False)
        self.win.recursive.set(False)

    def tearDown(self):
        self.root.destroy()
        gui.enable_dark_titlebar = self.real_titlebar
        gui.SETTINGS_PATH = self.real_settings
        self._sandbox.cleanup()
        self._config.cleanup()

    def make_files(self, *names):
        """Create files in the sandbox and point the window at it."""
        for name in names:
            path = self.folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * (10 + len(name)))
        self.win.set_folder(self.folder)

    def sort_confirmed(self):
        """Press Sort, answering yes to the confirmation dialog."""
        original = gui.messagebox.askyesno
        gui.messagebox.askyesno = lambda *a, **k: True
        try:
            self.win.do_sort()
        finally:
            gui.messagebox.askyesno = original

    def mark(self, item):
        """The tick glyph currently drawn on a row."""
        return self.win.tree.item(item, "text")[0]


class Grouping(WindowTest):

    def test_files_are_grouped_by_destination(self):
        self.make_files("cv.pdf", "notes.txt", "logo.png", "song.mp3")
        self.assertEqual(sorted(self.win.groups),
                         ["Documents", "Images", "Music"])
        self.assertEqual(len(self.win.groups["Documents"]), 2)

    def test_everything_starts_ticked(self):
        self.make_files("cv.pdf", "logo.png")
        self.assertEqual(len(self.win.checked), 2)

    def test_os_clutter_is_not_offered(self):
        self.make_files("cv.pdf", "desktop.ini")
        self.assertEqual(len(self.win.moves), 1)

    def test_switching_to_file_type_regroups(self):
        self.make_files("cv.pdf", "logo.png", "photo.jpg")
        self.win.by_extension.set(True)
        self.win.rescan()
        self.assertEqual(sorted(self.win.groups), ["JPG", "PDF", "PNG"])

    def test_subfolders_only_when_asked(self):
        self.make_files("cv.pdf", "sub/deep.pdf")
        self.assertEqual(len(self.win.moves), 1)
        self.win.recursive.set(True)
        self.win.rescan()
        self.assertEqual(len(self.win.moves), 2)

    def test_a_tidy_folder_offers_nothing(self):
        self.make_files("Images/done.png")
        self.assertEqual(self.win.moves, [])


class Ticking(WindowTest):

    def test_unticking_a_group_unticks_its_files(self):
        self.make_files("cv.pdf", "notes.txt", "logo.png")
        self.win.toggle("g:Documents")
        self.assertEqual(len(self.win.checked), 1)
        self.assertEqual(self.mark("g:Documents"), gui.UNCHECKED)

    def test_unticking_one_file_makes_the_group_partial(self):
        self.make_files("cv.pdf", "notes.txt")
        one = self.win.groups["Documents"][0]
        self.win.toggle("f:{}".format(one))
        self.assertEqual(len(self.win.checked), 1)
        self.assertEqual(self.mark("g:Documents"), gui.PARTIAL)

    def test_reticking_the_last_file_makes_the_group_whole_again(self):
        self.make_files("cv.pdf", "notes.txt")
        one = self.win.groups["Documents"][0]
        self.win.toggle("f:{}".format(one))
        self.win.toggle("f:{}".format(one))
        self.assertEqual(self.mark("g:Documents"), gui.CHECKED)

    def test_select_all_and_clear(self):
        self.make_files("cv.pdf", "logo.png", "song.mp3")
        self.win.set_all(False)
        self.assertEqual(self.win.checked, set())
        self.win.set_all(True)
        self.assertEqual(len(self.win.checked), 3)

    def test_sort_button_is_dead_when_nothing_is_ticked(self):
        self.make_files("cv.pdf")
        self.win.set_all(False)
        self.assertIn("disabled", self.win.sort_button.state())
        self.win.set_all(True)
        self.assertNotIn("disabled", self.win.sort_button.state())


class Keyboard(WindowTest):

    def test_space_toggles_the_focused_row(self):
        self.make_files("cv.pdf", "logo.png")
        first = self.win.tree.get_children()[0]
        self.win.tree.focus(first)
        before = len(self.win.checked)
        self.win.on_space(None)
        self.assertLess(len(self.win.checked), before)

    def test_the_first_row_gets_the_focus_automatically(self):
        self.make_files("cv.pdf", "logo.png")
        self.assertEqual(self.win.tree.focus(),
                         self.win.tree.get_children()[0])

    def test_space_and_return_are_bound_to_the_list(self):
        bound = " ".join(self.win.tree.bind())
        self.assertIn("space", bound)
        self.assertIn("Return", bound)

    def test_control_a_and_control_d_are_bound(self):
        bound = " ".join(self.win.tree.bind())
        self.assertIn("Control", bound)


class SortingAndUndo(WindowTest):

    def test_only_the_ticked_files_move(self):
        self.make_files("cv.pdf", "logo.png", "song.mp3")
        self.win.set_all(False)
        self.win.toggle("g:Documents")
        self.sort_confirmed()

        self.assertTrue((self.folder / "Documents" / "cv.pdf").exists())
        self.assertTrue((self.folder / "logo.png").exists())
        self.assertFalse((self.folder / "Images").exists())
        self.assertFalse((self.folder / "Music").exists())

    def test_the_plan_shrinks_to_what_is_left(self):
        self.make_files("cv.pdf", "logo.png")
        self.win.set_all(False)
        self.win.toggle("g:Documents")
        self.sort_confirmed()
        self.assertEqual(sorted(self.win.groups), ["Images"])

    def test_undo_puts_everything_back(self):
        self.make_files("cv.pdf", "logo.png")
        self.sort_confirmed()
        self.assertTrue(self.win.has_log)

        self.win.do_undo()
        self.assertTrue((self.folder / "cv.pdf").exists())
        self.assertTrue((self.folder / "logo.png").exists())
        self.assertFalse((self.folder / "Documents").exists())
        self.assertFalse(self.win.has_log)

    def test_undo_button_follows_whether_there_is_a_log(self):
        self.make_files("cv.pdf")
        self.assertIn("disabled", self.win.undo_button.state())
        self.sort_confirmed()
        self.assertNotIn("disabled", self.win.undo_button.state())

    def test_a_clash_is_renamed_and_shown_in_the_row(self):
        self.make_files("Images/logo.png", "logo.png")
        self.win.recursive.set(True)
        self.win.rescan()
        self.assertTrue(any("logo (1).png" in label for label in self.win.labels))


class Presentation(WindowTest):

    def test_human_size(self):
        self.assertEqual(gui.human_size(0), "0 B")
        self.assertEqual(gui.human_size(512), "512 B")
        self.assertEqual(gui.human_size(1536), "1.5 KB")
        self.assertEqual(gui.human_size(5 * 1024 * 1024), "5.0 MB")

    def test_every_category_has_its_own_colour(self):
        colours = gui.CATEGORY_COLORS
        self.assertEqual(len(set(colours.values())), len(colours))

    def test_related_file_types_share_a_colour(self):
        self.make_files("a.png", "b.jpg", "c.pdf")
        self.win.by_extension.set(True)
        self.win.rescan()
        png = self.win._dot("PNG")
        jpg = self.win._dot("JPG")
        pdf = self.win._dot("PDF")
        self.assertIs(png, jpg)          # both are Images
        self.assertIsNot(png, pdf)

    def test_the_real_settings_file_is_never_touched(self):
        self.assertNotEqual(gui.SETTINGS_PATH, self.real_settings)
        self.make_files("cv.pdf")
        self.assertTrue(gui.SETTINGS_PATH.exists())


if __name__ == "__main__":
    unittest.main()
