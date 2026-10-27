"""Wygaszacze ekranu: gwiezdne pole, wstęgi, logo, bąbelki, pusty."""
import math
import random
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from .. import config

SAVERS = ["starfield", "ribbons", "logo", "bubbles", "blank"]
LABELS = {"starfield": "ss_starfield", "ribbons": "ss_mystify", "logo": "ss_logo", "bubbles": "ss_bubbles",
          "blank": "ss_blank"}


class SaverState:
    """Stan animacji niezależny od rozmiaru — ten sam kod rysuje podgląd i pełny ekran."""

    def __init__(self, kind, seed=None):
        self.kind = kind
        self.rnd = random.Random(seed)
        self.t0 = time.monotonic()
        self.stars = [[self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1), self.rnd.uniform(0.05, 1)] for _ in range(260)]
        self.ribbons = []
        for k in range(2):
            pts = [[self.rnd.random(), self.rnd.random(), self.rnd.uniform(-0.01, 0.01), self.rnd.uniform(-0.01, 0.01)]
                   for _ in range(4)]
            self.ribbons.append({"pts": pts, "hist": [], "hue": self.rnd.random()})
        self.logo = [self.rnd.random() * 0.6, self.rnd.random() * 0.6, 0.004, 0.003]
        self.bubbles = [[self.rnd.random(), self.rnd.random(), self.rnd.uniform(0.04, 0.12),
                         self.rnd.uniform(-0.004, 0.004), self.rnd.uniform(-0.004, 0.004), self.rnd.random()] for _ in range(9)]

    def step(self):
        k = self.kind
        if k == "starfield":
            for s in self.stars:
                s[2] -= 0.012
                if s[2] <= 0.02:
                    s[0], s[1], s[2] = self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1), 1.0
        elif k == "ribbons":
            for rb in self.ribbons:
                for pt in rb["pts"]:
                    pt[0] += pt[2]
                    pt[1] += pt[3]
                    if not 0 <= pt[0] <= 1:
                        pt[2] = -pt[2]
                        pt[0] = min(1, max(0, pt[0]))
                    if not 0 <= pt[1] <= 1:
                        pt[3] = -pt[3]
                        pt[1] = min(1, max(0, pt[1]))
                rb["hist"].append([tuple(p[:2]) for p in rb["pts"]])
                if len(rb["hist"]) > 14:
                    rb["hist"].pop(0)
                rb["hue"] = (rb["hue"] + 0.002) % 1.0
        elif k == "logo":
            L = self.logo
            L[0] += L[2]
            L[1] += L[3]
            if not 0 <= L[0] <= 0.62:
                L[2] = -L[2]
            if not 0 <= L[1] <= 0.78:
                L[3] = -L[3]
        elif k == "bubbles":
            for b in self.bubbles:
                b[0] += b[3]
                b[1] += b[4]
                if not b[2] <= b[0] <= 1 - b[2]:
                    b[3] = -b[3]
                if not b[2] <= b[1] <= 1 - b[2]:
                    b[4] = -b[4]

    def paint(self, p, rect):
        p.fillRect(rect, QColor("#000000"))
        W, H = rect.width(), rect.height()
        ox, oy = rect.left(), rect.top()
        p.setRenderHint(QPainter.Antialiasing, True)
        k = self.kind
        if k == "starfield":
            cx, cy = ox + W / 2, oy + H / 2
            for x, y, z in self.stars:
                sx, sy = cx + x / z * W / 2, cy + y / z * H / 2
                if ox <= sx <= ox + W and oy <= sy <= oy + H:
                    r = max(0.6, (1 - z) * 2.6 * W / 640)
                    c = int(255 * min(1, (1 - z) * 1.4))
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(c, c, c))
                    p.drawEllipse(QPointF(sx, sy), r, r)
        elif k == "ribbons":
            for rb in self.ribbons:
                for i, pts in enumerate(rb["hist"]):
                    a = int(255 * (i + 1) / len(rb["hist"]))
                    c = QColor.fromHsvF(rb["hue"], 0.8, 1.0)
                    c.setAlpha(a)
                    p.setPen(QPen(c, max(1.0, W / 500)))
                    q = [QPointF(ox + x * W, oy + y * H) for x, y in pts]
                    for j in range(len(q)):
                        p.drawLine(q[j], q[(j + 1) % len(q)])
        elif k == "logo":
            from ..theme import iconcache
            x, y = ox + self.logo[0] * W, oy + self.logo[1] * H
            s = int(min(W, H) * 0.16)
            p.drawPixmap(int(x), int(y), iconcache.pixmap("logo", max(16, s)))
            f = QFont("DejaVu Sans")
            f.setPixelSize(max(6, int(s * 0.42)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(x + s * 1.05, y, W, s), Qt.AlignVCenter | Qt.AlignLeft, "Horyzont")
        elif k == "bubbles":
            for bx, by, br, _, _, hue in self.bubbles:
                cx, cy, r = ox + bx * W, oy + by * H, br * min(W, H)
                g = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.35), r * 1.2)
                c = QColor.fromHsvF(hue, 0.45, 1.0)
                g.setColorAt(0, QColor(255, 255, 255, 230))
                g.setColorAt(0.3, QColor(c.red(), c.green(), c.blue(), 120))
                g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 30))
                p.setBrush(g)
                p.setPen(QPen(QColor(255, 255, 255, 120), 1))
                p.drawEllipse(QPointF(cx, cy), r, r)


class SaverWidget(QWidget):
    def __init__(self, kind):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("horyzont-screensaver")
        self.state = SaverState(kind)
        self.setCursor(Qt.BlankCursor)
        self.setMouseTracking(True)
        self._start_pos = None
        self._started = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def _tick(self):
        self.state.step()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        self.state.paint(p, self.rect())

    def _quit(self):
        if time.monotonic() - self._started > 0.8:
            QApplication.quit()

    def mouseMoveEvent(self, e):
        pos = e.globalPosition().toPoint()
        if self._start_pos is None:
            self._start_pos = pos
        elif (pos - self._start_pos).manhattanLength() > 12:
            self._quit()

    def mousePressEvent(self, e):
        self._quit()

    def keyPressEvent(self, e):
        self._quit()


def main(args):
    from ..common.app import make_app
    app = make_app("screensaver")
    kind = args[0] if args else config.get("screensaver", "starfield")
    if kind not in SAVERS:
        kind = "starfield"
    w = SaverWidget(kind)
    w.showFullScreen()
    rc = app.exec()
    if config.get("screensaver_lock", False) and "--preview" not in args:
        from ..common import sysctl
        sysctl.lock_screen()
    return rc
