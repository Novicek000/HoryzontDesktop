"""Oryginalne tapety generowane proceduralnie (żadnych cudzych zdjęć).

- horyzont: zachód słońca nad warstwami grzbietów górskich
- zatoka:   miękkie fale w kolorach morza
- zorza:    wstęgi zorzy na nocnym niebie
- wydmy:    złote wydmy pod błękitnym niebem
- kropla:   abstrakcyjne koncentryczne kręgi na wodzie
oraz własne interpretacje klimatu tapet z początku lat 2000:
- wzgorze:  zielone wzgórze pod błękitnym niebem z obłokami
- lazur:    turkusowa zatoka z piaszczystym brzegiem
- jesien:   jesienne liście na rozmytym, ciepłym tle
- tulipany: pole czerwonych tulipanów
- wstegi:   świetliste zielono-niebieskie wstęgi na ciemnym tle
- swiatla:  rozmyte światła (bokeh) w odcieniach błękitu
"""
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QRadialGradient)

from .. import config

BUILTIN = ["horyzont", "wzgorze", "lazur", "tulipany", "jesien", "wstegi", "swiatla", "zatoka", "zorza", "wydmy",
           "kropla"]
LABELS = {
    "horyzont": ("Horyzont", "Horizon"),
    "zatoka": ("Zatoka", "Bay"),
    "zorza": ("Zorza", "Aurora"),
    "wydmy": ("Wydmy", "Dunes"),
    "kropla": ("Kropla", "Ripple"),
    "wzgorze": ("Wzgórze", "Hill"),
    "lazur": ("Lazur", "Azure"),
    "jesien": ("Jesień", "Autumn"),
    "tulipany": ("Tulipany", "Tulips"),
    "wstegi": ("Wstęgi światła", "Light Ribbons"),
    "swiatla": ("Światła", "Lights"),
}


def _ridge(w, h, base_y, amp, seed, roughness=0.5, octaves=5):
    rnd = random.Random(seed)
    phases = [rnd.uniform(0, math.tau) for _ in range(octaves)]
    path = QPainterPath()
    path.moveTo(0, h)
    steps = 160
    for i in range(steps + 1):
        x = w * i / steps
        y = 0.0
        a = 1.0
        f = 1.0
        for o in range(octaves):
            y += a * math.sin(x / w * math.pi * 2 * f + phases[o])
            a *= roughness
            f *= 2.13
        path.lineTo(x, base_y - y * amp)
    path.lineTo(w, h)
    path.closeSubpath()
    return path


