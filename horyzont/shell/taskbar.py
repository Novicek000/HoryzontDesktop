"""Pasek zadań: przycisk Start, szybkie uruchamianie, przyciski okien, zasobnik i zegar."""
import os

from PySide6.QtCore import QDateTime, QLocale, QPoint, QRect, QSize, Qt, QTimer, Signal, QVariantAnimation, QEasingCurve, QProcess
from PySide6.QtGui import QAction, QCursor, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout,
                               QLabel, QMenu, QSlider, QToolTip, QVBoxLayout,
                               QWidget)

from .. import config
from ..common import launcher, sysctl, taskbarlayout
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
    "horyzont-sndvol": "volume",
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
            elif key.startswith("desktop:"):
                from ..common.desktopentry import all_entries
                e = all_entries().get(key[8:])
                if e:
                    self.items.append((iconcache.theme_or_builtin(e.icon, "app"), e.name,
                                       lambda e=e: launcher.launch_entry(e)))
            elif key.startswith("builtin:"):
                from .startmenu import BUILTIN_MENU
                b = BUILTIN_MENU.get(key[8:])
                if b:
                    self.items.append((b[1], plain(b[0]), b[2]))
        self.updateGeometry()

    def sizeHint(self):
        return QSize(4 + len(self.items) * 24, current().metrics["taskbar_h"])

    def _columns(self):
        return max(1, (self.width()-4)//24)

    def _visible_count(self):
        if taskbarlayout.vertical():
            return min(len(self.items), self._columns()*max(1, self.height()//24))
        return len(self.items) if self.width() >= self.sizeHint().width() else max(0, (self.width()-20)//24)

    def _item_rect(self, index):
        cols = self._columns() if taskbarlayout.vertical() else max(1, len(self.items))
        height = min(current().metrics["taskbar_h"], self.height())
        return QRect(2+(index % cols)*24, (index//cols)*24+(height-22)//2, 22, 22)

    def mouseMoveEvent(self, e):
        i = next((j for j in range(self._visible_count()) if self._item_rect(j).contains(e.position().toPoint())), -1)
        if i != self._hover:
            self._hover = i
            self.update()
            if i >= 0:
                QToolTip.showText(QCursor.pos(), self.items[i][1], self)

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        visible = self._visible_count()
        if visible < len(self.items) and e.position().x() >= self.width()-18:
            menu = QMenu(self)
            for icon, text, action in self.items[visible:]:
                a = menu.addAction(icon if isinstance(icon, QIcon) else iconcache.icon(icon), text)
                a.triggered.connect(lambda _=False, cb=action: cb())
            menu.exec(self.mapToGlobal(QPoint(self.width()-18, self.height())))
        else:
            index = next((j for j in range(visible) if self._item_rect(j).contains(e.position().toPoint())), -1)
            if index >= 0:
                self.items[index][2]()

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        visible = self._visible_count()
        for i, (icon, name, _) in enumerate(self.items[:visible]):
            r = self._item_rect(i)
            if i == self._hover:
                t.draw_toolbar_button(p, r, HOVER) if t.name == "classic" else t.draw_task_button(p, r, HOVER)
            pm = icon.pixmap(16, 16) if isinstance(icon, QIcon) else iconcache.pixmap(icon, 16)
            p.drawPixmap(r.left() + 3, r.top() + 3, pm)
        if visible < len(self.items):
            p.setPen(t.taskbar_text_color())
            p.drawText(QRect(self.width()-18, 0, 18, min(self.height(), t.metrics["taskbar_h"])), Qt.AlignCenter, "»")


class VolumePopup(QFrame):
    applied = Signal()

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
        # Jedno asynchroniczne polecenie naraz; podczas przeciągania zostaje
        # tylko ostatnia wartość, bez blokowania pętli zdarzeń.
        self._pending = {}
        self._preview = False
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._failed)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._process.kill)
        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.timeout.connect(self._flush)
        self.slider.valueChanged.connect(lambda v: self._queue("volume", v))
        self.slider.sliderReleased.connect(self._released)
        self.mute.toggled.connect(lambda v: self._queue("mute", v))

    def _queue(self, key, value):
        self._pending[key] = value
        self._coalesce.start(30)
        if key == "volume" and not self.slider.isSliderDown():
            self._preview = True

    def _released(self):
        self._preview = True
        self._coalesce.stop()
        self._flush()

    def _flush(self):
        if self._process.state() != QProcess.NotRunning:
            return
        if not self._pending:
            if self._preview:
                self._preview = False
                from ..common import sounds
                sounds.play("volume", force=True)
            return
        key = next(iter(self._pending))
        value = self._pending.pop(key)
        if shutil_which("wpctl"):
            args = ["set-volume", "@DEFAULT_AUDIO_SINK@", f"{value / 100:.2f}"] if key == "volume" else ["set-mute", "@DEFAULT_AUDIO_SINK@", "1" if value else "0"]
            program = "wpctl"
        elif shutil_which("pactl"):
            args = ["set-sink-volume", "@DEFAULT_SINK@", f"{value}%"] if key == "volume" else ["set-sink-mute", "@DEFAULT_SINK@", "1" if value else "0"]
            program = "pactl"
        else:
            self._preview = False
            self._pending.clear()
            return
        self._process.start(program, args)
        self._timeout.start(3000)

    def _finished(self, code, status):
        self._timeout.stop()
        if code != 0:
            self._preview = False
        else:
            self.applied.emit()
        QTimer.singleShot(0, self._flush)

    def _failed(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self._preview = False
            QTimer.singleShot(0, self._flush)

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
        self._inactive_timer = QTimer(self)
        self._inactive_timer.timeout.connect(lambda: config.get("tray_hide_inactive", True) and self._rebuild())
        self._inactive_timer.start(30000)

    # ----------------------------------------------------------------- ukrywanie nieaktywnych ikon
    INACTIVE_SECONDS = 300
    expanded = False

    @staticmethod
    def behavior_key(entry):
        key = entry[4]
        return key

    def _item_title(self, entry):
        it = self._sni_item(entry[4])
        if it is not None:
            return it.title or it.id or (entry[1] or "").split("\n")[0]
        return {"net": plain("nc_local_conn"), "bt": "Bluetooth", "vol": plain("volume"), "bat": plain("power_opts"),
                "updates": "Horyzont Updates"}.get(entry[4], entry[4])

    def stable_key(self, entry):
        """Klucz zachowania niezależny od numeru połączenia D-Bus (identyfikator programu)."""
        it = self._sni_item(entry[4])
        if it is not None:
            return "app:" + (it.id or it.title or it.service)
        return "sys:" + entry[4]

    def _known_items(self, icons):
        known = dict(config.get("tray_known", {}))
        changed = False
        for e in icons:
            k = self.stable_key(e)
            title = self._item_title(e)
            if known.get(k) != title:
                known[k] = title
                changed = True
        if changed:
            config.set("tray_known", known)
        cur = sorted(self.stable_key(e) for e in icons)
        if cur != getattr(self, "_last_current", None):
            self._last_current = cur
            if cur != config.get("tray_current", []):
                config.set("tray_current", cur)

    def _filter_hidden(self, icons):
        if not config.get("tray_hide_inactive", True):
            return icons
        import time as _t
        beh = config.get("tray_behaviors", {})
        now = _t.monotonic()
        shown, hidden = [], 0
        for e in icons:
            b = beh.get(self.stable_key(e), "show" if e[4] and not e[4].startswith("sni:") else "auto")
            it = self._sni_item(e[4])
            if b == "show":
                visible = True
            elif b == "hide":
                visible = False
            else:
                visible = it is None or it.status == "NeedsAttention" or now - it.changed_at < self.INACTIVE_SECONDS
            if visible or self.expanded:
                shown.append(e)
            else:
                hidden += 1
        if hidden or (self.expanded and any(self._would_hide(e, beh, now) for e in icons)):
            shown.insert(0, (None, plain("tray_show_hidden") if not self.expanded else plain("tray_hide_inactive_tip"),
                             self.toggle_expanded, None, "chevron"))
        return shown

    def _would_hide(self, e, beh, now):
        b = beh.get(self.stable_key(e), "show" if e[4] and not e[4].startswith("sni:") else "auto")
        it = self._sni_item(e[4])
        if b == "hide":
            return True
        if b == "auto" and it is not None:
            return not (it.status == "NeedsAttention" or now - it.changed_at < self.INACTIVE_SECONDS)
        return False

    def toggle_expanded(self):
        self.expanded = not self.expanded
        self._rebuild()
        if self.expanded:
            QTimer.singleShot(15000, self._collapse)

    def _collapse(self):
        if self.expanded:
            self.expanded = False
            self._rebuild()

    def attach_sni(self, host):
        self.sni = host
        host.changed.connect(self._rebuild)
        self._rebuild()

    def _sni_item(self, key):
        if self.sni is None or not key or not key.startswith("sni:"):
            return None
        return self.sni.items.get(key[4:])

    def icon_anchor(self, key):
        for i, ic in enumerate(self._icons):
            if ic[4] == key:
                return self.mapToGlobal(self._icon_rect(i).center())
        if key != "chevron" and any(e[4] == key for e in getattr(self, "_all_icons", ())):
            return self.icon_anchor("chevron")
        return None

    def icon_x(self, key):
        point = self.icon_anchor(key)
        return point.x() if point is not None else None

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
                return self.icon_anchor("sni:" + it.key)
        return None

    # ----------------------------------------------------------------- stan
    def refresh_status(self):
        """Prośba o odświeżenie (wynik przyjdzie asynchronicznie)."""
        self.status.refresh_soon()
        self._rebuild()

    def _on_status(self, st):
        prev, self.state = self.state, st
        self._rebuild()
        self._notify_changes(prev, st)

    def _rebuild(self):
        st = self.state
        icons = []
        if self.sni is not None and config.get("tray_app_icons", True):
            for it in self.sni.visible_items():
                icons.append((it.icon, it.tip, None, None, "sni:" + it.key))
        upd = st.get("updates") or {}
        n_upd = int(upd.get("count", 0) or 0)
        if (n_upd or upd.get("message")) and config.get("updates_tray_icon", True):
            tip = tr("upd_tray_tip", n_upd) if n_upd else plain("upd_title")
            icons.append(("tray_updates", tip, self.open_updates, None, "updates"))
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
        self._all_icons = icons
        self._known_items(icons)
        icons = self._filter_hidden(icons)
        self._icons = icons
        self.updateGeometry()
        if getattr(self.bar, "tray", None) is self:
            self.bar.relayout()
        self.update()
        if getattr(self.bar, "balloons", None):
            self.bar.balloons.reposition()

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
                         lambda: launcher.start_builtin("control", ["power"]), key="bat")
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
                "tray_wifi_4": "net", "tray_bluetooth": "bt", "tray_bluetooth_off": "bt",
                "volume": "vol", "volume_muted": "vol", "tray_battery": "bat"}
        k = key or keys.get(icon if isinstance(icon, str) else "", None)
        self.bar.balloons.show({"title": title, "text": text, "icon": icon, "on_click": action,
                                "timeout_ms": 10000, "force": True,
                                "anchor": (lambda: self.icon_anchor(k)) if k else None})

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
        launcher.start_builtin("sndvol")

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
        cw = fm.horizontalAdvance("00:00:00" if config.get("clock_seconds") else "00:00") + 16 if config.get("clock_visible", True) else 0
        if taskbarlayout.vertical():
            cols = max(1, (self.bar.width() - 12) // 20)
            return QSize(self.bar.width(), 8 + ((len(self._icons) + cols - 1) // cols) * 24 + (24 if cw else 0))
        return QSize(16 + len(self._icons)*20 + cw, current().metrics["taskbar_h"])

    def _icon_rect(self, i):
        if taskbarlayout.vertical():
            cols = max(1, (self.width() - 12) // 20)
            return QRect(6 + (i % cols)*20, 4 + (i // cols)*24, 20, 24)
        return QRect(10 + i*20, 0, 20, self.height())

    def _clock_rect(self):
        fm = QFontMetrics(current().font("normal"))
        cw = fm.horizontalAdvance("00:00:00" if config.get("clock_seconds") else "00:00") + 16
        return QRect(0, self.height()-24, self.width(), 24) if taskbarlayout.vertical() else QRect(self.width()-cw-4, 0, cw, self.height())

    def _icon_at(self, pos):
        return next((i for i in range(len(self._icons)) if self._icon_rect(i).contains(pos)), -1)

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
        pop = getattr(self, "_volume_popup", None)
        if pop is None:
            pop = self._volume_popup = VolumePopup(self, self.state.get("volume"))
            pop.applied.connect(self.status.refresh_soon)
        elif not pop.isVisible():
            value = self.state.get("volume")
            if value:
                pop.slider.blockSignals(True)
                pop.mute.blockSignals(True)
                pop.slider.setValue(value[0])
                pop.mute.setChecked(value[1])
                pop.slider.blockSignals(False)
                pop.mute.blockSignals(False)
        pop.adjustSize()
        g = QRect(self.bar.mapToGlobal(QPoint()), self.bar.size())
        screen = self.bar.screen().geometry()
        anchor = self.mapToGlobal(self._icon_rect(next((i for i, it in enumerate(self._icons) if it[4] == "vol"), 0)).topLeft())
        pop.move(taskbarlayout.popup_position(g, pop.size(), screen, anchor))
        pop.show()

    def _draw_chevron(self, p, r):
        from PySide6.QtGui import QPen
        t = current()
        ns = "TrayNotifyVert" if taskbarlayout.vertical() else "TrayNotifyHoriz"
        cls = ns + ("Open" if self.expanded else "") + "::Button"
        if hasattr(t, "draw_part") and t.draw_part(p, r, cls, 2 if self.underMouse() else 1):
            return
        p.save()
        p.setPen(QPen(t.taskbar_text_color(), 1))
        c = r.center()
        d = -1 if self.expanded else 1
        # Niewielki podwójny szewron, bez obcej okrągłej obwódki.
        for off in (-2, 2):
            p.drawLine(c.x() + off + 2*d, c.y()-3, c.x() + off-d, c.y())
            p.drawLine(c.x() + off-d, c.y(), c.x() + off+2*d, c.y()+3)
        p.restore()

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        t.draw_tray(p, self.rect())
        for i, (name, _tip, _a, _m, key) in enumerate(self._icons):
            r = self._icon_rect(i)
            if key == "chevron":
                self._draw_chevron(p, r)
                continue
            pm = name.pixmap(16, 16) if isinstance(name, QIcon) else iconcache.pixmap(name, 16)
            p.drawPixmap(r.center().x()-7, r.center().y()-7, pm)
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


class BandGrip(QWidget):
    def __init__(self, bar, name):
        super().__init__(bar)
        self.bar, self.name = bar, name
        self.setCursor(Qt.SizeAllCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        t = current()
        cls = "TaskBar::Rebar.Gripper"
        if hasattr(t, "draw_part") and t.draw_part(p, self.rect().adjusted(1, 4, -1, -4), cls):
            return
        for y in range(5, self.height()-4, 3):
            p.fillRect(2, y, 2, 2, Qt.gray)
            p.fillRect(3, y+1, 2, 2, Qt.white)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.bar._band_drag = self.name

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.bar.move_band(self.name, self.bar.mapFromGlobal(event.globalPosition().toPoint()))

    def mouseReleaseEvent(self, event):
        self.bar._band_drag = None


class ResizeHandle(QWidget):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.bar._drag = "resize"
            self.bar._drag_origin = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        self.bar.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.bar.mouseReleaseEvent(event)


class Taskbar(QWidget):
    start_requested = Signal()

    def __init__(self, backend, shell):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setWindowTitle("horyzont-taskbar")
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDock, True)
        # Animacja odbywa się wewnątrz stałej powierzchni Wayland; ukryty obszar ma alfę 0.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.collapsed = False
        self._slide = 0.0
        self._drag = None
        self._band_drag = None
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._slide_changed)
        self.setMouseTracking(True)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._maybe_collapse)
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self.expand)
        self.shell = shell
        self.backend = backend
        self.buttons = {}  # uid -> TaskButton
        self.start = StartButton(self)
        self.start.clicked.connect(self.start_requested.emit)
        self.quick = QuickLaunch(self)
        self.task_area = QWidget(self)
        self.task_area.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.quick_grip = BandGrip(self, "quick")
        self.tasks_grip = BandGrip(self, "tasks")
        self.resize_handle = ResizeHandle(self)
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
        QTimer.singleShot(1500, self.apply_autohide)

    # ------------------------------------------------------------ autoukrywanie
    STRIP = 2

    def autohide(self):
        return bool(config.get("taskbar_autohide", False))

    def apply_autohide(self):
        if self.autohide():
            if not self.underMouse():
                self.collapse()
        else:
            self._hide_timer.stop()
            self.expand()

    def _slide_changed(self, value):
        self._slide = float(value)
        self.relayout()
        from PySide6.QtGui import QRegion
        visible = self.rect().translated(self._offset()).intersected(self.rect())
        if self.windowHandle() is not None:
            self.windowHandle().setMask(QRegion(visible) if self._slide else QRegion())
        self.update()

    def _offset(self):
        extent = self.width() if taskbarlayout.vertical() else self.height()
        d = round((extent-self.STRIP) * self._slide)
        return {"bottom": QPoint(0, d), "top": QPoint(0, -d), "left": QPoint(-d, 0), "right": QPoint(d, 0)}[taskbarlayout.edge()]

    def _animate(self, hidden):
        self.collapsed = hidden
        self._animation.stop()
        self._animation.setDuration(max(1, round(200 * abs(float(hidden)-self._slide))))
        self._animation.setStartValue(self._slide)
        self._animation.setEndValue(float(hidden))
        self._animation.start()

    def collapse(self):
        if self.autohide() and not self.collapsed:
            self._animate(True)

    def expand(self):
        if self.collapsed or self._slide:
            self._animate(False)

    def _maybe_collapse(self):
        """Chowa pasek, gdy kursor go opuścił i nic z niego nie jest otwarte (menu Start, menu kontekstowe)."""
        if not self.autohide() or self.collapsed:
            return
        busy = QApplication.activePopupWidget() is not None
        sm = getattr(self.shell, "start_menu", None)
        if sm is not None and sm.isVisible():
            busy = True
        if busy or self.geometry().contains(QCursor.pos()):
            self._hide_timer.start(700)
            return
        self.collapse()

    def enterEvent(self, e):
        self._hide_timer.stop()
        if self.collapsed:
            self._show_timer.start(120)

    def leaveEvent(self, e):
        self._show_timer.stop()
        if self.autohide():
            self._hide_timer.start(700)

    def reveal(self, hold_ms=0):
        """Pokazuje schowany pasek (np. po naciśnięciu klawisza Windows); po czasie chowa go ponownie."""
        if not self.autohide():
            return
        self.expand()
        self._hide_timer.start(max(1500, hold_ms))

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
        self.shell.place_taskbar()
        self.relayout()
        self.apply_autohide()

    def resizeEvent(self, e):
        self.relayout()

    def relayout(self):
        if not hasattr(self, "tray"):
            return
        base = current().metrics["taskbar_h"]
        locked = config.get("taskbar_locked", True)
        grip = 0 if locked else 7
        offset = self._offset()
        def place(widget, rect):
            widget.setGeometry(rect.translated(offset))
        quick = bool(config.get("taskbar_quick_launch", False) and self.quick.items)
        sw = self.start.sizeHint().width()
        self.start.show()
        self.task_area.show()
        self.tray.show()
        self.quick.setVisible(quick)
        self.quick_grip.setVisible(quick and not locked)
        self.tasks_grip.setVisible(not locked)
        if taskbarlayout.vertical():
            place(self.start, QRect(0, 0, self.width(), base))
            th = self.tray.sizeHint().height()
            place(self.tray, QRect(0, self.height()-th, self.width(), th))
            y = base+4
            qh = 0
            if quick:
                cols = max(1, (self.width()-grip-4)//24)
                natural = max(base, ((len(self.quick.items)+cols-1)//cols)*24)
                qh = max(base, min(self.height()//3, int(config.get("taskbar_quick_height", natural))))
                qy = self.height()-th-qh-4 if config.get("taskbar_quick_after", False) else y
                place(self.quick_grip, QRect(0, qy, grip, qh))
                place(self.quick, QRect(grip, qy, self.width()-grip, qh))
                if not config.get("taskbar_quick_after", False):
                    y += qh+4
            bottom = self.height()-th-(qh+4 if quick and config.get("taskbar_quick_after", False) else 0)
            place(self.tasks_grip, QRect(0, y, grip, max(0, bottom-y)))
            place(self.task_area, QRect(grip, y, self.width()-grip, max(0, bottom-y)))
        else:
            place(self.start, QRect(0, 0, sw, base))
            tw = self.tray.sizeHint().width()
            place(self.tray, QRect(self.width()-tw, 0, tw, self.height()))
            rows = max(1, self.height() // base)
            qr = min(rows-1, max(0, int(config.get("taskbar_quick_row", 0))))
            qw = min(max(24, int(config.get("taskbar_quick_width", self.quick.sizeHint().width()))), max(24, self.width()-sw-tw-64)) if quick else 0
            after = bool(config.get("taskbar_quick_after", False))
            x, right = sw+4, self.width()-tw-4
            qx = right-qw-grip if after else x
            if quick:
                place(self.quick_grip, QRect(qx, qr*base, grip, base))
                place(self.quick, QRect(qx+grip, qr*base, qw, base))
            # Sekcje mogą leżeć obok siebie albo w osobnych rzędach.
            tx = x + (qw+grip+4 if quick and qr == 0 and not after else 0)
            tright = qx-4 if quick and qr == 0 and after else right
            place(self.tasks_grip, QRect(tx, 0, grip, base))
            self._task_rows = rows if not quick or qr == 0 else qr
            place(self.task_area, QRect(tx+grip, 0, max(0, tright-tx-grip), self._task_rows*base))
        edge = taskbarlayout.edge()
        handle = {"bottom": QRect(0, 0, self.width(), 3), "top": QRect(0, self.height()-3, self.width(), 3),
                  "left": QRect(self.width()-3, 0, 3, self.height()), "right": QRect(0, 0, 3, self.height())}[edge]
        place(self.resize_handle, handle)
        self.resize_handle.setVisible(not locked)
        self.resize_handle.setCursor(Qt.SizeHorCursor if taskbarlayout.vertical() else Qt.SizeVerCursor)
        self.resize_handle.raise_()
        self._layout_buttons()
        if hasattr(self, "balloons"):
            self.balloons.reposition()

    def move_band(self, name, pos):
        if config.get("taskbar_locked", True):
            return
        if taskbarlayout.vertical():
            if name == "quick":
                config.set("taskbar_quick_after", pos.y() > self.height()//2)
            else:
                extent = self.height()-self.tray.height()-pos.y() if config.get("taskbar_quick_after", False) else pos.y()-self.start.height()
                config.set("taskbar_quick_height", max(24, extent))
            self.relayout()
            return
        base = current().metrics["taskbar_h"]
        if name == "quick":
            config.set("taskbar_quick_after", pos.x() > self.width()//2)
            row = max(0, min(self.height()//base-1, pos.y()//base))
            config.set("taskbar_quick_row", row)
        else:
            if config.get("taskbar_quick_after", False):
                width = self.width()-self.tray.width()-pos.x()-8
            else:
                width = pos.x()-self.start.width()-12
            config.set("taskbar_quick_width", max(24, width))
        self.relayout()

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
        rows = max(1, area.height() // current().metrics["taskbar_h"])
        cols = max(1, (count+rows-1)//rows)
        if taskbarlayout.vertical():
            cols, rows = 1, max(1, count)
        w = min(maxw, max(24, (area.width()-2)//cols))
        x = 0
        shown = set()
        for items in groups:
            lead = items[0]
            btn = self.buttons.get(lead.uid)
            if btn is None:
                continue
            btn.group = items if len(items) > 1 else None
            col, row = (x // rows, x % rows) if not taskbarlayout.vertical() else (0, x)
            y = row * current().metrics["taskbar_h"] + (current().metrics["taskbar_h"]-bh)//2
            btn.setGeometry(col*w, y, max(24, w-3), bh)
            btn.show()
            btn.update()
            shown.add(lead.uid)
            x += 1
        for uid, b in self.buttons.items():
            if uid not in shown:
                b.hide()

    # ------------------------------------------------------------ okna
    def _added(self, tl):
        self.update_fullscreen()
        if tl.title in SHELL_TITLES:
            return
        b = TaskButton(self, tl)
        self.buttons[tl.uid] = b
        self._layout_buttons()

    def _removed(self, tl):
        QTimer.singleShot(0, self.update_fullscreen)
        b = self.buttons.pop(tl.uid, None)
        if b:
            b.deleteLater()
        self._layout_buttons()

    def update_fullscreen(self):
        """Gdy aktywne okno jest na pełnym ekranie (np. film z YouTube), pasek zadań się chowa."""
        full = any(t.activated and t.fullscreen and not t.minimized for t in self.backend.toplevels
                   if t.title not in SHELL_TITLES)
        if full and not self.fullscreen_hidden:
            self.fullscreen_hidden = True
            self.hide()
        elif not full and self.fullscreen_hidden:
            self.fullscreen_hidden = False
            self.show()

    fullscreen_hidden = False

    def _changed(self, tl):
        self.update_fullscreen()
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
        elif e.button() == Qt.LeftButton and not config.get("taskbar_locked", True):
            pos = e.position().toPoint()
            edge = taskbarlayout.edge()
            border = {"bottom": pos.y() < 4, "top": pos.y() >= self.height()-4,
                      "left": pos.x() >= self.width()-4, "right": pos.x() < 4}[edge]
            self._drag = "resize" if border else "dock"
            self._drag_origin = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if not self._drag or config.get("taskbar_locked", True):
            return
        g = e.globalPosition().toPoint()
        screen = self.shell.screen_geometry()
        if self._drag == "resize":
            edge = taskbarlayout.edge()
            size = {"bottom": screen.bottom()-g.y()+1, "top": g.y()-screen.top()+1,
                    "left": g.x()-screen.left()+1, "right": screen.right()-g.x()+1}[edge]
            if taskbarlayout.vertical():
                config.set("taskbar_width", max(80, min(screen.width()//2, size)))
            else:
                config.set("taskbar_rows", max(1, min(6, round(size/current().metrics["taskbar_h"])) ))
            self.shell.place_taskbar()
        elif (g-self._drag_origin).manhattanLength() > QApplication.startDragDistance():
            distances = {"left": abs(g.x()-screen.left()), "right": abs(screen.right()-g.x()),
                         "top": abs(g.y()-screen.top()), "bottom": abs(screen.bottom()-g.y())}
            config.set("taskbar_edge", min(distances, key=distances.get))
            self.shell.place_taskbar()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self.shell.update_placement(reconfigure=True)
            if os.environ.get("LABWC_PID"):
                # Wayland stosuje regułę MoveTo podczas mapowania powierzchni.
                self.shell.remap_shell_windows()

    def context_menu(self, gpos, tray=False):
        m = QMenu(self)
        if tray:
            m.addAction(tr("tb_adjust_datetime")).triggered.connect(lambda: launcher.start_builtin("control", ["datetime"]))
            m.addAction(tr("tray_customize")).triggered.connect(
                lambda: launcher.start_builtin("control", ["taskbar", "customize"]))
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
        edges = m.addMenu(plain("tb_position"))
        edges.setEnabled(not config.get("taskbar_locked", True))
        for value in ("bottom", "top", "left", "right"):
            action = edges.addAction(plain("tb_edge_" + value))
            action.setCheckable(True)
            action.setChecked(taskbarlayout.edge() == value)
            action.triggered.connect(lambda _=False, v=value: self._dock(v))
        m.addSeparator()
        lock = m.addAction(tr("tb_lock"))
        lock.setCheckable(True)
        lock.setChecked(config.get("taskbar_locked", True))
        lock.toggled.connect(lambda v: config.set("taskbar_locked", v))
        m.addAction(tr("tb_properties")).triggered.connect(lambda: launcher.start_builtin("control", ["taskbar"]))
        m.exec(gpos - QPoint(0, m.sizeHint().height()))

    def _dock(self, edge):
        config.set("taskbar_edge", edge)
        self.shell.place_taskbar()
        self.shell.update_placement(reconfigure=True)
        if os.environ.get("LABWC_PID"):
            self.shell.remap_shell_windows()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.translate(self._offset())
        current().draw_taskbar(p, self.rect())
