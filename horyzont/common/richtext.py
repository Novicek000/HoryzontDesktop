"""Odczyt i zapis dokumentów tekstowych z formatowaniem dla WordPada.

RTF (czytanie i zapis), DOCX (czytanie i zapis podstawowego formatowania), ODT (czytanie; zapis przez Qt),
HTML i zwykły tekst. Wszystko na QTextDocument, bez zewnętrznych bibliotek.
"""
import html
import re
import zipfile
from xml.etree import ElementTree as ET

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextImageFormat, QTextListFormat)
from PySide6.QtCore import Qt

TWIPS_PER_PX = 15          # 1440 twipów na cal, 96 pikseli na cal
DEFAULT_FONT = "Arial"


# ====================================================================== RTF — odczyt
class _State:
    __slots__ = ("font", "size", "bold", "italic", "underline", "strike", "color", "bg", "script", "skip", "uc",
                 "dest")

    def __init__(self):
        self.font = 0
        self.size = 24        # pół-punkty
        self.bold = self.italic = self.underline = self.strike = False
        self.color = 0
        self.bg = 0
        self.script = 0       # 1 indeks górny, -1 dolny
        self.skip = False
        self.uc = 1
        self.dest = None

    def copy(self):
        s = _State()
        for k in self.__slots__:
            setattr(s, k, getattr(self, k))
        return s


SKIP_DESTS = {"stylesheet", "info", "header", "footer", "headerl", "headerr", "headerf", "footerl", "footerr",
              "footerf", "fldinst", "listtable", "listoverridetable", "rsidtbl", "generator", "xmlnstbl",
              "themedata", "colorschememapping", "datastore", "latentstyles", "pgdsctbl", "filetbl", "revtbl",
              "mmathPr", "pnseclvl", "object", "objdata", "nonshppict", "bkmkstart", "bkmkend", "annotation",
              "atnid", "atnauthor", "footnote", "operator", "author", "title", "subject", "keywords", "comment",
              "doccomm", "company", "template", "wgrffmtfilter", "pnseclvl", "panose", "falt", "fname"}

TOKEN_RE = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([\r\n]+)|([^\\{}\r\n]+)")


