"""Okna sesji: Uruchamianie, Wyłącz komputer, Wylogowywanie."""
import os

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from .. import config
from ..common import dialogs, launcher, sysctl
from ..common.window import HDialog
from ..i18n import plain, tr
from ..theme import iconcache
from ..theme.base import hgrad, rounded_path, vgrad
from ..theme.manager import current


class RunDialog(HDialog):
    def __init__(self, parent=None):
        super().__init__(plain("run_title"), "", parent, help_button=True)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(10)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("run", 32))
        row.addWidget(ic, 0, Qt.AlignTop)
        desc = QLabel(tr("run_desc"))
        desc.setWordWrap(True)
        row.addWidget(desc, 1)
        row.setSpacing(12)
        lay.addLayout(row)
        r2 = QHBoxLayout()
        lbl = QLabel(tr("run_open"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.addItems(config.get("run_history", []))
        self.combo.setCurrentIndex(0 if self.combo.count() else -1)
        self.combo.lineEdit().selectAll()
        lbl.setBuddy(self.combo)
        r2.addWidget(lbl)
        r2.addWidget(self.combo, 1)
        lay.addLayout(r2)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(self.run)
        cancel = QPushButton(plain("cancel"))
        cancel.clicked.connect(self.reject)
        browse = QPushButton(plain("browse"))
        browse.clicked.connect(self.browse)
        for b in (ok, cancel, browse):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.setFixedSize(360, self.sizeHint().height())
        self.combo.setFocus()

    def browse(self):
        f = dialogs.open_file(self, plain("browse"), os.path.expanduser("~"))
        if f:
            self.combo.setEditText(f)

    def run(self):
        text = self.combo.currentText().strip()
        if not text:
            return
        if launcher.run_command(text):
            hist = [h for h in config.get("run_history", []) if h != text]
            config.set("run_history", [text] + hist[:19])
            self.accept()
        else:
            dialogs.message(self, text, tr("run_notfound", text), "error")


class BigRoundButton(QWidget):
    clicked = Signal()

    def __init__(self, icon, text, parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.text = text
        self._hover = False
        self.setMouseTracking(True)
        self.setFixedSize(100, 86)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sz = 40 if not self._hover else 44
        x = (self.width() - sz) // 2
        y = 8 - (2 if self._hover else 0)
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawEllipse(QRect(x - 6, y - 6, sz + 12, sz + 12))
        p.drawPixmap(x, y, iconcache.pixmap(self.icon_name, sz))
        f = current().font("normal")
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(0, 56, self.width(), 26), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.text)


class SessionOverlay(QDialog):
    """Pełnoekranowe przyciemnienie z oknem pośrodku (jak w klasycznym zamykaniu systemu)."""

    def __init__(self, title, buttons, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.title = title
        scr = QApplication.primaryScreen().geometry()
        self.setGeometry(scr)
        self.box = QRect(0, 0, 330, 196)
        self.box.moveCenter(self.rect().center())
        self.button_widgets = []
        n = len(buttons)
        total = n * 100
        x0 = self.box.left() + (self.box.width() - total) // 2
        for i, (icon, text, act) in enumerate(buttons):
            b = BigRoundButton(icon, text, self)
            b.move(x0 + i * 100, self.box.top() + 62)
            b.clicked.connect(lambda act=act: (self.accept(), QTimer.singleShot(100, act)))
            self.button_widgets.append(b)
        self.cancel = QPushButton(plain("cancel"), self)
        self.cancel.adjustSize()
        self.cancel.move(self.box.right() - self.cancel.width() - 12, self.box.bottom() - self.cancel.height() - 8)
        self.cancel.clicked.connect(self.reject)
        self._fade = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(30)

    def _step(self):
        self._fade = min(110, self._fade + 12)
        self.update()
        if self._fade >= 110:
            self._timer.stop()

    def resizeEvent(self, e):
        self.box.moveCenter(self.rect().center())
        n = len(self.button_widgets)
        x0 = self.box.left() + (self.box.width() - n * 100) // 2
        for i, b in enumerate(self.button_widgets):
            b.move(x0 + i * 100, self.box.top() + 62)
        self.cancel.move(self.box.right() - self.cancel.width() - 12, self.box.bottom() - self.cancel.height() - 8)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 24, 28, self._fade))
        t = current()
        sc = getattr(t, "sc", None)
        dark = sc["accent_darker"] if sc else "#0b4a52"
        mid = sc["accent"] if sc else "#1f8591"
        light = sc["accent_light"] if sc else "#5cc6d0"
        b = self.box
        p.setRenderHint(QPainter.Antialiasing)
        head = QRect(b.left(), b.top(), b.width(), 44)
        foot = QRect(b.left(), b.bottom() - 44, b.width(), 45)
        middle = QRect(b.left(), head.bottom() + 1, b.width(), foot.top() - head.bottom() - 1)
        p.fillRect(head, vgrad(head, [(0, dark), (1, mid)]))
        p.fillRect(middle, vgrad(middle, [(0, light), (0.5, mid), (1, light)]))
        p.fillRect(foot, vgrad(foot, [(0, mid), (1, dark)]))
        line = QRect(b.left(), head.bottom() - 1, b.width(), 2)
        p.fillRect(line, hgrad(line, [(0, "#ffffff00"), (0.5, "#ffffff"), (1, "#ffffff00")]))
        p.setPen(QPen(QColor(dark).darker(130), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(b.adjusted(0, 0, -1, -1))
        f = t.font("big")
        f.setPixelSize(18)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(head.adjusted(14, 0, -60, 0), Qt.AlignVCenter | Qt.AlignLeft, self.title)
        p.drawPixmap(head.right() - 40, head.top() + 6, iconcache.pixmap("logo", 32))


def turn_off_dialog(parent=None):
    d = SessionOverlay(plain("turnoff_title"), [
        ("standby", plain("standby"), lambda: sysctl.power_action("standby")),
        ("shutdown", plain("turnoff"), lambda: sysctl.power_action("turnoff")),
        ("restart", plain("restart"), lambda: sysctl.power_action("restart")),
    ], parent)
    d.exec()


def logoff_dialog(parent=None):
    d = SessionOverlay(plain("logoff_title"), [
        ("switch_user", plain("switch_user"), sysctl.switch_user),
        ("logoff", plain("logoff"), sysctl.logoff),
    ], parent)
    d.exec()
