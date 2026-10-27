"""Wyślij do → Urządzenie Bluetooth: wybór sparowanego urządzenia i wysyłanie plików przez OBEX (bluez-obexd)."""
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton, QHBoxLayout, QVBoxLayout

from .appkit import T
from .window import HDialog
from ..theme import iconcache

OBEX = "org.bluez.obex"


class SendDialog(HDialog):
    def __init__(self, files, parent=None):
        super().__init__(T("Wysyłanie plików przez Bluetooth", "Bluetooth File Transfer"), "bluetooth", parent)
        self.files = [f for f in files if os.path.isfile(f)]
        self.bus = None
        self.session = None
        self.queue = []
        self.transfer = None
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        self.info = QLabel(T("Wybierz urządzenie, do którego chcesz wysłać pliki:",
                             "Select the device you want to send the files to:"))
        lay.addWidget(self.info)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.send_btn = QPushButton(T("&Wyślij", "&Send"))
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self.start)
        self.close_btn = QPushButton(T("Anuluj", "Cancel"))
        self.close_btn.clicked.connect(self.cancel)
        row.addWidget(self.send_btn)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.resize(380, 340)
        self._fill()

    def _fill(self):
        try:
            from ..apps.control.bluetooth import devices
            devs = devices(True)
        except Exception:
            devs = []
        for d in devs:
            it = QListWidgetItem(iconcache.icon("bluetooth"), f"{d['name']}  ({d['mac']})")
            it.setData(0x0100, d["mac"])
            self.list.addItem(it)
        if not devs:
            self.status.setText(T("Brak sparowanych urządzeń. Sparuj telefon lub komputer w Panelu sterowania → "
                                  "Urządzenia Bluetooth.", "No paired devices. Pair a device in Control Panel → "
                                                           "Bluetooth Devices."))
            self.send_btn.setEnabled(False)
        else:
            self.list.setCurrentRow(0)

    def start(self):
        it = self.list.currentItem()
        if it is None or not self.files:
            return
        mac = it.data(0x0100)
        from . import dbus
        try:
            self.bus = dbus.Connection("session")
            self.session = self.bus.call_sync(OBEX, "/org/bluez/obex", "org.bluez.obex.Client1", "CreateSession",
                                              "sa{sv}", (mac, {"Target": dbus.Variant("s", "opp")}), timeout=30)[0]
        except Exception as e:
            self.status.setText(T("Nie można połączyć z urządzeniem. Upewnij się, że jest włączone, ma włączony "
                                  "Bluetooth i że zainstalowany jest pakiet bluez-obexd.\n\n",
                                  "Cannot connect to the device. Make sure it is on and bluez-obexd is installed.\n\n")
                                + str(e))
            return
        self.queue = list(self.files)
        self.send_btn.setEnabled(False)
        self.list.setEnabled(False)
        self.progress.show()
        self._next()

    def _next(self):
        if not self.queue:
            self.status.setText(T(f"Wysłano plików: {len(self.files)}.", f"Files sent: {len(self.files)}."))
            self.close_btn.setText(T("Zakończ", "Finish"))
            self._remove_session()
            return
        f = self.queue.pop(0)
        self.status.setText(T(f"Wysyłanie: {os.path.basename(f)}", f"Sending: {os.path.basename(f)}"))
        try:
            res = self.bus.call_sync(OBEX, self.session, "org.bluez.obex.ObjectPush1", "SendFile", "s", (f,), timeout=30)
            self.transfer = res[0]
            self.size = max(1, os.path.getsize(f))
            self.progress.setValue(0)
            self.timer.start(400)
        except Exception as e:
            self.status.setText(T("Błąd wysyłania: ", "Transfer error: ") + str(e))
            self._remove_session()

    def _poll(self):
        from .dbus import unwrap
        try:
            props = unwrap(self.bus.call_sync(OBEX, self.transfer, "org.freedesktop.DBus.Properties", "GetAll", "s",
                                              ("org.bluez.obex.Transfer1",), timeout=5)[0])
        except Exception:
            # obiekt transferu znika po zakończeniu
            self.timer.stop()
            self.progress.setValue(100)
            self._next()
            return
        st = props.get("Status")
        self.progress.setValue(int(props.get("Transferred", 0) * 100 / self.size))
        if st == "complete":
            self.timer.stop()
            self.progress.setValue(100)
            self._next()
        elif st == "error":
            self.timer.stop()
            self.status.setText(T("Urządzenie odrzuciło plik lub przerwało transfer.", "The device rejected the transfer."))
            self._remove_session()

    def _remove_session(self):
        if self.session and self.bus:
            try:
                self.bus.call_sync(OBEX, "/org/bluez/obex", "org.bluez.obex.Client1", "RemoveSession", "o",
                                   (self.session,), timeout=5)
            except Exception:
                pass
        self.session = None

    def cancel(self):
        self.timer.stop()
        if self.transfer and self.bus:
            try:
                self.bus.call_sync(OBEX, self.transfer, "org.bluez.obex.Transfer1", "Cancel", timeout=3)
            except Exception:
                pass
        self._remove_session()
        self.reject()


def send_files(files, parent=None):
    d = SendDialog(files, parent)
    d.exec()