def rtf_to_document(data, doc=None):
    """Wczytuje RTF (bajty) do QTextDocument."""
    if isinstance(data, str):
        data = data.encode("latin-1", "replace")
    doc = doc or QTextDocument()
    doc.clear()
    cur = QTextCursor(doc)
    fonts, colors = {}, []
    codepage = "cp1252"
    st = _State()
    stack = []
    para = {"align": None, "li": 0, "ri": 0, "fi": 0, "sb": 0, "sa": 0, "bullet": False}
    first_block = [True]
    cur_list = [None]
    text_buf = []
    pict = None
    font_entry = None
    color_entry = {}
    uc_skip = [0]

    def char_fmt():
        f = QTextCharFormat()
        fam = fonts.get(st.font)
        if fam:
            f.setFontFamilies([fam])
        f.setFontPointSize(max(1, st.size / 2))
        f.setFontWeight(QFont.Bold if st.bold else QFont.Normal)
        f.setFontItalic(st.italic)
        f.setFontUnderline(st.underline)
        f.setFontStrikeOut(st.strike)
        if 0 < st.color < len(colors) and colors[st.color] is not None:
            f.setForeground(QBrush(colors[st.color]))
        if 0 < st.bg < len(colors) and colors[st.bg] is not None:
            f.setBackground(QBrush(colors[st.bg]))
        if st.script == 1:
            f.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
        elif st.script == -1:
            f.setVerticalAlignment(QTextCharFormat.AlignSubScript)
        return f

    def flush():
        if text_buf:
            cur.insertText("".join(text_buf), char_fmt())
            text_buf.clear()

    def apply_block_format():
        bf = QTextBlockFormat()
        if para["align"]:
            bf.setAlignment(para["align"])
        bf.setLeftMargin(max(0, para["li"]) / TWIPS_PER_PX)
        bf.setRightMargin(max(0, para["ri"]) / TWIPS_PER_PX)
        bf.setTextIndent(para["fi"] / TWIPS_PER_PX if not para["bullet"] else 0)
        bf.setTopMargin(para["sb"] / TWIPS_PER_PX)
        bf.setBottomMargin(para["sa"] / TWIPS_PER_PX)
        cur.setBlockFormat(bf)
        if para["bullet"]:
            if cur_list[0] is None:
                lf = QTextListFormat()
                lf.setStyle(QTextListFormat.ListDisc)
                cur_list[0] = cur.createList(lf)
            else:
                cur_list[0].add(cur.block())
        else:
            if cur.block().textList() is not None:
                cur.block().textList().remove(cur.block())
            cur_list[0] = None

    def new_par():
        flush()
        apply_block_format()
        cur.insertBlock()
        first_block[0] = False

    def text(s):
        if st.skip:
            if st.dest == "fonttbl_name" and font_entry is not None:
                font_entry["name"] += s
            elif st.dest == "pict" and pict is not None:
                pict["hex"].append(s)
            return
        if uc_skip[0]:
            n = min(uc_skip[0], len(s))
            s = s[n:]
            uc_skip[0] -= n
            if not s:
                return
        text_buf.append(s)

    for m in TOKEN_RE.finditer(data):
        word, num, hexc, sym, brace, nl, plain = m.groups()
        if brace == b"{":
            stack.append(st.copy())
            continue
        if brace == b"}":
            # koniec grupy: zamykamy obiekty związane z miejscem docelowym
            if st.dest == "pict" and pict is not None and stack and stack[-1].dest != "pict":
                flush()
                _insert_pict(cur, pict)
                pict = None
            if st.dest in ("fonttbl_entry", "fonttbl_name") and font_entry is not None and \
                    stack and stack[-1].dest not in ("fonttbl_entry", "fonttbl_name"):
                fonts[font_entry["id"]] = font_entry["name"].rstrip(";").strip()
                font_entry = None
            flush() if not st.skip else None
            st = stack.pop() if stack else _State()
            continue
        if nl:
            continue
        if plain is not None:
            if st.dest == "colortbl":
                for ch in plain.decode("latin-1"):
                    if ch == ";":
                        colors.append(QColor(color_entry.get("r", 0), color_entry.get("g", 0), color_entry.get("b", 0))
                                      if color_entry else None)
                        color_entry = {}
                continue
            if st.dest in ("fonttbl", "fonttbl_entry"):
                if font_entry is not None:
                    font_entry["name"] += plain.decode(codepage, "replace")
                continue
            if st.dest == "pict" and pict is not None:
                pict["hex"].append(plain.decode("latin-1"))
                continue
            text(plain.decode(codepage, "replace"))
            continue
        if hexc is not None:
            ch = bytes([int(hexc, 16)]).decode(codepage, "replace")
            if st.dest in ("fonttbl", "fonttbl_entry") and font_entry is not None:
                font_entry["name"] += ch
            else:
                text(ch)
            continue
        if sym is not None:
            c = sym.decode("latin-1")
            if c == "*":
                st.skip = True
                st.dest = "ignorable"
            elif c in "\\{}":
                text(c)
            elif c == "~":
                text("\u00a0")
            elif c == "-":
                text("\u00ad")
            elif c == "_":
                text("\u2011")
            elif c in "\r\n":
                if not st.skip:
                    new_par()
            continue
        w = word.decode("ascii")
        n = int(num) if num is not None else None
        # miejsca docelowe
        if w == "fonttbl":
            st.dest, st.skip = "fonttbl", True
            continue
        if w == "colortbl":
            st.dest, st.skip = "colortbl", True
            continue
        if w == "pict":
            st.dest, st.skip = "pict", True
            pict = {"type": None, "hex": [], "w": 0, "h": 0, "wg": 0, "hg": 0, "sx": 100, "sy": 100}
            continue
        if w in ("pntext", "listtext"):
            para["bullet"] = True
            st.skip, st.dest = True, w
            continue
        if w == "pn" or w == "ls":
            para["bullet"] = True
            if w == "pn":
                st.skip, st.dest = True, "pn"
            continue
        if w in SKIP_DESTS:
            st.skip, st.dest = True, w
            continue
        if st.dest == "fonttbl" or st.dest == "fonttbl_entry":
            if w == "f":
                font_entry = {"id": n, "name": ""}
                st.dest = "fonttbl_entry"
            continue
        if st.dest == "colortbl":
            if w in ("red", "green", "blue"):
                color_entry[w[0]] = n or 0
            continue
        if st.dest == "pict" and pict is not None:
            if w in ("pngblip", "jpegblip", "emfblip", "wmetafile", "dibitmap", "wbitmap", "macpict"):
                pict["type"] = w
            elif w == "picw":
                pict["w"] = n
            elif w == "pich":
                pict["h"] = n
            elif w == "picwgoal":
                pict["wg"] = n
            elif w == "pichgoal":
                pict["hg"] = n
            elif w == "picscalex":
                pict["sx"] = n
            elif w == "picscaley":
                pict["sy"] = n
            elif w == "bin":
                pass
            continue
        if w == "ansicpg" and n:
            codepage = f"cp{n}"
            try:
                "".encode(codepage)
            except LookupError:
                codepage = "cp1252"
            continue
        if st.skip:
            continue
        # znaki
        if w == "par" or w == "sect":
            new_par()
        elif w == "line":
            text("\u2028")
        elif w == "tab":
            text("\t")
        elif w == "u" and n is not None:
            text(chr(n + 65536 if n < 0 else n))
            uc_skip[0] = st.uc
        elif w == "uc":
            st.uc = n or 0
        elif w in ("emdash", "endash", "bullet", "lquote", "rquote", "ldblquote", "rdblquote", "emspace", "enspace"):
            text({"emdash": "—", "endash": "–", "bullet": "•", "lquote": "‘", "rquote": "’", "ldblquote": "“",
                  "rdblquote": "”", "emspace": "\u2003", "enspace": "\u2002"}[w])
        elif w == "cell":
            text("\t")
        elif w == "row":
            new_par()
        # znak
        elif w == "plain":
            flush()
            st.font, st.size, st.bold, st.italic, st.underline, st.strike = 0, 24, False, False, False, False
            st.color, st.bg, st.script = 0, 0, 0
        elif w == "f":
            flush()
            st.font = n or 0
        elif w == "fs":
            flush()
            st.size = n or 24
        elif w == "b":
            flush()
            st.bold = n != 0
        elif w == "i":
            flush()
            st.italic = n != 0
        elif w in ("ul", "uld", "uldb", "ulw", "ulth", "uldash"):
            flush()
            st.underline = n != 0
        elif w == "ulnone":
            flush()
            st.underline = False
        elif w in ("strike", "striked"):
            flush()
            st.strike = n != 0
        elif w == "cf":
            flush()
            st.color = n or 0
        elif w in ("highlight", "cb", "chcbpat"):
            flush()
            st.bg = n or 0
        elif w == "super":
            flush()
            st.script = 1
        elif w == "sub":
            flush()
            st.script = -1
        elif w == "nosupersub":
            flush()
            st.script = 0
        # akapit
        elif w == "pard":
            flush()
            para.update({"align": None, "li": 0, "ri": 0, "fi": 0, "sb": 0, "sa": 0, "bullet": False})
        elif w in ("ql", "qc", "qr", "qj"):
            para["align"] = {"ql": Qt.AlignLeft, "qc": Qt.AlignHCenter, "qr": Qt.AlignRight, "qj": Qt.AlignJustify}[w]
        elif w in ("li", "ri", "fi", "sb", "sa"):
            para[w] = n or 0
    flush()
    apply_block_format()
    # końcowy \par zostawia pusty akapit — usuwamy go
    last = doc.lastBlock()
    if doc.blockCount() > 1 and last.length() <= 1:
        c = QTextCursor(last)
        c.movePosition(QTextCursor.PreviousCharacter, QTextCursor.KeepAnchor)
        c.removeSelectedText()
    return doc


