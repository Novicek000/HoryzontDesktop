"""Widoki Eksploratora: Miniatury, Kafelki, Ikony, Lista, Szczegóły."""
import os

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFontMetrics, QPainter, QPen, QPixmap,
                           QTextLayout, QTextOption)
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QListView,
                               QStackedWidget, QStyle, QStyledItemDelegate,
                               QTreeView)

from ...theme import iconcache
from ...theme.base import hgrad
from ...theme.manager import current
from .model import IMAGE_EXT, HeaderRole, IconNameRole, ItemRole


def _wrap_lines(text, font, width, maxlines):
    fm = QFontMetrics(font)
    tl = QTextLayout(text, font)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    tl.setTextOption(opt)
    tl.beginLayout()
    lines = []
    while True:
        line = tl.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        lines.append(text[line.textStart():line.textStart() + line.textLength()].rstrip())
    tl.endLayout()
    if len(lines) > maxlines:
        rest = " ".join(lines[maxlines - 1:])
        lines = lines[:maxlines - 1] + [fm.elidedText(rest, Qt.ElideRight, width)]
    return lines or [""]


def _tinted(pm, color):
    out = QPixmap(pm.size())
    out.setDevicePixelRatio(pm.devicePixelRatio())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
    c = QColor(color)
    c.setAlpha(110)
    p.fillRect(out.rect(), c)
    p.end()
    return out


