"""Połączenia sieciowe (NetworkManager przez nmcli): lista, stan, właściwości,
Kreator nowego połączenia — wszystko w oknach Horyzontu (bez nm-connection-editor)."""
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout)

from ...common import dialogs, launcher, netman, sysctl
from ...common.window import HDialog
from ...common.wizard import Wizard, WizardPage
from ...i18n import plain, tr
from ...theme import iconcache
from .common import AppletDialog
from .folderwin import FolderWindow, entry, header

WIRED = ("ethernet", "802-3-ethernet")
WIFI = ("wifi", "802-11-wireless")


def _state_text(st):
    if st.startswith("connected"):
        return plain("nc_connected")
    if "unavailable" in st:
        return plain("nc_unavailable")
    if "disconnected" in st or st == "":
        return plain("nc_disconnected")
    if "connecting" in st:
        return plain("nc_connecting")
    if "unmanaged" in st:
        return plain("nc_unmanaged")
    return st


class NetworkWindow(FolderWindow):
    title_key = "network_conn"
    icon = "network_conn"

    def load_items(self):
        if not netman.available():
            return [header(plain("nc_no_nm"))]
        devs = {d["device"]: d for d in netman.devices()}
        cons = netman.connections()
        items = []
        groups = {"lan": [], "wifi": [], "vpn": [], "other": []}
        used_devices = set()
        for c in cons:
            if c["type"] in WIFI and not c["active"]:
                continue   # zapisane sieci Wi-Fi są w oknie sieci bezprzewodowych
            dev = devs.get(c["device"])
            st = dev["state"] if (dev and c["active"]) else ("connected" if c["active"] else "disconnected")
            c = dict(c, state=st)
            used_devices.add(c["device"])
            kind = "lan" if c["type"] in WIRED else "wifi" if c["type"] in WIFI else \
                "vpn" if c["type"] in ("vpn", "wireguard") else "other"
            groups[kind].append(c)
        # urządzenia bez aktywnego połączenia (np. odłączona karta Wi-Fi)
        for d in devs.values():
            if d["device"] in used_devices:
                continue
            if d["type"] in ("ethernet", "wifi"):
                kind = "lan" if d["type"] == "ethernet" else "wifi"
                if kind == "lan" and any(c["device"] == "" and c["type"] in WIRED for c in groups["lan"]):
                    continue
                groups[kind].append({"name": plain("nc_wireless_conn") if kind == "wifi" else plain("nc_local_conn"),
                                     "uuid": "", "type": d["type"], "device": d["device"], "state": d["state"],
                                     "active": False, "autoconnect": True})
        titles = {"lan": plain("nc_lan"), "wifi": plain("nc_wireless"), "vpn": plain("nc_vpn"), "other": plain("nc_other")}
        for kind in ("lan", "wifi", "vpn", "other"):
            if not groups[kind]:
                continue
            items.append(header(titles[kind]))
            for c in groups[kind]:
                info = c["device"] or plain("nc_no_device")
                ic = "network_wireless" if kind == "wifi" else "network_conn"
                it = entry(c["name"], ic, _state_text(c["state"]), info, key=(c["uuid"] or c["device"]), conn=c,
                           details=[_state_text(c["state"]), info])
                items.append(it)
        return items

    def fill_tasks(self, pane, sel):
        s = pane.add_section(plain("nc_tasks"), special=True)
        s.add_link("wizard", plain("nc_create"), self.create)
        if any(d["type"] == "wifi" for d in netman.devices()):
            s.add_link("network_wireless", plain("nc_view_wifi"), lambda: launcher.start_builtin("control", ["wifi"]))
        if sel:
            c = sel[0].extra["conn"]
            if c["state"].startswith("connected"):
                s.add_link("delete", plain("nc_disable_dev"), lambda: self.toggle(c, False))
                s.add_link("refresh", plain("nc_repair"), lambda: self.repair(c))
            else:
                s.add_link("refresh", plain("nc_enable_dev"), lambda: self.toggle(c, True))
            if c.get("uuid"):
                s.add_link("rename", plain("nc_rename"), lambda: self.rename(c))
            s.add_link("info", plain("nc_view_status"), lambda: self.status_dialog(c))
            if c.get("uuid"):
                s.add_link("properties", plain("nc_change_settings"), lambda: self.properties(c))
        self.other_places(pane)
        self.details(pane, sel)

    def activate(self, it):
        c = it.extra["conn"]
        if c["type"] in WIFI and not c.get("active"):
            launcher.start_builtin("control", ["wifi"])
        else:
            self.status_dialog(c)

    def item_menu(self, m, it):
        c = it.extra["conn"]
        if c["state"].startswith("connected"):
            m.addAction(tr("nc_disable"), lambda: self.toggle(c, False))
        else:
            m.addAction(tr("nc_enable"), lambda: self.toggle(c, True))
        m.addAction(tr("nc_status"), lambda: self.status_dialog(c))
        if c["state"].startswith("connected"):
            m.addAction(tr("nc_repair_m"), lambda: self.repair(c))
        if c["type"] in WIFI:
            m.addAction(tr("nc_view_wifi_m"), lambda: launcher.start_builtin("control", ["wifi"]))
        m.addSeparator()
        if c.get("uuid"):
            m.addAction(tr("delete"), lambda: self.delete(c))
            m.addAction(tr("rename"), lambda: self.rename(c))
            m.addSeparator()
            m.addAction(tr("properties"), lambda: self.properties(c))

    def toggle(self, c, on):
        if c["type"] in WIFI and on and not c.get("uuid"):
            launcher.start_builtin("control", ["wifi"])
            return
        if c.get("uuid"):
            rc, out, err = netman.con_up(c["uuid"]) if on else netman.con_down(c["uuid"])
        else:
            rc, out, err = netman.nmcli(["device", "connect" if on else "disconnect", c["device"]], 60)
        if rc != 0:
            dialogs.message(self, plain("network_conn"), (err or out).strip(), "error")
        QTimer.singleShot(600, self.refresh)

    def repair(self, c):
        """Jak „Napraw” w klasycznym systemie: odnowienie adresu i ponowne połączenie."""
        if c.get("device"):
            netman.nmcli(["device", "reapply", c["device"]], 30)
        if c.get("uuid"):
            rc, out, err = netman.con_up(c["uuid"])
        else:
            rc, out, err = netman.nmcli(["device", "connect", c["device"]], 60)
        if rc == 0:
            dialogs.message(self, plain("nc_repair_title"), tr("nc_repair_ok", c["name"]), "info")
        else:
            dialogs.message(self, plain("nc_repair_title"), (err or out).strip(), "error")
        self.refresh()

    def rename(self, c):
        new = dialogs.ask_text(self, plain("rename").replace("&", ""), plain("nc_new_name"), c["name"], "network_conn")
        if new and new != c["name"]:
            rc, out, err = netman.con_rename(c["uuid"], new)
            if rc != 0:
                dialogs.message(self, plain("network_conn"), (err or out).strip(), "error")
            self.refresh()

    def delete(self, c):
        if dialogs.message(self, plain("network_conn"), tr("nc_delete_q", c["name"]), "question", ("yes", "no")) == "yes":
            rc, out, err = netman.con_delete(c["uuid"])
            if rc != 0:
                dialogs.message(self, plain("network_conn"), (err or out).strip(), "error")
            self.refresh()

    def status_dialog(self, c):
        d = HDialog(tr("nc_status_title", c["name"]), "network_conn", self)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        g = QGroupBox(plain("nc_connection"))
        gl = QGridLayout(g)
        info = netman.device_ip(c["device"]) if c.get("device") else {}
        rows = [(plain("tm_status"), _state_text(c["state"])), (plain("nc_device"), c.get("device") or "—"),
                (plain("nc_ip_label"), info.get("IP4.ADDRESS", "—")),
                (plain("nc_gateway"), info.get("IP4.GATEWAY", "—") or "—"),
                (plain("nc_dns"), info.get("IP4.DNS", "—")),
                (plain("nc_mac"), info.get("GENERAL.HWADDR", "—"))]
        try:
            import psutil
            st = psutil.net_if_stats().get(c["device"])
            if st:
                rows.append((plain("tm_link_speed"), f"{st.speed} Mb/s" if st.speed > 0 else "—"))
            io = psutil.net_io_counters(pernic=True).get(c["device"])
            if io:
                rows.append((plain("tm_bytes_sent"), sysctl.group_digits(io.bytes_sent)))
                rows.append((plain("tm_bytes_recv"), sysctl.group_digits(io.bytes_recv)))
        except Exception:
            pass
        for i, (k, v) in enumerate(rows):
            gl.addWidget(QLabel(k + ":"), i, 0)
            gl.addWidget(QLabel(v), i, 1)
        lay.addWidget(g)
        row = QHBoxLayout()
        if c.get("uuid"):
            pb = QPushButton(plain("properties").replace("&", ""))
            pb.clicked.connect(lambda: (d.accept(), self.properties(c)))
            row.addWidget(pb)
        on = c["state"].startswith("connected")
        tb = QPushButton(plain("nc_disable").replace("&", "") if on else plain("nc_enable").replace("&", ""))
        tb.clicked.connect(lambda: (d.accept(), self.toggle(c, not on)))
        row.addWidget(tb)
        row.addStretch(1)
        b = QPushButton(plain("close"))
        b.clicked.connect(d.accept)
        row.addWidget(b)
        lay.addLayout(row)
        d.setFixedWidth(380)
        d.exec()

    def create(self):
        w = NewConnectionWizard(self)
        if w.start():
            QTimer.singleShot(500, self.refresh)

    def properties(self, c=None):
        if c is None:
            sel = self.selected()
            if not sel:
                return
            c = sel[0].extra["conn"]
        if not c.get("uuid"):
            return
        ConnectionProperties(c, self).exec()
        QTimer.singleShot(300, self.refresh)