def _insert_pict(cur, pict):
    hexdata = re.sub(r"[^0-9a-fA-F]", "", "".join(pict["hex"]))
    try:
        raw = bytes.fromhex(hexdata)
    except ValueError:
        return
    img = QImage()
    if pict["type"] in ("pngblip", "jpegblip"):
        img.loadFromData(raw)
    elif pict["type"] in ("dibitmap",):
        # DIB bez nagłówka pliku — dokładamy BITMAPFILEHEADER
        import struct
        hdr = struct.pack("<2sIHHI", b"BM", 14 + len(raw), 0, 0, 14 + struct.unpack_from("<I", raw, 0)[0])
        img.loadFromData(hdr + raw, "BMP")
    if img.isNull():
        cur.insertText("[obraz]")
        return
    _add_image(cur, img, pict["wg"] / TWIPS_PER_PX * pict["sx"] / 100 if pict["wg"] else 0,
               pict["hg"] / TWIPS_PER_PX * pict["sy"] / 100 if pict["hg"] else 0)


_img_counter = [0]


def _add_image(cur, img, w=0, h=0):
    doc = cur.document()
    _img_counter[0] += 1
    name = f"horyzont-img-{_img_counter[0]}.png"
    doc.addResource(QTextDocument.ImageResource, QUrl(name), img)
    fmt = QTextImageFormat()
    fmt.setName(name)
    if w and h:
        fmt.setWidth(w)
        fmt.setHeight(h)
    cur.insertImage(fmt)


# ====================================================================== RTF — zapis
def _rtf_escape(s, codepage="cp1250"):
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\t":
            out.append("\\tab ")
        elif ch == "\u2028":
            out.append("\\line ")
        elif ch == "\u00a0":
            out.append("\\~")
        elif o < 128:
            out.append(ch)
        else:
            try:
                b = ch.encode(codepage)
                fallback = "\\'%02x" % b[0] if len(b) == 1 else "?"
            except UnicodeEncodeError:
                fallback = "?"
            if o > 0xFFFF:
                # para zastępcza UTF-16
                o -= 0x10000
                hi, lo = 0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)
                out.append(f"\\u{hi - 65536}?\\u{lo - 65536}?")
            else:
                out.append(f"\\u{o if o < 32768 else o - 65536}{fallback}")
    return "".join(out)


