"""Aplety: Pasek zadań i menu Start, Opcje folderów, Opcje regionalne, Zasilanie,
Ułatwienia dostępu, Centrum zabezpieczeń."""
import glob
import mimetypes
import os
import shutil
import subprocess

from PySide6.QtCore import QDate, QDateTime, QLocale, QRect, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QPushButton, QRadioButton,
                               QSpinBox, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ... import config
from ...common import desktopentry, dialogs, launcher, sysctl
from ...common.window import HWindow
from ...common.appkit import T
from ...common.window import HDialog
from ...i18n import lang_code, plain, tr
from ...theme import iconcache
from ...theme.base import CHECKED, NORMAL
from ...theme.manager import current
from .common import AppletDialog, hline, run, run_privileged, wrap_label


def _cb(text, key, dlg, default=None):
    c = QCheckBox(text.replace("&", ""))
    c.setChecked(bool(config.get(key, default)))
    c.toggled.connect(dlg.changed)
    c._key = key
    return c


# ================================================================== Pasek zadań i menu Start
class TaskbarPreview(QWidget):
    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.setFixedHeight(64)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        r = self.rect().adjusted(0, 0, -1, -1)
        p.fillRect(r, t.color("desktop"))
        h = t.metrics["taskbar_h"]
        bar = QRect(r.left(), r.bottom() - h + 1, r.width(), h)
        t.draw_taskbar(p, bar)
        label = self.dlg.start_label()
        sw = t.start_button_width(label, h)
        iconcache.logo_override = self.dlg.logo_mode()
        try:
            t.draw_start_button(p, QRect(bar.left(), bar.top(), sw, h), NORMAL, label)
        finally:
            iconcache.logo_override = None
        x = sw + 4
        if self.dlg.ql.isChecked():
            for ic in ("show_desktop", "browser", "folder_open"):
                p.drawPixmap(x + 3, bar.top() + (h - 16) // 2, iconcache.pixmap(ic, 16))
                x += 22
            x += 4
        bh = t.metrics["task_button_h"]
        for i, (ic, txt) in enumerate((("folder_open", plain("my_documents")), ("notepad", plain("notepad")))):
            br = QRect(x, bar.top() + (h - bh) // 2 + 1, 120, bh)
            t.draw_task_button(p, br, CHECKED if i == 0 else NORMAL)
            p.drawPixmap(br.left() + 6, br.top() + (bh - 16) // 2, iconcache.pixmap(ic, 16))
            p.setFont(t.font("normal"))
            p.setPen(t.taskbar_text_color())
            p.drawText(br.adjusted(26, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, txt)
            x += 124
        tw = 70 if self.dlg.clock.isChecked() else 30
        tr_ = QRect(bar.right() - tw, bar.top(), tw + 1, h)
        t.draw_tray(p, tr_)
        p.drawPixmap(tr_.left() + 8, bar.top() + (h - 16) // 2, iconcache.pixmap("volume", 16))
        if self.dlg.clock.isChecked():
            p.setPen(t.taskbar_text_color())
            p.drawText(tr_.adjusted(26, 0, -4, 0), Qt.AlignCenter, QTime.currentTime().toString("H:mm"))


class TaskbarProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("taskbar_props"), "taskbar_props", parent)
        w, lay = self.add_tab(plain("tbp_taskbar"))
        g = QGroupBox(plain("tbp_appearance"))
        gl = QVBoxLayout(g)
        self.lock = _cb(tr("tbp_lock"), "taskbar_locked", self, True)
        self.autohide = _cb(tr("tbp_autohide"), "taskbar_autohide", self, False)
        self.ontop = _cb(tr("tbp_on_top"), "taskbar_on_top", self, True)
        self.group = _cb(tr("tbp_group"), "taskbar_group", self, True)
        self.ql = _cb(tr("tbp_quick_launch"), "taskbar_quick_launch", self, False)
        self.clock = _cb(tr("tbp_clock"), "clock_visible", self, True)
        self.secs = _cb(tr("tbp_seconds"), "clock_seconds", self, False)
        self.preview = TaskbarPreview(self)
        gl.addWidget(self.preview)
        for c in (self.lock, self.autohide, self.ontop, self.group, self.ql):
            gl.addWidget(c)
            c.toggled.connect(self.preview.update)
        lay.addWidget(g)
        g2 = QGroupBox(plain("tbp_notification"))
        g2l = QVBoxLayout(g2)
        g2l.addWidget(self.clock)
        g2l.addWidget(self.secs)
        self.tray_apps = _cb(tr("tbp_tray_apps"), "tray_app_icons", self, True)
        self.balloons = _cb(tr("tbp_balloons"), "balloon_tips", self, True)
        g2l.addWidget(self.tray_apps)
        hrow = QHBoxLayout()
        self.hide_inactive = _cb(tr("tbp_hide_inactive"), "tray_hide_inactive", self, True)
        hrow.addWidget(self.hide_inactive, 1)
        cust = QPushButton(plain("tbp_customize_btn"))
        cust.clicked.connect(self.customize_tray)
        hrow.addWidget(cust)
        g2l.addLayout(hrow)
        brow = QHBoxLayout()
        brow.addWidget(self.balloons, 1)
        test = QPushButton(plain("tbp_test_balloon"))
        test.clicked.connect(self._test_balloon)
        brow.addWidget(test)
        g2l.addLayout(brow)
        g2l.addWidget(wrap_label(plain("tbp_tray_hint")))
        self.clock.toggled.connect(self.preview.update)
        lay.addWidget(g2)
        # przycisk Start: napis i logo
        g3 = QGroupBox(plain("tbp_start_button"))
        g3l = QGridLayout(g3)
        from PySide6.QtWidgets import QLineEdit
        self.start_text = QLineEdit(config.get("start_text", ""))
        self.start_text.setPlaceholderText(plain("start"))
        self.start_text.setMaxLength(24)
        self.start_text.setToolTip(plain("tbp_start_text_hint"))
        self.start_text.textChanged.connect(lambda *_: (self.preview.update(), self.changed()))
        dflt = QPushButton(plain("tbp_start_text_default"))
        dflt.clicked.connect(lambda: self.start_text.setText(""))
        g3l.addWidget(QLabel(plain("tbp_start_text")), 1, 0)
        g3l.addWidget(self.start_text, 1, 1)
        g3l.addWidget(dflt, 1, 2)
        # logo Horyzontu (domyślne), bez logo albo własny obraz użytkownika
        self.logo_combo = QComboBox()
        self.logo_combo.addItem(iconcache.icon("logo"), plain("tbp_logo_horyzont"), "horyzont")
        self.logo_combo.addItem(plain("tbp_logo_none"), "none")
        self._custom_logo = ""
        cur = config.get("start_logo", "horyzont")
        if cur not in ("system", "horyzont", "none") and os.path.exists(cur):
            self._custom_logo = cur
            self.logo_combo.addItem(QIcon(cur), plain("tbp_logo_custom"), cur)
            self.logo_combo.setCurrentIndex(2)
        else:
            # „Własny obraz…” jest zawsze na liście — wybranie go otwiera okno wyboru pliku
            self.logo_combo.addItem(plain("tbp_logo_custom"), "")
            self.logo_combo.setCurrentIndex(max(0, self.logo_combo.findData(cur)))
        self._logo_prev = self.logo_combo.currentIndex()
        self.logo_combo.currentIndexChanged.connect(self._logo_selected)
        browse = QPushButton(plain("browse"))
        browse.clicked.connect(self._browse_logo)
        g3l.addWidget(QLabel(plain("tbp_logo_label")), 0, 0)
        g3l.addWidget(self.logo_combo, 0, 1)
        g3l.addWidget(browse, 0, 2)
        g3l.setColumnStretch(1, 1)
        lay.addWidget(g3)
        lay.addStretch(1)
        w2, l2 = self.add_tab(plain("tbp_startmenu"))
        r1 = QRadioButton(tr("tbp_start_modern").replace("&", ""))
        r1.setChecked(True)
        l2.addWidget(r1)
        l2.addWidget(wrap_label("   " + plain("tbp_start_modern_desc")))
        r2 = QRadioButton(tr("tbp_start_classic").replace("&", ""))
        r2.setEnabled(False)
        l2.addWidget(r2)
        cg = QGroupBox(plain("tbp_customize").replace("&", "").rstrip("."))
        cl = QGridLayout(cg)
        cl.addWidget(QLabel(plain("tbp_num_programs")), 0, 0)
        self.nprog = QSpinBox()
        self.nprog.setRange(0, 12)
        self.nprog.setValue(int(config.get("start_recent_count", 6)))
        self.nprog.valueChanged.connect(self.changed)
        cl.addWidget(self.nprog, 0, 1)
        clr = QPushButton(plain("tbp_clear_list"))
        clr.clicked.connect(lambda: (config.set("recent_programs", {}), dialogs.message(self, plain("taskbar_props"),
                                                                                      plain("tbp_cleared"), "info")))
        cl.addWidget(clr, 1, 1)
        clr2 = QPushButton(plain("tbp_clear_docs"))
        clr2.clicked.connect(lambda: (launcher.clear_recent_documents(), dialogs.message(self, plain("taskbar_props"),
                                                                                        plain("tbp_cleared"), "info")))
        cl.addWidget(clr2, 2, 1)
        l2.addWidget(cg)
        l2.addStretch(1)
        self.resize(440, 680)
        if page == "customize":
            QTimer.singleShot(200, self.customize_tray)

    def customize_tray(self):
        TrayCustomizeDialog(self).exec()

    def _test_balloon(self):
        """Wysyła prawdziwe powiadomienie przez D-Bus (to samo, co notify-send)."""
        try:
            from ...common import dbus
            bus = dbus.Connection()
            bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                          "org.freedesktop.Notifications", "Notify", "susssasa{sv}i",
                          ("Horyzont", 0, "dialog-information", plain("tbp_test_balloon_title"),
                           plain("tbp_test_balloon_text"), [], {"urgency": dbus.Variant("y", 1)}, -1))
            bus.sock.close()
        except Exception as e:
            dialogs.message(self, plain("taskbar_props"), str(e), "error")

    def start_label(self):
        t = self.start_text.text().strip() if hasattr(self, "start_text") else ""
        return t or plain("start")

    def logo_mode(self):
        return self.logo_combo.currentData() or "horyzont"

    def _logo_selected(self, i):
        if i == 2 and not self.logo_combo.itemData(2):
            if not self._browse_logo():
                self.logo_combo.blockSignals(True)
                self.logo_combo.setCurrentIndex(self._logo_prev)
                self.logo_combo.blockSignals(False)
                return
        self._logo_prev = self.logo_combo.currentIndex()
        self.preview.update()
        self.changed()

    def _browse_logo(self):
        fn = dialogs.open_file(self, plain("tbp_logo"), config.user_dir("PICTURES"),
                               plain("images_filter") + " (*.png *.svg *.jpg *.jpeg *.bmp *.ico *.webp)")
        if not fn:
            return False
        os.makedirs(config.DATA_DIR, exist_ok=True)
        dst = os.path.join(config.DATA_DIR, "start-logo" + os.path.splitext(fn)[1].lower())
        for old in glob.glob(os.path.join(config.DATA_DIR, "start-logo.*")):
            try:
                os.remove(old)
            except OSError:
                pass
        shutil.copyfile(fn, dst)
        iconcache.reset()
        # pozycja „Własny obraz” zawsze na końcu listy, z miniaturą wybranego pliku
        self.logo_combo.blockSignals(True)
        if self.logo_combo.count() > 2:
            self.logo_combo.removeItem(2)
        self.logo_combo.addItem(QIcon(dst), plain("tbp_logo_custom"), dst)
        self.logo_combo.setCurrentIndex(2)
        self.logo_combo.blockSignals(False)
        self._logo_prev = 2
        self.preview.update()
        self.changed()
        return True

    def apply(self):
        vals = {}
        for c in (self.lock, self.autohide, self.ontop, self.group, self.ql, self.clock, self.secs,
                  self.tray_apps, self.balloons, self.hide_inactive):
            vals[c._key] = c.isChecked()
        vals["start_recent_count"] = self.nprog.value()
        vals["start_logo"] = self.logo_mode()
        vals["start_text"] = self.start_text.text().strip()
        config.update(vals)
        try:
            from ...session import labwc
            labwc.apply_settings()
        except Exception:
            pass
        return True


class TrayCustomizeDialog(HDialog):
    """„Dostosuj powiadomienia”: zachowanie każdej ikony w obszarze powiadomień."""

    def __init__(self, parent):
        super().__init__(T("Dostosowywanie powiadomień", "Customize Notifications"), "taskbar_props", parent)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(wrap_label(T("Ikony aktywnych i pilnych powiadomień są zawsze wyświetlane, a nieaktywne ukrywane. "
                                   "Możesz zmienić to zachowanie dla elementów z listy.",
                                   "Horyzont displays icons for active and urgent notifications, and hides inactive "
                                   "ones. You can change this behavior for items in the list below.")))
        lay.addWidget(QLabel(T("Wybierz element, a następnie jego zachowanie powiadomień:",
                               "Select an item, then choose its notification behavior:")))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Nazwa", "Name"), T("Zachowanie", "Behavior")])
        self.tree.setRootIsDecorated(True)
        lay.addWidget(self.tree, 1)
        known = config.get("tray_known", {})
        beh = config.get("tray_behaviors", {})
        cur = QTreeWidgetItem([T("Bieżące elementy", "Current Items")])
        past = QTreeWidgetItem([T("Elementy z przeszłości", "Past Items")])
        self.tree.addTopLevelItem(cur)
        self.tree.addTopLevelItem(past)
        current_keys = set(config.get("tray_current", []))
        self.combos = {}
        labels = [("auto", T("Ukryj, gdy nieaktywne", "Hide when inactive")), ("hide", T("Zawsze ukrywaj", "Always hide")),
                  ("show", T("Zawsze pokazuj", "Always show"))]
        for key, title in sorted(known.items(), key=lambda kv: kv[1].lower()):
            parent_item = cur if (key in current_keys or not current_keys) else past
            it = QTreeWidgetItem(parent_item, [title, ""])
            it.setIcon(0, iconcache.icon("app" if key.startswith("app:") else "taskbar_props"))
            c = QComboBox()
            for k, lab in labels:
                c.addItem(lab, k)
            default = "auto" if key.startswith("app:") else "show"
            c.setCurrentIndex(max(0, c.findData(beh.get(key, default))))
            self.tree.setItemWidget(it, 1, c)
            self.combos[key] = c
        cur.setExpanded(True)
        past.setExpanded(True)
        self.tree.setColumnWidth(0, 220)
        row = QHBoxLayout()
        reset = QPushButton(T("&Przywróć domyślne", "&Restore Defaults"))
        reset.clicked.connect(lambda: [c.setCurrentIndex(c.findData("auto" if k.startswith("app:") else "show"))
                                       for k, c in self.combos.items()])
        row.addWidget(reset)
        row.addStretch(1)
        ok = QPushButton(T("OK", "OK"))
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        ca = QPushButton(T("Anuluj", "Cancel"))
        ca.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        self.resize(460, 420)

    def _save(self):
        config.set("tray_behaviors", {k: c.currentData() for k, c in self.combos.items()})
        self.accept()


def taskbar(page=None, parent=None):
    return TaskbarProperties(page, parent)


# ================================================================== Opcje folderów
ADVANCED_VIEW = [
    ("explorer_full_path_address", "fo_full_path", True),
    ("explorer_full_path_title", "fo_full_path_title", False),
    ("explorer_show_hidden", "fo_show_hidden", False),
    ("explorer_hide_ext", "fo_hide_ext", True),
    ("explorer_status_bar", "fo_status_bar", True),
    ("notepad_for_text", "fo_notepad_text", True),
    ("explorer_browse_archives", "fo_browse_archives", True),
]


class FolderOptions(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("folder_opts"), "folder_options", parent)
        w, lay = self.add_tab(plain("general"))
        g1 = QGroupBox(plain("fo_tasks"))
        g1l = QVBoxLayout(g1)
        self.tasks = QRadioButton(tr("fo_show_tasks").replace("&", ""))
        self.classic = QRadioButton(tr("fo_classic").replace("&", ""))
        (self.tasks if config.get("explorer_show_tasks", True) else self.classic).setChecked(True)
        for r in (self.tasks, self.classic):
            g1l.addWidget(r)
            r.toggled.connect(self.changed)
        lay.addWidget(g1)
        g2 = QGroupBox(plain("fo_browse"))
        g2l = QVBoxLayout(g2)
        self.same = QRadioButton(tr("fo_same_window").replace("&", ""))
        self.own = QRadioButton(tr("fo_own_window").replace("&", ""))
        (self.same if config.get("explorer_same_window", True) else self.own).setChecked(True)
        for r in (self.same, self.own):
            g2l.addWidget(r)
            r.toggled.connect(self.changed)
        lay.addWidget(g2)
        g3 = QGroupBox(plain("fo_click"))
        g3l = QVBoxLayout(g3)
        self.single = QRadioButton(tr("fo_single").replace("&", ""))
        self.double = QRadioButton(tr("fo_double").replace("&", ""))
        (self.single if config.get("explorer_single_click", False) else self.double).setChecked(True)
        self.single.setEnabled(False)
        for r in (self.single, self.double):
            g3l.addWidget(r)
            r.toggled.connect(self.changed)
        lay.addWidget(g3)
        rd = QPushButton(tr("fo_restore").replace("&", ""))
        rd.clicked.connect(self._defaults_general)
        lay.addWidget(rd, 0, Qt.AlignRight)
        lay.addStretch(1)
        w2, l2 = self.add_tab(plain("fo_view"))
        fv = QGroupBox(plain("fo_folder_views"))
        fvl = QHBoxLayout(fv)
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("folder", 32))
        fvl.addWidget(ic)
        fvl.addWidget(wrap_label(plain("fo_folder_views_desc")), 1)
        reset = QPushButton(plain("fo_reset_views"))
        reset.clicked.connect(lambda: (config.set("folder_views", {}), dialogs.message(self, plain("folder_opts"),
                                                                                       plain("tbp_cleared"), "info")))
        fvl.addWidget(reset)
        l2.addWidget(fv)
        l2.addWidget(QLabel(plain("fo_advanced")))
        self.adv = QTreeWidget()
        self.adv.setHeaderHidden(True)
        self.adv.setRootIsDecorated(False)
        for key, lab, default in ADVANCED_VIEW:
            it = QTreeWidgetItem([plain(lab).replace("&", "")])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if config.get(key, default) else Qt.Unchecked)
            it.setData(0, Qt.UserRole, key)
            self.adv.addTopLevelItem(it)
        self.adv.itemChanged.connect(self.changed)
        l2.addWidget(self.adv, 1)
        rd2 = QPushButton(tr("fo_restore").replace("&", ""))
        rd2.clicked.connect(self._defaults_view)
        l2.addWidget(rd2, 0, Qt.AlignRight)
        w3, l3 = self.add_tab(plain("fo_file_types"))
        l3.addWidget(QLabel(plain("fo_assoc")))
        self.types = QTreeWidget()
        self.types.setHeaderLabels([plain("fo_extension"), plain("fo_ftype"), plain("opens_with").rstrip(":")])
        self.types.setRootIsDecorated(False)
        self.types.setColumnWidth(0, 80)
        self.types.setColumnWidth(1, 150)
        l3.addWidget(self.types, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ch = QPushButton(tr("change").replace("&", ""))
        ch.clicked.connect(self._change_assoc)
        row.addWidget(ch)
        l3.addLayout(row)
        self._fill_types()
        self.resize(420, 470)

    def _fill_types(self):
        from ..explorer.model import type_name_for
        exts = [".txt", ".pdf", ".png", ".jpg", ".gif", ".mp3", ".ogg", ".mp4", ".mkv", ".html", ".zip", ".odt",
                ".docx", ".xlsx", ".svg", ".webp", ".flac", ".avi", ".tar", ".iso", ".rtf", ".csv", ".md"]
        for e in exts:
            mt, _ = mimetypes.guess_type("x" + e)
            app = ""
            if e in launcher.NOTEPAD_EXT and config.get("notepad_for_text", True):
                app = plain("notepad")
            elif mt:
                did = desktopentry.default_for_mime(mt)
                ent = desktopentry.all_entries().get(did)
                app = ent.name if ent else did
            it = QTreeWidgetItem([e.upper().lstrip("."), type_name_for("x" + e, False), app])
            it.setIcon(0, iconcache.icon(iconcache.name_for_file("x" + e, False)))
            it.setData(0, Qt.UserRole, mt)
            self.types.addTopLevelItem(it)

    def _change_assoc(self):
        it = self.types.currentItem()
        if it is None or not it.data(0, Qt.UserRole):
            return
        mt = it.data(0, Qt.UserRole)
        from ...common.window import HDialog
        d = HDialog(plain("fo_open_with_title"), "folder_options", self)
        lay = QVBoxLayout(d.body())
        lay.addWidget(QLabel(tr("fo_choose_program", it.text(0))))
        lst = QListWidget()
        ents = sorted((e for e in desktopentry.all_entries().values() if e.visible()), key=lambda e: e.name.lower())
        for e in ents:
            from PySide6.QtWidgets import QListWidgetItem
            li = QListWidgetItem(iconcache.theme_or_builtin(e.icon, "app"), e.name)
            li.setData(Qt.UserRole, e.id)
            lst.addItem(li)
        lay.addWidget(lst)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        d.resize(360, 420)
        if d.exec() and lst.currentItem() is not None:
            desktopentry.set_default_for_mime(mt, lst.currentItem().data(Qt.UserRole))
            it.setText(2, lst.currentItem().text())

    def _defaults_general(self):
        self.tasks.setChecked(True)
        self.same.setChecked(True)
        self.double.setChecked(True)

    def _defaults_view(self):
        for i in range(self.adv.topLevelItemCount()):
            it = self.adv.topLevelItem(i)
            key = it.data(0, Qt.UserRole)
            default = next(d for k, _, d in ADVANCED_VIEW if k == key)
            it.setCheckState(0, Qt.Checked if default else Qt.Unchecked)

    def apply(self):
        vals = {"explorer_show_tasks": self.tasks.isChecked(), "explorer_same_window": self.same.isChecked(),
                "explorer_single_click": self.single.isChecked()}
        for i in range(self.adv.topLevelItemCount()):
            it = self.adv.topLevelItem(i)
            vals[it.data(0, Qt.UserRole)] = it.checkState(0) == Qt.Checked
        config.update(vals)
        return True


def folder_options(page=None, parent=None):
    return FolderOptions(page, parent)


# ================================================================== Opcje regionalne
class RegionalOptions(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("regional"), "regional", parent)
        w, lay = self.add_tab(plain("rg_options"))
        g = QGroupBox(plain("rg_standards"))
        gl = QVBoxLayout(g)
        gl.addWidget(wrap_label(plain("rg_standards_desc")))
        self.locale = QComboBox()
        locs = []
        rc, out = run(["localectl", "list-locales"], 5)
        if rc == 0:
            locs = [l.strip() for l in out.splitlines() if l.strip()]
        if not locs:
            locs = ["pl_PL.UTF-8", "en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8", "cs_CZ.UTF-8", "uk_UA.UTF-8"]
        for l in locs:
            q = QLocale(l.split(".")[0])
            self.locale.addItem(f"{q.nativeLanguageName()} ({q.nativeTerritoryName()}) — {l}", l)
        cur = os.environ.get("LC_TIME") or os.environ.get("LANG", "pl_PL.UTF-8")
        self.locale.setCurrentIndex(max(0, self.locale.findData(cur)))
        self.locale.currentIndexChanged.connect(self._samples)
        self.locale.currentIndexChanged.connect(self.changed)
        gl.addWidget(self.locale)
        lay.addWidget(g)
        sg = QGroupBox(plain("rg_samples"))
        self.sl = QGridLayout(sg)
        self.sample_labels = []
        for i, key in enumerate(("rg_number", "rg_currency", "rg_time", "rg_short_date", "rg_long_date")):
            self.sl.addWidget(QLabel(plain(key)), i, 0)
            v = QLabel()
            self.sl.addWidget(v, i, 1)
            self.sample_labels.append(v)
        lay.addWidget(sg)
        lay.addStretch(1)
        self._samples()
        w2, l2 = self.add_tab(plain("rg_languages"))
        l2.addWidget(QLabel(plain("rg_ui_lang")))
        self.ui_lang = QComboBox()
        self.ui_lang.addItem(plain("kb_system_default"), "")
        self.ui_lang.addItem("Polski", "pl")
        self.ui_lang.addItem("English", "en")
        self.ui_lang.setCurrentIndex(max(0, self.ui_lang.findData(config.get("language", ""))))
        self.ui_lang.currentIndexChanged.connect(self.changed)
        l2.addWidget(self.ui_lang)
        l2.addWidget(wrap_label(plain("rg_restart_note")))
        l2.addStretch(1)
        self.resize(420, 430)

    def _samples(self, *_):
        loc = QLocale((self.locale.currentData() or "pl_PL").split(".")[0])
        now = QDateTime.currentDateTime()
        vals = [loc.toString(123456789.0, "f", 2), loc.toCurrencyString(123456789.0),
                loc.toString(now.time(), QLocale.LongFormat), loc.toString(now.date(), QLocale.ShortFormat),
                loc.toString(now.date(), QLocale.LongFormat)]
        for l, v in zip(self.sample_labels, vals):
            l.setText(v)

    def apply(self):
        config.set("language", self.ui_lang.currentData())
        loc = self.locale.currentData()
        if loc and loc != os.environ.get("LANG"):
            run_privileged(["localectl", "set-locale", f"LANG={loc}"], self)
        return True


def regional(page=None, parent=None):
    return RegionalOptions(page, parent)


# ================================================================== Zasilanie
TIMEOUTS = [0, 1, 2, 3, 5, 10, 15, 20, 25, 30, 45, 60, 120, 180]


class PowerOptions(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("power_opts"), "power", parent)
        w, lay = self.add_tab(plain("po_schemes"))
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("power", 32))
        head.addWidget(ic)
        head.addWidget(wrap_label(plain("po_desc")), 1)
        lay.addLayout(head)
        lay.addWidget(QLabel(plain("po_scheme")))
        self.profile = QComboBox()
        from ...common import power as pw
        names, cur = pw.profiles()
        self._profiles_ok = bool(names)
        labels = {"power-saver": "po_saver", "balanced": "po_balanced", "performance": "po_performance"}
        for key in (names or ["power-saver", "balanced", "performance"]):
            self.profile.addItem(plain(labels[key]) if key in labels else key, key)
        self._profile_start = cur
        self.profile.setCurrentIndex(max(0, self.profile.findData(cur or "balanced")))
        self.profile.setEnabled(self._profiles_ok)
        self.profile.currentIndexChanged.connect(self.changed)
        lay.addWidget(self.profile)
        if not self._profiles_ok:
            lay.addWidget(wrap_label(T("Profile zasilania wymagają usługi tuned-ppd lub power-profiles-daemon "
                                       "(instalator Horyzontu instaluje ją automatycznie).",
                                       "Power profiles require tuned-ppd or power-profiles-daemon.")))
        g = QGroupBox(plain("po_settings"))
        gl = QGridLayout(g)
        b = sysctl.battery()
        gl.addWidget(QLabel(plain("po_ac") if not b or b[1] else tr("po_battery", b[0])), 0, 1)
        gl.addWidget(QLabel(plain("po_monitor_off")), 1, 0)
        self.monitor = self._timeout_combo(config.get("monitor_off_minutes", 20))
        gl.addWidget(self.monitor, 1, 1)
        gl.addWidget(QLabel(plain("po_standby")), 2, 0)
        self.standby = self._timeout_combo(config.get("standby_minutes", 0))
        gl.addWidget(self.standby, 2, 1)
        lay.addWidget(g)
        if not shutil.which("swayidle"):
            lay.addWidget(wrap_label(plain("po_no_swayidle")))
        lay.addStretch(1)
        w2, l2 = self.add_tab(plain("po_advanced"))
        self.show_icon = QCheckBox(tr("po_show_icon").replace("&", ""))
        self.show_icon.setChecked(config.get("power_icon", True))
        self.show_icon.toggled.connect(self.changed)
        l2.addWidget(self.show_icon)
        box = QGroupBox(T("Przyciski zasilania", "Power buttons"))
        bl = QGridLayout(box)
        acts = [("ignore", T("Nic nie rób", "Do nothing")), ("lock", T("Zablokuj komputer", "Lock the computer")),
                ("suspend", T("Wstrzymaj", "Stand by")), ("hibernate", T("Hibernuj", "Hibernate")),
                ("poweroff", T("Zamknij system", "Shut down"))]
        from ...common import power as pw
        self._lid = {}
        rows = [("HandleLidSwitch", T("Po zamknięciu pokrywy komputera przenośnego (na baterii):",
                                      "When I close the lid of my portable computer (on batteries):"), "suspend"),
                ("HandleLidSwitchExternalPower", T("Po zamknięciu pokrywy (zasilanie z sieci):",
                                                   "When I close the lid (plugged in):"), "suspend"),
                ("HandlePowerKey", T("Po naciśnięciu przycisku zasilania komputera:",
                                     "When I press the power button on my computer:"), "poweroff")]
        for i, (key, label, default) in enumerate(rows):
            bl.addWidget(QLabel(label), i * 2, 0)
            c = QComboBox()
            for k, lab in acts:
                c.addItem(lab, k)
            cur = pw.logind_setting(key) or default
            c.setCurrentIndex(max(0, c.findData(cur)))
            c.currentIndexChanged.connect(self.changed)
            bl.addWidget(c, i * 2 + 1, 0)
            self._lid[key] = (c, c.currentData())
        l2.addWidget(box)
        l2.addWidget(wrap_label(T("Zmiana działania pokrywy i przycisku wymaga hasła administratora.",
                                  "Changing lid and button actions requires the administrator password.")))
        l2.addStretch(1)
        self.resize(420, 430)

    def _timeout_combo(self, val):
        c = QComboBox()
        for m in TIMEOUTS:
            c.addItem(plain("po_never") if m == 0 else tr("po_after_min", m), m)
        c.setCurrentIndex(max(0, c.findData(int(val))))
        c.currentIndexChanged.connect(self.changed)
        return c

    def apply(self):
        from ...common import power as pw
        prof = self.profile.currentData()
        if self._profiles_ok and prof and prof != self._profile_start:
            if pw.set_profile(prof, self):
                self._profile_start = prof
            else:
                dialogs.message(self, plain("power_opts"), T("Nie udało się zmienić profilu zasilania.",
                                                             "Could not change the power profile."), "error")
        changed = {k: c.currentData() for k, (c, old) in self._lid.items() if c.currentData() != old}
        if changed:
            vals = {k: c.currentData() for k, (c, old) in self._lid.items()}
            if pw.save_logind(vals, self):
                self._lid = {k: (c, c.currentData()) for k, (c, old) in self._lid.items()}
            else:
                return False
        config.update({"monitor_off_minutes": self.monitor.currentData(), "standby_minutes": self.standby.currentData(),
                       "power_icon": self.show_icon.isChecked()})
        try:
            from ...session import labwc
            labwc.apply_settings()
        except Exception:
            pass
        return True


def power(page=None, parent=None):
    return PowerOptions(page, parent)


# ================================================================== Ułatwienia dostępu
class AccessibilityOptions(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("access_opts"), "accessibility", parent)
        w, lay = self.add_tab(plain("acc_display"))
        g = QGroupBox(plain("acc_contrast"))
        gl = QVBoxLayout(g)
        gl.addWidget(wrap_label(plain("acc_contrast_desc")))
        self.contrast = QCheckBox(tr("acc_high_contrast").replace("&", ""))
        self.contrast.setChecked(config.get("visual_style") == "classic" and config.get("color_scheme") == "graphite")
        self.contrast.toggled.connect(self.changed)
        gl.addWidget(self.contrast)
        lay.addWidget(g)
        g2 = QGroupBox(plain("acc_text_scale"))
        g2l = QVBoxLayout(g2)
        self.scale = QComboBox()
        for key, lab in (("normal", "dp_font_normal"), ("large", "dp_font_large"), ("xlarge", "dp_font_xlarge")):
            self.scale.addItem(plain(lab), key)
        self.scale.setCurrentIndex(max(0, self.scale.findData(config.get("font_size", "normal"))))
        self.scale.currentIndexChanged.connect(self.changed)
        g2l.addWidget(self.scale)
        lay.addWidget(g2)
        lay.addStretch(1)
        w2, l2 = self.add_tab(plain("ms_buttons").replace("Przyciski", "Mysz") if lang_code() == "pl" else "Mouse")
        self.large_cursor = QCheckBox(tr("acc_large_cursor").replace("&", ""))
        self.large_cursor.setChecked(int(config.get("cursor_size", 24)) >= 48)
        self.large_cursor.toggled.connect(self.changed)
        l2.addWidget(self.large_cursor)
        l2.addWidget(wrap_label(plain("ms_relogin_note")))
        l2.addStretch(1)
        w3, l3 = self.add_tab(plain("acc_keyboard"))
        sticky = QCheckBox(tr("acc_sticky").replace("&", ""))
        sticky.setEnabled(False)
        l3.addWidget(sticky)
        l3.addWidget(wrap_label(plain("acc_sticky_note")))
        l3.addStretch(1)
        self.resize(400, 400)

    def apply(self):
        vals = {"font_size": self.scale.currentData(), "cursor_size": 48 if self.large_cursor.isChecked() else 24}
        if self.contrast.isChecked():
            vals.update({"visual_style": "classic", "color_scheme": "graphite"})
        config.update(vals)
        try:
            from ...session import labwc
            labwc.apply_settings()
        except Exception:
            pass
        return True


def accessibility(page=None, parent=None):
    return AccessibilityOptions(page, parent)


# ================================================================== Centrum zabezpieczeń
class Banner(QWidget):
    def __init__(self, title, state, color, desc):
        super().__init__()
        self.title, self.state, self.color, self.desc = title, state, color, desc
        self.setMinimumHeight(64)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        from ...theme.base import hgrad
        c = QColor(self.color)
        p.setBrush(hgrad(r, [(0, c.lighter(160)), (1, c.lighter(110))]))
        p.setPen(c.darker(130))
        p.drawRoundedRect(r, 6, 6)
        f = current().font("big")
        p.setFont(f)
        p.setPen(QColor("#202020"))
        p.drawText(r.adjusted(12, 6, -140, -30), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(current().font("normal"))
        p.drawText(r.adjusted(12, 32, -140, -4), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.desc)
        f.setBold(True)
        p.setFont(f)
        p.setPen(c.darker(200))
        p.drawText(r.adjusted(0, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, self.state)


class SecurityCenter(HWindow):
    def __init__(self):
        super().__init__(plain("security_center"), "security")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        t = QLabel(plain("sec_title"))
        f = current().font("title_big")
        t.setFont(f)
        t.setStyleSheet(f"color: {current().color('group_title').name()};")
        lay.addWidget(t)
        lay.addWidget(QLabel("<b>" + plain("sec_essentials") + "</b>"))
        fw = self._firewall()
        lay.addWidget(Banner(plain("sec_firewall"), *fw))
        up = self._updates()
        lay.addWidget(Banner(plain("sec_updates"), *up))
        se = self._selinux()
        lay.addWidget(Banner(plain("sec_selinux"), *se))
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(plain("sec_firewall_settings"))
        b.clicked.connect(self._fw_settings)
        row.addWidget(b)
        b2 = QPushButton(plain("sys_updates"))
        b2.clicked.connect(lambda: launcher.start_builtin("control", ["system", "updates"]))
        row.addWidget(b2)
        lay.addLayout(row)
        lay.addStretch(1)
        self.resize(560, 470)

    def _firewall(self):
        if shutil.which("firewall-cmd"):
            rc, out = run(["firewall-cmd", "--state"])
            on = out.strip() == "running"
            return (plain("sec_on") if on else plain("sec_off"), "#5ab55a" if on else "#d9534f",
                    plain("sec_fw_on") if on else plain("sec_fw_off"))
        return plain("sec_unknown"), "#e0b040", plain("sec_fw_missing")

    def _updates(self):
        rc, out = run(["systemctl", "is-enabled", "dnf-automatic.timer"])
        on = out.strip() == "enabled"
        return (plain("sec_on") if on else plain("sec_off"), "#5ab55a" if on else "#e0b040",
                plain("sec_upd_on") if on else plain("sec_upd_off"))

    def _selinux(self):
        if shutil.which("getenforce"):
            rc, out = run(["getenforce"])
            mode = out.strip()
            on = mode == "Enforcing"
            return (plain("sec_on") if on else mode.upper() or plain("sec_off"), "#5ab55a" if on else "#e0b040",
                    tr("sec_selinux_mode", mode or "?"))
        return plain("sec_unknown"), "#e0b040", plain("sec_selinux_missing")

    def _fw_settings(self):
        for c in (["firewall-config"], ["gnome-control-center", "network"]):
            if shutil.which(c[0]):
                launcher._spawn(c)
                return
        dialogs.message(self, plain("security_center"), plain("sec_no_fw_tool"), "info")


def security(page=None, parent=None):
    return SecurityCenter()
