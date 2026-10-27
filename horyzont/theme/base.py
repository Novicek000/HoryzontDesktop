"""Bazowa klasa motywu i narzędzia rysowania.

Motyw rysuje wszystkie "części" interfejsu: ramki okien, pasek zadań,
menu Start, panel zadań Eksploratora i kontrolki. Wbudowany motyw
rysuje je wektorowo; motyw .msstyles — z bitmap zawartych w pliku.
"""
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)

# stany przycisków
NORMAL, HOVER, PRESSED, DISABLED, CHECKED = "normal", "hover", "pressed", "disabled", "checked"


def C(c, a=None):
    """Kolor z nazwy; 8-cyfrowy zapis szesnastkowy to #RRGGBBAA (jak w CSS)."""
    if isinstance(c, str) and c.startswith("#") and len(c) == 9:
        q = QColor(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), int(c[7:9], 16))
    else:
        q = QColor(c)
    if a is not None:
        q.setAlpha(int(a))
    return q


def vgrad(rect, stops):
    r = QRectF(rect)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    for o, c in stops:
        g.setColorAt(o, C(c))
    return QBrush(g)


def hgrad(rect, stops):
    r = QRectF(rect)
    g = QLinearGradient(r.topLeft(), r.topRight())
    for o, c in stops:
        g.setColorAt(o, C(c))
    return QBrush(g)


def rgrad(center, radius, stops, focal=None):
    g = QRadialGradient(QPointF(center), radius, QPointF(focal or center))
    for o, c in stops:
        g.setColorAt(o, C(c))
    return QBrush(g)


def rounded_path(rect, r_tl, r_tr=None, r_br=None, r_bl=None):
    """Prostokąt z niezależnie zaokrąglonymi rogami."""
    if r_tr is None:
        r_tr = r_br = r_bl = r_tl
    r = QRectF(rect)
    p = QPainterPath()
    p.moveTo(r.left() + r_tl, r.top())
    p.lineTo(r.right() - r_tr, r.top())
    if r_tr:
        p.quadTo(r.right(), r.top(), r.right(), r.top() + r_tr)
    p.lineTo(r.right(), r.bottom() - r_br)
    if r_br:
        p.quadTo(r.right(), r.bottom(), r.right() - r_br, r.bottom())
    p.lineTo(r.left() + r_bl, r.bottom())
    if r_bl:
        p.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - r_bl)
    p.lineTo(r.left(), r.top() + r_tl)
    if r_tl:
        p.quadTo(r.left(), r.top(), r.left() + r_tl, r.top())
    p.closeSubpath()
    return p


def lighter(c, f=120):
    return QColor(c).lighter(f)


def darker(c, f=120):
    return QColor(c).darker(f)


