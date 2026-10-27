"""Obsługa stylów wizualnych w formacie .msstyles (pliki PE z zasobami).

Plik .msstyles to biblioteka DLL zawierająca:
- zasoby TEXTFILE z plikami INI (themes.ini oraz po jednym na schemat kolorów/rozmiar),
- bitmapy (RT_BITMAP) wskazywane w INI przez ``ImageFile = Katalog\\Plik.bmp``,
- listy nazw COLORNAMES / SIZENAMES / FILERESNAMES.

Horyzont odczytuje te dane, wycina klatki stanów i rysuje elementy metodą
dziewięciu wycinków (SizingMargins), tak jak robi to oryginalny silnik motywów.
Obsługiwany jest też rozpakowany katalog stylu (pliki INI + bitmapy) oraz
pliki .theme wskazujące na .msstyles.
"""
import configparser
import os
import re
import struct

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

from .base import (CHECKED, DISABLED, HOVER, NORMAL, PRESSED, Theme, draw_arrow,
                   draw_glyph, vgrad)

RT_BITMAP = 2


# ------------------------------------------------------------------ odczyt pliku
class MissingStyleError(ValueError):
    """Plik .theme wskazuje styl (.msstyles), którego nie ma obok niego."""

    def __init__(self, name):
        super().__init__(f"nie znaleziono pliku {name} obok pliku .theme")
        self.name = name


def find_style_for_theme(theme_path, base):
    """Szuka pliku stylu wskazanego w .theme: obok niego, w podfolderach (np. Luna/Luna.msstyles),
    w folderze nadrzędnym i w bibliotece stylów Horyzontu — bez rozróżniania wielkości liter."""
    want = base.lower()
    here = os.path.dirname(os.path.abspath(theme_path))
    from .. import config
    roots = [here, os.path.dirname(here), os.path.join(config.DATA_DIR, "themes"),
             os.path.expanduser("~/Pobrane"), os.path.expanduser("~/Downloads")]
    seen = set()
    for root in roots:
        if not os.path.isdir(root) or root in seen:
            continue
        seen.add(root)
        base_depth = root.rstrip("/").count("/")
        for dirpath, dirs, files in os.walk(root):
            if dirpath.count("/") - base_depth >= 3:
                dirs[:] = []
            for f in files:
                if f.lower() == want:
                    return os.path.join(dirpath, f)
    return None


class MsStylesFile:
    def __init__(self, path):
        self.path = path
        self.textfiles = {}
        self.bitmaps = {}
        self.pngs = {}
        self.lists = {}
        self.directory = None
        if os.path.isdir(path):
            self._load_dir(path)
        elif path.lower().endswith(".theme"):
            self._load_theme_file(path)
        else:
            self._load_pe(path)

    # --- PE
    def _load_pe(self, path):
        import pefile
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
            raise ValueError("plik nie zawiera zasobów stylu")
        for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            tname = str(t.name).upper() if t.name is not None else t.id
            for e in t.directory.entries:
                rname = str(e.name).upper() if e.name is not None else e.id
                for lang in e.directory.entries:
                    d = lang.data.struct
                    data = pe.get_data(d.OffsetToData, d.Size)
                    if tname == "TEXTFILE":
                        self.textfiles[str(rname)] = _decode_text(data)
                    elif tname == RT_BITMAP:
                        self.bitmaps[str(rname)] = data
                    elif tname in ("IMAGE", "PNG"):
                        self.pngs[str(rname)] = data
                    elif tname in ("COLORNAMES", "SIZENAMES", "FILERESNAMES"):
                        self.lists[tname] = [s for s in _decode_text(data).split("\0") if s]
                    break
        pe.close()
        if not self.textfiles:
            raise ValueError("w pliku nie znaleziono plików INI stylu")

    # --- rozpakowany katalog
    def _load_dir(self, path):
        self.directory = path
        for root, dirs, files in os.walk(path):
            for f in files:
                low = f.lower()
                full = os.path.join(root, f)
                if low.endswith(".ini"):
                    with open(full, "rb") as fh:
                        name = os.path.splitext(f)[0].upper().replace("_UTF16", "") + "_INI"
                        self.textfiles[name] = _decode_text(fh.read())
                elif low.endswith((".bmp", ".png")):
                    rel = os.path.relpath(full, path)
                    key = re.sub(r"[\\/.]", "_", rel).upper()
                    with open(full, "rb") as fh:
                        data = fh.read()
                    (self.pngs if low.endswith(".png") else self.bitmaps)[key] = ("file", data)
                    # dodatkowo pod nazwą bez pierwszego katalogu
                    key2 = re.sub(r"[\\/.]", "_", f).upper()
                    (self.pngs if low.endswith(".png") else self.bitmaps).setdefault(key2, ("file", data))
        if not self.textfiles:
            raise ValueError("katalog nie zawiera plików INI stylu")

    # --- plik .theme
    def _load_theme_file(self, path):
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        with open(path, "rb") as f:
            cp.read_string(_decode_text(f.read()))
        target = None
        for sect in cp.sections():
            if sect.lower() == "visualstyles":
                target = cp[sect].get("Path") or cp[sect].get("path")
                self.theme_color = cp[sect].get("ColorStyle")
        if not target:
            raise ValueError("plik .theme nie wskazuje stylu wizualnego")
        base = os.path.basename(target.replace("\\", "/"))
        cand = find_style_for_theme(path, base)
        if cand:
            self.path = cand
            self._load_pe(cand)
            return
        raise MissingStyleError(base)

    # --- schematy
    def schemes(self):
        """Lista (nazwa zasobu INI, nazwa wyświetlana) dla normalnego rozmiaru czcionki."""
        names = self.lists.get("FILERESNAMES") or sorted(k for k in self.textfiles if k != "THEMES_INI")
        colors = self.lists.get("COLORNAMES", [])
        sizes = self.lists.get("SIZENAMES", [])
        out = []
        if colors and sizes and len(names) == len(colors) * len(sizes):
            # układ: kolejne rozmiary dla każdego koloru albo odwrotnie — rozpoznajemy po prefiksie
            normal = [n for n in names if n.upper().startswith("NORMAL")]
            if len(normal) == len(colors):
                return list(zip(normal, colors))
            for i, c in enumerate(colors):
                out.append((names[i * len(sizes)], c))
            return out
        for n in names:
            if n.upper() == "THEMES_INI" or n.upper() not in self.textfiles:
                continue
            disp = n.upper().replace("_INI", "")
            if disp.startswith("NORMAL"):
                disp = disp[6:] or "NORMAL"
            out.append((n.upper(), disp.capitalize()))
        normal = [o for o in out if o[0].startswith("NORMAL")]
        return normal or out

    def size_variant(self, ini_name, size):
        """Wariant INI dla innego rozmiaru czcionki (np. LARGEFONTSBLUE_INI)."""
        name = ini_name.upper()
        if not name.startswith("NORMAL"):
            return ini_name
        rest = name[6:]
        prefix = {"large": "LARGEFONTS", "xlarge": "EXTRALARGE"}.get(size)
        if prefix and prefix + rest in self.textfiles:
            return prefix + rest
        return ini_name


