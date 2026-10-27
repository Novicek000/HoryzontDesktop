"""Panele boczne Eksploratora: drzewo folderów i wyszukiwanie."""
import fnmatch
import os

from PySide6.QtCore import QModelIndex, QSize, Qt, QThread, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QTreeView,
                               QVBoxLayout, QWidget)

from ... import config
from ...common.taskpane import TaskPane
from ...i18n import plain, tr
from ...theme import iconcache
from .model import list_drives, special_folder_icon

PathRole = Qt.UserRole + 10
LoadedRole = Qt.UserRole + 11


class FolderTree(QWidget):
    """Drzewo: Pulpit > Moje dokumenty, Mój komputer > dyski, Moje miejsca sieciowe, Kosz."""

    navigate = Signal(str)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(6, 2, 2, 2)
        lbl = QLabel(plain("folders"))
        hl.addWidget(lbl)
        hl.addStretch(1)
        x = QPushButton("✕")
        x.setFixedSize(20, 18)
        x.setFlat(True)
        x.clicked.connect(self.closed.emit)
        hl.addWidget(x)
        lay.addWidget(head)
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.NoFrame)
        self.tree.setIconSize(QSize(16, 16))
        self.model = QStandardItemModel(self)
        self.tree.setModel(self.model)
        lay.addWidget(self.tree)
        self.tree.expanded.connect(self._expand)
        self.tree.clicked.connect(self._clicked)
        self.build()

    def _item(self, label, icon, path, lazy=True):
        it = QStandardItem(iconcache.icon(icon), label)
        it.setData(path, PathRole)
        it.setEditable(False)
        if lazy:
            it.appendRow(QStandardItem(""))
            it.setData(False, LoadedRole)
        else:
            it.setData(True, LoadedRole)
        return it

    def build(self):
        self.model.clear()
        desk = config.user_dir("DESKTOP")
        root = self._item(plain("desktop"), "show_desktop", desk, lazy=False)
        self.model.appendRow(root)
        root.appendRow(self._item(plain("my_documents"), "documents", config.user_dir("DOCUMENTS")))
        comp = self._item(plain("my_computer"), "computer", "horyzont:computer", lazy=False)
        root.appendRow(comp)
        comp.appendRow(self._item(plain("home_folder"), "home", os.path.expanduser("~")))
        fixed, rem = list_drives()
        for d in fixed + rem:
            if d.path.startswith("/dev/"):
                continue
            comp.appendRow(self._item(d.label, d.icon, d.path))
        root.appendRow(self._item(plain("my_network"), "network", "horyzont:network", lazy=False))
        root.appendRow(self._item(plain("recycle_bin"), "recycle_empty", "horyzont:recycle", lazy=False))
        try:
            for n in sorted(os.listdir(desk), key=str.lower):
                p = os.path.join(desk, n)
                if os.path.isdir(p) and not n.startswith("."):
                    root.appendRow(self._item(n, "folder", p))
        except OSError:
            pass
        self.tree.expand(root.index())
        self.tree.expand(comp.index())

    def _expand(self, index):
        it = self.model.itemFromIndex(index)
        if it is None or it.data(LoadedRole):
            return
        it.setData(True, LoadedRole)
        it.removeRows(0, it.rowCount())
        path = it.data(PathRole)
        show_hidden = config.get("explorer_show_hidden", False)
        try:
            names = sorted(os.listdir(path), key=str.lower)
        except OSError:
            names = []
        for n in names:
            if n.startswith(".") and not show_hidden:
                continue
            p = os.path.join(path, n)
            if os.path.isdir(p):
                has_sub = False
                try:
                    with os.scandir(p) as sc:
                        for e in sc:
                            if e.is_dir(follow_symlinks=False) and (show_hidden or not e.name.startswith(".")):
                                has_sub = True
                                break
                except OSError:
                    pass
                it.appendRow(self._item(n, special_folder_icon(p) or "folder", p, lazy=has_sub))

    def _clicked(self, index):
        p = index.data(PathRole)
        if p:
            self.navigate.emit(p)

    def select_path(self, path):
        """Rozwija drzewo do wskazanego folderu."""
        def find(parent_item, target):
            for r in range(parent_item.rowCount()):
                ch = parent_item.child(r)
                p = ch.data(PathRole) or ""
                if p == target:
                    return ch
                if p and not p.startswith("horyzont:") and p != config.user_dir("DESKTOP") \
                        and target.startswith(p.rstrip("/") + "/"):
                    self.tree.expand(ch.index())
                    self._expand(ch.index())
                    res = find(ch, target)
                    if res:
                        return res
                elif p.startswith("horyzont:computer") or p == config.user_dir("DESKTOP"):
                    res = find(ch, target)
                    if res:
                        return res
            return None
        root = self.model.invisibleRootItem()
        res = find(root, path)
        if res is not None:
            self.tree.setCurrentIndex(res.index())
            self.tree.scrollTo(res.index())


