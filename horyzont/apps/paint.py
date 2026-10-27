"""Paint — prosty edytor grafiki rastrowej (narzędzia, paleta, zaznaczenia, przekształcenia obrazu)."""
import math
import os
import random
import sys
from array import array

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QImage, QImageReader, QImageWriter,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygon, QPolygonF, QTransform)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QColorDialog, QComboBox, QDialog,
                               QFontComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMenuBar, QPushButton, QRadioButton, QScrollArea, QSpinBox, QStatusBar, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .. import config
from ..common import dialogs
from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow

PALETTE = ["#000000", "#808080", "#800000", "#808000", "#008000", "#008080", "#000080", "#800080",
           "#808040", "#004040", "#0080ff", "#004080", "#8000ff", "#804000",
           "#ffffff", "#c0c0c0", "#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#ff00ff",
           "#ffff80", "#00ff80", "#80ffff", "#8080ff", "#ff0080", "#ff8040"]

TOOLS = [
    ("freeselect", "Zaznacz dowolny kształt", "Free-Form Select"),
    ("select", "Zaznacz", "Select"),
    ("eraser", "Gumka/gumka kolorowa", "Eraser/Color Eraser"),
    ("fill", "Wypełnij kolorem", "Fill With Color"),
    ("picker", "Wybierz kolor", "Pick Color"),
    ("magnifier", "Lupa", "Magnifier"),
    ("pencil", "Ołówek", "Pencil"),
    ("brush", "Pędzel", "Brush"),
    ("airbrush", "Aerograf", "Airbrush"),
    ("text", "Tekst", "Text"),
    ("line", "Linia", "Line"),
    ("curve", "Krzywa", "Curve"),
    ("rect", "Prostokąt", "Rectangle"),
    ("polygon", "Wielokąt", "Polygon"),
    ("ellipse", "Elipsa", "Ellipse"),
    ("roundrect", "Zaokrąglony prostokąt", "Rounded Rectangle"),
]

HINTS = {
    "freeselect": ("Zaznacza obszar obrazu o dowolnym kształcie.", "Selects a free-form part of the picture."),
    "select": ("Zaznacza prostokątny obszar obrazu, aby go przenieść, skopiować lub edytować.",
               "Selects a rectangular part of the picture to move, copy, or edit."),
    "eraser": ("Wymazuje fragment obrazu kolorem tła (prawy przycisk: zamienia tylko kolor pierwszoplanowy).",
               "Erases a portion of the picture, using the background color."),
    "fill": ("Wypełnia obszar bieżącym kolorem.", "Fills an area with the current drawing color."),
    "picker": ("Pobiera kolor z obrazu.", "Picks up a color from the picture for drawing."),
    "magnifier": ("Zmienia powiększenie.", "Changes the magnification."),
    "pencil": ("Rysuje linię o grubości jednego piksela.", "Draws a free-form line one pixel wide."),
    "brush": ("Rysuje pędzlem o wybranym kształcie i rozmiarze.", "Draws using a brush with the selected shape and size."),
    "airbrush": ("Rysuje aerografem o wybranym rozmiarze.", "Draws using an airbrush of the selected size."),
    "text": ("Wstawia tekst do obrazu.", "Inserts text into the picture."),
    "line": ("Rysuje linię prostą o wybranej grubości.", "Draws a straight line with the selected line width."),
    "curve": ("Rysuje krzywą o wybranej grubości.", "Draws a curved line with the selected line width."),
    "rect": ("Rysuje prostokąt w wybranym stylu wypełnienia.", "Draws a rectangle with the selected fill style."),
    "polygon": ("Rysuje wielokąt w wybranym stylu wypełnienia.", "Draws a polygon with the selected fill style."),
    "ellipse": ("Rysuje elipsę w wybranym stylu wypełnienia.", "Draws an ellipse with the selected fill style."),
    "roundrect": ("Rysuje zaokrąglony prostokąt w wybranym stylu wypełnienia.",
                  "Draws a rounded rectangle with the selected fill style."),
}

BRUSHES = [("circle", 7), ("circle", 4), ("circle", 1), ("square", 8), ("square", 5), ("square", 2),
           ("slash", 8), ("slash", 5), ("slash", 3), ("backslash", 8), ("backslash", 5), ("backslash", 3)]
ZOOMS = [1, 2, 4, 6, 8]


def image_filter():
    return ";;".join([
        T("Mapa bitowa 24-bitowa (*.bmp *.dib)", "24-bit Bitmap (*.bmp *.dib)"),
        "PNG (*.png)", "JPEG (*.jpg *.jpeg *.jpe *.jfif)", "GIF (*.gif)", "TIFF (*.tif *.tiff)",
        "WebP (*.webp)", T("Ikona (*.ico)", "Icon (*.ico)"),
        T("Wszystkie pliki obrazów", "All Picture Files") + " (*.bmp *.dib *.png *.jpg *.jpeg *.gif *.tif *.tiff *.webp *.ico *.xpm *.pbm *.pgm *.ppm *.svg)",
        T("Wszystkie pliki (*)", "All Files (*)"),
    ])


# ====================================================================== ikony narzędzi (oryginalne, rysowane)
def tool_icon(name, size=16):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    k = QColor("#202020")
    p.setPen(QPen(k, 1))
    if name == "freeselect":
        p.setPen(QPen(k, 1, Qt.DashLine))
        p.drawPath(_path([(3, 4), (8, 2), (13, 5), (11, 9), (14, 13), (6, 14), (2, 10)]))
        p.setPen(QPen(QColor("#b03020"), 1.5))
        p.drawLine(12, 13, 15, 10)
    elif name == "select":
        p.setPen(QPen(k, 1, Qt.DashLine))
        p.drawRect(2, 3, 12, 10)
    elif name == "eraser":
        p.setBrush(QColor("#f0c8d8"))
        p.drawPolygon(QPolygonF([QPointF(2, 11), QPointF(9, 4), QPointF(14, 9), QPointF(7, 15)]))
        p.setBrush(QColor("#4a74c8"))
        p.drawPolygon(QPolygonF([QPointF(2, 11), QPointF(5, 8), QPointF(10, 13), QPointF(7, 15)]))
    elif name == "fill":
        p.setBrush(QColor("#d8d8d8"))
        p.drawPolygon(QPolygonF([QPointF(3, 8), QPointF(8, 3), QPointF(13, 8), QPointF(8, 13)]))
        p.setPen(QPen(QColor("#1d6fd6"), 2))
        p.drawLine(13, 9, 14, 14)
    elif name == "picker":
        p.setPen(QPen(k, 1.2))
        p.drawLine(3, 13, 10, 6)
        p.setBrush(QColor("#303030"))
        p.drawEllipse(QRectF_(10, 2, 5, 5))
    elif name == "magnifier":
        p.setPen(QPen(k, 1.5))
        p.setBrush(QColor(200, 230, 255))
        p.drawEllipse(2, 2, 8, 8)
        p.setPen(QPen(QColor("#6b4a20"), 2.5))
        p.drawLine(10, 10, 14, 14)
    elif name == "pencil":
        p.setBrush(QColor("#f2c94c"))
        p.drawPolygon(QPolygonF([QPointF(3, 13), QPointF(4, 10), QPointF(12, 2), QPointF(14, 4), QPointF(6, 12)]))
        p.setBrush(QColor("#303030"))
        p.drawPolygon(QPolygonF([QPointF(3, 13), QPointF(4, 10), QPointF(6, 12)]))
    elif name == "brush":
        p.setPen(QPen(QColor("#7a4a20"), 2))
        p.drawLine(9, 7, 14, 2)
        p.setBrush(QColor("#2a2a2a"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(2, 14), QPointF(5, 8), QPointF(9, 6), QPointF(10, 9), QPointF(7, 12)]))
    elif name == "airbrush":
        p.setBrush(QColor("#9aa8b8"))
        p.drawRect(7, 6, 6, 8)
        p.drawRect(8, 3, 2, 3)
        p.setPen(QPen(QColor("#1d6fd6"), 1))
        for x, y in ((3, 3), (2, 6), (4, 5), (5, 2), (1, 4), (4, 8)):
            p.drawPoint(x, y)
    elif name == "text":
        f = QFont("serif")
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, "A")
    elif name == "line":
        p.setPen(QPen(k, 1.5))
        p.drawLine(2, 14, 14, 2)
    elif name == "curve":
        path = QPainterPath(QPointF(2, 13))
        path.cubicTo(QPointF(4, 0), QPointF(10, 18), QPointF(14, 3))
        p.setPen(QPen(k, 1.5))
        p.drawPath(path)
    elif name == "rect":
        p.drawRect(2, 4, 12, 9)
    elif name == "polygon":
        p.drawPolygon(QPolygonF([QPointF(2, 6), QPointF(8, 2), QPointF(14, 7), QPointF(11, 14), QPointF(4, 13)]))
    elif name == "ellipse":
        p.drawEllipse(1, 4, 14, 9)
    elif name == "roundrect":
        p.drawRoundedRect(2, 4, 12, 9, 3, 3)
    p.end()
    return pm


def QRectF_(x, y, w, h):
    from PySide6.QtCore import QRectF
    return QRectF(x, y, w, h)


def _path(points):
    path = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    path.closeSubpath()
    return path


