"""Menu kontekstowe programów w menu Start (prawy przycisk): Otwórz, Przypnij, Wyślij do, Zmień nazwę,
Usuń z menu, Odinstaluj, Właściwości — oraz QMenu, które je obsługuje."""
import os
import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import config
from ..common import desktopentry, dialogs, launcher
from ..common.appkit import T
from ..common.window import HDialog
from ..i18n import plain
from ..theme import iconcache

USER_APPS = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "applications")


def entry_for(key):
    if key.startswith("desktop:"):
        return desktopentry.all_entries().get(key[8:])
    return None


def builtin_info(key):
    from .startmenu import BUILTIN_MENU
    b = BUILTIN_MENU.get(key[8:]) if key.startswith("builtin:") else None
    return b


def display_name(key):
    e = entry_for(key)
    if e:
        return e.name
    b = builtin_info(key)
    return plain(b[0]) if b else key


def launch(key):
    e = entry_for(key)
    if e:
        launcher.launch_entry(e)
        return
    b = builtin_info(key)
    if b:
        b[2]()


# ---------------------------------------------------------------- zmiany w plikach .desktop użytkownika
def _override(entry, changes):
    """Kopia wpisu w ~/.local/share/applications z podmienionymi kluczami (ma pierwszeństwo przed systemowym)."""
    os.makedirs(USER_APPS, exist_ok=True)
    try:
        with open(entry.path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = ["[Desktop Entry]", "Type=Application", f"Name={entry.name}", f"Exec={entry.exec}"]
    out, section, done = [], None, set()
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            if section == "Desktop Entry":
                for k, v in changes.items():
                    if k not in done:
                        out.append(f"{k}={v}")
                        done.add(k)
            section = s[1:-1]
            out.append(line)
            continue
        if section == "Desktop Entry" and "=" in s:
            k = s.split("=", 1)[0].strip()
            base = k.split("[", 1)[0]
            if base in changes:
                if k == base:
                    out.append(f"{k}={changes[k]}")
                    done.add(k)
                # wersje zlokalizowane (Name[pl]=…) usuwamy, żeby nowa nazwa była widoczna
                continue
        out.append(line)
    if section == "Desktop Entry":
        for k, v in changes.items():
            if k not in done:
                out.append(f"{k}={v}")
    path = os.path.join(USER_APPS, entry.id)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    desktopentry.all_entries(refresh=True)
    return path


def desktop_shortcut(key):
    desk = config.user_dir("DESKTOP")
    os.makedirs(desk, exist_ok=True)
    e = entry_for(key)
    if e:
        dst = os.path.join(desk, os.path.basename(e.path))
        shutil.copyfile(e.path, dst)
        os.chmod(dst, 0o755)
        return dst
    b = builtin_info(key)
    if b:
        name = key[8:]
        dst = os.path.join(desk, f"horyzont-{name}.desktop")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(f"[Desktop Entry]\nType=Application\nName={plain(b[0])}\nExec=horyzont-{name}\n"
                    f"Icon={b[1]}\n")
        os.chmod(dst, 0o755)
        return dst
    return None


def owner_package(entry):
    """('flatpak', id, zakres) albo ('rpm', nazwa) albo None."""
    p = os.path.realpath(entry.path)
    if "/flatpak/exports/" in p:
        scope = "user" if p.startswith(os.path.expanduser("~")) else "system"
        return ("flatpak", entry.id[:-8] if entry.id.endswith(".desktop") else entry.id, scope)
    if shutil.which("rpm") and p.startswith("/usr/"):
        r = subprocess.run(["rpm", "-qf", "--qf", "%{NAME}\n", p], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() and "not owned" not in r.stdout:
            return ("rpm", r.stdout.strip().splitlines()[0])
    return None


def uninstall(key, parent=None):
    e = entry_for(key)
    if not e:
        return
    own = owner_package(e)
    if own is None:
        dialogs.message(parent, T("Odinstaluj", "Uninstall"),
                        T("Nie udało się ustalić, z jakiego pakietu pochodzi ten program.",
                          "Could not find the package this program comes from."), "info")
        return
    name = e.name
    label = own[1]
    if dialogs.message(parent, T("Odinstaluj", "Uninstall"),
                       T(f"Czy na pewno chcesz odinstalować program „{name}” (pakiet {label})?",
                         f"Are you sure you want to uninstall '{name}' (package {label})?"),
                       "question", ("yes", "no")) != "yes":
        return
    from ..common.jobs import run_job
    if own[0] == "flatpak":
        args = ["flatpak", "uninstall", "-y", "--noninteractive"] + (["--user"] if own[2] == "user" else []) + [own[1]]
        root = own[2] != "user"
    else:
        dnf = shutil.which("dnf5") or shutil.which("dnf") or "dnf"
        args = [dnf, "remove", "-y", own[1]]
        root = True
    run_job(parent, T("Odinstalowywanie", "Uninstalling"), T(f"Odinstalowywanie: {name}", f"Uninstalling {name}"),
            args, root=root)
    desktopentry.all_entries(refresh=True)


# ---------------------------------------------------------------- właściwości skrótu
class ShortcutProperties(HDialog):
    def __init__(self, key, parent=None):
        self.key = key
        self.entry = entry_for(key)
        name = display_name(key)
        super().__init__(T(f"Właściwości: {name}", f"{name} Properties"), "properties", parent)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        e = self.entry
        icon = iconcache.theme_or_builtin(e.icon, "app") if e else iconcache.icon(builtin_info(key)[1])
        # Ogólne
        w = QWidget()
        g = QGridLayout(w)
        ic = QLabel()
        ic.setPixmap(icon.pixmap(32, 32))
        g.addWidget(ic, 0, 0)
        self.name = QLineEdit(name)
        self.name.setEnabled(e is not None)
        g.addWidget(self.name, 0, 1)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        g.addWidget(line, 1, 0, 1, 2)
        rows = [(T("Typ pliku:", "Type of file:"), T("Skrót (plik .desktop)", "Shortcut (.desktop)") if e else
                 T("Program wbudowany Horyzontu", "Built-in Horyzont program")),
                (T("Lokalizacja:", "Location:"), os.path.dirname(e.path) if e else "—"),
                (T("Plik:", "File:"), os.path.basename(e.path) if e else "—")]
        for i, (k, v) in enumerate(rows):
            g.addWidget(QLabel(k), i + 2, 0)
            lv = QLabel(v)
            lv.setWordWrap(True)
            lv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(lv, i + 2, 1)
        g.setRowStretch(10, 1)
        g.setColumnStretch(1, 1)
        tabs.addTab(w, T("Ogólne", "General"))
        # Skrót
        w2 = QWidget()
        g2 = QGridLayout(w2)
        self.exec = QLineEdit(e.exec if e else f"horyzont-{key[8:]}")
        self.path = QLineEdit(e.path_dir if e else "")
        self.comment = QLineEdit(e.comment if e else "")
        self.icon = QLineEdit(e.icon if e else "")
        for i, (k, wd) in enumerate(((T("Element docelowy:", "Target:"), self.exec),
                                     (T("Rozpocznij w:", "Start in:"), self.path),
                                     (T("Komentarz:", "Comment:"), self.comment),
                                     (T("Ikona:", "Icon:"), self.icon))):
            g2.addWidget(QLabel(k), i, 0)
            wd.setEnabled(e is not None)
            g2.addWidget(wd, i, 1)
        if e:
            loc = QPushButton(T("&Znajdź element docelowy", "&Find Target"))
            loc.clicked.connect(self._find_target)
            g2.addWidget(loc, 4, 1, Qt.AlignLeft)
        g2.setRowStretch(5, 1)
        tabs.addTab(w2, T("Skrót", "Shortcut"))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        self.resize(400, 380)

    def _find_target(self):
        args = desktopentry.expand_exec(self.exec.text())
        prog = shutil.which(args[0]) if args else None
        if prog:
            launcher.start_builtin("explorer", [os.path.dirname(os.path.realpath(prog))])

    def _save(self):
        e = self.entry
        if e is not None:
            changes = {}
            if self.name.text().strip() and self.name.text().strip() != e.name:
                changes["Name"] = self.name.text().strip()
            if self.exec.text().strip() != e.exec:
                changes["Exec"] = self.exec.text().strip()
            if self.path.text().strip() != e.path_dir:
                changes["Path"] = self.path.text().strip()
            if self.comment.text().strip() != e.comment:
                changes["Comment"] = self.comment.text().strip()
            if self.icon.text().strip() != e.icon:
                changes["Icon"] = self.icon.text().strip()
            if changes:
                _override(e, changes)
        self.accept()


# ---------------------------------------------------------------- menu kontekstowe
def program_context(parent, key, gpos, on_change=None, on_launch=None):
    """Menu kontekstowe programu (wpis .desktop albo wbudowany)."""
    e = entry_for(key)
    m = QMenu(parent)
    a = m.addAction(T("&Otwórz", "&Open"))
    f = QFont(a.font())
    f.setBold(True)
    a.setFont(f)

    def do_launch():
        if on_launch:
            on_launch()
        launch(key)
    a.triggered.connect(do_launch)
    if e and e.path:
        m.addAction(T("Otwórz &lokalizację pliku", "Open File &Location"),
                    lambda: launcher.start_builtin("explorer", [os.path.dirname(e.path)]))
    m.addSeparator()
    pinned = list(config.get("start_pinned", []))
    if key in pinned:
        m.addAction(T("Odepnij od menu &Start", "Unpin from Start men&u"),
                    lambda: (pinned.remove(key), config.set("start_pinned", pinned), on_change and on_change()))
    else:
        m.addAction(T("Przypnij do menu &Start", "Pin to Start men&u"),
                    lambda: (pinned.append(key), config.set("start_pinned", pinned), on_change and on_change()))
    st = m.addMenu(T("Wyślij &do", "Se&nd To"))
    st.addAction(iconcache.icon("desktop_folder"), T("Pulpit (utwórz skrót)", "Desktop (create shortcut)"),
                 lambda: desktop_shortcut(key))
    ql = list(config.get("quick_launch", []))
    if key not in ql:
        st.addAction(iconcache.icon("show_desktop"), T("Pasek Szybkie uruchamianie", "Quick Launch"),
                     lambda: (config.update({"quick_launch": ql + [key], "taskbar_quick_launch": True})))
    m.addSeparator()
    if e:
        m.addAction(T("Zmień &nazwę", "Rena&me"), lambda: _rename(parent, key, on_change))
        m.addAction(T("&Usuń z menu", "&Remove from menu"), lambda: _hide(parent, key, on_change))
        m.addAction(iconcache.icon("addremove"), T("Odins&taluj…", "Unins&tall..."), lambda: uninstall(key, None))
        m.addSeparator()
    else:
        rp = dict(config.get("recent_programs", {}))
        if key in rp:
            m.addAction(T("&Usuń z tej listy", "Remove from This &List"),
                        lambda: (rp.__setitem__(key, -1000), config.set("recent_programs", rp), on_change and on_change()))
            m.addSeparator()
    m.addAction(T("&Właściwości", "P&roperties"), lambda: ShortcutProperties(key).exec())
    m.exec(gpos)


def _rename(parent, key, on_change):
    e = entry_for(key)
    if not e:
        return
    new = dialogs.ask_text(None, T("Zmień nazwę", "Rename"), T("Nowa nazwa:", "New name:"), e.name)
    if new and new.strip() and new.strip() != e.name:
        _override(e, {"Name": new.strip()})
        if on_change:
            on_change()


def _hide(parent, key, on_change):
    e = entry_for(key)
    if not e:
        return
    if dialogs.message(None, T("Usuwanie z menu", "Remove from menu"),
                       T(f"Usunąć „{e.name}” z menu Start?\nProgram pozostanie zainstalowany.",
                         f"Remove '{e.name}' from the Start menu?\nThe program stays installed."),
                       "question", ("yes", "no")) == "yes":
        _override(e, {"NoDisplay": "true"})
        if on_change:
            on_change()


class ProgramMenu(QMenu):
    """QMenu menu Start: prawy przycisk na programie otwiera jego menu kontekstowe."""

    def __init__(self, owner, title="", parent=None):
        super().__init__(title, parent)
        self.owner = owner
        self.setToolTipsVisible(True)

    def contextMenuEvent(self, ev):
        a = self.actionAt(ev.pos())
        key = a.data() if a is not None else None
        if isinstance(key, str) and (key.startswith("desktop:") or key.startswith("builtin:")):
            program_context(self, key, ev.globalPos(), on_change=self.owner.mark_dirty,
                            on_launch=self.owner.close_all)
            return
        super().contextMenuEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.RightButton:
            return
        super().mouseReleaseEvent(ev)

