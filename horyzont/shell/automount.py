"""Montowanie wymiennych nośników przez UDisks2 w aktywnej sesji użytkownika."""
import sys

from PySide6.QtCore import QTimer

from .. import config
from ..common import dbus

DEST = "org.freedesktop.UDisks2"
ROOT = "/org/freedesktop/UDisks2"
BLOCK = DEST + ".Block"
FILESYSTEM = DEST + ".Filesystem"
DRIVE = DEST + ".Drive"
MANAGER = "org.freedesktop.DBus.ObjectManager"


def candidates(objects):
    """Tylko niezamontowane systemy plików na USB/nośnikach wymiennych.

    Pomijamy dyski systemowe, loop, swap, zablokowane LUKS i wpisy fstab.
    O uprawnieniach i opcjach montowania decyduje UDisks2/polkit.
    """
    for path, interfaces in objects.items():
        block = interfaces.get(BLOCK, {})
        fs = interfaces.get(FILESYSTEM)
        if fs is None or fs.get("MountPoints") or block.get("IdUsage") != "filesystem":
            continue
        if block.get("HintIgnore", False) or block.get("HintSystem", True) or not block.get("HintAuto", True):
            continue
        if any(item[0] == "fstab" for item in block.get("Configuration", ())):
            continue
        drive = objects.get(block.get("Drive"), {}).get(DRIVE, {})
        if not (drive.get("Removable") or drive.get("MediaRemovable") or drive.get("ConnectionBus") == "usb"):
            continue
        yield path


class Automounter:
    def __init__(self, session_bus):
        # Powłoka może być restartowana; tylko jeden zarządca na sesję D-Bus.
        self.active = session_bus.request_name("org.horyzont.Automount")
        if not self.active:
            return
        self.bus = dbus.Connection("system")
        self.bus.attach_qt()
        self.attempted = set()
        self.reading = False
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.scan)
        for interface, member in ((MANAGER, "InterfacesAdded"), (MANAGER, "InterfacesRemoved"),
                                  ("org.freedesktop.DBus.Properties", "PropertiesChanged")):
            self.bus.add_match(f"type='signal',sender='{DEST}',interface='{interface}',member='{member}'")
            self.bus.on_signal(self._changed, interface=interface, member=member)
        self.scan()

    def _changed(self, message):
        if not message.path.startswith(ROOT + "/") and message.path != ROOT:
            return
        if message.member == "InterfacesRemoved" and BLOCK in message.body[1]:
            self.attempted.discard(message.body[0])
        self.timer.start()

    def scan(self):
        if not config.get("automount_removable", True):
            return
        if self.reading:
            self.timer.start()
            return
        self.reading = True
        self.bus.call(DEST, ROOT, MANAGER, "GetManagedObjects", callback=self._objects, error=self._scan_error)

    def _scan_error(self, error):
        self.reading = False
        print("horyzont: odczyt nośników:", error, file=sys.stderr)

    def _objects(self, body):
        self.reading = False
        objects = dbus.unwrap(body[0])
        self.attempted.intersection_update(objects)
        self.attempted.update(path for path, interfaces in objects.items()
                              if interfaces.get(FILESYSTEM, {}).get("MountPoints"))
        for path in candidates(objects):
            if path in self.attempted:
                continue
            # Nie montuj ponownie po świadomym odmontowaniu przez użytkownika.
            self.attempted.add(path)
            self.bus.call(DEST, path, FILESYSTEM, "Mount", "a{sv}",
                          ({"auth.no_user_interaction": dbus.Variant("b", True)},),
                          callback=lambda body: None,
                          error=lambda error, path=path: print("horyzont: montowanie", path, error, file=sys.stderr))
