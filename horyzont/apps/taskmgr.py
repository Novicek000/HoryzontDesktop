"""Menedżer zadań: aplikacje, procesy, wydajność, sieć, użytkownicy."""
import os
import signal
import time

import psutil
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QKeySequence, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMenu, QMenuBar,
                               QPushButton, QStatusBar, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import config
from ..common import dialogs, launcher, single, sysctl
from ..common.app import make_app
from ..common.window import HDialog, HWindow
from ..i18n import plain, tr
from ..theme import iconcache

SPEEDS = {"high": 500, "normal": 1000, "low": 4000, "paused": 0}
GREEN = QColor("#00ff00")
DARK_GREEN = QColor("#008040")
YELLOW = QColor("#ffff00")


def kb(n):
    return sysctl.group_digits(int(n // 1024))


# ------------------------------------------------------------------ wykresy
class LedMeter(QWidget):
    """Wskaźnik w stylu wyświetlacza LED z podpisem procentowym."""

    def __init__(self, color=GREEN, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.label = "0 %"
        self.color = color
        self.setMinimumSize(70, 90)

    def set_value(self, v, label):
        self.value = max(0.0, min(1.0, v))
        self.label = label
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor("#000000"))
        f = QFont("DejaVu Sans")
        f.setPixelSize(11)
        p.setFont(f)
        text_h = 18
        bar = QRect(r.center().x() - 16, 6, 33, r.height() - text_h - 10)
        rows = max(1, bar.height() // 3)
        lit = int(round(rows * self.value))
        for i in range(rows):
            y = bar.bottom() - i * 3 - 1
            on = i < lit
            c = self.color if on else QColor(0, 110, 0) if self.color == GREEN else QColor(110, 110, 0)
            for half in (0, 1):
                x = bar.left() + half * 17
                p.fillRect(QRect(x, y, 16, 2), c)
        p.setPen(self.color)
        p.drawText(QRect(0, r.height() - text_h, r.width(), text_h), Qt.AlignCenter, self.label)


class HistoryGraph(QWidget):
    """Wykres historii z przewijaną siatką."""

    def __init__(self, series_colors=(GREEN,), parent=None):
        super().__init__(parent)
        self.colors = list(series_colors)
        self.series = [[] for _ in self.colors]
        self.offset = 0
        self.setMinimumSize(120, 90)
        self.max_points = 400

    def add(self, values):
        for i, v in enumerate(values):
            if i >= len(self.series):
                self.series.append([])
                self.colors.append(self.colors[-1])
            self.series[i].append(max(0.0, min(1.0, v)))
            if len(self.series[i]) > self.max_points:
                self.series[i].pop(0)
        self.offset = (self.offset + 2) % 12
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor("#000000"))
        p.setPen(QPen(DARK_GREEN, 1))
        x = r.right() - self.offset
        while x > r.left():
            p.drawLine(x, r.top(), x, r.bottom())
            x -= 12
        y = r.bottom()
        while y > r.top():
            p.drawLine(r.left(), y, r.right(), y)
            y -= 12
        p.setRenderHint(QPainter.Antialiasing, True)
        step = 2
        for s, c in zip(self.series, self.colors):
            if len(s) < 2:
                continue
            pts = []
            n = min(len(s), r.width() // step + 1)
            data = s[-n:]
            for i, v in enumerate(data):
                px = r.right() - (len(data) - 1 - i) * step
                py = r.bottom() - v * (r.height() - 2) - 1
                pts.append(QPointF(px, py))
            p.setPen(QPen(c, 1.2))
            p.drawPolyline(QPolygonF(pts))


class NumItem(QTreeWidgetItem):
    """Element sortowany według wartości liczbowych zapisanych w UserRole."""

    def __lt__(self, other):
        tw = self.treeWidget()
        col = tw.sortColumn() if tw else 0
        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return (self.text(col) or "").lower() < (other.text(col) or "").lower()


# ------------------------------------------------------------------ zakładki
class ApplicationsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("tm_task"), plain("tm_status")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemDoubleClicked.connect(lambda *_: self.switch_to())
        lay.addWidget(self.tree)
        row = QHBoxLayout()
        row.addStretch(1)
        self.end = QPushButton(tr("tm_end_task"))
        self.end.clicked.connect(self.end_task)
        self.sw = QPushButton(tr("tm_switch_to"))
        self.sw.clicked.connect(self.switch_to)
        self.new = QPushButton(tr("tm_new_task"))
        self.new.clicked.connect(win.new_task)
        for b in (self.end, self.sw, self.new):
            row.addWidget(b)
        lay.addLayout(row)
        self.items = {}
        self.backend = None
        try:
            from ..wm import backend as wmb
            self.backend = wmb.create()
            self.backend.added.connect(lambda *_: self.refresh())
            self.backend.removed.connect(lambda *_: self.refresh())
            self.backend.changed.connect(lambda *_: self.refresh())
        except Exception:
            self.backend = None

    def refresh(self):
        if self.backend is None:
            return
        tls = [t for t in self.backend.toplevels if t.title not in ("horyzont-desktop", "horyzont-taskbar", "horyzont-startmenu")]
        alive = set()
        for tl in tls:
            alive.add(tl.uid)
            it = self.items.get(tl.uid)
            if it is None:
                it = QTreeWidgetItem(self.tree)
                self.items[tl.uid] = it
                from ..shell.taskbar import icon_for_toplevel
                qi, name = icon_for_toplevel(tl)
                it.setIcon(0, qi if qi is not None else iconcache.icon(name))
                it.setData(0, Qt.UserRole, tl.uid)
            it.setText(0, tl.title or tl.app_id)
            it.setText(1, plain("tm_running"))
        for uid in list(self.items):
            if uid not in alive:
                it = self.items.pop(uid)
                idx = self.tree.indexOfTopLevelItem(it)
                if idx >= 0:
                    self.tree.takeTopLevelItem(idx)
        has = bool(self.tree.selectedItems())
        self.end.setEnabled(has)
        self.sw.setEnabled(has)

    def _selected_tls(self):
        uids = {i.data(0, Qt.UserRole) for i in self.tree.selectedItems()}
        return [t for t in (self.backend.toplevels if self.backend else []) if t.uid in uids]

    def end_task(self):
        for t in self._selected_tls():
            self.backend.close(t)

    def switch_to(self):
        tls = self._selected_tls()
        if tls:
            self.backend.activate(tls[0])
            if config.get("taskmgr_min_on_use", True):
                self.win.showMinimized()

    def _menu(self, pos):
        tls = self._selected_tls()
        m = QMenu(self)
        if tls:
            m.addAction(tr("tm_switch_to"), self.switch_to)
            m.addAction(tr("tm_bring_front"), lambda: self.backend.activate(tls[0]))
            m.addSeparator()
            m.addAction(tr("tm_minimize"), lambda: [self.backend.minimize(t) for t in tls])
            m.addAction(tr("tm_maximize"), lambda: [self.backend.maximize(t) for t in tls])
            m.addSeparator()
            m.addAction(tr("tm_end_task"), self.end_task)
        else:
            m.addAction(tr("tm_new_task"), self.win.new_task)
        m.exec(self.tree.viewport().mapToGlobal(pos))


COLUMNS = [
    ("name", "tm_image_name", True),
    ("pid", "tm_pid", False),
    ("user", "tm_user_name", True),
    ("cpu", "tm_cpu", True),
    ("mem", "tm_mem_usage", True),
    ("threads", "tm_threads", False),
    ("nice", "tm_priority", False),
    ("cmd", "tm_command_line", False),
]


class ProcessesTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setSortingEnabled(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.visible_cols = config.get("taskmgr_columns", [c for c, _, d in COLUMNS if d])
        self._setup_columns()
        lay.addWidget(self.tree)
        row = QHBoxLayout()
        self.all_users = QCheckBox(tr("tm_show_all"))
        self.all_users.setChecked(config.get("taskmgr_all_users", True))
        self.all_users.toggled.connect(lambda v: (config.set("taskmgr_all_users", v), self.refresh()))
        row.addWidget(self.all_users)
        row.addStretch(1)
        self.end = QPushButton(tr("tm_end_process"))
        self.end.clicked.connect(self.end_process)
        row.addWidget(self.end)
        lay.addLayout(row)
        self.procs = {}
        self.items = {}
        self.ncpu = psutil.cpu_count() or 1
        self.me = sysctl.user_login()

    def _setup_columns(self):
        self.cols = [c for c, _, _ in COLUMNS if c in self.visible_cols]
        titles = {c: plain(k) for c, k, _ in COLUMNS}
        self.tree.setColumnCount(len(self.cols))
        self.tree.setHeaderLabels([titles[c] for c in self.cols])
        widths = {"name": 150, "pid": 55, "user": 100, "cpu": 50, "mem": 85, "threads": 55, "nice": 70, "cmd": 300}
        for i, c in enumerate(self.cols):
            self.tree.setColumnWidth(i, widths[c])
            if c in ("pid", "cpu", "mem", "threads"):
                self.tree.headerItem().setTextAlignment(i, Qt.AlignRight | Qt.AlignVCenter)
        self.tree.clear()
        self.items = {}
        if "cpu" in self.cols:
            self.tree.sortByColumn(self.cols.index("name"), Qt.AscendingOrder)

    def select_columns(self):
        d = HDialog(plain("tm_select_columns_title"), "", self.win, help_button=False)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(QLabel(plain("tm_select_columns_desc")))
        boxes = {}
        for c, k, _ in COLUMNS:
            cb = QCheckBox(plain(k))
            cb.setChecked(c in self.visible_cols)
            cb.setEnabled(c != "name")
            boxes[c] = cb
            lay.addWidget(cb)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        if d.exec() == QDialog.Accepted:
            self.visible_cols = [c for c, cb in boxes.items() if cb.isChecked()]
            config.set("taskmgr_columns", self.visible_cols)
            self._setup_columns()
            self.refresh()

    def refresh(self):
        show_all = self.all_users.isChecked()
        seen = set()
        sort_col = self.tree.sortColumn()
        self.tree.setSortingEnabled(False)
        for p in psutil.process_iter(["pid", "name", "username", "memory_info", "num_threads", "nice", "cmdline"]):
            info = p.info
            pid = info["pid"]
            user = info.get("username") or ""
            if not show_all and user != self.me:
                continue
            seen.add(pid)
            proc = self.procs.get(pid)
            if proc is None:
                self.procs[pid] = p
                try:
                    p.cpu_percent(None)
                except psutil.Error:
                    pass
                cpu = 0.0
            else:
                try:
                    cpu = proc.cpu_percent(None) / self.ncpu
                except psutil.Error:
                    cpu = 0.0
            it = self.items.get(pid)
            if it is None:
                it = NumItem(self.tree)
                self.items[pid] = it
                it.setData(0, Qt.UserRole + 5, pid)
                for i, c in enumerate(self.cols):
                    if c in ("pid", "cpu", "mem", "threads"):
                        it.setTextAlignment(i, Qt.AlignRight | Qt.AlignVCenter)
            mem = info["memory_info"].rss if info.get("memory_info") else 0
            vals = {
                "name": (info.get("name") or "?", None),
                "pid": (str(pid), pid),
                "user": (user, None),
                "cpu": (f"{int(round(cpu)):02d}", cpu),
                "mem": (f"{kb(mem)} KB", mem),
                "threads": (str(info.get("num_threads") or 0), info.get("num_threads") or 0),
                "nice": (self._nice_name(info.get("nice")), info.get("nice") or 0),
                "cmd": (" ".join(info.get("cmdline") or [])[:300], None),
            }
            for i, c in enumerate(self.cols):
                text, num = vals[c]
                if it.text(i) != text:
                    it.setText(i, text)
                if num is not None:
                    it.setData(i, Qt.UserRole, num)
        for pid in list(self.items):
            if pid not in seen:
                it = self.items.pop(pid)
                idx = self.tree.indexOfTopLevelItem(it)
                if idx >= 0:
                    self.tree.takeTopLevelItem(idx)
                self.procs.pop(pid, None)
        self.tree.setSortingEnabled(True)
        self.end.setEnabled(bool(self.tree.selectedItems()))
        return len(seen)

    def _nice_name(self, n):
        if n is None:
            return ""
        if n <= -15:
            return plain("tm_pri_realtime").replace("&", "")
        if n <= -5:
            return plain("tm_pri_high")
        if n < 0:
            return plain("tm_pri_above")
        if n == 0:
            return plain("tm_pri_normal")
        if n <= 10:
            return plain("tm_pri_below")
        return plain("tm_pri_low")

    def selected_pid(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole + 5) if it else None

    def end_process(self, tree=False):
        pid = self.selected_pid()
        if pid is None:
            return
        try:
            p = psutil.Process(pid)
            name = p.name()
        except psutil.Error:
            return
        if dialogs.message(self.win, plain("tm_warning_title"), tr("tm_end_confirm", name), "warning",
                           ("yes", "no")) != "yes":
            return
        targets = [p]
        if tree:
            try:
                targets = p.children(recursive=True) + [p]
            except psutil.Error:
                pass
        for t in targets:
            try:
                t.terminate()
            except psutil.AccessDenied as e:
                dialogs.message(self.win, plain("tm_cannot_end_title"), tr("tm_cannot_end", plain("tm_access_denied")), "error")
                return
            except psutil.Error:
                pass
        gone, alive = psutil.wait_procs(targets, timeout=1.5)
        for t in alive:
            try:
                t.kill()
            except psutil.Error:
                pass
        self.refresh()

    def set_priority(self, nice):
        pid = self.selected_pid()
        if pid is None:
            return
        try:
            psutil.Process(pid).nice(nice)
        except psutil.AccessDenied:
            dialogs.message(self.win, plain("tm_cannot_end_title"), tr("tm_cannot_priority"), "error")
        except psutil.Error:
            pass
        self.refresh()

    def _menu(self, pos):
        if self.tree.itemAt(pos) is None:
            return
        m = QMenu(self)
        m.addAction(tr("tm_end_process"), self.end_process)
        m.addAction(tr("tm_end_tree"), lambda: self.end_process(True))
        m.addSeparator()
        pm = m.addMenu(tr("tm_priority_set"))
        for key, val in (("tm_pri_realtime", -20), ("tm_pri_high", -10), ("tm_pri_above", -5),
                         ("tm_pri_normal", 0), ("tm_pri_below", 5), ("tm_pri_low", 19)):
            pm.addAction(tr(key), lambda v=val: self.set_priority(v))
        m.addSeparator()
        m.addAction(plain("tm_open_location"), self._open_location)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_location(self):
        pid = self.selected_pid()
        try:
            exe = psutil.Process(pid).exe()
            if exe:
                launcher.start_builtin("explorer", [os.path.dirname(exe)])
        except psutil.Error:
            pass


class PerformanceTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        g = QGridLayout(self)
        g.setContentsMargins(8, 8, 8, 8)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)

        def box(title, w):
            b = QGroupBox(title)
            l = QVBoxLayout(b)
            l.setContentsMargins(6, 6, 6, 6)
            l.addWidget(w)
            return b

        self.cpu_meter = LedMeter(GREEN)
        self.cpu_hist = HistoryGraph((GREEN,))
        self.mem_meter = LedMeter(GREEN)
        self.mem_hist = HistoryGraph((YELLOW,))
        g.addWidget(box(plain("tm_cpu_usage"), self.cpu_meter), 0, 0)
        g.addWidget(box(plain("tm_cpu_history"), self.cpu_hist), 0, 1, 1, 3)
        g.addWidget(box(plain("tm_mem_usage_g"), self.mem_meter), 1, 0)
        g.addWidget(box(plain("tm_mem_history"), self.mem_hist), 1, 1, 1, 3)
        g.setColumnStretch(1, 1)
        g.setRowStretch(0, 1)
        g.setRowStretch(1, 1)
        self.labels = {}

        def stats(title, keys):
            b = QGroupBox(title)
            gl = QGridLayout(b)
            gl.setContentsMargins(6, 4, 6, 4)
            gl.setVerticalSpacing(1)
            for i, k in enumerate(keys):
                gl.addWidget(QLabel(plain(k)), i, 0)
                v = QLabel("0")
                v.setAlignment(Qt.AlignRight)
                gl.addWidget(v, i, 1)
                self.labels[(title, k)] = v
            return b

        bottom = QGridLayout()
        self.t_totals = plain("tm_totals")
        self.t_phys = plain("tm_phys_mem")
        self.t_swap = plain("tm_commit")
        self.t_kern = plain("tm_kernel_mem")
        bottom.addWidget(stats(self.t_totals, ["tm_handles", "tm_threads_c", "tm_processes_c"]), 0, 0)
        bottom.addWidget(stats(self.t_phys, ["tm_total", "tm_available", "tm_cache"]), 0, 1)
        bottom.addWidget(stats(self.t_swap, ["tm_total", "tm_used", "tm_free"]), 1, 0)
        bottom.addWidget(stats(self.t_kern, ["tm_total", "tm_paged", "tm_nonpaged"]), 1, 1)
        g.addLayout(bottom, 2, 0, 1, 4)
        self.per_cpu = False
        psutil.cpu_percent(None)

    def set_per_cpu(self, v):
        self.per_cpu = v
        n = psutil.cpu_count() or 1
        self.cpu_hist.colors = [GREEN] * (n if v else 1)
        self.cpu_hist.series = [[] for _ in self.cpu_hist.colors]

    def refresh(self, nprocs):
        cpu = psutil.cpu_percent(None)
        self.cpu_meter.set_value(cpu / 100, f"{int(round(cpu))} %")
        if self.per_cpu:
            per = psutil.cpu_percent(None, percpu=True)
            self.cpu_hist.add([v / 100 for v in per])
        else:
            self.cpu_hist.add([cpu / 100])
        vm = psutil.virtual_memory()
        used = vm.total - vm.available
        self.mem_meter.set_value(used / vm.total, sysctl.human_size(used).replace(" ", " "))
        self.mem_hist.add([used / vm.total])
        sw = psutil.swap_memory()
        threads = 0
        handles = 0
        for p in psutil.process_iter(["num_threads", "num_fds"]):
            threads += p.info.get("num_threads") or 0
            handles += p.info.get("num_fds") or 0
        L = self.labels
        L[(self.t_totals, "tm_handles")].setText(sysctl.group_digits(handles))
        L[(self.t_totals, "tm_threads_c")].setText(sysctl.group_digits(threads))
        L[(self.t_totals, "tm_processes_c")].setText(sysctl.group_digits(nprocs))
        L[(self.t_phys, "tm_total")].setText(kb(vm.total))
        L[(self.t_phys, "tm_available")].setText(kb(vm.available))
        L[(self.t_phys, "tm_cache")].setText(kb(getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)))
        L[(self.t_swap, "tm_total")].setText(kb(sw.total))
        L[(self.t_swap, "tm_used")].setText(kb(sw.used))
        L[(self.t_swap, "tm_free")].setText(kb(sw.free))
        mi = _meminfo()
        L[(self.t_kern, "tm_total")].setText(kb(mi.get("Slab", 0) + mi.get("KernelStack", 0) + mi.get("PageTables", 0)))
        L[(self.t_kern, "tm_paged")].setText(kb(mi.get("SReclaimable", 0)))
        L[(self.t_kern, "tm_nonpaged")].setText(kb(mi.get("SUnreclaim", 0)))
        return cpu


def _meminfo():
    out = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                parts = v.split()
                if parts:
                    out[k] = int(parts[0]) * 1024
    except OSError:
        pass
    return out


class NetworkingTab(QWidget):
    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.graph = HistoryGraph((GREEN, YELLOW))
        self.graph.setMinimumHeight(150)
        self.title = QLabel("")
        lay.addWidget(self.title)
        lay.addWidget(self.graph, 1)
        legend = QLabel(f"<span style='color:#0a0'>■</span> {plain('tm_bytes_recv')}    "
                        f"<span style='color:#aa0'>■</span> {plain('tm_bytes_sent')}")
        lay.addWidget(legend)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("tm_adapter"), plain("tm_net_util"), plain("tm_link_speed"), plain("tm_state"),
                                   plain("tm_bytes_sent"), plain("tm_bytes_recv")])
        self.tree.setMaximumHeight(120)
        lay.addWidget(self.tree)
        self.last = psutil.net_io_counters(pernic=True)
        self.last_t = time.monotonic()
        self.items = {}

    def refresh(self):
        now = psutil.net_io_counters(pernic=True)
        t = time.monotonic()
        dt = max(0.1, t - self.last_t)
        stats = psutil.net_if_stats()
        total_rx = total_tx = 0.0
        total_speed = 0
        for nic, c in now.items():
            if nic == "lo":
                continue
            prev = self.last.get(nic, c)
            rx = (c.bytes_recv - prev.bytes_recv) / dt
            tx = (c.bytes_sent - prev.bytes_sent) / dt
            st = stats.get(nic)
            speed = (st.speed if st and st.speed > 0 else 100) * 1_000_000 / 8
            total_rx += rx
            total_tx += tx
            total_speed += speed
            util = (rx + tx) / speed * 100
            it = self.items.get(nic)
            if it is None:
                it = QTreeWidgetItem(self.tree)
                it.setIcon(0, iconcache.icon("network_conn"))
                self.items[nic] = it
            it.setText(0, nic)
            it.setText(1, f"{util:.2f} %".replace(".", ","))
            it.setText(2, f"{st.speed if st and st.speed > 0 else '?'} Mb/s")
            it.setText(3, plain("tm_connected") if st and st.isup else plain("tm_disconnected"))
            it.setText(4, sysctl.group_digits(c.bytes_sent))
            it.setText(5, sysctl.group_digits(c.bytes_recv))
        self.last, self.last_t = now, t
        if total_speed:
            self.graph.add([total_rx / total_speed * 20, total_tx / total_speed * 20])
        self.title.setText(plain("tm_net_util") + " (×20)")


class UsersTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setHeaderLabels([plain("tm_user"), plain("tm_session"), plain("tm_status"), plain("tm_client")])
        lay.addWidget(self.tree)
        row = QHBoxLayout()
        row.addStretch(1)
        d = QPushButton(tr("tm_disconnect"))
        d.clicked.connect(sysctl.lock_screen)
        lo = QPushButton(tr("tm_logoff"))
        lo.clicked.connect(lambda: dialogs.message(self.win, plain("taskmgr"), plain("tm_logoff_confirm"), "question",
                                                   ("yes", "no")) == "yes" and sysctl.logoff())
        sm = QPushButton(tr("tm_send_msg"))
        sm.setEnabled(False)
        for b in (d, lo, sm):
            row.addWidget(b)
        lay.addLayout(row)

    def refresh(self):
        self.tree.clear()
        sessions = psutil.users() or []
        if not sessions:
            it = QTreeWidgetItem(self.tree, [sysctl.user_login(), "1", plain("tm_active"), "localhost"])
            it.setIcon(0, iconcache.icon("user"))
        for i, u in enumerate(sessions):
            it = QTreeWidgetItem(self.tree, [u.name, u.terminal or str(i + 1), plain("tm_active"), u.host or "localhost"])
            it.setIcon(0, iconcache.icon("user"))