def _paint_horyzont(p, w, h):
    sky = QLinearGradient(0, 0, 0, h * 0.72)
    sky.setColorAt(0.0, QColor("#16345c"))
    sky.setColorAt(0.35, QColor("#3a6ea0"))
    sky.setColorAt(0.62, QColor("#9ab6cf"))
    sky.setColorAt(0.82, QColor("#f2c48d"))
    sky.setColorAt(1.0, QColor("#f59a5a"))
    p.fillRect(QRectF(0, 0, w, h), sky)
    # poświata słońca
    sx, sy = w * 0.68, h * 0.62
    glow = QRadialGradient(QPointF(sx, sy), h * 0.5)
    glow.setColorAt(0, QColor(255, 236, 190, 230))
    glow.setColorAt(0.08, QColor(255, 214, 150, 170))
    glow.setColorAt(0.35, QColor(255, 180, 120, 60))
    glow.setColorAt(1, QColor(255, 160, 100, 0))
    p.fillRect(QRectF(0, 0, w, h), glow)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 246, 220))
    p.drawEllipse(QPointF(sx, sy), h * 0.035, h * 0.035)
    # cienkie chmurki
    rnd = random.Random(7)
    for i in range(9):
        cy = h * rnd.uniform(0.18, 0.5)
        cx = w * rnd.uniform(-0.1, 1.0)
        cw = w * rnd.uniform(0.15, 0.4)
        ch = h * rnd.uniform(0.006, 0.016)
        g = QLinearGradient(cx, 0, cx + cw, 0)
        a = rnd.randint(40, 90)
        g.setColorAt(0, QColor(255, 220, 200, 0))
        g.setColorAt(0.5, QColor(255, 222, 205, a))
        g.setColorAt(1, QColor(255, 220, 200, 0))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(cx, cy, cw, ch), ch / 2, ch / 2)
    # grzbiety górskie od najdalszego
    layers = [
        (0.66, 0.05, "#7b86a8", "#8f8fae", 11, 0.55),
        (0.71, 0.06, "#5d6d96", "#6f7aa0", 23, 0.5),
        (0.77, 0.055, "#3f5683", "#4a6290", 37, 0.52),
        (0.84, 0.05, "#29436d", "#2f4b78", 41, 0.48),
        (0.92, 0.04, "#162d4f", "#1c375c", 53, 0.45),
    ]
    for base, amp, c1, c2, seed, rough in layers:
        path = _ridge(w, h, h * base, h * amp, seed, rough)
        g = QLinearGradient(0, h * (base - amp * 2), 0, h)
        g.setColorAt(0, QColor(c2))
        g.setColorAt(1, QColor(c1).darker(115))
        p.setBrush(g)
        p.drawPath(path)
        # mgiełka u podnóża warstwy (w obrębie samego grzbietu)
        haze = QLinearGradient(0, h * (base - amp * 1.5), 0, h * (base + 0.12))
        haze.setColorAt(0, QColor(250, 200, 160, 0))
        haze.setColorAt(0.75, QColor(250, 200, 160, 0))
        haze.setColorAt(1, QColor(250, 200, 160, 55))
        p.setBrush(haze)
        p.drawPath(path)
    # tafla jeziora na dole
    lake = QLinearGradient(0, h * 0.95, 0, h)
    lake.setColorAt(0, QColor("#2a4a74"))
    lake.setColorAt(1, QColor("#0f2140"))
    p.setBrush(lake)
    p.drawRect(QRectF(0, h * 0.955, w, h * 0.05))
    p.setBrush(QColor(255, 220, 170, 90))
    for i in range(6):
        yy = h * (0.962 + i * 0.006)
        ww = w * (0.08 - i * 0.01)
        p.drawRect(QRectF(sx - ww / 2, yy, ww, max(1.0, h * 0.0015)))


def _paint_zatoka(p, w, h):
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor("#0e4d64"))
    g.setColorAt(0.5, QColor("#1a7d8f"))
    g.setColorAt(1, QColor("#0a3446"))
    p.fillRect(QRectF(0, 0, w, h), g)
    p.setPen(Qt.NoPen)
    for i in range(12):
        t = i / 11
        base = h * (0.25 + t * 0.7)
        path = QPainterPath()
        path.moveTo(0, h)
        steps = 100
        for s in range(steps + 1):
            x = w * s / steps
            y = base + math.sin(x / w * math.tau * (1.2 + t * 0.6) + i * 0.9) * h * 0.035 \
                + math.sin(x / w * math.tau * 3.1 + i) * h * 0.01
            path.lineTo(x, y)
        path.lineTo(w, h)
        c = QColor.fromHsvF(0.5 - t * 0.03, 0.75 - t * 0.2, 0.55 + t * 0.25, 0.22)
        p.setBrush(c)
        p.drawPath(path)
    glow = QRadialGradient(QPointF(w * 0.3, h * 0.2), h * 0.7)
    glow.setColorAt(0, QColor(255, 255, 255, 60))
    glow.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, w, h), glow)


def _paint_zorza(p, w, h):
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor("#030a1c"))
    g.setColorAt(0.7, QColor("#0b2038"))
    g.setColorAt(1, QColor("#122a3a"))
    p.fillRect(QRectF(0, 0, w, h), g)
    rnd = random.Random(3)
    p.setPen(Qt.NoPen)
    for i in range(int(w * h / 5000)):
        a = rnd.randint(60, 230)
        p.setBrush(QColor(255, 255, 255, a))
        r = rnd.choice((0.6, 0.8, 1.0, 1.3))
        p.drawEllipse(QPointF(rnd.uniform(0, w), rnd.uniform(0, h * 0.75)), r, r)
    for band in range(4):
        base = h * (0.3 + band * 0.08)
        for k in range(30):
            path = QPainterPath()
            off = k * h * 0.004
            path.moveTo(0, base + off)
            for s in range(81):
                x = w * s / 80
                y = base + off + math.sin(x / w * math.tau * (0.8 + band * 0.25) + band * 1.7) * h * 0.08
                path.lineTo(x, y)
            col = QColor.fromHsvF((0.38 + band * 0.06) % 1.0, 0.8, 0.9, 0.035)
            from PySide6.QtGui import QPen
            p.setPen(QPen(col, h * 0.03))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#050d16"))
    p.drawPath(_ridge(w, h, h * 0.93, h * 0.04, 99, 0.55))


