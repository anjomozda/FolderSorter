"""
FolderSorter - a window for picking exactly what gets sorted.

A small tkinter front end for organizer.py: choose a folder, look at
everything that would move grouped by destination, untick whatever you
want left alone, then sort. All the real work - deciding where files go,
moving them, writing the undo log - is done by organizer.py. This file
only draws the window and calls into it.

The look is a flat dark theme built by repainting ttk's 'clam' theme,
which is the only built-in one that lets every colour be overridden.

Standard library only: tkinter ships with Python, so there is still
nothing to install.

Run with:
    python gui.py
    pythonw gui.py      (Windows: no console window sitting behind it)
"""

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import organizer

# Where the window remembers the last folder and the options you used.
SETTINGS_PATH = Path.home() / ".foldersorter-gui.json"

# Treeview has no real check boxes, so the tick state is drawn into the
# row label and toggled on click. PARTIAL means "some of this group".
# These live in Segoe UI Symbol; Windows substitutes it automatically.
CHECKED = "☑"
UNCHECKED = "☐"
PARTIAL = "▣"

# One dark palette, in one place. Every colour in the window comes from here.
PALETTE = {
    "bg": "#18181B",         # the window itself
    "surface": "#1F1F23",    # the list, inputs, secondary buttons
    "border": "#2E2E35",     # hairlines
    "hover": "#27272E",      # row under the mouse
    "text": "#E4E4E7",       # primary text
    "text2": "#A1A1AA",      # secondary text
    "muted": "#71717A",      # unticked rows, headings, hints
    "accent": "#3B82F6",     # the Sort button
    "accent_hi": "#60A5FA",  # hovered
    "accent_lo": "#2563EB",  # pressed
    "on_accent": "#FFFFFF",
}

# A colour per destination folder, shown as a dot in front of the name.
CATEGORY_COLORS = {
    "Images": "#F472B6",
    "Documents": "#60A5FA",
    "Music": "#A78BFA",
    "Videos": "#FB7185",
    "Archives": "#FBBF24",
    "Installers": "#34D399",
    "Code": "#22D3EE",
    "Fonts": "#FB923C",
    "Shortcuts": "#94A3B8",
    "Other": "#71717A",
}

FONT_TITLE = ("Segoe UI Semibold", 15)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_ICON = ("Segoe MDL2 Assets", 12)

# Segoe MDL2 Assets glyphs, checked against the font before being used.
ICON_FOLDER = ""

DOT_BOX = 16  # the square the category dot is drawn inside


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


