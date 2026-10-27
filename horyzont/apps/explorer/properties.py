"""Okno właściwości plików, folderów i dysków."""
import datetime
import os
import stat

from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialogButtonBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ...common import desktopentry, dialogs, fileops, launcher, sysctl
from ...common.window import HDialog
from ...i18n import plain, tr
from ...theme import iconcache
from .model import type_name_for


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #c8d0cf;")
    return f


def _fmt_dt(ts):
    if not ts:
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d, %H:%M:%S")


class _SizeWorker(QThread):
    result = Signal(int, int, int)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        files = folders = total = 0
        for p in self.paths:
            if os.path.isdir(p) and not os.path.islink(p):
                f, d, t = fileops.count_contents(p)
                files += f
                folders += d + 1
                total += t
            else:
                files += 1
                try:
                    total += os.lstat(p).st_size
                except OSError:
                    pass
        self.result.emit(files, folders, total)


class PiePanel(QWidget):
    def __init__(self, used, free, parent=None):
        super().__init__(parent)
        self.used, self.free = used, free
        self.setMinimumSize(140, 110)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        total = max(1, self.used + self.free)
        w = min(self.width() - 20, 150)
        h = w * 0.45
        x = (self.width() - w) / 2
        y = 10
        depth = 14
        ang = int(360 * 16 * self.used / total)
        used_c, free_c = QColor("#2a73b8"), QColor("#d64fd4")
        # boki "3D"
        for i in range(depth, 0, -1):
            r = QRectF(x, y + i, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(used_c.darker(150))
            p.drawPie(r, 90 * 16, -ang)
            p.setBrush(free_c.darker(150))
            p.drawPie(r, 90 * 16 - ang, -(360 * 16 - ang))
        r = QRectF(x, y, w, h)
        p.setPen(QPen(QColor("#333"), 0.6))
        p.setBrush(used_c)
        p.drawPie(r, 90 * 16, -ang)
        p.setBrush(free_c)
        p.drawPie(r, 90 * 16 - ang, -(360 * 16 - ang))


class PropertiesDialog(HDialog):
    def __init__(self, paths, parent=None):
        self.paths = [os.path.abspath(p) for p in paths]
        first = self.paths[0]
        if len(self.paths) == 1:
            title = tr("prop_title", os.path.basename(first.rstrip("/")) or first)
        else:
            names = [os.path.basename(x.rstrip("/")) for x in self.paths]
            title = tr("prop_title", ", ".join(names[:2]) + ", ...")
        super().__init__(title, iconcache.name_for_file(first), parent, help_button=True)
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.is_drive = len(self.paths) == 1 and os.path.ismount(first)
        self.tabs.addTab(self._general(), plain("general"))
        if len(self.paths) == 1 and not self.is_drive:
            self.tabs.addTab(self._permissions(), plain("prop_permissions"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        lay.addWidget(bb)
        self.resize(370, 470)

    # ------------------------------------------------------------ zakładka Ogólne
    def _general(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(12, 14, 12, 12)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(7)
        first = self.paths[0]
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("drive_hdd" if self.is_drive else iconcache.name_for_file(first), 32))
        g.addWidget(ic, 0, 0)
        self.name_edit = QLineEdit(os.path.basename(first.rstrip("/")) if len(self.paths) == 1 else "")
        self.name_edit.setEnabled(len(self.paths) == 1 and not self.is_drive)
        g.addWidget(self.name_edit, 0, 1, 1, 2)
        row = 1
        g.addWidget(_sep(), row, 0, 1, 3)
        row += 1

        def add(label, value):
            nonlocal row
            l = QLabel(label)
            v = QLabel(value)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setWordWrap(True)
            g.addWidget(l, row, 0)
            g.addWidget(v, row, 1, 1, 2)
            row += 1
            return v

        if self.is_drive:
            import psutil
            u = psutil.disk_usage(first)
            fs = ""
            for p in psutil.disk_partitions(all=True):
                if p.mountpoint == first:
                    fs = p.fstype.upper()
            add(plain("type"), plain("local_disk"))
            add(plain("file_system"), fs)
            g.addWidget(_sep(), row, 0, 1, 3)
            row += 1
            add(plain("used_space"), f"{sysctl.group_digits(u.used)} {plain('bytes')}   {sysctl.human_size(u.used)}")
            add(plain("free_space_c"), f"{sysctl.group_digits(u.free)} {plain('bytes')}   {sysctl.human_size(u.free)}")
            g.addWidget(_sep(), row, 0, 1, 3)
            row += 1
            add(plain("capacity"), f"{sysctl.group_digits(u.total)} {plain('bytes')}   {sysctl.human_size(u.total)}")
            g.addWidget(PiePanel(u.used, u.free), row, 0, 1, 3)
            row += 1
            lbl = QLabel(tr("drive_x", first))
            lbl.setAlignment(Qt.AlignCenter)
            g.addWidget(lbl, row, 0, 1, 3)
            row += 1
            g.setRowStretch(row, 1)
            return w

        single = len(self.paths) == 1
        st = None
        try:
            st = os.lstat(first)
        except OSError:
            pass
        is_dir = single and os.path.isdir(first)
        if single:
            add(plain("type_of_file") if not is_dir else plain("type"), type_name_for(first, is_dir))
            if not is_dir:
                e = self._default_app(first)
                if e:
                    add(plain("opens_with"), e)
            g.addWidget(_sep(), row, 0, 1, 3)
            row += 1
            add(plain("location"), os.path.dirname(first))
        else:
            add(plain("type"), plain("prop_multiple_types"))
            add(plain("location"), os.path.dirname(first))
        self.size_lbl = add(plain("size").rstrip(":") + ":", "…")
        self.disk_lbl = add(plain("size_on_disk"), "…")
        if is_dir or not single:
            self.contains_lbl = add(plain("contains"), "…")
        else:
            self.contains_lbl = None
        self._worker = _SizeWorker(self.paths)
        self._worker.result.connect(self._sizes)
        self._worker.start()
        if single and st:
            g.addWidget(_sep(), row, 0, 1, 3)
            row += 1
            try:
                ctime = os.stat(first).st_birthtime  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                ctime = st.st_ctime
            add(plain("created"), _fmt_dt(ctime))
            add(plain("modified_c"), _fmt_dt(st.st_mtime))
            add(plain("accessed"), _fmt_dt(st.st_atime))
            g.addWidget(_sep(), row, 0, 1, 3)
            row += 1
            g.addWidget(QLabel(plain("attributes")), row, 0)
            self.ro = QCheckBox(plain("read_only"))
            self.ro.setChecked(not os.access(first, os.W_OK))
            self.hid = QCheckBox(plain("hidden"))
            self.hid.setChecked(os.path.basename(first).startswith("."))
            g.addWidget(self.ro, row, 1)
            g.addWidget(self.hid, row, 2)
            row += 1
        g.setRowStretch(row, 1)
        return w

    def _default_app(self, path):
        import mimetypes
        ext = os.path.splitext(path)[1].lower()
        if ext in launcher.NOTEPAD_EXT:
            return plain("notepad")
        mt, _ = mimetypes.guess_type(path)
        if mt:
            e = desktopentry.all_entries().get(desktopentry.default_for_mime(mt))
            if e:
                return e.name
        return None

    def _sizes(self, files, folders, total):
        self.size_lbl.setText(f"{sysctl.human_size(total)} ({sysctl.group_digits(total)} {plain('bytes')})")
        disk = 0
        for p in self.paths:
            try:
                if os.path.isdir(p):
                    for root, dirs, fs in os.walk(p):
                        for f in fs:
                            try:
                                disk += os.lstat(os.path.join(root, f)).st_blocks * 512
                            except OSError:
                                pass
                else:
                    disk += os.lstat(p).st_blocks * 512
            except OSError:
                pass
        self.disk_lbl.setText(f"{sysctl.human_size(disk)} ({sysctl.group_digits(disk)} {plain('bytes')})")
        if self.contains_lbl is not None:
            nfold = folders - (1 if len(self.paths) == 1 and os.path.isdir(self.paths[0]) else 0)
            self.contains_lbl.setText(tr("n_files_folders", sysctl.group_digits(files), sysctl.group_digits(max(0, nfold))))

    # ------------------------------------------------------------ uprawnienia
    def _permissions(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(12, 14, 12, 12)
        first = self.paths[0]
        try:
            st = os.stat(first)
        except OSError:
            return w
        import grp
        import pwd
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        try:
            group = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            group = str(st.st_gid)
        g.addWidget(QLabel(plain("prop_owner")), 0, 0)
        g.addWidget(QLabel(owner), 0, 1)
        g.addWidget(QLabel(plain("prop_group")), 1, 0)
        g.addWidget(QLabel(group), 1, 1)
        heads = [plain("prop_read"), plain("prop_write"), plain("prop_exec")]
        for i, h in enumerate(heads):
            g.addWidget(QLabel(h), 2, 1 + i)
        self.perm_boxes = {}
        mode = st.st_mode
        bits = [(plain("prop_owner"), (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)),
                (plain("prop_group"), (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP)),
                (plain("prop_others"), (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH))]
        for r, (label, bs) in enumerate(bits):
            g.addWidget(QLabel(label), 3 + r, 0)
            for c, b in enumerate(bs):
                cb = QCheckBox()
                cb.setChecked(bool(mode & b))
                cb.setEnabled(st.st_uid == os.getuid())
                g.addWidget(cb, 3 + r, 1 + c)
                self.perm_boxes[b] = cb
        g.setRowStretch(7, 1)
        return w

    # ------------------------------------------------------------ zapis
    def _apply(self):
        if len(self.paths) != 1 or self.is_drive:
            return True
        p = self.paths[0]
        new = self.name_edit.text().strip()
        if new and new != os.path.basename(p) and "/" not in new:
            dest = os.path.join(os.path.dirname(p), new)
            try:
                if os.path.exists(dest):
                    raise OSError(tr("rename_fail", os.path.basename(p), new))
                os.rename(p, dest)
                self.paths[0] = p = dest
            except OSError as e:
                dialogs.message(self, plain("error"), str(e), "error")
                return False
        if getattr(self, "perm_boxes", None):
            mode = 0
            for b, cb in self.perm_boxes.items():
                if cb.isChecked():
                    mode |= b
            try:
                st = os.stat(p)
                os.chmod(p, (st.st_mode & ~0o777) | mode)
            except OSError:
                pass
        if hasattr(self, "ro"):
            try:
                st = os.stat(p)
                if self.ro.isChecked():
                    os.chmod(p, st.st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
                elif not os.access(p, os.W_OK):
                    os.chmod(p, st.st_mode | stat.S_IWUSR)
            except OSError:
                pass
        if hasattr(self, "hid"):
            base = os.path.basename(p)
            want_hidden = self.hid.isChecked()
            if want_hidden != base.startswith("."):
                newbase = "." + base if want_hidden else base.lstrip(".")
                dest = os.path.join(os.path.dirname(p), newbase)
                if not os.path.exists(dest):
                    try:
                        os.rename(p, dest)
                        self.paths[0] = dest
                    except OSError:
                        pass
        return True

    def _ok(self):
        if self._apply():
            self.accept()
