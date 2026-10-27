"""Oryginalne tapety generowane proceduralnie (żadnych cudzych zdjęć).

- horyzont: zachód słońca nad warstwami grzbietów górskich
- zatoka:   miękkie fale w kolorach morza
- zorza:    wstęgi zorzy na nocnym niebie
- wydmy:    złote wydmy pod błękitnym niebem
- kropla:   abstrakcyjne koncentryczne kręgi na wodzie
"""
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QRadialGradient)

from .. import config

BUILTIN = ["horyzont", "zatoka", "zorza", "wydmy", "kropla"]
LABELS = {
    "horyzont": ("Horyzont", "Horizon"),
    "zatoka": ("Zatoka", "Bay"),
    "zorza": ("Zorza", "Aurora"),
    "wydmy": ("Wydmy", "Dunes"),
    "kropla": ("Kropla", "Ripple"),
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


PAINTERS = {"horyzont": _paint_horyzont, "zatoka": _paint_zatoka, "zorza": _paint_zorza,
            "wydmy": _paint_wydmy, "kropla": _paint_kropla}


def render(name, w, h):
    w, h = max(64, int(w)), max(48, int(h))
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"wallpaper-{name}-{w}x{h}-v3.png")
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
