"""Właściwości: Ekran — kompozycje, pulpit, wygaszacz ekranu, wygląd, ustawienia."""
import glob
import os
import re
import shutil
import subprocess

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from ... import config
from ...common import dialogs
from ...common.window import HDialog
from ...common.appkit import T
from ...i18n import lang_code, plain, tr
from ...theme import iconcache, wallpaper
from ...theme.base import CHECKED, DISABLED, HOVER, NORMAL, PRESSED
from ...theme.builtin import SCHEMES, ClassicTheme, HoryzontTheme
from ..screensaver import LABELS as SS_LABELS, SAVERS, SaverState
from .common import AppletDialog, MonitorPreview, hline, wrap_label

THEMES_DIR = os.path.join(config.DATA_DIR, "themes")

BUILTIN_THEMES = [
    ("horyzont", {"visual_style": "builtin", "color_scheme": "teal", "wallpaper": "builtin:horyzont"}),
    ("horyzont_grafit", {"visual_style": "builtin", "color_scheme": "graphite", "wallpaper": "builtin:zatoka"}),
    ("horyzont_sliwka", {"visual_style": "builtin", "color_scheme": "plum", "wallpaper": "builtin:zorza"}),
    ("classic", {"visual_style": "classic", "color_scheme": "teal", "wallpaper": "", "desktop_color": "#3a6e8f"}),
]

THEME_LABELS = {
    "horyzont": ("Horyzont", "Horyzont"),
    "horyzont_grafit": ("Horyzont — grafit", "Horyzont — graphite"),
    "horyzont_sliwka": ("Horyzont — śliwka", "Horyzont — plum"),
    "classic": ("Klasyczny", "Classic"),
}

APPEARANCE_KEYS = ("visual_style", "color_scheme", "msstyles_scheme", "font_size", "wallpaper", "wallpaper_mode",
                   "desktop_color")


def theme_label(key):
    l = THEME_LABELS.get(key)
    return l[0 if lang_code() == "pl" else 1] if l else key


def make_theme(style, scheme, ms_scheme, font_size):
    fb = HoryzontTheme(scheme)
    if style == "classic":
        t = ClassicTheme(scheme)
    elif style and style not in ("builtin",) and os.path.exists(style):
        try:
            from ...theme.msstyles import MsStylesTheme
            t = MsStylesTheme(style, ms_scheme, fb)
        except Exception:
            t = fb
    else:
        t = fb
    t.font_scale = {"normal": 1.0, "large": 1.18, "xlarge": 1.36}.get(font_size, 1.0)
    return t


def library_styles():
    """Style .msstyles skopiowane do biblioteki użytkownika."""
    os.makedirs(THEMES_DIR, exist_ok=True)
    out = []
    for p in sorted(glob.glob(os.path.join(THEMES_DIR, "*.msstyles")) + glob.glob(os.path.join(THEMES_DIR, "*", "*.msstyles"))):
        out.append(p)
    cur = config.get("visual_style", "builtin")
    if cur not in ("builtin", "classic") and os.path.exists(cur) and cur not in out:
        out.append(cur)
    return out


def paint_preview(p, rect, theme, wall, mode, color, with_msgbox=True, title_active=None, title_inactive=None):
    """Podgląd kompozycji: pulpit z oknem nieaktywnym, aktywnym i oknem komunikatu."""
    p.save()
    p.setClipRect(rect)
    wallpaper.draw_desktop_background(p, rect, wall, mode, color)
    W, H = rect.width(), rect.height()
    m = theme.metrics
    # okno nieaktywne
    r1 = QRect(rect.left() + int(W * 0.06), rect.top() + int(H * 0.06), int(W * 0.62), int(H * 0.42))
    _mini_window(p, r1, theme, title_inactive or plain("dp_inactive_window"), False)
    r2 = QRect(rect.left() + int(W * 0.14), rect.top() + int(H * 0.22), int(W * 0.72), int(H * 0.6))
    _mini_window(p, r2, theme, title_active or plain("dp_active_window"), True, content=True)
    if with_msgbox:
        r3 = QRect(rect.left() + int(W * 0.42), rect.top() + int(H * 0.56), int(W * 0.5), int(H * 0.36))
        _mini_window(p, r3, theme, plain("dp_message_box"), True, msgbox=True, kinds=("close",))
    p.restore()


