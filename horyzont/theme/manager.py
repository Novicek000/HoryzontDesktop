"""Zarządca motywu: wczytuje motyw z ustawień, rejestruje czcionki,
ustawia paletę i styl Qt oraz rozgłasza zmiany do wszystkich okien."""
import glob
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from .. import config

_FONT_DIRS = [
    "/usr/share/fonts/wine-tahoma-fonts",
    "/usr/share/wine/fonts",
    "/usr/share/fonts/wine",
    os.path.expanduser("~/.local/share/fonts"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fonts"),
]
_family = None


def base_family():
    """Rodzina czcionki interfejsu: Tahoma (z pakietu Wine, LGPL) albo DejaVu Sans."""
    global _family
    if _family is not None:
        return _family
    if QApplication.instance() is None:
        return "Tahoma"
    fams = set(QFontDatabase.families())
    if "Tahoma" not in fams:
        for d in _FONT_DIRS:
            for f in glob.glob(os.path.join(d, "tahoma*.ttf")) + glob.glob(os.path.join(d, "Tahoma*.ttf")):
                QFontDatabase.addApplicationFont(f)
        fams = set(QFontDatabase.families())
    for cand in ("Tahoma", "Verdana", "DejaVu Sans", "Noto Sans", "Liberation Sans"):
        if cand in fams:
            _family = cand
            break
    else:
        _family = QFont().defaultFamily()
    return _family


def mono_family():
    fams = set(QFontDatabase.families())
    for cand in ("Lucida Console", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", "Monospace"):
        if cand in fams:
            return cand
    return "Monospace"


class ThemeManager(QObject):
    changed = Signal()

    _instance = None

    def __init__(self):
        super().__init__()
        self.theme = None
        self._key = None
        self.error = None
        self.reload()
        self._watcher = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def _make(self):
        from .builtin import ClassicTheme, HoryzontTheme
        style = config.get("visual_style", "builtin")
        scheme = config.get("color_scheme", "teal")
        self.error = None
        if style and style not in ("builtin", "classic") and os.path.exists(style):
            try:
                from .msstyles import MsStylesTheme
                return MsStylesTheme(style, config.get("msstyles_scheme", ""), fallback=HoryzontTheme(scheme))
            except Exception as e:  # uszkodzony plik — wracamy do wbudowanego
                self.error = str(e)
        if style == "classic":
            return ClassicTheme(scheme)
        return HoryzontTheme(scheme)

    def reload(self):
        key = (config.get("visual_style"), config.get("color_scheme"), config.get("msstyles_scheme"),
               config.get("font_size"))
        icons_key = (config.get("icon_pack", ""), config.get("start_logo", "horyzont"))
        if key == self._key and self.theme is not None:
            if icons_key != getattr(self, "_icons_key", None):
                self._icons_key = icons_key
                from . import iconcache
                iconcache.reset()
                return True
            return False
        if icons_key != getattr(self, "_icons_key", None):
            from . import iconcache
            iconcache.reset()
        self._icons_key = icons_key
        self._key = key
        self.theme = self._make()
        self.theme.font_scale = {"normal": 1.0, "large": 1.18, "xlarge": 1.36}.get(config.get("font_size"), 1.0)
        return True

    def watch(self):
        if self._watcher is None:
            self._watcher = config.watch(self._on_config)

    def _on_config(self):
        if self.reload():
            app = QApplication.instance()
            if app is not None:
                apply(app)
            self.changed.emit()


def current():
    return ThemeManager.instance().theme


def palette_for(theme):
    pal = QPalette()
    c = theme.color
    pal.setColor(QPalette.Window, c("window"))
    pal.setColor(QPalette.WindowText, c("window_text"))
    pal.setColor(QPalette.Base, c("base"))
    pal.setColor(QPalette.AlternateBase, c("alt_base"))
    pal.setColor(QPalette.Button, c("button"))
    pal.setColor(QPalette.ButtonText, c("button_text"))
    pal.setColor(QPalette.Text, c("window_text"))
    pal.setColor(QPalette.Highlight, c("highlight"))
    pal.setColor(QPalette.HighlightedText, c("highlight_text"))
    pal.setColor(QPalette.ToolTipBase, c("tooltip"))
    pal.setColor(QPalette.ToolTipText, QColor("#000000"))
    pal.setColor(QPalette.Link, c("link"))
    pal.setColor(QPalette.PlaceholderText, c("gray_text"))
    pal.setColor(QPalette.Light, QColor("#ffffff"))
    pal.setColor(QPalette.Midlight, c("window").lighter(108))
    pal.setColor(QPalette.Mid, c("window").darker(130))
    pal.setColor(QPalette.Dark, c("window").darker(160))
    pal.setColor(QPalette.Shadow, QColor("#404040"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c("gray_text"))
    pal.setColor(QPalette.Disabled, QPalette.Base, c("window").lighter(104))
    # zaznaczenie w nieaktywnym widoku: jasnoszare tło, czarny tekst
    pal.setColor(QPalette.Inactive, QPalette.Highlight, QColor("#d8dddc"))
    pal.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor("#000000"))
    return pal


def apply(app):
    """Ustawia styl, paletę i czcionkę aplikacji zgodnie z bieżącym motywem."""
    from .style import HoryzontStyle
    theme = current()
    app.setPalette(palette_for(theme))
    app.setFont(theme.font("normal"))
    st = app.style()
    if isinstance(st, HoryzontStyle):
        st.theme = theme
        # wymuszenie ponownego wypolerowania widżetów
        for w in app.allWidgets():
            w.update()
    else:
        app.setStyle(HoryzontStyle(theme))
    from PySide6.QtWidgets import QToolTip
    QToolTip.setPalette(app.palette())
    QToolTip.setFont(theme.font("normal"))


def init_app(app):
    ThemeManager.instance()
    base_family()
    ThemeManager.instance().theme.font_scale = ThemeManager.instance().theme.font_scale
    apply(app)
    ThemeManager.instance().watch()
