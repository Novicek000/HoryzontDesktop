"""org.freedesktop.FileManager1 — „Pokaż w folderze” z Firefoksa, Chromium, Thunderbirda, portali Flatpak itd.

Bez tej usługi D-Bus uruchamia przez aktywację Nautilusa (GNOME Pliki), nawet gdy domyślnym programem do folderów
jest Eksplorator Horyzontu.
"""
import os
import sys
from urllib.parse import unquote, urlparse

from ..common import dbus
from ..common.launcher import start_builtin

BUS_NAME = "org.freedesktop.FileManager1"
PATH = "/org/freedesktop/FileManager1"
IFACE = "org.freedesktop.FileManager1"

INTROSPECT = """<interface name="org.freedesktop.FileManager1">
<method name="ShowFolders"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
<method name="ShowItems"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
<method name="ShowItemProperties"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
</interface>"""


def uri_to_path(uri):
    if uri.startswith("file://"):
        return unquote(urlparse(uri).path) or "/"
    if "://" in uri:
        return None            # sftp://, smb:// itd. — nieobsługiwane lokalnie
    return os.path.expanduser(uri)


class FileManager1:
    INTROSPECT = INTROSPECT

    def __init__(self, bus):
        self.bus = bus
        self.ok = False
        bus.export(PATH, IFACE, self)
        try:
            self.ok = bus.request_name(BUS_NAME, 0x6)
        except dbus.DBusError as e:
            print("horyzont: FileManager1:", e, file=sys.stderr)

    def properties(self):
        return {}

    def handle(self, member, args, msg):
        uris = list(args[0]) if args else []
        paths = [p for p in (uri_to_path(u) for u in uris) if p]
        if member == "ShowFolders":
            for p in paths:
                start_builtin("explorer", [p])
            return None
        if member == "ShowItems":
            if paths:
                start_builtin("explorer", ["--select"] + paths)
            return None
        if member == "ShowItemProperties":
            if paths:
                start_builtin("explorer", ["--properties"] + paths)
            return None
        raise dbus.DBusError("org.freedesktop.DBus.Error.UnknownMethod", member)
