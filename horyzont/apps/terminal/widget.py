"""Widżet terminala: pseudoterminal, rysowanie ekranu, klawiatura, mysz, zaznaczanie."""
import codecs
import fcntl
import os
import pty
import signal
import struct
import termios

from PySide6.QtCore import QPoint, QRect, QSocketNotifier, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QKeySequence, QPainter
from PySide6.QtWidgets import QHBoxLayout, QScrollBar, QWidget

from .vt import BLINK, BOLD, DIM, HIDDEN, ITALIC, REVERSE, STRIKE, UNDER, Screen

# paleta klasycznej konsoli (16 kolorów, kolejność ANSI)
CLASSIC_PALETTE = ["#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080", "#c0c0c0",
                   "#808080", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff"]


def xterm_color(n, palette):
    if n < 16:
        return QColor(palette[n])
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        return QColor(steps[n // 36], steps[(n // 6) % 6], steps[n % 6])
    v = 8 + (n - 232) * 10
    return QColor(v, v, v)


KEYS = {
    Qt.Key_Return: "\r", Qt.Key_Enter: "\r", Qt.Key_Backspace: "\x7f", Qt.Key_Tab: "\t", Qt.Key_Escape: "\x1b",
    Qt.Key_Insert: "\x1b[2~", Qt.Key_Delete: "\x1b[3~", Qt.Key_PageUp: "\x1b[5~", Qt.Key_PageDown: "\x1b[6~",
    Qt.Key_F1: "\x1bOP", Qt.Key_F2: "\x1bOQ", Qt.Key_F3: "\x1bOR", Qt.Key_F4: "\x1bOS",
    Qt.Key_F5: "\x1b[15~", Qt.Key_F6: "\x1b[17~", Qt.Key_F7: "\x1b[18~", Qt.Key_F8: "\x1b[19~",
    Qt.Key_F9: "\x1b[20~", Qt.Key_F10: "\x1b[21~", Qt.Key_F11: "\x1b[23~", Qt.Key_F12: "\x1b[24~",
}
CURSOR_KEYS = {Qt.Key_Up: "A", Qt.Key_Down: "B", Qt.Key_Right: "C", Qt.Key_Left: "D", Qt.Key_Home: "H", Qt.Key_End: "F"}


class TerminalView(QWidget):
    """Sam obszar znaków (bez paska przewijania)."""

    title_changed = Signal(str)
    finished = Signal(int)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.IBeamCursor)
        self.setMouseTracking(True)
        self.screen = Screen(settings.get("cols", 80), settings.get("rows", 25), settings.get("scrollback", 3000))
        self.scroll_offset = 0          # 0 = koniec historii
        self.sel_start = self.sel_end = None
        self._selecting = False
        self.pid = None
        self.fd = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._blink_on = True
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._toggle_blink)
        self._blink.start(530)
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(8)
        self._repaint_timer.timeout.connect(self._flush_repaint)
        self.scrollbar = None
        self.apply_settings(settings)

    # ------------------------------------------------------------------ ustawienia
    def apply_settings(self, s):
        self.settings = s
        f = QFont(s.get("font", "Monospace"))
        f.setStyleHint(QFont.TypeWriter)
        f.setFixedPitch(True)
        f.setPointSizeF(float(s.get("font_size", 10)))
        f.setBold(bool(s.get("font_bold", False)))
        self.font_ = f
        self.font_bold = QFont(f)
        self.font_bold.setBold(True)
        fm = QFontMetrics(f)
        self.cw = max(1, fm.horizontalAdvance("M"))
        self.ch = max(1, fm.height())
        self.ascent = fm.ascent()
        self.palette_ = list(s.get("palette", CLASSIC_PALETTE))
        self.fg_default = QColor(self.palette_[int(s.get("fg", 7))])
        self.bg_default = QColor(self.palette_[int(s.get("bg", 0))])
        self.screen.scrollback_max = int(s.get("scrollback", 3000))
        self.update()

    def size_for(self, cols, rows):
        return cols * self.cw + 4, rows * self.ch + 4

    # ------------------------------------------------------------------ proces
    def start(self, argv, cwd=None, env=None, banner=""):
        if banner:
            self.screen.feed(banner.replace("\n", "\r\n"))
        e = dict(env or os.environ)
        e["TERM"] = "xterm-256color"
        e["COLORTERM"] = "truecolor"
        e.pop("COLUMNS", None)
        e.pop("LINES", None)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                if cwd and os.path.isdir(cwd):
                    os.chdir(cwd)
                else:
                    os.chdir(os.path.expanduser("~"))
                os.execvpe(argv[0], argv, e)
            except Exception as ex:  # pragma: no cover
                os.write(2, f"horyzont: nie można uruchomić {argv[0]}: {ex}\n".encode())
            os._exit(127)
        os.set_blocking(self.fd, False)
        self._set_winsize()
        self._notifier = QSocketNotifier(self.fd, QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._read)

    def _set_winsize(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.screen.rows, self.screen.cols,
                                                                     self.screen.cols * self.cw, self.screen.rows * self.ch))
            except OSError:
                pass

    def _read(self, *_):
        chunks = []
        while True:
            try:
                b = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                b = b""
            if not b:
                if chunks:
                    self._process(b"".join(chunks))
                self._ended()
                return
            chunks.append(b)
            if sum(len(c) for c in chunks) > 1 << 20:
                break
        if chunks:
            self._process(b"".join(chunks))

    def _process(self, data):
        text = self._decoder.decode(data)
        old_title = self.screen.title
        self.screen.feed(text)
        resp = self.screen.take_responses()
        if resp:
            self.send(resp)
        if self.screen.title != old_title:
            self.title_changed.emit(self.screen.title)
        if self.screen.bell:
            self.screen.bell = False
            QGuiApplication.beep()
        if self.scroll_offset == 0:
            pass
        self._blink_on = True
        self._schedule_repaint()

    def _schedule_repaint(self):
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    def _flush_repaint(self):
        self._update_scrollbar()
        self.update()

    def _ended(self):
        self._notifier.setEnabled(False)
        code = 0
        try:
            _, status = os.waitpid(self.pid, 0)
            code = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None
        self.finished.emit(code)

    def send(self, text):
        if self.fd is None:
            return
        data = text.encode("utf-8") if isinstance(text, str) else text
        try:
            os.write(self.fd, data)
        except OSError:
            pass

    def terminate(self):
        if self.pid and self.fd is not None:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGHUP)
            except OSError:
                try:
                    os.kill(self.pid, signal.SIGHUP)
                except OSError:
                    pass

    def busy_child(self):
        """Czy w terminalu działa program inny niż powłoka (pytamy przed zamknięciem)."""
        if self.fd is None:
            return None
        try:
            pgrp = os.tcgetpgrp(self.fd)
        except OSError:
            return None
        if pgrp and pgrp != self.pid:
            try:
                with open(f"/proc/{pgrp}/comm") as f:
                    return f.read().strip()
            except OSError:
                return "?"
        return None

    def cwd(self):
        try:
            pgrp = os.tcgetpgrp(self.fd) if self.fd is not None else self.pid
            return os.readlink(f"/proc/{pgrp or self.pid}/cwd")
        except OSError:
            return None

    # ------------------------------------------------------------------ geometria
    def resizeEvent(self, e):
        cols = max(10, (self.width() - 4) // self.cw)
        rows = max(3, (self.height() - 4) // self.ch)
        if (cols, rows) != (self.screen.cols, self.screen.rows):
            self.screen.resize(cols, rows)
            self._set_winsize()
            self._update_scrollbar()
        super().resizeEvent(e)

    def attach_scrollbar(self, sb):
        self.scrollbar = sb
        sb.valueChanged.connect(self._sb_moved)
        self._update_scrollbar()

    def _update_scrollbar(self):
        sb = self.scrollbar
        if sb is None:
            return
        h = len(self.screen.history) if self.screen.alt is None else 0
        sb.blockSignals(True)
        sb.setRange(0, h)
        sb.setPageStep(self.screen.rows)
        sb.setValue(h - self.scroll_offset)
        sb.blockSignals(False)

    def _sb_moved(self, v):
        h = len(self.screen.history) if self.screen.alt is None else 0
        self.scroll_offset = max(0, h - v)
        self.update()

    def first_visible(self):
        h = len(self.screen.history) if self.screen.alt is None else 0
        return h - self.scroll_offset

    # ------------------------------------------------------------------ rysowanie
    def _toggle_blink(self):
        self._blink_on = not self._blink_on
        x, y = self.screen.x, self.screen.y
        self.update(QRect(2 + x * self.cw - 1, 2 + (y + self.scroll_offset) * self.ch, self.cw * 2 + 2, self.ch))

    def _color(self, c, default):
        if c is None:
            return default
        if isinstance(c, tuple):
            return QColor(*c)
        return xterm_color(c, self.palette_)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.bg_default)
        scr = self.screen
        first = self.first_visible()
        clip = e.rect()
        r0 = max(0, (clip.top() - 2) // self.ch)
        r1 = min(scr.rows - 1, (clip.bottom() - 2) // self.ch + 1)
        sel = self._sel_norm()
        h = len(scr.history) if scr.alt is None else 0
        for row in range(r0, r1 + 1):
            idx = first + row
            if scr.alt is not None:
                if idx >= scr.rows:
                    break
                line, attrs = scr.lines[idx], scr.attrs[idx]
            else:
                if idx >= h + scr.rows:
                    break
                line, attrs = scr.line_at(idx)
            y = 2 + row * self.ch
            col = 0
            n = len(line)
            while col < n:
                a = attrs[col]
                start = col
                insel = self._in_sel(sel, idx, col)
                col += 1
                while col < n and attrs[col] == a and self._in_sel(sel, idx, col) == insel:
                    col += 1
                fg, bg, fl = a
                fgc = self._color(fg, self.fg_default)
                bgc = self._color(bg, self.bg_default)
                if fl & BOLD and isinstance(fg, int) and fg < 8:
                    fgc = QColor(self.palette_[fg + 8])
                if fl & REVERSE:
                    fgc, bgc = bgc, fgc
                if insel:
                    fgc, bgc = QColor(self.bg_default), QColor(self.fg_default)
                if fl & DIM:
                    fgc = QColor((fgc.red() + bgc.red()) // 2, (fgc.green() + bgc.green()) // 2, (fgc.blue() + bgc.blue()) // 2)
                x = 2 + start * self.cw
                w = (col - start) * self.cw
                if bgc != self.bg_default:
                    p.fillRect(x, y, w, self.ch, bgc)
                text = "".join(line[start:col])
                if fl & HIDDEN or (fl & BLINK and not self._blink_on) or not text.strip():
                    continue
                f = self.font_bold if fl & BOLD else self.font_
                if fl & (ITALIC | UNDER | STRIKE):
                    f = QFont(f)
                    f.setItalic(bool(fl & ITALIC))
                    f.setUnderline(bool(fl & UNDER))
                    f.setStrikeOut(bool(fl & STRIKE))
                p.setFont(f)
                p.setPen(fgc)
                # rysujemy komórka po komórce, gdy w tekście są znaki szerokie albo łączone
                if any(len(c) != 1 for c in line[start:col]):
                    for i, c in enumerate(line[start:col]):
                        if c:
                            p.drawText(x + i * self.cw, y + self.ascent, c)
                else:
                    p.drawText(x, y + self.ascent, text)
        # kursor
        if scr.cursor_visible and self.scroll_offset == 0 and self.hasFocus() and self._blink_on:
            size = {"small": 0.25, "medium": 0.5, "large": 1.0}.get(self.settings.get("cursor_size", "small"), 0.25)
            ch = max(2, int(self.ch * size))
            cx = 2 + scr.x * self.cw
            cy = 2 + scr.y * self.ch + self.ch - ch
            p.fillRect(cx, cy, self.cw, ch, self.fg_default)
        elif scr.cursor_visible and self.scroll_offset == 0 and not self.hasFocus():
            p.setPen(self.fg_default)
            p.drawRect(2 + scr.x * self.cw, 2 + scr.y * self.ch, self.cw - 1, self.ch - 1)

    # ------------------------------------------------------------------ zaznaczanie
    def _cell_at(self, pos):
        c = max(0, min(self.screen.cols, round((pos.x() - 2) / self.cw)))
        r = max(0, min(self.screen.rows - 1, (pos.y() - 2) // self.ch))
        return self.first_visible() + r, c

    def _sel_norm(self):
        if self.sel_start is None or self.sel_end is None or self.sel_start == self.sel_end:
            return None
        return tuple(sorted([self.sel_start, self.sel_end]))

    @staticmethod
    def _in_sel(sel, row, col):
        if sel is None:
            return False
        (r1, c1), (r2, c2) = sel
        if row < r1 or row > r2:
            return False
        if r1 == r2:
            return c1 <= col < c2
        if row == r1:
            return col >= c1
        if row == r2:
            return col < c2
        return True

    def has_selection(self):
        return self._sel_norm() is not None

    def selected_text(self):
        sel = self._sel_norm()
        if sel is None:
            return ""
        if self.screen.alt is not None:
            (r1, c1), (r2, c2) = sel
            out = []
            for r in range(r1, r2 + 1):
                line = self.screen.lines[r] if r < self.screen.rows else []
                s = c1 if r == r1 else 0
                e = c2 if r == r2 else len(line)
                out.append("".join(line[s:e]).rstrip())
            return "\n".join(out)
        return self.screen.text_range(*sel)

    def select_all(self):
        self.sel_start = (0, 0)
        self.sel_end = (self.screen.total_lines() - 1, self.screen.cols)
        self.update()

    def clear_selection(self):
        self.sel_start = self.sel_end = None
        self.update()

    def copy(self):
        t = self.selected_text()
        if t:
            QGuiApplication.clipboard().setText(t)
        self.clear_selection()
        return bool(t)

    def paste(self, text=None):
        t = text if text is not None else QGuiApplication.clipboard().text()
        if not t:
            return
        t = t.replace("\r\n", "\r").replace("\n", "\r")
        if self.screen.bracketed_paste:
            t = "\x1b[200~" + t + "\x1b[201~"
        self.send(t)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        if self.scroll_offset:
            self.scroll_offset = 0
            self._update_scrollbar()
            self.update()

    # ------------------------------------------------------------------ mysz
    def _mouse_report(self, e, button, release=False, motion=False):
        scr = self.screen
        c = max(1, min(scr.cols, (int(e.position().x()) - 2) // self.cw + 1))
        r = max(1, min(scr.rows, (int(e.position().y()) - 2) // self.ch + 1))
        code = button + (32 if motion else 0)
        if e.modifiers() & Qt.ShiftModifier:
            code += 4
        if e.modifiers() & Qt.ControlModifier:
            code += 16
        if scr.mouse_sgr:
            self.send(f"\x1b[<{code};{c};{r}{'m' if release else 'M'}")
        elif c < 224 and r < 224:
            b = 3 if release else code
            self.send("\x1b[M" + chr(32 + b) + chr(32 + c) + chr(32 + r))

    def _mouse_mode_active(self, e):
        return self.screen.mouse_mode and not (e.modifiers() & Qt.ShiftModifier)

    def mousePressEvent(self, e):
        self.setFocus()
        if self._mouse_mode_active(e):
            btn = {Qt.LeftButton: 0, Qt.MiddleButton: 1, Qt.RightButton: 2}.get(e.button())
            if btn is not None:
                self._mouse_report(e, btn)
            return
        if e.button() == Qt.LeftButton:
            self.sel_start = self.sel_end = self._cell_at(e.position().toPoint())
            self._selecting = True
            self.update()
        elif e.button() == Qt.RightButton:
            self.parent_window_right_click(e.globalPosition().toPoint())
        elif e.button() == Qt.MiddleButton:
            self.paste(QGuiApplication.clipboard().text(QGuiApplication.clipboard().Mode.Selection) or None)

    def parent_window_right_click(self, gpos):
        w = self.window()
        if hasattr(w, "terminal_right_click"):
            w.terminal_right_click(gpos)

    def mouseMoveEvent(self, e):
        if self._mouse_mode_active(e):
            if self.screen.mouse_mode in (1002, 1003) and (e.buttons() or self.screen.mouse_mode == 1003):
                btn = 0 if e.buttons() & Qt.LeftButton else 2 if e.buttons() & Qt.RightButton else 3
                self._mouse_report(e, btn, motion=True)
            return
        if self._selecting:
            self.sel_end = self._cell_at(e.position().toPoint())
            # przewijanie przy przeciąganiu poza widok
            if e.position().y() < 0:
                self._scroll_by(1)
            elif e.position().y() > self.height():
                self._scroll_by(-1)
            self.update()

    def mouseReleaseEvent(self, e):
        if self._mouse_mode_active(e):
            btn = {Qt.LeftButton: 0, Qt.MiddleButton: 1, Qt.RightButton: 2}.get(e.button())
            if btn is not None:
                self._mouse_report(e, btn, release=True)
            return
        if e.button() == Qt.LeftButton:
            self._selecting = False
            if self.has_selection():
                QGuiApplication.clipboard().setText(self.selected_text(), QGuiApplication.clipboard().Mode.Selection)

    def mouseDoubleClickEvent(self, e):
        if self._mouse_mode_active(e):
            return
        r, c = self._cell_at(e.position().toPoint())
        line, _ = self.screen.line_at(r) if self.screen.alt is None else (self.screen.lines[min(r, self.screen.rows - 1)], None)
        c = min(c, len(line) - 1)
        isword = lambda ch: ch.isalnum() or ch in "_-./~:@%+"  # noqa: E731
        if not line or not isword(line[c]):
            return
        s = c
        while s > 0 and isword(line[s - 1]):
            s -= 1
        t = c
        while t < len(line) and isword(line[t]):
            t += 1
        self.sel_start, self.sel_end = (r, s), (r, t)
        self.update()

    def _scroll_by(self, lines):
        h = len(self.screen.history) if self.screen.alt is None else 0
        self.scroll_offset = max(0, min(h, self.scroll_offset + lines))
        self._update_scrollbar()
        self.update()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if self.screen.mouse_mode and not (e.modifiers() & Qt.ShiftModifier):
            self._mouse_report(e, 64 if d > 0 else 65)
            return
        if self.screen.alt is not None:
            # program pełnoekranowy (less, man) — kółko jako strzałki
            key = ("\x1bOA" if self.screen.app_cursor else "\x1b[A") if d > 0 else ("\x1bOB" if self.screen.app_cursor else "\x1b[B")
            self.send(key * 3)
            return
        self._scroll_by(3 if d > 0 else -3)

    # ------------------------------------------------------------------ klawiatura
    def focusNextPrevChild(self, nxt):
        return False   # Tab trafia do terminala

    def event(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.ShortcutOverride:
            e.accept()   # wszystkie skróty idą do programu w terminalu
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        k = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        alt = bool(mods & Qt.AltModifier)
        # skróty okna
        if ctrl and shift and k == Qt.Key_C:
            self.copy()
            return
        if ctrl and shift and k == Qt.Key_V or shift and k == Qt.Key_Insert:
            self.paste()
            return
        if shift and k in (Qt.Key_PageUp, Qt.Key_PageDown):
            self._scroll_by(self.screen.rows - 1 if k == Qt.Key_PageUp else -(self.screen.rows - 1))
            return
        if self.has_selection() and k in (Qt.Key_Return, Qt.Key_Enter) and not self._selecting:
            # tryb szybkiej edycji: Enter kopiuje zaznaczenie
            self.copy()
            return
        self.clear_selection() if self.has_selection() else None
        seq = None
        if k in CURSOR_KEYS:
            ch = CURSOR_KEYS[k]
            mod = 1 + (1 if shift else 0) + (2 if alt else 0) + (4 if ctrl else 0)
            if mod > 1:
                seq = f"\x1b[1;{mod}{ch}"
            else:
                seq = ("\x1bO" if self.screen.app_cursor else "\x1b[") + ch
        elif k in KEYS:
            seq = KEYS[k]
            if k == Qt.Key_Backspace and ctrl:
                seq = "\x08"
            if k == Qt.Key_Tab and shift:
                seq = "\x1b[Z"
            if k == Qt.Key_Backtab:
                seq = "\x1b[Z"
            if (ctrl or shift or alt) and seq.startswith("\x1b[") and seq.endswith("~"):
                mod = 1 + (1 if shift else 0) + (2 if alt else 0) + (4 if ctrl else 0)
                seq = seq[:-1] + f";{mod}~"
        elif k == Qt.Key_Backtab:
            seq = "\x1b[Z"
        elif ctrl and Qt.Key_A <= k <= Qt.Key_Z:
            seq = chr(k - Qt.Key_A + 1)
        elif ctrl and k in (Qt.Key_BracketLeft, Qt.Key_Backslash, Qt.Key_BracketRight, Qt.Key_AsciiCircum, Qt.Key_Underscore):
            seq = {Qt.Key_BracketLeft: "\x1b", Qt.Key_Backslash: "\x1c", Qt.Key_BracketRight: "\x1d",
                   Qt.Key_AsciiCircum: "\x1e", Qt.Key_Underscore: "\x1f"}[k]
        elif ctrl and k == Qt.Key_Space:
            seq = "\x00"
        else:
            seq = e.text()
        if not seq:
            return
        if alt and len(seq) == 1:
            seq = "\x1b" + seq
        self.scroll_to_bottom()
        self.send(seq)

    def inputMethodEvent(self, e):
        t = e.commitString()
        if t:
            self.send(t)
