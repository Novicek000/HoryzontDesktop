"""WordPad — edytor dokumentów z formatowaniem (RTF, DOCX, ODT, TXT, HTML)."""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QMarginsF, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPainter,
                           QPageLayout, QPageSize, QPixmap, QPolygon, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextListFormat, QTextOption)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDoubleSpinBox, QFontComboBox, QFontDialog,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QMenu, QMenuBar,
                               QPushButton, QStatusBar, QTextEdit, QToolButton, QVBoxLayout, QWidget,
                               QColorDialog)

from .. import config
from ..common import dialogs, richtext
from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow
from ..theme import iconcache

PX_PER_CM = 96 / 2.54
PAGE_TEXT_WIDTH = round(14.66 * PX_PER_CM)   # A4 minus marginesy 3,17 cm
SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]

KINDS = [  # (rodzaj, opis pl, opis en, wzorce)
    ("rtf", "Format RTF (RTF)", "Rich Text Format (RTF)", "*.rtf"),
    ("docx", "Dokument programu Word (DOCX)", "Word document (DOCX)", "*.docx"),
    ("odt", "Dokument tekstowy OpenDocument (ODT)", "OpenDocument Text (ODT)", "*.odt"),
    ("txt", "Dokument tekstowy (TXT)", "Text Document (TXT)", "*.txt"),
    ("txt-ansi", "Dokument tekstowy — ANSI (TXT)", "Text Document — ANSI (TXT)", "*.txt"),
    ("html", "Strona sieci Web (HTML)", "Web page (HTML)", "*.htm *.html"),
]


def open_filter():
    return ";;".join([
        T("Wszystkie dokumenty", "All Documents") + " (*.rtf *.docx *.odt *.txt *.htm *.html *.doc *.text *.md)",
        T("Format RTF (*.rtf)", "Rich Text Format (*.rtf)"),
        T("Dokumenty programu Word (*.docx *.doc)", "Word documents (*.docx *.doc)"),
        T("Dokumenty OpenDocument (*.odt)", "OpenDocument Text (*.odt)"),
        T("Dokumenty tekstowe (*.txt)", "Text Documents (*.txt)"),
        T("Wszystkie pliki (*)", "All Files (*)"),
    ])


def save_filter():
    return ";;".join(f"{T(pl, en)} ({pat})" for _k, pl, en, pat in KINDS)


def kind_for_ext(path):
    ext = os.path.splitext(path)[1].lower()
    return {".rtf": "rtf", ".docx": "docx", ".odt": "odt", ".htm": "html", ".html": "html",
            ".txt": "txt", ".text": "txt", ".md": "txt"}.get(ext)


# ====================================================================== ikony paska narzędzi (oryginalne)
def _draw_icon(kind, size=16):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    k = QColor("#202020")
    p.setPen(k)
    if kind.startswith("align_"):
        widths = {"align_left": [(1, 14), (1, 9), (1, 14), (1, 9), (1, 14)],
                  "align_center": [(1, 14), (4, 8), (1, 14), (4, 8), (1, 14)],
                  "align_right": [(1, 14), (6, 9), (1, 14), (6, 9), (1, 14)]}[kind]
        for i, (x, w) in enumerate(widths):
            p.drawLine(x, 2 + i * 3, x + w - 1, 2 + i * 3)
    elif kind == "bullets":
        for i in range(3):
            p.setBrush(k)
            p.drawEllipse(1, 2 + i * 5, 2, 2)
            p.drawLine(6, 3 + i * 5, 14, 3 + i * 5)
    elif kind == "color":
        p.setBrush(QColor("#f3f3f3"))
        p.drawEllipse(1, 1, 13, 13)
        for (x, y), c in zip(((4, 4), (8, 3), (11, 7), (5, 9)), ("#d02020", "#e0b000", "#2070d0", "#20a040")):
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawEllipse(x, y, 3, 3)
    elif kind == "preview":
        p.setBrush(QColor("#ffffff"))
        p.drawRect(2, 1, 9, 12)
        p.setBrush(QColor(200, 230, 255))
        p.drawEllipse(7, 7, 6, 6)
        p.drawLine(12, 12, 15, 15)
    p.end()
    return QIcon(pm)


# ====================================================================== linijka
class Ruler(QWidget):
    """Linijka w centymetrach ze znacznikami wcięć bieżącego akapitu (można je przeciągać)."""

    indents_changed = Signal(float, float, float)   # lewe, pierwszego wiersza (względne), prawe — w px

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(24)
        self.left = 0.0
        self.first = 0.0
        self.right = 0.0
        self._drag = None

    def origin(self):
        ed = self.win.text
        top = self.window()
        x = self.mapFrom(top, ed.viewport().mapTo(top, QPoint(0, 0))).x()
        return x + int(ed.document().documentMargin()) - ed.horizontalScrollBar().value()

    def text_width(self):
        ed = self.win.text
        if ed.lineWrapMode() == QTextEdit.FixedPixelWidth:
            return ed.lineWrapColumnOrWidth()
        return ed.viewport().width() - 2 * int(ed.document().documentMargin())

    def set_block(self, bf):
        self.left = bf.leftMargin()
        self.first = bf.textIndent()
        self.right = bf.rightMargin()
        self.update()

    def _markers(self):
        o = self.origin()
        w = self.text_width()
        return {"first": o + self.left + self.first, "left": o + self.left, "right": o + w - self.right}

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        o = self.origin()
        w = self.text_width()
        band = QRect(o, 4, w, 14)
        p.fillRect(QRect(0, 4, self.width(), 14), QColor("#a0a0a0").lighter(130))
        p.fillRect(band, QColor("#ffffff"))
        p.setPen(QColor("#404040"))
        f = QFont(self.font())
        f.setPixelSize(9)
        p.setFont(f)
        cm = 0
        x = o
        while x <= o + w:
            if cm > 0:
                p.drawText(QRect(int(x) - 8, 4, 16, 14), Qt.AlignCenter, str(cm))
            half = x + PX_PER_CM / 2
            if half < o + w:
                p.drawLine(int(half), 9, int(half), 12)
            cm += 1
            x = o + cm * PX_PER_CM
        m = self._markers()
        p.setPen(QColor("#303030"))
        p.setBrush(QColor("#d8d8d8"))
        fx, lx, rx = int(m["first"]), int(m["left"]), int(m["right"])
        p.drawPolygon(QPolygon([QPoint(fx - 4, 1), QPoint(fx + 4, 1), QPoint(fx, 6)]))
        p.drawPolygon(QPolygon([QPoint(lx - 4, 22), QPoint(lx + 4, 22), QPoint(lx + 4, 19), QPoint(lx, 15),
                                QPoint(lx - 4, 19)]))
        p.drawPolygon(QPolygon([QPoint(rx - 4, 22), QPoint(rx + 4, 22), QPoint(rx + 4, 19), QPoint(rx, 15),
                                QPoint(rx - 4, 19)]))

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        m = self._markers()
        best = None
        for k, mx in m.items():
            if abs(mx - x) <= 6 and ((k == "first" and y < 9) or (k != "first" and y >= 9)):
                best = k
        self._drag = best

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        o = self.origin()
        x = e.position().x() - o
        w = self.text_width()
        step = PX_PER_CM / 4

        def snap(v):
            return round(v / step) * step
        if self._drag == "left":
            self.left = max(0.0, min(w - self.right - 20, snap(x)))
        elif self._drag == "first":
            self.first = snap(x) - self.left
        elif self._drag == "right":
            self.right = max(0.0, min(w - self.left - 20, snap(w - x)))
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self.indents_changed.emit(self.left, self.first, self.right)


