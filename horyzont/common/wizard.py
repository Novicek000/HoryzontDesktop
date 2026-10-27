"""Kreator w klasycznym układzie: strona powitalna i końcowa z ozdobnym pasem po lewej,
strony wewnętrzne z białym nagłówkiem (tytuł, podtytuł, ikona) i przyciski
„< Wstecz”, „Dalej >”, „Anuluj” na dole."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..i18n import plain
from ..theme import iconcache
from ..theme.base import vgrad
from ..theme.manager import current
from .window import HDialog


class WizardPage(QWidget):
    """exterior=True — strona powitalna/końcowa; inaczej strona wewnętrzna."""

    completeChanged = Signal()

    def __init__(self, title, subtitle="", exterior=False):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.exterior = exterior
        self.lay = QVBoxLayout()
        self.lay.setSpacing(8)

    # do nadpisania
    def on_enter(self, wizard):
        pass

    def validate(self, wizard):
        """Wywoływane po „Dalej”. Zwraca False, by zostać na stronie."""
        return True

    def is_complete(self):
        return True

    def next_id(self, wizard):
        """Indeks następnej strony (None = kolejna)."""
        return None


class _Banner(QWidget):
    """Ozdobny pas strony powitalnej — oryginalny rysunek: gradient, łuki i ikona kreatora."""

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.setFixedWidth(164)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = current()
        sc = getattr(t, "sc", {}) or {}
        c1 = sc.get("accent_light", "#5fb9c4")
        c2 = sc.get("accent_dark", "#0f5d67")
        r = QRectF(self.rect())
        p.fillRect(r, vgrad(r, [(0, c1), (1, c2)]))
        p.setPen(Qt.NoPen)
        for i, (yy, rad, a) in enumerate(((0.25, 160, 40), (0.6, 120, 30), (0.95, 200, 25))):
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QRectF(-rad * 0.6, r.height() * yy - rad / 2, rad, rad))
        path = QPainterPath()
        path.moveTo(r.width(), r.height() * 0.35)
        path.cubicTo(r.width() * 0.4, r.height() * 0.5, r.width() * 0.7, r.height() * 0.8, 0, r.height() * 0.9)
        p.setPen(QPen(QColor(255, 255, 255, 120), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.drawPixmap(int(r.width() - 72), 18, iconcache.pixmap(self.icon, 56))


class _Header(QWidget):
    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.title = ""
        self.subtitle = ""
        self.setFixedHeight(58)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        f = QFont(current().font("normal"))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#000000"))
        p.drawText(20, 8, self.width() - 90, 18, Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(current().font("normal"))
        p.drawText(36, 26, self.width() - 110, 30, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.subtitle)
        p.drawPixmap(self.width() - 54, 7, iconcache.pixmap(self.icon, 44))
        p.setPen(QColor("#aca899"))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class Wizard(HDialog):
    finished_ok = Signal()

    def __init__(self, title, icon="wizard", parent=None):
        super().__init__(title, icon, parent, help_button=False)
        self.icon = icon
        self.pages = []
        self.history = []
        self.data = {}
        outer = QVBoxLayout(self.body())
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #aca899;")
        outer.addWidget(line)
        brow = QHBoxLayout()
        brow.setContentsMargins(10, 10, 10, 10)
        brow.addStretch(1)
        self.back_btn = QPushButton("< " + plain("wiz_back"))
        self.next_btn = QPushButton(plain("wiz_next") + " >")
        self.cancel_btn = QPushButton(plain("cancel"))
        self.back_btn.clicked.connect(self.back)
        self.next_btn.clicked.connect(self.next)
        self.cancel_btn.clicked.connect(self.reject)
        brow.addWidget(self.back_btn)
        brow.addWidget(self.next_btn)
        brow.addSpacing(8)
        brow.addWidget(self.cancel_btn)
        outer.addLayout(brow)
        self.resize(520, 400)

    def add_page(self, page):
        holder = QWidget()
        if page.exterior:
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            hl.addWidget(_Banner(self.icon))
            right = QWidget()
            right.setAutoFillBackground(True)
            pal = right.palette()
            pal.setColor(right.backgroundRole(), QColor("#ffffff"))
            right.setPalette(pal)
            rl = QVBoxLayout(right)
            rl.setContentsMargins(20, 18, 18, 12)
            t = QLabel(page.title)
            f = QFont(current().font("normal"))
            f.setPointSizeF(f.pointSizeF() * 1.45 if f.pointSizeF() > 0 else 13)
            f.setBold(True)
            t.setFont(f)
            t.setWordWrap(True)
            rl.addWidget(t)
            rl.addSpacing(10)
            rl.addLayout(page.lay)
            rl.addStretch(1)
            hl.addWidget(right, 1)
        else:
            vl = QVBoxLayout(holder)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)
            hdr = _Header(self.icon)
            hdr.title, hdr.subtitle = page.title, page.subtitle
            vl.addWidget(hdr)
            body = QWidget()
            bl = QVBoxLayout(body)
            bl.setContentsMargins(36, 14, 30, 10)
            bl.addLayout(page.lay)
            bl.addStretch(1)
            vl.addWidget(body, 1)
        page.setParent(holder)
        page.hide()
        page.completeChanged.connect(self._update_buttons)
        self.pages.append(page)
        self.stack.addWidget(holder)
        return len(self.pages) - 1

    def start(self):
        self.history = []
        self._go(0)
        return self.exec()

    def current_index(self):
        return self.stack.currentIndex()

    def _go(self, i):
        self.stack.setCurrentIndex(i)
        self.pages[i].on_enter(self)
        self._update_buttons()

    def _update_buttons(self):
        i = self.current_index()
        page = self.pages[i]
        last = i == len(self.pages) - 1 or getattr(page, "final", False)
        self.back_btn.setEnabled(bool(self.history) and not getattr(page, "final", False))
        self.next_btn.setText(plain("wiz_finish") if last else plain("wiz_next") + " >")
        self.next_btn.setEnabled(page.is_complete())
        self.next_btn.setDefault(True)
        self.cancel_btn.setEnabled(not getattr(page, "final", False) or not last)

    def next(self):
        i = self.current_index()
        page = self.pages[i]
        if not page.validate(self):
            return
        if i == len(self.pages) - 1 or getattr(page, "final", False):
            self.finished_ok.emit()
            self.accept()
            return
        n = page.next_id(self)
        self.history.append(i)
        self._go(i + 1 if n is None else n)

    def back(self):
        if self.history:
            self._go(self.history.pop())

    def goto(self, i):
        self.history.append(self.current_index())
        self._go(i)
