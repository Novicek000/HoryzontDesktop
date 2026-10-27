"""Odczyt plików .desktop (freedesktop) — lista aplikacji do menu Start."""
import os
import re
import shlex

from ..i18n import lang_code


def data_dirs():
    home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    out = [home] + dirs
    extra = ["/var/lib/flatpak/exports/share", os.path.expanduser("~/.local/share/flatpak/exports/share")]
    for e in extra:
        if e not in out:
            out.append(e)
    return out


class DesktopEntry:
    __slots__ = ("path", "id", "name", "generic", "comment", "exec", "icon", "categories", "terminal",
                 "nodisplay", "wmclass", "type", "keywords", "try_exec", "path_dir", "only_show_in",
                 "not_show_in", "mimetypes")

    def __init__(self, path):
        self.path = path
        self.id = os.path.basename(path)
        self.name = self.generic = self.comment = self.exec = self.icon = ""
        self.categories = []
        self.terminal = False
        self.nodisplay = False
        self.wmclass = ""
        self.type = "Application"
        self.keywords = []
        self.try_exec = ""
        self.path_dir = ""
        self.only_show_in = []
        self.not_show_in = []
        self.mimetypes = []

    def command(self, files=()):
        return expand_exec(self.exec, files, self)

    def visible(self):
        if self.nodisplay or self.type != "Application" or not self.exec:
            return False
        desk = "Horyzont"
        if self.only_show_in and desk not in self.only_show_in and "X-Horyzont" not in self.only_show_in:
            return False
        if desk in self.not_show_in:
            return False
        if self.try_exec:
            te = self.try_exec
            if os.path.isabs(te):
                if not os.access(te, os.X_OK):
                    return False
            elif not _which(te):
                return False
        return True


def _which(cmd):
    for d in os.environ.get("PATH", "/usr/bin:/bin").split(":"):
        p = os.path.join(d, cmd)
        if os.access(p, os.X_OK) and not os.path.isdir(p):
            return p
    return None


def parse(path):
    lang = lang_code()
    entry = DesktopEntry(path)
    section = None
    loc = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    section = line[1:-1]
                    continue
                if section != "Desktop Entry" or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                m = re.match(r"^(\w[\w-]*)\[([^\]]+)\]$", k)
                if m:
                    key, l = m.group(1), m.group(2)
                    if l == lang or l.split("_")[0] == lang:
                        # dokładniejsze dopasowanie wygrywa
                        if key not in loc or l == lang:
                            loc[key] = v
                    continue
                if k == "Name":
                    entry.name = v
                elif k == "GenericName":
                    entry.generic = v
                elif k == "Comment":
                    entry.comment = v
                elif k == "Exec":
                    entry.exec = v
                elif k == "Icon":
                    entry.icon = v
                elif k == "Categories":
                    entry.categories = [c for c in v.split(";") if c]
                elif k == "Terminal":
                    entry.terminal = v.lower() == "true"
                elif k in ("NoDisplay", "Hidden"):
                    entry.nodisplay = entry.nodisplay or v.lower() == "true"
                elif k == "StartupWMClass":
                    entry.wmclass = v
                elif k == "Type":
                    entry.type = v
                elif k == "Keywords":
                    entry.keywords = [c for c in v.split(";") if c]
                elif k == "TryExec":
                    entry.try_exec = v
                elif k == "Path":
                    entry.path_dir = v
                elif k == "MimeType":
                    entry.mimetypes = [c for c in v.split(";") if c]
                elif k == "OnlyShowIn":
                    entry.only_show_in = [c for c in v.split(";") if c]
                elif k == "NotShowIn":
                    entry.not_show_in = [c for c in v.split(";") if c]
    except OSError:
        return None
    entry.name = loc.get("Name", entry.name)
    entry.generic = loc.get("GenericName", entry.generic)
    entry.comment = loc.get("Comment", entry.comment)
    if "Keywords" in loc:
        entry.keywords = [c for c in loc["Keywords"].split(";") if c]
    return entry


def expand_exec(exe, files=(), entry=None):
    """Zamienia kody pól (%f, %u, %F...) i zwraca listę argumentów."""
    try:
        parts = shlex.split(exe)
    except ValueError:
        parts = exe.split()
    out = []
    files = list(files)
    for part in parts:
        if part in ("%f", "%u"):
            if files:
                out.append(files[0])
            continue
        if part in ("%F", "%U"):
            out.extend(files)
            continue
        if part == "%i":
            if entry and entry.icon:
                out += ["--icon", entry.icon]
            continue
        if part == "%c":
            if entry:
                out.append(entry.name)
            continue
        if part == "%k":
            if entry:
                out.append(entry.path)
            continue
        part = re.sub(r"%[dDnNvmfFuU]", "", part).replace("%%", "%")
        if part:
            out.append(part)
    return out


