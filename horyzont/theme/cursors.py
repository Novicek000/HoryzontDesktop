"""Oryginalny motyw wskaźników „Horyzont” rysowany w kodzie i zapisywany w formacie Xcursor."""
import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from ..common import xcursor

SIZES = (24, 32, 48, 64)
VARIANTS = {"Horyzont": ("#ffffff", "#000000"), "Horyzont-Czarny": ("#000000", "#ffffff")}


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


ARROW = [(1, 1), (1, 23), (6.5, 17.8), (10.5, 26.5), (14, 25), (10, 16.4), (17.2, 16.4)]


def _arrow_path(sc=1.0, dx=0, dy=0):
    path = QPainterPath()
    path.addPolygon(_poly(*[(x * sc + dx, y * sc + dy) for x, y in ARROW]))
    path.closeSubpath()
    return path


def _draw(role, p, fill, line, frame=0, nframes=1):
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(line), 1.25)
    pen.setJoinStyle(Qt.MiterJoin)
    p.setPen(pen)
    p.setBrush(QColor(fill))
    hot = (1, 1)
    if role in ("normal", "help", "working"):
        p.drawPath(_arrow_path())
        if role == "help":
            f = p.font()
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            pt = QPainterPath()
            pt.addText(17, 27, f, "?")
            p.drawPath(pt)
        if role == "working":
            _spinner(p, 23, 23, 6.5, frame, nframes, fill, line)
    elif role == "busy":
        _spinner(p, 16, 16, 11, frame, nframes, fill, line)
        hot = (16, 16)
    elif role == "precision":
        p.setPen(QPen(QColor(fill), 3.2))
        for a, b in (((16, 2), (16, 12)), ((16, 20), (16, 30)), ((2, 16), (12, 16)), ((20, 16), (30, 16))):
            p.drawLine(QPointF(*a), QPointF(*b))
        p.setPen(QPen(QColor(line), 1.2))
        for a, b in (((16, 2), (16, 12)), ((16, 20), (16, 30)), ((2, 16), (12, 16)), ((20, 16), (30, 16))):
            p.drawLine(QPointF(*a), QPointF(*b))
        hot = (16, 16)
    elif role == "text":
        path = QPainterPath()
        path.addPolygon(_poly((11, 4), (14, 4), (16, 6), (18, 4), (21, 4), (21, 6), (17, 6), (17, 26), (21, 26),
                              (21, 28), (18, 28), (16, 26), (14, 28), (11, 28), (11, 26), (15, 26), (15, 6), (11, 6)))
        path.closeSubpath()
        p.setBrush(QColor(line))
        p.setPen(QPen(QColor(fill), 1.0))
        p.drawPath(path)
        hot = (16, 16)
    elif role == "handwriting":
        path = QPainterPath()
        path.addPolygon(_poly((3, 29), (5, 22), (22, 5), (27, 10), (10, 27)))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(19, 8), QPointF(24, 13))
        hot = (3, 29)
    elif role == "unavailable":
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(line), 6))
        p.drawEllipse(QRectF(6, 6, 20, 20))
        p.drawLine(QPointF(9, 23), QPointF(23, 9))
        p.setPen(QPen(QColor(fill), 3.4))
        p.drawEllipse(QRectF(6, 6, 20, 20))
        p.drawLine(QPointF(9, 23), QPointF(23, 9))
        hot = (16, 16)
    elif role in ("vert", "horz", "dgn1", "dgn2"):
        path = QPainterPath()
        path.addPolygon(_poly((16, 2), (23, 9), (19, 9), (19, 23), (23, 23), (16, 30), (9, 23), (13, 23), (13, 9), (9, 9)))
        path.closeSubpath()
        ang = {"vert": 0, "horz": 90, "dgn1": -45, "dgn2": 45}[role]
        p.save()
        p.translate(16, 16)
        p.rotate(ang)
        p.translate(-16, -16)
        p.drawPath(path)
        p.restore()
        hot = (16, 16)
    elif role == "move":
        path = QPainterPath()
        path.addPolygon(_poly((16, 1), (21, 6), (18, 6), (18, 14), (26, 14), (26, 11), (31, 16), (26, 21), (26, 18),
                              (18, 18), (18, 26), (21, 26), (16, 31), (11, 26), (14, 26), (14, 18), (6, 18), (6, 21),
                              (1, 16), (6, 11), (6, 14), (14, 14), (14, 6), (11, 6)))
        path.closeSubpath()
        p.drawPath(path)
        hot = (16, 16)
    elif role == "alternate":
        path = QPainterPath()
        path.addPolygon(_poly((16, 2), (26, 13), (19.5, 13), (19.5, 29), (12.5, 29), (12.5, 13), (6, 13)))
        path.closeSubpath()
        p.drawPath(path)
        hot = (16, 2)
    elif role == "link":
        path = QPainterPath()
        # dłoń: wyprostowany palec wskazujący, trzy zgięte palce, kciuk
        path.moveTo(11, 3)
        path.cubicTo(11, 1.2, 14.5, 1.2, 14.5, 3)
        path.lineTo(14.5, 12)
        path.cubicTo(14.8, 10.4, 18, 10.4, 18, 12.5)
        path.cubicTo(18.3, 10.9, 21.4, 10.9, 21.4, 13.2)
        path.cubicTo(21.7, 11.8, 24.8, 11.8, 24.8, 14)
        path.lineTo(24.8, 21)
        path.cubicTo(24.8, 25, 23, 27, 22, 29)
        path.lineTo(12, 29)
        path.cubicTo(11, 27, 9, 25, 6.5, 21)
        path.lineTo(4, 17)
        path.cubicTo(3, 15, 5.5, 13.4, 7, 15)
        path.lineTo(11, 18.5)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(QColor(line), 1.0))
        for x in (18, 21.4):
            p.drawLine(QPointF(x, 13), QPointF(x, 18))
        hot = (12.5, 1.5)
    return hot


