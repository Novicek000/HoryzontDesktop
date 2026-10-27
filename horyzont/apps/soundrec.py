"""Rejestrator dźwięku — nagrywanie z mikrofonu, odtwarzanie, proste efekty i edycja plików WAV."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array

from PySide6.QtCore import QBuffer, QByteArray, QElapsedTimer, QIODevice, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenuBar, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from .. import config
from ..common import dialogs
from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow

RATE = 44100
TITLE = ("Rejestrator dźwięku", "Sound Recorder")

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
    HAVE_MM = True
except Exception:  # pragma: no cover
    HAVE_MM = False


# ====================================================================== dźwięk w pamięci
def read_wav(path):
    """Zwraca (próbki mono int16, częstotliwość). Inne formaty przez ffmpeg, jeśli jest dostępny."""
    try:
        with wave.open(path, "rb") as w:
            ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError):
        ff = shutil.which("ffmpeg")
        if not ff:
            raise ValueError(T("To nie jest plik WAV w formacie PCM (do innych formatów potrzebny jest ffmpeg).",
                               "Not a PCM WAV file (ffmpeg is required for other formats)."))
        r = subprocess.run([ff, "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            raise ValueError(r.stderr.decode(errors="replace")[-300:])
        a = array("h")
        a.frombytes(r.stdout[:len(r.stdout) - len(r.stdout) % 2])
        return a, RATE
    if sw == 1:
        a = array("h", ((b - 128) << 8 for b in raw))
    elif sw == 2:
        a = array("h")
        a.frombytes(raw[:len(raw) - len(raw) % 2])
        if sys.byteorder == "big":
            a.byteswap()
    elif sw in (3, 4):
        a = array("h", (int.from_bytes(raw[i + sw - 2:i + sw], "little", signed=True) for i in range(0, len(raw) - sw + 1, sw)))
    else:
        raise ValueError(T("Nieobsługiwany format próbek.", "Unsupported sample format."))
    if ch > 1:
        n = len(a) // ch
        chans = [a[c::ch][:n] for c in range(ch)]
        a = array("h", (sum(t) // ch for t in zip(*chans)))
    return a, rate


def wav_bytes(samples, rate):
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        data = samples
        if sys.byteorder == "big":
            data = array("h", samples)
            data.byteswap()
        w.writeframes(data.tobytes())
    return bio.getvalue()


def resample(a, src, dst):
    if src == dst or not a:
        return array("h", a)
    n = int(len(a) * dst / src)
    step = src / dst
    return array("h", (a[min(len(a) - 1, int(i * step))] for i in range(n)))


def clip(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else int(v)


# ====================================================================== okno
class Wave(QFrame):
    """Zielona linia przebiegu na czarnym tle (fragment dźwięku wokół bieżącej pozycji)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedSize(150, 46)
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Sunken)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        r = self.contentsRect()
        p.fillRect(r, QColor("#000000"))
        mid = r.center().y()
        p.setPen(QPen(QColor("#00c000"), 1))
        data = self.win.wave_window()
        if not data:
            p.drawLine(r.left(), mid, r.right(), mid)
            return
        n = len(data)
        pts = []
        h = r.height() / 2 - 1
        for x in range(r.width()):
            v = data[min(n - 1, x * n // r.width())]
            pts.append(QPoint(r.left() + x, int(mid - v / 32768 * h)))
        p.drawPolyline(QPolygon(pts))


def _btn_icon(kind):
    pm = QPixmap(20, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    black = QColor("#000000")
    if kind == "start":
        p.setBrush(black)
        p.drawRect(3, 3, 2, 10)
        p.drawPolygon(QPolygon([QPoint(11, 3), QPoint(5, 8), QPoint(11, 13)]))
        p.drawPolygon(QPolygon([QPoint(17, 3), QPoint(11, 8), QPoint(17, 13)]))
    elif kind == "end":
        p.setBrush(black)
        p.drawPolygon(QPolygon([QPoint(3, 3), QPoint(9, 8), QPoint(3, 13)]))
        p.drawPolygon(QPolygon([QPoint(9, 3), QPoint(15, 8), QPoint(9, 13)]))
        p.drawRect(15, 3, 2, 10)
    elif kind == "play":
        p.setBrush(black)
        p.drawPolygon(QPolygon([QPoint(6, 2), QPoint(15, 8), QPoint(6, 14)]))
    elif kind == "stop":
        p.setBrush(black)
        p.drawRect(5, 3, 10, 10)
    elif kind == "rec":
        p.setBrush(QColor("#d00000"))
        p.drawEllipse(5, 3, 10, 10)
    p.end()
    return QIcon(pm)


class RecorderWindow(HWindow):
    def __init__(self, ctl, path=None):
        super().__init__(T(*TITLE), "recorder", resizable=False, maximizable=False)
        self.ctl = ctl
        self.path = None
        self.samples = array("h")
        self.rate = RATE
        self.pos = 0                 # pozycja w próbkach
        self.modified = False
        self.mode = None             # None / "play" / "rec"
        self.clipboard = None
        self._rec_dev = None
        self._rec_src = None
        self._rec_proc = None
        self._rec_start = 0
        self._sink = None
        self._sink_buf = None
        self._play_proc = None
        self._play_start = 0
        self._elapsed = QElapsedTimer()
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(10, 8, 10, 10)
        cl.setSpacing(8)
        top = QHBoxLayout()
        self.pos_label = QLabel()
        self.pos_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.len_label = QLabel()
        self.len_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.wave = Wave(self)
        top.addWidget(self.pos_label, 1)
        top.addWidget(self.wave)
        top.addWidget(self.len_label, 1)
        cl.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._slider_moved)
        self.slider.valueChanged.connect(self._slider_value)
        cl.addWidget(self.slider)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.buttons = {}
        for key, tip, fn in (("start", T("Szukaj początku", "Seek to Start"), self.seek_start),
                             ("end", T("Szukaj końca", "Seek to End"), self.seek_end),
                             ("play", T("Odtwarzaj", "Play"), self.play),
                             ("stop", T("Zatrzymaj", "Stop"), self.stop),
                             ("rec", T("Nagrywaj", "Record"), self.record)):
            b = QPushButton()
            b.setIcon(_btn_icon(key))
            b.setIconSize(QSize(20, 16))
            b.setFixedSize(54, 30)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            row.addWidget(b)
            self.buttons[key] = b
        cl.addLayout(row)
        lay.addWidget(content)
        self._build_menu()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)
        if path:
            self.load(path)
        self._update()
        self.body().adjustSize()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def _build_menu(self):
        mb = self.menubar
        m = mb.addMenu(T("&Plik", "&File"))
        act(m, T("&Nowy", "&New"), self.new, "Ctrl+N")
        act(m, T("&Otwórz…", "&Open..."), self.open_dialog, "Ctrl+O")
        act(m, T("&Zapisz", "&Save"), self.save, "Ctrl+S")
        act(m, T("Zapisz &jako…", "Save &As..."), self.save_as)
        act(m, T("&Przywróć…", "&Revert..."), self.revert)
        m.addSeparator()
        act(m, T("Właś&ciwości", "Proper&ties"), self.properties)
        m.addSeparator()
        act(m, T("Za&kończ", "E&xit"), self.close)
        m = mb.addMenu(T("&Edycja", "&Edit"))
        act(m, T("&Kopiuj", "&Copy"), self.copy, "Ctrl+C")
        act(m, T("&Wklej (wstaw)", "&Paste Insert"), self.paste_insert, "Ctrl+V")
        act(m, T("Wklej (&mieszaj)", "Paste Mi&x"), self.paste_mix)
        m.addSeparator()
        act(m, T("Wstaw &plik…", "&Insert File..."), self.insert_file)
        act(m, T("Miesza&j z plikiem…", "M&ix with File..."), self.mix_file)
        m.addSeparator()
        act(m, T("Usuń &przed bieżącym położeniem", "Delete &Before Current Position"), self.delete_before)
        act(m, T("Usuń p&o bieżącym położeniu", "Delete &After Current Position"), self.delete_after)
        m = mb.addMenu(T("Ef&ekty", "Effect&s"))
        act(m, T("&Zwiększ głośność (o 25%)", "&Increase Volume (by 25%)"), lambda: self.effect("louder"))
        act(m, T("Z&mniejsz głośność", "&Decrease Volume"), lambda: self.effect("quieter"))
        m.addSeparator()
        act(m, T("Zwiększ &szybkość (o 100%)", "Increase &Speed (by 100%)"), lambda: self.effect("faster"))
        act(m, T("Zmniejsz s&zybkość", "D&ecrease Speed"), lambda: self.effect("slower"))
        m.addSeparator()
        act(m, T("&Dodaj echo", "&Add Echo"), lambda: self.effect("echo"))
        act(m, T("&Odwróć", "&Reverse"), lambda: self.effect("reverse"))
        help_menu(mb, self, T(*TITLE), "recorder", "media")

    # -------------------------------------------------------- wyświetlanie
    def seconds(self, n):
        return f"{n / self.rate:.2f}".replace(".", "," if T("pl", "en") == "pl" else ".") + " s"

    def _update(self):
        self.pos_label.setText(T("Położenie:", "Position:") + "\n" + self.seconds(self.pos))
        self.len_label.setText(T("Długość:", "Length:") + "\n" + self.seconds(len(self.samples)))
        ms_len = int(len(self.samples) * 1000 / self.rate)
        self.slider.blockSignals(True)
        self.slider.setRange(0, ms_len)
        self.slider.setValue(int(self.pos * 1000 / self.rate))
        self.slider.blockSignals(False)
        has = len(self.samples) > 0
        rec = self.mode == "rec"
        self.buttons["play"].setEnabled(has and self.mode is None and self.pos < len(self.samples))
        self.buttons["stop"].setEnabled(self.mode is not None)
        self.buttons["rec"].setEnabled(self.mode is None)
        self.buttons["start"].setEnabled(not rec and self.pos > 0)
        self.buttons["end"].setEnabled(not rec and self.pos < len(self.samples))
        name = os.path.basename(self.path) if self.path else T("Dźwięk", "Sound")
        self.setWindowTitle(f"{name} - {T(*TITLE)}")
        self.wave.update()

    def wave_window(self):
        if not self.samples:
            return None
        if self.mode == "rec":
            return self.samples[-1500:]
        a = max(0, min(self.pos, len(self.samples) - 1))
        return self.samples[a:a + 1500] or self.samples[-1500:]

    def _slider_moved(self, ms):
        self.pos = min(len(self.samples), int(ms * self.rate / 1000))
        self._update()

    def _slider_value(self, ms):
        if self.mode is None:
            self.pos = min(len(self.samples), int(ms * self.rate / 1000))
            self._update()

    # -------------------------------------------------------- transport
    def seek_start(self):
        self.stop()
        self.pos = 0
        self._update()

    def seek_end(self):
        self.stop()
        self.pos = len(self.samples)
        self._update()

    def play(self):
        if not self.samples or self.mode is not None:
            return
        if self.pos >= len(self.samples):
            self.pos = 0
        self._play_start = self.pos
        data = self.samples[self.pos:].tobytes() if sys.byteorder == "little" else None
        if HAVE_MM and data is not None:
            fmt = QAudioFormat()
            fmt.setSampleRate(self.rate)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.Int16)
            dev = QMediaDevices.defaultAudioOutput()
            if not dev.isNull():
                self._sink = QAudioSink(dev, fmt, self)
                self._sink_buf = QBuffer(self)
                self._sink_buf.setData(QByteArray(data))
                self._sink_buf.open(QIODevice.ReadOnly)
                self._sink.start(self._sink_buf)
                self.mode = "play"
                self._update()
                return
        # zapasowo: zewnętrzny odtwarzacz
        player = next((shutil.which(c) for c in ("pw-play", "paplay", "aplay") if shutil.which(c)), None)
        if not player:
            dialogs.message(self, T(*TITLE), T("Brak urządzenia odtwarzającego dźwięk.", "No audio playback device."), "error")
            return
        tmp = os.path.join(tempfile.gettempdir(), f"horyzont-rec-{os.getpid()}.wav")
        with open(tmp, "wb") as f:
            f.write(wav_bytes(self.samples[self.pos:], self.rate))
        self._play_proc = QProcess(self)
        self._play_proc.finished.connect(lambda *_: self._play_finished())
        self._play_proc.start(player, [tmp])
        self._elapsed.start()
        self.mode = "play"
        self._update()

    def _play_finished(self):
        if self.mode == "play":
            self.pos = len(self.samples)
            self.mode = None
            self._play_proc = None
            self._update()

    def stop(self):
        if self.mode == "play":
            if self._sink is not None:
                self._sink.stop()
                self._sink = None
            if self._play_proc is not None:
                p = self._play_proc
                self._play_proc = None
                p.kill()
        elif self.mode == "rec":
            self._stop_recording()
        self.mode = None
        self._update()

    def record(self):
        if self.mode is not None:
            return
        self._rec_start = self.pos
        # nagranie nadpisuje dźwięk od bieżącej pozycji (jak w klasycznym rejestratorze)
        del self.samples[self.pos:]
        if HAVE_MM:
            dev = QMediaDevices.defaultAudioInput()
            if not dev.isNull():
                fmt = QAudioFormat()
                fmt.setSampleRate(self.rate)
                fmt.setChannelCount(1)
                fmt.setSampleFormat(QAudioFormat.Int16)
                self._rec_src = QAudioSource(dev, fmt, self)
                self._rec_dev = self._rec_src.start()
                if self._rec_dev is not None:
                    self._rec_dev.readyRead.connect(self._read_qt)
                    self.mode = "rec"
                    self.modified = True
                    self._update()
                    return
        cmds = [("parecord", ["--raw", "--format=s16le", f"--rate={self.rate}", "--channels=1"]),
                ("pw-record", ["--rate", str(self.rate), "--channels", "1", "--format", "s16", "-"]),
                ("arecord", ["-q", "-f", "S16_LE", "-r", str(self.rate), "-c", "1", "-t", "raw"])]
        for prog, args in cmds:
            path = shutil.which(prog)
            if path:
                self._rec_proc = QProcess(self)
                self._rec_proc.readyReadStandardOutput.connect(self._read_proc)
                self._rec_proc.start(path, args)
                if self._rec_proc.waitForStarted(2000):
                    self.mode = "rec"
                    self.modified = True
                    self._update()
                    return
        dialogs.message(self, T(*TITLE), T("Nie znaleziono mikrofonu ani programu do nagrywania (PipeWire/PulseAudio).",
                                           "No microphone or recording program was found."), "error")

    def _append_raw(self, data):
        if self._leftover:
            data = self._leftover + data
            self._leftover = b""
        if len(data) % 2:
            self._leftover = data[-1:]
            data = data[:-1]
        a = array("h")
        a.frombytes(data)
        if sys.byteorder == "big":
            a.byteswap()
        self.samples.extend(a)
        self.pos = len(self.samples)

    _leftover = b""

    def _read_qt(self):
        if self._rec_dev is not None:
            self._append_raw(bytes(self._rec_dev.readAll()))

    def _read_proc(self):
        if self._rec_proc is not None:
            self._append_raw(bytes(self._rec_proc.readAllStandardOutput()))

    def _stop_recording(self):
        if self._rec_src is not None:
            self._read_qt()
            self._rec_src.stop()
            self._rec_src = None
            self._rec_dev = None
        if self._rec_proc is not None:
            self._read_proc()
            p = self._rec_proc
            self._rec_proc = None
            p.terminate()
            p.waitForFinished(1000)

    def _tick(self):
        if self.mode == "play":
            if self._sink is not None:
                played = int(self._sink.processedUSecs() * self.rate / 1_000_000)
                self.pos = min(len(self.samples), self._play_start + played)
                from PySide6.QtMultimedia import QAudio
                if self._sink.state() in (QAudio.IdleState, QAudio.StoppedState) and played > 0:
                    self._sink.stop()
                    self._sink = None
                    self.mode = None
                    self.pos = len(self.samples)
            elif self._play_proc is not None:
                self.pos = min(len(self.samples), self._play_start + int(self._elapsed.elapsed() * self.rate / 1000))
            self._update()
        elif self.mode == "rec":
            self._update()

    # -------------------------------------------------------- pliki
    def maybe_save(self):
        if not self.modified:
            return True
        ans = dialogs.message(self, T(*TITLE), T("Dźwięk został zmieniony.\nCzy chcesz zapisać zmiany?",
                                                 "The sound has changed.\nDo you want to save the changes?"),
                              "warning", ("yes", "no", "cancel"))
        if ans == "yes":
            return self.save()
        return ans == "no"

    def new(self):
        if not self.maybe_save():
            return
        self.stop()
        self.samples = array("h")
        self.rate = RATE
        self.pos = 0
        self.path = None
        self.modified = False
        self._update()

    def open_dialog(self):
        if not self.maybe_save():
            return
        flt = T("Pliki dźwiękowe", "Sound files") + " (*.wav *.ogg *.mp3 *.flac *.opus *.m4a)" + ";;" + \
            T("Wszystkie pliki (*)", "All Files (*)")
        f = dialogs.open_file(self, T("Otwórz", "Open"), config.user_dir("MUSIC"), flt)
        if f:
            self.load(f)

    def load(self, path):
        self.stop()
        try:
            self.samples, self.rate = read_wav(path)
        except Exception as e:
            dialogs.message(self, T(*TITLE), T(f"Nie można otworzyć pliku {os.path.basename(path)}.\n{e}",
                                               f"Cannot open {os.path.basename(path)}.\n{e}"), "error")
            return False
        self.path = os.path.abspath(path) if path.lower().endswith(".wav") else None
        self.pos = 0
        self.modified = not path.lower().endswith(".wav")
        self._update()
        return True

    def save(self):
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        flt = T("Dźwięk WAV (*.wav)", "WAV sound (*.wav)")
        if shutil.which("ffmpeg"):
            flt += ";;OGG Vorbis (*.ogg);;MP3 (*.mp3);;FLAC (*.flac)"
        name = os.path.basename(self.path) if self.path else T("Dźwięk.wav", "Sound.wav")
        f, chosen = dialogs.save_file(self, T("Zapisz jako", "Save As"), config.user_dir("MUSIC"), flt, name)
        if not f:
            return False
        if not os.path.splitext(f)[1]:
            f += {"OGG": ".ogg", "MP3": ".mp3", "FLAC": ".flac"}.get(chosen.split(" ")[0], ".wav")
        return self._write(f)

    def _write(self, path):
        data = wav_bytes(self.samples, self.rate)
        try:
            if path.lower().endswith(".wav"):
                with open(path, "wb") as f:
                    f.write(data)
            else:
                r = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-f", "wav", "-i", "-", path],
                                   input=data, capture_output=True, timeout=300)
                if r.returncode != 0:
                    raise OSError(r.stderr.decode(errors="replace")[-300:])
        except Exception as e:
            dialogs.message(self, T(*TITLE), str(e), "error")
            return False
        self.path = os.path.abspath(path) if path.lower().endswith(".wav") else self.path
        self.modified = False
        self._update()
        return True

    def revert(self):
        if self.path and dialogs.message(self, T(*TITLE), T("Czy cofnąć wszystkie zmiany od ostatniego zapisu?",
                                                            "Discard all changes since the last save?"),
                                         "question", ("yes", "no")) == "yes":
            self.load(self.path)

    def properties(self):
        d = HDialog(T("Właściwości dźwięku", "Properties for Sound"), "recorder", self)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 10, 12, 10)
        g = QGridLayout()
        info = [(T("Nazwa:", "Name:"), os.path.basename(self.path) if self.path else T("(bez nazwy)", "(untitled)")),
                (T("Długość:", "Length:"), self.seconds(len(self.samples))),
                (T("Rozmiar danych:", "Data size:"), f"{len(self.samples) * 2:,} B".replace(",", " ")),
                (T("Format audio:", "Audio format:"), f"PCM {self.rate} Hz, 16 bit, mono")]
        for i, (a, b) in enumerate(info):
            g.addWidget(QLabel(a), i, 0)
            g.addWidget(QLabel(b), i, 1)
        lay.addLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel(T("Konwertuj na:", "Convert to:")))
        rates = QComboBox()
        for r in (8000, 11025, 16000, 22050, 32000, 44100, 48000):
            rates.addItem(f"{r} Hz", r)
        rates.setCurrentIndex(max(0, rates.findData(self.rate)))
        row.addWidget(rates)
        lay.addLayout(row)
        ok = QPushButton(T("OK", "OK"))
        ok.clicked.connect(d.accept)
        lay.addWidget(ok, 0, Qt.AlignRight)
        if d.exec() == QDialog.Accepted and rates.currentData() != self.rate:
            self.samples = resample(self.samples, self.rate, rates.currentData())
            self.pos = int(self.pos * rates.currentData() / self.rate)
            self.rate = rates.currentData()
            self.modified = True
            self._update()

    # -------------------------------------------------------- edycja
    def copy(self):
        self.clipboard = (array("h", self.samples), self.rate)

    def _insert(self, other, rate, mix=False):
        other = resample(other, rate, self.rate)
        p = self.pos
        if mix:
            end = p + len(other)
            if end > len(self.samples):
                self.samples.extend(array("h", [0]) * (end - len(self.samples)))
            for i, v in enumerate(other):
                self.samples[p + i] = clip(self.samples[p + i] + v)
        else:
            self.samples[p:p] = other
        self.modified = True
        self._update()

    def paste_insert(self):
        if self.clipboard:
            self._insert(*self.clipboard)

    def paste_mix(self):
        if self.clipboard:
            self._insert(*self.clipboard, mix=True)

    def _pick_file(self):
        flt = T("Pliki dźwiękowe", "Sound files") + " (*.wav *.ogg *.mp3 *.flac)"
        f = dialogs.open_file(self, T("Wybierz plik", "Choose File"), config.user_dir("MUSIC"), flt)
        if not f:
            return None
        try:
            return read_wav(f)
        except Exception as e:
            dialogs.message(self, T(*TITLE), str(e), "error")
            return None

    def insert_file(self):
        r = self._pick_file()
        if r:
            self._insert(*r)

    def mix_file(self):
        r = self._pick_file()
        if r:
            self._insert(*r, mix=True)

    def delete_before(self):
        if self.pos and dialogs.message(self, T(*TITLE), T(f"Usunąć dźwięk przed pozycją {self.seconds(self.pos)}?",
                                                           f"Delete before {self.seconds(self.pos)}?"),
                                        "question", ("ok", "cancel")) == "ok":
            del self.samples[:self.pos]
            self.pos = 0
            self.modified = True
            self._update()

    def delete_after(self):
        if self.pos < len(self.samples) and dialogs.message(self, T(*TITLE), T(f"Usunąć dźwięk po pozycji {self.seconds(self.pos)}?",
                                                                               f"Delete after {self.seconds(self.pos)}?"),
                                                            "question", ("ok", "cancel")) == "ok":
            del self.samples[self.pos:]
            self.modified = True
            self._update()

    def effect(self, kind):
        if not self.samples:
            return
        self.stop()
        a = self.samples
        if kind == "louder":
            self.samples = array("h", (clip(v * 1.25) for v in a))
        elif kind == "quieter":
            self.samples = array("h", (int(v / 1.25) for v in a))
        elif kind == "faster":
            self.samples = a[::2]
            self.pos //= 2
        elif kind == "slower":
            out = array("h", [0]) * (len(a) * 2)
            out[0::2] = a
            out[1::2] = a
            self.samples = out
            self.pos *= 2
        elif kind == "echo":
            d = int(self.rate * 0.15)
            out = array("h", a) + array("h", [0]) * d
            for i, v in enumerate(a):
                out[i + d] = clip(out[i + d] + v * 0.45)
            self.samples = out
        elif kind == "reverse":
            self.samples = array("h", reversed(a))
            self.pos = len(a) - self.pos
        self.pos = min(self.pos, len(self.samples))
        self.modified = True
        self._update()

    def closeEvent(self, e):
        self.stop()
        if not self.maybe_save():
            e.ignore()
            return
        super().closeEvent(e)


class RecorderApp:
    def __init__(self):
        self.windows = []

    def handle(self, args):
        files = [a for a in args if a and not a.startswith("-")] or [None]
        for f in files:
            w = RecorderWindow(self, f)
            n = len(self.windows)
            w.move(180 + 26 * (n % 6), 120 + 26 * (n % 6))
            w.show()
            w.raise_()
            w.activateWindow()
            self.windows.append(w)
            w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)


def main(args):
    return run_app("soundrec", RecorderApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
