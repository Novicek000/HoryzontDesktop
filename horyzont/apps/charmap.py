"""Mapa znaków — przeglądanie znaków czcionki, wyszukiwanie po nazwie, kopiowanie do schowka."""
import sys
import unicodedata

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QRawFont
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QCheckBox, QComboBox, QFontComboBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStatusBar, QVBoxLayout,
                               QWidget)

from .. import config
from ..common.appkit import T, run_app
from ..common.window import HWindow

COLS = 20

# Podzakresy Unicode: (polska nazwa, angielska nazwa, początek, koniec)
BLOCKS = [
    ("Łaciński podstawowy", "Basic Latin", 0x20, 0x7F),
    ("Łaciński-1 uzupełnienie", "Latin-1 Supplement", 0xA0, 0xFF),
    ("Łaciński rozszerzony-A (polskie litery)", "Latin Extended-A", 0x100, 0x17F),
    ("Łaciński rozszerzony-B", "Latin Extended-B", 0x180, 0x24F),
    ("Rozszerzenia IPA", "IPA Extensions", 0x250, 0x2AF),
    ("Litery modyfikujące", "Spacing Modifier Letters", 0x2B0, 0x2FF),
    ("Znaki diakrytyczne", "Combining Diacritical Marks", 0x300, 0x36F),
    ("Grecki", "Greek and Coptic", 0x370, 0x3FF),
    ("Cyrylica", "Cyrillic", 0x400, 0x52F),
    ("Ormiański", "Armenian", 0x530, 0x58F),
    ("Hebrajski", "Hebrew", 0x590, 0x5FF),
    ("Arabski", "Arabic", 0x600, 0x6FF),
    ("Dewanagari", "Devanagari", 0x900, 0x97F),
    ("Tajski", "Thai", 0xE00, 0xE7F),
    ("Gruziński", "Georgian", 0x10A0, 0x10FF),
    ("Łaciński rozszerzony dodatkowy", "Latin Extended Additional", 0x1E00, 0x1EFF),
    ("Grecki rozszerzony", "Greek Extended", 0x1F00, 0x1FFF),
    ("Interpunkcja ogólna", "General Punctuation", 0x2000, 0x206F),
    ("Indeksy górne i dolne", "Superscripts and Subscripts", 0x2070, 0x209F),
    ("Symbole walut", "Currency Symbols", 0x20A0, 0x20CF),
    ("Symbole literopodobne", "Letterlike Symbols", 0x2100, 0x214F),
    ("Liczby", "Number Forms", 0x2150, 0x218F),
    ("Strzałki", "Arrows", 0x2190, 0x21FF),
    ("Operatory matematyczne", "Mathematical Operators", 0x2200, 0x22FF),
    ("Różne symbole techniczne", "Miscellaneous Technical", 0x2300, 0x23FF),
    ("Znaki w kółkach", "Enclosed Alphanumerics", 0x2460, 0x24FF),
    ("Ramki", "Box Drawing", 0x2500, 0x257F),
    ("Bloki", "Block Elements", 0x2580, 0x259F),
    ("Kształty geometryczne", "Geometric Shapes", 0x25A0, 0x25FF),
    ("Różne symbole", "Miscellaneous Symbols", 0x2600, 0x26FF),
    ("Dingbaty", "Dingbats", 0x2700, 0x27BF),
    ("Strzałki dodatkowe", "Supplemental Arrows", 0x2900, 0x297F),
    ("Interpunkcja CJK", "CJK Symbols and Punctuation", 0x3000, 0x303F),
    ("Hiragana", "Hiragana", 0x3040, 0x309F),
    ("Katakana", "Katakana", 0x30A0, 0x30FF),
    ("Ideogramy CJK", "CJK Unified Ideographs", 0x4E00, 0x9FFF),
    ("Hangul", "Hangul Syllables", 0xAC00, 0xD7AF),
    ("Obszar prywatny", "Private Use Area", 0xE000, 0xF8FF),
    ("Formy prezentacyjne", "Alphabetic Presentation Forms", 0xFB00, 0xFB4F),
    ("Formy pełnej szerokości", "Halfwidth and Fullwidth Forms", 0xFF00, 0xFFEF),
    ("Symbole matematyczne alfanumeryczne", "Mathematical Alphanumeric Symbols", 0x1D400, 0x1D7FF),
    ("Karty do gry, domino, mahjong", "Playing Cards and Tiles", 0x1F000, 0x1F0FF),
    ("Emoji i piktogramy", "Emoji and Pictographs", 0x1F300, 0x1F6FF),
    ("Emoji dodatkowe", "Supplemental Symbols and Pictographs", 0x1F900, 0x1FAFF),
]

