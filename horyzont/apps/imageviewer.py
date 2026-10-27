"""Przeglądarka obrazów i faksów — podgląd zdjęć, przeglądanie folderu, powiększanie, obracanie, pokaz slajdów."""
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QIcon, QImageReader, QMovie, QPainter, QPen, QPixmap, QPolygonF,
                           QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
                               QWidget)

from .. import config
from ..common import dialogs
from ..common.appkit import T, run_app
from ..common.window import HWindow

EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".bmp", ".dib", ".tif", ".tiff", ".webp", ".ico", ".svg",
        ".xpm", ".pbm", ".pgm", ".ppm", ".tga", ".heic", ".heif", ".avif", ".jxl"}
TITLE = ("Przeglądarka obrazów i faksów", "Picture and Fax Viewer")


def _icon(kind, size=22):
    """Oryginalne ikony paska przeglądarki."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = size / 2
    green = QColor("#2f9a3a")
    blue = QColor("#2563c9")
    dark = QColor("#303030")
    if kind in ("prev", "next"):
        p.setBrush(green)
        p.setPen(QPen(QColor("#1d6b26"), 1))
        p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        d = -1 if kind == "prev" else 1
        p.drawPolygon(QPolygonF([QPointF(c + 4 * d, c), QPointF(c - 3 * d, c - 5), QPointF(c - 3 * d, c + 5)]))
    elif kind == "fit":
        p.setPen(QPen(dark, 1.4))
        p.setBrush(QColor("#ffffff"))
        p.drawRect(QRectF(3, 5, size - 6, size - 10))
        p.setBrush(blue)
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(6, 8, size - 12, size - 16))
    elif kind == "actual":
        p.setPen(QPen(dark, 1.4))
        p.setBrush(QColor("#ffffff"))
        p.drawRect(QRectF(3, 5, size - 6, size - 10))
        f = p.font()
        f.setPixelSize(9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(3, 5, size - 6, size - 10), Qt.AlignCenter, "1:1")
    elif kind == "slideshow":
        p.setPen(QPen(dark, 1.2))
        p.setBrush(QColor("#d7e6ff"))
        p.drawRect(QRectF(2, 4, size - 4, size - 9))
        p.setBrush(green)
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(c - 3, c - 5), QPointF(c + 5, c - 1), QPointF(c - 3, c + 3)]))
    elif kind in ("zoomin", "zoomout"):
        p.setPen(QPen(dark, 1.6))
        p.setBrush(QColor(210, 235, 255))
        p.drawEllipse(QRectF(2, 2, size - 9, size - 9))
        p.setPen(QPen(QColor("#6b4a20"), 3))
        p.drawLine(QPointF(size - 8, size - 8), QPointF(size - 2, size - 2))
        p.setPen(QPen(dark, 1.6))
        m = (size - 7) / 2 + 1
        p.drawLine(QPointF(m - 3.5, m), QPointF(m + 3.5, m))
        if kind == "zoomin":
            p.drawLine(QPointF(m, m - 3.5), QPointF(m, m + 3.5))
    elif kind in ("rotr", "rotl"):
        p.setPen(QPen(blue, 2.2))
        p.setBrush(Qt.NoBrush)
        r = QRectF(4, 4, size - 8, size - 8)
        if kind == "rotr":
            p.drawArc(r, 160 * 16, -250 * 16)
            tip = QPointF(c + 1, 4)
            p.setBrush(blue)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([tip + QPointF(4, 0), tip + QPointF(-2, -4), tip + QPointF(-2, 4)]))
        else:
            p.drawArc(r, 20 * 16, 250 * 16)
            tip = QPointF(c - 1, 4)
            p.setBrush(blue)
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([tip + QPointF(-4, 0), tip + QPointF(2, -4), tip + QPointF(2, 4)]))
    elif kind == "delete":
        p.setPen(QPen(QColor("#c0272d"), 3))
        p.drawLine(QPointF(5, 5), QPointF(size - 5, size - 5))
        p.drawLine(QPointF(size - 5, 5), QPointF(5, size - 5))
    p.end()
    return QIcon(pm)


class View(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.img = None          # QImage (po obrocie)
        self.movie = None
        self.zoom = None         # None = najlepsze dopasowanie
        self.offset = QPointF(0, 0)
        self._drag = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.message = ""

    def set_image(self, img, movie=None):
        if self.movie is not None:
            self.movie.stop()
            self.movie.frameChanged.disconnect()
        self.movie = movie
        self.img = img
        self.zoom = None
        self.offset = QPointF(0, 0)
        if movie is not None:
            movie.frameChanged.connect(lambda *_: self.update())
            movie.start()
        self.update()

    def current_image(self):
        if self.movie is not None:
            return self.movie.currentImage()
        return self.img

    def scale(self):
        img = self.current_image()
        if img is None or img.isNull():
            return 1.0
        if self.zoom is not None:
            return self.zoom
        r = self.rect().adjusted(10, 10, -10, -10)
        s = min(r.width() / img.width(), r.height() / img.height())
        return min(1.0, s)

    def target_rect(self):
        img = self.current_image()
        s = self.scale()
        w, h = img.width() * s, img.height() * s
        x = (self.width() - w) / 2 + self.offset.x()
        y = (self.height() - h) / 2 + self.offset.y()
        return QRectF(x, y, w, h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(config.get("viewer_bg", "#ffffff")))
        img = self.current_image()
        if img is None or img.isNull():
            p.setPen(QColor("#606060"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.message or
                       T("Brak obrazu do wyświetlenia.", "No picture to display."))
            return
        r = self.target_rect()
        if img.hasAlphaChannel():
            # szachownica pod przezroczystością
            tile = QPixmap(16, 16)
            tile.fill(QColor("#ffffff"))
            tp = QPainter(tile)
            tp.fillRect(0, 0, 8, 8, QColor("#e0e0e0"))
            tp.fillRect(8, 8, 8, 8, QColor("#e0e0e0"))
            tp.end()
            p.fillRect(r, tile)
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.scale() < 2)
        p.drawImage(r, img)

    def resizeEvent(self, e):
        self.update()

    def set_zoom(self, z, anchor=None):
        old = self.scale()
        z = max(0.02, min(32.0, z))
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        # punkt pod kursorem zostaje na miejscu
        r = self.target_rect()
        rel = (anchor - r.topLeft()) / old if old else QPointF(0, 0)
        self.zoom = z
        nr_w, nr_h = self.current_image().width() * z, self.current_image().height() * z
        new_tl = anchor - rel * z
        self.offset = QPointF(new_tl.x() - (self.width() - nr_w) / 2, new_tl.y() - (self.height() - nr_h) / 2)
        self._clamp()
        self.update()
        self.win.update_status()

    def _clamp(self):
        img = self.current_image()
        if img is None:
            return
        s = self.scale()
        w, h = img.width() * s, img.height() * s
        mx = max(0, (w - self.width()) / 2 + 10)
        my = max(0, (h - self.height()) / 2 + 10)
        self.offset = QPointF(max(-mx, min(mx, self.offset.x())), max(-my, min(my, self.offset.y())))

    def wheelEvent(self, e):
        if self.current_image() is None:
            return
        d = e.angleDelta().y()
        if e.modifiers() & Qt.ControlModifier or self.zoom is not None:
            self.set_zoom(self.scale() * (1.25 if d > 0 else 0.8), e.position())
        else:
            (self.win.prev_image if d > 0 else self.win.next_image)()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.zoom is not None:
            self._drag = (e.position(), QPointF(self.offset))
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag:
            start, off = self._drag
            self.offset = off + (e.position() - start)
            self._clamp()
            self.update()
        else:
            img = self.current_image()
            big = img is not None and self.zoom is not None and (
                img.width() * self.scale() > self.width() or img.height() * self.scale() > self.height())
            self.setCursor(Qt.OpenHandCursor if big else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, e):
        self.win.slideshow()


class Slideshow(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.win = win
        self.setStyleSheet("background: #000;")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(int(config.get("viewer_slide_seconds", 5)) * 1000)
        self.setCursor(Qt.BlankCursor)
        self.paused = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        img = self.win.view.current_image()
        if img is None or img.isNull():
            return
        size = QSize(img.size())
        if size.width() > self.width() or size.height() > self.height():
            size.scale(self.size(), Qt.KeepAspectRatio)
        r = QRect(QPoint(0, 0), size)
        r.moveCenter(self.rect().center())
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(r, img)
        if self.paused:
            p.setPen(QColor("#ffffff"))
            p.drawText(self.rect().adjusted(10, 10, -10, -10), Qt.AlignTop | Qt.AlignRight, T("Wstrzymano", "Paused"))

    def advance(self):
        if not self.paused:
            self.win.next_image(wrap=True)
            self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Escape, Qt.Key_F11):
            self.close()
        elif k in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Space, Qt.Key_Down):
            self.win.next_image(wrap=True)
            self.update()
        elif k in (Qt.Key_Left, Qt.Key_PageUp, Qt.Key_Up, Qt.Key_Backspace):
            self.win.prev_image(wrap=True)
            self.update()
        elif k == Qt.Key_P:
            self.paused = not self.paused
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.close()
        else:
            self.win.next_image(wrap=True)
            self.update()

    def closeEvent(self, e):
        self.timer.stop()
        super().closeEvent(e)


class ViewerWindow(HWindow):
    def __init__(self, ctl, path=None):
        super().__init__(T(*TITLE), "image_viewer")
        self.ctl = ctl
        self.path = None
        self.files = []
        self.rotation = 0
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.view = View(self)
        lay.addWidget(self.view, 1)
        bar = QFrame()
        bar.setFrameShape(QFrame.StyledPanel)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 3, 6, 3)
        bl.setSpacing(2)
        bl.addStretch(1)
        self.buttons = {}
        items = [("prev", T("Poprzedni obraz (Strzałka w lewo)", "Previous Image (Left Arrow)"), self.prev_image), None,
                 ("next", T("Następny obraz (Strzałka w prawo)", "Next Image (Right Arrow)"), self.next_image), "|",
                 ("fit", T("Najlepsze dopasowanie (Ctrl+B)", "Best Fit (Ctrl+B)"), self.best_fit),
                 ("actual", T("Rzeczywisty rozmiar (Ctrl+A)", "Actual Size (Ctrl+A)"), self.actual_size),
                 ("slideshow", T("Rozpocznij pokaz slajdów (F11)", "Start Slide Show (F11)"), self.slideshow), "|",
                 ("zoomin", T("Powiększ (+)", "Zoom In (+)"), lambda: self.view.set_zoom(self.view.scale() * 1.25)),
                 ("zoomout", T("Pomniejsz (-)", "Zoom Out (-)"), lambda: self.view.set_zoom(self.view.scale() * 0.8)), "|",
                 ("rotr", T("Obróć zgodnie z ruchem wskazówek zegara (Ctrl+K)", "Rotate Clockwise (Ctrl+K)"), lambda: self.rotate(90)),
                 ("rotl", T("Obróć przeciwnie do ruchu wskazówek zegara (Ctrl+L)", "Rotate Counterclockwise (Ctrl+L)"), lambda: self.rotate(-90)), "|",
                 ("delete", T("Usuń (Del)", "Delete (Del)"), self.delete), ("printer", T("Drukuj (Ctrl+P)", "Print (Ctrl+P)"), self.print_image),
                 ("copy", T("Kopiuj do (Ctrl+S)", "Copy To (Ctrl+S)"), self.copy_to),
                 ("paint", T("Zamknij ten program i otwórz obraz do edycji (Ctrl+E)", "Close and open for editing (Ctrl+E)"), self.edit), "|",
                 ("help", T("Pomoc (F1)", "Help (F1)"), self.help)]
        from ..theme import iconcache
        for it in items:
            if it is None:
                continue
            if it == "|":
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setFrameShadow(QFrame.Sunken)
                sep.setFixedHeight(24)
                bl.addWidget(sep)
                continue
            key, tip, fn = it
            b = QToolButton()
            b.setAutoRaise(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setIcon(iconcache.icon(key) if key in ("printer", "copy", "paint", "help") else _icon(key))
            b.setIconSize(QSize(22, 22))
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            bl.addWidget(b)
            self.buttons[key] = b
        bl.addStretch(1)
        lay.addWidget(bar)
        self.info = QLabel()
        self.info.setContentsMargins(6, 1, 6, 1)
        lay.addWidget(self.info)
        self.resize(760, 580)
        self.setAcceptDrops(True)
        if path:
            self.open(path)
        else:
            self.update_status()

    # -------------------------------------------------------- pliki
    def open(self, path):
        path = os.path.abspath(path)
        if os.path.isdir(path):
            folder = path
            self._scan(folder)
            if self.files:
                self._load(self.files[0])
            return
        self._scan(os.path.dirname(path))
        if path not in self.files:
            self.files.append(path)
        self._load(path)

    def _scan(self, folder):
        try:
            names = sorted(os.listdir(folder), key=lambda n: n.lower())
        except OSError:
            names = []
        self.files = [os.path.join(folder, n) for n in names if os.path.splitext(n)[1].lower() in EXTS]

    def _load(self, path):
        if not self._maybe_save_rotation():
            return
        self.path = path
        self.rotation = 0
        movie = None
        img = None
        if path.lower().endswith((".gif", ".webp")):
            m = QMovie(path)
            if m.isValid() and m.frameCount() != 1:
                movie = m
        if movie is None:
            r = QImageReader(path)
            r.setAutoTransform(True)
            img = r.read()
            if img.isNull():
                self.view.message = T(f"Nie można wyświetlić obrazu.\n{os.path.basename(path)}\n{r.errorString()}",
                                      f"Cannot display the picture.\n{os.path.basename(path)}\n{r.errorString()}")
                img = None
        self.view.set_image(img, movie)
        self.setWindowTitle(f"{os.path.basename(path)} - {T(*TITLE)}")
        self.update_status()
        from ..common.launcher import add_recent_document
        add_recent_document(path)

    def update_status(self):
        img = self.view.current_image()
        if not self.path:
            self.info.setText("")
            return
        idx = self.files.index(self.path) + 1 if self.path in self.files else 0
        parts = [f"{idx}/{len(self.files)}"]
        if img is not None and not img.isNull():
            parts.append(f"{img.width()} × {img.height()}")
            parts.append(f"{round(self.view.scale() * 100)}%")
        try:
            size = os.path.getsize(self.path)
            parts.append(f"{size / 1024:.0f} KB" if size < 1048576 else f"{size / 1048576:.1f} MB")
        except OSError:
            pass
        self.info.setText("   ".join(parts))
        for k in ("prev", "next"):
            self.buttons[k].setEnabled(len(self.files) > 1)

    def next_image(self, wrap=True):
        self._step(1, wrap)

    def prev_image(self, wrap=True):
        self._step(-1, wrap)

    def _step(self, d, wrap=True):
        if not self.files:
            return
        i = self.files.index(self.path) if self.path in self.files else -1
        j = i + d
        if wrap:
            j %= len(self.files)
        if 0 <= j < len(self.files) and j != i:
            self._load(self.files[j])

    def best_fit(self):
        self.view.zoom = None
        self.view.offset = QPointF(0, 0)
        self.view.update()
        self.update_status()

    def actual_size(self):
        self.view.set_zoom(1.0)

    def rotate(self, deg):
        v = self.view
        if v.movie is not None:
            v.img = v.movie.currentImage()
            v.movie.stop()
            v.movie = None
        if v.img is None:
            return
        v.img = v.img.transformed(QTransform().rotate(deg), Qt.SmoothTransformation)
        self.rotation = (self.rotation + deg) % 360
        v.zoom = None
        v.offset = QPointF(0, 0)
        v.update()
        self.update_status()

    def _maybe_save_rotation(self):
        if not self.rotation or not self.path:
            return True
        ans = dialogs.message(self, T(*TITLE), T("Obraz został obrócony. Czy zapisać zmiany w pliku?",
                                                 "The picture was rotated. Save the changes?"), "question",
                              ("yes", "no", "cancel"))
        if ans == "cancel":
            return False
        if ans == "yes":
            ext = os.path.splitext(self.path)[1].lower()
            q = 95 if ext in (".jpg", ".jpeg", ".jpe", ".jfif", ".webp") else -1
            if not self.view.img.save(self.path, None, q):
                dialogs.message(self, T(*TITLE), T("Nie można zapisać obrazu w tym formacie.",
                                                   "The picture cannot be saved in this format."), "error")
        self.rotation = 0
        return True

    def delete(self):
        if not self.path:
            return
        ans = dialogs.message(self, T("Potwierdzanie usunięcia pliku", "Confirm File Delete"),
                              T(f"Czy na pewno chcesz przenieść „{os.path.basename(self.path)}” do Kosza?",
                                f"Are you sure you want to send '{os.path.basename(self.path)}' to the Recycle Bin?"),
                              "question", ("yes", "no"))
        if ans != "yes":
            return
        path = self.path
        ok = False
        if shutil.which("gio"):
            ok = subprocess.run(["gio", "trash", path], capture_output=True).returncode == 0
        if not ok:
            try:
                os.remove(path)
                ok = True
            except OSError as e:
                dialogs.message(self, T(*TITLE), str(e), "error")
                return
        i = self.files.index(path) if path in self.files else 0
        self.files = [f for f in self.files if f != path]
        self.rotation = 0
        if self.files:
            self.path = None
            self._load(self.files[min(i, len(self.files) - 1)])
        else:
            self.path = None
            self.view.set_image(None)
            self.setWindowTitle(T(*TITLE))
            self.update_status()

    def copy_to(self):
        if not self.path:
            return
        f, _ = dialogs.save_file(self, T("Kopiuj do", "Copy To"), config.user_dir("PICTURES"),
                                 T("Wszystkie pliki (*)", "All Files (*)"), os.path.basename(self.path))
        if f:
            if self.rotation:
                self.view.img.save(f)
            else:
                shutil.copy2(self.path, f)

    def edit(self):
        if not self.path:
            return
        if not self._maybe_save_rotation():
            return
        from ..common import launcher
        launcher.start_builtin("paint", [self.path])
        self.close()

    def print_image(self):
        img = self.view.current_image()
        if img is None:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        pr = QPrinter()
        if QPrintDialog(pr, self).exec() == QDialog.Accepted:
            p = QPainter(pr)
            r = p.viewport()
            size = img.size()
            size.scale(r.size(), Qt.KeepAspectRatio)
            p.setViewport(r.x(), r.y(), size.width(), size.height())
            p.setWindow(img.rect())
            p.drawImage(0, 0, img)
            p.end()

    def help(self):
        from ..common import launcher
        launcher.start_builtin("explorer", ["horyzont:help:viewer"])

    def slideshow(self):
        if not self.files:
            return
        self._show = Slideshow(self)
        self._show.setGeometry(QApplication.primaryScreen().geometry())
        self._show.showFullScreen()

    # -------------------------------------------------------- klawiatura i zdarzenia
    def keyPressEvent(self, e):
        k = e.key()
        ctrl = e.modifiers() & Qt.ControlModifier
        if k in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Down) and self.view.zoom is None:
            self.next_image()
        elif k in (Qt.Key_Left, Qt.Key_PageUp, Qt.Key_Up) and self.view.zoom is None:
            self.prev_image()
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.view.set_zoom(self.view.scale() * 1.25)
        elif k == Qt.Key_Minus:
            self.view.set_zoom(self.view.scale() * 0.8)
        elif k == Qt.Key_Delete:
            self.delete()
        elif k == Qt.Key_F11:
            self.slideshow()
        elif k == Qt.Key_F1:
            self.help()
        elif ctrl and k == Qt.Key_K:
            self.rotate(90)
        elif ctrl and k == Qt.Key_L:
            self.rotate(-90)
        elif ctrl and k == Qt.Key_B:
            self.best_fit()
        elif ctrl and k == Qt.Key_A:
            self.actual_size()
        elif ctrl and k == Qt.Key_P:
            self.print_image()
        elif ctrl and k == Qt.Key_S:
            self.copy_to()
        elif ctrl and k == Qt.Key_E:
            self.edit()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open(urls[0])

    def closeEvent(self, e):
        if not self._maybe_save_rotation():
            e.ignore()
            return
        super().closeEvent(e)


class ViewerApp:
    def __init__(self):
        self.windows = []

    def handle(self, args):
        files = [a for a in args if a and not a.startswith("-")]
        if not files and self.windows:
            self.windows[-1].show()
            self.windows[-1].raise_()
            return
        for f in files or [None]:
            w = ViewerWindow(self, f)
            n = len(self.windows)
            w.move(100 + 26 * (n % 6), 70 + 26 * (n % 6))
            w.show()
            w.raise_()
            w.activateWindow()
            self.windows.append(w)
            w.closed.connect(lambda w=w: self.windows.remove(w) if w in self.windows else None)


def main(args):
    return run_app("imageviewer", ViewerApp().handle, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