def _mini_window(p, r, theme, title, active, content=False, msgbox=False, kinds=("min", "max", "close")):
    theme.draw_window_frame(p, r, active, False)
    l, t, rr, b = theme.frame_margins(False)
    body = r.adjusted(l, t, -rr, -b)
    p.fillRect(body, theme.color("window"))
    rects = theme.caption_button_rects(r.width(), False, kinds)
    for k, br in rects.items():
        theme.draw_caption_button(p, br.translated(r.topLeft()), k, NORMAL, active)
    left = min((x.left() for x in rects.values()), default=r.width())
    theme.draw_caption_text(p, QRect(r.left() + l + 6, r.top() + 1, max(0, left - l - 10), t), title, active)
    p.setFont(theme.font("normal"))
    if content:
        fm = p.fontMetrics()
        mb = QRect(body.left(), body.top(), body.width(), fm.height() + 6)
        p.fillRect(mb, theme.color("menubar"))
        x = mb.left() + 6
        for i, txt in enumerate((plain("dp_normal_item"), plain("dp_disabled_item"), plain("dp_selected_item"))):
            w = fm.horizontalAdvance(txt) + 12
            ir = QRect(x, mb.top(), w, mb.height())
            if i == 2:
                theme.draw_menu_highlight(p, ir, True)
                p.setPen(theme.color("highlight_text"))
            else:
                p.setPen(theme.color("gray_text") if i == 1 else theme.color("window_text"))
            p.drawText(ir, Qt.AlignCenter, txt)
            x += w
        tr_ = QRect(body.left() + 6, mb.bottom() + 6, body.width() - 12, body.bottom() - mb.bottom() - 12)
        if tr_.height() > 10:
            p.fillRect(tr_, theme.color("base"))
            theme.draw_edit_frame(p, tr_, False, False)
            p.setPen(theme.color("window_text"))
            p.drawText(tr_.adjusted(6, 4, -20, 0), Qt.AlignLeft | Qt.AlignTop, plain("dp_window_text"))
            sb = QRect(tr_.right() - 16, tr_.top() + 1, 16, tr_.height() - 2)
            theme.draw_sb_track(p, sb, False)
            theme.draw_sb_arrow(p, QRect(sb.left(), sb.top(), 16, 16), "up", NORMAL)
            if sb.height() > 50:
                theme.draw_sb_thumb(p, QRect(sb.left(), sb.top() + 17, 16, min(28, sb.height() - 40)), False, NORMAL)
            theme.draw_sb_arrow(p, QRect(sb.left(), sb.bottom() - 15, 16, 16), "down", NORMAL)
    if msgbox:
        p.setPen(theme.color("window_text"))
        p.drawText(body.adjusted(8, 4, -8, -26), Qt.AlignLeft | Qt.AlignTop, plain("dp_message_text"))
        bw = 60
        br = QRect(body.center().x() - bw // 2, body.bottom() - 24, bw, 20)
        if br.top() > body.top():
            theme.draw_button(p, br, NORMAL, default=True)
            p.setPen(theme.color("button_text"))
            p.drawText(br, Qt.AlignCenter, plain("ok"))


class Preview(QWidget):
    def __init__(self, dlg, msgbox=True, parent=None):
        super().__init__(parent)
        self.dlg = dlg
        self.msgbox = msgbox
        self.setMinimumSize(340, 170)

    def paintEvent(self, e):
        p = QPainter(self)
        s = self.dlg.pending
        theme = self.dlg.pending_theme()
        r = self.rect().adjusted(1, 1, -1, -1)
        paint_preview(p, r, theme, s["wallpaper"], s["wallpaper_mode"], s["desktop_color"], self.msgbox)
        p.setPen(QColor("#7a8a8c"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class DisplayProperties(AppletDialog):
    def __init__(self, page=None, parent=None):
        super().__init__(plain("display_props"), "display", parent)
        self.pending = {k: config.get(k) for k in APPEARANCE_KEYS}
        self.pending.update({k: config.get(k) for k in ("screensaver", "screensaver_timeout", "screensaver_lock",
                                                         "desktop_icons")})
        self._theme_cache = None
        self._build_themes()
        self._build_desktop()
        self._build_screensaver()
        self._build_appearance()
        self._build_settings()
        from . import iconstab
        iconstab.build(self)
        # szerokość tak dobrana, by wszystkie karty mieściły się bez strzałek przewijania
        tabs = getattr(self, "tabs", None)
        need = tabs.tabBar().sizeHint().width() + 34 if tabs is not None else 440
        self.resize(max(440, need), 540)
        if page:
            self.show_page(page)

    def show_page(self, page):
        idx = {"themes": 0, "desktop": 1, "screensaver": 2, "appearance": 3, "settings": 4, "icons": 5}.get(page)
        if idx is not None:
            self.tabs.setCurrentIndex(idx)

    def pending_theme(self):
        key = tuple(self.pending.get(k) for k in ("visual_style", "color_scheme", "msstyles_scheme", "font_size"))
        if self._theme_cache is None or self._theme_cache[0] != key:
            self._theme_cache = (key, make_theme(*key))
        return self._theme_cache[1]

    def set_pending(self, **kw):
        self.pending.update(kw)
        self.changed()
        self.refresh_previews()

    def refresh_previews(self):
        for w in (self.theme_preview, self.desk_preview, self.app_preview):
            w.update()

    # ================================================================ Kompozycje
    def _build_themes(self):
        w, lay = self.add_tab(plain("dp_themes"))
        lay.addWidget(wrap_label(tr("dp_theme_desc")))
        lay.addWidget(QLabel(plain("dp_theme")))
        row = QHBoxLayout()
        self.theme_combo = QComboBox()
        row.addWidget(self.theme_combo, 1)
        save = QPushButton(plain("dp_save_as"))
        save.clicked.connect(self.save_theme)
        self.del_btn = QPushButton(plain("dp_delete"))
        self.del_btn.clicked.connect(self.delete_theme)
        row.addWidget(save)
        row.addWidget(self.del_btn)
        lay.addLayout(row)
        lay.addWidget(QLabel(plain("dp_sample")))
        self.theme_preview = Preview(self)
        lay.addWidget(self.theme_preview, 1)
        self._fill_theme_combo()
        self.theme_combo.activated.connect(self._theme_picked)

    def _fill_theme_combo(self):
        c = self.theme_combo
        c.blockSignals(True)
        c.clear()
        cur_idx = -1
        for key, vals in BUILTIN_THEMES:
            c.addItem(iconcache.icon("display"), theme_label(key), ("builtin", key))
            if all(self.pending.get(k) == v for k, v in vals.items()):
                cur_idx = c.count() - 1
        for name, vals in config.get("saved_themes", {}).items():
            c.addItem(iconcache.icon("display"), name, ("saved", name))
            if cur_idx < 0 and all(self.pending.get(k) == v for k, v in vals.items() if k in APPEARANCE_KEYS):
                cur_idx = c.count() - 1
        for path in library_styles():
            c.addItem(iconcache.icon("display"), os.path.splitext(os.path.basename(path))[0] + " (.msstyles)", ("style", path))
            if cur_idx < 0 and self.pending.get("visual_style") == path:
                cur_idx = c.count() - 1
        if cur_idx < 0:
            c.insertItem(0, plain("dp_theme_modified"), ("current", None))
            cur_idx = 0
        c.insertSeparator(c.count())
        c.addItem(plain("dp_browse_theme"), ("browse", None))
        c.setCurrentIndex(cur_idx)
        c.blockSignals(False)
        data = c.currentData()
        self.del_btn.setEnabled(bool(data) and data[0] in ("saved", "style"))

    def _theme_picked(self, idx):
        data = self.theme_combo.itemData(idx)
        if not data:
            return
        kind, key = data
        if kind == "builtin":
            vals = dict(BUILTIN_THEMES[[k for k, _ in BUILTIN_THEMES].index(key)][1])
            vals.setdefault("msstyles_scheme", "")
            self.set_pending(**vals)
        elif kind == "saved":
            self.set_pending(**config.get("saved_themes", {}).get(key, {}))
        elif kind == "style":
            self._use_style(key)
        elif kind == "browse":
            f = dialogs.open_file(self, plain("dp_load_msstyles"), os.path.expanduser("~"), plain("dp_msstyles_filter"))
            if f:
                self.load_style_file(f)
            else:
                self._fill_theme_combo()
            return
        self._sync_appearance_controls()
        self.del_btn.setEnabled(kind in ("saved", "style"))

    def load_style_file(self, path):
        """Kopiuje plik stylu do biblioteki i wybiera go."""
        from ...theme.msstyles import MissingStyleError, MsStylesFile
        try:
            f = MsStylesFile(path)
            src = f.path
        except MissingStyleError as e:
            # plik .theme bez stylu obok — prosimy o wskazanie pliku .msstyles
            dialogs.message(self, plain("display_props"),
                            T(f"Kompozycja korzysta ze stylu „{e.name}”, którego nie ma obok pliku .theme.\n\n"
                              f"Wskaż plik {e.name} w następnym oknie.",
                              f"The theme uses the visual style '{e.name}', which is not next to the .theme file.\n\n"
                              f"Please locate {e.name} in the next window."), "info")
            found = dialogs.open_file(self, T(f"Wskaż plik {e.name}", f"Locate {e.name}"), os.path.dirname(path),
                                      T("Style wizualne", "Visual styles") + " (*.msstyles)")
            if not found:
                return
            color = None
            try:
                import configparser
                cp = configparser.ConfigParser(strict=False, interpolation=None)
                with open(path, "rb") as fh:
                    from ...theme.msstyles import _decode_text
                    cp.read_string(_decode_text(fh.read()))
                for sect in cp.sections():
                    if sect.lower() == "visualstyles":
                        color = cp[sect].get("ColorStyle")
            except Exception:
                pass
            try:
                f = MsStylesFile(found)
                f.theme_color = color
                src = f.path
            except Exception as e2:
                dialogs.message(self, plain("display_props"), tr("dp_msstyles_fail", str(e2)), "error")
                return
        except Exception as e:
            dialogs.message(self, plain("display_props"), tr("dp_msstyles_fail", str(e)), "error")
            return
        os.makedirs(THEMES_DIR, exist_ok=True)
        dest = os.path.join(THEMES_DIR, os.path.basename(src))
        try:
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.copy2(src, dest)
        except OSError as e:
            dialogs.message(self, plain("display_props"), tr("dp_msstyles_fail", str(e)), "error")
            return
        self._use_style(dest, getattr(f, "theme_color", None))
        self._fill_theme_combo()
        self.tabs.setCurrentIndex(0)

    def _use_style(self, path, color_hint=None):
        from ...theme.msstyles import list_schemes
        try:
            schemes = list_schemes(path)
        except Exception as e:
            dialogs.message(self, plain("display_props"), tr("dp_msstyles_fail", str(e)), "error")
            return
        scheme = schemes[0][0] if schemes else ""
        if color_hint:
            for s, name in schemes:
                if color_hint.lower() in (s.lower() + name.lower()):
                    scheme = s
        self.set_pending(visual_style=path, msstyles_scheme=scheme)
        self._sync_appearance_controls()

    def save_theme(self):
        name = dialogs.ask_text(self, plain("dp_save_as"), plain("dp_theme_name"), plain("dp_my_theme"))
        if not name:
            return
        saved = dict(config.get("saved_themes", {}))
        saved[name] = {k: self.pending.get(k) for k in APPEARANCE_KEYS}
        config.set("saved_themes", saved)
        self._fill_theme_combo()

    def delete_theme(self):
        data = self.theme_combo.currentData()
        if not data or data[0] not in ("saved", "style"):
            return
        name = self.theme_combo.currentText()
        if dialogs.message(self, plain("display_props"), T(f"Czy na pewno usunąć kompozycję „{name}”?",
                                                           f"Are you sure you want to delete the theme '{name}'?"),
                           "question", ("yes", "no")) != "yes":
            return
        if data[0] == "saved":
            saved = dict(config.get("saved_themes", {}))
            saved.pop(data[1], None)
            config.set("saved_themes", saved)
        else:
            path = data[1]
            lib = os.path.abspath(THEMES_DIR)
            try:
                folder = os.path.dirname(os.path.abspath(path))
                if folder != lib and folder.startswith(lib + os.sep):
                    shutil.rmtree(folder)          # styl rozpakowany do własnego podfolderu
                elif os.path.abspath(path).startswith(lib + os.sep):
                    os.remove(path)
            except OSError as e:
                dialogs.message(self, plain("display_props"), str(e), "error")
                return
            # usunięty styl był w użyciu — wracamy do domyślnej kompozycji Horyzont
            if self.pending.get("visual_style") == path or config.get("visual_style") == path:
                vals = dict(BUILTIN_THEMES[0][1])
                vals.setdefault("msstyles_scheme", "")
                self.set_pending(**vals)
                self._sync_appearance_controls()
                self.changed()
            saved = {k: v for k, v in config.get("saved_themes", {}).items() if v.get("visual_style") != path}
            config.set("saved_themes", saved)
        self._fill_theme_combo()

    # ================================================================ Pulpit
    def _build_desktop(self):
        w, lay = self.add_tab(plain("dp_desktop"))
        self.desk_preview = MonitorPreview(self._paint_desktop)
        lay.addWidget(self.desk_preview, 0, Qt.AlignHCenter)
        lay.addWidget(QLabel(plain("dp_background")))
        row = QHBoxLayout()
        self.wall_list = QListWidget()
        self.wall_list.setIconSize(QSize(24, 18))
        row.addWidget(self.wall_list, 1)
        col = QVBoxLayout()
        b = QPushButton(plain("browse"))
        b.clicked.connect(self._browse_wall)
        col.addWidget(b)
        col.addWidget(QLabel(plain("dp_position")))
        self.pos_combo = QComboBox()
        for key, lab in (("center", "dp_center"), ("tile", "dp_tile"), ("stretch", "dp_stretch"),
                         ("fill", "dp_fill"), ("fit", "dp_fit")):
            self.pos_combo.addItem(plain(lab), key)
        self.pos_combo.setCurrentIndex(max(0, self.pos_combo.findData(self.pending["wallpaper_mode"])))
        self.pos_combo.currentIndexChanged.connect(lambda i: self.set_pending(wallpaper_mode=self.pos_combo.itemData(i)))
        col.addWidget(self.pos_combo)
        col.addWidget(QLabel(plain("dp_color")))
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(60)
        self.color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        col.addWidget(self.color_btn)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row, 1)
        cust = QPushButton(plain("dp_customize"))
        cust.clicked.connect(self._customize_desktop)
        lay.addWidget(cust, 0, Qt.AlignLeft)
        self._fill_wallpapers()
        self.wall_list.currentItemChanged.connect(self._wall_picked)

    def _paint_desktop(self, p, r):
        s = self.pending
        wallpaper.draw_desktop_background(p, r, s["wallpaper"], s["wallpaper_mode"], s["desktop_color"])

    def _fill_wallpapers(self):
        lw = self.wall_list
        lw.blockSignals(True)
        lw.clear()
        it = QListWidgetItem(iconcache.icon("delete"), plain("dp_none"))
        it.setData(Qt.UserRole, "")
        lw.addItem(it)
        for name in wallpaper.BUILTIN:
            pm = QPixmap.fromImage(wallpaper.render(name, 96, 72).scaled(24, 18, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            it = QListWidgetItem(QIcon(pm), wallpaper.label(name))
            it.setData(Qt.UserRole, "builtin:" + name)
            lw.addItem(it)
        paths = []
        for d in ("/usr/share/backgrounds", "/usr/share/wallpapers", config.user_dir("PICTURES")):
            if not os.path.isdir(d):
                continue
            for root, dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                        paths.append(os.path.join(root, f))
                if len(paths) > 200:
                    break
        cur = self.pending["wallpaper"]
        if cur and not cur.startswith("builtin:") and cur not in paths and os.path.exists(cur):
            paths.insert(0, cur)
        for pth in paths[:200]:
            it = QListWidgetItem(iconcache.icon("file_image"), os.path.splitext(os.path.basename(pth))[0])
            it.setData(Qt.UserRole, pth)
            it.setToolTip(pth)
            lw.addItem(it)
        for i in range(lw.count()):
            if lw.item(i).data(Qt.UserRole) == cur:
                lw.setCurrentRow(i)
                break
        lw.blockSignals(False)

    def _wall_picked(self, cur, prev):
        if cur is not None:
            self.set_pending(wallpaper=cur.data(Qt.UserRole))

    def _browse_wall(self):
        f = dialogs.open_file(self, plain("browse"), config.user_dir("PICTURES"), plain("dp_wallpaper_filter"))
        if f:
            self.pending["wallpaper"] = f
            self._fill_wallpapers()
            self.set_pending(wallpaper=f)

    def _update_color_btn(self):
        pm = QPixmap(36, 14)
        pm.fill(QColor(self.pending["desktop_color"]))
        p = QPainter(pm)
        p.setPen(QColor("#404040"))
        p.drawRect(0, 0, 35, 13)
        p.end()
        self.color_btn.setIcon(QIcon(pm))
        self.color_btn.setIconSize(QSize(36, 14))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.pending["desktop_color"]), self, plain("dp_color"),
                                  QColorDialog.DontUseNativeDialog)
        if c.isValid():
            self.set_pending(desktop_color=c.name())
            self._update_color_btn()

    def _customize_desktop(self):
        d = HDialog(plain("dp_desktop_items"), "show_desktop", self)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        box = QGroupBox(plain("dp_desktop_icons"))
        bl = QGridLayout(box)
        icons = list(self.pending.get("desktop_icons") or [])
        checks = {}
        for i, (key, label, icon) in enumerate((("documents", "my_documents", "documents"), ("computer", "my_computer", "computer"),
                                                ("network", "my_network", "network"), ("recycle", "recycle_bin", "recycle_empty"))):
            cb = QCheckBox(plain(label))
            cb.setIcon(iconcache.icon(icon))
            cb.setChecked(key in icons)
            checks[key] = cb
            bl.addWidget(cb, i // 2, i % 2)
        lay.addWidget(box)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        if d.exec() == QDialog.Accepted:
            order = ["computer", "documents", "network", "recycle"]
            self.pending["desktop_icons"] = [k for k in order if checks[k].isChecked()]
            self.changed()

    # ================================================================ Wygaszacz
    def _build_screensaver(self):
        w, lay = self.add_tab(plain("dp_screensaver"))
        self.ss_state = SaverState(self.pending["screensaver"] or "blank", seed=4)
        self.ss_preview = MonitorPreview(lambda p, r: self.ss_state.paint(p, r))
        lay.addWidget(self.ss_preview, 0, Qt.AlignHCenter)
        box = QGroupBox(plain("dp_screensaver"))
        g = QGridLayout(box)
        self.ss_combo = QComboBox()
        self.ss_combo.addItem(plain("dp_ss_none"), "")
        for s in SAVERS:
            self.ss_combo.addItem(plain(SS_LABELS[s]), s)
        self.ss_combo.setCurrentIndex(max(0, self.ss_combo.findData(self.pending["screensaver"] or "")))
        self.ss_combo.currentIndexChanged.connect(self._ss_changed)
        g.addWidget(self.ss_combo, 0, 0, 1, 2)
        st = QPushButton(plain("dp_ss_settings"))
        st.setEnabled(False)
        g.addWidget(st, 0, 2)
        pv = QPushButton(plain("dp_ss_preview"))
        pv.clicked.connect(self._ss_preview_full)
        g.addWidget(pv, 0, 3)
        g.addWidget(QLabel(plain("dp_ss_wait")), 1, 0)
        self.ss_wait = QSpinBox()
        self.ss_wait.setRange(1, 240)
        self.ss_wait.setValue(int(self.pending["screensaver_timeout"] or 10))
        self.ss_wait.setSuffix(" " + plain("dp_ss_minutes"))
        self.ss_wait.valueChanged.connect(lambda v: (self.pending.__setitem__("screensaver_timeout", v), self.changed()))
        g.addWidget(self.ss_wait, 1, 1)
        self.ss_lock = QCheckBox(tr("dp_ss_resume"))
        self.ss_lock.setChecked(bool(self.pending["screensaver_lock"]))
        self.ss_lock.toggled.connect(lambda v: (self.pending.__setitem__("screensaver_lock", v), self.changed()))
        g.addWidget(self.ss_lock, 1, 2, 1, 2)
        lay.addWidget(box)
        pw = QGroupBox(plain("dp_power"))
        pl = QHBoxLayout(pw)
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("power", 32))
        pl.addWidget(ic)
        pl.addWidget(wrap_label(plain("dp_power_desc")), 1)
        pb = QPushButton(plain("dp_power_btn"))
        from ...common import launcher
        pb.clicked.connect(lambda: launcher.start_builtin("control", ["power"]))
        pl.addWidget(pb, 0, Qt.AlignBottom)
        lay.addWidget(pw)
        lay.addStretch(1)
        self.ss_timer = QTimer(self)
        self.ss_timer.timeout.connect(self._ss_tick)
        self.ss_timer.start(40)

    def _ss_tick(self):
        if self.tabs.currentIndex() == 2 and self.isVisible():
            self.ss_state.step()
            self.ss_preview.update()

    def _ss_changed(self, i):
        kind = self.ss_combo.itemData(i)
        self.pending["screensaver"] = kind
        self.ss_state = SaverState(kind or "blank", seed=4)
        self.changed()

    def _ss_preview_full(self):
        from ...common import launcher
        kind = self.ss_combo.currentData() or "blank"
        launcher._spawn(launcher.builtin_command("screensaver", [kind, "--preview"]))

    # ================================================================ Wygląd
    def _build_appearance(self):
        w, lay = self.add_tab(plain("dp_appearance"))
        self.app_preview = Preview(self, msgbox=True)
        lay.addWidget(self.app_preview, 1)
        g = QGridLayout()
        g.addWidget(QLabel(plain("dp_windows_buttons")), 0, 0, 1, 2)
        self.style_combo = QComboBox()
        g.addWidget(self.style_combo, 1, 0, 1, 2)
        g.addWidget(QLabel(plain("dp_color_scheme")), 2, 0, 1, 2)
        self.scheme_combo = QComboBox()
        g.addWidget(self.scheme_combo, 3, 0, 1, 2)
        g.addWidget(QLabel(plain("dp_font_size")), 4, 0, 1, 2)
        self.font_combo = QComboBox()
        for key, lab in (("normal", "dp_font_normal"), ("large", "dp_font_large"), ("xlarge", "dp_font_xlarge")):
            self.font_combo.addItem(plain(lab), key)
        g.addWidget(self.font_combo, 5, 0)
        col = QVBoxLayout()
        eff = QPushButton(plain("dp_effects"))
        eff.clicked.connect(self._effects)
        col.addWidget(eff)
        adv = QPushButton(plain("dp_advanced"))
        adv.setEnabled(False)
        col.addWidget(adv)
        g.addLayout(col, 4, 1, 2, 1, Qt.AlignRight | Qt.AlignBottom)
        lay.addLayout(g)
        self._sync_appearance_controls()
        self.style_combo.activated.connect(self._style_picked)
        self.scheme_combo.activated.connect(self._scheme_picked)
        self.font_combo.activated.connect(lambda i: self.set_pending(font_size=self.font_combo.itemData(i)))

    def _sync_appearance_controls(self):
        sc = self.style_combo
        sc.blockSignals(True)
        sc.clear()
        sc.addItem(plain("dp_style_builtin"), "builtin")
        sc.addItem(plain("dp_style_classic"), "classic")
        for pth in library_styles():
            sc.addItem(os.path.splitext(os.path.basename(pth))[0], pth)
        cur = self.pending.get("visual_style") or "builtin"
        if sc.findData(cur) < 0 and os.path.exists(cur):
            sc.addItem(os.path.basename(cur), cur)
        sc.setCurrentIndex(max(0, sc.findData(cur)))
        sc.blockSignals(False)
        self._fill_schemes()
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(self.pending.get("font_size", "normal"))))

    def _fill_schemes(self):
        c = self.scheme_combo
        c.blockSignals(True)
        c.clear()
        style = self.pending.get("visual_style") or "builtin"
        if style in ("builtin", "classic"):
            for key, sc in SCHEMES.items():
                c.addItem(sc["label_pl"] if lang_code() == "pl" else sc["label_en"], ("builtin", key))
            c.setCurrentIndex(max(0, list(SCHEMES).index(self.pending.get("color_scheme", "teal"))
                                  if self.pending.get("color_scheme") in SCHEMES else 0))
        else:
            from ...theme.msstyles import list_schemes
            try:
                schemes = list_schemes(style)
            except Exception:
                schemes = []
            for res, name in schemes:
                c.addItem(name, ("ms", res))
            for i in range(c.count()):
                if c.itemData(i)[1] == (self.pending.get("msstyles_scheme") or "").upper():
                    c.setCurrentIndex(i)
        c.blockSignals(False)

    def _style_picked(self, i):
        style = self.style_combo.itemData(i)
        if style in ("builtin", "classic"):
            self.set_pending(visual_style=style)
        else:
            self._use_style(style)
            return
        self._fill_schemes()
        self._fill_theme_combo()

    def _scheme_picked(self, i):
        kind, key = self.scheme_combo.itemData(i)
        if kind == "builtin":
            self.set_pending(color_scheme=key)
        else:
            self.set_pending(msstyles_scheme=key)
        self._fill_theme_combo()

    def _effects(self):
        d = HDialog(plain("dp_effects_title"), "display", self)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        opts = [("effect_menu_fade", "dp_eff_fade"), ("effect_shadows", "dp_eff_shadows"),
                ("effect_drag_full", "dp_eff_drag"), ("effect_hide_underline", "dp_eff_underline")]
        boxes = {}
        for key, lab in opts:
            cb = QCheckBox(plain(lab))
            cb.setChecked(bool(config.get(key, key != "effect_hide_underline")))
            lay.addWidget(cb)
            boxes[key] = cb
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        if d.exec() == QDialog.Accepted:
            for k, cb in boxes.items():
                config.set(k, cb.isChecked())

    # ================================================================ Ustawienia
    def _build_settings(self):
        w, lay = self.add_tab(plain("dp_settings"))
        self.outputs = read_outputs()
        mon = QLabel()
        mon.setPixmap(_monitor_pixmap())
        mon.setAlignment(Qt.AlignCenter)
        lay.addWidget(mon)
        lay.addWidget(QLabel(plain("dp_display")))
        self.out_combo = QComboBox()
        for o in self.outputs:
            self.out_combo.addItem(f"1. {o['name']} — {o.get('desc', '')}".strip(" —"), o["name"])
        if not self.outputs:
            self.out_combo.addItem(plain("dp_no_randr"))
            self.out_combo.setEnabled(False)
        lay.addWidget(self.out_combo)
        row = QHBoxLayout()
        res_box = QGroupBox(plain("dp_resolution"))
        rl = QVBoxLayout(res_box)
        sl_row = QHBoxLayout()
        sl_row.addWidget(QLabel(plain("dp_less")))
        self.res_slider = QSlider(Qt.Horizontal)
        sl_row.addWidget(self.res_slider, 1)
        sl_row.addWidget(QLabel(plain("dp_more")))
        rl.addLayout(sl_row)
        self.res_label = QLabel()
        self.res_label.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.res_label)
        row.addWidget(res_box, 1)
        cq = QGroupBox(plain("dp_color_quality"))
        cl = QVBoxLayout(cq)
        cqc = QComboBox()
        cqc.addItem(plain("dp_highest_32"))
        cl.addWidget(cqc)
        cl.addWidget(QLabel(plain("dp_scale")))
        self.scale_combo = QComboBox()
        for s in ("1", "1.25", "1.5", "1.75", "2"):
            self.scale_combo.addItem(f"{int(float(s) * 100)}%", s)
        cl.addWidget(self.scale_combo)
        row.addWidget(cq, 1)
        lay.addLayout(row)
        rr = QHBoxLayout()
        self.rate_label = QLabel(plain("dp_refresh_rate"))
        rr.addWidget(self.rate_label)
        self.rate_combo = QComboBox()
        self.rate_combo.currentIndexChanged.connect(lambda *_: self._settings_dirty())
        rr.addWidget(self.rate_combo, 1)
        lay.addLayout(rr)
        self.custom_note = wrap_label(T("Rozdzielczości oznaczone * nie są natywne dla tego ekranu — obraz będzie "
                                        "skalowany przez kartę graficzną.",
                                        "Resolutions marked * are not native to this display and will be scaled "
                                        "by the graphics card."))
        lay.addWidget(self.custom_note)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ident = QPushButton(plain("dp_identify"))
        ident.clicked.connect(self._identify)
        btns.addWidget(ident)
        trb = QPushButton(plain("dp_troubleshoot"))
        from ...common import launcher
        trb.clicked.connect(lambda: launcher.start_builtin("explorer", ["horyzont:help"]))
        btns.addWidget(trb)
        lay.addLayout(btns)
        lay.addStretch(1)
        self.out_combo.currentIndexChanged.connect(self._load_output)
        self.res_slider.valueChanged.connect(self._res_changed)
        self.scale_combo.currentIndexChanged.connect(lambda *_: self._settings_dirty())
        self._settings_changed = False
        self._load_output()

    STANDARD_MODES = [(800, 600), (1024, 768), (1152, 864), (1280, 720), (1280, 800), (1280, 1024), (1360, 768),
                      (1366, 768), (1440, 900), (1600, 900), (1600, 1200), (1680, 1050), (1920, 1080),
                      (1920, 1200), (2560, 1440), (2560, 1600), (3840, 2160)]

    def _load_output(self, *_):
        if not self.outputs:
            self.res_slider.setEnabled(False)
            self.rate_combo.setEnabled(False)
            self.res_label.setText("—")
            return
        o = self.outputs[max(0, self.out_combo.currentIndex())]
        if not o["modes"]:
            # brak listy trybów (np. ekran wirtualny) — przynajmniej bieżąca rozdzielczość ekranu
            from PySide6.QtWidgets import QApplication
            g = QApplication.primaryScreen().size() * QApplication.primaryScreen().devicePixelRatio()
            o["modes"] = [(g.width(), g.height(), 60.0)]
            o["cur"] = o["cur"] or o["modes"][0]
        native = sorted({(m[0], m[1]) for m in o["modes"]})
        maxw = max((w for w, h in native), default=0)
        maxh = max((h for w, h in native), default=0)
        # laptopy zwykle podają tylko rozdzielczość natywną — dokładamy standardowe niższe (tryby niestandardowe)
        extra = [(w, h) for w, h in self.STANDARD_MODES if w <= maxw and h <= maxh and (w, h) not in native]
        modes = sorted([(w, h, False) for w, h in native] + [(w, h, True) for w, h in extra],
                       key=lambda m: (m[0] * m[1], m[0]))
        self._modes = modes
        self.res_slider.blockSignals(True)
        self.res_slider.setRange(0, max(0, len(modes) - 1))
        cur = (o["cur"][0], o["cur"][1]) if o.get("cur") else None
        idx = next((i for i, m in enumerate(modes) if (m[0], m[1]) == cur), len(modes) - 1)
        self.res_slider.setValue(idx)
        self.res_slider.blockSignals(False)
        self._res_label()
        i = self.scale_combo.findData(str(o.get("scale", "1")).rstrip("0").rstrip(".") or "1")
        self.scale_combo.blockSignals(True)
        self.scale_combo.setCurrentIndex(max(0, i))
        self.scale_combo.blockSignals(False)
        self._fill_rates()
        self._settings_changed = False

    def _fill_rates(self):
        if not self._modes:
            return
        o = self.outputs[max(0, self.out_combo.currentIndex())]
        w, h, custom = self._modes[min(self.res_slider.value(), len(self._modes) - 1)]
        rates = sorted({round(m[2], 3) for m in o["modes"] if (m[0], m[1]) == (w, h)}, reverse=True)
        if custom or not rates:
            rates = [60.0]
        cur = o["cur"][2] if o.get("cur") and (o["cur"][0], o["cur"][1]) == (w, h) else rates[0]
        self.rate_combo.blockSignals(True)
        self.rate_combo.clear()
        for r in rates:
            self.rate_combo.addItem(f"{r:.0f} Hz" if abs(r - round(r)) < 0.05 else f"{r:.2f} Hz".replace(".", ","), r)
        self.rate_combo.setCurrentIndex(min(range(len(rates)), key=lambda i: abs(rates[i] - cur)))
        self.rate_combo.blockSignals(False)
        self.rate_combo.setEnabled(len(rates) > 1)

    def _res_label(self):
        if self._modes:
            w, h, custom = self._modes[self.res_slider.value()]
            self.res_label.setText(tr("dp_pixels", w, h) + (" *" if custom else ""))

    def _res_changed(self, v):
        self._res_label()
        self._fill_rates()
        self._settings_dirty()

    def _settings_dirty(self):
        self._settings_changed = True
        self.changed()

    def _identify(self):
        from PySide6.QtWidgets import QApplication
        lbl = QLabel("1")
        lbl.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        f = lbl.font()
        f.setPixelSize(120)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet("background: #000; color: #fff; padding: 20px;")
        lbl.show()
        QTimer.singleShot(2000, lbl.close)
        self._ident = lbl

    def _apply_display_settings(self):
        if not self._settings_changed or not self.outputs:
            return True
        from ...common import displaycfg
        o = self.outputs[max(0, self.out_combo.currentIndex())]
        w, h, custom = self._modes[self.res_slider.value()]
        rate = self.rate_combo.currentData() or 60.0
        scale = self.scale_combo.currentData()
        old = {"mode": f"{o['cur'][0]}x{o['cur'][1]}@{o['cur'][2]:.3f}" if o.get("cur") else None,
               "custom": False, "scale": str(o.get("scale", 1))}
        new = {"mode": f"{w}x{h}@{rate:.3f}", "custom": custom, "scale": scale}
        ok, err = displaycfg.apply_output(o["name"], new)
        if not ok:
            dialogs.message(self, plain("display_props"), T("Nie udało się zmienić ustawień ekranu:\n", "Could not change "
                                                            "the display settings:\n") + err, "error")
            return False
        displaycfg.notify_shell()
        if not keep_settings_dialog(self):
            if old["mode"]:
                displaycfg.apply_output(o["name"], old)
                displaycfg.notify_shell()
            self.outputs = read_outputs()
            self._load_output()
            return False
        displaycfg.save_output(o["name"], new)
        self._settings_changed = False
        self.outputs = read_outputs()
        return True

    # ================================================================ zapis
    def apply(self):
        if not self._apply_display_settings():
            return False
        vals = dict(self.pending)
        config.update(vals)
        try:
            from ...session import labwc
            labwc.apply_settings()
        except Exception:
            pass
        self._fill_theme_combo()
        return True