def _paint_wydmy(p, w, h):
    sky = QLinearGradient(0, 0, 0, h * 0.6)
    sky.setColorAt(0, QColor("#2c7fc0"))
    sky.setColorAt(1, QColor("#bfe2f5"))
    p.fillRect(QRectF(0, 0, w, h), sky)
    p.setPen(Qt.NoPen)
    cols = [("#e8b56a", "#c98a3e"), ("#e0a453", "#b97a30"), ("#d39343", "#a86a24"), ("#c78437", "#93591a")]
    for i, (c1, c2) in enumerate(cols):
        base = h * (0.55 + i * 0.12)
        path = QPainterPath()
        path.moveTo(0, h)
        for s in range(121):
            x = w * s / 120
            y = base - abs(math.sin(x / w * math.pi * (1.3 + i * 0.4) + i * 1.3)) * h * 0.09
            path.lineTo(x, y)
        path.lineTo(w, h)
        g = QLinearGradient(0, base - h * 0.1, w, h)
        g.setColorAt(0, QColor(c1))
        g.setColorAt(1, QColor(c2))
        p.setBrush(g)
        p.drawPath(path)


def _paint_kropla(p, w, h):
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#0c3b5a"))
    g.setColorAt(1, QColor("#2a8a96"))
    p.fillRect(QRectF(0, 0, w, h), g)
    from PySide6.QtGui import QPen
    cx, cy = w * 0.62, h * 0.55
    p.setBrush(Qt.NoBrush)
    for i in range(1, 26):
        r = i * h * 0.045
        a = max(0, 90 - i * 3)
        p.setPen(QPen(QColor(255, 255, 255, a), max(1.0, h * 0.003)))
        p.drawEllipse(QPointF(cx, cy), r * 1.6, r)


