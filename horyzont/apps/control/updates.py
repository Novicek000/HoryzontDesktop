"""Horyzont Updates — okno w stylu klasycznej usługi aktualizacji oraz aplet „Aktualizacje automatyczne”."""
import json
import os
import shutil
import sys
import tempfile
import threading

from PySide6.QtCore import QObject, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSplitter,
                               QStackedWidget, QTextBrowser, QTimeEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ... import config
from ...common import dialogs, launcher
from ...common.jobs import run_job
from ...common.taskpane import TaskPane
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ...theme.base import vgrad
from ...theme.manager import current
from ...updates import core


def agent_cmd():
    """Ścieżka agenta (dla pkexec — polkit pokazuje wtedy opis „Horyzont Updates”)."""
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    prefix = os.path.dirname(os.path.dirname(pkg_root))
    p = os.path.join(prefix, "libexec", "horyzont", "update-agent")
    if os.access(p, os.X_OK):
        return [p]
    return ["/usr/bin/env", f"PYTHONPATH={pkg_root}", sys.executable, "-m", "horyzont", "update-agent"]


class Banner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)

    def paintEvent(self, e):
        p = QPainter(self)
        sc = getattr(current(), "sc", {}) or {}
        r = self.rect()
        p.fillRect(r, vgrad(r, [(0, sc.get("accent_light", "#5fb9c4")), (1, sc.get("accent_dark", "#0f5d67"))]))
        p.drawPixmap(14, 8, iconcache.pixmap("updates", 48))
        f = QFont(current().font("normal"))
        f.setPixelSize(24)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 90))
        p.drawText(r.adjusted(75, 1, 0, 1), Qt.AlignVCenter | Qt.AlignLeft, "Horyzont Updates")
        p.setPen(QColor("#ffffff"))
        p.drawText(r.adjusted(74, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, "Horyzont Updates")


class _Checker(QObject):
    done = Signal(list, list)

    def run(self, s):
        def go():
            ups, errors = core.check_all(s.get("include_flatpak", True), s.get("include_horyzont", True))
            self.done.emit(ups, errors)
        threading.Thread(target=go, daemon=True).start()


def _title(text):
    l = QLabel(text)
    f = QFont(current().font("normal"))
    f.setPixelSize(19)
    l.setFont(f)
    l.setStyleSheet("color: #1f4f8a;")
    l.setWordWrap(True)
    return l


def _wrap(text):
    l = QLabel(text)
    l.setWordWrap(True)
    return l


class BigButton(QPushButton):
    def __init__(self, icon, title, desc, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.setIcon(iconcache.icon(icon))
        self.setIconSize(QSize(40, 40))
        self.setText(f"{title}\n{desc}")
        self.setStyleSheet("text-align: left; padding: 8px;")


class UpdatesWindow(HWindow):
    def __init__(self, page=None):
        super().__init__("Horyzont Updates", "updates")
        self.s = core.settings()
        self.updates = []
        root = QVBoxLayout(self.body())
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(Banner())
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        split.addWidget(self.pane)
        self.stack = QStackedWidget()
        split.addWidget(self.stack)
        split.setSizes([210, 560])
        root.addWidget(split, 1)
        self.pages = {}
        for name, builder in (("home", self._home), ("checking", self._checking), ("results", self._results),
                              ("history", self._history), ("settings", self._settings)):
            w = QWidget()
            w.setAutoFillBackground(True)
            pal = w.palette()
            pal.setColor(w.backgroundRole(), QColor("#ffffff"))
            w.setPalette(pal)
            lay = QVBoxLayout(w)
            lay.setContentsMargins(24, 18, 24, 18)
            lay.setSpacing(10)
            builder(lay)
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setWidget(w)
            self.stack.addWidget(sa)
            self.pages[name] = sa
        self._fill_pane()
        self.resize(820, 580)
        self.checker = _Checker()
        self.checker.done.connect(self._checked)
        self.show_page(page or "home")

    # ------------------------------------------------------------------ nawigacja
    def _fill_pane(self):
        p = self.pane
        p.clear()
        s = p.add_section("Horyzont Updates", special=True)
        s.add_link("home", plain("upd_home"), lambda: self.show_page("home"))
        s.add_link("search", plain("upd_check"), self.check)
        s.add_link("updates", plain("upd_review"), lambda: self.show_page("results") if self.updates else self.check())
        s.add_link("recent", plain("upd_history"), lambda: self.show_page("history"))
        s.add_link("auto_updates", plain("upd_settings"), lambda: self.show_page("settings"))
        o = p.add_section(plain("task_see_also"))
        o.add_link("addremove", plain("ap_addremove"), lambda: launcher.start_builtin("control", ["addremove"]))
        o.add_link("system", plain("ap_system"), lambda: launcher.start_builtin("control", ["system"]))

    def show_page(self, name):
        if name == "settings_only":
            name = "settings"
        if name == "check":
            self.check()
            return
        if name == "history":
            self._fill_history()
        if name == "home":
            self._fill_home()
        self.stack.setCurrentWidget(self.pages[name])

    # ------------------------------------------------------------------ strony
    def _home(self, lay):
        lay.addWidget(_title(plain("upd_welcome")))
        lay.addWidget(_wrap(plain("upd_welcome_desc")))
        self.home_status = _wrap("")
        self.home_status.setStyleSheet("background: #fffbe0; border: 1px solid #e0d080; padding: 8px;")
        lay.addWidget(self.home_status)
        b1 = BigButton("updates", plain("upd_express"), plain("upd_express_desc"))
        b1.clicked.connect(lambda: self.check(express=True))
        b2 = BigButton("search", plain("upd_custom"), plain("upd_custom_desc"))
        b2.clicked.connect(lambda: self.check())
        lay.addWidget(b1)
        lay.addWidget(b2)
        lay.addStretch(1)

    def _fill_home(self):
        st = core.read_status()
        mode = {"auto": "upd_mode_auto_short", "download": "upd_mode_download_short", "notify": "upd_mode_notify_short",
                "off": "upd_mode_off_short"}.get(self.s.get("mode"), "upd_mode_notify_short")
        lines = [tr("upd_last_check", st.get("checked", "—").replace("T", " ")), tr("upd_auto_is", plain(mode))]
        if st.get("count"):
            lines.append(tr("upd_waiting", st["count"]))
        if not self.s.get("github_repo"):
            lines.append(plain("upd_no_repo"))
        self.home_status.setText("\n".join(lines))

    def _checking(self, lay):
        lay.addWidget(_title(plain("upd_checking")))
        lay.addWidget(_wrap(plain("upd_checking_desc")))
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        lay.addWidget(bar)
        lay.addStretch(1)

    def _results(self, lay):
        self.res_title = _title("")
        lay.addWidget(self.res_title)
        self.res_desc = _wrap("")
        lay.addWidget(self.res_desc)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([plain("name"), plain("upd_version"), plain("upd_source")])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 160)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.currentItemChanged.connect(self._item_selected)
        lay.addWidget(self.tree, 1)
        self.details = QTextBrowser()
        self.details.setMaximumHeight(110)
        lay.addWidget(self.details)
        row = QHBoxLayout()
        self.res_errors = QLabel()
        self.res_errors.setStyleSheet("color: #a05000;")
        self.res_errors.setWordWrap(True)
        row.addWidget(self.res_errors, 1)
        self.install_btn = QPushButton(plain("upd_install"))
        self.install_btn.setIcon(iconcache.icon("updates"))
        self.install_btn.clicked.connect(self.install_selected)
        row.addWidget(self.install_btn)
        lay.addLayout(row)

    def _history(self, lay):
        lay.addWidget(_title(plain("upd_history")))
        self.hist = QTreeWidget()
        self.hist.setRootIsDecorated(False)
        self.hist.setHeaderLabels([plain("upd_date"), plain("name"), plain("upd_version"), plain("tm_status")])
        self.hist.setColumnWidth(0, 150)
        self.hist.setColumnWidth(1, 220)
        lay.addWidget(self.hist, 1)

    def _fill_history(self):
        self.hist.clear()
        for h in core.history():
            it = QTreeWidgetItem([h.get("date", "").replace("T", " "), h.get("name", ""), h.get("version", ""),
                                  plain("upd_ok") if h.get("ok") else plain("upd_failed")])
            it.setIcon(3, iconcache.icon("info" if h.get("ok") else "error"))
            self.hist.addTopLevelItem(it)

    def _settings(self, lay):
        lay.addWidget(_title(plain("upd_settings")))
        lay.addWidget(_wrap(plain("upd_settings_desc")))
        g = QGroupBox(plain("upd_auto_title"))
        gl = QVBoxLayout(g)
        self.mode_btns = {}
        bg = QButtonGroup(self)
        for k, lab in (("auto", "upd_mode_auto"), ("download", "upd_mode_download"), ("notify", "upd_mode_notify"),
                       ("off", "upd_mode_off")):
            rb = QRadioButton(plain(lab))
            bg.addButton(rb)
            gl.addWidget(rb)
            self.mode_btns[k] = rb
        self.mode_btns.get(self.s.get("mode", "notify"), self.mode_btns["notify"]).setChecked(True)
        row = QHBoxLayout()
        row.addSpacing(20)
        row.addWidget(QLabel(plain("upd_check_every")))
        self.freq = QComboBox()
        for k, lab in (("hourly", "upd_hourly"), ("every6h", "upd_every6h"), ("daily", "upd_daily"), ("weekly", "upd_weekly")):
            self.freq.addItem(plain(lab), k)
        self.freq.setCurrentIndex(max(0, self.freq.findData(self.s.get("frequency", "daily"))))
        row.addWidget(self.freq)
        self.weekday = QComboBox()
        for k, lab in (("Mon", "day_mon"), ("Tue", "day_tue"), ("Wed", "day_wed"), ("Thu", "day_thu"), ("Fri", "day_fri"),
                       ("Sat", "day_sat"), ("Sun", "day_sun")):
            self.weekday.addItem(plain(lab), k)
        self.weekday.setCurrentIndex(max(0, self.weekday.findData(self.s.get("weekday", "Sun"))))
        row.addWidget(self.weekday)
        row.addWidget(QLabel(plain("upd_at")))
        self.time = QTimeEdit(QTime.fromString(self.s.get("time", "03:00"), "HH:mm"))
        self.time.setDisplayFormat("HH:mm")
        row.addWidget(self.time)
        row.addStretch(1)
        gl.addLayout(row)
        self.freq.currentIndexChanged.connect(self._freq_changed)
        self._freq_changed()
        lay.addWidget(g)
        g2 = QGroupBox(plain("upd_what"))
        g2l = QVBoxLayout(g2)
        self.inc_flatpak = QCheckBox(plain("upd_inc_flatpak"))
        self.inc_flatpak.setChecked(self.s.get("include_flatpak", True))
        self.inc_horyzont = QCheckBox(plain("upd_inc_horyzont"))
        self.inc_horyzont.setChecked(self.s.get("include_horyzont", True))
        g2l.addWidget(self.inc_flatpak)
        g2l.addWidget(self.inc_horyzont)
        rr = QHBoxLayout()
        rr.addSpacing(20)
        rr.addWidget(QLabel(plain("upd_repo")))
        self.repo = QLineEdit(self.s.get("github_repo", ""))
        self.repo.setPlaceholderText("uzytkownik/horyzont")
        rr.addWidget(self.repo, 1)
        tb = QPushButton(plain("upd_test_repo"))
        tb.clicked.connect(self._test_repo)
        rr.addWidget(tb)
        g2l.addLayout(rr)
        lay.addWidget(g2)
        g3 = QGroupBox(plain("upd_takeover_title"))
        g3l = QVBoxLayout(g3)
        self.takeover = QCheckBox(plain("upd_takeover"))
        self.takeover.setChecked(self.s.get("takeover", True))
        g3l.addWidget(self.takeover)
        g3l.addWidget(_wrap(plain("upd_takeover_desc")))
        lay.addWidget(g3)
        row = QHBoxLayout()
        row.addStretch(1)
        save = QPushButton(plain("upd_save"))
        save.clicked.connect(self.save_settings)
        row.addWidget(save)
        lay.addLayout(row)
        lay.addStretch(1)

    def _freq_changed(self):
        f = self.freq.currentData()
        self.weekday.setVisible(f == "weekly")
        self.time.setEnabled(f in ("daily", "weekly"))

    def _test_repo(self):
        repo = self.repo.text().strip()
        if not repo:
            return
        u = None
        try:
            data = core._github(f"https://api.github.com/repos/{repo}")
            if not data:
                raise RuntimeError(plain("upd_repo_missing"))
            u = core.check_horyzont(repo)
        except Exception as e:
            dialogs.message(self, "Horyzont Updates", str(e), "warning")
            return
        msg = plain("upd_repo_ok") + "\n" + (tr("upd_repo_newer", u.new) if u else tr("upd_repo_current", config.VERSION))
        dialogs.message(self, "Horyzont Updates", msg, "info")

    def save_settings(self):
        mode = next(k for k, b in self.mode_btns.items() if b.isChecked())
        s = {"mode": mode, "frequency": self.freq.currentData(), "weekday": self.weekday.currentData(),
             "time": self.time.time().toString("HH:mm"), "include_flatpak": self.inc_flatpak.isChecked(),
             "include_horyzont": self.inc_horyzont.isChecked(), "takeover": self.takeover.isChecked(),
             "github_repo": self.repo.text().strip()}
        config.set("updates", s)
        self.s = core.settings()
        self.s.update(s)
        # część systemowa: harmonogram (timer systemd) i przejęcie aktualizacji Fedory
        fd, path = tempfile.mkstemp(prefix="hz-upd-", suffix=".json", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
        with os.fdopen(fd, "w") as f:
            json.dump(s, f)
        os.chmod(path, 0o644)
        ok, out = run_job(self, "Horyzont Updates", plain("upd_saving"), agent_cmd() + ["--configure", path],
                          icon="auto_updates")
        try:
            os.remove(path)
        except OSError:
            pass
        if s["takeover"] and shutil.which("gsettings"):
            import subprocess
            for k in ("download-updates", "download-updates-notify"):
                subprocess.run(["gsettings", "set", "org.gnome.software", k, "false"], capture_output=True)
        elif shutil.which("gsettings"):
            import subprocess
            subprocess.run(["gsettings", "reset", "org.gnome.software", "download-updates"], capture_output=True)
        if ok:
            dialogs.message(self, "Horyzont Updates", plain("upd_saved"), "info")

    # ------------------------------------------------------------------ sprawdzanie
    def check(self, express=False):
        self._express = express
        self.show_page("checking")
        self.s = core.settings()
        self.checker.run(self.s)

    def _checked(self, ups, errors):
        self.updates = ups
        core.write_status(ups, core.USER_STATUS, error="; ".join(errors) or None)
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        names = {"horyzont": plain("upd_group_horyzont"), "dnf": plain("upd_group_system"),
                 "flatpak": plain("upd_group_flatpak")}
        vers = core.installed_versions([u.name for u in ups if u.source == "dnf"])
        for u in ups:
            g = groups.get(u.source)
            if g is None:
                g = QTreeWidgetItem([names.get(u.source, u.source)])
                g.setFlags(g.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                g.setCheckState(0, Qt.Checked)
                g.setIcon(0, iconcache.icon({"horyzont": "logo", "dnf": "package", "flatpak": "flatpak"}.get(u.source, "package")))
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                self.tree.addTopLevelItem(g)
                groups[u.source] = g
            old = u.old or vers.get(u.name, "")
            it = QTreeWidgetItem([u.name + (f"  ({plain('upd_security')})" if u.security else ""),
                                  f"{old} → {u.new}" if old else u.new, u.description if u.source == "dnf" else ""])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked)
            it.setData(0, Qt.UserRole, u)
            if u.security:
                it.setIcon(0, iconcache.icon("security"))
            g.addChild(it)
        for g in groups.values():
            g.setText(0, f"{g.text(0)} ({g.childCount()})")
            g.setExpanded(g.childCount() <= 15)
        self.tree.blockSignals(False)
        n = len(ups)
        if n:
            self.res_title.setText(tr("upd_found", n))
            self.res_desc.setText(plain("upd_found_desc"))
        else:
            self.res_title.setText(plain("upd_none"))
            self.res_desc.setText(plain("upd_none_desc"))
        self.res_errors.setText("\n".join(errors))
        self._update_install_btn()
        self.stack.setCurrentWidget(self.pages["results"])
        if n and getattr(self, "_express", False):
            QTimer.singleShot(300, self.install_selected)

    def _item_changed(self, *_):
        self._update_install_btn()

    def _item_selected(self, cur, prev):
        u = cur.data(0, Qt.UserRole) if cur is not None else None
        if u is None:
            self.details.clear()
            return
        if u.source == "horyzont":
            self.details.setMarkdown(f"**{u.extra.get('title', u.new)}**\n\n{u.description or ''}")
        else:
            self.details.setPlainText(f"{u.name} {u.new}\n{plain('upd_source')}: {u.description or u.source}")

    def _selected(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                it = g.child(j)
                if it.checkState(0) == Qt.Checked:
                    out.append(it.data(0, Qt.UserRole))
        return out

    def _update_install_btn(self):
        n = len(self._selected())
        self.install_btn.setText(tr("upd_install_n", n))
        self.install_btn.setEnabled(n > 0)

    # ------------------------------------------------------------------ instalacja
    def install_selected(self):
        sel = self._selected()
        if not sel:
            return
        hist = []
        dnf_pkgs = [u.id for u in sel if u.source == "dnf"]
        all_dnf = len(dnf_pkgs) == len([u for u in self.updates if u.source == "dnf"])
        if dnf_pkgs:
            dnf = shutil.which("dnf") or shutil.which("dnf5") or "dnf"
            args = [dnf, "upgrade", "-y"] + ([] if all_dnf else dnf_pkgs)
            ok, out = run_job(self, "Horyzont Updates", tr("upd_installing_system", len(dnf_pkgs)), args, icon="updates")
            hist += [(u.name, u.new, ok, "dnf") for u in sel if u.source == "dnf"]
            if not ok:
                core.add_history(hist)
                return
        for scope in ("--system", "--user"):
            fl = [u.id for u in sel if u.source == "flatpak" and u.extra.get("scope") == scope]
            if fl:
                ok, out = run_job(self, "Horyzont Updates", tr("upd_installing_flatpak", len(fl)),
                                  ["flatpak", "update", "-y", "--noninteractive", scope] + fl, scope == "--system", icon="flatpak")
                hist += [(u.name, u.new, ok, "flatpak") for u in sel if u.source == "flatpak" and u.extra.get("scope") == scope]
        hz = next((u for u in sel if u.source == "horyzont"), None)
        need_relogin = False
        if hz is not None:
            ok = self._install_horyzont(hz)
            hist.append(("Horyzont", hz.new, ok, "horyzont"))
            need_relogin = ok
        core.add_history(hist)
        self.check()
        if need_relogin:
            if dialogs.message(self, "Horyzont Updates", tr("upd_hz_done", hz.new), "question", ("yes", "no")) == "yes":
                launcher.start_builtin("shell", ["--replace"])

    def _install_horyzont(self, u):
        from ..explorer.archive_ui import ProgressDialog
        res = {}

        def fn(progress, cancelled):
            res["dir"] = core.download_horyzont(u, lambda p: progress(p, ""), cancelled)
        pd = ProgressDialog("Horyzont Updates", tr("upd_downloading", u.new), fn, self, icon="updates")
        pd.exec()
        ok, kind, msg = pd.result
        if not ok:
            if not pd.worker.cancel:
                dialogs.message(self, "Horyzont Updates", tr("upd_download_failed", msg), "error")
            return False
        ok, out = run_job(self, "Horyzont Updates", tr("upd_installing_hz", u.new),
                          agent_cmd() + ["--install-horyzont", res["dir"]], icon="updates")
        return ok


def open_updates(page=None, parent=None):
    return UpdatesWindow(page)


def open_auto_updates(page=None, parent=None):
    return UpdatesWindow("settings")
