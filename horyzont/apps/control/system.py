"""Właściwości systemu."""
import os
import platform
import shutil
import subprocess
import time

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QCheckBox, QDialogButtonBox, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget, QPlainTextEdit)

from ... import config
from ...common import dialogs, launcher, sysctl
from ...common.window import HDialog, HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ..about import Banner
from .common import AppletDialog, hline, run, run_privileged, wrap_label


def uptime_text():
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
    except OSError:
        return "?"
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    return (f"{d} d " if d else "") + f"{h} h {m} min"


class DeviceManager(HWindow):
    """Prosty Menedżer urządzeń: drzewo urządzeń PCI/USB/bloków/wejścia z /sys."""

    def __init__(self):
        super().__init__(plain("sys_device_mgr"), "system")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        lay.addWidget(self.tree)
        root = QTreeWidgetItem([sysctl.hostname()])
        root.setIcon(0, iconcache.icon("computer"))
        self.tree.addTopLevelItem(root)
        cats = {}

        def cat(name, icon):
            if name not in cats:
                it = QTreeWidgetItem([name])
                it.setIcon(0, iconcache.icon(icon))
                root.addChild(it)
                cats[name] = it
            return cats[name]

        c = cat(plain("dm_cpu"), "system")
        ncpu = os.cpu_count() or 1
        name = sysctl.cpu_name()
        for i in range(ncpu):
            QTreeWidgetItem(c, [name])
        if shutil.which("lspci"):
            rc, out = run(["lspci", "-mm"])
            for line in out.splitlines():
                parts = [p.strip('"') for p in _split_quoted(line)]
                if len(parts) < 4:
                    continue
                cls, vendor, dev = parts[1], parts[2], parts[3]
                key, icon = _pci_category(cls)
                QTreeWidgetItem(cat(plain(key), icon), [f"{vendor} {dev}"])
        if shutil.which("lsusb"):
            rc, out = run(["lsusb"])
            for line in out.splitlines():
                desc = line.split(" ", 6)[-1] if line.count(" ") >= 6 else line
                QTreeWidgetItem(cat(plain("dm_usb"), "drive_usb"), [desc])
        for d in sorted(os.listdir("/sys/block")) if os.path.isdir("/sys/block") else []:
            if d.startswith(("loop", "ram", "zram")):
                continue
            model = ""
            try:
                with open(f"/sys/block/{d}/device/model") as f:
                    model = f.read().strip()
            except OSError:
                pass
            QTreeWidgetItem(cat(plain("dm_disks"), "drive_hdd"), [f"{model or d} ({d})"])
        from .applets_basic import input_devices
        for n in input_devices("kbd"):
            QTreeWidgetItem(cat(plain("dm_keyboards"), "keyboard"), [n])
        for n in input_devices("mouse"):
            QTreeWidgetItem(cat(plain("dm_mice"), "mouse"), [n])
        root.setExpanded(True)
        self.tree.sortItems(0, Qt.AscendingOrder)
        self.resize(480, 460)


def _split_quoted(line):
    import shlex
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()


def _pci_category(cls):
    c = cls.lower()
    if "vga" in c or "display" in c or "3d" in c:
        return "dm_display", "display"
    if "audio" in c or "multimedia" in c:
        return "dm_sound", "sound"
    if "ethernet" in c or "network" in c or "wireless" in c:
        return "dm_network", "network_conn"
    if "usb" in c:
        return "dm_usbctl", "drive_usb"
    if "sata" in c or "ide" in c or "nvme" in c or "storage" in c or "raid" in c:
        return "dm_storage", "drive_hdd"
    if "bridge" in c or "host" in c or "isa" in c or "smbus" in c:
        return "dm_system", "admin"
    return "dm_other", "app"


class UpdateWorker(QThread):
    done = Signal(int, str)

    def run(self):
        exe = shutil.which("dnf") or shutil.which("dnf5")
        if not exe:
            self.done.emit(-1, "")
            return
        try:
            r = subprocess.run([exe, "-q", "check-update"], capture_output=True, text=True, timeout=600)
            lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith(("Last", "Obsoleting", "Ostatnie"))]
            self.done.emit(r.returncode, "\n".join(lines))
        except Exception as e:
            self.done.emit(-1, str(e))


class SystemProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("system_props"), "system", parent)
        # Ogólne
        w, lay = self.add_tab(plain("general"))
        row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(iconcache.pixmap("logo", 96))
        logo.setAlignment(Qt.AlignTop)
        row.addWidget(logo)
        info = QVBoxLayout()
        osr = sysctl.os_release()

        def add(text, bold=False, indent=False):
            l = QLabel(text)
            l.setWordWrap(True)
            if bold:
                f = l.font()
                f.setBold(True)
                l.setFont(f)
            if indent:
                l.setContentsMargins(16, 0, 0, 0)
            info.addWidget(l)

        add(plain("sys_system"), True)
        add(osr.get("NAME", "Linux"), indent=True)
        add(osr.get("VERSION", platform.release()), indent=True)
        add(tr("sys_kernel", platform.release()), indent=True)
        add(f"Horyzont {config.VERSION}", indent=True)
        info.addSpacing(10)
        add(plain("sys_registered"), True)
        add(sysctl.user_full_name(), indent=True)
        add(sysctl.hostname(), indent=True)
        info.addSpacing(10)
        add(plain("sys_computer"), True)
        add(sysctl.cpu_name(), indent=True)
        add(f"{os.cpu_count()} × CPU, {platform.machine()}", indent=True)
        add(tr("sys_ram", sysctl.human_size(sysctl.mem_total())), indent=True)
        add(tr("sys_uptime", uptime_text()), indent=True)
        info.addStretch(1)
        row.addLayout(info, 1)
        lay.addLayout(row)
        # Nazwa komputera
        w2, l2 = self.add_tab(plain("sys_computer_name"))
        l2.addWidget(wrap_label(plain("sys_name_desc")))
        g = QGridLayout()
        g.addWidget(QLabel(plain("sys_desc")), 0, 0)
        self.desc = QLineEdit(config.get("computer_description", ""))
        self.desc.textChanged.connect(self.changed)
        g.addWidget(self.desc, 0, 1)
        g.addWidget(QLabel(plain("sys_full_name")), 1, 0)
        self.host_lbl = QLabel(sysctl.hostname())
        g.addWidget(self.host_lbl, 1, 1)
        l2.addLayout(g)
        ch = QPushButton(plain("sys_change_name"))
        ch.clicked.connect(self._change_hostname)
        l2.addWidget(ch, 0, Qt.AlignRight)
        l2.addStretch(1)
        # Sprzęt
        w3, l3 = self.add_tab(plain("sys_hardware"))
        gb = QGroupBox(plain("sys_device_mgr").replace("&", ""))
        gbl = QHBoxLayout(gb)
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("system", 32))
        gbl.addWidget(ic, 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.addWidget(wrap_label(plain("sys_device_mgr_desc")))
        dm = QPushButton(plain("sys_device_mgr"))
        dm.clicked.connect(self._device_manager)
        v.addWidget(dm, 0, Qt.AlignRight)
        gbl.addLayout(v, 1)
        l3.addWidget(gb)
        l3.addStretch(1)
        # Zaawansowane
        w4, l4 = self.add_tab(plain("advanced"))
        perf = QGroupBox(plain("sys_perf"))
        pl = QVBoxLayout(perf)
        pl.addWidget(wrap_label(plain("sys_perf_desc")))
        b = QPushButton(plain("settings"))
        b.clicked.connect(lambda: launcher.start_builtin("taskmgr"))
        pl.addWidget(b, 0, Qt.AlignRight)
        l4.addWidget(perf)
        env = QGroupBox(plain("sys_env").replace("&", ""))
        el = QVBoxLayout(env)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText("\n".join(f"{k}={v}" for k, v in sorted(os.environ.items()) if not k.startswith("_")))
        el.addWidget(txt)
        l4.addWidget(env, 1)
        # Przywracanie systemu
        w5, l5 = self.add_tab(plain("sys_restore"))
        l5.addWidget(wrap_label(plain("sys_restore_desc")))
        snap = shutil.which("snapper")
        tl = QTreeWidget()
        tl.setHeaderLabels(["#", plain("adm_time"), plain("adm_service_desc")])
        if snap:
            rc, out = run(["snapper", "list"], 10)
            for line in out.splitlines()[2:]:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7:
                    QTreeWidgetItem(tl, [parts[0], parts[3], parts[-2]])
        l5.addWidget(tl, 1)
        # Aktualizacje
        w6, l6 = self.add_tab(plain("sys_updates"))
        l6.addWidget(wrap_label(tr("sys_updates_desc")))
        self.upd_btn = QPushButton(plain("sys_check_updates"))
        self.upd_btn.clicked.connect(self._check_updates)
        l6.addWidget(self.upd_btn, 0, Qt.AlignLeft)
        self.upd_out = QPlainTextEdit()
        self.upd_out.setReadOnly(True)
        l6.addWidget(self.upd_out, 1)
        self.upd_install = QPushButton(plain("sys_install_updates"))
        self.upd_install.setEnabled(False)
        self.upd_install.clicked.connect(self._install_updates)
        l6.addWidget(self.upd_install, 0, Qt.AlignRight)
        rc, out = run(["systemctl", "is-enabled", "dnf-automatic.timer"])
        self.auto_upd = QCheckBox(plain("sys_auto_updates"))
        self.auto_upd.setChecked(out.strip() == "enabled")
        self.auto_upd.setEnabled(rc in (0, 1) and "not-found" not in out)
        self.auto_upd.toggled.connect(self.changed)
        l6.addWidget(self.auto_upd)
        # Zdalny
        w7, l7 = self.add_tab(plain("sys_remote"))
        l7.addWidget(wrap_label(tr("sys_remote_desc")))
        rc, out = run(["systemctl", "is-active", "sshd"])
        self.ssh = QCheckBox(tr("sys_ssh_enable").replace("&", ""))
        self.ssh.setChecked(out.strip() == "active")
        self._ssh_was = self.ssh.isChecked()
        self.ssh.toggled.connect(self.changed)
        l7.addWidget(self.ssh)
        l7.addStretch(1)
        self.resize(430, 470)
        if page == "updates":
            self.tabs.setCurrentIndex(5)

    def _device_manager(self):
        from .devmgr import DeviceManager as DM
        self._dm = DM()
        self._dm.show()

    def _change_hostname(self):
        new = dialogs.ask_text(self, plain("sys_computer_name"), plain("sys_new_name"), sysctl.hostname())
        if new and new != sysctl.hostname():
            ok, _ = run_privileged(["hostnamectl", "set-hostname", new], self)
            if ok:
                self.host_lbl.setText(new)

    def _check_updates(self):
        self.upd_btn.setEnabled(False)
        self.upd_out.setPlainText(plain("sys_checking"))
        self._w = UpdateWorker()
        self._w.done.connect(self._updates_done)
        self._w.start()

    def _updates_done(self, rc, text):
        self.upd_btn.setEnabled(True)
        if rc == 100:
            self.upd_out.setPlainText(text)
            self.upd_install.setEnabled(True)
        elif rc == 0:
            self.upd_out.setPlainText(plain("sys_up_to_date"))
        else:
            self.upd_out.setPlainText(text or plain("sys_no_dnf"))

    def _install_updates(self):
        exe = shutil.which("dnf") or shutil.which("dnf5") or "dnf"
        launcher.open_terminal()
        dialogs.message(self, plain("sys_updates"), tr("sys_update_cmd", f"sudo {os.path.basename(exe)} upgrade"), "info")

    def apply(self):
        config.set("computer_description", self.desc.text())
        if self.ssh.isChecked() != self._ssh_was:
            ok, _ = run_privileged(["systemctl", "enable" if self.ssh.isChecked() else "disable", "--now", "sshd"], self)
            if ok:
                self._ssh_was = self.ssh.isChecked()
        if self.auto_upd.isEnabled():
            rc, out = run(["systemctl", "is-enabled", "dnf-automatic.timer"])
            if (out.strip() == "enabled") != self.auto_upd.isChecked():
                run_privileged(["systemctl", "enable" if self.auto_upd.isChecked() else "disable", "--now",
                                "dnf-automatic.timer"], self)
        return True


def open_system(page=None, parent=None):
    return SystemProperties(page, parent)
