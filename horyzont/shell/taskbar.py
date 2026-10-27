"""Pasek zadań: przycisk Start, szybkie uruchamianie, przyciski okien, zasobnik i zegar."""
import os

from PySide6.QtCore import QDateTime, QLocale, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout,
                               QLabel, QMenu, QSlider, QToolTip, QVBoxLayout,
                               QWidget)

from .. import config
from ..common import launcher, sysctl
from ..common.desktopentry import find_for_app_id
from ..i18n import plain, tr
from ..theme import iconcache
from ..theme.base import CHECKED, HOVER, NORMAL, PRESSED
from ..theme.manager import ThemeManager, current

SHELL_TITLES = ("horyzont-desktop", "horyzont-taskbar", "horyzont-startmenu")

APP_ICONS = {
    "horyzont-explorer": "folder_open",
    "horyzont-notepad": "notepad",
    "horyzont-taskmgr": "taskmgr",
    "horyzont-control": "control_panel",
    "horyzont-cmd": "cmd",
    "horyzont-calc": "calculator",
    "horyzont-charmap": "charmap",
    "horyzont-paint": "paint",
    "horyzont-wordpad": "wordpad",
    "horyzont-imageviewer": "image_viewer",
    "horyzont-mplayer": "media_player",
    "horyzont-soundrec": "recorder",
    "horyzont-mines": "mines",
    "horyzont-solitaire": "cards",
    "horyzont-shell": "logo",
}


def icon_for_toplevel(tl):
    if tl.app_id in APP_ICONS:
        return None, APP_ICONS[tl.app_id]
    e = find_for_app_id(tl.app_id)
    if e and e.icon:
        return iconcache.theme_or_builtin(e.icon, "app"), None
    return None, "app"


def start_text():
    t = (config.get("start_text", "") or "").strip()
    return t if t else plain("start")


class StartButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_Hover)
        self._down = False
        self._hover = False
        self.text = start_text()
        self.setToolTip(tr("start") + " — " + plain("all_programs"))
        self.setToolTip("")

    def sizeHint(self):
        h = current().metrics["taskbar_h"]
        return QSize(current().start_button_width(self.text, h), h)

    def setDown(self, d):
        self._down = d
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        st = PRESSED if self._down else HOVER if self._hover else NORMAL
        current().draw_start_button(p, self.rect(), st, self.text)


