"""Stan ikon obszaru powiadomień zbierany w tle (bez blokowania paska zadań).

Wcześniej pasek co 10 s uruchamiał nmcli/wpctl w głównym wątku, co dawało
krótkie „przycięcia”. Teraz zbieranie działa w osobnym wątku, a zmiany sieci
i dźwięku przychodzą od razu dzięki `nmcli monitor` i `pactl subscribe`.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import threading

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .. import config
from ..common import netman, sysctl


def _run(args, timeout=5):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except Exception:
        return -1, ""


def bt_adapters():
    return [os.path.basename(p) for p in glob.glob("/sys/class/bluetooth/hci*") if ":" not in os.path.basename(p)]


def bt_state():
    """{'present', 'powered', 'connected': [nazwy]}"""
    if os.environ.get("HORYZONT_FAKE_BT"):   # testy
        return {"present": True, "powered": True, "connected": ["Słuchawki"], "available": True}
    st = {"present": bool(bt_adapters()), "powered": False, "connected": [], "available": bool(shutil.which("bluetoothctl"))}
    if not st["present"] or not st["available"]:
        return st
    rc, out = _run(["bluetoothctl", "show"], 4)
    st["powered"] = bool(re.search(r"Powered:\s*yes", out))
    if st["powered"]:
        rc, out = _run(["bluetoothctl", "devices", "Connected"], 4)
        for line in out.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[0] == "Device":
                st["connected"].append(parts[2])
    return st


def net_state():
    st = {"available": netman.available(), "kind": None, "state": "none", "name": "", "ssid": "", "signal": 0,
          "wifi_present": False, "wifi_enabled": True, "device": ""}
    if not st["available"]:
        s = sysctl.network_state()
        st["state"] = s or "none"
        st["kind"] = "ethernet"
        return st
    devs = netman.devices()
    st["wifi_present"] = any(d["type"] == "wifi" for d in devs)
    if st["wifi_present"]:
        st["wifi_enabled"] = netman.wifi_enabled()
    conn = [d for d in devs if d["state"].startswith("connected") and d["type"] in ("ethernet", "wifi")]
    if conn:
        # przewodowe ma pierwszeństwo, jak w systemie
        d = sorted(conn, key=lambda d: d["type"] != "ethernet")[0]
        st.update(kind=d["type"], state="connected", name=d["connection"], device=d["device"])
        if d["type"] == "wifi":
            st["ssid"] = d["connection"]
            rc, out, _ = netman.nmcli(["-t", "-f", "IN-USE,SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no"], 6)
            for line in out.splitlines():
                p = netman.split_terse(line)
                if len(p) >= 3 and p[0] == "*":
                    st["ssid"] = p[1] or st["ssid"]
                    try:
                        st["signal"] = int(p[2])
                    except ValueError:
                        pass
    else:
        connecting = [d for d in devs if "connecting" in d["state"]]
        if connecting:
            st.update(kind=connecting[0]["type"], state="connecting", device=connecting[0]["device"])
        elif st["wifi_present"]:
            st.update(kind="wifi", state="disconnected")
        elif any(d["type"] == "ethernet" for d in devs):
            st.update(kind="ethernet", state="disconnected")
    return st


def updates_state():
    """Stan aktualizacji: najświeższy z plików użytkownika i agenta systemowego."""
    try:
        from ..updates import core
        return core.read_status()
    except Exception:
        return {}


def collect():
    st = {}
    try:
        st["battery"] = sysctl.battery()
    except Exception:
        st["battery"] = None
    try:
        st["net"] = net_state()
    except Exception:
        st["net"] = {"available": False, "state": "none", "kind": None}
    try:
        st["volume"] = sysctl.volume_get() if config.get("volume_icon", True) else None
    except Exception:
        st["volume"] = None
    try:
        st["bt"] = bt_state()
    except Exception:
        st["bt"] = {"present": False}
    st["updates"] = updates_state()
    return st


class TrayStatus(QObject):
    """Zbiera stan w wątku tła; `updated(dict)` przychodzi w wątku GUI."""

    updated = Signal(dict)

    def __init__(self, interval=15):
        super().__init__()
        self.interval = interval
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="horyzont-tray", daemon=True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(600)
        self._debounce.timeout.connect(self._wake.set)
        self._monitors = []

    def start(self):
        self._thread.start()
        self._start_monitor(["nmcli", "monitor"])
        if shutil.which("pactl"):
            self._start_monitor(["pactl", "subscribe"], filt=("sink", "server"))

    def _start_monitor(self, args, filt=None):
        if not shutil.which(args[0]):
            return
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)

        def ready():
            data = bytes(p.readAll()).decode("utf-8", "replace")
            if filt is None or any(f in data for f in filt):
                self.refresh_soon()

        p.readyRead.connect(ready)
        p.start(args[0], args[1:])
        self._monitors.append(p)

    def refresh_soon(self):
        self._debounce.start()

    def refresh_now(self):
        self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()
        for p in self._monitors:
            p.kill()

    def _loop(self):
        while not self._stop:
            try:
                st = collect()
                self.updated.emit(st)
            except Exception as e:  # pragma: no cover
                print("horyzont: stan zasobnika:", e)
            self._wake.wait(self.interval)
            self._wake.clear()
