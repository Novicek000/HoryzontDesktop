"""Serwer powiadomień org.freedesktop.Notifications — powiadomienia programów pokazywane jako dymki w zasobniku.

Działa z notify-send, przeglądarkami (Firefox, Chromium), komunikatorami, Thunderbirdem, Steamem, dnf/PackageKit itd.
"""
import os

from PySide6.QtGui import QImage, QPixmap

from ..common import dbus
from ..theme import iconcache
from .balloon import CLOSED_BY_CALL

BUS_NAME = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
IFACE = "org.freedesktop.Notifications"
DEFAULT_TIMEOUT = 10000   # ms, jak klasyczne dymki

INTROSPECT = """<interface name="org.freedesktop.Notifications">
<method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/>
<arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/>
<arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="out"/></method>
<method name="CloseNotification"><arg type="u" direction="in"/></method>
<method name="GetCapabilities"><arg type="as" direction="out"/></method>
<method name="GetServerInformation"><arg type="s" direction="out"/><arg type="s" direction="out"/>
<arg type="s" direction="out"/><arg type="s" direction="out"/></method>
<signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
<signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
<signal name="ActivationToken"><arg type="u"/><arg type="s"/></signal>
</interface>"""


def image_from_data(data):
    """Podpowiedź image-data: (szerokość, wysokość, krok wiersza, alfa, bity, kanały, bajty)."""
    try:
        w, h, stride, alpha, _bits, channels, raw = dbus.unwrap(data)
        fmt = QImage.Format_RGBA8888 if (alpha or channels == 4) else QImage.Format_RGB888
        img = QImage(bytes(raw), w, h, stride, fmt).copy()
        return QPixmap.fromImage(img) if not img.isNull() else None
    except Exception:
        return None


def _desktop_icon(desktop_id):
    if not desktop_id:
        return None
    try:
        from ..common.desktopentry import find_for_app_id
        e = find_for_app_id(desktop_id)
        if e and e.icon:
            return iconcache.find_named_icon(e.icon)
    except Exception:
        pass
    return None


class NotificationServer:
    INTROSPECT = INTROSPECT

    def __init__(self, bus, queue, tray=None):
        self.bus = bus
        self.queue = queue
        self.tray = tray
        self._next = 1
        self.active = set()
        self.history = []          # ostatnie powiadomienia (do ewentualnego podglądu)
        self.ok = False
        bus.export(PATH, IFACE, self)
        try:
            # 0x2 REPLACE_EXISTING | 0x4 DO_NOT_QUEUE — przejmujemy nazwę, jeśli inny demon na to pozwala
            self.ok = bus.request_name(BUS_NAME, 0x6)
        except dbus.DBusError as e:
            print("horyzont: powiadomienia:", e)
        if not self.ok:
            print("horyzont: inny program obsługuje już powiadomienia (np. mako/dunst) — dymki Horyzontu wyłączone")

    def properties(self):
        return {}

    # ------------------------------------------------------------ D-Bus
    def handle(self, member, args, msg):
        if member == "GetCapabilities":
            return "as", [["body", "body-markup", "body-hyperlinks", "actions", "icon-static", "persistence", "sound"]]
        if member == "GetServerInformation":
            from .. import config
            return "ssss", ["Horyzont", "Horyzont", config.VERSION, "1.2"]
        if member == "CloseNotification":
            nid = int(args[0])
            if not self.queue.close_id(nid, CLOSED_BY_CALL) and nid in self.active:
                self._closed(nid, CLOSED_BY_CALL)
            return None
        if member == "Notify":
            return "u", [self.notify(*args)]
        raise dbus.DBusError("org.freedesktop.DBus.Error.UnknownMethod", member)

    def notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
        hints = hints or {}
        h = {k: dbus.unwrap(v) for k, v in hints.items() if k not in ("image-data", "image_data", "icon_data")}
        if replaces_id and replaces_id in self.active:
            nid = replaces_id
        else:
            nid = self._next
            self._next += 1
        self.active.add(nid)
        # ikona: image-data > image-path > app_icon > ikona programu z pliku .desktop
        icon = None
        for key in ("image-data", "image_data", "icon_data"):
            if key in hints:
                icon = image_from_data(hints[key])
                if icon:
                    break
        if icon is None:
            for path in (h.get("image-path"), h.get("image_path"), app_icon):
                if path:
                    ic = iconcache.find_named_icon(path)
                    if ic:
                        icon = ic
                        break
        if icon is None:
            icon = _desktop_icon(h.get("desktop-entry")) or _desktop_icon(app_name.lower() if app_name else "")
        urgency = int(h.get("urgency", 1) or 1) if str(h.get("urgency", 1)).isdigit() else 1
        if icon is None:
            icon = "warning" if urgency >= 2 else "info"
        pairs = [(actions[i], actions[i + 1]) for i in range(0, len(actions) - 1, 2)]
        if expire_timeout is None or expire_timeout < 0:
            timeout = None if urgency >= 2 else DEFAULT_TIMEOUT
        elif expire_timeout == 0:
            timeout = None
        else:
            timeout = max(4000, expire_timeout)
        title = summary or app_name or "Powiadomienie"
        text = body or ""
        if not summary and app_name:
            title = app_name
        entry = {
            "id": nid, "title": title, "text": text, "icon": icon, "actions": pairs, "markup": True,
            "timeout_ms": timeout, "urgent": urgency >= 2,
            "on_click": (lambda n=nid, p=pairs: self._invoke(n, "default") if any(k == "default" for k, _ in p) else None),
            "on_action": lambda k, n=nid: self._invoke(n, k),
            "on_closed": lambda reason, n=nid: self._closed(n, reason),
            "sound": not h.get("suppress-sound", False),
            "sound_file": h.get("sound-file") if isinstance(h.get("sound-file"), str) and os.path.isfile(h.get("sound-file")) else None,
            "anchor": (lambda a=app_name, d=h.get("desktop-entry"): self.tray.anchor_for_app(a, d)) if self.tray else None,
        }
        self.history.append((app_name, title, text))
        del self.history[:-50]
        self.queue.show(entry)
        return nid

    def _invoke(self, nid, key):
        if nid not in self.active:
            return
        self.bus.emit(PATH, IFACE, "ActionInvoked", "us", (nid, key))

    def _closed(self, nid, reason):
        if nid not in self.active:
            return
        self.active.discard(nid)
        self.bus.emit(PATH, IFACE, "NotificationClosed", "uu", (nid, int(reason)))
