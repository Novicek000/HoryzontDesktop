"""Ikony dodane w wersji 0.2 (te same zasady co w icons.py: viewBox 48x48, własne rysunki)."""
from .icons import S, lg, rg, shadow, folder, monitor, page


def _wifi_arcs(s, cx, cy, level, color="#2a8a96", off="#b9c4c9", sc=1.0, width=3.2):
    for i, r in enumerate((6, 12, 18, 24)):
        r *= sc
        col = color if i < level else off
        s.add(f'<path d="M{cx - r * 0.72:.1f} {cy - r * 0.72:.1f} A{r:.1f} {r:.1f} 0 0 1 {cx + r * 0.72:.1f} {cy - r * 0.72:.1f}" '
              f'fill="none" stroke="{col}" stroke-width="{width * sc:.1f}" stroke-linecap="round"/>')
    s.add(f'<circle cx="{cx}" cy="{cy - 1}" r="{2.6 * sc:.1f}" fill="{color if level > 0 else off}"/>')


def icon_key():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#ffe08a"), (1, "#d18a12")], 0, 0, 1, 1))
    s.add(f'<circle cx="15" cy="17" r="10" fill="{g}" stroke="#7a4a06" stroke-width="1.2"/>')
    s.add('<circle cx="12.5" cy="14.5" r="3.2" fill="#fff8e0" stroke="#7a4a06" stroke-width="1"/>')
    s.add(f'<path d="M21.5 23.5 L40 42 L43 39 L40 36 L42.5 33.5 L39.5 30.5 L37 33 L35 31 L37.5 28.5 L34.5 25.5 L32 28 L25 21 Z" '
          f'fill="{g}" stroke="#7a4a06" stroke-width="1.1" stroke-linejoin="round"/>')
    return s.svg()


def shield(s, x=0, y=0, sc=1.0, c1="#5bc0de", c2="#1f6f9a"):
    g = s.grad(lg([(0, c1), (1, c2)]))
    s.add(f'<g transform="translate({x} {y}) scale({sc})"><path d="M24 4 L40 10 V22 Q40 36 24 44 Q8 36 8 22 V10 Z" '
          f'fill="{g}" stroke="#123a55" stroke-width="1.2"/>'
          '<path d="M24 7 L37 12 V22 Q37 33 24 40 Z" fill="#fff" opacity="0.22"/></g>')


def globe(s, cx=22, cy=22, r=17):
    g = s.grad(rg([(0, "#bfe9ff"), (0.6, "#3d9bd6"), (1, "#1a5e9a")], 0.4, 0.35, 0.7))
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{g}" stroke="#123f66" stroke-width="1"/>')
    s.add(f'<path d="M{cx - 9} {cy - 10} Q{cx - 2} {cy - 13} {cx + 1} {cy - 6} Q{cx - 4} {cy - 2} {cx - 8} {cy + 1} '
          f'Q{cx - 13} {cy - 3} {cx - 9} {cy - 10} Z M{cx + 4} {cy + 2} Q{cx + 11} {cy} {cx + 12} {cy + 7} '
          f'Q{cx + 6} {cy + 14} {cx + 2} {cy + 10} Z" fill="#5fbf5a" opacity="0.9"/>')
    s.add(f'<ellipse cx="{cx - 5}" cy="{cy - 7}" rx="8" ry="4.5" fill="#fff" opacity="0.3"/>')


def arrows_round(s, cx=34, cy=34, r=10, color="#2ea043"):
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r + 2}" fill="#fff" stroke="#3a6e3a" stroke-width="1"/>')
    s.add(f'<path d="M{cx - r * 0.75:.1f} {cy - 2} A{r * 0.75:.1f} {r * 0.75:.1f} 0 0 1 {cx + r * 0.6:.1f} {cy - r * 0.45:.1f}" '
          f'fill="none" stroke="{color}" stroke-width="3"/>')
    s.add(f'<path d="M{cx + r * 0.75:.1f} {cy + 2} A{r * 0.75:.1f} {r * 0.75:.1f} 0 0 1 {cx - r * 0.6:.1f} {cy + r * 0.45:.1f}" '
          f'fill="none" stroke="{color}" stroke-width="3"/>')
    s.add(f'<path d="M{cx + r * 0.95:.1f} {cy - r * 0.75:.1f} L{cx + r * 0.6:.1f} {cy - r * 0.05:.1f} L{cx + r * 0.05:.1f} {cy - r * 0.6:.1f} Z" fill="{color}"/>')
    s.add(f'<path d="M{cx - r * 0.95:.1f} {cy + r * 0.75:.1f} L{cx - r * 0.6:.1f} {cy + r * 0.05:.1f} L{cx - r * 0.05:.1f} {cy + r * 0.6:.1f} Z" fill="{color}"/>')


