"""Dodaj lub usuń programy (RPM/DNF i Flatpak)."""
import os
import shutil
import subprocess

from PySide6.QtCore import QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget, QAbstractItemView, QHeaderView)

from ...common import desktopentry, dialogs, sysctl
from ...common.jobs import run_job
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ...theme.base import vgrad
from ...theme.manager import current
from .common import run

DNF = shutil.which("dnf") or shutil.which("dnf5") or "dnf"

COMPONENTS = [
    ("cmp_games", "games", ["gnome-mines", "aisleriot", "gnome-chess"]),
    ("cmp_graphics", "paint", ["gimp", "inkscape"]),
    ("cmp_office", "file_doc", ["libreoffice-writer", "libreoffice-calc"]),
    ("cmp_media", "media_player", ["vlc", "celluloid"]),
    ("cmp_wine", "app", ["wine"]),
    ("cmp_fonts", "fonts", ["wine-tahoma-fonts-system", "liberation-fonts"]),
    ("cmp_mail", "email", ["thunderbird"]),
    ("cmp_browser", "browser", ["flatpak:org.mozilla.firefox"]),
    ("cmp_screensaver", "display", ["swayidle", "swaylock"]),
    ("cmp_printing", "printer", ["cups", "cups-filters"]),
    ("cmp_flatpak", "flatpak", ["flatpak"]),
    ("cmp_archives", "folder_zip", ["7zip", "unar"]),
    ("cmp_bluetooth", "bluetooth", ["bluez"]),
]

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


class LoadWorker(QThread):
    loaded = Signal(list)

    def run(self):
        items = {}
        entries = [e for e in desktopentry.all_entries().values() if e.visible()]
        paths = [e.path for e in entries if e.path.startswith("/usr/")]
        owners = {}
        if paths and shutil.which("rpm"):
            try:
                r = subprocess.run(["rpm", "-qf", "--qf", "%{NAME}\t%{SIZE}\t%{VERSION}-%{RELEASE}\n"] + paths,
                                   capture_output=True, text=True, timeout=60)
                lines = r.stdout.splitlines()
                for pth, line in zip(paths, lines):
                    parts = line.split("\t")
                    if len(parts) == 3 and "not owned" not in line and "nie należy" not in line:
                        owners[pth] = (parts[0], int(parts[1] or 0), parts[2])
            except Exception:
                pass
        flat = {}
        if shutil.which("flatpak"):
            try:
                r = subprocess.run(["flatpak", "list", "--app", "--columns=application,name,size,version,installation"],
                                   capture_output=True, text=True, timeout=30)
                for line in r.stdout.splitlines():
                    p = line.split("\t")
                    if len(p) >= 5:
                        flat[p[0]] = p
            except Exception:
                pass
        for e in entries:
            if e.path in owners:
                pkg, size, ver = owners[e.path]
                key = ("rpm", pkg)
                if key not in items:
                    items[key] = {"name": e.name, "pkg": pkg, "size": size, "version": ver, "kind": "rpm",
                                  "icon": e.icon, "comment": e.comment}
            else:
                appid = e.id[:-8] if e.id.endswith(".desktop") else e.id
                if appid in flat:
                    p = flat[appid]
                    items[("flatpak", appid)] = {"name": e.name, "pkg": appid, "size_text": p[2], "size": 0,
                                                 "version": p[3], "kind": "flatpak", "icon": e.icon,
                                                 "comment": e.comment, "installation": p[4]}
        self.loaded.emit(sorted(items.values(), key=lambda d: d["name"].lower()))


class CommandWorker(QThread):
    done = Signal(int, str)

    def __init__(self, args):
        super().__init__()
        self.args = args

    def run(self):
        try:
            r = subprocess.run(self.args, capture_output=True, text=True, timeout=3600)
            self.done.emit(r.returncode, (r.stdout + "\n" + r.stderr).strip())
        except Exception as e:
            self.done.emit(-1, str(e))


