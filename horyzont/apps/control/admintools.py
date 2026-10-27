"""Narzędzia administracyjne: Usługi, Podgląd zdarzeń, Zarządzanie dyskami, Zaplanowane zadania."""
import json
import shutil
import subprocess

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMenu,
                               QPushButton, QSplitter, QTextEdit, QToolBar,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ...common import dialogs, launcher, sysctl
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from .common import run, run_privileged
from .folderwin import FolderWindow, entry


class AdminTools(FolderWindow):
    title_key = "admin_tools"
    icon = "admin"
    view_mode = "tiles"

    TOOLS = [("services", "adm_services", "gear_services"), ("events", "adm_event_viewer", "info"),
             ("disks", "adm_disk_mgmt", "drive_hdd"), ("devices", "sys_device_mgr", "system"),
             ("scheduled", "ap_scheduled", "scheduled")]

    def load_items(self):
        out = []
        for key, name, icon in self.TOOLS:
            icon = {"gear_services": "admin"}.get(icon, icon)
            out.append(entry(plain(name).replace("&", ""), icon, plain("ftype_shortcut"), "", key=key))
        return out

    def fill_tasks(self, pane, sel):
        s = pane.add_section(plain("task_file_folder"), special=True)
        if sel:
            s.add_link("forward", tr("open").replace("&", ""), lambda: self.activate(sel[0]))
        self.other_places(pane)
        self.details(pane, sel)

    def activate(self, it):
        key = it.path
        w = {"services": ServicesWindow, "events": EventViewer, "disks": DisksWindow,
             "scheduled": ScheduledWindow}.get(key)
        if key == "devices":
            from .system import DeviceManager
            w = DeviceManager
        if w:
            win = w()
            win.show()
            self._wins = getattr(self, "_wins", []) + [win]


class _Loader(QThread):
    loaded = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.loaded.emit(self.fn())
        except Exception as e:
            self.loaded.emit(e)


def list_services(user=False):
    base = ["systemctl"] + (["--user"] if user else [])
    rc, units = run(base + ["list-units", "--type=service", "--all", "--no-legend", "--no-pager", "--plain"], 20)
    rc2, files = run(base + ["list-unit-files", "--type=service", "--no-legend", "--no-pager"], 20)
    startup = {}
    for line in files.splitlines():
        p = line.split()
        if len(p) >= 2:
            startup[p[0]] = p[1]
    out = []
    seen = set()
    for line in units.splitlines():
        p = line.split(None, 4)
        if len(p) >= 4:
            name = p[0]
            seen.add(name)
            out.append((name, p[2], p[3], startup.get(name, ""), p[4] if len(p) > 4 else ""))
    for name, st in startup.items():
        if name not in seen and not name.endswith("@.service"):
            out.append((name, "inactive", "dead", st, ""))
    return sorted(out)