def icon_updates():
    """Horyzont Updates — globus z zieloną strzałką odświeżania."""
    s = S(); shadow(s)
    globe(s)
    arrows_round(s)
    return s.svg()


def icon_auto_updates():
    s = S(); shadow(s)
    shield(s, 0, 0, 0.92)
    s.add('<circle cx="34" cy="34" r="11" fill="#fff" stroke="#46525c" stroke-width="1"/>'
          '<path d="M34 27 V34 L39 37" fill="none" stroke="#2a3a44" stroke-width="2.2" stroke-linecap="round"/>')
    return s.svg()


def icon_tray_updates():
    s = S()
    shield(s, 0, 0, 1.0, "#ffd34d", "#d98a00")
    s.add('<path d="M24 13 V31 M16 24 L24 32 L32 24" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_wifi():
    s = S(); shadow(s)
    monitor(s, x=4, y=14, w=26, h=19)
    _wifi_arcs(s, 35, 24, 4, sc=0.75)
    return s.svg()


def _tray_wifi(level, off=False):
    s = S()
    _wifi_arcs(s, 24, 40, level, "#ffffff" if not off else "#9aa6ad", "#5f7a85", sc=1.25, width=4.0)
    if off:
        s.add('<circle cx="36" cy="12" r="10" fill="#c0392b" stroke="#fff" stroke-width="2"/>'
              '<path d="M31 7 L41 17 M41 7 L31 17" stroke="#fff" stroke-width="3"/>')
    return s.svg()


def icon_tray_wifi_0():
    return _tray_wifi(0)


def icon_tray_wifi_1():
    return _tray_wifi(1)


def icon_tray_wifi_2():
    return _tray_wifi(2)


def icon_tray_wifi_3():
    return _tray_wifi(3)


def icon_tray_wifi_4():
    return _tray_wifi(4)


def icon_tray_wifi_off():
    return _tray_wifi(0, True)


def icon_signal_bars():
    s = S()
    for i in range(5):
        h = 8 + i * 7
        s.add(f'<rect x="{4 + i * 8.5}" y="{44 - h}" width="6.5" height="{h}" fill="#3ab54a" stroke="#1d6b28" stroke-width="0.8"/>')
    return s.svg()


def bt_rune(s, cx=24, cy=24, sc=1.0, color="#ffffff", width=3.2):
    s.add(f'<path transform="translate({cx} {cy}) scale({sc}) translate(-24 -24)" '
          f'd="M16 16 L32 31 L24 39 V9 L32 17 L16 32" fill="none" stroke="{color}" stroke-width="{width}" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')


def icon_bluetooth():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#4aa3f0"), (1, "#0b4f9c")]))
    s.add(f'<path d="M24 3 Q41 3 41 24 Q41 45 24 45 Q7 45 7 24 Q7 3 24 3 Z" fill="{g}" stroke="#07305e" stroke-width="1.2"/>')
    bt_rune(s)
    return s.svg()


def icon_tray_bluetooth():
    s = S()
    g = s.grad(lg([(0, "#4aa3f0"), (1, "#0b4f9c")]))
    s.add(f'<path d="M24 1 Q44 1 44 24 Q44 47 24 47 Q4 47 4 24 Q4 1 24 1 Z" fill="{g}" stroke="#fff" stroke-width="2"/>')
    bt_rune(s, sc=1.05, width=4)
    return s.svg()


def icon_tray_bluetooth_off():
    s = S()
    s.add('<path d="M24 1 Q44 1 44 24 Q44 47 24 47 Q4 47 4 24 Q4 1 24 1 Z" fill="#8a969c" stroke="#fff" stroke-width="2"/>')
    bt_rune(s, sc=1.05, width=4, color="#e8eef0")
    return s.svg()


def icon_folder_zip():
    s = S(); folder(s)
    s.add('<rect x="20" y="17" width="6" height="24" fill="#e8eef2" stroke="#55606a" stroke-width="0.7"/>')
    for y in range(18, 38, 4):
        s.add(f'<rect x="20" y="{y}" width="3" height="2" fill="#55606a"/><rect x="23" y="{y + 2}" width="3" height="2" fill="#55606a"/>')
    s.add('<rect x="19" y="36" width="8" height="6" rx="1" fill="#c9d2d8" stroke="#46525c" stroke-width="0.8"/>')
    return s.svg()


def icon_extract():
    s = S(); folder(s, open_=True)
    s.add('<path d="M30 6 V20 M24 14 L30 20 L36 14" fill="none" stroke="#2ea043" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.svg()


def icon_cursor():
    s = S(); shadow(s, cx=22, rx=12)
    s.add('<path d="M12 5 V36 L19 29 L24 41 L29 39 L24 27.5 L33 27.5 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/>')
    return s.svg()


def icon_icon_pack():
    s = S(); shadow(s)
    for i, (x, y, c) in enumerate(((6, 6, "#f0a030"), (25, 6, "#2a8a96"), (6, 25, "#5fbf5a"), (25, 25, "#c0504d"))):
        g = s.grad(lg([(0, "#ffffff"), (1, c)]))
        s.add(f'<rect x="{x}" y="{y}" width="17" height="17" rx="3" fill="{g}" stroke="#3b4650" stroke-width="1"/>')
    return s.svg()


def icon_wizard():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#8a5ad8"), (1, "#3c1f7a")]))
    s.add(f'<path d="M24 3 L33 30 H15 Z" fill="{g}" stroke="#241044" stroke-width="1"/>')
    s.add('<path d="M10 30 H38 Q40 33 37 35 H11 Q8 33 10 30 Z" fill="#5b3aa0" stroke="#241044" stroke-width="1"/>')
    for x, y in ((22, 14), (26, 21), (20, 24)):
        s.add(f'<path d="M{x} {y - 2} L{x + 0.8} {y - 0.6} L{x + 2} {y} L{x + 0.8} {y + 0.6} L{x} {y + 2} '
              f'L{x - 0.8} {y + 0.6} L{x - 2} {y} L{x - 0.8} {y - 0.6} Z" fill="#ffe680"/>')
    return s.svg()


def icon_package():
    s = S(); shadow(s)
    side = s.grad(lg([(0, "#d9a656"), (1, "#a8742c")]))
    s.add(f'<path d="M5 15 L24 8 L43 15 V35 L24 43 L5 35 Z" fill="{side}" stroke="#6a4610" stroke-width="1"/>')
    s.add('<path d="M5 15 L24 22 L43 15 M24 22 V43" fill="none" stroke="#6a4610" stroke-width="1"/>')
    s.add('<path d="M14 11.5 L33 18.5 V25" fill="none" stroke="#f4e3b4" stroke-width="3"/>')
    return s.svg()


def icon_flatpak():
    s = S(); shadow(s)
    g = s.grad(lg([(0, "#7fb8f0"), (1, "#2a64b0")]))
    s.add(f'<path d="M24 4 L42 14 V34 L24 44 L6 34 V14 Z" fill="{g}" stroke="#123a6e" stroke-width="1.2"/>')
    s.add('<path d="M24 4 V24 L42 14 M24 24 L6 14 M24 24 V44" fill="none" stroke="#e8f2ff" stroke-width="1.6"/>')
    return s.svg()


def icon_user_add():
    from .icons import person
    s = S(); shadow(s, rx=12)
    person(s, 6, 8, 1.1, "#5ec3cf", "#1f6f78")
    s.add('<circle cx="36" cy="34" r="9" fill="#2ea043" stroke="#fff" stroke-width="1.6"/>'
          '<path d="M36 29 V39 M31 34 H41" stroke="#fff" stroke-width="3"/>')
    return s.svg()


def icon_network_wireless():
    s = S(); shadow(s)
    body = s.grad(lg([(0, "#f4f6f8"), (1, "#b0bac4")]))
    s.add(f'<rect x="6" y="18" width="22" height="17" rx="1.2" fill="{body}" stroke="#56606a" stroke-width="0.9"/>')
    s.add('<rect x="8.5" y="20.5" width="17" height="11" fill="#2a8ab0"/>')
    s.add('<path d="M13 35 H21 L22 38 H12 Z" fill="#9aa5b0" stroke="#56606a" stroke-width="0.6"/>')
    _wifi_arcs(s, 36, 20, 4, sc=0.6, width=3.2)
    return s.svg()


def icon_cmd():
    s = S(); shadow(s)
    s.add('<rect x="4" y="7" width="40" height="33" rx="2" fill="#1b1b1b" stroke="#55606a" stroke-width="1.2"/>')
    s.add('<rect x="4" y="7" width="40" height="6" rx="2" fill="#2a6f9a"/>')
    s.add('<text x="8" y="27" font-family="DejaVu Sans Mono, monospace" font-size="11" font-weight="bold" fill="#c0c0c0">&gt;</text>')
    s.add('<rect x="16" y="25" width="7" height="2.6" fill="#c0c0c0"/>')
    return s.svg()


def icon_sound_scheme():
    from .icons import speaker
    s = S(); shadow(s)
    page(s, 14, 4, 28, 36)
    speaker(s, 0, 12, 0.6)
    s.add('<path d="M28 14 V28 M28 14 L35 12 V26" fill="none" stroke="#2a8a96" stroke-width="2"/>'
          '<circle cx="26" cy="28" r="2.6" fill="#2a8a96"/><circle cx="33" cy="26" r="2.6" fill="#2a8a96"/>')
    return s.svg()


EXTRA = {name[5:]: fn for name, fn in list(globals().items()) if name.startswith("icon_") and callable(fn)}
