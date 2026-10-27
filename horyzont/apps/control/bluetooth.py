"""Urządzenia Bluetooth (BlueZ przez bluetoothctl): lista, opcje, sprzęt i Kreator dodawania urządzenia."""
import os
import re
import shutil
import subprocess

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from ... import config
from ...common import dialogs
from ...common.jobs import run_job
from ...common.privileged import ANSI_RE, PtyProcess
from ...common.wizard import Wizard, WizardPage
from ...i18n import plain, tr
from ...theme import iconcache
from .common import AppletDialog

MAC_RE = re.compile(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})", re.I)

CATEGORIES = [
    ("bt_cat_audio", "sound", ("audio", "headset", "headphone", "speaker")),
    ("bt_cat_input", "mouse", ("input", "mouse", "keyboard", "gaming", "tablet")),
    ("bt_cat_phone", "network", ("phone",)),
    ("bt_cat_computer", "computer", ("computer",)),
    ("bt_cat_other", "bluetooth", ("",)),
]


def ctl(args, timeout=8):
    if not shutil.which("bluetoothctl"):
        return 127, ""
    try:
        r = subprocess.run(["bluetoothctl"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ANSI_RE.sub("", r.stdout)
    except Exception as e:
        return -1, str(e)


def adapters():
    rc, out = ctl(["list"])
    res = []
    for line in out.splitlines():
        m = MAC_RE.search(line)
        if line.startswith("Controller") and m:
            name = line.split(m.group(1), 1)[1].replace("[default]", "").strip()
            res.append({"mac": m.group(1), "name": name, "default": "[default]" in line})
    return res


def adapter_info():
    rc, out = ctl(["show"])
    info = {}
    for line in out.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("Controller"):
            k, v = line.split(":", 1)
            info.setdefault(k.strip(), v.strip())
    return info


def devices(only_paired=True):
    rc, out = ctl(["devices", "Paired"] if only_paired else ["devices"])
    if only_paired and ("Invalid" in out or not out.strip()):
        rc2, out2 = ctl(["paired-devices"])
        if out2.strip():
            out = out2
    res = []
    for line in out.splitlines():
        p = line.strip().split(" ", 2)
        if len(p) >= 2 and p[0] == "Device" and MAC_RE.match(p[1]):
            res.append({"mac": p[1], "name": p[2] if len(p) > 2 else p[1]})
    return res


def device_info(mac):
    rc, out = ctl(["info", mac])
    info = {}
    for line in out.splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            info.setdefault(k.strip(), v.strip())
    return info


def category_for(icon):
    icon = (icon or "").lower()
    for key, ic, words in CATEGORIES:
        if any(w and w in icon for w in words):
            return key, ic
    return "bt_cat_other", "bluetooth"


class BtSession(QObject):
    """Interaktywny bluetoothctl w pty — parowanie z obsługą pytań agenta (PIN, klucz)."""

    line = Signal(str)
    found = Signal(str, str)          # mac, nazwa (wyszukiwanie)
    done = Signal(bool, str)          # zakończono sekwencję poleceń

    def __init__(self, parent_widget=None):
        super().__init__()
        self.parent_widget = parent_widget
        env = dict(os.environ, TERM="dumb", LC_ALL="C")
        self.proc = PtyProcess(["bluetoothctl"], env, self)
        self.proc.data.connect(self._data)
        self.buf = ""
        self.queue = []
        self.waiting = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)
        self.send("agent KeyboardDisplay")
        self.send("default-agent")

    def send(self, cmd):
        self.proc.write(cmd + "\n")

    def close(self):
        self.send("scan off")
        self.send("quit")
        QTimer.singleShot(1500, self.proc.interrupt)

    def run_sequence(self, steps, timeout=40000):
        """steps: lista (polecenie, wzorzec sukcesu, wzorzec błędu)."""
        self.queue = list(steps)
        self._next(timeout)

    def _next(self, timeout=40000):
        if not self.queue:
            self.waiting = None
            self.done.emit(True, "")
            return
        cmd, ok_pat, err_pat = self.queue.pop(0)
        self.waiting = (re.compile(ok_pat, re.I), re.compile(err_pat, re.I) if err_pat else None, timeout)
        self.send(cmd)
        self._timer.start(timeout)

    def _timeout(self):
        if self.waiting:
            self.waiting = None
            self.queue = []
            self.done.emit(False, plain("bt_timeout"))

    def _data(self, text):
        self.buf += ANSI_RE.sub("", text)
        lines = self.buf.split("\n")
        self.buf = lines.pop()
        for l in lines:
            self._handle(l.strip())
        tail = self.buf.strip()
        if tail.startswith("[agent]") and tail.endswith(":"):
            self.buf = ""
            self._agent_prompt(tail)

    def _handle(self, l):
        if not l:
            return
        l = re.sub(r"^\[[^\]]*\][#>]\s*", "", l)
        self.line.emit(l)
        m = re.search(r"\[(NEW|CHG)\] Device ([0-9A-F:]{17}) (.+)", l, re.I)
        if m and m.group(1).upper() == "NEW":
            name = m.group(3)
            self.found.emit(m.group(2), name)
        elif m and "Name:" in l:
            self.found.emit(m.group(2), m.group(3).split("Name:", 1)[1].strip())
        if l.startswith("[agent]") and (l.endswith(":") or "(yes/no)" in l):
            self._agent_prompt(l)
            return
        if l.startswith("[agent] Passkey:") or l.startswith("[agent] PIN code:"):
            code = l.split(":", 1)[1].strip()
            dialogs.message(self.parent_widget, plain("bt_title"), tr("bt_type_code", code), "info")
            return
        if self.waiting:
            ok_re, err_re, timeout = self.waiting
            if err_re and err_re.search(l):
                self._timer.stop()
                self.waiting = None
                self.queue = []
                self.done.emit(False, l)
            elif ok_re.search(l):
                self._timer.stop()
                self.waiting = None
                self._next(timeout)

    def _agent_prompt(self, p):
        low = p.lower()
        if "confirm passkey" in low or "request confirmation" in low:
            code = re.search(r"(\d{4,6})", p)
            q = tr("bt_confirm_code", code.group(1) if code else "")
            ans = dialogs.message(self.parent_widget, plain("bt_title"), q, "question", ("yes", "no"))
            self.send("yes" if ans == "yes" else "no")
        elif "authorize" in low or "accept pairing" in low:
            self.send("yes")
        elif "pin code" in low or "passkey" in low:
            v = dialogs.ask_text(self.parent_widget, plain("bt_title"), plain("bt_enter_pin"), "", "key")
            self.send(v or "0000")
        else:
            self.send("yes")


class BluetoothDevices(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("bt_devices_title"), "bluetooth", parent)
        self.present = bool(shutil.which("bluetoothctl")) and bool(adapters())
        # --- Urządzenia
        w, lay = self.add_tab(plain("bt_tab_devices"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(32, 32))
        self.tree.currentItemChanged.connect(self._sel)
        self.tree.itemDoubleClicked.connect(lambda *_: self.properties())
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.add_btn = QPushButton(plain("bt_add"))
        self.add_btn.clicked.connect(self.add_device)
        self.rem_btn = QPushButton(plain("bt_remove"))
        self.rem_btn.clicked.connect(self.remove)
        self.conn_btn = QPushButton(plain("bt_connect"))
        self.conn_btn.clicked.connect(self.toggle_connect)
        self.prop_btn = QPushButton(plain("properties").replace("&", ""))
        self.prop_btn.clicked.connect(self.properties)
        for b in (self.add_btn, self.rem_btn, self.conn_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.prop_btn)
        lay.addLayout(row)
        # --- Opcje
        w2, l2 = self.add_tab(plain("bt_tab_options"))
        info = adapter_info() if self.present else {}
        g1 = QGroupBox(plain("bt_discovery"))
        g1l = QVBoxLayout(g1)
        self.discoverable = QCheckBox(plain("bt_allow_discovery"))
        self.discoverable.setChecked(info.get("Discoverable") == "yes")
        g1l.addWidget(self.discoverable)
        lbl = QLabel(plain("bt_discovery_warn"))
        lbl.setWordWrap(True)
        g1l.addWidget(lbl)
        l2.addWidget(g1)
        g2 = QGroupBox(plain("bt_connections"))
        g2l = QVBoxLayout(g2)
        self.pairable = QCheckBox(plain("bt_allow_connect"))
        self.pairable.setChecked(info.get("Pairable", "yes") == "yes")
        self.alert = QCheckBox(plain("bt_alert_new"))
        self.alert.setChecked(config.get("bt_notify", True))
        g2l.addWidget(self.pairable)
        g2l.addWidget(self.alert)
        l2.addWidget(g2)
        self.tray = QCheckBox(plain("bt_show_tray"))
        self.tray.setChecked(config.get("bt_tray_icon", True))
        self.power = QCheckBox(plain("bt_power"))
        self.power.setChecked(info.get("Powered") == "yes")
        l2.addWidget(self.tray)
        l2.addWidget(self.power)
        l2.addStretch(1)
        for c in (self.discoverable, self.pairable, self.alert, self.tray, self.power):
            c.toggled.connect(self.changed)
        # --- Sprzęt
        w3, l3 = self.add_tab(plain("bt_tab_hardware"))
        l3.addWidget(QLabel(plain("bt_adapters")))
        self.hw = QTreeWidget()
        self.hw.setHeaderLabels([plain("name"), plain("bt_address")])
        self.hw.setRootIsDecorated(False)
        for a in adapters():
            it = QTreeWidgetItem([a["name"] or "Bluetooth", a["mac"]])
            it.setIcon(0, iconcache.icon("bluetooth"))
            self.hw.addTopLevelItem(it)
        self.hw.setColumnWidth(0, 200)
        l3.addWidget(self.hw, 1)
        g3 = QGroupBox(plain("bt_props"))
        g3l = QVBoxLayout(g3)
        hw_text = []
        if info:
            hw_text.append(f"{plain('name')}: {info.get('Alias') or info.get('Name', '')}")
            hw_text.append(f"{plain('tm_status')}: {plain('bt_works') if info.get('Powered') == 'yes' else plain('bt_off')}")
            for k in ("Modalias", "Class"):
                if info.get(k):
                    hw_text.append(f"{k}: {info[k]}")
        else:
            hw_text.append(plain("bt_no_adapter") if shutil.which("bluetoothctl") else plain("bt_no_bluez"))
        lab = QLabel("\n".join(hw_text))
        lab.setWordWrap(True)
        g3l.addWidget(lab)
        l3.addWidget(g3)
        if not shutil.which("bluetoothctl"):
            ib = QPushButton(plain("bt_install_bluez"))
            ib.clicked.connect(self._install_bluez)
            l3.addWidget(ib, 0, Qt.AlignLeft)
        self.resize(440, 470)
        self.reload()
        self.show_page(page)

    def show_page(self, page):
        if page == "options":
            self.tabs.setCurrentIndex(1)
        elif page == "hardware":
            self.tabs.setCurrentIndex(2)
        elif page == "add":
            QTimer.singleShot(200, self.add_device)

    def _install_bluez(self):
        ok, _ = run_job(self, plain("bt_devices_title"), tr("ar_installing", "bluez"),
                        ["dnf", "install", "-y", "bluez"], icon="bluetooth")
        if ok:
            subprocess.run(["systemctl", "start", "bluetooth"], capture_output=True)

    def reload(self):
        self.tree.clear()
        if not self.present:
            it = QTreeWidgetItem([plain("bt_no_adapter") if shutil.which("bluetoothctl") else plain("bt_no_bluez")])
            self.tree.addTopLevelItem(it)
            for b in (self.add_btn, self.rem_btn, self.conn_btn, self.prop_btn):
                b.setEnabled(False)
            return
        groups = {}
        for d in devices(True):
            info = device_info(d["mac"])
            key, icon = category_for(info.get("Icon", ""))
            d["info"] = info
            d["icon"] = icon
            groups.setdefault(key, []).append(d)
        for key, icon, _ in CATEGORIES:
            if key not in groups:
                continue
            head = QTreeWidgetItem([plain(key)])
            f = head.font(0)
            f.setBold(True)
            head.setFont(0, f)
            head.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(head)
            for d in groups[key]:
                info = d["info"]
                lines = [d["name"]]
                st = plain("bt_connected") if info.get("Connected") == "yes" else plain("bt_paired")
                bat = re.search(r"\((\d+)\)", info.get("Battery Percentage", ""))
                if bat:
                    st += " — " + tr("bt_battery", bat.group(1))
                it = QTreeWidgetItem([f"{d['name']}\n{st}"])
                it.setIcon(0, iconcache.icon(d["icon"]))
                it.setData(0, Qt.UserRole, d)
                head.addChild(it)
            head.setExpanded(True)
        if not groups:
            it = QTreeWidgetItem([plain("bt_no_devices")])
            it.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(it)
        self._sel(None, None)

    def _current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def _sel(self, cur, prev):
        d = self._current()
        for b in (self.rem_btn, self.conn_btn, self.prop_btn):
            b.setEnabled(d is not None)
        if d:
            self.conn_btn.setText(plain("bt_disconnect") if d["info"].get("Connected") == "yes" else plain("bt_connect"))

    def add_device(self):
        if not self.present:
            return
        w = AddDeviceWizard(self)
        w.start()
        self.reload()

    def remove(self):
        d = self._current()
        if not d:
            return
        if dialogs.message(self, plain("bt_devices_title"), tr("bt_remove_q", d["name"]), "question", ("yes", "no")) == "yes":
            ctl(["remove", d["mac"]], 15)
            self.reload()

    def toggle_connect(self):
        d = self._current()
        if not d:
            return
        on = d["info"].get("Connected") == "yes"
        rc, out = ctl(["disconnect" if on else "connect", d["mac"]], 30)
        if not on and ("Failed" in out or rc != 0):
            dialogs.message(self, plain("bt_devices_title"), tr("bt_connect_failed", d["name"]) + "\n\n" + out.strip()[-300:],
                            "warning")
        self.reload()

    def properties(self):
        d = self._current()
        if not d:
            return
        info = d["info"]
        rows = [(plain("name"), d["name"]), (plain("bt_address"), d["mac"]),
                (plain("bt_type"), plain(category_for(info.get("Icon", ""))[0])),
                (plain("tm_status"), plain("bt_connected") if info.get("Connected") == "yes" else plain("bt_paired")),
                (plain("bt_trusted"), plain("yes") if info.get("Trusted") == "yes" else plain("no"))]
        bat = re.search(r"\((\d+)\)", info.get("Battery Percentage", ""))
        if bat:
            rows.append((plain("bt_battery_label"), bat.group(1) + "%"))
        dialogs.message(self, tr("nc_props_title", d["name"]), "\n".join(f"{k}: {v}" for k, v in rows), "bluetooth")

    def apply(self):
        info = adapter_info() if self.present else {}
        if self.present:
            if self.power.isChecked() != (info.get("Powered") == "yes"):
                if self.power.isChecked() and shutil.which("rfkill"):
                    subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
                ctl(["power", "on" if self.power.isChecked() else "off"])
            if self.discoverable.isChecked() != (info.get("Discoverable") == "yes"):
                ctl(["discoverable", "on" if self.discoverable.isChecked() else "off"])
            if self.pairable.isChecked() != (info.get("Pairable") == "yes"):
                ctl(["pairable", "on" if self.pairable.isChecked() else "off"])
        config.update({"bt_tray_icon": self.tray.isChecked(), "bt_notify": self.alert.isChecked()})
        return True


class AddDeviceWizard(Wizard):
    def __init__(self, parent=None):
        super().__init__(plain("bt_wizard_title"), "bluetooth", parent)
        self.session = None
        p = WizardPage(plain("bt_wizard_welcome"), exterior=True)
        d = QLabel(plain("bt_wizard_welcome_desc"))
        d.setWordWrap(True)
        p.lay.addWidget(d)
        p.lay.addSpacing(10)
        self.ready = QCheckBox(plain("bt_wizard_ready"))
        self.ready.toggled.connect(lambda *_: p.completeChanged.emit())
        p.lay.addWidget(self.ready)
        p.is_complete = lambda: self.ready.isChecked()
        self.add_page(p)
        # wyszukiwanie
        p = WizardPage(plain("bt_wizard_select"), plain("bt_wizard_select_sub"))
        self.list = QListWidget()
        self.list.setIconSize(QSize(32, 32))
        self.list.currentItemChanged.connect(lambda *_: p.completeChanged.emit())
        p.lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.scan_lbl = QLabel()
        row.addWidget(self.scan_lbl, 1)
        rb = QPushButton(plain("bt_search_again"))
        rb.clicked.connect(self._scan)
        row.addWidget(rb)
        p.lay.addLayout(row)
        p.on_enter = lambda wz: self._scan()
        p.is_complete = lambda: self.list.currentItem() is not None
        p.validate = self._choose
        self.add_page(p)
        # parowanie
        p = WizardPage(plain("bt_wizard_pairing"), plain("bt_wizard_pairing_sub"))
        self.pair_lbl = QLabel()
        self.pair_lbl.setWordWrap(True)
        p.lay.addWidget(self.pair_lbl)
        self.pair_bar = QProgressBar()
        self.pair_bar.setRange(0, 0)
        self.pair_bar.setTextVisible(False)
        p.lay.addWidget(self.pair_bar)
        self.pair_log = QLabel()
        self.pair_log.setStyleSheet("color: #555;")
        self.pair_log.setWordWrap(True)
        p.lay.addWidget(self.pair_log)
        self._paired = None
        p.is_complete = lambda: self._paired is not None
        p.on_enter = lambda wz: self._pair()
        self.add_page(p)
        # koniec
        p = WizardPage(plain("bt_wizard_done"), exterior=True)
        self.done_lbl = QLabel()
        self.done_lbl.setWordWrap(True)
        p.lay.addWidget(self.done_lbl)
        p.final = True
        self.add_page(p)
        self.rejected.connect(self._cleanup)
        self.accepted.connect(self._cleanup)
        self.resize(540, 420)

    def _session(self):
        if self.session is None:
            self.session = BtSession(self)
            self.session.found.connect(self._found)
            self.session.line.connect(lambda l: self.pair_log.setText(l[-160:]) if self.current_index() == 2 else None)
            self.session.done.connect(self._pair_done)
        return self.session

    def _cleanup(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def _scan(self):
        self.list.clear()
        self._seen = {}
        s = self._session()
        s.send("power on")
        s.send("scan on")
        self.scan_lbl.setText(plain("bt_searching"))
        QTimer.singleShot(20000, lambda: self.scan_lbl.setText(tr("bt_found_n", self.list.count())))
        # urządzenia znane wcześniej, ale niesparowane
        paired = {d["mac"] for d in devices(True)}
        for d in devices(False):
            if d["mac"] not in paired:
                self._found(d["mac"], d["name"])

    def _found(self, mac, name):
        if not hasattr(self, "_seen"):
            self._seen = {}
        if re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", name.replace(":", "-"), re.I):
            name = mac   # bez nazwy
        it = self._seen.get(mac)
        if it is None:
            it = QListWidgetItem(iconcache.icon("bluetooth"), name)
            it.setData(Qt.UserRole, mac)
            self.list.addItem(it)
            self._seen[mac] = it
        elif name != mac:
            it.setText(name)

    def _choose(self, wz):
        it = self.list.currentItem()
        if it is None:
            return False
        self.mac = it.data(Qt.UserRole)
        self.dev_name = it.text()
        return True

    def _pair(self):
        self._paired = None
        self.pair_bar.setRange(0, 0)
        self.pair_lbl.setText(tr("bt_pairing_with", self.dev_name))
        s = self._session()
        s.send("scan off")
        mac = self.mac
        s.run_sequence([
            (f"pair {mac}", r"Pairing successful|AlreadyExists|already paired", r"Failed to pair|not available|AuthenticationFailed|AuthenticationCanceled"),
            (f"trust {mac}", r"trust succeeded|Changing .* trust succeeded|Trusted: yes", r"Failed"),
        ])
        self._update_buttons()

    def _pair_done(self, ok, msg):
        if self.current_index() != 2:
            return
        self.pair_bar.setRange(0, 1)
        self.pair_bar.setValue(1 if ok else 0)
        if ok:
            # łączymy od razu (nie wszystkie urządzenia to obsługują — np. telefony)
            self.session.send(f"connect {self.mac}")
            self._paired = self.mac
            self.pair_lbl.setText(tr("bt_pair_ok", self.dev_name))
            self.done_lbl.setText(tr("bt_wizard_done_desc", self.dev_name))
            self._update_buttons()
            QTimer.singleShot(600, self.next)
        else:
            self.pair_lbl.setText(tr("bt_pair_failed", self.dev_name) + "\n" + msg)
            self._paired = None
            self._update_buttons()


def open_bluetooth(page=None, parent=None):
    return BluetoothDevices(page, parent)
