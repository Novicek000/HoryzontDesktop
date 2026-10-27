"""Wbudowany motyw "Horyzont" — oryginalny styl w klimacie pulpitów z początku lat 2000.

Trzy schematy kolorów: morski (domyślny), grafitowy i śliwkowy.
Wszystko jest rysowane wektorowo, więc motyw skaluje się z rozmiarem czcionki.
"""
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath

from .base import (C, CHECKED, DISABLED, HOVER, NORMAL, PRESSED, Theme, darker,
                   draw_arrow, draw_chevron, draw_glyph, hgrad, lighter, mix,
                   rgrad, rounded_path, vgrad)

SCHEMES = {
    "teal": {
        "label_pl": "Morski", "label_en": "Teal",
        "accent": "#1f8591", "accent_dark": "#0f5d67", "accent_darker": "#0b4a52", "accent_light": "#5cc6d0",
        "accent_pale": "#e3eff1", "accent_pale2": "#c9e7eb",
        "taskbar": ["#4fb9c4", "#24909c", "#187a86", "#136d78", "#0f5d67"],
        "tray": ["#2aa0ac", "#1b8994", "#167c87"],
        "caption": ["#6fd0d9", "#36a6b2", "#2392a0", "#1d8592", "#1a7987"],
        "caption_in": ["#c7dfe1", "#a9cbcf", "#9ec3c8", "#97bdc2", "#90b6bb"],
        "border": "#16707b", "border_in": "#93b9be",
        "taskpane": ["#a8d8dd", "#6db2bc"],
        "desktop": "#2f6f86",
    },
    "graphite": {
        "label_pl": "Grafitowy", "label_en": "Graphite",
        "accent": "#4b5a68", "accent_dark": "#33404c", "accent_darker": "#26303a", "accent_light": "#8fa2b3",
        "accent_pale": "#e8ecef", "accent_pale2": "#d3dae0",
        "taskbar": ["#7f909f", "#596a79", "#4b5b69", "#42505d", "#36424d"],
        "tray": ["#62738a", "#53636f", "#4a5965"],
        "caption": ["#9aaebe", "#6e8294", "#5c7082", "#526577", "#4a5c6d"],
        "caption_in": ["#d5dbe0", "#bfc8cf", "#b6c0c8", "#afbac2", "#a8b3bc"],
        "border": "#465663", "border_in": "#a8b3bc",
        "taskpane": ["#c9d2da", "#8e9eab"],
        "desktop": "#4a5560",
    },
    "plum": {
        "label_pl": "Śliwkowy", "label_en": "Plum",
        "accent": "#6c4a8c", "accent_dark": "#4e3368", "accent_darker": "#3d2752", "accent_light": "#b394d0",
        "accent_pale": "#efe9f4", "accent_pale2": "#dfd2ea",
        "taskbar": ["#9a78bb", "#73529a", "#664689", "#5b3e7b", "#4e3368"],
        "tray": ["#7c5aa3", "#6a4a8f", "#604384"],
        "caption": ["#c3a3e0", "#9070b4", "#7d5ea3", "#725397", "#694b8b"],
        "caption_in": ["#e3d9ec", "#d2c3df", "#cab9d9", "#c3b1d3", "#bcaacd"],
        "border": "#5d4278", "border_in": "#bcaacd",
        "taskpane": ["#d6c7e4", "#a387c0"],
        "desktop": "#4b3a63",
    },
}

AMBER = ["#ffd38a", "#f6ad3e", "#e8901f", "#d47a12", "#c06a0c"]
AMBER_HOVER = ["#ffe0a8", "#ffbf5c", "#f5a032", "#e38a1c", "#cc7712"]
AMBER_PRESSED = ["#c97a1a", "#d4861c", "#e09429", "#e89e36", "#d48a26"]


