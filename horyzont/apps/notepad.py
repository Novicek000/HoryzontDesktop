"""Notatnik — prosty edytor tekstu."""
import codecs
import datetime
import os
import sys

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QFont, QFontDatabase, QKeySequence,
                           QTextCursor, QTextDocument, QTextOption)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFontDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMenuBar,
                               QPlainTextEdit, QPushButton, QRadioButton,
                               QStatusBar, QVBoxLayout, QWidget)

from .. import config
from ..common import dialogs, single
from ..common.app import make_app
from ..common.window import HDialog, HWindow
from ..i18n import lang_code, plain, tr
from ..theme import iconcache
from ..theme.manager import mono_family

ENCODINGS = [
    ("ANSI", "cp1250" if lang_code() == "pl" else "cp1252"),
    ("Unicode", "utf-16-le"),
    ("Unicode big endian", "utf-16-be"),
    ("UTF-8", "utf-8"),
]


def detect_and_decode(data):
    """Zwraca (tekst, kodowanie, czy CRLF)."""
    enc = None
    if data.startswith(codecs.BOM_UTF8):
        text, enc = data[3:].decode("utf-8", "replace"), "utf-8-bom"
    elif data.startswith(codecs.BOM_UTF16_LE):
        text, enc = data[2:].decode("utf-16-le", "replace"), "utf-16-le"
    elif data.startswith(codecs.BOM_UTF16_BE):
        text, enc = data[2:].decode("utf-16-be", "replace"), "utf-16-be"
    else:
        try:
            text, enc = data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            ansi = ENCODINGS[0][1]
            text, enc = data.decode(ansi, "replace"), ansi
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, enc, crlf


def encode(text, enc, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    if enc == "utf-8-bom":
        return codecs.BOM_UTF8 + text.encode("utf-8")
    if enc == "utf-16-le":
        return codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    if enc == "utf-16-be":
        return codecs.BOM_UTF16_BE + text.encode("utf-16-be")
    return text.encode(enc, "replace")


class FindDialog(HDialog):
    def __init__(self, editor, replace=False):
        super().__init__(plain("np_replace_title" if replace else "np_find_title"), "", editor, help_button=True)
        self.editor = editor
        self.replace_mode = replace
        g = QGridLayout(self.body())
        g.setContentsMargins(10, 10, 10, 10)
        l1 = QLabel(tr("np_find_what"))
        self.what = QLineEdit(editor.last_find)
        l1.setBuddy(self.what)
        g.addWidget(l1, 0, 0)
        g.addWidget(self.what, 0, 1)
        r = 1
        if replace:
            l2 = QLabel(tr("np_replace_with"))
            self.repl = QLineEdit()
            l2.setBuddy(self.repl)
            g.addWidget(l2, 1, 0)
            g.addWidget(self.repl, 1, 1)
            r = 2
        self.case = QCheckBox(tr("np_match_case"))
        self.case.setChecked(editor.last_case)
        g.addWidget(self.case, r + 1, 0, 1, 2)
        if not replace:
            box = QGroupBox(plain("np_direction"))
            bl = QHBoxLayout(box)
            self.up = QRadioButton(tr("np_dir_up"))
            self.down = QRadioButton(tr("np_dir_down"))
            self.down.setChecked(not editor.last_up)
            self.up.setChecked(editor.last_up)
            bl.addWidget(self.up)
            bl.addWidget(self.down)
            g.addWidget(box, r, 1, 2, 1, Qt.AlignRight)
        col = QVBoxLayout()
        self.next_btn = QPushButton(tr("np_find_next_btn"))
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self.find_next)
        col.addWidget(self.next_btn)
        if replace:
            b = QPushButton(tr("np_replace_btn"))
            b.clicked.connect(self.replace_one)
            col.addWidget(b)
            b = QPushButton(tr("np_replace_all"))
            b.clicked.connect(self.replace_all)
            col.addWidget(b)
        c = QPushButton(plain("cancel"))
        c.clicked.connect(self.close)
        col.addWidget(c)
        col.addStretch(1)
        g.addLayout(col, 0, 2, 4, 1)
        self.what.textChanged.connect(lambda t: self.next_btn.setEnabled(bool(t)))
        self.next_btn.setEnabled(bool(self.what.text()))
        self.what.selectAll()
        self.setFixedSize(self.sizeHint())

    def _sync(self):
        self.editor.last_find = self.what.text()
        self.editor.last_case = self.case.isChecked()
        if not self.replace_mode:
            self.editor.last_up = self.up.isChecked()

    def find_next(self):
        self._sync()
        return self.editor.find_next()

    def replace_one(self):
        self._sync()
        cur = self.editor.text.textCursor()
        sel = cur.selectedText()
        what = self.what.text()
        same = sel == what if self.case.isChecked() else sel.lower() == what.lower()
        if cur.hasSelection() and same:
            cur.insertText(self.repl.text())
        self.editor.find_next()

    def replace_all(self):
        self._sync()
        doc = self.editor.text.document()
        flags = QTextDocument.FindCaseSensitively if self.case.isChecked() else QTextDocument.FindFlags()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        n = 0
        c = doc.find(self.what.text(), 0, flags)
        while not c.isNull():
            c.insertText(self.repl.text())
            n += 1
            c = doc.find(self.what.text(), c.position(), flags)
        cur.endEditBlock()