def document_to_rtf(doc):
    fonts = []
    colors = []

    def font_idx(fam):
        fam = fam or DEFAULT_FONT
        if fam not in fonts:
            fonts.append(fam)
        return fonts.index(fam)

    def color_idx(c):
        key = (c.red(), c.green(), c.blue())
        if key not in colors:
            colors.append(key)
        return colors.index(key) + 1

    default_family = doc.defaultFont().family() or DEFAULT_FONT
    body = []
    block = doc.begin()
    while block.isValid():
        bf = block.blockFormat()
        parts = ["\\pard"]
        al = bf.alignment()
        if al & Qt.AlignHCenter:
            parts.append("\\qc")
        elif al & Qt.AlignRight:
            parts.append("\\qr")
        elif al & Qt.AlignJustify:
            parts.append("\\qj")
        lst = block.textList()
        li = round(bf.leftMargin() * TWIPS_PER_PX)
        fi = round(bf.textIndent() * TWIPS_PER_PX)
        if lst is not None:
            li = max(li, 360) + 360 * (lst.format().indent() - 1)
            parts.append("{\\pntext\\f%d\\'B7\\tab}{\\*\\pn\\pnlvlblt\\pnf%d\\pnindent0{\\pntxtb\\'B7}}" %
                         (font_idx("Symbol"), font_idx("Symbol")))
            fi = -360
            li += 360
        if li:
            parts.append(f"\\li{li}")
        if fi:
            parts.append(f"\\fi{fi}")
        if bf.rightMargin():
            parts.append(f"\\ri{round(bf.rightMargin() * TWIPS_PER_PX)}")
        if bf.topMargin():
            parts.append(f"\\sb{round(bf.topMargin() * TWIPS_PER_PX)}")
        if bf.bottomMargin():
            parts.append(f"\\sa{round(bf.bottomMargin() * TWIPS_PER_PX)}")
        body.append("".join(parts) + " ")
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                if cf.isImageFormat():
                    body.append(_rtf_image(doc, cf.toImageFormat()))
                else:
                    fams = _families(cf)
                    fam = (fams[0] if fams else None) or default_family
                    size = cf.fontPointSize() or doc.defaultFont().pointSizeF() or 10
                    codes = [f"\\f{font_idx(fam)}", f"\\fs{round(size * 2)}"]
                    if cf.fontWeight() >= QFont.DemiBold:
                        codes.append("\\b")
                    if cf.fontItalic():
                        codes.append("\\i")
                    if cf.fontUnderline():
                        codes.append("\\ul")
                    if cf.fontStrikeOut():
                        codes.append("\\strike")
                    if cf.hasProperty(QTextFormat.ForegroundBrush):
                        codes.append(f"\\cf{color_idx(cf.foreground().color())}")
                    if cf.hasProperty(QTextFormat.BackgroundBrush) and cf.background().style() != Qt.NoBrush:
                        codes.append(f"\\highlight{color_idx(cf.background().color())}")
                    va = cf.verticalAlignment()
                    if va == QTextCharFormat.AlignSuperScript:
                        codes.append("\\super")
                    elif va == QTextCharFormat.AlignSubScript:
                        codes.append("\\sub")
                    text = frag.text().replace("\u2029", "\n")
                    body.append("{" + "".join(codes) + " " + _rtf_escape(text).replace("\n", "\\line ") + "}")
            it += 1
        block = block.next()
        if block.isValid():
            body.append("\\par\n")
    if not fonts:
        font_idx(default_family)
    ftbl = "".join("{\\f%d\\fnil%s %s;}" % (i, "\\fcharset2" if f == "Symbol" else "\\fcharset238", _rtf_escape(f))
                   for i, f in enumerate(fonts))
    ctbl = "".join(f"\\red{r}\\green{g}\\blue{b};" for r, g, b in colors)
    head = ("{\\rtf1\\ansi\\ansicpg1250\\deff0\\deflang1045{\\fonttbl" + ftbl + "}\n{\\colortbl ;" + ctbl + "}\n"
            "{\\*\\generator Horyzont WordPad;}\\viewkind4\\uc1\n")
    return (head + "".join(body) + "}\n").encode("latin-1", "replace")


def _families(cf):
    """Rodziny czcionek fragmentu. (QTextCharFormat.fontFamilies() potrafi wysypać PySide6, gdy właściwość
    ma nietypowy typ — dlatego czytamy przez QFont.)"""
    if not (cf.hasProperty(QTextFormat.FontFamilies) or cf.hasProperty(QTextFormat.FontFamily)):
        return []
    try:
        return [f for f in cf.font().families() if f]
    except Exception:
        return []