class ExplorerDelegate(QStyledItemDelegate):
    def __init__(self, view, mode="tiles"):
        super().__init__(view)
        self.view = view
        self.mode = mode
        self.thumbs = None

    def _icon(self, index, size):
        it = index.data(ItemRole)
        if it is None:
            return QPixmap()
        if self.mode == "thumbnails" and self.thumbs is not None and not it.is_dir \
                and os.path.splitext(it.path)[1].lower() in IMAGE_EXT:
            pm = self.thumbs.get(it.path)
            if pm:
                return pm
        if it.qicon is not None:
            return it.qicon.pixmap(size, size)
        return iconcache.pixmap(it.icon, size, it.kind == "link")

    def header_size(self):
        w = max(200, self.view.viewport().width() - 14)
        return QSize(w, 30)

    def sizeHint(self, option, index):
        if index.data(HeaderRole):
            return self.header_size()
        fm = QFontMetrics(current().font("normal"))
        if self.mode == "tiles":
            return QSize(250, 58)
        if self.mode == "icons":
            return QSize(78, 74)
        if self.mode == "thumbnails":
            return QSize(118, 134)
        if self.mode == "list":
            it = index.data(ItemRole)
            w = min(260, fm.horizontalAdvance(it.label if it else "") + 26)
            return QSize(max(80, w), 18)
        return super().sizeHint(option, index)

    def paint(self, p, option, index):
        if index.data(HeaderRole):
            self._paint_header(p, option, index)
            return
        if self.mode == "tiles":
            self._paint_tile(p, option, index)
        elif self.mode == "icons":
            self._paint_icon(p, option, index, 32)
        elif self.mode == "thumbnails":
            self._paint_thumb(p, option, index)
        elif self.mode == "list":
            self._paint_list(p, option, index)
        else:
            super().paint(p, option, index)

    def _colors(self, option):
        t = current()
        selected = bool(option.state & QStyle.State_Selected)
        focus = self.view.hasFocus()
        hl = t.color("highlight") if focus else QColor("#d8dddc")
        text = t.color("highlight_text") if (selected and focus) else QColor("#000000")
        return selected, hl, text

    def _paint_header(self, p, option, index):
        t = current()
        r = option.rect
        f = t.font("normal")
        f.setBold(True)
        p.setFont(f)
        p.setPen(t.color("group_title"))
        p.drawText(r.adjusted(2, 0, 0, -6), Qt.AlignLeft | Qt.AlignBottom, index.data(Qt.DisplayRole))
        line = QRect(r.left(), r.bottom() - 3, r.width() - 20, 2)
        col = t.color("group_title").lighter(150).name()
        p.fillRect(line, hgrad(line, [(0, col), (0.6, col), (1, "#ffffff00")]))

    def _paint_tile(self, p, option, index):
        selected, hl, text_col = self._colors(option)
        r = option.rect
        it = index.data(ItemRole)
        pm = self._icon(index, 48)
        ir = QRect(r.left() + 4, r.top() + (r.height() - 48) // 2, 48, 48)
        p.drawPixmap(ir, _tinted(pm, hl) if selected else pm)
        f = current().font("normal")
        fm = QFontMetrics(f)
        tx = ir.right() + 6
        tw = r.right() - tx - 4
        lines = [it.label]
        sub = []
        if it.kind == "drive":
            if it.extra.get("empty"):
                sub = [it.type_name]
            else:
                sub = [it.type_name, f"{it.extra.get('free', '')} / {it.extra.get('total', '')}"]
        elif it.is_dir:
            sub = [it.type_name]
        elif it.kind == "special":
            sub = [x for x in (it.type_name, it.extra.get("info", "")) if x]
        else:
            from ...common import sysctl
            sub = [it.type_name, sysctl.human_size(it.size)]
        total_h = fm.height() * (1 + len(sub))
        y = r.top() + (r.height() - total_h) // 2
        name_w = min(tw, fm.horizontalAdvance(it.label) + 4)
        nr = QRect(tx, y, name_w, fm.height())
        if selected:
            p.fillRect(nr, hl)
        p.setFont(f)
        p.setPen(text_col if selected else QColor("#000000"))
        p.drawText(nr.adjusted(2, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(it.label, Qt.ElideRight, tw - 4))
        p.setPen(QColor("#7b7f81"))
        for s in sub:
            y += fm.height()
            p.drawText(QRect(tx + 2, y, tw, fm.height()), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(s, Qt.ElideRight, tw))
        if it.kind == "drive" and it.extra.get("total_b"):
            # pasek zajętości dysku
            used = 1 - it.extra["free_b"] / max(1, it.extra["total_b"])
            br = QRect(tx + 2, y + fm.height() + 1, min(140, tw - 4), 6)
            if br.bottom() < r.bottom():
                current().draw_progress_track(p, br)
                p.fillRect(QRect(br.left() + 1, br.top() + 1, int((br.width() - 2) * used), br.height() - 2),
                           current().color("highlight") if used < 0.9 else QColor("#c0392b"))

    def _paint_icon(self, p, option, index, size):
        selected, hl, text_col = self._colors(option)
        r = option.rect
        it = index.data(ItemRole)
        pm = self._icon(index, size)
        ir = QRect(r.left() + (r.width() - size) // 2, r.top() + 2, size, size)
        p.drawPixmap(ir, _tinted(pm, hl) if selected else pm)
        f = current().font("normal")
        fm = QFontMetrics(f)
        lines = _wrap_lines(it.label, f, r.width() - 4, 5 if selected else 2)
        w = max(fm.horizontalAdvance(l) for l in lines) + 4
        tr_ = QRect(r.left() + (r.width() - w) // 2, ir.bottom() + 3, w, fm.height() * len(lines) + 1)
        if selected:
            p.fillRect(tr_, hl)
        if option.state & QStyle.State_HasFocus and self.view.hasFocus():
            p.save()
            p.setPen(QPen(QColor("#000000") if not selected else QColor("#ffffff"), 1, Qt.DotLine))
            p.drawRect(tr_.adjusted(0, 0, -1, -1))
            p.restore()
        p.setFont(f)
        p.setPen(text_col)
        y = tr_.top()
        for l in lines:
            p.drawText(QRect(r.left(), y, r.width(), fm.height()), Qt.AlignHCenter | Qt.AlignTop, l)
            y += fm.height()

    def _paint_thumb(self, p, option, index):
        selected, hl, text_col = self._colors(option)
        r = option.rect
        it = index.data(ItemRole)
        box = QRect(r.left() + (r.width() - 100) // 2, r.top() + 3, 100, 100)
        p.fillRect(box, QColor("#ffffff"))
        p.setPen(QPen(hl if selected else QColor("#cfd6d5"), 2 if selected else 1))
        p.drawRect(box.adjusted(0, 0, -1, -1))
        is_img = not it.is_dir and os.path.splitext(it.path)[1].lower() in IMAGE_EXT
        pm = self._icon(index, 96 if is_img else 48)
        if pm.width() > 96 or pm.height() > 96:
            pm = pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        w = int(pm.width() / max(1, pm.devicePixelRatio()))
        h = int(pm.height() / max(1, pm.devicePixelRatio()))
        p.drawPixmap(box.left() + (box.width() - w) // 2, box.top() + (box.height() - h) // 2, pm)
        f = current().font("normal")
        fm = QFontMetrics(f)
        text = fm.elidedText(it.label, Qt.ElideRight, r.width() - 6)
        tw = fm.horizontalAdvance(text) + 6
        tr_ = QRect(r.left() + (r.width() - tw) // 2, box.bottom() + 5, tw, fm.height() + 2)
        if selected:
            p.fillRect(tr_, hl)
        p.setFont(f)
        p.setPen(text_col)
        p.drawText(tr_, Qt.AlignCenter, text)

    def _paint_list(self, p, option, index):
        selected, hl, text_col = self._colors(option)
        r = option.rect
        it = index.data(ItemRole)
        pm = self._icon(index, 16)
        p.drawPixmap(r.left() + 2, r.top() + (r.height() - 16) // 2, _tinted(pm, hl) if selected else pm)
        f = current().font("normal")
        fm = QFontMetrics(f)
        text = fm.elidedText(it.label, Qt.ElideRight, r.width() - 24)
        tr_ = QRect(r.left() + 20, r.top() + 1, fm.horizontalAdvance(text) + 4, r.height() - 2)
        if selected:
            p.fillRect(tr_, hl)
        p.setFont(f)
        p.setPen(text_col)
        p.drawText(tr_.adjusted(2, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

    def updateEditorGeometry(self, editor, option, index):
        r = option.rect
        if self.mode == "icons":
            editor.setGeometry(QRect(r.left() - 4, r.top() + 37, r.width() + 8, 20))
        elif self.mode == "tiles":
            editor.setGeometry(QRect(r.left() + 56, r.top() + 8, r.width() - 60, 20))
        elif self.mode == "thumbnails":
            editor.setGeometry(QRect(r.left(), r.top() + 106, r.width(), 20))
        elif self.mode == "list":
            editor.setGeometry(QRect(r.left() + 18, r.top(), max(140, r.width() - 18), r.height()))
        else:
            super().updateEditorGeometry(editor, option, index)


class _DropMixin:
    def _setup_dnd(self):
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            return super().dropEvent(e)
        idx = self.indexAt(e.position().toPoint())
        target = None
        it = idx.data(ItemRole) if idx.isValid() else None
        if it is not None and (it.is_dir or it.kind == "drive") and it.path:
            target = it.path
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if target in paths:
            target = None
        mods = e.modifiers()
        self.files_dropped.emit(paths, target or "", int(mods.value) if hasattr(mods, "value") else int(mods))
        e.setDropAction(Qt.CopyAction)
        e.accept()


class ExplorerListView(_DropMixin, QListView):
    files_dropped = Signal(list, str, int)

    def __init__(self, parent=None):
        QListView.__init__(self, parent)
        self.delegate = ExplorerDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(False)
        self.setFrameShape(QListView.NoFrame)
        self.setMouseTracking(True)
        self._setup_dnd()
        self.set_mode("tiles")

    def set_mode(self, mode):
        self.delegate.mode = mode
        if mode == "list":
            self.setViewMode(QListView.ListMode)
            self.setFlow(QListView.TopToBottom)
            self.setWrapping(True)
            self.setSpacing(1)
            self.setGridSize(QSize())
        else:
            self.setViewMode(QListView.IconMode)
            self.setFlow(QListView.LeftToRight)
            self.setWrapping(True)
            self.setGridSize(QSize())
            self.setSpacing({"tiles": 4, "icons": 2, "thumbnails": 6}.get(mode, 4))
        self.setMovement(QListView.Static)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.doItemsLayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        m = self.model()
        if m is not None and any(getattr(i, "header", False) for i in getattr(m, "items", [])):
            self.doItemsLayout()


class ExplorerTreeView(_DropMixin, QTreeView):
    files_dropped = Signal(list, str, int)

    def __init__(self, parent=None):
        QTreeView.__init__(self, parent)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        self.setFrameShape(QTreeView.NoFrame)
        self.setIconSize(QSize(16, 16))
        self.header().setStretchLastSection(False)
        self.header().setSectionsMovable(True)
        self.header().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._setup_dnd()

    def setModel(self, m):
        super().setModel(m)
        if m is None:
            return
        widths = {"name": 220, "size": 80, "type": 140, "modified": 120, "orig": 200, "deleted": 120,
                  "folder": 240, "total": 90, "free": 90, "fs": 80}
        for i, c in enumerate(getattr(m, "columns", [])):
            self.setColumnWidth(i, widths.get(c, 100))
        self.sortByColumn(m.sort_col, m.sort_order)


class ViewStack(QStackedWidget):
    """Przełącza między widokiem listowym (ikony/kafelki/lista/miniatury) a szczegółami."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list = ExplorerListView(self)
        self.tree = ExplorerTreeView(self)
        self.addWidget(self.list)
        self.addWidget(self.tree)
        self.mode = "tiles"
        self._model = None

    def set_model(self, m):
        self._model = m
        self.list.setModel(m)
        self.tree.setModel(m)

    def set_mode(self, mode):
        self.mode = mode
        if mode == "details":
            self.setCurrentWidget(self.tree)
        else:
            self.list.set_mode(mode)
            self.setCurrentWidget(self.list)

    def view(self):
        return self.currentWidget()

    def selected_items(self):
        v = self.view()
        sm = v.selectionModel()
        if sm is None:
            return []
        rows = sorted({i.row() for i in sm.selectedIndexes()})
        return [self._model.items[r] for r in rows if r < len(self._model.items) and not self._model.items[r].header]

    def current_index(self):
        return self.view().currentIndex()

    def select_path(self, path, edit=False):
        idx = self._model.index_of_path(path)
        if idx.isValid():
            v = self.view()
            v.setCurrentIndex(idx)
            v.scrollTo(idx)
            if edit:
                v.edit(idx)
