"""Odtwarzacz multimediów — muzyka i filmy (QtMultimedia), lista odtwarzania, wizualizacja dźwięku."""
import math
import os
import random
import sys
from array import array
from urllib.parse import unquote

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMenuBar, QPushButton, QSlider, QSplitter, QStackedWidget, QStyle, QToolButton,
                               QVBoxLayout, QWidget)

from .. import config
from ..common import dialogs
from ..common.appkit import T, act, help_menu, run_app
from ..common.window import HDialog, HWindow

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MM = True
except Exception:  # pragma: no cover — brak QtMultimedia
    HAVE_MM = False

try:
    from PySide6.QtMultimedia import QAudioBufferOutput
except Exception:
    QAudioBufferOutput = None

AUDIO_EXT = {".mp3", ".ogg", ".oga", ".opus", ".flac", ".wav", ".m4a", ".aac", ".wma", ".mid", ".midi", ".aiff", ".ape"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".wmv", ".mpg", ".mpeg", ".m4v", ".ogv", ".3gp", ".flv", ".ts"}
LIST_EXT = {".m3u", ".m3u8", ".pls"}
TITLE = ("Odtwarzacz multimediów", "Media Player")


def media_filter():
    return ";;".join([
        T("Pliki multimedialne", "Media files") + " (" + " ".join("*" + e for e in sorted(AUDIO_EXT | VIDEO_EXT | LIST_EXT)) + ")",
        T("Dźwięk", "Audio") + " (" + " ".join("*" + e for e in sorted(AUDIO_EXT)) + ")",
        T("Wideo", "Video") + " (" + " ".join("*" + e for e in sorted(VIDEO_EXT)) + ")",
        T("Listy odtwarzania", "Playlists") + " (*.m3u *.m3u8 *.pls)",
        T("Wszystkie pliki (*)", "All Files (*)"),
    ])


def fmt_time(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def ctl_icon(kind, size=20, color="#1d3f6e"):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    s = size
    if kind == "play":
        p.drawPolygon(QPolygonF([QPointF(s * 0.32, s * 0.2), QPointF(s * 0.8, s * 0.5), QPointF(s * 0.32, s * 0.8)]))
    elif kind == "pause":
        p.drawRect(QRectF(s * 0.28, s * 0.22, s * 0.16, s * 0.56))
        p.drawRect(QRectF(s * 0.56, s * 0.22, s * 0.16, s * 0.56))
    elif kind == "stop":
        p.drawRect(QRectF(s * 0.27, s * 0.27, s * 0.46, s * 0.46))
    elif kind in ("prev", "next"):
        d = 1 if kind == "next" else -1
        c = s / 2
        for off in (-0.13, 0.13):
            x = c + off * s * d
            p.drawPolygon(QPolygonF([QPointF(x - 0.13 * s * d, s * 0.28), QPointF(x + 0.13 * s * d, s * 0.5),
                                     QPointF(x - 0.13 * s * d, s * 0.72)]))
        p.drawRect(QRectF(c + 0.27 * s * d - (0.05 * s if d > 0 else 0), s * 0.28, 0.05 * s, 0.44 * s))
    elif kind in ("vol", "mute"):
        p.drawPolygon(QPolygonF([QPointF(s * 0.15, s * 0.38), QPointF(s * 0.3, s * 0.38), QPointF(s * 0.5, s * 0.2),
                                 QPointF(s * 0.5, s * 0.8), QPointF(s * 0.3, s * 0.62), QPointF(s * 0.15, s * 0.62)]))
        p.setBrush(Qt.NoBrush)
        if kind == "vol":
            p.setPen(QPen(QColor(color), 1.5))
            p.drawArc(QRectF(s * 0.4, s * 0.3, s * 0.3, s * 0.4), -50 * 16, 100 * 16)
            p.drawArc(QRectF(s * 0.35, s * 0.18, s * 0.5, s * 0.64), -50 * 16, 100 * 16)
        else:
            p.setPen(QPen(QColor("#c0272d"), 2))
            p.drawLine(QPointF(s * 0.6, s * 0.35), QPointF(s * 0.85, s * 0.65))
            p.drawLine(QPointF(s * 0.85, s * 0.35), QPointF(s * 0.6, s * 0.65))
    elif kind == "shuffle":
        p.setPen(QPen(QColor(color), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * 0.15, s * 0.3), QPointF(s * 0.75, s * 0.7))
        p.drawLine(QPointF(s * 0.15, s * 0.7), QPointF(s * 0.75, s * 0.3))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        for y in (0.3, 0.7):
            p.drawPolygon(QPolygonF([QPointF(s * 0.88, s * y), QPointF(s * 0.72, s * (y - 0.1)), QPointF(s * 0.72, s * (y + 0.1))]))
    elif kind == "repeat":
        p.setPen(QPen(QColor(color), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.3, s * 0.64, s * 0.4), 4, 4)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.62, s * 0.2), QPointF(s * 0.75, s * 0.3), QPointF(s * 0.62, s * 0.4)]))
    elif kind == "full":
        p.setPen(QPen(QColor(color), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.18, s * 0.25, s * 0.64, s * 0.5))
        p.drawLine(QPointF(s * 0.3, s * 0.38), QPointF(s * 0.42, s * 0.38))
        p.drawLine(QPointF(s * 0.3, s * 0.38), QPointF(s * 0.3, s * 0.48))
    elif kind == "list":
        p.setPen(QPen(QColor(color), 1.6))
        for i in range(3):
            p.drawLine(QPointF(s * 0.2, s * (0.3 + i * 0.2)), QPointF(s * 0.8, s * (0.3 + i * 0.2)))
    p.end()
    return QIcon(pm)


