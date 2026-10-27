"""Kalkulator — widok standardowy i naukowy (systemy liczbowe, trygonometria, nawiasy, statystyka, pamięć)."""
import decimal
import math
import sys
from decimal import Decimal

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMenuBar, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from .. import config
from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow

decimal.getcontext().prec = 34
DIGITS_MAX = 32
RED, BLUE, PURPLE = "#c00000", "#0000c8", "#7a2b8f"

# priorytety operatorów (widok naukowy liczy z kolejnością działań, standardowy — od lewej do prawej)
PREC = {"or": 1, "xor": 2, "and": 3, "lsh": 4, "rsh": 4, "+": 5, "-": 5, "*": 6, "/": 6, "mod": 6, "pow": 7, "root": 7}
WORD_BITS = {"qword": 64, "dword": 32, "word": 16, "byte": 8}


class CalcError(Exception):
    pass


def dec_point():
    return QLocale().decimalPoint() or ","


def group_sep():
    s = QLocale().groupSeparator() or " "
    return " " if s in ("\xa0", " ") else s


class Engine:
    """Logika kalkulatora niezależna od okna (łatwa do testów)."""

    def __init__(self):
        self.precedence = False
        self.base = 10
        self.word = "qword"
        self.angle = "deg"
        self.fe = False
        self.memory = Decimal(0)
        self.stats = []
        self.reset()

    def reset(self):
        self.entry = "0"          # wpisywana liczba (jako tekst w bieżącym systemie)
        self.value = Decimal(0)
        self.typing = False       # czy użytkownik wpisuje teraz cyfry
        self.levels = [[]]        # stos poziomów nawiasów: lista (wartość, operator)
        self.last_op = None       # do powtarzania „=”
        self.error = None
        self.exp_mode = False

    # -------------------------------------------------------- wartość bieżąca
    def current(self):
        if self.typing:
            return self.parse(self.entry)
        return self.value

    def parse(self, s):
        if self.base != 10:
            v = int(s or "0", self.base)
            return Decimal(self._signed(v))
        s = s.replace(dec_point(), ".")
        if s.endswith("e+") or s.endswith("e-") or s.endswith("e"):
            s = s.rstrip("e+-")
        try:
            return Decimal(s or "0")
        except decimal.InvalidOperation:
            return Decimal(0)

    def _mask(self, v):
        bits = WORD_BITS[self.word]
        return int(v) & ((1 << bits) - 1)

    def _signed(self, v):
        bits = WORD_BITS[self.word]
        v &= (1 << bits) - 1
        return v - (1 << bits) if v >> (bits - 1) else v

    def set_value(self, v):
        if isinstance(v, (int, float)):
            v = Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
        if not v.is_finite():
            raise CalcError(T("Nieprawidłowe dane wejściowe dla funkcji.", "Invalid input for function."))
        if abs(v) >= Decimal("1e10000"):
            raise CalcError(T("Przepełnienie.", "Overflow."))
        if self.base != 10:
            v = Decimal(self._signed(int(v)))
        self.value = v
        self.typing = False
        self.exp_mode = False

    # -------------------------------------------------------- wyświetlanie
    def display(self, grouping=False):
        if self.error:
            return self.error
        if self.typing:
            s = self.entry
            if self.base == 10 and dec_point() not in s and "e" not in s:
                s += dec_point()
            return self._group(s, grouping)
        return self._group(self.format(self.value), grouping)

    def format(self, v):
        if self.base != 10:
            n = self._mask(int(v))
            digits = "0123456789ABCDEF"
            if n == 0:
                return "0"
            out = ""
            while n:
                out = digits[n % self.base] + out
                n //= self.base
            return out
        if v == 0:
            return "0" + dec_point()
        v = +v
        a = abs(v)
        if self.fe or a >= Decimal(10) ** DIGITS_MAX or (a < Decimal("1e-31")):
            s = f"{v:.{DIGITS_MAX - 1}e}"
            mant, ex = s.split("e")
            mant = mant.rstrip("0").rstrip(".") if "." in mant else mant
            if "." not in mant:
                mant += "."
            e = int(ex)
            return mant.replace(".", dec_point()) + ("e+" if e >= 0 else "e-") + str(abs(e))
        q = v.quantize(Decimal(1).scaleb(-(DIGITS_MAX - len(str(int(a))) if a >= 1 else DIGITS_MAX)),
                       rounding=decimal.ROUND_HALF_EVEN) if a < Decimal(10) ** DIGITS_MAX else v
        s = format(q.normalize(), "f")
        if "." in s:
            s = s.rstrip("0")
            if s.endswith("."):
                s = s[:-1]
        if "." not in s:
            s += "."
        return s.replace(".", dec_point())

    def _group(self, s, on):
        if not on or "e" in s:
            return s
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if self.base == 10:
            ip, _, fp = s.partition(dec_point())
            n = 3
            sep = group_sep()
            has_point = dec_point() in s
        else:
            ip, fp, has_point = s, "", False
            n = 4 if self.base in (2, 16) else 3
            sep = " "
        parts = []
        while len(ip) > n:
            parts.insert(0, ip[-n:])
            ip = ip[:-n]
        parts.insert(0, ip)
        out = sep.join(parts) + (dec_point() + fp if has_point else "")
        return ("-" if neg else "") + out

    # -------------------------------------------------------- wpisywanie
    def digit(self, d):
        self.error = None
        if not self.typing:
            self.entry = "0"
            self.typing = True
        if self.base != 10:
            if int(d, 16) >= self.base:
                return
            cand = (self.entry.lstrip("0") + d) or "0"
            if int(cand, self.base) >> WORD_BITS[self.word]:
                return
            self.entry = cand
            return
        digits = sum(c.isdigit() for c in self.entry.split("e")[0])
        if self.exp_mode:
            mant, _, ex = self.entry.partition("e")
            sign, num = ex[:1], ex[1:]
            num = (num + d).lstrip("0") or "0"
            if len(num) > 4:
                return
            self.entry = f"{mant}e{sign}{num}"
            return
        if digits >= DIGITS_MAX:
            return
        if self.entry in ("0", "-0"):
            self.entry = self.entry[:-1] + d
        else:
            self.entry += d

    def point(self):
        if self.base != 10 or self.exp_mode:
            return
        if not self.typing:
            self.entry = "0"
            self.typing = True
        if dec_point() not in self.entry:
            self.entry += dec_point()

    def exp(self):
        if self.base != 10:
            return
        if not self.typing:
            self.entry = self.format(self.value).rstrip(dec_point())
            self.typing = True
        if "e" not in self.entry:
            self.entry += "e+0"
            self.exp_mode = True

    def backspace(self):
        if not self.typing:
            return
        if self.exp_mode and self.entry.endswith("e+0"):
            self.entry = self.entry[:-3]
            self.exp_mode = False
        else:
            self.entry = self.entry[:-1]
        if self.entry in ("", "-"):
            self.entry = "0"

    def negate(self):
        if self.typing:
            if self.exp_mode:
                mant, _, ex = self.entry.partition("e")
                self.entry = f"{mant}e{'-' if ex.startswith('+') else '+'}{ex[1:]}"
            elif self.base == 10:
                self.entry = self.entry[1:] if self.entry.startswith("-") else "-" + self.entry
            else:
                self.set_value(-self.current())
                self.typing = False
        else:
            self.set_value(-self.value)

    def clear_entry(self):
        self.error = None
        self.entry = "0"
        self.typing = True
        self.exp_mode = False

    # -------------------------------------------------------- działania
    def _apply(self, a, op, b):
        try:
            if op == "+":
                r = a + b
            elif op == "-":
                r = a - b
            elif op == "*":
                r = a * b
            elif op == "/":
                if b == 0:
                    raise CalcError(T("Nie można dzielić przez zero.", "Cannot divide by zero."))
                r = a / b
                if self.base != 10:
                    r = Decimal(int(a / b))
            elif op == "mod":
                if b == 0:
                    raise CalcError(T("Nie można dzielić przez zero.", "Cannot divide by zero."))
                r = a % b if self.base == 10 else Decimal(int(math.fmod(int(a), int(b))))
            elif op == "pow":
                r = self._pow(a, b)
            elif op == "root":
                if b == 0:
                    raise CalcError(T("Nieprawidłowe dane wejściowe dla funkcji.", "Invalid input for function."))
                r = self._pow(a, Decimal(1) / b)
            elif op in ("and", "or", "xor", "lsh", "rsh"):
                x, y = int(a), int(b)
                r = {"and": x & y, "or": x | y, "xor": x ^ y,
                     "lsh": x << max(0, min(y, 4096)), "rsh": x >> max(0, y)}[op]
                r = Decimal(r)
            else:
                r = b
        except (decimal.InvalidOperation, OverflowError, ValueError):
            raise CalcError(T("Nieprawidłowe dane wejściowe dla funkcji.", "Invalid input for function."))
        if self.base != 10:
            r = Decimal(self._signed(int(r)))
        return r

    def _pow(self, a, b):
        if b == b.to_integral_value() and abs(b) < 10000:
            return a ** int(b)
        if a < 0:
            # pierwiastek nieparzystego stopnia z liczby ujemnej
            inv = Decimal(1) / b if b != 0 else Decimal(0)
            if inv == inv.to_integral_value() and int(inv) % 2 == 1:
                return -Decimal(repr(math.pow(float(-a), float(b))))
            raise CalcError(T("Nieprawidłowe dane wejściowe dla funkcji.", "Invalid input for function."))
        return Decimal(f"{math.pow(float(a), float(b)):.15g}")

    def _reduce(self, level, min_prec):
        """Wylicza oczekujące działania o priorytecie >= min_prec; zwraca nową wartość bieżącą."""
        v = self.current()
        while level and (PREC[level[-1][1]] >= min_prec):
            a, op = level.pop()
            v = self._apply(a, op, v)
        return v

    def operator(self, op):
        try:
            level = self.levels[-1]
            if not self.typing and level and self._just_op:
                # zmiana operatora bez wpisania liczby
                level[-1] = (level[-1][0], op)
                return
            if self.precedence:
                v = self._reduce(level, PREC[op])
            else:
                v = self._reduce(level, 0)
            self.set_value(v)
            level.append((v, op))
            self._just_op = True
            self.last_op = None
        except CalcError as e:
            self._fail(e)

    _just_op = False

    def _mark_input(self):
        self._just_op = False

    def equals(self):
        try:
            if self.last_op and not self.typing and not any(self.levels):
                op, b = self.last_op
                self.set_value(self._apply(self.value, op, b))
                return
            v = self.current()
            last = None
            for level in reversed(self.levels):
                while level:
                    a, op = level.pop()
                    if last is None:
                        last = (op, v)
                    v = self._apply(a, op, v)
            self.levels = [[]]
            self.set_value(v)
            self.last_op = last
            self._just_op = False
        except CalcError as e:
            self._fail(e)

    def paren_open(self):
        if len(self.levels) >= 25:
            return
        self.levels.append([])
        self.typing = False
        self.value = Decimal(0)
        self.entry = "0"
        self._just_op = False

    def paren_close(self):
        if len(self.levels) <= 1:
            return
        try:
            v = self._reduce(self.levels[-1], 0)
            self.levels.pop()
            self.set_value(v)
            self._just_op = False
        except CalcError as e:
            self._fail(e)

    def depth(self):
        return len(self.levels) - 1

    def percent(self):
        level = self.levels[-1]
        x = level[-1][0] if level else Decimal(0)
        try:
            self.set_value(x * self.current() / 100)
        except CalcError as e:
            self._fail(e)

    def _fail(self, e):
        self.error = str(e)
        self.levels = [[]]
        self.typing = False
        self.value = Decimal(0)
        self.last_op = None

    # -------------------------------------------------------- funkcje
    def _to_rad(self, x):
        return {"deg": math.radians(x), "rad": x, "grad": x * math.pi / 200}[self.angle]

    def _from_rad(self, x):
        return {"deg": math.degrees(x), "rad": x, "grad": x * 200 / math.pi}[self.angle]

    def func(self, name, inv=False, hyp=False):
        x = self.current()
        try:
            fx = float(x)
            if name == "sqrt":
                if x < 0:
                    raise ValueError
                r = x.sqrt()
            elif name == "recip":
                if x == 0:
                    raise CalcError(T("Nie można dzielić przez zero.", "Cannot divide by zero."))
                r = Decimal(1) / x
            elif name in ("sin", "cos", "tan"):
                if hyp:
                    f = {"sin": (math.sinh, math.asinh), "cos": (math.cosh, math.acosh), "tan": (math.tanh, math.atanh)}[name]
                    r = f[1](fx) if inv else f[0](fx)
                elif inv:
                    r = self._from_rad({"sin": math.asin, "cos": math.acos, "tan": math.atan}[name](fx))
                else:
                    a = self._to_rad(fx)
                    if name == "tan" and abs(math.cos(a)) < 1e-15:
                        raise ValueError
                    r = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](a)
                    # dokładne zera dla kątów typu 180°
                    if abs(r) < 1e-15:
                        r = 0.0
                r = Decimal(f"{r:.15g}")
            elif name == "ln":
                r = x.exp() if inv else x.ln()
            elif name == "log":
                r = Decimal(10) ** x if inv else x.log10()
            elif name == "sq":
                r = x.sqrt() if inv else x * x
            elif name == "cube":
                r = self._pow(x, Decimal(1) / 3) if inv else x * x * x
            elif name == "fact":
                if x < 0 or x > 3000:
                    raise ValueError
                if x == x.to_integral_value():
                    r = Decimal(math.factorial(int(x)))
                else:
                    r = Decimal(repr(math.gamma(fx + 1)))
            elif name == "pi":
                r = Decimal("3.1415926535897932384626433832795") * (2 if inv else 1)
            elif name == "int":
                r = x - int(x) if inv else Decimal(int(x))
            elif name == "not":
                r = Decimal(~int(x))
            elif name == "dms":
                r = self._dms(x, inv)
            else:
                return
            self.set_value(r)
            self._just_op = False
        except CalcError as e:
            self._fail(e)
        except (ValueError, decimal.InvalidOperation, OverflowError, ZeroDivisionError):
            self._fail(CalcError(T("Nieprawidłowe dane wejściowe dla funkcji.", "Invalid input for function.")))

    def _dms(self, x, inv):
        if inv:
            # D.MMSS -> stopnie dziesiętne
            sign = -1 if x < 0 else 1
            x = abs(x)
            d = int(x)
            rest = (x - d) * 100
            m = int(rest)
            s = (rest - m) * 100
            return sign * (Decimal(d) + Decimal(m) / 60 + s / 3600)
        sign = -1 if x < 0 else 1
        x = abs(x)
        d = int(x)
        mf = (x - d) * 60
        m = int(mf)
        s = (mf - m) * 60
        return sign * (Decimal(d) + Decimal(m) / 100 + s / 10000)

    # -------------------------------------------------------- systemy liczbowe
    def set_base(self, base):
        v = self.current()
        self.typing = False
        if base != 10:
            self.base = base
            self.value = Decimal(self._signed(int(v)))
        else:
            self.base = 10
            self.value = v
        self.last_op = None

    def set_word(self, word):
        v = self.current()
        self.word = word
        self.typing = False
        self.value = Decimal(self._signed(int(v)))

    # -------------------------------------------------------- pamięć
    def mem(self, op):
        if op == "MC":
            self.memory = Decimal(0)
        elif op == "MR":
            self.set_value(self.memory)
            self._just_op = False
        elif op == "MS":
            self.memory = self.current()
            self.typing = False
            self.value = self.memory
        elif op == "M+":
            self.memory += self.current()
            self.typing = False
            self.value = self.current()

    def paste(self, text):
        """Wklejanie liczb i prostych wyrażeń (jak w klasycznym kalkulatorze)."""
        mapping = {"+": "+", "-": "-", "*": "*", "/": "/", "%": "%", "=": "=", "(": "(", ")": ")"}
        for ch in text.strip():
            if ch.isdigit() or (self.base == 16 and ch.upper() in "ABCDEF"):
                self.digit(ch.upper())
            elif ch in ".,":
                self.point()
            elif ch in mapping:
                c = mapping[ch]
                if c == "=":
                    self.equals()
                elif c == "(":
                    self.paren_open()
                elif c == ")":
                    self.paren_close()
                elif c == "%":
                    self.percent()
                else:
                    self.operator(c)
            elif ch in "\r\n":
                self.equals()


