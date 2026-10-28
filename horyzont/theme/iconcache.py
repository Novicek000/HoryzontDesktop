"""Renderowanie ikon SVG do QPixmap/QIcon z pamięcią podręczną."""
import mimetypes
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import icons

_pix_cache = {}
_icon_cache = {}
_renderers = {}

SIZES = (16, 24, 32, 48)

# --- zestawy ikon (.msicon) ------------------------------------------------
_pack = {"key": None, "files": {}}
PACK_EXTS = (".svg", ".png", ".ico", ".xpm", ".bmp")


def packs_dir():
    from .. import config
    return os.path.join(config.DATA_DIR, "iconpacks")


def _pack_index():
    """Słownik nazwa -> {rozmiar (0 = wektor/dowolny): ścieżka} dla bieżącego zestawu ikon."""
    from .. import config
    key = config.get("icon_pack", "")
    if key == _pack["key"]:
        return _pack["files"]
    files = {}
    if key:
        root = os.path.join(packs_dir(), key)
        for base in (os.path.join(root, "icons"), root):
            if not os.path.isdir(base):
                continue
            for fn in os.listdir(base):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in PACK_EXTS:
                    continue
                size = 0
                if "@" in stem:
                    stem, _, sz = stem.rpartition("@")
                    size = int(sz) if sz.isdigit() else 0
                if ext.lower() != ".svg" and size == 0:
                    size = -1   # bitmapa bez podanego rozmiaru
                files.setdefault(stem, {})[size] = os.path.join(base, fn)
    _pack["key"], _pack["files"] = key, files
    return files


def reset():
    """Czyści pamięć podręczną (zmiana zestawu ikon lub logo)."""
    _pix_cache.clear()
    _icon_cache.clear()
    _pack["key"] = None
    _logo_cache.clear()


def _pack_pixmap(name, size):
    idx = _pack_index()
    if not idx:
        return None
    entry = idx.get(name) or idx.get(icons.ALIASES.get(name, name))
    if not entry:
        return None
    path = entry.get(size) or entry.get(0)
    if path is None:
        # najbliższy większy rozmiar, inaczej największy
        sizes = sorted(s for s in entry if s > 0)
        bigger = [s for s in sizes if s >= size]
        path = entry[bigger[0]] if bigger else entry[sizes[-1]] if sizes else entry.get(-1)
    if path is None:
        return None
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if path.lower().endswith(".svg"):
        QSvgRenderer(path).render(p, QRectF(0, 0, size, size))
    else:
        src = QImage(path)
        if src.isNull():
            ic = QIcon(path)
            src = ic.pixmap(size, size).toImage()
        if src.isNull():
            p.end()
            return None
        src = src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawImage((size - src.width()) // 2, (size - src.height()) // 2, src)
    p.end()
    return img


def _renderer(name):
    r = _renderers.get(name)
    if r is None:
        r = QSvgRenderer(QByteArray(icons.svg_for(name).encode("utf-8")))
        _renderers[name] = r
    return r


def pixmap(name, size=32, overlay_shortcut=False):
    key = (name, size, overlay_shortcut)
    pm = _pix_cache.get(key)
    if pm is not None:
        return pm
    img = _pack_pixmap(name, size)
    from_pack = img is not None
    if not from_pack:
        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if not from_pack:
        _renderer(name).render(p, QRectF(0, 0, size, size))
    if overlay_shortcut:
        p.drawPixmap(0, 0, pixmap("shortcut_overlay", size))
    p.end()
    pm = QPixmap.fromImage(img)
    _pix_cache[key] = pm
    return pm


def icon(name, overlay_shortcut=False):
    key = (name, overlay_shortcut)
    ic = _icon_cache.get(key)
    if ic is None:
        ic = QIcon()
        for s in SIZES:
            ic.addPixmap(pixmap(name, s, overlay_shortcut))
        _icon_cache[key] = ic
    return ic


# --- logo przycisku Start ----------------------------------------------------
_logo_cache = {}


logo_override = None   # podgląd w oknie właściwości (bez zapisywania ustawień)


def os_name():
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as f:
                vals = dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)
            return (vals.get("NAME") or "Linux").strip('"\'')
        except OSError:
            pass
    return "Linux"


