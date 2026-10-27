"""Menedżer urządzeń w klasycznym układzie: drzewo kategorii, właściwości (Ogólne / Sterownik / Szczegóły),
widok według typu lub według połączenia, wykrywanie urządzeń bez sterownika. Dane z /sys, /proc, lspci i lsusb."""
import glob
import os
import platform
import re
import shutil
import subprocess

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QMenuBar,
                               QPlainTextEdit, QPushButton, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ...common.appkit import T, act, help_menu
from ...common.window import HDialog, HWindow
from ...theme import iconcache

# kategoria: (nazwa pl, nazwa en, ikona)
CATS = {
    "battery": ("Baterie", "Batteries", "tray_battery"),
    "bluetooth": ("Radiowe urządzenia Bluetooth", "Bluetooth Radios", "bluetooth"),
    "computer": ("Komputer", "Computer", "computer"),
    "disk": ("Napędy dysków", "Disk drives", "drive_hdd"),
    "display": ("Karty graficzne", "Display adapters", "display"),
    "cdrom": ("Napędy DVD/CD-ROM", "DVD/CD-ROM drives", "drive_cd"),
    "hid": ("Urządzenia interfejsu HID", "Human Interface Devices", "keyboard"),
    "storage": ("Kontrolery magazynu", "Storage controllers", "drive_system"),
    "imaging": ("Urządzenia przetwarzania obrazów", "Imaging devices", "pictures"),
    "keyboard": ("Klawiatury", "Keyboards", "keyboard"),
    "monitor": ("Monitory", "Monitors", "display"),
    "mouse": ("Mysz i inne urządzenia wskazujące", "Mice and other pointing devices", "mouse"),
    "network": ("Karty sieciowe", "Network adapters", "network_conn"),
    "ports": ("Porty (COM i LPT)", "Ports (COM & LPT)", "printer"),
    "cpu": ("Procesory", "Processors", "system"),
    "sound": ("Kontrolery dźwięku, wideo i gier", "Sound, video and game controllers", "sound"),
    "system": ("Urządzenia systemowe", "System devices", "admin"),
    "usb": ("Kontrolery uniwersalnej magistrali szeregowej", "Universal Serial Bus controllers", "drive_usb"),
    "usbdev": ("Urządzenia USB", "USB devices", "drive_usb"),
    "memory": ("Czytniki kart pamięci", "Memory technology devices", "drive_usb"),
    "other": ("Inne urządzenia", "Other devices", "question"),
}


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def _driver_of(syspath):
    link = os.path.join(syspath, "driver")
    if os.path.islink(link):
        return os.path.basename(os.readlink(link))
    return ""


def _module_of(syspath):
    link = os.path.join(syspath, "driver", "module")
    if os.path.islink(link):
        return os.path.basename(os.readlink(link))
    return ""


class Device:
    def __init__(self, cat, name, syspath="", vendor="", location="", driver=None, ids=(), extra=None, needs_driver=True):
        self.cat = cat
        self.name = name
        self.syspath = os.path.realpath(syspath) if syspath else ""
        self.vendor = vendor
        self.location = location
        self.driver = _driver_of(syspath) if driver is None and syspath else (driver or "")
        self.module = _module_of(syspath) if syspath else ""
        self.ids = list(ids)
        self.extra = extra or {}
        self.needs_driver = needs_driver

    @property
    def problem(self):
        return self.needs_driver and not self.driver