class ServicesWindow(HWindow):
    def __init__(self):
        super().__init__(plain("adm_services"), "admin")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        tb = QToolBar()
        tb.setIconSize(QSize(16, 16))
        self.scope = QComboBox()
        self.scope.addItems([plain("adm_system_services"), plain("adm_user_services")])
        self.scope.currentIndexChanged.connect(self.refresh)
        tb.addWidget(self.scope)
        tb.addSeparator()
        tb.addAction(iconcache.icon("media_player"), plain("adm_start").replace("&", ""), lambda: self.act("start"))
        tb.addAction(iconcache.icon("delete"), plain("adm_stop").replace("&", ""), lambda: self.act("stop"))
        tb.addAction(iconcache.icon("refresh"), plain("adm_restart").replace("&", ""), lambda: self.act("restart"))
        tb.addSeparator()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(plain("search_go"))
        self.filter.textChanged.connect(self._filter)
        tb.addWidget(self.filter)
        lay.addWidget(tb)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("adm_service_name"), plain("adm_service_desc"), plain("adm_service_status"),
                                   plain("adm_service_startup")])
        self.tree.setColumnWidth(0, 230)
        self.tree.setColumnWidth(1, 300)
        self.tree.setSortingEnabled(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        self.resize(820, 520)
        self.refresh()

    def refresh(self):
        user = self.scope.currentIndex() == 1
        self.tree.clear()
        self._ld = _Loader(lambda: list_services(user))
        self._ld.loaded.connect(self._loaded)
        self._ld.start()

    def _loaded(self, items):
        if isinstance(items, Exception):
            return
        for name, active, sub, startup, desc in items:
            st = plain("adm_started") if active == "active" else ""
            stt = {"enabled": plain("adm_auto"), "disabled": plain("adm_disabled"), "static": plain("adm_manual"),
                   "masked": plain("adm_disabled")}.get(startup, startup)
            it = QTreeWidgetItem([name, desc, st, stt])
            it.setIcon(0, iconcache.icon("admin"))
            self.tree.addTopLevelItem(it)
        self._filter(self.filter.text())

    def _filter(self, t):
        t = t.lower()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            it.setHidden(bool(t) and t not in it.text(0).lower() and t not in it.text(1).lower())

    def act(self, verb):
        it = self.tree.currentItem()
        if it is None:
            return
        name = it.text(0)
        if self.scope.currentIndex() == 1:
            r = subprocess.run(["systemctl", "--user", verb, name], capture_output=True, text=True)
            if r.returncode:
                dialogs.message(self, plain("adm_services"), r.stderr, "error")
        else:
            run_privileged(["systemctl", verb, name], self)
        self.refresh()

    def _menu(self, pos):
        if self.tree.itemAt(pos) is None:
            return
        m = QMenu(self)
        for verb, key in (("start", "adm_start"), ("stop", "adm_stop"), ("restart", "adm_restart")):
            m.addAction(tr(key), lambda v=verb: self.act(v))
        m.addSeparator()
        m.addAction(plain("adm_enable"), lambda: self.act("enable"))
        m.addAction(plain("adm_disable"), lambda: self.act("disable"))
        m.exec(self.tree.viewport().mapToGlobal(pos))


def read_journal(prio, n=400):
    if not shutil.which("journalctl"):
        return []
    args = ["journalctl", "-o", "json", "-n", str(n), "--no-pager", "-q"]
    if prio is not None:
        args += ["-p", str(prio)]
    rc, out = run(args, 30)
    events = []
    for line in out.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        events.append(j)
    events.reverse()
    return events


class EventViewer(HWindow):
    LEVELS = {0: "error", 1: "error", 2: "error", 3: "error", 4: "warning", 5: "info", 6: "info", 7: "info"}

    def __init__(self):
        super().__init__(plain("adm_event_viewer"), "info")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        self.logs = QTreeWidget()
        self.logs.setHeaderHidden(True)
        for key, prio, icon in (("adm_log_all", None, "info"), ("adm_log_errors", 3, "error"),
                                ("adm_log_warnings", 4, "warning")):
            it = QTreeWidgetItem([plain(key)])
            it.setIcon(0, iconcache.icon(icon))
            it.setData(0, Qt.UserRole, prio)
            self.logs.addTopLevelItem(it)
        self.logs.currentItemChanged.connect(lambda c, p: c and self.load(c.data(0, Qt.UserRole)))
        split.addWidget(self.logs)
        right = QSplitter(Qt.Vertical)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("adm_level"), plain("adm_time"), plain("adm_source"), plain("adm_message")])
        self.tree.setColumnWidth(0, 90)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 140)
        self.tree.currentItemChanged.connect(self._show)
        right.addWidget(self.tree)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        right.addWidget(self.detail)
        right.setSizes([380, 120])
        split.addWidget(right)
        split.setSizes([170, 650])
        lay.addWidget(split)
        self.resize(860, 560)
        self.logs.setCurrentItem(self.logs.topLevelItem(0))

    def load(self, prio):
        self.tree.clear()
        self._ld = _Loader(lambda: read_journal(prio))
        self._ld.loaded.connect(self._loaded)
        self._ld.start()

    def _loaded(self, events):
        if isinstance(events, Exception):
            return
        import datetime
        names = {"error": plain("error"), "warning": plain("warning"), "info": plain("adm_information")}
        for j in events:
            pr = int(j.get("PRIORITY", 6))
            lvl = self.LEVELS.get(pr, "info")
            ts = int(j.get("__REALTIME_TIMESTAMP", "0")) / 1e6
            t = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
            src = j.get("SYSLOG_IDENTIFIER") or j.get("_COMM") or ""
            msg = j.get("MESSAGE", "")
            if isinstance(msg, list):
                msg = bytes(msg).decode("utf-8", "replace")
            it = QTreeWidgetItem([names[lvl], t, src, msg.splitlines()[0] if msg else ""])
            it.setIcon(0, iconcache.icon(lvl))
            it.setData(0, Qt.UserRole, msg)
            self.tree.addTopLevelItem(it)

    def _show(self, cur, prev):
        if cur is not None:
            self.detail.setPlainText(cur.data(0, Qt.UserRole) or "")


