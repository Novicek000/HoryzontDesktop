"""Powłoka Horyzont: pulpit + pasek zadań + menu Start + polecenia sesji."""
import os
import sys

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication

from .. import config
from ..common import launcher, single, sysctl
from ..common.app import make_app
from ..theme.manager import current


class Shell:
    def __init__(self, app):
        self.app = app
        from ..wm import backend as wmb
        self.backend = wmb.create()
        from .desktop import Desktop
        from .taskbar import Taskbar
        self.desktop = Desktop(self)
        self.taskbar = Taskbar(self.backend, self)
        self.taskbar.start_requested.connect(self.toggle_start)
        self.start_menu = None
        self._start_closed_at = 0
        self._run = None
        from .startmenu import StartMenu
        self.start_menu = StartMenu(self)
        self.start_menu.closed.connect(self._start_closed)
        self.start_menu.size_changed.connect(lambda: self.update_placement(reconfigure=True))
        self.place_all()
        scr = QApplication.primaryScreen()
        scr.geometryChanged.connect(lambda *_: self.place_all(rewrite=True))
        self.desktop.show()
        self.taskbar.show()
        if config.get("startup_sound", False):
            from ..common import sounds
            QTimer.singleShot(800, lambda: sounds.play("startup"))
        self.server = single.Server("shell", self.command)
        # okresowe sprawdzanie aktualizacji (gdy nie robi tego agent systemowy)
        self._upd_timer = QTimer()
        self._upd_timer.timeout.connect(self._maybe_check_updates)
        self._upd_timer.start(30 * 60 * 1000)
        QTimer.singleShot(10 * 60 * 1000, self._maybe_check_updates)
        # D-Bus: ikony programów w zasobniku i serwer powiadomień (dymki)
        self.bus = self.sni = self.notifications = None
        self._start_dbus_services()
        # programy z autostartu (~/.config/autostart, /etc/xdg/autostart) — po zasobniku, żeby ich ikony trafiły do nas
        if not os.environ.get("HORYZONT_NO_AUTOSTART"):
            QTimer.singleShot(2500, self._run_autostart)
        # agent uwierzytelniania polkit z oknami w stylu Horyzontu
        from ..common.privileged import SessionAgent
        self.polkit_agent = SessionAgent()
        QTimer.singleShot(1500, self.polkit_agent.start)
        from ..theme.manager import ThemeManager
        ThemeManager.instance().changed.connect(self._theme_changed)
        self._cfg_watch = config.watch(self._config_changed)
        if os.environ.get("HORYZONT_DEBUG"):
            QTimer.singleShot(2000, lambda: print("DEBUG taskbar", self.taskbar.geometry(), self.taskbar.start.geometry(),
                                                  self.taskbar.tray.geometry(), "screen", self.screen_geometry(),
                                                  "dpr", self.taskbar.devicePixelRatioF(), "desk", self.desktop.geometry(),
                                                  file=sys.stderr, flush=True))

    def _start_dbus_services(self):
        from ..common import dbus
        try:
            self.bus = dbus.Connection("session")
            self.bus.attach_qt()
        except Exception as e:
            print("horyzont: brak magistrali sesji D-Bus — zasobnik programów i dymki programów niedostępne:", e,
                  file=sys.stderr)
            self.bus = None
            return
        try:
            from .sni import SniHost
            self.sni = SniHost(self.bus)
            self.taskbar.tray.attach_sni(self.sni)
        except Exception as e:
            print("horyzont: zasobnik programów:", e, file=sys.stderr)
        try:
            from .notifications import NotificationServer
            self.notifications = NotificationServer(self.bus, self.taskbar.balloons, self.taskbar.tray)
        except Exception as e:
            print("horyzont: powiadomienia:", e, file=sys.stderr)

    def _run_autostart(self):
        from . import autostart
        # tylko raz na sesję (ponowne uruchomienie powłoki nie może dublować programów)
        rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        marker = os.path.join(rt, f"horyzont-autostart-{os.environ.get('WAYLAND_DISPLAY', 'x')}-{os.environ.get('LABWC_PID', '')}")
        if os.path.exists(marker):
            return
        try:
            open(marker, "w").close()
        except OSError:
            pass
        try:
            started = autostart.run_all()
            if started:
                print("horyzont: autostart:", ", ".join(started), file=sys.stderr)
        except Exception as e:
            print("horyzont: autostart:", e, file=sys.stderr)

    # ------------------------------------------------------------ geometria
    def screen_geometry(self):
        return QApplication.primaryScreen().geometry()

    def place_all(self, rewrite=False):
        g = self.screen_geometry()
        self.desktop.setGeometry(g)
        self.place_taskbar()
        self.update_placement(reconfigure=rewrite)

    def run_dialog_size(self):
        from .sessiondialogs import RunDialog
        d = RunDialog(None)
        sz = d.size()
        d.deleteLater()
        return sz

    def update_placement(self, reconfigure=False):
        """Pozycje menu Start i okna Uruchamianie: lewy dolny róg, nad paskiem zadań."""
        g = self.screen_geometry()
        tb = current().metrics["taskbar_h"]
        sm = self.start_menu.size()
        sm_pos = QPoint(g.left(), g.bottom() + 1 - tb - sm.height())
        self.start_menu.set_place(sm_pos)
        rs = self.run_dialog_size()
        run_pos = QPoint(g.left() + 4, g.bottom() + 1 - tb - rs.height() - 4)
        self._run_pos = run_pos
        from ..i18n import plain
        if os.environ.get("LABWC_PID"):
            from ..session import labwc
            changed = labwc.save_placement(g.width(), g.height(), tb, {
                "horyzont-startmenu": (sm_pos.x(), sm_pos.y()),
                plain("run_title"): (run_pos.x(), run_pos.y()),
            })
            if changed or reconfigure:
                labwc.write_all(g.width(), g.height(), tb)
                labwc.reconfigure()

    def _maybe_check_updates(self):
        import datetime
        import threading
        from ..updates import core
        s = core.settings()
        if s.get("mode") == "off" or getattr(self, "_upd_running", False):
            return
        st = core.read_status()
        try:
            last = datetime.datetime.fromisoformat(st.get("checked", "")).timestamp()
        except ValueError:
            last = 0
        import time
        if time.time() - last < core.interval_seconds(s.get("frequency", "daily")):
            return
        self._upd_running = True

        def work():
            try:
                ups, errors = core.check_all(s.get("include_flatpak", True), s.get("include_horyzont", True))
                core.write_status(ups, core.USER_STATUS, error="; ".join(errors) or None)
            except Exception as e:
                print("horyzont: sprawdzanie aktualizacji:", e, file=sys.stderr)
            finally:
                self._upd_running = False
                if getattr(self.taskbar, "tray", None) is not None:
                    self.taskbar.tray.status.refresh_now()
        threading.Thread(target=work, daemon=True).start()

    def _theme_changed(self):
        if self.start_menu is not None:
            self.start_menu.mark_dirty()
        self.place_taskbar()

    def _config_changed(self):
        if self.start_menu is not None:
            self.start_menu.mark_dirty()

    def place_taskbar(self):
        g = self.screen_geometry()
        h = current().metrics["taskbar_h"]
        # stały rozmiar = min i max rozmiar okna; labwc bez tego wymusza wysokość >= 60 px
        self.taskbar.setFixedSize(g.width(), h)
        self.taskbar.move(g.left(), g.bottom() - h + 1)

    # ------------------------------------------------------------ menu Start
    def toggle_start(self, from_click=True):
        import time
        if self.start_menu.isVisible():
            self.start_menu.hide()
            return
        # kliknięcie w przycisk Start najpierw odbiera menu fokus (i je zamyka) — nie otwieramy ponownie
        if from_click and time.monotonic() - self._start_closed_at < 0.3:
            return
        self.taskbar.start.setDown(True)
        self.start_menu.show_menu()

    def hide_start(self):
        if self.start_menu is not None and self.start_menu.isVisible():
            self.start_menu.hide()

    def _start_closed(self):
        import time
        self._start_closed_at = time.monotonic()
        self.taskbar.start.setDown(False)

    # ------------------------------------------------------------ polecenia
    def show_run(self):
        from .sessiondialogs import RunDialog
        if self._run is not None and self._run.isVisible():
            self._run.raise_()
            self._run.activateWindow()
            return
        d = RunDialog(None)
        if getattr(self, "_run_pos", None) is not None:
            d.move(self._run_pos)
        d.show()
        d.raise_()
        d.activateWindow()
        self._run = d

    def show_turnoff(self):
        from .sessiondialogs import turn_off_dialog
        turn_off_dialog()

    def show_logoff(self):
        from .sessiondialogs import logoff_dialog
        logoff_dialog()

    def show_help(self):
        launcher.start_builtin("explorer", ["horyzont:help"])

    def command(self, args):
        if not args:
            return
        c = args[0]
        if c == "start-menu":
            self.toggle_start(from_click=False)
        elif c == "run":
            self.show_run()
        elif c == "show-desktop":
            self.taskbar.show_desktop()
        elif c == "turnoff":
            self.show_turnoff()
        elif c == "logoff":
            self.show_logoff()
        elif c == "lock":
            sysctl.lock_screen()
        elif c == "reload":
            self.desktop.reload()
            self.taskbar.relayout()
        elif c == "quit":
            self.app.quit()


