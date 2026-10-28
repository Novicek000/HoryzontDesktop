"""Okno Eksploratora."""
import os
import shutil
import subprocess
import urllib.parse
from types import SimpleNamespace

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
                               QMenu, QMenuBar, QSplitter, QStatusBar,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from ... import config
from ...common import desktopentry, dialogs, fileops, isomount, launcher, sysctl
from ...common.taskpane import TaskPane
from ...common.window import HWindow
from ...common.appkit import T
from ...i18n import plain, tr
from ...theme import iconcache
from .fileopui import run_copy
from .model import (ComputerModel, FolderModel, ItemRole, NetworkModel,
                    SearchModel, ThumbnailCache, TrashModel, format_date,
                    special_folder_icon, special_folder_label)
from .panes import FolderTree, SearchPane
from .properties import PropertiesDialog
from .views import ViewStack

VIEW_MODES = ["thumbnails", "tiles", "icons", "list", "details"]
VIEW_KEYS = {"thumbnails": "view_thumbnails", "tiles": "view_tiles", "icons": "view_icons",
             "list": "view_list", "details": "view_details"}


def display_name(loc):
    from . import archive_ui
    if archive_ui.is_loc(loc):
        a, inner = archive_ui.parse_loc(loc)
        return os.path.basename(inner) if inner else os.path.basename(a)
    if loc == "horyzont:computer":
        return plain("my_computer")
    if loc == "horyzont:recycle":
        return plain("recycle_bin")
    if loc == "horyzont:network":
        return plain("my_network")
    if loc == "horyzont:search":
        return plain("search_results")
    lab = special_folder_label(loc)
    if lab:
        return lab
    if loc == config.user_dir("DESKTOP"):
        return plain("desktop")
    if loc == os.path.expanduser("~"):
        return plain("home_folder")
    if loc == "/":
        return plain("system_disk") + " (/)"
    return os.path.basename(loc.rstrip("/")) or loc


def location_icon(loc):
    if loc.startswith("horyzont:archive:"):
        return "folder_zip"
    return {"horyzont:computer": "computer", "horyzont:recycle": "recycle_empty",
            "horyzont:network": "network", "horyzont:search": "search"}.get(loc) or \
        special_folder_icon(loc) or ("drive_system" if loc == "/" else "folder_open")