def _decode_text(data):
    if isinstance(data, tuple):
        data = data[1]
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    # UTF-16LE bez BOM: co drugi bajt zerowy
    if len(data) > 4 and data[1:2] == b"\0" and data[3:4] == b"\0":
        return data.decode("utf-16-le", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def dib_to_image(data):
    """Bitmapa z zasobu RT_BITMAP (bez nagłówka pliku) -> QImage z kanałem alfa."""
    if isinstance(data, tuple):
        img = QImage.fromData(data[1])
        return _alpha_fix(img)
    if len(data) < 40:
        return QImage()
    hsize = struct.unpack_from("<I", data, 0)[0]
    width, height, planes, bpp, comp = struct.unpack_from("<iiHHI", data, 4)
    if bpp == 32 and comp in (0, 3):
        top_down = height < 0
        h = abs(height)
        off = hsize + (12 if comp == 3 and hsize == 40 else 0)
        stride = width * 4
        raw = data[off:off + stride * h]
        has_alpha = any(raw[i] for i in range(3, min(len(raw), stride * h), 4))
        # bitmapy stylów zwykle mają alfę przemnożoną (AlphaBlend); jeśli kolor > alfa, alfa jest prosta
        premult = has_alpha and not any(max(raw[i], raw[i + 1], raw[i + 2]) > raw[i + 3]
                                        for i in range(0, min(len(raw), stride * h), 4))
        img = QImage(width, h, QImage.Format_ARGB32_Premultiplied if premult else QImage.Format_ARGB32)
        for y in range(h):
            row = raw[(y if top_down else h - 1 - y) * stride:((y if top_down else h - 1 - y) + 1) * stride]
            line = bytearray(row)
            if not has_alpha:
                for i in range(3, len(line), 4):
                    line[i] = 255
            ptr = img.scanLine(y)
            ptr[:len(line)] = bytes(line)
        return img.convertToFormat(QImage.Format_ARGB32)
    # pozostałe głębie: dokładamy nagłówek pliku BMP i czytamy przez Qt
    ncolors = struct.unpack_from("<I", data, 32)[0] if hsize >= 36 else 0
    if bpp <= 8 and ncolors == 0:
        ncolors = 1 << bpp
    palette = ncolors * (4 if hsize >= 40 else 3)
    extra = 12 if comp == 3 and hsize == 40 else 0
    offset = 14 + hsize + palette + extra
    fileheader = b"BM" + struct.pack("<IHHI", 14 + len(data), 0, 0, offset)
    img = QImage.fromData(fileheader + data, "BMP")
    return img.convertToFormat(QImage.Format_ARGB32)


def _alpha_fix(img):
    return img.convertToFormat(QImage.Format_ARGB32) if not img.isNull() else img


def parse_ini(text):
    """INI stylu -> słownik sekcja(małe litery) -> {klucz(małe litery): wartość}."""
    out = {}
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and "]" in line:
            cur = line[1:line.index("]")].strip().lower()
            out.setdefault(cur, {})
            continue
        if cur is None or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(";")[0].strip()
        out[cur][k.strip().lower()] = v
    return out


def ints(v, n=None):
    if v is None:
        return None
    vals = [int(x) for x in re.findall(r"-?\d+", v)]
    if n is not None and len(vals) < n:
        return None
    return vals


def color(v):
    vals = ints(v, 3)
    return QColor(vals[0], vals[1], vals[2]) if vals else None


def boolv(v, default=False):
    if v is None:
        return default
    return v.strip().lower() in ("true", "1", "yes")


def font_from(v, fallback):
    """'Tahoma, 8, Bold' -> QFont (punkty przeliczone na piksele przy 96 dpi)."""
    if not v:
        return fallback
    parts = [p.strip() for p in v.split(",")]
    f = QFont(parts[0] if parts[0] else fallback.family())
    try:
        pt = int(parts[1]) if len(parts) > 1 else 8
    except ValueError:
        pt = 8
    if pt > 1:
        f.setPixelSize(max(8, round(pt * 96 / 72)))
    else:
        f.setPixelSize(fallback.pixelSize())
    style = " ".join(parts[2:]).lower()
    f.setBold("bold" in style)
    f.setItalic("italic" in style)
    return f


# ------------------------------------------------------------------ rysowanie części
class Part:
    """Rozwiązane właściwości jednej części (np. Button.Pushbutton)."""

    def __init__(self, style, name):
        self.style = style
        self.name = name


STATE_INDEX = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 4, CHECKED: 5}


