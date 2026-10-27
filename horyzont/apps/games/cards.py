"""Karty do gry rysowane w kodzie (oryginalny wzór) — używane przez Pasjans."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)

CARD_W, CARD_H = 71, 96
SUITS = "SHDC"            # pik, kier, karo, trefl
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RANK_PL = {"J": "W", "Q": "D", "K": "K", "A": "A"}   # walet, dama, król, as
RED = QColor("#d40000")
BLACK = QColor("#000000")

BACKS = [
    ("lattice", "Kratka", "Lattice"),
    ("diamonds", "Romby", "Diamonds"),
    ("waves", "Fale", "Waves"),
    ("horizon", "Horyzont", "Horizon"),
    ("leaves", "Liście", "Leaves"),
    ("stars", "Gwiazdy", "Stars"),
    ("checks", "Szachownica", "Checks"),
    ("sunset", "Zachód słońca", "Sunset"),
]

_cache = {}


def is_red(suit):
    return suit in "HD"


def suit_path(suit, size):
    """Kształt symbolu koloru (pik/kier/karo/trefl) w kwadracie size×size, środek w (0,0)."""
    s = size / 2
    p = QPainterPath()
    if suit == "H":
        p.moveTo(0, s * 0.95)
        p.cubicTo(-s * 1.15, s * 0.05, -s * 0.95, -s * 1.05, 0, -s * 0.45)
        p.cubicTo(s * 0.95, -s * 1.05, s * 1.15, s * 0.05, 0, s * 0.95)
    elif suit == "D":
        p.moveTo(0, -s)
        p.quadTo(s * 0.35, -s * 0.35, s * 0.78, 0)
        p.quadTo(s * 0.35, s * 0.35, 0, s)
        p.quadTo(-s * 0.35, s * 0.35, -s * 0.78, 0)
        p.quadTo(-s * 0.35, -s * 0.35, 0, -s)
    elif suit == "S":
        p.moveTo(0, -s)
        p.cubicTo(s * 0.3, -s * 0.5, s * 1.1, -s * 0.15, s * 0.82, s * 0.38)
        p.cubicTo(s * 0.62, s * 0.72, s * 0.2, s * 0.62, s * 0.08, s * 0.35)
        p.lineTo(s * 0.32, s)
        p.lineTo(-s * 0.32, s)
        p.lineTo(-s * 0.08, s * 0.35)
        p.cubicTo(-s * 0.2, s * 0.62, -s * 0.62, s * 0.72, -s * 0.82, s * 0.38)
        p.cubicTo(-s * 1.1, -s * 0.15, -s * 0.3, -s * 0.5, 0, -s)
    else:  # C trefl
        r = s * 0.42
        p.addEllipse(QPointF(0, -s * 0.48), r, r)
        p.addEllipse(QPointF(-s * 0.5, s * 0.1), r, r)
        p.addEllipse(QPointF(s * 0.5, s * 0.1), r, r)
        stem = QPainterPath()
        stem.moveTo(-s * 0.08, 0)
        stem.lineTo(s * 0.08, 0)
        stem.lineTo(s * 0.32, s)
        stem.lineTo(-s * 0.32, s)
        stem.closeSubpath()
        p = p.united(stem)
        p.addRect(QRectF(-s * 0.12, -s * 0.2, s * 0.24, s * 0.5))
    return p.simplified()


def draw_suit(p, suit, cx, cy, size, flip=False):
    p.save()
    p.translate(cx, cy)
    if flip:
        p.rotate(180)
    p.setPen(Qt.NoPen)
    p.setBrush(RED if is_red(suit) else BLACK)
    p.drawPath(suit_path(suit, size))
    p.restore()


# rozmieszczenie symboli na kartach 2–10: (x, y) w jednostkach 0..1 obszaru środka
PIPS = {
    2: [(0.5, 0.0), (0.5, 1.0)],
    3: [(0.5, 0.0), (0.5, 0.5), (0.5, 1.0)],
    4: [(0, 0), (1, 0), (0, 1), (1, 1)],
    5: [(0, 0), (1, 0), (0.5, 0.5), (0, 1), (1, 1)],
    6: [(0, 0), (1, 0), (0, 0.5), (1, 0.5), (0, 1), (1, 1)],
    7: [(0, 0), (1, 0), (0.5, 0.25), (0, 0.5), (1, 0.5), (0, 1), (1, 1)],
    8: [(0, 0), (1, 0), (0.5, 0.25), (0, 0.5), (1, 0.5), (0.5, 0.75), (0, 1), (1, 1)],
    9: [(0, 0), (1, 0), (0, 1 / 3), (1, 1 / 3), (0.5, 0.5), (0, 2 / 3), (1, 2 / 3), (0, 1), (1, 1)],
    10: [(0, 0), (1, 0), (0.5, 1 / 6), (0, 1 / 3), (1, 1 / 3), (0, 2 / 3), (1, 2 / 3), (0.5, 5 / 6), (0, 1), (1, 1)],
}


def _rounded(p, r, radius=5):
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    return path


def card_face(rank, suit, scale=1.0):
    key = ("face", rank, suit, scale)
    if key in _cache:
        return _cache[key]
    w, h = round(CARD_W * scale), round(CARD_H * scale)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    r = QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1)
    p.setPen(QPen(QColor("#000000"), 1))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(_rounded(p, r))
    col = RED if is_red(suit) else BLACK
    from ...common.appkit import T
    label = T(RANK_PL.get(rank, rank), rank)
    f = QFont("DejaVu Sans")
    f.setBold(True)
    f.setPixelSize(13 if rank != "10" else 12)
    p.setFont(f)
    p.setPen(col)
    # narożniki
    for flip in (False, True):
        p.save()
        if flip:
            p.translate(CARD_W, CARD_H)
            p.rotate(180)
        p.drawText(QRectF(1, 2, 16, 14), Qt.AlignCenter, label)
        draw_suit(p, suit, 9, 21, 9)
        p.restore()
    n = RANKS.index(rank) + 1
    if n == 1:
        draw_suit(p, suit, CARD_W / 2, CARD_H / 2, 34 if suit == "S" else 26)
        if suit == "S":
            # ozdobny as pik
            p.setPen(QPen(QColor("#ffffff"), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(CARD_W / 2, CARD_H / 2 - 1), 4, 4)
    elif n <= 10:
        area = QRectF(25, 15, CARD_W - 50, CARD_H - 30)
        for x, y in PIPS[n]:
            cx = area.left() + x * area.width()
            cy = area.top() + y * area.height()
            draw_suit(p, suit, cx, cy, 12, flip=y > 0.5)
    else:
        _court(p, rank, suit, col)
    p.end()
    _cache[key] = pm
    return pm


def _court(p, rank, suit, col):
    """Figury: oryginalny, prosty wzór — ramka, korona/diadem i duża litera, symetrycznie odbite."""
    box = QRectF(15, 13, CARD_W - 30, CARD_H - 26)
    accent = {"S": QColor("#2a4b9b"), "H": QColor("#c8102e"), "D": QColor("#d98a00"), "C": QColor("#1e7a3c")}[suit]
    g = QLinearGradient(box.topLeft(), box.bottomRight())
    g.setColorAt(0, QColor("#fff7d6"))
    g.setColorAt(1, QColor("#f2e3a8"))
    p.setBrush(g)
    p.setPen(QPen(col, 1))
    p.drawRect(box)
    for flip in (False, True):
        p.save()
        if flip:
            p.translate(CARD_W, CARD_H)
            p.rotate(180)
        cx = CARD_W / 2
        top = box.top() + 3
        # nakrycie głowy
        p.setPen(QPen(QColor("#5a3a00"), 0.8))
        p.setBrush(QColor("#f0c419"))
        crown = QPainterPath()
        if rank == "K":
            crown.moveTo(cx - 10, top + 12)
            for i, dx in enumerate((-10, -6, -3, 0, 3, 6, 10)):
                crown.lineTo(cx + dx, top + (2 if i % 2 == 0 else 7))
            crown.lineTo(cx + 10, top + 12)
        elif rank == "Q":
            crown.moveTo(cx - 9, top + 12)
            crown.quadTo(cx - 9, top + 3, cx, top + 2)
            crown.quadTo(cx + 9, top + 3, cx + 9, top + 12)
        else:
            crown.addRect(QRectF(cx - 8, top + 5, 16, 6))
            crown.moveTo(cx - 8, top + 5)
            crown.lineTo(cx, top + 1)
            crown.lineTo(cx + 8, top + 5)
        crown.closeSubpath()
        p.drawPath(crown)
        p.setBrush(accent)
        p.drawEllipse(QPointF(cx, top + 8), 1.6, 1.6)
        # twarz
        p.setBrush(QColor("#fde0c0"))
        p.setPen(QPen(QColor("#6b4a2b"), 0.8))
        p.drawEllipse(QRectF(cx - 6.5, top + 12, 13, 13))
        p.setPen(QPen(QColor("#3a2a1a"), 1))
        p.drawPoint(QPointF(cx - 2.5, top + 17.5))
        p.drawPoint(QPointF(cx + 2.5, top + 17.5))
        p.drawArc(QRectF(cx - 2.5, top + 18.5, 5, 3), 200 * 16, 140 * 16)
        # szata
        robe = QPainterPath()
        robe.moveTo(cx - 13, box.center().y() - 1)
        robe.quadTo(cx - 12, top + 26, cx, top + 25)
        robe.quadTo(cx + 12, top + 26, cx + 13, box.center().y() - 1)
        robe.closeSubpath()
        p.setPen(QPen(col, 0.8))
        p.setBrush(accent)
        p.drawPath(robe)
        draw_suit(p, suit, cx + 8, top + 29, 7)
        p.restore()
    p.setPen(QPen(QColor(0, 0, 0, 90), 0.6))
    p.drawLine(QPointF(box.left(), box.center().y()), QPointF(box.right(), box.center().y()))


def card_back(style, scale=1.0):
    key = ("back", style, scale)
    if key in _cache:
        return _cache[key]
    w, h = round(CARD_W * scale), round(CARD_H * scale)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    outer = QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1)
    p.setPen(QPen(QColor("#000000"), 1))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(_rounded(p, outer))
    inner = QRectF(4, 4, CARD_W - 8, CARD_H - 8)
    p.setClipPath(_rounded(p, inner, 3))
    _back_pattern(p, style, inner)
    p.setClipping(False)
    p.setPen(QPen(QColor(0, 0, 0, 120), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(_rounded(p, inner, 3))
    p.end()
    _cache[key] = pm
    return pm


def _back_pattern(p, style, r):
    if style == "lattice":
        p.fillRect(r, QColor("#1f4fa8"))
        p.setPen(QPen(QColor("#8fb4f0"), 1))
        for i in range(-20, 30):
            x = r.left() + i * 6
            p.drawLine(QPointF(x, r.top()), QPointF(x + r.height(), r.bottom()))
            p.drawLine(QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()))
    elif style == "diamonds":
        p.fillRect(r, QColor("#b3121f"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f2c0c4"))
        for yi in range(0, 14):
            for xi in range(0, 10):
                cx = r.left() + xi * 8 + (4 if yi % 2 else 0)
                cy = r.top() + yi * 7
                path = QPainterPath()
                path.moveTo(cx, cy - 3)
                path.lineTo(cx + 2.5, cy)
                path.lineTo(cx, cy + 3)
                path.lineTo(cx - 2.5, cy)
                path.closeSubpath()
                p.drawPath(path)
    elif style == "waves":
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#0a6e8a"))
        g.setColorAt(1, QColor("#03384b"))
        p.fillRect(r, g)
        p.setBrush(Qt.NoBrush)
        for yi in range(0, 20):
            p.setPen(QPen(QColor(255, 255, 255, 70 + (yi % 3) * 30), 1.2))
            path = QPainterPath()
            y = r.top() + yi * 5
            path.moveTo(r.left(), y)
            x = r.left()
            while x < r.right() + 8:
                path.quadTo(x + 4, y - 3, x + 8, y)
                x += 8
            p.drawPath(path)
    elif style == "horizon":
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#1f8591"))
        g.setColorAt(0.55, QColor("#7fd1d8"))
        g.setColorAt(0.56, QColor("#2f6f3e"))
        g.setColorAt(1, QColor("#16391f"))
        p.fillRect(r, g)
        p.setPen(Qt.NoPen)
        rg = QRadialGradient(QPointF(r.center().x(), r.top() + r.height() * 0.55), 14)
        rg.setColorAt(0, QColor("#fff6c0"))
        rg.setColorAt(1, QColor(255, 246, 192, 0))
        p.setBrush(rg)
        p.drawEllipse(QPointF(r.center().x(), r.top() + r.height() * 0.55), 14, 14)
        hills = QPainterPath()
        hills.moveTo(r.left(), r.top() + r.height() * 0.62)
        hills.quadTo(r.left() + r.width() * 0.3, r.top() + r.height() * 0.48, r.center().x(), r.top() + r.height() * 0.6)
        hills.quadTo(r.right() - r.width() * 0.2, r.top() + r.height() * 0.68, r.right(), r.top() + r.height() * 0.56)
        hills.lineTo(r.right(), r.bottom())
        hills.lineTo(r.left(), r.bottom())
        hills.closeSubpath()
        p.setBrush(QColor("#245a31"))
        p.drawPath(hills)
    elif style == "leaves":
        p.fillRect(r, QColor("#2e6b2a"))
        p.setPen(QPen(QColor("#1d4a1a"), 0.6))
        p.setBrush(QColor("#7fb84a"))
        for yi in range(0, 9):
            for xi in range(0, 6):
                cx = r.left() + xi * 12 + (6 if yi % 2 else 0)
                cy = r.top() + yi * 11 + 3
                p.save()
                p.translate(cx, cy)
                p.rotate(35 if (xi + yi) % 2 else -35)
                leaf = QPainterPath()
                leaf.moveTo(0, -5)
                leaf.quadTo(4, 0, 0, 5)
                leaf.quadTo(-4, 0, 0, -5)
                p.drawPath(leaf)
                p.restore()
    elif style == "stars":
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#140a3a"))
        g.setColorAt(1, QColor("#3a1a6b"))
        p.fillRect(r, g)
        import random
        rnd = random.Random(7)
        p.setPen(Qt.NoPen)
        for _ in range(60):
            p.setBrush(QColor(255, 255, 255, rnd.randint(120, 255)))
            p.drawEllipse(QPointF(r.left() + rnd.random() * r.width(), r.top() + rnd.random() * r.height()),
                          rnd.random() * 0.9 + 0.3, rnd.random() * 0.9 + 0.3)
        p.setBrush(QColor("#ffe9a0"))
        p.drawEllipse(QPointF(r.right() - 16, r.top() + 18), 8, 8)
        p.setBrush(QColor("#2a1458"))
        p.drawEllipse(QPointF(r.right() - 12, r.top() + 15), 7, 7)
    elif style == "checks":
        p.fillRect(r, QColor("#ffffff"))
        for yi in range(0, 15):
            for xi in range(0, 11):
                if (xi + yi) % 2 == 0:
                    p.fillRect(QRectF(r.left() + xi * 6, r.top() + yi * 6, 6, 6), QColor("#6b2b8f"))
    else:  # sunset
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#ff7e2d"))
        g.setColorAt(0.6, QColor("#ffd27a"))
        g.setColorAt(0.61, QColor("#2c4a7a"))
        g.setColorAt(1, QColor("#14233d"))
        p.fillRect(r, g)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffef9a"))
        p.drawEllipse(QPointF(r.center().x(), r.top() + r.height() * 0.6), 13, 13)
        p.setBrush(QColor(255, 220, 140, 120))
        for i in range(5):
            y = r.top() + r.height() * 0.64 + i * 4
            p.drawRect(QRectF(r.center().x() - 12 + i * 2, y, 24 - i * 4, 1.2))


def placeholder(scale=1.0, kind="empty"):
    key = ("ph", kind, scale)
    if key in _cache:
        return _cache[key]
    w, h = round(CARD_W * scale), round(CARD_H * scale)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    r = QRectF(1, 1, CARD_W - 2, CARD_H - 2)
    p.setPen(QPen(QColor(0, 0, 0, 110), 1))
    p.setBrush(QColor(0, 0, 0, 30))
    p.drawRoundedRect(r, 5, 5)
    if kind == "recycle":
        p.setPen(QPen(QColor(0, 220, 0), 5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(CARD_W / 2, CARD_H / 2), 18, 18)
    elif kind == "stop":
        p.setPen(QPen(QColor(220, 0, 0), 5))
        p.drawEllipse(QPointF(CARD_W / 2, CARD_H / 2), 18, 18)
        p.drawLine(QPointF(CARD_W / 2 - 12, CARD_H / 2 + 12), QPointF(CARD_W / 2 + 12, CARD_H / 2 - 12))
    p.end()
    _cache[key] = pm
    return pm
