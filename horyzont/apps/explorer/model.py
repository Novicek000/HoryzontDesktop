"""Modele danych Eksploratora: folder, Mój komputer, Kosz, wyniki wyszukiwania."""
import datetime
import math
import mimetypes
import os
import stat

from PySide6.QtCore import (QAbstractTableModel, QFileSystemWatcher, QMimeData,
                            QModelIndex, QObject, QRunnable, QSize, Qt,
                            QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import QImage, QImageReader, QPixmap

from ... import config
from ...common import desktopentry, fileops, isomount, sysctl
from ...common.appkit import T
from ...i18n import lang_code, plain, tr
from ...theme import iconcache

ItemRole = Qt.UserRole + 1
IconNameRole = Qt.UserRole + 2
HeaderRole = Qt.UserRole + 3
SortRole = Qt.UserRole + 4
InfoRole = Qt.UserRole + 5

COLUMN_TITLES = {
    "name": "name", "size": "size", "type": "type", "modified": "modified",
    "orig": "orig_location", "deleted": "date_deleted", "folder": "in_folder",
    "total": "capacity", "free": "free_space_c", "fs": "file_system",
    "packed": "arc_col_packed", "password": "arc_col_password", "ratio": "arc_col_ratio",
}

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico", ".svg"}


_FLAGS = {}


class Item:
    __slots__ = ("path", "name", "label", "is_dir", "size", "mtime", "type_name", "icon", "qicon", "kind",
                 "header", "extra", "hidden")

    def __init__(self, path="", name="", is_dir=False):
        self.path = path
        self.name = name
        self.label = name
        self.is_dir = is_dir
        self.size = 0
        self.mtime = 0
        self.type_name = ""
        self.icon = "file"
        self.qicon = None
        self.kind = "file"  # file, dir, drive, special, header, trash, link
        self.header = False
        self.extra = {}
        self.hidden = False


def type_name_for(path, is_dir):
    if is_dir:
        return plain("file_folder")
    ext = os.path.splitext(path)[1].lower()
    e = ext.lstrip(".").upper()
    if ext in (".txt", ".log", ".nfo"):
        return plain("ftype_text")
    if ext == ".desktop":
        return plain("ftype_shortcut")
    if ext == ".pdf":
        return plain("ftype_pdf")
    if ext in (".html", ".htm"):
        return plain("ftype_html")
    if ext in (".doc", ".docx", ".odt", ".rtf"):
        return plain("ftype_doc")
    if ext in (".xls", ".xlsx", ".ods", ".csv"):
        return plain("ftype_sheet")
    if ext in IMAGE_EXT:
        return tr("ftype_image", e)
    if ext in (".exe", ".com", ".scr"):
        return plain("ftype_exe")
    if ext == ".msi":
        return T("Pakiet Instalatora Windows", "Windows Installer Package")
    if ext == ".bat":
        return T("Plik wsadowy MS-DOS", "MS-DOS Batch File")
    if ext in (".iso", ".img"):
        return T("Plik obrazu dysku", "Disc Image File")
    mt, _ = mimetypes.guess_type(path)
    if mt:
        if mt.startswith("audio/"):
            return tr("ftype_audio", e)
        if mt.startswith("video/"):
            return tr("ftype_video", e)
    if ext in (".zip", ".tar", ".gz", ".xz", ".bz2", ".7z", ".rar", ".zst", ".rpm"):
        return tr("ftype_archive", e)
    if not ext:
        try:
            if os.access(path, os.X_OK) and not os.path.isdir(path):
                return plain("ftype_exe")
        except OSError:
            pass
        return plain("ftype_file")
    return tr("ftype_generic", e)


def format_size_kb(n):
    """Rozmiar w widoku szczegółów: zawsze w KB, zaokrąglony w górę (jak w klasycznym Eksploratorze)."""
    kb = int(math.ceil(n / 1024.0)) if n else 0
    return f"{sysctl.group_digits(kb)} KB"


def format_date(ts):
    if not ts:
        return ""
    d = datetime.datetime.fromtimestamp(ts)
    return d.strftime("%Y-%m-%d %H:%M")


def program_icon(it):
    """Własna ikona programu Windows (.exe) — ustawia it.qicon, gdy jest już wyciągnięta; inaczej zleca to w tle."""
    if it.qicon is not None:
        return True
    if it.is_dir or it.kind not in ("file", "link") or not it.path:
        return False
    if os.path.splitext(it.path)[1].lower() not in (".exe", ".scr", ".cpl", ".ocx", ".dll"):
        return False
    from ...common.exeicon import ExeIconLoader
    ic = ExeIconLoader.instance().get(it.path)
    if ic is not None:
        it.qicon = ic
        return True
    return False


def item_for_path(path, st=None):
    name = os.path.basename(path.rstrip("/")) or path
    try:
        st = st or os.stat(path)
        is_dir = stat.S_ISDIR(st.st_mode)
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        try:
            st = os.lstat(path)
            is_dir, size, mtime = False, st.st_size, st.st_mtime
        except OSError:
            is_dir, size, mtime = False, 0, 0
    it = Item(path, name, is_dir)
    it.size = 0 if is_dir else size
    it.mtime = mtime
    it.kind = "dir" if is_dir else "file"
    it.hidden = name.startswith(".")
    it.type_name = type_name_for(path, is_dir)
    if name.endswith(".desktop") and not is_dir:
        e = desktopentry.parse(path)
        if e:
            if e.name:
                it.label = e.name
            if e.icon:
                it.qicon = iconcache.theme_or_builtin(e.icon, "app")
        it.icon = "app"
        it.kind = "link"
    else:
        it.icon = iconcache.name_for_file(path, is_dir)
        if is_dir:
            special = special_folder_icon(path)
            if special:
                it.icon = special
        elif config.get("explorer_hide_ext", True):
            base, ext = os.path.splitext(name)
            if base and ext and ext.lower() in KNOWN_EXT:
                it.label = base
    return it


KNOWN_EXT = {".txt", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".mp3", ".wav", ".ogg", ".flac",
             ".mp4", ".mkv", ".avi", ".webm", ".zip", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods",
             ".html", ".htm", ".log", ".ini", ".rtf", ".webp", ".svg", ".desktop"}


def special_folder_icon(path):
    d = config.user_dirs()
    m = {d.get("DOCUMENTS"): "documents", d.get("PICTURES"): "pictures", d.get("MUSIC"): "music",
         d.get("VIDEOS"): "videos", d.get("DOWNLOAD"): "downloads", d.get("DESKTOP"): "desktop_folder"}
    return m.get(path.rstrip("/"))


def special_folder_label(path):
    d = config.user_dirs()
    if path.rstrip("/") == d.get("DOCUMENTS"):
        return plain("my_documents")
    if path.rstrip("/") == d.get("PICTURES"):
        return plain("sm_pictures")
    if path.rstrip("/") == d.get("MUSIC"):
        return plain("sm_music")
    return None


class BaseModel(QAbstractTableModel):
    columns = ["name", "size", "type", "modified"]
    location_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.sort_col = 0
        self.sort_order = Qt.AscendingOrder
        self.folder = None
        from ...common.exeicon import ExeIconLoader
        ExeIconLoader.instance().updated.connect(self._exe_icon_ready)

    def _exe_icon_ready(self, path):
        for row, it in enumerate(self.items):
            if it.path == path:
                it.qicon = None
                program_icon(it)
                a = self.index(row, 0)
                self.dataChanged.emit(a, self.index(row, max(0, len(self.columns) - 1)), [Qt.DecorationRole])

    def index(self, row, column, parent=QModelIndex()):
        # szybsza wersja: bez wywołań rowCount/columnCount z C++ dla każdego indeksu
        if 0 <= row < len(self.items) and 0 <= column < len(self.columns) and not parent.isValid():
            return self.createIndex(row, column)
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and section < len(self.columns):
            return plain(COLUMN_TITLES.get(self.columns[section], self.columns[section])).rstrip(":")
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal:
            if self.columns[section] in ("size", "total", "free"):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def item(self, index):
        if not index.isValid() or index.row() >= len(self.items):
            return None
        return self.items[index.row()]

    def cell_text(self, it, col):
        if col == "name":
            return it.label
        if col == "size":
            if it.is_dir or it.header or it.kind in ("drive", "special"):
                return ""
            return format_size_kb(it.size)
        if col == "type":
            return it.type_name
        if col == "modified":
            return format_date(it.mtime)
        return str(it.extra.get(col, ""))

    def data(self, index, role=Qt.DisplayRole):
        it = self.item(index)
        if it is None:
            return None
        col = self.columns[index.column()]
        if role == Qt.DisplayRole:
            return self.cell_text(it, col)
        if role == Qt.EditRole and col == "name":
            return it.name
        if role == Qt.DecorationRole and col == "name":
            if it.qicon is not None or program_icon(it):
                return it.qicon
            return iconcache.icon(it.icon)
        if role == ItemRole:
            return it
        if role == IconNameRole:
            return it.icon
        if role == HeaderRole:
            return it.header
        if role == Qt.TextAlignmentRole:
            if col in ("size", "total", "free"):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and it.hidden:
            from PySide6.QtGui import QColor
            return QColor("#808080")
        if role == Qt.ToolTipRole and col == "name" and not it.header:
            lines = [f"{plain('type')}: {it.type_name}"] if it.type_name else []
            if not it.is_dir and it.kind in ("file", "link"):
                lines.append(f"{plain('size')}: {sysctl.human_size(it.size)}")
            if it.mtime:
                lines.append(f"{plain('modified')}: {format_date(it.mtime)}")
            return "\n".join(lines) or None
        return None

    def flags(self, index):
        it = self.item(index)
        if it is None:
            return Qt.ItemIsDropEnabled
        if it.header:
            return Qt.NoItemFlags
        # gotowe kombinacje flag — operacje na wyliczeniach Qt w Pythonie są wolne (wywoływane setki razy)
        key = (it.kind in ("file", "dir", "link"), self.columns[index.column()] == "name",
               it.is_dir or it.kind == "drive")
        f = _FLAGS.get(key)
        if f is None:
            f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if key[0]:
                f |= Qt.ItemIsDragEnabled
                if key[1]:
                    f |= Qt.ItemIsEditable
            if key[2]:
                f |= Qt.ItemIsDropEnabled
            _FLAGS[key] = f
        return f

    # --- przeciąganie
    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, indexes):
        md = QMimeData()
        paths = []
        for i in indexes:
            it = self.item(i)
            if it and it.path and it.path not in paths and it.kind in ("file", "dir", "link"):
                paths.append(it.path)
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        return md

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction | Qt.LinkAction

    def supportedDragActions(self):
        return Qt.CopyAction | Qt.MoveAction | Qt.LinkAction

    def sort(self, column, order=Qt.AscendingOrder):
        self.sort_col, self.sort_order = column, order
        if column >= len(self.columns):
            return
        key = self.columns[column]
        self.layoutAboutToBeChanged.emit()
        rev = order == Qt.DescendingOrder

        def k(it):
            if key == "size":
                v = it.size
            elif key == "modified":
                v = it.mtime
            elif key == "type":
                v = it.type_name.lower()
            elif key == "name":
                v = it.label.lower()
            else:
                v = str(it.extra.get(key, "")).lower()
            return v
        dirs = [i for i in self.items if i.is_dir]
        files = [i for i in self.items if not i.is_dir]
        dirs.sort(key=k, reverse=rev)
        files.sort(key=k, reverse=rev)
        self.items = dirs + files
        self.layoutChanged.emit()

    def index_of_path(self, path):
        for r, it in enumerate(self.items):
            if it.path == path:
                return self.index(r, 0)
        return QModelIndex()


class FolderModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda *_: self._timer.start())
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        self.error = None

    def set_folder(self, path):
        if self.folder and self.folder in self.watcher.directories():
            self.watcher.removePath(self.folder)
        self.folder = path
        if os.path.isdir(path):
            self.watcher.addPath(path)
        self.refresh()

    def refresh(self):
        show_hidden = config.get("explorer_show_hidden", False)
        items = []
        self.error = None
        try:
            with os.scandir(self.folder) as it:
                for e in it:
                    if not show_hidden and e.name.startswith("."):
                        continue
                    try:
                        st = e.stat()
                    except OSError:
                        st = None
                    items.append(item_for_path(e.path, st))
        except OSError as ex:
            self.error = str(ex)
        self.beginResetModel()
        self.items = items
        self.endResetModel()
        self.sort(self.sort_col, self.sort_order)

    def setData(self, index, value, role=Qt.EditRole):
        it = self.item(index)
        if role != Qt.EditRole or it is None:
            return False
        new = str(value).strip()
        if not new or new == it.name or "/" in new:
            return False
        dest = os.path.join(os.path.dirname(it.path), new)
        if os.path.exists(dest):
            self.rename_error = tr("rename_fail", it.name, new)
            return False
        try:
            os.rename(it.path, dest)
        except OSError as e:
            self.rename_error = tr("rename_fail", it.name, str(e))
            return False
        self.refresh()
        return True