def _cloud(p, cx, cy, size, rnd, alpha=235):
    """Kłębiasty obłok z nakładających się miękkich kół (płaski spód)."""
    p.save()
    clip = QPainterPath()
    clip.addRect(QRectF(cx - size * 3, cy - size * 3, size * 6, size * 3 + size * 0.35))
    p.setClipPath(clip)
    for _ in range(int(18 + size / 6)):
        r = size * rnd.uniform(0.35, 0.8)
        x = cx + rnd.gauss(0, size * 0.9)
        y = cy - abs(rnd.gauss(0, size * 0.35)) - r * 0.2
        g = QRadialGradient(QPointF(x - r * 0.2, y - r * 0.3), r * 1.15)
        g.setColorAt(0, QColor(255, 255, 255, alpha))
        g.setColorAt(0.55, QColor(250, 252, 255, int(alpha * 0.85)))
        g.setColorAt(0.85, QColor(225, 235, 248, int(alpha * 0.35)))
        g.setColorAt(1, QColor(220, 232, 248, 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(x, y), r * 1.15, r * 1.15)
    p.restore()


def _grass_texture(p, path, w, h, rnd, colors, density=1.0):
    p.save()
    p.setClipPath(path)
    from PySide6.QtGui import QPen
    n = int(w * h / 180 * density)
    for _ in range(n):
        x = rnd.uniform(0, w)
        y = rnd.uniform(h * 0.45, h)
        ln = h * rnd.uniform(0.004, 0.012) * (0.5 + (y / h))
        c = QColor(rnd.choice(colors))
        c.setAlpha(rnd.randint(40, 110))
        p.setPen(QPen(c, max(1.0, h * 0.0012)))
        p.drawLine(QPointF(x, y), QPointF(x + rnd.uniform(-1, 1) * ln * 0.4, y - ln))
    p.restore()


def _paint_wzgorze(p, w, h):
    sky = QLinearGradient(0, 0, 0, h * 0.7)
    sky.setColorAt(0, QColor("#1650b8"))
    sky.setColorAt(0.45, QColor("#3a86dc"))
    sky.setColorAt(0.85, QColor("#8cc0ef"))
    sky.setColorAt(1, QColor("#b9daf6"))
    p.fillRect(QRectF(0, 0, w, h), sky)
    p.setPen(Qt.NoPen)
    rnd = random.Random(11)
    for cx, cy, sz in ((0.18, 0.2, 0.07), (0.42, 0.13, 0.05), (0.63, 0.24, 0.085), (0.86, 0.16, 0.06),
                       (0.3, 0.36, 0.04), (0.75, 0.38, 0.035), (0.05, 0.4, 0.03), (0.95, 0.33, 0.04)):
        _cloud(p, w * cx, h * cy, h * sz, rnd)
    # wzgórze dalsze (po prawej) i główne
    back = QPainterPath()
    back.moveTo(w * 0.35, h)
    back.cubicTo(w * 0.55, h * 0.62, w * 0.8, h * 0.6, w * 1.05, h * 0.66)
    back.lineTo(w * 1.05, h)
    back.closeSubpath()
    g = QLinearGradient(0, h * 0.6, 0, h)
    g.setColorAt(0, QColor("#6aa83a"))
    g.setColorAt(1, QColor("#2c6a1e"))
    p.setBrush(g)
    p.drawPath(back)
    hill = QPainterPath()
    hill.moveTo(-w * 0.05, h * 0.72)
    hill.cubicTo(w * 0.15, h * 0.58, w * 0.42, h * 0.55, w * 0.62, h * 0.68)
    hill.cubicTo(w * 0.78, h * 0.78, w * 0.95, h * 0.8, w * 1.05, h * 0.83)
    hill.lineTo(w * 1.05, h)
    hill.lineTo(-w * 0.05, h)
    hill.closeSubpath()
    g = QLinearGradient(w * 0.3, h * 0.55, w * 0.5, h)
    g.setColorAt(0, QColor("#a6d150"))
    g.setColorAt(0.35, QColor("#74b136"))
    g.setColorAt(1, QColor("#2f7a1f"))
    p.setBrush(g)
    p.drawPath(hill)
    # światło na grzbiecie
    shine = QRadialGradient(QPointF(w * 0.33, h * 0.6), h * 0.3)
    shine.setColorAt(0, QColor(230, 255, 160, 70))
    shine.setColorAt(1, QColor(230, 255, 160, 0))
    p.save()
    p.setClipPath(hill)
    p.fillRect(QRectF(0, 0, w, h), shine)
    p.restore()
    _grass_texture(p, hill, w, h, rnd, ["#9ccc4a", "#4f9a2a", "#c3e070", "#3d7f22"], 0.8)


def _paint_lazur(p, w, h):
    sky = QLinearGradient(0, 0, 0, h * 0.4)
    sky.setColorAt(0, QColor("#2f8fd8"))
    sky.setColorAt(1, QColor("#bfe6f7"))
    p.fillRect(QRectF(0, 0, w, h), sky)
    p.setPen(Qt.NoPen)
    rnd = random.Random(5)
    for cx, cy, sz in ((0.2, 0.15, 0.035), (0.7, 0.1, 0.03), (0.5, 0.25, 0.02)):
        _cloud(p, w * cx, h * cy, h * sz, rnd, 200)
    sea = QLinearGradient(0, h * 0.38, 0, h)
    sea.setColorAt(0, QColor("#0a6fa8"))
    sea.setColorAt(0.35, QColor("#06a3bd"))
    sea.setColorAt(0.7, QColor("#2fd0c8"))
    sea.setColorAt(1, QColor("#8fe8d6"))
    p.fillRect(QRectF(0, h * 0.38, w, h * 0.62), sea)
    from PySide6.QtGui import QPen
    for i in range(160):
        y = h * (0.4 + (i / 160) ** 1.4 * 0.6)
        x = rnd.uniform(-0.1, 1.0) * w
        ln = w * rnd.uniform(0.02, 0.12) * (0.3 + y / h)
        p.setPen(QPen(QColor(255, 255, 255, rnd.randint(25, 80)), max(1.0, h * 0.0015 * (y / h))))
        path = QPainterPath(QPointF(x, y))
        path.quadTo(x + ln / 2, y - h * 0.004, x + ln, y)
        p.drawPath(path)
    p.setPen(Qt.NoPen)
    sand = QPainterPath()
    sand.moveTo(-w * 0.05, h * 0.86)
    sand.cubicTo(w * 0.3, h * 0.8, w * 0.6, h * 0.95, w * 1.05, h * 0.88)
    sand.lineTo(w * 1.05, h)
    sand.lineTo(-w * 0.05, h)
    sand.closeSubpath()
    g = QLinearGradient(0, h * 0.82, 0, h)
    g.setColorAt(0, QColor("#f3e3bd"))
    g.setColorAt(1, QColor("#d9bf8a"))
    p.setBrush(g)
    p.drawPath(sand)
    foam = QPainterPath()
    foam.moveTo(-w * 0.05, h * 0.86)
    foam.cubicTo(w * 0.3, h * 0.8, w * 0.6, h * 0.95, w * 1.05, h * 0.88)
    p.setPen(QPen(QColor(255, 255, 255, 170), h * 0.006))
    p.setBrush(Qt.NoBrush)
    p.drawPath(foam)


def _leaf_path(size):
    path = QPainterPath(QPointF(0, -size))
    pts = [(0.25, -0.75), (0.55, -0.8), (0.45, -0.45), (0.85, -0.35), (0.6, -0.05), (0.8, 0.25), (0.35, 0.2),
           (0.1, 0.55)]
    for x, y in pts:
        path.lineTo(x * size, y * size)
    path.lineTo(0, size * 0.55)
    for x, y in reversed(pts):
        path.lineTo(-x * size, y * size)
    path.closeSubpath()
    return path


def _paint_jesien(p, w, h):
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#3a1a08"))
    g.setColorAt(0.5, QColor("#7a3410"))
    g.setColorAt(1, QColor("#2a1206"))
    p.fillRect(QRectF(0, 0, w, h), g)
    rnd = random.Random(21)
    p.setPen(Qt.NoPen)
    for _ in range(70):
        r = h * rnd.uniform(0.02, 0.12)
        c = QColor(rnd.choice(["#ffb347", "#ff7b29", "#ffd36b", "#e0531b"]))
        rg = QRadialGradient(QPointF(rnd.uniform(0, w), rnd.uniform(0, h)), r)
        c.setAlpha(rnd.randint(30, 90))
        rg.setColorAt(0, c)
        rg.setColorAt(0.7, QColor(c.red(), c.green(), c.blue(), c.alpha() // 2))
        rg.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
        p.setBrush(rg)
        p.drawRect(QRectF(0, 0, w, h))
    from PySide6.QtGui import QPen
    for i in range(14):
        size = h * rnd.uniform(0.06, 0.16)
        x, y = rnd.uniform(0.05, 0.95) * w, rnd.uniform(0.1, 0.95) * h
        p.save()
        p.translate(x, y)
        p.rotate(rnd.uniform(0, 360))
        base = QColor(rnd.choice(["#d93a12", "#f07a1a", "#f2b21c", "#b8260f", "#e8901f"]))
        lg = QLinearGradient(0, -size, 0, size)
        lg.setColorAt(0, base.lighter(130))
        lg.setColorAt(1, base.darker(130))
        p.setBrush(lg)
        p.setPen(QPen(base.darker(160), max(1.0, size * 0.02)))
        p.drawPath(_leaf_path(size))
        p.setPen(QPen(base.darker(150), max(1.0, size * 0.025)))
        p.drawLine(QPointF(0, size * 0.9), QPointF(0, -size * 0.85))
        for a in (-1, 1):
            p.drawLine(QPointF(0, size * 0.1), QPointF(a * size * 0.55, -size * 0.45))
            p.drawLine(QPointF(0, size * 0.25), QPointF(a * size * 0.6, -size * 0.05))
        p.restore()


def _paint_tulipany(p, w, h):
    sky = QLinearGradient(0, 0, 0, h * 0.45)
    sky.setColorAt(0, QColor("#3c8fe0"))
    sky.setColorAt(1, QColor("#d7ecfb"))
    p.fillRect(QRectF(0, 0, w, h), sky)
    p.setPen(Qt.NoPen)
    rnd = random.Random(8)
    for cx, cy, sz in ((0.15, 0.14, 0.04), (0.55, 0.1, 0.05), (0.85, 0.2, 0.035)):
        _cloud(p, w * cx, h * cy, h * sz, rnd, 220)
    field = QLinearGradient(0, h * 0.42, 0, h)
    field.setColorAt(0, QColor("#4f8f2a"))
    field.setColorAt(1, QColor("#1f4f12"))
    p.fillRect(QRectF(0, h * 0.42, w, h * 0.58), field)
    from PySide6.QtGui import QPen
    rows = 26
    for r in range(rows):
        t = r / (rows - 1)
        y = h * (0.44 + t ** 1.6 * 0.6)
        size = h * (0.004 + t ** 1.8 * 0.05)
        n = int(w / (size * 2.6)) + 2
        for k in range(n):
            x = (k + rnd.uniform(-0.3, 0.3) + (r % 2) * 0.5) * size * 2.6
            yy = y + rnd.uniform(-size * 0.3, size * 0.3)
            p.setPen(QPen(QColor("#2f6a1a"), max(1.0, size * 0.18)))
            p.drawLine(QPointF(x, yy), QPointF(x, yy + size * 2.2))
            p.setPen(Qt.NoPen)
            col = QColor(rnd.choice(["#e0101e", "#d00818", "#f22a2a", "#c40616"]))
            tg = QLinearGradient(x - size, yy - size, x + size, yy + size)
            tg.setColorAt(0, col.lighter(125))
            tg.setColorAt(1, col.darker(130))
            p.setBrush(tg)
            cup = QPainterPath(QPointF(x - size * 0.75, yy - size * 0.6))
            cup.lineTo(x - size * 0.4, yy - size * 0.15)
            cup.lineTo(x, yy - size * 0.7)
            cup.lineTo(x + size * 0.4, yy - size * 0.15)
            cup.lineTo(x + size * 0.75, yy - size * 0.6)
            cup.quadTo(x + size * 0.85, yy + size * 0.55, x, yy + size * 0.6)
            cup.quadTo(x - size * 0.85, yy + size * 0.55, x - size * 0.75, yy - size * 0.6)
            p.drawPath(cup)


def _paint_wstegi(p, w, h):
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#04140c"))
    g.setColorAt(0.5, QColor("#062a1c"))
    g.setColorAt(1, QColor("#020806"))
    p.fillRect(QRectF(0, 0, w, h), g)
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    from PySide6.QtGui import QPen
    rnd = random.Random(42)
    ribbons = [((0.33, 0.95, 0.55), 0.62, 0.22, 1.0), ((0.45, 0.9, 0.6), 0.5, 0.16, 0.8),
               ((0.52, 0.85, 0.75), 0.7, 0.12, 0.6), ((0.27, 0.9, 0.45), 0.38, 0.1, 0.5)]
    for (hue, sat, val), base, width, strength in ribbons:
        for k in range(70):
            t = k / 69
            path = QPainterPath()
            y0 = h * (base + (t - 0.5) * width)
            path.moveTo(-w * 0.1, y0 + h * 0.18)
            path.cubicTo(w * 0.3, y0 - h * (0.25 - t * 0.12), w * 0.6, y0 + h * (0.2 - t * 0.1), w * 1.1, y0 - h * 0.15)
            a = (1 - abs(t - 0.5) * 2) ** 1.5
            col = QColor.fromHsvF(hue + (t - 0.5) * 0.06, sat, val, min(1.0, 0.16 * strength * (0.3 + a)))
            p.setPen(QPen(col, max(1.0, h * 0.0045)))
            p.drawPath(path)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.setPen(Qt.NoPen)
    for _ in range(int(w * h / 9000)):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        r = rnd.uniform(0.5, 2.2) * h / 1000
        p.setBrush(QColor(200, 255, 220, rnd.randint(40, 160)))
        p.drawEllipse(QPointF(x, y), r, r)
    glow = QRadialGradient(QPointF(w * 0.62, h * 0.55), h * 0.6)
    glow.setColorAt(0, QColor(120, 255, 190, 40))
    glow.setColorAt(1, QColor(120, 255, 190, 0))
    p.fillRect(QRectF(0, 0, w, h), glow)


def _paint_swiatla(p, w, h):
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#020b2a"))
    g.setColorAt(0.6, QColor("#0a2a6a"))
    g.setColorAt(1, QColor("#041030"))
    p.fillRect(QRectF(0, 0, w, h), g)
    rnd = random.Random(17)
    p.setPen(Qt.NoPen)
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for _ in range(90):
        r = h * rnd.uniform(0.01, 0.09)
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        hue = rnd.uniform(0.52, 0.62)
        c = QColor.fromHsvF(hue, rnd.uniform(0.3, 0.8), 1.0, rnd.uniform(0.05, 0.22))
        rg = QRadialGradient(QPointF(x, y), r)
        rg.setColorAt(0, c)
        rg.setColorAt(0.85, QColor(c.red(), c.green(), c.blue(), int(c.alpha() * 0.8)))
        rg.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
        p.setBrush(rg)
        p.drawEllipse(QPointF(x, y), r, r)
    streak = QLinearGradient(0, h * 0.7, w, h * 0.3)
    streak.setColorAt(0, QColor(80, 160, 255, 0))
    streak.setColorAt(0.5, QColor(140, 200, 255, 70))
    streak.setColorAt(1, QColor(80, 160, 255, 0))
    path = QPainterPath()
    path.moveTo(0, h * 0.8)
    path.cubicTo(w * 0.35, h * 0.55, w * 0.6, h * 0.65, w, h * 0.3)
    path.lineTo(w, h * 0.36)
    path.cubicTo(w * 0.6, h * 0.71, w * 0.35, h * 0.61, 0, h * 0.86)
    path.closeSubpath()
    p.setBrush(streak)
    p.drawPath(path)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)


PAINTERS = {"horyzont": _paint_horyzont, "zatoka": _paint_zatoka, "zorza": _paint_zorza,
            "wydmy": _paint_wydmy, "kropla": _paint_kropla, "wzgorze": _paint_wzgorze, "lazur": _paint_lazur,
            "jesien": _paint_jesien, "tulipany": _paint_tulipany, "wstegi": _paint_wstegi, "swiatla": _paint_swiatla}


def render(name, w, h):
    w, h = max(64, int(w)), max(48, int(h))
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"wallpaper-{name}-{w}x{h}-v4.png")
    img = QImage()
    if os.path.exists(path) and img.load(path):
        return img
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    PAINTERS.get(name, _paint_horyzont)(p, w, h)
    p.end()
    if w * h > 200 * 150:
        img.save(path)
    return img


def label(name):
    from ..i18n import lang_code
    l = LABELS.get(name)
    if not l:
        return name
    return l[0] if lang_code() == "pl" else l[1]


def draw_desktop_background(p, rect, wallpaper=None, mode=None, color=None):
    """Rysuje tło pulpitu (tapeta + kolor) w podanym prostokącie."""
    wallpaper = config.get("wallpaper") if wallpaper is None else wallpaper
    mode = config.get("wallpaper_mode") if mode is None else mode
    color = QColor(config.get("desktop_color") if color is None else color)
    p.fillRect(rect, color)
    if not wallpaper:
        return
    if wallpaper.startswith("builtin:"):
        img = render(wallpaper.split(":", 1)[1], rect.width(), rect.height())
        p.drawImage(rect, img)
        return
    img = QImage(wallpaper)
    if img.isNull():
        return
    W, H = rect.width(), rect.height()
    iw, ih = img.width(), img.height()
    if mode == "center":
        p.drawImage(int(rect.left() + (W - iw) / 2), int(rect.top() + (H - ih) / 2), img)
    elif mode == "tile":
        y = rect.top()
        while y < rect.bottom():
            x = rect.left()
            while x < rect.right():
                p.drawImage(x, y, img)
                x += iw
            y += ih
    elif mode == "stretch":
        p.drawImage(rect, img)
    elif mode == "fit":
        s = min(W / iw, H / ih)
        tw, th = iw * s, ih * s
        p.drawImage(QRectF(rect.left() + (W - tw) / 2, rect.top() + (H - th) / 2, tw, th), img)
    else:  # fill
        s = max(W / iw, H / ih)
        tw, th = iw * s, ih * s
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(rect.left() + (W - tw) / 2, rect.top() + (H - th) / 2, tw, th), img)