def mix(c1, c2, t):
    a, b = QColor(c1), QColor(c2)
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class Theme:
    """Interfejs motywu. Domyślne implementacje są celowo proste."""

    name = "base"
    display_name = "Base"

    def __init__(self):
        self.metrics = {
            "caption_h": 28,
            "border": 4,
            "caption_button": 21,
            "caption_button_gap": 2,
            "taskbar_h": 30,
            "start_w": 104,
            "task_button_max_w": 160,
            "task_button_h": 24,
            "tray_pad": 10,
            "frame_radius": 7,
            "sm_width": 400,
            "sm_header_h": 58,
            "sm_footer_h": 38,
            "taskpane_w": 222,
            "menu_item_h": 22,
            "small_caption_h": 22,
        }
        self.colors = {}
        self.font_scale = 1.0

    # ------------------------------------------------------------ czcionki
    def font(self, kind="normal"):
        from .manager import base_family
        sizes = {"normal": 11, "caption": 13, "small": 10, "menu": 11, "icon": 11, "status": 11,
                 "start_button": 16, "sm_user": 15, "sm_item": 11, "taskpane_header": 11, "big": 14,
                 "title_big": 19}
        f = QFont(base_family())
        f.setPixelSize(max(8, round(sizes.get(kind, 11) * self.font_scale)))
        if kind in ("caption", "start_button", "sm_user", "taskpane_header", "title_big"):
            f.setBold(True)
        if kind == "start_button":
            f.setItalic(False)
        return f

    def color(self, key, default="#000000"):
        return QColor(self.colors.get(key, default))

    # ------------------------------------------------------------ okna
    def caption_button_rects(self, w, maximized, kinds=("min", "max", "close")):
        m = self.metrics
        b = 0 if maximized else m["border"]
        size = m["caption_button"]
        top = (m["caption_h"] + (0 if maximized else 2) - size) // 2
        x = w - b - 3 - size
        rects = {}
        for k in reversed(kinds):
            rects[k] = QRect(x, top, size, size)
            x -= size + m["caption_button_gap"]
            if k == "close":
                x -= 2
        return rects

    def frame_margins(self, maximized=False):
        m = self.metrics
        b = 0 if maximized else m["border"]
        return b, m["caption_h"], b, b

    def draw_window_frame(self, p, rect, active, maximized):
        p.fillRect(rect, self.color("caption_active" if active else "caption_inactive", "#336"))

    def draw_caption_button(self, p, rect, kind, state, active):
        p.fillRect(rect, QColor("#ccc"))

    def draw_caption_text(self, p, rect, text, active):
        p.setFont(self.font("caption"))
        fm = p.fontMetrics()
        text = fm.elidedText(text, Qt.ElideRight, rect.width())
        if active:
            p.setPen(C("#000", 110))
            p.drawText(rect.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.setPen(self.color("caption_text_active" if active else "caption_text_inactive", "#fff"))
        p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    # ------------------------------------------------------------ pasek zadań
    def draw_taskbar(self, p, rect):
        p.fillRect(rect, QColor("#246"))

    def draw_start_button(self, p, rect, state, text):
        p.fillRect(rect, QColor("#3a3"))

    def draw_task_button(self, p, rect, state):
        p.fillRect(rect, QColor("#468"))

    def draw_tray(self, p, rect):
        p.fillRect(rect, QColor("#357"))

    def taskbar_text_color(self):
        return self.color("taskbar_text", "#ffffff")

    # ------------------------------------------------------------ menu Start
    def draw_sm_frame(self, p, rect):
        p.fillRect(rect, QColor("#fff"))

    def draw_sm_header(self, p, rect):
        p.fillRect(rect, QColor("#246"))

    def draw_sm_left(self, p, rect):
        p.fillRect(rect, QColor("#fff"))

    def draw_sm_right(self, p, rect):
        p.fillRect(rect, QColor("#def"))

    def draw_sm_footer(self, p, rect):
        p.fillRect(rect, QColor("#246"))

    def draw_sm_separator(self, p, rect, right=False):
        p.fillRect(rect, QColor("#ccc"))

    def draw_sm_item_hover(self, p, rect, right=False):
        p.fillRect(rect, self.color("highlight", "#2a8a96"))

    def draw_sm_footer_button(self, p, rect, state):
        if state == HOVER:
            p.fillRect(rect, C("#fff", 40))

    # ------------------------------------------------------------ panel zadań
    def draw_taskpane_bg(self, p, rect):
        p.fillRect(rect, QColor("#8bc"))

    def draw_taskpane_header(self, p, rect, special, hover, expanded):
        p.fillRect(rect, QColor("#fff"))

    def draw_taskpane_body(self, p, rect, special):
        p.fillRect(rect, QColor("#eef"))

    # ------------------------------------------------------------ kontrolki
    def draw_button(self, p, rect, state, default=False, focus=False):
        p.fillRect(rect, QColor("#ddd"))

    def draw_checkbox(self, p, rect, checked, state, partial=False):
        p.fillRect(rect, QColor("#fff"))

    def draw_radio(self, p, rect, checked, state):
        p.drawEllipse(rect)

    def draw_groupbox(self, p, rect):
        p.drawRect(rect)

    def draw_edit_frame(self, p, rect, focus, disabled):
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def draw_combo_button(self, p, rect, state, direction="down"):
        p.fillRect(rect, QColor("#ccc"))

    def draw_sb_track(self, p, rect, horizontal, pressed=False):
        p.fillRect(rect, QColor("#eee"))

    def draw_sb_thumb(self, p, rect, horizontal, state):
        p.fillRect(rect, QColor("#bbb"))

    def draw_sb_arrow(self, p, rect, direction, state):
        p.fillRect(rect, QColor("#bbb"))

    def draw_progress_track(self, p, rect):
        p.fillRect(rect, QColor("#fff"))

    def draw_progress_chunk(self, p, rect):
        p.fillRect(rect, QColor("#2a8a96"))

    def draw_tab(self, p, rect, selected, state):
        p.fillRect(rect, QColor("#fff" if selected else "#eee"))

    def draw_tab_pane(self, p, rect):
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def draw_header_section(self, p, rect, state):
        p.fillRect(rect, QColor("#eee"))

    def draw_toolbar_button(self, p, rect, state):
        if state in (HOVER, PRESSED, CHECKED):
            p.fillRect(rect, QColor("#dde"))

    def draw_menu_frame(self, p, rect):
        p.setPen(QColor("#888"))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def draw_menu_highlight(self, p, rect, menubar=False):
        p.fillRect(rect, self.color("menu_highlight", "#2a8a96"))

    def draw_slider_groove(self, p, rect, horizontal):
        p.fillRect(rect, QColor("#ccc"))

    def draw_slider_handle(self, p, rect, horizontal, state):
        p.fillRect(rect, QColor("#888"))

    def draw_tooltip(self, p, rect):
        p.fillRect(rect, QColor("#ffffe1"))
        p.setPen(QColor("#000"))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def draw_balloon(self, p, rect):
        self.draw_tooltip(p, rect)


def draw_glyph(p, rect, kind, color, width=2.0):
    """Symbole przycisków okna: min, max, restore, close, help."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    r = QRectF(rect)
    s = min(r.width(), r.height())
    cx, cy = r.center().x(), r.center().y()
    u = s / 21.0
    pen = QPen(QColor(color), width * u, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "min":
        p.fillRect(QRectF(cx - 4.5 * u, cy + 3 * u, 7 * u, 2.6 * u), QColor(color))
    elif kind == "max":
        rr = QRectF(cx - 5 * u, cy - 5 * u, 10 * u, 10 * u)
        p.setPen(QPen(QColor(color), 1.4 * u))
        p.drawRect(rr)
        p.fillRect(QRectF(rr.left(), rr.top(), rr.width(), 2.6 * u), QColor(color))
    elif kind == "restore":
        p.setPen(QPen(QColor(color), 1.3 * u))
        back = QRectF(cx - 2 * u, cy - 6 * u, 8 * u, 7 * u)
        front = QRectF(cx - 6 * u, cy - 1.5 * u, 8 * u, 7 * u)
        # tylne okienko rysujemy z wyciętym miejscem na przednie
        from PySide6.QtGui import QRegion
        full = QRegion(r.toAlignedRect())
        p.setClipRegion(full.subtracted(QRegion(front.adjusted(-0.5 * u, -0.5 * u, 0.5 * u, 0.5 * u).toAlignedRect())))
        p.drawRect(back)
        p.fillRect(QRectF(back.left(), back.top(), back.width(), 2 * u), QColor(color))
        p.setClipping(False)
        p.drawRect(front)
        p.fillRect(QRectF(front.left(), front.top(), front.width(), 2 * u), QColor(color))
    elif kind == "close":
        p.setPen(QPen(QColor(color), 2.4 * u, Qt.SolidLine, Qt.RoundCap))
        d = 4.6 * u
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
    elif kind == "help":
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(13 * u))
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(r, Qt.AlignCenter, "?")
    p.restore()


def draw_arrow(p, rect, direction, color, size=None):
    """Mały wypełniony trójkąt (strzałki przewijania, listy rozwijanej, podmenu)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    r = QRectF(rect)
    cx, cy = r.center().x(), r.center().y()
    s = size or max(3.0, min(r.width(), r.height()) * 0.22)
    path = QPainterPath()
    if direction == "down":
        path.moveTo(cx - s, cy - s * 0.5); path.lineTo(cx + s, cy - s * 0.5); path.lineTo(cx, cy + s * 0.6)
    elif direction == "up":
        path.moveTo(cx - s, cy + s * 0.5); path.lineTo(cx + s, cy + s * 0.5); path.lineTo(cx, cy - s * 0.6)
    elif direction == "left":
        path.moveTo(cx + s * 0.5, cy - s); path.lineTo(cx + s * 0.5, cy + s); path.lineTo(cx - s * 0.6, cy)
    else:
        path.moveTo(cx - s * 0.5, cy - s); path.lineTo(cx - s * 0.5, cy + s); path.lineTo(cx + s * 0.6, cy)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    p.restore()


def draw_chevron(p, rect, direction, color, width=1.8):
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    r = QRectF(rect)
    cx, cy = r.center().x(), r.center().y()
    s = min(r.width(), r.height()) * 0.22
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    for dy in (-s * 0.55, s * 0.55):
        if direction == "up":
            pts = [QPointF(cx - s, cy + dy + s * 0.45), QPointF(cx, cy + dy - s * 0.45), QPointF(cx + s, cy + dy + s * 0.45)]
        else:
            pts = [QPointF(cx - s, cy + dy - s * 0.45), QPointF(cx, cy + dy + s * 0.45), QPointF(cx + s, cy + dy - s * 0.45)]
        p.drawPolyline(pts)
    p.restore()
