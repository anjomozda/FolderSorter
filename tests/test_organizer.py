"""Tests for organizer.py - the sorting logic, with no window involved.

Every test gets its own throwaway folder from tempfile, so nothing here
touches a real folder and nothing is left behind.

Run from the project root with:
    python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import organizer  # noqa: E402


class SandboxTest(unittest.TestCase):
    """Base class: a fresh empty folder per test, plus a few helpers."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.ext_map = organizer.build_extension_map()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relative, content="x"):
        """Create a file inside the sandbox, making parent folders as needed."""
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def plan(self, recursive=False, by_extension=False):
        files = organizer.collect_files(self.folder, recursive, set())
        return organizer.plan_moves(files, self.folder, self.ext_map, by_extension)

    def tree(self):
        """Every path in the sandbox, relative and sorted, for comparing."""
        return sorted(str(p.relative_to(self.folder)).replace("\\", "/")
                      for p in self.folder.rglob("*"))


class DestinationName(SandboxTest):

    def test_known_extension_gets_its_category(self):
        self.assertEqual(organizer.destination_name(Path("a.png"), self.ext_map),
                         "Images")
        self.assertEqual(organizer.destination_name(Path("a.pdf"), self.ext_map),
                         "Documents")

    def test_case_is_ignored(self):
        self.assertEqual(organizer.destination_name(Path("a.JPG"), self.ext_map),
                         "Images")

    def test_unknown_and_missing_extensions_go_to_other(self):
        self.assertEqual(organizer.destination_name(Path("a.xyz"), self.ext_map),
                         organizer.OTHER)
        self.assertEqual(organizer.destination_name(Path("noext"), self.ext_map),
                         organizer.OTHER)

    def test_by_extension_uses_the_suffix_in_capitals(self):
        self.assertEqual(
            organizer.destination_name(Path("a.PnG"), self.ext_map, True), "PNG")
        self.assertEqual(
            organizer.destination_name(Path("noext"), self.ext_map, True),
            organizer.OTHER)


class CollectFiles(SandboxTest):

    def test_skips_hidden_files_and_os_clutter(self):
        self.write("keep.pdf")
        self.write("desktop.ini")
        self.write("Thumbs.db")
        self.write(".hidden")
        self.write(".git/config")
        found = organizer.collect_files(self.folder, True, set())
        self.assertEqual([p.name for p in found], ["keep.pdf"])

    def test_skips_the_paths_it_is_given(self):
        script = self.write("organizer.py")
        self.write("keep.pdf")
        found = organizer.collect_files(self.folder, False, {script.resolve()})
        self.assertEqual([p.name for p in found], ["keep.pdf"])

    def test_reaches_into_subfolders_only_when_asked(self):
        self.write("top.pdf")
        self.write("sub/deep.pdf")
        self.assertEqual(len(organizer.collect_files(self.folder, False, set())), 1)
        self.assertEqual(len(organizer.collect_files(self.folder, True, set())), 2)


class UniqueDestination(SandboxTest):

    def test_reserves_names_within_a_single_run(self):
        taken = set()
        target = self.folder / "a.txt"
        first = organizer.unique_destination(target, taken)
        second = organizer.unique_destination(target, taken)
        self.assertEqual(first.name, "a.txt")
        self.assertEqual(second.name, "a (1).txt")

    def test_avoids_names_already_on_disk(self):
        self.write("a.txt")
        chosen = organizer.unique_destination(self.folder / "a.txt", set())
        self.assertEqual(chosen.name, "a (1).txt")


class Planning(SandboxTest):

    def test_clashing_names_are_numbered_never_overwritten(self):
        self.write("slika.png", "one")
        self.write("a/slika.png", "two")
        self.write("b/slika.png", "three")
        moves = self.plan(recursive=True)
        self.assertEqual(sorted(dest.name for _, dest in moves),
                         ["slika (1).png", "slika (2).png", "slika.png"])

    def test_a_file_already_in_place_is_left_out(self):
        self.write("Images/done.png")
        self.write("loose.png")
        moves = self.plan(recursive=True)
        self.assertEqual([src.name for src, _ in moves], ["loose.png"])

    def test_by_extension_groups_by_suffix(self):
        self.write("a.pdf")
        self.write("b.pdf")
        self.write("c.png")
        moves = self.plan(by_extension=True)
        self.assertEqual(sorted({dest.parent.name for _, dest in moves}),
                         ["PDF", "PNG"])


class PruneEmptyDirs(SandboxTest):

    def test_removes_only_the_empty_ones(self):
        (self.folder / "Empty").mkdir()
        self.write("Full/keep.txt")
        organizer.prune_empty_dirs(self.folder, ["Empty", "Full", "Missing"])
        self.assertFalse((self.folder / "Empty").exists())
        self.assertTrue((self.folder / "Full").exists())


class SortingAndUndo(SandboxTest):

    def sort_now(self, **kwargs):
        """Run a full sort and write the log, the way main() does."""
        done, failures = organizer.apply_moves(self.plan(**kwargs))
        if done:
            organizer.write_log(self.folder, done,
                                kwargs.get("by_extension", False))
        return done, failures

    def test_round_trip_restores_the_folder_exactly(self):
        for name in ("cv.pdf", "logo.png", "sub/deep.pdf", "song.mp3"):
            self.write(name, name)
        before = self.tree()

        done, failures = self.sort_now(recursive=True)
        self.assertEqual(len(done), 4)
        self.assertEqual(failures, [])
        self.assertNotEqual(self.tree(), before)

        counts = organizer.undo_moves(self.folder, organizer.read_log(self.folder))
        self.assertEqual(counts, (4, 0, 0))
        self.assertEqual(self.tree(), before)

    def test_a_second_run_has_nothing_to_do(self):
        self.write("cv.pdf")
        self.sort_now()
        self.assertEqual(self.plan(), [])

    def test_undo_cleans_up_extension_folders_too(self):
        self.write("cv.pdf")
        self.write("logo.png")
        self.sort_now(by_extension=True)
        self.assertTrue((self.folder / "PDF").is_dir())

        organizer.undo_moves(self.folder, organizer.read_log(self.folder))
        self.assertFalse((self.folder / "PDF").exists())
        self.assertFalse((self.folder / "PNG").exists())

    def test_the_log_records_which_mode_produced_it(self):
        self.write("cv.pdf")
        self.sort_now(by_extension=True)
        self.assertEqual(organizer.read_log(self.folder)["mode"], "extension")

    def test_the_log_is_removed_by_a_clean_undo(self):
        self.write("cv.pdf")
        self.sort_now()
        organizer.undo_moves(self.folder, organizer.read_log(self.folder))
        self.assertIsNone(organizer.read_log(self.folder))

    def test_undo_counts_files_that_are_already_gone(self):
        self.write("cv.pdf")
        done, _ = self.sort_now()
        done[0][1].unlink()          # somebody deleted it in the meantime
        counts = organizer.undo_moves(self.folder, organizer.read_log(self.folder))
        self.assertEqual(counts, (0, 1, 0))


class ReadLog(SandboxTest):

    def test_no_log_at_all(self):
        self.assertIsNone(organizer.read_log(self.folder))

    def test_a_damaged_log_is_reported_as_missing_not_raised(self):
        (self.folder / organizer.LOG_NAME).write_text("{ not json",
                                                      encoding="utf-8")
        self.assertIsNone(organizer.read_log(self.folder))


if __name__ == "__main__":
    unittest.main()
