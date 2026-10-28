"""Obraz konta na ekranie logowania: przy starcie powłoki przekazujemy obraz z menu Start do AccountsService
(z niego korzystają ekran powitalny Horyzont, GDM i inne), jeśli konto nie ma tam jeszcze obrazu albo
użytkownik wybrał inny obraz w Horyzoncie, a AccountsService o tym nie wie.
"""
import json
import os
import shutil
import subprocess
import threading

from .. import config

MARKER = os.path.join(config.CACHE_DIR, "account-picture-synced")


def _explicit_choice():
    """Czy obraz został wybrany w Panelu sterowania (a nie jest tylko domyślnym latawcem)."""
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as f:
            return "user_picture" in json.load(f)
    except (OSError, ValueError):
        return False


def _accounts_icon(uid):
    try:
        r = subprocess.run(["busctl", "--system", "get-property", "org.freedesktop.Accounts",
                            f"/org/freedesktop/Accounts/User{uid}", "org.freedesktop.Accounts.User", "IconFile"],
                           capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split(" ", 1)
    return parts[1].strip('"') if len(parts) == 2 else ""


def sync(force=False):
    """Wywoływać w wątku okien (renderowanie obrazu); komunikacja z AccountsService idzie w tle."""
    if not shutil.which("busctl"):
        return
    pic = config.get("user_picture", "builtin:kite")
    try:
        with open(MARKER, encoding="utf-8") as f:
            if f.read().strip() == pic and not force:
                return
    except OSError:
        pass
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from ..theme import iconcache
    if pic.startswith("builtin:"):
        pm = iconcache.pixmap("avatar_" + pic.split(":", 1)[1], 96)
    else:
        pm = QPixmap(pic)
        if pm.isNull():
            return
        pm = pm.scaled(96, 96, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    tmp = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or config.CACHE_DIR, "horyzont-face.png")
    if not pm.save(tmp, "PNG"):
        return
    explicit = _explicit_choice()

    def work():
        uid = os.getuid()
        cur = _accounts_icon(uid)
        if cur is None:            # AccountsService niedostępny
            return
        has_icon = bool(cur) and os.path.exists(cur)
        if has_icon and not explicit and not force:
            # obraz ustawiony gdzie indziej (np. w GNOME), a w Horyzoncie nikt go nie zmieniał — zostawiamy
            _write_marker(pic)
            return
        try:
            os.chmod(tmp, 0o644)
            r = subprocess.run(["busctl", "--system", "call", "org.freedesktop.Accounts",
                                f"/org/freedesktop/Accounts/User{uid}", "org.freedesktop.Accounts.User",
                                "SetIconFile", "s", tmp], capture_output=True, text=True, timeout=15,
                               stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                face = os.path.expanduser("~/.face")
                if not os.path.exists(face) or explicit:
                    try:
                        shutil.copyfile(tmp, face)
                    except OSError:
                        pass
                _write_marker(pic)
        except (OSError, subprocess.TimeoutExpired):
            pass
    threading.Thread(target=work, daemon=True).start()


def _write_marker(pic):
    try:
        os.makedirs(os.path.dirname(MARKER), exist_ok=True)
        with open(MARKER, "w", encoding="utf-8") as f:
            f.write(pic)
    except OSError:
        pass