# ================================================================ właściwości połączenia
IP_FIELDS = ["connection.id", "connection.autoconnect", "connection.interface-name",
             "ipv4.method", "ipv4.addresses", "ipv4.gateway", "ipv4.dns", "ipv4.ignore-auto-dns",
             "ipv6.method", "802-11-wireless.ssid", "802-11-wireless-security.key-mgmt",
             "802-11-wireless-security.psk", "connection.type"]


class IPv4Dialog(HDialog):
    def __init__(self, s, parent=None):
        super().__init__(plain("nc_ipv4_props"), "network_conn", parent)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(_wrap(plain("nc_ipv4_desc")))
        self.auto = QRadioButton(plain("nc_ip_auto"))
        self.manual = QRadioButton(plain("nc_ip_manual"))
        lay.addWidget(self.auto)
        g = QGroupBox()
        gl = QFormLayout(g)
        self.ip = QLineEdit()
        self.mask = QLineEdit()
        self.gw = QLineEdit()
        gl.addRow(plain("nc_ip_label") + ":", self.ip)
        gl.addRow(plain("nc_mask") + ":", self.mask)
        gl.addRow(plain("nc_gateway") + ":", self.gw)
        lay.addWidget(self.manual)
        lay.addWidget(g)
        self.dns_auto = QRadioButton(plain("nc_dns_auto"))
        self.dns_manual = QRadioButton(plain("nc_dns_manual"))
        g2 = QGroupBox()
        gl2 = QFormLayout(g2)
        self.dns1 = QLineEdit()
        self.dns2 = QLineEdit()
        gl2.addRow(plain("nc_dns1"), self.dns1)
        gl2.addRow(plain("nc_dns2"), self.dns2)
        lay.addWidget(self.dns_auto)
        lay.addWidget(self.dns_manual)
        lay.addWidget(g2)
        bg = QButtonGroup(self)
        bg.addButton(self.auto)
        bg.addButton(self.manual)
        bg2 = QButtonGroup(self)
        bg2.addButton(self.dns_auto)
        bg2.addButton(self.dns_manual)
        method = s.get("ipv4.method", "auto")
        (self.manual if method == "manual" else self.auto).setChecked(True)
        addr = (s.get("ipv4.addresses") or "").split(",")[0].strip()
        if "/" in addr:
            ip, pre = addr.split("/", 1)
            self.ip.setText(ip)
            self.mask.setText(_prefix_to_mask(int(pre)))
        self.gw.setText(s.get("ipv4.gateway", "") if s.get("ipv4.gateway") not in ("--",) else "")
        dns = [x for x in (s.get("ipv4.dns") or "").replace(" ", "").split(",") if x and x != "--"]
        (self.dns_manual if dns else self.dns_auto).setChecked(True)
        if dns:
            self.dns1.setText(dns[0])
            if len(dns) > 1:
                self.dns2.setText(dns[1])
        for w in (self.auto, self.manual, self.dns_auto, self.dns_manual):
            w.toggled.connect(self._enable)
        self._enable()
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.clicked.connect(self._ok)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        self.setFixedWidth(400)
        self.result_settings = None

    def _enable(self):
        man = self.manual.isChecked()
        for w in (self.ip, self.mask, self.gw):
            w.setEnabled(man)
        if man:
            self.dns_manual.setChecked(True)
        self.dns_auto.setEnabled(not man)
        for w in (self.dns1, self.dns2):
            w.setEnabled(self.dns_manual.isChecked())

    def _ok(self):
        st = {}
        if self.manual.isChecked():
            try:
                pre = _mask_to_prefix(self.mask.text().strip() or "255.255.255.0")
            except ValueError:
                dialogs.message(self, plain("nc_ipv4_props"), plain("nc_bad_mask"), "warning")
                return
            if not _valid_ip(self.ip.text().strip()):
                dialogs.message(self, plain("nc_ipv4_props"), plain("nc_bad_ip"), "warning")
                return
            st["ipv4.method"] = "manual"
            st["ipv4.addresses"] = f"{self.ip.text().strip()}/{pre}"
            st["ipv4.gateway"] = self.gw.text().strip()
        else:
            st["ipv4.method"] = "auto"
            st["ipv4.addresses"] = ""
            st["ipv4.gateway"] = ""
        dns = [x.text().strip() for x in (self.dns1, self.dns2) if x.text().strip()]
        if self.dns_manual.isChecked() and dns:
            st["ipv4.dns"] = ",".join(dns)
            st["ipv4.ignore-auto-dns"] = "yes"
        else:
            st["ipv4.dns"] = ""
            st["ipv4.ignore-auto-dns"] = "no"
        self.result_settings = st
        self.accept()