# ------------------------------------------------------------------ okno
class TaskManagerWindow(HWindow):
    def __init__(self):
        super().__init__(plain("taskmgr"), "taskmgr")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.apps = ApplicationsTab(self)
        self.procs = ProcessesTab(self)
        self.perf = PerformanceTab(self)
        self.net = NetworkingTab(self)
        self.users = UsersTab(self)
        self.tabs.addTab(self.apps, plain("tm_applications"))
        self.tabs.addTab(self.procs, plain("tm_processes"))
        self.tabs.addTab(self.perf, plain("tm_performance"))
        self.tabs.addTab(self.net, plain("tm_networking"))
        self.tabs.addTab(self.users, plain("tm_users"))
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 6, 6)
        wl.addWidget(self.tabs)
        lay.addWidget(wrap, 1)
        self.status = QStatusBar()
        self.st_procs = QLabel()
        self.st_cpu = QLabel()
        self.st_mem = QLabel()
        for w in (self.st_procs, self.st_cpu, self.st_mem):
            w.setMinimumWidth(110)
            self.status.addWidget(w, 1)
        lay.addWidget(self.status)
        self._build_menus()
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.setCurrentIndex(config.get("taskmgr_tab", 0))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.set_speed(config.get("taskmgr_speed", "normal"))
        self.compact = False
        self.resize(470, 520)
        self.refresh()
        self.apps.refresh()
        if config.get("taskmgr_on_top", True):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def _build_menus(self):
        mb = self.menubar
        m = mb.addMenu(tr("menu_file"))
        m.addAction(tr("tm_new_task_run"), self.new_task)
        m.addSeparator()
        m.addAction(tr("tm_exit"), self.close)
        m = mb.addMenu(tr("menu_options"))
        a = m.addAction(tr("tm_always_top"))
        a.setCheckable(True)
        a.setChecked(config.get("taskmgr_on_top", True))
        a.toggled.connect(self._on_top)
        a = m.addAction(tr("tm_min_on_use"))
        a.setCheckable(True)
        a.setChecked(config.get("taskmgr_min_on_use", True))
        a.toggled.connect(lambda v: config.set("taskmgr_min_on_use", v))
        a = m.addAction(tr("tm_hide_min"))
        a.setCheckable(True)
        a.setChecked(config.get("taskmgr_hide_min", False))
        a.toggled.connect(lambda v: config.set("taskmgr_hide_min", v))
        self.m_view = mb.addMenu(tr("menu_view"))
        self.m_view.aboutToShow.connect(self._fill_view)
        self.m_windows = mb.addMenu(tr("tm_windows_menu"))
        self.m_windows.addAction(tr("tm_minimize"), lambda: [self.apps.backend.minimize(t) for t in self.apps._selected_tls()])
        self.m_windows.addAction(tr("tm_maximize"), lambda: [self.apps.backend.maximize(t) for t in self.apps._selected_tls()])
        self.m_windows.addSeparator()
        self.m_windows.addAction(tr("tm_bring_front"), lambda: self.apps.switch_to())
        m = mb.addMenu(tr("menu_shutdown"))
        m.addAction(tr("tm_sd_standby"), lambda: sysctl.power_action("standby"))
        m.addAction(tr("tm_sd_hibernate"), lambda: sysctl.power_action("hibernate"))
        m.addAction(tr("tm_sd_turnoff"), lambda: sysctl.power_action("turnoff"))
        m.addAction(tr("tm_sd_restart"), lambda: sysctl.power_action("restart"))
        m.addSeparator()
        m.addAction(tr("tm_sd_logoff"), sysctl.logoff)
        m.addAction(tr("tm_sd_switch"), sysctl.switch_user)
        m.addAction(tr("tm_sd_lock"), sysctl.lock_screen)
        m = mb.addMenu(tr("menu_help"))
        m.addAction(tr("tm_help_topics"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        m.addSeparator()
        from .about import show_about
        m.addAction(tr("tm_about"), lambda: show_about(self, plain("taskmgr"), "taskmgr"))
        a = QAction(self)
        a.setShortcut(QKeySequence("F5"))
        a.triggered.connect(self.refresh)
        self.addAction(a)

    def _fill_view(self):
        m = self.m_view
        m.clear()
        m.addAction(tr("tm_refresh_now"), self.refresh)
        sp = m.addMenu(tr("tm_update_speed"))
        g = QActionGroup(sp)
        cur = config.get("taskmgr_speed", "normal")
        for key, lab in (("high", "tm_speed_high"), ("normal", "tm_speed_normal"), ("low", "tm_speed_low"),
                         ("paused", "tm_speed_paused")):
            a = sp.addAction(tr(lab))
            a.setCheckable(True)
            a.setChecked(key == cur)
            g.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_speed(k))
        idx = self.tabs.currentIndex()
        if idx == 1:
            m.addSeparator()
            m.addAction(tr("tm_select_columns"), self.procs.select_columns)
        elif idx == 2:
            m.addSeparator()
            h = m.addMenu(tr("tm_cpu_history_m"))
            g2 = QActionGroup(h)
            a1 = h.addAction(tr("tm_one_graph"))
            a2 = h.addAction(tr("tm_graph_per_cpu"))
            for a, v in ((a1, False), (a2, True)):
                a.setCheckable(True)
                a.setChecked(self.perf.per_cpu == v)
                g2.addAction(a)
                a.triggered.connect(lambda _=False, v=v: self.perf.set_per_cpu(v))

    def _tab_changed(self, i):
        config.set("taskmgr_tab", i)
        self.m_windows.menuAction().setVisible(i == 0)
        self.refresh()

    def _on_top(self, v):
        config.set("taskmgr_on_top", v)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, v)
        self.show()

    def set_speed(self, key):
        config.set("taskmgr_speed", key)
        ms = SPEEDS.get(key, 1000)
        if ms:
            self.timer.start(ms)
        else:
            self.timer.stop()

    def refresh(self):
        idx = self.tabs.currentIndex()
        if idx == 1:
            n = self.procs.refresh()
        else:
            n = len(psutil.pids())
        cpu = self.perf.refresh(n)
        if idx == 3:
            self.net.refresh()
        elif idx == 4:
            self.users.refresh()
        elif idx == 0:
            self.apps.refresh()
        vm = psutil.virtual_memory()
        self.st_procs.setText(tr("tm_status_procs", n))
        self.st_cpu.setText(tr("tm_status_cpu", int(round(cpu))))
        self.st_mem.setText(tr("tm_status_mem", sysctl.human_size(vm.total - vm.available), sysctl.human_size(vm.total)))

    def new_task(self):
        d = HDialog(plain("tm_new_task_title"), "", self, help_button=True)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("run", 32))
        row.addWidget(ic, 0, Qt.AlignTop)
        lbl = QLabel(tr("run_desc"))
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        lay.addLayout(row)
        r2 = QHBoxLayout()
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(config.get("run_history", []))
        ol = QLabel(tr("run_open"))
        ol.setBuddy(combo)
        r2.addWidget(ol)
        r2.addWidget(combo, 1)
        lay.addLayout(r2)
        b = QHBoxLayout()
        b.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ca = QPushButton(plain("cancel"))
        br = QPushButton(plain("browse"))
        for x in (ok, ca, br):
            b.addWidget(x)
        lay.addLayout(b)
        ca.clicked.connect(d.reject)
        br.clicked.connect(lambda: (lambda f: f and combo.setEditText(f))(dialogs.open_file(d, plain("browse"))))

        def go():
            t = combo.currentText().strip()
            if t and launcher.run_command(t):
                d.accept()
            elif t:
                dialogs.message(d, t, tr("run_notfound", t), "error")
        ok.clicked.connect(go)
        d.setFixedSize(360, d.sizeHint().height())
        d.exec()

    def mouseDoubleClickEvent(self, e):
        # tryb "małego okna": podwójne kliknięcie obramowania chowa menu i zakładki
        pos = e.position().toPoint()
        if self._caption_rect().contains(pos):
            return super().mouseDoubleClickEvent(e)
        self.set_compact(not self.compact)

    def set_compact(self, v):
        self.compact = v
        self.menubar.setVisible(not v)
        self.status.setVisible(not v)
        self.tabs.tabBar().setVisible(not v)

    def changeEvent(self, e):
        super().changeEvent(e)
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.WindowStateChange and self.isMinimized() and config.get("taskmgr_hide_min", False):
            QTimer.singleShot(0, self.hide)


def main(args):
    app = make_app("taskmgr")
    if single.try_forward("taskmgr", args, 200):
        return 0
    w = TaskManagerWindow()

    def handle(a):
        w.showNormal()
        w.raise_()
        w.activateWindow()
    server = single.Server("taskmgr", handle)
    w.show()
    return app.exec()
