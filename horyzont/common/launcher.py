"""Uruchamianie programów, otwieranie plików, folderów i adresów."""
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.parse
from xml.sax.saxutils import escape

from .. import config
from ..i18n import plain, tr

# wbudowane aplikacje środowiska: klucz -> (klucz nazwy, ikona, kategoria, dostępna)
BUILTIN = {
    "explorer": ("app_explorer", "folder_open", "cat_accessories"),
    "notepad": ("notepad", "notepad", "cat_accessories"),
    "taskmgr": ("taskmgr", "taskmgr", "cat_system"),
    "control": ("control_panel", "control_panel", "cat_system"),
    "terminal": ("app_terminal", "terminal", "cat_accessories"),
    "calc": ("app_calc", "calculator", "cat_accessories"),
    "charmap": ("app_charmap", "charmap", "cat_system"),
    "paint": ("app_paint", "paint", "cat_accessories"),
    "wordpad": ("app_wordpad", "wordpad", "cat_accessories"),
    "imageviewer": ("app_imageviewer", "image_viewer", "cat_accessories"),
    "mplayer": ("app_mplayer", "media_player", "cat_multimedia"),
    "soundrec": ("app_soundrec", "recorder", "cat_multimedia"),
    "mines": ("app_mines", "mines", "cat_games"),
    "solitaire": ("app_solitaire", "cards", "cat_games"),
}

# rozszerzenia otwierane wbudowanymi programami, gdy w systemie nie ustawiono innego domyślnego
BUILTIN_VIEWERS = {
    "imageviewer": {".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".bmp", ".dib", ".tif", ".tiff", ".webp", ".ico",
                    ".xpm", ".pbm", ".pgm", ".ppm", ".tga", ".heic", ".avif"},
    "wordpad": {".rtf", ".docx", ".odt", ".doc", ".wri"},
    "mplayer": {".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".wma", ".mid", ".midi", ".mp4", ".mkv",
                ".avi", ".webm", ".mov", ".wmv", ".mpg", ".mpeg", ".m4v", ".ogv", ".m3u", ".m3u8", ".pls"},
    "soundrec": {".wav"},
}

# polecenia znane z klasycznych systemów, wpisywane w oknie Uruchamianie
RUN_ALIASES = {
    "notepad": ("builtin", "notepad"),
    "notepad.exe": ("builtin", "notepad"),
    "explorer": ("builtin", "explorer"),
    "explorer.exe": ("builtin", "explorer"),
    "taskmgr": ("builtin", "taskmgr"),
    "taskmgr.exe": ("builtin", "taskmgr"),
    "control": ("builtin", "control"),
    "control.exe": ("builtin", "control"),
    "cmd": ("builtin", "terminal"),
    "cmd.exe": ("builtin", "terminal"),
    "command": ("builtin", "terminal"),
    "desk.cpl": ("control", "display"),
    "timedate.cpl": ("control", "datetime"),
    "main.cpl": ("control", "mouse"),
    "mmsys.cpl": ("control", "sound"),
    "sysdm.cpl": ("control", "system"),
    "appwiz.cpl": ("control", "addremove"),
    "ncpa.cpl": ("control", "network"),
    "nusrmgr.cpl": ("control", "users"),
    "intl.cpl": ("control", "regional"),
    "powercfg.cpl": ("control", "power"),
    "access.cpl": ("control", "access"),
    "fonts": ("control", "fonts"),
    "services.msc": ("control", "services"),
    "winver": ("builtin", "winver"),
    "winver.exe": ("builtin", "winver"),
    "calc": ("builtin", "calc"), "calc.exe": ("builtin", "calc"),
    "charmap": ("builtin", "charmap"), "charmap.exe": ("builtin", "charmap"),
    "mspaint": ("builtin", "paint"), "mspaint.exe": ("builtin", "paint"), "pbrush": ("builtin", "paint"),
    "paint": ("builtin", "paint"),
    "wordpad": ("builtin", "wordpad"), "wordpad.exe": ("builtin", "wordpad"), "write": ("builtin", "wordpad"),
    "write.exe": ("builtin", "wordpad"),
    "winmine": ("builtin", "mines"), "winmine.exe": ("builtin", "mines"), "saper": ("builtin", "mines"),
    "sol": ("builtin", "solitaire"), "sol.exe": ("builtin", "solitaire"), "pasjans": ("builtin", "solitaire"),
    "wmplayer": ("builtin", "mplayer"), "wmplayer.exe": ("builtin", "mplayer"), "mplayer2": ("builtin", "mplayer"),
    "mplay32": ("builtin", "mplayer"),
    "sndrec32": ("builtin", "soundrec"), "sndrec32.exe": ("builtin", "soundrec"),
    "shimgvw": ("builtin", "imageviewer"),
}