def apply_theme(root):
    """Repaint ttk's 'clam' theme into the flat dark one used here.

    clam is the only built-in theme whose colours are all settable.
    `lightcolor` and `darkcolor` are what draw the raised 3D edges, so
    flattening them into the background is most of the job.
    """
    p = PALETTE
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=p["bg"])

    style.configure(".",
                    background=p["bg"], foreground=p["text"],
                    fieldbackground=p["surface"], bordercolor=p["border"],
                    lightcolor=p["bg"], darkcolor=p["bg"],
                    troughcolor=p["surface"], focuscolor=p["bg"],
                    font=FONT_BODY)

    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Muted.TLabel", foreground=p["muted"], font=FONT_SMALL)
    style.configure("Status.TLabel", foreground=p["text2"], font=FONT_SMALL)
    style.configure("Icon.TLabel", foreground=p["accent"], font=FONT_ICON)
    style.configure("Empty.TLabel", background=p["surface"],
                    foreground=p["muted"], font=FONT_BODY)

    # Secondary buttons: flat, surface coloured, brightening on hover.
    style.configure("TButton", background=p["surface"], foreground=p["text"],
                    borderwidth=0, padding=(14, 9), font=FONT_BODY)
    style.map("TButton",
              background=[("disabled", p["bg"]), ("pressed", p["border"]),
                          ("active", p["hover"])],
              foreground=[("disabled", p["muted"])])

    # The one primary button.
    style.configure("Accent.TButton", background=p["accent"],
                    foreground=p["on_accent"], font=FONT_BOLD)
    style.map("Accent.TButton",
              background=[("disabled", p["surface"]), ("pressed", p["accent_lo"]),
                          ("active", p["accent_hi"])],
              foreground=[("disabled", p["muted"])])

    # The two mode buttons, sitting side by side as one segmented control.
    style.configure("Seg.Toolbutton", background=p["surface"],
                    foreground=p["text2"], borderwidth=0,
                    padding=(16, 8), font=FONT_BODY)
    style.map("Seg.Toolbutton",
              background=[("selected", p["accent"]), ("active", p["hover"])],
              foreground=[("selected", p["on_accent"])])

    style.configure("TEntry", fieldbackground=p["surface"],
                    foreground=p["text2"], insertcolor=p["text"],
                    bordercolor=p["border"], lightcolor=p["border"],
                    darkcolor=p["border"], padding=9)
    style.map("TEntry",
              fieldbackground=[("readonly", p["surface"])],
              foreground=[("readonly", p["text2"])])

    style.configure("TCheckbutton", background=p["bg"], foreground=p["text2"],
                    indicatorbackground=p["surface"],
                    indicatorforeground=p["on_accent"],
                    bordercolor=p["border"], padding=4, font=FONT_BODY)
    style.map("TCheckbutton",
              background=[("active", p["bg"])],
              foreground=[("active", p["text"])],
              indicatorbackground=[("selected", p["accent"]),
                                   ("active", p["hover"])])

    style.configure("Treeview", background=p["surface"],
                    fieldbackground=p["surface"], foreground=p["text"],
                    borderwidth=0, relief="flat", rowheight=32, font=FONT_BODY)
    style.map("Treeview",
              background=[("selected", p["surface"])],
              foreground=[("selected", p["text"])])
    style.configure("Treeview.Heading", background=p["bg"],
                    foreground=p["muted"], relief="flat", borderwidth=0,
                    padding=(10, 10), font=FONT_SMALL)
    style.map("Treeview.Heading", background=[("active", p["bg"])])

    # A thin scrollbar with no arrow buttons at the ends.
    style.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Vertical.TScrollbar", background=p["border"],
                    troughcolor=p["surface"], bordercolor=p["surface"],
                    borderwidth=0, width=10)
    style.map("Vertical.TScrollbar", background=[("active", p["muted"])])

    return style