class Visualization(QWidget):
    """Wizualizacja „słupki” liczona z rzeczywistego sygnału (gdy QtMultimedia udostępnia bufory dźwięku),
    w przeciwnym razie okładka i tytuł utworu."""

    BANDS = 20

    def __init__(self):
        super().__init__()
        self.levels = [0.0] * self.BANDS
        self.peaks = [0.0] * self.BANDS
        self.title = ""
        self.artist = ""
        self.cover = None
        self.active = False
        self.real = False
        self._samples = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)
        # współczynniki do pasm (prosta DFT dla wybranych częstotliwości)
        self._freqs = [60 * (16000 / 60) ** (i / (self.BANDS - 1)) for i in range(self.BANDS)]
        self._rate = 44100
        self._coef = None

    def set_info(self, title, artist, cover):
        self.title, self.artist, self.cover = title, artist, cover
        self.update()

    def feed(self, samples, rate):
        self._samples = samples
        self.real = True
        if rate != self._rate or self._coef is None:
            self._rate = rate
            n = 256
            self._coef = [[(math.cos(2 * math.pi * f * k / rate), math.sin(2 * math.pi * f * k / rate)) for k in range(0, n, 2)]
                          for f in self._freqs]

    def _tick(self):
        if not self.active:
            changed = any(self.levels)
            self.levels = [v * 0.85 for v in self.levels]
            self.peaks = [max(0.0, v - 0.02) for v in self.peaks]
            if changed:
                self.update()
            return
        if self.real and self._samples is not None and self._coef is not None:
            s = self._samples[:256]
            if len(s) >= 64:
                sub = s[0::2]
                n = len(sub)
                new = []
                for coef in self._coef:
                    re = im = 0.0
                    for (c, si), x in zip(coef, sub):
                        re += x * c
                        im += x * si
                    mag = math.sqrt(re * re + im * im) / max(1, n) * 6
                    new.append(min(1.0, math.log10(1 + 9 * mag)))
                self.levels = [max(n_, o * 0.7) for n_, o in zip(new, self.levels)]
        for i, v in enumerate(self.levels):
            self.peaks[i] = max(v, self.peaks[i] - 0.015)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor("#0b1a2e"))
        g.setColorAt(1, QColor("#000000"))
        p.fillRect(r, g)
        area = r.adjusted(30, 30, -30, -70)
        if self.cover is not None and not self.cover.isNull():
            cs = min(area.height(), 180)
            cr = QRect(area.left(), area.top(), cs, cs)
            p.drawImage(cr, self.cover.scaled(cs, cs, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            area.setLeft(cr.right() + 20)
        bw = area.width() / self.BANDS
        for i in range(self.BANDS):
            h = self.levels[i] * area.height()
            x = area.left() + i * bw
            bg = QLinearGradient(0, area.bottom() - area.height(), 0, area.bottom())
            bg.setColorAt(0, QColor("#ffe14d"))
            bg.setColorAt(0.5, QColor("#5fd35f"))
            bg.setColorAt(1, QColor("#1f8f5f"))
            p.fillRect(QRectF(x + 2, area.bottom() - h, bw - 4, h), bg)
            pk = area.bottom() - self.peaks[i] * area.height()
            p.fillRect(QRectF(x + 2, pk - 2, bw - 4, 2), QColor("#ffffff"))
        p.setPen(QColor("#dfe9f5"))
        f = QFont(self.font())
        f.setPixelSize(17)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r.adjusted(30, r.height() - 64, -30, -36), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor("#8fb0d6"))
        p.drawText(r.adjusted(30, r.height() - 36, -30, -12), Qt.AlignLeft | Qt.AlignVCenter, self.artist)


class SeekSlider(QSlider):
    """Suwak przewijania: kliknięcie przeskakuje od razu w wybrane miejsce."""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximum() > 0:
            v = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(e.position().x()), self.width())
            self.setValue(v)
            self.sliderMoved.emit(v)
        super().mousePressEvent(e)


