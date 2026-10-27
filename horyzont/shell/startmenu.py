"""Dwukolumnowe menu Start."""
import os

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QPainter, QPixmap, QColor, QPen
from PySide6.QtWidgets import QMenu, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy

from .. import config
from ..common import desktopentry, launcher, sysctl
from ..i18n import plain, tr
from ..theme import iconcache
from ..theme.base import HOVER, NORMAL, PRESSED
from ..theme.manager import current

BUILTIN_MENU = {
    # klucz: (nazwa, ikona, akcja)
    "explorer": ("app_explorer", "folder_open", lambda: launcher.start_builtin("explorer")),
    "notepad": ("notepad", "notepad", lambda: launcher.start_builtin("notepad")),
    "taskmgr": ("taskmgr", "taskmgr", lambda: launcher.start_builtin("taskmgr")),
    "control": ("control_panel", "control_panel", lambda: launcher.start_builtin("control")),
    "terminal": ("cmd_title", "cmd", lambda: launcher.open_terminal()),
    "calc": ("app_calc", "calculator", lambda: launcher.start_builtin("calc")),
    "charmap": ("app_charmap", "charmap", lambda: launcher.start_builtin("charmap")),
    "paint": ("app_paint", "paint", lambda: launcher.start_builtin("paint")),
    "wordpad": ("app_wordpad", "wordpad", lambda: launcher.start_builtin("wordpad")),
    "imageviewer": ("app_imageviewer", "image_viewer", lambda: launcher.start_builtin("imageviewer")),
    "mplayer": ("app_mplayer", "media_player", lambda: launcher.start_builtin("mplayer")),
    "soundrec": ("app_soundrec", "recorder", lambda: launcher.start_builtin("soundrec")),
    "sndvol": ("app_sndvol", "volume", lambda: launcher.start_builtin("sndvol")),
    "mines": ("app_mines", "mines", lambda: launcher.start_builtin("mines")),
    "solitaire": ("app_solitaire", "cards", lambda: launcher.start_builtin("solitaire")),
}


def user_picture_pixmap(size=48):
    pic = config.get("user_picture", "builtin:kite")
    if pic.startswith("builtin:"):
        return iconcache.pixmap("avatar_" + pic.split(":", 1)[1], size)
    pm = QPixmap(pic)
    if pm.isNull():
        return iconcache.pixmap("avatar_kite", size)
    return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


