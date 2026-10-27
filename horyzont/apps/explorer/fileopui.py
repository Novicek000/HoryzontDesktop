"""Kopiowanie/przenoszenie z oknem postępu oraz pytaniem o zastąpienie plików."""
import os
import threading

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout)

from ...common import dialogs, fileops
from ...common.window import HDialog
from ...i18n import plain, tr
from ...theme import iconcache


class _Worker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(list, list)

    def __init__(self, srcs, dest, move, decisions):
        super().__init__()
        self.srcs, self.dest, self.move, self.decisions = srcs, dest, move, decisions
        self.cancelled = False

    def run(self):
        def prog(i, n, name):
            self.progress.emit(i, n, name)
            return not self.cancelled

        created, errors = fileops.copy_into(self.srcs, self.dest, self.move,
                                            conflict=lambda name: self.decisions.get(name, "rename"),
                                            progress=prog)
        self.finished_ok.emit(created, errors)


class ProgressDialog(HDialog):
    def __init__(self, parent, move):
        super().__init__(plain("moving" if move else "copying"), "copy", parent, help_button=False)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 12, 12, 12)
        row = QHBoxLayout()
        a = QLabel()
        a.setPixmap(iconcache.pixmap("folder", 32))
        b = QLabel()
        b.setPixmap(iconcache.pixmap("file_text", 32))
        c = QLabel()
        c.setPixmap(iconcache.pixmap("folder_open", 32))
        self._anim = b
        row.addWidget(a)
        row.addStretch(1)
        row.addWidget(b)
        row.addStretch(1)
        row.addWidget(c)
        lay.addLayout(row)
        self.label = QLabel("")
        lay.addWidget(self.label)
        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        self.cancel = QPushButton(plain("cancel"))
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(self.cancel)
        lay.addLayout(h)
        self.setFixedSize(380, self.sizeHint().height())


def run_copy(parent, srcs, dest, move=False, done=None):
    """Kopiuje/przenosi pliki pokazując postęp. ``done(created, errors)`` po zakończeniu."""
    srcs = [s for s in srcs if s and os.path.abspath(os.path.dirname(s)) != os.path.abspath(dest) or not move]
    if not srcs:
        return
    # rozstrzygnięcie konfliktów przed rozpoczęciem
    decisions = {}
    yes_all = False
    for s in srcs:
        name = os.path.basename(s.rstrip("/"))
        if os.path.abspath(os.path.dirname(s)) == os.path.abspath(dest):
            continue
        if os.path.lexists(os.path.join(dest, name)):
            if yes_all:
                decisions[name] = "replace"
                continue
            ans = dialogs.message(parent, plain("confirm_replace_title"), tr("confirm_replace", name), "warning",
                                  (plain("yes"), plain("yes_all"), plain("no"), plain("cancel")), plain("yes"))
            if ans == plain("yes"):
                decisions[name] = "replace"
            elif ans == plain("yes_all"):
                decisions[name] = "replace"
                yes_all = True
            elif ans == plain("no"):
                decisions[name] = "skip"
            else:
                return
    total_small = len(srcs) <= 3 and all(os.path.isfile(s) and os.path.getsize(s) < 20_000_000 for s in srcs if os.path.exists(s))
    if total_small:
        created, errors = fileops.copy_into(srcs, dest, move, conflict=lambda n: decisions.get(n, "rename"))
        _report(parent, errors)
        if done:
            done(created, errors)
        return
    dlg = ProgressDialog(parent, move)
    w = _Worker(srcs, dest, move, decisions)

    def prog(i, n, name):
        dlg.bar.setMaximum(n)
        dlg.bar.setValue(i)
        dlg.label.setText(name)

    def fin(created, errors):
        dlg.accept()
        _report(parent, errors)
        if done:
            done(created, errors)

    w.progress.connect(prog)
    w.finished_ok.connect(fin)
    dlg.cancel.clicked.connect(lambda: setattr(w, "cancelled", True))
    w.start()
    dlg._worker = w
    dlg.exec()
    w.wait(100)


def _report(parent, errors):
    if errors:
        dialogs.message(parent, plain("error"), "\n".join(f"{os.path.basename(p)}: {m}" for p, m in errors[:6]), "error")
