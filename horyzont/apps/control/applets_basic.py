"""Aplety: Data i godzina, Mysz, Klawiatura, Dźwięki i urządzenia audio."""
import datetime as _dt
import glob
import math
import os
import shutil
import subprocess

from PySide6.QtCore import QDate, QDateTime, QPointF, QRectF, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QCalendarWidget, QCheckBox, QComboBox,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPushButton, QSlider,
                               QSpinBox, QTimeEdit, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ... import config
from ...common import dialogs, sounds, sysctl
from ...i18n import lang_code, plain, tr
from ...theme import iconcache
from .common import AppletDialog, hline, run, run_privileged, wrap_label


def _apply_labwc():
    try:
        from ...session import labwc
        labwc.apply_settings()
    except Exception:
        pass


def _slider(minv, maxv, val, left="", right=""):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    if left:
        h.addWidget(QLabel(left))
    s = QSlider(Qt.Horizontal)
    s.setRange(minv, maxv)
    s.setValue(val)
    s.setTickPosition(QSlider.TicksBelow)
    s.setTickInterval(max(1, (maxv - minv) // 10))
    h.addWidget(s, 1)
    if right:
        h.addWidget(QLabel(right))
    return w, s


def input_devices(kind):
    """Urządzenia wejściowe z /proc/bus/input/devices: kind = 'mouse' albo 'kbd'."""
    out = []
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return out
    for b in blocks:
        name = handlers = ""
        for line in b.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip('"')
            elif line.startswith("H: Handlers="):
                handlers = line.split("=", 1)[1]
        if name and kind in handlers:
            out.append(name)
    return out


# ================================================================== Data i godzina
class AnalogClock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.time = QTime.currentTime()
        self.setMinimumSize(150, 150)

    def set_time(self, t):
        self.time = t
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height()) - 8
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        c = r.center()
        p.setPen(QPen(QColor("#5a6a6c"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(r)
        for i in range(60):
            a = math.radians(i * 6)
            r1 = s / 2 - (8 if i % 5 == 0 else 4)
            r2 = s / 2 - 2
            p.setPen(QPen(QColor("#1f6f78") if i % 5 == 0 else QColor("#9aaaac"), 2.2 if i % 5 == 0 else 1))
            p.drawLine(QPointF(c.x() + math.sin(a) * r1, c.y() - math.cos(a) * r1),
                       QPointF(c.x() + math.sin(a) * r2, c.y() - math.cos(a) * r2))
        t = self.time
        hands = [((t.hour() % 12 + t.minute() / 60) * 30, s * 0.26, 4.0, "#203030"),
                 ((t.minute() + t.second() / 60) * 6, s * 0.38, 3.0, "#203030"),
                 (t.second() * 6, s * 0.42, 1.2, "#c0392b")]
        for ang, length, width, col in hands:
            a = math.radians(ang)
            p.setPen(QPen(QColor(col), width, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(c, QPointF(c.x() + math.sin(a) * length, c.y() - math.cos(a) * length))
        p.setBrush(QColor("#c0392b"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 3, 3)


def current_timezone():
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    rc, out = run(["timedatectl", "show", "-p", "Timezone", "--value"])
    return out.strip() if rc == 0 and out.strip() else "UTC"


class DateTimeProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("datetime_props"), "datetime", parent)
        self.user_changed_time = False
        w, lay = self.add_tab(plain("dt_tab"))
        row = QHBoxLayout()
        dbox = QGroupBox(plain("dt_date"))
        dl = QVBoxLayout(dbox)
        top = QHBoxLayout()
        self.month = QComboBox()
        loc = __import__("PySide6.QtCore", fromlist=["QLocale"]).QLocale()
        for m in range(1, 13):
            self.month.addItem(loc.standaloneMonthName(m))
        self.year = QSpinBox()
        self.year.setRange(1970, 2099)
        top.addWidget(self.month, 1)
        top.addWidget(self.year)
        dl.addLayout(top)
        self.cal = QCalendarWidget()
        self.cal.setNavigationBarVisible(False)
        self.cal.setGridVisible(False)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.cal.setFirstDayOfWeek(Qt.Monday)
        dl.addWidget(self.cal)
        row.addWidget(dbox, 3)
        tbox = QGroupBox(plain("dt_time"))
        tl = QVBoxLayout(tbox)
        self.clock = AnalogClock()
        tl.addWidget(self.clock, 1)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")
        tl.addWidget(self.time_edit)
        row.addWidget(tbox, 2)
        lay.addLayout(row)
        self.tz_label = QLabel(tr("dt_current_tz", current_timezone()))
        lay.addWidget(self.tz_label)
        now = QDateTime.currentDateTime()
        self.cal.setSelectedDate(now.date())
        self.month.setCurrentIndex(now.date().month() - 1)
        self.year.setValue(now.date().year())
        self.time_edit.setTime(now.time())
        self.month.currentIndexChanged.connect(self._nav)
        self.year.valueChanged.connect(self._nav)
        self.cal.selectionChanged.connect(self._date_changed)
        self.time_edit.timeChanged.connect(self._time_changed)
        self._editing_time = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        # strefa czasowa
        w2, l2 = self.add_tab(plain("dt_tz"))
        self.tz = QComboBox()
        try:
            import zoneinfo
            zones = sorted(zoneinfo.available_timezones())
        except Exception:
            zones = ["UTC", "Europe/Warsaw"]
        self.tz.addItems(zones)
        self.tz.setCurrentText(current_timezone())
        self.tz.setEditable(False)
        l2.addWidget(self.tz)
        l2.addWidget(_world_map())
        self.dst = QCheckBox(plain("dt_dst"))
        self.dst.setChecked(True)
        self.dst.setEnabled(False)
        l2.addWidget(self.dst)
        l2.addStretch(1)
        self.tz.currentIndexChanged.connect(self.changed)
        # czas internetowy
        w3, l3 = self.add_tab(plain("dt_inet"))
        rc, out = run(["timedatectl", "show", "-p", "NTP", "--value"])
        self.ntp = QCheckBox(tr("dt_auto_sync"))
        self.ntp.setChecked(out.strip() == "yes")
        self.ntp.toggled.connect(self.changed)
        l3.addWidget(self.ntp)
        rc2, out2 = run(["timedatectl", "show-timesync", "-p", "ServerName", "--value"])
        l3.addWidget(QLabel(plain("dt_server") + " " + (out2.strip() or "pool.ntp.org (chronyd)")))
        l3.addWidget(wrap_label(plain("dt_inet_desc")))
        l3.addStretch(1)
        l3.addWidget(wrap_label(tr("dt_need_admin")))
        self.resize(430, 420)
        if page == "timezone":
            self.tabs.setCurrentIndex(1)

    def _nav(self, *_):
        d = self.cal.selectedDate()
        day = min(d.day(), QDate(self.year.value(), self.month.currentIndex() + 1, 1).daysInMonth())
        self.cal.setSelectedDate(QDate(self.year.value(), self.month.currentIndex() + 1, day))
        self.cal.setCurrentPage(self.year.value(), self.month.currentIndex() + 1)

    def _date_changed(self):
        self.user_changed_time = True
        self.changed()

    def _time_changed(self, t):
        if not self._editing_time:
            self.user_changed_time = True
            self.changed()
        self.clock.set_time(t)

    def _tick(self):
        if not self.user_changed_time:
            self._editing_time = True
            self.time_edit.setTime(QTime.currentTime())
            self._editing_time = False
        else:
            self._editing_time = True
            self.time_edit.setTime(self.time_edit.time().addSecs(1))
            self._editing_time = False

    def apply(self):
        ok = True
        if self.tz.currentText() != current_timezone():
            ok, _ = run_privileged(["timedatectl", "set-timezone", self.tz.currentText()], self)
            if ok:
                self.tz_label.setText(tr("dt_current_tz", self.tz.currentText()))
        rc, out = run(["timedatectl", "show", "-p", "NTP", "--value"])
        want = self.ntp.isChecked()
        if (out.strip() == "yes") != want:
            ok, _ = run_privileged(["timedatectl", "set-ntp", "true" if want else "false"], self)
        if self.user_changed_time and not want:
            d = self.cal.selectedDate().toString("yyyy-MM-dd")
            t = self.time_edit.time().toString("HH:mm:ss")
            ok, _ = run_privileged(["timedatectl", "set-time", f"{d} {t}"], self)
            self.user_changed_time = False
        elif self.user_changed_time and want:
            dialogs.message(self, plain("datetime_props"), plain("dt_ntp_on_note"), "info")
            self.user_changed_time = False
        return ok


def _world_map():
    """Uproszczona mapa świata z zaznaczeniem pasa strefy czasowej."""
    class Map(QWidget):
        def __init__(self):
            super().__init__()
            self.setMinimumHeight(150)

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            r = self.rect().adjusted(1, 1, -1, -1)
            p.fillRect(r, QColor("#2a5a9a"))
            p.setBrush(QColor("#4a9a4a"))
            p.setPen(Qt.NoPen)
            W, H = r.width(), r.height()
            blobs = [(0.12, 0.25, 0.18, 0.22), (0.2, 0.55, 0.08, 0.28), (0.45, 0.22, 0.12, 0.16), (0.48, 0.45, 0.1, 0.3),
                     (0.6, 0.2, 0.3, 0.25), (0.8, 0.65, 0.1, 0.12), (0.3, 0.1, 0.08, 0.06)]
            for x, y, w, h in blobs:
                p.drawEllipse(QRectF(r.left() + x * W, r.top() + y * H, w * W, h * H))
            off = _dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600
            x = r.left() + (off + 12) / 24 * W
            p.fillRect(QRectF(x - W / 48, r.top(), W / 24, H), QColor(255, 255, 255, 70))
            p.setPen(QColor("#ffffff"))
            p.drawText(r.adjusted(4, 2, 0, 0), Qt.AlignLeft | Qt.AlignTop, f"UTC{off:+.0f}")
    return Map()


def datetime(page=None, parent=None):  # nazwa używana przez rejestr
    return DateTimeProperties(page, parent)


# ================================================================== Mysz
class MouseProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("mouse_props"), "mouse", parent)
        w, lay = self.add_tab(plain("ms_buttons"))
        g1 = QGroupBox(plain("ms_button_config"))
        gv = QVBoxLayout(g1)
        self.left = QCheckBox(tr("ms_switch").replace("&", ""))
        self.left.setChecked(config.get("mouse_left_handed", False))
        self.left.toggled.connect(self.changed)
        gv.addWidget(self.left)
        h = QHBoxLayout()
        h.addWidget(wrap_label(plain("ms_switch_desc")), 1)
        pic = QLabel()
        pic.setPixmap(iconcache.pixmap("mouse", 48))
        h.addWidget(pic)
        gv.addLayout(h)
        lay.addWidget(g1)
        g2 = QGroupBox(plain("ms_dblclick"))
        gl = QHBoxLayout(g2)
        gl.addWidget(wrap_label(plain("ms_dblclick_desc")), 1)
        self.folder = QLabel()
        self.folder_open = False
        self.folder.setPixmap(iconcache.pixmap("folder", 32))
        self.folder.mouseDoubleClickEvent = self._toggle_folder
        gl.addWidget(self.folder)
        lay.addWidget(g2)
        sw, self.dbl = _slider(200, 900, 1100 - int(config.get("mouse_double_click", 500)), plain("ms_slow"), plain("ms_fast"))
        lay.addWidget(sw)
        self.dbl.valueChanged.connect(self.changed)
        lay.addStretch(1)
        # wskaźniki
        w2, l2 = self.add_tab(plain("ms_pointers"))
        self._build_pointers(l2)
        # opcje wskaźnika
        w3, l3 = self.add_tab(plain("ms_options"))
        g3 = QGroupBox(plain("ms_motion"))
        g3l = QVBoxLayout(g3)
        g3l.addWidget(QLabel(plain("ms_speed")))
        sw3, self.speed = _slider(-100, 100, int(float(config.get("mouse_speed", 0.0)) * 100), plain("ms_slow"), plain("ms_fast"))
        self.speed.valueChanged.connect(self.changed)
        g3l.addWidget(sw3)
        self.precision = QCheckBox(plain("ms_precision"))
        self.precision.setChecked(not config.get("mouse_accel_flat", False))
        self.precision.toggled.connect(self.changed)
        g3l.addWidget(self.precision)
        l3.addWidget(g3)
        l3.addStretch(1)
        # kółko
        w4, l4 = self.add_tab(plain("ms_wheel"))
        g4 = QGroupBox(plain("ms_scrolling"))
        g4l = QVBoxLayout(g4)
        self.natural = QCheckBox(tr("ms_natural").replace("&", ""))
        self.natural.setChecked(config.get("mouse_natural_scroll", False))
        self.natural.toggled.connect(self.changed)
        g4l.addWidget(self.natural)
        self.tap = QCheckBox(plain("ms_tap"))
        self.tap.setChecked(config.get("touchpad_tap", True))
        self.tap.toggled.connect(self.changed)
        g4l.addWidget(self.tap)
        l4.addWidget(g4)
        l4.addStretch(1)
        # sprzęt
        w5, l5 = self.add_tab(plain("ms_hardware"))
        l5.addWidget(QLabel(plain("ms_devices")))
        lst = QListWidget()
        for d in input_devices("mouse"):
            lst.addItem(d)
        lst.setIconSize(lst.iconSize())
        l5.addWidget(lst)
        self.resize(420, 440)

    # ------------------------------------------------------------ wskaźniki
    def _build_pointers(self, l2):
        from ...common import xcursor
        from ...theme import cursors
        for v in cursors.VARIANTS:
            try:
                cursors.generate(v)
            except Exception as e:
                print("horyzont: motyw wskaźników:", e)
        g = QGroupBox(plain("ms_scheme"))
        gl = QGridLayout(g)
        self.cursor_theme = QComboBox()
        self.cursor_theme.activated.connect(self._ptr_theme_changed)
        gl.addWidget(self.cursor_theme, 0, 0, 1, 3)
        self.ptr_preview = QLabel()
        self.ptr_preview.setFixedSize(64, 64)
        self.ptr_preview.setAlignment(Qt.AlignCenter)
        self.ptr_preview.setStyleSheet("background: #ffffff; border: 1px solid #8a9b9e;")
        gl.addWidget(self.ptr_preview, 0, 3, 2, 1)
        sv = QPushButton(plain("snd_save_as"))
        sv.clicked.connect(self._ptr_save)
        self.ptr_del = QPushButton(plain("delete").replace("&", ""))
        self.ptr_del.clicked.connect(self._ptr_delete)
        inst = QPushButton(plain("ms_install_scheme"))
        inst.clicked.connect(self._ptr_install)
        gl.addWidget(sv, 1, 0)
        gl.addWidget(self.ptr_del, 1, 1)
        gl.addWidget(inst, 1, 2)
        l2.addWidget(g)
        l2.addWidget(QLabel(plain("ms_customize")))
        self.ptr_list = QTreeWidget()
        self.ptr_list.setHeaderHidden(True)
        self.ptr_list.setRootIsDecorated(False)
        self.ptr_list.setColumnCount(2)
        self.ptr_list.setIconSize(QSize(32, 32))
        self.ptr_list.header().setStretchLastSection(False)
        from PySide6.QtWidgets import QHeaderView
        self.ptr_list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ptr_list.setColumnWidth(1, 44)
        for role, key, _ in xcursor.ROLES:
            it = QTreeWidgetItem([plain(key), ""])
            it.setData(0, Qt.UserRole, role)
            self.ptr_list.addTopLevelItem(it)
        self.ptr_list.itemDoubleClicked.connect(lambda *_: self._ptr_browse())
        l2.addWidget(self.ptr_list, 1)
        row = QHBoxLayout()
        self.cursor_size = QComboBox()
        for sz, k in ((24, "ms_size_normal"), (32, "ms_size_large"), (48, "ms_size_xlarge"), (64, "ms_size_huge")):
            self.cursor_size.addItem(plain(k), sz)
        self.cursor_size.setCurrentIndex(max(0, self.cursor_size.findData(int(config.get("cursor_size", 24)))))
        self.cursor_size.currentIndexChanged.connect(self.changed)
        row.addWidget(QLabel(plain("ms_cursor_size")))
        row.addWidget(self.cursor_size)
        row.addStretch(1)
        dflt = QPushButton(plain("ms_use_default"))
        dflt.clicked.connect(self._ptr_default)
        br = QPushButton(plain("browse"))
        br.clicked.connect(self._ptr_browse)
        row.addWidget(dflt)
        row.addWidget(br)
        l2.addLayout(row)
        self._ptr_custom = {}
        self._ptr_fill_themes(config.get("cursor_theme", "") or "Horyzont")

    def _ptr_fill_themes(self, current_key):
        from ...common import xcursor
        self.cursor_theme.clear()
        themes = xcursor.list_themes()
        order = ["Horyzont", "Horyzont-Czarny"] + sorted(k for k in themes if k not in ("Horyzont", "Horyzont-Czarny"))
        for k in order:
            if k in themes:
                label = {"Horyzont": plain("ms_scheme_horyzont"), "Horyzont-Czarny": plain("ms_scheme_horyzont_black")}.get(k, themes[k])
                self.cursor_theme.addItem(label, k)
        i = self.cursor_theme.findData(current_key)
        self.cursor_theme.setCurrentIndex(max(0, i))
        self._ptr_base = self.cursor_theme.currentData() or ""
        self._ptr_refresh()

    def _ptr_theme_changed(self, *_):
        self._ptr_base = self.cursor_theme.currentData() or ""
        self._ptr_custom = {}
        self._ptr_refresh()
        self.changed()

    def _ptr_file(self, role):
        from ...common import xcursor
        return self._ptr_custom.get(role) or xcursor.find_cursor(self._ptr_base, role)

    def _ptr_refresh(self):
        from ...common import xcursor
        from PySide6.QtGui import QPixmap
        for i in range(self.ptr_list.topLevelItemCount()):
            it = self.ptr_list.topLevelItem(i)
            role = it.data(0, Qt.UserRole)
            fp = self._ptr_file(role)
            img = xcursor.preview_image(fp, 32) if fp else None
            it.setIcon(1, QIcon(QPixmap.fromImage(img)) if img is not None else QIcon())
            f = it.font(0)
            f.setBold(role in self._ptr_custom)
            it.setFont(0, f)
        fp = self._ptr_file("normal")
        img = xcursor.preview_image(fp, 48) if fp else None
        if img is not None:
            from PySide6.QtGui import QPixmap
            self.ptr_preview.setPixmap(QPixmap.fromImage(img))
        self.ptr_del.setEnabled(self._ptr_base.startswith("Horyzont-wlasny-"))

    def _ptr_browse(self):
        it = self.ptr_list.currentItem()
        if it is None:
            self.ptr_list.setCurrentItem(self.ptr_list.topLevelItem(0))
            it = self.ptr_list.currentItem()
        fn = dialogs.open_file(self, plain("ms_browse_title"), os.path.expanduser("~"),
                               plain("ms_cursor_files") + " (*.cur *.ani *.png);;" + plain("all_files") + " (*)")
        if not fn:
            return
        from ...common import xcursor
        try:
            xcursor.load_any(fn)
        except Exception as e:
            dialogs.message(self, plain("mouse_props"), tr("ms_bad_cursor", os.path.basename(fn)) + f"\n\n{e}", "error")
            return
        self._ptr_custom[it.data(0, Qt.UserRole)] = fn
        self._ptr_refresh()
        self.changed()

    def _ptr_default(self):
        it = self.ptr_list.currentItem()
        if it is not None:
            self._ptr_custom.pop(it.data(0, Qt.UserRole), None)
            self._ptr_refresh()
            self.changed()

    def _ptr_build(self, name):
        from ...common import xcursor
        assign = {}
        for role, _, _ in xcursor.ROLES:
            fp = self._ptr_file(role)
            if fp:
                assign[role] = os.path.realpath(fp)
        xcursor.build_theme(name, assign, inherits=self._ptr_base or "Adwaita")
        return name

    def _ptr_save(self):
        name = dialogs.ask_text(self, plain("snd_save_title"), plain("ms_save_label"), "", "cursor")
        if not name:
            return
        key = "Horyzont-wlasny-" + "".join(c if c.isalnum() else "-" for c in name)
        try:
            self._ptr_build(key)
        except Exception as e:
            dialogs.message(self, plain("mouse_props"), str(e), "error")
            return
        self._ptr_custom = {}
        self._ptr_fill_themes(key)
        self.changed()

    def _ptr_delete(self):
        key = self._ptr_base
        if not key.startswith("Horyzont-wlasny-"):
            return
        if dialogs.message(self, plain("mouse_props"), tr("snd_delete_q", key[16:]), "question", ("yes", "no")) == "yes":
            shutil.rmtree(os.path.join(os.path.expanduser("~/.icons"), key), ignore_errors=True)
            self._ptr_fill_themes("Horyzont")
            self.changed()

    def _ptr_install(self):
        """Instaluje schemat z folderu albo archiwum: motyw Xcursor lub kursory Windows (.cur/.ani z plikiem .inf)."""
        from ...common import xcursor
        fn = dialogs.open_file(self, plain("ms_install_scheme"), os.path.expanduser("~/Downloads"),
                               plain("ms_scheme_files") + " (*.zip *.tar.gz *.tgz *.tar.xz *.tar.bz2 *.inf *.cur *.ani)")
        if not fn:
            return
        import tempfile
        work = tempfile.mkdtemp(prefix="hz-cursors-")
        try:
            if fn.lower().endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(fn) as z:
                    for m in z.namelist():
                        if m.startswith("/") or ".." in m.split("/"):
                            continue
                        z.extract(m, work)
                src = work
            elif fn.lower().endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")):
                import tarfile
                with tarfile.open(fn) as t:
                    t.extractall(work, filter="data")
                src = work
            else:
                src = os.path.dirname(fn)
            # 1) gotowy motyw Xcursor (katalog z podkatalogiem cursors)
            for root, dirs, files in os.walk(src):
                if "cursors" in dirs and root != src or (root == src and "cursors" in dirs):
                    name = os.path.basename(root) if root != src else os.path.splitext(os.path.basename(fn))[0]
                    dest = os.path.join(os.path.expanduser("~/.icons"), name)
                    shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(root, dest, symlinks=True)
                    self._ptr_fill_themes(name)
                    self.changed()
                    dialogs.message(self, plain("mouse_props"), tr("ms_installed", name), "info")
                    return
            # 2) kursory Windows
            for root, dirs, files in os.walk(src):
                if any(f.lower().endswith((".cur", ".ani")) for f in files):
                    assign = xcursor.parse_inf_scheme(root)
                    if assign:
                        name = os.path.basename(root.rstrip("/")) if root != work else os.path.splitext(os.path.basename(fn))[0]
                        key = "Horyzont-wlasny-" + "".join(c if c.isalnum() else "-" for c in name)
                        xcursor.build_theme(key, assign, inherits="Horyzont")
                        self._ptr_custom = {}
                        self._ptr_fill_themes(key)
                        self.changed()
                        dialogs.message(self, plain("mouse_props"), tr("ms_installed_win", len(assign), name), "info")
                        return
            dialogs.message(self, plain("mouse_props"), plain("ms_nothing_found"), "warning")
        except Exception as e:
            dialogs.message(self, plain("mouse_props"), str(e), "error")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _toggle_folder(self, e):
        self.folder_open = not self.folder_open
        self.folder.setPixmap(iconcache.pixmap("folder_open" if self.folder_open else "folder", 32))

    def apply(self):
        theme = self.cursor_theme.currentData() or ""
        if self._ptr_custom:
            # zmienione pojedyncze wskaźniki — zapisujemy jako schemat „(zmodyfikowany)”
            theme = "Horyzont-wlasny-zmodyfikowany"
            try:
                self._ptr_build(theme)
            except Exception as e:
                dialogs.message(self, plain("mouse_props"), str(e), "error")
                return False
            self._ptr_custom = {}
            self._ptr_fill_themes(theme)
        apply_cursor_theme(theme, self.cursor_size.currentData())
        config.update({
            "mouse_left_handed": self.left.isChecked(),
            "mouse_double_click": 1100 - self.dbl.value(),
            "mouse_speed": self.speed.value() / 100.0,
            "mouse_accel_flat": not self.precision.isChecked(),
            "mouse_natural_scroll": self.natural.isChecked(),
            "touchpad_tap": self.tap.isChecked(),
            "cursor_theme": theme,
            "cursor_size": self.cursor_size.currentData(),
        })
        from PySide6.QtWidgets import QApplication
        QApplication.setDoubleClickInterval(1100 - self.dbl.value())
        _apply_labwc()
        return True


def apply_cursor_theme(theme, size):
    """Motyw wskaźników dla programów GTK/Qt i dla przyszłych procesów (labwc czyta zmienne przy przeładowaniu)."""
    os.environ["XCURSOR_THEME"] = theme
    os.environ["XCURSOR_SIZE"] = str(size)
    if shutil.which("gsettings"):
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", theme], capture_output=True)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(size)], capture_output=True)
    # domyślny motyw dla programów X11 i dla kolejnych sesji
    try:
        d = os.path.expanduser("~/.icons/default")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.theme"), "w", encoding="utf-8") as f:
            f.write(f"[Icon Theme]\nName=Default\nInherits={theme}\n")
    except OSError:
        pass
    if shutil.which("dbus-update-activation-environment"):
        subprocess.run(["dbus-update-activation-environment", "--systemd", f"XCURSOR_THEME={theme}", f"XCURSOR_SIZE={size}"],
                       capture_output=True)


def mouse(page=None, parent=None):
    return MouseProperties(page, parent)


# ================================================================== Klawiatura
LAYOUTS = [("pl", "Polski (programisty)"), ("us", "Angielski (USA)"), ("gb", "Angielski (Wielka Brytania)"),
           ("de", "Niemiecki"), ("fr", "Francuski"), ("es", "Hiszpański"), ("it", "Włoski"), ("cz", "Czeski"),
           ("sk", "Słowacki"), ("ua", "Ukraiński"), ("ru", "Rosyjski"), ("lt", "Litewski"), ("hu", "Węgierski")]


class KeyboardProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("keyboard_props"), "keyboard", parent)
        w, lay = self.add_tab(plain("kb_speed"))
        g = QGroupBox(plain("kb_repeat"))
        gl = QVBoxLayout(g)
        gl.addWidget(QLabel(plain("kb_repeat_delay")))
        sw, self.delay = _slider(150, 1000, 1150 - int(config.get("keyboard_repeat_delay", 600)), plain("kb_long"), plain("kb_short"))
        self.delay.valueChanged.connect(self.changed)
        gl.addWidget(sw)
        gl.addWidget(QLabel(plain("kb_repeat_rate")))
        sw2, self.rate = _slider(2, 60, int(config.get("keyboard_repeat_rate", 25)), plain("ms_slow"), plain("ms_fast"))
        self.rate.valueChanged.connect(self.changed)
        gl.addWidget(sw2)
        gl.addWidget(QLabel(plain("kb_test")))
        gl.addWidget(QLineEdit())
        lay.addWidget(g)
        g2 = QGroupBox(plain("kb_blink"))
        g2l = QVBoxLayout(g2)
        sw3, self.blink = _slider(0, 1800, 2000 - int(config.get("cursor_flash_ms", 1000)), plain("kb_none"), plain("ms_fast"))
        self.blink.valueChanged.connect(self.changed)
        g2l.addWidget(sw3)
        lay.addWidget(g2)
        lay.addStretch(1)
        w2, l2 = self.add_tab(plain("kb_layout"))
        l2.addWidget(QLabel(plain("kb_layout_desc")))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem(plain("kb_system_default"), "")
        for code, name in LAYOUTS:
            self.layout_combo.addItem(f"{name} [{code}]", code)
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(config.get("keyboard_layout", ""))))
        self.layout_combo.currentIndexChanged.connect(self.changed)
        l2.addWidget(self.layout_combo)
        l2.addStretch(1)
        w3, l3 = self.add_tab(plain("ms_hardware"))
        lst = QListWidget()
        for d in input_devices("kbd"):
            lst.addItem(d)
        l3.addWidget(QLabel(plain("ms_devices")))
        l3.addWidget(lst)
        self.resize(400, 420)

    def apply(self):
        config.update({
            "keyboard_repeat_delay": 1150 - self.delay.value(),
            "keyboard_repeat_rate": self.rate.value(),
            "cursor_flash_ms": 2000 - self.blink.value(),
            "keyboard_layout": self.layout_combo.currentData(),
        })
        from PySide6.QtWidgets import QApplication
        QApplication.setCursorFlashTime(2000 - self.blink.value())
        _apply_labwc()
        return True


def keyboard(page=None, parent=None):
    return KeyboardProperties(page, parent)


# ================================================================== Dźwięk
class SoundProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("sound_props"), "sound", parent)
        w, lay = self.add_tab(plain("snd_volume"))
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("sound", 48))
        head.addWidget(ic)
        out_name, in_name = sysctl.audio_devices()
        head.addWidget(QLabel(out_name), 1)
        lay.addLayout(head)
        g = QGroupBox(plain("snd_device_volume"))
        gl = QVBoxLayout(g)
        v = sysctl.volume_get()
        sw, self.vol = _slider(0, 100, v[0] if v else 50, plain("snd_low"), plain("snd_high"))
        self.vol.setEnabled(v is not None)
        gl.addWidget(sw)
        self.mute = QCheckBox(tr("snd_mute").replace("&", ""))
        self.mute.setChecked(bool(v and v[1]))
        self.mute.setEnabled(v is not None)
        gl.addWidget(self.mute)
        self.tray = QCheckBox(tr("snd_tray").replace("&", ""))
        self.tray.setChecked(config.get("volume_icon", True))
        self.tray.toggled.connect(self.changed)
        gl.addWidget(self.tray)
        lay.addWidget(g)
        if v is None:
            lay.addWidget(wrap_label(plain("snd_no_audio")))
        lay.addStretch(1)
        self.vol.valueChanged.connect(sysctl.volume_set)
        self.mute.toggled.connect(sysctl.volume_mute)
        # dźwięki — schematy i zdarzenia
        w2, l2 = self.add_tab(plain("snd_sounds"))
        l2.addWidget(wrap_label(plain("snd_scheme_desc")))
        l2.addWidget(QLabel(plain("snd_scheme")))
        srow = QHBoxLayout()
        self.scheme = QComboBox()
        self._events = dict(config.get("sound_events", {}))
        self._fill_schemes(config.get("sound_scheme", "horyzont"))
        self.scheme.activated.connect(self._scheme_chosen)
        srow.addWidget(self.scheme, 1)
        l2.addLayout(srow)
        brow = QHBoxLayout()
        brow.addStretch(1)
        save = QPushButton(plain("snd_save_as"))
        save.clicked.connect(self._save_scheme)
        self.del_btn = QPushButton(plain("delete").replace("&", ""))
        self.del_btn.clicked.connect(self._delete_scheme)
        imp = QPushButton(plain("snd_import"))
        imp.clicked.connect(self._import_scheme)
        for b_ in (save, self.del_btn, imp):
            brow.addWidget(b_)
        l2.addLayout(brow)
        l2.addWidget(wrap_label(plain("snd_events_desc")))
        self.events = QTreeWidget()
        self.events.setHeaderHidden(True)
        self.events.setRootIsDecorated(False)
        for ev in sounds.EVENTS:
            it = QTreeWidgetItem([sounds.label(ev)])
            it.setData(0, Qt.UserRole, ev)
            self.events.addTopLevelItem(it)
        self.events.currentItemChanged.connect(self._event_selected)
        l2.addWidget(self.events, 1)
        l2.addWidget(QLabel(plain("snd_sound_label")))
        row = QHBoxLayout()
        self.ev_sound = QComboBox()
        self.ev_sound.activated.connect(self._event_sound_chosen)
        row.addWidget(self.ev_sound, 1)
        play = QPushButton("▶")
        play.setFixedWidth(34)
        play.setToolTip(plain("snd_play"))
        play.clicked.connect(self._play_current)
        row.addWidget(play)
        br = QPushButton(plain("browse"))
        br.clicked.connect(self._browse_sound)
        row.addWidget(br)
        l2.addLayout(row)
        self.startup = QCheckBox(tr("snd_play_startup").replace("&", ""))
        self.startup.setChecked(config.get("startup_sound", False))
        self.startup.toggled.connect(self.changed)
        l2.addWidget(self.startup)
        self._refresh_event_icons()
        self.events.setCurrentItem(self.events.topLevelItem(0))
        # audio
        w3, l3 = self.add_tab(plain("snd_audio"))
        for title, name, icon in ((plain("snd_output"), out_name, "sound"), (plain("snd_input"), in_name, "recorder")):
            gb = QGroupBox(title)
            gbl = QHBoxLayout(gb)
            i2 = QLabel()
            i2.setPixmap(iconcache.pixmap(icon, 32))
            gbl.addWidget(i2)
            cb = QComboBox()
            cb.addItem(name)
            gbl.addWidget(cb, 1)
            l3.addWidget(gb)
        mixer = QPushButton(plain("snd_open_mixer"))
        mixer.clicked.connect(self._mixer)
        l3.addWidget(mixer, 0, Qt.AlignLeft)
        l3.addStretch(1)
        self.resize(400, 460)

    def _mixer(self):
        from ...common import launcher
        for c in ("pavucontrol", "pwvucontrol", "gnome-control-center"):
            if shutil.which(c):
                launcher._spawn([c] + (["sound"] if c == "gnome-control-center" else []))
                return
        dialogs.message(self, plain("sound_props"), plain("snd_no_mixer"), "info")

    # ------------------------------------------------------------ schematy dźwięków
    def _fill_schemes(self, current_key):
        self.scheme.blockSignals(True)
        self.scheme.clear()
        for key, name in sounds.schemes():
            self.scheme.addItem(name, key)
        if self._events:
            self.scheme.addItem(plain("snd_modified", self._scheme_name(current_key)), "modified")
            self.scheme.setCurrentIndex(self.scheme.count() - 1)
        else:
            i = self.scheme.findData(current_key)
            self.scheme.setCurrentIndex(max(0, i))
        self._base_scheme = current_key
        self.scheme.blockSignals(False)

    def _scheme_name(self, key):
        for k, n in sounds.schemes():
            if k == key:
                return n
        return key

    def _scheme_chosen(self, *_):
        key = self.scheme.currentData()
        if key == "modified":
            return
        self._events = {}
        self._base_scheme = key
        i = self.scheme.findData("modified")
        if i >= 0:
            self.scheme.removeItem(i)
        self._refresh_event_icons()
        self._event_selected(self.events.currentItem(), None)
        self.del_btn.setEnabled(key.startswith("user:"))
        self.changed()

    def _effective(self, ev):
        if ev in self._events:
            return self._events[ev]
        return sounds.scheme_sound(self._base_scheme, ev)

    def _refresh_event_icons(self):
        for i in range(self.events.topLevelItemCount()):
            it = self.events.topLevelItem(i)
            ev = it.data(0, Qt.UserRole)
            it.setIcon(0, iconcache.icon("sound") if self._effective(ev) else QIcon())
        self.del_btn.setEnabled(str(self._base_scheme).startswith("user:"))

    def _event_selected(self, cur, prev):
        self.ev_sound.blockSignals(True)
        self.ev_sound.clear()
        self.ev_sound.addItem(plain("snd_none_item"), "")
        if cur is None:
            self.ev_sound.blockSignals(False)
            return
        ev = cur.data(0, Qt.UserRole)
        eff = self._effective(ev)
        default = sounds.scheme_sound(self._base_scheme, ev)
        if default:
            self.ev_sound.addItem(plain("snd_scheme_item"), "__scheme__")
        if eff and eff != default:
            self.ev_sound.addItem(os.path.basename(eff), eff)
        for k, _ in (("horyzont", 0), ("zatoka", 0), ("krysztal", 0)):
            pth = sounds.scheme_sound(k, ev)
            if pth and self.ev_sound.findData(pth) < 0 and pth != default:
                self.ev_sound.addItem(f"{self._scheme_name(k)}", pth)
        if not eff:
            self.ev_sound.setCurrentIndex(0)
        elif eff == default:
            self.ev_sound.setCurrentIndex(1)
        else:
            self.ev_sound.setCurrentIndex(max(0, self.ev_sound.findData(eff)))
        self.ev_sound.blockSignals(False)

    def _set_event(self, ev, value):
        default = sounds.scheme_sound(self._base_scheme, ev)
        if value == "__scheme__" or value == default:
            self._events.pop(ev, None)
        else:
            self._events[ev] = value
        base = self._base_scheme
        self._fill_schemes(base)
        self._refresh_event_icons()
        self.changed()

    def _event_sound_chosen(self, *_):
        it = self.events.currentItem()
        if it is None:
            return
        self._set_event(it.data(0, Qt.UserRole), self.ev_sound.currentData())

    def _browse_sound(self):
        it = self.events.currentItem()
        if it is None:
            return
        fn = dialogs.open_file(self, plain("snd_browse_title"), config.user_dir("MUSIC"), plain("snd_filter") + " (*.wav *.ogg *.oga *.flac *.mp3)")
        if fn:
            self._set_event(it.data(0, Qt.UserRole), fn)
            self._event_selected(it, None)

    def _play_current(self):
        it = self.events.currentItem()
        if it is None:
            return
        sounds.play_file(self._effective(it.data(0, Qt.UserRole)))

    def _save_scheme(self):
        name = dialogs.ask_text(self, plain("snd_save_title"), plain("snd_save_label"), "", "sound")
        if not name:
            return
        data = {ev: self._effective(ev) for ev in sounds.EVENTS}
        # pliki wbudowane kopiujemy, by schemat działał niezależnie od pamięci podręcznej
        dest = os.path.join(config.DATA_DIR, "sound-schemes", name)
        os.makedirs(dest, exist_ok=True)
        for ev, pth in list(data.items()):
            if pth and pth.startswith(config.CACHE_DIR):
                tgt = os.path.join(dest, ev + ".wav")
                shutil.copyfile(pth, tgt)
                data[ev] = tgt
        schemes = dict(config.get("sound_schemes", {}))
        schemes[name] = data
        config.update({"sound_schemes": schemes, "sound_scheme": "user:" + name, "sound_events": {}})
        self._events = {}
        self._fill_schemes("user:" + name)
        self._refresh_event_icons()

    def _delete_scheme(self):
        key = self._base_scheme
        if not str(key).startswith("user:"):
            return
        name = key[5:]
        if dialogs.message(self, plain("sound_props"), tr("snd_delete_q", name), "question", ("yes", "no")) != "yes":
            return
        schemes = dict(config.get("sound_schemes", {}))
        schemes.pop(name, None)
        config.update({"sound_schemes": schemes, "sound_scheme": "horyzont"})
        shutil.rmtree(os.path.join(config.DATA_DIR, "sound-schemes", name), ignore_errors=True)
        self._events = {}
        self._fill_schemes("horyzont")
        self._refresh_event_icons()

    def _import_scheme(self):
        """Folder z plikami nazwanymi jak zdarzenia (startup.wav, error.ogg…) lub archiwum ZIP."""
        d = dialogs.choose_dir(self, plain("snd_import"), os.path.expanduser("~"))
        if not d:
            return
        name = os.path.basename(d.rstrip("/"))
        dest = os.path.join(config.DATA_DIR, "sound-schemes", name)
        os.makedirs(dest, exist_ok=True)
        data = {}
        aliases = {"start": "startup", "windows logon": "logon", "windows logoff": "logoff", "logon sound": "logon",
                   "critical stop": "error", "chord": "error", "ding": "exclamation", "notify": "notify",
                   "recycle": "recycle", "shutdown": "shutdown", "startup": "startup", "exclamation": "exclamation",
                   "hardware insert": "device_connect", "hardware remove": "device_disconnect",
                   "battery low": "battery_low", "balloon": "balloon", "question": "question", "menu command": "menu"}
        for fn in os.listdir(d):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in (".wav", ".ogg", ".oga", ".flac", ".mp3"):
                continue
            key = stem.lower().replace("_", " ").replace("-", " ")
            ev = stem if stem in sounds.EVENTS else next((v for k, v in aliases.items() if k in key), None)
            if ev:
                tgt = os.path.join(dest, ev + ext.lower())
                shutil.copyfile(os.path.join(d, fn), tgt)
                data[ev] = tgt
        if not data:
            dialogs.message(self, plain("sound_props"), plain("snd_import_none"), "warning")
            return
        schemes = dict(config.get("sound_schemes", {}))
        schemes[name] = data
        config.update({"sound_schemes": schemes})
        self._events = {}
        self._fill_schemes("user:" + name)
        self._base_scheme = "user:" + name
        self._refresh_event_icons()
        self.changed()
        dialogs.message(self, plain("sound_props"), tr("snd_import_ok", len(data), name), "info")

    def apply(self):
        config.update({"volume_icon": self.tray.isChecked(), "sound_scheme": self._base_scheme,
                       "sound_events": dict(self._events), "startup_sound": self.startup.isChecked()})
        return True


def sound(page=None, parent=None):
    return SoundProperties(page, parent)
