"""Dymki powiadomień nad obszarem powiadomień (w stylu klasycznego pulpitu) i kolejka, która je wyświetla.

Z dymków korzystają: zasobnik systemowy (sieć, Bluetooth, bateria, aktualizacje) i serwer powiadomień
org.freedesktop.Notifications (powiadomienia programów: notify-send, przeglądarki, komunikatory...).
"""
import html
import re
import time

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..theme import iconcache
from ..common import taskbarlayout

TAIL_H = 18
MAX_BODY_W = 320

# powody zamknięcia (zgodne ze specyfikacją powiadomień)
EXPIRED, DISMISSED, CLOSED_BY_CALL, UNDEFINED = 1, 2, 3, 4


def _pixmap(icon, size=16):
    if icon is None:
        return QPixmap()
    if isinstance(icon, QPixmap):
        return icon.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not icon.isNull() else icon
    if isinstance(icon, QIcon):
        return icon.pixmap(size, size)
    return iconcache.pixmap(icon, size)


_ALLOWED = {"b", "i", "u", "a", "br"}


def safe_markup(text):
    """Treść z body-markup: zostawia <b> <i> <u> <a href> <br>, resztę escapuje. Zwykły tekst — escapuje."""
    if not text:
        return ""
    out, pos = [], 0
    for m in re.finditer(r"<(/?)([a-zA-Z]+)([^>]*)>", text):
        out.append(html.escape(html.unescape(text[pos:m.start()]), quote=False))
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag in _ALLOWED:
            if tag == "a" and not closing:
                h = re.search(r'href\s*=\s*"([^"]*)"|href\s*=\s*\'([^\']*)\'', attrs)
                href = (h.group(1) or h.group(2)) if h else ""
                if href.startswith(("http://", "https://", "mailto:")):
                    out.append(f'<a href="{html.escape(href)}">')
                else:
                    out.append("<a>")
            elif tag == "br":
                out.append("<br>")
            else:
                out.append(f"<{closing}{tag}>")
        pos = m.end()
    out.append(html.escape(html.unescape(text[pos:]), quote=False))
    return "".join(out).replace("\n", "<br>")


