"""Emulator terminala zgodny z xterm (podzbiór wystarczający dla bash, vim, nano, htop, mc, less, git…).

Ekran trzyma znaki i atrybuty w listach wierszy. Atrybut to krotka
(fg, bg, flags), gdzie fg/bg to None (domyślny), int 0..255 albo (r, g, b).
"""
import unicodedata
from collections import deque

BOLD, DIM, ITALIC, UNDER, BLINK, REVERSE, HIDDEN, STRIKE = 1, 2, 4, 8, 16, 32, 64, 128
DEFAULT_ATTR = (None, None, 0)

# znaki rysowania ramek DEC (ESC ( 0)
DEC_GRAPHICS = {
    "`": "◆", "a": "▒", "b": "␉", "c": "␌", "d": "␍", "e": "␊", "f": "°", "g": "±", "h": "␤", "i": "␋",
    "j": "┘", "k": "┐", "l": "┌", "m": "└", "n": "┼", "o": "⎺", "p": "⎻", "q": "─", "r": "⎼", "s": "⎽",
    "t": "├", "u": "┤", "v": "┴", "w": "┬", "x": "│", "y": "≤", "z": "≥", "{": "π", "|": "≠", "}": "£", "~": "·",
}


def char_width(ch):
    o = ord(ch)
    if o < 0x300:
        return 1
    if unicodedata.combining(ch):
        return 0
    if 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF and unicodedata.east_asian_width(ch) == "W":
        return 2
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


