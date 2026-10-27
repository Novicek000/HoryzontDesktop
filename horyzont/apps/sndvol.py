"""Regulacja głośności — mikser w klasycznym układzie: kolumna głośności głównej, kolumny programów i mikrofonu.

Korzysta z pactl (PipeWire/PulseAudio). Każda kolumna ma suwak balansu, pionowy suwak głośności i pole „Wycisz”.
"""
import json
import shutil
import subprocess
import sys

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QMenuBar, QPushButton,
                               QRadioButton, QScrollArea, QSlider, QStatusBar, QVBoxLayout, QWidget)

from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow

TITLE = ("Regulacja głośności", "Volume Control")


def pactl_json(*args):
    try:
        r = subprocess.run(["pactl", "-f", "json", *args], capture_output=True, text=True, timeout=4)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except Exception:
        pass
    return None


def pactl(*args):
    try:
        subprocess.run(["pactl", *args], capture_output=True, timeout=4)
    except Exception:
        pass


def default_name(kind):
    try:
        r = subprocess.run(["pactl", f"get-default-{kind}"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip()
    except Exception:
        return ""


def _channels(obj):
    """Lista procentów głośności kanałów."""
    vol = obj.get("volume") or {}
    out = []
    for ch, v in vol.items():
        try:
            out.append((ch, int(str(v.get("value_percent", "0")).rstrip("%"))))
        except ValueError:
            pass
    return out


class Column(QFrame):
    """Kolumna miksera: nazwa, balans, głośność, wyciszenie."""

    def __init__(self, win, kind, ident, title, master=False):
        super().__init__()
        self.win = win
        self.kind = kind            # sink / sink-input / source
        self.ident = ident
        self._busy = False
        self.chan_names = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        self.title = QLabel(title)
        f = QFont(self.title.font())
        f.setBold(True)
        self.title.setFont(f)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setFixedWidth(124)
        self.title.setMinimumHeight(30)
        lay.addWidget(self.title)
        lay.addWidget(QLabel(T("Balans:", "Balance:")), 0, Qt.AlignHCenter)
        bal = QHBoxLayout()
        bal.addWidget(QLabel("L"))
        self.balance = QSlider(Qt.Horizontal)
        self.balance.setRange(-100, 100)
        self.balance.setTickPosition(QSlider.TicksBelow)
        self.balance.setTickInterval(25)
        self.balance.setFixedWidth(80)
        bal.addWidget(self.balance)
        bal.addWidget(QLabel("P" if T("pl", "en") == "pl" else "R"))
        lay.addLayout(bal)
        lay.addWidget(QLabel(T("Głośność:", "Volume:")), 0, Qt.AlignHCenter)
        self.volume = QSlider(Qt.Vertical)
        self.volume.setRange(0, 100)
        self.volume.setTickPosition(QSlider.TicksLeft)
        self.volume.setTickInterval(10)
        self.volume.setMinimumHeight(140)
        lay.addWidget(self.volume, 1, Qt.AlignHCenter)
        self.pct = QLabel("")
        self.pct.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.pct)
        self.mute = QCheckBox(T("Wycisz wszystko", "Mute all") if master else T("Wycisz", "Mute"))
        lay.addWidget(self.mute, 0, Qt.AlignHCenter)
        self.volume.valueChanged.connect(self._apply_volume)
        self.balance.valueChanged.connect(self._apply_volume)
        self.mute.toggled.connect(self._apply_mute)
        for s in (self.volume, self.balance):
            s.sliderPressed.connect(lambda: self.win.hold(True))
            s.sliderReleased.connect(lambda: self.win.hold(False))

    def set_state(self, chans, muted):
        self._busy = True
        self.chan_names = [c for c, _ in chans]
        vals = [v for _, v in chans] or [0]
        vol = max(vals)
        self.volume.setValue(min(100, vol))
        if len(vals) >= 2 and vol > 0:
            left, right = vals[0], vals[1]
            bal = int(round((right - left) / max(left, right) * 100))
        else:
            bal = 0
        self.balance.setValue(bal)
        self.balance.setEnabled(len(vals) >= 2)
        self.mute.setChecked(bool(muted))
        self.pct.setText(f"{vol}%")
        self._busy = False

    def _apply_volume(self, *_):
        if self._busy:
            return
        v = self.volume.value()
        b = self.balance.value()
        self.pct.setText(f"{v}%")
        if len(self.chan_names) >= 2:
            left = round(v * (1 - max(0, b) / 100))
            right = round(v * (1 + min(0, b) / 100))
            vols = [f"{left}%", f"{right}%"] + [f"{v}%"] * (len(self.chan_names) - 2)
        else:
            vols = [f"{v}%"]
        cmd = {"sink": "set-sink-volume", "sink-input": "set-sink-input-volume", "source": "set-source-volume"}[self.kind]
        pactl(cmd, str(self.ident), *vols)

    def _apply_mute(self, on):
        if self._busy:
            return
        cmd = {"sink": "set-sink-mute", "sink-input": "set-sink-input-mute", "source": "set-source-mute"}[self.kind]
        pactl(cmd, str(self.ident), "1" if on else "0")


class PropertiesDialog(HDialog):
    def __init__(self, win):
        super().__init__(T("Właściwości", "Properties"), "volume", win)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(QLabel(T("Urządzenie miksera:", "Mixer device:")))
        self.device = QComboBox()
        lay.addWidget(self.device)
        grp = QFrame()
        gl = QVBoxLayout(grp)
        gl.setContentsMargins(0, 6, 0, 6)
        gl.addWidget(QLabel(T("Regulacja głośności dla:", "Adjust volume for:")))
        self.play = QRadioButton(T("Odtwarzanie", "Playback"))
        self.rec = QRadioButton(T("Nagrywanie", "Recording"))
        (self.rec if win.mode == "record" else self.play).setChecked(True)
        gl.addWidget(self.play)
        gl.addWidget(self.rec)
        lay.addWidget(grp)
        self.play.toggled.connect(lambda *_: self._fill(win))
        self._fill(win)
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
        self.setMinimumWidth(360)

    def _fill(self, win):
        self.device.clear()
        kind = "sources" if self.rec.isChecked() else "sinks"
        default = default_name("source" if kind == "sources" else "sink")
        for d in pactl_json("list", kind) or []:
            if kind == "sources" and d.get("monitor_source") is not None and ".monitor" in d.get("name", ""):
                continue
            self.device.addItem(d.get("description") or d.get("name"), d.get("name"))
            if d.get("name") == default:
                self.device.setCurrentIndex(self.device.count() - 1)


class MixerWindow(HWindow):
    def __init__(self):
        super().__init__(T(*TITLE), "volume", maximizable=False)
        self.mode = "play"
        self._hold = False
        self._pending = False
        self.columns = {}
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        m = self.menubar.addMenu(T("&Opcje", "&Options"))
        act(m, T("&Właściwości", "&Properties"), self.properties)
        m.addSeparator()
        act(m, T("&Zakończ", "E&xit"), self.close)
        help_menu(self.menubar, self, T(*TITLE), "volume", "media")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.holder = QWidget()
        self.row = QHBoxLayout(self.holder)
        self.row.setContentsMargins(4, 4, 4, 4)
        self.row.setSpacing(0)
        self.scroll.setWidget(self.holder)
        lay.addWidget(self.scroll, 1)
        self.status = QStatusBar()
        self.dev_label = QLabel()
        self.status.addWidget(self.dev_label, 1)
        lay.addWidget(self.status)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh)
        self.sub = None
        if shutil.which("pactl"):
            self.sub = QProcess(self)
            self.sub.readyReadStandardOutput.connect(self._events)
            self.sub.start("pactl", ["subscribe"])
        self.refresh()

    def hold(self, on):
        self._hold = on
        if not on and self._pending:
            self.refresh_timer.start(200)

    def _events(self):
        data = bytes(self.sub.readAllStandardOutput()).decode(errors="replace")
        if any(k in data for k in ("sink", "source", "server")):
            if self._hold:
                self._pending = True
            else:
                self.refresh_timer.start(150)

    def _clear(self):
        while self.row.count():
            it = self.row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.columns = {}

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.VLine)
        s.setFrameShadow(QFrame.Sunken)
        return s

    def refresh(self):
        self._pending = False
        if not shutil.which("pactl"):
            self._clear()
            lbl = QLabel(T("Brak programu pactl. Zainstaluj pakiet pulseaudio-utils (Panel sterowania → Dodaj lub usuń "
                           "programy).", "pactl is missing. Install pulseaudio-utils."))
            lbl.setWordWrap(True)
            self.row.addWidget(lbl)
            return
        if self.mode == "record":
            devs = [d for d in (pactl_json("list", "sources") or []) if ".monitor" not in d.get("name", "")]
            default = default_name("source")
            items = [("source", d) for d in devs]
            main = next((d for d in devs if d.get("name") == default), devs[0] if devs else None)
            self.dev_label.setText(main.get("description", "") if main else "")
        else:
            sinks = pactl_json("list", "sinks") or []
            default = default_name("sink")
            main = next((d for d in sinks if d.get("name") == default), sinks[0] if sinks else None)
            inputs = pactl_json("list", "sink-inputs") or []
            sources = [d for d in (pactl_json("list", "sources") or []) if ".monitor" not in d.get("name", "")]
            dsrc = default_name("source")
            mic = next((d for d in sources if d.get("name") == dsrc), sources[0] if sources else None)
            items = ([("sink", main)] if main else []) + [("sink-input", i) for i in inputs] + \
                ([("source", mic)] if mic else [])
            self.dev_label.setText(main.get("description", "") if main else T("Brak urządzenia odtwarzającego",
                                                                                  "No playback device"))
        keys = [(k, str(d.get("index"))) for k, d in items]
        if set(keys) != set(self.columns):
            self._clear()
            first = True
            for k, d in items:
                if not first:
                    self.row.addWidget(self._sep())
                first = False
                props = d.get("properties") or {}
                if k == "sink" and self.mode != "record":
                    title = T("Regulacja głośności", "Volume Control")
                elif k == "sink-input":
                    title = props.get("application.name") or props.get("media.name") or T("Program", "Program")
                elif self.mode == "record":
                    title = d.get("description") or T("Mikrofon", "Microphone")
                else:
                    title = T("Mikrofon", "Microphone")
                col = Column(self, k, d.get("index"), title, master=(k == "sink"))
                self.columns[(k, str(d.get("index")))] = col
                self.row.addWidget(col)
            self.row.addStretch(1)
        for k, d in items:
            col = self.columns.get((k, str(d.get("index"))))
            if col is not None:
                col.set_state(_channels(d), d.get("mute"))
        n = max(1, len(self.columns))
        self.resize(min(1000, 50 + n * 142), max(self.height(), 410) if self.isVisible() else 410)

    def properties(self):
        d = PropertiesDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        self.mode = "record" if d.rec.isChecked() else "play"
        dev = d.device.currentData()
        if dev:
            pactl("set-default-source" if self.mode == "record" else "set-default-sink", dev)
        self.setWindowTitle(T("Regulacja nagrywania", "Recording Control") if self.mode == "record" else T(*TITLE))
        self._clear()
        self.refresh()

    def closeEvent(self, e):
        if self.sub is not None:
            self.sub.kill()
        super().closeEvent(e)


class MixerApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = MixerWindow()
            self.win.move(200, 120)
        if "--record" in args and self.win.mode != "record":
            self.win.mode = "record"
            self.win.refresh()
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    return run_app("sndvol", MixerApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