def _image_of(doc, fmt):
    res = doc.resource(QTextDocument.ImageResource, QUrl(fmt.name()))
    if isinstance(res, QImage):
        return res
    if hasattr(res, "toImage"):
        return res.toImage()
    img = QImage(fmt.name())
    return img


def _png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def _rtf_image(doc, fmt):
    img = _image_of(doc, fmt)
    if img is None or img.isNull():
        return ""
    data = _png_bytes(img)
    w = fmt.width() or img.width()
    h = fmt.height() or img.height()
    hexs = data.hex()
    lines = "\n".join(hexs[i:i + 128] for i in range(0, len(hexs), 128))
    return ("{\\pict\\pngblip\\picw%d\\pich%d\\picwgoal%d\\pichgoal%d\n%s}" %
            (img.width(), img.height(), round(w * TWIPS_PER_PX), round(h * TWIPS_PER_PX), lines))


# ====================================================================== DOCX
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _w(tag):
    return f"{{{W}}}{tag}"


def docx_to_document(path, doc=None):
    doc = doc or QTextDocument()
    doc.clear()
    cur = QTextCursor(doc)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        rels = {}
        try:
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                rels[r.get("Id")] = r.get("Target")
        except KeyError:
            pass
        body = root.find(_w("body"))
        first = [True]
        cur_list = [None]

        def para(p):
            if not first[0]:
                cur.insertBlock()
            first[0] = False
            ppr = p.find(_w("pPr"))
            bf = QTextBlockFormat()
            bullet = False
            if ppr is not None:
                jc = ppr.find(_w("jc"))
                if jc is not None:
                    v = jc.get(_w("val"))
                    bf.setAlignment({"center": Qt.AlignHCenter, "right": Qt.AlignRight, "end": Qt.AlignRight,
                                     "both": Qt.AlignJustify}.get(v, Qt.AlignLeft))
                ind = ppr.find(_w("ind"))
                if ind is not None:
                    left = ind.get(_w("left")) or ind.get(_w("start"))
                    if left and left.lstrip("-").isdigit():
                        bf.setLeftMargin(int(left) / TWIPS_PER_PX)
                    fl = ind.get(_w("firstLine"))
                    if fl and fl.isdigit():
                        bf.setTextIndent(int(fl) / TWIPS_PER_PX)
                if ppr.find(_w("numPr")) is not None:
                    bullet = True
                ps = ppr.find(_w("pStyle"))
                heading = ps is not None and (ps.get(_w("val")) or "").lower().startswith(("heading", "nagłówek", "title"))
            else:
                heading = False
            if bullet:
                bf.setLeftMargin(0)
                bf.setTextIndent(0)
            cur.setBlockFormat(bf)
            if bullet:
                if cur_list[0] is None:
                    lf = QTextListFormat()
                    lf.setStyle(QTextListFormat.ListDisc)
                    cur_list[0] = cur.createList(lf)
                else:
                    cur_list[0].add(cur.block())
            else:
                cur_list[0] = None
            for el in p.iter():
                if el.tag == _w("r"):
                    run(el, heading)

        def run(r, heading):
            rpr = r.find(_w("rPr"))
            f = QTextCharFormat()
            if heading:
                f.setFontWeight(QFont.Bold)
                f.setFontPointSize(14)
            if rpr is not None:
                def on(tag):
                    e = rpr.find(_w(tag))
                    return e is not None and e.get(_w("val")) not in ("0", "false", "none")
                if on("b"):
                    f.setFontWeight(QFont.Bold)
                if on("i"):
                    f.setFontItalic(True)
                if on("u"):
                    f.setFontUnderline(True)
                if on("strike"):
                    f.setFontStrikeOut(True)
                sz = rpr.find(_w("sz"))
                if sz is not None and (sz.get(_w("val")) or "").isdigit():
                    f.setFontPointSize(int(sz.get(_w("val"))) / 2)
                col = rpr.find(_w("color"))
                if col is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", col.get(_w("val")) or ""):
                    f.setForeground(QColor("#" + col.get(_w("val"))))
                hl = rpr.find(_w("highlight"))
                if hl is not None and hl.get(_w("val")) not in (None, "none"):
                    f.setBackground(QColor(hl.get(_w("val"))))
                fn = rpr.find(_w("rFonts"))
                if fn is not None:
                    fam = fn.get(_w("ascii")) or fn.get(_w("hAnsi"))
                    if fam:
                        f.setFontFamilies([fam])
                va = rpr.find(_w("vertAlign"))
                if va is not None:
                    v = va.get(_w("val"))
                    if v == "superscript":
                        f.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
                    elif v == "subscript":
                        f.setVerticalAlignment(QTextCharFormat.AlignSubScript)
            for el in r:
                if el.tag == _w("t"):
                    cur.insertText(el.text or "", f)
                elif el.tag == _w("tab"):
                    cur.insertText("\t", f)
                elif el.tag in (_w("br"), _w("cr")):
                    cur.insertText("\u2028", f)
                elif el.tag == _w("drawing"):
                    blip = el.find(f".//{{{A}}}blip")
                    if blip is not None:
                        rid = blip.get(f"{{{R}}}embed")
                        target = rels.get(rid)
                        if target:
                            try:
                                data = z.read("word/" + target.lstrip("/").replace("word/", "", 1))
                                img = QImage()
                                img.loadFromData(data)
                                ext = el.find(f".//{{{WP}}}extent")
                                w = h = 0
                                if ext is not None:
                                    w = int(ext.get("cx", "0")) / 9525
                                    h = int(ext.get("cy", "0")) / 9525
                                if not img.isNull():
                                    _add_image(cur, img, w, h)
                            except KeyError:
                                pass

        for child in body:
            if child.tag == _w("p"):
                para(child)
            elif child.tag == _w("tbl"):
                for tr in child.iter(_w("tr")):
                    cells = []
                    for tc in tr.iter(_w("tc")):
                        cells.append("".join(t.text or "" for t in tc.iter(_w("t"))))
                    if not first[0]:
                        cur.insertBlock()
                    first[0] = False
                    cur.insertText("\t".join(cells))
    return doc