def start_logo(size, mode=None):
    """Logo na przycisku Start wg ustawienia start_logo: horyzont / none / ścieżka do obrazu użytkownika.

    Dawna wartość „system” (logo dystrybucji) oznacza teraz logo Horyzontu."""
    from .. import config
    if mode is None:
        mode = logo_override if logo_override is not None else config.get("start_logo", "horyzont")
    if mode == "system":
        mode = "horyzont"
    key = (mode, size)
    if key in _logo_cache:
        return _logo_cache[key]
    pm = None
    if mode == "none":
        pm = QPixmap()
    elif mode and mode not in ("horyzont",) and os.path.exists(mode):
        img = QImage(mode)
        if mode.lower().endswith(".svg"):
            img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            p = QPainter(img)
            QSvgRenderer(mode).render(p, QRectF(0, 0, size, size))
            p.end()
        if not img.isNull():
            pm = QPixmap.fromImage(img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    if pm is None or (pm.isNull() and mode != "none"):
        pm = pixmap("logo", size)
    _logo_cache[key] = pm
    return pm


_named_cache = {}


def find_named_icon(name, extra_paths=()):
    """Ikona freedesktop po nazwie (programy w zasobniku, powiadomienia). Zwraca QIcon albo None.

    Szuka w podanych katalogach (np. IconThemePath programu), w motywie ikon Qt, w hicolor i w /usr/share/pixmaps.
    """
    if not name:
        return None
    if name.startswith("file://"):
        from urllib.parse import unquote
        name = unquote(name[7:])
    if os.path.isabs(name):
        if os.path.exists(name):
            ic = QIcon(name)
            return None if ic.isNull() else ic
        return None
    key = (name, tuple(extra_paths))
    if key in _named_cache:
        return _named_cache[key]
    found = None
    exts = (".png", ".svg", ".xpm")
    sizes = ("22x22", "24x24", "16x16", "32x32", "48x48", "64x64", "scalable", "128x128", "256x256")
    roots = [p for p in extra_paths if p and os.path.isdir(p)]
    home_icons = os.path.expanduser("~/.local/share/icons")
    data_dirs = [os.path.expanduser("~/.local/share")] + \
        (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    # 1) katalogi programu (bez struktury lub ze strukturą motywu)
    for r in roots:
        for ext in exts:
            fp = os.path.join(r, name + ext)
            if os.path.exists(fp):
                found = fp
                break
        if found:
            break
        for dirpath, _dirs, files in os.walk(r):
            for ext in exts:
                if name + ext in files:
                    found = os.path.join(dirpath, name + ext)
                    break
            if found:
                break
        if found:
            break
    ic = QIcon(found) if found else None
    # 2) bieżący motyw ikon Qt
    if ic is None:
        t = QIcon.fromTheme(name)
        if not t.isNull():
            ic = t
    # 3) hicolor, pixmaps
    if ic is None:
        bases = [home_icons] + [os.path.join(d, "icons") for d in data_dirs if d]
        for b in bases:
            for theme in ("hicolor", "Adwaita", "breeze"):
                for sz in sizes:
                    for cat in ("apps", "status", "devices", "actions", "categories", "places", "panel"):
                        for ext in exts:
                            fp = os.path.join(b, theme, sz, cat, name + ext)
                            if os.path.exists(fp):
                                found = fp
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if not found:
            for d in data_dirs:
                for ext in exts:
                    fp = os.path.join(d, "pixmaps", name + ext)
                    if os.path.exists(fp):
                        found = fp
                        break
                if found:
                    break
        if found:
            ic = QIcon(found)
    if ic is not None and ic.isNull():
        ic = None
    if len(_named_cache) > 300:
        _named_cache.clear()
    _named_cache[key] = ic
    return ic


def theme_or_builtin(theme_name, fallback):
    """Ikona z motywu systemowego (np. dla aplikacji .desktop) albo wbudowana."""
    if theme_name:
        if os.path.isabs(theme_name) and os.path.exists(theme_name):
            ic = QIcon(theme_name)
            if not ic.isNull():
                return ic
        elif icons.has(theme_name):
            return icon(theme_name)
        else:
            ic = QIcon.fromTheme(theme_name)
            if not ic.isNull():
                return ic
    return icon(fallback)


# --- ikony typów plików ---------------------------------------------------
_EXT_MAP = {
    "txt": "file_text", "log": "file_text", "ini": "file_text", "cfg": "file_text", "conf": "file_text",
    "md": "file_text", "csv": "file_sheet", "nfo": "file_text",
    "png": "file_image", "jpg": "file_image", "jpeg": "file_image", "gif": "file_image", "bmp": "file_image",
    "webp": "file_image", "svg": "file_image", "tif": "file_image", "tiff": "file_image", "ico": "file_image",
    "mp3": "file_audio", "wav": "file_audio", "ogg": "file_audio", "flac": "file_audio", "m4a": "file_audio",
    "opus": "file_audio", "wma": "file_audio", "mid": "file_audio",
    "mp4": "file_video", "mkv": "file_video", "avi": "file_video", "webm": "file_video", "mov": "file_video",
    "wmv": "file_video", "mpg": "file_video",
    "zip": "folder_zip", "tar": "file_archive", "gz": "file_archive", "xz": "file_archive", "bz2": "file_archive",
    "7z": "folder_zip", "rar": "folder_zip", "zst": "file_archive", "rpm": "file_archive", "iso": "drive_cd", "img": "drive_cd",
    "pdf": "file_pdf", "html": "file_html", "htm": "file_html", "xml": "file_code",
    "doc": "file_doc", "docx": "file_doc", "odt": "file_doc", "rtf": "wordpad",
    "xls": "file_sheet", "xlsx": "file_sheet", "ods": "file_sheet",
    "py": "file_code", "js": "file_code", "c": "file_code", "h": "file_code", "cpp": "file_code", "sh": "file_code",
    "json": "file_code", "rs": "file_code", "go": "file_code", "java": "file_code", "css": "file_code",
    "exe": "file_exe", "appimage": "file_exe", "bin": "file_exe", "run": "file_exe",
    "ttf": "file_font", "otf": "file_font", "woff": "file_font",
    "desktop": "file_exe", "msstyles": "display", "theme": "display", "msicon": "icon_pack",
}


def name_for_file(path, is_dir=None):
    if is_dir is None:
        is_dir = os.path.isdir(path)
    if is_dir:
        return "folder"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]
    if os.access(path, os.X_OK):
        return "file_exe"
    mt, _ = mimetypes.guess_type(path)
    if mt:
        if mt.startswith("text/"):
            return "file_text"
        if mt.startswith("image/"):
            return "file_image"
        if mt.startswith("audio/"):
            return "file_audio"
        if mt.startswith("video/"):
            return "file_video"
    return "file"
