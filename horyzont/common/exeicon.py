"""Ikony programów Windows (.exe, .dll, .ocx, .cpl, .scr) wyciągane z zasobów PE — jak w Eksploratorze Windows.

Zasób RT_GROUP_ICON opisuje zestaw rozmiarów, a każdy obraz leży w osobnym zasobie RT_ICON. Składamy z nich
zwykły plik .ico (nagłówek ICONDIR + wpisy z przesunięciami) i zapisujemy w ~/.cache/horyzont/exeicons.
Wyciąganie działa w wątku w tle, wynik jest zapamiętywany według ścieżki, rozmiaru i daty modyfikacji pliku.
"""
import hashlib
import os
import struct

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QIcon

PE_EXT = {".exe", ".dll", ".ocx", ".cpl", ".scr", ".sys"}
ICON_EXT = {".exe", ".scr", ".cpl", ".ocx", ".dll"}
RT_ICON = 3
RT_GROUP_ICON = 14
MAX_SIZE = 1024 * 1024 * 1024        # większych plików nie czytamy (np. obrazy płyt nazwane .exe)


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "horyzont", "exeicons")


def _cache_key(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    raw = f"{os.path.abspath(path)}\0{st.st_size}\0{int(st.st_mtime)}".encode("utf-8", "surrogateescape")
    return hashlib.sha1(raw).hexdigest()


def _entry_by_id(dir_entry, wanted_id):
    for e in getattr(dir_entry, "entries", []) or []:
        if e.id == wanted_id or (e.name is not None and str(e.name) == str(wanted_id)):
            return e
    return None


def _first_data(entry):
    """Zejście do pierwszego liścia (poziom języka) katalogu zasobów."""
    while entry is not None and hasattr(entry, "directory"):
        kids = entry.directory.entries
        if not kids:
            return None
        entry = kids[0]
    return getattr(entry, "data", None)


def extract_ico(path, max_groups=1):
    """Zwraca bajty pliku .ico z pierwszą (główną) ikoną programu albo None."""
    import pefile
    try:
        if os.path.getsize(path) > MAX_SIZE:
            return None
        pe = pefile.PE(path, fast_load=True)
    except Exception:
        return None
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        root = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
        if root is None:
            return None
        groups = _entry_by_id(root, RT_GROUP_ICON)
        icons = _entry_by_id(root, RT_ICON)
        if groups is None or icons is None:
            return None
        icon_dir = icons.directory
        for g in groups.directory.entries[:max_groups]:
            data = _first_data(g)
            if data is None:
                continue
            raw = pe.get_data(data.struct.OffsetToData, data.struct.Size)
            if len(raw) < 6:
                continue
            _res, typ, count = struct.unpack_from("<HHH", raw, 0)
            if typ != 1 or count == 0:
                continue
            entries, images = [], []
            for i in range(count):
                off = 6 + i * 14
                if off + 14 > len(raw):
                    break
                w, h, colors, res, planes, bits, size, nid = struct.unpack_from("<BBBBHHIH", raw, off)
                ie = _entry_by_id(icon_dir, nid)
                idata = _first_data(ie) if ie is not None else None
                if idata is None:
                    continue
                img = pe.get_data(idata.struct.OffsetToData, idata.struct.Size)
                entries.append((w, h, colors, res, planes, bits, len(img)))
                images.append(img)
            if not images:
                continue
            out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
            offset = 6 + 16 * len(images)
            for (w, h, colors, res, planes, bits, size) in entries:
                out += struct.pack("<BBBBHHII", w, h, colors, res, planes, bits, size, offset)
                offset += size
            for img in images:
                out += img
            return bytes(out)
        return None
    except Exception:
        return None
    finally:
        try:
            pe.close()
        except Exception:
            pass


def cached_path(path):
    """Ścieżka zapamiętanej ikony: (plik .ico | "" gdy brak ikony | None gdy jeszcze nie sprawdzano)."""
    key = _cache_key(path)
    if key is None:
        return ""
    ico = os.path.join(cache_dir(), key + ".ico")
    if os.path.exists(ico):
        return ico
    if os.path.exists(os.path.join(cache_dir(), key + ".none")):
        return ""
    return None


def extract_to_cache(path):
    key = _cache_key(path)
    if key is None:
        return ""
    os.makedirs(cache_dir(), exist_ok=True)
    data = extract_ico(path)
    if not data:
        try:
            open(os.path.join(cache_dir(), key + ".none"), "w").close()
        except OSError:
            pass
        return ""
    ico = os.path.join(cache_dir(), key + ".ico")
    tmp = ico + f".{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, ico)
    except OSError:
        return ""
    return ico


def icon_sync(path):
    """Ikona programu od razu (dla pulpitu i okien dialogowych — kilka plików). None, gdy brak ikony."""
    if os.path.splitext(path)[1].lower() not in ICON_EXT:
        return None
    ico = cached_path(path)
    if ico is None:
        ico = extract_to_cache(path)
    if not ico:
        return None
    ic = QIcon(ico)
    return None if ic.isNull() else ic


class _Signals(QObject):
    done = Signal(str, str)


class _Job(QRunnable):
    def __init__(self, path, signals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        try:
            ico = extract_to_cache(self.path)
        except Exception:
            ico = ""
        self.signals.done.emit(self.path, ico)


class ExeIconLoader(QObject):
    """Wspólny dla procesu: get() zwraca QIcon od razu z pamięci lub dysku, a brakujące wyciąga w tle."""
    updated = Signal(str)
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ExeIconLoader()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.cache = {}
        self.pending = set()
        self.signals = _Signals()
        self.signals.done.connect(self._done)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)

    def handles(self, path):
        return os.path.splitext(path)[1].lower() in ICON_EXT

    def get(self, path):
        if path in self.cache:
            return self.cache[path]
        ico = cached_path(path)
        if ico is not None:
            ic = QIcon(ico) if ico else None
            self.cache[path] = ic if ic is not None and not ic.isNull() else None
            return self.cache[path]
        if path not in self.pending:
            self.pending.add(path)
            self.pool.start(_Job(path, self.signals))
        return None

    def _done(self, path, ico):
        self.pending.discard(path)
        ic = QIcon(ico) if ico else None
        self.cache[path] = ic if ic is not None and not ic.isNull() else None
        if self.cache[path] is not None:
            self.updated.emit(path)