SCAN_RANGES = [(0x20, 0x2FFF), (0x3000, 0xD7FF), (0xE000, 0xFFFD), (0x1D400, 0x1D7FF), (0x1F000, 0x1FAFF)]


def char_name(cp):
    try:
        return unicodedata.name(chr(cp)).title()
    except ValueError:
        if 0x4E00 <= cp <= 0x9FFF:
            return "CJK Unified Ideograph"
        if 0xE000 <= cp <= 0xF8FF:
            return T("Znak użytkownika", "Private Use Character")
        return T("Znak bez nazwy", "Unnamed character")


def alt_code(cp):
    """Kod Alt+0nnn w stronie kodowej cp1250 (jak w klasycznej Mapie znaków), o ile istnieje."""
    try:
        b = chr(cp).encode("cp1250")
        if len(b) == 1 and b[0] >= 0x80:
            return f"Alt+0{b[0]}"
    except UnicodeEncodeError:
        pass
    return ""


class CharGrid(QAbstractScrollArea):
    current_changed = Signal(int)
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.chars = []
        self.index = 0
        self.font_ = QFont()
        self.cell = 22
        self._pressed = False
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setFrameShape(QFrame.StyledPanel)
        self.viewport().setMouseTracking(True)

    def sizeHint(self):
        return QSize(COLS * self.cell + self.verticalScrollBar().sizeHint().width() + 4, 10 * self.cell + 4)

    def set_chars(self, chars, font):
        cur = self.chars[self.index] if self.chars and self.index < len(self.chars) else None
        self.chars = chars
        self.font_ = QFont(font)
        self.font_.setPixelSize(15)
        self.index = chars.index(cur) if cur in chars else 0
        self._update_scroll()
        self.ensure_visible()
        self.viewport().update()
        if chars:
            self.current_changed.emit(chars[self.index])

    def rows(self):
        return (len(self.chars) + COLS - 1) // COLS

    def visible_rows(self):
        return max(1, self.viewport().height() // self.cell)

    def _update_scroll(self):
        sb = self.verticalScrollBar()
        sb.setRange(0, max(0, self.rows() - self.visible_rows()))
        sb.setPageStep(self.visible_rows())
        sb.setSingleStep(1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_scroll()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()

    def ensure_visible(self):
        row = self.index // COLS
        sb = self.verticalScrollBar()
        if row < sb.value():
            sb.setValue(row)
        elif row >= sb.value() + self.visible_rows():
            sb.setValue(row - self.visible_rows() + 1)

    def set_index(self, i):
        if not self.chars:
            return
        i = max(0, min(len(self.chars) - 1, i))
        self.index = i
        self.ensure_visible()
        self.viewport().update()
        self.current_changed.emit(self.chars[i])

    def select_cp(self, cp):
        if cp in self.chars:
            self.set_index(self.chars.index(cp))
            return True
        return False

    def _index_at(self, pos):
        c = pos.x() // self.cell
        r = pos.y() // self.cell + self.verticalScrollBar().value()
        if c >= COLS:
            return -1
        i = r * COLS + c
        return i if 0 <= i < len(self.chars) else -1

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), QColor("#ffffff"))
        p.setFont(self.font_)
        first = self.verticalScrollBar().value()
        rows = self.visible_rows() + 1
        grid = QPen(QColor("#9a9a9a"))
        for r in range(rows):
            for c in range(COLS):
                i = (first + r) * COLS + c
                rect = QRect(c * self.cell, r * self.cell, self.cell, self.cell)
                p.setPen(grid)
                p.drawRect(rect.adjusted(0, 0, 0, 0))
                if i >= len(self.chars):
                    continue
                sel = i == self.index
                if sel:
                    p.fillRect(rect.adjusted(1, 1, 0, 0), self.palette().highlight())
                    p.setPen(self.palette().highlightedText().color())
                else:
                    p.setPen(QColor("#000000"))
                p.drawText(rect, Qt.AlignCenter, chr(self.chars[i]))
        # powiększony podgląd przytrzymanego znaku
        if self._pressed and self.chars:
            r = (self.index // COLS) - first
            c = self.index % COLS
            if 0 <= r <= rows:
                big = QRect(0, 0, self.cell * 2 + 8, self.cell * 2 + 8)
                big.moveCenter(QRect(c * self.cell, r * self.cell, self.cell, self.cell).center())
                vr = self.viewport().rect()
                big.moveLeft(max(0, min(vr.width() - big.width() - 1, big.left())))
                big.moveTop(max(0, min(vr.height() - big.height() - 1, big.top())))
                p.fillRect(big, QColor("#ffffff"))
                p.setPen(QPen(QColor("#000000"), 2))
                p.drawRect(big.adjusted(1, 1, -1, -1))
                f = QFont(self.font_)
                f.setPixelSize(34)
                p.setFont(f)
                p.drawText(big, Qt.AlignCenter, chr(self.chars[self.index]))

    def mousePressEvent(self, e):
        i = self._index_at(e.position().toPoint())
        if i >= 0 and e.button() == Qt.LeftButton:
            self._pressed = True
            self.set_index(i)

    def mouseMoveEvent(self, e):
        if self._pressed:
            i = self._index_at(e.position().toPoint())
            if i >= 0 and i != self.index:
                self.set_index(i)

    def mouseReleaseEvent(self, e):
        self._pressed = False
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        i = self._index_at(e.position().toPoint())
        if i >= 0:
            self.activated.emit(self.chars[i])

    def wheelEvent(self, e):
        sb = self.verticalScrollBar()
        sb.setValue(sb.value() - e.angleDelta().y() // 40)

    def keyPressEvent(self, e):
        k = e.key()
        moves = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -COLS, Qt.Key_Down: COLS,
                 Qt.Key_PageUp: -COLS * self.visible_rows(), Qt.Key_PageDown: COLS * self.visible_rows()}
        if k in moves:
            self.set_index(self.index + moves[k])
        elif k == Qt.Key_Home:
            self.set_index(0)
        elif k == Qt.Key_End:
            self.set_index(len(self.chars) - 1)
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.chars:
                self.activated.emit(self.chars[self.index])
        elif e.text() and e.text().isprintable():
            if not self.select_cp(ord(e.text()[0])):
                super().keyPressEvent(e)
        else:
            super().keyPressEvent(e)


class CharmapWindow(HWindow):
    def __init__(self):
        super().__init__(T("Mapa znaków", "Character Map"), "charmap", resizable=False, maximizable=False)
        self._supported = {}
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(8, 8, 8, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        fl = QLabel(T("&Czcionka:", "&Font:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setMinimumWidth(300)
        fl.setBuddy(self.font_combo)
        top.addWidget(fl)
        top.addWidget(self.font_combo, 1)
        hb = QPushButton(T("Pomo&c", "&Help"))
        hb.clicked.connect(lambda: __import__("horyzont.common.launcher", fromlist=["x"]).start_builtin(
            "explorer", ["horyzont:help:charmap"]))
        top.addWidget(hb)
        lay.addLayout(top)
        self.grid = CharGrid()
        lay.addWidget(self.grid, 1)
        row = QHBoxLayout()
        cl = QLabel(T("Znaki do s&kopiowania:", "Characters to c&opy:"))
        self.to_copy = QLineEdit()
        cl.setBuddy(self.to_copy)
        row.addWidget(cl)
        row.addWidget(self.to_copy, 1)
        sel = QPushButton(T("&Wybierz", "&Select"))
        sel.clicked.connect(lambda: self.add_char(self.grid.chars[self.grid.index]) if self.grid.chars else None)
        row.addWidget(sel)
        self.copy_btn = QPushButton(T("Ko&piuj", "&Copy"))
        self.copy_btn.clicked.connect(self.copy)
        row.addWidget(self.copy_btn)
        lay.addLayout(row)
        self.advanced = QCheckBox(T("Widok z&aawansowany", "Ad&vanced view"))
        lay.addWidget(self.advanced)
        self.adv = QWidget()
        g = QGridLayout(self.adv)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(QLabel(T("Zestaw znaków:", "Character set:")), 0, 0)
        cs = QComboBox()
        cs.addItem("Unicode")
        cs.setEnabled(False)
        g.addWidget(cs, 0, 1)
        g.addWidget(QLabel(T("Przejdź do Unicode:", "Go to Unicode:")), 0, 2)
        self.goto = QLineEdit()
        self.goto.setPlaceholderText("U+0105")
        self.goto.setMaximumWidth(90)
        self.goto.returnPressed.connect(self._goto)
        g.addWidget(self.goto, 0, 3)
        g.addWidget(QLabel(T("Grupuj według:", "Group by:")), 1, 0)
        self.group = QComboBox()
        self.group.addItem(T("Wszystkie", "All"), -1)
        for i, b in enumerate(BLOCKS):
            self.group.addItem(T(b[0], b[1]), i)
        g.addWidget(self.group, 1, 1, 1, 3)
        sl = QLabel(T("Wy&szukaj:", "S&earch for:"))
        g.addWidget(sl, 2, 0)
        self.search = QLineEdit()
        sl.setBuddy(self.search)
        self.search.setPlaceholderText(T("np. ogonek, arrow, euro", "e.g. arrow, euro"))
        self.search.returnPressed.connect(self.refill)
        g.addWidget(self.search, 2, 1, 1, 2)
        sb = QPushButton(T("&Szukaj", "Sea&rch"))
        sb.clicked.connect(self.refill)
        g.addWidget(sb, 2, 3)
        g.setColumnStretch(1, 1)
        lay.addWidget(self.adv)
        self.status = QStatusBar()
        self.status_label = QLabel()
        self.status.addWidget(self.status_label, 1)
        self.key_label = QLabel()
        self.status.addPermanentWidget(self.key_label)
        lay.addWidget(self.status)
        self.advanced.toggled.connect(self._toggle_adv)
        self.font_combo.currentFontChanged.connect(lambda f: self.refill())
        self.group.currentIndexChanged.connect(lambda *_: self.refill())
        self.grid.current_changed.connect(self._show_status)
        self.grid.activated.connect(self.add_char)
        self.to_copy.textChanged.connect(lambda t: self.copy_btn.setEnabled(bool(t)))
        self.copy_btn.setEnabled(False)
        fam = config.get("charmap_font", "")
        if fam and fam in QFontDatabase.families():
            self.font_combo.setCurrentFont(QFont(fam))
        self.advanced.setChecked(bool(config.get("charmap_advanced", False)))
        self._toggle_adv(self.advanced.isChecked())
        self.refill()

    def _toggle_adv(self, on):
        self.adv.setVisible(on)
        config.set("charmap_advanced", on)
        QTimer.singleShot(0, lambda: self.setFixedSize(self.sizeHint()))

    def supported(self, font):
        key = font.family()
        if key in self._supported:
            return self._supported[key]
        raw = QRawFont.fromFont(font)
        out = []
        for a, b in SCAN_RANGES:
            for cp in range(a, b + 1):
                if 0xD800 <= cp <= 0xDFFF:
                    continue
                if raw.supportsCharacter(cp):
                    cat = unicodedata.category(chr(cp))
                    if cat in ("Cc", "Cs") or (cat == "Cn" and not (0xE000 <= cp <= 0xF8FF)):
                        continue
                    out.append(cp)
        self._supported[key] = out
        return out

    def refill(self):
        font = self.font_combo.currentFont()
        config.set("charmap_font", font.family())
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            chars = self.supported(font)
            if self.advanced.isChecked():
                gi = self.group.currentData()
                if gi is not None and gi >= 0:
                    _, _, a, b = BLOCKS[gi]
                    chars = [c for c in chars if a <= c <= b]
                q = self.search.text().strip().lower()
                if q:
                    words = q.split()
                    chars = [c for c in chars if all(w in char_name(c).lower() for w in words)]
            self.grid.set_chars(chars, font)
        finally:
            QApplication.restoreOverrideCursor()
        if not chars:
            self.status_label.setText(T("Brak znaków spełniających kryteria.", "No characters match."))

    def _goto(self):
        t = self.goto.text().strip().upper().replace("U+", "")
        try:
            cp = int(t, 16)
        except ValueError:
            return
        if not self.grid.select_cp(cp):
            self.status_label.setText(T("Tego znaku nie ma w wybranej czcionce.", "This character is not in the font."))

    def _show_status(self, cp):
        self.status_label.setText(f"U+{cp:04X}: {char_name(cp)}")
        a = alt_code(cp)
        self.key_label.setText(T("Klawisze: ", "Keystroke: ") + a if a else "")

    def add_char(self, cp):
        self.to_copy.insert(chr(cp))

    def copy(self):
        t = self.to_copy.selectedText() or self.to_copy.text()
        QApplication.clipboard().setText(t)


class CharmapApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = CharmapWindow()
            self.win.move(140, 80)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    return run_app("charmap", CharmapApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
