"""Wspólny start aplikacji Horyzont."""
import os
import signal
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ..theme import manager


def make_app(app_id, argv=None):
    """Tworzy QApplication z identyfikatorem okna ``horyzont-<app_id>``."""
    if argv is None:
        argv = sys.argv
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("horyzont-" + app_id)
    app.setOrganizationName("Horyzont")
    # na Waylandzie z tej nazwy powstaje app_id, po którym labwc rozpoznaje okna
    app.setDesktopFileName("horyzont-" + app_id)
    _load_translations(app)
    manager.init_app(app)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return app


def _load_translations(app):
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from ..i18n import lang_code
    loc = QLocale("pl_PL" if lang_code() == "pl" else "en_US")
    QLocale.setDefault(loc)
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    app._translators = []
    for name in ("qtbase", "qt"):
        t = QTranslator(app)
        if t.load(loc, name, "_", path) or t.load(loc, name, "_", "/usr/share/qt6/translations"):
            app.installTranslator(t)
            app._translators.append(t)
