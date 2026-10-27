"""„Otwórz za pomocą” w stylu klasycznego Windows, okno dla nieznanych typów plików oraz programy Windows (.exe).

Uruchamiane jako osobny proces (``python3 -m horyzont openwith ...``), żeby działało tak samo z pulpitu,
Eksploratora, okna Uruchamianie i innych programów:

    openwith <plik>              okno „Otwórz za pomocą”
    openwith --unknown <plik>    „Horyzont nie może otworzyć tego pliku” (brak skojarzonego programu)
    openwith --windows <plik>    program Windows bez zainstalowanego Wine/Bottles — propozycja instalacji
"""
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from . import desktopentry, launcher
from .appkit import T
from .window import HDialog
from ..theme import iconcache

# typy MIME programów Windows (różne wersje shared-mime-info używają różnych nazw)
WINDOWS_MIMES = ["application/x-ms-dos-executable", "application/x-msdownload",
                 "application/vnd.microsoft.portable-executable", "application/x-msi", "application/x-ms-shortcut",
                 "application/x-bat", "application/x-wine-extension-msp"]
WINDOWS_EXT = {".exe": "application/x-ms-dos-executable", ".msi": "application/x-msi", ".com":
               "application/x-ms-dos-executable", ".bat": "application/x-bat", ".lnk": "application/x-ms-shortcut",
               ".msp": "application/x-wine-extension-msp", ".scr": "application/x-ms-dos-executable"}
BOTTLES_ID = "com.usebottles.bottles"
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"


# ---------------------------------------------------------------- typy MIME i programy
def mime_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in WINDOWS_EXT:
        return WINDOWS_EXT[ext]
    mt = mimetypes.guess_type(path)[0]
    if mt and mt != "application/octet-stream":
        return mt
    if shutil.which("file"):
        try:
            out = subprocess.run(["file", "-b", "--mime-type", path], capture_output=True, text=True,
                                 timeout=3).stdout.strip()
            if out and "/" in out:
                return out
        except (OSError, subprocess.SubprocessError):
            pass
    return mt or "application/octet-stream"


def _mime_matches(entry_types, mime):
    if mime in entry_types:
        return True
    top = mime.split("/")[0]
    if top + "/*" in entry_types:
        return True
    if mime in WINDOWS_MIMES and any(t in WINDOWS_MIMES for t in entry_types):
        return True
    # pliki tekstowe (skrypty, konfiguracje, kod) otwiera każdy edytor tekstu
    if top == "text" and "text/plain" in entry_types:
        return True
    return False


def program_lists(path, mime=None):
    """(zalecane, inne) — listy DesktopEntry. Zalecane: programy deklarujące obsługę typu pliku."""
    mime = mime or mime_for(path)
    entries = desktopentry.all_entries()
    rec, other = [], []
    for e in entries.values():
        user_app = e.id.startswith("userapp-")
        if not (e.visible() or (user_app and e.exec)):
            continue
        if _mime_matches(getattr(e, "mimetypes", ()), mime):
            rec.append(e)
        elif not user_app:
            other.append(e)
    default = desktopentry.default_for_mime(mime)
    rec.sort(key=lambda e: (e.id != default, not e.id.startswith("horyzont-"), e.name.lower()))
    other.sort(key=lambda e: e.name.lower())
    return rec, other


def register_program(exe_path, mime):
    """Program wybrany przez „Przeglądaj…” — ukryty plik .desktop, żeby dało się go zapamiętać jako domyślny."""
    base = os.path.basename(exe_path)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-") or "program"
    appdir = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "applications")
    os.makedirs(appdir, exist_ok=True)
    did = f"userapp-{slug}.desktop"
    path = os.path.join(appdir, did)
    types = []
    old = desktopentry.parse(path) if os.path.exists(path) else None
    if old is not None:
        types = list(getattr(old, "mimetypes", ()))
    if mime not in types:
        types.append(mime)
    quoted = exe_path.replace("\\", "\\\\").replace('"', '\\"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\n"
                f"Name={base}\nExec=\"{quoted}\" %f\nNoDisplay=true\n"
                f"MimeType={';'.join(types)};\nX-Horyzont-UserApp=true\n")
    desktopentry.all_entries(refresh=True)
    return did


