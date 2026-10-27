"""Pulpit: tapeta, ikony, zaznaczanie, przeciąganie i menu kontekstowe."""
import os
import urllib.parse

from PySide6.QtCore import (QFileSystemWatcher, QMimeData, QPoint, QRect, QSize,
                            Qt, QTimer, QUrl)
from PySide6.QtGui import (QColor, QDrag, QFont, QFontMetrics, QPainter,
                           QPixmap, QTextLayout, QTextOption)
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

from .. import config
from ..common import desktopentry, dialogs, fileops, launcher, sysctl
from ..i18n import plain, tr
from ..theme import iconcache, wallpaper
from ..theme.manager import ThemeManager, current

CELL_W, CELL_H = 76, 74
MARGIN = 4

SPECIAL = {
    "documents": ("my_documents", "documents"),
    "computer": ("my_computer", "computer"),
    "network": ("my_network", "network"),
    "recycle": ("recycle_bin", "recycle_empty"),
}


class DIcon:
    def __init__(self, key, label, icon=None, qicon=None, path=None, special=None, shortcut=False, entry=None):
        self.key = key
        self.label = label
        self.icon = icon
        self.qicon = qicon
        self.path = path
        self.special = special
        self.shortcut = shortcut
        self.entry = entry
        self.pos = QPoint(0, 0)
        self.selected = False