def enable_dark_titlebar(root):
    """Ask Windows to draw this window's title bar dark (no-op elsewhere).

    Tk cannot style the title bar itself, but Windows will do it on request
    through DWM. Attribute 20 is the documented one; older Windows 10 builds
    used 19, so both are tried. The call only takes effect once the window
    has been hidden and shown again - without that it succeeds and nothing
    changes, which is why the withdraw/deiconify pair is here. Called before
    any widgets exist, so there is nothing to see flicker.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16)
        on = ctypes.c_int(1)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        else:
            return
        root.withdraw()
        root.update_idletasks()
        root.deiconify()
    except Exception:
        pass


def make_dot(color, box=DOT_BOX, diameter=10):
    """Draw a filled circle as a PhotoImage, on a transparent square.

    Treeview colours a whole row at once, so a coloured dot cannot be part
    of the row text. Using the row's image slot instead is what lets each
    destination folder have its own colour. A new PhotoImage starts fully
    transparent, so only the circle itself is painted and the row
    background - including the hover highlight - shows through the rest.
    """
    img = tk.PhotoImage(width=box, height=box)
    radius = diameter / 2.0
    centre = box / 2.0
    for y in range(box):
        offset = y + 0.5 - centre
        if abs(offset) > radius:
            continue
        half = (radius * radius - offset * offset) ** 0.5
        left = int(round(centre - half))
        right = int(round(centre + half))
        if right > left:
            img.put(color, to=(left, y, right, y + 1))
    return img


def make_icon():
    """Draw the little folder mark used in the title bar and taskbar."""
    img = tk.PhotoImage(width=32, height=32)
    img.put(PALETTE["accent_hi"], to=(4, 7, 15, 11))
    img.put(PALETTE["accent"], to=(3, 10, 29, 26))
    return img


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
        self.hover_item = None
        self.dots = {}        # colour -> PhotoImage, kept alive here

        settings = load_settings()
        self.by_extension = tk.BooleanVar(value=settings.get("by_extension", False))
        self.recursive = tk.BooleanVar(value=settings.get("recursive", False))
        self.folder_text = tk.StringVar(value="")

        apply_theme(root)
        self._build_ui()

        remembered = settings.get("folder", "")
        if remembered and Path(remembered).is_dir():
            self.set_folder(Path(remembered))
        else:
            self._update_empty()

    # ------------------------------------------------------------------
    # building the window
    # ------------------------------------------------------------------

    def _build_ui(self):
        p = PALETTE
        self.root.title("FolderSorter")
        self.root.geometry("920x660")
        self.root.minsize(760, 520)

        enable_dark_titlebar(self.root)

        self.icon = make_icon()
        try:
            self.root.iconphoto(True, self.icon)
        except tk.TclError:
            pass

        self.blank = tk.PhotoImage(width=DOT_BOX, height=DOT_BOX)

        # --- header ---
        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=20, pady=(18, 0))
        ttk.Label(head, text="FolderSorter", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="pick what moves, then sort",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0), pady=(7, 0))
        tk.Frame(self.root, bg=p["border"], height=1).pack(
            fill="x", padx=20, pady=(14, 0))

        # --- which folder ---
        row = ttk.Frame(self.root)
        row.pack(fill="x", padx=20, pady=(16, 0))
        ttk.Label(row, text=ICON_FOLDER, style="Icon.TLabel").pack(
            side="left", padx=(2, 12))
        entry = ttk.Entry(row, textvariable=self.folder_text, font=FONT_BODY)
        entry.pack(side="left", fill="x", expand=True)
        entry.state(["readonly"])
        ttk.Button(row, text="Browse", command=self.choose_folder).pack(
            side="left", padx=(10, 0))

        # --- how to sort ---
        opts = ttk.Frame(self.root)
        opts.pack(fill="x", padx=20, pady=(14, 0))
        # The border-coloured frame shows through the 1px gap, which is
        # what makes the two buttons read as one segmented control.
        seg = tk.Frame(opts, bg=p["border"])
        seg.pack(side="left")
        ttk.Radiobutton(seg, text="By category", value=False,
                        variable=self.by_extension, command=self.rescan,
                        style="Seg.Toolbutton").pack(side="left", padx=(0, 1))
        ttk.Radiobutton(seg, text="By file type", value=True,
                        variable=self.by_extension, command=self.rescan,
                        style="Seg.Toolbutton").pack(side="left")
        ttk.Checkbutton(opts, text="Include subfolders", variable=self.recursive,
                        command=self.rescan).pack(side="right", pady=4)

        # --- the plan, as a tree of groups and files ---
        outer = tk.Frame(self.root, bg=p["border"])
        outer.pack(fill="both", expand=True, padx=20, pady=(16, 0))
        wrap = tk.Frame(outer, bg=p["surface"])
        wrap.pack(fill="both", expand=True, padx=1, pady=1)

        self.tree = ttk.Treeview(wrap, columns=("count", "size"),
                                 selectmode="none")
        self.tree.heading("#0", text="   DESTINATION FOLDER  /  FILE", anchor="w")
        self.tree.heading("count", text="FILES", anchor="e")
        self.tree.heading("size", text="SIZE", anchor="e")
        self.tree.column("#0", width=560, stretch=True)
        self.tree.column("count", width=90, anchor="e", stretch=False)
        self.tree.column("size", width=110, anchor="e", stretch=False)

        bar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

        self.tree.tag_configure("group_on", foreground=p["text"], font=FONT_BOLD)
        self.tree.tag_configure("group_off", foreground=p["muted"], font=FONT_BOLD)
        self.tree.tag_configure("on", foreground=p["text2"])
        self.tree.tag_configure("off", foreground=p["muted"])
        self.tree.tag_configure("hover", background=p["hover"])

        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<Motion>", self.on_motion)
        self.tree.bind("<Leave>", lambda e: self._set_hover(None))

        # Shown over the list when there is nothing in it.
        self.empty = ttk.Label(wrap, style="Empty.TLabel", anchor="center")

        # --- status line and buttons ---
        self.status = tk.StringVar(value="")
        foot = ttk.Frame(self.root)
        foot.pack(fill="x", padx=20, pady=(14, 18))
        ttk.Label(foot, textvariable=self.status, style="Status.TLabel").pack(
            side="left", pady=(9, 0))

        self.sort_button = ttk.Button(foot, text="Sort", style="Accent.TButton",
                                      command=self.do_sort)
        self.sort_button.pack(side="right")
        self.undo_button = ttk.Button(foot, text="Undo last run",
                                      command=self.do_undo)
        self.undo_button.pack(side="right", padx=(0, 8))
        ttk.Button(foot, text="Clear",
                   command=lambda: self.set_all(False)).pack(side="right", padx=(0, 8))
        ttk.Button(foot, text="Select all",
                   command=lambda: self.set_all(True)).pack(side="right", padx=(0, 8))

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

    def _dot(self, group_name):
        """The coloured dot image for a destination folder.

        In by-file-type mode the group is called PNG or PDF, so the
        extension is translated back to its category first - that way every
        kind of image gets the same colour.
        """
        color = CATEGORY_COLORS.get(group_name)
        if color is None:
            category = self.ext_map.get("." + group_name.lower(), organizer.OTHER)
            color = CATEGORY_COLORS.get(category, PALETTE["muted"])
        if color not in self.dots:
            self.dots[color] = make_dot(color)
        return self.dots[color]

    def populate(self):
        """Fill the tree: one parent row per destination folder."""
        self.tree.delete(*self.tree.get_children())
        self.hover_item = None
        self.groups = {}
        for index, (_, dest) in enumerate(self.moves):
            self.groups.setdefault(dest.parent.name, []).append(index)

        for name in sorted(self.groups):
            indexes = self.groups[name]
            total = sum(self.sizes[i] for i in indexes)
            self.tree.insert("", "end", iid="g:" + name,
                             text="{}  {}".format(CHECKED, name),
                             image=self._dot(name),
                             values=(len(indexes), human_size(total)))
            for i in indexes:
                self.tree.insert("g:" + name, "end", iid="f:{}".format(i),
                                 text="{}  {}".format(CHECKED, self.labels[i]),
                                 image=self.blank,
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

    def on_motion(self, event):
        """Highlight whichever row the mouse is over."""
        item = self.tree.identify_row(event.y)
        if item != self.hover_item:
            self._set_hover(item or None)

    def _set_hover(self, item):
        """Move the hover highlight from the old row to a new one."""
        previous = self.hover_item
        self.hover_item = item
        for target in (previous, item):
            if target and self.tree.exists(target):
                tags = [t for t in self.tree.item(target, "tags") if t != "hover"]
                if target == item:
                    tags.append("hover")
                self.tree.item(target, tags=tags)

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
                mark, tag = CHECKED, "group_on"
            elif ticked == 0:
                mark, tag = UNCHECKED, "group_off"
            else:
                mark, tag = PARTIAL, "group_on"
            self._draw_row("g:" + name, "{}  {}".format(mark, name), tag)
            for i in indexes:
                on = i in self.checked
                self._draw_row("f:{}".format(i),
                               "{}  {}".format(CHECKED if on else UNCHECKED,
                                               self.labels[i]),
                               "on" if on else "off")
        self.update_status()

    def _draw_row(self, item, text, tag):
        """Set a row's label and tag, keeping the hover highlight if it is there."""
        tags = [tag, "hover"] if item == self.hover_item else [tag]
        self.tree.item(item, text=text, tags=tags)

    def update_status(self):
        picked = len(self.checked)
        if self.folder is None:
            self.status.set("")
        elif not self.moves:
            self.status.set("Nothing to sort")
        else:
            size = sum(self.sizes[i] for i in self.checked)
            self.status.set("{} of {} files selected   ·   {}".format(
                picked, len(self.moves), human_size(size)))
        self.sort_button.state(["!disabled"] if picked else ["disabled"])
        self.undo_button.state(["!disabled"] if self.has_log else ["disabled"])
        self._update_empty()

    def _update_empty(self):
        """Show a message over the list whenever there are no rows in it."""
        if self.folder is None:
            message = "Choose a folder to get started"
        elif not self.moves:
            message = "Nothing to sort — this folder is already tidy"
        else:
            self.empty.place_forget()
            return
        self.empty.configure(text=message)
        self.empty.place(relx=0.5, rely=0.5, anchor="center")

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
        self.status.set("Moved {} files   ·   undo is available".format(len(done)))

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
        note = "Put back {} files".format(restored)
        if missing:
            note += "   ·   {} already gone".format(missing)
        if failed:
            note += "   ·   {} could not be moved back".format(failed)
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
    SorterWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
