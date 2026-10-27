"""Saper — klasyczna gra logiczna (grafika oryginalna, rysowana w kodzie)."""
import random
import sys
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygon, QPolygonF
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenuBar, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ... import config
from ...common.appkit import T, act, help_menu, run_app
from ...common.window import HDialog, HWindow
from . import play_tone

LEVELS = {"beginner": (9, 9, 10), "intermediate": (16, 16, 40), "expert": (30, 16, 99)}
NUM_COLORS = ["", "#0000ff", "#008000", "#ff0000", "#000080", "#800000", "#008080", "#000000", "#808080"]
GRAY, LIGHT, DARK = QColor("#c0c0c0"), QColor("#ffffff"), QColor("#808080")
HIDDEN, OPEN, FLAG, QUESTION = 0, 1, 2, 3


def bevel(p, r, raised=True, width=2):
    tl, br = (LIGHT, DARK) if raised else (DARK, LIGHT)
    for i in range(width):
        p.setPen(tl)
        p.drawLine(r.left() + i, r.top() + i, r.right() - i, r.top() + i)
        p.drawLine(r.left() + i, r.top() + i, r.left() + i, r.bottom() - i)
        p.setPen(br)
        p.drawLine(r.left() + i, r.bottom() - i, r.right() - i, r.bottom() - i)
        p.drawLine(r.right() - i, r.top() + i, r.right() - i, r.bottom() - i)


SEGMENTS = {  # siedmiosegmentowe cyfry: a b c d e f g
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
    "8": "abcdefg", "9": "abcdfg", "-": "g",
}


def draw_led(p, r, value):
    p.fillRect(r, QColor("#000000"))
    s = f"{value:03d}" if value >= 0 else "-" + f"{min(99, -value):02d}"
    s = s[-3:]
    dw = r.width() / 3
    for i, ch in enumerate(s):
        x0 = r.left() + i * dw + 2
        y0 = r.top() + 2
        w = dw - 4
        h = r.height() - 4
        t = max(2, w / 5)
        on = SEGMENTS.get(ch, "")
        segs = {
            "a": [(x0 + 1, y0), (x0 + w - 1, y0), (x0 + w - t - 1, y0 + t), (x0 + t + 1, y0 + t)],
            "d": [(x0 + 1, y0 + h), (x0 + w - 1, y0 + h), (x0 + w - t - 1, y0 + h - t), (x0 + t + 1, y0 + h - t)],
            "f": [(x0, y0 + 1), (x0 + t, y0 + t + 1), (x0 + t, y0 + h / 2 - t / 2 - 1), (x0, y0 + h / 2 - 1)],
            "b": [(x0 + w, y0 + 1), (x0 + w - t, y0 + t + 1), (x0 + w - t, y0 + h / 2 - t / 2 - 1), (x0 + w, y0 + h / 2 - 1)],
            "e": [(x0, y0 + h / 2 + 1), (x0 + t, y0 + h / 2 + t / 2 + 1), (x0 + t, y0 + h - t - 1), (x0, y0 + h - 1)],
            "c": [(x0 + w, y0 + h / 2 + 1), (x0 + w - t, y0 + h / 2 + t / 2 + 1), (x0 + w - t, y0 + h - t - 1), (x0 + w, y0 + h - 1)],
            "g": [(x0 + 1, y0 + h / 2), (x0 + t, y0 + h / 2 - t / 2), (x0 + w - t, y0 + h / 2 - t / 2), (x0 + w - 1, y0 + h / 2),
                  (x0 + w - t, y0 + h / 2 + t / 2), (x0 + t, y0 + h / 2 + t / 2)],
        }
        p.setPen(Qt.NoPen)
        for k, pts in segs.items():
            p.setBrush(QColor("#ff0000") if k in on else QColor("#400000"))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


