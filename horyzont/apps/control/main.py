"""Proces Panelu sterowania (okno główne i aplety)."""
import sys

from ...common import single
from ...common.app import make_app
from .registry import open_applet


class ControlApp:
    def __init__(self, app):
        self.app = app
        self.windows = []
        self.applets = {}

    def open_panel(self):
        from .panel import ControlPanelWindow
        for w in self.windows:
            if w.isVisible():
                w.showNormal()
                w.raise_()
                w.activateWindow()
                return w
        w = ControlPanelWindow(self)
        w.show()
        self.windows.append(w)
        return w

    def open_applet(self, key, page=None, parent=None):
        existing = self.applets.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    if page and hasattr(existing, "show_page"):
                        existing.show_page(page)
                    return existing
            except RuntimeError:
                pass
        w = open_applet(key, page, None)
        if w is not None:
            self.applets[key] = w
            w.show()
            w.raise_()
            w.activateWindow()
        return w

    def handle(self, args):
        if not args:
            self.open_panel()
            return
        key = args[0]
        rest = args[1:]
        if "--load-style" in rest:
            i = rest.index("--load-style")
            path = rest[i + 1] if i + 1 < len(rest) else None
            w = self.open_applet("display", "themes")
            if path and w is not None and hasattr(w, "load_style_file"):
                w.load_style_file(path)
            return
        if "--install-icons" in rest:
            i = rest.index("--install-icons")
            path = rest[i + 1] if i + 1 < len(rest) else None
            w = self.open_applet("display", "icons")
            if path and w is not None:
                from .iconstab import install_file
                install_file(w, path, getattr(w, "_ip_fill", None))
            return
        self.open_applet(key, rest[0] if rest else None)


def main(args):
    app = make_app("control")
    if single.try_forward("control", args, 200):
        return 0
    ctl = ControlApp(app)
    server = single.Server("control", ctl.handle)
    ctl.handle(args)
    return app.exec()