# ---------------------------------------------------------------- programy Windows
def bottles_installed():
    for base in ("/var/lib/flatpak/app", os.path.expanduser("~/.local/share/flatpak/app")):
        if os.path.isdir(os.path.join(base, BOTTLES_ID)):
            return True
    return False


def windows_runner(path):
    """Polecenie uruchamiające program Windows albo None, gdy nie ma czym (brak Wine i Bottles)."""
    ext = os.path.splitext(path)[1].lower()
    mime = WINDOWS_EXT.get(ext, WINDOWS_MIMES[0])
    entries = desktopentry.all_entries()
    for m in [mime] + WINDOWS_MIMES:
        did = desktopentry.default_for_mime(m)
        if did and did in entries and not did.startswith("horyzont-"):
            args = entries[did].command([path])
            if args:
                return args
    if shutil.which("wine"):
        return ["wine", "start", "/unix", path]
    if bottles_installed() and shutil.which("flatpak"):
        return ["flatpak", "run", "--command=bottles", "--file-forwarding", BOTTLES_ID, "@@", path, "@@"]
    return None


def pe_info(path):
    """Opis i producent z zasobu wersji programu (jak w Właściwościach pliku w Windows)."""
    try:
        import pefile
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        info = {}
        for fi in getattr(pe, "FileInfo", []) or []:
            for entry in fi:
                for st in getattr(entry, "StringTable", []) or []:
                    for k, v in st.entries.items():
                        info[k.decode("utf-8", "ignore")] = v.decode("utf-8", "ignore").strip()
        pe.close()
        return info
    except Exception:
        return {}


def _file_icon(path, size=32):
    from .exeicon import icon_sync
    ic = icon_sync(path) if os.path.splitext(path)[1].lower() in (".exe", ".scr") else None
    if ic is not None:
        return ic.pixmap(size, size)
    return iconcache.pixmap(iconcache.name_for_file(path, False), size)


def _header(lay, path, text):
    row = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(_file_icon(path))
    ic.setFixedSize(40, 40)
    ic.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    row.addWidget(ic)
    col = QVBoxLayout()
    t = QLabel(text)
    t.setWordWrap(True)
    col.addWidget(t)
    f = QLabel(T("Plik: ", "File: ") + f"<b>{_esc(os.path.basename(path))}</b>")
    f.setTextFormat(Qt.RichText)
    col.addWidget(f)
    row.addLayout(col, 1)
    lay.addLayout(row)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _line():
    ln = QFrame()
    ln.setFrameShape(QFrame.HLine)
    ln.setFrameShadow(QFrame.Sunken)
    return ln