def _spinner(p, cx, cy, r, frame, nframes, fill, line):
    p.save()
    p.setPen(QPen(QColor(line), 1.0))
    n = 8
    for i in range(n):
        a = 2 * math.pi * i / n - math.pi / 2
        k = ((i - frame) % n) / n
        col = QColor("#2a8a96")
        col.setAlphaF(0.25 + 0.75 * (1 - k))
        p.setBrush(col)
        dr = r * 0.22
        p.drawEllipse(QPointF(cx + math.cos(a) * r * 0.72, cy + math.sin(a) * r * 0.72), dr, dr)
    p.restore()


def render(role, size, fill, line, frame=0, nframes=1):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    k = size / 32.0
    p.scale(k, k)
    hot = _draw(role, p, fill, line, frame, nframes)
    p.end()
    return img, (int(round(hot[0] * k)), int(round(hot[1] * k)))


def generate(name="Horyzont", force=False):
    """Zapisuje motyw w ~/.icons/<name> (jeśli go jeszcze nie ma). Zwraca ścieżkę."""
    fill, line = VARIANTS.get(name, VARIANTS["Horyzont"])
    base = os.path.join(os.path.expanduser("~/.icons"), name)
    cdir = os.path.join(base, "cursors")
    marker = os.path.join(base, ".horyzont-v1")
    if os.path.exists(marker) and not force:
        return base
    os.makedirs(cdir, exist_ok=True)
    for role, _, names in xcursor.ROLES:
        frames = []
        anim = role in ("busy", "working")
        nf = 8 if anim else 1
        for size in SIZES:
            for fr in range(nf):
                img, hot = render(role, size, fill, line, fr, nf)
                frames.append(xcursor.Frame(img, hot[0], hot[1], 90 if anim else 0, size))
        target = os.path.join(cdir, names[0])
        if os.path.lexists(target):
            os.remove(target)
        xcursor.write_xcursor(target, frames)
        for alias in names[1:]:
            ap = os.path.join(cdir, alias)
            if os.path.lexists(ap):
                os.remove(ap)
            os.symlink(names[0], ap)
    with open(os.path.join(base, "index.theme"), "w", encoding="utf-8") as f:
        f.write(f"[Icon Theme]\nName={name.replace('-', ' ')}\nComment=Horyzont — oryginalne wskaźniki\nInherits=Adwaita\n")
    open(marker, "w").close()
    return base