class _SearchWorker(QThread):
    found = Signal(list)
    status = Signal(str)

    def __init__(self, root, pattern, text, hidden):
        super().__init__()
        self.root, self.pattern, self.text, self.hidden = root, pattern, text, hidden
        self.stop = False

    def run(self):
        batch = []
        pat = self.pattern.lower()
        if pat and not any(c in pat for c in "*?["):
            pat = f"*{pat}*"
        needle = self.text.encode("utf-8", "ignore").lower() if self.text else None
        n = 0
        for root, dirs, files in os.walk(self.root):
            if self.stop:
                break
            if not self.hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            self.status.emit(root)
            for name in dirs + files:
                if pat and not fnmatch.fnmatch(name.lower(), pat):
                    continue
                p = os.path.join(root, name)
                if needle is not None:
                    if os.path.isdir(p):
                        continue
                    try:
                        if os.path.getsize(p) > 20_000_000:
                            continue
                        with open(p, "rb") as f:
                            if needle not in f.read().lower():
                                continue
                    except OSError:
                        continue
                batch.append(p)
                n += 1
                if len(batch) >= 50:
                    self.found.emit(batch)
                    batch = []
        if batch:
            self.found.emit(batch)
        self.status.emit("")


class SearchPane(TaskPane):
    """Panel wyszukiwania plików i folderów."""

    results = Signal(list)
    started = Signal()
    finished = Signal(int)
    closed = Signal()

    def __init__(self, start_dir, parent=None):
        super().__init__(parent)
        self.count = 0
        self.setMinimumWidth(250)
        sec = self.add_section(plain("search_header"), special=True)
        form = QWidget()
        fl = QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)
        intro = QLabel(plain("search_title"))
        intro.setWordWrap(True)
        fl.addWidget(intro)
        fl.addWidget(QLabel(plain("search_name")))
        self.name = QLineEdit()
        fl.addWidget(self.name)
        fl.addWidget(QLabel(plain("search_text")))
        self.text = QLineEdit()
        fl.addWidget(self.text)
        fl.addWidget(QLabel(plain("search_in")))
        self.where = QComboBox()
        self.where.setEditable(True)
        self.where.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.where.setMinimumContentsLength(8)
        for p in (start_dir, os.path.expanduser("~"), config.user_dir("DOCUMENTS"), "/"):
            if p and self.where.findText(p) < 0:
                self.where.addItem(iconcache.icon("folder"), p)
        fl.addWidget(self.where)
        self.hidden = QCheckBox(plain("search_hidden"))
        fl.addWidget(self.hidden)
        row = QHBoxLayout()
        self.go = QPushButton(plain("search_go"))
        self.go.setDefault(True)
        self.stop_btn = QPushButton(plain("search_stop"))
        self.stop_btn.setEnabled(False)
        row.addWidget(self.go)
        row.addWidget(self.stop_btn)
        fl.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        fl.addWidget(self.status)
        sec.add_widget(form)
        back = self.add_section(plain("task_other_places"))
        back.add_link("back", plain("search_close"), self.closed.emit)
        self.go.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.name.returnPressed.connect(self.start)
        self.text.returnPressed.connect(self.start)
        self.worker = None

    def start(self):
        root = os.path.expanduser(self.where.currentText().strip() or "~")
        if not os.path.isdir(root):
            return
        self.stop()
        self.count = 0
        self.started.emit()
        self.worker = _SearchWorker(root, self.name.text().strip(), self.text.text().strip(), self.hidden.isChecked())
        self.worker.found.connect(self._found)
        self.worker.status.connect(self._status)
        self.worker.finished.connect(self._done)
        self.go.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.worker.start()

    def _found(self, paths):
        self.count += len(paths)
        self.results.emit(paths)

    def _status(self, s):
        if s:
            fm = self.status.fontMetrics()
            self.status.setText(fm.elidedText(tr("search_looking", s), Qt.ElideMiddle, self.status.width() * 2))

    def _done(self):
        self.go.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status.setText(tr("search_done", self.count))
        self.finished.emit(self.count)

    def stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop = True
            self.worker.wait(2000)
