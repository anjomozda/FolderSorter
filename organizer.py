"""
FolderSorter - tidy up a messy folder by sorting files into folders by type.

Looks at every file in a folder, decides which category it belongs to based
on its extension (Images, Documents, Music, Videos, ...), and moves it into
a folder of that name. Name clashes are resolved by adding " (1)", " (2)",
so nothing is ever overwritten.

By default it is careful: it prints the full plan first and asks for
confirmation before touching anything. Every run writes a small log file,
so a sort can always be reversed with --undo.

Prints a colorful terminal report: an ASCII-art logo, the move plan as a
table, and a summary. Colors turn off automatically when the output is not
a terminal (e.g. piped to a file), or with --no-color.

Usage examples:
    python organizer.py C:\\Users\\me\\Downloads
    python organizer.py ~/Downloads --dry-run
    python organizer.py ~/Downloads -y
    python organizer.py ~/Downloads --recursive
    python organizer.py ~/Downloads --undo
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Which extensions land in which folder. Everything unknown goes to "Other".
CATEGORIES = {
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
               ".ico", ".tif", ".tiff", ".heic", ".raw", ".psd"},
    "Documents": {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt",
                  ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".epub", ".mobi"},
    "Music": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".mid"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Installers": {".exe", ".msi", ".msix", ".appx", ".deb", ".rpm", ".dmg", ".pkg"},
    "Code": {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json",
             ".xml", ".yml", ".yaml", ".sql", ".sh", ".ps1", ".bat", ".ipynb",
             ".c", ".cpp", ".h", ".java", ".rb", ".go", ".rs", ".php"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2"},
    "Shortcuts": {".lnk", ".url", ".desktop"},
}

# Fallback folder for extensions we don't recognise.
OTHER = "Other"

# The undo log, written into the folder that was sorted.
LOG_NAME = ".foldersorter-log.json"

# Files we never touch, whatever their extension.
ALWAYS_SKIP = {"desktop.ini", "thumbs.db", LOG_NAME}

# Don't flood the terminal when sorting hundreds of files.
MAX_PLAN_ROWS = 40

# ANSI style codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GRAY = "\033[90m"

# ASCII-art logo (figlet "slant"). Colored with a cyan -> blue gradient,
# one 256-color code per line.
LOGO_LINES = [
    r"    ______        __     __           _____              __            ",
    r"   / ____/____   / /____/ /___   ____/ ___/ ____   ____ / /_ ___   ____",
    r"  / /_   / __ \ / // __  // _ \ / __/\__ \ / __ \ / __// __// _ \ / __/",
    r" / __/  / /_/ // // /_/ //  __// /  ___/ // /_/ // /  / /_ /  __// /   ",
    r"/_/     \____//_/ \__,_/ \___//_/  /____/ \____//_/   \__/ \___//_/    ",
]
LOGO_GRADIENT = [51, 45, 39, 33, 27]  # bright cyan -> blue
LOGO_WIDTH = max(len(line) for line in LOGO_LINES)

TAG = "@anjomozda"

# Width of the table divider lines.
RULE = 70


class Style:
    """Small helper that wraps text in ANSI codes, or not, if disabled."""

    def __init__(self, enabled):
        self.enabled = enabled

    def __call__(self, text, *codes):
        if not self.enabled or not codes:
            return text
        return "".join(codes) + text + RESET


def enable_windows_ansi():
    """Turn on ANSI escape handling in the Windows console (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def build_extension_map():
    """Flatten CATEGORIES into a flat {'.png': 'Images', ...} lookup table.

    Built once, so deciding a file's category is a single dict lookup
    instead of a search through every category.
    """
    mapping = {}
    for category, extensions in CATEGORIES.items():
        for ext in extensions:
            mapping[ext] = category
    return mapping


def category_for(path, ext_map):
    """Return the category folder name for a file, or 'Other' if unknown."""
    return ext_map.get(path.suffix.lower(), OTHER)


def collect_files(folder, recursive, skip):
    """Collect the files in `folder` that should be sorted.

    Skips anything already sitting in a category folder (so running twice
    is harmless), hidden files and folders, OS bookkeeping files, and the
    paths in `skip` - which is how the script avoids moving itself.
    """
    category_dirs = set(CATEGORIES) | {OTHER}
    entries = folder.rglob("*") if recursive else folder.iterdir()

    files = []
    for entry in entries:
        if not entry.is_file():
            continue
        rel = entry.relative_to(folder)
        # Already sorted, or tucked away in a hidden folder like .git
        if len(rel.parts) > 1 and rel.parts[0] in category_dirs:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if entry.name.lower() in ALWAYS_SKIP:
            continue
        if entry.resolve() in skip:
            continue
        files.append(entry)

    return sorted(files)


def unique_destination(dest, taken):
    """Return a free path for `dest`, adding ' (1)', ' (2)', ... if needed.

    Checks both the disk and `taken` - the names already handed out during
    this run - so two files with the same name never collide with each
    other either.
    """
    candidate = dest
    counter = 1
    while candidate in taken or candidate.exists():
        candidate = dest.with_name("{} ({}){}".format(dest.stem, counter, dest.suffix))
        counter += 1
    taken.add(candidate)
    return candidate


def plan_moves(files, folder, ext_map):
    """Work out where every file should go. Returns a list of (src, dest)."""
    taken = set()
    moves = []
    for src in files:
        category = category_for(src, ext_map)
        dest = unique_destination(folder / category / src.name, taken)
        moves.append((src, dest))
    return moves


def apply_moves(moves):
    """Carry out the planned moves. Returns (done, failures).

    One unmovable file (locked, in use, no permission) must not abort the
    whole run, so every move is guarded individually.
    """
    done = []
    failures = []
    for src, dest in moves:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            done.append((src, dest))
        except OSError as exc:
            failures.append((src, exc))
    return done, failures


def write_log(folder, done):
    """Record what was moved, so --undo can put it all back."""
    log = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "folder": str(folder),
        "moves": [{"from": str(src), "to": str(dest)} for src, dest in done],
    }
    log_path = folder / LOG_NAME
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return log_path


