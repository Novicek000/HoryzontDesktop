"""Własny, rysowany wektorowo zestaw ikon środowiska Horyzont.

Każda ikona to mały dokument SVG (viewBox 48x48) budowany z prostych
elementów. Ikony są renderowane do pixmap w potrzebnych rozmiarach
i trzymane w pamięci podręcznej.
"""
from functools import lru_cache

_uid = [0]


def _id(prefix):
    _uid[0] += 1
    return f"{prefix}{_uid[0]}"


def _stops(stops):
    out = []
    for st in stops:
        o, c = st[0], st[1]
        op = ' stop-opacity="%s"' % st[2] if len(st) > 2 else ""
        out.append('<stop offset="%s" stop-color="%s"%s/>' % (o, c, op))
    return "".join(out)


def lg(stops, x1=0, y1=0, x2=0, y2=1, units="objectBoundingBox"):
    gid = _id("g")
    st = _stops(stops)
    return gid, f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" gradientUnits="{units}">{st}</linearGradient>'


def rg(stops, cx=0.5, cy=0.5, r=0.5, fx=None, fy=None):
    gid = _id("r")
    st = _stops(stops)
    fxy = f' fx="{fx}" fy="{fy}"' if fx is not None else ""
    return gid, f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}"{fxy}>{st}</radialGradient>'


class S:
    """Pomocnik do składania dokumentu SVG."""

    def __init__(self):
        self.defs = []
        self.body = []

    def grad(self, g):
        gid, d = g
        self.defs.append(d)
        return f"url(#{gid})"

    def add(self, s):
        self.body.append(s)
        return self

    def svg(self):
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
                f'<defs>{"".join(self.defs)}</defs>{"".join(self.body)}</svg>')


def shadow(s, cx=24, cy=44, rx=18, ry=2.6, op=0.28):
    f = s.grad(rg([(0, "#000", op), (1, "#000", 0)]))
    s.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{f}"/>')


# ---------------------------------------------------------------- foldery
def folder(s, open_=False, tint=("#f6cf63", "#e3a73a", "#b97b1e")):
    shadow(s, cy=43.5)
    back = s.grad(lg([(0, tint[1]), (1, tint[2])]))
    s.add(f'<path d="M4 11.5 Q4 9 6.5 9 H17 L20.5 12.5 H40.5 Q43 12.5 43 15 V39 Q43 41 41 41 H6 Q4 41 4 39 Z" '
          f'fill="{back}" stroke="#8c5a12" stroke-width="0.9"/>')
    # kartka w środku
    s.add('<path d="M8 15 H39 V36 H8 Z" fill="#fffef8" stroke="#c9c2a8" stroke-width="0.6"/>')
    front = s.grad(lg([(0, "#fff0b0"), (0.25, tint[0]), (1, tint[1])]))
    if open_:
        s.add(f'<path d="M7.5 20 H45 Q46.5 20 46 21.6 L41.8 39.6 Q41.4 41 40 41 H5.5 Q3.8 41 4.2 39.4 L5.6 21.4 Q5.9 20 7.5 20 Z" '
              f'fill="{front}" stroke="#8c5a12" stroke-width="0.9"/>')
    else:
        s.add(f'<path d="M4 18.5 Q4 17 5.5 17 H41.5 Q43 17 43 18.5 V39 Q43 41 41 41 H6 Q4 41 4 39 Z" '
              f'fill="{front}" stroke="#8c5a12" stroke-width="0.9"/>')
        s.add('<path d="M5.2 18.4 H41.8" stroke="#fff6cf" stroke-width="1" opacity="0.9"/>')


def emblem_circle(s, color1, color2, cx=33, cy=32, r=9):
    g = s.grad(lg([(0, color1), (1, color2)]))
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{g}" stroke="#fff" stroke-width="1.4"/>')


def icon_folder():
    s = S(); folder(s); return s.svg()


def icon_folder_open():
    s = S(); folder(s, open_=True); return s.svg()


def icon_documents():
    s = S(); folder(s)
    # kartki wystające z folderu
    s.add('<path d="M13 8 H28 L32 12 V26 H13 Z" fill="#fff" stroke="#6b7f8c" stroke-width="0.8"/>')
    s.add('<path d="M28 8 V12 H32" fill="#dfe8ee" stroke="#6b7f8c" stroke-width="0.8"/>')
    for y in (15, 18, 21):
        s.add(f'<path d="M16 {y} H29" stroke="#4d8fb0" stroke-width="1"/>')
    front = s.grad(lg([(0, "#fff0b0"), (0.25, "#f6cf63"), (1, "#e3a73a")]))
    s.add(f'<path d="M4 22.5 Q4 21 5.5 21 H41.5 Q43 21 43 22.5 V39 Q43 41 41 41 H6 Q4 41 4 39 Z" fill="{front}" stroke="#8c5a12" stroke-width="0.9"/>')
    return s.svg()


def icon_pictures():
    s = S(); folder(s)
    s.add('<rect x="21" y="23" width="21" height="16" rx="1.5" fill="#fff" stroke="#55606a" stroke-width="0.9" transform="rotate(-6 31 31)"/>')
    sky = s.grad(lg([(0, "#7fc4ef"), (1, "#d9f0ff")]))
    s.add(f'<rect x="23" y="25" width="17" height="12" fill="{sky}" transform="rotate(-6 31 31)"/>')
    s.add('<path d="M23 37 L28.5 30 L32 34 L35 31 L40 37 Z" fill="#3f8f5b" transform="rotate(-6 31 31)"/>')
    s.add('<circle cx="36.5" cy="28" r="1.8" fill="#ffd34d" transform="rotate(-6 31 31)"/>')
    return s.svg()


def icon_music():
    s = S(); folder(s)
    emblem_circle(s, "#ff9b5a", "#d9531e")
    s.add('<path d="M31 37 V27.5 L37.5 26 V34.5" fill="none" stroke="#fff" stroke-width="1.7"/>')
    s.add('<ellipse cx="29.6" cy="37" rx="2.2" ry="1.7" fill="#fff"/><ellipse cx="36.1" cy="34.5" rx="2.2" ry="1.7" fill="#fff"/>')
    return s.svg()


def icon_videos():
    s = S(); folder(s)
    s.add('<rect x="22" y="24" width="20" height="15" rx="1.5" fill="#2b2f36" stroke="#fff" stroke-width="1"/>')
    for x in (24, 28, 32, 36, 40):
        s.add(f'<rect x="{x-0.9}" y="25.2" width="1.8" height="1.8" fill="#fff"/><rect x="{x-0.9}" y="36" width="1.8" height="1.8" fill="#fff"/>')
    s.add('<path d="M29.5 28.5 V34.5 L35 31.5 Z" fill="#ffcf4a"/>')
    return s.svg()