# ====================================================================== wypełnianie
def flood_fill(img, x, y, color):
    """Wypełnienie obszaru tego samego koloru (metoda linii poziomych). Zwraca True, gdy coś zmieniono."""
    w, h = img.width(), img.height()
    if not (0 <= x < w and 0 <= y < h):
        return False
    if img.format() != QImage.Format_RGB32:
        conv = img.convertToFormat(QImage.Format_RGB32)
        img.swap(conv)
    bpl = img.bytesPerLine() // 4
    ptr = img.bits()
    buf = memoryview(ptr).cast("I")
    target = buf[y * bpl + x]
    new = QColor(color).rgb() | 0xFF000000
    target |= 0xFF000000
    if (target & 0xFFFFFF) == (new & 0xFFFFFF):
        return False
    rows = [array("I", bytes(buf[r * bpl:r * bpl + w])) for r in range(h)]
    stack = [(x, y)]
    while stack:
        sx, sy = stack.pop()
        row = rows[sy]
        if (row[sx] | 0xFF000000) != target:
            continue
        lx = sx
        while lx > 0 and (row[lx - 1] | 0xFF000000) == target:
            lx -= 1
        rx = sx
        while rx < w - 1 and (row[rx + 1] | 0xFF000000) == target:
            rx += 1
        row[lx:rx + 1] = array("I", [new]) * (rx - lx + 1)
        for ny in (sy - 1, sy + 1):
            if 0 <= ny < h:
                nrow = rows[ny]
                i = lx
                while i <= rx:
                    if (nrow[i] | 0xFF000000) == target:
                        stack.append((i, ny))
                        while i <= rx and (nrow[i] | 0xFF000000) == target:
                            i += 1
                    i += 1
    for r in range(h):
        buf[r * bpl:r * bpl + w] = rows[r]
    return True