# ---------------------------------------------------------------------- zbieranie danych
def _pci_names():
    """slot -> (klasa, producent, urządzenie, sterownik) z lspci, jeśli jest."""
    out = {}
    if not shutil.which("lspci"):
        return out
    try:
        txt = subprocess.run(["lspci", "-vmmk"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return out
    for block in txt.strip().split("\n\n"):
        d = {}
        for line in block.splitlines():
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
        if "Slot" in d:
            out[d["Slot"]] = d
    return out


_PCI_IDS = None


def pci_ids_name(vendor, device):
    """Nazwy z bazy pci.ids (pakiet hwdata), gdy nie ma lspci."""
    global _PCI_IDS
    if _PCI_IDS is None:
        _PCI_IDS = {}
        for path in ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids", "/usr/share/pci.ids"):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    ven = None
                    for line in f:
                        if line.startswith("#") or not line.strip():
                            continue
                        if line.startswith("C "):
                            break
                        if not line.startswith("\t"):
                            ven = line[:4].lower()
                            _PCI_IDS[ven] = line[6:].strip()
                        elif not line.startswith("\t\t") and ven:
                            _PCI_IDS[ven + ":" + line[1:5].lower()] = line[7:].strip()
                break
            except OSError:
                continue
    v = vendor.lower().replace("0x", "")
    d = device.lower().replace("0x", "")
    return _PCI_IDS.get(v, ""), _PCI_IDS.get(v + ":" + d, "")


def _pci_cat(cls_hex):
    c = int(cls_hex, 16) >> 8 if cls_hex else 0
    base, sub = c >> 8, c & 0xFF
    if base == 0x03:
        return "display"
    if base == 0x02 or (base == 0x0D and sub in (0x11, 0x80)):
        return "network"
    if base == 0x04:
        return "sound"
    if base == 0x01:
        return "storage"
    if base == 0x0C and sub == 0x03:
        return "usb"
    if base == 0x0C and sub == 0x05:
        return "system"
    if base == 0x0D:
        return "bluetooth" if sub == 0x11 else "network"
    if base == 0x05 or base == 0x06 or base == 0x08 or base == 0x11 or base == 0x0B:
        return "system"
    if base == 0x0C:
        return "system"
    if base == 0xFF or base == 0x00:
        return "other"
    return "system"


def collect():
    devs = []
    # komputer
    product = _read("/sys/class/dmi/id/product_name")
    vendor = _read("/sys/class/dmi/id/sys_vendor")
    arch = platform.machine()
    devs.append(Device("computer", T(f"Komputer z procesorem {arch} (ACPI)", f"ACPI {arch}-based PC"), "/sys/class/dmi/id",
                       vendor=vendor, location=product, driver="acpi", needs_driver=False,
                       extra={T("Model", "Model"): product, "BIOS": _read("/sys/class/dmi/id/bios_version")}))
    # procesory
    names = re.findall(r"^model name\s*:\s*(.+)$", _read("/proc/cpuinfo"), re.M)
    for i, n in enumerate(names or [platform.processor() or "CPU"] * (os.cpu_count() or 1)):
        p = f"/sys/devices/system/cpu/cpu{i}"
        devs.append(Device("cpu", re.sub(r"\s+", " ", n), p, driver="processor", needs_driver=False,
                           location=T(f"Procesor {i}", f"Processor {i}")))
    # PCI
    names = _pci_names()
    for p in sorted(glob.glob("/sys/bus/pci/devices/*")):
        slot = os.path.basename(p)
        cls = _read(os.path.join(p, "class"))
        info = names.get(slot) or names.get(slot.split(":", 1)[-1]) or {}
        cat = _pci_cat(cls)
        vname, dname = ("", "")
        if not info:
            vname, dname = pci_ids_name(_read(os.path.join(p, "vendor")), _read(os.path.join(p, "device")))
            info = {"Vendor": vname, "Device": dname, "Class": cls} if dname else {}
        name = info.get("Device") or f"PCI {_read(os.path.join(p, 'vendor'))}:{_read(os.path.join(p, 'device'))}"
        bus, dev = slot.split(":")[1], slot.split(":")[2]
        loc = T(f"Magistrala PCI {int(bus, 16)}, urządzenie {int(dev.split('.')[0], 16)}, funkcja {dev.split('.')[1]}",
                f"PCI bus {int(bus, 16)}, device {int(dev.split('.')[0], 16)}, function {dev.split('.')[1]}")
        ids = [f"PCI\\VEN_{_read(os.path.join(p, 'vendor'))[2:].upper()}&DEV_{_read(os.path.join(p, 'device'))[2:].upper()}"
               f"&SUBSYS_{_read(os.path.join(p, 'subsystem_device'))[2:].upper()}{_read(os.path.join(p, 'subsystem_vendor'))[2:].upper()}"]
        # mostki i kontrolery hosta nie potrzebują sterownika
        needs = cat not in ("system",) or bool(info.get("Driver"))
        devs.append(Device(cat, name, p, vendor=info.get("Vendor", ""), location=loc, ids=ids,
                           extra={T("Klasa", "Class"): info.get("Class", cls), "Modalias": _read(os.path.join(p, "modalias"))},
                           needs_driver=needs and cat != "system"))
    # USB
    for p in sorted(glob.glob("/sys/bus/usb/devices/*")):
        b = os.path.basename(p)
        if ":" in b:
            continue
        prod = _read(os.path.join(p, "product"))
        manu = _read(os.path.join(p, "manufacturer"))
        vid, pid = _read(os.path.join(p, "idVendor")), _read(os.path.join(p, "idProduct"))
        if b.startswith("usb"):
            devs.append(Device("usb", T("Główny koncentrator USB", "USB Root Hub") + f" ({prod})" if prod else
                               T("Główny koncentrator USB", "USB Root Hub"), p, vendor=manu, location=b,
                               ids=[f"USB\\ROOT_HUB&VID{vid}&PID{pid}"]))
            continue
        classes = set()
        drivers = []
        for itf in glob.glob(p + "/" + b + ":*"):
            classes.add(_read(os.path.join(itf, "bInterfaceClass")))
            d = _driver_of(itf)
            if d:
                drivers.append(d)
        dcls = _read(os.path.join(p, "bDeviceClass"))
        if dcls == "09":
            cat = "usb"
            name = T("Koncentrator USB", "USB Hub") + (f" ({prod})" if prod else "")
        elif "e0" in classes:
            cat = "bluetooth"
            name = prod or T("Adapter Bluetooth USB", "USB Bluetooth adapter")
        elif "0e" in classes:
            cat = "imaging"
            name = prod or T("Kamera USB", "USB camera")
        elif "08" in classes:
            cat = "memory"
            name = prod or T("Urządzenie pamięci masowej USB", "USB Mass Storage Device")
        elif "01" in classes:
            cat = "sound"
            name = prod or T("Urządzenie audio USB", "USB Audio Device")
        elif "03" in classes:
            cat = "hid"
            name = prod or T("Urządzenie HID USB", "USB Input Device")
        elif "02" in classes or "0a" in classes:
            cat = "network" if "net" in " ".join(drivers) or "cdc_ether" in drivers else "ports"
            name = prod or T("Urządzenie komunikacyjne USB", "USB communications device")
        else:
            cat = "usbdev"
            name = prod or f"USB {vid}:{pid}"
        dev = Device(cat, name, p, vendor=manu, location=T(f"Port {b}", f"Port {b}"),
                     driver=", ".join(sorted(set(drivers))) or _driver_of(p), ids=[f"USB\\VID_{vid.upper()}&PID_{pid.upper()}"],
                     extra={T("Szybkość", "Speed"): _read(os.path.join(p, "speed")) + " Mb/s",
                            T("Numer seryjny", "Serial number"): _read(os.path.join(p, "serial"))})
        dev.needs_driver = cat not in ("usbdev",)
        devs.append(dev)
    # dyski
    for p in sorted(glob.glob("/sys/block/*")):
        n = os.path.basename(p)
        if n.startswith(("loop", "ram", "zram", "dm-", "md")):
            continue
        model = _read(os.path.join(p, "device", "model")) or n
        if n.startswith("sr"):
            devs.append(Device("cdrom", model, os.path.join(p, "device"), location=f"/dev/{n}", needs_driver=False))
            continue
        try:
            size = int(_read(os.path.join(p, "size"), "0")) * 512
        except ValueError:
            size = 0
        sz = f"{size / 1e9:.0f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"
        devs.append(Device("disk", f"{model} ({sz})", os.path.join(p, "device"), vendor=_read(os.path.join(p, "device", "vendor")),
                           location=f"/dev/{n}", needs_driver=False,
                           extra={T("Rozmiar", "Size"): sz, T("Wymienny", "Removable"): _read(os.path.join(p, "removable"))}))
    # urządzenia wejścia
    txt = _read("/proc/bus/input/devices")
    for block in txt.split("\n\n"):
        name = re.search(r'N: Name="(.*)"', block)
        handlers = re.search(r"H: Handlers=(.*)", block)
        sysfs = re.search(r"S: Sysfs=(.*)", block)
        if not name or not handlers:
            continue
        h = handlers.group(1)
        n = name.group(1)
        path = "/sys" + sysfs.group(1) if sysfs else ""
        low = n.lower()
        if "kbd" in h and ("keyboard" in low or "klawiat" in low or re.search(r"\bkbd\b", low) or "at translated" in low):
            devs.append(Device("keyboard", n, path, driver="evdev", needs_driver=False))
        elif "mouse" in h:
            devs.append(Device("mouse", n, path, driver="evdev", needs_driver=False))
        elif any(k in low for k in ("button", "lid switch", "video bus", "hotkey", "wmi")):
            devs.append(Device("system", n, path, driver="evdev", needs_driver=False))
    # monitory (EDID)
    for p in sorted(glob.glob("/sys/class/drm/card*-*")):
        if _read(os.path.join(p, "status")) != "connected":
            continue
        name = _edid_name(os.path.join(p, "edid")) or T("Monitor Plug and Play", "Plug and Play Monitor")
        conn = os.path.basename(p).split("-", 1)[1]
        devs.append(Device("monitor", name, p, location=conn, driver="drm", needs_driver=False))
    # baterie i zasilacz
    for p in sorted(glob.glob("/sys/class/power_supply/*")):
        typ = _read(os.path.join(p, "type"))
        if typ == "Battery" and _read(os.path.join(p, "scope")) != "Device":
            model = _read(os.path.join(p, "model_name"))
            devs.append(Device("battery", T("Bateria", "Battery") + (f" {model}" if model else ""), p,
                               vendor=_read(os.path.join(p, "manufacturer")), driver="acpi", needs_driver=False,
                               extra={T("Pojemność", "Capacity"): _read(os.path.join(p, "capacity")) + " %",
                                      T("Technologia", "Technology"): _read(os.path.join(p, "technology"))}))
        elif typ == "Mains":
            devs.append(Device("battery", T("Zasilacz sieciowy", "AC Adapter"), p, driver="acpi", needs_driver=False))
    # porty szeregowe
    for p in sorted(glob.glob("/sys/class/tty/ttyS*") + glob.glob("/sys/class/tty/ttyUSB*") + glob.glob("/sys/class/tty/ttyACM*")):
        n = os.path.basename(p)
        if n.startswith("ttyS") and _read(os.path.join(p, "type"), "0") == "0":
            continue
        devs.append(Device("ports", T(f"Port komunikacyjny ({n})", f"Communications Port ({n})"), os.path.join(p, "device"),
                           location=f"/dev/{n}"))
    # dźwięk spoza PCI/USB (np. SoF) — gdy brak innych
    if not any(d.cat == "sound" for d in devs):
        for line in _read("/proc/asound/cards").splitlines():
            m = re.match(r"\s*\d+\s+\[.*\]:\s*(.*)", line)
            if m:
                devs.append(Device("sound", m.group(1).strip(), needs_driver=False, driver="snd"))
    return devs


def _edid_name(path):
    try:
        with open(path, "rb") as f:
            e = f.read()
    except OSError:
        return ""
    if len(e) < 128:
        return ""
    for off in (54, 72, 90, 108):
        blk = e[off:off + 18]
        if blk[:3] == b"\x00\x00\x00" and blk[3] == 0xFC:
            return blk[5:].split(b"\n")[0].decode("ascii", "replace").strip()
    return ""


def _overlay_problem(icon_name):
    pm = iconcache.pixmap(icon_name, 16).copy()
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#ffd400"))
    p.setPen(QColor("#7a5a00"))
    p.drawEllipse(7, 7, 9, 9)
    p.setPen(QColor("#000000"))
    f = p.font()
    f.setPixelSize(8)
    f.setBold(True)
    p.setFont(f)
    p.drawText(7, 7, 9, 9, Qt.AlignCenter, "!")
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------- właściwości
class DevicePropertiesDialog(HDialog):
    def __init__(self, dev, parent):
        super().__init__(T(f"Właściwości: {dev.name}", f"{dev.name} Properties"), CATS[dev.cat][2], parent)
        self.dev = dev
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        cat_name = T(*CATS[dev.cat][:2])
        # Ogólne
        w = QWidget()
        gl = QVBoxLayout(w)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap(CATS[dev.cat][2], 32))
        head.addWidget(ic)
        nm = QLabel(dev.name)
        nm.setWordWrap(True)
        head.addWidget(nm, 1)
        gl.addLayout(head)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        gl.addWidget(line)
        g = QGridLayout()
        for i, (k, v) in enumerate(((T("Typ urządzenia:", "Device type:"), cat_name),
                                    (T("Producent:", "Manufacturer:"), dev.vendor or T("(nieznany)", "(unknown)")),
                                    (T("Lokalizacja:", "Location:"), dev.location or "—"))):
            g.addWidget(QLabel(k), i, 0)
            lv = QLabel(v)
            lv.setWordWrap(True)
            lv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(lv, i, 1)
        g.setColumnStretch(1, 1)
        gl.addLayout(g)
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel(T("Stan urządzenia", "Device status")))
        st = QPlainTextEdit()
        st.setReadOnly(True)
        st.setMaximumHeight(80)
        if dev.problem:
            st.setPlainText(T("Sterowniki dla tego urządzenia nie są zainstalowane.\n\nAby znaleźć sterownik, sprawdź "
                              "Dodaj lub usuń programy → Składniki systemu albo zainstaluj pakiet firmware producenta.",
                              "The drivers for this device are not installed."))
        else:
            st.setPlainText(T("To urządzenie działa poprawnie.", "This device is working properly."))
        bl.addWidget(st)
        gl.addWidget(box)
        gl.addStretch(1)
        tabs.addTab(w, T("Ogólne", "General"))
        # Sterownik
        w2 = QWidget()
        g2 = QGridLayout(w2)
        ver = ""
        if dev.module and shutil.which("modinfo"):
            try:
                ver = subprocess.run(["modinfo", "-F", "version", dev.module], capture_output=True, text=True,
                                     timeout=3).stdout.strip()
            except Exception:
                ver = ""
        rows = [(T("Dostawca sterownika:", "Driver Provider:"), T("Jądro Linux", "Linux kernel") if dev.driver else "—"),
                (T("Sterownik:", "Driver:"), dev.driver or T("(brak)", "(none)")),
                (T("Moduł jądra:", "Kernel module:"), dev.module or T("(wbudowany)", "(built-in)") if dev.driver else "—"),
                (T("Wersja sterownika:", "Driver Version:"), ver or platform.release())]
        for i, (k, v) in enumerate(rows):
            g2.addWidget(QLabel(k), i, 0)
            g2.addWidget(QLabel(v), i, 1)
        det = QPushButton(T("&Szczegóły sterownika…", "Driver &Details..."))
        det.setEnabled(bool(dev.module) and bool(shutil.which("modinfo")))
        det.clicked.connect(self._driver_details)
        g2.addWidget(det, len(rows), 0, 1, 2, Qt.AlignLeft)
        g2.setRowStretch(len(rows) + 1, 1)
        g2.setColumnStretch(1, 1)
        tabs.addTab(w2, T("Sterownik", "Driver"))
        # Szczegóły
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        self.prop = QComboBox()
        self.values = QListWidget()
        props = {T("Identyfikatory sprzętu", "Hardware Ids"): dev.ids,
                 T("Ścieżka urządzenia (sysfs)", "Device instance path"): [dev.syspath] if dev.syspath else [],
                 T("Sterownik", "Driver"): [dev.driver] if dev.driver else []}
        for k, v in dev.extra.items():
            if v:
                props[k] = [v]
        self._props = props
        for k in props:
            self.prop.addItem(k)
        self.prop.currentTextChanged.connect(lambda k: (self.values.clear(), self.values.addItems(self._props.get(k, []))))
        l3.addWidget(self.prop)
        l3.addWidget(self.values, 1)
        self.values.addItems(props[self.prop.currentText()] if props else [])
        tabs.addTab(w3, T("Szczegóły", "Details"))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        self.resize(400, 440)

    def _driver_details(self):
        d = HDialog(T("Szczegóły pliku sterownika", "Driver File Details"), "system", self)
        lay = QVBoxLayout(d.body())
        t = QPlainTextEdit()
        t.setReadOnly(True)
        try:
            t.setPlainText(subprocess.run(["modinfo", self.dev.module], capture_output=True, text=True, timeout=3).stdout)
        except Exception as e:
            t.setPlainText(str(e))
        lay.addWidget(t)
        b = QPushButton(T("OK", "OK"))
        b.clicked.connect(d.accept)
        lay.addWidget(b, 0, Qt.AlignRight)
        d.resize(520, 380)
        d.exec()


