"""Stały układ przycisków GTK dla Waylanda, XWaylanda i aplikacji Flatpak."""
import json
import configparser
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .. import config

SCHEMA = "org.gnome.desktop.wm.preferences"
KEY = "button-layout"
RIGHT = "minimize,maximize,close"
LAYOUT = "menu:" + RIGHT


def _gsettings(*args):
    try:
        r = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def xp_layout(value):
    value = (value or "").strip().strip("'\"")
    return None if value == LAYOUT else LAYOUT


def _settings_ini(path, layout):
    """Zmień tylko klucz w [Settings]. None usuwa klucz przy przywracaniu.

    Zwraca (czy zmieniono, poprzednia wartość); zachowuje inne klucze i sekcje.
    """
    try:
        text = Path(path).read_text(encoding="utf-8") if os.path.exists(path) else ""
        lines = text.splitlines()
        section, header, indexes, old = "", None, [], None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
                if section == "[Settings]":
                    header = i
            elif section == "[Settings]" and re.match(r"^gtk-decoration-layout\s*=", stripped):
                indexes.append(i)
                old = stripped.split("=", 1)[1].strip()
        if (len(indexes) == 1 and old == layout) or (not indexes and layout is None):
            return False, old
        insert = indexes[0] if indexes else (header + 1 if header is not None else len(lines))
        for i in reversed(indexes):
            del lines[i]
        if layout is not None:
            if header is None:
                lines.append("[Settings]")
                insert = len(lines)
            lines.insert(insert, "gtk-decoration-layout=" + layout)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, old
    except OSError as e:
        print("horyzont: ustawienia GTK:", path, e, file=sys.stderr)
        return False, None


def settings_paths():
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    roots = [cfg]
    # Flatpak ma osobny XDG_CONFIG_HOME dla każdej aplikacji — hostowy plik nie wystarcza.
    apps = Path.home() / ".var/app"
    if apps.is_dir():
        roots.extend(str(p / "config") for p in apps.iterdir() if p.is_dir())
    return [os.path.join(root, ver, "settings.ini") for root in roots for ver in ("gtk-3.0", "gtk-4.0")]


def apply():
    """Migracja istniejących ustawień oraz wymuszenie układu podczas sesji."""
    originals = dict(config.get("gtk_button_ini_orig", {}) or {})
    changed = False
    for path in settings_paths():
        updated, old = _settings_ini(path, LAYOUT)
        if updated and path not in originals:
            originals[path] = old
            changed = True
    if changed:
        config.set("gtk_button_ini_orig", originals)
    _portal_config()
    if not shutil.which("gsettings"):
        return None
    cur = _gsettings("get", SCHEMA, KEY)
    if cur is None:
        return None
    new = xp_layout(cur)
    if new is None:
        return None
    if config.get("gtk_button_layout_orig") is None:
        config.set("gtk_button_layout_orig", cur.strip().strip("'\""))
    if _gsettings("set", SCHEMA, KEY, new) is None:
        print("horyzont: nie udało się zapisać układu przycisków GSettings", file=sys.stderr)
        return None
    return new


def _portal_config():
    """Konfiguracja użytkownika ma pierwszeństwo przed plikami instalatora."""
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = Path(root) / "xdg-desktop-portal/horyzont-portals.conf"
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
        if not cp.has_section("preferred"):
            cp.add_section("preferred")
            cp.set("preferred", "default", "gtk")
            cp.set("preferred", "org.freedesktop.impl.portal.ScreenCast", "wlr")
            cp.set("preferred", "org.freedesktop.impl.portal.Screenshot", "wlr")
            cp.set("preferred", "org.freedesktop.impl.portal.Inhibit", "none")
            cp.set("preferred", "org.freedesktop.impl.portal.Secret", "gnome-keyring")
        key = "org.freedesktop.impl.portal.Settings"
        if cp.get("preferred", key, fallback="") == "gnome;gtk":
            return
        cp.set("preferred", key, "gnome;gtk")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            cp.write(f, space_around_delimiters=False)
    except (OSError, configparser.Error) as e:
        print("horyzont: portal ustawień GTK:", e, file=sys.stderr)


