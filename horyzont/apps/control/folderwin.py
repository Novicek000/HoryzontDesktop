"""Okno w stylu folderu (panel zadań + kafelki) dla apletów: Połączenia sieciowe,
Drukarki i faksy, Czcionki, Narzędzia administracyjne, Zaplanowane zadania."""
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (QLabel, QMenu, QMenuBar, QSplitter, QStatusBar,
                               QVBoxLayout)

from ...common import launcher
from ...common.taskpane import TaskPane
from ...common.window import HWindow
from ...i18n import plain, tr
from ..explorer.model import BaseModel, Item, ItemRole
from ..explorer.views import ViewStack


class ItemsModel(BaseModel):
    columns = ["name", "type", "info"]

    def __init__(self, loader, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.folder = "horyzont:applet"

    def refresh(self):
        items = self.loader()
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def cell_text(self, it, col):
        if col == "info":
            return it.extra.get("info", "")
        return super().cell_text(it, col)

    def flags(self, index):
        it = self.item(index)
        if it is None or it.header:
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def sort(self, column, order=Qt.AscendingOrder):
        pass


def header(text):
    h = Item("", text)
    h.header = True
    h.kind = "header"
    return h


def entry(name, icon, type_name="", info="", key=None, **extra):
    it = Item(key or name, name)
    it.label = name
    it.icon = icon
    it.kind = "special"
    it.type_name = type_name
    it.extra = dict(extra, info=info)
    return it


class FolderWindow(HWindow):
    """Podklasy definiują: load_items(), fill_tasks(pane, selected), activate(item), item_menu(menu, item)."""

    title_key = "control_panel"
    icon = "control_panel"
    view_mode = "tiles"

    def __init__(self):
        super().__init__(plain(self.title_key), self.icon)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        mb = QMenuBar()
        m = mb.addMenu(tr("menu_file"))
        m.addAction(tr("close_window"), self.close)
        m = mb.addMenu(tr("menu_view"))
        for mode in ("tiles", "icons", "list", "details"):
            m.addAction(tr({"tiles": "view_tiles", "icons": "view_icons", "list": "view_list",
                            "details": "view_details"}[mode]), lambda md=mode: self.views.set_mode(md))
        m.addSeparator()
        m.addAction(tr("refresh") + "\tF5", self.refresh)
        m = mb.addMenu(tr("menu_help"))
        m.addAction(tr("help_topics"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        lay.addWidget(mb)
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        split.addWidget(self.pane)
        self.model = ItemsModel(self.load_items, self)
        self.views = ViewStack()
        self.views.set_model(self.model)
        split.addWidget(self.views)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 520])
        lay.addWidget(split, 1)
        self.status = QStatusBar()
        lay.addWidget(self.status)
        for v in (self.views.list, self.views.tree):
            v.doubleClicked.connect(self._activated)
            v.setContextMenuPolicy(Qt.CustomContextMenu)
            v.customContextMenuRequested.connect(self._menu)
        self.refresh()
        self.resize(760, 500)

    def refresh(self):
        self.model.refresh()
        self.views.set_model(self.model)
        for v in (self.views.list, self.views.tree):
            v.selectionModel().selectionChanged.connect(lambda *_: self._update_tasks())
        self.views.set_mode(self.view_mode)
        self._update_tasks()

    def selected(self):
        return self.views.selected_items()

    def _update_tasks(self):
        self.pane.setUpdatesEnabled(False)
        self.pane.clear()
        self.fill_tasks(self.pane, self.selected())
        self.pane.setUpdatesEnabled(True)
        n = sum(1 for i in self.model.items if not i.header)
        self.status.showMessage(tr("n_objects", n))

    def _activated(self, idx):
        it = idx.data(ItemRole)
        if it is not None and not it.header:
            self.activate(it)

    def _menu(self, pos):
        v = self.views.view()
        idx = v.indexAt(pos)
        it = idx.data(ItemRole) if idx.isValid() else None
        m = QMenu(self)
        if it is not None and not it.header:
            v.setCurrentIndex(idx)
            self.item_menu(m, it)
        else:
            m.addAction(tr("refresh"), self.refresh)
        if not m.isEmpty():
            m.exec(v.viewport().mapToGlobal(pos))

    # do nadpisania
    def load_items(self):
        return []

    def fill_tasks(self, pane, sel):
        pass

    def activate(self, it):
        pass

    def item_menu(self, m, it):
        pass

    def other_places(self, pane):
        o = pane.add_section(plain("task_other_places"))
        from ...common.taskpane import place_menu
        from ... import config
        docs = config.user_dir("DOCUMENTS")
        o.add_link("control_panel", plain("control_panel"), lambda: launcher.start_builtin("control"),
                   context=lambda g: place_menu(self, "horyzont:control", g))
        o.add_link("computer", plain("my_computer"), lambda: launcher.start_builtin("explorer", ["horyzont:computer"]),
                   context=lambda g: place_menu(self, "horyzont:computer", g))
        o.add_link("documents", plain("my_documents"), lambda: launcher.start_builtin("explorer", [docs]),
                   context=lambda g: place_menu(self, docs, g))
        return o

    def details(self, pane, sel):
        d = pane.add_section(plain("task_details"))
        if sel:
            it = sel[0]
            d.add_text(it.label, bold=True)
            if it.type_name:
                d.add_text(it.type_name)
            for line in it.extra.get("details", []):
                d.add_text(line)
        else:
            d.set_expanded(False)
        return d