def prune_empty_categories(folder):
    """Remove category folders left empty after an undo."""
    for name in list(CATEGORIES) + [OTHER]:
        target = folder / name
        try:
            if target.is_dir() and not any(target.iterdir()):
                target.rmdir()
        except OSError:
            pass


def undo(st, folder):
    """Move everything from the last run back where it came from."""
    log_path = folder / LOG_NAME
    if not log_path.exists():
        print("  " + st("Nothing to undo - no log file in this folder.", YELLOW))
        print("  " + st("A log is only written after files are actually moved.", DIM))
        return

    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("  " + st("Could not read the log file - it looks damaged.", RED))
        return

    when = log.get("when", "?")
    entries = log.get("moves", [])
    print("  {}   {}".format(st("Undoing", DIM), st(when, BOLD)))
    print("  {}     {} {}".format(st("Files", DIM), len(entries),
                                  st("recorded", DIM)))
    print()

    restored = 0
    missing = 0
    failed = 0
    taken = set()
    # Reverse order, so files land back in the order they were taken.
    for entry in reversed(entries):
        current = Path(entry["to"])
        original = Path(entry["from"])
        if not current.exists():
            missing += 1
            continue
        try:
            target = unique_destination(original, taken)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(target))
            restored += 1
        except OSError:
            failed += 1

    prune_empty_categories(folder)
    if not failed:
        try:
            log_path.unlink()
        except OSError:
            pass

    dot = st("\u00b7", GRAY)
    line = "  {} {}".format(st("\u2713", GREEN),
                            st("{} restored".format(restored), BOLD, GREEN))
    if missing:
        line += "   {}   {}".format(dot, st("{} already gone".format(missing), YELLOW))
    if failed:
        line += "   {}   {}".format(dot, st("{} failed".format(failed), RED))
    print(line)


def print_logo(st, use_color):
    """Print the ASCII-art logo with a color gradient and the author tag."""
    print()
    for line, code in zip(LOGO_LINES, LOGO_GRADIENT):
        if use_color:
            print("  \033[38;5;{}m{}{}".format(code, line, RESET))
        else:
            print("  " + line)
    tag_line = "by {}".format(TAG).rjust(LOGO_WIDTH)
    print("  " + st(tag_line, MAGENTA))
    print()


def print_info(st, folder, moves, recursive):
    """Print a compact info block above the plan."""
    scope = "including subfolders" if recursive else "top level only"
    categories = len({dest.parent.name for _, dest in moves})
    dot = st("\u00b7", GRAY)
    print("  {}   {}".format(st("Folder", DIM), st(str(folder), BOLD)))
    print("  {}     {} files to sort   {}   {} categories   {}   {}".format(
        st("Plan", DIM), len(moves), dot, categories, dot, st(scope, GRAY)))
    print()


