"""Kursory: odczyt i zapis formatu Xcursor oraz odczyt kursorów Windows (.cur, .ani).

Pozwala budować własne motywy wskaźników (także z plików .cur/.ani) dla Waylanda.
"""
import os
import struct

from PySide6.QtGui import QColor, QImage

XC_MAGIC = b"Xcur"
XC_IMAGE = 0xFFFD0002

# role jak w klasycznych ustawieniach myszy -> nazwy plików Xcursor (pierwsza to plik, reszta to dowiązania)
ROLES = [
    ("normal", "ptr_normal", ["default", "left_ptr", "arrow", "top_left_arrow", "context-menu"]),
    ("help", "ptr_help", ["help", "question_arrow", "whats_this", "left_ptr_help", "d9ce0ab605698f320427677b458ad60b"]),
    ("working", "ptr_working", ["progress", "left_ptr_watch", "half-busy", "08e8e1c95fe2fc01f976f1e063a24ccd",
                                "3ecb610c1bf2410f44200f48c40d3599"]),
    ("busy", "ptr_busy", ["wait", "watch"]),
    ("precision", "ptr_precision", ["crosshair", "cross", "tcross", "cell", "plus"]),
    ("text", "ptr_text", ["text", "xterm", "ibeam", "vertical-text"]),
    ("handwriting", "ptr_handwriting", ["pencil", "draft"]),
    ("unavailable", "ptr_unavailable", ["not-allowed", "crossed_circle", "no-drop", "forbidden", "circle",
                                        "03b6e0fcb3499374a867c041f52298f0"]),
    ("vert", "ptr_vert", ["ns-resize", "size_ver", "sb_v_double_arrow", "v_double_arrow", "n-resize", "s-resize",
                          "top_side", "bottom_side", "row-resize", "00008160000006810000408080010102"]),
    ("horz", "ptr_horz", ["ew-resize", "size_hor", "sb_h_double_arrow", "h_double_arrow", "e-resize", "w-resize",
                          "left_side", "right_side", "col-resize", "028006030e0e7ebffc7f7070c0600140"]),
    ("dgn1", "ptr_dgn1", ["nwse-resize", "size_fdiag", "bd_double_arrow", "nw-resize", "se-resize",
                          "top_left_corner", "bottom_right_corner", "c7088f0f3e6c8088236ef8e1e3e70000"]),
    ("dgn2", "ptr_dgn2", ["nesw-resize", "size_bdiag", "fd_double_arrow", "ne-resize", "sw-resize",
                          "top_right_corner", "bottom_left_corner", "fcf1c3c7cd4491d801f1e1c78f100000"]),
    ("move", "ptr_move", ["move", "fleur", "all-scroll", "size_all", "grabbing", "closedhand", "dnd-move"]),
    ("alternate", "ptr_alternate", ["up-arrow", "center_ptr", "up_arrow"]),
    ("link", "ptr_link", ["pointer", "hand2", "hand1", "pointing_hand", "hand", "openhand", "grab",
                          "e29285e634086352946a0e7090d73106", "9d800788f1b08800ae810202380a0822"]),
]
ROLE_KEYS = [r[0] for r in ROLES]


class Frame:
    __slots__ = ("size", "image", "xhot", "yhot", "delay")

    def __init__(self, image, xhot, yhot, delay=0, size=None):
        self.image = image
        self.xhot, self.yhot = xhot, yhot
        self.delay = delay
        self.size = size or max(image.width(), image.height())