def document_to_docx(doc, path):
    images = []
    paras = []
    block = doc.begin()
    uses_list = False
    while block.isValid():
        bf = block.blockFormat()
        ppr = []
        al = bf.alignment()
        if al & Qt.AlignHCenter:
            ppr.append('<w:jc w:val="center"/>')
        elif al & Qt.AlignRight:
            ppr.append('<w:jc w:val="right"/>')
        elif al & Qt.AlignJustify:
            ppr.append('<w:jc w:val="both"/>')
        if block.textList() is not None:
            uses_list = True
            ppr.insert(0, '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
        elif bf.leftMargin() or bf.textIndent():
            ppr.append(f'<w:ind w:left="{round(bf.leftMargin() * TWIPS_PER_PX)}" '
                       f'w:firstLine="{max(0, round(bf.textIndent() * TWIPS_PER_PX))}"/>')
        runs = []
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                if cf.isImageFormat():
                    img = _image_of(doc, cf.toImageFormat())
                    if img is not None and not img.isNull():
                        images.append(_png_bytes(img))
                        n = len(images)
                        fw = cf.toImageFormat().width() or img.width()
                        fh = cf.toImageFormat().height() or img.height()
                        runs.append(_docx_drawing(n, round(fw * 9525), round(fh * 9525)))
                else:
                    rpr = []
                    fams = _families(cf)
                    fam = fams[0] if fams else None
                    if fam:
                        e = html.escape(fam, quote=True)
                        rpr.append(f'<w:rFonts w:ascii="{e}" w:hAnsi="{e}" w:cs="{e}"/>')
                    if cf.fontWeight() >= QFont.DemiBold:
                        rpr.append("<w:b/>")
                    if cf.fontItalic():
                        rpr.append("<w:i/>")
                    if cf.fontStrikeOut():
                        rpr.append("<w:strike/>")
                    if cf.hasProperty(QTextFormat.ForegroundBrush):
                        rpr.append(f'<w:color w:val="{cf.foreground().color().name()[1:].upper()}"/>')
                    if cf.fontPointSize():
                        rpr.append(f'<w:sz w:val="{round(cf.fontPointSize() * 2)}"/>')
                    if cf.fontUnderline():
                        rpr.append('<w:u w:val="single"/>')
                    va = cf.verticalAlignment()
                    if va == QTextCharFormat.AlignSuperScript:
                        rpr.append('<w:vertAlign w:val="superscript"/>')
                    elif va == QTextCharFormat.AlignSubScript:
                        rpr.append('<w:vertAlign w:val="subscript"/>')
                    rp = f"<w:rPr>{''.join(rpr)}</w:rPr>" if rpr else ""
                    pieces = re.split(r"(\t|\u2028)", frag.text())
                    inner = []
                    for piece in pieces:
                        if piece == "\t":
                            inner.append("<w:tab/>")
                        elif piece == "\u2028":
                            inner.append("<w:br/>")
                        elif piece:
                            inner.append(f'<w:t xml:space="preserve">{html.escape(piece, quote=False)}</w:t>')
                    runs.append(f"<w:r>{rp}{''.join(inner)}</w:r>")
            it += 1
        paras.append(f"<w:p>{'<w:pPr>' + ''.join(ppr) + '</w:pPr>' if ppr else ''}{''.join(runs)}</w:p>")
        block = block.next()
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:wp="{WP}" xmlns:a="{A}" xmlns:pic="{PIC}">'
                f'<w:body>{"".join(paras)}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                f'<w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/>'
                f'</w:sectPr></w:body></w:document>')
    rels = ['<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'] if uses_list else []
    for i in range(len(images)):
        rels.append(f'<Relationship Id="rIdImg{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{i + 1}.png"/>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Default Extension="png" ContentType="image/png"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   + ('<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>' if uses_list else '')
                   + '</Types>')
        z.writestr("_rels/.rels",
                   f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PR}">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/_rels/document.xml.rels",
                   f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PR}">{"".join(rels)}</Relationships>')
        z.writestr("word/document.xml", document)
        if uses_list:
            z.writestr("word/numbering.xml",
                       f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="{W}">'
                       '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
                       '<w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>'
                       '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')
        for i, data in enumerate(images):
            z.writestr(f"word/media/image{i + 1}.png", data)


