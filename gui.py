"""
FolderSorter - a window for picking exactly what gets sorted.

A small tkinter front end for organizer.py: choose a folder, look at
everything that would move grouped by destination, untick whatever you
want left alone, then sort. All the real work - deciding where files go,
moving them, writing the undo log - is done by organizer.py. This file
only draws the window and calls into it.

Standard library only: tkinter ships with Python, so there is still
nothing to install.

Run with:
    python gui.py
    pythonw gui.py      (Windows: no console window sitting behind it)
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import organizer

# Where the window remembers the last folder and the options you used.
SETTINGS_PATH = Path.home() / ".foldersorter-gui.json"

# Treeview has no real check boxes, so the tick state is drawn into the
# row label and toggled on click. PARTIAL means "some of this group".
CHECKED = "☑"
UNCHECKED = "☐"
PARTIAL = "▣"


def human_size(num_bytes):
    """Format a byte count as a short, readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "{:.0f} B".format(size)
            return "{:.1f} {}".format(size, unit)
        size /= 1024


def load_settings():
    """Read the remembered folder and options, or {} if anything is off."""
    try:
        # utf-8-sig, so a byte order mark left by an editor like Notepad
        # does not turn the whole file into a parse error.
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    """Remember the folder and options for next time. Never fatal."""
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