def ensure_user_dirs():
    import shutil
    import subprocess
    if shutil.which("xdg-user-dirs-update"):
        subprocess.run(["xdg-user-dirs-update"], capture_output=True)
    for k in ("DESKTOP", "DOCUMENTS", "PICTURES", "MUSIC"):
        os.makedirs(config.user_dir(k), exist_ok=True)


def prepare_compositor(app):
    """Pod labwc: zapisuje reguły okien z rozmiarem ekranu i prosi o przeładowanie."""
    if not os.environ.get("LABWC_PID"):
        return 0
    from ..session import labwc
    g = QApplication.primaryScreen().geometry()
    labwc.write_all(g.width(), g.height(), current().metrics["taskbar_h"])
    labwc.reconfigure()
    return 400


def main(argv):
    app = make_app("shell", argv)
    replace = "--replace" in argv
    if not replace and single.try_forward("shell", ["reload"], 200):
        print("horyzont: powłoka już działa", file=sys.stderr)
        return 0
    if replace:
        single.try_forward("shell", ["quit"], 200)
    app.setQuitOnLastWindowClosed(False)
    ensure_user_dirs()
    delay = prepare_compositor(app)
    holder = {}
    QTimer.singleShot(delay, lambda: holder.setdefault("shell", Shell(app)))
    return app.exec()


def shell_cmd(argv):
    """`horyzont shell-cmd <polecenie>` — wysyła polecenie do działającej powłoki."""
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(argv)
    ok = single.try_forward("shell", argv[1:] if len(argv) > 1 else [], 500)
    return 0 if ok else 1