def _docx_drawing(n, cx, cy):
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="Obraz {n}"/><a:graphic><a:graphicData uri="{PIC}"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{n}" name="image{n}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="rIdImg{n}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


# ====================================================================== ODT (odczyt)
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
XLINK = "http://www.w3.org/1999/xlink"
SVG = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"


def _t(tag):
    return f"{{{TEXT}}}{tag}"


def odt_to_document(path, doc=None):
    doc = doc or QTextDocument()
    doc.clear()
    cur = QTextCursor(doc)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
        styles = {}
        for src in [root]:
            for st in src.iter(f"{{{STYLE}}}style"):
                name = st.get(f"{{{STYLE}}}name")
                d = {"parent": st.get(f"{{{STYLE}}}parent-style-name")}
                tp = st.find(f"{{{STYLE}}}text-properties")
                if tp is not None:
                    d["bold"] = tp.get(f"{{{FO}}}font-weight") == "bold"
                    d["italic"] = tp.get(f"{{{FO}}}font-style") == "italic"
                    d["underline"] = tp.get(f"{{{STYLE}}}text-underline-style") not in (None, "none")
                    d["strike"] = tp.get(f"{{{STYLE}}}text-line-through-style") not in (None, "none")
                    if tp.get(f"{{{FO}}}color"):
                        d["color"] = tp.get(f"{{{FO}}}color")
                    if tp.get(f"{{{FO}}}background-color") not in (None, "transparent"):
                        d["bg"] = tp.get(f"{{{FO}}}background-color")
                    fs = tp.get(f"{{{FO}}}font-size") or ""
                    if fs.endswith("pt"):
                        try:
                            d["size"] = float(fs[:-2])
                        except ValueError:
                            pass
                    if tp.get(f"{{{STYLE}}}font-name"):
                        d["font"] = tp.get(f"{{{STYLE}}}font-name")
                    pos = tp.get(f"{{{STYLE}}}text-position") or ""
                    if pos.startswith("super"):
                        d["script"] = 1
                    elif pos.startswith("sub"):
                        d["script"] = -1
                pp = st.find(f"{{{STYLE}}}paragraph-properties")
                if pp is not None and pp.get(f"{{{FO}}}text-align"):
                    d["align"] = pp.get(f"{{{FO}}}text-align")
                styles[name] = d
        body = root.find(f"{{{OFFICE}}}body/{{{OFFICE}}}text")
        first = [True]

        def char_fmt(stack):
            f = QTextCharFormat()
            for name in stack:
                d = styles.get(name) or {}
                if d.get("bold"):
                    f.setFontWeight(QFont.Bold)
                if d.get("italic"):
                    f.setFontItalic(True)
                if d.get("underline"):
                    f.setFontUnderline(True)
                if d.get("strike"):
                    f.setFontStrikeOut(True)
                if d.get("color"):
                    f.setForeground(QColor(d["color"]))
                if d.get("bg"):
                    f.setBackground(QColor(d["bg"]))
                if d.get("size"):
                    f.setFontPointSize(d["size"])
                if d.get("font"):
                    f.setFontFamilies([d["font"]])
                if d.get("script") == 1:
                    f.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
                elif d.get("script") == -1:
                    f.setVerticalAlignment(QTextCharFormat.AlignSubScript)
            return f

        def put(txt, stack):
            txt = re.sub(r"[ \t\r\n]+", " ", txt)
            if cur.atBlockStart():
                txt = txt.lstrip(" ")
            if txt:
                cur.insertText(txt, char_fmt(stack))

        def inline(el, stack):
            if el.text:
                put(el.text, stack)
            for ch in el:
                tag = ch.tag
                if tag == _t("span"):
                    inline(ch, stack + [ch.get(_t("style-name"))])
                elif tag == _t("s"):
                    cur.insertText(" " * int(ch.get(_t("c"), "1")), char_fmt(stack))
                elif tag == _t("tab"):
                    cur.insertText("\t", char_fmt(stack))
                elif tag == _t("line-break"):
                    cur.insertText("\u2028", char_fmt(stack))
                elif tag == _t("a"):
                    inline(ch, stack)
                elif tag == f"{{{DRAW}}}frame":
                    im = ch.find(f"{{{DRAW}}}image")
                    if im is not None:
                        href = im.get(f"{{{XLINK}}}href") or ""
                        try:
                            img = QImage()
                            img.loadFromData(z.read(href))
                            if not img.isNull():
                                _add_image(cur, img)
                        except KeyError:
                            pass
                else:
                    inline(ch, stack)
                if ch.tail:
                    put(ch.tail, stack)

        def paragraph(el, bullet=False, list_holder=None, heading=False):
            if not first[0]:
                cur.insertBlock()
            first[0] = False
            st = styles.get(el.get(_t("style-name"))) or {}
            parent = styles.get(st.get("parent")) or {}
            align = st.get("align") or parent.get("align")
            bf = QTextBlockFormat()
            if align:
                bf.setAlignment({"center": Qt.AlignHCenter, "end": Qt.AlignRight, "right": Qt.AlignRight,
                                 "justify": Qt.AlignJustify}.get(align, Qt.AlignLeft))
            cur.setBlockFormat(bf)
            if bullet:
                if list_holder[0] is None:
                    lf = QTextListFormat()
                    lf.setStyle(QTextListFormat.ListDisc)
                    list_holder[0] = cur.createList(lf)
                else:
                    list_holder[0].add(cur.block())
            stack = [el.get(_t("style-name"))]
            if heading:
                f = QTextCharFormat()
                f.setFontWeight(QFont.Bold)
                f.setFontPointSize(15)
                cur.setCharFormat(f)
            inline(el, stack)

        def walk(container):
            for el in container:
                if el.tag in (_t("p"), _t("h")):
                    paragraph(el, heading=el.tag == _t("h"))
                elif el.tag == _t("list"):
                    holder = [None]
                    for item in el.iter(_t("list-item")):
                        for p in item:
                            if p.tag in (_t("p"), _t("h")):
                                paragraph(p, True, holder)
                elif el.tag == _t("section"):
                    walk(el)
                elif el.tag.endswith("}table"):
                    for row in el.iter("{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-row"):
                        cells = ["".join(c.itertext()) for c in row]
                        if not first[0]:
                            cur.insertBlock()
                        first[0] = False
                        cur.insertText("\t".join(cells))
        if body is not None:
            walk(body)
    return doc


