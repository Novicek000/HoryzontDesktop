"""Foldery skompresowane w Eksploratorze: przeglądanie archiwów, hasła, Kreator wyodrębniania,
tworzenie archiwów ZIP („Wyślij do → Folder skompresowany”)."""
import hashlib
import os
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QVBoxLayout)

from ... import config
from ...common import archives, dialogs, launcher
from ...common.window import HDialog
from ...common.wizard import Wizard, WizardPage
from ...i18n import plain, tr
from ...theme import iconcache
from .model import BaseModel, Item, type_name_for

PREFIX = "horyzont:archive:"
SEP = "::"
_passwords = {}   # hasła podane w tej sesji: ścieżka archiwum -> hasło


def make_loc(archive, inner=""):
    return f"{PREFIX}{archive}{SEP}{inner.strip('/')}"


def parse_loc(loc):
    rest = loc[len(PREFIX):]
    archive, _, inner = rest.rpartition(SEP)
    if not archive:
        archive, inner = rest, ""
    return archive, inner.strip("/")


def is_loc(loc):
    return bool(loc) and loc.startswith(PREFIX)


def display_path(loc):
    a, inner = parse_loc(loc)
    return a + ("/" + inner if inner else "")


# ------------------------------------------------------------------ hasło
class PasswordDialog(HDialog):
    def __init__(self, archive, parent=None, wrong=False):
        super().__init__(plain("arc_pw_title"), "key", parent, help_button=False)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(14, 14, 14, 12)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("folder_zip", 32))
        row.addWidget(ic, 0, Qt.AlignTop)
        t = QLabel(tr("arc_pw_desc", os.path.basename(archive)))
        t.setWordWrap(True)
        row.addWidget(t, 1)
        lay.addLayout(row)
        if wrong:
            w = QLabel(plain("arc_pw_wrong"))
            w.setStyleSheet("color: #b00000;")
            lay.addWidget(w)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(plain("auth_password")))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        r2.addWidget(self.pw, 1)
        lay.addLayout(r2)
        show = QCheckBox(plain("wifi_show_chars"))
        show.toggled.connect(lambda on: self.pw.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        lay.addWidget(show)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(self.reject)
        b.addWidget(ok)
        b.addWidget(ca)
        lay.addLayout(b)
        self.setFixedWidth(400)
        self.pw.setFocus()


def ask_password(parent, archive, wrong=False):
    d = PasswordDialog(archive, parent, wrong)
    if d.exec():
        _passwords[archive] = d.pw.text()
        return d.pw.text()
    return None


def list_with_password(parent, archive):
    """Lista wpisów — w razie potrzeby pyta o hasło. Zwraca listę albo None (anulowano/błąd)."""
    pw = _passwords.get(archive)
    wrong = False
    while True:
        try:
            return archives.list_entries(archive, pw)
        except archives.NeedPassword:
            pass
        except archives.WrongPassword:
            wrong = True
        except archives.ArchiveError as e:
            dialogs.message(parent, os.path.basename(archive), tr("arc_open_failed", os.path.basename(archive)) + f"\n\n{e}", "error")
            return None
        pw = ask_password(parent, archive, wrong)
        if pw is None:
            return None


# ------------------------------------------------------------------ model
class ArchiveModel(BaseModel):
    columns = ["name", "type", "packed", "password", "size", "ratio", "modified"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.archive = None
        self.inner = ""
        self.entries = []
        self._cache_key = None

    def open(self, parent_widget, archive, inner=""):
        key = (archive, os.path.getmtime(archive) if os.path.exists(archive) else 0)
        if key != self._cache_key:
            entries = list_with_password(parent_widget, archive)
            if entries is None:
                return False
            self.entries = entries
            self._cache_key = key
        self.archive, self.inner = archive, inner
        self.folder = make_loc(archive, inner)
        return True

    def refresh(self):
        items = {}
        prefix = self.inner + "/" if self.inner else ""
        for e in self.entries:
            if not e.name.startswith(prefix) or e.name == self.inner:
                continue
            rest = e.name[len(prefix):]
            first, _, more = rest.partition("/")
            is_dir = bool(more) or e.is_dir
            member = prefix + first
            it = items.get(member)
            if it is None:
                it = Item(make_loc(self.archive, member) if is_dir else member, first, is_dir)
                it.kind = "archive_entry"
                it.icon = "folder" if is_dir else iconcache.name_for_file(first, False)
                it.type_name = type_name_for(first, is_dir)
                it.extra = {"archive": self.archive, "member": member, "packed": 0, "encrypted": False}
                items[member] = it
            if not more:
                it.size = e.size
                it.mtime = e.mtime
                it.extra["packed"] = e.packed
                it.extra["encrypted"] = e.encrypted
            elif is_dir:
                it.extra["encrypted"] = it.extra["encrypted"] or e.encrypted
        self.beginResetModel()
        self.items = list(items.values())
        self.endResetModel()
        self.sort(self.sort_col, self.sort_order)

    def cell_text(self, it, col):
        if col == "packed":
            return "" if it.is_dir else f"{max(1, it.extra.get('packed', 0) // 1024)} KB"
        if col == "password":
            return plain("yes") if it.extra.get("encrypted") else plain("no")
        if col == "ratio":
            if it.is_dir or not it.size or not it.extra.get("packed"):
                return ""
            return f"{max(0, round(100 - it.extra['packed'] * 100 / it.size))}%"
        return super().cell_text(it, col)

    def flags(self, index):
        it = self.item(index)
        if it is None:
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def mimeData(self, indexes):
        return None


# ------------------------------------------------------------------ praca w tle
class _Worker(QObject):
    progress = Signal(int, str)
    done = Signal(bool, str, str)   # ok, rodzaj błędu ("", "need", "wrong", "error"), komunikat

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancel = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.fn(lambda p, n: self.progress.emit(p, n), lambda: self.cancel)
            self.done.emit(True, "", "")
        except archives.NeedPassword as e:
            self.done.emit(False, "need", str(e))
        except archives.WrongPassword as e:
            self.done.emit(False, "wrong", str(e))
        except Exception as e:
            self.done.emit(False, "error", str(e))


class ProgressDialog(HDialog):
    """Okienko postępu (kopiowanie z archiwum, kompresowanie)."""

    def __init__(self, title, text, fn, parent=None, icon="folder_zip"):
        super().__init__(title, icon, parent, help_button=False)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(14, 14, 14, 12)
        self.lbl = QLabel(text)
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.file = QLabel()
        self.file.setStyleSheet("color: #444;")
        lay.addWidget(self.file)
        b = QHBoxLayout()
        b.addStretch(1)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(self._cancel)
        b.addWidget(ca)
        lay.addLayout(b)
        self.setFixedWidth(420)
        self.result = (False, "error", "")
        self.worker = _Worker(fn)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._done)
        QTimer.singleShot(0, self.worker.start)

    def _progress(self, p, name):
        if p < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(p)
        if name:
            self.file.setText(name[-70:])

    def _cancel(self):
        self.worker.cancel = True
        self.reject()

    def _done(self, ok, kind, msg):
        self.result = (ok, kind, msg)
        self.accept()


def run_extract(parent, archive, dest, members=None, title=None):
    """Rozpakowanie z oknem postępu i pytaniem o hasło. Zwraca True po sukcesie."""
    pw = _passwords.get(archive)
    wrong = False
    while True:
        def fn(progress, cancelled, pw=pw):
            archives.extract(archive, dest, members, pw, progress, cancelled)
        d = ProgressDialog(title or plain("arc_extracting_title"), tr("arc_extracting", os.path.basename(archive)), fn, parent)
        d.exec()
        ok, kind, msg = d.result
        if ok:
            return True
        if d.worker.cancel:
            return False
        if kind in ("need", "wrong"):
            wrong = kind == "wrong" or (kind == "need" and pw is not None)
            pw = ask_password(parent, archive, wrong)
            if pw is None:
                return False
            continue
        dialogs.message(parent, plain("arc_extracting_title"), tr("arc_extract_failed", os.path.basename(archive)) + f"\n\n{msg}", "error")
        return False


def open_member(parent, archive, member):
    """Otwiera plik z archiwum — rozpakowuje go do pamięci podręcznej i uruchamia skojarzony program."""
    h = hashlib.sha1(archive.encode("utf-8")).hexdigest()[:12]
    dest = os.path.join(config.CACHE_DIR, "archive-view", h)
    target = os.path.join(dest, member)
    if not os.path.exists(target):
        if not run_extract(parent, archive, dest, [member], plain("arc_opening")):
            return
    launcher.open_path(target)


def default_dest(archive):
    base = os.path.basename(archive)
    stem = base[: -len(archives.lower_ext(archive))] if archives.lower_ext(archive) else os.path.splitext(base)[0]
    return os.path.join(os.path.dirname(archive), stem or "archiwum")


def extract_here(parent, archive):
    """Wyodrębnij tutaj — jeśli w archiwum jest wiele elementów najwyższego poziomu, tworzy folder o nazwie archiwum."""
    entries = list_with_password(parent, archive)
    if entries is None:
        return False
    tops = {e.name.split("/")[0] for e in entries}
    dest = os.path.dirname(archive) if len(tops) == 1 else _unique(default_dest(archive))
    return run_extract(parent, archive, dest)


def _unique(path):
    if not os.path.exists(path):
        return path
    i = 2
    while os.path.exists(f"{path} ({i})"):
        i += 1
    return f"{path} ({i})"


# ------------------------------------------------------------------ kreator
class ExtractWizard(Wizard):
    def __init__(self, archive, parent=None, members=None):
        super().__init__(plain("arc_wizard_title"), "extract", parent)
        self.archive = archive
        self.members = members
        p = WizardPage(plain("arc_wizard_welcome"), exterior=True)
        t = QLabel(plain("arc_wizard_welcome_desc"))
        t.setWordWrap(True)
        p.lay.addWidget(t)
        p.lay.addSpacing(16)
        p.lay.addWidget(QLabel(plain("ncw_continue")))
        self.add_page(p)
        p = WizardPage(plain("arc_wizard_dest"), plain("arc_wizard_dest_sub"))
        p.lay.addWidget(QLabel(plain("arc_wizard_dest_label")))
        row = QHBoxLayout()
        self.dest = QLineEdit(_unique(default_dest(archive)))
        row.addWidget(self.dest, 1)
        b = QPushButton(plain("browse"))
        b.clicked.connect(self._browse)
        row.addWidget(b)
        p.lay.addLayout(row)
        pwb = QPushButton(plain("arc_password_btn"))
        pwb.clicked.connect(lambda: ask_password(self, archive))
        p.lay.addWidget(pwb, 0, Qt.AlignLeft)
        p.lay.addSpacing(10)
        self.prog_lbl = QLabel()
        p.lay.addWidget(self.prog_lbl)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        p.lay.addWidget(self.bar)
        p.validate = self._extract
        self.add_page(p)
        p = WizardPage(plain("arc_wizard_done"), exterior=True)
        self.done_lbl = QLabel()
        self.done_lbl.setWordWrap(True)
        p.lay.addWidget(self.done_lbl)
        self.show_files = QCheckBox(plain("arc_show_files"))
        self.show_files.setChecked(True)
        p.lay.addSpacing(10)
        p.lay.addWidget(self.show_files)
        p.lay.addSpacing(10)
        p.lay.addWidget(QLabel(plain("ncw_done_close")))
        p.final = True
        self.add_page(p)
        self.finished_ok.connect(self._finish)
        self.resize(540, 400)

    def _browse(self):
        d = dialogs.choose_dir(self, plain("arc_wizard_dest"), os.path.dirname(self.dest.text()))
        if d:
            self.dest.setText(os.path.join(d, os.path.basename(default_dest(self.archive))))

    def _extract(self, wz):
        dest = self.dest.text().strip()
        if not dest:
            return False
        self.next_btn.setEnabled(False)
        ok = run_extract(self, self.archive, dest, self.members)
        self.next_btn.setEnabled(True)
        if ok:
            self.done_lbl.setText(tr("arc_wizard_done_desc", dest))
        return ok

    def _finish(self):
        if self.show_files.isChecked():
            launcher.start_builtin("explorer", [self.dest.text().strip()])


# ------------------------------------------------------------------ kompresowanie
def compress(parent, paths, ask=False):
    """Wyślij do → Folder skompresowany (zip). ask=True — okno z nazwą i hasłem."""
    if not paths:
        return None
    first = paths[0]
    folder = os.path.dirname(first.rstrip("/"))
    stem = os.path.splitext(os.path.basename(first.rstrip("/")))[0] if len(paths) == 1 else os.path.basename(folder) or "archiwum"
    target = _unique(os.path.join(folder, stem + ".zip"))
    password = None
    if ask:
        d = HDialog(plain("arc_add_title"), "folder_zip", parent, help_button=False)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(QLabel(plain("arc_add_name")))
        name = QLineEdit(os.path.basename(target))
        lay.addWidget(name)
        use_pw = QCheckBox(plain("arc_add_pw"))
        lay.addWidget(use_pw)
        pw1, pw2 = QLineEdit(), QLineEdit()
        for e, lab in ((pw1, "auth_password"), (pw2, "ncw_pw_confirm")):
            e.setEchoMode(QLineEdit.Password)
            e.setEnabled(False)
            r = QHBoxLayout()
            l_ = QLabel(plain(lab))
            l_.setMinimumWidth(110)
            r.addWidget(l_)
            r.addWidget(e, 1)
            lay.addLayout(r)
        use_pw.toggled.connect(lambda on: (pw1.setEnabled(on), pw2.setEnabled(on)))
        if not archives.tool("7z"):
            use_pw.setEnabled(False)
            use_pw.setToolTip(plain("arc_need_7z"))
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)

        def accept():
            if use_pw.isChecked() and (not pw1.text() or pw1.text() != pw2.text()):
                dialogs.message(d, plain("arc_add_title"), plain("wifi_key_mismatch"), "warning")
                return
            d.accept()
        ok.clicked.connect(accept)
        b.addWidget(ok)
        b.addWidget(ca)
        lay.addLayout(b)
        d.setFixedWidth(380)
        if not d.exec():
            return None
        n = name.text().strip() or os.path.basename(target)
        if not n.lower().endswith(".zip"):
            n += ".zip"
        target = os.path.join(folder, n)
        password = pw1.text() if use_pw.isChecked() else None

    def fn(progress, cancelled):
        archives.create_zip(paths, target, progress, cancelled, password)
    pd = ProgressDialog(plain("arc_compressing_title"), tr("arc_compressing", os.path.basename(target)), fn, parent)
    pd.exec()
    ok, kind, msg = pd.result
    if not ok and not pd.worker.cancel:
        dialogs.message(parent, plain("arc_compressing_title"), msg, "error")
        return None
    return target if ok else None