# ====================================================================== płótno
class Canvas(QWidget):
    """Obraz w powiększeniu + uchwyty zmiany rozmiaru. Rysowanie wykonuje okno (PaintWindow)."""

    HANDLE = 3

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self._resizing = None
        self._resize_preview = None

    def img_rect(self):
        z = self.win.zoom
        return QRect(0, 0, self.win.image.width() * z, self.win.image.height() * z)

    def sizeHint(self):
        r = self.img_rect()
        return QSize(r.width() + 8, r.height() + 8)

    def update_size(self):
        self.setFixedSize(self.sizeHint())
        self.update()

    def _handles(self):
        r = self.img_rect()
        H = self.HANDLE
        return {
            "r": QRect(r.right() + 1, r.center().y() - H // 2, H, H),
            "b": QRect(r.center().x() - H // 2, r.bottom() + 1, H, H),
            "rb": QRect(r.right() + 1, r.bottom() + 1, H, H),
        }

    def to_img(self, pos):
        z = self.win.zoom
        return QPoint(math.floor(pos.x() / z), math.floor(pos.y() / z))

    def paintEvent(self, e):
        p = QPainter(self)
        w = self.win
        z = w.zoom
        img = w.work if w.work is not None else w.image
        r = self.img_rect()
        clip = e.rect().intersected(r)
        if not clip.isEmpty():
            src = QRect(clip.x() // z, clip.y() // z, clip.width() // z + 2, clip.height() // z + 2)
            p.drawImage(QRect(src.x() * z, src.y() * z, src.width() * z, src.height() * z), img, src)
        # zaznaczenie pływające
        if w.sel is not None:
            sx, sy = w.sel_pos.x() * z, w.sel_pos.y() * z
            p.drawImage(QRect(sx, sy, w.sel_img.width() * z, w.sel_img.height() * z), w.sel_display())
        # siatka przy dużym powiększeniu
        if w.show_grid and z >= 4:
            p.setPen(QColor(128, 128, 128, 110))
            for x in range(clip.left() - clip.left() % z, clip.right() + 1, z):
                p.drawLine(x, clip.top(), x, clip.bottom())
            for y in range(clip.top() - clip.top() % z, clip.bottom() + 1, z):
                p.drawLine(clip.left(), y, clip.right(), y)
        # ramka zaznaczenia
        if w.sel is not None or w.sel_drag_rect is not None:
            if w.sel is not None:
                rr = QRect(w.sel_pos.x() * z, w.sel_pos.y() * z, w.sel_img.width() * z, w.sel_img.height() * z)
            else:
                d = w.sel_drag_rect.normalized()
                rr = QRect(d.x() * z, d.y() * z, d.width() * z, d.height() * z)
            pen = QPen(QColor("#000000"), 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(rr.adjusted(0, 0, -1, -1))
            if w.sel_path is not None and w.sel is not None:
                p.save()
                p.translate(w.sel_pos.x() * z, w.sel_pos.y() * z)
                p.scale(z, z)
                p.setPen(QPen(QColor("#000000"), 0, Qt.DotLine))
                p.drawPath(w.sel_path)
                p.restore()
        if w.free_points:
            p.save()
            p.scale(z, z)
            p.setPen(QPen(QColor("#000000"), 0, Qt.DotLine))
            p.drawPolyline(QPolygon(w.free_points))
            p.restore()
        # uchwyty
        p.setPen(QColor("#00008b"))
        p.setBrush(QColor("#00008b"))
        for hr in self._handles().values():
            p.drawRect(hr.adjusted(0, 0, -1, -1))
        if self._resize_preview is not None:
            p.setPen(QPen(QColor("#000000"), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            rp = self._resize_preview
            p.drawRect(0, 0, rp.width() * z - 1, rp.height() * z - 1)

    def _handle_at(self, pos):
        for k, r in self._handles().items():
            if r.adjusted(-2, -2, 2, 2).contains(pos):
                return k
        return None

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        h = self._handle_at(pos)
        if h and e.button() == Qt.LeftButton:
            self._resizing = h
            self._resize_preview = QSize(self.win.image.size())
            return
        self.win.canvas_press(self.to_img(pos), e.button(), e.modifiers(), pos)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._resizing:
            z = self.win.zoom
            w = max(1, round(pos.x() / z)) if "r" in self._resizing else self.win.image.width()
            h = max(1, round(pos.y() / z)) if "b" in self._resizing else self.win.image.height()
            self._resize_preview = QSize(w, h)
            self.win.status_size.setText(f"{w}x{h}")
            self.update()
            return
        h = self._handle_at(pos)
        if h:
            self.setCursor({"r": Qt.SizeHorCursor, "b": Qt.SizeVerCursor, "rb": Qt.SizeFDiagCursor}[h])
        else:
            self.setCursor(self.win.tool_cursor())
        self.win.canvas_move(self.to_img(pos), e.buttons(), e.modifiers())

    def mouseReleaseEvent(self, e):
        if self._resizing:
            size = self._resize_preview
            self._resizing = None
            self._resize_preview = None
            if size != self.win.image.size():
                self.win.resize_canvas(size.width(), size.height())
            self.update()
            return
        self.win.canvas_release(self.to_img(e.position().toPoint()), e.button(), e.modifiers())

    def mouseDoubleClickEvent(self, e):
        self.win.canvas_double(self.to_img(e.position().toPoint()), e.button())

    def leaveEvent(self, e):
        self.win.status_pos.setText("")


# ====================================================================== pasek narzędzi
class ToolBox(QFrame):
    tool_changed = Signal(str)

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)
        grid = QGridLayout()
        grid.setSpacing(1)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for i, (key, pl, en) in enumerate(TOOLS):
            b = QToolButton()
            b.setIcon(tool_icon(key))
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(25, 25)
            b.setCheckable(True)
            b.setToolTip(T(pl, en))
            b.setAutoRaise(False)
            self.group.addButton(b)
            self.buttons[key] = b
            b.clicked.connect(lambda _=False, k=key: self.tool_changed.emit(k))
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        self.options = ToolOptions(win)
        lay.addWidget(self.options, 0, Qt.AlignHCenter)
        lay.addStretch(1)
        self.setFixedWidth(58)

    def set_tool(self, key):
        self.buttons[key].setChecked(True)
        self.options.update()


class ToolOptions(QFrame):
    """Pole opcji pod narzędziami: grubość linii, kształt pędzla, styl wypełnienia, rozmiar gumki…"""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Sunken)
        self.setFixedSize(42, 66)

    def _items(self):
        w = self.win
        t = w.tool
        r = self.contentsRect()
        if t in ("select", "freeselect", "text"):
            return [("opaque", False, QRect(r.x() + 3, r.y() + 3, 34, 28)), ("opaque", True, QRect(r.x() + 3, r.y() + 33, 34, 28))]
        if t == "magnifier":
            return [("zoom", z, QRect(r.x() + 3, r.y() + 3 + i * 12, 34, 12)) for i, z in enumerate((1, 2, 6, 8))]
        if t in ("line", "curve"):
            return [("width", n, QRect(r.x() + 3, r.y() + 3 + i * 12, 34, 12)) for i, n in enumerate((1, 2, 3, 4, 5))]
        if t == "eraser":
            return [("eraser", n, QRect(r.x() + 3, r.y() + 3 + i * 15, 34, 15)) for i, n in enumerate((4, 6, 8, 10))]
        if t == "brush":
            out = []
            for i, b in enumerate(BRUSHES):
                out.append(("brush", i, QRect(r.x() + 2 + (i % 3) * 12, r.y() + 3 + (i // 3) * 15, 12, 15)))
            return out
        if t == "airbrush":
            return [("air", 0, QRect(r.x() + 2, r.y() + 2, 18, 22)), ("air", 1, QRect(r.x() + 20, r.y() + 2, 18, 22)),
                    ("air", 2, QRect(r.x() + 4, r.y() + 26, 34, 34))]
        if t in ("rect", "ellipse", "roundrect", "polygon"):
            return [("fill", n, QRect(r.x() + 3, r.y() + 3 + n * 20, 34, 19)) for n in range(3)]
        return []

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        w = self.win
        hl = self.palette().highlight().color()
        for kind, val, r in self._items():
            sel = {"opaque": w.transparent == val, "zoom": w.zoom == val, "width": w.line_width == val,
                   "eraser": w.eraser_size == val, "brush": w.brush_index == val, "air": w.air_index == val,
                   "fill": w.fill_style == val}[kind]
            if sel:
                p.fillRect(r, hl)
            fg = QColor("#ffffff") if sel else QColor("#000000")
            p.setPen(fg)
            p.setBrush(fg)
            c = r.center()
            if kind == "width":
                p.fillRect(QRect(r.x() + 4, c.y() - val // 2, r.width() - 8, val), fg)
            elif kind == "zoom":
                p.setFont(QFont(self.font().family(), 7))
                p.drawText(r, Qt.AlignCenter, f"{val}x")
            elif kind == "eraser":
                p.fillRect(QRect(c.x() - val // 2, c.y() - val // 2, val, val), fg)
            elif kind == "brush":
                shape, size = BRUSHES[val]
                self._brush_shape(p, c, shape, size, fg)
            elif kind == "air":
                rnd = random.Random(val)
                rad = (4, 7, 12)[val]
                for _ in range(10 + val * 12):
                    a, d = rnd.random() * 6.283, rnd.random() * rad
                    p.drawPoint(int(c.x() + math.cos(a) * d), int(c.y() + math.sin(a) * d))
            elif kind == "fill":
                rr = r.adjusted(5, 4, -5, -4)
                p.setPen(QColor("#000000") if not sel else fg)
                if val == 0:
                    p.setBrush(Qt.NoBrush)
                elif val == 1:
                    p.setBrush(QColor("#808080"))
                else:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor("#808080"))
                p.drawRect(rr)
            elif kind == "opaque":
                p.setPen(Qt.NoPen)
                rr = r.adjusted(4, 3, -4, -3)
                if not val:
                    p.setBrush(QColor("#ffffff"))
                    p.drawRect(rr)
                p.setBrush(QColor("#c03030"))
                p.drawEllipse(rr.adjusted(3, 3, -12, -8))
                p.setBrush(QColor("#2a62c4"))
                p.drawRect(rr.adjusted(12, 8, -2, -2))

    @staticmethod
    def _brush_shape(p, c, shape, size, color):
        p.setPen(color)
        p.setBrush(color)
        if shape == "circle":
            p.drawEllipse(c, max(1, size // 2), max(1, size // 2))
        elif shape == "square":
            p.fillRect(QRect(c.x() - size // 2, c.y() - size // 2, size, size), color)
        elif shape == "slash":
            p.drawLine(c.x() - size // 2, c.y() + size // 2, c.x() + size // 2, c.y() - size // 2)
        else:
            p.drawLine(c.x() - size // 2, c.y() - size // 2, c.x() + size // 2, c.y() + size // 2)

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        w = self.win
        for kind, val, r in self._items():
            if r.contains(pos):
                if kind == "opaque":
                    w.transparent = val
                elif kind == "zoom":
                    w.set_zoom(val)
                elif kind == "width":
                    w.line_width = val
                elif kind == "eraser":
                    w.eraser_size = val
                elif kind == "brush":
                    w.brush_index = val
                elif kind == "air":
                    w.air_index = val
                elif kind == "fill":
                    w.fill_style = val
                self.update()
                w.canvas.update()
                return


class ColorBox(QFrame):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(40)
        self.cells = []

    def paintEvent(self, e):
        p = QPainter(self)
        w = self.win
        # bieżące kolory
        box = QRect(4, 4, 30, 30)
        p.fillRect(box, QColor("#ffffff"))
        p.setPen(QColor("#808080"))
        p.drawRect(box)
        p.fillRect(QRect(15, 15, 13, 13), w.bg)
        p.setPen(QColor("#000000"))
        p.drawRect(QRect(15, 15, 13, 13))
        p.fillRect(QRect(9, 9, 13, 13), w.fg)
        p.drawRect(QRect(9, 9, 13, 13))
        self.cells = []
        for i, c in enumerate(w.palette_colors):
            col, row = i % 14, i // 14
            r = QRect(38 + col * 16, 4 + row * 16, 15, 15)
            p.fillRect(r, QColor(c))
            p.setPen(QColor("#808080"))
            p.drawLine(r.topLeft(), r.topRight())
            p.drawLine(r.topLeft(), r.bottomLeft())
            p.setPen(QColor("#ffffff"))
            p.drawLine(r.bottomLeft(), r.bottomRight())
            p.drawLine(r.topRight(), r.bottomRight())
            self.cells.append((r, i))

    def _cell(self, pos):
        for r, i in self.cells:
            if r.contains(pos):
                return i
        return -1

    def mousePressEvent(self, e):
        i = self._cell(e.position().toPoint())
        if i < 0:
            return
        c = QColor(self.win.palette_colors[i])
        if e.button() == Qt.RightButton:
            self.win.bg = c
        else:
            self.win.fg = c
        self.update()

    def mouseDoubleClickEvent(self, e):
        i = self._cell(e.position().toPoint())
        if i >= 0:
            self.win.edit_colors(i)


class TextBar(QFrame):
    """Pasek „Czcionki” dla narzędzia Tekst."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.addWidget(QLabel(T("Czcionki:", "Fonts:")))
        self.family = QFontComboBox()
        self.size = QComboBox()
        self.size.setEditable(True)
        for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28, 36, 48, 72):
            self.size.addItem(str(s))
        self.size.setCurrentText("12")
        self.size.setFixedWidth(60)
        self.bold = QToolButton()
        self.bold.setText("B")
        self.italic = QToolButton()
        self.italic.setText("I")
        self.under = QToolButton()
        self.under.setText("U")
        f = self.bold.font()
        f.setBold(True)
        self.bold.setFont(f)
        f = self.italic.font()
        f.setItalic(True)
        self.italic.setFont(f)
        f = self.under.font()
        f.setUnderline(True)
        self.under.setFont(f)
        lay.addWidget(self.family)
        lay.addWidget(self.size)
        for b in (self.bold, self.italic, self.under):
            b.setCheckable(True)
            b.setFixedSize(24, 22)
            lay.addWidget(b)
            b.toggled.connect(lambda *_: self.win.text_font_changed())
        lay.addStretch(1)
        self.family.currentFontChanged.connect(lambda *_: self.win.text_font_changed())
        self.size.currentTextChanged.connect(lambda *_: self.win.text_font_changed())

    def font(self):
        f = QFont(self.family.currentFont())
        try:
            f.setPixelSize(max(4, int(int(self.size.currentText() or "12") * 96 / 72)))
        except ValueError:
            f.setPixelSize(16)
        f.setBold(self.bold.isChecked())
        f.setItalic(self.italic.isChecked())
        f.setUnderline(self.under.isChecked())
        return f


# ====================================================================== okna dialogowe
class AttributesDialog(HDialog):
    def __init__(self, win):
        super().__init__(T("Atrybuty", "Attributes"), "paint", win)
        self.win = win
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        info = QLabel(T("Ostatnio zapisany plik:", "File last saved:") + " " +
                      (_mtime(win.path) if win.path else T("niedostępne", "Not Available")) + "\n" +
                      T("Rozmiar na dysku:", "Size on disk:") + " " +
                      (f"{os.path.getsize(win.path):,} B".replace(",", " ") if win.path and os.path.exists(win.path) else
                       T("niedostępne", "Not Available")))
        lay.addWidget(info)
        g = QGridLayout()
        g.addWidget(QLabel(T("&Szerokość:", "&Width:")), 0, 0)
        self.w = QSpinBox()
        self.w.setRange(1, 20000)
        self.w.setValue(win.image.width())
        g.addWidget(self.w, 0, 1)
        g.addWidget(QLabel(T("&Wysokość:", "&Height:")), 0, 2)
        self.h = QSpinBox()
        self.h.setRange(1, 20000)
        self.h.setValue(win.image.height())
        g.addWidget(self.h, 0, 3)
        lay.addLayout(g)
        units = QGroupBox(T("Jednostki", "Units"))
        ul = QHBoxLayout(units)
        for t in (T("Cale", "Inches"), T("Centymetry", "Cm"), T("Piksele", "Pixels")):
            rb = QRadioButton(t)
            rb.setChecked(t in ("Piksele", "Pixels"))
            rb.setEnabled(t in ("Piksele", "Pixels"))
            ul.addWidget(rb)
        lay.addWidget(units)
        colors = QGroupBox(T("Kolory", "Colors"))
        cl = QHBoxLayout(colors)
        self.bw = QRadioButton(T("&Czarno-biały", "&Black and white"))
        self.col = QRadioButton(T("Kol&ory", "Co&lors"))
        self.col.setChecked(True)
        cl.addWidget(self.bw)
        cl.addWidget(self.col)
        lay.addWidget(colors)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, fn in ((T("OK", "OK"), self.accept), (T("Anuluj", "Cancel"), self.reject),
                         (T("&Domyślne", "&Default"), self._default)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

    def _default(self):
        scr = QApplication.primaryScreen().geometry()
        self.w.setValue(min(scr.width(), 1024) - 300)
        self.h.setValue(min(scr.height(), 768) - 300)


def _mtime(path):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "—"


class FlipDialog(HDialog):
    def __init__(self, win):
        super().__init__(T("Przerzucanie i obracanie", "Flip and Rotate"), "paint", win)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        box = QGroupBox(T("Przerzuć lub obróć", "Flip or rotate"))
        bl = QVBoxLayout(box)
        self.h = QRadioButton(T("Przerzuć w &poziomie", "&Flip horizontal"))
        self.v = QRadioButton(T("Przerzuć w p&ionie", "Flip &vertical"))
        self.r = QRadioButton(T("&Obróć o kąt", "&Rotate by angle"))
        self.h.setChecked(True)
        for w in (self.h, self.v, self.r):
            bl.addWidget(w)
        self.angles = QWidget()
        al = QVBoxLayout(self.angles)
        al.setContentsMargins(24, 0, 0, 0)
        self.a90 = QRadioButton("&90°")
        self.a180 = QRadioButton("&180°")
        self.a270 = QRadioButton("&270°")
        self.a90.setChecked(True)
        for w in (self.a90, self.a180, self.a270):
            al.addWidget(w)
        bl.addWidget(self.angles)
        self.angles.setEnabled(False)
        self.r.toggled.connect(self.angles.setEnabled)
        lay.addWidget(box)
        lay.addLayout(_ok_cancel(self))

    def result_op(self):
        if self.h.isChecked():
            return "fh"
        if self.v.isChecked():
            return "fv"
        return "r90" if self.a90.isChecked() else "r180" if self.a180.isChecked() else "r270"


class StretchDialog(HDialog):
    def __init__(self, win):
        super().__init__(T("Rozciąganie i pochylanie", "Stretch and Skew"), "paint", win)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        st = QGroupBox(T("Rozciąganie", "Stretch"))
        g = QGridLayout(st)
        self.sh = QSpinBox()
        self.sv = QSpinBox()
        for s in (self.sh, self.sv):
            s.setRange(1, 500)
            s.setValue(100)
            s.setSuffix(" %")
        g.addWidget(QLabel(T("W &poziomie:", "&Horizontal:")), 0, 0)
        g.addWidget(self.sh, 0, 1)
        g.addWidget(QLabel(T("W p&ionie:", "&Vertical:")), 1, 0)
        g.addWidget(self.sv, 1, 1)
        lay.addWidget(st)
        sk = QGroupBox(T("Pochylanie", "Skew"))
        g2 = QGridLayout(sk)
        self.kh = QSpinBox()
        self.kv = QSpinBox()
        for s in (self.kh, self.kv):
            s.setRange(-89, 89)
            s.setSuffix(" °")
        g2.addWidget(QLabel(T("W p&oziomie:", "H&orizontal:")), 0, 0)
        g2.addWidget(self.kh, 0, 1)
        g2.addWidget(QLabel(T("W pi&onie:", "V&ertical:")), 1, 0)
        g2.addWidget(self.kv, 1, 1)
        lay.addWidget(sk)
        lay.addLayout(_ok_cancel(self))


def _ok_cancel(dlg):
    row = QHBoxLayout()
    row.addStretch(1)
    ok = QPushButton(T("OK", "OK"))
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    ca = QPushButton(T("Anuluj", "Cancel"))
    ca.clicked.connect(dlg.reject)
    row.addWidget(ok)
    row.addWidget(ca)
    return row


class ViewBitmap(QWidget):
    """Widok → Wyświetl mapę bitową: sam obraz na całym ekranie, dowolny klawisz lub klik zamyka."""

    def __init__(self, img):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.img = img
        self.setCursor(Qt.BlankCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        r = self.img.rect()
        r.moveCenter(self.rect().center())
        p.drawImage(r.topLeft(), self.img)

    def mousePressEvent(self, e):
        self.close()

    def keyPressEvent(self, e):
        self.close()


# ====================================================================== okno główne
class PaintWindow(HWindow):
    def __init__(self, ctl, path=None):
        super().__init__("", "paint")
        self.ctl = ctl
        self.path = None
        self.modified = False
        self.image = QImage(*self._default_size(), QImage.Format_RGB32)
        self.image.fill(QColor("#ffffff"))
        self.work = None
        self.zoom = 1
        self.show_grid = False
        self.fg = QColor("#000000")
        self.bg = QColor("#ffffff")
        self.palette_colors = list(config.get("paint_palette", PALETTE)) if len(config.get("paint_palette", PALETTE)) == 28 else list(PALETTE)
        self.tool = "pencil"
        self.prev_tool = "pencil"
        self.line_width = 1
        self.eraser_size = 6
        self.brush_index = 1
        self.air_index = 1
        self.fill_style = 0
        self.transparent = False
        self.undo_stack = []
        self.redo_stack = []
        # zaznaczenie
        self.sel = None              # True, gdy istnieje pływające zaznaczenie
        self.sel_img = None
        self.sel_pos = QPoint()
        self.sel_src = None          # QRect albo None (gdy wklejone)
        self.sel_path = None         # kształt (zaznaczenie dowolne), we współrzędnych zaznaczenia
        self.sel_lifted = False
        self.sel_drag_rect = None
        self.free_points = []
        self._drag = None
        self._press = None
        self._button = None
        self._last = None
        self.curve = None
        self.poly = None
        self.text_edit = None
        self.text_rect = None
        self._air_timer = QTimer(self)
        self._air_timer.timeout.connect(self._air_tick)
        self._build()
        self.set_tool("pencil")
        self.resize(760, 560)
        if path:
            self.load(path)
        self._update_title()

    def _default_size(self):
        w, h = config.get("paint_size", [640, 480]) if isinstance(config.get("paint_size", None), list) else (640, 480)
        return int(w), int(h)

    # -------------------------------------------------------- budowa
    def _build(self):
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.text_bar = TextBar(self)
        self.text_bar.hide()
        lay.addWidget(self.text_bar)
        mid = QHBoxLayout()
        mid.setSpacing(0)
        self.toolbox = ToolBox(self)
        self.toolbox.tool_changed.connect(self.set_tool)
        mid.addWidget(self.toolbox)
        self.scroll = QScrollArea()
        self.scroll.setBackgroundRole(self.scroll.backgroundRole())
        self.scroll.setStyleSheet("QScrollArea { background: #808080; border: none; } "
                                  "QScrollArea > QWidget > QWidget { background: #808080; }")
        self.canvas = Canvas(self)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(3, 3, 3, 3)
        hl.addWidget(self.canvas, 0, Qt.AlignLeft | Qt.AlignTop)
        hl.addStretch(1)
        self.scroll.setWidget(holder)
        self.scroll.setWidgetResizable(True)
        mid.addWidget(self.scroll, 1)
        lay.addLayout(mid, 1)
        self.colorbox = ColorBox(self)
        lay.addWidget(self.colorbox)
        self.status = QStatusBar()
        self.status_hint = QLabel()
        self.status.addWidget(self.status_hint, 1)
        self.status_pos = QLabel()
        self.status_pos.setMinimumWidth(90)
        self.status_size = QLabel()
        self.status_size.setMinimumWidth(90)
        self.status.addPermanentWidget(self.status_pos)
        self.status.addPermanentWidget(self.status_size)
        lay.addWidget(self.status)
        self.canvas.update_size()
        self._build_menus()

    def _build_menus(self):
        mb = self.menubar
        m = mb.addMenu(T("&Plik", "&File"))
        act(m, T("&Nowy", "&New"), self.new, "Ctrl+N")
        act(m, T("&Otwórz…", "&Open..."), self.open_dialog, "Ctrl+O")
        act(m, T("&Zapisz", "&Save"), self.save, "Ctrl+S")
        act(m, T("Zapisz &jako…", "Save &As..."), self.save_as)
        m.addSeparator()
        act(m, T("&Drukuj…", "&Print..."), self.print_image, "Ctrl+P")
        m.addSeparator()
        act(m, T("Ustaw jako tło pulpitu (&sąsiadująco)", "Set As Background (&Tiled)"), lambda: self.set_wallpaper("tile"))
        act(m, T("Ustaw jako tło pulpitu (&wyśrodkowane)", "Set As Background (Cen&tered)"), lambda: self.set_wallpaper("center"))
        m.addSeparator()
        act(m, T("&Zakończ", "E&xit"), self.close, "Alt+F4")
        m = mb.addMenu(T("&Edycja", "&Edit"))
        self.a_undo = act(m, T("&Cofnij", "&Undo"), self.undo, "Ctrl+Z")
        self.a_redo = act(m, T("&Ponów", "&Repeat"), self.redo, "Ctrl+Y")
        m.addSeparator()
        self.a_cut = act(m, T("Wy&tnij", "Cu&t"), self.cut, "Ctrl+X")
        self.a_copy = act(m, T("&Kopiuj", "&Copy"), self.copy, "Ctrl+C")
        act(m, T("&Wklej", "&Paste"), self.paste, "Ctrl+V")
        self.a_clear = act(m, T("Wy&czyść zaznaczenie", "C&lear Selection"), self.clear_selection, "Del")
        act(m, T("Zaznacz &wszystko", "Select &All"), self.select_all, "Ctrl+A")
        m.addSeparator()
        self.a_copy_to = act(m, T("Kopiuj &do…", "C&opy To..."), self.copy_to)
        act(m, T("Wklej &z…", "Paste &From..."), self.paste_from)
        m.aboutToShow.connect(self._update_edit)
        m = mb.addMenu(T("&Widok", "&View"))
        self.a_toolbox = act(m, T("&Pasek narzędzi", "&Tool Box"), self.toolbox.setVisible, "Ctrl+T", checkable=True, checked=True)
        self.a_colorbox = act(m, T("Pole &kolorów", "&Color Box"), self.colorbox.setVisible, "Ctrl+L", checkable=True, checked=True)
        self.a_status = act(m, T("Pasek &stanu", "&Status Bar"), self.status.setVisible, checkable=True, checked=True)
        self.a_textbar = act(m, T("Pasek narzędzi &tekstu", "T&ext Toolbar"), self._toggle_textbar, checkable=True, checked=True)
        m.addSeparator()
        zm = m.addMenu(T("Po&większenie", "&Zoom"))
        act(zm, T("&Normalny rozmiar", "&Normal Size"), lambda: self.set_zoom(1), "Ctrl+PgUp")
        act(zm, T("&Duży rozmiar", "&Large Size"), lambda: self.set_zoom(4), "Ctrl+PgDown")
        act(zm, T("&Niestandardowe…", "C&ustom..."), self.custom_zoom)
        zm.addSeparator()
        self.a_grid = act(zm, T("Pokaż &siatkę", "Show &Grid"), self._toggle_grid, "Ctrl+G", checkable=True)
        act(m, T("&Wyświetl mapę bitową", "&View Bitmap"), self.view_bitmap, "Ctrl+F")
        m = mb.addMenu(T("&Obraz", "&Image"))
        act(m, T("&Przerzuć/obróć…", "&Flip/Rotate..."), self.flip_rotate, "Ctrl+R")
        act(m, T("&Rozciągnij/pochyl…", "&Stretch/Skew..."), self.stretch_skew, "Ctrl+W")
        act(m, T("&Odwróć kolory", "&Invert Colors"), self.invert, "Ctrl+I")
        act(m, T("&Atrybuty…", "&Attributes..."), self.attributes, "Ctrl+E")
        act(m, T("&Wyczyść obraz", "&Clear Image"), self.clear_image, "Ctrl+Shift+N")
        self.a_opaque = act(m, T("&Rysuj nieprzezroczyste", "&Draw Opaque"), self._toggle_opaque, checkable=True, checked=True)
        m = mb.addMenu(T("&Kolory", "&Colors"))
        act(m, T("&Edytuj kolory…", "&Edit Colors..."), lambda: self.edit_colors(None))
        help_menu(mb, self, "Paint", "paint", "paint")

    def _update_edit(self):
        has = self.sel is not None
        self.a_cut.setEnabled(has)
        self.a_copy.setEnabled(has)
        self.a_clear.setEnabled(has)
        self.a_copy_to.setEnabled(has)
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))

    def _toggle_textbar(self, on):
        self.text_bar.setVisible(on and self.tool == "text")

    def _toggle_grid(self, on):
        self.show_grid = on
        self.canvas.update()

    def _toggle_opaque(self, on):
        self.transparent = not on
        self.toolbox.options.update()
        self.canvas.update()

    # -------------------------------------------------------- stan
    def _update_title(self):
        name = os.path.basename(self.path) if self.path else T("Bez tytułu", "untitled")
        self.setWindowTitle(f"{name} - Paint")

    def set_modified(self, v=True):
        self.modified = v

    def push_undo(self):
        self.undo_stack.append(self.image.copy())
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.set_modified()

    def undo(self):
        if self.text_edit is not None:
            self._cancel_text()
            return
        if self.sel is not None:
            self.drop_selection(commit=False)
        if not self.undo_stack:
            return
        self.redo_stack.append(self.image.copy())
        self.image = self.undo_stack.pop()
        self.canvas.update_size()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.image.copy())
        self.image = self.redo_stack.pop()
        self.canvas.update_size()

    # -------------------------------------------------------- narzędzia
    def set_tool(self, key):
        if key != self.tool:
            self._finish_pending()
            if key != "picker":
                self.prev_tool = key
        self.tool = key
        self.toolbox.set_tool(key)
        self.text_bar.setVisible(key == "text" and self.a_textbar.isChecked())
        self.status_hint.setText(T(*HINTS[key]))
        self.canvas.setCursor(self.tool_cursor())
        self.canvas.update()

    def _finish_pending(self):
        if self.sel is not None:
            self.drop_selection()
        if self.text_edit is not None:
            self._commit_text()
        if self.poly:
            self._commit_polygon(close=False)
        if self.curve:
            self._commit_curve()

    def tool_cursor(self):
        t = self.tool
        if t in ("select", "freeselect", "line", "curve", "rect", "polygon", "ellipse", "roundrect"):
            return Qt.CrossCursor
        if t == "text":
            return Qt.IBeamCursor
        if t == "magnifier":
            return Qt.PointingHandCursor
        if t == "eraser":
            sz = self.eraser_size * self.zoom
            pm = QPixmap(sz + 2, sz + 2)
            pm.fill(Qt.white)
            p = QPainter(pm)
            p.setPen(QColor("#000000"))
            p.drawRect(0, 0, sz + 1, sz + 1)
            p.end()
            return QCursor(pm)
        return Qt.CrossCursor

    def set_zoom(self, z):
        self._finish_pending()
        self.zoom = z
        self.canvas.update_size()
        self.toolbox.options.update()
        self.canvas.setCursor(self.tool_cursor())

    def custom_zoom(self):
        dlg = HDialog(T("Powiększenie niestandardowe", "Custom Zoom"), "paint", self)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel(T("Bieżące powiększenie:", "Current zoom:") + f" {self.zoom * 100}%"))
        box = QGroupBox(T("Powiększ do", "Zoom to"))
        bl = QGridLayout(box)
        grp = QButtonGroup(dlg)
        for i, z in enumerate(ZOOMS):
            rb = QRadioButton(f"{z * 100}%")
            rb.setChecked(z == self.zoom)
            grp.addButton(rb, z)
            bl.addWidget(rb, i // 3, i % 3)
        lay.addWidget(box)
        lay.addLayout(_ok_cancel(dlg))
        if dlg.exec() == QDialog.Accepted and grp.checkedId() > 0:
            self.set_zoom(grp.checkedId())

    # -------------------------------------------------------- rysowanie
    def _painter(self, img=None):
        p = QPainter(img if img is not None else self.image)
        p.setRenderHint(QPainter.Antialiasing, False)
        return p

    def _color(self, button, swap=False):
        right = button == Qt.RightButton
        if swap:
            right = not right
        return self.bg if right else self.fg

    def _pen(self, color, width):
        return QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def _stamp_brush(self, p, pt, color):
        shape, size = BRUSHES[self.brush_index]
        if shape == "circle":
            if size <= 1:
                p.setPen(color)
                p.drawPoint(pt)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                r = size / 2
                p.drawEllipse(QPointF(pt.x() + 0.5, pt.y() + 0.5), r, r)
        elif shape == "square":
            p.fillRect(QRect(pt.x() - size // 2, pt.y() - size // 2, size, size), color)
        else:
            p.setPen(QPen(color, 1))
            d = size // 2
            if shape == "slash":
                p.drawLine(pt.x() - d, pt.y() + d, pt.x() + d, pt.y() - d)
            else:
                p.drawLine(pt.x() - d, pt.y() - d, pt.x() + d, pt.y() + d)

    def _brush_line(self, a, b, color):
        p = self._painter()
        dx, dy = b.x() - a.x(), b.y() - a.y()
        n = max(abs(dx), abs(dy), 1)
        for i in range(n + 1):
            self._stamp_brush(p, QPoint(round(a.x() + dx * i / n), round(a.y() + dy * i / n)), color)
        p.end()

    def _erase_line(self, a, b, button):
        s = self.eraser_size
        dx, dy = b.x() - a.x(), b.y() - a.y()
        n = max(abs(dx), abs(dy), 1)
        if button == Qt.RightButton:
            # gumka kolorowa: zamienia tylko kolor pierwszoplanowy na kolor tła
            fgv, bgv = self.fg.rgb(), self.bg.rgb()
            for i in range(n + 1):
                cx, cy = round(a.x() + dx * i / n), round(a.y() + dy * i / n)
                for y in range(cy - s // 2, cy + s // 2):
                    if 0 <= y < self.image.height():
                        for x in range(cx - s // 2, cx + s // 2):
                            if 0 <= x < self.image.width() and self.image.pixel(x, y) == fgv:
                                self.image.setPixel(x, y, bgv)
            return
        p = self._painter()
        for i in range(n + 1):
            cx, cy = round(a.x() + dx * i / n), round(a.y() + dy * i / n)
            p.fillRect(QRect(cx - s // 2, cy - s // 2, s, s), self.bg)
        p.end()

    def _air_tick(self):
        if self._last is None:
            return
        rad = (4, 8, 12)[self.air_index]
        p = self._painter()
        p.setPen(self._air_color)
        for _ in range(6 + rad):
            a, d = random.random() * 6.2832, random.random() * rad
            p.drawPoint(int(self._last.x() + math.cos(a) * d), int(self._last.y() + math.sin(a) * d))
        p.end()
        self.canvas.update()

    def _shape_pen_brush(self, button):
        """(pióro, pędzel) wg stylu wypełnienia: obrys / obrys + wypełnienie tłem / samo wypełnienie."""
        main = self._color(button)
        other = self._color(button, swap=True)
        w = self.line_width
        if self.fill_style == 0:
            return self._pen(main, w), Qt.NoBrush
        if self.fill_style == 1:
            return self._pen(main, w), QBrush(other)
        return Qt.NoPen, QBrush(main)

    def _draw_shape(self, img, a, b, button, mods):
        p = self._painter(img)
        t = self.tool
        if t == "line":
            if mods & Qt.ShiftModifier:
                b = self._snap45(a, b)
            pen = QPen(self._color(button), self.line_width, Qt.SolidLine, Qt.SquareCap if self.line_width > 1 else Qt.FlatCap)
            p.setPen(pen)
            if a == b:
                p.drawPoint(a)
            else:
                p.drawLine(a, b)
        elif t in ("rect", "ellipse", "roundrect"):
            r = QRect(a, b).normalized()
            if mods & Qt.ShiftModifier:
                side = max(r.width(), r.height())
                r = QRect(a.x() if b.x() >= a.x() else a.x() - side, a.y() if b.y() >= a.y() else a.y() - side, side, side)
            pen, brush = self._shape_pen_brush(button)
            p.setPen(pen)
            p.setBrush(brush)
            if pen != Qt.NoPen:
                hw = self.line_width / 2
                rf = QRectF_(r.x() + hw - 0.5 + 0.5, r.y() + hw, max(0, r.width() - self.line_width + 1), max(0, r.height() - self.line_width + 1))
            else:
                rf = QRectF_(r.x(), r.y(), r.width() + 1, r.height() + 1)
            if t == "rect":
                p.drawRect(rf)
            elif t == "ellipse":
                p.setRenderHint(QPainter.Antialiasing, False)
                p.drawEllipse(rf)
            else:
                p.drawRoundedRect(rf, 8, 8)
        p.end()

    @staticmethod
    def _snap45(a, b):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        ang = math.atan2(dy, dx)
        step = round(ang / (math.pi / 4)) * (math.pi / 4)
        d = math.hypot(dx, dy)
        return QPoint(a.x() + round(math.cos(step) * d), a.y() + round(math.sin(step) * d))

    # -------------------------------------------------------- mysz na płótnie
    def canvas_press(self, pt, button, mods, wpos):
        if button not in (Qt.LeftButton, Qt.RightButton):
            return
        t = self.tool
        self._button = button
        self._press = pt
        self._last = pt
        if self.text_edit is not None and t == "text":
            if not self.text_rect.contains(pt):
                self._commit_text()
            return
        if t in ("select", "freeselect"):
            if self.sel is not None and self._in_selection(pt):
                if not self.sel_lifted:
                    self._lift_selection()
                if mods & Qt.ControlModifier:
                    # Ctrl+przeciągnięcie: kopia zostaje na miejscu
                    self.push_undo()
                    self._stamp_selection()
                self._drag = ("move", pt - self.sel_pos, bool(mods & Qt.ShiftModifier))
                return
            self.drop_selection()
            if t == "select":
                self.sel_drag_rect = QRect(pt, pt)
            else:
                self.free_points = [pt]
            self._drag = ("new",)
            return
        if t == "picker":
            if self.image.rect().contains(pt):
                c = QColor(self.image.pixel(pt))
                if button == Qt.RightButton:
                    self.bg = c
                else:
                    self.fg = c
                self.colorbox.update()
            self.set_tool(self.prev_tool if self.prev_tool != "picker" else "pencil")
            return
        if t == "magnifier":
            if self.zoom == 1:
                self.set_zoom(4)
                QTimer.singleShot(0, lambda: self._center_on(pt))
            else:
                self.set_zoom(1)
            return
        if t == "fill":
            self.push_undo()
            if not flood_fill(self.image, pt.x(), pt.y(), self._color(button)):
                self.undo_stack.pop()
            self.canvas.update()
            return
        if t == "text":
            self.sel_drag_rect = QRect(pt, pt)
            self._drag = ("text",)
            return
        if t == "polygon":
            if self.poly is None:
                self.poly = {"points": [pt, pt], "button": button}
                self.push_undo()
            else:
                self.poly["points"].append(pt)
            self._render_polygon()
            return
        if t == "curve":
            if self.curve is None:
                self.push_undo()
                self.curve = {"a": pt, "b": pt, "c1": None, "c2": None, "stage": 0, "button": button}
            else:
                st = self.curve["stage"]
                if st == 1:
                    self.curve["c1"] = pt
                    self.curve["c2"] = pt
                elif st == 2:
                    self.curve["c2"] = pt
            self._render_curve()
            return
        self.push_undo()
        if t == "pencil":
            p = self._painter()
            p.setPen(self._color(button))
            p.drawPoint(pt)
            p.end()
        elif t == "brush":
            self._brush_line(pt, pt, self._color(button))
        elif t == "eraser":
            self._erase_line(pt, pt, button)
        elif t == "airbrush":
            self._air_color = self._color(button)
            self._air_tick()
            self._air_timer.start(30)
        elif t in ("line", "rect", "ellipse", "roundrect"):
            self.work = self.image.copy()
            self._draw_shape(self.work, pt, pt, button, mods)
        self.canvas.update()

    def canvas_move(self, pt, buttons, mods):
        self.status_pos.setText(f"{pt.x()},{pt.y()}")
        t = self.tool
        if t == "polygon" and self.poly is not None:
            self.poly["points"][-1] = pt
            self._render_polygon()
            return
        if t == "curve" and self.curve is not None and buttons:
            st = self.curve["stage"]
            if st == 0:
                self.curve["b"] = pt
            elif st == 1:
                self.curve["c1"] = pt
                self.curve["c2"] = pt
            else:
                self.curve["c2"] = pt
            self._render_curve()
            return
        if not buttons or self._press is None:
            return
        button = self._button
        if t in ("select", "freeselect", "text") and self._drag:
            if self._drag[0] == "move":
                _, off, stamp = self._drag
                if stamp:
                    self._stamp_selection()
                self.sel_pos = pt - off
                self.set_modified()
            elif t == "freeselect" and self._drag[0] == "new":
                if pt != self.free_points[-1]:
                    self.free_points.append(pt)
            else:
                self.sel_drag_rect = QRect(self._press, pt)
                r = self.sel_drag_rect.normalized()
                self.status_size.setText(f"{r.width()}x{r.height()}")
            self.canvas.update()
            return
        if t == "pencil":
            p = self._painter()
            p.setPen(self._color(button))
            p.drawLine(self._last, pt)
            p.end()
        elif t == "brush":
            self._brush_line(self._last, pt, self._color(button))
        elif t == "eraser":
            self._erase_line(self._last, pt, button)
        elif t in ("line", "rect", "ellipse", "roundrect"):
            self.work = self.image.copy()
            self._draw_shape(self.work, self._press, pt, button, mods)
            r = QRect(self._press, pt).normalized()
            self.status_size.setText(f"{r.width()}x{r.height()}")
        self._last = pt
        self.canvas.update()

    def canvas_release(self, pt, button, mods):
        t = self.tool
        self._air_timer.stop()
        if t == "polygon" and self.poly is not None:
            return
        if t == "curve" and self.curve is not None:
            st = self.curve["stage"]
            self.curve["stage"] = st + 1
            if self.curve["stage"] >= 3:
                self._commit_curve()
            return
        if self._press is None:
            return
        if t in ("line", "rect", "ellipse", "roundrect") and self.work is not None:
            self.image = self.work
            self.work = None
        elif t in ("select", "freeselect") and self._drag:
            if self._drag[0] == "new":
                if t == "select" and self.sel_drag_rect is not None:
                    r = self.sel_drag_rect.normalized().intersected(self.image.rect())
                    self.sel_drag_rect = None
                    if r.width() > 1 and r.height() > 1:
                        self._make_selection(r)
                elif t == "freeselect" and len(self.free_points) > 2:
                    self._make_free_selection(self.free_points)
                self.free_points = []
        elif t == "text" and self._drag and self._drag[0] == "text":
            r = self.sel_drag_rect.normalized() if self.sel_drag_rect else QRect()
            self.sel_drag_rect = None
            if r.width() < 10 or r.height() < 10:
                r = QRect(pt, QSize(160, 40))
            self._start_text(r)
        self._drag = None
        self._press = None
        self.status_size.setText("")
        self.canvas.update()

    def canvas_double(self, pt, button):
        if self.tool == "polygon" and self.poly is not None:
            self._commit_polygon(close=True)

    def _center_on(self, pt):
        z = self.zoom
        self.scroll.ensureVisible(pt.x() * z, pt.y() * z, self.scroll.viewport().width() // 2,
                                  self.scroll.viewport().height() // 2)

    # -------------------------------------------------------- wielokąt i krzywa
    def _render_polygon(self):
        pts = self.poly["points"]
        self.work = self.image.copy()
        p = self._painter(self.work)
        p.setPen(QPen(self._color(self.poly["button"]), self.line_width))
        p.drawPolyline(QPolygon(pts))
        p.end()
        self.canvas.update()

    def _commit_polygon(self, close=True):
        pts = self.poly["points"]
        button = self.poly["button"]
        self.poly = None
        self.work = None
        if len(pts) < 2:
            return
        p = self._painter()
        if close:
            pen, brush = self._shape_pen_brush(button)
            p.setPen(pen)
            p.setBrush(brush)
            p.drawPolygon(QPolygon(pts))
        else:
            p.setPen(QPen(self._color(button), self.line_width))
            p.drawPolyline(QPolygon(pts))
        p.end()
        self.canvas.update()

    def _curve_path(self):
        c = self.curve
        path = QPainterPath(QPointF(c["a"]))
        if c["c1"] is None:
            path.lineTo(QPointF(c["b"]))
        else:
            path.cubicTo(QPointF(c["c1"]), QPointF(c["c2"] or c["c1"]), QPointF(c["b"]))
        return path

    def _render_curve(self):
        self.work = self.image.copy()
        p = self._painter(self.work)
        p.setPen(QPen(self._color(self.curve["button"]), self.line_width))
        p.drawPath(self._curve_path())
        p.end()
        self.canvas.update()

    def _commit_curve(self):
        if self.curve is None:
            return
        self._render_curve()
        self.image = self.work
        self.work = None
        self.curve = None
        self.canvas.update()

    # -------------------------------------------------------- tekst
    def _start_text(self, r):
        r = r.intersected(self.image.rect())
        if r.isEmpty():
            return
        self.text_rect = r
        z = self.zoom
        te = QTextEdit(self.canvas)
        te.setFrameShape(QFrame.NoFrame)
        te.setGeometry(r.x() * z, r.y() * z, r.width() * z, r.height() * z)
        te.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setAcceptRichText(False)
        te.document().setDocumentMargin(1)
        self.text_edit = te
        self.text_font_changed()
        te.show()
        te.setFocus()
        if not self.a_textbar.isChecked():
            self.a_textbar.setChecked(True)

    def text_font_changed(self):
        if self.text_edit is None:
            return
        f = self.text_bar.font()
        fz = QFont(f)
        fz.setPixelSize(f.pixelSize() * self.zoom)
        self.text_edit.setFont(fz)
        bg = "transparent" if self.transparent else self.bg.name()
        self.text_edit.setStyleSheet(f"QTextEdit {{ background: {bg}; color: {self.fg.name()}; "
                                     f"border: 1px dashed #000; }}")

    def _commit_text(self):
        te, r = self.text_edit, self.text_rect
        self.text_edit = None
        text = te.toPlainText()
        te.deleteLater()
        if not text.strip():
            return
        self.push_undo()
        p = self._painter()
        p.setRenderHint(QPainter.TextAntialiasing, True)
        if not self.transparent:
            p.fillRect(r, self.bg)
        p.setPen(self.fg)
        p.setFont(self.text_bar.font())
        p.drawText(r.adjusted(1, 1, -1, -1), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        p.end()
        self.canvas.update()

    def _cancel_text(self):
        te = self.text_edit
        self.text_edit = None
        te.deleteLater()

    # -------------------------------------------------------- zaznaczenia
    def _make_selection(self, r):
        self.sel = True
        self.sel_img = self.image.copy(r).convertToFormat(QImage.Format_ARGB32)
        self.sel_pos = r.topLeft()
        self.sel_src = QRect(r)
        self.sel_path = None
        self.sel_lifted = False
        self.status_size.setText(f"{r.width()}x{r.height()}")

    def _make_free_selection(self, pts):
        poly = QPolygon(pts)
        br = poly.boundingRect().intersected(self.image.rect())
        if br.width() < 2 or br.height() < 2:
            return
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(p - br.topLeft()) for p in pts]))
        path.closeSubpath()
        img = QImage(br.size(), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setClipPath(path)
        p.drawImage(0, 0, self.image, br.x(), br.y(), br.width(), br.height())
        p.end()
        self.sel = True
        self.sel_img = img
        self.sel_pos = br.topLeft()
        self.sel_src = QRect(br)
        self.sel_path = path
        self.sel_lifted = False

    def _in_selection(self, pt):
        return QRect(self.sel_pos, self.sel_img.size()).contains(pt)

    def _lift_selection(self):
        """Pierwsze przesunięcie zaznaczenia zostawia w jego miejscu kolor tła (jak w klasycznym Paincie)."""
        if self.sel_lifted:
            return
        self.push_undo()
        if self.sel_src is not None:
            p = self._painter()
            if self.sel_path is not None:
                p.translate(self.sel_src.topLeft())
                p.fillPath(self.sel_path, self.bg)
            else:
                p.fillRect(self.sel_src, self.bg)
            p.end()
        self.sel_lifted = True

    def sel_display(self):
        """Zaznaczenie do wyświetlenia — w trybie przezroczystym bez pikseli w kolorze tła."""
        if not self.transparent:
            return self.sel_img
        from PySide6.QtGui import QBitmap, QRegion
        out = self.sel_img.convertToFormat(QImage.Format_ARGB32).copy()
        mask = out.createMaskFromColor(QColor(self.bg).rgb() | 0xFF000000, Qt.MaskInColor)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.setClipRegion(QRegion(QBitmap.fromImage(mask)))
        p.fillRect(out.rect(), Qt.transparent)
        p.end()
        return out

    def _stamp_selection(self):
        p = self._painter()
        p.drawImage(self.sel_pos, self.sel_display())
        p.end()

    def drop_selection(self, commit=True):
        if self.sel is None:
            return
        if commit and (self.sel_lifted or self.sel_src is None):
            if self.sel_src is None and not self.sel_lifted:
                self.push_undo()
            self._stamp_selection()
        self.sel = None
        self.sel_img = None
        self.sel_src = None
        self.sel_path = None
        self.sel_lifted = False
        self.canvas.update()

    def select_all(self):
        self.set_tool("select")
        self.drop_selection()
        self._make_selection(self.image.rect())
        self.canvas.update()

    def copy(self):
        if self.sel is not None:
            QApplication.clipboard().setImage(self.sel_display())

    def cut(self):
        if self.sel is None:
            return
        self.copy()
        self.clear_selection()

    def clear_selection(self):
        if self.sel is None:
            return
        self._lift_selection()
        self.sel = None
        self.sel_img = None
        self.sel_path = None
        self.sel_src = None
        self.sel_lifted = False
        self.canvas.update()

    def paste(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            return
        self.paste_image(img)

    def paste_image(self, img):
        self._finish_pending()
        if img.width() > self.image.width() or img.height() > self.image.height():
            ans = dialogs.message(self, "Paint", T("Obraz w Schowku jest większy niż mapa bitowa.\nCzy chcesz powiększyć mapę bitową?",
                                                   "The image in the clipboard is larger than the bitmap.\nWould you like the bitmap enlarged?"),
                                  "question", ("yes", "no", "cancel"))
            if ans == "cancel":
                return
            if ans == "yes":
                self.resize_canvas(max(img.width(), self.image.width()), max(img.height(), self.image.height()))
        self.set_tool("select")
        self.sel = True
        self.sel_img = img.convertToFormat(QImage.Format_ARGB32)
        z = self.zoom
        self.sel_pos = QPoint(self.scroll.horizontalScrollBar().value() // z, self.scroll.verticalScrollBar().value() // z)
        self.sel_src = None
        self.sel_path = None
        self.sel_lifted = False
        self.set_modified()
        self.canvas.update()

    def copy_to(self):
        if self.sel is None:
            return
        f, _ = dialogs.save_file(self, T("Kopiuj do", "Copy To"), config.user_dir("PICTURES"), image_filter(), "*.png")
        if f:
            if not os.path.splitext(f)[1]:
                f += ".png"
            self.sel_display().save(f)

    def paste_from(self):
        f = dialogs.open_file(self, T("Wklej z", "Paste From"), config.user_dir("PICTURES"), image_filter())
        if f:
            img = QImage(f)
            if not img.isNull():
                self.paste_image(img)

    # -------------------------------------------------------- obraz
    def resize_canvas(self, w, h):
        self._finish_pending()
        self.push_undo()
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(self.bg)
        p = QPainter(img)
        p.drawImage(0, 0, self.image)
        p.end()
        self.image = img
        config.set("paint_size", [w, h])
        self.canvas.update_size()

    def _transform_target(self, fn):
        """Wykonuje przekształcenie na zaznaczeniu (jeśli jest) albo na całym obrazie."""
        if self.sel is not None:
            self._lift_selection()
            self.sel_img = fn(self.sel_img)
            self.sel_path = None
        else:
            self.push_undo()
            self.image = fn(self.image).convertToFormat(QImage.Format_RGB32)
        self.canvas.update_size()

    def flip_rotate(self):
        d = FlipDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        op = d.result_op()

        def fn(img):
            if op == "fh":
                return img.flipped(Qt.Horizontal) if hasattr(img, "flipped") else img.mirrored(True, False)
            if op == "fv":
                return img.flipped(Qt.Vertical) if hasattr(img, "flipped") else img.mirrored(False, True)
            ang = {"r90": 90, "r180": 180, "r270": 270}[op]
            return img.transformed(QTransform().rotate(ang))
        self._transform_target(fn)

    def stretch_skew(self):
        d = StretchDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        sh, sv = d.sh.value() / 100, d.sv.value() / 100
        kh, kv = d.kh.value(), d.kv.value()
        bg = QColor(self.bg)

        def fn(img):
            out = img
            if sh != 1 or sv != 1:
                out = out.scaled(max(1, round(out.width() * sh)), max(1, round(out.height() * sv)),
                                 Qt.IgnoreAspectRatio, Qt.FastTransformation)
            if kh or kv:
                t = QTransform().shear(math.tan(math.radians(kh)), math.tan(math.radians(kv)))
                r = t.mapRect(QRectF_(0, 0, out.width(), out.height())).toAlignedRect()
                res = QImage(r.size(), QImage.Format_ARGB32)
                res.fill(bg)
                p = QPainter(res)
                p.translate(-r.x(), -r.y())
                p.setTransform(t, True)
                p.drawImage(0, 0, out)
                p.end()
                out = res
            return out
        self._transform_target(fn)

    def invert(self):
        def fn(img):
            img = img.copy()
            img.invertPixels()
            return img
        self._transform_target(fn)

    def attributes(self):
        d = AttributesDialog(self)
        if d.exec() == QDialog.Accepted:
            w, h = d.w.value(), d.h.value()
            if (w, h) != (self.image.width(), self.image.height()):
                self.resize_canvas(w, h)
            if d.bw.isChecked():
                ans = dialogs.message(self, "Paint", T("Zamiana na czarno-biały obraz jest nieodwracalna. Kontynuować?",
                                                       "Converting to black and white cannot be undone. Continue?"),
                                      "warning", ("yes", "no"))
                if ans == "yes":
                    self.push_undo()
                    self.image = self.image.convertToFormat(QImage.Format_Mono, Qt.ThresholdDither).convertToFormat(QImage.Format_RGB32)
                    self.canvas.update()

    def clear_image(self):
        if self.sel is not None:
            self.clear_selection()
            return
        self.push_undo()
        self.image.fill(self.bg)
        self.canvas.update()

    def edit_colors(self, index):
        if index is None:
            # edycja koloru pierwszoplanowego (tak jak w klasycznym Paincie)
            index = next((i for i, c in enumerate(self.palette_colors) if QColor(c) == self.fg), 0)
        dlg = HDialog(T("Edytuj kolory", "Edit Colors"), "paint", self)
        cd = QColorDialog(QColor(self.palette_colors[index]), dlg)
        cd.setOption(QColorDialog.DontUseNativeDialog, True)
        cd.setWindowFlags(Qt.Widget)
        lay = QVBoxLayout(dlg.body())
        lay.addWidget(cd)
        cd.finished.connect(dlg.done)
        if dlg.exec() == QDialog.Accepted:
            c = cd.selectedColor()
            self.palette_colors[index] = c.name()
            self.fg = c
            config.set("paint_palette", self.palette_colors)
            self.colorbox.update()

    def view_bitmap(self):
        self._finish_pending()
        v = ViewBitmap(self.image)
        v.setGeometry(QApplication.primaryScreen().geometry())
        v.showFullScreen()
        self._viewer = v

    # -------------------------------------------------------- pliki
    def maybe_save(self):
        if not self.modified:
            return True
        name = self.path or T("Bez tytułu", "untitled")
        ans = dialogs.message(self, "Paint", T(f"Czy zapisać zmiany w pliku {name}?", f"Save changes to {name}?"),
                              "warning", ("yes", "no", "cancel"))
        if ans == "yes":
            return self.save()
        return ans == "no"

    def new(self):
        if not self.maybe_save():
            return
        self._finish_pending()
        self.image = QImage(*self._default_size(), QImage.Format_RGB32)
        self.image.fill(QColor("#ffffff"))
        self.path = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.modified = False
        self.canvas.update_size()
        self._update_title()

    def open_dialog(self):
        if not self.maybe_save():
            return
        start = os.path.dirname(self.path) if self.path else config.user_dir("PICTURES")
        f = dialogs.open_file(self, T("Otwórz", "Open"), start, image_filter())
        if f:
            self.load(f)

    def load(self, path):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            dialogs.message(self, "Paint", T(f"Programowi Paint nie można odczytać tego pliku.\n{path}\n\n{reader.errorString()}",
                                             f"Paint cannot read this file.\n{path}\n\n{reader.errorString()}"), "error")
            return False
        if img.hasAlphaChannel():
            flat = QImage(img.size(), QImage.Format_RGB32)
            flat.fill(QColor("#ffffff"))
            p = QPainter(flat)
            p.drawImage(0, 0, img)
            p.end()
            img = flat
        self._finish_pending()
        self.image = img.convertToFormat(QImage.Format_RGB32)
        self.path = os.path.abspath(path)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.modified = False
        self.canvas.update_size()
        self._update_title()
        from ..common.launcher import add_recent_document
        add_recent_document(self.path)
        return True

    def save(self):
        if not self.path:
            return self.save_as()
        ext = os.path.splitext(self.path)[1].lower().lstrip(".")
        if ext and ext.encode() not in [bytes(f).lower() for f in QImageWriter.supportedImageFormats()]:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        start = self.path or os.path.join(config.user_dir("PICTURES"), T("Bez tytułu", "untitled") + ".png")
        f, flt = dialogs.save_file(self, T("Zapisz jako", "Save As"), os.path.dirname(start), image_filter(),
                                   os.path.basename(start))
        if not f:
            return False
        if not os.path.splitext(f)[1]:
            exts = {"Mapa": ".bmp", "24-bit": ".bmp", "PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "TIFF": ".tif",
                    "WebP": ".webp", "Ikona": ".ico", "Icon": ".ico"}
            f += next((v for k, v in exts.items() if flt.startswith(k)), ".png")
        return self._write(f)

    def _write(self, path):
        self._finish_pending()
        ext = os.path.splitext(path)[1].lower()
        img = self.image
        if ext in (".jpg", ".jpeg", ".jpe", ".jfif", ".bmp", ".dib"):
            img = img.convertToFormat(QImage.Format_RGB888)
        quality = 90 if ext in (".jpg", ".jpeg", ".jpe", ".jfif", ".webp") else -1
        fmt = {".dib": "BMP", ".jpe": "JPG", ".jfif": "JPG"}.get(ext)
        ok = img.save(path, fmt, quality) if fmt else img.save(path, None, quality)
        if not ok:
            dialogs.message(self, "Paint", T(f"Nie można zapisać pliku {path}.", f"Cannot save {path}."), "error")
            return False
        self.path = os.path.abspath(path)
        self.modified = False
        self._update_title()
        return True

    def set_wallpaper(self, mode):
        if not self.path or self.modified:
            dialogs.message(self, "Paint", T("Najpierw zapisz obraz.", "Save the picture first."), "info")
            if not self.save():
                return
        config.update({"wallpaper": self.path, "wallpaper_mode": mode})

    def print_image(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter()
        if QPrintDialog(printer, self).exec() == QDialog.Accepted:
            p = QPainter(printer)
            r = p.viewport()
            size = self.image.size()
            size.scale(r.size(), Qt.KeepAspectRatio)
            p.setViewport(r.x(), r.y(), size.width(), size.height())
            p.setWindow(self.image.rect())
            p.drawImage(0, 0, self.image)
            p.end()

    # -------------------------------------------------------- zdarzenia okna
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self.poly is not None:
                self.poly = None
                self.work = None
                self.undo()
            elif self.curve is not None:
                self.curve = None
                self.work = None
                self.undo()
            elif self.sel is not None:
                self.drop_selection()
            self.canvas.update()
            return
        if e.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and self.sel is not None:
            self._lift_selection()
            d = {Qt.Key_Left: QPoint(-1, 0), Qt.Key_Right: QPoint(1, 0), Qt.Key_Up: QPoint(0, -1), Qt.Key_Down: QPoint(0, 1)}[e.key()]
            self.sel_pos += d
            self.canvas.update()
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls and self.maybe_save():
            self.load(urls[0])

    def closeEvent(self, e):
        if self.text_edit is not None:
            self._commit_text()
        if self.maybe_save():
            e.accept()
            super().closeEvent(e)
        else:
            e.ignore()


class PaintApp:
    def __init__(self):
        self.windows = []

    def handle(self, args):
        files = [a for a in args if a and not a.startswith("-")] or [None]
        for f in files:
            w = PaintWindow(self, f)
            n = len(self.windows)
            w.move(70 + 26 * (n % 8), 50 + 26 * (n % 8))
            w.setAcceptDrops(True)
            w.show()
            w.raise_()
            w.activateWindow()
            self.windows.append(w)
            w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)


def main(args):
    return run_app("paint", PaintApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