class Board(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMouseTracking(False)
        self.cell = 16
        self.pressed = set()
        self._buttons = Qt.NoButton

    def sizeHint(self):
        g = self.win.game
        return QSize(g.w * self.cell, g.h * self.cell)

    def _cell_at(self, pos):
        x, y = int(pos.x() // self.cell), int(pos.y() // self.cell)
        g = self.win.game
        if 0 <= x < g.w and 0 <= y < g.h:
            return x, y
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        g = self.win.game
        c = self.cell
        f = QFont("Arial")
        f.setBold(True)
        f.setPixelSize(int(c * 0.8))
        p.setFont(f)
        color = self.win.color
        for y in range(g.h):
            for x in range(g.w):
                r = QRect(x * c, y * c, c, c)
                st = g.state[y][x]
                if st == OPEN or (st in (HIDDEN, QUESTION) and (x, y) in self.pressed):
                    p.fillRect(r, GRAY)
                    p.setPen(DARK)
                    p.drawLine(r.topLeft(), r.topRight())
                    p.drawLine(r.topLeft(), r.bottomLeft())
                    if st == OPEN:
                        if g.mines[y][x]:
                            if (x, y) == g.exploded:
                                p.fillRect(r.adjusted(1, 1, 0, 0), QColor("#ff0000"))
                            self._mine(p, r)
                        else:
                            n = g.count[y][x]
                            if n:
                                p.setPen(QColor(NUM_COLORS[n]) if color else QColor("#000000"))
                                p.drawText(r.adjusted(1, 1, 0, 0), Qt.AlignCenter, str(n))
                    elif st == QUESTION:
                        p.setPen(QColor("#000000"))
                        p.drawText(r.adjusted(1, 1, 0, 0), Qt.AlignCenter, "?")
                    continue
                p.fillRect(r, GRAY)
                bevel(p, r, True, 2 if c < 24 else 3)
                if st == FLAG:
                    if g.over and not g.mines[y][x]:
                        self._mine(p, r)
                        p.setPen(QPen(QColor("#ff0000"), 2))
                        p.drawLine(r.left() + 3, r.top() + 3, r.right() - 3, r.bottom() - 3)
                        p.drawLine(r.right() - 3, r.top() + 3, r.left() + 3, r.bottom() - 3)
                    else:
                        self._flag(p, r, color)
                elif st == QUESTION:
                    p.setPen(QColor("#000000"))
                    p.drawText(r, Qt.AlignCenter, "?")
                elif g.over and g.mines[y][x] and not g.won:
                    p.fillRect(r, GRAY)
                    p.setPen(DARK)
                    p.drawLine(r.topLeft(), r.topRight())
                    p.drawLine(r.topLeft(), r.bottomLeft())
                    self._mine(p, r)

    def _mine(self, p, r):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = r.center().x() + 1, r.center().y() + 1
        rad = r.width() * 0.28
        p.setPen(QPen(QColor("#000000"), max(1, r.width() // 12)))
        p.drawLine(QPointF(cx - rad * 1.45, cy), QPointF(cx + rad * 1.45, cy))
        p.drawLine(QPointF(cx, cy - rad * 1.45), QPointF(cx, cy + rad * 1.45))
        p.drawLine(QPointF(cx - rad, cy - rad), QPointF(cx + rad, cy + rad))
        p.drawLine(QPointF(cx - rad, cy + rad), QPointF(cx + rad, cy - rad))
        p.setBrush(QColor("#000000"))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx - rad * 0.35, cy - rad * 0.35), rad * 0.25, rad * 0.25)
        p.restore()

    def _flag(self, p, r, color):
        c = r.width()
        x, y = r.left(), r.top()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff0000") if color else QColor("#000000"))
        p.drawPolygon(QPolygon([QPoint(x + c * 9 // 16, y + c * 3 // 16), QPoint(x + c * 9 // 16, y + c * 8 // 16),
                                QPoint(x + c * 4 // 16, y + c * 11 // 32)]))
        p.setBrush(QColor("#000000"))
        p.drawRect(x + c * 8 // 16, y + c * 8 // 16, max(1, c // 16), c * 3 // 16)
        p.drawRect(x + c * 5 // 16, y + c * 11 // 16, c * 6 // 16, max(1, c // 16))
        p.drawRect(x + c * 4 // 16, y + c * 12 // 16, c * 8 // 16, max(2, c * 2 // 16))

    def _update_pressed(self, pos, buttons):
        cell = self._cell_at(pos)
        g = self.win.game
        self.pressed = set()
        if cell and not g.over:
            both = (buttons & Qt.LeftButton and buttons & Qt.RightButton) or buttons & Qt.MiddleButton
            cells = g.neighbors(*cell) + [cell] if both else [cell]
            self.pressed = {c for c in cells if g.state[c[1]][c[0]] in (HIDDEN, QUESTION)}
        self.win.face_state = "wow" if self.pressed or (buttons & Qt.LeftButton) else "smile"
        self.update()
        self.win.header.update()

    def mousePressEvent(self, e):
        if self.win.game.over:
            return
        self._buttons = e.buttons()
        cell = self._cell_at(e.position().toPoint())
        if e.button() == Qt.RightButton and not (e.buttons() & Qt.LeftButton) and cell:
            self.win.game.cycle_mark(*cell, self.win.marks)
            self.win.after_move()
            self._chord_armed = False
            return
        self._update_pressed(e.position().toPoint(), e.buttons())

    def mouseMoveEvent(self, e):
        if e.buttons() and not self.win.game.over:
            self._update_pressed(e.position().toPoint(), e.buttons() | self._buttons)

    def mouseReleaseEvent(self, e):
        g = self.win.game
        cell = self._cell_at(e.position().toPoint())
        was = self._buttons
        both = (was & Qt.LeftButton and was & Qt.RightButton) or e.button() == Qt.MiddleButton
        self.pressed = set()
        self._buttons = e.buttons()
        if not g.over and cell:
            if both:
                g.chord(*cell)
                self._buttons = Qt.NoButton
            elif e.button() == Qt.LeftButton and not (e.buttons() & Qt.RightButton):
                g.reveal(*cell)
        self.win.face_state = "smile"
        self.win.after_move()


class Header(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(37)
        self._face_down = False

    def face_rect(self):
        return QRect(self.width() // 2 - 13, 6, 26, 26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), GRAY)
        bevel(p, self.rect(), False, 2)
        g = self.win.game
        draw_led(p, QRect(7, 7, 41, 24), g.mines_left())
        draw_led(p, QRect(self.width() - 48, 7, 41, 24), min(999, g.elapsed()))
        r = self.face_rect()
        p.fillRect(r, GRAY)
        p.setPen(DARK)
        p.drawRect(r.adjusted(0, 0, -1, -1))
        bevel(p, r.adjusted(1, 1, -1, -1), not self._face_down, 2)
        self._face(p, r.adjusted(4 + (1 if self._face_down else 0), 4 + (1 if self._face_down else 0),
                                 -4 + (1 if self._face_down else 0), -4 + (1 if self._face_down else 0)))

    def _face(self, p, r):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        st = "dead" if self.win.game.over and not self.win.game.won else "cool" if self.win.game.won else self.win.face_state
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QColor("#ffff00"))
        p.drawEllipse(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5))
        cx, cy = r.center().x() + 0.5, r.center().y() + 0.5
        p.setBrush(QColor("#000000"))
        if st == "dead":
            p.setPen(QPen(QColor("#000000"), 1.3))
            for ex in (cx - 4, cx + 4):
                p.drawLine(QPointF(ex - 2, cy - 5), QPointF(ex + 2, cy - 1))
                p.drawLine(QPointF(ex + 2, cy - 5), QPointF(ex - 2, cy - 1))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - 5, cy + 3, 10, 6), 0, 180 * 16)
        elif st == "cool":
            p.drawRect(QRectF(cx - 7, cy - 4, 14, 1.5))
            p.drawEllipse(QRectF(cx - 7, cy - 4, 6, 4))
            p.drawEllipse(QRectF(cx + 1, cy - 4, 6, 4))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - 5, cy - 1, 10, 7), 200 * 16, 140 * 16)
        elif st == "wow":
            p.drawEllipse(QPointF(cx - 3.5, cy - 3), 1.4, 1.6)
            p.drawEllipse(QPointF(cx + 3.5, cy - 3), 1.4, 1.6)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy + 4), 2.2, 2.2)
        else:
            p.drawEllipse(QPointF(cx - 3.5, cy - 3), 1.2, 1.2)
            p.drawEllipse(QPointF(cx + 3.5, cy - 3), 1.2, 1.2)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - 5, cy - 2, 10, 8), 200 * 16, 140 * 16)
        p.restore()

    def mousePressEvent(self, e):
        if self.face_rect().contains(e.position().toPoint()):
            self._face_down = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._face_down:
            self._face_down = False
            self.update()
            if self.face_rect().contains(e.position().toPoint()):
                self.win.new_game()


class Game:
    def __init__(self, w, h, n):
        self.w, self.h, self.n = w, h, min(n, w * h - 9)
        self.mines = [[False] * w for _ in range(h)]
        self.count = [[0] * w for _ in range(h)]
        self.state = [[HIDDEN] * w for _ in range(h)]
        self.started = None
        self.finished_at = None
        self.over = False
        self.won = False
        self.exploded = None
        self.placed = False

    def neighbors(self, x, y):
        return [(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dx or dy) and 0 <= x + dx < self.w and 0 <= y + dy < self.h]

    def _place(self, sx, sy):
        safe = {(sx, sy)} | set(self.neighbors(sx, sy))
        cells = [(x, y) for y in range(self.h) for x in range(self.w) if (x, y) not in safe]
        if len(cells) < self.n:
            cells = [(x, y) for y in range(self.h) for x in range(self.w) if (x, y) != (sx, sy)]
        for x, y in random.sample(cells, self.n):
            self.mines[y][x] = True
        for y in range(self.h):
            for x in range(self.w):
                self.count[y][x] = sum(self.mines[ny][nx] for nx, ny in self.neighbors(x, y))
        self.placed = True

    def elapsed(self):
        if self.started is None:
            return 0
        end = self.finished_at or time.monotonic()
        return int(end - self.started) + 1

    def mines_left(self):
        return self.n - sum(row.count(FLAG) for row in self.state)

    def reveal(self, x, y):
        if self.over or self.state[y][x] in (OPEN, FLAG):
            return
        if not self.placed:
            self._place(x, y)
            self.started = time.monotonic()
        if self.mines[y][x]:
            self.state[y][x] = OPEN
            self.exploded = (x, y)
            self.over = True
            self.finished_at = time.monotonic()
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if self.state[cy][cx] == OPEN:
                continue
            self.state[cy][cx] = OPEN
            if self.count[cy][cx] == 0:
                for nx, ny in self.neighbors(cx, cy):
                    if self.state[ny][nx] in (HIDDEN, QUESTION) and not self.mines[ny][nx]:
                        stack.append((nx, ny))
        self._check_win()

    def chord(self, x, y):
        if self.state[y][x] != OPEN or not self.count[y][x]:
            return
        flags = sum(self.state[ny][nx] == FLAG for nx, ny in self.neighbors(x, y))
        if flags == self.count[y][x]:
            for nx, ny in self.neighbors(x, y):
                if self.state[ny][nx] in (HIDDEN, QUESTION):
                    self.reveal(nx, ny)

    def cycle_mark(self, x, y, marks):
        st = self.state[y][x]
        if st == HIDDEN:
            self.state[y][x] = FLAG
        elif st == FLAG:
            self.state[y][x] = QUESTION if marks else HIDDEN
        elif st == QUESTION:
            self.state[y][x] = HIDDEN

    def _check_win(self):
        hidden = sum(1 for y in range(self.h) for x in range(self.w) if self.state[y][x] != OPEN)
        if hidden == self.n and not self.over:
            self.over = True
            self.won = True
            self.finished_at = time.monotonic()
            for y in range(self.h):
                for x in range(self.w):
                    if self.mines[y][x]:
                        self.state[y][x] = FLAG


class CustomDialog(HDialog):
    def __init__(self, win, w, h, n):
        super().__init__(T("Pole niestandardowe", "Custom Field"), "mines", win)
        lay = QHBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        g = QGridLayout()
        self.h = QSpinBox()
        self.h.setRange(9, 24)
        self.h.setValue(h)
        self.w = QSpinBox()
        self.w.setRange(9, 30)
        self.w.setValue(w)
        self.n = QSpinBox()
        self.n.setRange(10, 667)
        self.n.setValue(n)
        for i, (label, sb) in enumerate(((T("&Wysokość:", "&Height:"), self.h), (T("&Szerokość:", "&Width:"), self.w),
                                         (T("&Miny:", "&Mines:"), self.n))):
            lab = QLabel(label)
            lab.setBuddy(sb)
            g.addWidget(lab, i, 0)
            g.addWidget(sb, i, 1)
        lay.addLayout(g)
        col = QVBoxLayout()
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        col.addWidget(ok)
        col.addWidget(ca)
        col.addStretch(1)
        lay.addLayout(col)


class MinesWindow(HWindow):
    def __init__(self):
        super().__init__(T("Saper", "Minesweeper"), "mines", resizable=False, maximizable=False)
        self.level = config.get("mines_level", "beginner")
        self.custom = config.get("mines_custom", [9, 9, 10])
        self.marks = config.get("mines_marks", True)
        self.color = config.get("mines_color", True)
        self.sound = config.get("mines_sound", False)
        self.big = config.get("mines_big", False)
        self.face_state = "smile"
        self.game = Game(*self._dims())
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.frame = QWidget()
        self.frame.setAutoFillBackground(True)
        pal = self.frame.palette()
        pal.setColor(self.frame.backgroundRole(), GRAY)
        self.frame.setPalette(pal)
        self.frame.paintEvent = self._paint_frame
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(9, 9, 9, 9)
        fl.setSpacing(6)
        self.header = Header(self)
        fl.addWidget(self.header)
        self.board_holder = QWidget()
        bl = QVBoxLayout(self.board_holder)
        bl.setContentsMargins(3, 3, 3, 3)
        self.board_holder.paintEvent = self._paint_board_holder
        self.board = Board(self)
        bl.addWidget(self.board)
        fl.addWidget(self.board_holder)
        lay.addWidget(self.frame)
        self._build_menu()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)
        self._last_second = 0
        self.new_game()

    def _paint_frame(self, e):
        p = QPainter(self.frame)
        p.fillRect(self.frame.rect(), GRAY)
        bevel(p, self.frame.rect(), True, 3)

    def _paint_board_holder(self, e):
        p = QPainter(self.board_holder)
        bevel(p, self.board_holder.rect(), False, 3)

    def _dims(self):
        if self.level == "custom":
            return tuple(self.custom)
        return LEVELS.get(self.level, LEVELS["beginner"])

    def _build_menu(self):
        m = self.menubar.addMenu(T("&Gra", "&Game"))
        act(m, T("&Nowa", "&New"), self.new_game, "F2")
        m.addSeparator()
        self.level_actions = {}
        for key, label in (("beginner", T("&Początkujący", "&Beginner")), ("intermediate", T("&Zaawansowany", "&Intermediate")),
                           ("expert", T("&Ekspert", "&Expert")), ("custom", T("&Niestandardowy…", "&Custom..."))):
            a = act(m, label, lambda k=key: self.set_level(k))
            a.setCheckable(True)
            self.level_actions[key] = a
        m.addSeparator()
        act(m, T("&Znaki zapytania (?)", "&Marks (?)"), lambda on: self._opt("marks", on), checkable=True, checked=self.marks)
        act(m, T("&Kolor", "Co&lor"), lambda on: self._opt("color", on), checkable=True, checked=self.color)
        act(m, T("&Dźwięk", "&Sound"), lambda on: self._opt("sound", on), checkable=True, checked=self.sound)
        act(m, T("&Duże pola", "&Large squares"), lambda on: self._opt("big", on), checkable=True, checked=self.big)
        m.addSeparator()
        act(m, T("Naj&lepsze wyniki…", "Best &Times..."), self.best_times)
        m.addSeparator()
        act(m, T("Za&kończ", "E&xit"), self.close)
        help_menu(self.menubar, self, T("Saper", "Minesweeper"), "mines", "games")

    def _opt(self, name, on):
        setattr(self, name, on)
        config.set("mines_" + name, on)
        if name == "big":
            self._resize()
        self.board.update()

    def set_level(self, key):
        if key == "custom":
            d = CustomDialog(self, *self._dims())
            if d.exec() != QDialog.Accepted:
                for k, a in self.level_actions.items():
                    a.setChecked(k == self.level)
                return
            w, h = d.w.value(), d.h.value()
            self.custom = [w, h, max(10, min(d.n.value(), (w - 1) * (h - 1)))]
            config.set("mines_custom", self.custom)
        self.level = key
        config.set("mines_level", key)
        self.new_game()

    def new_game(self):
        self.game = Game(*self._dims())
        self.face_state = "smile"
        self._last_second = 0
        for k, a in self.level_actions.items():
            a.setChecked(k == self.level)
        self._resize()

    def _resize(self):
        self.board.cell = 24 if self.big else 16
        g = self.game
        self.board.setFixedSize(g.w * self.board.cell, g.h * self.board.cell)
        self.board.update()
        self.header.update()
        self.body().adjustSize()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def _tick(self):
        g = self.game
        if g.started and not g.over:
            s = g.elapsed()
            if s != self._last_second:
                self._last_second = s
                self.header.update()
                if self.sound and s <= 999:
                    play_tone("tick", [(1800, 0.025, "square")])

    def after_move(self):
        g = self.game
        self.board.update()
        self.header.update()
        if g.over:
            if g.won:
                if self.sound:
                    play_tone("win", [(523, 0.12, "sine"), (659, 0.12, "sine"), (784, 0.25, "sine")])
                self._record()
            elif self.sound:
                play_tone("boom", [(80, 0.5, "noise")])

    def _record(self):
        if self.level not in LEVELS:
            return
        t = self.game.elapsed()
        best = config.get("mines_best", {})
        cur = best.get(self.level)
        if cur and cur[0] <= t:
            return
        names = {"beginner": T("początkującego", "beginner"), "intermediate": T("zaawansowanego", "intermediate"),
                 "expert": T("eksperta", "expert")}
        d = HDialog(T("Saper", "Minesweeper"), "mines", self, help_button=False)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(14, 12, 14, 12)
        lab = QLabel(T(f"Masz najszybszy czas dla poziomu {names[self.level]}.\nWpisz swoje imię.",
                       f"You have the fastest time for {names[self.level]} level.\nPlease type your name."))
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
        import getpass
        name = QLineEdit(config.get("mines_last_name", "") or getpass.getuser())
        name.selectAll()
        lay.addWidget(name)
        ok = QPushButton(T("OK", "OK"))
        ok.clicked.connect(d.accept)
        lay.addWidget(ok, 0, Qt.AlignCenter)
        d.exec()
        nm = name.text().strip() or T("Anonim", "Anonymous")
        config.set("mines_last_name", nm)
        best[self.level] = [t, nm]
        config.set("mines_best", best)
        self.best_times()

    def best_times(self):
        best = config.get("mines_best", {})
        d = HDialog(T("Najszybsi saperzy", "Fastest Mine Sweepers"), "mines", self, help_button=False)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(14, 12, 14, 12)
        g = QGridLayout()
        for i, (k, label) in enumerate((("beginner", T("Początkujący:", "Beginner:")),
                                        ("intermediate", T("Zaawansowany:", "Intermediate:")),
                                        ("expert", T("Ekspert:", "Expert:")))):
            v = best.get(k) or [999, T("Anonim", "Anonymous")]
            g.addWidget(QLabel(label), i, 0)
            g.addWidget(QLabel(T(f"{v[0]} s", f"{v[0]} seconds")), i, 1)
            g.addWidget(QLabel(v[1]), i, 2)
        lay.addLayout(g)
        row = QHBoxLayout()
        reset = QPushButton(T("&Resetuj wyniki", "&Reset Scores"))
        reset.clicked.connect(lambda: (config.set("mines_best", {}), d.accept(), self.best_times()))
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(d.accept)
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)
        d.exec()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F2:
            self.new_game()
        else:
            super().keyPressEvent(e)


class MinesApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = MinesWindow()
            self.win.move(160, 100)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    return run_app("mines", MinesApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