# ====================================================================== edytor
class Editor(QTextEdit):
    def canInsertFromMimeData(self, source):
        return source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage() and not source.hasText():
            img = QImage(source.imageData())
            if not img.isNull():
                self.window().insert_image(img)
                return
        if source.hasUrls() and not source.hasText():
            for u in source.urls():
                if u.isLocalFile():
                    img = QImage(u.toLocalFile())
                    if not img.isNull():
                        self.window().insert_image(img)
            return
        super().insertFromMimeData(source)


class ParagraphDialog(HDialog):
    def __init__(self, win, bf):
        super().__init__(T("Akapit", "Paragraph"), "wordpad", win)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        box = QGroupBox(T("Wcięcia", "Indentation"))
        g = QGridLayout(box)
        self.left = QDoubleSpinBox()
        self.right = QDoubleSpinBox()
        self.first = QDoubleSpinBox()
        for i, (sb, label, val) in enumerate(((self.left, T("&Lewe:", "&Left:"), bf.leftMargin()),
                                               (self.right, T("&Prawe:", "&Right:"), bf.rightMargin()),
                                               (self.first, T("&Pierwszy wiersz:", "&First line:"), bf.textIndent()))):
            sb.setRange(-10 if sb is self.first else 0, 20)
            sb.setDecimals(2)
            sb.setSingleStep(0.25)
            sb.setSuffix(" cm")
            sb.setValue(val / PX_PER_CM)
            lab = QLabel(label)
            lab.setBuddy(sb)
            g.addWidget(lab, i, 0)
            g.addWidget(sb, i, 1)
        lay.addWidget(box)
        row = QHBoxLayout()
        al = QLabel(T("&Wyrównanie:", "&Alignment:"))
        self.align = QComboBox()
        for label, v in ((T("Do lewej", "Left"), Qt.AlignLeft), (T("Do prawej", "Right"), Qt.AlignRight),
                         (T("Do środka", "Center"), Qt.AlignHCenter), (T("Wyjustuj", "Justify"), Qt.AlignJustify)):
            self.align.addItem(label, int(v))
        cur = int(bf.alignment()) & int(Qt.AlignHorizontal_Mask)
        idx = max(0, self.align.findData(cur if cur not in (0, int(Qt.AlignLeading)) else int(Qt.AlignLeft)))
        self.align.setCurrentIndex(idx)
        al.setBuddy(self.align)
        row.addWidget(al)
        row.addWidget(self.align, 1)
        lay.addLayout(row)
        lay.addLayout(_buttons(self))


