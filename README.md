# FolderSorter

A small, dependency-free Python script that tidies up a messy folder. It looks at every file, works out which category it belongs to from its extension, and moves it into a folder of that name — `Images/`, `Documents/`, `Music/`, and so on.

It is deliberately careful: it shows you the whole plan and **asks before it moves anything**, and every run can be reversed with a single `--undo`.

## Features

- Sorts files into **10 categories** by extension: Images, Documents, Music, Videos, Archives, Installers, Code, Fonts, Shortcuts, and Other
- **Asks first**: prints the full move plan as a table, then waits for a `y` before touching anything
- **`--undo`**: every sort writes a small log file, so the whole thing can be put back exactly as it was
- **Never overwrites**: a name clash becomes `photo (1).jpg`, `photo (2).jpg`, …
- **Safe to run twice**: files already sitting in a category folder are left alone
- **`--dry-run`** to preview without even being asked
- **`--recursive`** to also pull files up out of subfolders
- Skips hidden files and folders (`.git`, dotfiles) and OS clutter (`desktop.ini`, `Thumbs.db`) — and never moves itself
- One locked or in-use file doesn't abort the run; it's reported at the end
- **Colorful terminal UI**: an ASCII-art logo with a color gradient and a clean plan table (auto-disabled when piping to a file, or with `--no-color` / `--no-logo`)
- Standard library only — nothing to install

## Requirements

- Python 3.7+

No third-party packages needed. Works on **Windows, macOS, and Linux** (standard library only).

## Usage

```bash
python organizer.py <folder> [options]
```

> **Linux / macOS:** use `python3` instead of `python`.

If you leave out the folder, it sorts the folder you are currently in.

### Options

| Option | Description | Default |
| --- | --- | --- |
| `folder` | Folder to organize (positional) | current folder |
| `--dry-run` | Only show the plan; never ask, never move | off |
| `-y`, `--yes` | Skip the confirmation prompt | asks first |
| `--undo` | Put back everything the last run moved | — |
| `-r`, `--recursive` | Also pull files out of subfolders | top level only |
| `--no-color` | Disable colored output | colors on (if terminal) |
| `--no-logo` | Hide the ASCII-art logo | logo shown |

### Examples

```bash
# See what would happen to your Downloads folder, without being asked anything
python organizer.py ~/Downloads --dry-run

# Sort the Desktop (shows the plan, then asks for confirmation)
python organizer.py C:\Users\me\Desktop

# Sort without the prompt, subfolders included
python organizer.py ~/Downloads -r -y

# Changed your mind
python organizer.py ~/Downloads --undo
```

### Sample output

In a real terminal the logo has a cyan→blue gradient and the destinations are green; here is the plain-text shape:

```
    ______        __     __           _____              __
   / ____/____   / /____/ /___   ____/ ___/ ____   ____ / /_ ___   ____
  / /_   / __ \ / // __  // _ \ / __/\__ \ / __ \ / __// __// _ \ / __/
 / __/  / /_/ // // /_/ //  __// /  ___/ // /_/ // /  / /_ /  __// /
/_/     \____//_/ \__,_/ \___//_/  /____/ \____//_/   \__/ \___//_/
                                                          by @anjomozda

  Folder   C:\Users\me\Desktop
  Plan     24 files to sort   ·   9 categories   ·   top level only

  FILE                                        DESTINATION
  ──────────────────────────────────────────────────────────────────────
  ● arhiva.zip                                Archives/
  ● cv.pdf                                    Documents/
  ● Discord.lnk                               Shortcuts/
  ● logo.png                                  Images/
  ● pesma.mp3                                 Music/
  ● reportaza.mp4                             Videos/
  ● setup.exe                                 Installers/
  ● slika.png                                 Images/slika (1).png
  ● nesto.xyz                                 Other/

  Move 24 files? [y/N] y

  ✓ 24 moved   ·   0.1s
  Undo with:  python organizer.py "C:\Users\me\Desktop" --undo
```

## ⚠️ Safety

Moving files around in bulk is the kind of thing you want to be able to take back, so:

- **Nothing moves without a `y`.** Running the script with no options only shows you the plan and then asks.
- **Use `--dry-run` first** on a folder you care about, to see exactly what would happen.
- **`--undo` reverses the last run** in that folder, using the `.foldersorter-log.json` file written next to your files. Deleting that log means the run can no longer be undone automatically.
- Only the **last** run is remembered — each sort replaces the previous log.
- `--recursive` empties out your subfolders into the category folders. That's the point, but it's a bigger change than the default, so preview it with `--dry-run` first.

## How it works

The category table is flattened once into a plain `{".png": "Images", ...}` dictionary, so classifying a file is a single dict lookup on `Path.suffix`. Anything with an unknown extension — or no extension at all — goes to `Other/`.

The script then builds the complete list of `(source, destination)` pairs **before** moving anything. Destinations are checked against both the disk and the names already handed out during this run, which is what stops two files called `slika.png` from different subfolders from colliding with each other.

Files are moved with `shutil.move` rather than `os.rename`, so moving across drives works, and each move is wrapped individually — a single locked file gets reported instead of aborting the run. Afterwards the successful moves are written to `.foldersorter-log.json`, and `--undo` simply walks that list backwards, moving every file back to the path it came from and removing the category folders it emptied.

Making a second run harmless is just a matter of skipping any file whose top-level folder is already one of the category names, so sorting an already-sorted folder reports "nothing to do" instead of building `Images/Images/`.