class Desktop(QWidget):
    def __init__(self, shell):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setWindowTitle("horyzont-desktop")
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDesktop, True)
        self.shell = shell
        self.icons = []
        self._bg = None
        self._bg_key = None
        self._press = None
        self._press_icon = None
        self._rubber = None
        self._drag_started = False
        self._editor = None
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.desktop_dir = config.user_dir("DESKTOP")
        os.makedirs(self.desktop_dir, exist_ok=True)
        self.watcher = QFileSystemWatcher([self.desktop_dir])
        trash_files = os.path.join(fileops.TRASH_HOME, "files")
        os.makedirs(trash_files, exist_ok=True)
        self.watcher.addPath(trash_files)
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(250)
        self._reload_timer.timeout.connect(self.reload)
        self.watcher.directoryChanged.connect(lambda *_: self._reload_timer.start())
        ThemeManager.instance().changed.connect(self._theme_changed)
        self._cfg = config.watch(self._config_changed)
        self._last_wall = (config.get("wallpaper"), config.get("wallpaper_mode"), config.get("desktop_color"))
        self.reload()

    # ------------------------------------------------------------ dane
    def reload(self):
        sel = {i.key for i in self.icons if i.selected}
        icons = []
        if config.get("desktop_show_icons", True):
            for key in config.get("desktop_icons", []):
                if key in SPECIAL:
                    name, ic = SPECIAL[key]
                    if key == "recycle" and fileops.trash_count() > 0:
                        ic = "recycle_full"
                    icons.append(DIcon("special:" + key, plain(name), ic, special=key))
            try:
                names = sorted(os.listdir(self.desktop_dir), key=lambda s: s.lower())
            except OSError:
                names = []
            for n in names:
                if n.startswith("."):
                    continue
                p = os.path.join(self.desktop_dir, n)
                if n.endswith(".desktop"):
                    e = desktopentry.parse(p)
                    label = (e.name if e and e.name else n[:-8])
                    qi = iconcache.theme_or_builtin(e.icon, "app") if e else None
                    icons.append(DIcon("file:" + n, label, "app", qicon=qi, path=p, shortcut=True, entry=e))
                else:
                    label = n
                    if config.get("explorer_hide_ext", True) and not os.path.isdir(p):
                        base, ext = os.path.splitext(n)
                        if base and ext:
                            label = base
                    icons.append(DIcon("file:" + n, label, iconcache.name_for_file(p), path=p))
        for i in icons:
            i.selected = i.key in sel
        self.icons = icons
        self.layout_icons()
        self.update()

    def layout_icons(self):
        positions = config.get("icon_positions", {})
        h = self.height() or 600
        rows = max(1, (h - MARGIN * 2) // CELL_H)
        taken = set()
        auto = config.get("desktop_auto_arrange", False)
        free = []
        for ic in self.icons:
            if not auto and ic.key in positions:
                x, y = positions[ic.key]
                ic.pos = QPoint(int(x), int(y))
                taken.add(self._cell_of(ic.pos))
            else:
                free.append(ic)
        idx = 0
        for ic in free:
            while True:
                col, row = divmod(idx, rows)
                idx += 1
                if (col, row) not in taken:
                    break
            ic.pos = QPoint(MARGIN + col * CELL_W, MARGIN + row * CELL_H)
            taken.add((col, row))

    def _cell_of(self, pos):
        return ((pos.x() - MARGIN + CELL_W // 2) // CELL_W, (pos.y() - MARGIN + CELL_H // 2) // CELL_H)

    def _snap(self, pos):
        col, row = self._cell_of(pos)
        col = max(0, col)
        row = max(0, min(row, max(0, (self.height() - MARGIN * 2) // CELL_H - 1)))
        return QPoint(MARGIN + col * CELL_W, MARGIN + row * CELL_H)

    def save_positions(self):
        pos = dict(config.get("icon_positions", {}))
        for ic in self.icons:
            pos[ic.key] = [ic.pos.x(), ic.pos.y()]
        config.set("icon_positions", pos)

    def arrange_by(self, how):
        def key(ic):
            if ic.special:
                return (0, list(SPECIAL).index(ic.special), "")
            p = ic.path
            try:
                st = os.stat(p)
            except OSError:
                st = None
            if how == "size":
                return (1, st.st_size if st else 0, ic.label.lower())
            if how == "type":
                return (1, os.path.splitext(p)[1].lower() if not os.path.isdir(p) else "", ic.label.lower())
            if how == "modified":
                return (1, -(st.st_mtime if st else 0), ic.label.lower())
            return (1, 0 if os.path.isdir(p) else 1, ic.label.lower())
        self.icons.sort(key=key)
        config.set("icon_positions", {})
        self.layout_icons()
        self.save_positions()
        self.update()

    # ------------------------------------------------------------ rysowanie
    def _theme_changed(self):
        self.update()

    def _config_changed(self):
        w = (config.get("wallpaper"), config.get("wallpaper_mode"), config.get("desktop_color"))
        if w != self._last_wall:
            self._last_wall = w
            self._bg = None
        self.reload()

    def resizeEvent(self, e):
        self._bg = None
        self.layout_icons()

    def _background(self):
        key = (self.width(), self.height(), self._last_wall)
        if self._bg is None or self._bg_key != key:
            pm = QPixmap(self.size())
            p = QPainter(pm)
            wallpaper.draw_desktop_background(p, self.rect())
            p.end()
            self._bg = pm
            self._bg_key = key
        return self._bg

    def icon_rect(self, ic):
        return QRect(ic.pos.x(), ic.pos.y(), CELL_W, CELL_H)

    def _icon_image_rect(self, ic):
        return QRect(ic.pos.x() + (CELL_W - 32) // 2, ic.pos.y() + 2, 32, 32)

    def _label_layout(self, ic, font):
        fm = QFontMetrics(font)
        width = CELL_W - 4
        lines = []
        tl = QTextLayout(ic.label, font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        opt.setAlignment(Qt.AlignHCenter)
        tl.setTextOption(opt)
        tl.beginLayout()
        maxlines = 2 if not ic.selected else 5
        while True:
            line = tl.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            lines.append((line.textStart(), line.textLength()))
        tl.endLayout()
        texts = [ic.label[s:s + n].rstrip() for s, n in lines]
        if len(texts) > maxlines:
            rest = " ".join(texts[maxlines - 1:])
            texts = texts[:maxlines - 1] + [fm.elidedText(rest, Qt.ElideRight, width)]
        return texts

    def _label_rect(self, ic, font):
        fm = QFontMetrics(font)
        texts = self._label_layout(ic, font)
        w = max((fm.horizontalAdvance(t) for t in texts), default=10) + 4
        h = fm.height() * len(texts) + 2
        x = ic.pos.x() + (CELL_W - w) // 2
        return QRect(x, ic.pos.y() + 37, w, h), texts

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._background())
        t = current()
        font = t.font("icon")
        p.setFont(font)
        fm = QFontMetrics(font)
        hl = t.color("highlight")
        for ic in self.icons:
            if not self.icon_rect(ic).intersects(e.rect()):
                continue
            ir = self._icon_image_rect(ic)
            if ic.qicon is not None:
                pm = ic.qicon.pixmap(32, 32)
                if ic.shortcut:
                    p.drawPixmap(ir, pm)
                    p.drawPixmap(ir, iconcache.pixmap("shortcut_overlay", 32))
                else:
                    p.drawPixmap(ir, pm)
            else:
                p.drawPixmap(ir, iconcache.pixmap(ic.icon, 32, ic.shortcut))
            if ic.selected:
                tint = QColor(hl)
                tint.setAlpha(110)
                p.save()
                p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
                p.restore()
                # nakładka podświetlenia na ikonie
                mask = iconcache.pixmap(ic.icon or "file", 32)
                tinted = QPixmap(mask.size())
                tinted.fill(Qt.transparent)
                tp = QPainter(tinted)
                tp.drawPixmap(0, 0, mask if ic.qicon is None else ic.qicon.pixmap(32, 32))
                tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
                tp.fillRect(tinted.rect(), tint)
                tp.end()
                p.drawPixmap(ir, tinted)
            lr, texts = self._label_rect(ic, font)
            if ic.selected:
                p.fillRect(lr, hl)
                if self.hasFocus():
                    p.save()
                    from PySide6.QtGui import QPen
                    p.setPen(QPen(QColor("#ffffff"), 1, Qt.DotLine))
                    p.drawRect(lr.adjusted(0, 0, -1, -1))
                    p.restore()
            y = lr.top() + 1
            for line in texts:
                r = QRect(ic.pos.x(), y, CELL_W, fm.height())
                if not ic.selected:
                    p.setPen(QColor(0, 0, 0, 200))
                    p.drawText(r.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, line)
                p.setPen(QColor("#ffffff"))
                p.drawText(r, Qt.AlignHCenter | Qt.AlignTop, line)
                y += fm.height()
        if self._rubber is not None:
            r = self._rubber.normalized()
            c = QColor(hl)
            c.setAlpha(60)
            p.fillRect(r, c)
            from PySide6.QtGui import QPen
            p.setPen(QPen(hl, 1))
            p.drawRect(r.adjusted(0, 0, -1, -1))

    # ------------------------------------------------------------ trafienia
    def icon_at(self, pos):
        font = current().font("icon")
        for ic in reversed(self.icons):
            if self._icon_image_rect(ic).adjusted(-4, -2, 4, 2).contains(pos):
                return ic
            lr, _ = self._label_rect(ic, font)
            if lr.contains(pos):
                return ic
        return None

    def selected(self):
        return [i for i in self.icons if i.selected]

    def clear_selection(self):
        for i in self.icons:
            i.selected = False

    # ------------------------------------------------------------ mysz
    def mousePressEvent(self, e):
        if hasattr(self.shell, "hide_start"):
            self.shell.hide_start()
        self.setFocus()
        self._finish_edit()
        pos = e.position().toPoint()
        ic = self.icon_at(pos)
        mods = e.modifiers()
        if e.button() == Qt.LeftButton:
            if ic:
                if mods & Qt.ControlModifier:
                    ic.selected = not ic.selected
                elif not ic.selected:
                    self.clear_selection()
                    ic.selected = True
                self._press = pos
                self._press_icon = ic
                self._drag_started = False
            else:
                if not mods & Qt.ControlModifier:
                    self.clear_selection()
                self._rubber = QRect(pos, pos)
            self.update()
        elif e.button() == Qt.RightButton:
            if ic:
                if not ic.selected:
                    self.clear_selection()
                    ic.selected = True
                self.update()
                self.item_menu(ic, e.globalPosition().toPoint())
            else:
                self.clear_selection()
                self.update()
                self.background_menu(e.globalPosition().toPoint(), pos)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._rubber is not None:
            self._rubber.setBottomRight(pos)
            r = self._rubber.normalized()
            for ic in self.icons:
                ic.selected = r.intersects(self._icon_image_rect(ic)) or r.intersects(self._label_rect(ic, current().font("icon"))[0])
            self.update()
            return
        if self._press_icon and e.buttons() & Qt.LeftButton:
            if (pos - self._press).manhattanLength() > QApplication.startDragDistance():
                self._start_drag(pos)

    def _start_drag(self, pos):
        sel = self.selected()
        files = [i.path for i in sel if i.path]
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(f) for f in files])
        md.setData("application/x-horyzont-desktop-move", b"1")
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = iconcache.pixmap(self._press_icon.icon or "file", 32)
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(16, 16))
        self._drag_origin = self._press
        self._press_icon = None
        drag.exec(Qt.MoveAction | Qt.CopyAction | Qt.LinkAction, Qt.MoveAction)

    def mouseReleaseEvent(self, e):
        if self._rubber is not None:
            self._rubber = None
            self.update()
        elif self._press_icon and e.button() == Qt.LeftButton and not (e.modifiers() & Qt.ControlModifier):
            for i in self.icons:
                i.selected = i is self._press_icon
            self.update()
        self._press_icon = None

    def mouseDoubleClickEvent(self, e):
        ic = self.icon_at(e.position().toPoint())
        if ic and e.button() == Qt.LeftButton:
            self.open_icon(ic)

    # ------------------------------------------------------------ przeciąganie
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        pos = e.position().toPoint()
        if md.hasFormat("application/x-horyzont-desktop-move") and e.source() is self:
            target = self.icon_at(pos)
            sel = self.selected()
            if target and not target.selected and target.special == "recycle":
                self.delete_selected(ask=True)
                e.acceptProposedAction()
                return
            if target and not target.selected and target.path and os.path.isdir(target.path):
                fileops.copy_into([i.path for i in sel if i.path], target.path, move=True)
                e.acceptProposedAction()
                self.reload()
                return
            delta = pos - self._drag_origin
            for ic in sel:
                np = ic.pos + delta
                np.setX(max(0, min(self.width() - CELL_W, np.x())))
                np.setY(max(0, min(self.height() - CELL_H, np.y())))
                ic.pos = self._snap(np) if config.get("desktop_align_grid", True) else np
            config.set("desktop_auto_arrange", False)
            self.save_positions()
            self.update()
            e.setDropAction(Qt.MoveAction)
            e.accept()
            return
        files = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if not files:
            return
        target = self.icon_at(pos)
        if target and target.special == "recycle":
            fileops.trash_paths(files)
            e.acceptProposedAction()
            return
        dest = target.path if target and target.path and os.path.isdir(target.path) else self.desktop_dir
        move = e.dropAction() == Qt.MoveAction or (e.keyboardModifiers() & Qt.ShiftModifier)
        same_fs = all(os.stat(f).st_dev == os.stat(dest).st_dev for f in files if os.path.exists(f))
        if e.keyboardModifiers() & Qt.ControlModifier:
            move = False
        elif not e.keyboardModifiers():
            move = same_fs
        created, errors = fileops.copy_into(files, dest, move=move)
        if dest == self.desktop_dir and created:
            pos_map = dict(config.get("icon_positions", {}))
            for i, c in enumerate(created):
                pp = self._snap(pos + QPoint(0, i * CELL_H))
                pos_map["file:" + os.path.basename(c)] = [pp.x(), pp.y()]
            config.set("icon_positions", pos_map)
        e.acceptProposedAction()
        self.reload()

    # ------------------------------------------------------------ klawiatura
    def keyPressEvent(self, e):
        k = e.key()
        sel = self.selected()
        if k in (Qt.Key_Return, Qt.Key_Enter) and sel:
            for ic in sel:
                self.open_icon(ic)
        elif k == Qt.Key_Delete and sel:
            self.delete_selected(ask=True, permanent=bool(e.modifiers() & Qt.ShiftModifier))
        elif k == Qt.Key_F2 and len(sel) == 1:
            self.rename(sel[0])
        elif k == Qt.Key_F5:
            self.reload()
        elif k == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            for i in self.icons:
                i.selected = True
            self.update()
        elif k == Qt.Key_C and e.modifiers() & Qt.ControlModifier:
            self.copy_selected(cut=False)
        elif k == Qt.Key_X and e.modifiers() & Qt.ControlModifier:
            self.copy_selected(cut=True)
        elif k == Qt.Key_V and e.modifiers() & Qt.ControlModifier:
            self.paste()
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and self.icons:
            self._move_selection(k)
        else:
            super().keyPressEvent(e)

    def _move_selection(self, key):
        cur = self.selected()[0] if self.selected() else self.icons[0]
        best = None
        bd = None
        for ic in self.icons:
            if ic is cur:
                continue
            d = ic.pos - cur.pos
            ok = {Qt.Key_Left: d.x() < -10 and abs(d.y()) < CELL_H, Qt.Key_Right: d.x() > 10 and abs(d.y()) < CELL_H,
                  Qt.Key_Up: d.y() < -10 and abs(d.x()) < CELL_W, Qt.Key_Down: d.y() > 10 and abs(d.x()) < CELL_W}[key]
            if ok:
                dist = d.manhattanLength()
                if bd is None or dist < bd:
                    best, bd = ic, dist
        if best or not self.selected():
            self.clear_selection()
            (best or cur).selected = True
            self.update()

    # ------------------------------------------------------------ akcje
    def open_icon(self, ic):
        if ic.special == "computer":
            launcher.start_builtin("explorer", ["horyzont:computer"])
        elif ic.special == "documents":
            launcher.open_path(config.user_dir("DOCUMENTS"))
        elif ic.special == "network":
            launcher.start_builtin("explorer", ["horyzont:network"])
        elif ic.special == "recycle":
            launcher.start_builtin("explorer", ["horyzont:recycle"])
        elif ic.path:
            if ic.entry is not None and ic.path.endswith(".desktop"):
                if ic.entry.type == "Link":
                    self._open_link(ic.path)
                else:
                    launcher.launch_entry(ic.entry)
            else:
                launcher.open_path(ic.path)

    def _open_link(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("URL="):
                        url = line[4:].strip()
                        if url.startswith("file://"):
                            launcher.open_path(urllib.parse.unquote(url[7:]))
                        else:
                            launcher.xdg_open(url)
                        return
        except OSError:
            pass

    def delete_selected(self, ask=True, permanent=False):
        items = [i for i in self.selected() if i.path]
        specials = [i for i in self.selected() if i.special]
        if specials and not items:
            # usuwanie ikon specjalnych chowa je z pulpitu
            keys = list(config.get("desktop_icons", []))
            for s in specials:
                if s.special in keys and s.special != "recycle":
                    keys.remove(s.special)
            config.set("desktop_icons", keys)
            return
        if not items:
            return
        if ask:
            if permanent:
                text = tr("confirm_delete_perm", items[0].label) if len(items) == 1 else tr("confirm_delete_many", len(items))
            else:
                text = tr("confirm_delete_one", items[0].label) if len(items) == 1 else tr("confirm_delete_many", len(items))
            if dialogs.message(self, plain("confirm_delete_title"), text, "recycle_full" if not permanent else "warning",
                               ("yes", "no")) != "yes":
                return
        paths = [i.path for i in items]
        errors = fileops.delete_permanently(paths) if permanent else fileops.trash_paths(paths)
        if errors:
            dialogs.message(self, plain("error"), "\n".join(f"{os.path.basename(p)}: {m}" for p, m in errors[:5]), "error")
        self.reload()

    def copy_selected(self, cut=False):
        paths = [i.path for i in self.selected() if i.path]
        if paths:
            fileops.set_clipboard(paths, cut)

    def paste(self, at=None):
        paths, cut = fileops.get_clipboard()
        if not paths:
            return
        created, errors = fileops.copy_into(paths, self.desktop_dir, move=cut)
        if cut:
            QApplication.clipboard().clear()
        if at is not None and created:
            pos_map = dict(config.get("icon_positions", {}))
            for i, c in enumerate(created):
                pp = self._snap(at + QPoint(0, i * CELL_H))
                pos_map["file:" + os.path.basename(c)] = [pp.x(), pp.y()]
            config.set("icon_positions", pos_map)
        self.reload()

    def rename(self, ic):
        if not ic.path:
            return
        font = current().font("icon")
        lr, _ = self._label_rect(ic, font)
        ed = QLineEdit(self)
        ed.setText(os.path.basename(ic.path))
        ed.setFont(font)
        ed.setAlignment(Qt.AlignCenter)
        ed.setGeometry(ic.pos.x() - 6, lr.top() - 1, CELL_W + 12, max(lr.height(), 20) + 2)
        base, ext = os.path.splitext(ed.text())
        ed.setSelection(0, len(base) if base and not os.path.isdir(ic.path) else len(ed.text()))
        ed.show()
        ed.setFocus()
        self._editor = (ed, ic)
        ed.returnPressed.connect(self._finish_edit)
        ed.editingFinished.connect(self._finish_edit)

    def _finish_edit(self):
        if not self._editor:
            return
        ed, ic = self._editor
        self._editor = None
        new = ed.text().strip()
        ed.deleteLater()
        if new and new != os.path.basename(ic.path) and "/" not in new:
            dest = os.path.join(os.path.dirname(ic.path), new)
            if os.path.exists(dest):
                dialogs.message(self, plain("error"), tr("rename_fail", os.path.basename(ic.path), new), "error")
            else:
                try:
                    os.rename(ic.path, dest)
                    pos = dict(config.get("icon_positions", {}))
                    pos["file:" + new] = [ic.pos.x(), ic.pos.y()]
                    config.set("icon_positions", pos)
                except OSError as e:
                    dialogs.message(self, plain("error"), tr("rename_fail", os.path.basename(ic.path), str(e)), "error")
        self.setFocus()
        self.reload()

    # ------------------------------------------------------------ menu
    def background_menu(self, gpos, pos):
        m = QMenu(self)
        arr = m.addMenu(tr("desk_arrange"))
        for how, key in (("name", "desk_arrange_name"), ("size", "desk_arrange_size"),
                         ("type", "desk_arrange_type"), ("modified", "desk_arrange_modified")):
            arr.addAction(tr(key)).triggered.connect(lambda _=False, h=how: self.arrange_by(h))
        arr.addSeparator()
        aa = arr.addAction(tr("desk_auto_arrange"))
        aa.setCheckable(True)
        aa.setChecked(config.get("desktop_auto_arrange", False))
        aa.toggled.connect(lambda v: (config.set("desktop_auto_arrange", v), v and config.set("icon_positions", {}),
                                      self.reload()))
        ag = arr.addAction(tr("desk_align_grid"))
        ag.setCheckable(True)
        ag.setChecked(config.get("desktop_align_grid", True))
        ag.toggled.connect(lambda v: config.set("desktop_align_grid", v))
        arr.addSeparator()
        si = arr.addAction(tr("desk_show_icons"))
        si.setCheckable(True)
        si.setChecked(config.get("desktop_show_icons", True))
        si.toggled.connect(lambda v: config.set("desktop_show_icons", v))
        m.addAction(tr("desk_refresh")).triggered.connect(self.reload)
        m.addSeparator()
        pa = m.addAction(tr("desk_paste"))
        pa.setEnabled(fileops.clipboard_has_files())
        pa.triggered.connect(lambda: self.paste(pos))
        ps = m.addAction(tr("desk_paste_shortcut"))
        ps.setEnabled(fileops.clipboard_has_files())
        ps.triggered.connect(self._paste_shortcut)
        m.addSeparator()
        new = m.addMenu(tr("desk_new"))
        new.addAction(iconcache.icon("folder"), tr("new_folder")).triggered.connect(lambda: self._new("folder", pos))
        new.addAction(iconcache.icon("shortcut_overlay"), tr("new_shortcut")).triggered.connect(lambda: self._new("shortcut", pos))
        new.addSeparator()
        new.addAction(iconcache.icon("file_text"), plain("new_text")).triggered.connect(lambda: self._new("text", pos))
        tpl = os.path.expanduser("~/Templates")
        if os.path.isdir(tpl):
            for fn in sorted(os.listdir(tpl)):
                fp = os.path.join(tpl, fn)
                if os.path.isfile(fp):
                    new.addAction(iconcache.icon(iconcache.name_for_file(fp)), os.path.splitext(fn)[0]).triggered.connect(
                        lambda _=False, fp=fp: self._new_from_template(fp, pos))
        m.addSeparator()
        m.addAction(tr("desk_properties")).triggered.connect(lambda: launcher.start_builtin("control", ["display"]))
        m.exec(gpos)

    def _paste_shortcut(self):
        paths, _ = fileops.get_clipboard()
        for p in paths:
            fileops.new_shortcut(self.desktop_dir, p)
        self.reload()

    def _place_new(self, path, pos):
        pp = self._snap(pos)
        pos_map = dict(config.get("icon_positions", {}))
        pos_map["file:" + os.path.basename(path)] = [pp.x(), pp.y()]
        config.set("icon_positions", pos_map)
        self.reload()
        for ic in self.icons:
            if ic.path == path:
                self.clear_selection()
                ic.selected = True
                self.rename(ic)
                break

    def _new(self, kind, pos):
        try:
            if kind == "folder":
                path = fileops.new_folder(self.desktop_dir)
            elif kind == "text":
                path = fileops.new_text_document(self.desktop_dir)
            else:
                target = dialogs.ask_text(self, plain("new_shortcut"), plain("location"), os.path.expanduser("~"))
                if not target:
                    return
                path = fileops.new_shortcut(self.desktop_dir, os.path.expanduser(target))
        except OSError as e:
            dialogs.message(self, plain("error"), str(e), "error")
            return
        self._place_new(path, pos)

    def _new_from_template(self, src, pos):
        import shutil
        name = fileops.unique_name(self.desktop_dir, os.path.basename(src))
        dest = os.path.join(self.desktop_dir, name)
        shutil.copy2(src, dest)
        self._place_new(dest, pos)

    def item_menu(self, ic, gpos):
        m = QMenu(self)
        sel = self.selected()

        def bold(a):
            f = a.font()
            f.setBold(True)
            a.setFont(f)
            return a

        if ic.special:
            bold(m.addAction(tr("open"))).triggered.connect(lambda: self.open_icon(ic))
            if ic.special in ("computer", "documents", "recycle"):
                m.addAction(tr("explore")).triggered.connect(lambda: self.open_icon(ic))
            if ic.special in ("computer", "documents"):
                m.addAction(tr("search_dots")).triggered.connect(lambda: launcher.start_builtin("explorer", ["--search"]))
            if ic.special == "computer":
                m.addSeparator()
                m.addAction(tr("manage")).triggered.connect(lambda: launcher.start_builtin("control", ["admin"]))
            if ic.special == "recycle":
                m.addSeparator()
                eb = m.addAction(tr("empty_bin"))
                eb.setEnabled(fileops.trash_count() > 0)
                eb.triggered.connect(self.empty_bin)
            m.addSeparator()
            if ic.special != "recycle":
                m.addAction(tr("delete")).triggered.connect(lambda: self.delete_selected(ask=False))
            m.addSeparator()
            props = {"computer": ["system"], "recycle": None, "documents": None, "network": ["network"]}[ic.special]

            def show_props():
                if props:
                    launcher.start_builtin("control", props)
                elif ic.special == "documents":
                    launcher.start_builtin("explorer", ["--properties", config.user_dir("DOCUMENTS")])
                else:
                    launcher.start_builtin("explorer", ["horyzont:recycle"])
            m.addAction(tr("properties")).triggered.connect(show_props)
            m.exec(gpos)
            return
        bold(m.addAction(tr("open"))).triggered.connect(lambda: [self.open_icon(i) for i in sel])
        if ic.path and os.path.isdir(ic.path):
            m.addAction(tr("explore")).triggered.connect(lambda: launcher.open_path(ic.path))
        elif ic.path and not ic.path.endswith(".desktop"):
            ow = m.addMenu(tr("open_with"))
            self._fill_open_with(ow, ic.path)
        m.addSeparator()
        st = m.addMenu(tr("send_to"))
        st.addAction(iconcache.icon("documents"), plain("my_documents")).triggered.connect(
            lambda: fileops.copy_into([i.path for i in sel if i.path], config.user_dir("DOCUMENTS")))
        st.addAction(iconcache.icon("desktop_folder"), plain("create_shortcut")).triggered.connect(self._paste_shortcut_from_sel)
        m.addSeparator()
        m.addAction(tr("cut")).triggered.connect(lambda: self.copy_selected(True))
        m.addAction(tr("copy")).triggered.connect(lambda: self.copy_selected(False))
        m.addSeparator()
        m.addAction(tr("create_shortcut")).triggered.connect(self._paste_shortcut_from_sel)
        m.addAction(tr("delete")).triggered.connect(lambda: self.delete_selected(ask=True))
        rn = m.addAction(tr("rename"))
        rn.setEnabled(len(sel) == 1)
        rn.triggered.connect(lambda: self.rename(ic))
        m.addSeparator()
        m.addAction(tr("properties")).triggered.connect(
            lambda: launcher.start_builtin("explorer", ["--properties"] + [i.path for i in sel if i.path]))
        m.exec(gpos)

    def _paste_shortcut_from_sel(self):
        for i in self.selected():
            if i.path:
                fileops.new_shortcut(self.desktop_dir, i.path, os.path.splitext(os.path.basename(i.path))[0])
        self.reload()

    def _fill_open_with(self, menu, path):
        import mimetypes
        mt, _ = mimetypes.guess_type(path)
        added = 0
        menu.addAction(iconcache.icon("notepad"), plain("notepad")).triggered.connect(
            lambda: launcher.start_builtin("notepad", [path]))
        if mt:
            for e in desktopentry.all_entries().values():
                if not e.visible():
                    continue
                try:
                    with open(e.path, encoding="utf-8", errors="ignore") as f:
                        data = f.read()
                except OSError:
                    continue
                if f"MimeType=" in data and (mt in data or mt.split("/")[0] + "/*" in data):
                    menu.addAction(iconcache.theme_or_builtin(e.icon, "app"), e.name).triggered.connect(
                        lambda _=False, e=e: launcher.open_path(path, with_entry=e))
                    added += 1
                    if added > 12:
                        break

    def empty_bin(self):
        n = fileops.trash_count()
        if n and dialogs.message(self, plain("recycle_bin"), tr("confirm_empty_bin", n), "recycle_full", ("yes", "no")) == "yes":
            fileops.trash_empty()
            self.reload()