class MsStylesTheme(Theme):
    name = "msstyles"

    def __init__(self, path, scheme="", fallback=None):
        super().__init__()
        from .manager import ThemeManager  # noqa: F401
        self.file = MsStylesFile(path)
        self.fb = fallback
        self.path = path
        schemes = self.file.schemes()
        if not schemes:
            raise ValueError("brak schematów kolorów w stylu")
        names = [s[0] for s in schemes]
        if scheme and scheme.upper() in names:
            self.scheme = scheme.upper()
        else:
            self.scheme = names[0]
        self.display_name = os.path.splitext(os.path.basename(self.file.path))[0]
        self.ini = parse_ini(self.file.textfiles.get(self.scheme, ""))
        self.images = {}
        self._pix = {}
        self.metrics = dict(fallback.metrics) if fallback else self.metrics
        self.colors = dict(fallback.colors) if fallback else {}
        if fallback is not None:
            self.sc = getattr(fallback, "sc", None)
        self._setup_metrics()

    # --------------------------------------------------------- właściwości
    def sect(self, cls, state=None):
        """Szuka właściwości: Klasa.Część(Stan) -> Klasa.Część -> Klasa -> Globals."""
        cls = cls.lower()
        chain = []
        names = [cls]
        if "::" in cls:
            names.append(cls.split("::", 1)[1])
        for n in names:
            if state:
                chain.append(f"{n}({state.lower()})")
            chain.append(n)
            if "." in n:
                chain.append(n.split(".", 1)[0])
        return chain

    def prop(self, cls, key, state=None, default=None):
        key = key.lower()
        for s in self.sect(cls, state):
            d = self.ini.get(s)
            if d and key in d:
                return d[key]
        g = self.ini.get("globals", {})
        return g.get(key, default)

    def has(self, cls):
        cls = cls.lower()
        if cls in self.ini:
            return True
        if "::" in cls and cls.split("::", 1)[1] in self.ini:
            return True
        return False

    def image(self, filename):
        if not filename:
            return None
        key = re.sub(r"[\\/.]", "_", filename.strip()).upper()
        if key in self.images:
            return self.images[key]
        data = self.file.bitmaps.get(key)
        img = None
        if data is not None:
            img = dib_to_image(data)
        else:
            png = self.file.pngs.get(key) or self.file.pngs.get(key.replace("_BMP", "_PNG"))
            if png is not None:
                img = QImage.fromData(png[1] if isinstance(png, tuple) else png)
                img = img.convertToFormat(QImage.Format_ARGB32)
        if img is None or img.isNull():
            self.images[key] = None
            return None
        self.images[key] = img
        return img

    def _select_file(self, cls, state, target_size=None, glyph=False):
        main = self.prop(cls, "glyphimagefile" if glyph else "imagefile", state)
        if main:
            return main
        ist = (self.prop(cls, "imageselecttype", state) or "").lower()
        if ist in ("dpi", ""):
            for i in range(1, 8):
                f = self.prop(cls, f"imagefile{i}", state)
                if f:
                    return f
            return None
        if ist == "size":
            best = None
            for i in range(5, 0, -1):
                f = self.prop(cls, f"imagefile{i}", state)
                if not f:
                    continue
                ms = ints(self.prop(cls, f"minsize{i}", state), 2)
                if ms is None:
                    img = self.image(f)
                    if img is None:
                        continue
                    ms = [img.width(), img.height() // max(1, self._count(cls, state))]
                if target_size is None or (ms[0] <= target_size.width() and ms[1] <= target_size.height()):
                    return f
                best = f
            return self.prop(cls, "imagefile1", state) or best
        return None

    def _count(self, cls, state=None):
        v = ints(self.prop(cls, "imagecount", state))
        return max(1, v[0]) if v else 1

    def frame(self, cls, index, state=None, glyph=False, target=None):
        """Wycina klatkę ``index`` (od 1) z obrazu części."""
        f = self._select_file(cls, state, target, glyph)
        img = self.image(f)
        if img is None:
            return None
        count = self._count(cls, state)
        layout = (self.prop(cls, "imagelayout", state) or "vertical").lower()
        index = max(1, min(index, count))
        key = (f, index, count, layout)
        if key in self._pix:
            return self._pix[key]
        if layout.startswith("horiz"):
            fw = img.width() // count
            sub = img.copy(fw * (index - 1), 0, fw, img.height())
        else:
            fh = img.height() // count
            sub = img.copy(0, fh * (index - 1), img.width(), fh)
        transparent = boolv(self.prop(cls, "glyphtransparent" if glyph else "transparent", state))
        if transparent:
            tc = color(self.prop(cls, "glyphtransparentcolor" if glyph else "transparentcolor", state)) or QColor(255, 0, 255)
            sub = apply_transparent_color(sub, tc)
        self._pix[key] = sub
        return sub

    def natural_size(self, cls, state=None):
        img = self.frame(cls, 1, state)
        return QSize(img.width(), img.height()) if img is not None else None

    def draw_part(self, p, rect, cls, index=1, state=None, glyph_index=None):
        """Rysuje część w prostokącie (9 wycinków). Zwraca False, gdy obrazu brak."""
        rect = QRect(rect)
        bgtype = (self.prop(cls, "bgtype", state) or "imagefile").lower()
        if bgtype == "borderfill":
            self._border_fill(p, rect, cls, state)
            return True
        if bgtype == "none":
            return True
        img = self.frame(cls, index, state, target=rect.size())
        if img is None:
            return False
        sizing = (self.prop(cls, "sizingtype", state) or "stretch").lower()
        if sizing == "truesize":
            w, h = img.width(), img.height()
            if w > rect.width() or h > rect.height():
                s = min(rect.width() / max(1, w), rect.height() / max(1, h))
                w, h = int(w * s), int(h * s)
            ha = (self.prop(cls, "halign", state) or "center").lower()
            va = (self.prop(cls, "valign", state) or "center").lower()
            x = rect.left() if ha == "left" else rect.right() - w + 1 if ha == "right" else rect.left() + (rect.width() - w) // 2
            y = rect.top() if va == "top" else rect.bottom() - h + 1 if va == "bottom" else rect.top() + (rect.height() - h) // 2
            p.drawImage(QRect(x, y, w, h), img)
        else:
            m = ints(self.prop(cls, "sizingmargins", state), 4) or [0, 0, 0, 0]
            self._nine(p, rect, img, m[0], m[1], m[2], m[3], sizing == "tile",
                       boolv(self.prop(cls, "borderonly", state)))
        if glyph_index is not None and (self.prop(cls, "glyphtype", state) or "").lower() == "imageglyph":
            cm = ints(self.prop(cls, "contentmargins", state), 4) or [0, 0, 0, 0]
            inner = rect.adjusted(cm[0], cm[2], -cm[1], -cm[3])
            g = self.frame(cls, glyph_index, state, glyph=True, target=inner.size())
            if g is not None and (self._select_file(cls, state, inner.size(), True) !=
                                  self._select_file(cls, state, inner.size(), False)):
                gx = inner.left() + (inner.width() - g.width()) // 2
                gy = inner.top() + (inner.height() - g.height()) // 2
                p.drawImage(gx, gy, g)
        return True

    def _border_fill(self, p, rect, cls, state):
        fill = color(self.prop(cls, "fillcolor", state))
        ft = (self.prop(cls, "filltype", state) or "").lower()
        if ft == "vertgradient":
            c1 = color(self.prop(cls, "gradientcolor1", state))
            c2 = color(self.prop(cls, "gradientcolor2", state))
            if c1 and c2:
                p.fillRect(rect, vgrad(rect, [(0, c1), (1, c2)]))
        elif fill:
            p.fillRect(rect, fill)
        bs = ints(self.prop(cls, "bordersize", state))
        bc = color(self.prop(cls, "bordercolor", state))
        if bc and (bs is None or bs[0] > 0):
            p.setPen(bc)
            p.setBrush(Qt.NoBrush)
            p.drawRect(rect.adjusted(0, 0, -1, -1))

    _nine_cache = None

    @classmethod
    def _nine(cls, p, rect, img, ml, mr, mt, mb, tile=False, border_only=False):
        """Rysuje obraz metodą 9 wycinków. Wynik dla danego rozmiaru trafia do pamięci
        podręcznej — kolejne odrysowania to jedno drawPixmap (płynniejsze okna)."""
        from collections import OrderedDict
        if cls._nine_cache is None:
            cls._nine_cache = OrderedDict()
        rw, rh = rect.width(), rect.height()
        if rw <= 0 or rh <= 0:
            return
        key = (img.cacheKey(), rw, rh, ml, mr, mt, mb, tile, border_only)
        pm = cls._nine_cache.get(key)
        if pm is None:
            if rw * rh > 4000 * 3000:
                cls._nine_render(p, rect, img, ml, mr, mt, mb, tile, border_only)
                return
            out = QImage(rw, rh, QImage.Format_ARGB32_Premultiplied)
            out.fill(Qt.transparent)
            q = QPainter(out)
            cls._nine_render(q, QRect(0, 0, rw, rh), img, ml, mr, mt, mb, tile, border_only)
            q.end()
            pm = QPixmap.fromImage(out)
            cls._nine_cache[key] = pm
            while len(cls._nine_cache) > 400:
                cls._nine_cache.popitem(last=False)
        else:
            cls._nine_cache.move_to_end(key)
        p.drawPixmap(rect.topLeft(), pm)

    @staticmethod
    def _nine_render(p, rect, img, ml, mr, mt, mb, tile=False, border_only=False):
        W, H = img.width(), img.height()
        ml, mr = min(ml, W // 2), min(mr, W - min(ml, W // 2))
        mt, mb = min(mt, H // 2), min(mb, H - min(mt, H // 2))
        rw, rh = rect.width(), rect.height()
        if rw < ml + mr:
            k = rw / max(1, ml + mr)
            ml_d, mr_d = int(ml * k), rw - int(ml * k)
        else:
            ml_d, mr_d = ml, mr
        if rh < mt + mb:
            k = rh / max(1, mt + mb)
            mt_d, mb_d = int(mt * k), rh - int(mt * k)
        else:
            mt_d, mb_d = mt, mb
        sx = [0, ml, W - mr, W]
        sy = [0, mt, H - mb, H]
        dx = [rect.left(), rect.left() + ml_d, rect.left() + rw - mr_d, rect.left() + rw]
        dy = [rect.top(), rect.top() + mt_d, rect.top() + rh - mb_d, rect.top() + rh]
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        for j in range(3):
            for i in range(3):
                if border_only and i == 1 and j == 1:
                    continue
                s = QRect(sx[i], sy[j], sx[i + 1] - sx[i], sy[j + 1] - sy[j])
                d = QRect(dx[i], dy[j], dx[i + 1] - dx[i], dy[j + 1] - dy[j])
                if s.width() <= 0 or s.height() <= 0 or d.width() <= 0 or d.height() <= 0:
                    continue
                if tile and i == 1 or tile and j == 1:
                    piece = QPixmap.fromImage(img.copy(s))
                    p.drawTiledPixmap(d, piece)
                else:
                    p.drawImage(d, img, s)
        p.restore()

    # --------------------------------------------------------- metryki i kolory
    def _setup_metrics(self):
        sm = {k: v for k, v in self.ini.get("sysmetrics", {}).items()}
        cbh = ints(sm.get("captionbarheight"))
        fl = self.natural_size("Window.FrameLeft")
        bw = fl.width() if fl else 4
        cap = self.natural_size("Window.Caption")
        if cbh:
            caption_h = cbh[0] + bw
        elif cap:
            caption_h = cap.height()
        else:
            caption_h = 28
        self.metrics["border"] = bw
        self.metrics["caption_h"] = caption_h
        # jak w klasycznym stylu: przycisk = wysokość paska − 4 px, odstępy 2 px między przyciskami
        self.metrics["caption_button"] = max(14, (cbh[0] - 4) if cbh else 21)
        self.metrics["caption_button_gap"] = 2
        self.metrics["frame_radius"] = 0
        tb = self.natural_size("TaskBar.BackgroundBottom")
        if tb and tb.height() >= 20:
            self.metrics["taskbar_h"] = tb.height()
        sb = self.natural_size("Start::Button")
        self._start_size = sb
        tbn = self.natural_size("TaskBand::Toolbar.Button")
        if tbn:
            self.metrics["task_button_h"] = min(self.metrics["taskbar_h"] - 4, max(20, tbn.height()))
        up = self.natural_size("StartPanel.UserPane")
        if up:
            self.metrics["sm_header_h"] = max(50, up.height())
        lo = self.natural_size("StartPanel.Logoff")
        if lo:
            self.metrics["sm_footer_h"] = max(30, lo.height())
        dps = ints(self.prop("StartPanel", "defaultpanesize"), 4)
        if dps and dps[2] > 200:
            self.metrics["sm_width"] = max(360, dps[2] + 20)
        mapping = {
            "window": "window", "windowtext": "window_text", "btnface": "button", "btntext": "button_text",
            "highlight": "highlight", "highlighttext": "highlight_text", "menu": "menu", "menutext": "menu_text",
            "graytext": "gray_text", "infobk": "tooltip", "hottracking": "link", "background": "desktop",
            "captiontext": "caption_text_active", "inactivecaptiontext": "caption_text_inactive",
            "menubar": "menubar",
        }
        for k, ck in mapping.items():
            c = color(sm.get(k))
            if c:
                self.colors[ck] = c.name()
        btn = color(sm.get("btnface"))
        if btn:
            self.colors["window"] = btn.name()
            self.colors["status_bar"] = btn.name()
            if "menubar" not in sm:
                self.colors["menubar"] = btn.name()
        dlg = color(self.prop("Window.Dialog", "fillcolor"))
        if dlg:
            self.colors["window"] = dlg.name()
        if boolv(sm.get("flatmenus")):
            mh = color(sm.get("menuhilight"))
            if mh:
                self.colors["menu_highlight"] = mh.name()
        else:
            self.colors["menu_highlight"] = self.colors.get("highlight", "#316ac5")
        self.flat_menus = boolv(sm.get("flatmenus"), True)
        # panel zadań: gradient z [ExplorerBar], tekst nagłówków z części
        c1 = color(self.prop("ExplorerBar", "gradientcolor1"))
        c2 = color(self.prop("ExplorerBar", "gradientcolor2"))
        self._pane_grad = (c1, c2) if c1 and c2 else None
        for key, cls in (("taskpane_header_text", "ExplorerBar.NormalGroupHead"),
                         ("taskpane_header_special_text", "ExplorerBar.SpecialGroupHead")):
            c = color(self.prop(cls, "textcolor"))
            if c:
                self.colors[key] = c.name()
        for key, cls in (("taskpane_link", "ExplorerBar.NormalGroupBackground"),):
            c = color(self.prop(cls, "textcolor"))
            if c:
                self.colors[key] = c.name()
                self.colors["taskpane_link_hover"] = c.lighter(140).name()
        for key, cls in (("sm_text", "StartPanel.ProgList"), ("sm_right_text", "StartPanel.PlacesList"),
                         ("sm_user_text", "StartPanel.UserPane"), ("sm_footer_text", "StartPanel.Logoff")):
            c = color(self.prop(cls, "textcolor"))
            if c:
                self.colors[key] = c.name()
        c = color(self.prop("TaskBand::Toolbar", "textcolor"))
        if c:
            self.colors["taskbar_text"] = c.name()
        self._fonts = {
            "caption": sm.get("captionfont"), "menu": sm.get("menufont"), "icon": sm.get("icontitlefont"),
            "status": sm.get("statusfont"), "normal": sm.get("msgboxfont") or sm.get("menufont"),
        }

    def _make_font(self, kind):
        base = super()._make_font(kind)
        spec = self._fonts.get(kind) if hasattr(self, "_fonts") else None
        if kind in ("sm_item", "small"):
            spec = self._fonts.get("menu")
        if spec:
            f = font_from(spec, base)
            if self.font_scale != 1.0:
                f.setPixelSize(max(8, round(f.pixelSize() * self.font_scale)))
            if kind in ("caption",):
                return f
            if kind in ("start_button", "sm_user", "taskpane_header", "title_big", "big"):
                f.setPixelSize(base.pixelSize())
                f.setBold(base.bold())
            return f
        return base

    def _fbcall(self, name, *a, **kw):
        if self.fb is not None:
            return getattr(self.fb, name)(*a, **kw)

    # --------------------------------------------------------- okna
    def draw_window_frame(self, p, rect, active, maximized):
        idx = 1 if active else 2
        m = self.metrics
        r = QRect(rect)
        ch = m["caption_h"]
        b = 0 if maximized else m["border"]
        cap_cls = "Window.MaxCaption" if maximized and self.has("Window.MaxCaption") else "Window.Caption"
        if not self.draw_part(p, QRect(r.left(), r.top(), r.width(), ch), cap_cls, idx):
            return self._fbcall("draw_window_frame", p, rect, active, maximized)
        if not maximized:
            self.draw_part(p, QRect(r.left(), r.top() + ch, b, r.height() - ch - b), "Window.FrameLeft", idx)
            self.draw_part(p, QRect(r.right() - b + 1, r.top() + ch, b, r.height() - ch - b), "Window.FrameRight", idx)
            fb = self.natural_size("Window.FrameBottom")
            bh = b if fb is None else max(b, min(fb.height(), 8))
            self.draw_part(p, QRect(r.left(), r.bottom() - bh + 1, r.width(), bh), "Window.FrameBottom", idx)

    def frame_margins(self, maximized=False):
        m = self.metrics
        b = 0 if maximized else m["border"]
        fb = self.natural_size("Window.FrameBottom")
        bottom = b if fb is None or maximized else max(b, min(fb.height(), 8))
        return b, m["caption_h"], b, bottom

    def draw_caption_button(self, p, rect, kind, state, active):
        cls = {"min": "Window.MinButton", "max": "Window.MaxButton", "restore": "Window.RestoreButton",
               "close": "Window.CloseButton", "help": "Window.HelpButton"}[kind]
        if not self.has(cls):
            return self._fbcall("draw_caption_button", p, rect, kind, state, active)
        count = self._count(cls)
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 4}.get(state, 1)
        if not active and count >= 8:
            i += 4
        if not self.draw_part(p, rect, cls, i, glyph_index=i):
            self._fbcall("draw_caption_button", p, rect, kind, state, active)

    def draw_caption_text(self, p, rect, text, active):
        f = self.font("caption")
        p.setFont(f)
        fm = p.fontMetrics()
        text = fm.elidedText(text, Qt.ElideRight, rect.width())
        col = QColor(self.colors.get("caption_text_active" if active else "caption_text_inactive", "#ffffff"))
        tc = color(self.prop("Window.Caption", "textcolor", "Active" if active else "Inactive"))
        if tc:
            col = tc
        sh = color(self.prop("Window.Caption", "textshadowcolor"))
        off = ints(self.prop("Window.Caption", "textshadowoffset"), 2)
        if sh and off and active:
            p.setPen(sh)
            p.drawText(rect.translated(off[0], off[1]), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.setPen(col)
        p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    # --------------------------------------------------------- pasek zadań
    def draw_taskbar(self, p, rect):
        if not self.draw_part(p, rect, "TaskBar.BackgroundBottom"):
            self._fbcall("draw_taskbar", p, rect)

    def start_button_width(self, text, height):
        if self._start_size:
            w = self._start_size.width()
            spec = ints(self.prop("Start::Button", "font"))
            if not (spec and spec[0] <= 1):   # napis rysujemy sami — dłuższy napis poszerza przycisk
                from PySide6.QtGui import QFontMetrics
                f = font_from(self.prop("Start::Button", "font"), self.font("start_button"))
                f.setPixelSize(max(f.pixelSize(), 14))
                w = max(w, int(height * 1.05) + QFontMetrics(f).horizontalAdvance(text) + 18)
            return w
        return self._fbcall("start_button_width", text, height)

    def draw_start_button(self, p, rect, state, text):
        cls = "Start::Button"
        if not self.has(cls):
            return self._fbcall("draw_start_button", p, rect, state, text)
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3}.get(state, 1)
        self.draw_part(p, rect, cls, i)
        f = font_from(self.prop(cls, "font"), self.font("start_button"))
        spec = ints(self.prop(cls, "font"))
        if spec and spec[0] <= 1:
            return  # napis jest częścią obrazu
        f.setPixelSize(max(f.pixelSize(), 14))
        p.setFont(f)
        cm = ints(self.prop(cls, "contentmargins"), 4)
        left = cm[0] if cm and cm[0] > 8 else int(rect.height() * 1.05)
        r = QRect(rect.left() + left, rect.top() + (1 if state == PRESSED else 0), rect.width() - left, rect.height())
        sh = color(self.prop(cls, "textshadowcolor"))
        off = ints(self.prop(cls, "textshadowoffset"), 2) or [1, 1]
        if sh:
            p.setPen(sh)
            p.drawText(r.translated(off[0], off[1]), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.setPen(color(self.prop(cls, "textcolor")) or QColor("#ffffff"))
        p.drawText(r, Qt.AlignVCenter | Qt.AlignLeft, text)

    def draw_task_button(self, p, rect, state):
        cls = "TaskBand::Toolbar.Button"
        if state == "flash" and self.has("TaskBand.FlashButton"):
            self.draw_part(p, rect, "TaskBand.FlashButton")
            return
        if not self.has(cls):
            return self._fbcall("draw_task_button", p, rect, state)
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, CHECKED: 5, "flash": 5}.get(state, 1)
        self.draw_part(p, rect, cls, i)

    def draw_tray(self, p, rect):
        for cls in ("TrayNotifyHoriz::TrayNotify.Background", "TrayNotify.Background", "TrayNotify::Background"):
            if self.has(cls):
                self.draw_part(p, rect, cls)
                return
        self._fbcall("draw_tray", p, rect)

    # --------------------------------------------------------- menu Start
    def draw_sm_frame(self, p, rect):
        pass

    def draw_sm_header(self, p, rect):
        cls = "StartPanel.UserPane"
        if (self.prop(cls, "bgtype") or "").lower() == "none":
            c = color(self.prop(cls, "fillcolorhint"))
            if c is not None:
                p.fillRect(rect, c)
                return
        if not self.draw_part(p, rect, cls):
            self._fbcall("draw_sm_header", p, rect)

    def draw_sm_left(self, p, rect):
        if not self.draw_part(p, rect, "StartPanel.ProgList"):
            self._fbcall("draw_sm_left", p, rect)

    def draw_sm_right(self, p, rect):
        if not self.draw_part(p, rect, "StartPanel.PlacesList"):
            self._fbcall("draw_sm_right", p, rect)

    def draw_sm_footer(self, p, rect):
        if not self.draw_part(p, rect, "StartPanel.Logoff"):
            self._fbcall("draw_sm_footer", p, rect)

    def draw_sm_separator(self, p, rect, right=False):
        cls = "StartPanel.PlacesListSeparator" if right else "StartPanel.ProgListSeparator"
        r = QRect(rect)
        ns = self.natural_size(cls)
        h = ns.height() if ns else 2
        rr = QRect(r.left(), r.center().y() - h // 2, r.width(), h)
        if not self.draw_part(p, rr, cls):
            self._fbcall("draw_sm_separator", p, rect, right)

    def draw_sm_item_hover(self, p, rect, right=False):
        p.fillRect(rect, QColor(self.colors.get("menu_highlight", self.colors.get("highlight", "#316ac5"))))

    def draw_sm_footer_button(self, p, rect, state):
        if state == HOVER:
            if not self.draw_part(p, rect, "StartPanel.LogoffButtons", 1, "Hot"):
                self._fbcall("draw_sm_footer_button", p, rect, state)

    # --------------------------------------------------------- panel zadań
    def draw_taskpane_bg(self, p, rect):
        if self._pane_grad:
            p.fillRect(rect, vgrad(rect, [(0, self._pane_grad[0]), (1, self._pane_grad[1])]))
        else:
            self._fbcall("draw_taskpane_bg", p, rect)

    def draw_taskpane_header(self, p, rect, special, hover, expanded):
        cls = "ExplorerBar.SpecialGroupHead" if special else "ExplorerBar.NormalGroupHead"
        if not self.draw_part(p, rect, cls):
            return self._fbcall("draw_taskpane_header", p, rect, special, hover, expanded)
        bcls = ("ExplorerBar.SpecialGroup" if special else "ExplorerBar.NormalGroup") + ("Collapse" if expanded else "Expand")
        ns = self.natural_size(bcls)
        if ns:
            br = QRect(rect.right() - ns.width() - 3, rect.top() + (rect.height() - ns.height()) // 2, ns.width(), ns.height())
            self.draw_part(p, br, bcls, 2 if hover else 1)

    def draw_taskpane_body(self, p, rect, special):
        cls = "ExplorerBar.SpecialGroupBackground" if special else "ExplorerBar.NormalGroupBackground"
        if not self.draw_part(p, rect, cls):
            self._fbcall("draw_taskpane_body", p, rect, special)

    # --------------------------------------------------------- kontrolki
    def draw_button(self, p, rect, state, default=False, focus=False):
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 4, CHECKED: 3}.get(state, 1)
        if state == NORMAL and (default or focus):
            i = 5
        if not self.draw_part(p, rect, "Button.Pushbutton", i):
            self._fbcall("draw_button", p, rect, state, default, focus)

    def draw_checkbox(self, p, rect, checked, state, partial=False):
        base = 9 if partial else (5 if checked else 1)
        i = base + {NORMAL: 0, HOVER: 1, PRESSED: 2, DISABLED: 3}.get(state, 0)
        if not self.draw_part(p, rect, "Button.Checkbox", i):
            self._fbcall("draw_checkbox", p, rect, checked, state, partial)

    def draw_radio(self, p, rect, checked, state):
        i = (5 if checked else 1) + {NORMAL: 0, HOVER: 1, PRESSED: 2, DISABLED: 3}.get(state, 0)
        if not self.draw_part(p, rect, "Button.Radiobutton", i):
            self._fbcall("draw_radio", p, rect, checked, state)

    def draw_groupbox(self, p, rect):
        if not self.draw_part(p, rect, "Button.Groupbox"):
            self._fbcall("draw_groupbox", p, rect)

    def draw_edit_frame(self, p, rect, focus, disabled):
        bc = color(self.prop("Edit", "bordercolor")) or color(self.prop("Edit.Edittext", "bordercolor"))
        if bc is None:
            bc = color(self.prop("Combobox", "bordercolor"))
        if bc is None:
            return self._fbcall("draw_edit_frame", p, rect, focus, disabled)
        p.setPen(bc if not disabled else bc.lighter(130))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRect(rect).adjusted(0, 0, -1, -1))

    def draw_combo_button(self, p, rect, state, direction="down"):
        if direction == "up" and self.has("Spin.Up"):
            cls = "Spin.Up"
        elif direction == "down" and rect.height() < 14 and self.has("Spin.Down"):
            cls = "Spin.Down"
        else:
            cls = "Combobox.DropDownButton"
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 4}.get(state, 1)
        if not self.draw_part(p, rect, cls, i, glyph_index=i):
            self._fbcall("draw_combo_button", p, rect, state, direction)

    def draw_sb_track(self, p, rect, horizontal, pressed=False):
        cls = "ScrollBar.LowerTrackHorz" if horizontal else "ScrollBar.LowerTrackVert"
        if not self.draw_part(p, rect, cls, 3 if pressed else 1):
            self._fbcall("draw_sb_track", p, rect, horizontal, pressed)

    def draw_sb_thumb(self, p, rect, horizontal, state):
        cls = "ScrollBar.ThumbBtnHorz" if horizontal else "ScrollBar.ThumbBtnVert"
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 4}.get(state, 1)
        if not self.draw_part(p, rect, cls, i):
            return self._fbcall("draw_sb_thumb", p, rect, horizontal, state)
        gcls = "ScrollBar.GripperHorz" if horizontal else "ScrollBar.GripperVert"
        ns = self.natural_size(gcls)
        if ns and (rect.width() > ns.width() + 6 if horizontal else rect.height() > ns.height() + 6):
            self.draw_part(p, rect, gcls, i)

    def draw_sb_arrow(self, p, rect, direction, state):
        base = {"up": 1, "down": 5, "left": 9, "right": 13}[direction]
        i = base + {NORMAL: 0, HOVER: 1, PRESSED: 2, DISABLED: 3}.get(state, 0)
        if not self.draw_part(p, rect, "ScrollBar.ArrowBtn", i, glyph_index=i):
            self._fbcall("draw_sb_arrow", p, rect, direction, state)

    def draw_progress_track(self, p, rect):
        if not self.draw_part(p, rect, "Progress.Bar"):
            self._fbcall("draw_progress_track", p, rect)

    def draw_progress_chunk(self, p, rect):
        if not self.draw_part(p, rect, "Progress.Chunk"):
            self._fbcall("draw_progress_chunk", p, rect)

    def draw_tab(self, p, rect, selected, state):
        cls = "Tab.TopTabItem" if self.has("Tab.TopTabItem") else "Tab.TabItem"
        i = 3 if selected else {NORMAL: 1, HOVER: 2, DISABLED: 4}.get(state, 1)
        if not self.draw_part(p, rect, cls, i):
            self._fbcall("draw_tab", p, rect, selected, state)

    def draw_tab_pane(self, p, rect):
        if not self.draw_part(p, rect, "Tab.Pane"):
            self._fbcall("draw_tab_pane", p, rect)

    def draw_header_section(self, p, rect, state):
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3}.get(state, 1)
        if not self.draw_part(p, rect, "Header.HeaderItem", i):
            self._fbcall("draw_header_section", p, rect, state)

    def draw_toolbar_button(self, p, rect, state):
        if state not in (HOVER, PRESSED, CHECKED):
            return
        i = {HOVER: 2, PRESSED: 3, CHECKED: 5}.get(state, 1)
        if not self.draw_part(p, rect, "Toolbar.Button", i):
            self._fbcall("draw_toolbar_button", p, rect, state)

    def draw_menu_frame(self, p, rect):
        c = QColor(self.colors.get("gray_text", "#888888"))
        p.setPen(c)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRect(rect).adjusted(0, 0, -1, -1))

    def draw_menu_highlight(self, p, rect, menubar=False):
        p.fillRect(rect, QColor(self.colors.get("menu_highlight", "#316ac5")))

    def draw_slider_groove(self, p, rect, horizontal):
        cls = "TrackBar.Track" if horizontal else "TrackBar.TrackVert"
        ns = self.natural_size(cls)
        r = QRect(rect)
        if ns:
            if horizontal:
                r = QRect(rect.left(), rect.center().y() - ns.height() // 2, rect.width(), ns.height())
            else:
                r = QRect(rect.center().x() - ns.width() // 2, rect.top(), ns.width(), rect.height())
        if not self.draw_part(p, r, cls):
            self._fbcall("draw_slider_groove", p, rect, horizontal)

    def draw_slider_handle(self, p, rect, horizontal, state):
        cls = "TrackBar.ThumbBottom" if horizontal else "TrackBar.ThumbRight"
        if not self.has(cls):
            cls = "TrackBar.Thumb" if horizontal else "TrackBar.ThumbVert"
        i = {NORMAL: 1, HOVER: 2, PRESSED: 3, DISABLED: 5}.get(state, 1)
        if not self.draw_part(p, rect, cls, i):
            self._fbcall("draw_slider_handle", p, rect, horizontal, state)


def apply_transparent_color(img, col):
    """Piksele w kolorze ``col`` stają się przezroczyste (z zachowaniem istniejącej alfy)."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    mask = img.createMaskFromColor(QColor(col.red(), col.green(), col.blue(), 255).rgba(), Qt.MaskInColor)
    mask.setColorTable([0x00000000, 0xFF000000])
    stencil = mask.convertToFormat(QImage.Format_ARGB32)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    p.drawImage(0, 0, stencil)
    p.end()
    return img


def list_schemes(path):
    """Zwraca listę (zasób, nazwa) schematów kolorów w pliku stylu."""
    return MsStylesFile(path).schemes()