class TaskButton(QWidget):
    def __init__(self, bar, tl):
        super().__init__(bar.task_area)
        self.bar = bar
        self.tl = tl
        self.group = None  # lista okien, gdy przycisk grupuje
        self.setAttribute(Qt.WA_Hover)
        self._hover = False
        self._pressed = False
        self._qicon, self._icon_name = icon_for_toplevel(tl)
        self.setMouseTracking(True)

    def is_active(self):
        if self.group:
            return any(t.activated and not t.minimized for t in self.group)
        return self.tl.activated and not self.tl.minimized

    def label(self):
        if self.group:
            from ..common.desktopentry import find_for_app_id
            e = find_for_app_id(self.tl.app_id)
            name = e.name if e else (self.tl.app_id or self.tl.title)
            return name
        return self.tl.title or self.tl.app_id

    def enterEvent(self, e):
        self._hover = True
        self.update()
        title = self.label()
        fm = QFontMetrics(current().font("normal"))
        if fm.horizontalAdvance(title) > self.width() - 32:
            QToolTip.showText(QCursor.pos(), title, self)

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if hasattr(self.bar.shell, "hide_start"):
            self.bar.shell.hide_start()
        if e.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
        elif e.button() == Qt.RightButton:
            self.bar.task_menu(self, e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.bar.task_clicked(self)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        active = self.is_active()
        st = CHECKED if active or self._pressed else HOVER if self._hover else NORMAL
        t.draw_task_button(p, self.rect(), st)
        off = 1 if st == CHECKED else 0
        x = 7 + off
        y = (self.height() - 16) // 2 + off
        if self._qicon is not None:
            p.drawPixmap(x, y, self._qicon.pixmap(16, 16))
        else:
            p.drawPixmap(x, y, iconcache.pixmap(self._icon_name, 16))
        x += 16 + 5
        f = t.font("normal")
        if active:
            f.setBold(True)
        p.setFont(f)
        p.setPen(t.taskbar_text_color())
        text = self.label()
        if self.group:
            text = f"{len(self.group)}  {text}"
        r = QRect(x, off, self.width() - x - 6, self.height())
        p.drawText(r, Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(f).elidedText(text, Qt.ElideRight, r.width()))
        if self.group:
            from ..theme.base import draw_arrow
            draw_arrow(p, QRect(self.width() - 14, 0, 10, self.height()), "down", t.taskbar_text_color(), 3)


class QuickLaunch(QWidget):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.items = []
        self._hover = -1
        self.setMouseTracking(True)
        self.reload()

    def reload(self):
        self.items = []
        for key in config.get("quick_launch", []):
            if key == "show-desktop":
                self.items.append(("show_desktop", plain("show_desktop"), lambda: self.bar.show_desktop()))
            elif key == "browser":
                e = launcher.default_app("browser")
                if e:
                    self.items.append(("browser", e.name, lambda e=e: launcher.launch_entry(e)))
            elif key == "explorer":
                self.items.append(("folder_open", plain("app_explorer"), lambda: launcher.start_builtin("explorer")))
        self.updateGeometry()

    def sizeHint(self):
        return QSize(8 + len(self.items) * 24, current().metrics["taskbar_h"])

    def mouseMoveEvent(self, e):
        i = (int(e.position().x()) - 6) // 24
        i = i if 0 <= i < len(self.items) else -1
        if i != self._hover:
            self._hover = i
            self.update()
            if i >= 0:
                QToolTip.showText(QCursor.pos(), self.items[i][1], self)

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and 0 <= self._hover < len(self.items):
            self.items[self._hover][2]()

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        # uchwyt
        p.setPen(Qt.NoPen)
        for y in range(5, self.height() - 4, 3):
            p.fillRect(2, y, 2, 2, Qt.white if t.name != "classic" else Qt.gray)
        for i, (icon, name, _) in enumerate(self.items):
            r = QRect(6 + i * 24, (self.height() - 22) // 2, 22, 22)
            if i == self._hover:
                t.draw_toolbar_button(p, r, HOVER) if t.name == "classic" else t.draw_task_button(p, r, HOVER)
            p.drawPixmap(r.left() + 3, r.top() + 3, iconcache.pixmap(icon, 16))


class VolumePopup(QFrame):
    def __init__(self, parent=None, vol=None):
        super().__init__(parent, Qt.Popup)
        self.setFrameShape(QFrame.Box)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel(plain("volume"))
        lbl.setAlignment(Qt.AlignHCenter)
        lay.addWidget(lbl)
        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setTickPosition(QSlider.TicksBothSides)
        self.slider.setTickInterval(10)
        self.slider.setMinimumHeight(110)
        lay.addWidget(self.slider, 0, Qt.AlignHCenter)
        self.mute = QCheckBox(plain("mute"))
        lay.addWidget(self.mute)
        v = vol if vol is not None else sysctl.volume_get()
        if v:
            self.slider.setValue(v[0])
            self.mute.setChecked(v[1])
        self.slider.valueChanged.connect(sysctl.volume_set)
        self.mute.toggled.connect(sysctl.volume_mute)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), current().color("window"))
        current().draw_menu_frame(p, self.rect())