def print_plan(st, moves, folder):
    """Print the move plan as a table: which file goes where."""
    header = "  {:<44}{}".format("FILE", "DESTINATION")
    print(st(header, DIM, BOLD))
    print("  " + st("\u2500" * RULE, GRAY))

    for src, dest in moves[:MAX_PLAN_ROWS]:
        name = str(src.relative_to(folder))
        # Truncate below the column width, so there is always a gap before
        # the destination column even for a name that fills it exactly.
        if len(name) > 40:
            name = name[:37] + "..."
        # Show the new name too, but only when we had to rename the file.
        if dest.name == src.name:
            target = dest.parent.name + "/"
        else:
            target = "{}/{}".format(dest.parent.name, dest.name)
        row = ("  " + st("\u25cf", CYAN) + " "
               + st("{:<42}".format(name), BOLD)
               + st(target, GREEN))
        print(row.rstrip())

    hidden = len(moves) - MAX_PLAN_ROWS
    if hidden > 0:
        print("  " + st("... and {} more".format(hidden), DIM))
    print()


def print_summary(st, folder, moved, failures, duration):
    """Print the result of an actual sort, plus how to undo it."""
    dot = st("\u00b7", GRAY)
    line = "  {} {}   {}   {}".format(
        st("\u2713", GREEN),
        st("{} moved".format(moved), BOLD, GREEN),
        dot,
        st("{:.1f}s".format(duration), DIM))
    if failures:
        line += "   {}   {}".format(dot, st("{} failed".format(len(failures)), RED))
    print(line)

    for src, exc in failures[:5]:
        print("    " + st("! {}: {}".format(src.name, exc), RED))

    if moved:
        command = 'python organizer.py "{}" --undo'.format(folder)
        print("  {}  {}".format(st("Undo with:", DIM), st(command, CYAN)))


def print_footer(st):
    """Print a divider and the author signature."""
    print()
    print("  " + st("\u2500" * 48, GRAY))
    print("  " + st("made by anjomozda  \u00b7  github.com/anjomozda", DIM))


def confirm(st, count):
    """Ask before moving anything. Returns True only on an explicit yes."""
    if not sys.stdin.isatty():
        print("  " + st("Not running in a terminal - nothing was moved.", YELLOW))
        print("  " + st("Re-run with --yes to sort without being asked.", DIM))
        return False
    prompt = "  {} {} ".format(
        st("Move {} files?".format(count), BOLD),
        st("[y/N]", GRAY))
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    print()
    return answer in ("y", "yes")


def main():
    # --- CLI arguments ---
    parser = argparse.ArgumentParser(
        description="Tidy up a folder by sorting files into folders by type")
    parser.add_argument("folder", nargs="?", default=".",
                        help="folder to organize (default: current folder)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only show the plan, never move anything")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--undo", action="store_true",
                        help="put back everything the last run moved")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="also pull files out of subfolders")
    parser.add_argument("--no-color", action="store_true",
                        help="disable colored output")
    parser.add_argument("--no-logo", action="store_true",
                        help="hide the ASCII-art logo")
    args = parser.parse_args()

    # Reconfigure stdout to UTF-8 so box-drawing glyphs render everywhere.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Colors on only for a real terminal, unless explicitly disabled.
    use_color = sys.stdout.isatty() and not args.no_color
    if use_color:
        enable_windows_ansi()
    st = Style(use_color)

    if not args.no_logo:
        print_logo(st, use_color)

    # --- Check the target folder exists ---
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print("  " + st("Error: '{}' is not a folder.".format(args.folder), RED))
        return

    if args.undo:
        undo(st, folder)
        print_footer(st)
        print()
        return

    # --- Work out what would move where ---
    ext_map = build_extension_map()
    skip = {Path(__file__).resolve()}
    files = collect_files(folder, args.recursive, skip)
    moves = plan_moves(files, folder, ext_map)

    if not moves:
        print("  " + st("Nothing to do - this folder is already tidy.", GREEN))
        print_footer(st)
        print()
        return

    print_info(st, folder, moves, args.recursive)
    print_plan(st, moves, folder)

    # --- Move, but only with permission ---
    if args.dry_run:
        print("  " + st("DRY RUN - nothing was moved.", YELLOW))
        print("  " + st("Re-run without --dry-run to sort for real.", DIM))
    elif args.yes or confirm(st, len(moves)):
        start = time.time()
        done, failures = apply_moves(moves)
        duration = time.time() - start
        if done:
            write_log(folder, done)
        print_summary(st, folder, len(done), failures, duration)
    else:
        print("  " + st("Cancelled - nothing was moved.", YELLOW))

    print_footer(st)
    print()


if __name__ == "__main__":
    main()