def document_to_odt(doc, path):
    from PySide6.QtGui import QTextDocumentWriter
    w = QTextDocumentWriter(path, QByteArray(b"ODF"))
    return w.write(doc)


# ====================================================================== wspólne
def detect(path, head=None):
    """Rodzaj pliku: rtf / docx / odt / doc / html / txt."""
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if head is None:
        try:
            with open(path, "rb") as f:
                head = f.read(8)
        except OSError:
            head = b""
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            if "word/document.xml" in names:
                return "docx"
            if "content.xml" in names:
                return "odt"
        except zipfile.BadZipFile:
            pass
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "doc"
    if ext in ("htm", "html", "xhtml"):
        return "html"
    return "txt"


def load(path, doc):
    kind = detect(path)
    if kind == "rtf":
        with open(path, "rb") as f:
            rtf_to_document(f.read(), doc)
    elif kind == "docx":
        docx_to_document(path, doc)
    elif kind == "odt":
        odt_to_document(path, doc)
    elif kind == "html":
        with open(path, "rb") as f:
            data = f.read()
        doc.setHtml(data.decode("utf-8", "replace"))
    elif kind == "doc":
        raise ValueError("doc")
    else:
        from ..apps.notepad import detect_and_decode
        with open(path, "rb") as f:
            text, _enc, _crlf = detect_and_decode(f.read())
        doc.setPlainText(text)
    return kind


def save(doc, path, kind):
    if kind == "rtf":
        data = document_to_rtf(doc)
        with open(path, "wb") as f:
            f.write(data)
    elif kind == "docx":
        document_to_docx(doc, path)
    elif kind == "odt":
        if not document_to_odt(doc, path):
            raise OSError("ODF")
    elif kind == "html":
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.toHtml())
    elif kind == "txt-ansi":
        with open(path, "wb") as f:
            f.write(doc.toPlainText().replace("\u2028", "\n").replace("\n", "\r\n").encode("cp1250", "replace"))
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.toPlainText().replace("\u2028", "\n"))