class Screen:
    def __init__(self, cols=80, rows=25, scrollback=3000):
        self.cols, self.rows = cols, rows
        self.scrollback_max = scrollback
        self.history = deque(maxlen=scrollback)
        self.title = ""
        self.response = []          # odpowiedzi do procesu (np. raport pozycji kursora)
        self.bell = False
        self.dirty = True
        self.reset()

    # ------------------------------------------------------------------ stan
    def reset(self):
        self.lines = [self._blank_line() for _ in range(self.rows)]
        self.attrs = [self._blank_attrs() for _ in range(self.rows)]
        self.wrapped = [False] * self.rows
        self.x = self.y = 0
        self.attr = DEFAULT_ATTR
        self.saved = (0, 0, DEFAULT_ATTR, False)
        self.top, self.bottom = 0, self.rows - 1
        self.autowrap = True
        self.pending_wrap = False
        self.origin = False
        self.insert = False
        self.cursor_visible = True
        self.app_cursor = False
        self.app_keypad = False
        self.bracketed_paste = False
        self.mouse_mode = 0          # 0 brak, 1000 kliknięcia, 1002 przeciąganie, 1003 każdy ruch
        self.mouse_sgr = False
        self.alt = None              # zapisany ekran główny podczas ekranu alternatywnego
        self.g0_graphics = self.g1_graphics = False
        self.shift_out = False
        self.tabs = set(range(8, 1000, 8))
        self.cursor_shape = 0
        self.last_char = " "
        self._state = "ground"
        self._params = ""
        self._inter = ""
        self._osc = ""
        self.dirty = True

    def _blank_line(self, n=None):
        return [" "] * (n or self.cols)

    def _blank_attrs(self, n=None, attr=None):
        a = attr if attr is not None else (None, self.attr[1] if hasattr(self, "attr") else None, 0)
        return [a] * (n or self.cols)

    def resize(self, cols, rows):
        cols, rows = max(2, cols), max(2, rows)
        if (cols, rows) == (self.cols, self.rows):
            return
        # wiersze
        if rows < self.rows:
            # przesuwamy nadmiar do historii (jeśli kursor jest nisko)
            excess = self.rows - rows
            cut = min(excess, max(0, self.y - rows + 1))
            for _ in range(cut):
                if self.alt is None:
                    self.history.append((self.lines[0], self.attrs[0]))
                del self.lines[0], self.attrs[0], self.wrapped[0]
            self.y -= cut
            del self.lines[rows:], self.attrs[rows:], self.wrapped[rows:]
        else:
            for _ in range(rows - self.rows):
                if self.alt is None and self.history and self.y >= self.rows - 1:
                    l, a = self.history.pop()
                    self.lines.insert(0, l)
                    self.attrs.insert(0, a)
                    self.wrapped.insert(0, False)
                    self.y += 1
                else:
                    self.lines.append([" "] * self.cols)
                    self.attrs.append([DEFAULT_ATTR] * self.cols)
                    self.wrapped.append(False)
        # kolumny
        for i in range(len(self.lines)):
            l, a = self.lines[i], self.attrs[i]
            if len(l) < cols:
                l.extend([" "] * (cols - len(l)))
                a.extend([DEFAULT_ATTR] * (cols - len(a)))
            else:
                del l[cols:], a[cols:]
        self.cols, self.rows = cols, rows
        self.top, self.bottom = 0, rows - 1
        self.x = min(self.x, cols - 1)
        self.y = min(self.y, rows - 1)
        self.pending_wrap = False
        if self.alt is not None:
            # ekran główny też dopasowujemy
            ml, ma, mw, mx, my = self.alt
            ml = [((l + [" "] * cols)[:cols]) for l in ml[:rows]] + [[" "] * cols for _ in range(rows - len(ml[:rows]))]
            ma = [((a + [DEFAULT_ATTR] * cols)[:cols]) for a in ma[:rows]] + [[DEFAULT_ATTR] * cols for _ in range(rows - len(ma[:rows]))]
            self.alt = (ml, ma, [False] * rows, min(mx, cols - 1), min(my, rows - 1))
        self.dirty = True

    # ------------------------------------------------------------------ wejście
    def feed(self, text):
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            st = self._state
            if st == "ground":
                # szybka ścieżka dla zwykłego tekstu
                j = i
                while j < n and text[j] >= " " and text[j] != "\x7f":
                    j += 1
                if j > i:
                    self._print_run(text[i:j])
                    i = j
                    continue
                self._control(ch)
            elif st == "esc":
                self._esc(ch)
            elif st == "csi":
                if "0" <= ch <= "9" or ch in ";:?><=!":
                    self._params += ch
                elif " " <= ch <= "/":
                    self._inter += ch
                elif "@" <= ch <= "~":
                    self._state = "ground"
                    self._csi(ch)
                elif ch in "\x1b":
                    self._state = "esc"
                else:
                    self._control(ch)
            elif st == "osc":
                if ch == "\x07":
                    self._state = "ground"
                    self._osc_done()
                elif ch == "\x1b":
                    self._state = "osc_esc"
                else:
                    self._osc += ch
            elif st == "osc_esc":
                self._state = "ground"
                if ch == "\\":
                    self._osc_done()
            elif st == "charset":
                graphics = ch == "0"
                if self._inter == "(":
                    self.g0_graphics = graphics
                elif self._inter == ")":
                    self.g1_graphics = graphics
                self._state = "ground"
            elif st == "dcs":
                if ch == "\x1b":
                    self._state = "dcs_esc"
            elif st == "dcs_esc":
                self._state = "ground" if ch == "\\" else "dcs"
            elif st == "esc_inter":
                self._state = "ground"   # np. ESC # 8 (DECALN) — pomijamy
            i += 1
        self.dirty = True

    def _control(self, ch):
        if ch == "\x1b":
            self._state = "esc"
        elif ch == "\r":
            self.x = 0
            self.pending_wrap = False
        elif ch in "\n\x0b\x0c":
            self._index()
        elif ch == "\b":
            if self.pending_wrap:
                self.pending_wrap = False
            elif self.x > 0:
                self.x -= 1
        elif ch == "\t":
            nxt = min([t for t in self.tabs if t > self.x] or [self.cols - 1])
            self.x = min(nxt, self.cols - 1)
        elif ch == "\x07":
            self.bell = True
        elif ch == "\x0e":
            self.shift_out = True
        elif ch == "\x0f":
            self.shift_out = False

    def _print_run(self, s):
        graphics = self.g1_graphics if self.shift_out else self.g0_graphics
        for ch in s:
            if graphics and ch in DEC_GRAPHICS:
                ch = DEC_GRAPHICS[ch]
            w = char_width(ch)
            if w == 0:
                # znak łączący — doklejamy do poprzedniej komórki
                px = self.x - 1 if not self.pending_wrap else self.x
                if 0 <= px < self.cols:
                    self.lines[self.y][px] += ch
                continue
            if self.pending_wrap:
                if self.autowrap:
                    self.wrapped[self.y] = True
                    self.x = 0
                    self._index()
                self.pending_wrap = False
            if w == 2 and self.x == self.cols - 1:
                if self.autowrap:
                    self.lines[self.y][self.x] = " "
                    self.wrapped[self.y] = True
                    self.x = 0
                    self._index()
            line, attrs = self.lines[self.y], self.attrs[self.y]
            if self.insert:
                line.insert(self.x, ch)
                attrs.insert(self.x, self.attr)
                del line[self.cols:], attrs[self.cols:]
            else:
                line[self.x] = ch
                attrs[self.x] = self.attr
            if w == 2 and self.x + 1 < self.cols:
                line[self.x + 1] = ""
                attrs[self.x + 1] = self.attr
            self.last_char = ch
            if self.x + w >= self.cols:
                self.x = self.cols - 1
                self.pending_wrap = True
            else:
                self.x += w

    def _index(self):
        if self.y == self.bottom:
            self._scroll_up(1)
        elif self.y < self.rows - 1:
            self.y += 1

    def _rindex(self):
        if self.y == self.top:
            self._scroll_down(1)
        elif self.y > 0:
            self.y -= 1

    def _scroll_up(self, n):
        n = max(1, min(n, self.bottom - self.top + 1))
        for _ in range(n):
            l = self.lines.pop(self.top)
            a = self.attrs.pop(self.top)
            self.wrapped.pop(self.top)
            if self.top == 0 and self.alt is None:
                self.history.append((l, a))
            self.lines.insert(self.bottom, [" "] * self.cols)
            self.attrs.insert(self.bottom, [(None, self.attr[1], 0)] * self.cols)
            self.wrapped.insert(self.bottom, False)

    def _scroll_down(self, n):
        n = max(1, min(n, self.bottom - self.top + 1))
        for _ in range(n):
            self.lines.pop(self.bottom)
            self.attrs.pop(self.bottom)
            self.wrapped.pop(self.bottom)
            self.lines.insert(self.top, [" "] * self.cols)
            self.attrs.insert(self.top, [(None, self.attr[1], 0)] * self.cols)
            self.wrapped.insert(self.top, False)

    # ------------------------------------------------------------------ ESC
    def _esc(self, ch):
        self._state = "ground"
        if ch == "[":
            self._state = "csi"
            self._params = ""
            self._inter = ""
        elif ch == "]":
            self._state = "osc"
            self._osc = ""
        elif ch in "()*+":
            self._state = "charset"
            self._inter = ch
        elif ch == "P":
            self._state = "dcs"
        elif ch == "#":
            self._state = "esc_inter"
        elif ch == "7":
            self.saved = (self.x, self.y, self.attr, self.origin)
        elif ch == "8":
            self.x, self.y, self.attr, self.origin = self.saved
            self.pending_wrap = False
        elif ch == "D":
            self._index()
        elif ch == "E":
            self.x = 0
            self._index()
        elif ch == "M":
            self._rindex()
        elif ch == "H":
            self.tabs.add(self.x)
        elif ch == "c":
            self.reset()
        elif ch == "=":
            self.app_keypad = True
        elif ch == ">":
            self.app_keypad = False
        elif ch == "\\":
            pass

    def _osc_done(self):
        num, _, val = self._osc.partition(";")
        if num in ("0", "2"):
            self.title = val

    # ------------------------------------------------------------------ CSI
    def _csi(self, cmd):
        raw = self._params
        private = raw[:1] if raw[:1] in "?><=!" else ""
        if private:
            raw = raw[1:]
        ps = []
        for p in raw.replace(":", ";").split(";") if raw else []:
            try:
                ps.append(int(p) if p else 0)
            except ValueError:
                ps.append(0)

        def p(i, d=1):
            v = ps[i] if i < len(ps) else 0
            return v if v else d

        if self._inter:
            if cmd == "q" and self._inter == " ":
                self.cursor_shape = p(0, 0)
            return
        if private == "?" and cmd in "hl":
            self._dec_mode(ps, cmd == "h")
            return
        if private in (">", "=") :
            if cmd == "c":
                self.response.append("\x1b[>0;10;1c")
            return
        cols, rows = self.cols, self.rows
        if cmd == "A":
            self.y = max(self.top if self.y >= self.top else 0, self.y - p(0))
        elif cmd == "B":
            self.y = min(self.bottom if self.y <= self.bottom else rows - 1, self.y + p(0))
        elif cmd in "Ca":
            self.x = min(cols - 1, self.x + p(0))
        elif cmd == "D":
            self.x = max(0, self.x - p(0))
        elif cmd == "E":
            self.x = 0
            self.y = min(rows - 1, self.y + p(0))
        elif cmd == "F":
            self.x = 0
            self.y = max(0, self.y - p(0))
        elif cmd in "G`":
            self.x = min(cols - 1, p(0) - 1)
        elif cmd in "Hf":
            r, c = p(0) - 1, p(1) - 1
            if self.origin:
                r += self.top
            self.y = max(0, min(rows - 1, r))
            self.x = max(0, min(cols - 1, c))
        elif cmd == "d":
            self.y = max(0, min(rows - 1, p(0) - 1 + (self.top if self.origin else 0)))
        elif cmd == "e":
            self.y = min(rows - 1, self.y + p(0))
        elif cmd == "J":
            self._erase_display(p(0, 0))
        elif cmd == "K":
            self._erase_line(p(0, 0))
        elif cmd == "L":
            if self.top <= self.y <= self.bottom:
                for _ in range(min(p(0), self.bottom - self.y + 1)):
                    self.lines.pop(self.bottom)
                    self.attrs.pop(self.bottom)
                    self.wrapped.pop(self.bottom)
                    self.lines.insert(self.y, [" "] * cols)
                    self.attrs.insert(self.y, [(None, self.attr[1], 0)] * cols)
                    self.wrapped.insert(self.y, False)
                self.x = 0
        elif cmd == "M":
            if self.top <= self.y <= self.bottom:
                for _ in range(min(p(0), self.bottom - self.y + 1)):
                    self.lines.pop(self.y)
                    self.attrs.pop(self.y)
                    self.wrapped.pop(self.y)
                    self.lines.insert(self.bottom, [" "] * cols)
                    self.attrs.insert(self.bottom, [(None, self.attr[1], 0)] * cols)
                    self.wrapped.insert(self.bottom, False)
                self.x = 0
        elif cmd == "P":
            n = min(p(0), cols - self.x)
            l, a = self.lines[self.y], self.attrs[self.y]
            del l[self.x:self.x + n], a[self.x:self.x + n]
            l.extend([" "] * n)
            a.extend([(None, self.attr[1], 0)] * n)
        elif cmd == "@":
            n = min(p(0), cols - self.x)
            l, a = self.lines[self.y], self.attrs[self.y]
            for _ in range(n):
                l.insert(self.x, " ")
                a.insert(self.x, (None, self.attr[1], 0))
            del l[cols:], a[cols:]
        elif cmd == "X":
            n = min(p(0), cols - self.x)
            for i in range(self.x, self.x + n):
                self.lines[self.y][i] = " "
                self.attrs[self.y][i] = (None, self.attr[1], 0)
        elif cmd == "S":
            self._scroll_up(p(0))
        elif cmd == "T" and not ps[1:]:
            self._scroll_down(p(0))
        elif cmd == "b":
            self._print_run(self.last_char * min(p(0), 2000))
        elif cmd == "r":
            t, b = p(0) - 1, p(1, rows) - 1
            if 0 <= t < b < rows:
                self.top, self.bottom = t, b
                self.x, self.y = 0, (t if self.origin else 0)
        elif cmd == "s":
            self.saved = (self.x, self.y, self.attr, self.origin)
        elif cmd == "u":
            self.x, self.y, self.attr, self.origin = self.saved
        elif cmd == "m":
            self._sgr(ps)
        elif cmd == "n":
            if p(0, 0) == 6:
                self.response.append(f"\x1b[{self.y + 1};{self.x + 1}R")
            elif p(0, 0) == 5:
                self.response.append("\x1b[0n")
        elif cmd == "c":
            self.response.append("\x1b[?62;22c")
        elif cmd == "g":
            if p(0, 0) == 0:
                self.tabs.discard(self.x)
            elif p(0, 0) == 3:
                self.tabs.clear()
        elif cmd == "I":
            for _ in range(p(0)):
                self.x = min([t for t in self.tabs if t > self.x] or [cols - 1])
        elif cmd == "Z":
            for _ in range(p(0)):
                self.x = max([t for t in self.tabs if t < self.x] or [0])
        elif cmd == "h" and 4 in ps:
            self.insert = True
        elif cmd == "l" and 4 in ps:
            self.insert = False
        elif cmd == "t":
            if p(0, 0) == 18:
                self.response.append(f"\x1b[8;{rows};{cols}t")
        self.pending_wrap = False

    def _dec_mode(self, ps, on):
        for m in ps:
            if m == 1:
                self.app_cursor = on
            elif m == 6:
                self.origin = on
                self.x, self.y = 0, (self.top if on else 0)
            elif m == 7:
                self.autowrap = on
            elif m == 25:
                self.cursor_visible = on
            elif m in (1000, 1002, 1003):
                self.mouse_mode = m if on else 0
            elif m == 1006:
                self.mouse_sgr = on
            elif m == 2004:
                self.bracketed_paste = on
            elif m in (47, 1047, 1049):
                if on and self.alt is None:
                    if m == 1049:
                        self.saved = (self.x, self.y, self.attr, self.origin)
                    self.alt = (self.lines, self.attrs, self.wrapped, self.x, self.y)
                    self.lines = [[" "] * self.cols for _ in range(self.rows)]
                    self.attrs = [[DEFAULT_ATTR] * self.cols for _ in range(self.rows)]
                    self.wrapped = [False] * self.rows
                elif not on and self.alt is not None:
                    self.lines, self.attrs, self.wrapped, ax, ay = self.alt
                    self.alt = None
                    if m == 1049:
                        self.x, self.y, self.attr, self.origin = self.saved
                    self.top, self.bottom = 0, self.rows - 1
            elif m == 1048:
                if on:
                    self.saved = (self.x, self.y, self.attr, self.origin)
                else:
                    self.x, self.y, self.attr, self.origin = self.saved

    def _sgr(self, ps):
        if not ps:
            ps = [0]
        fg, bg, fl = self.attr
        i = 0
        while i < len(ps):
            c = ps[i]
            if c == 0:
                fg, bg, fl = None, None, 0
            elif c == 1:
                fl |= BOLD
            elif c == 2:
                fl |= DIM
            elif c == 3:
                fl |= ITALIC
            elif c == 4:
                fl |= UNDER
            elif c in (5, 6):
                fl |= BLINK
            elif c == 7:
                fl |= REVERSE
            elif c == 8:
                fl |= HIDDEN
            elif c == 9:
                fl |= STRIKE
            elif c == 21 or c == 22:
                fl &= ~(BOLD | DIM)
            elif c == 23:
                fl &= ~ITALIC
            elif c == 24:
                fl &= ~UNDER
            elif c == 25:
                fl &= ~BLINK
            elif c == 27:
                fl &= ~REVERSE
            elif c == 28:
                fl &= ~HIDDEN
            elif c == 29:
                fl &= ~STRIKE
            elif 30 <= c <= 37:
                fg = c - 30
            elif c == 39:
                fg = None
            elif 40 <= c <= 47:
                bg = c - 40
            elif c == 49:
                bg = None
            elif 90 <= c <= 97:
                fg = c - 90 + 8
            elif 100 <= c <= 107:
                bg = c - 100 + 8
            elif c in (38, 48, 58):
                col = None
                if i + 1 < len(ps) and ps[i + 1] == 5 and i + 2 < len(ps):
                    col = ps[i + 2] & 255
                    i += 2
                elif i + 1 < len(ps) and ps[i + 1] == 2 and i + 4 < len(ps):
                    col = (ps[i + 2] & 255, ps[i + 3] & 255, ps[i + 4] & 255)
                    i += 4
                if c == 38:
                    fg = col
                elif c == 48:
                    bg = col
            i += 1
        self.attr = (fg, bg, fl)

    def _erase_display(self, mode):
        blank = (None, self.attr[1], 0)
        if mode == 0:
            self._erase_line(0)
            for r in range(self.y + 1, self.rows):
                self.lines[r] = [" "] * self.cols
                self.attrs[r] = [blank] * self.cols
                self.wrapped[r] = False
        elif mode == 1:
            self._erase_line(1)
            for r in range(0, self.y):
                self.lines[r] = [" "] * self.cols
                self.attrs[r] = [blank] * self.cols
        elif mode in (2, 3):
            if mode == 2 and self.alt is None:
                # jak w xterm: czyszczony ekran trafia do historii (clear nie gubi przewijania)
                last = max((r for r in range(self.rows) if "".join(self.lines[r]).strip()), default=-1)
                for r in range(last + 1):
                    self.history.append((self.lines[r], self.attrs[r]))
            for r in range(self.rows):
                self.lines[r] = [" "] * self.cols
                self.attrs[r] = [blank] * self.cols
                self.wrapped[r] = False
            if mode == 3:
                self.history.clear()

    def _erase_line(self, mode):
        blank = (None, self.attr[1], 0)
        l, a = self.lines[self.y], self.attrs[self.y]
        if mode == 0:
            rng = range(self.x, self.cols)
        elif mode == 1:
            rng = range(0, min(self.cols, self.x + 1))
        else:
            rng = range(self.cols)
        for i in rng:
            l[i] = " "
            a[i] = blank

    # ------------------------------------------------------------------ odczyt
    def total_lines(self):
        return len(self.history) + self.rows

    def line_at(self, idx):
        """Wiersz o indeksie absolutnym (0 = najstarszy w historii)."""
        h = len(self.history)
        if idx < h:
            return self.history[idx]
        return self.lines[idx - h], self.attrs[idx - h]

    def text_range(self, a, b):
        """Tekst między punktami (wiersz absolutny, kolumna)."""
        (r1, c1), (r2, c2) = sorted([a, b])
        out = []
        for r in range(r1, r2 + 1):
            if r >= self.total_lines():
                break
            line, _ = self.line_at(r)
            s = c1 if r == r1 else 0
            e = c2 if r == r2 else len(line)
            out.append("".join(line[s:e]).rstrip())
        return "\n".join(out)

    def take_responses(self):
        r, self.response = self.response, []
        return "".join(r)
