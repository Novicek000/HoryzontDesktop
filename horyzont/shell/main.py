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
        if os.environ.get("LABWC_PID"):
            # zapisane w Panelu sterowania rozdzielczość, odświeżanie i skala ekranu
            from ..common import displaycfg
            displaycfg.apply_saved()
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
        self._watch_screen(QApplication.primaryScreen())
        QApplication.instance().primaryScreenChanged.connect(self._primary_changed)
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
        try:
            from ..common.desktopentry import ensure_session_defaults
            ensure_session_defaults()
        except Exception:
            pass
        self._start_dbus_services()
        QTimer.singleShot(6000, self._check_qt_platform)
        QTimer.singleShot(2500, self._gtk_buttons)
        QTimer.singleShot(1200, self._start_login1)
        # obraz konta dla ekranu logowania (AccountsService)
        QTimer.singleShot(8000, self._sync_account_picture)
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
        try:
            from .filemanager1 import FileManager1
            self.filemanager1 = FileManager1(self.bus)
        except Exception as e:
            print("horyzont: FileManager1:", e, file=sys.stderr)

    def _gtk_buttons(self):
        # Firefox i programy GNOME rysują pasek tytułu same — dokładamy Minimalizuj i Maksymalizuj
        try:
            from ..session import gtkdeco
            gtkdeco.apply()
        except Exception as e:
            print("horyzont: układ przycisków GTK:", e, file=sys.stderr)

    def _check_qt_platform(self):
        """Programy Qt powinny działać natywnie w Wayland. Bez pakietu qt6-qtwayland Qt przełącza się na XWayland —
        wtedy m.in. okna hasła tracą fokus, a skalowanie jest rozmyte. Uprzedzamy o tym dymkiem."""
        if QApplication.platformName() == "wayland" or not os.environ.get("WAYLAND_DISPLAY"):
            return
        try:
            self.taskbar.tray.balloon("Horyzont", "Brakuje pakietu qt6-qtwayland — programy Horyzontu działają przez "
                                      "XWayland. Zainstaluj go: sudo dnf install qt6-qtwayland (albo uruchom ponownie "
                                      "update.sh) i zaloguj się ponownie.", "warning")
        except Exception as e:
            print("horyzont: platforma Qt:", QApplication.platformName(), e, file=sys.stderr)

    def _start_login1(self):
        """Sygnał Lock z systemd-logind (np. po zamknięciu pokrywy z akcją „Zablokuj”) blokuje ekran."""
        from ..common import dbus
        try:
            self.sysbus = dbus.Connection("system")
            self.sysbus.attach_qt()
            path = self.sysbus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1",
                                         "org.freedesktop.login1.Manager", "GetSessionByPID", "u", (os.getpid(),))[0]
        except Exception as e:
            print("horyzont: logind:", e, file=sys.stderr)
            return
        self.sysbus.add_match(f"type='signal',sender='org.freedesktop.login1',path='{path}',"
                              "interface='org.freedesktop.login1.Session',member='Lock'")
        self.sysbus.on_signal(lambda m: sysctl.lock_screen(), path=path, interface="org.freedesktop.login1.Session",
                              member="Lock")

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

    def _watch_screen(self, scr):
        self._screen_timer = getattr(self, "_screen_timer", None) or QTimer()
        self._screen_timer.setSingleShot(True)
        self._screen_timer.setInterval(250)
        try:
            self._screen_timer.timeout.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._screen_timer.timeout.connect(self._screen_changed)
        for sig in (scr.geometryChanged, scr.logicalDotsPerInchChanged, scr.physicalDotsPerInchChanged):
            sig.connect(lambda *_: self._screen_timer.start())
        self._last_geom = (scr.geometry(), scr.devicePixelRatio())

    def _primary_changed(self, scr):
        self._watch_screen(scr)
        self._screen_timer.start()

    def _screen_changed(self):
        """Zmiana rozdzielczości lub skali: nowe położenia w rc.xml i ponowne wyświetlenie okien powłoki,
        żeby labwc umieścił je według nowych reguł (reguły działają tylko przy pojawieniu się okna)."""
        scr = QApplication.primaryScreen()
        geom = (scr.geometry(), scr.devicePixelRatio())
        if geom == getattr(self, "_last_geom", None):
            return
        self._last_geom = geom
        self.place_all(rewrite=True)
        QTimer.singleShot(400, self.remap_shell_windows)

    def remap_shell_windows(self):
        for w in (self.desktop, self.taskbar):
            if w.isVisible():
                w.hide()
        QTimer.singleShot(80, self._show_shell_windows)

    def _show_shell_windows(self):
        self.desktop.show()
        if not getattr(self.taskbar, "fullscreen_hidden", False):
            self.taskbar.show()

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

    def _sync_account_picture(self):
        try:
            from ..common import accountpic
            accountpic.sync()
        except Exception as e:
            print("horyzont: obraz konta:", e, file=sys.stderr)

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
        self.taskbar.expand()
        self.taskbar.start.setDown(True)
        self.start_menu.show_menu()

    def hide_start(self):
        if self.start_menu is not None and self.start_menu.isVisible():
            self.start_menu.hide()

    def _start_closed(self):
        import time
        self._start_closed_at = time.monotonic()
        if self.taskbar.autohide():
            self.taskbar._hide_timer.start(700)
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
        elif c == "relayout":
            self._last_geom = None
            self._screen_changed()
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