class TabsDialog(HDialog):
    def __init__(self, win, positions):
        super().__init__(T("Tabulatory", "Tabs"), "wordpad", win)
        self.positions = sorted(positions)
        lay = QHBoxLayout(self.body())
        lay.setContentsMargins(10, 10, 10, 10)
        left = QVBoxLayout()
        left.addWidget(QLabel(T("&Położenie tabulatora:", "&Tab stop position:")))
        self.pos = QDoubleSpinBox()
        self.pos.setRange(0, 30)
        self.pos.setDecimals(2)
        self.pos.setSuffix(" cm")
        left.addWidget(self.pos)
        self.list = QListWidget()
        left.addWidget(self.list)
        lay.addLayout(left)
        right = QVBoxLayout()
        for text, fn in ((T("&Ustaw", "&Set"), self._set), (T("&Wyczyść", "Cl&ear"), self._clear),
                         (T("Wyczyść &wszystkie", "Clear &All"), self._clear_all)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            right.addWidget(b)
        right.addStretch(1)
        right.addLayout(_buttons(self, vertical=True))
        lay.addLayout(right)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        for p in self.positions:
            self.list.addItem(f"{p / PX_PER_CM:.2f} cm".replace(".", ","))

    def _set(self):
        px = self.pos.value() * PX_PER_CM
        if px > 0 and all(abs(px - p) > 1 for p in self.positions):
            self.positions = sorted(self.positions + [px])
            self._refresh()

    def _clear(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.positions[i]
            self._refresh()

    def _clear_all(self):
        self.positions = []
        self._refresh()


def _buttons(dlg, vertical=False):
    row = QVBoxLayout() if vertical else QHBoxLayout()
    if not vertical:
        row.addStretch(1)
    ok = QPushButton(T("OK", "OK"))
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    ca = QPushButton(T("Anuluj", "Cancel"))
    ca.clicked.connect(dlg.reject)
    row.addWidget(ok)
    row.addWidget(ca)
    return row


# ====================================================================== okno
class WordPadWindow(HWindow):
    def __init__(self, ctl, path=None):
        super().__init__("", "wordpad")
        self.ctl = ctl
        self.path = None
        self.kind = config.get("wordpad_default_kind", "rtf")
        self.last_find = ""
        self.last_case = False
        self.last_up = False
        self._find_dlg = None
        self._printer = None
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.toolbar = self._make_toolbar()
        lay.addWidget(self.toolbar)
        self.formatbar = self._make_formatbar()
        lay.addWidget(self.formatbar)
        self.text = Editor()
        self.text.setAcceptRichText(True)
        self.text.document().setDocumentMargin(8)
        f = QFont("Arial" if "Arial" in QFontDatabase.families() else QApplication.font().family())
        f.setPointSize(10)
        self.text.document().setDefaultFont(f)
        self.text.setStyleSheet("QTextEdit { background: #ffffff; color: #000000; }")
        self.ruler = Ruler(self)
        self.ruler.indents_changed.connect(self._ruler_indents)
        lay.addWidget(self.ruler)
        lay.addWidget(self.text, 1)
        self.status = QStatusBar()
        self.status.addWidget(QLabel(T("Aby uzyskać Pomoc, naciśnij klawisz F1", "For Help, press F1")), 1)
        lay.addWidget(self.status)
        self._build_menus()
        self.set_wrap(config.get("wordpad_wrap", "ruler"))
        self.text.currentCharFormatChanged.connect(self._char_changed)
        self.text.cursorPositionChanged.connect(self._cursor_moved)
        self.text.document().modificationChanged.connect(lambda *_: self._update_title())
        self.text.horizontalScrollBar().valueChanged.connect(lambda *_: self.ruler.update())
        for key, w in (("wordpad_toolbar", self.toolbar), ("wordpad_formatbar", self.formatbar),
                       ("wordpad_ruler", self.ruler), ("wordpad_status", self.status)):
            w.setVisible(config.get(key, True))
        self.resize(780, 560)
        if path:
            self.load(path)
        self._char_changed(self.text.currentCharFormat())
        self._cursor_moved()
        if not path:
            # ustawienie czcionki i układu nowego dokumentu to nie zmiana treści — bez pytania o zapis
            self.text.document().setModified(False)
        self._update_title()
        self.setAcceptDrops(True)

    # -------------------------------------------------------- paski
    def _tb(self, icon, tip, fn, checkable=False):
        b = QToolButton()
        b.setIcon(icon)
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCheckable(checkable)
        if checkable:
            b.toggled.connect(lambda on: fn(on))
        else:
            b.clicked.connect(lambda _=False: fn())
        return b

    def _make_toolbar(self):
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(1)
        items = [("file", T("Nowy", "New"), self.new), ("folder_open", T("Otwórz", "Open"), self.open_dialog),
                 ("drive_floppy", T("Zapisz", "Save"), self.save), None,
                 ("printer", T("Drukuj", "Print"), self.print_doc), (None, T("Podgląd wydruku", "Print Preview"), self.preview),
                 None, ("search", T("Znajdź", "Find"), lambda: self.show_find(False)), None,
                 ("cut", T("Wytnij", "Cut"), lambda: self.text.cut()), ("copy", T("Kopiuj", "Copy"), lambda: self.text.copy()),
                 ("paste", T("Wklej", "Paste"), lambda: self.text.paste()), ("undo", T("Cofnij", "Undo"), lambda: self.text.undo()),
                 None, ("datetime", T("Data/godzina", "Date/Time"), self.insert_datetime)]
        for it in items:
            if it is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setFrameShadow(QFrame.Sunken)
                lay.addWidget(sep)
                continue
            icon = iconcache.icon(it[0]) if it[0] else _draw_icon("preview")
            lay.addWidget(self._tb(icon, it[1], it[2]))
        lay.addStretch(1)
        return bar

    def _make_formatbar(self):
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        self.font_box = QFontComboBox()
        self.font_box.setFocusPolicy(Qt.ClickFocus)
        self.font_box.setMinimumWidth(170)
        self.font_box.currentFontChanged.connect(self._set_family)
        lay.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.setFixedWidth(56)
        for s in SIZES:
            self.size_box.addItem(str(s))
        self.size_box.textActivated.connect(self._set_size)
        self.size_box.lineEdit().returnPressed.connect(lambda: self._set_size(self.size_box.currentText()))
        lay.addWidget(self.size_box)
        lay.addSpacing(6)
        self.b_bold = self._tb(QIcon(), T("Pogrubienie", "Bold"), self._set_bold, True)
        self.b_italic = self._tb(QIcon(), T("Kursywa", "Italic"), self._set_italic, True)
        self.b_under = self._tb(QIcon(), T("Podkreślenie", "Underline"), self._set_underline, True)
        for b, t, attr in ((self.b_bold, "B", "setBold"), (self.b_italic, "I", "setItalic"), (self.b_under, "U", "setUnderline")):
            b.setText(t)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            f = b.font()
            getattr(f, attr)(True)
            f.setFamily("serif")
            b.setFont(f)
            b.setFixedSize(24, 22)
            lay.addWidget(b)
        self.b_color = self._tb(_draw_icon("color"), T("Kolor", "Color"), self._color_menu)
        lay.addWidget(self.b_color)
        lay.addSpacing(6)
        self.b_left = self._tb(_draw_icon("align_left"), T("Wyrównaj do lewej", "Align Left"), lambda on: self._align(Qt.AlignLeft, on), True)
        self.b_center = self._tb(_draw_icon("align_center"), T("Wyśrodkuj", "Center"), lambda on: self._align(Qt.AlignHCenter, on), True)
        self.b_right = self._tb(_draw_icon("align_right"), T("Wyrównaj do prawej", "Align Right"), lambda on: self._align(Qt.AlignRight, on), True)
        for b in (self.b_left, self.b_center, self.b_right):
            lay.addWidget(b)
        lay.addSpacing(6)
        self.b_bullets = self._tb(_draw_icon("bullets"), T("Punktory", "Bullets"), self._bullets, True)
        lay.addWidget(self.b_bullets)
        lay.addStretch(1)
        return bar

    # -------------------------------------------------------- menu
    def _build_menus(self):
        mb = self.menubar
        m = mb.addMenu(T("&Plik", "&File"))
        act(m, T("&Nowy…", "&New..."), self.new, "Ctrl+N")
        act(m, T("&Otwórz…", "&Open..."), self.open_dialog, "Ctrl+O")
        act(m, T("&Zapisz", "&Save"), self.save, "Ctrl+S")
        act(m, T("Zapisz &jako…", "Save &As..."), self.save_as)
        m.addSeparator()
        act(m, T("&Drukuj…", "&Print..."), self.print_doc, "Ctrl+P")
        act(m, T("Podgląd &wydruku", "Print Pre&view"), self.preview)
        act(m, T("&Ustawienia strony…", "Page Set&up..."), self.page_setup)
        m.addSeparator()
        self.recent_menu = m.addMenu(T("Ostatnio &używane", "Recent &Files"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addSeparator()
        act(m, T("&Zakończ", "E&xit"), self.close)
        m = mb.addMenu(T("&Edycja", "&Edit"))
        self.a_undo = act(m, T("&Cofnij", "&Undo"), self.text.undo, "Ctrl+Z")
        self.a_redo = act(m, T("&Ponów", "&Redo"), self.text.redo, "Ctrl+Y")
        m.addSeparator()
        self.a_cut = act(m, T("Wy&tnij", "Cu&t"), self.text.cut, "Ctrl+X")
        self.a_copy = act(m, T("&Kopiuj", "&Copy"), self.text.copy, "Ctrl+C")
        act(m, T("&Wklej", "&Paste"), self.text.paste, "Ctrl+V")
        act(m, T("Wklej jako &zwykły tekst", "Paste &Special (plain text)"), self.paste_plain, "Ctrl+Shift+V")
        self.a_clear = act(m, T("Wy&czyść", "Cle&ar"), lambda: self.text.textCursor().removeSelectedText(), "Del")
        act(m, T("Zaznacz &wszystko", "Select A&ll"), self.text.selectAll, "Ctrl+A")
        m.addSeparator()
        act(m, T("&Znajdź…", "&Find..."), lambda: self.show_find(False), "Ctrl+F")
        act(m, T("Znajdź &następny", "Find &Next"), self.find_next_or_dialog, "F3")
        act(m, T("Za&mień…", "R&eplace..."), lambda: self.show_find(True), "Ctrl+H")
        m.aboutToShow.connect(self._update_edit)
        m = mb.addMenu(T("&Widok", "&View"))
        for text, w, key in ((T("&Pasek narzędzi", "&Toolbar"), self.toolbar, "wordpad_toolbar"),
                             (T("Pasek &formatu", "&Format Bar"), self.formatbar, "wordpad_formatbar"),
                             (T("&Linijka", "&Ruler"), self.ruler, "wordpad_ruler"),
                             (T("Pasek &stanu", "&Status Bar"), self.status, "wordpad_status")):
            act(m, text, lambda on, w=w, key=key: (w.setVisible(on), config.set(key, on)), checkable=True,
                checked=config.get(key, True))
        m.addSeparator()
        wm = m.addMenu(T("&Opcje zawijania", "&Word Wrap"))
        self.wrap_actions = {}
        for key, text in (("none", T("&Bez zawijania", "&No wrap")), ("window", T("Zawijaj do &okna", "Wrap to &window")),
                          ("ruler", T("Zawijaj do &linijki", "Wrap to &ruler"))):
            a = wm.addAction(text)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self.set_wrap(k))
            self.wrap_actions[key] = a
        m = mb.addMenu(T("W&staw", "&Insert"))
        act(m, T("&Data i godzina…", "&Date and Time..."), self.insert_datetime_dialog)
        act(m, T("&Obraz…", "&Picture..."), self.insert_picture_dialog)
        m = mb.addMenu(T("F&ormat", "F&ormat"))
        act(m, T("&Czcionka…", "&Font..."), self.font_dialog)
        self.a_bullet = act(m, T("&Styl punktora", "&Bullet Style"), self._bullets, checkable=True)
        act(m, T("&Akapit…", "&Paragraph..."), self.paragraph_dialog)
        act(m, T("&Tabulatory…", "&Tabs..."), self.tabs_dialog)
        m.addSeparator()
        act(m, T("Indeks &górny", "Su&perscript"), lambda: self._script(QTextCharFormat.AlignSuperScript), "Ctrl+Shift+=")
        act(m, T("Indeks &dolny", "Su&bscript"), lambda: self._script(QTextCharFormat.AlignSubScript), "Ctrl+=")
        act(m, T("&Przekreślenie", "&Strikethrough"), self._strike)
        act(m, T("&Wyczyść formatowanie", "&Clear Formatting"), self._clear_format, "Ctrl+Space")
        help_menu(mb, self, "WordPad", "wordpad", "wordpad")
        # skróty formatowania
        for seq, fn in (("Ctrl+B", lambda: self.b_bold.toggle()), ("Ctrl+I", lambda: self.b_italic.toggle()),
                        ("Ctrl+U", lambda: self.b_under.toggle()), ("Ctrl+E", lambda: self._align(Qt.AlignHCenter, True)),
                        ("Ctrl+L", lambda: self._align(Qt.AlignLeft, True)), ("Ctrl+R", lambda: self._align(Qt.AlignRight, True)),
                        ("Ctrl+J", lambda: self._align(Qt.AlignJustify, True))):
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(fn)
            self.addAction(a)

    def _update_edit(self):
        has = self.text.textCursor().hasSelection()
        for a in (self.a_cut, self.a_copy, self.a_clear):
            a.setEnabled(has)
        self.a_undo.setEnabled(self.text.document().isUndoAvailable())
        self.a_redo.setEnabled(self.text.document().isRedoAvailable())

    def _fill_recent(self):
        self.recent_menu.clear()
        files = [f for f in config.get("wordpad_recent", []) if os.path.exists(f)]
        for i, f in enumerate(files[:6]):
            a = self.recent_menu.addAction(f"&{i + 1} {os.path.basename(f)}")
            a.setToolTip(f)
            a.triggered.connect(lambda _=False, f=f: self.maybe_save() and self.load(f))
        if not files:
            a = self.recent_menu.addAction(T("(brak)", "(empty)"))
            a.setEnabled(False)

    def _remember(self, path):
        rec = [path] + [f for f in config.get("wordpad_recent", []) if f != path]
        config.set("wordpad_recent", rec[:8])

    # -------------------------------------------------------- stan
    def display_name(self):
        return os.path.basename(self.path) if self.path else T("Dokument", "Document")

    def _update_title(self):
        self.setWindowTitle(f"{self.display_name()} - WordPad")

    def set_wrap(self, mode):
        config.set("wordpad_wrap", mode)
        for k, a in getattr(self, "wrap_actions", {}).items():
            a.setChecked(k == mode)
        if mode == "none":
            self.text.setLineWrapMode(QTextEdit.NoWrap)
        elif mode == "window":
            self.text.setLineWrapMode(QTextEdit.WidgetWidth)
        else:
            self.text.setLineWrapMode(QTextEdit.FixedPixelWidth)
            self.text.setLineWrapColumnOrWidth(PAGE_TEXT_WIDTH)
        self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.ruler.update()

    def _char_changed(self, fmt):
        f = fmt.font()
        self.font_box.blockSignals(True)
        self.size_box.blockSignals(True)
        fams = f.families()
        if fams:
            self.font_box.setCurrentFont(QFont(fams[0]))
        size = fmt.fontPointSize() or self.text.document().defaultFont().pointSizeF()
        self.size_box.setCurrentText(str(int(size)) if size == int(size) else f"{size:.1f}")
        self.font_box.blockSignals(False)
        self.size_box.blockSignals(False)
        for b, v in ((self.b_bold, fmt.fontWeight() >= QFont.DemiBold), (self.b_italic, fmt.fontItalic()),
                     (self.b_under, fmt.fontUnderline())):
            b.blockSignals(True)
            b.setChecked(v)
            b.blockSignals(False)

    def _cursor_moved(self):
        bf = self.text.textCursor().blockFormat()
        al = int(bf.alignment()) & int(Qt.AlignHorizontal_Mask)
        for b, v in ((self.b_left, al in (0, int(Qt.AlignLeft), int(Qt.AlignLeading))),
                     (self.b_center, al == int(Qt.AlignHCenter)), (self.b_right, al in (int(Qt.AlignRight), int(Qt.AlignTrailing)))):
            b.blockSignals(True)
            b.setChecked(v)
            b.blockSignals(False)
        in_list = self.text.textCursor().currentList() is not None
        self.b_bullets.blockSignals(True)
        self.b_bullets.setChecked(in_list)
        self.b_bullets.blockSignals(False)
        self.a_bullet.blockSignals(True)
        self.a_bullet.setChecked(in_list)
        self.a_bullet.blockSignals(False)
        self.ruler.set_block(bf)

    # -------------------------------------------------------- formatowanie
    def _merge(self, fmt):
        c = self.text.textCursor()
        if c.hasSelection():
            c.mergeCharFormat(fmt)
        self.text.mergeCurrentCharFormat(fmt)
        self.text.setFocus()

    def _set_family(self, font):
        f = QTextCharFormat()
        f.setFontFamilies([font.family()])
        self._merge(f)

    def _set_size(self, text):
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            return
        if 1 <= v <= 1638:
            f = QTextCharFormat()
            f.setFontPointSize(v)
            self._merge(f)

    def _set_bold(self, on):
        f = QTextCharFormat()
        f.setFontWeight(QFont.Bold if on else QFont.Normal)
        self._merge(f)

    def _set_italic(self, on):
        f = QTextCharFormat()
        f.setFontItalic(on)
        self._merge(f)

    def _set_underline(self, on):
        f = QTextCharFormat()
        f.setFontUnderline(on)
        self._merge(f)

    def _strike(self):
        f = QTextCharFormat()
        f.setFontStrikeOut(not self.text.currentCharFormat().fontStrikeOut())
        self._merge(f)

    def _script(self, align):
        f = QTextCharFormat()
        cur = self.text.currentCharFormat().verticalAlignment()
        f.setVerticalAlignment(QTextCharFormat.AlignNormal if cur == align else align)
        self._merge(f)

    def _clear_format(self):
        c = self.text.textCursor()
        f = QTextCharFormat()
        f.setFont(self.text.document().defaultFont())
        if c.hasSelection():
            c.setCharFormat(f)
        self.text.setCurrentCharFormat(f)

    def _color_menu(self):
        m = QMenu(self)
        colors = [(T("Czarny", "Black"), "#000000"), (T("Kasztanowy", "Maroon"), "#800000"), (T("Zielony", "Green"), "#008000"),
                  (T("Oliwkowy", "Olive"), "#808000"), (T("Granatowy", "Navy"), "#000080"), (T("Purpurowy", "Purple"), "#800080"),
                  (T("Zielononiebieski", "Teal"), "#008080"), (T("Szary", "Gray"), "#808080"), (T("Srebrny", "Silver"), "#c0c0c0"),
                  (T("Czerwony", "Red"), "#ff0000"), (T("Limonkowy", "Lime"), "#00ff00"), (T("Żółty", "Yellow"), "#ffff00"),
                  (T("Niebieski", "Blue"), "#0000ff"), (T("Fuksja", "Fuchsia"), "#ff00ff"), (T("Akwamaryna", "Aqua"), "#00ffff"),
                  (T("Biały", "White"), "#ffffff")]
        for name, c in colors:
            pm = QPixmap(14, 10)
            pm.fill(QColor(c))
            p = QPainter(pm)
            p.setPen(QColor("#808080"))
            p.drawRect(0, 0, 13, 9)
            p.end()
            m.addAction(QIcon(pm), name, lambda c=c: self._set_color(QColor(c)))
        m.addSeparator()
        m.addAction(T("Inny kolor…", "More colors..."), self._pick_color)
        m.exec(self.b_color.mapToGlobal(QPoint(0, self.b_color.height())))

    def _pick_color(self):
        dlg = HDialog(T("Kolor", "Color"), "wordpad", self)
        cd = QColorDialog(self.text.textColor(), dlg)
        cd.setOption(QColorDialog.DontUseNativeDialog, True)
        cd.setWindowFlags(Qt.Widget)
        QVBoxLayout(dlg.body()).addWidget(cd)
        cd.finished.connect(dlg.done)
        if dlg.exec() == QDialog.Accepted:
            self._set_color(cd.selectedColor())

    def _set_color(self, c):
        f = QTextCharFormat()
        f.setForeground(c)
        self._merge(f)

    def _align(self, a, on=True):
        self.text.setAlignment(a)
        self._cursor_moved()

    def _bullets(self, on=None):
        c = self.text.textCursor()
        lst = c.currentList()
        if on is None:
            on = lst is None
        c.beginEditBlock()
        if on and lst is None:
            lf = QTextListFormat()
            lf.setStyle(QTextListFormat.ListDisc)
            c.createList(lf)
        elif not on and lst is not None:
            start, end = c.selectionStart(), c.selectionEnd()
            b = self.text.document().findBlock(start)
            while b.isValid() and b.position() <= end:
                if b.textList() is not None:
                    b.textList().remove(b)
                    bf = b.blockFormat()
                    bf.setIndent(0)
                    QTextCursor(b).setBlockFormat(bf)
                b = b.next()
        c.endEditBlock()
        self._cursor_moved()

    def _ruler_indents(self, left, first, right):
        c = self.text.textCursor()
        bf = QTextBlockFormat()
        bf.setLeftMargin(left)
        bf.setTextIndent(first)
        bf.setRightMargin(right)
        c.mergeBlockFormat(bf)
        self.text.setFocus()

    def font_dialog(self):
        dlg = HDialog(T("Czcionka", "Font"), "wordpad", self)
        fmt = self.text.currentCharFormat()
        f = fmt.font()
        if not fmt.fontPointSize():
            f.setPointSizeF(self.text.document().defaultFont().pointSizeF())
        fd = QFontDialog(f, dlg)
        fd.setOption(QFontDialog.DontUseNativeDialog, True)
        fd.setWindowFlags(Qt.Widget)
        lay = QVBoxLayout(dlg.body())
        lay.addWidget(fd)
        row = QHBoxLayout()
        row.addWidget(QLabel(T("Kolor:", "Color:")))
        color = QComboBox()
        for name, c in ((T("Automatyczny", "Automatic"), ""), (T("Czarny", "Black"), "#000000"), (T("Czerwony", "Red"), "#ff0000"),
                        (T("Zielony", "Green"), "#008000"), (T("Niebieski", "Blue"), "#0000ff"), (T("Szary", "Gray"), "#808080"),
                        (T("Kasztanowy", "Maroon"), "#800000"), (T("Granatowy", "Navy"), "#000080"), (T("Purpurowy", "Purple"), "#800080")):
            color.addItem(name, c)
        row.addWidget(color)
        row.addStretch(1)
        lay.addLayout(row)
        fd.finished.connect(dlg.done)
        if dlg.exec() == QDialog.Accepted:
            nf = fd.selectedFont()
            cf = QTextCharFormat()
            cf.setFontFamilies([nf.family()])
            cf.setFontPointSize(nf.pointSizeF() if nf.pointSizeF() > 0 else 10)
            cf.setFontWeight(QFont.Bold if nf.bold() else QFont.Normal)
            cf.setFontItalic(nf.italic())
            cf.setFontUnderline(nf.underline())
            cf.setFontStrikeOut(nf.strikeOut())
            if color.currentData():
                cf.setForeground(QColor(color.currentData()))
            self._merge(cf)

    def paragraph_dialog(self):
        c = self.text.textCursor()
        d = ParagraphDialog(self, c.blockFormat())
        if d.exec() == QDialog.Accepted:
            bf = QTextBlockFormat()
            bf.setLeftMargin(d.left.value() * PX_PER_CM)
            bf.setRightMargin(d.right.value() * PX_PER_CM)
            bf.setTextIndent(d.first.value() * PX_PER_CM)
            bf.setAlignment(Qt.Alignment(d.align.currentData()))
            c.mergeBlockFormat(bf)
            self._cursor_moved()

    def tabs_dialog(self):
        c = self.text.textCursor()
        tabs = [t.position for t in c.blockFormat().tabPositions()]
        d = TabsDialog(self, tabs)
        if d.exec() == QDialog.Accepted:
            from PySide6.QtGui import QTextOption as TO
            bf = QTextBlockFormat()
            bf.setTabPositions([TO.Tab(p, TO.LeftTab) for p in d.positions])
            c.mergeBlockFormat(bf)

    # -------------------------------------------------------- wstawianie
    def insert_datetime(self):
        self.text.insertPlainText(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    def insert_datetime_dialog(self):
        now = datetime.datetime.now()
        months = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
                  "października", "listopada", "grudnia"]
        days = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
        fmts = [now.strftime("%Y-%m-%d"), now.strftime("%d.%m.%Y"), now.strftime("%d.%m.%y"),
                f"{now.day} {months[now.month - 1]} {now.year}" if T("pl", "en") == "pl" else now.strftime("%B %d, %Y"),
                f"{days[now.weekday()]}, {now.day} {months[now.month - 1]} {now.year}" if T("pl", "en") == "pl"
                else now.strftime("%A, %B %d, %Y"),
                now.strftime("%H:%M:%S"), now.strftime("%H:%M"), now.strftime("%Y-%m-%d %H:%M")]
        dlg = HDialog(T("Data i godzina", "Date and Time"), "wordpad", self)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel(T("&Dostępne formaty:", "&Available formats:")))
        lst = QListWidget()
        lst.addItems(fmts)
        lst.setCurrentRow(0)
        lst.itemDoubleClicked.connect(lambda *_: dlg.accept())
        lay.addWidget(lst)
        lay.addLayout(_buttons(dlg))
        dlg.resize(280, 300)
        if dlg.exec() == QDialog.Accepted and lst.currentItem():
            self.text.insertPlainText(lst.currentItem().text())

    def insert_picture_dialog(self):
        f = dialogs.open_file(self, T("Wstaw obraz", "Insert Picture"), config.user_dir("PICTURES"),
                              T("Obrazy", "Pictures") + " (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg *.tif *.tiff)")
        if f:
            img = QImage(f)
            if img.isNull():
                dialogs.message(self, "WordPad", T("Nie można odczytać obrazu.", "Cannot read the picture."), "error")
                return
            self.insert_image(img)

    def insert_image(self, img):
        w, h = img.width(), img.height()
        if w > PAGE_TEXT_WIDTH:
            h = h * PAGE_TEXT_WIDTH / w
            w = PAGE_TEXT_WIDTH
        richtext._add_image(self.text.textCursor(), img, w, h)

    def paste_plain(self):
        self.text.insertPlainText(QApplication.clipboard().text())

    # -------------------------------------------------------- szukanie (okno wspólne z Notatnikiem)
    def show_find(self, replace):
        from .notepad import FindDialog
        if self._find_dlg is not None:
            self._find_dlg.close()
        sel = self.text.textCursor().selectedText()
        if sel and " " not in sel:
            self.last_find = sel
        self._find_dlg = FindDialog(self, replace)
        self._find_dlg.show()

    def find_next_or_dialog(self):
        if not self.last_find:
            self.show_find(False)
        else:
            self.find_next()

    def find_next(self):
        flags = QTextDocument.FindFlags()
        if self.last_case:
            flags |= QTextDocument.FindCaseSensitively
        if self.last_up:
            flags |= QTextDocument.FindBackward
        if not self.text.find(self.last_find, flags):
            dialogs.message(self._find_dlg or self, "WordPad",
                            T("WordPad zakończył przeszukiwanie dokumentu.", "WordPad has finished searching the document."), "info")
            return False
        return True

    # -------------------------------------------------------- pliki
    def maybe_save(self):
        if not self.text.document().isModified():
            return True
        ans = dialogs.message(self, "WordPad", T(f"Czy zapisać zmiany w dokumencie {self.display_name()}?",
                                                 f"Save changes to {self.display_name()}?"),
                              "warning", ("yes", "no", "cancel"))
        if ans == "yes":
            return self.save()
        return ans == "no"

    def new(self):
        if not self.maybe_save():
            return
        dlg = HDialog(T("Nowy", "New"), "wordpad", self)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel(T("Nowy &typ dokumentu:", "New document &type:")))
        lst = QListWidget()
        kinds = [k for k in KINDS if k[0] in ("rtf", "docx", "odt", "txt")]
        for k, pl, en, _ in kinds:
            lst.addItem(T(pl, en))
        lst.setCurrentRow(0)
        lst.itemDoubleClicked.connect(lambda *_: dlg.accept())
        lay.addWidget(lst)
        lay.addLayout(_buttons(dlg))
        dlg.resize(300, 230)
        if dlg.exec() != QDialog.Accepted:
            return
        self.kind = kinds[max(0, lst.currentRow())][0]
        config.set("wordpad_default_kind", self.kind)
        self.text.clear()
        self.path = None
        self.text.document().setModified(False)
        self._update_title()

    def open_dialog(self):
        if not self.maybe_save():
            return
        start = os.path.dirname(self.path) if self.path else config.user_dir("DOCUMENTS")
        f = dialogs.open_file(self, T("Otwórz", "Open"), start, open_filter())
        if f:
            self.load(f)

    def load(self, path):
        if not os.path.exists(path):
            dialogs.message(self, "WordPad", T(f"Nie można odnaleźć pliku {path}.", f"Cannot find {path}."), "error")
            return False
        doc = self.text.document()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            kind = richtext.detect(path)
            if kind == "doc":
                kind = self._load_doc(path, doc)
                if kind is None:
                    return False
            else:
                richtext.load(path, doc)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            dialogs.message(self, "WordPad", T(f"Nie można otworzyć dokumentu {os.path.basename(path)}.\n\n{e}",
                                               f"Cannot open {os.path.basename(path)}.\n\n{e}"), "error")
            return False
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
        self.kind = kind if kind in ("rtf", "docx", "odt", "html", "txt") else "rtf"
        self.path = os.path.abspath(path) if kind != "doc-converted" else None
        if kind == "doc-converted":
            self.kind = "docx"
        doc.setModified(False)
        self.text.moveCursor(QTextCursor.Start)
        self._update_title()
        if self.path:
            self._remember(self.path)
            from ..common.launcher import add_recent_document
            add_recent_document(self.path)
        return True

    def _load_doc(self, path, doc):
        """Stary format Word (.doc) — konwersja przez LibreOffice, jeśli jest zainstalowany."""
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            dialogs.message(self, "WordPad", T("Pliki w starym formacie Word (.doc) można otworzyć po zainstalowaniu "
                                               "pakietu LibreOffice (Panel sterowania → Dodaj lub usuń programy).",
                                               "Old Word (.doc) files can be opened after installing LibreOffice."), "info")
            return None
        tmp = tempfile.mkdtemp(prefix="wordpad-")
        r = subprocess.run([soffice, "--headless", "--convert-to", "docx", "--outdir", tmp, path],
                           capture_output=True, timeout=120)
        out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".docx")
        if r.returncode != 0 or not os.path.exists(out):
            raise OSError(T("konwersja nie powiodła się", "conversion failed"))
        richtext.docx_to_document(out, doc)
        shutil.rmtree(tmp, ignore_errors=True)
        dialogs.message(self, "WordPad", T("Dokument w starym formacie Word został otwarty. Zapisz go w formacie DOCX, RTF lub ODT.",
                                           "The old Word document was opened. Save it as DOCX, RTF or ODT."), "info")
        return "doc-converted"

    def save(self):
        if not self.path:
            return self.save_as()
        return self._write(self.path, self.kind)

    def save_as(self):
        start_dir = os.path.dirname(self.path) if self.path else config.user_dir("DOCUMENTS")
        ext = {"rtf": ".rtf", "docx": ".docx", "odt": ".odt", "html": ".html"}.get(self.kind, ".txt")
        name = os.path.splitext(os.path.basename(self.path))[0] if self.path else T("Dokument", "Document")
        # filtr odpowiadający bieżącemu typowi na początku listy
        order = sorted(KINDS, key=lambda k: k[0] != self.kind)
        flt = ";;".join(f"{T(pl, en)} ({pat})" for _k, pl, en, pat in order)
        f, chosen = dialogs.save_file(self, T("Zapisz jako", "Save As"), start_dir, flt, name + ext)
        if not f:
            return False
        kind = next((k for k, pl, en, _ in KINDS if chosen.startswith(T(pl, en))), None) or kind_for_ext(f) or "rtf"
        want_ext = {"rtf": ".rtf", "docx": ".docx", "odt": ".odt", "html": ".html", "txt": ".txt", "txt-ansi": ".txt"}[kind]
        if not os.path.splitext(f)[1]:
            f += want_ext
        if kind in ("txt", "txt-ansi") and self._has_formatting():
            ans = dialogs.message(self, "WordPad", T("Zapisujesz dokument w formacie tekstowym. Całe formatowanie "
                                                     "zostanie usunięte. Kontynuować?",
                                                     "You are about to save the document in a Text-Only format, which "
                                                     "will remove all formatting. Continue?"), "warning", ("yes", "no"))
            if ans != "yes":
                return False
        return self._write(f, kind)

    def _has_formatting(self):
        b = self.text.document().begin()
        while b.isValid():
            if b.textList() is not None:
                return True
            it = b.begin()
            while not it.atEnd():
                cf = it.fragment().charFormat()
                if cf.isImageFormat() or cf.fontWeight() >= QFont.DemiBold or cf.fontItalic() or cf.fontUnderline():
                    return True
                it += 1
            b = b.next()
        return False

    def _write(self, path, kind):
        try:
            richtext.save(self.text.document(), path, kind)
        except Exception as e:
            dialogs.message(self, "WordPad", T(f"Nie można zapisać dokumentu {path}.\n\n{e}", f"Cannot save {path}.\n\n{e}"), "error")
            return False
        self.path = os.path.abspath(path)
        self.kind = "txt" if kind == "txt-ansi" else kind
        self.text.document().setModified(False)
        self._update_title()
        self._remember(self.path)
        return True

    # -------------------------------------------------------- drukowanie
    def _get_printer(self):
        if self._printer is None:
            from PySide6.QtPrintSupport import QPrinter
            self._printer = QPrinter()
            self._printer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                                    QMarginsF(31.7, 25.4, 31.7, 25.4),
                                                    QPageLayout.Millimeter))
        return self._printer

    def page_setup(self):
        from PySide6.QtPrintSupport import QPageSetupDialog
        QPageSetupDialog(self._get_printer(), self).exec()

    def print_doc(self):
        from PySide6.QtPrintSupport import QPrintDialog
        p = self._get_printer()
        if QPrintDialog(p, self).exec() == QDialog.Accepted:
            self.text.document().print_(p)

    def preview(self):
        from PySide6.QtPrintSupport import QPrintPreviewWidget
        dlg = HDialog(T("Podgląd wydruku", "Print Preview"), "wordpad", self, resizable=True)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        pw = QPrintPreviewWidget(self._get_printer())
        pw.paintRequested.connect(lambda pr: self.text.document().print_(pr))
        for text, fn in ((T("&Drukuj…", "&Print..."), lambda: (dlg.accept(), self.print_doc())),
                         (T("&Następna strona", "&Next Page"), lambda: pw.setCurrentPage(pw.currentPage() + 1)),
                         (T("&Poprzednia strona", "Pre&v Page"), lambda: pw.setCurrentPage(pw.currentPage() - 1)),
                         (T("&Dwie strony", "&Two Page"), lambda: pw.setViewMode(QPrintPreviewWidget.FacingPagesView)),
                         (T("Po&większ", "Zoom &In"), lambda: pw.zoomIn()), (T("Po&mniejsz", "Zoom &Out"), lambda: pw.zoomOut()),
                         (T("&Zamknij", "&Close"), dlg.reject)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        lay.addWidget(pw, 1)
        dlg.resize(820, 640)
        dlg.exec()

    # -------------------------------------------------------- zdarzenia
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls and self.maybe_save():
            self.load(urls[0])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.ruler.update()

    def closeEvent(self, e):
        if self.maybe_save():
            if self._find_dlg is not None:
                self._find_dlg.close()
            e.accept()
            super().closeEvent(e)
        else:
            e.ignore()


class WordPadApp:
    def __init__(self):
        self.windows = []

    def handle(self, args):
        files = [a for a in args if a and not a.startswith("-")] or [None]
        for f in files:
            w = WordPadWindow(self, f)
            n = len(self.windows)
            w.move(60 + 26 * (n % 8), 40 + 26 * (n % 8))
            w.show()
            w.raise_()
            w.activateWindow()
            self.windows.append(w)
            w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)


def main(args):
    return run_app("wordpad", WordPadApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