class Tray(QWidget):
    """Obszar powiadomień: aktualizacje, Bluetooth, sieć, głośność, bateria, zegar."""

    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.setMouseTracking(True)
        self._icons = []  # (nazwa ikony, podpowiedź, akcja lewego przycisku, menu prawego przycisku, klucz)
        self.state = {}
        self._prev = {}
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start(1000)
        self._last_minute = None
        from .traystatus import TrayStatus
        self.status = TrayStatus()
        self.status.updated.connect(self._on_status)
        QTimer.singleShot(0, self.status.start)
        self.sni = None   # ikony programów (StatusNotifierItem), podpinane przez powłokę

    def attach_sni(self, host):
        self.sni = host
        host.changed.connect(self._rebuild)
        self._rebuild()

    def _sni_item(self, key):
        if self.sni is None or not key or not key.startswith("sni:"):
            return None
        return self.sni.items.get(key[4:])

    def icon_x(self, key):
        """Globalna współrzędna X środka ikony o danym kluczu (do ogonka dymku) albo None."""
        for i, ic in enumerate(self._icons):
            if ic[4] == key:
                return self.mapToGlobal(QPoint(10 + i * 20 + 10, 0)).x()
        return None

    def anchor_for_app(self, app_name, desktop_entry=None):
        """Dymek powiadomienia programu wskazuje jego ikonę w zasobniku (jeśli ją ma)."""
        if self.sni is None:
            return None
        names = {n.lower() for n in (app_name, desktop_entry) if n}
        if not names:
            return None
        for it in self.sni.visible_items():
            cand = {(it.id or "").lower(), (it.title or "").lower()}
            if any(n and any(n in c or c in n for c in cand if c) for n in names):
                return self.icon_x("sni:" + it.key)
        return None

    # ----------------------------------------------------------------- stan
    def refresh_status(self):
        """Prośba o odświeżenie (wynik przyjdzie asynchronicznie)."""
        self.status.refresh_soon()
        self._rebuild()

    def _on_status(self, st):
        prev, self.state = self.state, st
        self._notify_changes(prev, st)
        self._rebuild()

    def _rebuild(self):
        st = self.state
        icons = []
        if self.sni is not None and config.get("tray_app_icons", True):
            for it in self.sni.visible_items():
                icons.append((it.icon, it.tip, None, None, "sni:" + it.key))
        upd = st.get("updates") or {}
        n_upd = int(upd.get("count", 0) or 0)
        if n_upd and config.get("updates_tray_icon", True):
            icons.append(("tray_updates", tr("upd_tray_tip", n_upd), self.open_updates, None, "updates"))
        bt = st.get("bt") or {}
        if bt.get("present") and config.get("bt_tray_icon", True):
            tip = plain("bt_title") + "\n" + (plain("bt_on") if bt.get("powered") else plain("bt_off"))
            if bt.get("connected"):
                tip += "\n" + tr("bt_connected_to", ", ".join(bt["connected"]))
            icons.append(("tray_bluetooth" if bt.get("powered") else "tray_bluetooth_off", tip, self.bt_menu,
                          self.bt_menu, "bt"))
        net = st.get("net") or {}
        if net.get("kind") == "wifi" or (net.get("wifi_present") and net.get("state") != "connected"):
            if net.get("state") == "connected":
                from ..common.netman import signal_level
                lvl = signal_level(net.get("signal", 0))
                icon = f"tray_wifi_{lvl}"
                tip = tr("tray_wifi_tip", net.get("ssid", ""), _signal_words(net.get("signal", 0)))
            elif not net.get("wifi_enabled", True):
                icon, tip = "tray_wifi_off", plain("wifi_turned_off")
            else:
                icon, tip = "tray_wifi_off", plain("tray_wifi_none")
            icons.append((icon, tip, self.open_wifi, self.net_menu, "net"))
        elif net.get("state") in ("connected", "connecting"):
            icons.append(("tray_network", tr("tray_lan_tip", net.get("name", "")), self.open_net_status, self.net_menu, "net"))
        elif net.get("state") == "disconnected":
            icons.append(("tray_network_off", plain("tray_cable_unplugged"), self.open_network, self.net_menu, "net"))
        v = st.get("volume")
        if v is not None:
            icons.append(("volume_muted" if v[1] else "volume", f"{plain('volume')}: {v[0]}%", self.show_volume,
                          self.volume_menu, "vol"))
        b = st.get("battery")
        if b is not None:
            icons.append(("tray_battery", tr("po_battery", b[0]) + ("" if not b[1] else " — " + tr("po_ac")),
                          lambda: launcher.start_builtin("control", ["power"]), None, "bat"))
        self._icons = icons
        self.updateGeometry()
        if getattr(self.bar, "tray", None) is self:
            self.bar.relayout()
        self.update()

    def _notify_changes(self, prev, st):
        if not prev:
            n = int((st.get("updates") or {}).get("count", 0) or 0)
            if n:
                QTimer.singleShot(4000, lambda: self.balloon(plain("upd_balloon_title"), tr("upd_balloon_text", n),
                                                             "tray_updates", self.open_updates))
            return
        pn, nn = prev.get("net") or {}, st.get("net") or {}
        if nn.get("state") == "connected" and (pn.get("state") != "connected" or pn.get("name") != nn.get("name")):
            if nn.get("kind") == "wifi":
                self.balloon(plain("wifi_title"), tr("tray_now_connected_wifi", nn.get("ssid", ""),
                                                     _signal_words(nn.get("signal", 0))), "tray_wifi_4")
            else:
                self.balloon(plain("nc_local_conn"), tr("tray_now_connected", nn.get("name", "")), "tray_network")
        elif pn.get("state") == "connected" and nn.get("state") == "disconnected":
            self.balloon(plain("nc_local_conn") if pn.get("kind") != "wifi" else plain("wifi_title"),
                         plain("tray_disconnected"), "tray_network_off")
        pb, nb = set((prev.get("bt") or {}).get("connected", [])), set((st.get("bt") or {}).get("connected", []))
        for name in nb - pb:
            self.balloon(plain("bt_title"), tr("bt_device_connected", name), "tray_bluetooth")
            from ..common import sounds
            sounds.play("device_connect")
        if pb - nb:
            from ..common import sounds
            sounds.play("device_disconnect")
        bat = st.get("battery")
        pbat = prev.get("battery")
        if bat and not bat[1] and bat[0] <= 10 and not (pbat and not pbat[1] and pbat[0] <= 10):
            self.balloon(plain("po_battery_low_title"), tr("po_battery_low_text", bat[0]), "warning",
                         lambda: launcher.start_builtin("control", ["power"]))
            from ..common import sounds
            sounds.play("battery_low")
        pu = int((prev.get("updates") or {}).get("count", 0) or 0)
        nu = int((st.get("updates") or {}).get("count", 0) or 0)
        if nu > pu:
            self.balloon(plain("upd_balloon_title"), tr("upd_balloon_text", nu), "tray_updates", self.open_updates)
        msg = (st.get("updates") or {}).get("message")
        if msg and msg != (prev.get("updates") or {}).get("message"):
            self.balloon(plain("upd_title"), msg, "updates", self.open_updates)

    def balloon(self, title, text, icon="info", action=None, key=None):
        """Dymek systemowy (sieć, Bluetooth, bateria, aktualizacje) — przez wspólną kolejkę dymków."""
        keys = {"tray_updates": "updates", "updates": "updates", "tray_network": "net", "tray_network_off": "net",
                "tray_wifi_4": "net", "tray_bluetooth": "bt"}
        k = key or keys.get(icon if isinstance(icon, str) else "", None)
        self.bar.balloons.show({"title": title, "text": text, "icon": icon, "on_click": action,
                                "timeout_ms": 10000, "force": True,
                                "anchor": (lambda: self.icon_x(k)) if k else None})

    # ----------------------------------------------------------------- akcje
    def open_updates(self):
        launcher.start_builtin("control", ["updates"])

    def open_wifi(self):
        launcher.start_builtin("control", ["wifi"])

    def open_network(self):
        launcher.start_builtin("control", ["network"])

    def open_net_status(self):
        launcher.start_builtin("control", ["network"])

    def net_menu(self, gpos=None):
        net = self.state.get("net") or {}
        m = QMenu(self)
        if net.get("wifi_present"):
            m.addAction(iconcache.icon("network_wireless"), tr("nc_view_wifi_m"), self.open_wifi)
            m.addSeparator()
        m.addAction(tr("nc_status"), self.open_net_status)
        if net.get("state") == "connected" and net.get("device"):
            m.addAction(tr("nc_repair_m"), lambda: self._repair(net))
        if net.get("wifi_present"):
            on = net.get("wifi_enabled", True)
            m.addAction(plain("wifi_turn_off") if on else plain("wifi_turn_on"), lambda: self._wifi_radio(not on))
        m.addSeparator()
        m.addAction(tr("tray_open_network"), self.open_network)
        m.exec(gpos or QCursor.pos())

    def _repair(self, net):
        import subprocess
        subprocess.Popen(["nmcli", "device", "reapply", net["device"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.balloon(plain("nc_repair_title"), tr("nc_repair_ok", net.get("name", "")), "tray_network")
        self.status.refresh_soon()

    def _wifi_radio(self, on):
        import subprocess
        subprocess.Popen(["nmcli", "radio", "wifi", "on" if on else "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.status.refresh_soon()

    def bt_menu(self, gpos=None):
        bt = self.state.get("bt") or {}
        m = QMenu(self)
        m.addAction(iconcache.icon("bluetooth"), plain("bt_add_device"), lambda: launcher.start_builtin("control", ["bluetooth", "add"]))
        m.addAction(plain("bt_show_devices"), lambda: launcher.start_builtin("control", ["bluetooth"]))
        m.addSeparator()
        on = bt.get("powered")
        m.addAction(plain("bt_turn_off") if on else plain("bt_turn_on"), lambda: self._bt_power(not on))
        m.addAction(plain("bt_open_settings"), lambda: launcher.start_builtin("control", ["bluetooth", "options"]))
        m.addSeparator()
        m.addAction(plain("bt_remove_icon"), lambda: config.set("bt_tray_icon", False))
        m.exec(gpos or QCursor.pos())

    def _bt_power(self, on):
        import subprocess
        if on and shutil_which("rfkill"):
            subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
        subprocess.Popen(["bluetoothctl", "power", "on" if on else "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        QTimer.singleShot(1200, self.status.refresh_now)

    def volume_menu(self, gpos=None):
        m = QMenu(self)
        a = m.addAction(tr("vol_open_mixer"), self._open_mixer)
        f = a.font()
        f.setBold(True)
        a.setFont(f)
        m.addAction(tr("vol_adjust"), lambda: launcher.start_builtin("control", ["sound"]))
        m.exec(gpos or QCursor.pos())

    def _open_mixer(self):
        for c in ("pavucontrol", "pwvucontrol", "pavucontrol-qt"):
            if shutil_which(c):
                launcher._spawn([c])
                return
        launcher.start_builtin("control", ["sound"])

    def _tick(self):
        now = QDateTime.currentDateTime()
        key = now.toString("HH:mm:ss" if config.get("clock_seconds") else "HH:mm")
        if key != self._last_minute:
            self._last_minute = key
            self.update()

    def clock_text(self):
        fmt = "H:mm:ss" if config.get("clock_seconds") else "H:mm"
        return QDateTime.currentDateTime().toString(fmt)

    def sizeHint(self):
        fm = QFontMetrics(current().font("normal"))
        w = 12 + len(self._icons) * 20
        if config.get("clock_visible", True):
            w += fm.horizontalAdvance("00:00:00" if config.get("clock_seconds") else "00:00") + 16
        return QSize(w + 4, current().metrics["taskbar_h"])

    def _clock_rect(self):
        fm = QFontMetrics(current().font("normal"))
        cw = fm.horizontalAdvance("00:00:00" if config.get("clock_seconds") else "00:00") + 16
        return QRect(self.width() - cw - 4, 0, cw, self.height())

    def _icon_at(self, pos):
        x = 10
        for i, ic in enumerate(self._icons):
            if QRect(x, 0, 20, self.height()).contains(pos):
                return i
            x += 20
        return -1

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        i = self._icon_at(pos)
        if i >= 0:
            QToolTip.showText(QCursor.pos(), self._icons[i][1], self)
        elif config.get("clock_visible", True) and self._clock_rect().contains(pos):
            loc = QLocale()
            QToolTip.showText(QCursor.pos(), loc.toString(QDateTime.currentDateTime().date(), QLocale.LongFormat), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if hasattr(self.bar.shell, "hide_start"):
            self.bar.shell.hide_start()
        i = self._icon_at(pos)
        it = self._sni_item(self._icons[i][4]) if i >= 0 else None
        if it is not None:
            gpos = e.globalPosition().toPoint()
            if e.button() == Qt.RightButton:
                self.sni.context(it, gpos)
            elif e.button() == Qt.MiddleButton:
                self.sni.secondary(it, gpos)
            else:
                self.sni.activate(it, gpos)
            return
        if e.button() == Qt.RightButton:
            if i >= 0 and self._icons[i][3]:
                self._icons[i][3](e.globalPosition().toPoint())
            else:
                self.bar.context_menu(e.globalPosition().toPoint(), tray=True)
            return
        if i >= 0 and self._icons[i][2]:
            act = self._icons[i][2]
            if act in (self.bt_menu,):
                act(e.globalPosition().toPoint())
            else:
                act()

    def wheelEvent(self, e):
        i = self._icon_at(e.position().toPoint())
        it = self._sni_item(self._icons[i][4]) if i >= 0 else None
        if it is not None:
            d = e.angleDelta()
            if d.y():
                self.sni.scroll(it, d.y(), "vertical")
            elif d.x():
                self.sni.scroll(it, d.x(), "horizontal")

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        if self._clock_rect().contains(pos):
            launcher.start_builtin("control", ["datetime"])
            return
        i = self._icon_at(pos)
        if i >= 0 and self._icons[i][4] == "bt":
            launcher.start_builtin("control", ["bluetooth"])

    def show_volume(self):
        pop = VolumePopup(self, self.state.get("volume"))
        pop.adjustSize()
        pop.slider.valueChanged.connect(lambda *_: self.status.refresh_soon())
        g = self.mapToGlobal(QPoint(0, 0))
        pop.move(g.x() + 10, g.y() - pop.height() - 2)
        pop.show()

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        t.draw_tray(p, self.rect())
        x = 10
        for name, *_ in self._icons:
            if isinstance(name, QIcon):
                pm = name.pixmap(16, 16)
                if pm.width() > 16 or pm.height() > 16:
                    pm = pm.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                dpr = pm.devicePixelRatio() or 1
                w, h = int(pm.width() / dpr), int(pm.height() / dpr)
                p.drawPixmap(x + 2 + (16 - w) // 2, (self.height() - h) // 2, pm)
            else:
                p.drawPixmap(x + 2, (self.height() - 16) // 2, iconcache.pixmap(name, 16))
            x += 20
        if config.get("clock_visible", True):
            p.setFont(t.font("normal"))
            p.setPen(t.taskbar_text_color())
            p.drawText(self._clock_rect(), Qt.AlignCenter, self.clock_text())


def shutil_which(c):
    import shutil
    return shutil.which(c)


def _signal_words(sig):
    if sig >= 80:
        return plain("sig_excellent")
    if sig >= 60:
        return plain("sig_very_good")
    if sig >= 40:
        return plain("sig_good")
    if sig >= 20:
        return plain("sig_low")
    return plain("sig_very_low")


class Taskbar(QWidget):
    start_requested = Signal()

    def __init__(self, backend, shell):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setWindowTitle("horyzont-taskbar")
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDock, True)
        self.shell = shell
        self.backend = backend
        self.buttons = {}  # uid -> TaskButton
        self.start = StartButton(self)
        self.start.clicked.connect(self.start_requested.emit)
        self.quick = QuickLaunch(self)
        self.task_area = QWidget(self)
        from .balloon import BalloonQueue
        self.balloons = BalloonQueue(self)
        self.balloons.enabled = bool(config.get("balloon_tips", True))
        self.tray = Tray(self)
        backend.added.connect(self._added)
        backend.removed.connect(self._removed)
        backend.changed.connect(self._changed)
        for tl in backend.toplevels:
            self._added(tl)
        ThemeManager.instance().changed.connect(self._theme_changed)
        self._cfg_watch = config.watch(self._config_changed)

    # ------------------------------------------------------------ układ
    def _theme_changed(self):
        self.start.updateGeometry()
        self.shell.place_taskbar()
        self.relayout()
        self.update()

    def _config_changed(self):
        t = start_text()
        if t != self.start.text:
            self.start.text = t
            self.start.updateGeometry()
            self.start.update()
        self.quick.reload()
        self.balloons.enabled = bool(config.get("balloon_tips", True))
        self.tray.refresh_status()
        self.relayout()

    def resizeEvent(self, e):
        self.relayout()

    def relayout(self):
        h = self.height()
        sw = self.start.sizeHint().width()
        self.start.setGeometry(0, 0, sw, h)
        x = sw + 4
        if config.get("taskbar_quick_launch", False) and self.quick.items:
            qw = self.quick.sizeHint().width()
            self.quick.setGeometry(x, 0, qw, h)
            self.quick.show()
            x += qw + 4
        else:
            self.quick.hide()
        tw = self.tray.sizeHint().width()
        self.tray.setGeometry(self.width() - tw, 0, tw, h)
        self.task_area.setGeometry(x, 0, max(0, self.width() - tw - x - 4), h)
        self._layout_buttons()

    def _visible_toplevels(self):
        out = []
        for tl in self.backend.toplevels:
            if tl.title in SHELL_TITLES:
                continue
            if tl.parent is not None:
                continue
            out.append(tl)
        return out

    def _layout_buttons(self):
        tls = self._visible_toplevels()
        area = self.task_area
        h = area.height()
        bh = current().metrics["task_button_h"]
        top = (h - bh) // 2 + 1
        maxw = current().metrics["task_button_max_w"]
        n = len(tls)
        for b in self.buttons.values():
            b.group = None
        groups = []
        if n and config.get("taskbar_group", True) and area.width() / n < 90:
            by_app = {}
            for tl in tls:
                by_app.setdefault(tl.app_id or tl.title, []).append(tl)
            for app, items in by_app.items():
                groups.append(items)
        else:
            groups = [[tl] for tl in tls]
        count = len(groups)
        w = min(maxw, (area.width() - 2) // count) if count else maxw
        x = 0
        shown = set()
        for items in groups:
            lead = items[0]
            btn = self.buttons.get(lead.uid)
            if btn is None:
                continue
            btn.group = items if len(items) > 1 else None
            btn.setGeometry(x, top, max(24, w - 3), bh)
            btn.show()
            btn.update()
            shown.add(lead.uid)
            x += w
        for uid, b in self.buttons.items():
            if uid not in shown:
                b.hide()

    # ------------------------------------------------------------ okna
    def _added(self, tl):
        if tl.title in SHELL_TITLES:
            return
        b = TaskButton(self, tl)
        self.buttons[tl.uid] = b
        self._layout_buttons()

    def _removed(self, tl):
        b = self.buttons.pop(tl.uid, None)
        if b:
            b.deleteLater()
        self._layout_buttons()

    def _changed(self, tl):
        if tl.title in SHELL_TITLES:
            b = self.buttons.pop(tl.uid, None)
            if b:
                b.deleteLater()
            self._layout_buttons()
            return
        if tl.uid not in self.buttons:
            self._added(tl)
        else:
            b = self.buttons[tl.uid]
            b._qicon, b._icon_name = icon_for_toplevel(tl)
        for b in self.buttons.values():
            b.update()

    def task_clicked(self, btn):
        if btn.group:
            m = QMenu(self)
            for tl in btn.group:
                qi, name = icon_for_toplevel(tl)
                a = m.addAction(qi if qi is not None else iconcache.icon(name), tl.title)
                a.triggered.connect(lambda _=False, t=tl: self.backend.activate(t))
            m.addSeparator()
            m.addAction(tr("task_close_group")).triggered.connect(lambda: [self.backend.close(t) for t in btn.group])
            m.exec(btn.mapToGlobal(QPoint(0, 0)) - QPoint(0, m.sizeHint().height()))
            return
        tl = btn.tl
        if tl.activated and not tl.minimized:
            self.backend.minimize(tl)
        else:
            self.backend.activate(tl)

    def task_menu(self, btn, gpos):
        if btn.group:
            self.task_clicked(btn)
            return
        tl = btn.tl
        m = QMenu(self)
        a_r = m.addAction(tr("task_restore"))
        a_r.setEnabled(tl.minimized or tl.maximized)
        a_n = m.addAction(tr("task_minimize"))
        a_n.setEnabled(not tl.minimized)
        a_x = m.addAction(tr("task_maximize"))
        a_x.setEnabled(not tl.maximized)
        m.addSeparator()
        a_c = m.addAction(tr("task_close"))
        f = a_c.font()
        f.setBold(True)
        a_c.setFont(f)
        act = m.exec(gpos - QPoint(0, m.sizeHint().height()))
        if act is a_r:
            if tl.minimized:
                self.backend.activate(tl)
            else:
                self.backend.unmaximize(tl)
        elif act is a_n:
            self.backend.minimize(tl)
        elif act is a_x:
            self.backend.maximize(tl)
            self.backend.activate(tl)
        elif act is a_c:
            self.backend.close(tl)

    def show_desktop(self):
        tls = self._visible_toplevels()
        if all(t.minimized for t in tls):
            for t in getattr(self, "_restored", []):
                if t in self.backend.toplevels:
                    self.backend.unminimize(t)
            self._restored = []
        else:
            self._restored = [t for t in tls if not t.minimized]
            for t in self._restored:
                self.backend.minimize(t)

    # ------------------------------------------------------------ menu kontekstowe
    def mousePressEvent(self, e):
        if hasattr(self.shell, "hide_start"):
            self.shell.hide_start()
        if e.button() == Qt.RightButton:
            self.context_menu(e.globalPosition().toPoint())

    def context_menu(self, gpos, tray=False):
        m = QMenu(self)
        if tray:
            m.addAction(tr("tb_adjust_datetime")).triggered.connect(lambda: launcher.start_builtin("control", ["datetime"]))
            m.addSeparator()
        tb = m.addMenu(tr("tb_toolbars"))
        ql = tb.addAction(tr("tb_quick_launch"))
        ql.setCheckable(True)
        ql.setChecked(config.get("taskbar_quick_launch", False))
        ql.toggled.connect(lambda v: (config.set("taskbar_quick_launch", v), self.relayout()))
        m.addSeparator()
        m.addAction(tr("tb_show_desktop")).triggered.connect(self.show_desktop)
        m.addSeparator()
        m.addAction(tr("tb_taskmgr")).triggered.connect(lambda: launcher.start_builtin("taskmgr"))
        m.addSeparator()
        lock = m.addAction(tr("tb_lock"))
        lock.setCheckable(True)
        lock.setChecked(config.get("taskbar_locked", True))
        lock.toggled.connect(lambda v: config.set("taskbar_locked", v))
        m.addAction(tr("tb_properties")).triggered.connect(lambda: launcher.start_builtin("control", ["taskbar"]))
        m.exec(gpos - QPoint(0, m.sizeHint().height()))

    def paintEvent(self, e):
        p = QPainter(self)
        current().draw_taskbar(p, self.rect())