def _wrap(t):
    l = QLabel(t)
    l.setWordWrap(True)
    return l


def _valid_ip(s):
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _mask_to_prefix(mask):
    if mask.isdigit():
        n = int(mask)
        if 0 <= n <= 32:
            return n
        raise ValueError
    if not _valid_ip(mask):
        raise ValueError
    bits = "".join(f"{int(p):08b}" for p in mask.split("."))
    if "01" in bits:
        raise ValueError
    return bits.count("1")


def _prefix_to_mask(pre):
    bits = ("1" * pre).ljust(32, "0")
    return ".".join(str(int(bits[i:i + 8], 2)) for i in range(0, 32, 8))


class ConnectionProperties(AppletDialog):
    def __init__(self, c, parent=None):
        super().__init__(tr("nc_props_title", c["name"]), "network_conn", parent)
        self.c = c
        self.s = netman.con_settings(c["uuid"], IP_FIELDS)
        self.pending = {}
        w, lay = self.add_tab(plain("general"))
        lay.addWidget(QLabel(plain("nc_connect_using")))
        dev = QLineEdit(c.get("device") or self.s.get("connection.interface-name") or plain("nc_any_device"))
        dev.setReadOnly(True)
        lay.addWidget(dev)
        lay.addWidget(QLabel(plain("nc_components")))
        self.comp = QListWidget()
        for key, icon in (("nc_ipv4", "network_conn"), ("nc_ipv6", "network_conn")):
            it = QListWidgetItem(iconcache.icon(icon), plain(key))
            self.comp.addItem(it)
        self.comp.setCurrentRow(0)
        self.comp.setMaximumHeight(90)
        lay.addWidget(self.comp)
        row = QHBoxLayout()
        row.addStretch(1)
        pb = QPushButton(plain("properties").replace("&", ""))
        pb.clicked.connect(self._comp_props)
        row.addWidget(pb)
        lay.addLayout(row)
        self.desc = _wrap(plain("nc_ipv4_about"))
        g = QGroupBox(plain("description"))
        QVBoxLayout(g).addWidget(self.desc)
        lay.addWidget(g)
        self.auto = QCheckBox(plain("nc_autoconnect"))
        self.auto.setChecked(self.s.get("connection.autoconnect", "yes") == "yes")
        self.auto.toggled.connect(self.changed)
        lay.addWidget(self.auto)
        lay.addStretch(1)
        if c["type"] in WIFI:
            w2, l2 = self.add_tab(plain("nc_security_tab"))
            l2.addWidget(QLabel(plain("wifi_ssid") + " " + (self.s.get("802-11-wireless.ssid") or c["name"])))
            g2 = QGroupBox(plain("wifi_security"))
            gl = QFormLayout(g2)
            km = self.s.get("802-11-wireless-security.key-mgmt", "")
            gl.addRow(plain("nc_sec_type"), QLabel({"wpa-psk": "WPA2-Personal", "sae": "WPA3-Personal", "none": "WEP",
                                                    "wpa-eap": "WPA-Enterprise"}.get(km, km or plain("wifi_sec_none"))))
            self.psk = QLineEdit(self.s.get("802-11-wireless-security.psk", ""))
            self.psk.setEchoMode(QLineEdit.Password)
            self.psk.textEdited.connect(self.changed)
            gl.addRow(plain("wifi_key"), self.psk)
            show = QCheckBox(plain("wifi_show_chars"))
            show.toggled.connect(lambda on: self.psk.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
            gl.addRow("", show)
            l2.addWidget(g2)
            l2.addStretch(1)
        self.comp.currentRowChanged.connect(lambda r: self.desc.setText(plain("nc_ipv4_about" if r == 0 else "nc_ipv6_about")))
        self.resize(400, 460)

    def _comp_props(self):
        if self.comp.currentRow() == 0:
            d = IPv4Dialog(dict(self.s, **self.pending), self)
            if d.exec() and d.result_settings:
                self.pending.update(d.result_settings)
                self.changed()
        else:
            d = HDialog(plain("nc_ipv6"), "network_conn", self)
            lay = QVBoxLayout(d.body())
            lay.setContentsMargins(12, 12, 12, 12)
            cb = QComboBox()
            opts = [("auto", "nc_ipv6_auto"), ("disabled", "nc_ipv6_off"), ("ignore", "nc_ipv6_ignore")]
            for v, k in opts:
                cb.addItem(plain(k), v)
            cur = self.pending.get("ipv6.method", self.s.get("ipv6.method", "auto"))
            i = cb.findData(cur)
            cb.setCurrentIndex(i if i >= 0 else 0)
            lay.addWidget(QLabel(plain("nc_ipv6_method")))
            lay.addWidget(cb)
            row = QHBoxLayout()
            row.addStretch(1)
            ok = QPushButton(plain("ok"))
            ok.clicked.connect(d.accept)
            row.addWidget(ok)
            lay.addLayout(row)
            d.setFixedWidth(340)
            if d.exec():
                self.pending["ipv6.method"] = cb.currentData()
                self.changed()

    def apply(self):
        st = dict(self.pending)
        st["connection.autoconnect"] = "yes" if self.auto.isChecked() else "no"
        if hasattr(self, "psk") and self.psk.text() != self.s.get("802-11-wireless-security.psk", ""):
            st["802-11-wireless-security.psk"] = self.psk.text()
        rc, out, err = netman.con_modify(self.c["uuid"], st)
        if rc != 0:
            dialogs.message(self, plain("network_conn"), (err or out).strip(), "error")
            return False
        if self.c.get("active") and any(k.startswith("ipv") for k in st):
            if dialogs.message(self, plain("network_conn"), plain("nc_reconnect_q"), "question", ("yes", "no")) == "yes":
                netman.con_up(self.c["uuid"])
        self.pending = {}
        return True


# ================================================================ kreator
class NewConnectionWizard(Wizard):
    def __init__(self, parent=None):
        super().__init__(plain("ncw_title"), "wizard", parent)
        # 0 powitanie
        p = WizardPage(plain("ncw_welcome"), exterior=True)
        p.lay.addWidget(_wrap(plain("ncw_welcome_desc")))
        for k in ("ncw_w1", "ncw_w2", "ncw_w3"):
            p.lay.addWidget(_wrap("•  " + plain(k)))
        p.lay.addSpacing(20)
        p.lay.addWidget(_wrap(plain("ncw_continue")))
        self.add_page(p)
        # 1 typ połączenia
        p = WizardPage(plain("ncw_type"), plain("ncw_type_sub"))
        self.t_internet = QRadioButton(plain("ncw_t_internet"))
        self.t_wifi = QRadioButton(plain("ncw_t_wifi"))
        self.t_vpn = QRadioButton(plain("ncw_t_vpn"))
        self.t_internet.setChecked(True)
        for rb, desc in ((self.t_internet, "ncw_t_internet_d"), (self.t_wifi, "ncw_t_wifi_d"), (self.t_vpn, "ncw_t_vpn_d")):
            f = rb.font()
            f.setBold(True)
            rb.setFont(f)
            p.lay.addWidget(rb)
            d = _wrap(plain(desc))
            d.setContentsMargins(22, 0, 0, 8)
            p.lay.addWidget(d)
        p.next_id = lambda wz: 2 if self.t_internet.isChecked() else 5 if self.t_vpn.isChecked() else 7
        self.add_page(p)
        # 2 sposób połączenia z Internetem
        p = WizardPage(plain("ncw_how"), plain("ncw_how_sub"))
        self.h_cable = QRadioButton(plain("ncw_h_cable"))
        self.h_pppoe = QRadioButton(plain("ncw_h_pppoe"))
        self.h_cable.setChecked(True)
        for rb, desc in ((self.h_cable, "ncw_h_cable_d"), (self.h_pppoe, "ncw_h_pppoe_d")):
            f = rb.font()
            f.setBold(True)
            rb.setFont(f)
            p.lay.addWidget(rb)
            d = _wrap(plain(desc))
            d.setContentsMargins(22, 0, 0, 8)
            p.lay.addWidget(d)
        p.next_id = lambda wz: 3 if self.h_cable.isChecked() else 4
        self.add_page(p)
        # 3 kabel — adres
        p = WizardPage(plain("ncw_cable"), plain("ncw_cable_sub"))
        self.c_dev = QComboBox()
        for d in netman.devices():
            if d["type"] == "ethernet":
                self.c_dev.addItem(iconcache.icon("network_conn"), d["device"], d["device"])
        p.lay.addWidget(QLabel(plain("nc_connect_using")))
        p.lay.addWidget(self.c_dev)
        self.c_auto = QRadioButton(plain("nc_ip_auto"))
        self.c_manual = QRadioButton(plain("nc_ip_manual"))
        self.c_auto.setChecked(True)
        p.lay.addWidget(self.c_auto)
        p.lay.addWidget(self.c_manual)
        form = QFormLayout()
        self.c_ip, self.c_mask, self.c_gw, self.c_dns = QLineEdit(), QLineEdit("255.255.255.0"), QLineEdit(), QLineEdit()
        form.addRow(plain("nc_ip_label") + ":", self.c_ip)
        form.addRow(plain("nc_mask") + ":", self.c_mask)
        form.addRow(plain("nc_gateway") + ":", self.c_gw)
        form.addRow(plain("nc_dns1"), self.c_dns)
        p.lay.addLayout(form)

        def en():
            for w in (self.c_ip, self.c_mask, self.c_gw, self.c_dns):
                w.setEnabled(self.c_manual.isChecked())
        self.c_manual.toggled.connect(en)
        en()

        def val(wz):
            if self.c_dev.count() == 0:
                dialogs.message(wz, plain("ncw_title"), plain("ncw_no_ethernet"), "warning")
                return False
            if self.c_manual.isChecked():
                try:
                    _mask_to_prefix(self.c_mask.text().strip())
                except ValueError:
                    dialogs.message(wz, plain("ncw_title"), plain("nc_bad_mask"), "warning")
                    return False
                if not _valid_ip(self.c_ip.text().strip()):
                    dialogs.message(wz, plain("ncw_title"), plain("nc_bad_ip"), "warning")
                    return False
            wz.data["kind"] = "ethernet"
            return True
        p.validate = val
        p.next_id = lambda wz: 6
        self.add_page(p)
        # 4 PPPoE
        p = WizardPage(plain("ncw_pppoe"), plain("ncw_pppoe_sub"))
        form = QFormLayout()
        self.p_dev = QComboBox()
        for d in netman.devices():
            if d["type"] == "ethernet":
                self.p_dev.addItem(d["device"], d["device"])
        self.p_user, self.p_pw, self.p_pw2 = QLineEdit(), QLineEdit(), QLineEdit()
        self.p_pw.setEchoMode(QLineEdit.Password)
        self.p_pw2.setEchoMode(QLineEdit.Password)
        form.addRow(plain("nc_device") + ":", self.p_dev)
        form.addRow(plain("ncw_user"), self.p_user)
        form.addRow(plain("auth_password"), self.p_pw)
        form.addRow(plain("ncw_pw_confirm"), self.p_pw2)
        p.lay.addLayout(form)

        def valp(wz):
            if not self.p_user.text().strip():
                return False
            if self.p_pw.text() != self.p_pw2.text():
                dialogs.message(wz, plain("ncw_title"), plain("wifi_key_mismatch"), "warning")
                return False
            wz.data["kind"] = "pppoe"
            return True
        p.validate = valp
        p.next_id = lambda wz: 6
        self.add_page(p)
        # 5 VPN — import pliku
        p = WizardPage(plain("ncw_vpn"), plain("ncw_vpn_sub"))
        p.lay.addWidget(_wrap(plain("ncw_vpn_desc")))
        row = QHBoxLayout()
        self.v_file = QLineEdit()
        row.addWidget(self.v_file, 1)
        bb = QPushButton(plain("browse"))
        bb.clicked.connect(self._browse_vpn)
        row.addWidget(bb)
        p.lay.addLayout(row)
        self.v_type = QComboBox()
        self.v_type.addItem("OpenVPN (.ovpn)", "openvpn")
        self.v_type.addItem("WireGuard (.conf)", "wireguard")
        p.lay.addWidget(QLabel(plain("ncw_vpn_type")))
        p.lay.addWidget(self.v_type)

        def valv(wz):
            if not os.path.isfile(self.v_file.text()):
                dialogs.message(wz, plain("ncw_title"), plain("ncw_vpn_nofile"), "warning")
                return False
            wz.data["kind"] = "vpn"
            return True
        p.validate = valv
        p.next_id = lambda wz: 6
        self.add_page(p)
        # 6 nazwa połączenia
        p = WizardPage(plain("ncw_name"), plain("ncw_name_sub"))
        p.lay.addWidget(QLabel(plain("ncw_name_label")))
        self.name = QLineEdit()
        p.lay.addWidget(self.name)
        p.lay.addWidget(_wrap(plain("ncw_name_hint")))

        def enter_name(wz):
            if not self.name.text():
                k = wz.data.get("kind")
                self.name.setText({"pppoe": plain("ncw_name_pppoe"), "vpn": os.path.splitext(os.path.basename(self.v_file.text()))[0]}
                                  .get(k, plain("nc_local_conn")))
        p.on_enter = enter_name
        p.validate = self._create
        p.next_id = lambda wz: 8
        self.add_page(p)
        # 7 sieć bezprzewodowa
        p = WizardPage(plain("ncw_t_wifi"), plain("ncw_wifi_sub"))
        p.lay.addWidget(_wrap(plain("ncw_wifi_desc")))
        ob = QPushButton(plain("nc_view_wifi"))
        ob.clicked.connect(lambda: launcher.start_builtin("control", ["wifi"]))
        p.lay.addWidget(ob)
        p.final = True
        self.add_page(p)
        # 8 zakończenie
        p = WizardPage(plain("ncw_done"), exterior=True)
        self.done_lbl = _wrap("")
        p.lay.addWidget(self.done_lbl)
        p.lay.addSpacing(20)
        p.lay.addWidget(_wrap(plain("ncw_done_close")))
        p.final = True
        self.add_page(p)
        self.resize(560, 420)

    def _browse_vpn(self):
        fn = dialogs.open_file(self, plain("ncw_vpn"), os.path.expanduser("~"), "VPN (*.ovpn *.conf)")
        if fn:
            self.v_file.setText(fn)
            self.v_type.setCurrentIndex(0 if fn.endswith(".ovpn") else 1)

    def _create(self, wz):
        name = self.name.text().strip()
        if not name:
            return False
        k = self.data.get("kind")
        if k == "ethernet":
            args = ["connection", "add", "type", "ethernet", "con-name", name, "ifname", self.c_dev.currentData()]
            if self.c_manual.isChecked():
                pre = _mask_to_prefix(self.c_mask.text().strip())
                args += ["ipv4.method", "manual", "ipv4.addresses", f"{self.c_ip.text().strip()}/{pre}"]
                if self.c_gw.text().strip():
                    args += ["ipv4.gateway", self.c_gw.text().strip()]
                if self.c_dns.text().strip():
                    args += ["ipv4.dns", self.c_dns.text().strip()]
        elif k == "pppoe":
            args = ["connection", "add", "type", "pppoe", "con-name", name, "ifname", self.p_dev.currentData() or "*",
                    "pppoe.username", self.p_user.text().strip(), "pppoe.password", self.p_pw.text()]
        else:
            args = ["connection", "import", "type", self.v_type.currentData(), "file", self.v_file.text()]
        rc, out, err = netman.nmcli(args, 60)
        if rc != 0:
            msg = (err or out).strip()
            if k == "vpn" and "plugin" in msg.lower():
                msg += "\n\n" + plain("ncw_vpn_plugin")
            dialogs.message(self, plain("ncw_title"), msg, "error")
            return False
        if k == "vpn":
            # nazwa nadana przez import — zmieniamy na wybraną
            for c in netman.connections():
                if c["name"] == os.path.splitext(os.path.basename(self.v_file.text()))[0] and c["name"] != name:
                    netman.con_rename(c["uuid"], name)
        self.done_lbl.setText(tr("ncw_done_desc", name))
        return True


def open_network(page=None, parent=None):
    w = NetworkWindow()
    if page == "new":
        QTimer.singleShot(200, w.create)
    return w
