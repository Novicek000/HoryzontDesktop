"""Okno "Informacje" (winver) — wspólne dla wszystkich programów."""
import platform

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import config
from ..common import sysctl
from ..common.window import HDialog
from ..i18n import plain, tr
from ..theme import iconcache
from ..theme.base import hgrad, vgrad
from ..theme.manager import current


class Banner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(78)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        t = current()
        sc = getattr(t, "sc", None) or {"accent_darker": "#0b4a52", "accent": "#1f8591", "accent_light": "#5cc6d0"}
        p.fillRect(r, hgrad(r, [(0, sc["accent_darker"]), (0.55, sc["accent"]), (1, sc["accent_light"])]))
        p.drawPixmap(18, 11, iconcache.pixmap("logo", 56))
        f = QFont(t.font("title_big"))
        f.setPixelSize(30)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 90))
        p.drawText(QRect(87, 1, r.width() - 90, r.height()), Qt.AlignVCenter | Qt.AlignLeft, "Horyzont")
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(86, 0, r.width() - 90, r.height()), Qt.AlignVCenter | Qt.AlignLeft, "Horyzont")
        f2 = t.font("normal")
        f2.setItalic(True)
        p.setFont(f2)
        p.drawText(QRect(0, 0, r.width() - 12, r.height() - 8), Qt.AlignRight | Qt.AlignBottom, "dla Fedory")
        line = QRect(0, r.height() - 3, r.width(), 3)
        p.fillRect(line, hgrad(line, [(0, "#f6ad3e"), (1, "#ffffff00")]))


def show_about(parent, app_name, icon):
    d = HDialog(tr("about_title", app_name), icon, parent, help_button=False)
    lay = QVBoxLayout(d.body())
    lay.setContentsMargins(0, 0, 0, 10)
    lay.addWidget(Banner())
    row = QHBoxLayout()
    row.setContentsMargins(16, 12, 16, 0)
    ic = QLabel()
    ic.setPixmap(iconcache.pixmap(icon, 32))
    row.addWidget(ic, 0, Qt.AlignTop)
    info = QLabel(tr("about_text", config.VERSION, sysctl.os_name(), platform.release()) + "\n\n" +
                  tr("about_licensed", sysctl.user_full_name()) + "\n\n" +
                  tr("about_mem", sysctl.human_size(sysctl.mem_total())))
    info.setWordWrap(True)
    row.addWidget(info, 1)
    lay.addLayout(row)
    btn = QPushButton(plain("ok"))
    btn.setDefault(True)
    btn.clicked.connect(d.accept)
    h = QHBoxLayout()
    h.addStretch(1)
    h.addWidget(btn)
    h.setContentsMargins(0, 0, 12, 0)
    lay.addLayout(h)
    d.setFixedWidth(420)
    d.adjustSize()
    d.exec()


def main(args):
    from ..common.app import make_app
    app = make_app("winver")
    show_about(None, "Horyzont", "logo")
    return 0