TERMINALS = ["ptyxis", "gnome-terminal", "konsole", "xfce4-terminal", "foot", "alacritty", "kitty",
             "wezterm", "lxterminal", "mate-terminal", "xterm"]

# rozszerzenia otwierane wbudowanym Notatnikiem
NOTEPAD_EXT = {".txt", ".log", ".ini", ".cfg", ".conf", ".nfo", ".md", ".csv", ".json", ".xml", ".sh",
               ".py", ".c", ".h", ".cpp", ".js", ".css", ".yaml", ".yml", ".toml", ".desktop", ".service"}


def _spawn(args, cwd=None, env=None):
    try:
        subprocess.Popen(args, cwd=cwd or os.path.expanduser("~"), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                         env=env)
        return True
    except (OSError, ValueError) as e:
        print("horyzont: nie można uruchomić", args, e, file=sys.stderr)
        return False


def builtin_command(name, args=()):
    return [sys.executable, "-m", "horyzont", name, *args]


def start_builtin(name, args=()):
    """Uruchamia wbudowaną aplikację; jeśli już działa, przekazuje jej argumenty."""
    if name == "terminal":
        name = "cmd"
    note_program(f"builtin:{name}")
    try:
        from .single import try_forward
        from PySide6.QtCore import QCoreApplication
        if QCoreApplication.instance() is not None and try_forward(name, args, 150):
            return True
    except Exception:
        pass
    env = dict(os.environ)
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env["PYTHONPATH"] = pkg_root + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return _spawn(builtin_command(name, args), env=env)


def open_terminal(cwd=None):
    """Wiersz polecenia Horyzontu (albo zewnętrzny terminal wybrany w ustawieniach)."""
    ext = config.get("terminal_app", "")
    if not ext:
        return start_builtin("cmd", ["--cwd", cwd] if cwd else [])
    for t in [ext] + TERMINALS:
        path = shutil.which(t)
        if path:
            args = [path]
            if cwd:
                if t in ("gnome-terminal", "ptyxis", "xfce4-terminal", "mate-terminal"):
                    args.append(f"--working-directory={cwd}")
                elif t == "konsole":
                    args += ["--workdir", cwd]
                elif t == "foot":
                    args.append(f"--working-directory={cwd}")
            return _spawn(args, cwd=cwd)
    return False


def launch_entry(entry, files=()):
    args = entry.command(files)
    if not args:
        return False
    note_program(f"desktop:{entry.id}")
    if entry.terminal and not config.get("terminal_app", ""):
        return start_builtin("cmd", ["--exec"] + list(args))
    if entry.terminal:
        for t in TERMINALS:
            path = shutil.which(t)
            if path:
                if t in ("gnome-terminal", "ptyxis"):
                    args = [path, "--"] + args
                else:
                    args = [path, "-e"] + args
                break
    return _spawn(args, cwd=entry.path_dir or None)


def note_program(key):
    """Liczy uruchomienia programów — z tego powstaje lista najczęściej używanych w menu Start."""
    try:
        rp = dict(config.get("recent_programs", {}))
        rp[key] = rp.get(key, 0) + 1
        config.set("recent_programs", rp)
    except Exception:
        pass


def is_url(s):
    return bool(urllib.parse.urlparse(s).scheme in ("http", "https", "ftp", "mailto", "file")) or s.startswith("www.")


def xdg_open(target):
    for tool in (["gio", "open"], ["xdg-open"]):
        if shutil.which(tool[0]):
            return _spawn(tool + [target])
    return False


def open_path(path, with_entry=None):
    """Otwiera plik lub folder tak jak dwukrotne kliknięcie w Eksploratorze."""
    path = os.path.expanduser(path)
    if path.startswith("horyzont:"):
        return start_builtin("explorer", [path])
    if os.path.isdir(path):
        return start_builtin("explorer", [path])
    if not os.path.exists(path):
        return False
    add_recent_document(path)
    if with_entry is not None:
        return launch_entry(with_entry, [path])
    if path.endswith(".desktop"):
        from .desktopentry import parse
        e = parse(path)
        if e:
            return launch_entry(e)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".msstyles", ".theme"):
        return start_builtin("control", ["display", "--load-style", path])
    if ext == ".msicon":
        return start_builtin("control", ["display", "--install-icons", path])
    if with_entry is None and config.get("explorer_browse_archives", True):
        from . import archives
        if archives.is_archive(path):
            return start_builtin("explorer", [path])
    if ext in NOTEPAD_EXT and config.get("notepad_for_text", True):
        return start_builtin("notepad", [path])
    builtin = builtin_for_path(path)
    if builtin:
        return start_builtin(builtin, [path])
    if os.access(path, os.X_OK) and _is_elf(path):
        return _spawn([path], cwd=os.path.dirname(path))
    return xdg_open(path)