class DisksWindow(HWindow):
    def __init__(self):
        super().__init__(plain("adm_disk_mgmt"), "drive_hdd")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([plain("dk_volume"), plain("size"), plain("file_system"), plain("dk_mount"),
                                   plain("dk_used"), plain("type")])
        self.tree.setColumnWidth(0, 200)
        lay.addWidget(self.tree, 1)
        info = QLabel(plain("dk_info"))
        info.setWordWrap(True)
        info.setContentsMargins(6, 4, 6, 4)
        lay.addWidget(info)
        row = QHBoxLayout()
        row.addStretch(1)
        for c, lab in ((["gnome-disks"], "dk_open_disks"), (["gparted"], "dk_open_gparted")):
            if shutil.which(c[0]):
                b = QPushButton(plain(lab))
                b.clicked.connect(lambda _=False, c=c: launcher._spawn(c))
                row.addWidget(b)
        lay.addLayout(row)
        self.resize(760, 420)
        self.load()

    def load(self):
        if not shutil.which("lsblk"):
            return
        rc, out = run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,FSUSE%,TYPE,LABEL,MODEL"])
        try:
            data = json.loads(out)
        except ValueError:
            return

        def add(parent, d):
            name = d.get("label") or d.get("model") or d["name"]
            it = QTreeWidgetItem([f"{name} ({d['name']})" if name != d["name"] else d["name"],
                                  sysctl.human_size(int(d.get("size") or 0)), (d.get("fstype") or "").upper(),
                                  d.get("mountpoint") or "", d.get("fsuse%") or "", d.get("type") or ""])
            icon = {"disk": "drive_hdd", "part": "drive_hdd", "rom": "drive_cd", "crypt": "lock"}.get(d.get("type"), "drive_hdd")
            if d.get("type") == "disk" and "usb" in (d.get("model") or "").lower():
                icon = "drive_usb"
            it.setIcon(0, iconcache.icon(icon))
            if parent is None:
                self.tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            for ch in d.get("children", []) or []:
                add(it, ch)
            it.setExpanded(True)
        for d in data.get("blockdevices", []):
            if d.get("type") in ("loop",) or d["name"].startswith(("zram", "loop")):
                continue
            add(None, d)


class ScheduledWindow(HWindow):
    def __init__(self):
        super().__init__(plain("ap_scheduled"), "scheduled")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("name"), plain("sc_next"), plain("sc_last"), plain("sc_unit"), plain("sc_scope")])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 170)
        self.tree.setColumnWidth(2, 170)
        lay.addWidget(self.tree)
        lay.addWidget(QLabel("  " + plain("sc_info")))
        self.resize(820, 420)
        for user in (False, True):
            args = ["systemctl"] + (["--user"] if user else []) + ["list-timers", "--all", "--no-pager", "-o", "json"]
            rc, out = run(args, 15)
            try:
                timers = json.loads(out)
            except ValueError:
                timers = []
            import datetime
            for t in timers:
                def fmt(us):
                    try:
                        return datetime.datetime.fromtimestamp(int(us) / 1e6).strftime("%Y-%m-%d %H:%M") if us else "—"
                    except (TypeError, ValueError):
                        return "—"
                it = QTreeWidgetItem([t.get("unit", ""), fmt(t.get("next")), fmt(t.get("last")), t.get("activates", ""),
                                      plain("sc_user") if user else plain("sc_system")])
                it.setIcon(0, iconcache.icon("scheduled"))
                self.tree.addTopLevelItem(it)


def open_admin(page=None, parent=None):
    w = AdminTools()
    if page == "disks":
        d = DisksWindow()
        d.show()
        w._wins = [d]
    return w


def open_services(page=None, parent=None):
    return ServicesWindow()


def open_events(page=None, parent=None):
    return EventViewer()


def open_disks(page=None, parent=None):
    return DisksWindow()


def open_scheduled(page=None, parent=None):
    return ScheduledWindow()