class HoryzontTheme(Theme):
    name = "builtin"

    def __init__(self, scheme="teal"):
        super().__init__()
        self.scheme_name = scheme if scheme in SCHEMES else "teal"
        sc = self.sc = SCHEMES[self.scheme_name]
        self.display_name = "Horyzont"
        self.colors = {
            "window": "#ebeee9",
            "window_text": "#000000",
            "base": "#ffffff",
            "alt_base": "#f3f6f5",
            "button": "#ebeee9",
            "button_text": "#000000",
            "highlight": sc["accent"],
            "highlight_text": "#ffffff",
            "menu": "#ffffff",
            "menu_text": "#000000",
            "menu_highlight": sc["accent"],
            "menubar": "#ebeee9",
            "gray_text": "#a3a8a5",
            "link": sc["accent_dark"],
            "tooltip": "#ffffe1",
            "caption_text_active": "#ffffff",
            "caption_text_inactive": "#f2f6f7",
            "taskbar_text": "#ffffff",
            "desktop": sc["desktop"],
            "desktop_text": "#ffffff",
            "taskpane_link": sc["accent_dark"],
            "taskpane_link_hover": sc["accent"],
            "taskpane_header_text": sc["accent_darker"],
            "taskpane_header_special_text": "#ffffff",
            "sm_text": "#000000",
            "sm_right_text": darker(sc["accent_darker"], 130).name(),
            "sm_user_text": "#ffffff",
            "sm_footer_text": "#ffffff",
            "group_title": sc["accent_dark"],
            "frame_line": "#8fa7ab",
            "tab_border": "#8fb0b5",
            "status_bar": "#ebeee9",
            "dialog_header": "#ffffff",
        }

    # ================================================================ okna
    def draw_window_frame(self, p, rect, active, maximized):
        sc = self.sc
        m = self.metrics
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect)
        rad = 0 if maximized else m["frame_radius"]
        ch = m["caption_h"]
        b = 0 if maximized else m["border"]
        cols = sc["caption"] if active else sc["caption_in"]
        border = sc["border"] if active else sc["border_in"]
        outline = darker(border, 150) if active else darker(border, 120)

        # cała ramka
        path = rounded_path(r, rad, rad, 0, 0)
        p.fillPath(path, QColor(border))
        # pasek tytułu
        cap = QRectF(r.left(), r.top(), r.width(), ch)
        cap_path = rounded_path(cap, rad, rad, 0, 0)
        p.fillPath(cap_path, vgrad(cap, [(0, cols[0]), (0.12, cols[1]), (0.45, cols[2]), (0.75, cols[3]), (1, cols[4])]))
        # połysk w górnej części tytułu
        gloss = QRectF(cap.left() + 1, cap.top() + 1, cap.width() - 2, ch * 0.42)
        p.fillPath(rounded_path(gloss, max(0, rad - 1), max(0, rad - 1), 0, 0),
                   vgrad(gloss, [(0, "#ffffff55" if active else "#ffffff40"), (1, "#ffffff00")]))
        if not maximized:
            # wewnętrzne krawędzie ramki (jaśniejsze)
            p.setPen(QPen(lighter(border, 135), 1))
            p.drawLine(QPointF(r.left() + 1.5, r.top() + rad), QPointF(r.left() + 1.5, r.bottom() - 1.5))
            p.drawLine(QPointF(r.right() - 1.5, r.top() + rad), QPointF(r.right() - 1.5, r.bottom() - 1.5))
            p.drawLine(QPointF(r.left() + 1.5, r.bottom() - 1.5), QPointF(r.right() - 1.5, r.bottom() - 1.5))
            # zewnętrzny obrys
            p.setPen(QPen(outline, 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(rounded_path(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad, 0, 0))
            # górna jasna linia
            p.setPen(QPen(QColor(255, 255, 255, 120 if active else 90), 1))
            p.drawLine(QPointF(r.left() + rad, r.top() + 1.5), QPointF(r.right() - rad, r.top() + 1.5))
            # linia oddzielająca pasek tytułu od obszaru roboczego
            p.setPen(QPen(darker(border, 125), 1))
            p.drawLine(QPointF(b - 0.5, ch - 0.5), QPointF(r.right() - b + 0.5, ch - 0.5))
        p.restore()

    def draw_caption_button(self, p, rect, kind, state, active):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        sc = self.sc
        if kind == "close":
            if not active:
                stops = ["#e8b3a8", "#d8968a", "#cf8a7e"]
            elif state == PRESSED:
                stops = ["#9c2a10", "#b8381a", "#d04a28"]
            elif state == HOVER:
                stops = ["#ffb39a", "#f2714a", "#de4f26"]
            else:
                stops = ["#f9967a", "#e45a34", "#c8401c"]
        else:
            base = sc["caption"]
            if not active:
                stops = [lighter(sc["caption_in"][0], 104).name(), sc["caption_in"][2], sc["caption_in"][4]]
            elif state == PRESSED:
                stops = [darker(base[4], 135).name(), darker(base[3], 120).name(), base[3]]
            elif state == HOVER:
                stops = [lighter(base[0], 115).name(), lighter(base[1], 118).name(), lighter(base[3], 115).name()]
            else:
                stops = [lighter(base[0], 108).name(), base[1], base[3]]
        path = rounded_path(r, 3.5)
        p.fillPath(path, vgrad(r, [(0, stops[0]), (0.5, stops[1]), (1, stops[2])]))
        p.setPen(QPen(QColor(255, 255, 255, 230 if active else 160), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        glyph_col = "#ffffff" if active else "#f4f7f8"
        draw_glyph(p, rect, kind, glyph_col)
        p.restore()

    # ================================================================ pasek zadań
    def draw_taskbar(self, p, rect):
        t = self.sc["taskbar"]
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, t[0]), (0.09, t[1]), (0.18, t[2]), (0.6, t[3]), (1, t[4])]))
        p.setPen(QColor(255, 255, 255, 110))
        p.drawLine(r.topLeft() + QPointF(0, 0.5), r.topRight() + QPointF(0, 0.5))

    def draw_start_button(self, p, rect, state, text):
        from .iconcache import start_logo
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect)
        stops = AMBER_PRESSED if state == PRESSED else AMBER_HOVER if state == HOVER else AMBER
        rad = r.height() * 0.5
        path = rounded_path(r, 0, rad, rad, 0)
        p.fillPath(path, vgrad(r, [(0, stops[0]), (0.12, stops[1]), (0.45, stops[2]), (0.8, stops[3]), (1, stops[4])]))
        gloss = QRectF(r.left(), r.top() + 1, r.width() - rad * 0.6, r.height() * 0.42)
        if state != PRESSED:
            p.fillPath(rounded_path(gloss, 0, rad * 0.8, rad * 0.4, 0), vgrad(gloss, [(0, "#ffffff80"), (1, "#ffffff00")]))
        p.setPen(QPen(QColor("#7a3e06"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rounded_path(r.adjusted(-1, 0.5, -0.5, -0.5), 0, rad, rad, 0))
        # logo
        logo = int(r.height() * 0.8)
        lx = int(r.left() + 7)
        ly = int(r.top() + (r.height() - logo) / 2)
        lp = start_logo(logo)
        if lp.isNull():
            logo, lx = 0, lx + 4
        else:
            p.drawPixmap(lx + (logo - lp.width()) // 2, ly + (logo - lp.height()) // 2 + (1 if state == PRESSED else 0), lp)
        # napis
        f = self.font("start_button")
        p.setFont(f)
        tr = QRectF(lx + logo + 4, r.top() + (1 if state == PRESSED else 0), r.width() - logo - 14, r.height())
        p.setPen(QColor(90, 40, 0, 170))
        p.drawText(tr.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.setPen(QColor("#ffffff"))
        p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, text)
        p.restore()

    def start_button_width(self, text, height):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font("start_button"))
        return int(height * 0.8) + 7 + 4 + fm.horizontalAdvance(text) + 22

    def draw_task_button(self, p, rect, state):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        sc = self.sc
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(r, 3)
        t = sc["taskbar"]
        if state in (PRESSED, CHECKED):
            p.fillPath(path, vgrad(r, [(0, darker(t[4], 125).name()), (0.2, darker(t[4], 110).name()), (1, t[3])]))
            p.setPen(QPen(darker(t[4], 160), 1))
            p.drawPath(path)
            p.setPen(QPen(QColor(0, 0, 0, 60), 1))
            p.drawLine(r.topLeft() + QPointF(3, 1), r.topRight() + QPointF(-3, 1))
        elif state == "flash":
            p.fillPath(path, vgrad(r, [(0, AMBER[0]), (0.5, AMBER[2]), (1, AMBER[4])]))
            p.setPen(QPen(QColor("#7a3e06"), 1))
            p.drawPath(path)
        else:
            top = lighter(t[1], 130 if state == HOVER else 118)
            mid = lighter(t[2], 128 if state == HOVER else 116)
            bot = lighter(t[3], 125 if state == HOVER else 112)
            p.fillPath(path, vgrad(r, [(0, top.name()), (0.5, mid.name()), (1, bot.name())]))
            p.setPen(QPen(darker(t[4], 135), 1))
            p.drawPath(path)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawLine(r.topLeft() + QPointF(3, 1), r.topRight() + QPointF(-3, 1))
        p.restore()

    def draw_tray(self, p, rect):
        tr = self.sc["tray"]
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, lighter(tr[0], 115).name()), (0.12, tr[0]), (0.5, tr[1]), (1, tr[2])]))
        p.setPen(QPen(darker(tr[2], 150), 1))
        p.drawLine(QPointF(r.left() + 0.5, r.top()), QPointF(r.left() + 0.5, r.bottom()))
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawLine(QPointF(r.left() + 1.5, r.top() + 1), QPointF(r.left() + 1.5, r.bottom()))
        p.setPen(QColor(255, 255, 255, 110))
        p.drawLine(r.topLeft() + QPointF(0, 0.5), r.topRight() + QPointF(0, 0.5))

    # ================================================================ menu Start
    def draw_sm_frame(self, p, rect):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(self.sc["accent_darker"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rounded_path(r, 6, 6, 0, 0))
        p.restore()

    def draw_sm_header(self, p, rect):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect)
        c = sc["caption"]
        path = rounded_path(r, 6, 6, 0, 0)
        p.fillPath(path, vgrad(r, [(0, c[0]), (0.15, c[1]), (0.6, c[2]), (1, c[4])]))
        gloss = QRectF(r.left(), r.top(), r.width(), r.height() * 0.45)
        p.fillPath(rounded_path(gloss, 6, 6, 0, 0), vgrad(gloss, [(0, "#ffffff50"), (1, "#ffffff00")]))
        # pomarańczowa linia u dołu nagłówka
        line = QRectF(r.left(), r.bottom() - 2, r.width(), 2)
        p.fillRect(line, hgrad(line, [(0, "#ffffff00"), (0.3, AMBER[1]), (0.7, AMBER[1]), (1, "#ffffff00")]))
        p.restore()

    def draw_sm_left(self, p, rect):
        p.fillRect(rect, QColor("#ffffff"))

    def draw_sm_right(self, p, rect):
        sc = self.sc
        r = QRectF(rect)
        p.fillRect(r, QColor(sc["accent_pale"]))
        p.setPen(QPen(QColor(sc["accent_pale2"]).darker(108), 1))
        p.drawLine(r.topLeft() + QPointF(0.5, 0), r.bottomLeft() + QPointF(0.5, 0))

    def draw_sm_footer(self, p, rect):
        c = self.sc["caption"]
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, c[2]), (0.5, c[3]), (1, c[4])]))
        p.setPen(QColor(255, 255, 255, 90))
        p.drawLine(r.topLeft() + QPointF(0, 0.5), r.topRight() + QPointF(0, 0.5))

    def draw_sm_separator(self, p, rect, right=False):
        r = QRectF(rect)
        col = QColor(self.sc["accent_light"]) if right else QColor("#c9d3d4")
        y = r.center().y()
        p.fillRect(QRectF(r.left(), y, r.width(), 1),
                   hgrad(r, [(0, "#ffffff00"), (0.15, col.name()), (0.85, col.name()), (1, "#ffffff00")]))

    def draw_sm_item_hover(self, p, rect, right=False):
        p.fillRect(rect, QColor(self.sc["accent"]))

    def draw_sm_footer_button(self, p, rect, state):
        if state in (HOVER, PRESSED):
            p.save()
            p.setRenderHint(QPainter.Antialiasing, True)
            r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            p.setBrush(QColor(255, 255, 255, 50 if state == HOVER else 25))
            p.drawRoundedRect(r, 3, 3)
            p.restore()

    # ================================================================ panel zadań
    def draw_taskpane_bg(self, p, rect):
        t = self.sc["taskpane"]
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, t[0]), (1, t[1])]))

    def draw_taskpane_header(self, p, rect, special, hover, expanded):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect)
        path = rounded_path(r, 5, 5, 0, 0)
        if special:
            p.fillPath(path, hgrad(r, [(0, sc["accent_dark"]), (1, sc["accent_light"])]))
        else:
            p.fillPath(path, hgrad(r, [(0, "#ffffff"), (0.45, "#ffffff"), (1, sc["accent_pale2"])]))
        # przycisk ze strzałkami
        d = min(18.0, r.height() - 5)
        br = QRectF(r.right() - d - 5, r.center().y() - d / 2, d, d)
        if special:
            p.setBrush(QColor(255, 255, 255, 60 if not hover else 100))
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        else:
            p.setBrush(vgrad(br, [(0, "#ffffff"), (1, sc["accent_pale2"])]))
            p.setPen(QPen(QColor(sc["accent_light"]).darker(110 if not hover else 130), 1))
        p.drawEllipse(br)
        col = "#ffffff" if special else (sc["accent"] if hover else sc["accent_dark"])
        draw_chevron(p, br, "up" if expanded else "down", col, 1.6)
        p.restore()

    def draw_taskpane_body(self, p, rect, special):
        r = QRectF(rect)
        p.fillRect(r, QColor("#f3fafb" if special else "#e8f3f5") if self.scheme_name == "teal"
                   else QColor(mix(self.sc["accent_pale"], "#ffffff", 0.5 if special else 0.15)))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(0.5, 0, -0.5, -0.5))

    # ================================================================ kontrolki
    def draw_button(self, p, rect, state, default=False, focus=False):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(r, 3)
        if state == DISABLED:
            p.fillPath(path, QColor("#f4f5f2"))
            p.setPen(QPen(QColor("#c3cac8"), 1))
            p.drawPath(path)
            p.restore()
            return
        if state == PRESSED:
            p.fillPath(path, vgrad(r, [(0, "#d6dddc"), (0.6, "#e8eceb"), (1, "#f2f5f4")]))
        else:
            p.fillPath(path, vgrad(r, [(0, "#ffffff"), (0.55, "#f2f4f3"), (0.9, "#e3e8e6"), (1, "#d3dad8")]))
        if state == HOVER:
            inner = r.adjusted(1.5, 1.5, -1.5, -1.5)
            p.setPen(QPen(QColor(AMBER[1]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(rounded_path(inner, 2))
        elif default or focus:
            inner = r.adjusted(1.5, 1.5, -1.5, -1.5)
            p.setPen(QPen(QColor(sc["accent_light"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(rounded_path(inner, 2))
        p.setPen(QPen(QColor(sc["accent_darker"]).darker(115), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.restore()

    def draw_checkbox(self, p, rect, checked, state, partial=False):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        dis = state == DISABLED
        if dis:
            p.fillRect(r, QColor("#ffffff"))
        elif state == PRESSED:
            p.fillRect(r, vgrad(r, [(0, "#c4d2d4"), (1, "#eef3f3")]))
        else:
            p.fillRect(r, vgrad(r, [(0, "#dfe6e5"), (1, "#ffffff")]))
        if state == HOVER:
            p.setPen(QPen(QColor(AMBER[1]), 2))
            p.drawRect(r.adjusted(1.5, 1.5, -1.5, -1.5))
        p.setPen(QPen(QColor("#c3cac8" if dis else sc["accent_darker"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        col = QColor("#c3cac8" if dis else sc["accent"])
        if partial:
            p.fillRect(r.adjusted(3, 3, -3, -3), col)
        elif checked:
            pen = QPen(col, max(1.8, r.width() * 0.17), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            w = r.width()
            p.drawPolyline([QPointF(r.left() + w * 0.22, r.top() + w * 0.5),
                            QPointF(r.left() + w * 0.42, r.top() + w * 0.72),
                            QPointF(r.left() + w * 0.78, r.top() + w * 0.28)])
        p.restore()

    def draw_radio(self, p, rect, checked, state):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        dis = state == DISABLED
        p.setBrush(QColor("#ffffff") if dis else vgrad(r, [(0, "#dfe6e5"), (1, "#ffffff")]))
        p.setPen(QPen(QColor("#c3cac8" if dis else sc["accent_darker"]), 1))
        p.drawEllipse(r)
        if state == HOVER:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(AMBER[1]), 1.6))
            p.drawEllipse(r.adjusted(1.6, 1.6, -1.6, -1.6))
        if checked:
            d = r.width() * 0.5
            dot = QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#c3cac8") if dis else rgrad(dot.center() - QPointF(d * 0.15, d * 0.15), d * 0.7,
                                                            [(0, sc["accent_light"]), (1, sc["accent_dark"])]))
            p.drawEllipse(dot)
        p.restore()

    def draw_groupbox(self, p, rect):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor("#c2d2d4"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        p.restore()

    def draw_edit_frame(self, p, rect, focus, disabled):
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        col = "#c3cac8" if disabled else (self.sc["accent"] if focus else "#7aa1a8")
        p.setPen(QPen(QColor(col), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)

    def draw_combo_button(self, p, rect, state, direction="down"):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5)
        path = rounded_path(r, 2)
        if state == DISABLED:
            p.fillPath(path, QColor("#eef0ee"))
            draw_arrow(p, rect, direction, "#c3cac8", 3.5)
            p.restore()
            return
        top = sc["accent_pale"]
        bot = QColor(sc["accent_light"]).lighter(112).name()
        if state == HOVER:
            top, bot = "#ffffff", QColor(sc["accent_light"]).lighter(120).name()
        elif state == PRESSED:
            top, bot = QColor(sc["accent_light"]).name(), sc["accent_pale2"]
        p.fillPath(path, vgrad(r, [(0, top), (1, bot)]))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawPath(path)
        draw_arrow(p, rect, direction, sc["accent_darker"], 3.5)
        p.restore()

    def draw_sb_track(self, p, rect, horizontal, pressed=False):
        r = QRectF(rect)
        if horizontal:
            p.fillRect(r, vgrad(r, [(0, "#e6eceb"), (0.5, "#f6f8f8"), (1, "#eef2f1")]))
        else:
            p.fillRect(r, hgrad(r, [(0, "#e6eceb"), (0.5, "#f6f8f8"), (1, "#eef2f1")]))
        if pressed:
            p.fillRect(r, QColor(0, 0, 0, 25))

    def _sb_box(self, p, rect, horizontal, state):
        sc = self.sc
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(r, 3)
        a, b = QColor(sc["accent_pale"]), QColor(sc["accent_pale2"]).darker(104)
        if state == HOVER:
            a, b = QColor("#ffffff"), QColor(sc["accent_pale2"])
        elif state == PRESSED:
            a, b = QColor(sc["accent_pale2"]).darker(108), QColor(sc["accent_pale2"])
        elif state == DISABLED:
            a, b = QColor("#f2f4f4"), QColor("#e8ecec")
        g = (vgrad if horizontal else hgrad)(r, [(0, a.name()), (1, b.name())])
        p.fillPath(path, g)
        p.setPen(QPen(QColor(sc["accent_light"]).darker(105) if state != DISABLED else QColor("#d8dede"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def draw_sb_thumb(self, p, rect, horizontal, state):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        self._sb_box(p, rect, horizontal, state)
        r = QRectF(rect)
        c = r.center()
        p.setPen(QPen(QColor(self.sc["accent"]).lighter(140), 1))
        if (horizontal and r.width() > 18) or (not horizontal and r.height() > 18):
            for i in (-3, -1, 1, 3):
                if horizontal:
                    p.drawLine(QPointF(c.x() + i, c.y() - 3), QPointF(c.x() + i, c.y() + 3))
                else:
                    p.drawLine(QPointF(c.x() - 3, c.y() + i), QPointF(c.x() + 3, c.y() + i))
        p.restore()

    def draw_sb_arrow(self, p, rect, direction, state):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        self._sb_box(p, rect, direction in ("left", "right"), state)
        draw_arrow(p, rect, direction, "#b0bcbc" if state == DISABLED else self.sc["accent_darker"], 3.2)
        p.restore()

    def draw_progress_track(self, p, rect):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#7aa1a8"), 1))
        p.drawRoundedRect(r, 3, 3)
        p.restore()

    def draw_progress_chunk(self, p, rect):
        sc = self.sc
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, QColor(sc["accent_light"]).lighter(125).name()), (0.45, sc["accent"]),
                                (1, QColor(sc["accent_light"]).lighter(110).name())]))

    def draw_tab(self, p, rect, selected, state):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, 0.5)
        path = rounded_path(r, 3, 3, 0, 0)
        if selected:
            p.fillPath(path, QColor("#fcfdfd"))
        else:
            p.fillPath(path, vgrad(r, [(0, "#ffffff"), (1, "#e4eaea" if state != HOVER else "#f2f6f6")]))
        p.setPen(QPen(QColor(self.colors["tab_border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if selected or state == HOVER:
            line = QRectF(r.left() + 0.5, r.top() + 0.5, r.width() - 1, 2.5)
            p.fillPath(rounded_path(line, 2, 2, 0, 0), QColor(sc["accent"] if selected else AMBER[1]))
        if selected:
            p.setPen(QPen(QColor("#fcfdfd"), 2))
            p.drawLine(QPointF(r.left() + 1, r.bottom()), QPointF(r.right() - 1, r.bottom()))
        p.restore()

    def draw_tab_pane(self, p, rect):
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.fillRect(r, vgrad(r, [(0, "#fcfdfd"), (1, "#f2f5f4")]))
        p.setPen(QPen(QColor(self.colors["tab_border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)

    def draw_header_section(self, p, rect, state):
        r = QRectF(rect)
        p.fillRect(r, vgrad(r, [(0, "#ffffff"), (1, "#eef2f1")]))
        line = QRectF(r.left(), r.bottom() - 2, r.width(), 3)
        col = AMBER[1] if state == HOVER else (self.sc["accent_light"] if state == PRESSED else "#d8e0df")
        p.fillRect(line, QColor(col))
        p.setPen(QColor("#d0d8d7"))
        p.drawLine(QPointF(r.right() - 0.5, r.top() + 3), QPointF(r.right() - 0.5, r.bottom() - 4))

    def draw_toolbar_button(self, p, rect, state):
        if state not in (HOVER, PRESSED, CHECKED):
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(r, 3)
        if state == PRESSED or state == CHECKED:
            p.fillPath(path, vgrad(r, [(0, "#d3dede"), (1, "#e9efef")]))
        else:
            p.fillPath(path, vgrad(r, [(0, "#ffffff"), (1, "#e3eaea")]))
        p.setPen(QPen(QColor("#a9bec1"), 1))
        p.drawPath(path)
        p.restore()

    def draw_menu_frame(self, p, rect):
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#8a9b9e"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)

    def draw_menu_highlight(self, p, rect, menubar=False):
        p.fillRect(rect, QColor(self.sc["accent"]))

    def draw_slider_groove(self, p, rect, horizontal):
        r = QRectF(rect)
        if horizontal:
            g = QRectF(r.left(), r.center().y() - 2, r.width(), 4)
        else:
            g = QRectF(r.center().x() - 2, r.top(), 4, r.height())
        p.fillRect(g, QColor("#dfe5e4"))
        p.setPen(QColor("#9aaeb1"))
        p.drawLine(g.topLeft(), g.topRight() if horizontal else g.bottomLeft())
        p.setPen(QColor("#ffffff"))
        p.drawLine(g.bottomLeft(), g.bottomRight() if horizontal else g.topRight())

    def draw_slider_handle(self, p, rect, horizontal, state):
        sc = self.sc
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        if horizontal:
            tip = r.height() * 0.3
            path.moveTo(r.left(), r.top() + 2)
            path.quadTo(r.left(), r.top(), r.left() + 2, r.top())
            path.lineTo(r.right() - 2, r.top())
            path.quadTo(r.right(), r.top(), r.right(), r.top() + 2)
            path.lineTo(r.right(), r.bottom() - tip)
            path.lineTo(r.center().x(), r.bottom())
            path.lineTo(r.left(), r.bottom() - tip)
            path.closeSubpath()
        else:
            path = rounded_path(r, 2)
        top, bot = "#ffffff", sc["accent_pale2"]
        if state == HOVER:
            top, bot = "#ffffff", QColor(AMBER[0]).name()
        elif state == PRESSED:
            top, bot = sc["accent_pale2"], sc["accent_light"]
        p.fillPath(path, vgrad(r, [(0, top), (1, bot)]))
        p.setPen(QPen(QColor(sc["accent_dark"]), 1))
        p.drawPath(path)
        p.restore()

    def draw_balloon(self, p, rect):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor("#ffffe1"))
        p.setPen(QPen(QColor("#555555"), 1))
        p.drawRoundedRect(r, 7, 7)
        p.restore()


class ClassicTheme(HoryzontTheme):
    """Styl klasyczny: płaskie, szare, wypukłe kontrolki."""

    name = "classic"

    def __init__(self, scheme="teal"):
        super().__init__(scheme)
        self.display_name = "Klasyczny"
        self.metrics.update({"caption_h": 22, "border": 4, "caption_button": 16, "frame_radius": 0,
                             "taskbar_h": 28, "task_button_h": 22, "caption_button_gap": 0})
        self.colors.update({"window": "#d4d0c8", "button": "#d4d0c8", "menubar": "#d4d0c8",
                            "status_bar": "#d4d0c8", "taskbar_text": "#000000",
                            "menu": "#d4d0c8", "sm_right_text": "#000000", "sm_user_text": "#ffffff"})

    @staticmethod
    def bevel(p, r, raised=True, deep=True):
        r = QRect(r)
        hi, lo, dk = QColor("#ffffff"), QColor("#808080"), QColor("#404040")
        lt = QColor("#d4d0c8")
        a, b = (hi, dk) if raised else (dk, hi)
        p.setPen(a)
        p.drawLine(r.topLeft(), r.topRight() - QPointF(1, 0).toPoint())
        p.drawLine(r.topLeft(), r.bottomLeft() - QPointF(0, 1).toPoint())
        p.setPen(b)
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.drawLine(r.topRight(), r.bottomRight())
        if deep:
            inner = r.adjusted(1, 1, -1, -1)
            p.setPen(lt if raised else lo)
            p.drawLine(inner.topLeft(), inner.topRight())
            p.drawLine(inner.topLeft(), inner.bottomLeft())
            p.setPen(lo if raised else lt)
            p.drawLine(inner.bottomLeft(), inner.bottomRight())
            p.drawLine(inner.topRight(), inner.bottomRight())

    def draw_window_frame(self, p, rect, active, maximized):
        r = QRect(rect)
        p.fillRect(r, QColor("#d4d0c8"))
        if not maximized:
            self.bevel(p, r.adjusted(0, 0, -1, -1), True, True)
        b = 0 if maximized else 4
        cap = QRect(b, b, r.width() - 2 * b, self.metrics["caption_h"] - b - 1)
        sc = self.sc
        if active:
            p.fillRect(cap, hgrad(cap, [(0, sc["accent_darker"]), (1, sc["accent_light"])]))
        else:
            p.fillRect(cap, hgrad(cap, [(0, "#808080"), (1, "#c0c0c0")]))

    def frame_margins(self, maximized=False):
        b = 0 if maximized else 4
        return b, self.metrics["caption_h"], b, b

    def caption_button_rects(self, w, maximized, kinds=("min", "max", "close")):
        b = 0 if maximized else 4
        size_w, size_h = 16, 14
        top = b + (self.metrics["caption_h"] - b - 1 - size_h) // 2
        x = w - b - 2 - size_w
        rects = {}
        for k in reversed(kinds):
            rects[k] = QRect(x, top, size_w, size_h)
            x -= size_w + (2 if k == "close" else 0)
        return rects

    def draw_caption_button(self, p, rect, kind, state, active):
        r = QRect(rect)
        p.fillRect(r, QColor("#d4d0c8"))
        self.bevel(p, r.adjusted(0, 0, -1, -1), state != PRESSED, True)
        off = 1 if state == PRESSED else 0
        draw_glyph(p, QRectF(r).translated(off, off), kind, "#000000", 1.3)

    def draw_caption_text(self, p, rect, text, active):
        p.setFont(self.font("caption"))
        fm = p.fontMetrics()
        p.setPen(QColor("#ffffff" if active else "#d4d0c8"))
        p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(text, Qt.ElideRight, rect.width()))

    def draw_taskbar(self, p, rect):
        p.fillRect(rect, QColor("#d4d0c8"))
        p.setPen(QColor("#ffffff"))
        p.drawLine(rect.topLeft() + QPointF(0, 1).toPoint(), rect.topRight() + QPointF(0, 1).toPoint())

    def draw_start_button(self, p, rect, state, text):
        from .iconcache import start_logo
        r = QRect(rect).adjusted(2, 3, -2, -2)
        p.fillRect(r, QColor("#d4d0c8"))
        self.bevel(p, r.adjusted(0, 0, -1, -1), state != PRESSED, True)
        off = 1 if state == PRESSED else 0
        lp = start_logo(16)
        tx = 24
        if lp.isNull():
            tx = 8
        else:
            p.drawPixmap(r.left() + 4 + off, r.top() + (r.height() - lp.height()) // 2 + off, lp)
        f = self.font("normal"); f.setBold(True); p.setFont(f)
        p.setPen(QColor("#000"))
        p.drawText(r.adjusted(tx + off, off, 0, off), Qt.AlignVCenter | Qt.AlignLeft, text)

    def start_button_width(self, text, height):
        from PySide6.QtGui import QFontMetrics
        f = self.font("normal"); f.setBold(True)
        return QFontMetrics(f).horizontalAdvance(text) + 36

    def draw_task_button(self, p, rect, state):
        r = QRect(rect)
        if state in (PRESSED, CHECKED):
            p.fillRect(r, QColor("#e8e6e2"))
            self.bevel(p, r.adjusted(0, 0, -1, -1), False, True)
        else:
            p.fillRect(r, QColor("#d4d0c8"))
            self.bevel(p, r.adjusted(0, 0, -1, -1), True, True)

    def draw_tray(self, p, rect):
        r = QRect(rect).adjusted(0, 3, -2, -2)
        self.bevel(p, r.adjusted(0, 0, -1, -1), False, False)

    def draw_sm_header(self, p, rect):
        sc = self.sc
        p.fillRect(rect, vgrad(rect, [(0, sc["accent_darker"]), (1, sc["accent"])]))

    def draw_sm_right(self, p, rect):
        p.fillRect(rect, QColor("#d4d0c8"))

    def draw_sm_left(self, p, rect):
        p.fillRect(rect, QColor("#ffffff"))

    def draw_sm_footer(self, p, rect):
        p.fillRect(rect, QColor("#d4d0c8"))
        p.setPen(QColor("#808080"))
        p.drawLine(rect.topLeft(), rect.topRight())

    def draw_sm_frame(self, p, rect):
        self.bevel(p, QRect(rect).adjusted(0, 0, -1, -1), True, True)

    def draw_button(self, p, rect, state, default=False, focus=False):
        r = QRect(rect)
        p.fillRect(r, QColor("#d4d0c8"))
        if default and state != PRESSED:
            p.setPen(QColor("#000"))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            r = r.adjusted(1, 1, -1, -1)
        self.bevel(p, r.adjusted(0, 0, -1, -1), state != PRESSED, True)

    def draw_checkbox(self, p, rect, checked, state, partial=False):
        r = QRect(rect)
        p.fillRect(r, QColor("#ffffff" if state != DISABLED else "#d4d0c8"))
        self.bevel(p, r.adjusted(0, 0, -1, -1), False, True)
        if checked or partial:
            pen = QPen(QColor("#000" if state != DISABLED else "#808080"), 2)
            p.setPen(pen)
            p.drawPolyline([QPointF(r.left() + 3, r.top() + 6), QPointF(r.left() + 5.5, r.top() + 8.5),
                            QPointF(r.left() + 10, r.top() + 4)])

    def draw_sb_thumb(self, p, rect, horizontal, state):
        p.fillRect(rect, QColor("#d4d0c8"))
        self.bevel(p, QRect(rect).adjusted(0, 0, -1, -1), True, True)

    def draw_sb_arrow(self, p, rect, direction, state):
        p.fillRect(rect, QColor("#d4d0c8"))
        self.bevel(p, QRect(rect).adjusted(0, 0, -1, -1), state != PRESSED, True)
        draw_arrow(p, rect, direction, "#808080" if state == DISABLED else "#000", 3)

    def draw_sb_track(self, p, rect, horizontal, pressed=False):
        p.fillRect(rect, QColor("#e8e6e2"))

    def draw_tab(self, p, rect, selected, state):
        r = QRect(rect)
        p.fillRect(r, QColor("#d4d0c8"))
        p.setPen(QColor("#ffffff"))
        p.drawLine(r.bottomLeft(), r.topLeft() + QPointF(0, 2).toPoint())
        p.drawLine(r.topLeft() + QPointF(2, 0).toPoint(), r.topRight() - QPointF(2, 0).toPoint())
        p.setPen(QColor("#404040"))
        p.drawLine(r.topRight() + QPointF(0, 2).toPoint(), r.bottomRight())

    def draw_tab_pane(self, p, rect):
        p.fillRect(rect, QColor("#d4d0c8"))
        self.bevel(p, QRect(rect).adjusted(0, 0, -1, -1), True, True)

    def draw_header_section(self, p, rect, state):
        p.fillRect(rect, QColor("#d4d0c8"))
        self.bevel(p, QRect(rect).adjusted(0, 0, -1, -1), state != PRESSED, False)

    def draw_taskpane_bg(self, p, rect):
        p.fillRect(rect, QColor("#ffffff"))

    def draw_taskpane_header(self, p, rect, special, hover, expanded):
        p.fillRect(rect, QColor("#d4d0c8"))
        draw_chevron(p, QRectF(rect.right() - 20, rect.top(), 18, rect.height()), "up" if expanded else "down", "#000", 1.4)

    def draw_taskpane_body(self, p, rect, special):
        p.fillRect(rect, QColor("#f4f3ef"))
