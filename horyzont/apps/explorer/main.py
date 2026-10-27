"""Proces Eksploratora: wiele okien w jednym procesie."""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ...common import single
from ...common.app import make_app


class ExplorerApp:
    def __init__(self, app):
        self.app = app
        self.windows = []
        self.help = None

    def open(self, loc=None, folders=False):
        if loc and loc.startswith("horyzont:help"):
            from .help import HelpWindow
            if self.help is None or not self.help.isVisible():
                self.help = HelpWindow()
            topic = loc.split(":", 2)[2] if loc.count(":") >= 2 else None
            if topic:
                self.help.show_topic(topic)
            self.help.show()
            self.help.raise_()
            self.help.activateWindow()
            return self.help
        from .window import ExplorerWindow
        w = ExplorerWindow(self, loc)
        if folders:
            w.set_side("folders")
        n = len([x for x in self.windows if x.isVisible()])
        w.move(60 + 26 * (n % 8), 40 + 26 * (n % 8))
        w.show()
        w.raise_()
        w.activateWindow()
        self.windows.append(w)
        w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)
        return w

    def handle(self, args):
        if not args:
            self.open()
            return
        if args[0] == "--properties":
            from .properties import PropertiesDialog
            d = PropertiesDialog(args[1:], None)
            d.show()
            d.raise_()
            self._keep = getattr(self, "_keep", [])
            self._keep.append(d)
            return
        if args[0] == "--search":
            w = self.open(os.path.expanduser("~"))
            w.set_side("search")
            return
        if args[0] in ("/e", "--folders"):
            self.open(args[1] if len(args) > 1 else None, folders=True)
            return
        for a in args:
            self.open(a)


def main(args):
    app = make_app("explorer")
    if single.try_forward("explorer", args, 200):
        return 0
    app.setQuitOnLastWindowClosed(True)
    ctl = ExplorerApp(app)
    server = single.Server("explorer", ctl.handle)
    ctl.handle(args)
    return app.exec()
