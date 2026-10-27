"""Panel zadań (lewa kolumna Eksploratora i Panelu sterowania) z sekcjami do zwijania."""
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QCursor
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..theme import iconcache
from ..theme.manager import ThemeManager, current


class TaskLink(QWidget):
    clicked = Signal()

    def __init__(self, icon, text, callback=None, parent=None, bold=False, qicon=None, context=None):
        super().__init__(parent)
        self.context = context   # funkcja(pozycja globalna) — menu kontekstowe (np. dla „Inne miejsca”)
        self.icon_name = icon
        self.qicon = qicon
        self.text = text
        self.bold = bold
        self._hover = False
        if callback:
            self.clicked.connect(callback)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _font(self):
        f = current().font("normal")
        f.setBold(self.bold)
        if self._hover:
            f.setUnderline(True)
        return f

    def heightForWidth(self, w):
        fm = QFontMetrics(self._font())
        r = fm.boundingRect(QRect(0, 0, max(20, w - 24), 1000), Qt.TextWordWrap, self.text)
        return max(18, r.height() + 4)

    def hasHeightForWidth(self):
        return True

    def sizeHint(self):
        return QSize(150, self.heightForWidth(self.width() if self.width() > 30 else 170))

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def contextMenuEvent(self, e):
        if self.context is not None:
            self.context(e.globalPos())
            e.accept()
        else:
            super().contextMenuEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        x = 0
        if self.qicon is not None:
            p.drawPixmap(0, 1, self.qicon.pixmap(16, 16))
            x = 22
        elif self.icon_name:
            p.drawPixmap(0, 1, iconcache.pixmap(self.icon_name, 16))
            x = 22
        p.setFont(self._font())
        p.setPen(t.color("taskpane_link_hover" if self._hover else "taskpane_link"))
        p.drawText(QRect(x, 0, self.width() - x, self.height()), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                   self.text)


class TaskSection(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, special=False, parent=None):
        super().__init__(parent)
        self.title = title
        self.special = special
        self.expanded = True
        self._hover = False
        self.header_h = 25
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 10, 10, 10)
        self.body_layout.setSpacing(5)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, self.header_h, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.body)
        self.setMouseTracking(True)

    def add_link(self, icon, text, callback=None, bold=False, qicon=None, context=None):
        l = TaskLink(icon, text, callback, self.body, bold=bold, qicon=qicon, context=context)
        self.body_layout.addWidget(l)
        return l

    def add_widget(self, w):
        self.body_layout.addWidget(w)
        return w

    def add_text(self, text, bold=False, wrap=True):
        lbl = QLabel(text, self.body)
        lbl.setWordWrap(wrap)
        f = current().font("normal")
        f.setBold(bold)
        lbl.setFont(f)
        self.body_layout.addWidget(lbl)
        return lbl

    def set_expanded(self, e):
        self.expanded = e
        self.body.setVisible(e)
        self.update()
        self.toggled.emit(e)

    def mouseMoveEvent(self, e):
        h = e.position().y() < self.header_h
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.position().y() < self.header_h and e.button() == Qt.LeftButton:
            self.set_expanded(not self.expanded)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        hr = QRect(0, 0, self.width(), self.header_h)
        t.draw_taskpane_header(p, hr, self.special, self._hover, self.expanded)
        f = t.font("taskpane_header")
        p.setFont(f)
        col = t.color("taskpane_header_special_text" if self.special else "taskpane_header_text")
        if self._hover and not self.special:
            col = t.color("taskpane_link_hover")
        p.setPen(col)
        p.drawText(hr.adjusted(12, 0, -30, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(f).elidedText(self.title, Qt.ElideRight, hr.width() - 42))
        if self.expanded:
            t.draw_taskpane_body(p, QRect(0, self.header_h, self.width(), self.height() - self.header_h), self.special)


class _PaneContent(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        current().draw_taskpane_bg(p, self.rect())


class TaskPane(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = _PaneContent()
        self.lay = QVBoxLayout(self.content)
        self.lay.setContentsMargins(12, 12, 12, 12)
        self.lay.setSpacing(15)
        self.lay.addStretch(1)
        self.setWidget(self.content)
        w = current().metrics["taskpane_w"]
        self.setMinimumWidth(int(w * current().font_scale))
        self.setMaximumWidth(int(w * 1.6 * current().font_scale))
        ThemeManager.instance().changed.connect(self.content.update)
        from PySide6.QtCore import QTimer
        self._sb_timer = QTimer(self)
        self._sb_timer.setSingleShot(True)
        self._sb_timer.setInterval(0)
        self._sb_timer.timeout.connect(self._update_scrollbar)

    def _update_scrollbar(self):
        vw = self.viewport().width()
        need = self.lay.totalHeightForWidth(vw) if self.lay.hasHeightForWidth() else self.content.sizeHint().height()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if need > self.viewport().height() + 2 else Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sb_timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        self._sb_timer.start()

    def clear(self):
        while self.lay.count() > 1:
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def add_section(self, title, special=False):
        s = TaskSection(title, special, self.content)
        self.lay.insertWidget(self.lay.count() - 1, s)
        s.toggled.connect(lambda *_: self._sb_timer.start())
        self._sb_timer.start()
        return s

    def add_widget(self, w):
        self.lay.insertWidget(self.lay.count() - 1, w)
        return w


def place_menu(parent, path, gpos):
    """Menu kontekstowe miejsca (Mój komputer, Moje dokumenty…) w oknach innych niż Eksplorator."""
    from PySide6.QtWidgets import QMenu
    from . import launcher
    from ..i18n import tr
    m = QMenu(parent)
    if path == "horyzont:control":
        a = m.addAction(tr("open"), lambda: launcher.start_builtin("control"))
    else:
        a = m.addAction(tr("open"), lambda: launcher.start_builtin("explorer", [path]))
        m.addAction(tr("explore"), lambda: launcher.start_builtin("explorer", ["--folders", path]))
    f = a.font()
    f.setBold(True)
    a.setFont(f)
    if path == "horyzont:computer":
        m.addAction(tr("manage"), lambda: launcher.start_builtin("control", ["disks"]))
        m.addSeparator()
        m.addAction(tr("properties"), lambda: launcher.start_builtin("control", ["system"]))
    elif path == "horyzont:network":
        m.addSeparator()
        m.addAction(tr("properties"), lambda: launcher.start_builtin("control", ["network"]))
    m.exec(gpos)
