"""Ikony programów w zasobniku: StatusNotifierWatcher + Host (protokół StatusNotifierItem / AppIndicator)
oraz menu com.canonical.dbusmenu.

Programy, które „chowają się do zasobnika” (Discord, Steam, Telegram, Nextcloud, KeePassXC, OBS, programy Qt
z QSystemTrayIcon, Electron, libappindicator/ayatana), rejestrują tu swoje ikony; powłoka rysuje je w obszarze
powiadomień obok zegara.
"""
import re
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QMenu

from ..common import dbus
from ..common.dbus import Variant
from ..theme import iconcache

WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_NAMES = ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher")
ITEM_IFACES = ("org.kde.StatusNotifierItem", "org.freedesktop.StatusNotifierItem")
MENU_IFACE = "com.canonical.dbusmenu"
DBUS = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")


def _watcher_introspect(iface):
    return f"""<interface name="{iface}">
<method name="RegisterStatusNotifierItem"><arg name="service" type="s" direction="in"/></method>
<method name="RegisterStatusNotifierHost"><arg name="service" type="s" direction="in"/></method>
<property name="RegisteredStatusNotifierItems" type="as" access="read"/>
<property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
<property name="ProtocolVersion" type="i" access="read"/>
<signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
<signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
<signal name="StatusNotifierHostRegistered"/>
<signal name="StatusNotifierHostUnregistered"/>
</interface>"""


def icon_from_pixmaps(pixmaps):
    """IconPixmap: lista (szerokość, wysokość, bajty ARGB32 w kolejności sieciowej)."""
    ic = QIcon()
    for item in pixmaps or []:
        try:
            w, h, data = item
            if w <= 0 or h <= 0 or len(data) < w * h * 4:
                continue
            src = bytes(data[:w * h * 4])
            b = bytearray(len(src))
            # A R G B (big-endian) -> B G R A (QImage.Format_ARGB32 w pamięci little-endian)
            b[0::4], b[1::4], b[2::4], b[3::4] = src[3::4], src[2::4], src[1::4], src[0::4]
            img = QImage(bytes(b), w, h, w * 4, QImage.Format_ARGB32).copy()
            ic.addPixmap(QPixmap.fromImage(img))
        except Exception:
            continue
    return None if ic.isNull() else ic


def _strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    import html
    return html.unescape(s).strip()


class SniItem:
    __slots__ = ("key", "service", "owner", "path", "iface", "props", "icon", "tip", "status", "menu_path",
                 "item_is_menu", "registered_at", "_refresh", "id", "title")

    def __init__(self, key, service, owner, path):
        self.key, self.service, self.owner, self.path = key, service, owner, path
        self.iface = ITEM_IFACES[0]
        self.props = {}
        self.icon = None
        self.tip = ""
        self.status = "Active"
        self.menu_path = None
        self.item_is_menu = False
        self.registered_at = time.monotonic()
        self._refresh = None
        self.id = ""
        self.title = ""

    @property
    def visible(self):
        return self.status != "Passive" and self.icon is not None


