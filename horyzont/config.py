"""Ustawienia środowiska trzymane w ~/.config/horyzont/settings.json.

Wszystkie procesy (powłoka, Eksplorator, aplety) czytają ten sam plik.
Zmiany są rozgłaszane przez obserwację pliku (patrz ``watch``).
"""
import json
import os
import tempfile

VERSION = "0.4.1"

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "horyzont")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "horyzont")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "horyzont")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "language": "",
    # wygląd
    "visual_style": "builtin",          # "builtin", "classic" albo ścieżka do .msstyles
    "msstyles_scheme": "",              # nazwa schematu kolorów w pliku .msstyles
    "color_scheme": "teal",             # schemat wbudowanego stylu: teal / graphite / plum
    "font_size": "normal",              # normal / large / xlarge
    "wallpaper": "builtin:horyzont",    # builtin:<nazwa>, ścieżka do pliku albo "" (brak)
    "wallpaper_mode": "fill",           # center / tile / stretch / fill / fit
    "desktop_color": "#3a6e8f",
    "screensaver": "starfield",
    "screensaver_timeout": 10,
    "screensaver_lock": False,
    # pulpit
    "desktop_icons": ["computer", "documents", "network", "recycle"],
    "desktop_show_icons": True,
    "desktop_auto_arrange": False,
    "desktop_align_grid": True,
    "icon_positions": {},
    # pasek zadań
    "taskbar_locked": True,
    "taskbar_autohide": False,
    "taskbar_on_top": True,
    "taskbar_group": True,
    "taskbar_quick_launch": False,
    "quick_launch": ["show-desktop", "browser", "explorer"],
    "clock_visible": True,
    "clock_seconds": False,
    "start_style": "modern",            # modern / classic
    "start_text": "",                   # napis na przycisku Start (pusty = „Start”)
    "balloon_tips": True,               # dymki powiadomień (programy i system)
    "tray_app_icons": True,             # ikony programów w zasobniku (StatusNotifierItem)
    "start_logo": "system",             # system (logo dystrybucji) / horyzont / none / ścieżka do obrazu
    "icon_pack": "",                    # nazwa zestawu ikon .msicon (pusty = wbudowany)
    "start_pinned": ["browser", "email"],
    "start_recent_count": 6,
    "recent_programs": {},
    "volume_icon": True,
    # Eksplorator
    "explorer_view": "tiles",
    "explorer_show_tasks": True,
    "explorer_same_window": True,
    "explorer_single_click": False,
    "explorer_show_hidden": False,
    "explorer_hide_ext": True,
    "explorer_full_path_address": True,
    "explorer_full_path_title": False,
    "explorer_status_bar": True,
    "explorer_folders_pane": False,
    "folder_views": {},
    # Panel sterowania
    "control_view": "category",
    # Notatnik
    "notepad_font": "Lucida Console,10",
    "notepad_wrap": False,
    "notepad_statusbar": False,
    # Menedżer zadań
    "taskmgr_on_top": True,
    "taskmgr_speed": "normal",
    "taskmgr_tab": 0,
    # konto
    "user_picture": "builtin:kite",
    # dźwięk
    "startup_sound": False,
}

_cache = None
_mtime = 0


def _ensure_dirs():
    for d in (CONFIG_DIR, CACHE_DIR, DATA_DIR):
        os.makedirs(d, exist_ok=True)


def load(force=False):
    global _cache, _mtime
    try:
        mt = os.path.getmtime(SETTINGS_FILE)
    except OSError:
        mt = 0
    if _cache is not None and not force and mt == _mtime:
        return _cache
    data = dict(DEFAULTS)
    if mt:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    _cache = data
    _mtime = mt
    return _cache


def get(key, default=None):
    d = load()
    if key in d:
        return d[key]
    return DEFAULTS.get(key, default)


def set(key, value, save_now=True):  # noqa: A001 - nazwa celowa
    d = load()
    d[key] = value
    if save_now:
        save()


def update(values):
    d = load()
    d.update(values)
    save()


def save():
    global _mtime
    _ensure_dirs()
    d = load()
    # zapisujemy tylko wartości różne od domyślnych, żeby plik był czytelny
    out = {k: v for k, v in d.items() if DEFAULTS.get(k, object()) != v}
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)
    try:
        _mtime = os.path.getmtime(SETTINGS_FILE)
    except OSError:
        pass


def watch(callback):
    """Wywołuje ``callback()`` gdy plik ustawień zmieni się (także w innym procesie).

    Zwraca obiekt obserwatora, który trzeba trzymać przy życiu.
    """
    from PySide6.QtCore import QFileSystemWatcher, QTimer
    _ensure_dirs()
    w = QFileSystemWatcher()
    w.addPath(CONFIG_DIR)
    if os.path.exists(SETTINGS_FILE):
        w.addPath(SETTINGS_FILE)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(150)
    state = {"mtime": _mtime}

    def fire():
        try:
            mt = os.path.getmtime(SETTINGS_FILE)
        except OSError:
            mt = 0
        if mt != state["mtime"]:
            state["mtime"] = mt
            load(force=True)
            callback()
        if os.path.exists(SETTINGS_FILE) and SETTINGS_FILE not in w.files():
            w.addPath(SETTINGS_FILE)

    timer.timeout.connect(fire)
    w.fileChanged.connect(lambda *_: timer.start())
    w.directoryChanged.connect(lambda *_: timer.start())
    w._timer = timer  # utrzymanie referencji
    return w


def user_dirs():
    """Zwraca ścieżki folderów użytkownika (XDG) — Dokumenty, Obrazy, Muzyka..."""
    home = os.path.expanduser("~")
    dirs = {"DOCUMENTS": "Documents", "PICTURES": "Pictures", "MUSIC": "Music",
            "DESKTOP": "Desktop", "DOWNLOAD": "Downloads", "VIDEOS": "Videos"}
    result = {k: os.path.join(home, v) for k, v in dirs.items()}
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config")), "user-dirs.dirs")
    try:
        with open(cfg, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("XDG_") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k[4:].replace("_DIR", "")
                    v = v.strip().strip('"').replace("$HOME", home)
                    result[k] = v
    except OSError:
        pass
    return result


def user_dir(kind):
    return user_dirs().get(kind, os.path.expanduser("~"))