class SorterWindow:
    """The whole window: folder picker, options, file tree and buttons."""

    def __init__(self, root):
        self.root = root
        self.ext_map = organizer.build_extension_map()

        # Never offer to move the two files this program is made of.
        self.skip = {Path(organizer.__file__).resolve(), Path(__file__).resolve()}

        self.folder = None
        self.moves = []       # the full plan: list of (src, dest)
        self.sizes = []       # byte size of each move's source file
        self.labels = []      # row text for each move, worked out once
        self.checked = set()  # indexes into self.moves that are ticked
        self.groups = {}      # destination folder name -> list of indexes
        self.has_log = False  # is there something to undo in this folder?

        settings = load_settings()
        self.by_extension = tk.BooleanVar(value=settings.get("by_extension", False))
        self.recursive = tk.BooleanVar(value=settings.get("recursive", False))
        self.folder_text = tk.StringVar(value="")

        self._build_ui()

        remembered = settings.get("folder", "")
        if remembered and Path(remembered).is_dir():
            self.set_folder(Path(remembered))

    # ------------------------------------------------------------------
    # building the window
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.root.title("FolderSorter")
        self.root.geometry("800x580")
        self.root.minsize(640, 440)

        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(head, text="FolderSorter",
                  font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(head, text="pick what moves, then sort",
                  foreground="#777777").pack(side="left", padx=(10, 0))

        # --- which folder ---
        row = ttk.Frame(self.root)
        row.pack(fill="x", padx=12, pady=6)
        ttk.Label(row, text="Folder").pack(side="left")
        entry = ttk.Entry(row, textvariable=self.folder_text)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        entry.state(["readonly"])
        ttk.Button(row, text="Browse…", command=self.choose_folder).pack(side="left")

        # --- how to sort ---
        opts = ttk.Frame(self.root)
        opts.pack(fill="x", padx=12, pady=6)
        ttk.Label(opts, text="Sort").pack(side="left")
        ttk.Radiobutton(opts, text="by category", value=False,
                        variable=self.by_extension,
                        command=self.rescan).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(opts, text="by file type  (PDF, PNG, DOCX…)", value=True,
                        variable=self.by_extension,
                        command=self.rescan).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(opts, text="include subfolders",
                        variable=self.recursive,
                        command=self.rescan).pack(side="right")

        # --- the plan, as a tree of groups and files ---
        wrap = ttk.Frame(self.root)
        wrap.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(wrap, columns=("count", "size"),
                                 selectmode="none")
        self.tree.heading("#0", text="Destination folder  /  file")
        self.tree.heading("count", text="Files")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=520, stretch=True)
        self.tree.column("count", width=80, anchor="e", stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        bar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_click)

        # --- status line and buttons ---
        self.status = tk.StringVar(value="Choose a folder to begin.")
        ttk.Label(self.root, textvariable=self.status).pack(
            fill="x", padx=12, pady=(4, 0))

        buttons = ttk.Frame(self.root)
        buttons.pack(fill="x", padx=12, pady=10)
        ttk.Button(buttons, text="Select all",
                   command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(buttons, text="Select none",
                   command=lambda: self.set_all(False)).pack(side="left", padx=6)
        self.sort_button = ttk.Button(buttons, text="Sort", command=self.do_sort)
        self.sort_button.pack(side="right")
        self.undo_button = ttk.Button(buttons, text="Undo last run",
                                      command=self.do_undo)
        self.undo_button.pack(side="right", padx=6)

    # ------------------------------------------------------------------
    # working out the plan
    # ------------------------------------------------------------------

    def choose_folder(self):
        """Open the folder picker, starting where we last were."""
        start = self.folder_text.get() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose a folder to sort",
                                         initialdir=start, parent=self.root)
        if chosen:
            self.set_folder(Path(chosen))

    def set_folder(self, folder):
        self.folder = folder.resolve()
        self.folder_text.set(str(self.folder))
        self.rescan()

    def rescan(self):
        """Rebuild the plan from what is on disk right now, and redraw."""
        if self.folder is None or not self.folder.is_dir():
            return
        files = organizer.collect_files(self.folder, self.recursive.get(), self.skip)
        self.moves = organizer.plan_moves(files, self.folder, self.ext_map,
                                          self.by_extension.get())
        self.sizes = [self._size(src) for src, _ in self.moves]
        self.labels = [self._make_label(i) for i in range(len(self.moves))]
        self.checked = set(range(len(self.moves)))
        self.has_log = organizer.read_log(self.folder) is not None
        self.populate()
        self.remember()

    @staticmethod
    def _size(path):
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _make_label(self, index):
        """Row text for one file: its path, plus any rename forced by a clash."""
        src, dest = self.moves[index]
        name = str(src.relative_to(self.folder))
        if dest.name != src.name:
            name += "   → " + dest.name
        return name

    def populate(self):
        """Fill the tree: one parent row per destination folder."""
        self.tree.delete(*self.tree.get_children())
        self.groups = {}
        for index, (_, dest) in enumerate(self.moves):
            self.groups.setdefault(dest.parent.name, []).append(index)

        for name in sorted(self.groups):
            indexes = self.groups[name]
            total = sum(self.sizes[i] for i in indexes)
            self.tree.insert("", "end", iid="g:" + name,
                             text="{} {}".format(CHECKED, name),
                             values=(len(indexes), human_size(total)))
            for i in indexes:
                self.tree.insert("g:" + name, "end", iid="f:{}".format(i),
                                 text="{} {}".format(CHECKED, self.labels[i]),
                                 values=("", human_size(self.sizes[i])))
        self.refresh()

    # ------------------------------------------------------------------
    # ticking and unticking
    # ------------------------------------------------------------------

    def on_click(self, event):
        """Toggle the row that was clicked. The expand arrow is left alone."""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if self.tree.identify_element(event.x, event.y) == "Treeitem.indicator":
            return
        self.toggle(item)

    def toggle(self, item):
        """Flip one file, or a whole group at once."""
        if item.startswith("g:"):
            indexes = self.groups.get(item[2:], [])
            if all(i in self.checked for i in indexes):
                self.checked.difference_update(indexes)
            else:
                self.checked.update(indexes)
        else:
            self.checked.symmetric_difference_update({int(item[2:])})
        self.refresh()

    def set_all(self, on):
        self.checked = set(range(len(self.moves))) if on else set()
        self.refresh()

    def refresh(self):
        """Redraw every tick box, then the status line and the buttons."""
        for name, indexes in self.groups.items():
            ticked = sum(1 for i in indexes if i in self.checked)
            if ticked == len(indexes):
                mark = CHECKED
            elif ticked == 0:
                mark = UNCHECKED
            else:
                mark = PARTIAL
            self.tree.item("g:" + name, text="{} {}".format(mark, name))
            for i in indexes:
                box = CHECKED if i in self.checked else UNCHECKED
                self.tree.item("f:{}".format(i),
                               text="{} {}".format(box, self.labels[i]))
        self.update_status()

    def update_status(self):
        picked = len(self.checked)
        if self.folder is None:
            self.status.set("Choose a folder to begin.")
        elif not self.moves:
            self.status.set("Nothing to sort - this folder is already tidy.")
        else:
            size = sum(self.sizes[i] for i in self.checked)
            self.status.set("{} of {} files selected   ·   {}".format(
                picked, len(self.moves), human_size(size)))
        self.sort_button.state(["!disabled"] if picked else ["disabled"])
        self.undo_button.state(["!disabled"] if self.has_log else ["disabled"])

    # ------------------------------------------------------------------
    # doing it
    # ------------------------------------------------------------------

    def do_sort(self):
        """Move the ticked files, after one last confirmation."""
        chosen = [self.moves[i][0] for i in sorted(self.checked)]
        if not chosen:
            return
        question = ("Move {} files into folders inside\n\n{}\n\n"
                    "You can undo this afterwards.".format(len(chosen), self.folder))
        if not messagebox.askyesno("Sort files", question, parent=self.root):
            return

        # Re-plan for just the picked files. Otherwise a file you unticked
        # could still be the reason another one becomes "photo (1).jpg".
        moves = organizer.plan_moves(chosen, self.folder, self.ext_map,
                                     self.by_extension.get())
        done, failures = organizer.apply_moves(moves)
        if done:
            organizer.write_log(self.folder, done, self.by_extension.get())
        self.rescan()

        if failures:
            detail = "\n".join("   " + src.name for src, _ in failures[:5])
            messagebox.showwarning(
                "Done, with problems",
                "Moved {} files.\n\n{} could not be moved:\n{}".format(
                    len(done), len(failures), detail),
                parent=self.root)
        self.status.set("Moved {} files. Undo is available.".format(len(done)))

    def do_undo(self):
        """Put back everything the last run moved."""
        log = organizer.read_log(self.folder) if self.folder else None
        if log is None:
            messagebox.showinfo("Nothing to undo",
                                "There is no undo log in this folder.",
                                parent=self.root)
            return
        count = len(log.get("moves", []))
        if not messagebox.askyesno(
                "Undo last run",
                "Put back {} files, sorted on {}?".format(count, log.get("when", "?")),
                parent=self.root):
            return

        restored, missing, failed = organizer.undo_moves(self.folder, log)
        self.rescan()
        note = "Put back {} files.".format(restored)
        if missing:
            note += "  {} were already gone.".format(missing)
        if failed:
            note += "  {} could not be moved back.".format(failed)
        self.status.set(note)

    def remember(self):
        """Save the folder and options, so next time they are already set."""
        save_settings({
            "folder": str(self.folder) if self.folder else "",
            "by_extension": self.by_extension.get(),
            "recursive": self.recursive.get(),
        })


def main():
    root = tk.Tk()
    # Use the native-looking theme where there is one; plain ttk otherwise.
    style = ttk.Style()
    for theme in ("vista", "aqua", "clam"):
        if theme in style.theme_names():
            style.theme_use(theme)
            break
    SorterWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