class TrashModel(BaseModel):
    columns = ["name", "orig", "deleted", "size", "type"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder = "horyzont:recycle"
        self.watcher = QFileSystemWatcher(self)
        d = os.path.join(fileops.TRASH_HOME, "files")
        os.makedirs(d, exist_ok=True)
        self.watcher.addPath(d)
        self.watcher.directoryChanged.connect(lambda *_: QTimer.singleShot(200, self.refresh))

    def refresh(self):
        items = []
        for t in fileops.trash_list():
            it = Item(t.file, t.name, t.is_dir)
            it.kind = "trash"
            it.size = t.size
            it.icon = iconcache.name_for_file(t.file, t.is_dir)
            it.type_name = type_name_for(t.file, t.is_dir)
            it.extra = {"orig": os.path.dirname(t.orig), "deleted": t.date.replace("T", " ")[:16], "trash": t}
            items.append(it)
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def flags(self, index):
        it = self.item(index)
        if it is None:
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class ComputerModel(BaseModel):
    columns = ["name", "type", "total", "free", "fs"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder = "horyzont:computer"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)

    def refresh(self):
        items = []

        def header(key):
            h = Item("", plain(key))
            h.header = True
            h.kind = "header"
            items.append(h)

        header("files_stored")
        docs = config.user_dir("DOCUMENTS")
        it = Item(docs, tr("user_documents", sysctl.user_full_name()), True)
        it.label = it.name
        it.kind = "dir"
        it.icon = "documents"
        it.type_name = plain("file_folder")
        items.append(it)
        home = os.path.expanduser("~")
        it = Item(home, plain("home_folder"), True)
        it.label = it.name
        it.kind = "dir"
        it.icon = "home"
        it.type_name = plain("file_folder")
        items.append(it)
        fixed, removable = list_drives()
        if fixed:
            header("hard_disks")
            items += fixed
        if removable:
            header("removable")
            items += removable
        old = [(i.path, i.label, i.extra.get("free")) for i in self.items]
        new = [(i.path, i.label, i.extra.get("free")) for i in items]
        if old == new:
            return
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def sort(self, column, order=Qt.AscendingOrder):
        pass


def list_drives():
    """Zwraca (dyski stałe, nośniki wymienne) jako listy Item."""
    fixed, removable = [], []
    try:
        import psutil
        parts = psutil.disk_partitions(all=False)
    except Exception:
        parts = []
    seen = set()
    skip_prefix = ("/boot", "/snap", "/var/lib", "/run/user", "/sys", "/proc", "/dev", "/efi", "/var/snap", "/tmp")
    for p in parts:
        mp = p.mountpoint
        if mp in seen or p.fstype in ("squashfs", "tmpfs", "overlay", "devtmpfs", "vfat") and not mp.startswith(("/run/media", "/media", "/mnt")):
            continue
        if mp != "/" and mp.startswith(skip_prefix):
            continue
        seen.add(mp)
        try:
            import psutil
            u = psutil.disk_usage(mp)
        except Exception:
            continue
        is_rem = mp.startswith(("/run/media", "/media", "/mnt"))
        if mp == "/":
            label = f"{plain('system_disk')} (/)"
            icon = "drive_system"
        elif mp == "/home":
            label = f"{plain('local_disk')} (/home)"
            icon = "drive_hdd"
        else:
            label = f"{os.path.basename(mp)} ({mp})"
            icon = "drive_usb" if is_rem else "drive_hdd"
        type_name = plain("local_disk") if not is_rem else plain("removable_disk")
        iso = isomount.backing_file(p.device)
        if iso or p.fstype in isomount.DISC_FS or p.device.startswith("/dev/sr"):
            # obraz płyty zamontowany przez Horyzont (albo prawdziwa płyta) — jak stacja CD w XP
            is_rem = True
            icon = "drive_cd"
            type_name = plain("cd_drive")
            if iso:
                label = f"{os.path.basename(mp)} ({os.path.basename(iso)})"
                type_name = T("Wirtualna stacja CD", "Virtual CD Drive")
        it = Item(mp, label, True)
        it.label = label
        it.kind = "drive"
        it.icon = icon
        it.type_name = type_name
        it.extra = {"total": sysctl.human_size(u.total), "free": sysctl.human_size(u.free), "fs": p.fstype.upper(),
                    "total_b": u.total, "free_b": u.free, "device": p.device, "iso": iso or ""}
        (removable if is_rem else fixed).append(it)
    # napędy optyczne bez nośnika
    for dev in ("/dev/sr0", "/dev/sr1"):
        if os.path.exists(dev) and not any(i.extra.get("device") == dev for i in removable):
            it = Item(dev, plain("cd_drive"), True)
            it.label = plain("cd_drive")
            it.kind = "drive"
            it.icon = "drive_cd"
            it.type_name = plain("cd_drive")
            it.extra = {"device": dev, "empty": True}
            removable.append(it)
    return fixed, removable


class SearchModel(BaseModel):
    columns = ["name", "folder", "size", "type", "modified"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder = "horyzont:search"

    def clear(self):
        self.beginResetModel()
        self.items = []
        self.endResetModel()

    def add_paths(self, paths):
        if not paths:
            return
        new = []
        for p in paths:
            it = item_for_path(p)
            it.extra = {"folder": os.path.dirname(p)}
            new.append(it)
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items) + len(new) - 1)
        self.items += new
        self.endInsertRows()


