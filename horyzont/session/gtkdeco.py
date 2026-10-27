"""Przyciski na pasku tytułu programów GTK z własną ramką (Firefox, programy GNOME).

Takie programy rysują pasek tytułu same i biorą układ przycisków z ustawienia
org.gnome.desktop.wm.preferences button-layout (w GNOME domyślnie tylko „zamknij”).
Horyzont dokłada przyciski Minimalizuj i Maksymalizuj, jak w XP, i zapamiętuje
poprzednią wartość, żeby można ją było przywrócić.
"""
import os
import shutil
import subprocess

from .. import config

SCHEMA = "org.gnome.desktop.wm.preferences"
KEY = "button-layout"
RIGHT = "minimize,maximize,close"


def _gsettings(*args):
    try:
        r = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def xp_layout(value):
    """Zwraca układ z przyciskami XP albo None, gdy obecny układ ma już minimalizację/maksymalizację."""
    v = (value or "").strip().strip("'\"")
    if "minimize" in v or "maximize" in v:
        return None
    left = v.split(":", 1)[0] if ":" in v else ""
    left = ",".join(b for b in left.split(",") if b and b != "close")
    return f"{left}:{RIGHT}"


def _settings_ini(path, layout):
    """Dopisuje gtk-decoration-layout do settings.ini GTK, jeśli użytkownik go nie ustawił."""
    try:
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    except OSError:
        return
    if "gtk-decoration-layout" in text:
        return
    if "[Settings]" not in text:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "[Settings]\n"
    lines = text.splitlines()
    i = lines.index("[Settings]") if "[Settings]" in lines else len(lines) - 1
    lines.insert(i + 1, f"gtk-decoration-layout={layout}")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def apply():
    """Wywoływane przy starcie powłoki. Zwraca nowy układ albo None, gdy nic nie zmieniono."""
    if not config.get("gtk_xp_buttons", True):
        return None
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    for ver in ("gtk-3.0", "gtk-4.0"):
        _settings_ini(os.path.join(cfg, ver, "settings.ini"), "menu:" + RIGHT)
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
    _gsettings("set", SCHEMA, KEY, new)
    return new


def restore():
    """Przywraca układ przycisków sprzed Horyzontu (np. przy odinstalowaniu)."""
    orig = config.get("gtk_button_layout_orig")
    if orig is None or not shutil.which("gsettings"):
        return
    if orig in ("", "appmenu:close"):
        _gsettings("reset", SCHEMA, KEY)
    else:
        _gsettings("set", SCHEMA, KEY, orig)
    config.set("gtk_button_layout_orig", None)
