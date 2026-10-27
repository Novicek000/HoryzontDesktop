"""Punkt wejścia: ``python3 -m horyzont <program> [argumenty]``.

Programy: session, shell, shell-cmd, explorer, notepad, taskmgr, control, winver, cmd,
calc, charmap, paint, wordpad, mines, solitaire, imageviewer, mplayer, soundrec, sndvol, openwith.
"""
import sys


def main():
    argv = sys.argv[1:]
    prog = argv[0] if argv else "shell"
    rest = argv[1:]
    if prog == "session":
        from .session.run import main as m
        return m(rest)
    if prog == "shell":
        from .shell.main import main as m
        return m([sys.argv[0]] + rest)
    if prog == "shell-cmd":
        # szybka ścieżka bez Qt: skrót klawiszowy ma działać natychmiast
        from .common.single import forward_fast
        return 0 if forward_fast("shell", rest) else 1
    if prog == "explorer":
        from .apps.explorer.main import main as m
        return m(rest)
    if prog == "notepad":
        from .apps.notepad import main as m
        return m(rest)
    if prog == "taskmgr":
        from .apps.taskmgr import main as m
        return m(rest)
    if prog == "control":
        from .apps.control.main import main as m
        return m(rest)
    if prog == "winver":
        from .apps.about import main as m
        return m(rest)
    if prog == "update-agent":
        from .updates.agent import main as m
        return m(rest)
    if prog in ("cmd", "terminal"):
        from .apps.terminal.main import main as m
        return m(rest)
    apps = {"calc": "calc", "charmap": "charmap", "paint": "paint", "wordpad": "wordpad",
            "imageviewer": "imageviewer", "viewer": "imageviewer", "mplayer": "mediaplayer",
            "mediaplayer": "mediaplayer", "soundrec": "soundrec", "mines": "games.minesweeper",
            "minesweeper": "games.minesweeper", "solitaire": "games.solitaire", "sndvol": "sndvol"}
    if prog in apps:
        import importlib
        mod = importlib.import_module(".apps." + apps[prog], __package__)
        return mod.main(rest)
    if prog == "openwith":
        from .common.openwith import main as m
        return m(rest)
    if prog == "screensaver":
        from .apps.screensaver import main as m
        return m(rest)
    if prog == "gen-cursors":
        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication([sys.argv[0]])  # noqa: F841 — potrzebne do rysowania tekstu
        from .theme import cursors
        for v in cursors.VARIANTS:
            cursors.generate(v, force="--force" in rest)
        return 0
    if prog in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    print(f"horyzont: nieznany program '{prog}'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