# ------------------------------------------------------------------ Xcursor
def read_xcursor(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != XC_MAGIC:
        raise ValueError("to nie jest plik Xcursor")
    header, version, ntoc = struct.unpack_from("<III", data, 4)
    frames = []
    for i in range(ntoc):
        typ, subtype, pos = struct.unpack_from("<III", data, 16 + i * 12)
        if typ != XC_IMAGE:
            continue
        hlen, t2, nominal, ver, w, h, xh, yh, delay = struct.unpack_from("<IIIIIIIII", data, pos)
        px = data[pos + 36: pos + 36 + w * h * 4]
        img = QImage(px, w, h, w * 4, QImage.Format_ARGB32_Premultiplied).copy()
        frames.append(Frame(img, xh, yh, delay, nominal))
    return frames


def write_xcursor(path, frames):
    """frames: lista Frame (różne rozmiary i/lub klatki animacji)."""
    chunks = []
    for fr in frames:
        img = fr.image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        w, h = img.width(), img.height()
        raw = bytes(img.constBits())[: w * h * 4] if img.bytesPerLine() == w * 4 else b"".join(
            bytes(img.constScanLine(y))[: w * 4] for y in range(h))
        chunks.append((fr.size, struct.pack("<IIIIIIIII", 36, XC_IMAGE, fr.size, 1, w, h,
                                            min(fr.xhot, w - 1), min(fr.yhot, h - 1), fr.delay) + raw))
    ntoc = len(chunks)
    pos = 16 + ntoc * 12
    toc = b""
    body = b""
    for size, ch in chunks:
        toc += struct.pack("<III", XC_IMAGE, size, pos + len(body))
        body += ch
    with open(path, "wb") as f:
        f.write(XC_MAGIC + struct.pack("<III", 16, 0x10000, ntoc) + toc + body)


# ------------------------------------------------------------------ Windows .cur / .ico
def _dib_to_image(data, w, h):
    """BITMAPINFOHEADER + piksele + maska AND -> QImage ARGB."""
    hsz, bw, bh2, planes, bpp = struct.unpack_from("<IiiHH", data, 0)
    ncolors = struct.unpack_from("<I", data, 32)[0] if hsz >= 36 else 0
    bh = abs(bh2) // 2
    w, h = bw, bh
    off = hsz
    palette = []
    if bpp <= 8:
        n = ncolors or (1 << bpp)
        for i in range(n):
            b, g, r, _ = struct.unpack_from("<BBBB", data, off + i * 4)
            palette.append((r, g, b))
        off += n * 4
    stride = ((w * bpp + 31) // 32) * 4
    xor = data[off: off + stride * h]
    off += stride * h
    mstride = ((w + 31) // 32) * 4
    andm = data[off: off + mstride * h]
    img = QImage(w, h, QImage.Format_ARGB32)
    has_alpha = bpp == 32 and any(xor[i * 4 + 3] for i in range(min(len(xor) // 4, w * h)))
    for y in range(h):
        row = xor[(h - 1 - y) * stride:(h - y) * stride]
        mrow = andm[(h - 1 - y) * mstride:(h - y) * mstride] if andm else b""
        for x in range(w):
            if bpp == 32:
                b, g, r, a = row[x * 4: x * 4 + 4]
                if not has_alpha:
                    a = 255
            elif bpp == 24:
                b, g, r = row[x * 3: x * 3 + 3]
                a = 255
            else:
                if bpp == 8:
                    idx = row[x]
                elif bpp == 4:
                    idx = (row[x // 2] >> (4 if x % 2 == 0 else 0)) & 0xF
                else:
                    idx = (row[x // 8] >> (7 - x % 8)) & 1
                r, g, b = palette[idx] if idx < len(palette) else (0, 0, 0)
                a = 255
            if mrow and not has_alpha:
                masked = (mrow[x // 8] >> (7 - x % 8)) & 1
                if masked:
                    # maska AND=1: przezroczysty (XOR=0) albo „odwrócenie ekranu” (XOR!=0) — to drugie rysujemy na czarno
                    if (r, g, b) == (0, 0, 0):
                        a = 0
                    else:
                        r = g = b = 0
                        a = 255
            img.setPixelColor(x, y, QColor(r, g, b, a))
    return img


def read_cur(data):
    """Plik .cur/.ico (bajty) -> lista Frame (wszystkie rozmiary)."""
    reserved, typ, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or typ not in (1, 2):
        raise ValueError("to nie jest plik .cur ani .ico")
    frames = []
    for i in range(count):
        w, h, cc, res, p1, p2, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + i * 16)
        w, h = w or 256, h or 256
        blob = data[offset: offset + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            img = QImage.fromData(blob, "PNG")
        else:
            img = _dib_to_image(blob, w, h)
        xh, yh = (p1, p2) if typ == 2 else (0, 0)
        frames.append(Frame(img.convertToFormat(QImage.Format_ARGB32_Premultiplied), xh, yh, 0, max(img.width(), img.height())))
    return frames


def read_ani(data):
    """Animowany kursor .ani -> lista Frame (pierwszy rozmiar każdej klatki, z opóźnieniami)."""
    if data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise ValueError("to nie jest plik .ani")
    pos = 12
    icons, rates, seq = [], None, None
    jif = 10
    nsteps = 0
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8: pos + 8 + size]
        if cid == b"anih" and len(body) >= 36:
            (_, nframes, nsteps, _, _, _, _, jif, flags) = struct.unpack_from("<IIIIIIIII", body, 0)
        elif cid == b"rate":
            rates = list(struct.unpack_from(f"<{len(body) // 4}I", body, 0))
        elif cid == b"seq ":
            seq = list(struct.unpack_from(f"<{len(body) // 4}I", body, 0))
        elif cid == b"LIST" and body[:4] == b"fram":
            p = 4
            while p + 8 <= len(body):
                sid = body[p:p + 4]
                ssz = struct.unpack_from("<I", body, p + 4)[0]
                if sid == b"icon":
                    icons.append(read_cur(body[p + 8: p + 8 + ssz]))
                p += 8 + ssz + (ssz & 1)
        pos += 8 + size + (size & 1)
    if not icons:
        raise ValueError("plik .ani nie zawiera klatek")
    order = seq or list(range(len(icons)))
    frames = []
    for i, idx in enumerate(order):
        if idx >= len(icons):
            continue
        fr = max(icons[idx], key=lambda f: f.size)
        delay_j = rates[i] if rates and i < len(rates) else jif
        frames.append(Frame(fr.image, fr.xhot, fr.yhot, max(20, int(delay_j * 1000 / 60)), fr.size))
    return frames


def load_any(path):
    """Kursor z pliku .cur, .ani, .ico, Xcursor albo obrazu (PNG — gorący punkt w lewym górnym rogu)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == XC_MAGIC:
        return read_xcursor(path)
    if data[:4] == b"RIFF":
        return read_ani(data)
    if data[:4] in (b"\x00\x00\x02\x00", b"\x00\x00\x01\x00"):
        return read_cur(data)
    img = QImage(path)
    if img.isNull():
        raise ValueError("nieznany format kursora")
    return [Frame(img.convertToFormat(QImage.Format_ARGB32_Premultiplied), 0, 0)]


def scaled_set(frames, sizes=(24, 32, 48, 64)):
    """Z klatek o jednym rozmiarze robi zestaw rozmiarów Xcursor (skalowanie z zachowaniem gorącego punktu)."""
    from PySide6.QtCore import Qt
    # grupujemy klatki animacji wg największego rozmiaru źródła
    src_size = max(f.size for f in frames)
    anim = [f for f in frames if f.size == src_size] or frames
    out = []
    for s in sizes:
        k = s / max(1, max(anim[0].image.width(), anim[0].image.height()))
        if src_size == 32 and s == 24:
            k = 0.75
        for f in anim:
            if abs(k - 1.0) < 0.01:
                img = f.image
            else:
                img = f.image.scaled(max(1, round(f.image.width() * k)), max(1, round(f.image.height() * k)),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
            out.append(Frame(img, round(f.xhot * k), round(f.yhot * k), f.delay, s))
    return out


# ------------------------------------------------------------------ motywy
def theme_dirs():
    home = os.path.expanduser("~")
    return [os.path.join(home, ".icons"), os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share")), "icons"),
            "/usr/local/share/icons", "/usr/share/icons", "/usr/share/pixmaps"]


def list_themes():
    """{nazwa katalogu: wyświetlana nazwa} motywów zawierających kursory."""
    out = {}
    for base in theme_dirs():
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            if os.path.isdir(os.path.join(base, d, "cursors")) and d not in out:
                name = d
                idx = os.path.join(base, d, "index.theme")
                try:
                    with open(idx, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.startswith("Name="):
                                name = line.split("=", 1)[1].strip()
                                break
                except OSError:
                    pass
                out[d] = name
    return out


def theme_path(theme):
    for base in theme_dirs():
        p = os.path.join(base, theme)
        if os.path.isdir(p):
            return p
    return None


def _inherits(theme):
    p = theme_path(theme)
    if not p:
        return []
    try:
        with open(os.path.join(p, "index.theme"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Inherits="):
                    return [x.strip() for x in line.split("=", 1)[1].split(",") if x.strip()]
    except OSError:
        pass
    return []


def find_cursor(theme, role, depth=0):
    names = next((r[2] for r in ROLES if r[0] == role), [role])
    p = theme_path(theme) if theme else None
    if p:
        for n in names:
            fp = os.path.join(p, "cursors", n)
            if os.path.exists(fp):
                return fp
    if depth < 4:
        for parent in _inherits(theme) if theme else ["default", "Adwaita"]:
            r = find_cursor(parent, role, depth + 1)
            if r:
                return r
        if depth == 0 and theme not in ("Adwaita", "default"):
            return find_cursor("Adwaita", role, depth + 1)
    return None


def preview_image(path, size=32):
    """Pierwsza klatka kursora najbliższa żądanemu rozmiarowi."""
    try:
        frames = load_any(path)
    except Exception:
        return None
    if not frames:
        return None
    best = min(frames, key=lambda f: (abs(f.size - size), -f.size))
    return best.image


def build_theme(name, assignments, inherits="Adwaita", sizes=(24, 32, 48, 64)):
    """Tworzy motyw ~/.icons/<name> z przypisań {rola: plik źródłowy}. Zwraca ścieżkę."""
    base = os.path.join(os.path.expanduser("~/.icons"), name)
    cdir = os.path.join(base, "cursors")
    os.makedirs(cdir, exist_ok=True)
    for role, src in assignments.items():
        if not src or not os.path.exists(src):
            continue
        names = next((r[2] for r in ROLES if r[0] == role), None)
        if not names:
            continue
        frames = load_any(src)
        if src.endswith((".cur", ".ani", ".ico", ".png")) or not open(src, "rb").read(4) == XC_MAGIC:
            frames = scaled_set(frames, sizes)
        target = os.path.join(cdir, names[0])
        if os.path.islink(target) or os.path.exists(target):
            os.remove(target)
        write_xcursor(target, frames)
        for alias in names[1:]:
            ap = os.path.join(cdir, alias)
            if os.path.islink(ap) or os.path.exists(ap):
                os.remove(ap)
            os.symlink(names[0], ap)
    with open(os.path.join(base, "index.theme"), "w", encoding="utf-8") as f:
        f.write(f"[Icon Theme]\nName={name}\nComment=Horyzont\nInherits={inherits}\n")
    return base


def parse_inf_scheme(folder):
    """Schemat kursorów Windows (install.inf / *.inf) -> {rola: plik}."""
    keymap = {"pointer": "normal", "arrow": "normal", "normal": "normal", "help": "help", "work": "working",
              "working": "working", "appstarting": "working", "busy": "busy", "wait": "busy", "cross": "precision",
              "precision": "precision", "crosshair": "precision", "text": "text", "ibeam": "text", "hand": "handwriting",
              "handwriting": "handwriting", "nwpen": "handwriting", "unavailable": "unavailable",
              "unavailiable": "unavailable", "unavail": "unavailable", "no": "unavailable", "vert": "vert",
              "sizens": "vert", "horz": "horz", "sizewe": "horz", "dgn1": "dgn1", "sizenwse": "dgn1",
              "dgn2": "dgn2", "sizenesw": "dgn2", "move": "move", "sizeall": "move", "alternate": "alternate",
              "uparrow": "alternate", "link": "link"}
    files = {f.lower(): os.path.join(folder, f) for f in os.listdir(folder)}
    result = {}
    for f in files:
        if not f.endswith(".inf"):
            continue
        try:
            with open(files[f], encoding="utf-8", errors="replace") as fh:
                section = ""
                for line in fh:
                    line = line.strip()
                    if line.startswith("["):
                        section = line.lower()
                        continue
                    if section == "[strings]" and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip().lower()
                        v = v.strip().strip('"').replace("\\", "/").split("/")[-1].lower()
                        if k in keymap and v in files:
                            result.setdefault(keymap[k], files[v])
        except OSError:
            continue
    if not result:
        # bez .inf — dopasowanie po nazwach plików
        words = [("normal", "normal"), ("arrow", "normal"), ("help", "help"), ("work", "working"), ("busy", "busy"),
                 ("precision", "precision"), ("cross", "precision"), ("text", "text"), ("beam", "text"),
                 ("hand", "handwriting"), ("unavail", "unavailable"), ("vert", "vert"), ("horz", "horz"),
                 ("hori", "horz"), ("dgn1", "dgn1"), ("diag1", "dgn1"), ("diagonal1", "dgn1"), ("dgn2", "dgn2"),
                 ("diag2", "dgn2"), ("diagonal2", "dgn2"), ("move", "move"), ("alt", "alternate"), ("link", "link")]
        for f, p in files.items():
            if not f.endswith((".cur", ".ani")):
                continue
            stem = os.path.splitext(f)[0]
            for w, role in words:
                if w in stem and role not in result:
                    if w == "hand" and "link" in stem:
                        continue
                    result[role] = p
                    break
    return result
