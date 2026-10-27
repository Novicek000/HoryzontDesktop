"""Wspólne elementy apletów Panelu sterowania."""
import subprocess

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialogButtonBox, QFrame, QLabel, QTabWidget,
                               QVBoxLayout, QWidget)

from ...common import dialogs
from ...common.window import HDialog
from ...i18n import plain, tr
from ...theme.base import vgrad


class AppletDialog(HDialog):
    """Okno apletu z zakładkami i przyciskami OK / Anuluj / Zastosuj."""

    def __init__(self, title, icon, parent=None, apply=True):
        super().__init__(title, icon, parent, help_button=True)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        if apply:
            buttons |= QDialogButtonBox.Apply
        self.bb = QDialogButtonBox(buttons)
        self.bb.accepted.connect(self._ok)
        self.bb.rejected.connect(self.reject)
        if apply:
            self.apply_btn = self.bb.button(QDialogButtonBox.Apply)
            self.apply_btn.clicked.connect(self._apply)
            self.apply_btn.setEnabled(False)
        else:
            self.apply_btn = None
        lay.addWidget(self.bb)

    def changed(self, *_):
        if self.apply_btn is not None:
            self.apply_btn.setEnabled(True)

    def apply(self):
        """Do nadpisania: zapisuje ustawienia. Zwraca False, by przerwać zamknięcie."""
        return True

    def _apply(self):
        if self.apply() is not False and self.apply_btn is not None:
            self.apply_btn.setEnabled(False)

    def _ok(self):
        if self.apply_btn is None or self.apply_btn.isEnabled():
            if self.apply() is False:
                return
        self.accept()

    def add_tab(self, title):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.tabs.addTab(w, title)
        return w, lay


class MonitorPreview(QWidget):
    """Rysunek monitora z miniaturą zawartości (tapeta, wygaszacz)."""

    def __init__(self, painter_fn=None, parent=None):
        super().__init__(parent)
        self.painter_fn = painter_fn
        self.setFixedSize(186, 160)

    def screen_rect(self):
        return QRect(17, 16, 152, 113)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(6, 4, 174, 136)
        p.setBrush(vgrad(body, [(0, "#eef1f3"), (1, "#b6c0c8")]))
        p.setPen(QPen(QColor("#5c6670"), 1))
        p.drawRoundedRect(body, 6, 6)
        # podstawka
        p.setBrush(vgrad(QRectF(60, 140, 66, 16), [(0, "#c8d0d6"), (1, "#8d99a3")]))
        p.drawRect(QRectF(80, 139, 26, 8))
        p.drawRoundedRect(QRectF(52, 146, 82, 9), 3, 3)
        sr = self.screen_rect()
        p.fillRect(sr.adjusted(-1, -1, 1, 1), QColor("#30383e"))
        p.save()
        p.setClipRect(sr)
        if self.painter_fn:
            self.painter_fn(p, sr)
        else:
            p.fillRect(sr, QColor("#000000"))
        p.restore()
        p.setBrush(QColor("#38c46c"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(160, 132, 4, 4))


def run_privileged(args, parent=None):
    """Uruchamia polecenie jako administrator (okno hasła Horyzont). Zwraca (ok, wyjście)."""
    from ...common.privileged import run_privileged as rp
    return rp(args, parent)


def run(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except Exception as e:
        return -1, str(e)


def hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #c8d0cf;")
    return f


def wrap_label(text):
    l = QLabel(text)
    l.setWordWrap(True)
    return l
