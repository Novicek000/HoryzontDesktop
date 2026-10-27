"""Okno postępu długiej operacji (instalacja, aktualizacja) z dziennikiem szczegółów."""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
                               QPushButton, QVBoxLayout)

from ..i18n import plain
from ..theme import iconcache
from .privileged import PrivilegedJob
from .window import HDialog

PCT_RE = re.compile(r"(\d{1,3})\s?%")
STEP_RE = re.compile(r"\[\s*(\d+)/(\d+)\]")


class JobDialog(HDialog):
    def __init__(self, title, text, args, root=True, parent=None, icon="addremove", auto_close=True):
        super().__init__(title, icon, parent, help_button=False)
        self.auto_close = auto_close
        self.ok = False
        self.output = ""
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap(icon, 32))
        row.addWidget(ic, 0, Qt.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)
        lay.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.status = QLabel(plain("job_starting"))
        self.status.setStyleSheet("color: #444;")
        lay.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        f = QFont("Monospace")
        f.setStyleHint(QFont.TypeWriter)
        f.setPointSize(8)
        self.log.setFont(f)
        self.log.hide()
        lay.addWidget(self.log, 1)
        btns = QHBoxLayout()
        self.details_btn = QPushButton(plain("job_details") + " >>")
        self.details_btn.clicked.connect(self._toggle_details)
        btns.addWidget(self.details_btn)
        btns.addStretch(1)
        self.cancel_btn = QPushButton(plain("cancel"))
        self.cancel_btn.clicked.connect(self._cancel)
        btns.addWidget(self.cancel_btn)
        self.close_btn = QPushButton(plain("close"))
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.hide()
        btns.addWidget(self.close_btn)
        lay.addLayout(btns)
        self.setMinimumWidth(460)
        self.job = PrivilegedJob(args, self, root=root)
        self.job.output.connect(self._out)
        self.job.finished.connect(self._done)
        self._partial = ""

    def _toggle_details(self):
        vis = not self.log.isVisible()
        self.log.setVisible(vis)
        self.details_btn.setText(plain("job_details") + (" <<" if vis else " >>"))
        self.resize(self.width(), 460 if vis else self.minimumSizeHint().height())

    def _out(self, text):
        self.output += text
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)
        self.log.ensureCursorVisible()
        last = [l for l in (self._partial + text).replace("\r", "\n").split("\n") if l.strip()]
        self._partial = (self._partial + text)[-400:]
        if last:
            line = last[-1].strip()
            self.status.setText(line[:110])
            m = STEP_RE.search(line)
            if m and int(m.group(2)) > 0:
                self.bar.setRange(0, int(m.group(2)))
                self.bar.setValue(int(m.group(1)))
            else:
                m = PCT_RE.search(line)
                if m and 0 <= int(m.group(1)) <= 100:
                    self.bar.setRange(0, 100)
                    self.bar.setValue(int(m.group(1)))

    def _cancel(self):
        self.job.cancel()
        self.status.setText(plain("job_cancelling"))

    def _done(self, ok, text):
        self.ok = ok
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if ok else 0)
        self.cancel_btn.hide()
        self.close_btn.show()
        self.close_btn.setDefault(True)
        if ok:
            self.status.setText(plain("job_done"))
            if self.auto_close:
                self.accept()
        else:
            self.status.setText(plain("job_failed"))
            self.status.setStyleSheet("color: #b00000; font-weight: bold;")
            if not self.log.isVisible():
                self._toggle_details()
            if not self.output.strip():
                self.log.setPlainText(text)

    def run(self):
        from PySide6.QtCore import QTimer
        # najpierw pokazujemy okno postępu, potem uruchamiamy polecenie — okno hasła pojawi się nad nim
        QTimer.singleShot(250, self.job.start)
        self.exec()
        return self.ok, self.output


def run_job(parent, title, text, args, root=True, icon="addremove", auto_close=True):
    """Uruchamia polecenie z oknem postępu. Zwraca (ok, wyjście)."""
    d = JobDialog(title, text, args, root, parent, icon, auto_close)
    return d.run()
