"""Okna komunikatów, pytania i okna wyboru plików w ramce motywu."""
import os

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..i18n import plain, tr
from ..theme import iconcache
from .window import HDialog

BUTTON_TEXT = {"ok": "ok", "cancel": "cancel", "yes": "yes", "no": "no", "close": "close",
               "apply": "apply", "retry": "Ponów", "ignore": "Ignoruj"}


def message(parent, title, text, icon="info", buttons=("ok",), default=None, detail=None):
    """Pokazuje komunikat i zwraca klucz klikniętego przycisku (lub 'cancel' po zamknięciu)."""
    dlg = HDialog(title, "", parent, help_button=False)
    body = dlg.body()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(12, 14, 12, 12)
    lay.setSpacing(14)
    row = QHBoxLayout()
    row.setSpacing(14)
    if icon:
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap(icon, 32))
        ic.setAlignment(Qt.AlignTop)
        row.addWidget(ic, 0, Qt.AlignTop)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setMinimumWidth(min(380, max(200, len(text) * 6)))
    lbl.setMaximumWidth(460)
    row.addWidget(lbl, 1)
    lay.addLayout(row)
    if detail:
        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet("color: #555;")
        lay.addWidget(d)
    brow = QHBoxLayout()
    brow.addStretch(1)
    result = {"key": "cancel"}
    for key in buttons:
        b = QPushButton(plain(BUTTON_TEXT.get(key, key)) if key in BUTTON_TEXT else key)
        if key in ("retry", "ignore"):
            b.setText(BUTTON_TEXT[key])
        b.clicked.connect(lambda _=False, k=key: (result.__setitem__("key", k), dlg.accept()))
        if key == (default or buttons[0]):
            b.setDefault(True)
            b.setFocus()
        brow.addWidget(b)
    brow.addStretch(1)
    lay.addLayout(brow)
    dlg.adjustSize()
    if "cancel" not in buttons and "no" in buttons:
        result["key"] = "no"
    try:
        from . import sounds
        ev = {"error": "error", "warning": "exclamation", "question": "question", "info": "notify",
              "recycle_full": "exclamation"}.get(icon)
        if ev:
            sounds.play(ev)
    except Exception:
        pass
    dlg.exec()
    return result["key"]


def ask_text(parent, title, label, text="", icon=""):
    dlg = HDialog(title, icon, parent, help_button=False)
    lay = QVBoxLayout(dlg.body())
    lay.setContentsMargins(12, 12, 12, 12)
    lay.addWidget(QLabel(label))
    le = QLineEdit(text)
    le.selectAll()
    lay.addWidget(le)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.resize(340, dlg.sizeHint().height())
    if dlg.exec() == QDialog.Accepted:
        return le.text()
    return None


class _EmbeddedFileDialog(HDialog):
    def __init__(self, parent, title, directory, filters, mode, default_name="", extra=None):
        super().__init__(title, "folder_open", parent, resizable=True, help_button=True)
        self.fd = QFileDialog(self, title, directory, filters)
        self.fd.setOption(QFileDialog.DontUseNativeDialog, True)
        self.fd.setWindowFlags(Qt.Widget)
        self.fd.setSizeGripEnabled(False)
        if mode == "open":
            self.fd.setAcceptMode(QFileDialog.AcceptOpen)
            self.fd.setFileMode(QFileDialog.ExistingFile)
        elif mode == "open_many":
            self.fd.setAcceptMode(QFileDialog.AcceptOpen)
            self.fd.setFileMode(QFileDialog.ExistingFiles)
        elif mode == "dir":
            self.fd.setFileMode(QFileDialog.Directory)
            self.fd.setOption(QFileDialog.ShowDirsOnly, True)
        else:
            self.fd.setAcceptMode(QFileDialog.AcceptSave)
            self.fd.setFileMode(QFileDialog.AnyFile)
            if default_name:
                self.fd.selectFile(default_name)
        home = QDir.homePath()
        from .. import config
        side = [home, config.user_dir("DESKTOP"), config.user_dir("DOCUMENTS"), config.user_dir("PICTURES"),
                config.user_dir("MUSIC"), "/"]
        from PySide6.QtCore import QUrl
        self.fd.setSidebarUrls([QUrl.fromLocalFile(p) for p in side if os.path.isdir(p)])
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.fd)
        if extra is not None:
            lay.addWidget(extra)
        self.fd.finished.connect(self.done)
        self.resize(640, 440)


def _run_file_dialog(parent, title, directory, filters, mode, default_name="", extra=None):
    d = _EmbeddedFileDialog(parent, title, directory or os.path.expanduser("~"), filters, mode, default_name, extra)
    if d.exec() == QDialog.Accepted:
        files = d.fd.selectedFiles()
        return files, d.fd.selectedNameFilter()
    return [], ""


def open_file(parent, title, directory="", filters=""):
    files, _ = _run_file_dialog(parent, title, directory, filters, "open")
    return files[0] if files else None


def open_files(parent, title, directory="", filters=""):
    files, _ = _run_file_dialog(parent, title, directory, filters, "open_many")
    return files


def save_file(parent, title, directory="", filters="", default_name="", extra=None):
    files, flt = _run_file_dialog(parent, title, directory, filters, "save", default_name, extra)
    return (files[0] if files else None), flt


def choose_dir(parent, title, directory=""):
    files, _ = _run_file_dialog(parent, title, directory, "", "dir")
    return files[0] if files else None