# ---------------------------------------------------------------- Otwórz za pomocą
class OpenWithDialog(HDialog):
    def __init__(self, path, parent=None, always=False, launch=True):
        super().__init__(T("Otwórz za pomocą", "Open With"), "app", parent)
        self.path = path
        self.launch = launch
        self.mime = mime_for(path)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        _header(lay, path, T("Wybierz program, którego chcesz użyć do otwarcia tego pliku:",
                             "Choose the program you want to use to open this file:"))
        lay.addWidget(QLabel(T("Programy", "Programs")))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QSize(32, 32))
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._ok() if it.data(0, Qt.UserRole) else None)
        self.tree.currentItemChanged.connect(self._sel_changed)
        lay.addWidget(self.tree, 1)
        self._fill()
        row = QHBoxLayout()
        row.addStretch(1)
        br = QPushButton(T("P&rzeglądaj...", "B&rowse..."))
        br.clicked.connect(self._browse)
        row.addWidget(br)
        lay.addLayout(row)
        self.always = QCheckBox(T("&Zawsze używaj wybranego programu do otwierania tego rodzaju plików",
                                  "&Always use the selected program to open this kind of file"))
        self.always.setChecked(always or not launch)
        self.always.setVisible(launch)
        lay.addWidget(self.always)
        web = QLabel(T("Jeśli programu nie ma na liście lub na komputerze, możesz "
                       "<a href='search'>poszukać odpowiedniego programu w Flathub</a>.",
                       "If the program you want is not in the list or on your computer, you can "
                       "<a href='search'>look for the appropriate program on Flathub</a>."))
        web.setWordWrap(True)
        web.setTextFormat(Qt.RichText)
        web.linkActivated.connect(lambda _l: search_web(self.path, self.mime))
        lay.addWidget(web)
        lay.addWidget(_line())
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._ok)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(ca)
        lay.addLayout(btns)
        self.resize(430, 520)
        self._sel_changed(self.tree.currentItem(), None)

    def _group(self, title):
        g = QTreeWidgetItem([title])
        f = g.font(0)
        f.setBold(True)
        g.setFont(0, f)
        g.setFlags(Qt.ItemIsEnabled)
        self.tree.addTopLevelItem(g)
        g.setExpanded(True)
        return g

    def _fill(self, select_id=None):
        self.tree.clear()
        rec, other = program_lists(self.path, self.mime)
        first = None
        for title, lst in ((T("Programy zalecane:", "Recommended Programs:"), rec),
                           (T("Inne programy:", "Other Programs:"), other)):
            if not lst:
                continue
            g = self._group(title)
            for e in lst:
                it = QTreeWidgetItem(g, [e.name])
                it.setIcon(0, iconcache.theme_or_builtin(e.icon, "app"))
                it.setData(0, Qt.UserRole, e.id)
                if e.comment:
                    it.setToolTip(0, e.comment)
                if first is None or e.id == select_id:
                    first = it
        if first is not None:
            self.tree.setCurrentItem(first)

    def _sel_changed(self, cur, _prev):
        if hasattr(self, "ok_btn"):
            self.ok_btn.setEnabled(bool(cur is not None and cur.data(0, Qt.UserRole)))

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, T("Otwórz za pomocą...", "Open With..."), "/usr/bin",
                                           T("Programy (*)", "Programs (*)"))
        if not f:
            return
        if f.endswith(".desktop"):
            e = desktopentry.parse(f)
            did = os.path.basename(f) if e else None
        else:
            if not os.access(f, os.X_OK):
                from .dialogs import message
                message(self, T("Otwórz za pomocą", "Open With"),
                        T("Wybrany plik nie jest programem.", "The selected file is not a program."), "warning", ("ok",))
                return
            did = register_program(f, self.mime)
        if did:
            self._fill(did)

    def chosen(self):
        it = self.tree.currentItem()
        did = it.data(0, Qt.UserRole) if it is not None else None
        return desktopentry.all_entries().get(did) if did else None

    def _ok(self):
        e = self.chosen()
        if e is None:
            return
        if self.always.isChecked():
            try:
                desktopentry.set_default_for_mime(self.mime, e.id)
            except OSError as ex:
                print("horyzont: nie można zapisać domyślnego programu:", ex, file=sys.stderr)
        if self.launch:
            launcher.add_recent_document(self.path)
            launcher.launch_entry(e, [self.path])
        self.accept()


def search_web(path, mime):
    ext = os.path.splitext(path)[1].lstrip(".") or mime.split("/")[-1]
    launcher.xdg_open("https://flathub.org/apps/search?q=" + urllib.parse.quote(ext))