class Balloon(QFrame):
    """Pojedynczy dymek: ikona, pogrubiony tytuł, ✕, treść, opcjonalne odnośniki akcji; ogonek wskazuje zasobnik."""

    clicked = Signal()
    action = Signal(str)
    closed = Signal(int)   # powód

    def __init__(self, title, text, icon="info", actions=(), markup=False, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._reason = None
        self.setWindowTitle("horyzont-balloon")
        self.tail_side = "bottom"
        self.tail_point = None
        self.tail_x = None         # współrzędna X ogonka (globalna), ustawiana przez kolejkę
        self.shown_at = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 10, 10 + TAIL_H)
        lay.setSpacing(5)
        row = QHBoxLayout()
        row.setSpacing(6)
        pm = _pixmap(icon, 16)
        if not pm.isNull():
            ic = QLabel()
            ic.setPixmap(pm)
            ic.setFixedSize(16, 16)
            row.addWidget(ic, 0, Qt.AlignTop)
        t = QLabel(html.escape(title or ""))
        t.setTextFormat(Qt.RichText)
        t.setStyleSheet("font-weight: bold; color: #000; background: transparent;")
        t.setWordWrap(True)
        t.setMaximumWidth(MAX_BODY_W - 40)
        row.addWidget(t, 1)
        self.xbtn = QLabel("✕")
        self.xbtn.setToolTip("Zamknij")
        self.xbtn.setFixedSize(16, 16)
        self.xbtn.setAlignment(Qt.AlignCenter)
        self.xbtn.setStyleSheet("color: #4d4d4d; background: transparent; border: 1px solid transparent; border-radius: 2px;")
        self.xbtn.setCursor(Qt.PointingHandCursor)
        self.xbtn.mousePressEvent = lambda e: self.dismiss(DISMISSED)
        self.xbtn.enterEvent = lambda e: self.xbtn.setStyleSheet(
            "color: #fff; background: #d3593a; border: 1px solid #a8361d; border-radius: 2px;")
        self.xbtn.leaveEvent = lambda e: self.xbtn.setStyleSheet(
            "color: #4d4d4d; background: transparent; border: 1px solid transparent; border-radius: 2px;")
        row.addWidget(self.xbtn, 0, Qt.AlignTop)
        lay.addLayout(row)
        if text:
            body = QLabel(safe_markup(text) if markup else html.escape(text).replace("\n", "<br>"))
            body.setTextFormat(Qt.RichText)
            body.setWordWrap(True)
            body.setOpenExternalLinks(False)
            body.linkActivated.connect(self._link)
            body.setStyleSheet("color: #000; background: transparent;")
            fm = QFontMetrics(body.font())
            body.setMinimumWidth(min(MAX_BODY_W, max(140, fm.horizontalAdvance(text.split("\n")[0]) // 2)))
            body.setMaximumWidth(MAX_BODY_W)
            lay.addWidget(body)
        acts = [(k, l) for k, l in actions if k != "default" and l]
        if acts:
            arow = QHBoxLayout()
            arow.setSpacing(12)
            for key, label in acts[:4]:
                a = QLabel(f'<a href="act:{html.escape(key)}" style="color:#0033cc">{html.escape(label)}</a>')
                a.setTextFormat(Qt.RichText)
                a.setStyleSheet("background: transparent;")
                a.linkActivated.connect(self._link)
                arow.addWidget(a)
            arow.addStretch(1)
            lay.addLayout(arow)
        self.adjustSize()
        self.setCursor(Qt.PointingHandCursor)

    def _link(self, href):
        if href.startswith("act:"):
            self.action.emit(href[4:])
            self.dismiss(DISMISSED)
        elif href.startswith(("http://", "https://", "mailto:")):
            from ..common import launcher
            launcher.xdg_open(href)
            self.dismiss(DISMISSED)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        self.dismiss(DISMISSED)

    def dismiss(self, reason=DISMISSED):
        if self._reason is None:
            self._reason = reason
            self.closed.emit(reason)
        self.close()

    def closeEvent(self, e):
        if self._reason is None:
            self._reason = UNDEFINED
            self.closed.emit(UNDEFINED)
        super().closeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = self.tail_side
        r = self.rect().adjusted(1, 1, -2, -2)
        r.adjust(TAIL_H if side == "left" else 0, TAIL_H if side == "top" else 0,
                 -TAIL_H if side == "right" else 0, -TAIL_H if side == "bottom" else 0)
        path = QPainterPath()
        path.addRoundedRect(r, 7, 7)
        if self.tail_point is not None:
            pt = self.mapFromGlobal(self.tail_point)
            tail = QPainterPath()
            if side in ("bottom", "top"):
                tx = max(r.left()+12, min(r.right()-12, pt.x()))
                by = r.bottom()-2 if side == "bottom" else r.top()+2
                tip = self.height()-1 if side == "bottom" else 1
                tail.moveTo(tx-10, by); tail.lineTo(tx, tip); tail.lineTo(tx+10, by)
            else:
                ty = max(r.top()+12, min(r.bottom()-12, pt.y()))
                bx = r.left()+2 if side == "left" else r.right()-2
                tip = 1 if side == "left" else self.width()-1
                tail.moveTo(bx, ty-10); tail.lineTo(tip, ty); tail.lineTo(bx, ty+10)
            tail.closeSubpath()
            path = path.united(tail)
        p.setBrush(QColor("#ffffe1"))
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawPath(path)


class BalloonQueue(QObject):
    """Wyświetla dymki po jednym (jak w klasycznym zasobniku). Nowy dymek zastępuje bieżący, gdy ten był
    już widoczny przez kilka sekund; pilne zostają do kliknięcia."""

    MIN_VISIBLE = 4.0

    def __init__(self, taskbar):
        super().__init__(taskbar)
        self.bar = taskbar
        self.current = None      # (wpis, Balloon)
        self.queue = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._expire)
        self._swap = QTimer(self)
        self._swap.setSingleShot(True)
        self._swap.timeout.connect(self._maybe_next)
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(150)
        self._position_timer.timeout.connect(self.reposition)
        self.enabled = True

    # wpis: dict(id, title, text, icon, actions, markup, timeout_ms (None = bez limitu), anchor (funkcja -> x),
    #            on_click, on_action(key), on_closed(reason), sound=True)
    def show(self, entry):
        if not self.enabled and not entry.get("force"):
            cb = entry.get("on_closed")
            if cb:
                QTimer.singleShot(0, lambda: cb(EXPIRED))
            return
        nid = entry.get("id")
        if nid is not None:
            if self.current and self.current[0].get("id") == nid:
                self._close_current(None)   # podmiana treści bez sygnału zamknięcia
                self._display(entry)
                return
            for i, q in enumerate(self.queue):
                if q.get("id") == nid:
                    self.queue[i] = entry
                    return
        self.queue.append(entry)
        self._maybe_next()

    def close_id(self, nid, reason=CLOSED_BY_CALL):
        if self.current and self.current[0].get("id") == nid:
            self._close_current(reason)
            QTimer.singleShot(250, self._maybe_next)
            return True
        for q in list(self.queue):
            if q.get("id") == nid:
                self.queue.remove(q)
                cb = q.get("on_closed")
                if cb:
                    cb(reason)
                return True
        return False

    def _maybe_next(self):
        if not self.queue:
            return
        if self.current:
            entry, b = self.current
            if entry.get("timeout_ms") is None and entry.get("urgent"):
                return
            left = self.MIN_VISIBLE - (time.monotonic() - b.shown_at)
            if left > 0:
                self._swap.start(int(left * 1000) + 50)
                return
            self._close_current(EXPIRED)
        self._display(self.queue.pop(0))

    def _display(self, entry):
        b = Balloon(entry.get("title", ""), entry.get("text", ""), entry.get("icon", "info"),
                    entry.get("actions", ()), entry.get("markup", False), parent=self.bar)
        b.clicked.connect(lambda: entry.get("on_click") and entry["on_click"]())
        b.action.connect(lambda k: entry.get("on_action") and entry["on_action"](k))
        b.closed.connect(lambda reason, e=entry, bb=b: self._closed(e, bb, reason))
        # Na Waylandzie popup musi mieć pasek jako rodzica powierzchni, nawet
        # gdy ostatnio aktywne było np. okno regulacji głośności.
        self._place(b, entry)
        b.winId()
        if b.windowHandle() and self.bar.windowHandle():
            b.windowHandle().setTransientParent(self.bar.windowHandle())
        b.shown_at = time.monotonic()
        b.show()
        b.raise_()
        self.current = (entry, b)
        self._position_timer.start()
        QTimer.singleShot(0, self.reposition)
        if entry.get("sound", True):
            try:
                from ..common import sounds
                if entry.get("sound_file"):
                    sounds.play_file(entry["sound_file"])
                else:
                    sounds.play("balloon")
            except Exception:
                pass
        t = entry.get("timeout_ms")
        if t is not None:
            self._timer.start(max(1500, int(t)))
        else:
            self._timer.stop()

    def _place(self, b, entry):
        bar = self.bar
        g = bar.mapToGlobal(QPoint(0, 0))
        anchor = None
        try:
            anchor = entry.get("anchor") and entry["anchor"]()
        except Exception:
            anchor = None
        side = taskbarlayout.edge()
        b.tail_side = side
        b.layout().setContentsMargins(12+(TAIL_H if side == "left" else 0), 9+(TAIL_H if side == "top" else 0),
                                     10+(TAIL_H if side == "right" else 0), 10+(TAIL_H if side == "bottom" else 0))
        b.adjustSize()
        if anchor is not None and not isinstance(anchor, QPoint):
            anchor = QPoint(int(anchor), g.y())
        b.tail_point = anchor
        b.tail_x = anchor.x() if anchor is not None else None
        tray = getattr(bar, "tray", None)
        center = anchor or (tray.mapToGlobal(tray.rect().center()) if tray else g)
        screen = (bar.screen() or QApplication.primaryScreen()).geometry()
        if side in ("bottom", "top"):
            x = center.x()-b.width()//2
            y = g.y()-b.height()+6 if side == "bottom" else g.y()+bar.height()-6
        else:
            x = g.x()+bar.width()-6 if side == "left" else g.x()-b.width()+6
            y = center.y()-b.height()//2
        x = max(screen.left()+4, min(screen.right()+1-b.width()-4, x))
        y = max(screen.top()+4, min(screen.bottom()+1-b.height()-4, y))
        if b.pos() != QPoint(x, y):
            b.move(x, y)
        b.update()

    def reposition(self):
        if self.current:
            entry, balloon = self.current
            self._place(balloon, entry)

    def _expire(self):
        if self.current:
            # nie zamykamy dymku, nad którym jest wskaźnik myszy
            entry, b = self.current
            try:
                if b.geometry().contains(QCursor.pos()):
                    self._timer.start(2000)
                    return
            except RuntimeError:
                pass
            self._close_current(EXPIRED)
        QTimer.singleShot(250, self._maybe_next)

    def _close_current(self, reason):
        if not self.current:
            return
        entry, b = self.current
        self.current = None
        self._position_timer.stop()
        self._timer.stop()
        try:
            b.closed.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            b.close()
        except RuntimeError:
            pass
        if reason is not None and entry.get("on_closed"):
            entry["on_closed"](reason)

    def _closed(self, entry, b, reason):
        if self.current and self.current[1] is b:
            self.current = None
            self._position_timer.stop()
            self._timer.stop()
        if entry.get("on_closed"):
            entry["on_closed"](reason)
        QTimer.singleShot(250, self._maybe_next)