class SMItem(QWidget):
    """Element menu Start: ikona + nazwa (+ opcjonalny podpis lub strzałka podmenu)."""

    activated = Signal()

    def __init__(self, menu, text, icon, action=None, bold=False, subtitle="", big=True, right=False,
                 submenu=None, qicon=None, key=None):
        super().__init__(menu)
        self.menu = menu
        self.text = text
        self.icon_name = icon
        self.qicon = qicon
        self.action = action
        self.bold = bold
        self.subtitle = subtitle
        self.big = big
        self.right = right
        self.submenu = submenu
        self.key = key
        self._hover = False
        self.setMouseTracking(True)
        self._sub_timer = QTimer(self)
        self._sub_timer.setSingleShot(True)
        self._sub_timer.setInterval(350)
        self._sub_timer.timeout.connect(self._open_sub)

    def sizeHint(self):
        t = current()
        isz = 32 if self.big else 24
        fm = QFontMetrics(t.font("sm_item"))
        h = max(isz + 6, fm.height() * (2 if self.subtitle else 1) + 8)
        return QSize(160, h)

    def enterEvent(self, e):
        self._hover = True
        self.menu.item_hovered(self)
        self.update()
        if self.submenu:
            self._sub_timer.start()

    def leaveEvent(self, e):
        self._hover = False
        self._sub_timer.stop()
        self.update()

    def _open_sub(self):
        if self.submenu and self._hover:
            self.menu.open_submenu(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.submenu:
                self.menu.open_submenu(self)
                return
            self.menu.trigger(self)
        elif e.button() == Qt.RightButton:
            self.menu.item_context(self, e.globalPosition().toPoint())

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        hl = self._hover or (self.menu.open_item is self)
        if hl:
            t.draw_sm_item_hover(p, self.rect(), self.right)
        isz = 32 if self.big else 24
        x = 6
        y = (self.height() - isz) // 2
        if self.qicon is not None:
            p.drawPixmap(x, y, self.qicon.pixmap(isz, isz))
        else:
            p.drawPixmap(x, y, iconcache.pixmap(self.icon_name, isz))
        x += isz + 6
        f = t.font("sm_item")
        f.setBold(self.bold)
        p.setFont(f)
        if hl:
            col = t.color("highlight_text")
        else:
            col = t.color("sm_right_text" if self.right else "sm_text")
        p.setPen(col)
        fm = QFontMetrics(f)
        avail = self.width() - x - (16 if self.submenu else 4)
        if self.subtitle:
            r1 = QRect(x, 0, avail, self.height() // 2 + 1)
            p.drawText(r1, Qt.AlignBottom | Qt.AlignLeft, fm.elidedText(self.text, Qt.ElideRight, avail))
            f2 = t.font("sm_item")
            p.setFont(f2)
            p.setPen(t.color("highlight_text") if hl else QColor("#6e7a7c"))
            r2 = QRect(x, self.height() // 2 + 1, avail, self.height() // 2)
            p.drawText(r2, Qt.AlignTop | Qt.AlignLeft, QFontMetrics(f2).elidedText(self.subtitle, Qt.ElideRight, avail))
        else:
            p.drawText(QRect(x, 0, avail, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(self.text, Qt.ElideRight, avail))
        if self.submenu:
            from ..theme.base import draw_arrow
            draw_arrow(p, QRect(self.width() - 14, 0, 10, self.height()), "right", col, 3.2)


class SMSeparator(QWidget):
    def __init__(self, parent, right=False):
        super().__init__(parent)
        self.right = right
        self.setFixedHeight(9)

    def paintEvent(self, e):
        p = QPainter(self)
        current().draw_sm_separator(p, self.rect().adjusted(6, 0, -6, 0), self.right)


class AllProgramsButton(QWidget):
    def __init__(self, menu):
        super().__init__(menu)
        self.menu = menu
        self._hover = False
        self.open_sub = False
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(lambda: self._hover and self.menu.open_all_programs(self))

    def enterEvent(self, e):
        self._hover = True
        self.menu.item_hovered(self)
        self._timer.start()
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.menu.open_all_programs(self)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        text = plain("all_programs")
        f = t.font("sm_item")
        f.setBold(True)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text)
        total = tw + 8 + 22
        x0 = (self.width() - total) // 2
        hl = self._hover or self.menu.open_item is self
        if hl:
            t.draw_sm_item_hover(p, QRect(x0 - 10, 3, total + 20, self.height() - 6))
        p.setFont(f)
        p.setPen(t.color("highlight_text") if hl else t.color("sm_text"))
        p.drawText(QRect(x0, 0, tw, self.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        # strzałka w kółku
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRect(x0 + tw + 8, (self.height() - 18) // 2, 18, 18)
        from ..theme.base import vgrad
        p.setBrush(vgrad(r, [(0, "#ffd38a"), (1, "#d47a12")]))
        p.setPen(QPen(QColor("#8a4f08"), 1))
        p.drawEllipse(r)
        from ..theme.base import draw_arrow
        draw_arrow(p, r, "right", "#ffffff", 4.2)


class FooterButton(QWidget):
    def __init__(self, menu, text, icon, action):
        super().__init__(menu)
        self.menu = menu
        self.text = text
        self.icon_name = icon
        self.action = action
        self._hover = False
        self.setMouseTracking(True)

    def sizeHint(self):
        fm = QFontMetrics(current().font("sm_item"))
        return QSize(22 + 6 + fm.horizontalAdvance(self.text) + 12, 30)

    def enterEvent(self, e):
        self._hover = True
        self.menu.item_hovered(self)
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.menu.hide()
            QTimer.singleShot(50, self.action)

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        t.draw_sm_footer_button(p, self.rect(), HOVER if self._hover else NORMAL)
        p.drawPixmap(4, (self.height() - 22) // 2, iconcache.pixmap(self.icon_name, 22))
        p.setFont(t.font("sm_item"))
        p.setPen(t.color("sm_footer_text"))
        p.drawText(QRect(30, 0, self.width() - 30, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class SMColumn(QWidget):
    def __init__(self, parent, right):
        super().__init__(parent)
        self.right = right

    def paintEvent(self, e):
        p = QPainter(self)
        if self.right:
            current().draw_sm_right(p, self.rect())
        else:
            current().draw_sm_left(p, self.rect())


class StartMenu(QWidget):
    """Menu Start jako osobne okno bez ramki.

    Okno najwyższego poziomu (a nie popup) — dzięki temu kompozytor może je
    ustawić w lewym dolnym rogu regułą okna (także po wciśnięciu klawisza
    Windows, gdy nie ma kliknięcia, do którego można „przypiąć” popup),
    a menu dostaje fokus klawiatury. Zawartość budujemy z wyprzedzeniem,
    więc pokazanie menu jest natychmiastowe.
    """
    closed = Signal()
    size_changed = Signal()
    TITLE = "horyzont-startmenu"

    def __init__(self, shell, parent=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.shell = shell
        self.setWindowTitle(self.TITLE)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.open_item = None
        self._submenu = None
        self._all_programs_menu = None
        self.dirty = True
        self._place = QPoint(0, 0)
        self.build()

    # ------------------------------------------------------------ budowa
    def build(self):
        for c in self.findChildren(QWidget):
            c.deleteLater()
        t = current()
        m = t.metrics
        scale = t.font_scale
        W = int(m["sm_width"] * scale)
        hh = int(m["sm_header_h"] * scale)
        fh = int(m["sm_footer_h"] * scale)
        self.header_h, self.footer_h = hh, fh
        lay = QVBoxLayout(self) if self.layout() is None else self.layout()
        while lay.count():
            lay.takeAt(0)
        lay.setContentsMargins(1, hh, 1, fh)
        lay.setSpacing(0)
        cols = QWidget(self)
        hl = QHBoxLayout(cols)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        self.left = SMColumn(cols, False)
        self.right = SMColumn(cols, True)
        hl.addWidget(self.left, 1)
        hl.addWidget(self.right, 1)
        lay.addWidget(cols)

        # --- lewa kolumna
        ll = QVBoxLayout(self.left)
        ll.setContentsMargins(4, 6, 4, 4)
        ll.setSpacing(0)
        for key in config.get("start_pinned", ["browser", "email"]):
            if key in ("browser", "email"):
                e = launcher.default_app(key)
                title = plain("sm_internet" if key == "browser" else "sm_email")
                if e:
                    it = SMItem(self, title, "browser" if key == "browser" else "email",
                                action=lambda e=e: launcher.launch_entry(e), bold=True, subtitle=e.name,
                                qicon=iconcache.theme_or_builtin(e.icon, "browser" if key == "browser" else "email"))
                else:
                    it = SMItem(self, title, "browser" if key == "browser" else "email",
                                action=lambda k=key: launcher.xdg_open("https://" if k == "browser" else "mailto:"),
                                bold=True)
                ll.addWidget(it)
            elif key.startswith("desktop:"):
                e = desktopentry.all_entries().get(key[8:])
                if e:
                    ll.addWidget(SMItem(self, e.name, "app", action=lambda e=e: launcher.launch_entry(e), bold=True,
                                        qicon=iconcache.theme_or_builtin(e.icon, "app"), key=key))
            elif key.startswith("builtin:") and key[8:] in BUILTIN_MENU:
                name, icon, action = BUILTIN_MENU[key[8:]]
                ll.addWidget(SMItem(self, plain(name), icon, action=action, bold=True, key=key))
        ll.addWidget(SMSeparator(self.left))
        for key, (name, icon, qicon, action) in self.frequent_programs():
            ll.addWidget(SMItem(self, name, icon, action=action, qicon=qicon, key=key))
        ll.addStretch(1)
        ll.addWidget(SMSeparator(self.left))
        self.all_programs = AllProgramsButton(self)
        ll.addWidget(self.all_programs)

        # --- prawa kolumna
        rl = QVBoxLayout(self.right)
        rl.setContentsMargins(4, 6, 4, 6)
        rl.setSpacing(0)

        def add(text, icon, action=None, bold=False, submenu=None):
            rl.addWidget(SMItem(self, plain(text), icon, action=action, bold=bold, big=False, right=True,
                                submenu=submenu))

        add("sm_documents", "documents", lambda: launcher.open_path(config.user_dir("DOCUMENTS")), True)
        add("sm_recent", "recent", None, True, submenu=self._recent_menu)
        add("sm_pictures", "pictures", lambda: launcher.open_path(config.user_dir("PICTURES")), True)
        add("sm_music", "music", lambda: launcher.open_path(config.user_dir("MUSIC")), True)
        add("sm_computer", "computer", lambda: launcher.start_builtin("explorer", ["horyzont:computer"]), True)
        add("sm_network", "network", lambda: launcher.start_builtin("explorer", ["horyzont:network"]))
        rl.addWidget(SMSeparator(self.right, True))
        add("sm_control", "control_panel", lambda: launcher.start_builtin("control"))
        add("sm_printers", "printer", lambda: launcher.start_builtin("control", ["printers"]))
        rl.addWidget(SMSeparator(self.right, True))
        add("sm_help", "help", lambda: self.shell.show_help())
        add("sm_search", "search", lambda: launcher.start_builtin("explorer", ["--search"]))
        add("sm_run", "run", lambda: self.shell.show_run())
        rl.addStretch(1)

        # --- stopka
        self.footer_buttons = [
            FooterButton(self, plain("sm_logoff"), "logoff", self.shell.show_logoff),
            FooterButton(self, plain("sm_turnoff"), "shutdown", self.shell.show_turnoff),
        ]
        old = self.size()
        self.resize(W, max(int(400 * scale), lay.sizeHint().height()))
        self.setFixedWidth(W)
        h = max(int(410 * scale), hh + fh + max(ll.sizeHint().height(), rl.sizeHint().height()))
        self.setFixedHeight(h)
        self._place_footer()
        self.dirty = False
        if self._all_programs_menu is not None:
            self._all_programs_menu.deleteLater()
            self._all_programs_menu = None
        if self.size() != old:
            self.size_changed.emit()

    def _place_footer(self):
        x = self.width() - 8
        for b in reversed(self.footer_buttons):
            sz = b.sizeHint()
            x -= sz.width()
            b.setGeometry(x, self.height() - self.footer_h + (self.footer_h - sz.height()) // 2, sz.width(), sz.height())
            x -= 6

    def frequent_programs(self):
        rp = config.get("recent_programs", {})
        count = config.get("start_recent_count", 6)
        items = []
        entries = desktopentry.all_entries()
        defaults = ["builtin:mplayer", "builtin:paint", "builtin:wordpad", "builtin:notepad", "builtin:calc",
                    "builtin:explorer", "builtin:terminal"]
        keys = sorted(rp, key=lambda k: -rp[k])
        for d in defaults:
            if d not in keys:
                keys.append(d)
        pinned = set(config.get("start_pinned", []))
        for k in keys:
            if k in pinned or rp.get(k, 0) <= -1000:
                continue
            if k.startswith("builtin:"):
                b = BUILTIN_MENU.get(k[8:])
                if b:
                    items.append((k, (plain(b[0]), b[1], None, b[2])))
            elif k.startswith("desktop:"):
                e = entries.get(k[8:])
                if e and e.visible():
                    items.append((k, (e.name, "app", iconcache.theme_or_builtin(e.icon, "app"),
                                      lambda e=e: launcher.launch_entry(e))))
            if len(items) >= count:
                break
        return items

    def paintEvent(self, e):
        p = QPainter(self)
        t = current()
        r = self.rect()
        t.draw_sm_header(p, QRect(0, 0, r.width(), self.header_h))
        t.draw_sm_footer(p, QRect(0, r.height() - self.footer_h, r.width(), self.footer_h))
        # ramka między kolumnami i bokami
        p.fillRect(QRect(0, self.header_h, 1, r.height() - self.header_h - self.footer_h), t.color("taskpane_header_text"))
        p.fillRect(QRect(r.width() - 1, self.header_h, 1, r.height() - self.header_h - self.footer_h), t.color("taskpane_header_text"))
        # obraz użytkownika
        ps = int(48 * t.font_scale)
        px, py = 8, (self.header_h - ps) // 2
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(QRect(px + 1, py + 2, ps + 4, ps + 4), 4, 4)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRect(px - 2, py - 2, ps + 4, ps + 4), 4, 4)
        p.drawPixmap(px, py, user_picture_pixmap(ps))
        f = t.font("sm_user")
        p.setFont(f)
        name = sysctl.user_full_name()
        tr_ = QRect(px + ps + 12, 0, r.width() - ps - 30, self.header_h)
        p.setPen(QColor(0, 0, 0, 120))
        p.drawText(tr_.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft, name)
        p.setPen(t.color("sm_user_text"))
        p.drawText(tr_, Qt.AlignVCenter | Qt.AlignLeft, name)
        t.draw_sm_frame(p, r)

    # ------------------------------------------------------------ zachowanie
    def item_hovered(self, item):
        if self._submenu is not None and self.open_item is not item:
            self._submenu.close()

    def trigger(self, item):
        self.hide()
        if item.action:
            QTimer.singleShot(30, item.action)
        self.mark_dirty()   # lista najczęściej używanych programów mogła się zmienić

    def item_context(self, item, gpos):
        if not item.key:
            return
        from .progmenu import program_context
        program_context(self, item.key, gpos, on_change=self.build, on_launch=self.hide,
                        in_frequent=item.key not in config.get("start_pinned", []))

    def close_all(self):
        """Zamyka podmenu Wszystkie programy i samo menu Start (przed uruchomieniem programu)."""
        m = getattr(self, "_all_programs_menu", None)
        if m is not None:
            m.close()
        self.hide()

    def _recent_menu(self, parent):
        m = QMenu(parent)
        docs = launcher.recent_documents(15)
        if not docs:
            a = m.addAction(plain("sm_empty"))
            a.setEnabled(False)
        for d in docs:
            a = m.addAction(iconcache.icon(iconcache.name_for_file(d)), os.path.basename(d))
            a.triggered.connect(lambda _=False, d=d: (self.hide(), launcher.open_path(d)))
        return m

    def open_submenu(self, item):
        if self._submenu is not None:
            self._submenu.close()
        menu = item.submenu(self)
        self._show_sub(item, menu)

    def open_all_programs(self, btn):
        if self._submenu is not None and self.open_item is btn:
            return
        if self._submenu is not None:
            self._submenu.close()
        if self._all_programs_menu is None:
            self._all_programs_menu = self.build_all_programs(self)
            self._all_programs_menu.aboutToHide.connect(self._after_sub_hidden)
        self._show_sub(btn, self._all_programs_menu)

    def _show_sub(self, item, menu):
        self._submenu = menu
        self.open_item = item
        item.update()

        def done():
            if self._submenu is menu:
                self._submenu = None
                self.open_item = None
                item.update()

        try:
            menu.aboutToHide.disconnect(self._sub_done)
        except Exception:
            pass
        self._sub_done = done
        menu.aboutToHide.connect(done)
        if menu is not self._all_programs_menu:
            menu.aboutToHide.connect(self._after_sub_hidden)
        if isinstance(item, AllProgramsButton):
            pos = item.mapToGlobal(QPoint(item.width() - 4, item.height())) - QPoint(0, menu.sizeHint().height())
        else:
            pos = item.mapToGlobal(QPoint(item.width() - 2, 0))
        menu.popup(pos)

    def build_all_programs(self, parent):
        from .progmenu import ProgramMenu

        def submenu(menu, icon, title):
            sm = ProgramMenu(self, title, menu)
            sm.setIcon(iconcache.icon(icon))
            menu.addMenu(sm)
            return sm
        root = ProgramMenu(self, "", parent)
        entries = [e for e in desktopentry.all_entries().values()
                   if e.visible() and not e.id.startswith("horyzont-")]
        folders = {}
        for e in entries:
            # programy o odpowiednikach wbudowanych pomijamy, by nie dublować
            folders.setdefault(desktopentry.folder_for(e), []).append(e)
        order = [k for k, _ in desktopentry.CATEGORY_FOLDERS] + ["cat_other"]

        def add_entry(menu, e):
            a = menu.addAction(iconcache.theme_or_builtin(e.icon, "app"), e.name)
            a.setData("desktop:" + e.id)
            a.triggered.connect(lambda _=False, e=e: (self.hide(), launcher.launch_entry(e)))
            if e.comment:
                a.setToolTip(e.comment)

        def add_builtin(menu, key):
            name, icon, action = BUILTIN_MENU[key]
            a = menu.addAction(iconcache.icon(icon), plain(name))
            a.setData("builtin:" + key)
            a.triggered.connect(lambda _=False, action=action: (self.hide(), action()))

        upd = root.addAction(iconcache.icon("updates"), "Horyzont Updates")
        upd.triggered.connect(lambda: (self.hide(), launcher.start_builtin("control", ["updates"])))
        root.addSeparator()
        # Akcesoria — z wbudowanymi programami
        acc = submenu(root, "programs", plain("cat_accessories"))
        acc.setToolTipsVisible(True)
        fun = submenu(acc, "programs", plain("cat_multimedia"))
        for key in ("mplayer", "soundrec", "sndvol"):
            add_builtin(fun, key)
        systools = submenu(acc, "programs", plain("cat_system"))
        add_builtin(systools, "charmap")
        add_builtin(systools, "taskmgr")
        for e in sorted(folders.get("cat_system", []), key=lambda e: e.name.lower()):
            add_entry(systools, e)
        acc.addSeparator()
        acc_items = [("builtin", "explorer"), ("builtin", "notepad"), ("builtin", "terminal"), ("builtin", "calc"),
                     ("builtin", "paint"), ("builtin", "wordpad"), ("builtin", "imageviewer")]
        for e in folders.get("cat_accessories", []):
            acc_items.append(("entry", e))

        def sort_key(it):
            if it[0] == "builtin":
                return plain(BUILTIN_MENU[it[1]][0]).lower()
            return it[1].name.lower()

        for kind, obj in sorted(acc_items, key=sort_key):
            if kind == "builtin":
                add_builtin(acc, obj)
            else:
                add_entry(acc, obj)
        # pozostałe foldery (Gry zawsze — z wbudowanym Saperem i Pasjansem)
        for key in order:
            if key in ("cat_accessories", "cat_system"):
                continue
            items = folders.get(key, [])
            if not items and key != "cat_games":
                continue
            sub = submenu(root, "games" if key == "cat_games" else "programs", plain(key))
            sub.setToolTipsVisible(True)
            if key == "cat_games":
                add_builtin(sub, "solitaire")
                add_builtin(sub, "mines")
                if items:
                    sub.addSeparator()
            for e in sorted(items, key=lambda e: e.name.lower()):
                add_entry(sub, e)
        # Autostart
        auto = submenu(root, "programs", plain("cat_startup"))
        autostart_dir = os.path.expanduser("~/.config/autostart")
        found = False
        if os.path.isdir(autostart_dir):
            for fn in sorted(os.listdir(autostart_dir)):
                if fn.endswith(".desktop"):
                    e = desktopentry.parse(os.path.join(autostart_dir, fn))
                    if e and e.name:
                        add_entry(auto, e)
                        found = True
        if not found:
            a = auto.addAction(plain("sm_empty"))
            a.setEnabled(False)
        root.addSeparator()
        for kind in ("browser", "email"):
            e = launcher.default_app(kind)
            if e:
                add_entry(root, e)
        add_builtin(root, "control")
        return root

    def mark_dirty(self):
        self.dirty = True
        if not self.isVisible():
            QTimer.singleShot(300, self._rebuild_if_hidden)

    def _rebuild_if_hidden(self):
        if self.dirty and not self.isVisible():
            self.build()

    def set_place(self, pos):
        self._place = QPoint(pos)

    def show_menu(self):
        if self.dirty:
            self.build()
        self.move(self._place)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def popup_at(self, gpos):  # zgodność wsteczna
        self.set_place(QPoint(gpos.x(), gpos.y() - self.height()))
        self.show_menu()

    def event(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.WindowDeactivate and self.isVisible():
            QTimer.singleShot(60, self._close_if_inactive)
        return super().event(e)

    def _close_if_inactive(self):
        from PySide6.QtWidgets import QApplication
        if not self.isVisible() or self.isActiveWindow():
            return
        pw = QApplication.activePopupWidget()
        if pw is not None:
            return   # otwarte podmenu (Wszystkie programy, Moje bieżące dokumenty)
        self.hide()

    def _after_sub_hidden(self):
        QTimer.singleShot(150, self._close_if_inactive)

    def hideEvent(self, e):
        if self._submenu is not None:
            self._submenu.close()
        # menu jest używane ponownie — wyczyść podświetlenia
        for w in self.findChildren(QWidget):
            if getattr(w, "_hover", False):
                w._hover = False
                w.update()
        self._kb_current = None
        self.open_item = None
        self.closed.emit()
        super().hideEvent(e)
        if self.dirty:
            QTimer.singleShot(300, self._rebuild_if_hidden)

    def _nav_items(self):
        left = [w for w in self.left.findChildren(QWidget) if isinstance(w, (SMItem, AllProgramsButton))]
        right = [w for w in self.right.findChildren(QWidget) if isinstance(w, SMItem)]
        key = lambda w: w.mapTo(self, QPoint(0, 0)).y()  # noqa: E731
        return sorted(left, key=key), sorted(right, key=key)

    def _kb_select(self, w):
        for col in self._nav_items():
            for it in col:
                if it._hover and it is not w:
                    it._hover = False
                    it.update()
        if w is not None:
            w._hover = True
            w.update()
        self._kb_current = w

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Escape, Qt.Key_Meta, Qt.Key_Super_L):
            self.hide()
            return
        left, right = self._nav_items()
        cur = getattr(self, "_kb_current", None)
        if cur is not None and not cur._hover:
            cur = None
        col = right if cur in right else left
        if k in (Qt.Key_Down, Qt.Key_Up):
            if not col:
                return
            if cur is None:
                self._kb_select(col[0] if k == Qt.Key_Down else col[-1])
            else:
                i = col.index(cur) + (1 if k == Qt.Key_Down else -1)
                self._kb_select(col[i % len(col)])
            return
        if k in (Qt.Key_Left, Qt.Key_Right) and cur is not None:
            if k == Qt.Key_Right and isinstance(cur, AllProgramsButton):
                self.open_all_programs(cur)
                return
            if k == Qt.Key_Right and isinstance(cur, SMItem) and cur.submenu:
                self.open_submenu(cur)
                return
            other = right if col is left else left
            if other:
                y = cur.mapTo(self, QPoint(0, 0)).y()
                self._kb_select(min(other, key=lambda w: abs(w.mapTo(self, QPoint(0, 0)).y() - y)))
            return
        if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and cur is not None:
            if isinstance(cur, AllProgramsButton):
                self.open_all_programs(cur)
            elif cur.submenu:
                self.open_submenu(cur)
            else:
                self.trigger(cur)
            return
        # pierwsza litera nazwy
        txt = e.text().lower()
        if txt and txt.isprintable():
            for it in left + right:
                if isinstance(it, SMItem) and it.text.lower().startswith(txt):
                    self._kb_select(it)
                    return
        super().keyPressEvent(e)