class NotepadWindow(HWindow):
    def __init__(self, ctl, path=None):
        super().__init__("", "notepad")
        self.ctl = ctl
        self.path = None
        self.encoding = "utf-8"
        self.crlf = False
        self.last_find = ""
        self.last_case = False
        self.last_up = False
        self._find_dlg = None
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.text = QPlainTextEdit()
        self.text.setFrameShape(QPlainTextEdit.NoFrame)
        self.text.setStyleSheet("QPlainTextEdit { border-top: 1px solid #a3b3b5; }")
        lay.addWidget(self.text, 1)
        self.status = QStatusBar()
        self.pos_label = QLabel()
        self.pos_label.setMinimumWidth(140)
        self.status.addPermanentWidget(self.pos_label)
        lay.addWidget(self.status)
        self._build_menus()
        self._apply_font()
        self.set_wrap(config.get("notepad_wrap", False))
        self.text.cursorPositionChanged.connect(self._update_pos)
        self.text.document().modificationChanged.connect(lambda *_: self._update_title())
        self.setAcceptDrops(True)
        self.resize(640, 460)
        if path:
            self.load(path)
        self._update_title()
        self._update_pos()

    # ------------------------------------------------------------ menu
    def _build_menus(self):
        mb = self.menubar

        def act(menu, key, fn, shortcut=None):
            a = menu.addAction(tr(key))
            a.triggered.connect(fn)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutContext(Qt.WindowShortcut)
            return a

        m = mb.addMenu(tr("menu_file"))
        act(m, "np_new", self.new, "Ctrl+N")
        act(m, "np_open", self.open_dialog, "Ctrl+O")
        act(m, "np_save", self.save, "Ctrl+S")
        act(m, "np_save_as", self.save_as)
        m.addSeparator()
        act(m, "np_page_setup", self.page_setup)
        act(m, "np_print", self.print_doc, "Ctrl+P")
        m.addSeparator()
        act(m, "np_exit", self.close)
        m = mb.addMenu(tr("menu_edit"))
        self.a_undo = act(m, "np_undo", self.text.undo, "Ctrl+Z")
        m.addSeparator()
        self.a_cut = act(m, "np_cut", self.text.cut, "Ctrl+X")
        self.a_copy = act(m, "np_copy", self.text.copy, "Ctrl+C")
        self.a_paste = act(m, "np_paste", self.text.paste, "Ctrl+V")
        self.a_del = act(m, "np_delete", lambda: self.text.textCursor().removeSelectedText(), "Del")
        m.addSeparator()
        self.a_find = act(m, "np_find", lambda: self.show_find(False), "Ctrl+F")
        self.a_find_next = act(m, "np_find_next", self.find_next_or_dialog, "F3")
        self.a_replace = act(m, "np_replace", lambda: self.show_find(True), "Ctrl+H")
        self.a_goto = act(m, "np_goto", self.goto_line, "Ctrl+G")
        m.addSeparator()
        act(m, "np_select_all", self.text.selectAll, "Ctrl+A")
        act(m, "np_time_date", self.insert_time, "F5")
        m.aboutToShow.connect(self._update_edit_menu)
        m = mb.addMenu(tr("menu_format"))
        self.a_wrap = m.addAction(tr("np_word_wrap"))
        self.a_wrap.setCheckable(True)
        self.a_wrap.toggled.connect(self.set_wrap)
        act(m, "np_font", self.choose_font)
        m = mb.addMenu(tr("menu_view"))
        self.a_status = m.addAction(tr("np_status_bar"))
        self.a_status.setCheckable(True)
        self.a_status.setChecked(config.get("notepad_statusbar", False))
        self.a_status.toggled.connect(self._toggle_status)
        m = mb.addMenu(tr("menu_help"))
        act(m, "np_help_topics", lambda: _open_help())
        m.addSeparator()
        act(m, "np_about", self.about)

    def _update_edit_menu(self):
        has_sel = self.text.textCursor().hasSelection()
        self.a_cut.setEnabled(has_sel)
        self.a_copy.setEnabled(has_sel)
        self.a_del.setEnabled(has_sel)
        self.a_undo.setEnabled(self.text.document().isUndoAvailable())
        self.a_paste.setEnabled(QApplication.clipboard().text() != "")
        has_text = not self.text.document().isEmpty()
        self.a_find.setEnabled(has_text)
        self.a_find_next.setEnabled(has_text)
        self.a_goto.setEnabled(not self.a_wrap.isChecked())

    # ------------------------------------------------------------ stan
    def display_name(self):
        return os.path.basename(self.path) if self.path else plain("untitled")

    def _update_title(self):
        self.setWindowTitle(f"{self.display_name()} - {plain('notepad')}")

    def _update_pos(self):
        c = self.text.textCursor()
        self.pos_label.setText("   " + tr("np_status", c.blockNumber() + 1, c.positionInBlock() + 1))

    def _toggle_status(self, v):
        config.set("notepad_statusbar", v)
        self.status.setVisible(v and not self.a_wrap.isChecked())

    def set_wrap(self, on):
        self.a_wrap.blockSignals(True)
        self.a_wrap.setChecked(on)
        self.a_wrap.blockSignals(False)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth if on else QPlainTextEdit.NoWrap)
        config.set("notepad_wrap", on)
        # w klasycznym Notatniku pasek stanu jest niedostępny przy zawijaniu wierszy
        self.a_status.setEnabled(not on)
        self.status.setVisible(self.a_status.isChecked() and not on)

    def _apply_font(self):
        spec = config.get("notepad_font", "Lucida Console,10")
        fam, _, size = spec.partition(",")
        f = QFont(fam if fam in QFontDatabase.families() else mono_family())
        try:
            f.setPointSize(int(size or 10))
        except ValueError:
            f.setPointSize(10)
        self.text.setFont(f)

    def choose_font(self):
        dlg = HDialog(plain("np_font"), "", self, help_button=True)
        fd = QFontDialog(self.text.font(), dlg)
        fd.setOption(QFontDialog.DontUseNativeDialog, True)
        fd.setWindowFlags(Qt.Widget)
        lay = QVBoxLayout(dlg.body())
        lay.addWidget(fd)
        fd.finished.connect(dlg.done)
        if dlg.exec() == QDialog.Accepted:
            f = fd.selectedFont()
            config.set("notepad_font", f"{f.family()},{f.pointSize()}")
            self.text.setFont(f)

    # ------------------------------------------------------------ pliki
    def maybe_save(self):
        if not self.text.document().isModified():
            return True
        if not self.path and self.text.document().isEmpty():
            return True
        ans = dialogs.message(self, plain("notepad"), tr("np_save_changes", self.path or plain("untitled")),
                              "warning", ("yes", "no", "cancel"))
        if ans == "yes":
            return self.save()
        return ans == "no"

    def new(self):
        if not self.maybe_save():
            return
        self.text.clear()
        self.path = None
        self.encoding = "utf-8"
        self.crlf = False
        self.text.document().setModified(False)
        self._update_title()

    def open_dialog(self):
        if not self.maybe_save():
            return
        start = os.path.dirname(self.path) if self.path else config.user_dir("DOCUMENTS")
        f = dialogs.open_file(self, plain("open"), start, f"{plain('np_text_files')};;{plain('np_all_files')}")
        if f:
            self.load(f)

    def load(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            if not os.path.exists(path):
                # jak w klasycznym Notatniku: propozycja utworzenia nowego pliku
                if dialogs.message(self, plain("notepad"), tr("np_create_new", os.path.basename(path)), "question",
                                   ("yes", "no", "cancel")) == "yes":
                    try:
                        open(path, "w").close()
                        return self.load(path)
                    except OSError:
                        pass
                return
            dialogs.message(self, plain("notepad"), tr("np_open_fail", path), "error")
            return
        text, enc, crlf = detect_and_decode(data)
        self.text.setPlainText(text)
        self.path = os.path.abspath(path)
        self.encoding = enc
        self.crlf = crlf
        self.text.document().setModified(False)
        if text.startswith(".LOG"):
            c = self.text.textCursor()
            c.movePosition(QTextCursor.End)
            c.insertText("\n" + self._time_str() + "\n")
            self.text.setTextCursor(c)
        self._update_title()
        from ..common.launcher import add_recent_document
        add_recent_document(self.path)

    def save(self):
        if not self.path:
            return self.save_as()
        return self._write(self.path, self.encoding)

    def save_as(self):
        start = self.path or os.path.join(config.user_dir("DOCUMENTS"), "*.txt")
        extra = QWidget()
        h = QHBoxLayout(extra)
        h.setContentsMargins(4, 0, 4, 0)
        combo = QComboBox()
        el = QLabel(tr("np_encoding"))
        el.setBuddy(combo)
        h.addWidget(el)
        for label, enc in ENCODINGS:
            combo.addItem(label, enc)
        cur = {"utf-8-bom": "utf-8"}.get(self.encoding, self.encoding)
        idx = max(0, combo.findData(cur))
        combo.setCurrentIndex(idx)
        h.addWidget(combo)
        h.addStretch(1)
        f, flt = dialogs.save_file(self, plain("save_as"), os.path.dirname(start) if self.path else config.user_dir("DOCUMENTS"),
                                   f"{plain('np_text_files')};;{plain('np_all_files')}",
                                   os.path.basename(self.path) if self.path else "*.txt", extra)
        if not f:
            return False
        if flt.startswith(plain("np_text_files")) and not os.path.splitext(f)[1]:
            f += ".txt"
        return self._write(f, combo.currentData())

    def _write(self, path, enc):
        try:
            data = encode(self.text.toPlainText(), enc, self.crlf)
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError as e:
            dialogs.message(self, plain("notepad"), tr("np_save_fail", path, str(e)), "error")
            return False
        self.path = os.path.abspath(path)
        self.encoding = enc
        self.text.document().setModified(False)
        self._update_title()
        return True

    def page_setup(self):
        from PySide6.QtPrintSupport import QPageSetupDialog, QPrinter
        if not hasattr(self, "_printer"):
            self._printer = QPrinter()
        QPageSetupDialog(self._printer, self).exec()

    def print_doc(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        if not hasattr(self, "_printer"):
            self._printer = QPrinter()
        d = QPrintDialog(self._printer, self)
        if d.exec() == QDialog.Accepted:
            doc = self.text.document().clone()
            doc.setDefaultFont(self.text.font())
            doc.print_(self._printer)

    # ------------------------------------------------------------ edycja
    def _time_str(self):
        now = datetime.datetime.now()
        return now.strftime("%H:%M %Y-%m-%d")

    def insert_time(self):
        self.text.insertPlainText(self._time_str())

    def show_find(self, replace):
        if self._find_dlg is not None:
            self._find_dlg.close()
        sel = self.text.textCursor().selectedText()
        if sel and " " not in sel:
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
            dialogs.message(self._find_dlg or self, plain("notepad"), tr("np_not_found", self.last_find), "info")
            return False
        return True

    def goto_line(self):
        dlg = HDialog(plain("np_goto_title"), "", self, help_button=True)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(10, 10, 10, 10)
        le = QLineEdit(str(self.text.textCursor().blockNumber() + 1))
        ll = QLabel(tr("np_line_number"))
        ll.setBuddy(le)
        lay.addWidget(ll)
        le.selectAll()
        lay.addWidget(le)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ca = QPushButton(plain("cancel"))
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        ca.clicked.connect(dlg.reject)

        def go():
            try:
                n = int(le.text())
            except ValueError:
                return
            if n < 1 or n > self.text.document().blockCount():
                dialogs.message(dlg, plain("np_goto_title"), plain("np_line_beyond"), "")
                return
            block = self.text.document().findBlockByNumber(n - 1)
            c = self.text.textCursor()
            c.setPosition(block.position())
            self.text.setTextCursor(c)
            dlg.accept()
        ok.clicked.connect(go)
        dlg.setFixedSize(260, dlg.sizeHint().height())
        dlg.exec()

    def about(self):
        from .about import show_about
        show_about(self, plain("notepad"), "notepad")

    # ------------------------------------------------------------ zdarzenia
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls and self.maybe_save():
            self.load(urls[0])

    def closeEvent(self, e):
        if self.maybe_save():
            if self._find_dlg is not None:
                self._find_dlg.close()
            e.accept()
            super().closeEvent(e)
        else:
            e.ignore()


def _open_help():
    from ..common import launcher
    launcher.start_builtin("explorer", ["horyzont:help"])


class NotepadApp:
    def __init__(self):
        self.windows = []

    def handle(self, args):
        files = [a for a in args if not a.startswith("-")] or [None]
        for f in files:
            w = NotepadWindow(self, f)
            n = len(self.windows)
            w.move(80 + 24 * (n % 8), 60 + 24 * (n % 8))
            w.show()
            w.raise_()
            w.activateWindow()
            self.windows.append(w)
            w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)


def main(args):
    app = make_app("notepad")
    args = [os.path.abspath(a) if not a.startswith("-") else a for a in args]
    if single.try_forward("notepad", args, 200):
        return 0
    ctl = NotepadApp()
    server = single.Server("notepad", ctl.handle)
    ctl.handle(args)
    return app.exec()
