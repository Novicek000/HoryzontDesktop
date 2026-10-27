"""Autostart programów wg specyfikacji XDG (~/.config/autostart i /etc/xdg/autostart).

Programy z opcją „uruchamiaj przy starcie systemu” (Discord, Steam, Nextcloud, Telegram...) zapisują tu swój plik
.desktop. Pomijamy usługi, które Horyzont zastępuje własnymi (aplet sieci, powiadomienia, agent polkit).
"""
import os

from ..common import desktopentry, launcher

DESKTOP_NAMES = ("Horyzont", "X-Horyzont")

# zastępowane przez powłokę Horyzontu albo przeznaczone dla innych środowisk
SKIP = {
    "nm-applet", "blueman", "blueman-applet", "mako", "dunst", "xfce4-notifyd", "notification-daemon",
    "polkit-gnome-authentication-agent-1", "lxpolkit", "polkit-mate-authentication-agent-1",
    "polkit-kde-authentication-agent-1", "org.kde.polkit-kde-authentication-agent-1", "xfce-polkit",
    "pasystray", "volumeicon", "cbatticon", "xfce4-power-manager", "lxqt-notificationd",
    "org.gnome.SettingsDaemon", "gnome-software-service", "org.gnome.Software", "geoclue-demo-agent",
}


def _dirs():
    home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    dirs = [home] + (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":")
    return [os.path.join(d, "autostart") for d in dirs if d]


def _raw_flags(path):
    flags = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            section = None
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    section = line[1:-1]
                    continue
                if section == "Desktop Entry" and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in ("Hidden", "X-GNOME-Autostart-enabled", "X-KDE-autostart-enabled", "X-MATE-Autostart-enabled",
                             "X-GNOME-Autostart-Phase", "X-Horyzont-Autostart", "OnlyShowIn", "NotShowIn"):
                        flags[k] = v.strip()
    except OSError:
        pass
    return flags


def entries():
    """Lista (id, DesktopEntry) do uruchomienia; pliki użytkownika przesłaniają systemowe o tym samym id."""
    seen = set()
    out = []
    for d in _dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".desktop") or fn in seen:
                continue
            seen.add(fn)
            path = os.path.join(d, fn)
            fl = _raw_flags(path)
            if fl.get("Hidden", "").lower() == "true":
                continue
            if any(fl.get(k, "").lower() == "false" for k in ("X-GNOME-Autostart-enabled", "X-KDE-autostart-enabled",
                                                               "X-MATE-Autostart-enabled")):
                continue
            if fl.get("X-Horyzont-Autostart", "").lower() == "false":
                continue
            if fl.get("X-GNOME-Autostart-Phase") in ("Initialization", "WindowManager", "Panel", "Desktop"):
                continue   # elementy sesji GNOME
            only = [x for x in fl.get("OnlyShowIn", "").split(";") if x]
            if only and not any(x in DESKTOP_NAMES for x in only):
                continue
            nots = [x for x in fl.get("NotShowIn", "").split(";") if x]
            if any(x in DESKTOP_NAMES for x in nots):
                continue
            if fn[:-8] in SKIP:
                continue
            e = desktopentry.parse(path)
            if e is None or not e.exec or e.type != "Application":
                continue
            if e.try_exec:
                te = e.try_exec
                if (os.path.isabs(te) and not os.access(te, os.X_OK)) or (not os.path.isabs(te) and not desktopentry._which(te)):
                    continue
            prog = os.path.basename((e.command() or [""])[0])
            if prog in SKIP:
                continue
            out.append((fn, e))
    return out


def run_all():
    started = []
    for fn, e in entries():
        args = e.command()
        if not args:
            continue
        if launcher._spawn(args, cwd=e.path_dir or None) is not False:
            started.append(fn[:-8])
    return started
