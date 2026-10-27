"""Zasilanie: profile (power-profiles-daemon / tuned-ppd przez D-Bus) i akcje pokrywy/przycisku (systemd-logind)."""
import os
import shutil
import subprocess
import tempfile

PPD_NAMES = [("org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles"),
             ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")]
LOGIND_DROPIN = "/etc/systemd/logind.conf.d/50-horyzont.conf"
LID_ACTIONS = ["ignore", "lock", "suspend", "hibernate", "poweroff"]


def _system_bus():
    from . import dbus
    return dbus.Connection("system")


def _ppd():
    """(bus, nazwa, ścieżka, interfejs) dostępnej usługi profili albo None."""
    try:
        bus = _system_bus()
    except Exception:
        return None
    for name, path in PPD_NAMES:
        try:
            bus.call_sync(name, path, "org.freedesktop.DBus.Properties",
                          "Get", "ss", (name, "ActiveProfile"), timeout=2)
            return bus, name, path
        except Exception:
            continue
    bus.sock.close()
    return None


def profiles():
    """(lista profili, aktywny) — np. (["power-saver", "balanced", "performance"], "balanced")."""
    found = _ppd()
    if found:
        bus, name, path = found
        from .dbus import unwrap
        try:
            act = unwrap(bus.call_sync(name, path, "org.freedesktop.DBus.Properties", "Get", "ss",
                                       (name, "ActiveProfile"))[0])
            lst = unwrap(bus.call_sync(name, path, "org.freedesktop.DBus.Properties", "Get", "ss",
                                       (name, "Profiles"))[0])
            names = [p.get("Profile") for p in lst if p.get("Profile")]
            return names or ["power-saver", "balanced", "performance"], act
        finally:
            bus.sock.close()
    if shutil.which("powerprofilesctl"):
        r = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True)
        if r.returncode == 0:
            return ["power-saver", "balanced", "performance"], r.stdout.strip()
    if shutil.which("tuned-adm"):
        r = subprocess.run(["tuned-adm", "active"], capture_output=True, text=True)
        cur = r.stdout.split(":", 1)[-1].strip()
        mapping = {"powersave": "power-saver", "balanced": "balanced", "throughput-performance": "performance"}
        return ["power-saver", "balanced", "performance"], mapping.get(cur, "balanced")
    return [], None


def set_profile(profile, parent=None):
    from .dbus import Variant
    found = _ppd()
    if found:
        bus, name, path = found
        try:
            bus.call_sync(name, path, "org.freedesktop.DBus.Properties", "Set", "ssv",
                          (name, "ActiveProfile", Variant("s", profile)))
            return True
        except Exception:
            pass
        finally:
            bus.sock.close()
    if shutil.which("powerprofilesctl"):
        if subprocess.run(["powerprofilesctl", "set", profile], capture_output=True).returncode == 0:
            return True
    if shutil.which("tuned-adm"):
        tp = {"power-saver": "powersave", "balanced": "balanced", "performance": "throughput-performance"}[profile]
        from .privileged import run_privileged
        return run_privileged(["tuned-adm", "profile", tp], parent)[0]
    return False


def logind_setting(key):
    """Bieżąca wartość z systemd-logind (np. HandleLidSwitch)."""
    try:
        bus = _system_bus()
        from .dbus import unwrap
        v = unwrap(bus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.DBus.Properties",
                                 "Get", "ss", ("org.freedesktop.login1.Manager", key), timeout=2)[0])
        bus.sock.close()
        return v
    except Exception:
        return None


def save_logind(values, parent=None):
    """values: {"HandleLidSwitch": "suspend", ...} — zapis do pliku drop-in i przeładowanie logind."""
    lines = ["# Horyzont — Opcje zasilania (Panel sterowania)", "[Login]"]
    for k, v in values.items():
        lines.append(f"{k}={v}")
    fd, tmp = tempfile.mkstemp(prefix="horyzont-logind-", suffix=".conf")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    script = ('mkdir -p /etc/systemd/logind.conf.d && install -m 644 "$1" "$2" && '
              '(systemctl kill -s HUP systemd-logind 2>/dev/null || true)')
    from .privileged import run_privileged
    try:
        ok, out = run_privileged(["sh", "-c", script, "sh", tmp, LOGIND_DROPIN], parent)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return ok