class CalcButton(QPushButton):
    def __init__(self, text, color=BLUE, w=36, h=29, tip=None):
        super().__init__(text)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(w, h)
        pal = self.palette()
        pal.setColor(QPalette.ButtonText, QColor(color))
        self.setPalette(pal)
        if tip:
            self.setToolTip(tip)


class Display(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(24)
        self.setContextMenuPolicy(Qt.NoContextMenu)


class StatsBox(HDialog):
    changed = Signal()

    def __init__(self, engine, parent):
        super().__init__(T("Statystyka", "Statistics Box"), "calculator", parent, help_button=False)
        self.engine = engine
        lay = QVBoxLayout(self.body())
        self.list = QListWidget()
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in ((T("&RET", "&RET"), self.hide), (T("&ZAŁ", "&LOAD"), self.load),
                         (T("&W", "&CD"), self.clear_one), (T("Wy&czyść", "C&AD"), self.clear_all)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.count = QLabel()
        lay.addWidget(self.count)
        self.resize(260, 240)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for v in self.engine.stats:
            self.list.addItem(self.engine.format(v))
        self.count.setText(f"n={len(self.engine.stats)}")
        self.changed.emit()

    def load(self):
        i = self.list.currentRow()
        if i >= 0:
            self.engine.set_value(self.engine.stats[i])
            self.changed.emit()

    def clear_one(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.engine.stats[i]
            self.refresh()

    def clear_all(self):
        self.engine.stats.clear()
        self.refresh()


class CalcWindow(HWindow):
    def __init__(self):
        super().__init__(T("Kalkulator", "Calculator"), "calculator", resizable=False, maximizable=False)
        self.engine = Engine()
        self.scientific = bool(config.get("calc_scientific", False))
        self.grouping = bool(config.get("calc_grouping", False))
        self._stats = None
        outer = QVBoxLayout(self.body())
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.menubar = QMenuBar()
        outer.addWidget(self.menubar)
        self.content = QWidget()
        outer.addWidget(self.content)
        self._build_menus()
        self._build()

    # -------------------------------------------------------- menu
    def _build_menus(self):
        mb = self.menubar
        m = mb.addMenu(T("&Edycja", "&Edit"))
        act(m, T("&Kopiuj", "&Copy") + "\tCtrl+C", self.copy, "Ctrl+C")
        act(m, T("&Wklej", "&Paste") + "\tCtrl+V", self.paste, "Ctrl+V")
        m = mb.addMenu(T("&Widok", "&View"))
        self.a_std = act(m, T("&Standardowy", "S&tandard"), lambda: self.set_mode(False), checkable=False)
        self.a_sci = act(m, T("&Naukowy", "&Scientific"), lambda: self.set_mode(True), checkable=False)
        for a in (self.a_std, self.a_sci):
            a.setCheckable(True)
        m.addSeparator()
        self.a_group = act(m, T("&Grupowanie cyfr", "&Digit grouping"), self._toggle_group, checkable=True,
                           checked=self.grouping)
        help_menu(mb, self, T("Kalkulator", "Calculator"), "calculator", "calc")

    def set_mode(self, sci):
        if sci == self.scientific:
            self.a_std.setChecked(not sci)
            self.a_sci.setChecked(sci)
            return
        self.scientific = sci
        config.set("calc_scientific", sci)
        if not sci and self.engine.base != 10:
            self.engine.set_base(10)
        self._build()

    def _toggle_group(self, on):
        self.grouping = on
        config.set("calc_grouping", on)
        self.refresh()

    # -------------------------------------------------------- układ
    def _build(self):
        self.a_std.setChecked(not self.scientific)
        self.a_sci.setChecked(self.scientific)
        self.engine.precedence = self.scientific
        old = self.content.layout()
        if old is not None:
            QWidget().setLayout(old)   # zabiera stary układ razem z przyciskami
        self.buttons = {}
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)
        self.display = Display()
        f = QFont(self.display.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() + 1)
        elif f.pixelSize() > 0:
            f.setPixelSize(f.pixelSize() + 1)
        self.display.setFont(f)
        lay.addWidget(self.display)
        if self.scientific:
            self._build_scientific(lay)
        else:
            self._build_standard(lay)
        self.content.adjustSize()
        self.body().adjustSize()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())
        self.refresh()

    def _mem_box(self):
        self.mem_label = QLabel("")
        self.mem_label.setFixedSize(28, 26)
        self.mem_label.setAlignment(Qt.AlignCenter)
        self.mem_label.setFrameShape(QFrame.Panel)
        self.mem_label.setFrameShadow(QFrame.Sunken)
        return self.mem_label

    def _b(self, key, text, color, w=36, h=29, tip=None):
        b = CalcButton(text, color, w, h, tip)
        b.clicked.connect(lambda _=False, k=key: self.press(k))
        self.buttons[key] = b
        return b

    def _build_standard(self, lay):
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self._mem_box())
        top.addSpacing(8)
        for key, text in (("back", "Backspace"), ("CE", "CE"), ("C", "C")):
            top.addWidget(self._b(key, text, RED, 62))
        lay.addLayout(top)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        rows = [
            [("MC", "MC", RED), ("7", "7", BLUE), ("8", "8", BLUE), ("9", "9", BLUE), ("/", "/", RED), ("sqrt", "sqrt", BLUE)],
            [("MR", "MR", RED), ("4", "4", BLUE), ("5", "5", BLUE), ("6", "6", BLUE), ("*", "*", RED), ("%", "%", BLUE)],
            [("MS", "MS", RED), ("1", "1", BLUE), ("2", "2", BLUE), ("3", "3", BLUE), ("-", "-", RED), ("recip", "1/x", BLUE)],
            [("M+", "M+", RED), ("0", "0", BLUE), ("neg", "+/-", BLUE), (".", dec_point(), BLUE), ("+", "+", RED), ("=", "=", RED)],
        ]
        for r, row in enumerate(rows):
            for c, (key, text, color) in enumerate(row):
                grid.addWidget(self._b(key, text, color), r, c + (1 if c else 0))
        grid.setColumnMinimumWidth(1, 4)
        lay.addLayout(grid)

    def _build_scientific(self, lay):
        e = self.engine
        # wiersz 1: systemy liczbowe i jednostki kątów / rozmiar słowa
        r1 = QHBoxLayout()
        bases = QFrame()
        bases.setFrameShape(QFrame.StyledPanel)
        bl = QHBoxLayout(bases)
        bl.setContentsMargins(6, 0, 6, 0)
        self.base_group = QButtonGroup(self)
        for b, text in ((16, "Hex"), (10, "Dec"), (8, "Oct"), (2, "Bin")):
            rb = QRadioButton(text)
            rb.setFocusPolicy(Qt.NoFocus)
            rb.setChecked(e.base == b)
            self.base_group.addButton(rb, b)
            bl.addWidget(rb)
        self.base_group.idClicked.connect(self._set_base)
        r1.addWidget(bases)
        self.unit_frame = QFrame()
        self.unit_frame.setFrameShape(QFrame.StyledPanel)
        ul = QHBoxLayout(self.unit_frame)
        ul.setContentsMargins(6, 0, 6, 0)
        self.unit_group = QButtonGroup(self)
        self.unit_buttons = []
        for i in range(4):
            rb = QRadioButton()
            rb.setFocusPolicy(Qt.NoFocus)
            self.unit_group.addButton(rb, i)
            self.unit_buttons.append(rb)
            ul.addWidget(rb)
        self.unit_group.idClicked.connect(self._set_unit)
        r1.addWidget(self.unit_frame, 1)
        lay.addLayout(r1)
        # wiersz 2: Inv, Hyp, wskaźnik nawiasów, Backspace CE C
        r2 = QHBoxLayout()
        flags = QFrame()
        flags.setFrameShape(QFrame.StyledPanel)
        fl = QHBoxLayout(flags)
        fl.setContentsMargins(6, 0, 6, 0)
        self.inv = QCheckBox("Inv")
        self.hyp = QCheckBox("Hyp")
        for cb in (self.inv, self.hyp):
            cb.setFocusPolicy(Qt.NoFocus)
            fl.addWidget(cb)
        r2.addWidget(flags)
        self.paren_label = QLabel("")
        self.paren_label.setFixedSize(40, 24)
        self.paren_label.setAlignment(Qt.AlignCenter)
        self.paren_label.setFrameShape(QFrame.Panel)
        self.paren_label.setFrameShadow(QFrame.Sunken)
        r2.addWidget(self.paren_label)
        r2.addStretch(1)
        for key, text in (("back", "Backspace"), ("CE", "CE"), ("C", "C")):
            r2.addWidget(self._b(key, text, RED, 62))
        lay.addLayout(r2)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        W = 34
        left = [
            [("Sta", "Sta", BLUE), ("FE", "F-E", PURPLE), ("(", "(", PURPLE), (")", ")", PURPLE)],
            [("Ave", "Ave", BLUE), ("dms", "dms", PURPLE), ("Exp", "Exp", PURPLE), ("ln", "ln", PURPLE)],
            [("Sum", "Sum", BLUE), ("sin", "sin", PURPLE), ("pow", "x^y", PURPLE), ("log", "log", PURPLE)],
            [("s", "s", BLUE), ("cos", "cos", PURPLE), ("cube", "x^3", PURPLE), ("fact", "n!", PURPLE)],
            [("Dat", "Dat", BLUE), ("tan", "tan", PURPLE), ("sq", "x^2", PURPLE), ("recip", "1/x", PURPLE)],
        ]
        right = [
            [("MC", "MC", RED), ("7", "7", BLUE), ("8", "8", BLUE), ("9", "9", BLUE), ("/", "/", RED), ("mod", "Mod", RED), ("and", "And", RED)],
            [("MR", "MR", RED), ("4", "4", BLUE), ("5", "5", BLUE), ("6", "6", BLUE), ("*", "*", RED), ("or", "Or", RED), ("xor", "Xor", RED)],
            [("MS", "MS", RED), ("1", "1", BLUE), ("2", "2", BLUE), ("3", "3", BLUE), ("-", "-", RED), ("lsh", "Lsh", RED), ("not", "Not", RED)],
            [("M+", "M+", RED), ("0", "0", BLUE), ("neg", "+/-", BLUE), (".", dec_point(), BLUE), ("+", "+", RED), ("=", "=", RED), ("int", "Int", RED)],
            [("pi", "pi", BLUE), ("A", "A", BLUE), ("B", "B", BLUE), ("C_", "C", BLUE), ("D", "D", BLUE), ("E", "E", BLUE), ("F", "F", BLUE)],
        ]
        for r, row in enumerate(left):
            for c, (key, text, color) in enumerate(row):
                grid.addWidget(self._b(key, text, color, W), r, c)
        grid.setColumnMinimumWidth(4, 6)
        for r, row in enumerate(right):
            for c, (key, text, color) in enumerate(row):
                col = 5 + c + (1 if c else 0)
                grid.addWidget(self._b(key, text, color, W), r, col)
        grid.setColumnMinimumWidth(6, 4)
        lay.addLayout(grid)
        self.mem_label = QLabel("")
        self.mem_label.setFixedSize(30, 22)
        self.mem_label.setAlignment(Qt.AlignCenter)
        self.mem_label.setFrameShape(QFrame.Panel)
        self.mem_label.setFrameShadow(QFrame.Sunken)
        r2.insertWidget(2, self.mem_label)
        self._update_units()

    def _update_units(self):
        if not self.scientific:
            return
        e = self.engine
        if e.base == 10:
            labels = [(T("Stopnie", "Degrees"), "deg"), (T("Radiany", "Radians"), "rad"), (T("Gradusy", "Grads"), "grad")]
            cur = e.angle
        else:
            labels = [("Qword", "qword"), ("Dword", "dword"), ("Word", "word"), ("Byte", "byte")]
            cur = e.word
        for i, rb in enumerate(self.unit_buttons):
            if i < len(labels):
                rb.setText(labels[i][0])
                rb.setProperty("unit", labels[i][1])
                rb.setVisible(True)
                rb.setChecked(labels[i][1] == cur)
            else:
                rb.setVisible(False)

    def _set_unit(self, i):
        unit = self.unit_buttons[i].property("unit")
        if self.engine.base == 10:
            self.engine.angle = unit
        else:
            self.engine.set_word(unit)
        self.refresh()

    def _set_base(self, b):
        self.engine.set_base(b)
        self._update_units()
        self.refresh()

    # -------------------------------------------------------- akcje
    def press(self, key):
        e = self.engine
        inv = self.scientific and self.inv.isChecked()
        hyp = self.scientific and self.hyp.isChecked()
        if e.error and key not in ("C", "CE"):
            e.error = None
            e.reset()
        if key == "C_":
            key = "C_hex"
        if key in "0123456789" or key in ("A", "B", "C_hex", "D", "E", "F"):
            e.digit("C" if key == "C_hex" else key)
            e._mark_input()
        elif key == ".":
            e.point()
            e._mark_input()
        elif key in ("+", "-", "*", "/", "mod", "and", "or", "xor"):
            e.operator(key)
        elif key == "pow":
            e.operator("root" if inv else "pow")
        elif key == "lsh":
            e.operator("rsh" if inv else "lsh")
        elif key == "=":
            e.equals()
        elif key == "C":
            e.reset()
        elif key == "CE":
            e.clear_entry()
        elif key == "back":
            e.backspace()
        elif key == "neg":
            e.negate()
        elif key == "%":
            e.percent()
        elif key in ("sqrt", "recip", "sin", "cos", "tan", "ln", "log", "sq", "cube", "fact", "pi", "int", "not", "dms"):
            e.func(key, inv, hyp)
        elif key in ("MC", "MR", "MS", "M+"):
            e.mem(key)
        elif key == "(":
            e.paren_open()
        elif key == ")":
            e.paren_close()
        elif key == "FE":
            e.fe = not e.fe
        elif key == "Exp":
            e.exp()
        elif key == "Sta":
            self._show_stats()
        elif key == "Dat":
            e.stats.append(e.current())
            e.typing = False
            e.value = e.current()
            if self._stats:
                self._stats.refresh()
        elif key in ("Ave", "Sum", "s"):
            self._stat(key, inv)
        if self.scientific and key not in ("C", "CE"):
            self.inv.setChecked(False)
            self.hyp.setChecked(False)
        self.refresh()

    def _stat(self, key, inv):
        e = self.engine
        data = e.stats
        if not data:
            return
        n = len(data)
        if key == "Ave":
            r = sum(x * x for x in data) / n if inv else sum(data) / n
        elif key == "Sum":
            r = sum(x * x for x in data) if inv else sum(data)
        else:
            mean = sum(data) / n
            var = sum((x - mean) ** 2 for x in data)
            if inv:
                r = (var / n).sqrt()
            else:
                if n < 2:
                    return
                r = (var / (n - 1)).sqrt()
        e.set_value(r)

    def _show_stats(self):
        if self._stats is None:
            self._stats = StatsBox(self.engine, self)
            self._stats.changed.connect(self.refresh)
        self._stats.refresh()
        self._stats.show()
        self._stats.raise_()

    def refresh(self):
        e = self.engine
        self.display.setText(e.display(self.grouping))
        self.mem_label.setText("M" if e.memory != 0 else "")
        if self.scientific:
            d = e.depth()
            self.paren_label.setText(f"(={d}" if d else "")
            for k in ("A", "B", "C_", "D", "E", "F"):
                self.buttons[k].setEnabled(e.base == 16)
            for k in "23456789":
                self.buttons[k].setEnabled(int(k) < e.base)
            dec_only = ("sin", "cos", "tan", "dms", "FE", "Exp", "ln", "log", "pi", ".", "sqrt")
            for k in dec_only:
                if k in self.buttons:
                    self.buttons[k].setEnabled(e.base == 10)
            for k in ("Ave", "Sum", "s", "Dat"):
                self.buttons[k].setEnabled(bool(e.stats) or k == "Dat")

    def copy(self):
        e = self.engine
        txt = e.display(False)
        if e.base == 10 and txt.endswith(dec_point()):
            txt = txt[:-1]
        QApplication.clipboard().setText(txt)

    def paste(self):
        self.engine.paste(QApplication.clipboard().text())
        self.refresh()

    # -------------------------------------------------------- klawiatura
    def keyPressEvent(self, ev):
        k, t = ev.key(), ev.text()
        mods = ev.modifiers()
        if mods & Qt.ControlModifier:
            ctrl = {Qt.Key_M: "MS", Qt.Key_R: "MR", Qt.Key_P: "M+", Qt.Key_L: "MC"}
            if k in ctrl:
                self.press(ctrl[k])
                return
            return super().keyPressEvent(ev)
        keymap = {Qt.Key_Return: "=", Qt.Key_Enter: "=", Qt.Key_Escape: "C", Qt.Key_Delete: "CE",
                  Qt.Key_Backspace: "back", Qt.Key_F9: "neg"}
        if k in keymap:
            self.press(keymap[k])
            return
        chars = {"+": "+", "-": "-", "*": "*", "/": "/", "=": "=", "%": "mod" if self.scientific else "%",
                 "@": "sqrt" if not self.scientific else "sq", "r": "recip", "(": "(", ")": ")",
                 "^": "pow", "!": "fact", "s": "sin", "o": "cos", "t": "tan", "n": "ln", "l": "log",
                 "p": "pi", "#": "cube", "&": "and", "|": "or", "<": "lsh", "~": "not", ";": "int",
                 "x": "Exp", "m": "dms", "v": "FE", "i": "Inv"}
        if t and t in "0123456789":
            self.press(t)
        elif t and t.upper() in "ABCDEF" and self.engine.base == 16:
            self.press("C_" if t.upper() == "C" else t.upper())
        elif t in (".", ","):
            self.press(".")
        elif t in chars and (self.scientific or chars[t] in ("+", "-", "*", "/", "=", "%", "sqrt", "recip")):
            if chars[t] == "Inv":
                self.inv.setChecked(not self.inv.isChecked())
            else:
                self.press(chars[t])
        else:
            super().keyPressEvent(ev)


class CalcApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = CalcWindow()
            self.win.move(120, 90)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    ctl = CalcApp()
    return run_app("calc", ctl.handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