def restore():
    for path, old in (config.get("gtk_button_ini_orig", {}) or {}).items():
        _settings_ini(path, old)
    config.set("gtk_button_ini_orig", {})
    orig = config.get("gtk_button_layout_orig")
    if orig is not None and shutil.which("gsettings"):
        _gsettings("set", SCHEMA, KEY, orig)
        config.set("gtk_button_layout_orig", None)


class SettingsManager:
    """Żyje razem z powłoką: XSettings dla X11 + naprawa ustawień w tle.

    QProcess zapobiega blokowaniu pulpitu podczas odczytów GSettings/dconf.
    """
    def __init__(self, app):
        from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
        self.stopping = False
        self.worker = QProcess(app)
        env = QProcessEnvironment.systemEnvironment()
        root = str(Path(__file__).resolve().parents[2])
        env.insert("PYTHONPATH", root + os.pathsep + env.value("PYTHONPATH"))
        self.worker.setProcessEnvironment(env)
        self.worker.setProcessChannelMode(QProcess.ForwardedErrorChannel)
        self.worker.setStandardOutputFile(os.devnull)
        self.worker.finished.connect(self._applied)
        self.portals = QProcess(app)
        self.portals.setProcessChannelMode(QProcess.ForwardedErrorChannel)
        self._portals_refreshed = False
        self.timer = QTimer(app)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(15000)
        self.monitor = QProcess(app)
        self.monitor.setProcessChannelMode(QProcess.ForwardedErrorChannel)
        self.monitor.readyReadStandardOutput.connect(self._setting_changed)
        if shutil.which("gsettings"):
            self.monitor.start("gsettings", ["monitor", SCHEMA, KEY])
        self.xsettings = QProcess(app)
        self.xsettings.setProcessChannelMode(QProcess.ForwardedErrorChannel)
        self.xsettings_file = os.path.join(config.CONFIG_DIR, "xsettingsd.conf")
        self._prepare_xsettings()
        app.aboutToQuit.connect(self.stop)
        self.refresh()

    def _setting_changed(self):
        self.monitor.readAllStandardOutput()
        self.refresh()

    def _applied(self, code, status):
        if code == 0 and not self._portals_refreshed and not self.stopping:
            self._portals_refreshed = True
            # Także restart powłoki po aktualizacji musi odświeżyć już działające
            # portale (nowe schematy i konfiguracja), bez wymagania czystej instalacji.
            self.portals.start("sh", ["-c",
                "dbus-update-activation-environment --systemd WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP "
                "XDG_SESSION_DESKTOP XDG_SESSION_TYPE; "
                "systemctl --user try-restart xdg-desktop-portal-gnome.service xdg-desktop-portal-gtk.service; "
                "systemctl --user try-restart xdg-desktop-portal.service"])

    def _prepare_xsettings(self):
        if not os.environ.get("DISPLAY") or not shutil.which("xsettingsd"):
            return
        # Zachowaj pozostałe XSettings, gdy były już dostarczane przez innego menedżera.
        text = ""
        try:
            text = Path(self.xsettings_file).read_text(encoding="utf-8")
        except OSError:
            if shutil.which("dump_xsettings"):
                try:
                    r = subprocess.run(["dump_xsettings"], capture_output=True, text=True, timeout=2)
                    if r.returncode == 0:
                        text = r.stdout
                except (OSError, subprocess.TimeoutExpired):
                    pass
        lines = [line for line in text.splitlines() if not line.strip().startswith("Gtk/DecorationLayout")]
        lines.append("Gtk/DecorationLayout " + json.dumps(LAYOUT))
        os.makedirs(config.CONFIG_DIR, exist_ok=True)
        Path(self.xsettings_file).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def refresh(self):
        from PySide6.QtCore import QProcess
        if self.stopping:
            return
        if self.worker.state() == QProcess.NotRunning:
            self.worker.start(sys.executable, ["-m", "horyzont", "gtk-buttons"])
        if os.environ.get("DISPLAY") and shutil.which("xsettingsd") and self.xsettings.state() == QProcess.NotRunning:
            if not os.path.exists(self.xsettings_file):
                self._prepare_xsettings()
            self.xsettings.start("xsettingsd", ["--config=" + self.xsettings_file])

    def stop(self):
        self.stopping = True
        self.timer.stop()
        for process in (self.monitor, self.worker, self.xsettings, self.portals):
            if process.state() != process.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(1000):
                    process.kill()
                    process.waitForFinished(1000)
