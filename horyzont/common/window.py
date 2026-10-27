"""Okna z własną ramką (dekoracje po stronie klienta) rysowaną przez motyw."""
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QKeySequence, QPainter, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QMenu, QSizeGrip,
                               QToolTip, QVBoxLayout, QWidget)

from ..i18n import tr
from ..theme import iconcache
from ..theme.base import HOVER, NORMAL, PRESSED
from ..theme.manager import ThemeManager, current

RESIZE_MARGIN = 5


class FrameMixin:
    """Wspólna logika ramki dla HWindow (QWidget) i HDialog (QDialog)."""

    def _frame_init(self, title="", icon_name="app", resizable=True, minimizable=True,
                    maximizable=True, help_button=False, closable=True):
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._icon_name = icon_name
        self._resizable = resizable
        self._kinds = []
        if help_button:
            self._kinds.append("help")
        if minimizable:
            self._kinds.append("min")
        if maximizable:
            self._kinds.append("max")
        if closable:
            self._kinds.append("close")
        self._hover = None
        self._pressed = None
        self._drag_pos = None
        self._resize_edges = None
        self._resize_start = None
        self._sys_op = False   # trwa przesuwanie/zmiana rozmiaru przez kompozytor
        self._body = QWidget(self)
        self._body.setObjectName("frameBody")
        self._body.setAutoFillBackground(True)
        self._body.setMouseTracking(False)
        # kursor zmiany rozmiaru ustawiamy na całym oknie — po wejściu wskaźnika
        # do treści okna trzeba go zdjąć (treść nie przekazuje ruchów myszy ramce)
        self._body.installEventFilter(self)
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        self._outer = lay
        lay.addWidget(self._body)
        self.setWindowTitle(title)
        self.setWindowIcon(iconcache.icon(icon_name))
        self._apply_margins()
        ThemeManager.instance().changed.connect(self._on_theme)

    # --------------------------------------------------------------- API
    def body(self):
        return self._body

    def setCentralWidget(self, w):
        lay = self._body.layout()
        if lay is None:
            lay = QVBoxLayout(self._body)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
        lay.addWidget(w)

    def setIconName(self, name):
        self._icon_name = name
        self.setWindowIcon(iconcache.icon(name))
        self.update()

    def is_max(self):
        return bool(self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen))

    def toggle_maximize(self):
        if "max" not in self._kinds:
            return
        if self.is_max():
            self.showNormal()
        else:
            self.showMaximized()

    # --------------------------------------------------------------- geometria
    def _apply_margins(self):
        l, t, r, b = current().frame_margins(self.is_max())
        self._outer.setContentsMargins(l, t, r, b)
        self.update()

    def _on_theme(self):
        try:
            self._apply_margins()
            self._body.setPalette(QApplication.palette())
            self.update()
        except RuntimeError:
            pass

    def _button_rects(self):
        kinds = tuple(self._kinds)
        theme = current()
        rects = theme.caption_button_rects(self.width(), self.is_max(), tuple(k for k in kinds if k != "help"))
        if "help" in kinds:
            # pomoc stoi po lewej od zamknięcia (lub minimalizacji)
            left = min(r.left() for r in rects.values()) if rects else self.width() - 30
            size = theme.metrics["caption_button"]
            any_r = next(iter(rects.values())) if rects else QRect(0, 4, size, size)
            rects["help"] = QRect(left - size - theme.metrics["caption_button_gap"], any_r.top(), size, size)
        return rects

    def _caption_rect(self):
        l, t, r, b = current().frame_margins(self.is_max())
        return QRect(0, 0, self.width(), t)

    def _edges_at(self, pos):
        if not self._resizable or self.is_max():
            return None
        m = RESIZE_MARGIN
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        edges = Qt.Edges()
        if x < m:
            edges |= Qt.LeftEdge
        elif x >= w - m:
            edges |= Qt.RightEdge
        if y < m:
            edges |= Qt.TopEdge
        elif y >= h - m:
            edges |= Qt.BottomEdge
        return edges if edges else None

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "_body", None):
            t = ev.type()
            if t == QEvent.Enter:
                self.unsetCursor()
                self._end_sys_op()
            elif t in (QEvent.MouseButtonPress, QEvent.MouseMove):
                self._end_sys_op()
        return False

    def _start_sys_op(self, resize_edges=None):
        """Przesuwanie/rozciąganie okna przez kompozytor. Na czas tej operacji labwc
        odbiera oknu fokus klawiatury — ramka ma jednak dalej wyglądać na aktywną."""
        wh = self.windowHandle()
        if wh is None:
            return False
        ok = wh.startSystemResize(resize_edges) if resize_edges else wh.startSystemMove()
        if ok:
            self._sys_op = True
            self.update()
        return ok

    def _end_sys_op(self):
        if self._sys_op:
            self._sys_op = False
            self.update()

    # --------------------------------------------------------------- rysowanie
    def paintEvent(self, ev):
        theme = current()
        p = QPainter(self)
        active = self.isActiveWindow() or self._sys_op
        theme.draw_window_frame(p, self.rect(), active, self.is_max())
        l, t, r, b = theme.frame_margins(self.is_max())
        # ikona
        icon_size = 16
        x = l + 5
        if self._icon_name:
            p.drawPixmap(x, (t - icon_size) // 2 + (0 if self.is_max() else 1), iconcache.pixmap(self._icon_name, icon_size))
            x += icon_size + 5
        rects = self._button_rects()
        right = min((rr.left() for rr in rects.values()), default=self.width() - r) - 6
        text_rect = QRect(x, 0 if self.is_max() else 1, max(0, right - x), t)
        theme.draw_caption_text(p, text_rect, self.windowTitle(), active)
        for kind, rr in rects.items():
            k = kind
            if kind == "max" and self.is_max():
                k = "restore"
            st = NORMAL
            if self._pressed == kind and self._hover == kind:
                st = PRESSED
            elif self._hover == kind:
                st = HOVER
            theme.draw_caption_button(p, rr, k, st, active)
        p.end()

    # --------------------------------------------------------------- mysz
    def _button_at(self, pos):
        for kind, rr in self._button_rects().items():
            if rr.contains(pos):
                return kind
        return None

    def mousePressEvent(self, ev):
        pos = ev.position().toPoint()
        self._end_sys_op()
        if ev.button() == Qt.LeftButton:
            edges = self._edges_at(pos)
            if edges:
                if not self._start_sys_op(edges):
                    self._resize_edges = edges
                    self._resize_start = (ev.globalPosition().toPoint(), QRect(self.geometry()))
                return
            b = self._button_at(pos)
            if b:
                self._pressed = b
                self.update()
                return
            if self._caption_rect().contains(pos):
                l, t, r, bb = current().frame_margins(self.is_max())
                if pos.x() < l + 24 and self._icon_name:
                    self._show_system_menu(self.mapToGlobal(QPoint(l, t)))
                    return
                if self.is_max():
                    # przeciąganie zmaksymalizowanego okna nie przywraca go w tej wersji
                    return
                if not self._start_sys_op():
                    self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return
        elif ev.button() == Qt.RightButton and self._caption_rect().contains(pos):
            self._show_system_menu(ev.globalPosition().toPoint())
            return
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        pos = ev.position().toPoint()
        if ev.button() == Qt.LeftButton and self._caption_rect().contains(pos) and not self._button_at(pos):
            l, t, r, b = current().frame_margins(self.is_max())
            if pos.x() < l + 24 and self._icon_name:
                self.close()
                return
            self.toggle_maximize()
            return
        super().mouseDoubleClickEvent(ev)

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        if not ev.buttons():
            self._end_sys_op()
        if self._resize_edges and self._resize_start:
            g0, rect0 = self._resize_start
            d = ev.globalPosition().toPoint() - g0
            r = QRect(rect0)
            if self._resize_edges & Qt.LeftEdge:
                r.setLeft(min(r.right() - self.minimumWidth(), rect0.left() + d.x()))
            if self._resize_edges & Qt.RightEdge:
                r.setRight(rect0.right() + d.x())
            if self._resize_edges & Qt.TopEdge:
                r.setTop(min(r.bottom() - self.minimumHeight(), rect0.top() + d.y()))
            if self._resize_edges & Qt.BottomEdge:
                r.setBottom(rect0.bottom() + d.y())
            self.setGeometry(r)
            return
        if self._drag_pos is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            return
        edges = self._edges_at(pos)
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edges in (Qt.LeftEdge, Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in (Qt.TopEdge, Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()
        h = self._button_at(pos)
        if h != self._hover:
            self._hover = h
            self.update()
            tips = {"min": "tip_minimize", "max": "tip_restore" if self.is_max() else "tip_maximize",
                    "close": "tip_close", "help": "help"}
            if h:
                QTimer.singleShot(600, lambda k=h: self._hover == k and QToolTip.showText(QCursor.pos(), tr(tips[k]), self))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        pos = ev.position().toPoint()
        self._drag_pos = None
        self._resize_edges = None
        if self._pressed:
            k = self._pressed
            self._pressed = None
            self.update()
            if self._button_at(pos) == k:
                self._caption_action(k)
            return
        super().mouseReleaseEvent(ev)

    def leaveEvent(self, ev):
        if self._hover:
            self._hover = None
            self.update()
        self.unsetCursor()
        super().leaveEvent(ev)

    def enterEvent(self, ev):
        self._end_sys_op()
        super().enterEvent(ev)

    def _caption_action(self, kind):
        if kind == "close":
            self.close()
        elif kind == "min":
            self.showMinimized()
        elif kind == "max":
            self.toggle_maximize()
        elif kind == "help":
            QApplication.setOverrideCursor(Qt.WhatsThisCursor)
            from PySide6.QtWidgets import QWhatsThis
            QApplication.restoreOverrideCursor()
            QWhatsThis.enterWhatsThisMode()

    def _show_system_menu(self, gpos):
        m = QMenu(self)
        maxed = self.is_max()
        a_restore = m.addAction(tr("wm_restore"))
        a_restore.setIcon(_glyph_icon("restore"))
        a_restore.setEnabled(maxed)
        a_move = m.addAction(tr("wm_move"))
        a_move.setEnabled(not maxed)
        a_size = m.addAction(tr("wm_size"))
        a_size.setEnabled(not maxed and self._resizable)
        a_min = m.addAction(tr("wm_minimize"))
        a_min.setIcon(_glyph_icon("min"))
        a_min.setEnabled("min" in self._kinds)
        a_max = m.addAction(tr("wm_maximize"))
        a_max.setIcon(_glyph_icon("max"))
        a_max.setEnabled("max" in self._kinds and not maxed)
        if hasattr(self, "_extend_system_menu"):
            self._extend_system_menu(m)
        m.addSeparator()
        a_close = m.addAction(tr("wm_close"))
        a_close.setIcon(_glyph_icon("close"))
        f = a_close.font()
        f.setBold(True)
        a_close.setFont(f)
        act = m.exec(gpos)
        if act is a_restore:
            self.showNormal()
        elif act is a_min:
            self.showMinimized()
        elif act is a_max:
            self.showMaximized()
        elif act is a_close:
            self.close()
        elif act is a_move:
            self._start_sys_op()
        elif act is a_size:
            self._start_sys_op(Qt.RightEdge | Qt.BottomEdge)

    # --------------------------------------------------------------- zdarzenia
    def changeEvent(self, ev):
        if ev.type() in (QEvent.ActivationChange, QEvent.WindowTitleChange):
            if ev.type() == QEvent.ActivationChange and self.isActiveWindow():
                self._sys_op = False   # kompozytor oddał fokus po zakończeniu przesuwania
            self.update()
        elif ev.type() == QEvent.WindowStateChange:
            self._apply_margins()
        super().changeEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Space and ev.modifiers() & Qt.AltModifier:
            l, t, r, b = current().frame_margins(self.is_max())
            self._show_system_menu(self.mapToGlobal(QPoint(l, t)))
            return
        if ev.key() == Qt.Key_F4 and ev.modifiers() & Qt.AltModifier:
            self.close()
            return
        super().keyPressEvent(ev)


def _glyph_icon(kind):
    from PySide6.QtGui import QPixmap, QColor
    from ..theme.base import draw_glyph
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_glyph(p, QRect(0, 0, 16, 16), kind, QColor("#000000"), 1.6)
    p.end()
    return QIcon(pm)


class HWindow(FrameMixin, QWidget):
    """Okno główne aplikacji z ramką w stylu motywu."""

    closed = Signal()

    def __init__(self, title="", icon_name="app", parent=None, resizable=True, minimizable=True,
                 maximizable=True, help_button=False):
        QWidget.__init__(self, parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self._frame_init(title, icon_name, resizable, minimizable, maximizable, help_button)

    def closeEvent(self, ev):
        super().closeEvent(ev)
        if ev.isAccepted():
            self.closed.emit()


class HDialog(FrameMixin, QDialog):
    """Okno dialogowe z ramką motywu (domyślnie bez minimalizacji i maksymalizacji)."""

    def __init__(self, title="", icon_name="", parent=None, resizable=False, help_button=True):
        QDialog.__init__(self, parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._frame_init(title, icon_name, resizable, False, False, help_button)

    def paintEvent(self, ev):
        FrameMixin.paintEvent(self, ev)
