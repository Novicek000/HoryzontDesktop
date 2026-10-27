"""Start sesji: przygotowuje konfigurację labwc i uruchamia kompozytor.

Wywoływane z pliku /usr/share/wayland-sessions/horyzont.desktop przez
menedżer logowania (GDM, SDDM, LightDM).
"""
import os
import shutil
import sys

from . import labwc


def _prepare_cursors():
    """Przy pierwszym starcie tworzy oryginalny motyw wskaźników „Horyzont” (~/.icons/Horyzont)."""
    marker = os.path.expanduser("~/.icons/Horyzont/.horyzont-v1")
    if os.path.exists(marker):
        return
    import subprocess
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    try:
        subprocess.run([sys.executable, "-m", "horyzont", "gen-cursors"], env=env, timeout=60)
    except Exception as e:
        print("horyzont: nie udało się utworzyć motywu wskaźników:", e, file=sys.stderr)


def main(argv):
    if not shutil.which("labwc"):
        print("horyzont: brak kompozytora labwc — zainstaluj: sudo dnf install labwc", file=sys.stderr)
        return 1
    os.environ.setdefault("XDG_CURRENT_DESKTOP", "Horyzont:wlroots")
    os.environ.setdefault("XDG_SESSION_DESKTOP", "horyzont")
    os.environ.setdefault("XDG_SESSION_TYPE", "wayland")
    _prepare_cursors()
    labwc.write_all()
    args = ["labwc", "-C", labwc.LABWC_DIR]
    if "--debug" in argv:
        args.append("-d")
    os.execvp("labwc", args)
    return 0