def _monitor_pixmap():
    pm = QPixmap(120, 90)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.drawPixmap(0, 0, iconcache.pixmap("computer", 90).scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    p.end()
    return pm


def read_outputs():
    """Odczyt monitorów i trybów z wlr-randr."""
    if not shutil.which("wlr-randr"):
        return []
    try:
        out = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return []
    outputs = []
    cur = None
    in_modes = False
    for line in out.splitlines():
        if line and not line.startswith(" "):
            name, _, desc = line.partition(" ")
            cur = {"name": name, "desc": desc.strip().strip('"'), "modes": [], "cur": None, "scale": 1}
            outputs.append(cur)
            in_modes = False
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("Modes:"):
            in_modes = True
            continue
        if in_modes:
            # „1920x1080 px, 60.000000 Hz (preferred, current)”; ekrany wirtualne podają tryb bez Hz
            m = re.match(r"(\d+)x(\d+) px(?:, ([\d.]+) Hz)?(.*)", s)
            if m:
                mode = (int(m.group(1)), int(m.group(2)), float(m.group(3) or 60.0))
                cur["modes"].append(mode)
                if "current" in m.group(4):
                    cur["cur"] = mode
                continue
            in_modes = False
        if s.startswith("Scale:"):
            try:
                cur["scale"] = float(s.split(":", 1)[1])
            except ValueError:
                pass
    return outputs


def keep_settings_dialog(parent):
    """Pytanie po zmianie rozdzielczości z odliczaniem 15 s; brak odpowiedzi = przywrócenie."""
    d = HDialog(plain("dp_keep_title"), "display", parent, help_button=False)
    lay = QVBoxLayout(d.body())
    lay.setContentsMargins(12, 12, 12, 12)
    lbl = QLabel()
    lbl.setWordWrap(True)
    lay.addWidget(lbl)
    row = QHBoxLayout()
    row.addStretch(1)
    yes = QPushButton(plain("yes"))
    no = QPushButton(plain("no"))
    row.addWidget(yes)
    row.addWidget(no)
    lay.addLayout(row)
    left = {"n": 15}

    def tick():
        lbl.setText(tr("dp_keep_text", left["n"]))
        left["n"] -= 1
        if left["n"] < 0:
            d.reject()
    t = QTimer(d)
    t.timeout.connect(tick)
    tick()
    t.start(1000)
    yes.clicked.connect(d.accept)
    no.clicked.connect(d.reject)
    d.setFixedWidth(380)
    return d.exec() == QDialog.Accepted


def open_display(page=None, parent=None):
    return DisplayProperties(page, parent)