# ---------------------------------------------------------------------- okno
class DeviceManager(HWindow):
    def __init__(self):
        super().__init__(T("Menedżer urządzeń", "Device Manager"), "system")
        self.view = "type"
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        mb = QMenuBar()
        lay.addWidget(mb)
        m = mb.addMenu(T("&Plik", "&File"))
        act(m, T("&Zakończ", "E&xit"), self.close)
        m = mb.addMenu(T("&Akcja", "&Action"))
        act(m, T("&Skanuj w poszukiwaniu zmian sprzętu", "Scan for &hardware changes"), self.refresh, "F5")
        m.addSeparator()
        self.a_props = act(m, T("&Właściwości", "P&roperties"), self.properties, "Alt+Return")
        m = mb.addMenu(T("&Widok", "&View"))
        self.a_type = act(m, T("Urządzenia według &typu", "Devices by &type"), lambda: self.set_view("type"))
        self.a_conn = act(m, T("Urządzenia według &połączenia", "Devices by &connection"), lambda: self.set_view("conn"))
        for a in (self.a_type, self.a_conn):
            a.setCheckable(True)
        help_menu(mb, self, T("Menedżer urządzeń", "Device Manager"), "system")
        bar = QFrame()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(4, 2, 4, 2)
        for icon, tip, fn in (("properties", T("Właściwości", "Properties"), self.properties),
                              ("refresh", T("Skanuj w poszukiwaniu zmian sprzętu", "Scan for hardware changes"), self.refresh)):
            b = QToolButton()
            b.setIcon(iconcache.icon(icon))
            b.setIconSize(QSize(16, 16))
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bl.addWidget(b)
        bl.addStretch(1)
        lay.addWidget(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(lambda it, c: self.properties(it))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context)
        lay.addWidget(self.tree, 1)
        self.resize(520, 520)
        self.refresh()

    def set_view(self, v):
        self.view = v
        self.refresh()

    def refresh(self):
        self.a_type.setChecked(self.view == "type")
        self.a_conn.setChecked(self.view == "conn")
        self.devices = collect()
        self.tree.clear()
        from ...common import sysctl
        root = QTreeWidgetItem([sysctl.hostname()])
        root.setIcon(0, iconcache.icon("computer"))
        self.tree.addTopLevelItem(root)
        if self.view == "type":
            cats = {}
            for d in self.devices:
                if d.cat not in cats:
                    pl, en, icon = CATS[d.cat]
                    it = QTreeWidgetItem([T(pl, en)])
                    it.setIcon(0, iconcache.icon(icon))
                    cats[d.cat] = it
                it = QTreeWidgetItem(cats[d.cat], [d.name])
                it.setIcon(0, _overlay_problem(CATS[d.cat][2]) if d.problem else iconcache.icon(CATS[d.cat][2]))
                it.setData(0, Qt.UserRole, d)
                if d.problem:
                    cats[d.cat].setExpanded(True)
            for key in sorted(cats, key=lambda k: cats[k].text(0).lower()):
                root.addChild(cats[key])
                if any(cats[key].child(i).data(0, Qt.UserRole).problem for i in range(cats[key].childCount())):
                    cats[key].setExpanded(True)
        else:
            # według połączenia: zagnieżdżenie po ścieżkach w /sys/devices
            items = {}
            devs = sorted([d for d in self.devices if d.syspath.startswith("/sys/devices")], key=lambda d: d.syspath)
            for d in devs:
                parent = root
                best = ""
                for path in items:
                    if d.syspath.startswith(path + "/") and len(path) > len(best):
                        best = path
                if best:
                    parent = items[best]
                it = QTreeWidgetItem(parent, [d.name])
                it.setIcon(0, _overlay_problem(CATS[d.cat][2]) if d.problem else iconcache.icon(CATS[d.cat][2]))
                it.setData(0, Qt.UserRole, d)
                items[d.syspath] = it
            for d in self.devices:
                if not d.syspath.startswith("/sys/devices"):
                    it = QTreeWidgetItem(root, [d.name])
                    it.setIcon(0, iconcache.icon(CATS[d.cat][2]))
                    it.setData(0, Qt.UserRole, d)
            self.tree.expandAll()
        root.setExpanded(True)

    def properties(self, item=None):
        item = item or self.tree.currentItem()
        if item is None:
            return
        d = item.data(0, Qt.UserRole)
        if isinstance(d, Device):
            DevicePropertiesDialog(d, self).exec()
        else:
            item.setExpanded(not item.isExpanded())

    def _context(self, pos):
        it = self.tree.itemAt(pos)
        if it is None:
            return
        self.tree.setCurrentItem(it)
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction(T("&Skanuj w poszukiwaniu zmian sprzętu", "Scan for &hardware changes"), self.refresh)
        if isinstance(it.data(0, Qt.UserRole), Device):
            m.addSeparator()
            a = m.addAction(T("&Właściwości", "P&roperties"), lambda: self.properties(it))
            f = a.font()
            f.setBold(True)
            a.setFont(f)
        m.exec(self.tree.viewport().mapToGlobal(pos))


def open_device_manager(page=None, parent=None):
    w = DeviceManager()
    return w

