"""Okno Panelu sterowania: widok kategorii i widok klasyczny."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMenuBar,
                               QScrollArea, QSplitter, QStackedWidget,
                               QStatusBar, QToolBar, QToolButton, QVBoxLayout,
                               QWidget, QAbstractItemView, QListView)
from PySide6.QtGui import QAction

from ... import config
from ...common import launcher
from ...common.taskpane import TaskLink, TaskPane
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ...theme.base import hgrad
from ...theme.manager import current
from .registry import APPLETS, CATEGORIES


class BigTitle(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        f = current().font("title_big")
        f.setPixelSize(int(22 * current().font_scale))
        f.setBold(False)
        self.setFont(f)
        self.setStyleSheet(f"color: {current().color('group_title').name()};")


class CategoryLink(QWidget):
    def __init__(self, icon, text, callback, parent=None, size=32):
        super().__init__(parent)
        self.icon, self.text, self.cb, self.size = icon, text, callback, size
        self._hover = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(size + 10)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.cb()

    def sizeHint(self):
        return QSize(260, self.size + 12)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        p.drawPixmap(4, (self.height() - self.size) // 2, iconcache.pixmap(self.icon, self.size))
        f = t.font("normal")
        if self.size >= 32:
            f.setPixelSize(int(12 * t.font_scale))
        f.setUnderline(self._hover)
        p.setFont(f)
        p.setPen(t.color("taskpane_link_hover" if self._hover else "taskpane_link"))
        p.drawText(QRect(self.size + 14, 0, self.width() - self.size - 16, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text)


class ControlPanelWindow(HWindow):
    def __init__(self, ctl):
        super().__init__(plain("control_panel"), "control_panel")
        self.ctl = ctl
        self.history = []
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        mb = QMenuBar()
        m = mb.addMenu(tr("menu_file"))
        m.addAction(tr("close_window"), self.close)
        m = mb.addMenu(tr("menu_edit"))
        m.addAction(tr("np_select_all")).setEnabled(False)
        m = mb.addMenu(tr("menu_view"))
        self.a_cat = m.addAction(plain("t_switch_category"), lambda: self.set_view("category"))
        self.a_cls = m.addAction(plain("t_switch_classic"), lambda: self.set_view("classic"))
        m.addSeparator()
        m.addAction(tr("refresh") + "\tF5", self.refresh)
        mb.addMenu(tr("menu_favorites")).addAction(tr("add_favorites")).setEnabled(False)
        m = mb.addMenu(tr("menu_tools"))
        m.addAction(tr("folder_options"), lambda: self.open_applet("folder_options"))
        m = mb.addMenu(tr("menu_help"))
        m.addAction(tr("help_topics"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        m.addSeparator()
        m.addAction(tr("about_os"), lambda: launcher.start_builtin("winver"))
        lay.addWidget(mb)
        tb = QToolBar()
        tb.setIconSize(QSize(24, 24))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.a_back = tb.addAction(iconcache.icon("back"), plain("back"), self.back)
        self.a_fwd = tb.addAction(iconcache.icon("forward"), "", lambda: None)
        self.a_fwd.setEnabled(False)
        tb.addAction(iconcache.icon("up"), "", lambda: launcher.start_builtin("explorer", ["horyzont:computer"]))
        tb.addSeparator()
        tb.addAction(iconcache.icon("search"), plain("search"), lambda: launcher.start_builtin("explorer", ["--search"]))
        tb.addAction(iconcache.icon("folders_tree"), plain("folders"),
                     lambda: launcher.start_builtin("explorer", ["--folders", "horyzont:computer"]))
        lay.addWidget(tb)
        addr = QWidget()
        al = QHBoxLayout(addr)
        al.setContentsMargins(4, 2, 4, 2)
        l = QLabel(plain("address"))
        l.setStyleSheet("color: #6d7577;")
        al.addWidget(l)
        self.address = QComboBox()
        self.address.addItem(iconcache.icon("control_panel"), plain("control_panel"))
        al.addWidget(self.address, 1)
        go = QToolButton()
        go.setIcon(iconcache.icon("go"))
        go.setText(plain("go"))
        go.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        go.setAutoRaise(True)
        al.addWidget(go)
        lay.addWidget(addr)
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        split.addWidget(self.pane)
        self.stack = QStackedWidget()
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 560])
        lay.addWidget(split, 1)
        self.status = QStatusBar()
        lay.addWidget(self.status)
        self.page_widget = None
        self.classic = QListWidget()
        self.classic.setViewMode(QListView.IconMode)
        self.classic.setResizeMode(QListView.Adjust)
        self.classic.setMovement(QListView.Static)
        self.classic.setGridSize(QSize(96, 80))
        self.classic.setIconSize(QSize(32, 32))
        self.classic.setWordWrap(True)
        self.classic.setFrameShape(QFrame.NoFrame)
        self.classic.itemActivated.connect(lambda it: self.open_applet(it.data(Qt.UserRole)))
        self.classic.currentItemChanged.connect(self._classic_status)
        for key in sorted(APPLETS, key=lambda k: plain(APPLETS[k][0]).lower()):
            name, desc, icon, _, _ = APPLETS[key]
            it = QListWidgetItem(iconcache.icon(icon), plain(name))
            it.setData(Qt.UserRole, key)
            it.setToolTip(plain(desc))
            self.classic.addItem(it)
        self.stack.addWidget(self.classic)
        self.resize(800, 560)
        self.set_view(config.get("control_view", "category"))

    # ------------------------------------------------------------ widoki
    def set_view(self, view, remember=True):
        if remember:
            config.set("control_view", view)
        self.view = view
        self.history = []
        if view == "classic":
            self.stack.setCurrentWidget(self.classic)
            self.status.showMessage(tr("n_objects", self.classic.count()))
        else:
            self.show_categories()
        self._fill_pane()

    def _fill_pane(self, category=None):
        self.pane.clear()
        s = self.pane.add_section(plain("control_panel"), special=True)
        if self.view == "classic":
            s.add_link("control_panel", plain("t_switch_category"), lambda: self.set_view("category"))
        else:
            s.add_link("control_panel", plain("t_switch_classic"), lambda: self.set_view("classic"))
        see = self.pane.add_section(plain("task_see_also"))
        see.add_link("updates", "Horyzont Updates", lambda: launcher.start_builtin("control", ["updates"]))
        see.add_link("help", plain("sm_help"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        if category is not None:
            trb = self.pane.add_section(plain("cp_troubleshooters"))
            trb.add_link("help", plain("cp_trouble_display"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        self.a_back.setEnabled(bool(self.history))

    def _scroll(self, w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(w)
        w.setAutoFillBackground(True)
        pal = w.palette()
        pal.setColor(w.backgroundRole(), QColor("#ffffff"))
        w.setPalette(pal)
        return sa

    def _set_page(self, w):
        if self.page_widget is not None:
            self.stack.removeWidget(self.page_widget)
            self.page_widget.deleteLater()
        self.page_widget = self._scroll(w)
        self.stack.addWidget(self.page_widget)
        self.stack.setCurrentWidget(self.page_widget)

    def show_categories(self):
        self.setWindowTitle(plain("control_panel"))
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(16)
        lay.addWidget(BigTitle(plain("task_pick_category")))
        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {current().color('group_title').lighter(140).name()}, stop:1 #ffffff);")
        lay.addWidget(line)
        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(12)
        for i, (key, name, icon, tasks, applets) in enumerate(CATEGORIES):
            link = CategoryLink(icon, plain(name), lambda k=key: self.show_category(k), w)
            grid.addWidget(link, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        self._set_page(w)
        self.status.showMessage("")

    def show_category(self, key, add_history=True):
        cat = next(c for c in CATEGORIES if c[0] == key)
        _, name, icon, tasks, applets = cat
        if tasks is None and len(applets) == 1:
            self.open_applet(applets[0])
            return
        if add_history:
            self.history.append("categories")
        self.setWindowTitle(plain(name))
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 18, 26, 20)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(BigTitle(plain(name)), 1)
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap(icon, 48))
        head.addWidget(ic)
        lay.addLayout(head)
        if tasks:
            lay.addWidget(BigTitle(plain("cp_pick_task")))
            for tkey, (applet, page) in tasks:
                l = CategoryLink("forward", plain(tkey), lambda a=applet, p=page: self.open_applet(a, p), w, size=16)
                lay.addWidget(l)
        lay.addSpacing(12)
        lay.addWidget(BigTitle(plain("cp_or_pick")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        for i, a in enumerate(applets):
            n, d, ic2, _, _ = APPLETS[a]
            l = CategoryLink(ic2, plain(n), lambda a=a: self.open_applet(a), w)
            l.setToolTip(plain(d))
            grid.addWidget(l, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        self._set_page(w)
        self._fill_pane(key)

    def back(self):
        if self.history:
            self.history.pop()
            self.show_categories()
            self._fill_pane()

    def refresh(self):
        self.set_view(self.view, remember=False)

    def _classic_status(self, cur, prev):
        if cur is not None:
            self.status.showMessage(cur.toolTip())

    def open_applet(self, key, page=None):
        self.ctl.open_applet(key, page, self)