class SniHost(QObject):
    """Właściciel org.kde.StatusNotifierWatcher i jednocześnie host wyświetlający ikony."""

    changed = Signal()

    def __init__(self, bus, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.items = {}            # klucz -> SniItem
        self.own_watcher = False
        self.hosts = set()
        bus.add_match("type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'")
        bus.on_signal(self._name_owner_changed, sender="org.freedesktop.DBus", member="NameOwnerChanged")
        for iface in ITEM_IFACES:
            bus.add_match(f"type='signal',interface='{iface}'")
            bus.on_signal(self._item_signal, interface=iface)
        bus.add_match(f"type='signal',interface='{MENU_IFACE}'")
        for name in WATCHER_NAMES:
            bus.export(WATCHER_PATH, name, _WatcherIface(self, name))
        try:
            got = [bus.request_name(n, 0x4) for n in WATCHER_NAMES]
            self.own_watcher = got[0]
        except dbus.DBusError as e:
            print("horyzont: zasobnik:", e)
        host_name = f"org.kde.StatusNotifierHost-{_pid()}"
        try:
            bus.request_name(host_name, 0x4)
        except dbus.DBusError:
            pass
        if self.own_watcher:
            self.hosts.add(host_name)
            for n in WATCHER_NAMES:
                bus.emit(WATCHER_PATH, n, "StatusNotifierHostRegistered")
        else:
            # zasobnikiem zarządza już inny program — jesteśmy tylko hostem
            print("horyzont: StatusNotifierWatcher należy do innego programu — działam jako host")
            bus.add_match("type='signal',interface='org.kde.StatusNotifierWatcher'")
            bus.on_signal(lambda m: self._ext_registered(m.body[0]), interface="org.kde.StatusNotifierWatcher",
                          member="StatusNotifierItemRegistered")
            bus.on_signal(lambda m: self._remove_key(m.body[0]), interface="org.kde.StatusNotifierWatcher",
                          member="StatusNotifierItemUnregistered")
            bus.call("org.kde.StatusNotifierWatcher", WATCHER_PATH, "org.kde.StatusNotifierWatcher",
                     "RegisterStatusNotifierHost", "s", (host_name,))
            bus.get_property("org.kde.StatusNotifierWatcher", WATCHER_PATH, "org.kde.StatusNotifierWatcher",
                             "RegisteredStatusNotifierItems",
                             lambda keys: [self._ext_registered(k) for k in keys or []])

    # ------------------------------------------------------------ rejestracja
    def register(self, arg, sender):
        if arg.startswith("/"):
            service, path = sender, arg
        else:
            service, path = arg, "/StatusNotifierItem"
        if service.startswith(":"):
            self._add(service, service, path)
        else:
            self.bus.call(*DBUS, "GetNameOwner", "s", (service,),
                          lambda body, s=service, p=path: self._add(s, body[0], p),
                          lambda *_: self._add(service, sender, path))

    def _ext_registered(self, key):
        i = key.find("/")
        service, path = (key[:i], key[i:]) if i > 0 else (key, "/StatusNotifierItem")
        if service.startswith(":"):
            self._add(service, service, path)
        else:
            self.bus.call(*DBUS, "GetNameOwner", "s", (service,),
                          lambda body, s=service, p=path: self._add(s, body[0], p), lambda *_: None)

    def _add(self, service, owner, path):
        key = service + path
        if key in self.items:
            self._refresh(self.items[key])
            return
        it = SniItem(key, service, owner, path)
        self.items[key] = it
        for n in WATCHER_NAMES if self.own_watcher else ():
            self.bus.emit(WATCHER_PATH, n, "StatusNotifierItemRegistered", "s", (key,))
        self._refresh(it)

    def _remove_key(self, key):
        it = self.items.pop(key, None)
        if it is None:
            return
        for n in WATCHER_NAMES if self.own_watcher else ():
            self.bus.emit(WATCHER_PATH, n, "StatusNotifierItemUnregistered", "s", (key,))
        self.changed.emit()

    def _name_owner_changed(self, m):
        name, old, new = m.body
        if new:
            return
        for key, it in list(self.items.items()):
            if it.owner == old or it.service == name:
                self._remove_key(key)
        self.hosts.discard(name)

    # ------------------------------------------------------------ właściwości
    def _refresh(self, it, delay=0):
        if delay:
            if it._refresh is None:
                t = QTimer(self)
                t.setSingleShot(True)
                t.timeout.connect(lambda i=it: self._refresh(i))
                it._refresh = t
            it._refresh.start(delay)
            return
        self.bus.get_all(it.owner, it.path, it.iface, lambda props, i=it: self._got_props(i, props),
                         lambda name, msg, i=it: self._props_failed(i, name))

    def _props_failed(self, it, name):
        if it.iface == ITEM_IFACES[0]:
            it.iface = ITEM_IFACES[1]
            self._refresh(it)
        elif it.key in self.items:
            print("horyzont: zasobnik: nie można odczytać", it.key, name)

    def _got_props(self, it, props):
        if it.key not in self.items:
            return
        it.props = props
        it.status = props.get("Status", "Active") or "Active"
        it.id = props.get("Id", "") or ""
        it.title = props.get("Title", "") or ""
        menu = props.get("Menu")
        it.menu_path = menu if menu and menu != "/" else None
        it.item_is_menu = bool(props.get("ItemIsMenu", False))
        theme_path = props.get("IconThemePath") or ""
        extra = [theme_path] if theme_path else []
        icon = None
        if it.status == "NeedsAttention":
            icon = iconcache.find_named_icon(props.get("AttentionIconName", ""), extra) or \
                icon_from_pixmaps(props.get("AttentionIconPixmap"))
        if icon is None:
            icon = iconcache.find_named_icon(props.get("IconName", ""), extra) or icon_from_pixmaps(props.get("IconPixmap"))
        if icon is None:
            icon = iconcache.icon("program")
        it.icon = icon
        tip = props.get("ToolTip")
        text = ""
        if isinstance(tip, (list, tuple)) and len(tip) >= 4:
            title, desc = _strip_html(tip[2]), _strip_html(tip[3])
            text = title + ("\n" + desc if desc and desc != title else "")
        it.tip = text or it.title or it.id or it.service
        self.changed.emit()

    def _item_signal(self, m):
        it = self._find(m.sender, m.path)
        if it is None:
            return
        if m.member == "NewStatus" and m.body:
            it.status = m.body[0]
        # Steam, Discord i inne potrafią wysyłać dziesiątki sygnałów na sekundę — zbieramy je
        self._refresh(it, 120)

    def _find(self, owner, path):
        for it in self.items.values():
            if it.owner == owner and it.path == path:
                return it
        return None

    def visible_items(self):
        return sorted((i for i in self.items.values() if i.visible), key=lambda i: i.registered_at)

    # ------------------------------------------------------------ interakcja
    def activate(self, it, gpos):
        if it.item_is_menu and it.menu_path:
            return self.show_menu(it, gpos)

        def failed(name, msg):
            # libappindicator/ayatana nie obsługują Activate — wtedy pokazujemy menu
            if it.menu_path:
                self.show_menu(it, gpos)
        self.bus.call(it.owner, it.path, it.iface, "Activate", "ii", (gpos.x(), gpos.y()), lambda *_: None, failed)

    def secondary(self, it, gpos):
        self.bus.call(it.owner, it.path, it.iface, "SecondaryActivate", "ii", (gpos.x(), gpos.y()), lambda *_: None,
                      lambda *_: None)

    def scroll(self, it, delta, orientation="vertical"):
        self.bus.call(it.owner, it.path, it.iface, "Scroll", "is", (int(delta), orientation), lambda *_: None,
                      lambda *_: None)

    def context(self, it, gpos):
        if it.menu_path:
            return self.show_menu(it, gpos)
        self.bus.call(it.owner, it.path, it.iface, "ContextMenu", "ii", (gpos.x(), gpos.y()), lambda *_: None,
                      lambda *_: None)

    def show_menu(self, it, gpos, parent=None):
        menu = DbusMenu(self.bus, it.owner, it.menu_path, parent)
        if not menu.load():
            self.bus.call(it.owner, it.path, it.iface, "ContextMenu", "ii", (gpos.x(), gpos.y()), lambda *_: None,
                          lambda *_: None)
            return
        menu.exec(gpos)
        menu.closed_event()
        menu.deleteLater()


class _WatcherIface:
    def __init__(self, host, name):
        self.host = host
        self.name = name
        self.INTROSPECT = _watcher_introspect(name)

    def properties(self):
        return {
            "RegisteredStatusNotifierItems": ("as", list(self.host.items.keys())),
            "IsStatusNotifierHostRegistered": ("b", True),
            "ProtocolVersion": ("i", 0),
        }

    def handle(self, member, args, msg):
        if member == "RegisterStatusNotifierItem":
            self.host.register(args[0], msg.sender)
            return None
        if member == "RegisterStatusNotifierHost":
            self.host.hosts.add(args[0])
            self.host.bus.emit(WATCHER_PATH, self.name, "StatusNotifierHostRegistered")
            return None
        raise dbus.DBusError("org.freedesktop.DBus.Error.UnknownMethod", member)


def _pid():
    import os
    return os.getpid()


# ---------------------------------------------------------------- dbusmenu
def _label(text):
    # „_” oznacza mnemonik w dbusmenu, „__” to dosłowny podkreślnik; w Qt odpowiednikiem jest „&”
    text = (text or "").replace("&", "&&")
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "_":
            if i + 1 < len(text) and text[i + 1] == "_":
                out.append("_")
                i += 2
                continue
            out.append("&")
        else:
            out.append(c)
        i += 1
    return "".join(out)


class DbusMenu(QMenu):
    def __init__(self, bus, dest, path, parent=None, root_id=0):
        super().__init__(parent)
        self.bus, self.dest, self.path = bus, dest, path
        self.root_id = root_id

    def load(self):
        try:
            try:
                self.bus.call_sync(self.dest, self.path, MENU_IFACE, "AboutToShow", "i", (self.root_id,), timeout=0.5)
            except dbus.DBusError:
                pass
            self._event(self.root_id, "opened")
            body = self.bus.call_sync(self.dest, self.path, MENU_IFACE, "GetLayout", "iias",
                                      (self.root_id, -1, []), timeout=1.5)
        except (dbus.DBusError, OSError) as e:
            print("horyzont: menu zasobnika:", e)
            return False
        _rev, layout = body
        self.clear()
        self._fill(self, layout)
        return not self.isEmpty()

    def _fill(self, menu, node):
        _id, _props, children = node
        group = None
        for ch in children:
            ch = ch.value if isinstance(ch, Variant) else ch
            cid, props, sub = ch
            props = dbus.unwrap(props)
            if not props.get("visible", True):
                continue
            if props.get("type") == "separator":
                menu.addSeparator()
                continue
            label = _label(props.get("label", ""))
            icon = None
            if props.get("icon-data"):
                pm = QPixmap()
                if pm.loadFromData(bytes(props["icon-data"])):
                    icon = QIcon(pm)
            elif props.get("icon-name"):
                icon = iconcache.find_named_icon(props["icon-name"])
            if sub or props.get("children-display") == "submenu":
                sm = menu.addMenu(label)
                if icon:
                    sm.setIcon(icon)
                sm.setEnabled(props.get("enabled", True))
                self._fill(sm, ch)
                sm.aboutToShow.connect(lambda i=cid: self._event(i, "opened"))
                continue
            a = menu.addAction(label)
            if icon:
                a.setIcon(icon)
            a.setEnabled(props.get("enabled", True))
            tt = props.get("toggle-type", "")
            if tt in ("checkmark", "radio"):
                a.setCheckable(True)
                a.setChecked(props.get("toggle-state", 0) == 1)
                if tt == "radio":
                    from PySide6.QtGui import QActionGroup
                    if group is None:
                        group = QActionGroup(menu)
                    group.addAction(a)
            else:
                group = None
            a.triggered.connect(lambda _=False, i=cid: self._event(i, "clicked"))

    def _event(self, item_id, kind):
        try:
            self.bus.call(self.dest, self.path, MENU_IFACE, "Event", "isvu",
                          (item_id, kind, Variant("i", 0), int(time.time()) & 0xffffffff), lambda *_: None,
                          lambda *_: None)
        except OSError:
            pass

    def closed_event(self):
        self._event(self.root_id, "closed")
