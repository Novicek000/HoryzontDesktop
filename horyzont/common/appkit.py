"""Wspólne drobiazgi dla programów dodatkowych (Kalkulator, Paint, WordPad, gry, multimedia)."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from ..i18n import lang_code


def T(pl, en):
    """Tekst w języku interfejsu (polski / angielski)."""
    return pl if lang_code() == "pl" else en


def act(menu, text, fn=None, shortcut=None, checkable=False, checked=False, icon=None):
    a = menu.addAction(text)
    if icon is not None:
        a.setIcon(icon)
    if checkable:
        a.setCheckable(True)
        a.setChecked(checked)
        if fn:
            a.toggled.connect(fn)
    elif fn:
        a.triggered.connect(lambda _=False: fn())
    if shortcut:
        a.setShortcut(QKeySequence(shortcut))
        a.setShortcutContext(Qt.WindowShortcut)
    return a


def help_menu(menubar, parent, title, icon, topic=None):
    m = menubar.addMenu(T("Pomo&c", "&Help"))

    def open_help():
        from . import launcher
        launcher.start_builtin("explorer", ["horyzont:help" + (":" + topic if topic else "")])

    act(m, T("&Tematy pomocy", "&Help Topics"), open_help, "F1")
    m.addSeparator()

    def about():
        from ..apps.about import show_about
        show_about(parent, title, icon)
    act(m, T("&Informacje o programie", "&About") + " " + title, about)
    return m


def run_app(app_id, handle, args, abspath=True):
    """Start programu z jedną instancją: kolejne uruchomienia przekazują argumenty do działającej."""
    from . import single
    from .app import make_app
    app = make_app(app_id)
    if abspath:
        args = [os.path.abspath(a) if a and not a.startswith("-") and os.path.exists(a) else a for a in args]
    if single.try_forward(app_id, args, 200):
        return 0
    server = single.Server(app_id, handle)  # noqa: F841 — musi żyć do końca programu
    app._horyzont_server = server
    handle(args)
    return app.exec()


def file_filter(*pairs):
    """file_filter((opis, "*.png *.jpg"), ...) -> napis filtra dla okna dialogowego."""
    return ";;".join(f"{d} ({p})" for d, p in pairs)