class SideButton(QWidget):
    """Duży przycisk na lewym pasku okna (ikona nad podpisem)."""

    def __init__(self, icon, text, cb, parent=None):
        super().__init__(parent)
        self.icon, self.text, self.cb = icon, text, cb
        self.active = False
        self._hover = False
        self.setFixedSize(100, 92)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.cb()

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        if self.active or self._hover:
            c = QColor(255, 255, 255, 70 if self.active else 40)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(c)
            p.setPen(QColor(255, 255, 255, 140))
            p.drawRoundedRect(self.rect().adjusted(4, 2, -4, -2), 4, 4)
        p.drawPixmap((self.width() - 32) // 2, 8, iconcache.pixmap(self.icon, 32))
        f = t.font("normal")
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(4, 44, self.width() - 8, self.height() - 46), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                   self.text)


class SideBar(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        sc = getattr(t, "sc", None) or {"accent_dark": "#0f5d67", "accent": "#1f8591"}
        p.fillRect(self.rect(), vgrad(self.rect(), [(0, sc["accent"]), (1, sc["accent_dark"])]))


class AddRemoveWindow(HWindow):
    def __init__(self, page=None):
        super().__init__(plain("addremove"), "addremove")
        root = QHBoxLayout(self.body())
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = SideBar()
        side.setFixedWidth(108)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(4, 6, 4, 6)
        self.side_buttons = []
        for icon, key, idx in (("addremove", "ar_change_remove", 0), ("drive_cd", "ar_add_new", 1),
                               ("flatpak", "ar_flatpak_tab", 2), ("programs", "ar_components", 3)):
            b = SideButton(icon, plain(key), lambda i=idx: self.show_page(i))
            sl.addWidget(b)
            self.side_buttons.append(b)
        sl.addStretch(1)
        root.addWidget(side)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self._build_installed()
        self._build_add()
        self._build_flatpak()
        self._build_components()
        self.resize(760, 540)
        self.show_page({"add": 1, "flatpak": 2, "components": 3}.get(page, 0))

    def show_page(self, i):
        self.stack.setCurrentIndex(i)
        for j, b in enumerate(self.side_buttons):
            b.active = j == i
            b.update()
        if i == 2 and not getattr(self, "_fp_loaded", False):
            self._fp_loaded = True
            self._fp_refresh()

    # ------------------------------------------------------------ zainstalowane
    def _build_installed(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>" + plain("ar_installed") + "</b>"))
        top.addStretch(1)
        self.show_upd = QCheckBox(tr("ar_show_updates").replace("&", ""))
        self.show_upd.setEnabled(False)
        top.addWidget(self.show_upd)
        top.addWidget(QLabel(plain("ar_sort_by")))
        self.sort = QComboBox()
        self.sort.addItems([plain("name"), plain("ar_size")])
        self.sort.currentIndexChanged.connect(self._sort)
        top.addWidget(self.sort)
        lay.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([plain("name"), plain("ar_size"), plain("ar_source")])
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(32, 32))
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 70)
        self.tree.currentItemChanged.connect(self._selected)
        lay.addWidget(self.tree, 1)
        self.detail = QFrame()
        self.detail.setStyleSheet(f"QFrame {{ background: {current().color('highlight').lighter(185).name()}; }}")
        dl = QHBoxLayout(self.detail)
        self.detail_lbl = QLabel()
        self.detail_lbl.setWordWrap(True)
        dl.addWidget(self.detail_lbl, 1)
        self.remove_btn = QPushButton(plain("ar_remove"))
        self.remove_btn.clicked.connect(self._remove)
        dl.addWidget(self.remove_btn)
        self.detail.hide()
        lay.addWidget(self.detail)
        self.loading = QLabel(plain("ar_loading"))
        lay.addWidget(self.loading)
        self.stack.addWidget(w)
        self._loader = LoadWorker()
        self._loader.loaded.connect(self._loaded)
        self._loader.start()

    def _loaded(self, items):
        self.loading.hide()
        self.items = items
        self.tree.clear()
        for d in items:
            it = QTreeWidgetItem([d["name"], d.get("size_text") or (sysctl.human_size(d["size"]) if d["size"] else ""),
                                  plain("ar_flatpak") if d["kind"] == "flatpak" else plain("ar_rpm")])
            it.setIcon(0, iconcache.theme_or_builtin(d["icon"], "app"))
            it.setData(0, Qt.UserRole, d)
            it.setData(1, Qt.UserRole, d["size"])
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(it)

    def _sort(self, i):
        self.tree.sortItems(0 if i == 0 else 1, Qt.AscendingOrder if i == 0 else Qt.DescendingOrder)

    def _selected(self, cur, prev):
        if cur is None:
            self.detail.hide()
            return
        d = cur.data(0, Qt.UserRole)
        self.detail_lbl.setText(f"<b>{d['name']}</b> — {d.get('comment', '')}<br>{plain('ar_package')} {d['pkg']} "
                                f"({d.get('version', '')})")
        self.detail.show()

    def _remove(self):
        it = self.tree.currentItem()
        if it is None:
            return
        d = it.data(0, Qt.UserRole)
        if dialogs.message(self, plain("addremove"), tr("ar_remove_confirm", d["name"]), "question", ("yes", "no")) != "yes":
            return
        if d["kind"] == "flatpak":
            user = d.get("installation") == "user"
            args = ["flatpak", "uninstall", "-y", "--noninteractive", "--user" if user else "--system", d["pkg"]]
            root = not user
        else:
            args, root = [DNF, "remove", "-y", d["pkg"]], True
        ok, _ = run_job(self, plain("addremove"), tr("ar_removing", d["name"]), args, root)
        if ok:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(it))
            self.detail.hide()

    def _run(self, args, on_ok, text=None, root=True):
        """args bez pkexec — o uprawnienia dba okno postępu."""
        if args and args[0] == "pkexec":
            args = args[1:]
        ok, _ = run_job(self, plain("addremove"), text or plain("ar_working"), args, root)
        if ok:
            on_ok()

    # ------------------------------------------------------------ nowe programy
    def _build_add(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel("<b>" + plain("ar_add_new") + "</b>"))
        row = QHBoxLayout()
        row.addWidget(QLabel(plain("ar_search_repo")))
        self.q = QLineEdit()
        self.q.returnPressed.connect(self._search)
        row.addWidget(self.q, 1)
        b = QPushButton(plain("search_go"))
        b.clicked.connect(self._search)
        row.addWidget(b)
        lay.addLayout(row)
        self.results = QTreeWidget()
        self.results.setHeaderLabels([plain("name"), plain("adm_service_desc")])
        self.results.setRootIsDecorated(False)
        self.results.setColumnWidth(0, 200)
        lay.addWidget(self.results, 1)
        row2 = QHBoxLayout()
        self.search_status = QLabel()
        row2.addWidget(self.search_status, 1)
        inst = QPushButton(plain("ar_install"))
        inst.clicked.connect(self._install)
        row2.addWidget(inst)
        sw = QPushButton(plain("ar_open_software"))
        sw.clicked.connect(self._software_center)
        row2.addWidget(sw)
        lay.addLayout(row2)
        self.stack.addWidget(w)

    def _search(self):
        term = self.q.text().strip()
        if not term:
            return
        self.search_status.setText(plain("sys_checking"))
        self.results.clear()
        self._sw = CommandWorker([DNF, "-q", "repoquery", "--qf", "%{name}\t%{summary}\n", f"*{term}*"])

        def done(rc, out):
            seen = set()
            for line in out.splitlines():
                if "\t" not in line:
                    continue
                name, summ = line.split("\t", 1)
                if name in seen:
                    continue
                seen.add(name)
                it = QTreeWidgetItem([name, summ])
                it.setIcon(0, iconcache.icon("addremove"))
                self.results.addTopLevelItem(it)
            self.search_status.setText(tr("search_done", len(seen)))
        self._sw.done.connect(done)
        self._sw.start()

    def _install(self):
        it = self.results.currentItem()
        if it is None:
            return
        name = it.text(0)
        self.search_status.setText(tr("ar_installing", name))
        self._run([DNF, "install", "-y", name], lambda: self.search_status.setText(tr("ar_installed_ok", name)),
                  tr("ar_installing", name))

    def _software_center(self):
        from ...common import launcher
        for c in ("gnome-software", "plasma-discover", "dnfdragora"):
            if shutil.which(c):
                launcher._spawn([c])
                return
        dialogs.message(self, plain("addremove"), plain("ar_no_software_center"), "info")

    # ------------------------------------------------------------ Flatpak
    def _build_flatpak(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>" + plain("ar_flatpak_title") + "</b>"))
        top.addStretch(1)
        top.addWidget(QLabel(plain("fp_scope")))
        self.fp_scope = QComboBox()
        self.fp_scope.addItem(plain("fp_system"), "system")
        self.fp_scope.addItem(plain("fp_user"), "user")
        top.addWidget(self.fp_scope)
        # po zmianie instalacji (system / użytkownik) sprawdzamy jej repozytoria i listę programów
        self.fp_scope.currentIndexChanged.connect(lambda _i: self._fp_refresh())
        lay.addLayout(top)
        self.fp_info = QLabel()
        self.fp_info.setWordWrap(True)
        lay.addWidget(self.fp_info)
        row = QHBoxLayout()
        self.fp_setup_btn = QPushButton()
        self.fp_setup_btn.clicked.connect(self._fp_setup)
        row.addWidget(self.fp_setup_btn)
        row.addStretch(1)
        lay.addLayout(row)
        # wyszukiwanie we Flathubie
        srow = QHBoxLayout()
        srow.addWidget(QLabel(plain("fp_search")))
        self.fp_q = QLineEdit()
        self.fp_q.setPlaceholderText("np. GIMP, VLC, Spotify")
        self.fp_q.returnPressed.connect(self._fp_search)
        srow.addWidget(self.fp_q, 1)
        sb = QPushButton(plain("search_go"))
        sb.clicked.connect(self._fp_search)
        srow.addWidget(sb)
        lay.addLayout(srow)
        self.fp_tree = QTreeWidget()
        self.fp_tree.setHeaderLabels([plain("name"), plain("adm_service_desc"), plain("fp_version"), plain("fp_where")])
        self.fp_tree.setRootIsDecorated(False)
        self.fp_tree.setIconSize(QSize(24, 24))
        self.fp_tree.setColumnWidth(0, 190)
        self.fp_tree.setColumnWidth(1, 260)
        self.fp_tree.setColumnWidth(2, 70)
        self.fp_tree.currentItemChanged.connect(self._fp_selected)
        self.fp_tree.itemChanged.connect(self._fp_checked)
        self.fp_tree.itemDoubleClicked.connect(self._fp_toggle)
        self._fp_cart = {}   # aplikacje zaznaczone do instalacji (zostają zaznaczone między wyszukiwaniami)
        lay.addWidget(self.fp_tree, 1)
        self.fp_status = QLabel()
        self.fp_status.setWordWrap(True)
        lay.addWidget(self.fp_status)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.fp_show_installed = QPushButton(plain("fp_installed"))
        self.fp_show_installed.clicked.connect(self._fp_refresh)
        brow.addWidget(self.fp_show_installed)
        self.fp_update_btn = QPushButton(plain("fp_update_all"))
        self.fp_update_btn.clicked.connect(self._fp_update)
        brow.addWidget(self.fp_update_btn)
        self.fp_file_btn = QPushButton(plain("fp_from_file"))
        self.fp_file_btn.clicked.connect(self._fp_install_file)
        brow.addWidget(self.fp_file_btn)
        self.fp_action = QPushButton(plain("ar_install"))
        self.fp_action.clicked.connect(self._fp_primary)
        brow.addWidget(self.fp_action)
        self.fp_run = QPushButton(plain("fp_run"))
        self.fp_run.clicked.connect(self._fp_launch)
        brow.addWidget(self.fp_run)
        lay.addLayout(brow)
        self.stack.addWidget(w)
        self._fp_mode = "installed"

    def _fp_state(self):
        if not shutil.which("flatpak"):
            return "missing"
        # repozytorium sprawdzamy dla wybranej instalacji: systemowy Flathub nie wystarcza do instalacji „--user”
        rc, out = run(["flatpak", "remotes", "--columns=name"] + self._fp_scope_args(), 15)
        names = {l.strip() for l in out.splitlines() if l.strip()}
        if "flathub" not in names and not self._fp_root():
            # dla bieżącego użytkownika Flathub dodajemy od razu (bez hasła)
            rc, _ = run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_URL], 60)
            if rc == 0:
                return "ready"
        return "ready" if "flathub" in names else "noflathub"

    def _fp_refresh(self):
        st = self._fp_state()
        self.fp_setup_btn.setVisible(st != "ready")
        if st == "missing":
            self.fp_info.setText(plain("fp_missing"))
            self.fp_setup_btn.setText(plain("fp_install_support"))
        elif st == "noflathub":
            self.fp_info.setText(plain("fp_no_flathub"))
            self.fp_setup_btn.setText(plain("fp_add_flathub"))
        else:
            self.fp_info.setText(plain("fp_ready"))
        for wdg in (self.fp_q, self.fp_update_btn, self.fp_file_btn, self.fp_show_installed):
            wdg.setEnabled(st != "missing")
        self._fp_mode = "installed"
        self.fp_tree.blockSignals(True)
        self.fp_tree.clear()
        if st == "missing":
            self.fp_tree.blockSignals(False)
            self.fp_status.setText("")
            self._fp_update_action()
            return
        rc, out = run(["flatpak", "list", "--app", "--columns=application,name,description,version,installation"], 30)
        n = 0
        for line in out.splitlines():
            p = line.split("\t")
            if len(p) < 5:
                continue
            it = QTreeWidgetItem([p[1], p[2], p[3], plain("fp_user") if p[4] == "user" else plain("fp_system")])
            it.setIcon(0, iconcache.theme_or_builtin(p[0], "flatpak"))
            it.setData(0, Qt.UserRole, {"id": p[0], "name": p[1], "installation": p[4], "installed": True})
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Unchecked)
            self.fp_tree.addTopLevelItem(it)
            n += 1
        self.fp_tree.blockSignals(False)
        self._fp_n_installed = n
        self._fp_update_action()
        self._fp_selected(self.fp_tree.currentItem(), None)

    def _fp_scope_args(self):
        return ["--user"] if self.fp_scope.currentData() == "user" else ["--system"]

    def _fp_root(self):
        return self.fp_scope.currentData() != "user"

    def _fp_setup(self):
        st = self._fp_state()
        if st == "missing":
            ok, _ = run_job(self, plain("addremove"), tr("ar_installing", "flatpak"), [DNF, "install", "-y", "flatpak"])
        else:
            ok, _ = run_job(self, plain("addremove"), plain("fp_adding_flathub"),
                            ["flatpak", "remote-add", "--if-not-exists"] + self._fp_scope_args() + ["flathub", FLATHUB_URL],
                            self._fp_root(), icon="flatpak")
        self._fp_refresh()

    def _fp_search(self):
        term = self.fp_q.text().strip()
        if not term:
            return
        self.fp_status.setText(plain("sys_checking"))
        self.fp_tree.clear()
        self._fp_mode = "search"
        self._fp_update_action()
        search = ["flatpak", "search", "--columns=application,name,description,version,remotes", term]
        if not getattr(self, "_fp_appstream_done", False):
            # katalog aplikacji (appstream) — bez niego „flatpak search” nic nie znajduje (np. świeżo dodany Flathub);
            # dla repozytorium systemowego polkit pozwala na to aktywnemu użytkownikowi bez hasła
            self._fp_appstream_done = True
            self.fp_status.setText(plain("sys_checking"))
            self._fp_worker = CommandWorker(["sh", "-c", 'flatpak update --appstream >/dev/null 2>&1; exec "$@"', "_"]
                                            + search)
        else:
            self._fp_worker = CommandWorker(search)

        def done(rc, out):
            n = 0
            installed = set()
            r2, o2 = run(["flatpak", "list", "--app", "--columns=application"], 15)
            installed = {l.strip() for l in o2.splitlines()}
            self.fp_tree.blockSignals(True)
            for line in out.splitlines():
                p = line.split("\t")
                if len(p) < 5 or "." not in p[0]:
                    continue
                it = QTreeWidgetItem([p[1], p[2], p[3], p[4]])
                it.setIcon(0, iconcache.icon("flatpak"))
                it.setData(0, Qt.UserRole, {"id": p[0], "name": p[1], "remote": p[4].split(",")[0],
                                            "installed": p[0] in installed})
                if p[0] in installed:
                    it.setText(3, plain("fp_already"))
                    it.setFlags(it.flags() & ~Qt.ItemIsUserCheckable)
                else:
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.Checked if p[0] in self._fp_cart else Qt.Unchecked)
                self.fp_tree.addTopLevelItem(it)
                n += 1
            self.fp_tree.blockSignals(False)
            self._fp_found = n
            self.fp_status.setText(tr("search_done", n) if n or rc == 0 else out.strip()[-200:])
            self._fp_update_action()
        self._fp_worker.done.connect(done)
        self._fp_worker.start()

    def _fp_selected(self, cur, prev):
        d = cur.data(0, Qt.UserRole) if cur is not None else None
        self.fp_run.setEnabled(d is not None and d.get("installed", False))

    def _fp_toggle(self, it, col=0):
        if it.flags() & Qt.ItemIsUserCheckable:
            it.setCheckState(0, Qt.Unchecked if it.checkState(0) == Qt.Checked else Qt.Checked)

    def _fp_checked(self, it, col=0):
        d = it.data(0, Qt.UserRole)
        if d is None or self._fp_mode != "search":
            self._fp_update_action()
            return
        if it.checkState(0) == Qt.Checked:
            self._fp_cart[d["id"]] = d
        else:
            self._fp_cart.pop(d["id"], None)
        self._fp_update_action()

    def _fp_checked_installed(self):
        out = []
        for i in range(self.fp_tree.topLevelItemCount()):
            it = self.fp_tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                out.append(it.data(0, Qt.UserRole))
        return out

    def _fp_update_action(self):
        if self._fp_mode == "installed":
            n = len(self._fp_checked_installed())
            self.fp_action.setText(tr("fp_remove_n", n) if n else plain("ar_remove"))
            self.fp_action.setEnabled(n > 0)
            if hasattr(self, "_fp_n_installed"):
                extra = f" · {tr('fp_checked_n', n)}" if n else ""
                self.fp_status.setText(tr("fp_n_installed", self._fp_n_installed) + extra)
        else:
            n = len(self._fp_cart)
            self.fp_action.setText(tr("fp_install_n", n) if n else plain("ar_install"))
            self.fp_action.setEnabled(n > 0)
            if hasattr(self, "_fp_found"):
                extra = f" · {tr('fp_checked_n', n)}" if n else ""
                self.fp_status.setText(tr("search_done", self._fp_found) + extra)

    def _fp_primary(self):
        if self._fp_mode == "installed":
            sel = self._fp_checked_installed()
            if not sel:
                return
            names = ", ".join(d["name"] for d in sel)
            if dialogs.message(self, plain("addremove"), tr("ar_remove_confirm", names), "question", ("yes", "no")) != "yes":
                return
            for user in (False, True):
                ids = [d["id"] for d in sel if (d.get("installation") == "user") == user]
                if not ids:
                    continue
                ok, _ = run_job(self, plain("addremove"), tr("ar_removing", ", ".join(d["name"] for d in sel
                                                                                     if (d.get("installation") == "user") == user)),
                                ["flatpak", "uninstall", "-y", "--noninteractive", "--user" if user else "--system"] + ids,
                                not user, icon="flatpak")
                if not ok:
                    break
            self._fp_refresh()
            return
        sel = list(self._fp_cart.values())
        if not sel:
            return
        by_remote = {}
        for d in sel:
            by_remote.setdefault(d.get("remote") or "flathub", []).append(d)
        done = []
        for remote, items in by_remote.items():
            ok, _ = run_job(self, plain("addremove"), tr("ar_installing", ", ".join(d["name"] for d in items)),
                            ["flatpak", "install", "-y", "--noninteractive"] + self._fp_scope_args() +
                            [remote] + [d["id"] for d in items], self._fp_root(), icon="flatpak")
            if ok:
                done += items
        if not done:
            return
        for d in done:
            d["installed"] = True
            self._fp_cart.pop(d["id"], None)
        ids = {d["id"] for d in done}
        self.fp_tree.blockSignals(True)
        for i in range(self.fp_tree.topLevelItemCount()):
            it = self.fp_tree.topLevelItem(i)
            d = it.data(0, Qt.UserRole)
            if d and d["id"] in ids:
                d["installed"] = True
                it.setData(0, Qt.UserRole, d)
                it.setText(3, plain("fp_already"))
                it.setData(0, Qt.CheckStateRole, None)
                it.setFlags(it.flags() & ~Qt.ItemIsUserCheckable)
        self.fp_tree.blockSignals(False)
        self._fp_update_action()
        self.fp_status.setText(tr("ar_installed_ok", ", ".join(d["name"] for d in done)))
        desktopentry.all_entries(refresh=True)

    def _fp_update(self):
        user = self.fp_scope.currentData() == "user"
        ok, _ = run_job(self, plain("addremove"), plain("fp_updating"),
                        ["flatpak", "update", "-y", "--noninteractive", "--user" if user else "--system"], not user,
                        icon="flatpak")
        if ok:
            self._fp_refresh()

    def _fp_install_file(self):
        fn = dialogs.open_file(self, plain("fp_from_file"), os.path.expanduser("~/Downloads"),
                               "Flatpak (*.flatpakref *.flatpak *.flatpakrepo)")
        if not fn:
            return
        if fn.endswith(".flatpakrepo"):
            name = os.path.splitext(os.path.basename(fn))[0]
            args = ["flatpak", "remote-add", "--if-not-exists"] + self._fp_scope_args() + [name, fn]
        else:
            args = ["flatpak", "install", "-y", "--noninteractive"] + self._fp_scope_args() + [fn]
        ok, _ = run_job(self, plain("addremove"), tr("ar_installing", os.path.basename(fn)), args, self._fp_root(),
                        icon="flatpak")
        if ok:
            self._fp_refresh()

    def _fp_launch(self):
        it = self.fp_tree.currentItem()
        if it is None:
            return
        d = it.data(0, Qt.UserRole)
        from ...common import launcher
        launcher._spawn(["flatpak", "run", d["id"]])

    # ------------------------------------------------------------ składniki
    def _build_components(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(QLabel("<b>" + plain("ar_components") + "</b>"))
        lay.addWidget(QLabel(plain("ar_components_desc")))
        self.comp_list = QListWidget()
        self.comp_list.setIconSize(QSize(24, 24))
        installed = self._installed_set([p for _, _, pk in COMPONENTS for p in pk])
        for key, icon, pkgs in COMPONENTS:
            it = QListWidgetItem(iconcache.icon(icon),
                                 f"{plain(key)}  ({', '.join(p.split(':', 1)[-1] for p in pkgs)})")
            have = all(p in installed for p in pkgs)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if have else Qt.Unchecked)
            it.setData(Qt.UserRole, (pkgs, have))
            self.comp_list.addItem(it)
        lay.addWidget(self.comp_list, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(plain("apply"))
        b.clicked.connect(self._apply_components)
        row.addWidget(b)
        lay.addLayout(row)
        self.stack.addWidget(w)

    def _installed_set(self, pkgs):
        """Zainstalowane pakiety: nazwy RPM oraz „flatpak:ID” dla programów z Flatpaka (np. Firefox z Flathuba)."""
        out = set()
        rpms = [p for p in pkgs if not p.startswith("flatpak:")]
        if rpms and shutil.which("rpm"):
            try:
                r = subprocess.run(["rpm", "-q", "--qf", "%{NAME}\n"] + rpms, capture_output=True, text=True, timeout=30)
                out |= {l.strip() for l in r.stdout.splitlines() if l.strip() and " " not in l}
            except Exception:
                pass
        for p in pkgs:
            if p.startswith("flatpak:") and shutil.which("flatpak"):
                try:
                    if subprocess.run(["flatpak", "info", p[8:]], capture_output=True, timeout=30).returncode == 0:
                        out.add(p)
                except Exception:
                    pass
        return out

    def _apply_components(self):
        add, rem = [], []
        for i in range(self.comp_list.count()):
            it = self.comp_list.item(i)
            pkgs, have = it.data(Qt.UserRole)
            want = it.checkState() == Qt.Checked
            if want and not have:
                add += pkgs
            elif have and not want:
                rem += pkgs
        if not add and not rem:
            return
        # programy z Flatpaka (np. Firefox z Flathuba) — osobno, przez flatpak
        fadd = [p[8:] for p in add if p.startswith("flatpak:")]
        frem = [p[8:] for p in rem if p.startswith("flatpak:")]
        add = [p for p in add if not p.startswith("flatpak:")]
        rem = [p for p in rem if not p.startswith("flatpak:")]
        if fadd:
            ok, _ = run_job(self, plain("addremove"), tr("ar_installing", ", ".join(fadd)),
                            ["flatpak", "install", "-y", "--noninteractive", "--system", "flathub"] + fadd)
            if not ok:
                return
        if frem:
            ok, _ = run_job(self, plain("addremove"), tr("ar_removing", ", ".join(frem)),
                            ["flatpak", "uninstall", "-y", "--noninteractive", "--system"] + frem)
            if not ok:
                return
        if not add and not rem:
            dialogs.message(self, plain("addremove"), plain("ar_done"), "info")
            self._refresh_components()
            return
        # jedno polecenie dnf dla instalacji i usuwania — jedno pytanie o hasło
        if add and rem:
            args = [DNF, "-y", "swap", rem[0], add[0]] if len(add) == len(rem) == 1 else None
        else:
            args = None
        if args is None:
            if add:
                ok, _ = run_job(self, plain("addremove"), tr("ar_installing", ", ".join(add)), [DNF, "install", "-y"] + add)
                if not ok:
                    return
            if rem:
                ok, _ = run_job(self, plain("addremove"), tr("ar_removing", ", ".join(rem)), [DNF, "remove", "-y"] + rem)
                if not ok:
                    return
        else:
            ok, _ = run_job(self, plain("addremove"), plain("ar_working"), args)
            if not ok:
                return
        dialogs.message(self, plain("addremove"), plain("ar_done"), "info")
        self._refresh_components()

    def _refresh_components(self):
        installed = self._installed_set([p for _, _, pk in COMPONENTS for p in pk])
        for i in range(self.comp_list.count()):
            it = self.comp_list.item(i)
            pkgs, _ = it.data(Qt.UserRole)
            have = all(p in installed for p in pkgs)
            it.setCheckState(Qt.Checked if have else Qt.Unchecked)
            it.setData(Qt.UserRole, (pkgs, have))


def open_addremove(page=None, parent=None):
    return AddRemoveWindow(page)