def builtin_for_path(path):
    """Wbudowany program dla pliku, jeśli użytkownik nie wybrał w systemie innego domyślnego programu."""
    ext = os.path.splitext(path)[1].lower()
    key = next((k for k, exts in BUILTIN_VIEWERS.items() if ext in exts), None)
    if key is None:
        return None
    try:
        import mimetypes
        from .desktopentry import default_for_mime
        mime = mimetypes.guess_type(path)[0]
        default = default_for_mime(mime) if mime else None
        if default and not default.startswith("horyzont-"):
            return None
    except Exception:
        pass
    return key


def _is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def run_command(text):
    """Polecenie z okna Uruchamianie. Zwraca True, jeśli udało się coś uruchomić."""
    text = text.strip()
    if not text:
        return False
    low = text.lower()
    if low in RUN_ALIASES:
        kind, target = RUN_ALIASES[low]
        if kind == "builtin":
            return start_builtin(target)
        return start_builtin("control", [target])
    first = low.split()[0]
    if first in RUN_ALIASES and RUN_ALIASES[first][0] == "builtin":
        rest = shlex.split(text)[1:]
        return start_builtin(RUN_ALIASES[first][1], rest)
    if is_url(text):
        if text.startswith("www."):
            text = "https://" + text
        return xdg_open(text)
    p = os.path.expanduser(text)
    if os.path.exists(p):
        return open_path(p)
    try:
        args = shlex.split(text)
    except ValueError:
        return False
    if not args:
        return False
    exe = shutil.which(os.path.expanduser(args[0]))
    if exe:
        return _spawn([exe] + args[1:])
    # nazwa aplikacji z menu
    from .desktopentry import all_entries
    for e in all_entries().values():
        if e.visible() and (e.name.lower() == low or e.id.lower() == low + ".desktop"):
            return launch_entry(e)
    return False


# --- ostatnio używane dokumenty (format XBEL współdzielony z GTK) -------
RECENT_FILE = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "recently-used.xbel")


def recent_documents(limit=15):
    import xml.etree.ElementTree as ET
    out = []
    try:
        tree = ET.parse(RECENT_FILE)
    except (OSError, ET.ParseError):
        return out
    items = []
    for b in tree.getroot().findall("bookmark"):
        href = b.get("href", "")
        if not href.startswith("file://"):
            continue
        path = urllib.parse.unquote(href[7:])
        if not os.path.exists(path):
            continue
        items.append((b.get("visited") or b.get("modified") or "", path))
    items.sort(reverse=True)
    seen = set()
    for _, p in items:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def add_recent_document(path):
    import xml.etree.ElementTree as ET
    path = os.path.abspath(path)
    href = "file://" + urllib.parse.quote(path)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        if os.path.exists(RECENT_FILE):
            tree = ET.parse(RECENT_FILE)
            root = tree.getroot()
        else:
            root = ET.Element("xbel", version="1.0")
            tree = ET.ElementTree(root)
        found = None
        for b in root.findall("bookmark"):
            if b.get("href") == href:
                found = b
                break
        if found is None:
            found = ET.SubElement(root, "bookmark", href=href, added=now)
        found.set("modified", now)
        found.set("visited", now)
        os.makedirs(os.path.dirname(RECENT_FILE), exist_ok=True)
        tree.write(RECENT_FILE, encoding="utf-8", xml_declaration=True)
    except Exception:
        pass


def clear_recent_documents():
    try:
        os.remove(RECENT_FILE)
    except OSError:
        pass


def default_app(kind):
    """Domyślna przeglądarka ('browser') lub program pocztowy ('email') jako DesktopEntry."""
    from .desktopentry import all_entries, default_for_mime
    entries = all_entries()
    mime = {"browser": "x-scheme-handler/https", "email": "x-scheme-handler/mailto"}[kind]
    did = default_for_mime(mime) or (default_for_mime("x-scheme-handler/http") if kind == "browser" else "")
    if did and did in entries:
        return entries[did]
    wanted = ({"WebBrowser"} if kind == "browser" else {"Email"})
    for e in entries.values():
        if e.visible() and wanted & set(e.categories):
            return e
    return None
