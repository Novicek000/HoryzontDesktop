"""Wiersz polecenia — okno konsoli w klasycznym stylu (czarne tło, szary tekst) z powłoką bash."""
import os
import pwd
import shlex
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QMenu, QPushButton, QRadioButton, QScrollBar,
                               QSpinBox, QVBoxLayout, QWidget)

from ... import config
from ...common import dialogs, single
from ...common.app import make_app
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ..control.common import AppletDialog
from .widget import CLASSIC_PALETTE, TerminalView

DEFAULTS = {
    "font": "", "font_size": 10, "font_bold": False, "cols": 80, "rows": 25, "scrollback": 3000,
    "fg": 7, "bg": 0, "palette": CLASSIC_PALETTE, "cursor_size": "small", "quick_edit": True,
    "classic_prompt": True, "shell": "",
}


def settings():
    s = dict(DEFAULTS)
    s.update(config.get("terminal", {}) or {})
    if not s["font"]:
        fams = set(QFontDatabase.families())
        for cand in ("Lucida Console", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", "Source Code Pro",
                     "Cascadia Mono", "Monospace"):
            if cand in fams:
                s["font"] = cand
                break
        else:
            s["font"] = "Monospace"
    return s


def save_settings(s):
    out = {k: v for k, v in s.items() if DEFAULTS.get(k) != v}
    config.set("terminal", out)


def user_shell():
    sh = os.environ.get("SHELL")
    if not sh:
        try:
            sh = pwd.getpwuid(os.getuid()).pw_shell
        except KeyError:
            sh = "/bin/bash"
    return sh or "/bin/bash"


def os_pretty():
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            vals = dict(l.rstrip("\n").split("=", 1) for l in f if "=" in l)
        return vals.get("PRETTY_NAME", "Linux").strip('"')
    except OSError:
        return "Linux"


def banner():
    return f"{os_pretty()} [Horyzont {config.VERSION}]\n(C) {plain('cmd_banner_line')}\n\n"