# ---------------------------------------------------------------- nieznany typ pliku
class UnknownTypeDialog(HDialog):
    def __init__(self, path, parent=None):
        super().__init__("Horyzont", "warning", parent)
        self.path = path
        self.choice = None
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        _header(lay, path, T("Horyzont nie może otworzyć tego pliku:", "Horyzont cannot open this file:"))
        txt = QLabel(T("Aby otworzyć ten plik, Horyzont musi wiedzieć, jaki program go utworzył. Możesz "
                       "poszukać programu w sieci Web albo wybrać go ręcznie z listy programów zainstalowanych "
                       "na tym komputerze.\n\nCo chcesz zrobić?",
                       "To open this file, Horyzont needs to know what program created it. You can look it up on "
                       "the Web or manually select from a list of programs on your computer.\n\n"
                       "What do you want to do?"))
        txt.setWordWrap(True)
        lay.addWidget(txt)
        self.grp = QButtonGroup(self)
        self.web = QRadioButton(T("&Użyj usługi sieci Web, aby znaleźć odpowiedni program",
                                  "&Use the Web service to find the appropriate program"))
        self.lst = QRadioButton(T("&Wybierz program z listy", "&Select the program from a list"))
        self.lst.setChecked(True)
        for i, b in enumerate((self.web, self.lst)):
            self.grp.addButton(b, i)
            lay.addWidget(b)
        lay.addSpacing(6)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(ca)
        lay.addLayout(btns)
        self.setFixedWidth(440)

    def _ok(self):
        self.choice = "web" if self.web.isChecked() else "list"
        self.accept()