def icon_downloads():
    s = S(); folder(s)
    emblem_circle(s, "#4fc08d", "#1f8a5b")
    s.add('<path d="M33 26 V35 M29 31.5 L33 35.5 L37 31.5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_recent():
    s = S(); folder(s)
    emblem_circle(s, "#6fb8e8", "#2a73b8")
    s.add('<path d="M33 27 V32 L36 34" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round"/>')
    return s.svg()


def icon_desktop_folder():
    s = S(); folder(s)
    s.add('<rect x="20" y="24" width="22" height="14" rx="1.2" fill="#1f5f78" stroke="#fff" stroke-width="1"/>')
    s.add('<rect x="20" y="35" width="22" height="3" fill="#2c3e50"/><rect x="20.5" y="35.4" width="5" height="2.2" rx="1" fill="#f0a030"/>')
    return s.svg()


def icon_home():
    s = S(); shadow(s)
    wall = s.grad(lg([(0, "#fff8e8"), (1, "#e6d6b4")]))
    roof = s.grad(lg([(0, "#e8704a"), (1, "#a8381c")]))
    s.add(f'<path d="M9 22 V41 H39 V22 L24 10 Z" fill="{wall}" stroke="#7b6340" stroke-width="1"/>')
    s.add(f'<path d="M4 24 L24 7 L44 24 L40.5 26.5 L24 12.5 L7.5 26.5 Z" fill="{roof}" stroke="#7a2510" stroke-width="1"/>')
    s.add('<rect x="20" y="28" width="8" height="13" fill="#7a4a24" stroke="#4d2c10" stroke-width="0.8"/>')
    s.add('<rect x="11.5" y="27" width="6" height="6" fill="#9fd4f2" stroke="#5c4a30" stroke-width="0.8"/>')
    s.add('<rect x="30.5" y="27" width="6" height="6" fill="#9fd4f2" stroke="#5c4a30" stroke-width="0.8"/>')
    return s.svg()


# ---------------------------------------------------------------- komputer i sprzęt
def monitor(s, screen=None, x=5, y=6, w=38, h=27):
    shadow(s, cy=44, rx=15)
    body = s.grad(lg([(0, "#f4f6f8"), (1, "#b9c2cb")]))
    s.add(f'<path d="M20 {y+h} H28 L30 40 H18 Z" fill="#9aa5b0" stroke="#5e6872" stroke-width="0.8"/>')
    s.add(f'<rect x="13" y="39.5" width="22" height="3.2" rx="1.4" fill="{body}" stroke="#5e6872" stroke-width="0.8"/>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2.5" fill="{body}" stroke="#56606a" stroke-width="1"/>')
    scr = screen or s.grad(lg([(0, "#1d6f8a"), (0.55, "#3aa6c2"), (1, "#bfe9f2")], 0, 0, 1, 1))
    s.add(f'<rect x="{x+3}" y="{y+3}" width="{w-6}" height="{h-6.5}" rx="1" fill="{scr}" stroke="#36414b" stroke-width="0.7"/>')
    gl = s.grad(lg([(0, "#fff", 0.55), (1, "#fff", 0)]))
    s.add(f'<path d="M{x+3} {y+3} H{x+w-3} V{y+9} Q{x+20} {y+13} {x+3} {y+11} Z" fill="{gl}"/>')
    s.add(f'<circle cx="{x+w-4}" cy="{y+h-1.8}" r="0.9" fill="#36c36c"/>')


def icon_computer():
    s = S(); monitor(s)
    # mała jednostka centralna obok
    tower = s.grad(lg([(0, "#eef1f4"), (1, "#aab4be")], 0, 0, 1, 0))
    s.add(f'<rect x="35" y="22" width="10" height="20" rx="1.5" fill="{tower}" stroke="#56606a" stroke-width="0.9"/>')
    s.add('<rect x="37" y="25" width="6" height="1.6" fill="#59636d"/><rect x="37" y="28" width="6" height="1.6" fill="#59636d"/><circle cx="40" cy="37" r="1.3" fill="#36c36c"/>')
    return s.svg()


def icon_network():
    s = S(); shadow(s)
    globe = s.grad(rg([(0, "#bff0ff"), (0.6, "#3a9fd0"), (1, "#145a8a")], 0.4, 0.35, 0.65))
    s.add(f'<circle cx="28" cy="20" r="14" fill="{globe}" stroke="#0f4a72" stroke-width="1"/>')
    s.add('<path d="M18 13 Q22 16 21 20 Q19 23 22 26 Q25 28 23 32 M32 8 Q30 12 34 14 Q38 15 37 20 Q36 24 40 25" fill="none" stroke="#3eb36b" stroke-width="3" stroke-linecap="round" opacity="0.85"/>')
    s.add('<ellipse cx="28" cy="20" rx="14" ry="5" fill="none" stroke="#fff" stroke-width="0.8" opacity="0.5"/>')
    # komputer
    body = s.grad(lg([(0, "#f4f6f8"), (1, "#b0bac4")]))
    s.add(f'<rect x="4" y="25" width="20" height="14" rx="1.5" fill="{body}" stroke="#56606a" stroke-width="0.9"/>')
    s.add('<rect x="6" y="27" width="16" height="9.5" fill="#2a8ab0"/>')
    s.add('<path d="M11 39 H17 L18 42 H10 Z" fill="#9aa5b0" stroke="#56606a" stroke-width="0.7"/>')
    s.add('<path d="M22 32 Q28 34 28 34" stroke="#56606a" stroke-width="1.2" fill="none"/>')
    return s.svg()


def recycle_bin(s, full=False):
    shadow(s, cy=44, rx=14)
    body = s.grad(lg([(0, "#9fb4bf"), (0.35, "#e9f1f5"), (1, "#7d939f")], 0, 0, 1, 0))
    s.add(f'<path d="M11 14 L14 42 Q14.3 43 15.5 43 H32.5 Q33.7 43 34 42 L37 14 Z" fill="{body}" stroke="#46585f" stroke-width="1"/>')
    for x in (17, 21.5, 26.5, 31):
        s.add(f'<path d="M{x} 18 L{x + (x-24)*0.08} 39" stroke="#5b7079" stroke-width="1.6" stroke-linecap="round" opacity="0.7"/>')
    if full:
        s.add('<path d="M14 13 L17 5 L26 7 L24 13 Z" fill="#fff" stroke="#8a9aa3" stroke-width="0.7"/>')
        s.add('<path d="M22 13 Q26 3 33 6 L35 13 Z" fill="#fff6c8" stroke="#a8996a" stroke-width="0.7"/>')
        s.add('<path d="M18.5 9 L24 10 M20 7 L24 8" stroke="#6aa0c0" stroke-width="0.7"/>')
    lid = s.grad(lg([(0, "#d6e3ea"), (1, "#7f96a2")]))
    s.add(f'<rect x="9" y="11.5" width="30" height="4" rx="2" fill="{lid}" stroke="#46585f" stroke-width="1"/>')
    # symbol obiegu
    s.add('<g transform="translate(24 29) scale(0.55)" fill="none" stroke="#2f9e5b" stroke-width="3.4" stroke-linecap="round">'
          '<path d="M-6 -6 L0 -11 L6 -6"/><path d="M8 2 L6 10 L-2 10"/><path d="M-8 4 L-9 -2 L-4 -6"/></g>')


def icon_recycle_empty():
    s = S(); recycle_bin(s, False); return s.svg()


def icon_recycle_full():
    s = S(); recycle_bin(s, True); return s.svg()


def icon_browser():
    s = S(); shadow(s)
    globe = s.grad(rg([(0, "#d8f6ff"), (0.55, "#3fa8dc"), (1, "#0e4e86")], 0.38, 0.32, 0.7))
    s.add(f'<circle cx="24" cy="23" r="17" fill="{globe}" stroke="#0b3f6c" stroke-width="1"/>')
    s.add('<path d="M11 15 Q15 18 14 23 Q13 27 17 30 Q20 33 18 38 M28 7 Q26 12 30 14 Q35 16 33 22 Q32 27 37 29" fill="none" stroke="#45b86e" stroke-width="3.6" stroke-linecap="round" opacity="0.9"/>')
    ring = s.grad(lg([(0, "#ffd26a"), (1, "#e2861c")]))
    s.add(f'<ellipse cx="24" cy="24" rx="22" ry="8" fill="none" stroke="{ring}" stroke-width="3" transform="rotate(-25 24 24)"/>')
    s.add('<path d="M10 16 Q16 8 26 7" stroke="#fff" stroke-width="2" fill="none" opacity="0.6" stroke-linecap="round"/>')
    return s.svg()


def icon_email():
    s = S(); shadow(s)
    env = s.grad(lg([(0, "#ffffff"), (1, "#d6dee4")]))
    s.add(f'<rect x="5" y="12" width="38" height="26" rx="2" fill="{env}" stroke="#5a6872" stroke-width="1"/>')
    s.add('<path d="M5.6 13 L24 27 L42.4 13" fill="none" stroke="#5a6872" stroke-width="1"/>')
    s.add('<path d="M5.6 37.4 L19 24.5 M42.4 37.4 L29 24.5" fill="none" stroke="#9aa8b2" stroke-width="0.9"/>')
    stamp = s.grad(lg([(0, "#ff9b5a"), (1, "#d9531e")]))
    s.add(f'<rect x="33" y="15" width="7" height="8" fill="{stamp}" stroke="#fff" stroke-width="0.8"/>')
    return s.svg()


def icon_control_panel():
    s = S(); shadow(s)
    body = s.grad(lg([(0, "#f7f9fb"), (1, "#c6d0d8")]))
    s.add(f'<rect x="5" y="7" width="38" height="33" rx="2.5" fill="{body}" stroke="#56606a" stroke-width="1"/>')
    s.add('<rect x="5" y="7" width="38" height="6" rx="2.5" fill="#2a8a96"/><rect x="5" y="10" width="38" height="3" fill="#2a8a96"/>')
    for i, (x, v) in enumerate([(12, 26), (20, 20), (28, 31)]):
        s.add(f'<path d="M{x} 17 V36" stroke="#6b7680" stroke-width="1.6" stroke-linecap="round"/>')
        s.add(f'<rect x="{x-3}" y="{v-2}" width="6" height="4" rx="1" fill="#f0a030" stroke="#8a5410" stroke-width="0.8"/>')
    g = s.grad(rg([(0, "#fff"), (1, "#7fc8d6")]))
    s.add(f'<circle cx="36.5" cy="26" r="4.5" fill="{g}" stroke="#2f6f78" stroke-width="1"/><path d="M36.5 26 L38.5 23" stroke="#c0392b" stroke-width="1.2"/>')
    return s.svg()


def icon_printer():
    s = S(); shadow(s)
    s.add('<path d="M13 6 H32 L35 9 V20 H13 Z" fill="#fff" stroke="#6f7c86" stroke-width="0.9"/>')
    body = s.grad(lg([(0, "#eef1f4"), (1, "#9eaab5")]))
    s.add(f'<path d="M5 19 H43 Q45 19 45 21 V34 H3 V21 Q3 19 5 19 Z" fill="{body}" stroke="#4f5a64" stroke-width="1"/>')
    s.add('<rect x="10" y="30" width="28" height="12" fill="#fff" stroke="#6f7c86" stroke-width="0.9"/>')
    s.add('<path d="M13 34 H33 M13 37 H28" stroke="#4d8fb0" stroke-width="1"/>')
    s.add('<circle cx="39" cy="24" r="1.3" fill="#36c36c"/>')
    return s.svg()


def round_badge(s, c1, c2, cx=24, cy=24, r=18, stroke="#0b3f6c"):
    shadow(s, cy=44, rx=14)
    g = s.grad(rg([(0, c1), (1, c2)], 0.4, 0.3, 0.75))
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{g}" stroke="{stroke}" stroke-width="1"/>')
    gl = s.grad(lg([(0, "#fff", 0.7), (1, "#fff", 0)]))
    s.add(f'<ellipse cx="{cx}" cy="{cy - r*0.45}" rx="{r*0.7}" ry="{r*0.42}" fill="{gl}"/>')


def icon_help():
    s = S(); round_badge(s, "#8fd3f4", "#1c6fae")
    s.add('<path d="M18.5 18.5 Q18.5 12 24.5 12 Q30.5 12 30.5 17.5 Q30.5 21 26.5 23 Q24.5 24 24.5 27.5" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round"/>')
    s.add('<circle cx="24.5" cy="34" r="2.7" fill="#fff"/>')
    return s.svg()


def icon_info():
    s = S(); round_badge(s, "#8fd3f4", "#1c6fae")
    s.add('<circle cx="24" cy="14" r="2.8" fill="#fff"/><path d="M24 20 V34" stroke="#fff" stroke-width="5" stroke-linecap="round"/>')
    return s.svg()


def icon_question():
    return icon_help()


def icon_error():
    s = S(); round_badge(s, "#ff8a7a", "#b0170c", stroke="#6e0a04")
    s.add('<path d="M17 17 L31 31 M31 17 L17 31" stroke="#fff" stroke-width="4.4" stroke-linecap="round"/>')
    return s.svg()


def icon_warning():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#fff1a6"), (1, "#f2b51c")]))
    s.add(f'<path d="M24 5 Q26 5 27 7 L44 38 Q45 41 42 41 H6 Q3 41 4 38 L21 7 Q22 5 24 5 Z" fill="{g}" stroke="#8a6200" stroke-width="1.1"/>')
    s.add('<path d="M24 16 V29" stroke="#222" stroke-width="4.4" stroke-linecap="round"/><circle cx="24" cy="35" r="2.6" fill="#222"/>')
    return s.svg()


def icon_search():
    s = S(); shadow(s, cx=22)
    s.add('<path d="M29 30 L41 42" stroke="#5a3a1c" stroke-width="6" stroke-linecap="round"/>')
    s.add('<path d="M29 30 L41 42" stroke="#b07a3c" stroke-width="3.6" stroke-linecap="round"/>')
    lens = s.grad(rg([(0, "#ffffff"), (0.7, "#cfeaf5"), (1, "#87bcd2")], 0.4, 0.35, 0.7))
    s.add(f'<circle cx="20" cy="20" r="13" fill="{lens}" stroke="#4f5a64" stroke-width="3"/>')
    s.add('<path d="M12 17 Q14 11 20 10.5" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round"/>')
    return s.svg()


def window_shape(s, x=5, y=8, w=38, h=30, title="#2a8a96"):
    body = s.grad(lg([(0, "#ffffff"), (1, "#dfe6ea")]))
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{body}" stroke="#46525c" stroke-width="1"/>')
    tg = s.grad(lg([(0, "#5ec3cf"), (1, title)]))
    s.add(f'<path d="M{x} {y+2} Q{x} {y} {x+2} {y} H{x+w-2} Q{x+w} {y} {x+w} {y+2} V{y+6} H{x} Z" fill="{tg}"/>')
    s.add(f'<rect x="{x+w-5.5}" y="{y+1.3}" width="3.6" height="3.4" rx="0.8" fill="#e8613c" stroke="#fff" stroke-width="0.5"/>')


def icon_run():
    s = S(); shadow(s)
    window_shape(s, 4, 9, 34, 26)
    s.add('<path d="M23 31 L43 31 M36 24 L43 31 L36 38" fill="none" stroke="#1f8a5b" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_app():
    s = S(); shadow(s); window_shape(s)
    s.add('<rect x="9" y="18" width="12" height="15" fill="#d6e8ef" stroke="#8aa3b0" stroke-width="0.6"/>')
    s.add('<path d="M24 19 H38 M24 23 H38 M24 27 H35 M24 31 H37" stroke="#9aa8b2" stroke-width="1.2"/>')
    return s.svg()


def icon_programs():
    s = S(); shadow(s)
    window_shape(s, 13, 5, 30, 22, "#7a5aa8")
    window_shape(s, 4, 18, 30, 22)
    s.add('<path d="M8 28 H30 M8 32 H26" stroke="#9aa8b2" stroke-width="1.2"/>')
    return s.svg()


def icon_logoff():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#ffd27a"), (1, "#e2861c")]))
    s.add(f'<rect x="6" y="6" width="36" height="36" rx="7" fill="{g}" stroke="#8a4f08" stroke-width="1"/>')
    gl = s.grad(lg([(0, "#fff", 0.65), (1, "#fff", 0)]))
    s.add(f'<rect x="8" y="8" width="32" height="15" rx="6" fill="{gl}"/>')
    s.add('<path d="M22 14 H14 V34 H22" fill="none" stroke="#fff" stroke-width="3" stroke-linejoin="round"/>')
    s.add('<path d="M20 24 H35 M30 18.5 L35.5 24 L30 29.5" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_shutdown():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#ff8a6a"), (1, "#c0321a")]))
    s.add(f'<rect x="6" y="6" width="36" height="36" rx="7" fill="{g}" stroke="#7a1606" stroke-width="1"/>')
    gl = s.grad(lg([(0, "#fff", 0.6), (1, "#fff", 0)]))
    s.add(f'<rect x="8" y="8" width="32" height="15" rx="6" fill="{gl}"/>')
    s.add('<path d="M17.5 16.5 A10 10 0 1 0 30.5 16.5" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>')
    s.add('<path d="M24 11 V24" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>')
    return s.svg()


def icon_restart():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#7fe0a8"), (1, "#1f8a5b")]))
    s.add(f'<rect x="6" y="6" width="36" height="36" rx="7" fill="{g}" stroke="#0e5a36" stroke-width="1"/>')
    gl = s.grad(lg([(0, "#fff", 0.6), (1, "#fff", 0)]))
    s.add(f'<rect x="8" y="8" width="32" height="15" rx="6" fill="{gl}"/>')
    s.add('<path d="M32 18 A10 10 0 1 0 34 26" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>')
    s.add('<path d="M27 17 H33.5 V10.5" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_standby():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#ffe27a"), (1, "#d9a21c")]))
    s.add(f'<rect x="6" y="6" width="36" height="36" rx="7" fill="{g}" stroke="#7a5606" stroke-width="1"/>')
    gl = s.grad(lg([(0, "#fff", 0.6), (1, "#fff", 0)]))
    s.add(f'<rect x="8" y="8" width="32" height="15" rx="6" fill="{gl}"/>')
    s.add('<path d="M28 13 A11 11 0 1 0 35 31 A9 9 0 0 1 28 13 Z" fill="#fff"/>')
    return s.svg()


def icon_switch_user():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#8fd3f4"), (1, "#1c6fae")]))
    s.add(f'<rect x="6" y="6" width="36" height="36" rx="7" fill="{g}" stroke="#0b3f6c" stroke-width="1"/>')
    s.add('<circle cx="19" cy="20" r="5" fill="#fff"/><path d="M10 34 Q10 27 19 27 Q28 27 28 34 Z" fill="#fff"/>')
    s.add('<circle cx="31" cy="18" r="4" fill="#fff" opacity="0.8"/><path d="M24 30 Q25 24 31 24 Q38 24 38 31 H29" fill="#fff" opacity="0.8"/>')
    return s.svg()


def icon_lock():
    s = S(); shadow(s)
    s.add('<path d="M15 22 V15 A9 9 0 0 1 33 15 V22" fill="none" stroke="#8a96a0" stroke-width="4"/>')
    g = s.grad(lg([(0, "#ffd27a"), (1, "#d9861c")]))
    s.add(f'<rect x="10" y="21" width="28" height="21" rx="3" fill="{g}" stroke="#7a4a06" stroke-width="1"/>')
    s.add('<circle cx="24" cy="30" r="3" fill="#6a3a04"/><path d="M24 31 V37" stroke="#6a3a04" stroke-width="2.4"/>')
    return s.svg()


# ---------------------------------------------------------------- dokumenty
def page(s, x=9, y=4, w=30, h=40, fold=9, fill=None):
    shadow(s, cy=44.5, rx=14)
    fl = fill or s.grad(lg([(0, "#ffffff"), (1, "#e6ecf0")], 0, 0, 1, 1))
    s.add(f'<path d="M{x} {y} H{x+w-fold} L{x+w} {y+fold} V{y+h} H{x} Z" fill="{fl}" stroke="#66737d" stroke-width="1"/>')
    fg = s.grad(lg([(0, "#ffffff"), (1, "#c5d0d8")], 0, 0, 1, 1))
    s.add(f'<path d="M{x+w-fold} {y} V{y+fold} H{x+w}" fill="{fg}" stroke="#66737d" stroke-width="1" stroke-linejoin="round"/>')


def icon_file():
    s = S(); page(s); return s.svg()


def icon_file_text():
    s = S(); page(s)
    for y in range(16, 40, 4):
        w = 18 if y % 8 else 15
        s.add(f'<path d="M14 {y} H{14+w}" stroke="#5a96b5" stroke-width="1.3"/>')
    return s.svg()


def icon_notepad():
    s = S(); shadow(s, rx=14)
    pg = s.grad(lg([(0, "#fffef2"), (1, "#f0ead0")]))
    s.add(f'<rect x="9" y="7" width="30" height="36" rx="1.5" fill="{pg}" stroke="#6f6a52" stroke-width="1"/>')
    s.add('<rect x="9" y="7" width="30" height="6" fill="#4aa0c8" stroke="#2a6a8a" stroke-width="0.8"/>')
    for x in range(13, 38, 4):
        s.add(f'<path d="M{x} 4.5 V10" stroke="#5c6670" stroke-width="1.6" stroke-linecap="round"/>')
    for y in range(18, 41, 4):
        s.add(f'<path d="M12.5 {y} H35.5" stroke="#9fc4da" stroke-width="0.9"/>')
    s.add('<path d="M16 15 V41" stroke="#e88a8a" stroke-width="0.8"/>')
    return s.svg()


def icon_file_image():
    s = S(); page(s)
    sky = s.grad(lg([(0, "#7fc4ef"), (1, "#d9f0ff")]))
    s.add(f'<rect x="13" y="17" width="22" height="19" fill="{sky}" stroke="#7a8a95" stroke-width="0.7"/>')
    s.add('<path d="M13 36 L20 26 L25 32 L29 28 L35 36 Z" fill="#3f8f5b"/><circle cx="30" cy="22" r="2.3" fill="#ffd34d"/>')
    return s.svg()


def icon_file_audio():
    s = S(); page(s)
    s.add('<path d="M20 35 V21 L31 18.5 V32" fill="none" stroke="#d9531e" stroke-width="2.4"/>')
    s.add('<ellipse cx="18" cy="35" rx="3.2" ry="2.5" fill="#d9531e"/><ellipse cx="29" cy="32.2" rx="3.2" ry="2.5" fill="#d9531e"/>')
    return s.svg()


def icon_file_video():
    s = S(); page(s)
    s.add('<rect x="13" y="18" width="22" height="17" rx="1.5" fill="#2b2f36"/>')
    for x in (15.5, 20, 24.5, 29, 33):
        s.add(f'<rect x="{x-0.9}" y="19.2" width="1.8" height="1.8" fill="#fff"/><rect x="{x-0.9}" y="32" width="1.8" height="1.8" fill="#fff"/>')
    s.add('<path d="M21.5 23.5 V30 L27.5 26.7 Z" fill="#ffcf4a"/>')
    return s.svg()


def icon_file_archive():
    s = S(); page(s)
    s.add('<rect x="18" y="4.5" width="5" height="39" fill="#e8b94a" opacity="0.9"/>')
    for y in range(7, 30, 4):
        s.add(f'<rect x="19" y="{y}" width="3" height="2" fill="#7a5410"/>')
    s.add('<rect x="17" y="30" width="7" height="8" rx="1" fill="#c9cfd4" stroke="#4f5a64" stroke-width="0.9"/>')
    return s.svg()


def doc_band(color, label):
    s = S(); page(s)
    s.add(f'<rect x="9.5" y="24" width="29" height="11" fill="{color}"/>')
    s.add(f'<text x="24" y="32.5" font-family="DejaVu Sans, sans-serif" font-size="8" font-weight="bold" fill="#fff" text-anchor="middle">{label}</text>')
    s.add('<path d="M14 15 H28 M14 19 H31 M14 39 H31" stroke="#9aa8b2" stroke-width="1.2"/>')
    return s.svg()


def icon_file_pdf():
    return doc_band("#c0392b", "PDF")


def icon_file_html():
    return doc_band("#2a73b8", "HTML")


def icon_file_doc():
    return doc_band("#2a5fa8", "DOC")


def icon_file_sheet():
    return doc_band("#1f8a5b", "XLS")


def icon_file_code():
    s = S(); page(s)
    s.add('<path d="M19 20 L14 26 L19 32 M29 20 L34 26 L29 32 M26 18 L22 34" fill="none" stroke="#7a5aa8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_file_exe():
    s = S(); shadow(s); window_shape(s, 6, 9, 36, 28)
    s.add('<rect x="16" y="20" width="16" height="12" rx="1" fill="#3aa6c2"/><path d="M20 26 L23 29 L29 22" fill="none" stroke="#fff" stroke-width="2"/>')
    return s.svg()


def icon_file_font():
    s = S(); page(s)
    s.add('<text x="22.5" y="36" font-family="DejaVu Serif, serif" font-size="22" font-weight="bold" fill="#2a8a96" text-anchor="middle">A</text>')
    return s.svg()


def icon_shortcut_overlay():
    s = S()
    s.add('<rect x="1" y="27" width="20" height="20" rx="2" fill="#fff" stroke="#46525c" stroke-width="1.2"/>')
    s.add('<path d="M6 42 Q6 33 14 33 V30 L19 35 L14 40 V37 Q10 37 6 42 Z" fill="#1c6fae"/>')
    return s.svg()


# ---------------------------------------------------------------- dyski
def drive_box(s, color="#c6ced6"):
    shadow(s, cy=41, rx=19)
    top = s.grad(lg([(0, "#f6f8fa"), (1, color)]))
    s.add(f'<path d="M6 22 L12 14 H42 L42 22 Z" fill="{top}" stroke="#4f5a64" stroke-width="1"/>')
    front = s.grad(lg([(0, "#dfe5ea"), (1, "#8e9ba6")]))
    s.add(f'<rect x="4" y="22" width="40" height="15" rx="1.5" fill="{front}" stroke="#4f5a64" stroke-width="1"/>')
    s.add('<path d="M8 32 H30" stroke="#6b7680" stroke-width="1.5"/>')
    s.add('<circle cx="38" cy="30" r="1.8" fill="#36c36c" stroke="#1e6b3a" stroke-width="0.6"/>')


def icon_drive_hdd():
    s = S(); drive_box(s); return s.svg()


def icon_drive_system():
    s = S(); drive_box(s)
    sun_logo(s, 33, 13, 6.5)
    return s.svg()


def icon_drive_cd():
    s = S(); shadow(s, cy=44)
    disc = s.grad(lg([(0, "#f3f6ff"), (0.3, "#c8d6f0"), (0.5, "#f0e0ff"), (0.7, "#c8f0e6"), (1, "#e0e6f0")], 0, 0, 1, 1))
    s.add(f'<circle cx="24" cy="24" r="19" fill="{disc}" stroke="#6f7c86" stroke-width="1"/>')
    s.add('<circle cx="24" cy="24" r="6" fill="#e9eef2" stroke="#8a97a2" stroke-width="0.8"/><circle cx="24" cy="24" r="2.5" fill="#fff" stroke="#8a97a2" stroke-width="0.8"/>')
    s.add('<path d="M12 14 Q16 9 23 8" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round"/>')
    return s.svg()


def icon_drive_usb():
    s = S(); shadow(s, cy=44, rx=10)
    body = s.grad(lg([(0, "#5ec3cf"), (1, "#1f6f78")], 0, 0, 1, 0))
    s.add(f'<rect x="16" y="14" width="16" height="28" rx="3" fill="{body}" stroke="#0f4a52" stroke-width="1"/>')
    s.add('<rect x="19" y="4" width="10" height="11" fill="#d9dee3" stroke="#5e6872" stroke-width="1"/>')
    s.add('<rect x="21" y="7" width="2" height="2" fill="#5e6872"/><rect x="25" y="7" width="2" height="2" fill="#5e6872"/>')
    s.add('<circle cx="24" cy="34" r="1.6" fill="#ffcf4a"/>')
    return s.svg()


def icon_drive_network():
    s = S(); drive_box(s)
    s.add('<path d="M24 37 V44 M14 44 H34" stroke="#2a73b8" stroke-width="2"/>')
    return s.svg()


def icon_drive_floppy():
    s = S(); shadow(s)
    body = s.grad(lg([(0, "#4d5965"), (1, "#22282e")]))
    s.add(f'<path d="M7 6 H38 L42 10 V42 H7 Z" fill="{body}" stroke="#111" stroke-width="1"/>')
    s.add('<rect x="14" y="6" width="18" height="12" fill="#c9cfd4"/><rect x="25" y="8" width="4" height="8" fill="#4d5965"/>')
    s.add('<rect x="12" y="26" width="24" height="16" fill="#f4f4f0"/>')
    return s.svg()


# ---------------------------------------------------------------- aplety
def icon_taskmgr():
    s = S()
    scr = s.grad(lg([(0, "#06280f"), (1, "#0b3a18")]))
    monitor(s, screen=scr)
    s.add('<path d="M9 28 L14 22 L18 25 L23 15 L28 21 L32 17 L38 23" fill="none" stroke="#3cff6a" stroke-width="1.6"/>')
    return s.svg()


def icon_display():
    s = S()
    monitor(s)
    s.add('<circle cx="17" cy="19" r="2.6" fill="#ff6a4a"/><circle cx="24" cy="16" r="2.6" fill="#ffd34d"/><circle cx="31" cy="19" r="2.6" fill="#5ad07a"/><circle cx="24" cy="23" r="2.6" fill="#5a9cff"/>')
    return s.svg()


def icon_datetime():
    s = S(); shadow(s)
    s.add('<rect x="4" y="9" width="24" height="28" rx="2" fill="#fff" stroke="#5a6872" stroke-width="1"/>')
    s.add('<rect x="4" y="9" width="24" height="7" rx="2" fill="#c0392b"/><rect x="4" y="13" width="24" height="3" fill="#c0392b"/>')
    s.add('<text x="16" y="31" font-family="DejaVu Sans, sans-serif" font-size="12" font-weight="bold" fill="#333" text-anchor="middle">26</text>')
    face = s.grad(rg([(0, "#ffffff"), (1, "#d6e2ea")]))
    s.add(f'<circle cx="32" cy="29" r="12" fill="{face}" stroke="#2a8a96" stroke-width="2.4"/>')
    s.add('<path d="M32 29 V21.5 M32 29 L37 32" stroke="#222" stroke-width="1.8" stroke-linecap="round"/><circle cx="32" cy="29" r="1.2" fill="#c0392b"/>')
    return s.svg()


def icon_mouse():
    s = S(); shadow(s, rx=10)
    s.add('<path d="M24 4 Q24 1 28 1" fill="none" stroke="#5e6872" stroke-width="1.4"/>')
    body = s.grad(lg([(0, "#ffffff"), (1, "#b9c4cd")], 0, 0, 1, 1))
    s.add(f'<path d="M24 5 Q38 5 38 20 V30 Q38 44 24 44 Q10 44 10 30 V20 Q10 5 24 5 Z" fill="{body}" stroke="#4f5a64" stroke-width="1.1"/>')
    s.add('<path d="M10.5 20 H37.5 M24 5 V20" stroke="#4f5a64" stroke-width="1"/>')
    s.add('<rect x="22.4" y="9" width="3.2" height="7" rx="1.6" fill="#2a8a96"/>')
    return s.svg()


def icon_keyboard():
    s = S(); shadow(s)
    body = s.grad(lg([(0, "#f4f6f8"), (1, "#a9b4be")]))
    s.add(f'<path d="M3 20 L7 13 H41 L45 20 V35 Q45 37 43 37 H5 Q3 37 3 35 Z" fill="{body}" stroke="#4f5a64" stroke-width="1"/>')
    for row, y in enumerate((17, 22, 27)):
        for i in range(8):
            x = 8 + i * 4.3 + row * 1.2
            s.add(f'<rect x="{x}" y="{y}" width="3.4" height="3.4" rx="0.6" fill="#fff" stroke="#7a8590" stroke-width="0.5"/>')
    s.add('<rect x="14" y="32" width="20" height="3" rx="0.8" fill="#fff" stroke="#7a8590" stroke-width="0.5"/>')
    return s.svg()


def speaker(s, x=0, y=0, sc=1.0, waves=True, muted=False):
    body = s.grad(lg([(0, "#e8edf1"), (1, "#7c8994")]))
    s.add(f'<g transform="translate({x} {y}) scale({sc})">'
          f'<path d="M6 18 H14 L25 8 V40 L14 30 H6 Q4 30 4 28 V20 Q4 18 6 18 Z" fill="{body}" stroke="#3f4a54" stroke-width="1.1"/>')
    if muted:
        s.add('<path d="M31 18 L43 30 M43 18 L31 30" stroke="#c0392b" stroke-width="3" stroke-linecap="round"/>')
    elif waves:
        s.add('<path d="M30 17 Q35 24 30 31 M35 12 Q43 24 35 36" fill="none" stroke="#2a8a96" stroke-width="2.6" stroke-linecap="round"/>')
    s.add('</g>')


def icon_sound():
    s = S(); shadow(s); speaker(s); return s.svg()


def icon_volume():
    s = S(); speaker(s); return s.svg()


def icon_volume_muted():
    s = S(); speaker(s, muted=True); return s.svg()


def icon_system():
    s = S(); monitor(s)
    s.add('<path d="M16 20 L22 26 L33 14" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_addremove():
    s = S(); shadow(s)
    side = s.grad(lg([(0, "#d9a656"), (1, "#a8742c")]))
    s.add(f'<path d="M5 16 L24 10 L43 16 V36 L24 43 L5 36 Z" fill="{side}" stroke="#6a4610" stroke-width="1"/>')
    s.add('<path d="M5 16 L24 22 L43 16 M24 22 V43" fill="none" stroke="#6a4610" stroke-width="1"/>')
    s.add('<path d="M24 22 L43 16 V36 L24 43 Z" fill="#c48d40" opacity="0.6"/>')
    disc = s.grad(lg([(0, "#f3f6ff"), (0.4, "#c8d6f0"), (0.6, "#f0e0ff"), (1, "#c8f0e6")], 0, 0, 1, 1))
    s.add(f'<circle cx="30" cy="12" r="10" fill="{disc}" stroke="#6f7c86" stroke-width="0.9"/><circle cx="30" cy="12" r="2.6" fill="#fff" stroke="#8a97a2" stroke-width="0.7"/>')
    return s.svg()


def icon_network_conn():
    s = S(); shadow(s)
    for x, c in ((6, "#2a8ab0"), (26, "#2a8ab0")):
        body = s.grad(lg([(0, "#f4f6f8"), (1, "#b0bac4")]))
        s.add(f'<rect x="{x}" y="10" width="16" height="13" rx="1.2" fill="{body}" stroke="#56606a" stroke-width="0.9"/>')
        s.add(f'<rect x="{x+2}" y="12" width="12" height="8.5" fill="{c}"/>')
        s.add(f'<path d="M{x+5} 23 H{x+11} L{x+12} 26 H{x+4} Z" fill="#9aa5b0" stroke="#56606a" stroke-width="0.6"/>')
    s.add('<path d="M14 26 V34 H34 V26" fill="none" stroke="#2a73b8" stroke-width="2"/>')
    s.add('<rect x="19" y="31" width="10" height="7" rx="1" fill="#f0a030" stroke="#8a5410" stroke-width="0.8"/>')
    return s.svg()


def person(s, x, y, sc, c1, c2):
    g = s.grad(lg([(0, c1), (1, c2)]))
    s.add(f'<g transform="translate({x} {y}) scale({sc})">'
          f'<circle cx="12" cy="8" r="7" fill="#f5cfa8" stroke="#8a5a30" stroke-width="0.9"/>'
          f'<path d="M5 6 Q6 0 12 0.5 Q19 0 19.5 7 Q16 3.5 12 4 Q8 4 5 6 Z" fill="#6a4020"/>'
          f'<path d="M0 30 Q0 17 12 17 Q24 17 24 30 Z" fill="{g}" stroke="#2a3a44" stroke-width="0.9"/></g>')


def icon_users():
    s = S(); shadow(s)
    person(s, 20, 8, 1.0, "#f0a030", "#b8661a")
    person(s, 4, 13, 1.05, "#5ec3cf", "#1f6f78")
    return s.svg()


def icon_user():
    s = S(); shadow(s, rx=12)
    person(s, 11, 8, 1.1, "#5ec3cf", "#1f6f78")
    return s.svg()


def icon_fonts():
    s = S(); folder(s)
    s.add('<text x="30" y="38" font-family="DejaVu Serif, serif" font-size="20" font-weight="bold" fill="#2a8a96" stroke="#fff" stroke-width="0.8" text-anchor="middle">A</text>')
    return s.svg()


def icon_taskbar_props():
    s = S(); shadow(s)
    window_shape(s, 6, 6, 36, 28)
    tb = s.grad(lg([(0, "#3aa6b2"), (1, "#0e5560")]))
    s.add(f'<rect x="3" y="34" width="42" height="7" rx="1" fill="{tb}" stroke="#0a3a42" stroke-width="0.8"/>')
    s.add('<rect x="4" y="35" width="10" height="5" rx="2.4" fill="#f0a030"/><rect x="16" y="35.5" width="9" height="4" rx="1" fill="#5ec3cf"/>')
    s.add('<rect x="6" y="16" width="14" height="18" fill="#fff" stroke="#46525c" stroke-width="0.8"/><rect x="6" y="16" width="14" height="4" fill="#2a8a96"/>')
    return s.svg()


def gear(s, cx, cy, r, c1="#d8dde2", c2="#7c8994"):
    import math
    pts = []
    teeth = 8
    for i in range(teeth * 2):
        a = math.pi * i / teeth
        rr = r if i % 2 == 0 else r * 0.78
        a1, a2 = a - math.pi / (teeth * 2.6), a + math.pi / (teeth * 2.6)
        pts.append(f"{cx + rr*math.cos(a1):.2f},{cy + rr*math.sin(a1):.2f}")
        pts.append(f"{cx + rr*math.cos(a2):.2f},{cy + rr*math.sin(a2):.2f}")
    g = s.grad(lg([(0, c1), (1, c2)], 0, 0, 1, 1))
    s.add(f'<polygon points="{" ".join(pts)}" fill="{g}" stroke="#3f4a54" stroke-width="0.9"/>')
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.32}" fill="#fff" stroke="#3f4a54" stroke-width="0.8"/>')


def icon_folder_options():
    s = S(); folder(s); gear(s, 33, 31, 9); return s.svg()


def icon_admin():
    s = S(); shadow(s)
    gear(s, 19, 21, 14)
    s.add('<path d="M28 32 L40 44" stroke="#5a3a1c" stroke-width="6" stroke-linecap="round"/>')
    s.add('<path d="M28 32 L40 44" stroke="#c48d40" stroke-width="3.6" stroke-linecap="round"/>')
    s.add('<circle cx="27" cy="30" r="5.5" fill="none" stroke="#8a97a2" stroke-width="3"/>')
    return s.svg()


def icon_regional():
    s = S(); shadow(s)
    globe = s.grad(rg([(0, "#d8f6ff"), (0.55, "#3fa8dc"), (1, "#0e4e86")], 0.38, 0.32, 0.7))
    s.add(f'<circle cx="21" cy="21" r="16" fill="{globe}" stroke="#0b3f6c" stroke-width="1"/>')
    s.add('<path d="M9 14 Q14 17 13 22 Q12 26 16 29 M25 6 Q23 11 27 13 Q32 15 30 21" fill="none" stroke="#45b86e" stroke-width="3.4" stroke-linecap="round"/>')
    face = s.grad(rg([(0, "#ffffff"), (1, "#d6e2ea")]))
    s.add(f'<circle cx="34" cy="33" r="10" fill="{face}" stroke="#f0a030" stroke-width="2.2"/>')
    s.add('<path d="M34 33 V27 M34 33 L38 35" stroke="#222" stroke-width="1.6" stroke-linecap="round"/>')
    return s.svg()


def icon_power():
    s = S(); shadow(s)
    batt = s.grad(lg([(0, "#e8edf1"), (1, "#9aa6b0")], 0, 0, 1, 0))
    s.add(f'<rect x="8" y="10" width="20" height="32" rx="2.5" fill="{batt}" stroke="#3f4a54" stroke-width="1"/>')
    s.add('<rect x="14" y="6" width="8" height="5" rx="1" fill="#5e6872"/>')
    lvl = s.grad(lg([(0, "#7fe0a8"), (1, "#1f8a5b")]))
    s.add(f'<rect x="11" y="22" width="14" height="17" rx="1" fill="{lvl}"/>')
    s.add('<path d="M38 8 L30 26 H37 L33 42 L44 20 H37 L41 8 Z" fill="#ffcf4a" stroke="#8a6200" stroke-width="1" stroke-linejoin="round"/>')
    return s.svg()


def icon_accessibility():
    s = S(); round_badge(s, "#8fd3f4", "#1c6fae")
    s.add('<circle cx="24" cy="12.5" r="3.2" fill="#fff"/>')
    s.add('<path d="M13 18 L24 20 L35 18 M24 20 V28 L18 37 M24 28 L30 37" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_scheduled():
    s = S(); folder(s)
    face = s.grad(rg([(0, "#ffffff"), (1, "#d6e2ea")]))
    s.add(f'<circle cx="33" cy="31" r="9" fill="{face}" stroke="#2a8a96" stroke-width="2"/>')
    s.add('<path d="M33 31 V25.5 M33 31 L37 33" stroke="#222" stroke-width="1.6" stroke-linecap="round"/>')
    return s.svg()


def icon_security():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#ff6a5a"), (0.5, "#f0a030"), (0.5, "#2a8a96"), (1, "#145a8a")], 0, 0, 1, 1))
    s.add(f'<path d="M24 4 L40 10 V22 Q40 36 24 44 Q8 36 8 22 V10 Z" fill="{g}" stroke="#1f2a33" stroke-width="1.2"/>')
    s.add('<path d="M24 4 V44 M8 22 H40" stroke="#fff" stroke-width="1.6" opacity="0.8"/>')
    return s.svg()


def icon_games():
    s = S(); shadow(s)
    s.add('<rect x="6" y="10" width="20" height="28" rx="2.5" fill="#fff" stroke="#46525c" stroke-width="1" transform="rotate(-12 16 24)"/>')
    s.add('<path d="M14 18 Q14 14 16.5 14 Q19 14 19 18 Q19 21 16.5 24 Q14 21 14 18 Z" fill="#c0392b" transform="rotate(-12 16 24)"/>')
    s.add('<rect x="20" y="10" width="20" height="28" rx="2.5" fill="#fff" stroke="#46525c" stroke-width="1" transform="rotate(10 30 24)"/>')
    s.add('<path d="M30 15 L34 21 L30 27 L26 21 Z" fill="#c0392b" transform="rotate(10 30 24)"/>')
    s.add('<text x="25" y="35" font-family="DejaVu Serif, serif" font-size="9" font-weight="bold" fill="#222" transform="rotate(10 30 24)">A</text>')
    return s.svg()


def icon_accessories():
    return icon_programs()


def icon_terminal():
    s = S(); shadow(s)
    s.add('<rect x="4" y="8" width="40" height="32" rx="2" fill="#151a1e" stroke="#46525c" stroke-width="1"/>')
    s.add('<rect x="4" y="8" width="40" height="6" rx="2" fill="#7c8994"/><rect x="4" y="11" width="40" height="3" fill="#7c8994"/>')
    s.add('<path d="M10 21 L16 26 L10 31" fill="none" stroke="#d8dde2" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
    s.add('<path d="M19 32 H28" stroke="#d8dde2" stroke-width="2.4" stroke-linecap="round"/>')
    return s.svg()


def icon_calculator():
    s = S(); shadow(s, rx=13)
    body = s.grad(lg([(0, "#f4f6f8"), (1, "#a9b4be")], 0, 0, 1, 1))
    s.add(f'<rect x="10" y="4" width="28" height="39" rx="3" fill="{body}" stroke="#46525c" stroke-width="1"/>')
    s.add('<rect x="13.5" y="7.5" width="21" height="8" rx="1" fill="#cfe6d2" stroke="#5e6872" stroke-width="0.7"/>')
    s.add('<text x="33" y="14" font-family="DejaVu Sans Mono, monospace" font-size="6" fill="#223" text-anchor="end">123</text>')
    for r in range(4):
        for c in range(4):
            col = "#f0a030" if c == 3 else "#ffffff"
            s.add(f'<rect x="{13.5 + c*5.4}" y="{19 + r*5.6}" width="4.4" height="4.4" rx="0.8" fill="{col}" stroke="#7a8590" stroke-width="0.5"/>')
    return s.svg()


def icon_paint():
    s = S(); shadow(s)
    pal = s.grad(lg([(0, "#f2d9a8"), (1, "#c8a46a")]))
    s.add(f'<path d="M24 8 Q42 8 43 22 Q44 32 34 31 Q29 31 30 36 Q31 42 23 41 Q6 40 6 25 Q6 8 24 8 Z" fill="{pal}" stroke="#6a4a20" stroke-width="1"/>')
    for cx, cy, c in ((15, 20, "#c0392b"), (22, 14, "#f0a030"), (31, 15, "#ffd34d"), (37, 22, "#2f9e5b"), (13, 30, "#2a73b8")):
        s.add(f'<circle cx="{cx}" cy="{cy}" r="3.2" fill="{c}" stroke="#4a3010" stroke-width="0.5"/>')
    s.add('<path d="M44 4 L24 30" stroke="#8a5a30" stroke-width="3" stroke-linecap="round"/><path d="M24 30 L21 35 L26 32 Z" fill="#222"/>')
    return s.svg()


def icon_wordpad():
    s = S(); page(s)
    s.add('<text x="13" y="24" font-family="DejaVu Serif, serif" font-size="11" font-weight="bold" fill="#2a5fa8">A</text>')
    s.add('<path d="M22 17 H33 M22 21 H31 M14 27 H33 M14 31 H30 M14 35 H33 M14 39 H27" stroke="#5a6872" stroke-width="1.2"/>')
    return s.svg()


def icon_mines():
    s = S(); shadow(s)
    s.add('<circle cx="24" cy="25" r="12" fill="#222"/>')
    for a in range(0, 360, 45):
        s.add(f'<path d="M24 25 L24 8" stroke="#222" stroke-width="3" transform="rotate({a} 24 25)" stroke-linecap="round"/>')
    s.add('<circle cx="20" cy="21" r="3" fill="#fff"/>')
    return s.svg()


def icon_cards():
    return icon_games()


def icon_charmap():
    s = S(); shadow(s)
    s.add('<rect x="5" y="7" width="38" height="33" rx="2" fill="#fff" stroke="#46525c" stroke-width="1"/>')
    for i in range(1, 4):
        s.add(f'<path d="M{5+i*9.5} 7 V40 M5 {7+i*8.25} H43" stroke="#b9c4cd" stroke-width="0.8"/>')
    s.add('<text x="24" y="31" font-family="DejaVu Serif, serif" font-size="18" font-weight="bold" fill="#2a8a96" text-anchor="middle">Ω</text>')
    return s.svg()


def icon_image_viewer():
    s = S(); shadow(s)
    s.add('<rect x="5" y="9" width="38" height="30" rx="2" fill="#fff" stroke="#46525c" stroke-width="1"/>')
    sky = s.grad(lg([(0, "#7fc4ef"), (1, "#d9f0ff")]))
    s.add(f'<rect x="8" y="12" width="32" height="24" fill="{sky}"/>')
    s.add('<path d="M8 36 L18 23 L25 31 L30 26 L40 36 Z" fill="#3f8f5b"/><circle cx="33" cy="18" r="3" fill="#ffd34d"/>')
    return s.svg()


def icon_media_player():
    s = S(); round_badge(s, "#ffd27a", "#d9701c", stroke="#7a3a06")
    s.add('<path d="M19 14 V34 L35 24 Z" fill="#fff"/>')
    return s.svg()


def icon_sysinfo():
    s = S(); monitor(s)
    s.add('<circle cx="24" cy="15" r="2" fill="#fff"/><path d="M24 19.5 V27" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>')
    return s.svg()


def icon_disk_cleanup():
    s = S(); drive_box(s)
    s.add('<path d="M30 4 L22 22" stroke="#8a5a30" stroke-width="2.6" stroke-linecap="round"/>')
    s.add('<path d="M18 20 L26 24 L22 30 L14 26 Z" fill="#f0c040" stroke="#8a6200" stroke-width="0.8"/>')
    return s.svg()


def icon_recorder():
    s = S(); round_badge(s, "#cfd6dc", "#6f7c86", stroke="#3f4a54")
    s.add('<rect x="19" y="10" width="10" height="18" rx="5" fill="#2b2f36"/><path d="M15 23 Q15 32 24 32 Q33 32 33 23 M24 32 V38 M18 38 H30" fill="none" stroke="#2b2f36" stroke-width="2.2"/>')
    return s.svg()


# ---------------------------------------------------------------- nawigacja
def nav_arrow(direction="left", c1="#7fe0e8", c2="#1f7a86", stroke="#0e4a52"):
    s = S()
    g = s.grad(rg([(0, c1), (1, c2)], 0.45, 0.35, 0.7))
    s.add(f'<circle cx="24" cy="24" r="20" fill="{g}" stroke="{stroke}" stroke-width="1.4"/>')
    gl = s.grad(lg([(0, "#fff", 0.7), (1, "#fff", 0)]))
    s.add(f'<ellipse cx="24" cy="14" rx="14" ry="8" fill="{gl}"/>')
    rot = {"left": 0, "right": 180, "up": 90, "down": 270}[direction]
    s.add(f'<path d="M30 13 L18 24 L30 35" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" transform="rotate({rot} 24 24)"/>')
    return s.svg()


def icon_back():
    return nav_arrow("left")


def icon_forward():
    return nav_arrow("right")


def icon_go():
    return nav_arrow("right", "#ffd27a", "#d9701c", "#7a3a06")


def icon_up():
    s = S(); folder(s)
    s.add('<path d="M24 37 V24 M17 29 L24 22 L31 29" fill="none" stroke="#1f7a86" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_views():
    s = S()
    for i, (x, y) in enumerate(((6, 6), (26, 6), (6, 26), (26, 26))):
        g = s.grad(lg([(0, "#ffffff"), (1, "#c6d0d8")]))
        s.add(f'<rect x="{x}" y="{y}" width="16" height="16" rx="2" fill="{g}" stroke="#46525c" stroke-width="1"/>')
        s.add(f'<rect x="{x+3}" y="{y+3}" width="10" height="7" fill="#3aa6c2"/>')
    return s.svg()


def icon_folders_tree():
    s = S()
    s.add('<path d="M10 10 V38 H22 M10 22 H22" fill="none" stroke="#6b7680" stroke-width="1.6" stroke-dasharray="2 1.6"/>')
    s.add('<g transform="translate(-2 -6) scale(0.5)">'); folder(s); s.add('</g>')
    s.add('<g transform="translate(18 10) scale(0.55)">'); folder(s); s.add('</g>')
    s.add('<g transform="translate(18 26) scale(0.55)">'); folder(s); s.add('</g>')
    return s.svg()


def icon_new_folder():
    s = S(); folder(s)
    s.add('<path d="M36 4 L38 10 L44 10 L39 14 L41 20 L36 16 L31 20 L33 14 L28 10 L34 10 Z" fill="#ffd34d" stroke="#8a6200" stroke-width="0.8"/>')
    return s.svg()


def icon_cut():
    s = S()
    s.add('<path d="M16 6 L30 32 M32 6 L18 32" stroke="#6b7680" stroke-width="3" stroke-linecap="round"/>')
    s.add('<circle cx="15" cy="36" r="6" fill="none" stroke="#c0392b" stroke-width="3"/><circle cx="33" cy="36" r="6" fill="none" stroke="#c0392b" stroke-width="3"/>')
    return s.svg()


def icon_copy():
    s = S()
    page(s, 5, 4, 24, 30, 6); page(s, 18, 13, 24, 30, 6)
    return s.svg()


def icon_paste():
    s = S(); shadow(s)
    board = s.grad(lg([(0, "#d9a656"), (1, "#a8742c")]))
    s.add(f'<rect x="7" y="8" width="26" height="34" rx="2" fill="{board}" stroke="#6a4610" stroke-width="1"/>')
    s.add('<rect x="13" y="5" width="14" height="7" rx="2" fill="#c9cfd4" stroke="#4f5a64" stroke-width="0.9"/>')
    s.add('<path d="M20 18 H36 L41 23 V44 H20 Z" fill="#fff" stroke="#66737d" stroke-width="1"/>')
    s.add('<path d="M24 28 H37 M24 32 H37 M24 36 H33" stroke="#5a96b5" stroke-width="1.2"/>')
    return s.svg()


def icon_delete():
    s = S()
    s.add('<path d="M10 10 L38 38 M38 10 L10 38" stroke="#7a1606" stroke-width="9" stroke-linecap="round"/>')
    s.add('<path d="M10 10 L38 38 M38 10 L10 38" stroke="#e8483a" stroke-width="6" stroke-linecap="round"/>')
    return s.svg()


def icon_properties():
    s = S(); page(s)
    s.add('<rect x="13" y="16" width="5" height="5" fill="#2a8a96"/><path d="M21 18.5 H33" stroke="#5a6872" stroke-width="1.4"/>')
    s.add('<rect x="13" y="25" width="5" height="5" fill="#f0a030"/><path d="M21 27.5 H33" stroke="#5a6872" stroke-width="1.4"/>')
    s.add('<rect x="13" y="34" width="5" height="5" fill="#2f9e5b"/><path d="M21 36.5 H31" stroke="#5a6872" stroke-width="1.4"/>')
    return s.svg()


def icon_undo():
    s = S()
    s.add('<path d="M14 18 H30 Q40 18 40 28 Q40 38 30 38 H18" fill="none" stroke="#1f7a86" stroke-width="5" stroke-linecap="round"/>')
    s.add('<path d="M18 8 L8 18 L18 28 Z" fill="#1f7a86"/>')
    return s.svg()


def icon_refresh():
    s = S()
    s.add('<path d="M38 20 A15 15 0 1 0 39 30" fill="none" stroke="#1f8a5b" stroke-width="5" stroke-linecap="round"/>')
    s.add('<path d="M42 8 V22 H28 Z" fill="#1f8a5b"/>')
    return s.svg()


def icon_tray_network():
    s = S()
    for x, y in ((3, 4), (19, 18)):
        s.add(f'<rect x="{x}" y="{y}" width="24" height="17" rx="1.5" fill="#e9eef2" stroke="#2c3a44" stroke-width="2"/>')
        s.add(f'<rect x="{x+3}" y="{y+3}" width="18" height="10" fill="#3aa6c2"/>')
    s.add('<rect x="10" y="22" width="10" height="4" fill="#2c3a44"/><rect x="26" y="36" width="10" height="4" fill="#2c3a44"/>')
    return s.svg()


def icon_tray_network_off():
    s = S()
    s.add(icon_tray_network().split("</defs>")[1].replace("</svg>", ""))
    s.add('<circle cx="36" cy="12" r="10" fill="#c0392b" stroke="#fff" stroke-width="2"/><path d="M31 7 L41 17 M41 7 L31 17" stroke="#fff" stroke-width="3"/>')
    return s.svg()


def icon_tray_battery():
    return icon_power()


def icon_star():
    s = S()
    g = s.grad(lg([(0, "#fff1a6"), (1, "#f2b51c")]))
    s.add(f'<path d="M24 4 L29.5 17 L43 18 L32.5 27 L36 41 L24 33.5 L12 41 L15.5 27 L5 18 L18.5 17 Z" fill="{g}" stroke="#8a6200" stroke-width="1.2"/>')
    return s.svg()


def icon_chevron_down():
    s = S()
    s.add('<path d="M12 16 L24 28 L36 16 M12 26 L24 38 L36 26" fill="none" stroke="#1f6f78" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_show_desktop():
    s = S(); shadow(s)
    s.add('<rect x="4" y="8" width="40" height="30" rx="2" fill="#3a6e8f" stroke="#1f3a4a" stroke-width="1"/>')
    s.add('<path d="M4 30 Q16 22 26 28 Q36 33 44 26 V36 Q44 38 42 38 H6 Q4 38 4 36 Z" fill="#2a8a96"/>')
    s.add('<rect x="8" y="12" width="5" height="5" fill="#ffd34d"/><rect x="8" y="20" width="5" height="5" fill="#fff"/>')
    s.add('<path d="M28 8 L40 4 V30 L28 34 Z" fill="#e9eef2" stroke="#46525c" stroke-width="1"/>')
    return s.svg()


# ---------------------------------------------------------------- logo i obrazy kont
def sun_logo(s, cx=24, cy=24, r=20):
    """Własne logo środowiska: słońce wschodzące nad linią horyzontu."""
    import math
    g = s.grad(rg([(0, "#fff6c8"), (0.5, "#ffc13a"), (1, "#e8701c")], 0.45, 0.4, 0.6))
    rays = []
    for i in range(12):
        a = math.pi * 2 * i / 12
        x1, y1 = cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62
        x2, y2 = cx + math.cos(a) * r * 0.98, cy + math.sin(a) * r * 0.98
        rays.append(f'<path d="M{x1:.2f} {y1:.2f} L{x2:.2f} {y2:.2f}" stroke="#ffcf4a" stroke-width="{r*0.13:.2f}" stroke-linecap="round"/>')
    s.add("".join(rays))
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.5:.2f}" fill="{g}" stroke="#b8501a" stroke-width="{max(0.6, r*0.04):.2f}"/>')
    s.add(f'<path d="M{cx - r*0.5:.2f} {cy + r*0.12:.2f} H{cx + r*0.5:.2f}" stroke="#fff" stroke-width="{r*0.07:.2f}" opacity="0.85"/>')
    s.add(f'<path d="M{cx - r*0.42:.2f} {cy + r*0.27:.2f} H{cx + r*0.42:.2f}" stroke="#fff" stroke-width="{r*0.06:.2f}" opacity="0.65"/>')


def icon_logo():
    s = S(); sun_logo(s); return s.svg()


def avatar(bg1, bg2, content):
    s = S()
    g = s.grad(lg([(0, bg1), (1, bg2)]))
    s.add(f'<rect x="0" y="0" width="48" height="48" fill="{g}"/>')
    content(s)
    return s.svg()


def _kite(s):
    s.add('<path d="M28 6 L40 18 L28 34 L16 18 Z" fill="#e8483a" stroke="#7a1606" stroke-width="1"/>')
    s.add('<path d="M28 6 V34 M16 18 H40" stroke="#ffd34d" stroke-width="1.4"/>')
    s.add('<path d="M28 34 Q24 40 28 44 Q32 47 26 48" fill="none" stroke="#5a3a1c" stroke-width="1"/>')
    for x, y in ((25, 39), (29, 44)):
        s.add(f'<path d="M{x-2} {y} L{x+2} {y-1} L{x+2} {y+1} Z" fill="#2a8a96"/>')
    s.add('<ellipse cx="10" cy="10" rx="7" ry="3" fill="#fff" opacity="0.8"/>')


def _boat(s):
    s.add('<rect x="0" y="32" width="48" height="16" fill="#1f6f9a"/>')
    s.add('<path d="M0 36 Q6 34 12 36 T24 36 T36 36 T48 36" fill="none" stroke="#9fd4f2" stroke-width="1"/>')
    s.add('<path d="M24 6 V30 L10 30 Z" fill="#fff" stroke="#46525c" stroke-width="0.8"/><path d="M26 10 V30 L38 30 Z" fill="#f0a030" stroke="#46525c" stroke-width="0.8"/>')
    s.add('<path d="M8 31 H40 L36 37 H12 Z" fill="#8a3a1c"/>')


def _flower(s):
    s.add('<path d="M24 26 Q22 38 26 48" stroke="#2f7a3a" stroke-width="2.4" fill="none"/>')
    s.add('<path d="M25 38 Q32 32 38 36 Q31 41 25 38 Z" fill="#3f9f4a"/>')
    for a in range(0, 360, 36):
        s.add(f'<ellipse cx="24" cy="12" rx="4" ry="8" fill="#ffd34d" stroke="#c88a10" stroke-width="0.6" transform="rotate({a} 24 20)"/>')
    s.add('<circle cx="24" cy="20" r="6" fill="#7a4a24"/>')


def _cat(s):
    s.add('<circle cx="38" cy="10" r="6" fill="#fff6c8"/>')
    s.add('<path d="M10 48 Q8 30 18 26 L16 16 L22 22 Q26 21 30 22 L36 16 L34 26 Q42 30 40 48 Z" fill="#2b2f36"/>')
    s.add('<circle cx="21" cy="29" r="1.6" fill="#ffd34d"/><circle cx="29" cy="29" r="1.6" fill="#ffd34d"/>')


def _guitar(s):
    s.add('<path d="M30 4 L34 8 L22 24" stroke="#3a2a1a" stroke-width="3" stroke-linecap="round"/>')
    s.add('<path d="M22 22 Q30 26 28 34 Q26 44 16 44 Q6 44 6 34 Q6 26 14 26 Q18 20 22 22 Z" fill="#c8701c" stroke="#5a3010" stroke-width="1"/>')
    s.add('<circle cx="17" cy="33" r="3.4" fill="#2b1a0a"/>')


def _planet(s):
    for x, y in ((6, 8), (40, 6), (36, 40), (8, 38), (20, 4)):
        s.add(f'<circle cx="{x}" cy="{y}" r="0.9" fill="#fff"/>')
    g = s.grad(rg([(0, "#ffd9a8"), (1, "#c8701c")], 0.4, 0.35, 0.7))
    s.add(f'<circle cx="24" cy="24" r="12" fill="{g}"/>')
    s.add('<ellipse cx="24" cy="24" rx="21" ry="5.5" fill="none" stroke="#9fd4f2" stroke-width="2" transform="rotate(-20 24 24)"/>')


def icon_avatar_kite():
    return avatar("#8fd3f4", "#d9f2ff", _kite)


def icon_avatar_boat():
    return avatar("#ffd9a8", "#9fd4f2", _boat)


def icon_avatar_flower():
    return avatar("#9fd4f2", "#e6f7ff", _flower)


def icon_avatar_cat():
    return avatar("#3a3f6a", "#8a6aa8", _cat)


def icon_avatar_guitar():
    return avatar("#f6e6c8", "#e0b878", _guitar)


def icon_avatar_planet():
    return avatar("#0e1a3a", "#2a3a6a", _planet)


AVATARS = ["kite", "boat", "flower", "cat", "guitar", "planet"]


# ---------------------------------------------------------------- rejestr
ICONS = {name[5:]: fn for name, fn in globals().items() if name.startswith("icon_") and callable(fn)}


def _load_extra():
    from .icons_extra import EXTRA
    for k, fn in EXTRA.items():
        ICONS.setdefault(k, fn)

ALIASES = {
    "trash": "recycle_empty",
    "documents_folder": "documents",
    "explorer": "folder_open",
    "text": "file_text",
    "image": "file_image",
    "audio": "file_audio",
    "video": "file_video",
    "archive": "file_archive",
    "exe": "file_exe",
    "pdf": "file_pdf",
    "html": "file_html",
    "word": "file_doc",
    "sheet": "file_sheet",
    "code": "file_code",
}


@lru_cache(maxsize=None)
def svg_for(name):
    if "key" not in ICONS:
        _load_extra()
    name = ALIASES.get(name, name)
    if name.startswith("avatar_") or name in ICONS:
        fn = ICONS.get(name)
        if fn:
            return fn()
    return ICONS["file"]()


def has(name):
    if "key" not in ICONS:
        _load_extra()
    return ALIASES.get(name, name) in ICONS