class ExplorerWindow(HWindow):
    def __init__(self, app_ctl, location=None):
        super().__init__("", "folder_open")
        self.ctl = app_ctl
        self.history = []
        self.hpos = -1
        self.location = None
        self.thumbs = ThumbnailCache(96)
        self.folder_model = FolderModel(self)
        self.trash_model = TrashModel(self)
        self.computer_model = ComputerModel(self)
        self.search_model = SearchModel(self)
        self.network_model = NetworkModel(self)
        from .archive_ui import ArchiveModel
        self.archive_model = ArchiveModel(self)
        self.model = self.folder_model
        self.side_mode = "tasks" if config.get("explorer_show_tasks", True) else "none"
        self._build()
        self.resize(780, 540)
        self.navigate(location or config.user_dir("DOCUMENTS"))

    # ================================================================ budowa
    def _build(self):
        body = self.body()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self._build_menus()
        # pasek narzędzi
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.act_back = QAction(iconcache.icon("back"), plain("back"), self)
        self.act_back.triggered.connect(self.back)
        self.act_fwd = QAction(iconcache.icon("forward"), plain("forward"), self)
        self.act_fwd.triggered.connect(self.forward)
        self.act_up = QAction(iconcache.icon("up"), plain("up"), self)
        self.act_up.triggered.connect(self.up)
        self.toolbar.addAction(self.act_back)
        self.back_btn = self.toolbar.widgetForAction(self.act_back)
        self.back_menu = QMenu(self)
        self.back_btn.setMenu(self.back_menu)
        self.back_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.back_menu.aboutToShow.connect(lambda: self._fill_history(self.back_menu, -1))
        self.toolbar.addAction(self.act_fwd)
        fwd_btn = self.toolbar.widgetForAction(self.act_fwd)
        fwd_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.fwd_menu = QMenu(self)
        fwd_btn.setMenu(self.fwd_menu)
        fwd_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.fwd_menu.aboutToShow.connect(lambda: self._fill_history(self.fwd_menu, 1))
        self.toolbar.addAction(self.act_up)
        self.toolbar.widgetForAction(self.act_up).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar.addSeparator()
        self.act_search = QAction(iconcache.icon("search"), plain("search"), self)
        self.act_search.setCheckable(True)
        self.act_search.triggered.connect(lambda c: self.set_side("search" if c else "tasks"))
        self.toolbar.addAction(self.act_search)
        self.act_folders = QAction(iconcache.icon("folders_tree"), plain("folders"), self)
        self.act_folders.setCheckable(True)
        self.act_folders.triggered.connect(lambda c: self.set_side("folders" if c else "tasks"))
        self.toolbar.addAction(self.act_folders)
        self.toolbar.addSeparator()
        self.views_btn = QToolButton()
        self.views_btn.setIcon(iconcache.icon("views"))
        self.views_btn.setToolTip(plain("views"))
        self.views_btn.setAutoRaise(True)
        self.views_btn.setPopupMode(QToolButton.InstantPopup)
        self.views_menu = QMenu(self)
        self._fill_view_menu(self.views_menu)
        self.views_btn.setMenu(self.views_menu)
        self.toolbar.addWidget(self.views_btn)
        lay.addWidget(self.toolbar)
        self._sep_line(lay)
        # pasek adresu
        self.addrbar = QWidget()
        al = QHBoxLayout(self.addrbar)
        al.setContentsMargins(4, 2, 4, 2)
        al.setSpacing(4)
        lbl = QLabel(plain("address"))
        lbl.setStyleSheet("color: #6d7577;")
        al.addWidget(lbl)
        self.address = QComboBox()
        self.address.setEditable(True)
        self.address.setInsertPolicy(QComboBox.NoInsert)
        self.address.lineEdit().returnPressed.connect(self._address_go)
        self.address.activated.connect(self._address_pick)
        al.addWidget(self.address, 1)
        self.go_btn = QToolButton()
        self.go_btn.setIcon(iconcache.icon("go"))
        self.go_btn.setText(plain("go"))
        self.go_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.go_btn.setAutoRaise(True)
        self.go_btn.clicked.connect(self._address_go)
        al.addWidget(self.go_btn)
        lay.addWidget(self.addrbar)
        self._sep_line(lay)
        # obszar główny
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(4)
        self.side = QWidget()
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.taskpane = TaskPane()
        self.tree = FolderTree()
        self.tree.navigate.connect(self.navigate)
        self.tree.closed.connect(lambda: self.set_side("tasks"))
        self.search = SearchPane(os.path.expanduser("~"))
        self.search.results.connect(self.search_model.add_paths)
        self.search.started.connect(self._search_started)
        self.search.finished.connect(lambda n: self.update_status())
        self.search.closed.connect(lambda: self.set_side("tasks"))
        sl.addWidget(self.taskpane)
        sl.addWidget(self.tree)
        sl.addWidget(self.search)
        self.splitter.addWidget(self.side)
        self.views = ViewStack()
        self.views.list.delegate.thumbs = self.thumbs
        self.thumbs.updated.connect(lambda p: self.views.list.viewport().update())
        self.splitter.addWidget(self.views)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([200, 600])
        lay.addWidget(self.splitter, 1)
        for v in (self.views.list, self.views.tree):
            v.doubleClicked.connect(self._activated)
            v.setContextMenuPolicy(Qt.CustomContextMenu)
            v.customContextMenuRequested.connect(self._context_menu)
            v.files_dropped.connect(self._dropped)
        self.statusbar = QStatusBar()
        self.status_left = QLabel()
        self.status_size = QLabel()
        self.status_zone = QLabel()
        self.statusbar.addWidget(self.status_left, 1)
        self.statusbar.addPermanentWidget(self.status_size)
        self.statusbar.addPermanentWidget(self.status_zone)
        lay.addWidget(self.statusbar)
        self.statusbar.setVisible(config.get("explorer_status_bar", True))
        self._apply_side()
        self._shortcuts()

    def _sep_line(self, lay):
        from PySide6.QtWidgets import QFrame
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color: #c9d1d0;")
        f.setFixedHeight(1)
        lay.addWidget(f)

    def _build_menus(self):
        mb = self.menubar
        self.m_file = mb.addMenu(tr("menu_file"))
        self.m_file.aboutToShow.connect(self._fill_file_menu)
        m = mb.addMenu(tr("menu_edit"))
        self.a_undo = m.addAction(tr("np_undo"))
        self.a_undo.setEnabled(False)
        m.addSeparator()
        self.a_cut = m.addAction(tr("np_cut"), self.cut)
        self.a_copy = m.addAction(tr("np_copy"), self.copy)
        self.a_paste = m.addAction(tr("np_paste"), self.paste)
        self.a_paste_sc = m.addAction(tr("desk_paste_shortcut"), self.paste_shortcut)
        m.addSeparator()
        m.addAction(tr("copy_to_folder"), lambda: self.copy_move_to(False))
        m.addAction(tr("move_to_folder"), lambda: self.copy_move_to(True))
        m.addSeparator()
        m.addAction(tr("np_select_all"), lambda: self.views.view().selectAll())
        m.addAction(tr("invert_selection"), self.invert_selection)
        m.aboutToShow.connect(self._update_edit_menu)
        m = mb.addMenu(tr("menu_view"))
        tb = m.addMenu(tr("toolbars"))
        a = tb.addAction(tr("std_buttons"))
        a.setCheckable(True)
        a.setChecked(True)
        a.toggled.connect(lambda v: self.toolbar.setVisible(v))
        a = tb.addAction(tr("address_bar"))
        a.setCheckable(True)
        a.setChecked(True)
        a.toggled.connect(lambda v: self.addrbar.setVisible(v))
        a = m.addAction(tr("status_bar"))
        a.setCheckable(True)
        a.setChecked(config.get("explorer_status_bar", True))
        a.toggled.connect(lambda v: (self.statusbar.setVisible(v), config.set("explorer_status_bar", v)))
        eb = m.addMenu(tr("explorer_bar"))
        self.a_eb_search = eb.addAction(plain("search") + "\tCtrl+E")
        self.a_eb_search.setCheckable(True)
        self.a_eb_search.triggered.connect(lambda c: self.set_side("search" if c else "tasks"))
        self.a_eb_folders = eb.addAction(plain("folders"))
        self.a_eb_folders.setCheckable(True)
        self.a_eb_folders.triggered.connect(lambda c: self.set_side("folders" if c else "tasks"))
        m.addSeparator()
        self._fill_view_menu(m)
        m.addSeparator()
        arr = m.addMenu(tr("arrange_icons_by"))
        for i, k in enumerate(("name", "size", "type", "modified")):
            arr.addAction(plain(k), lambda c=k: self.arrange(c))
        m.addSeparator()
        go = m.addMenu(tr("go_to"))
        go.addAction(plain("back") + "\tAlt+Left", self.back)
        go.addAction(plain("forward") + "\tAlt+Right", self.forward)
        go.addAction(plain("up_level"), self.up)
        go.addSeparator()
        go.addAction(iconcache.icon("home"), plain("home_folder"), lambda: self.navigate(os.path.expanduser("~")))
        m.addAction(tr("refresh") + "\tF5", self.refresh)
        self.m_fav = mb.addMenu(tr("menu_favorites"))
        self.m_fav.aboutToShow.connect(self._fill_favorites)
        m = mb.addMenu(tr("menu_tools"))
        m.addAction(tr("map_network"), self.map_network_drive)
        m.addAction(plain("disconnect_drive"), self.disconnect_drive)
        m.addSeparator()
        m.addAction(tr("folder_options"), lambda: launcher.start_builtin("control", ["folder_options"]))
        m = mb.addMenu(tr("menu_help"))
        m.addAction(tr("help_topics"), lambda: self.ctl.open("horyzont:help"))
        m.addSeparator()
        m.addAction(tr("about_os"), lambda: launcher.start_builtin("winver"))

    def _fill_view_menu(self, m):
        group = QActionGroup(m)
        group.setExclusive(True)
        if not hasattr(self, "_view_actions"):
            self._view_actions = []
        for mode in VIEW_MODES:
            a = m.addAction(tr(VIEW_KEYS[mode]))
            a.setCheckable(True)
            a.setData(mode)
            group.addAction(a)
            a.triggered.connect(lambda _=False, md=mode: self.set_view(md))
            self._view_actions.append(a)

    def _shortcuts(self):
        def sc(key, fn):
            a = QAction(self)
            a.setShortcut(QKeySequence(key))
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(fn)
            self.addAction(a)
        sc("Backspace", self.up)
        sc("Alt+Left", self.back)
        sc("Alt+Right", self.forward)
        sc("Alt+Up", self.up)
        sc("F5", self.refresh)
        sc("Ctrl+R", self.refresh)
        sc("F2", self.rename)
        sc("Delete", lambda: self.delete(False))
        sc("Shift+Delete", lambda: self.delete(True))
        sc("Ctrl+C", self.copy)
        sc("Ctrl+X", self.cut)
        sc("Ctrl+V", self.paste)
        sc("Ctrl+A", lambda: self.views.view().selectAll())
        sc("Alt+Return", self.properties)
        sc("Return", self.open_selected)
        sc("F3", lambda: self.set_side("search"))
        sc("Ctrl+E", lambda: self.set_side("search"))
        sc("Ctrl+F", lambda: self.set_side("search"))
        sc("Ctrl+Shift+N", self.new_folder)
        sc("Ctrl+W", self.close)
        sc("F4", lambda: (self.address.setFocus(), self.address.showPopup()))
        sc("Alt+D", lambda: (self.address.setFocus(), self.address.lineEdit().selectAll()))
        sc("Ctrl+H", lambda: (config.set("explorer_show_hidden", not config.get("explorer_show_hidden")), self.refresh()))

    # ================================================================ nawigacja
    def navigate(self, loc, add_history=True):
        from . import archive_ui
        from ...common import archives
        loc = os.path.expanduser(loc)
        if not loc.startswith("horyzont:"):
            loc = os.path.abspath(loc)
            if os.path.isfile(loc) and archives.is_archive(loc) and config.get("explorer_browse_archives", True):
                loc = archive_ui.make_loc(loc, "")
            elif os.path.isfile(loc):
                launcher.open_path(loc)
                return
            elif not os.path.isdir(loc):
                dialogs.message(self, plain("error"), tr("explorer_notfound", loc), "error")
                return
        if archive_ui.is_loc(loc):
            arc, inner = archive_ui.parse_loc(loc)
            if not os.path.isfile(arc):
                dialogs.message(self, plain("error"), tr("explorer_notfound", arc), "error")
                return
            if not self.archive_model.open(self, arc, inner):
                return
        if loc and loc.startswith("horyzont:help"):
            self.ctl.open(loc)
            return
        self.location = loc
        if add_history:
            self.history = self.history[:self.hpos + 1]
            if not self.history or self.history[-1] != loc:
                self.history.append(loc)
            self.hpos = len(self.history) - 1
        if loc == "horyzont:computer":
            self.model = self.computer_model
        elif loc == "horyzont:recycle":
            self.model = self.trash_model
        elif loc == "horyzont:network":
            self.model = self.network_model
        elif loc == "horyzont:search":
            self.model = self.search_model
        elif archive_ui.is_loc(loc):
            self.model = self.archive_model
        else:
            self.model = self.folder_model
            self.folder_model.set_folder(loc)
        if loc != "horyzont:search":
            self.model.refresh()
        self.views.set_model(self.model)
        for v in (self.views.list, self.views.tree):
            v.selectionModel().selectionChanged.connect(self._selection_changed)
        self.set_view(self._view_for(loc), remember=False)
        self.setWindowTitle(display_name(loc) if not config.get("explorer_full_path_title") or loc.startswith("horyzont:") else loc)
        self.setIconName(location_icon(loc))
        self._update_address()
        self.act_back.setEnabled(self.hpos > 0)
        self.act_fwd.setEnabled(self.hpos < len(self.history) - 1)
        self.act_up.setEnabled(loc not in ("horyzont:computer",) and loc != config.user_dir("DESKTOP"))
        self.update_taskpane()
        self.update_status()
        if self.side_mode == "folders" and not loc.startswith("horyzont:"):
            self.tree.select_path(loc)
        if getattr(self.folder_model, "error", None) and self.model is self.folder_model:
            QTimer.singleShot(0, lambda: dialogs.message(self, display_name(loc), self.folder_model.error, "error"))

    def _view_for(self, loc):
        views = config.get("folder_views", {})
        if loc in views:
            return views[loc]
        if loc == "horyzont:computer":
            return "tiles"
        if loc in ("horyzont:recycle",):
            return "tiles"
        if loc == "horyzont:search" or loc.startswith("horyzont:archive:"):
            return "details"
        if loc == config.user_dir("PICTURES"):
            return "thumbnails"
        return config.get("explorer_view", "tiles")

    def back(self):
        if self.hpos > 0:
            self.hpos -= 1
            self.navigate(self.history[self.hpos], add_history=False)

    def forward(self):
        if self.hpos < len(self.history) - 1:
            self.hpos += 1
            self.navigate(self.history[self.hpos], add_history=False)

    def up(self):
        loc = self.location
        if loc and loc.startswith("horyzont:archive:"):
            from . import archive_ui
            arc, inner = archive_ui.parse_loc(loc)
            if inner:
                self.navigate(archive_ui.make_loc(arc, os.path.dirname(inner)))
            else:
                self.navigate(os.path.dirname(arc))
            return
        if loc is None or loc.startswith("horyzont:"):
            if loc in ("horyzont:recycle", "horyzont:network"):
                self.navigate(config.user_dir("DESKTOP"))
            return
        if loc == "/":
            self.navigate("horyzont:computer")
            return
        if loc in (config.user_dir("DOCUMENTS"),):
            self.navigate(config.user_dir("DESKTOP"))
            return
        parent = os.path.dirname(loc.rstrip("/"))
        self.navigate(parent or "/")

    def refresh(self):
        if self.location:
            self.model.refresh() if self.model is not self.search_model else None
            self.update_taskpane()
            self.update_status()

    def _fill_history(self, menu, direction):
        menu.clear()
        if direction < 0:
            rng = range(self.hpos - 1, max(-1, self.hpos - 10), -1)
        else:
            rng = range(self.hpos + 1, min(len(self.history), self.hpos + 10))
        for i in rng:
            loc = self.history[i]
            a = menu.addAction(iconcache.icon(location_icon(loc)), display_name(loc))
            a.triggered.connect(lambda _=False, i=i: self._jump(i))

    def _jump(self, i):
        self.hpos = i
        self.navigate(self.history[i], add_history=False)

    # ================================================================ pasek adresu
    def _update_address(self):
        self.address.blockSignals(True)
        self.address.clear()
        entries = [(plain("desktop"), "show_desktop", config.user_dir("DESKTOP")),
                   (plain("my_documents"), "documents", config.user_dir("DOCUMENTS")),
                   (plain("my_computer"), "computer", "horyzont:computer"),
                   (plain("home_folder"), "home", os.path.expanduser("~")),
                   (plain("system_disk") + " (/)", "drive_system", "/"),
                   (plain("my_network"), "network", "horyzont:network"),
                   (plain("recycle_bin"), "recycle_empty", "horyzont:recycle")]
        cur = None
        for i, (name, icon, path) in enumerate(entries):
            self.address.addItem(iconcache.icon(icon), name, path)
            if path == self.location:
                cur = i
        if cur is None:
            text = self.location if config.get("explorer_full_path_address", True) or self.location.startswith("horyzont:") \
                else display_name(self.location)
            if self.location.startswith("horyzont:archive:"):
                from . import archive_ui
                text = archive_ui.display_path(self.location)
            elif self.location.startswith("horyzont:"):
                text = display_name(self.location)
            self.address.insertItem(0, iconcache.icon(location_icon(self.location)), text, self.location)
            cur = 0
        self.address.setCurrentIndex(cur)
        if not self.location.startswith("horyzont:") and config.get("explorer_full_path_address", True):
            self.address.setEditText(self.location)
        self.address.blockSignals(False)

    def _address_pick(self, idx):
        loc = self.address.itemData(idx)
        if loc:
            self.navigate(loc)

    def _address_go(self):
        text = self.address.currentText().strip()
        if not text:
            return
        for i in range(self.address.count()):
            if self.address.itemText(i) == text and self.address.itemData(i):
                self.navigate(self.address.itemData(i))
                return
        if launcher.is_url(text) and not text.startswith("file:"):
            launcher.xdg_open(text)
            return
        if text.startswith("file://"):
            text = urllib.parse.unquote(text[7:])
        p = os.path.expanduser(text)
        if os.path.exists(p):
            self.navigate(p)
        elif not launcher.run_command(text):
            dialogs.message(self, plain("error"), tr("explorer_notfound", text), "error")

    # ================================================================ widok
    def set_view(self, mode, remember=True):
        if mode not in VIEW_MODES:
            mode = "tiles"
        if self.model in (self.trash_model, self.search_model) and mode == "thumbnails":
            mode = "details"
        self.views.set_mode(mode)
        for a in getattr(self, "_view_actions", []):
            a.setChecked(a.data() == mode)
        if remember and self.location:
            v = dict(config.get("folder_views", {}))
            v[self.location] = mode
            config.set("folder_views", v)

    def arrange(self, col):
        cols = self.model.columns
        if col in cols:
            self.model.sort(cols.index(col), Qt.AscendingOrder)

    def set_side(self, mode):
        self.side_mode = mode
        self._apply_side()

    def _apply_side(self):
        m = self.side_mode
        self.taskpane.setVisible(m == "tasks")
        self.tree.setVisible(m == "folders")
        self.search.setVisible(m == "search")
        self.side.setVisible(m != "none")
        self.act_search.setChecked(m == "search")
        self.act_folders.setChecked(m == "folders")
        self.a_eb_search.setChecked(m == "search")
        self.a_eb_folders.setChecked(m == "folders")
        if m == "folders" and self.location and not self.location.startswith("horyzont:"):
            self.tree.select_path(self.location)
        if m == "search":
            loc = self.location if self.location and not self.location.startswith("horyzont:") else os.path.expanduser("~")
            if self.search.where.findText(loc) < 0:
                self.search.where.insertItem(0, iconcache.icon("folder"), loc)
            self.search.where.setCurrentText(loc)
            self.search.name.setFocus()

    def _search_started(self):
        self.search_model.clear()
        if self.location != "horyzont:search":
            self.navigate("horyzont:search")

    # ================================================================ zaznaczenie
    def selected(self):
        return self.views.selected_items()

    def selected_paths(self):
        return [i.path for i in self.selected() if i.path and i.kind in ("file", "dir", "link", "drive")]

    def _selection_changed(self, *_):
        # przy zaznaczaniu ramką sygnał przychodzi przy każdym ruchu myszy —
        # panel zadań odświeżamy dopiero, gdy zaznaczanie się „uspokoi”
        if not hasattr(self, "_sel_timer"):
            from PySide6.QtCore import QTimer
            self._sel_timer = QTimer(self)
            self._sel_timer.setSingleShot(True)
            self._sel_timer.setInterval(70)
            self._sel_timer.timeout.connect(self._apply_selection_change)
        self._sel_timer.start()

    def _apply_selection_change(self):
        key = tuple(id(i) for i in self.selected())
        if key != getattr(self, "_last_sel_key", None) or not key:
            self._last_sel_key = key
            self.update_taskpane()
        self.update_status()

    def invert_selection(self):
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        v = self.views.view()
        sm = v.selectionModel()
        m = self.model
        for r in range(m.rowCount()):
            idx = m.index(r, 0)
            sm.select(idx, QItemSelectionModel.Toggle | QItemSelectionModel.Rows)

    def update_status(self):
        sel = self.selected()
        n = self.model.rowCount() - sum(1 for i in self.model.items if i.header)
        if sel:
            self.status_left.setText(tr("n_selected", len(sel)))
            total = sum(i.size for i in sel if not i.is_dir)
            self.status_size.setText(sysctl.human_size(total) if any(not i.is_dir for i in sel) else "")
        else:
            self.status_left.setText(tr("n_objects", n))
            if self.model is self.folder_model:
                total = sum(i.size for i in self.model.items if not i.is_dir)
                free = ""
                try:
                    du = shutil.disk_usage(self.location)
                    free = tr("free_space", sysctl.human_size(du.free))
                except OSError:
                    pass
                self.status_left.setText(tr("n_objects", n) + (f" ({free})" if free else ""))
                self.status_size.setText(sysctl.human_size(total))
            else:
                self.status_size.setText("")
        self.status_zone.setText("  " + plain("my_computer_zone") + "  ")

    # ================================================================ panel zadań
    def update_taskpane(self):
        tp = self.taskpane
        tp.setUpdatesEnabled(False)
        tp.clear()
        loc = self.location or ""
        sel = self.selected()
        if loc == "horyzont:computer":
            s = tp.add_section(plain("task_system"), special=True)
            s.add_link("sysinfo", plain("t_view_sysinfo"), lambda: launcher.start_builtin("control", ["system"]))
            s.add_link("addremove", plain("t_addremove"), lambda: launcher.start_builtin("control", ["addremove"]))
            s.add_link("control_panel", plain("t_change_setting"), lambda: launcher.start_builtin("control"))
            o = tp.add_section(plain("task_other_places"))
            self._place_link(o, "network", plain("my_network"), "horyzont:network")
            self._place_link(o, "documents", plain("my_documents"), config.user_dir("DOCUMENTS"))
            self._place_link(o, "control_panel", plain("control_panel"), "horyzont:control")
            self._details_section(tp, sel, computer=True)
        elif loc == "horyzont:recycle":
            s = tp.add_section(plain("task_bin"), special=True)
            s.add_link("recycle_empty", plain("t_empty_bin"), self.empty_bin)
            if sel:
                s.add_link("undo", plain("t_restore_item") if len(sel) == 1 else plain("t_restore_selected"), self.restore_selected)
            else:
                s.add_link("undo", plain("t_restore_all"), self.restore_all)
            o = tp.add_section(plain("task_other_places"))
            self._place_link(o, "show_desktop", plain("desktop"), config.user_dir("DESKTOP"))
            self._place_link(o, "documents", plain("my_documents"), config.user_dir("DOCUMENTS"))
            self._place_link(o, "computer", plain("my_computer"), "horyzont:computer")
            self._place_link(o, "network", plain("my_network"), "horyzont:network")
            self._details_section(tp, sel)
        elif loc.startswith("horyzont:archive:"):
            from . import archive_ui
            arc, inner = archive_ui.parse_loc(loc)
            s = tp.add_section(plain("arc_tasks"), special=True)
            s.add_link("extract", plain("arc_extract_all_link"), lambda: archive_ui.ExtractWizard(arc, self).start())
            if sel:
                s.add_link("copy", plain("arc_extract_sel_link"), self.extract_selected)
            o = tp.add_section(plain("task_other_places"))
            parent_dir = os.path.dirname(arc)
            self._place_link(o, special_folder_icon(parent_dir) or "folder", display_name(parent_dir), parent_dir)
            if parent_dir != config.user_dir("DOCUMENTS"):
                self._place_link(o, "documents", plain("my_documents"), config.user_dir("DOCUMENTS"))
            self._place_link(o, "computer", plain("my_computer"), "horyzont:computer")
            d = tp.add_section(plain("task_details"))
            d.add_text(os.path.basename(arc), bold=True)
            d.add_text(plain("arc_type"))
            try:
                d.add_text(f"{plain('size').rstrip(':')}: {sysctl.human_size(os.path.getsize(arc))}")
            except OSError:
                pass
        elif loc == "horyzont:network":
            s = tp.add_section(plain("nc_tasks"), special=True)
            s.add_link("drive_network", plain("t_add_network_place"), self.map_network_drive)
            s.add_link("network_conn", plain("t_view_connections"), lambda: launcher.start_builtin("control", ["network"]))
            o = tp.add_section(plain("task_other_places"))
            self._place_link(o, "show_desktop", plain("desktop"), config.user_dir("DESKTOP"))
            self._place_link(o, "computer", plain("my_computer"), "horyzont:computer")
            self._place_link(o, "documents", plain("my_documents"), config.user_dir("DOCUMENTS"))
            self._details_section(tp, sel)
        else:
            s = tp.add_section(plain("task_file_folder"), special=True)
            disc = isomount.disc_mount(loc) if not sel else None
            if disc:
                # katalog główny płyty / obrazu: tylko do odczytu — jak w XP: instalator i wysuwanie
                setup = isomount.setup_program(loc)
                if setup:
                    s.add_link("app", T("Uruchom program instalacyjny", "Run the setup program"),
                               lambda p=setup: launcher.open_path(p))
                s.add_link("drive_cd", T("Wysuń ten dysk", "Eject this disc"),
                           lambda d=disc, mp=loc: self.eject_image(d, mp) if isomount.loop_base(d)
                           else self._eject(SimpleNamespace(path=mp, extra={"device": d})))
                s.add_link("copy", plain("t_share_folder_path"), lambda: QApplication.clipboard().setText(loc))
            elif not sel:
                s.add_link("new_folder", plain("t_make_folder"), self.new_folder)
                s.add_link("copy", plain("t_share_folder_path"), lambda: QApplication.clipboard().setText(loc))
            elif len(sel) == 1:
                it = sel[0]
                isd = it.is_dir
                from ...common import archives as _arc
                if not isd and _arc.is_archive(it.path, browsable_only=False):
                    from . import archive_ui
                    s.add_link("extract", plain("arc_extract_all_link"), lambda p=it.path: (archive_ui.ExtractWizard(p, self).start(), self.refresh()))
                s.add_link("rename", plain("t_rename_folder" if isd else "t_rename"), self.rename)
                s.add_link("cut", plain("t_move_folder" if isd else "t_move"), lambda: self.copy_move_to(True))
                s.add_link("copy", plain("t_copy_folder" if isd else "t_copy"), lambda: self.copy_move_to(False))
                s.add_link("delete", plain("t_delete_folder" if isd else "t_delete"), lambda: self.delete(False))
            else:
                s.add_link("cut", plain("t_move_items"), lambda: self.copy_move_to(True))
                s.add_link("copy", plain("t_copy_items"), lambda: self.copy_move_to(False))
                s.add_link("delete", plain("t_delete_items"), lambda: self.delete(False))
            if loc == config.user_dir("PICTURES"):
                pt = tp.add_section(plain("picture_tasks"))
                pt.add_link("image_viewer", plain("t_slideshow"), self.slideshow)
            if loc == config.user_dir("MUSIC"):
                mt = tp.add_section(plain("music_tasks"))
                mt.add_link("media_player", plain("t_play_all"), lambda: launcher.xdg_open(loc))
            o = tp.add_section(plain("task_other_places"))
            parent = os.path.dirname(loc.rstrip("/")) if loc != "/" else None
            if parent:
                self._place_link(o, special_folder_icon(parent) or "folder", display_name(parent), parent)
            elif loc == "/":
                self._place_link(o, "computer", plain("my_computer"), "horyzont:computer")
            docs = config.user_dir("DOCUMENTS")
            if loc != docs:
                self._place_link(o, "documents", plain("my_documents"), docs)
            if loc != config.user_dir("DESKTOP"):
                self._place_link(o, "show_desktop", plain("desktop"), config.user_dir("DESKTOP"))
            self._place_link(o, "computer", plain("my_computer"), "horyzont:computer")
            self._place_link(o, "network", plain("my_network"), "horyzont:network")
            self._details_section(tp, sel)
        tp.setUpdatesEnabled(True)

    def _place_link(self, section, icon, text, path):
        """Link w „Inne miejsca” — kliknięcie otwiera, prawy przycisk pokazuje menu jak dla ikony."""
        if path == "horyzont:control":
            cb = lambda: launcher.start_builtin("control")  # noqa: E731
        else:
            cb = lambda p=path: self.navigate(p)  # noqa: E731
        return section.add_link(icon, text, cb, context=lambda gpos, p=path: self.place_menu(p, gpos))

    def place_menu(self, path, gpos):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        bold = m.font()
        bold.setBold(True)
        if path == "horyzont:control":
            a = m.addAction(tr("open"), lambda: launcher.start_builtin("control"))
            a.setFont(bold)
            m.addAction(tr("open_new_window"), lambda: launcher.start_builtin("control"))
            m.exec(gpos)
            return
        a = m.addAction(tr("open"), lambda: self.navigate(path))
        a.setFont(bold)
        m.addAction(tr("explore"), lambda: (self.navigate(path), self.set_side("folders")))
        m.addAction(tr("open_new_window"), lambda: self.ctl.open(path))
        if path == "horyzont:computer":
            m.addAction(tr("search_dots"), lambda: self.set_side("search"))
            m.addAction(tr("manage"), lambda: launcher.start_builtin("control", ["disks"]))
            m.addSeparator()
            m.addAction(tr("map_drive"), self.map_network_drive)
            m.addAction(tr("disconnect_drive"), lambda: self.navigate("horyzont:computer"))
            m.addSeparator()
            m.addAction(tr("properties"), lambda: launcher.start_builtin("control", ["system"]))
        elif path == "horyzont:network":
            m.addAction(tr("search_computers"), lambda: self.set_side("search"))
            m.addSeparator()
            m.addAction(tr("map_drive"), self.map_network_drive)
            m.addSeparator()
            m.addAction(tr("properties"), lambda: launcher.start_builtin("control", ["network"]))
        elif path == "horyzont:recycle":
            m.addAction(tr("empty_bin"), self.empty_bin)
            m.addSeparator()
            m.addAction(tr("properties"), lambda: PropertiesDialog([path], self).exec())
        else:
            m.addAction(tr("search_dots"), lambda: (self.navigate(path), self.set_side("search")))
            m.addSeparator()
            m.addAction(tr("copy_path"), lambda: QApplication.clipboard().setText(path))
            m.addSeparator()
            m.addAction(tr("properties"), lambda: PropertiesDialog([path], self).exec())
        m.exec(gpos)

    def _details_section(self, tp, sel, computer=False):
        d = tp.add_section(plain("task_details"))
        d.set_expanded(len(sel) > 0 or computer)
        if computer and not sel:
            d.add_text(sysctl.hostname(), bold=True)
            d.add_text(sysctl.os_name())
            d.add_text(sysctl.cpu_name())
            d.add_text(tr("sys_ram", sysctl.human_size(sysctl.mem_total())))
            return
        if not sel:
            loc = self.location or ""
            d.add_text(display_name(loc), bold=True)
            d.add_text(plain("file_folder") if not loc.startswith("horyzont:") else "")
            try:
                d.add_text(tr("modified_c", "") + " " + format_date(os.stat(loc).st_mtime))
            except OSError:
                pass
            return
        if len(sel) == 1:
            it = sel[0]
            d.add_text(it.label, bold=True)
            d.add_text(it.type_name)
            if it.kind == "drive" and it.extra.get("total"):
                d.add_text(f"{plain('free_space_c')} {it.extra.get('free')}")
                d.add_text(f"{plain('capacity')} {it.extra.get('total')}")
                d.add_text(f"{plain('file_system')} {it.extra.get('fs')}")
            else:
                if it.mtime:
                    d.add_text(f"{plain('modified_c')} {format_date(it.mtime)}")
                if not it.is_dir:
                    d.add_text(f"{plain('size').rstrip(':')}: {sysctl.human_size(it.size)}")
                if it.kind == "trash":
                    d.add_text(f"{plain('orig_location')}: {it.extra.get('orig')}")
            if it.kind == "file" and os.path.splitext(it.path)[1].lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                pm = self.thumbs.get(it.path)
                if pm:
                    lbl = QLabel()
                    lbl.setPixmap(pm.scaled(150, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    d.add_widget(lbl)
        else:
            d.add_text(tr("n_selected", len(sel)), bold=True)
            total = sum(i.size for i in sel if not i.is_dir)
            d.add_text(f"{plain('total_size_label')} {sysctl.human_size(total)}")

    # ================================================================ akcje
    def _activated(self, index):
        it = index.data(ItemRole)
        if it is None or it.header:
            return
        self.open_item(it)

    def open_item(self, it, new_window=False):
        if it.kind == "archive_entry":
            from . import archive_ui
            if it.is_dir:
                self.navigate(it.path)
            else:
                archive_ui.open_member(self, it.extra["archive"], it.extra["member"])
            return
        if it.kind == "trash":
            PropertiesDialog([it.path], self).exec()
            return
        if it.kind == "drive" and it.extra.get("empty"):
            dialogs.message(self, it.label, plain("drive_not_ready"), "warning")
            return
        if it.is_dir or it.kind == "drive":
            if new_window or not config.get("explorer_same_window", True):
                self.ctl.open(it.path)
            else:
                self.navigate(it.path)
            return
        if it.kind == "link":
            e = desktopentry.parse(it.path)
            if e and e.type == "Link":
                self._open_link_file(it.path)
                return
        if it.kind == "file" and isomount.is_mountable(it.path) and config.get("iso_open_mounts", True) \
                and isomount.available():
            self.mount_image(it.path)
            return
        launcher.open_path(it.path)

    # ================================================================ obrazy płyt (.iso)
    def mount_image(self, path, navigate=True):
        """Montuje obraz płyty jako wirtualną stację CD i otwiera ją (jak „Zamontuj” w Windows)."""
        mp = isomount.mountpoint_for(path)
        if mp:
            if navigate:
                self.navigate(mp)
            return
        QApplication.setOverrideCursor(Qt.BusyCursor)
        self.status_left.setText(T("Montowanie obrazu „{0}”…", "Mounting image \"{0}\"...").format(os.path.basename(path)))

        def done(mp, err):
            QApplication.restoreOverrideCursor()
            self.update_status()
            if err == "NO_UDISKS":
                mp, err = isomount.mount_privileged(path, self)
            if mp:
                self.refresh()
                if navigate:
                    self.navigate(mp)
                return
            name = os.path.basename(path)
            if err == "NO_FS":
                msg = T("Plik „{0}” nie zawiera systemu plików płyty CD/DVD, który można zamontować.",
                        "The file \"{0}\" does not contain a CD/DVD file system that can be mounted.").format(name)
            else:
                msg = T("Nie można zamontować obrazu „{0}”.", "Cannot mount the image \"{0}\".").format(name)
                if "NotAuthorized" in err or "not authorized" in err.lower():
                    msg += "\n\n" + T("Brak uprawnień do montowania (polkit).", "Not authorized to mount (polkit).")
                elif err.strip():
                    msg += "\n\n" + err.strip()[-600:]
            dialogs.message(self, T("Zamontuj", "Mount"), msg, "error")

        isomount.run_async(isomount.mount, (path,), done)

    def eject_image(self, device, mountpoint=""):
        QApplication.setOverrideCursor(Qt.BusyCursor)

        def done(ok, err):
            QApplication.restoreOverrideCursor()
            if not ok and mountpoint and os.path.ismount(mountpoint) and "busy" not in err.lower():
                # zamontowany przez pkexec (bez udisks2) — odmontowanie też jako administrator
                ok, err = isomount.eject_privileged(mountpoint, self)
                ok = ok and not os.path.ismount(mountpoint)
            if ok:
                cur = self.current_dir() or ""
                if mountpoint and (cur == mountpoint or cur.startswith(mountpoint + "/")):
                    self.navigate("horyzont:computer")
                self.refresh()
                return
            msg = T("Nie można wysunąć stacji — jakiś program używa plików z tej płyty. Zamknij go i spróbuj ponownie.",
                    "Cannot eject the drive because a program is using files on this disc. Close it and try again.")
            if err and err != "busy":
                msg += "\n\n" + err.strip()[-600:]
            dialogs.message(self, plain("eject"), msg, "warning")

        isomount.run_async(isomount.eject, (device or mountpoint,), done)

    def _open_link_file(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("URL="):
                        url = line[4:].strip()
                        if url.startswith("file://"):
                            p = urllib.parse.unquote(url[7:])
                            if os.path.isdir(p):
                                self.navigate(p)
                            else:
                                launcher.open_path(p)
                        else:
                            launcher.xdg_open(url)
                        return
        except OSError:
            pass

    def open_selected(self):
        w = QApplication.focusWidget()
        if w is not None and w is not self.views.view():
            return
        for it in self.selected()[:10]:
            self.open_item(it)

    def compress_selected(self, ask):
        from . import archive_ui
        paths = self.selected_paths()
        t = archive_ui.compress(self, paths, ask)
        if t:
            self.refresh()
            idx = self.model.index_of_path(t)
            if idx.isValid():
                self.views.view().setCurrentIndex(idx)

    def extract_selected(self):
        from . import archive_ui
        sel = [i for i in self.selected() if i.kind == "archive_entry"]
        if not sel:
            return
        d = dialogs.choose_dir(self, plain("arc_extract_sel").replace("&", ""), os.path.dirname(sel[0].extra["archive"]))
        if d:
            if archive_ui.run_extract(self, sel[0].extra["archive"], d, [i.extra["member"] for i in sel]):
                launcher.start_builtin("explorer", [d])

    def current_dir(self):
        if self.location and not self.location.startswith("horyzont:"):
            return self.location
        return None

    def new_folder(self):
        d = self.current_dir()
        if not d:
            return
        try:
            p = fileops.new_folder(d)
        except OSError as e:
            dialogs.message(self, plain("error"), str(e), "error")
            return
        self.folder_model.refresh()
        QTimer.singleShot(50, lambda: self.views.select_path(p, edit=True))

    def new_file(self, kind):
        d = self.current_dir()
        if not d:
            return
        try:
            if kind == "text":
                p = fileops.new_text_document(d)
            else:
                return
        except OSError as e:
            dialogs.message(self, plain("error"), str(e), "error")
            return
        self.folder_model.refresh()
        QTimer.singleShot(50, lambda: self.views.select_path(p, edit=True))

    def new_from_template(self, src):
        d = self.current_dir()
        if not d:
            return
        name = fileops.unique_name(d, os.path.basename(src))
        dest = os.path.join(d, name)
        shutil.copy2(src, dest)
        self.folder_model.refresh()
        QTimer.singleShot(50, lambda: self.views.select_path(dest, edit=True))

    def rename(self):
        v = self.views.view()
        idx = v.currentIndex()
        sel = self.selected()
        if len(sel) == 1 and self.model is self.folder_model:
            idx = self.model.index_of_path(sel[0].path)
            v.setCurrentIndex(idx)
            v.edit(idx)

    def delete(self, permanent=False):
        if self.model is self.trash_model:
            sel = self.selected()
            if sel and dialogs.message(self, plain("confirm_delete_title"),
                                       tr("confirm_delete_perm", sel[0].label) if len(sel) == 1 else tr("confirm_delete_many", len(sel)),
                                       "warning", ("yes", "no")) == "yes":
                for it in sel:
                    fileops.trash_delete(it.extra["trash"])
                self.trash_model.refresh()
            return
        paths = [i.path for i in self.selected() if i.kind in ("file", "dir", "link")]
        if not paths:
            return
        first = os.path.basename(paths[0])
        if permanent:
            text = tr("confirm_delete_perm", first) if len(paths) == 1 else tr("confirm_delete_many", len(paths))
        else:
            text = tr("confirm_delete_one", first) if len(paths) == 1 else tr("confirm_delete_many", len(paths))
        if dialogs.message(self, plain("confirm_delete_title"), text, "warning" if permanent else "recycle_full",
                           ("yes", "no")) != "yes":
            return
        errors = fileops.delete_permanently(paths) if permanent else fileops.trash_paths(paths)
        if errors:
            dialogs.message(self, plain("error"), "\n".join(f"{os.path.basename(p)}: {m}" for p, m in errors[:6]), "error")
        self.refresh()

    def copy(self):
        p = self.selected_paths()
        if p:
            fileops.set_clipboard(p, False)

    def cut(self):
        p = self.selected_paths()
        if p:
            fileops.set_clipboard(p, True)

    def paste(self):
        d = self.current_dir()
        if not d:
            return
        paths, cut = fileops.get_clipboard()
        if not paths:
            return

        def done(created, errors):
            if cut:
                QApplication.clipboard().clear()
            self.refresh()
        run_copy(self, paths, d, move=cut, done=done)

    def paste_shortcut(self):
        d = self.current_dir()
        if not d:
            return
        for p in fileops.get_clipboard()[0]:
            fileops.new_shortcut(d, p)
        self.refresh()

    def copy_move_to(self, move):
        paths = self.selected_paths()
        if not paths:
            return
        dest = dialogs.choose_dir(self, plain("move_to_folder" if move else "copy_to_folder"), self.current_dir() or "")
        if dest:
            run_copy(self, paths, dest, move=move, done=lambda c, e: self.refresh())

    def _dropped(self, paths, target, mods):
        dest = target or self.current_dir()
        if not dest or not paths:
            return
        if self.location == "horyzont:recycle" and not target:
            fileops.trash_paths(paths)
            self.refresh()
            return
        try:
            same_fs = all(os.stat(p).st_dev == os.stat(dest).st_dev for p in paths)
        except OSError:
            same_fs = False
        move = same_fs
        if mods & int(Qt.ControlModifier.value if hasattr(Qt.ControlModifier, "value") else Qt.ControlModifier):
            move = False
        if mods & int(Qt.ShiftModifier.value if hasattr(Qt.ShiftModifier, "value") else Qt.ShiftModifier):
            move = True
        if move and all(os.path.dirname(p) == dest for p in paths):
            return
        run_copy(self, paths, dest, move=move, done=lambda c, e: self.refresh())

    def properties(self):
        sel = self.selected()
        if self.location == "horyzont:computer" and not sel:
            launcher.start_builtin("control", ["system"])
            return
        paths = [i.path for i in sel if i.path] or ([self.current_dir()] if self.current_dir() else [])
        if paths:
            PropertiesDialog(paths, self).show()

    def empty_bin(self):
        n = fileops.trash_count()
        if n and dialogs.message(self, plain("recycle_bin"), tr("confirm_empty_bin", n), "recycle_full", ("yes", "no")) == "yes":
            fileops.trash_empty()
            self.trash_model.refresh()
            self.update_taskpane()
            self.update_status()

    def restore_selected(self):
        for it in self.selected():
            if it.kind == "trash":
                try:
                    fileops.trash_restore(it.extra["trash"])
                except OSError as e:
                    dialogs.message(self, plain("error"), str(e), "error")
        self.trash_model.refresh()

    def restore_all(self):
        for t in fileops.trash_list():
            try:
                fileops.trash_restore(t)
            except OSError:
                pass
        self.trash_model.refresh()

    def slideshow(self):
        imgs = [i.path for i in self.model.items if i.kind == "file" and os.path.splitext(i.path)[1].lower()
                in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")]
        if imgs:
            launcher.xdg_open(imgs[0])

    def map_network_drive(self):
        addr = dialogs.ask_text(self, plain("map_network").replace("&", "").rstrip("."), plain("map_network_prompt"),
                                "smb://")
        if addr and shutil.which("gio"):
            r = subprocess.run(["gio", "mount", addr], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                dialogs.message(self, plain("error"), r.stderr.strip() or r.stdout.strip(), "error")
            else:
                self.navigate("horyzont:network")

    def disconnect_drive(self):
        sel = [i for i in self.selected() if i.path.startswith(f"/run/user/{os.getuid()}/gvfs")]
        for it in sel:
            subprocess.run(["gio", "mount", "-u", it.path], capture_output=True)
        self.refresh()

    # ================================================================ menu
    def _update_edit_menu(self):
        has = bool(self.selected_paths())
        self.a_cut.setEnabled(has)
        self.a_copy.setEnabled(has)
        can_paste = bool(self.current_dir()) and fileops.clipboard_has_files()
        self.a_paste.setEnabled(can_paste)
        self.a_paste_sc.setEnabled(can_paste)

    def _fill_file_menu(self):
        m = self.m_file
        m.clear()
        sel = self.selected()
        if sel:
            self._item_actions(m, sel)
        else:
            if self.current_dir():
                self._new_menu(m)
                m.addSeparator()
            m.addAction(tr("create_shortcut")).setEnabled(False)
            m.addAction(tr("delete")).setEnabled(False)
            m.addAction(tr("rename")).setEnabled(False)
            m.addAction(tr("properties"), self.properties)
        m.addSeparator()
        m.addAction(tr("close_window"), self.close)

    def _new_menu(self, m):
        new = m.addMenu(tr("desk_new"))
        new.addAction(iconcache.icon("folder"), tr("new_folder"), self.new_folder)
        new.addAction(iconcache.icon("shortcut_overlay"), tr("new_shortcut"), self._new_shortcut)
        new.addSeparator()
        new.addAction(iconcache.icon("file_text"), plain("new_text"), lambda: self.new_file("text"))
        tpl = os.path.expanduser("~/Templates")
        if os.path.isdir(tpl):
            for fn in sorted(os.listdir(tpl)):
                fp = os.path.join(tpl, fn)
                if os.path.isfile(fp):
                    new.addAction(iconcache.icon(iconcache.name_for_file(fp)), os.path.splitext(fn)[0],
                                  lambda fp=fp: self.new_from_template(fp))

    def _new_shortcut(self):
        d = self.current_dir()
        target = dialogs.ask_text(self, plain("new_shortcut"), plain("location"), os.path.expanduser("~"))
        if d and target:
            fileops.new_shortcut(d, os.path.expanduser(target))
            self.refresh()

    def _item_actions(self, m, sel):
        it = sel[0]

        def bold(a):
            f = a.font()
            f.setBold(True)
            a.setFont(f)
            return a

        if it.kind == "trash":
            bold(m.addAction(tr("restore"), self.restore_selected))
            m.addSeparator()
            m.addAction(tr("cut")).setEnabled(False)
            m.addSeparator()
            m.addAction(tr("delete"), lambda: self.delete(False))
            m.addSeparator()
            m.addAction(tr("properties"), lambda: PropertiesDialog([it.path], self).show())
            return
        if it.kind == "archive_entry":
            from . import archive_ui
            bold(m.addAction(tr("open"), lambda: self.open_item(it)))
            m.addAction(iconcache.icon("extract"), tr("arc_extract_sel"), self.extract_selected)
            m.addSeparator()
            m.addAction(tr("arc_extract_all"), lambda: archive_ui.ExtractWizard(it.extra["archive"], self).start())
            return
        if it.kind == "file" and len(sel) == 1 and isomount.is_mountable(it.path) and isomount.available():
            mp = isomount.mountpoint_for(it.path)
            if mp:
                bold(m.addAction(iconcache.icon("drive_cd"), T("Otwórz stację CD", "Open CD Drive"), lambda: self.navigate(mp)))
                m.addAction(plain("eject"), lambda: self.eject_image(isomount.loop_for(it.path), mp))
            else:
                bold(m.addAction(iconcache.icon("drive_cd"), T("Zamontuj", "Mount"), lambda: self.mount_image(it.path)))
            from ...common import archives as _arc0
            if _arc0.is_archive(it.path):
                m.addAction(T("Przeglądaj jako folder skompresowany", "Browse as compressed folder"),
                            lambda: self.navigate(it.path))
        else:
            bold(m.addAction(tr("open"), lambda: [self.open_item(i) for i in sel[:10]]))
        if it.kind == "file":
            ext = os.path.splitext(it.path)[1].lower()
            if ext in launcher.BUILTIN_VIEWERS["imageviewer"]:
                m.addAction(tr("open_preview"), lambda: launcher.start_builtin("imageviewer", [it.path]))
                if ext not in (".heic", ".avif", ".tga"):
                    m.addAction(tr("open_edit"), lambda: launcher.start_builtin("paint", [it.path]))
            elif ext in launcher.BUILTIN_VIEWERS["mplayer"] or ext == ".wav":
                m.addAction(tr("open_play"), lambda: launcher.start_builtin("mplayer", [p.path for p in sel[:200]]))
                if ext == ".wav":
                    m.addAction(tr("open_edit"), lambda: launcher.start_builtin("soundrec", [it.path]))
            elif ext in (".rtf", ".docx", ".odt"):
                m.addAction(tr("open_edit"), lambda: launcher.start_builtin("wordpad", [it.path]))
        from ...common import archives as _arc
        if it.kind == "file" and len(sel) == 1 and _arc.is_archive(it.path, browsable_only=False):
            from . import archive_ui
            m.addAction(iconcache.icon("extract"), tr("arc_extract_all"), lambda: (archive_ui.ExtractWizard(it.path, self).start(), self.refresh()))
            m.addAction(tr("arc_extract_here"), lambda: (archive_ui.extract_here(self, it.path), self.refresh()))
        if it.is_dir or it.kind == "drive":
            m.addAction(tr("explore"), lambda: self.ctl.open(it.path, folders=True))
            m.addAction(tr("search_dots"), lambda: (self.navigate(it.path), self.set_side("search")))
        elif it.kind == "file":
            ow = m.addMenu(tr("open_with"))
            self._fill_open_with(ow, it.path)
        if it.kind == "drive":
            m.addSeparator()
            if it.path.startswith(("/run/media", "/media")):
                m.addAction(plain("eject"), lambda: self._eject(it))
            m.addSeparator()
            m.addAction(tr("properties"), lambda: PropertiesDialog([it.path], self).show())
            return
        m.addSeparator()
        st = m.addMenu(tr("send_to"))
        st.addAction(iconcache.icon("folder_zip"), plain("arc_send_zip"), lambda: self.compress_selected(False))
        st.addAction(iconcache.icon("desktop_folder"), plain("send_desktop_shortcut"),
                     lambda: [fileops.new_shortcut(config.user_dir("DESKTOP"), p,
                                                   os.path.splitext(os.path.basename(p))[0]) for p in self.selected_paths()])
        st.addAction(iconcache.icon("documents"), plain("my_documents"),
                     lambda: run_copy(self, self.selected_paths(), config.user_dir("DOCUMENTS")))
        if shutil.which("bluetoothctl"):
            st.addAction(iconcache.icon("bluetooth"), T("Urządzenie Bluetooth…", "Bluetooth Device..."),
                         lambda: __import__("horyzont.common.btsend", fromlist=["x"]).send_files(self.selected_paths(), self))
        for d in self._removable_dirs():
            st.addAction(iconcache.icon("drive_usb"), os.path.basename(d), lambda d=d: run_copy(self, self.selected_paths(), d))
        m.addAction(iconcache.icon("folder_zip"), tr("arc_add_to"), lambda: self.compress_selected(True))
        m.addSeparator()
        m.addAction(tr("cut"), self.cut)
        m.addAction(tr("copy"), self.copy)
        if len(sel) == 1 and it.is_dir and fileops.clipboard_has_files():
            m.addAction(tr("paste"), lambda: run_copy(self, fileops.get_clipboard()[0], it.path,
                                                      move=fileops.get_clipboard()[1], done=lambda c, e: self.refresh()))
        m.addSeparator()
        m.addAction(tr("create_shortcut"), lambda: ([fileops.new_shortcut(self.current_dir(), p) for p in self.selected_paths()],
                                                    self.refresh()) if self.current_dir() else None)
        m.addAction(tr("delete"), lambda: self.delete(False))
        r = m.addAction(tr("rename"), self.rename)
        r.setEnabled(len(sel) == 1 and self.model is self.folder_model)
        m.addSeparator()
        m.addAction(tr("properties"), self.properties)

    def _removable_dirs(self):
        out = []
        for base in (f"/run/media/{sysctl.user_login()}", "/media"):
            if os.path.isdir(base):
                for n in os.listdir(base):
                    p = os.path.join(base, n)
                    if os.path.ismount(p):
                        out.append(p)
        return out

    def _eject(self, it):
        dev = it.extra.get("device", "")
        if isomount.loop_base(dev):
            self.eject_image(dev, it.path)
            return
        if shutil.which("gio"):
            subprocess.run(["gio", "mount", "-e", it.path], capture_output=True)
        elif shutil.which("udisksctl"):
            subprocess.run(["udisksctl", "unmount", "-b", it.extra.get("device", "")], capture_output=True)
        self.refresh()

    def _fill_open_with(self, menu, path):
        from ...common.openwith import fill_menu
        fill_menu(menu, path)

    def _context_menu(self, pos):
        v = self.views.view()
        idx = v.indexAt(pos)
        gpos = v.viewport().mapToGlobal(pos)
        m = QMenu(self)
        if idx.isValid() and idx.data(ItemRole) is not None and not idx.data(ItemRole).header:
            if not v.selectionModel().isSelected(idx):
                v.setCurrentIndex(idx)
            self._item_actions(m, self.selected())
        else:
            v.clearSelection()
            vm = m.addMenu(tr("menu_view").replace("&", "&"))
            self._fill_view_menu(vm)
            for a in vm.actions():
                a.setChecked(a.data() == self.views.mode)
            arr = m.addMenu(tr("arrange_icons_by"))
            for k in self.model.columns:
                from .model import COLUMN_TITLES
                arr.addAction(plain(COLUMN_TITLES.get(k, k)).rstrip(":"), lambda c=k: self.arrange(c))
            m.addSeparator()
            m.addAction(tr("refresh"), self.refresh)
            if self.location == "horyzont:recycle":
                m.addSeparator()
                m.addAction(tr("empty_bin"), self.empty_bin).setEnabled(fileops.trash_count() > 0)
            if self.current_dir():
                m.addSeparator()
                pa = m.addAction(tr("paste"), self.paste)
                pa.setEnabled(fileops.clipboard_has_files())
                ps = m.addAction(tr("desk_paste_shortcut"), self.paste_shortcut)
                ps.setEnabled(fileops.clipboard_has_files())
                m.addSeparator()
                self._new_menu(m)
                m.addSeparator()
                m.addAction(plain("open_terminal_here"), lambda: launcher.open_terminal(self.current_dir()))
            m.addSeparator()
            m.addAction(tr("properties"), self.properties)
        m.exec(gpos)

    def _fill_favorites(self):
        m = self.m_fav
        m.clear()
        m.addAction(tr("add_favorites"), self._add_favorite)
        m.addAction(tr("organize_favorites"), self._organize_favorites)
        m.addSeparator()
        for p in self._favorites():
            if os.path.exists(p) or p.startswith("horyzont:"):
                m.addAction(iconcache.icon(location_icon(p)), display_name(p), lambda p=p: self.navigate(p))

    def _favorites(self):
        favs = list(config.get("favorites", []))
        bm = os.path.expanduser("~/.config/gtk-3.0/bookmarks")
        try:
            with open(bm, encoding="utf-8") as f:
                for line in f:
                    url = line.split(" ")[0].strip()
                    if url.startswith("file://"):
                        p = urllib.parse.unquote(url[7:])
                        if p not in favs:
                            favs.append(p)
        except OSError:
            pass
        return favs

    def _add_favorite(self):
        favs = list(config.get("favorites", []))
        if self.location and self.location not in favs:
            favs.append(self.location)
            config.set("favorites", favs)

    def _organize_favorites(self):
        favs = list(config.get("favorites", []))
        if not favs:
            dialogs.message(self, plain("menu_favorites").replace("&", ""), plain("favorites_empty"), "info")
            return
        from PySide6.QtWidgets import QListWidget, QPushButton
        from ...common.window import HDialog
        d = HDialog(tr("organize_favorites").replace("&", "").rstrip("."), "star", self)
        lay = QVBoxLayout(d.body())
        lw = QListWidget()
        for p in favs:
            lw.addItem(p)
        lay.addWidget(lw)
        row = QHBoxLayout()
        rm = QPushButton(plain("delete"))
        rm.clicked.connect(lambda: [lw.takeItem(lw.row(i)) for i in lw.selectedItems()])
        ok = QPushButton(plain("close"))
        ok.clicked.connect(d.accept)
        row.addWidget(rm)
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)
        d.resize(400, 300)
        d.exec()
        config.set("favorites", [lw.item(i).text() for i in range(lw.count())])

    def closeEvent(self, e):
        self.search.stop()
        super().closeEvent(e)