_cache = None


def all_entries(refresh=False):
    """Słownik id -> DesktopEntry (wpisy z wcześniejszych katalogów mają pierwszeństwo)."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    seen = {}
    for d in data_dirs():
        appdir = os.path.join(d, "applications")
        if not os.path.isdir(appdir):
            continue
        for root, dirs, files in os.walk(appdir):
            for fn in files:
                if not fn.endswith(".desktop"):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), appdir).replace(os.sep, "-")
                if rel in seen:
                    continue
                e = parse(os.path.join(root, fn))
                if e is None:
                    continue
                e.id = rel
                seen[rel] = e
    _cache = seen
    return seen


def find_for_app_id(app_id):
    """Szuka wpisu .desktop pasującego do app_id okna (Wayland) lub klasy WM."""
    if not app_id:
        return None
    entries = all_entries()
    aid = app_id.lower()
    cand = [aid + ".desktop", aid.split(".")[-1] + ".desktop"]
    for c in cand:
        for k, e in entries.items():
            if k.lower() == c:
                return e
    for e in entries.values():
        if e.wmclass and e.wmclass.lower() == aid:
            return e
    for e in entries.values():
        base = os.path.basename(shlex.split(e.exec)[0]).lower() if e.exec else ""
        if base == aid:
            return e
    return None


# --- przypisanie kategorii do folderów menu Start ----------------------
CATEGORY_FOLDERS = [
    ("cat_games", {"Game"}),
    ("cat_accessories", {"Utility", "TextEditor", "Calculator", "Archiving", "Accessibility", "Clock"}),
    ("cat_graphics", {"Graphics"}),
    ("cat_internet", {"Network", "WebBrowser", "Email", "InstantMessaging", "Chat"}),
    ("cat_multimedia", {"AudioVideo", "Audio", "Video", "Music", "Player"}),
    ("cat_office", {"Office", "WordProcessor", "Spreadsheet", "Presentation"}),
    ("cat_development", {"Development", "IDE"}),
    ("cat_education", {"Education", "Science"}),
    ("cat_system", {"System", "Monitor", "PackageManager", "FileManager", "TerminalEmulator"}),
    ("cat_settings", {"Settings", "DesktopSettings", "HardwareSettings"}),
]


def folder_for(entry):
    cats = set(entry.categories)
    for key, s in CATEGORY_FOLDERS:
        if cats & s:
            return key
    return "cat_other"


def _mimeapps_files():
    """Pliki mimeapps.list w kolejności pierwszeństwa (specyfikacja XDG)."""
    home = os.path.expanduser("~")
    cfg_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    cfg_dirs = (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":")
    desktops = [d.lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d]
    out = []
    for d in [cfg_home] + cfg_dirs:
        for de in desktops:
            out.append(os.path.join(d, f"{de}-mimeapps.list"))
        out.append(os.path.join(d, "mimeapps.list"))
    for d in data_dirs():
        for de in desktops:
            out.append(os.path.join(d, "applications", f"{de}-mimeapps.list"))
        out.append(os.path.join(d, "applications", "mimeapps.list"))
        out.append(os.path.join(d, "applications", "defaults.list"))
    return out


def default_for_mime(mime):
    """Id pliku .desktop domyślnego programu dla typu MIME — bez uruchamiania xdg-mime."""
    entries = all_entries()
    for path in _mimeapps_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                section = ""
                for line in f:
                    line = line.strip()
                    if line.startswith("["):
                        section = line
                        continue
                    if section == "[Default Applications]" and line.startswith(mime + "="):
                        for did in line.split("=", 1)[1].split(";"):
                            did = did.strip()
                            if did and did in entries:
                                return did
        except OSError:
            continue
    # pierwszy program deklarujący obsługę typu
    for e in entries.values():
        if mime in getattr(e, "mimetypes", ()) and e.visible():
            return e.id
    return ""


def set_default_for_mime(mime, desktop_id):
    """Zapisuje domyślny program w ~/.config/mimeapps.list."""
    import configparser
    path = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "mimeapps.list")
    cp = configparser.RawConfigParser(delimiters=("=",))
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
    except Exception:
        pass
    if not cp.has_section("Default Applications"):
        cp.add_section("Default Applications")
    cp.set("Default Applications", mime, desktop_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)