# ---------------------------------------------------------------- programy Windows bez Wine
class WindowsProgramDialog(HDialog):
    def __init__(self, path, parent=None):
        super().__init__(T("Program dla systemu Windows", "Windows Program"), "file_exe", parent)
        self.path = path
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        _header(lay, path, T("Ten plik jest programem dla systemu Windows.", "This file is a Windows program."))
        info = pe_info(path) if os.path.splitext(path)[1].lower() in (".exe", ".scr") else {}
        details = []
        desc = info.get("FileDescription") or info.get("ProductName")
        if desc:
            details.append(T("Opis: ", "Description: ") + _esc(desc))
        if info.get("CompanyName"):
            details.append(T("Producent: ", "Company: ") + _esc(info["CompanyName"]))
        if info.get("ProductVersion") or info.get("FileVersion"):
            details.append(T("Wersja: ", "Version: ") + _esc(info.get("ProductVersion") or info.get("FileVersion")))
        if details:
            d = QLabel("<br>".join(details))
            d.setTextFormat(Qt.RichText)
            d.setStyleSheet("color: #404040;")
            d.setContentsMargins(46, 0, 0, 0)
            lay.addWidget(d)
        txt = QLabel(T("Horyzont może uruchamiać wiele programów Windows za pomocą warstwy zgodności. "
                       "Nie jest ona jeszcze zainstalowana. Wybierz, co zainstalować:",
                       "Horyzont can run many Windows programs using a compatibility layer, which is not installed "
                       "yet. Choose what to install:"))
        txt.setWordWrap(True)
        lay.addWidget(txt)
        self.grp = QButtonGroup(self)
        self.bottles = QRadioButton(T("&Bottles (zalecane)", "&Bottles (recommended)"))
        self.bottles.setChecked(True)
        lay.addWidget(self.bottles)
        lay.addWidget(self._desc(T("Każdy program działa w osobnej „butelce” z gotowymi ustawieniami (gry, programy "
                                   "biurowe). Instalacja z Flathub — około 1 GB do pobrania.",
                                   "Each program runs in its own bottle with ready-made presets. Installed from "
                                   "Flathub — about 1 GB to download.")))
        self.wine = QRadioButton(T("&Wine", "&Wine"))
        lay.addWidget(self.wine)
        lay.addWidget(self._desc(T("Klasyczna warstwa zgodności z repozytorium Fedory. Programy uruchamiają się od "
                                   "razu po dwukrotnym kliknięciu.",
                                   "The classic compatibility layer from the Fedora repositories. Programs start "
                                   "right away on double-click.")))
        self.grp.addButton(self.bottles, 0)
        self.grp.addButton(self.wine, 1)
        note = QLabel(T("Uwaga: nie każdy program Windows działa poprawnie. Instalatory sterowników i programy "
                        "antywirusowe nie zadziałają.",
                        "Note: not every Windows program works. Driver installers and antivirus software will not "
                        "work."))
        note.setWordWrap(True)
        note.setStyleSheet("color: #606060;")
        lay.addWidget(note)
        lay.addWidget(_line())
        btns = QHBoxLayout()
        ow = QPushButton(T("Otwórz &za pomocą...", "Open &With..."))
        ow.clicked.connect(self._open_with)
        btns.addWidget(ow)
        btns.addStretch(1)
        inst = QPushButton(T("&Zainstaluj i uruchom", "&Install and Run"))
        inst.setDefault(True)
        inst.clicked.connect(self._install)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        btns.addWidget(inst)
        btns.addWidget(ca)
        lay.addLayout(btns)
        self.setFixedWidth(450)

    def _desc(self, text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setContentsMargins(22, 0, 0, 4)
        return lb

    def install_command(self):
        if self.wine.isChecked():
            return ["dnf", "install", "-y", "wine"], "Wine"
        steps = []
        if not shutil.which("flatpak"):
            steps.append("dnf install -y flatpak")
        steps.append(f"flatpak remote-add --if-not-exists flathub {FLATHUB}")
        steps.append(f"flatpak install -y --noninteractive flathub {BOTTLES_ID}")
        return ["sh", "-c", " && ".join(steps)], "Bottles"

    def _install(self):
        from .jobs import run_job
        args, name = self.install_command()
        ok, _out = run_job(self, T("Instalowanie", "Installing"), T(f"Instalowanie: {name}", f"Installing {name}"),
                           args, root=True, icon="addremove", auto_close=True)
        if not ok:
            return
        desktopentry.all_entries(refresh=True)
        run = windows_runner(self.path)
        if run:
            launcher._spawn(run, cwd=os.path.dirname(self.path))
        self.accept()

    def _open_with(self):
        self.hide()
        d = OpenWithDialog(self.path)
        d.exec()
        self.accept()


# ---------------------------------------------------------------- podmenu „Otwórz za pomocą”
def fill_menu(menu, path):
    """Podmenu jak w Windows XP: programy zalecane dla typu pliku, kreska, „Wybierz program...”."""
    rec, _other = program_lists(path)
    seen = set()
    for e in rec[:14]:
        if e.name in seen:
            continue
        seen.add(e.name)
        menu.addAction(iconcache.theme_or_builtin(e.icon, "app"), e.name,
                       lambda e=e: launcher.open_path(path, with_entry=e))
    if not rec:
        menu.addAction(iconcache.icon("notepad"), T("Notatnik", "Notepad"),
                       lambda: launcher.start_builtin("notepad", [path]))
    menu.addSeparator()
    menu.addAction(T("&Wybierz program...", "&Choose Program..."), lambda: launcher.open_with_dialog(path))


# ---------------------------------------------------------------- wejście
def open_with(path, parent=None):
    d = OpenWithDialog(path, parent)
    d.exec()


def handle(args):
    mode = "open"
    files = []
    for a in args:
        if a == "--unknown":
            mode = "unknown"
        elif a == "--windows":
            mode = "windows"
        elif a == "--always":
            mode = "always"
        else:
            files.append(a)
    for path in files:
        if not os.path.exists(path):
            continue
        if mode == "windows":
            d = WindowsProgramDialog(path)
            d.exec()
        elif mode == "unknown":
            d = UnknownTypeDialog(path)
            if d.exec():
                if d.choice == "web":
                    search_web(path, mime_for(path))
                else:
                    OpenWithDialog(path, always=True).exec()
        else:
            OpenWithDialog(path, always=(mode == "always")).exec()


def main(args):
    from .app import make_app
    app = make_app("openwith")
    app.setQuitOnLastWindowClosed(False)
    handle([os.path.abspath(a) if not a.startswith("-") else a for a in args])
    return 0