class PlayerWindow(HWindow):
    def __init__(self, ctl):
        super().__init__(T(*TITLE), "media_player")
        self.ctl = ctl
        self.items = []         # ścieżki lub adresy
        self.index = -1
        self.shuffle = bool(config.get("mp_shuffle", False))
        self.repeat = bool(config.get("mp_repeat", False))
        self._full = False
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.menubar = QMenuBar()
        lay.addWidget(self.menubar)
        self.split = QSplitter(Qt.Horizontal)
        self.stack = QStackedWidget()
        self.vis = Visualization()
        self.stack.addWidget(self.vis)
        if HAVE_MM:
            self.video = QVideoWidget()
            self.video.setStyleSheet("background: #000;")
            self.stack.addWidget(self.video)
        self.split.addWidget(self.stack)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(4, 4, 4, 4)
        head = QLabel(T("Lista odtwarzania", "Playlist"))
        head.setStyleSheet("font-weight: bold;")
        sl.addWidget(head)
        self.playlist = QListWidget()
        self.playlist.itemDoubleClicked.connect(lambda it: self.play_index(self.playlist.row(it)))
        sl.addWidget(self.playlist, 1)
        row = QHBoxLayout()
        for text, fn in ((T("Dodaj…", "Add..."), self.add_files), (T("Usuń", "Remove"), self.remove_selected),
                         (T("Wyczyść", "Clear"), self.clear_list)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        sl.addLayout(row)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 1)
        self.split.setCollapsible(0, False)
        self.stack.setMinimumWidth(320)
        side.setMinimumWidth(170)
        self.split.setSizes([600, 220])
        self.side = side
        side.setVisible(config.get("mp_playlist", True))
        lay.addWidget(self.split, 1)
        lay.addWidget(self._controls())
        self.status = QLabel()
        self.status.setContentsMargins(8, 2, 8, 2)
        lay.addWidget(self.status)
        self._build_menu()
        self._setup_player()
        self.resize(820, 560)
        self.setAcceptDrops(True)
        self._set_status(T("Gotowy", "Ready") if HAVE_MM else
                         T("Brak modułu QtMultimedia — zainstaluj pakiet qt6-qtmultimedia.",
                           "QtMultimedia is missing — install qt6-qtmultimedia."))

    # -------------------------------------------------------- budowa
    def _btn(self, kind, tip, fn, big=False, checkable=False):
        b = QToolButton()
        b.setIcon(ctl_icon(kind, 28 if big else 20))
        b.setIconSize(QSize(28, 28) if big else QSize(20, 20))
        b.setToolTip(tip)
        b.setAutoRaise(not big)
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.NoFocus)
        if big:
            b.setFixedSize(42, 42)
            b.setStyleSheet("QToolButton { border-radius: 21px; border: 1px solid #5a7fb0; "
                            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #b9d0ef); }"
                            "QToolButton:pressed { background: #9fbbe3; }")
        if checkable:
            b.toggled.connect(fn)
        else:
            b.clicked.connect(lambda _=False: fn())
        return b

    def _controls(self):
        panel = QFrame()
        panel.setObjectName("mpPanel")
        panel.setStyleSheet("#mpPanel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef3fa, stop:1 #c9d8ec); "
                            "border-top: 1px solid #8ea8c8; }")
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(4)
        self.seek = SeekSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self._seek)
        v.addWidget(self.seek)
        h = QHBoxLayout()
        self.b_play = self._btn("play", T("Odtwórz", "Play"), self.toggle_play, big=True)
        h.addWidget(self.b_play)
        h.addWidget(self._btn("stop", T("Zatrzymaj", "Stop"), self.stop))
        h.addWidget(self._btn("prev", T("Poprzedni", "Previous"), self.prev))
        h.addWidget(self._btn("next", T("Następny", "Next"), self.next))
        h.addSpacing(12)
        self.b_mute = self._btn("vol", T("Wycisz", "Mute"), self.toggle_mute)
        h.addWidget(self.b_mute)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(config.get("mp_volume", 80)))
        self.volume.setFixedWidth(110)
        self.volume.valueChanged.connect(self._set_volume)
        h.addWidget(self.volume)
        h.addStretch(1)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-family: monospace;")
        h.addWidget(self.time_label)
        h.addSpacing(10)
        self.b_shuffle = self._btn("shuffle", T("Losowo", "Shuffle"), self._set_shuffle, checkable=True)
        self.b_shuffle.setChecked(self.shuffle)
        self.b_repeat = self._btn("repeat", T("Powtarzaj", "Repeat"), self._set_repeat, checkable=True)
        self.b_repeat.setChecked(self.repeat)
        h.addWidget(self.b_shuffle)
        h.addWidget(self.b_repeat)
        h.addWidget(self._btn("list", T("Lista odtwarzania", "Playlist"), lambda: self.toggle_playlist()))
        h.addWidget(self._btn("full", T("Pełny ekran (Alt+Enter)", "Full Screen (Alt+Enter)"), self.toggle_full))
        v.addLayout(h)
        self.panel = panel
        return panel

    def _build_menu(self):
        mb = self.menubar
        m = mb.addMenu(T("&Plik", "&File"))
        act(m, T("&Otwórz…", "&Open..."), self.open_files, "Ctrl+O")
        act(m, T("Otwórz &adres URL…", "Open &URL..."), self.open_url, "Ctrl+U")
        act(m, T("Dodaj &folder…", "Add &Folder..."), self.add_folder)
        m.addSeparator()
        act(m, T("&Zapisz listę odtwarzania…", "&Save Playlist..."), self.save_playlist)
        m.addSeparator()
        act(m, T("Za&kończ", "E&xit"), self.close)
        m = mb.addMenu(T("&Widok", "&View"))
        act(m, T("&Pełny ekran", "&Full Screen"), self.toggle_full, "Alt+Return")
        self.a_list = act(m, T("&Lista odtwarzania", "&Playlist"), self.toggle_playlist, checkable=True,
                          checked=self.side.isVisible())
        m = mb.addMenu(T("&Odtwarzanie", "&Play"))
        act(m, T("&Odtwórz/Wstrzymaj", "&Play/Pause"), self.toggle_play, "Ctrl+P")
        act(m, T("&Zatrzymaj", "&Stop"), self.stop, "Ctrl+S")
        m.addSeparator()
        act(m, T("&Poprzedni", "Pre&vious"), self.prev, "Ctrl+B")
        act(m, T("&Następny", "&Next"), self.next, "Ctrl+F")
        m.addSeparator()
        act(m, T("Przewiń do &przodu", "Fast &Forward"), lambda: self._jump(10000), "Ctrl+Shift+F")
        act(m, T("Przewiń do &tyłu", "&Rewind"), lambda: self._jump(-10000), "Ctrl+Shift+B")
        m.addSeparator()
        act(m, T("Gło&śniej", "Volume &Up"), lambda: self.volume.setValue(self.volume.value() + 5), "F10")
        act(m, T("Ci&szej", "Volume &Down"), lambda: self.volume.setValue(self.volume.value() - 5), "F9")
        act(m, T("&Wycisz", "&Mute"), self.toggle_mute, "F8")
        help_menu(mb, self, T(*TITLE), "media_player", "media")

    def _setup_player(self):
        if not HAVE_MM:
            self.player = None
            return
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self._set_volume(self.volume.value())
        self.player.positionChanged.connect(self._pos)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, int(d)))
        self.player.playbackStateChanged.connect(self._state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._error)
        self.player.metaDataChanged.connect(self._meta)
        self.player.hasVideoChanged.connect(lambda v: self.stack.setCurrentIndex(1 if v else 0))
        if QAudioBufferOutput is not None:
            try:
                self.buf_out = QAudioBufferOutput(self)
                self.player.setAudioBufferOutput(self.buf_out)
                self.buf_out.audioBufferReceived.connect(self._audio_buffer)
            except Exception:
                self.buf_out = None

    # -------------------------------------------------------- lista
    def add_paths(self, paths, play=False):
        first_new = len(self.items)
        for p in paths:
            if not p:
                continue
            if os.path.isdir(p):
                for root, _dirs, files in os.walk(p):
                    for f in sorted(files):
                        if os.path.splitext(f)[1].lower() in AUDIO_EXT | VIDEO_EXT:
                            self._append(os.path.join(root, f))
            elif os.path.splitext(p)[1].lower() in LIST_EXT:
                for q in self._read_list(p):
                    self._append(q)
            else:
                self._append(p)
        if play and len(self.items) > first_new:
            self.play_index(first_new)

    def _append(self, p):
        self.items.append(p)
        name = os.path.basename(p) if not p.startswith(("http://", "https://")) else p
        it = QListWidgetItem(name)
        it.setToolTip(p)
        self.playlist.addItem(it)

    def _read_list(self, path):
        out = []
        base = os.path.dirname(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = [l.strip() for l in f]
        except OSError:
            return out
        for l in lines:
            if path.lower().endswith(".pls"):
                if l.lower().startswith("file") and "=" in l:
                    l = l.split("=", 1)[1]
                else:
                    continue
            if not l or l.startswith("#"):
                continue
            if l.startswith("file://"):
                l = unquote(l[7:])
            if not l.startswith(("http://", "https://", "/")):
                l = os.path.join(base, l)
            out.append(l)
        return out

    def remove_selected(self):
        for it in self.playlist.selectedItems():
            i = self.playlist.row(it)
            self.playlist.takeItem(i)
            del self.items[i]
            if i < self.index:
                self.index -= 1
            elif i == self.index:
                self.index = -1

    def clear_list(self):
        self.stop()
        self.items.clear()
        self.playlist.clear()
        self.index = -1

    def open_files(self):
        files = dialogs.open_files(self, T("Otwórz", "Open"), config.get("mp_last_dir", "") or config.user_dir("MUSIC"),
                                   media_filter())
        if files:
            config.set("mp_last_dir", os.path.dirname(files[0]))
            self.add_paths(files, play=True)

    def add_files(self):
        files = dialogs.open_files(self, T("Dodaj do listy", "Add to Playlist"), config.get("mp_last_dir", "") or
                                   config.user_dir("MUSIC"), media_filter())
        if files:
            self.add_paths(files, play=self.index < 0)

    def add_folder(self):
        d = dialogs.choose_dir(self, T("Dodaj folder", "Add Folder"), config.user_dir("MUSIC"))
        if d:
            self.add_paths([d], play=self.index < 0)

    def open_url(self):
        dlg = HDialog(T("Otwieranie adresu URL", "Open URL"), "media_player", self)
        lay = QVBoxLayout(dlg.body())
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel(T("Wpisz adres URL lub ścieżkę pliku multimedialnego:", "Enter the URL or path of a media file:")))
        le = QLineEdit("https://")
        le.setMinimumWidth(380)
        lay.addWidget(le)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(dlg.accept)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(dlg.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        if dlg.exec() == QDialog.Accepted and le.text().strip() not in ("", "https://"):
            self.add_paths([le.text().strip()], play=True)

    def save_playlist(self):
        if not self.items:
            return
        f, _ = dialogs.save_file(self, T("Zapisz listę odtwarzania", "Save Playlist"), config.user_dir("MUSIC"),
                                 T("Lista odtwarzania (*.m3u)", "Playlist (*.m3u)"), "lista.m3u")
        if f:
            if not f.lower().endswith((".m3u", ".m3u8")):
                f += ".m3u"
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n" + "\n".join(self.items) + "\n")

    # -------------------------------------------------------- odtwarzanie
    def play_index(self, i):
        if not self.player or not (0 <= i < len(self.items)):
            return
        self.index = i
        for k in range(self.playlist.count()):
            f = self.playlist.item(k).font()
            f.setBold(k == i)
            self.playlist.item(k).setFont(f)
        self.playlist.setCurrentRow(i)
        src = self.items[i]
        url = QUrl(src) if src.startswith(("http://", "https://", "rtsp://", "mms://")) else QUrl.fromLocalFile(src)
        self.player.setSource(url)
        self.player.play()
        name = os.path.splitext(os.path.basename(src))[0] if not src.startswith("http") else src
        self.vis.set_info(name, "", None)
        self.setWindowTitle(f"{name} - {T(*TITLE)}")
        if os.path.exists(src):
            from ..common.launcher import add_recent_document
            add_recent_document(src)

    def toggle_play(self):
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.player.source().isEmpty():
            if self.items:
                self.play_index(max(0, self.index))
            else:
                self.open_files()
        else:
            self.player.play()

    def stop(self):
        if self.player:
            self.player.stop()

    def next(self):
        if not self.items:
            return
        if self.shuffle and len(self.items) > 1:
            j = random.choice([k for k in range(len(self.items)) if k != self.index])
        else:
            j = self.index + 1
            if j >= len(self.items):
                if not self.repeat:
                    self.stop()
                    return
                j = 0
        self.play_index(j)

    def prev(self):
        if not self.items:
            return
        if self.player and self.player.position() > 3000:
            self.player.setPosition(0)
            return
        self.play_index((self.index - 1) % len(self.items))

    def _jump(self, ms):
        if self.player:
            self.player.setPosition(max(0, self.player.position() + ms))

    def _seek(self, v):
        if self.player:
            self.player.setPosition(v)

    def _set_volume(self, v):
        config.set("mp_volume", v)
        if HAVE_MM and getattr(self, "audio", None):
            self.audio.setVolume((v / 100) ** 2)   # skala zbliżona do odczuwalnej głośności

    def toggle_mute(self):
        if HAVE_MM and getattr(self, "audio", None):
            m = not self.audio.isMuted()
            self.audio.setMuted(m)
            self.b_mute.setIcon(ctl_icon("mute" if m else "vol"))

    def _set_shuffle(self, on):
        self.shuffle = on
        config.set("mp_shuffle", on)

    def _set_repeat(self, on):
        self.repeat = on
        config.set("mp_repeat", on)

    def toggle_playlist(self, on=None):
        if on is None:
            on = not self.side.isVisible()
        self.side.setVisible(on)
        self.a_list.blockSignals(True)
        self.a_list.setChecked(on)
        self.a_list.blockSignals(False)
        config.set("mp_playlist", on)

    def toggle_full(self):
        self._full = not self._full
        for w in (self.menubar, self.status):
            w.setVisible(not self._full)
        self.side.setVisible(not self._full and config.get("mp_playlist", True))
        self.panel.setVisible(not self._full)
        if self._full:
            self.showFullScreen()
        else:
            self.showNormal()

    # -------------------------------------------------------- sygnały odtwarzacza
    def _pos(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(ms))
        self.time_label.setText(f"{fmt_time(ms)} / {fmt_time(self.player.duration())}")

    def _state(self, st):
        playing = st == QMediaPlayer.PlayingState
        self.b_play.setIcon(ctl_icon("pause" if playing else "play", 28))
        self.vis.active = playing
        if st == QMediaPlayer.StoppedState:
            self.vis.real = False
        name = self.vis.title
        self._set_status({QMediaPlayer.PlayingState: T("Odtwarzanie: ", "Playing: ") + name,
                          QMediaPlayer.PausedState: T("Wstrzymano: ", "Paused: ") + name,
                          QMediaPlayer.StoppedState: T("Zatrzymano", "Stopped")}[st])

    def _media_status(self, st):
        if st == QMediaPlayer.EndOfMedia:
            if self.repeat and len(self.items) == 1:
                self.player.setPosition(0)
                self.player.play()
            else:
                QTimer.singleShot(0, self.next)
        elif st == QMediaPlayer.InvalidMedia:
            self._set_status(T("Nie można odtworzyć pliku — nieobsługiwany format lub brak kodeków. "
                               "Kodeki MP3/H.264 zapewnia pakiet ffmpeg z RPM Fusion.",
                               "Cannot play the file — unsupported format or missing codecs."))

    def _error(self, err, text=""):
        if err != QMediaPlayer.NoError:
            self._set_status(T("Błąd: ", "Error: ") + (text or self.player.errorString()))

    def _meta(self):
        md = self.player.metaData()
        title = md.stringValue(QMediaMetaData.Title) or self.vis.title
        artist = md.stringValue(QMediaMetaData.ContributingArtist) or md.stringValue(QMediaMetaData.AlbumArtist)
        album = md.stringValue(QMediaMetaData.AlbumTitle)
        cover = md.value(QMediaMetaData.ThumbnailImage) or md.value(QMediaMetaData.CoverArtImage)
        if not isinstance(cover, QImage):
            cover = None
        self.vis.set_info(title, " — ".join(x for x in (artist, album) if x), cover)
        if title:
            self.setWindowTitle(f"{title} - {T(*TITLE)}")
            if 0 <= self.index < self.playlist.count():
                self.playlist.item(self.index).setText(f"{artist} — {title}" if artist else title)

    def _audio_buffer(self, buf):
        try:
            fmt = buf.format()
            data = bytes(buf.constData())
            ch = max(1, fmt.channelCount())
            sf = fmt.sampleFormat()
            from PySide6.QtMultimedia import QAudioFormat
            if sf == QAudioFormat.Float:
                arr = array("f")
                arr.frombytes(data[:len(data) - len(data) % 4])
                mono = arr[0::ch][:512]
            elif sf == QAudioFormat.Int16:
                arr = array("h")
                arr.frombytes(data[:len(data) - len(data) % 2])
                mono = [x / 32768 for x in arr[0::ch][:512]]
            elif sf == QAudioFormat.Int32:
                arr = array("i")
                arr.frombytes(data[:len(data) - len(data) % 4])
                mono = [x / 2147483648 for x in arr[0::ch][:512]]
            else:
                return
            self.vis.feed(list(mono), fmt.sampleRate() or 44100)
        except Exception:
            pass

    def _set_status(self, text):
        self.status.setText(text)

    # -------------------------------------------------------- zdarzenia
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._full:
            self.toggle_full()
        elif e.key() == Qt.Key_Space:
            self.toggle_play()
        else:
            super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.stack.geometry().contains(self.body().mapFrom(self, e.position().toPoint())):
            self.toggle_full()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in e.mimeData().urls()]
        self.add_paths(paths, play=True)

    def closeEvent(self, e):
        if self.player:
            self.player.stop()
        super().closeEvent(e)


class PlayerApp:
    def __init__(self):
        self.win = None

    def handle(self, args):
        if self.win is None:
            self.win = PlayerWindow(self)
            self.win.move(110, 70)
        files = [a for a in args if a and not a.startswith("-")]
        if files:
            self.win.add_paths(files, play=True)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()


def main(args):
    return run_app("mplayer", PlayerApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
