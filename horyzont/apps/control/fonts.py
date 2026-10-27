"""Czcionki: lista zainstalowanych krojów, podgląd, instalacja nowych."""
import os
import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QHBoxLayout

from ...common import dialogs
from ...common.window import HWindow
from ...i18n import plain, tr
from .folderwin import FolderWindow, entry


class FontPreview(HWindow):
    def __init__(self, family):
        super().__init__(family, "file_font")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        pr = QPushButton(plain("np_print").split("\t")[0].replace("&", ""))
        pr.setEnabled(False)
        bar.addWidget(pr)
        bar.addStretch(1)
        lay.addLayout(bar)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        w = QWidget()
        w.setStyleSheet("background: #ffffff;")
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 12, 16, 12)
        title = QLabel(family)
        f = QFont(family)
        f.setPixelSize(30)
        title.setFont(f)
        v.addWidget(title)
        styles = QFontDatabase.styles(family)
        v.addWidget(QLabel(plain("fonts_styles") + " " + ", ".join(styles)))
        abc = QLabel("abcdefghijklmnopqrstuvwxyz ąćęłńóśźż\nABCDEFGHIJKLMNOPQRSTUVWXYZ ĄĆĘŁŃÓŚŹŻ\n1234567890.:,;(\"*!?')")
        f2 = QFont(family)
        f2.setPixelSize(18)
        abc.setFont(f2)
        v.addWidget(abc)
        for size in (12, 18, 24, 36, 48, 60, 72):
            l = QLabel(f"{size}  " + plain("fonts_sample"))
            ff = QFont(family)
            ff.setPixelSize(size)
            l.setFont(ff)
            v.addWidget(l)
        v.addStretch(1)
        sa.setWidget(w)
        lay.addWidget(sa, 1)
        self.resize(620, 560)


class FontsWindow(FolderWindow):
    title_key = "fonts"
    icon = "fonts"
    view_mode = "icons"

    def load_items(self):
        items = []
        for fam in sorted(QFontDatabase.families(), key=str.lower):
            if QFontDatabase.isPrivateFamily(fam):
                continue
            n = len(QFontDatabase.styles(fam))
            items.append(entry(fam, "file_font", plain("fonts_type"), tr("fonts_n_styles", n), key=fam,
                               details=[tr("fonts_n_styles", n)]))
        return items

    def fill_tasks(self, pane, sel):
        s = pane.add_section(plain("fonts_tasks"), special=True)
        s.add_link("new_folder", plain("fonts_install").replace("&", ""), self.install)
        if sel:
            s.add_link("file_font", plain("fonts_preview"), lambda: self.activate(sel[0]))
        self.other_places(pane)
        self.details(pane, sel)

    def activate(self, it):
        w = FontPreview(it.label)
        w.show()
        self._previews = getattr(self, "_previews", []) + [w]

    def item_menu(self, m, it):
        f = m.addAction(tr("open"), lambda: self.activate(it))
        fn = f.font()
        fn.setBold(True)
        f.setFont(fn)

    def install(self):
        files = dialogs.open_files(self, plain("fonts_install").replace("&", ""), os.path.expanduser("~"),
                                   plain("fonts_filter"))
        if not files:
            return
        dest = os.path.expanduser("~/.local/share/fonts")
        os.makedirs(dest, exist_ok=True)
        for f in files:
            shutil.copy2(f, dest)
            QFontDatabase.addApplicationFont(os.path.join(dest, os.path.basename(f)))
        if shutil.which("fc-cache"):
            subprocess.Popen(["fc-cache", "-f", dest])
        self.refresh()


def open_fonts(page=None, parent=None):
    return FontsWindow()