class NetworkModel(BaseModel):
    columns = ["name", "type"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder = "horyzont:network"

    def refresh(self):
        items = []
        gvfs = f"/run/user/{os.getuid()}/gvfs"
        if os.path.isdir(gvfs):
            for n in sorted(os.listdir(gvfs)):
                it = Item(os.path.join(gvfs, n), n, True)
                it.label = n.replace("smb-share:server=", "\\\\").replace(",share=", "\\")
                it.kind = "dir"
                it.icon = "drive_network"
                it.type_name = plain("network_drives")
                items.append(it)
        self.beginResetModel()
        self.items = items
        self.endResetModel()


# --- miniatury ----------------------------------------------------------
class _ThumbSignals(QObject):
    done = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path, size, signals):
        super().__init__()
        self.path, self.size, self.signals = path, size, signals

    def run(self):
        r = QImageReader(self.path)
        r.setAutoTransform(True)
        s = r.size()
        if s.isValid() and s.width() > 0:
            sc = min(self.size / s.width(), self.size / s.height(), 1.0)
            r.setScaledSize(QSize(max(1, int(s.width() * sc)), max(1, int(s.height() * sc))))
        img = r.read()
        self.signals.done.emit(self.path, img)


class ThumbnailCache(QObject):
    updated = Signal(str)

    def __init__(self, size=96):
        super().__init__()
        self.size = size
        self.cache = {}
        self.pending = set()
        self.signals = _ThumbSignals()
        self.signals.done.connect(self._done)
        self.pool = QThreadPool.globalInstance()

    def get(self, path):
        if path in self.cache:
            return self.cache[path]
        if path not in self.pending:
            self.pending.add(path)
            self.pool.start(_ThumbJob(path, self.size, self.signals))
        return None

    def _done(self, path, img):
        self.pending.discard(path)
        self.cache[path] = QPixmap.fromImage(img) if not img.isNull() else False
        self.updated.emit(path)