def _rcfile(classic):
    """Plik startowy bash: wczytuje ~/.bashrc i (opcjonalnie) ustawia monit w stylu „ścieżka>”."""
    path = os.path.join(config.CACHE_DIR, "cmd-bashrc")
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    lines = ["[ -f /etc/bashrc ] && . /etc/bashrc", "[ -f ~/.bashrc ] && . ~/.bashrc"]
    if classic:
        lines += [
            "PROMPT_COMMAND='printf \"\\033]0;%s\\007\" \"Wiersz polecenia\"'",
            "PS1='\\w>'",
            "alias cls='clear'",
            "alias dir='ls -la --group-directories-first'",
            "alias copy='cp -i'",
            "alias move='mv -i'",
            "alias del='rm -i'",
            "alias ren='mv -i'",
            "alias md='mkdir'",
            "alias rd='rmdir'",
            "alias ver='cat /etc/os-release | head -2'",
        ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


class CmdWindow(HWindow):
    def __init__(self, app_ctl, cwd=None, command=None):
        super().__init__(plain("cmd_title"), "cmd")
        self.ctl = app_ctl
        self.s = settings()
        lay = QHBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.term = TerminalView(self.s)
        self.sb = QScrollBar(Qt.Vertical)
        self.term.attach_scrollbar(self.sb)
        lay.addWidget(self.term, 1)
        lay.addWidget(self.sb)
        self.term.title_changed.connect(self._title)
        self.term.finished.connect(self._finished)
        w, h = self.term.size_for(self.s["cols"], self.s["rows"])
        l, t, r, b = self._outer.contentsMargins().left(), self._outer.contentsMargins().top(), \
            self._outer.contentsMargins().right(), self._outer.contentsMargins().bottom()
        self.resize(w + self.sb.sizeHint().width() + l + r, h + t + b)
        shell = self.s.get("shell") or user_shell()
        env = dict(os.environ)
        if command:
            argv = [shell, "-c", command + "; echo; read -n1 -s -r -p \"" + plain("cmd_press_key") + "\""] \
                if isinstance(command, str) else list(command)
            self.term.start(argv, cwd, env)
        else:
            argv = [shell]
            if os.path.basename(shell) == "bash":
                argv = [shell, "--rcfile", _rcfile(self.s.get("classic_prompt", True)), "-i"]
            self.term.start(argv, cwd or os.path.expanduser("~"), env, banner())
        self.term.setFocus()

    def _title(self, t):
        if t and t != plain("cmd_title"):
            self.setWindowTitle(f"{plain('cmd_title')} - {t}")
        else:
            self.setWindowTitle(plain("cmd_title"))

    def _finished(self, code):
        self.close()

    def closeEvent(self, e):
        busy = self.term.busy_child()
        if busy and busy not in ("bash", "sh", "zsh", "fish"):
            if dialogs.message(self, plain("cmd_title"), tr("cmd_close_busy", busy), "warning", ("yes", "no")) != "yes":
                e.ignore()
                return
        self.term.terminate()
        super().closeEvent(e)

    # ------------------------------------------------------------------ menu systemowe
    def _extend_system_menu(self, m):
        edit = QMenu(plain("cmd_edit"), m)
        edit.addAction(plain("cmd_mark"), lambda: self.term.setFocus())
        a = edit.addAction(plain("copy").replace("&", "") + "\tEnter", self.term.copy)
        a.setEnabled(self.term.has_selection())
        edit.addAction(plain("paste").replace("&", ""), self.term.paste)
        edit.addAction(plain("select_all").replace("&", ""), self.term.select_all)
        edit.addAction(plain("cmd_find"), self.find)
        m.addSeparator()
        m.addMenu(edit)
        m.addAction(plain("cmd_new_window"), lambda: self.ctl.new_window(self.term.cwd()))
        m.addAction(plain("cmd_defaults"), lambda: self.properties(defaults=True))
        m.addAction(plain("properties").replace("&", ""), self.properties)

    def terminal_right_click(self, gpos):
        if self.s.get("quick_edit", True):
            if self.term.has_selection():
                self.term.copy()
            else:
                self.term.paste()
            return
        m = QMenu(self)
        m.addAction(plain("cmd_mark"), lambda: None)
        m.addAction(plain("copy").replace("&", ""), self.term.copy).setEnabled(self.term.has_selection())
        m.addAction(plain("paste").replace("&", ""), self.term.paste)
        m.addAction(plain("select_all").replace("&", ""), self.term.select_all)
        m.addAction(plain("cmd_find"), self.find)
        m.exec(gpos)

    def find(self):
        text = dialogs.ask_text(self, plain("cmd_find").rstrip("."), plain("cmd_find_what"), "", "search")
        if not text:
            return
        scr = self.term.screen
        low = text.lower()
        for idx in range(scr.total_lines() - 1, -1, -1):
            line, _ = scr.line_at(idx)
            s = "".join(c if c else "" for c in line).lower()
            pos = s.find(low)
            if pos >= 0:
                self.term.sel_start, self.term.sel_end = (idx, pos), (idx, pos + len(text))
                h = len(scr.history)
                self.term.scroll_offset = max(0, h - idx + scr.rows // 2) if idx < h else 0
                self.term.scroll_offset = min(self.term.scroll_offset, h)
                self.term._update_scrollbar()
                self.term.update()
                return
        dialogs.message(self, plain("cmd_title"), tr("cmd_not_found", text), "info")

    def properties(self, defaults=False):
        d = CmdProperties(self.s, self, defaults)
        if d.exec():
            self.s = d.result_settings
            save_settings(self.s)
            self.term.apply_settings(self.s)


class ColorSwatches(QWidget):
    def __init__(self, palette, pick, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.pick = pick
        self.sel = 0
        self.setFixedSize(16 * 20 + 2, 22)

    def paintEvent(self, e):
        p = QPainter(self)
        for i, c in enumerate(self.palette_):
            r = (1 + i * 20, 1, 18, 18)
            p.fillRect(*r, QColor(c))
            p.setPen(QColor("#000000"))
            p.drawRect(r[0], r[1], r[2] - 1, r[3] - 1)
            if i == self.sel:
                p.setPen(QColor("#ffffff"))
                p.drawRect(r[0] + 2, r[1] + 2, r[2] - 5, r[3] - 5)

    def mousePressEvent(self, e):
        i = int(e.position().x() - 1) // 20
        if 0 <= i < 16:
            self.sel = i
            self.pick(i)
            self.update()


class CmdProperties(AppletDialog):
    def __init__(self, s, parent=None, defaults=False):
        super().__init__(plain("cmd_props_title") if not defaults else plain("cmd_defaults"), "cmd", parent, apply=False)
        self.s = dict(s)
        self.result_settings = self.s
        # Opcje
        w, lay = self.add_tab(plain("cmd_tab_options"))
        g = QGroupBox(plain("cmd_cursor_size"))
        gl = QVBoxLayout(g)
        self.cur = {}
        bg = QButtonGroup(self)
        for k, lab in (("small", "cmd_small"), ("medium", "cmd_medium"), ("large", "cmd_large")):
            rb = QRadioButton(plain(lab))
            rb.setChecked(self.s.get("cursor_size") == k)
            bg.addButton(rb)
            gl.addWidget(rb)
            self.cur[k] = rb
        lay.addWidget(g)
        g2 = QGroupBox(plain("cmd_history"))
        g2l = QGridLayout(g2)
        g2l.addWidget(QLabel(plain("cmd_scrollback")), 0, 0)
        self.scrollback = QSpinBox()
        self.scrollback.setRange(100, 100000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(int(self.s.get("scrollback", 3000)))
        g2l.addWidget(self.scrollback, 0, 1)
        lay.addWidget(g2)
        g3 = QGroupBox(plain("cmd_edit_options"))
        g3l = QVBoxLayout(g3)
        self.quick = QCheckBox(plain("cmd_quick_edit"))
        self.quick.setChecked(self.s.get("quick_edit", True))
        self.classic = QCheckBox(plain("cmd_classic_prompt"))
        self.classic.setChecked(self.s.get("classic_prompt", True))
        g3l.addWidget(self.quick)
        g3l.addWidget(self.classic)
        lay.addWidget(g3)
        lay.addStretch(1)
        # Czcionka
        w2, l2 = self.add_tab(plain("cmd_tab_font"))
        row = QHBoxLayout()
        v = QVBoxLayout()
        v.addWidget(QLabel(plain("cmd_size")))
        self.size_list = QListWidget()
        for sz in (6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 36):
            self.size_list.addItem(str(sz))
        items = self.size_list.findItems(str(int(self.s.get("font_size", 10))), Qt.MatchExactly)
        if items:
            self.size_list.setCurrentItem(items[0])
        v.addWidget(self.size_list)
        row.addLayout(v)
        v2 = QVBoxLayout()
        v2.addWidget(QLabel(plain("cmd_font")))
        self.font_list = QListWidget()
        fams = [f for f in QFontDatabase.families() if QFontDatabase.isFixedPitch(f)]
        for f in sorted(set(fams)):
            self.font_list.addItem(f)
        it = self.font_list.findItems(self.s.get("font", ""), Qt.MatchExactly)
        if it:
            self.font_list.setCurrentItem(it[0])
        v2.addWidget(self.font_list)
        self.bold = QCheckBox(plain("cmd_bold"))
        self.bold.setChecked(self.s.get("font_bold", False))
        v2.addWidget(self.bold)
        row.addLayout(v2, 1)
        l2.addLayout(row, 1)
        self.preview = QLabel("~/Dokumenty> ls\nnotatka.txt  zdjęcia")
        self.preview.setMinimumHeight(70)
        l2.addWidget(QLabel(plain("cmd_preview")))
        l2.addWidget(self.preview)
        for wdg in (self.size_list, self.font_list):
            wdg.currentItemChanged.connect(lambda *_: self._update_preview())
        self.bold.toggled.connect(lambda *_: self._update_preview())
        # Układ
        w3, l3 = self.add_tab(plain("cmd_tab_layout"))
        g4 = QGroupBox(plain("cmd_window_size"))
        g4l = QGridLayout(g4)
        self.cols = QSpinBox()
        self.cols.setRange(20, 400)
        self.cols.setValue(int(self.s.get("cols", 80)))
        self.rows = QSpinBox()
        self.rows.setRange(5, 200)
        self.rows.setValue(int(self.s.get("rows", 25)))
        g4l.addWidget(QLabel(plain("cmd_width")), 0, 0)
        g4l.addWidget(self.cols, 0, 1)
        g4l.addWidget(QLabel(plain("cmd_height")), 1, 0)
        g4l.addWidget(self.rows, 1, 1)
        l3.addWidget(g4)
        l3.addWidget(QLabel(plain("cmd_layout_note")))
        l3.addStretch(1)
        # Kolory
        w4, l4 = self.add_tab(plain("cmd_tab_colors"))
        self.which_fg = QRadioButton(plain("cmd_screen_text"))
        self.which_bg = QRadioButton(plain("cmd_screen_bg"))
        self.which_fg.setChecked(True)
        l4.addWidget(self.which_fg)
        l4.addWidget(self.which_bg)
        self.sw = ColorSwatches(self.s["palette"], self._pick)
        self.sw.sel = int(self.s.get("fg", 7))
        self.which_fg.toggled.connect(lambda on: self._which())
        l4.addWidget(self.sw)
        reset = QPushButton(plain("cmd_classic_colors"))
        reset.clicked.connect(self._classic_colors)
        l4.addWidget(reset, 0, Qt.AlignLeft)
        l4.addWidget(QLabel(plain("cmd_preview")))
        self.color_preview = QLabel("~> echo Horyzont\nHoryzont")
        self.color_preview.setMinimumHeight(60)
        l4.addWidget(self.color_preview)
        l4.addStretch(1)
        self._update_preview()
        self.resize(400, 470)

    def _which(self):
        self.sw.sel = int(self.s["fg"] if self.which_fg.isChecked() else self.s["bg"])
        self.sw.update()

    def _pick(self, i):
        if self.which_fg.isChecked():
            self.s["fg"] = i
        else:
            self.s["bg"] = i
        self._update_preview()

    def _classic_colors(self):
        self.s["fg"], self.s["bg"], self.s["palette"] = 7, 0, list(CLASSIC_PALETTE)
        self._which()
        self._update_preview()

    def _update_preview(self):
        fam = self.font_list.currentItem().text() if self.font_list.currentItem() else self.s.get("font")
        size = self.size_list.currentItem().text() if self.size_list.currentItem() else str(self.s.get("font_size", 10))
        style = (f"font-family: '{fam}'; font-size: {size}pt; {'font-weight: bold;' if self.bold.isChecked() else ''}"
                 f"color: {self.s['palette'][int(self.s['fg'])]}; background: {self.s['palette'][int(self.s['bg'])]}; padding: 4px;")
        self.preview.setStyleSheet(style)
        self.color_preview.setStyleSheet(style)

    def apply(self):
        s = self.s
        s["cursor_size"] = next(k for k, rb in self.cur.items() if rb.isChecked()) if any(rb.isChecked() for rb in self.cur.values()) else "small"
        s["scrollback"] = self.scrollback.value()
        s["quick_edit"] = self.quick.isChecked()
        s["classic_prompt"] = self.classic.isChecked()
        if self.font_list.currentItem():
            s["font"] = self.font_list.currentItem().text()
        if self.size_list.currentItem():
            s["font_size"] = int(self.size_list.currentItem().text())
        s["font_bold"] = self.bold.isChecked()
        s["cols"] = self.cols.value()
        s["rows"] = self.rows.value()
        self.result_settings = s
        return True


class CmdApp:
    def __init__(self, app):
        self.app = app
        self.windows = []

    def new_window(self, cwd=None, command=None):
        w = CmdWindow(self, cwd, command)
        w.show()
        w.raise_()
        w.activateWindow()
        self.windows.append(w)
        w.closed.connect(lambda w=w: self._closed(w))
        return w

    def _closed(self, w):
        if w in self.windows:
            self.windows.remove(w)
        if not self.windows:
            QTimer.singleShot(0, self.app.quit)

    def handle(self, args):
        cwd = None
        command = None
        a = list(args)
        if "--cwd" in a:
            i = a.index("--cwd")
            cwd = a[i + 1] if i + 1 < len(a) else None
            del a[i:i + 2]
        if "--exec" in a:
            i = a.index("--exec")
            command = a[i + 1:]
            del a[i:]
        elif a and a[0] in ("/c", "/k", "-c"):
            command = " ".join(a[1:])
        self.new_window(cwd, command)


def main(args):
    app = make_app("cmd")
    if single.try_forward("cmd", args or ["--cwd", os.getcwd()], 200):
        return 0
    app.setQuitOnLastWindowClosed(False)
    ctl = CmdApp(app)
    server = single.Server("cmd", ctl.handle)  # noqa: F841
    ctl.handle(args)
    return app.exec()
