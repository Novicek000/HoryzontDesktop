"""Konta użytkowników."""
import grp
import os
import pty
import pwd
import select
import shlex
import shutil
import time

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QRadioButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget, QFrame,
                               QSplitter)

from ... import config
from ...common import dialogs, launcher, sysctl
from ...common.taskpane import TaskPane
from ...common.window import HWindow
from ...i18n import plain, tr
from ...theme import iconcache
from ...theme.icons import AVATARS
from ...theme.manager import current
from .common import run_privileged
from .panel import BigTitle, CategoryLink


def accounts():
    out = []
    for p in pwd.getpwall():
        if p.pw_uid >= 1000 and p.pw_uid < 60000 and not p.pw_shell.endswith(("nologin", "false")):
            out.append(p)
    me = os.getuid()
    if not any(p.pw_uid == me for p in out):
        try:
            out.insert(0, pwd.getpwuid(me))
        except KeyError:
            pass
    return out


def is_admin_user(name):
    try:
        for g in ("wheel", "sudo", "admin"):
            try:
                if name in grp.getgrnam(g).gr_mem:
                    return True
            except KeyError:
                pass
        return pwd.getpwnam(name).pw_uid == 0
    except KeyError:
        return False


def _secret_file(text):
    """Plik z hasłem dla chpasswd — w prywatnym katalogu użytkownika (tmpfs), tylko do odczytu właściciela."""
    import tempfile
    d = os.environ.get("XDG_RUNTIME_DIR") or None
    fd, path = tempfile.mkstemp(prefix=".hz-", dir=d)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def root_sh(parent, script, *args):
    """Skrypt powłoki jako administrator; argumenty przekazujemy jako $1, $2… (bez sklejania tekstu)."""
    return run_privileged(["sh", "-c", script, "sh"] + [str(a) for a in args], parent)


def set_password_as_root(parent, login, password):
    path = _secret_file(f"{login}:{password}\n")
    try:
        ok, _ = root_sh(parent, 'chpasswd < "$1"', path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return ok


def accounts_service_icon(parent, p, image_path):
    """Obraz konta dla ekranu logowania (AccountsService)."""
    if not shutil.which("busctl"):
        return False
    obj = f"/org/freedesktop/Accounts/User{p.pw_uid}"
    args = ["busctl", "call", "org.freedesktop.Accounts", obj, "org.freedesktop.Accounts.User", "SetIconFile", "s", image_path]
    if p.pw_uid == os.getuid():
        import subprocess
        r = subprocess.run(args, capture_output=True, text=True)
        return r.returncode == 0
    ok, _ = run_privileged(args, parent)
    return ok


def admins():
    return [a for a in accounts() if is_admin_user(a.pw_name)]


def picture_for(p, size=48):
    if p.pw_uid == os.getuid():
        from ...shell.startmenu import user_picture_pixmap
        return user_picture_pixmap(size)
    for face in (os.path.join(p.pw_dir, ".face"), f"/var/lib/AccountsService/icons/{p.pw_name}"):
        if not os.access(face, os.R_OK):
            continue
        pm = QPixmap(face)
        if not pm.isNull():
            return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return iconcache.pixmap("avatar_" + AVATARS[p.pw_uid % len(AVATARS)], size)


class AccountTile(QWidget):
    def __init__(self, p, cb, parent=None):
        super().__init__(parent)
        self.p, self.cb = p, cb
        self._hover = False
        self.setFixedSize(250, 64)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        self.cb(self.p)

    def paintEvent(self, e):
        q = QPainter(self)
        t = current()
        if self._hover:
            c = t.color("highlight")
            c.setAlpha(40)
            q.fillRect(self.rect(), c)
        q.setPen(QColor("#ffffff"))
        q.setBrush(QColor("#ffffff"))
        q.drawRoundedRect(QRect(5, 5, 54, 54), 4, 4)
        q.drawPixmap(8, 8, picture_for(self.p, 48))
        f = t.font("normal")
        f.setPixelSize(int(13 * t.font_scale))
        q.setFont(f)
        q.setPen(t.color("taskpane_link"))
        name = self.p.pw_gecos.split(",")[0] or self.p.pw_name
        q.drawText(QRect(68, 10, self.width() - 70, 22), Qt.AlignLeft | Qt.AlignVCenter, name)
        q.setFont(t.font("normal"))
        q.setPen(QColor("#6a7678"))
        q.drawText(QRect(68, 32, self.width() - 70, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   plain("ua_admin") if is_admin_user(self.p.pw_name) else plain("ua_limited"))


class UsersWindow(HWindow):
    def __init__(self, page=None):
        super().__init__(plain("user_accounts"), "users")
        lay = QVBoxLayout(self.body())
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        split = QSplitter(Qt.Horizontal)
        self.pane = TaskPane()
        split.addWidget(self.pane)
        self.stack = QStackedWidget()
        split.addWidget(self.stack)
        split.setSizes([210, 560])
        lay.addWidget(split, 1)
        self.resize(780, 520)
        self.show_home()
        if page == "picture":
            self.show_picture(pwd.getpwuid(os.getuid()))

    def _page(self, w):
        while self.stack.count():
            old = self.stack.widget(0)
            self.stack.removeWidget(old)
            old.deleteLater()
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        w.setAutoFillBackground(True)
        pal = w.palette()
        pal.setColor(w.backgroundRole(), QColor("#ffffff"))
        w.setPalette(pal)
        sa.setWidget(w)
        self.stack.addWidget(sa)

    def _pane(self, back=False):
        self.pane.clear()
        if back:
            s = self.pane.add_section(plain("ua_nav"), special=True)
            s.add_link("back", plain("back"), self.show_home)
            s.add_link("home", plain("ua_home"), self.show_home)
        rel = self.pane.add_section(plain("ua_related"))
        rel.add_link("control_panel", plain("control_panel"), lambda: launcher.start_builtin("control"))
        rel.add_link("help", plain("sm_help"), lambda: launcher.start_builtin("explorer", ["horyzont:help"]))

    def show_home(self):
        self._pane()
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(10)
        lay.addWidget(BigTitle(plain("ua_pick_task")))
        lay.addWidget(CategoryLink("forward", plain("cp_task_change_account"), self.show_home, w, 16))
        lay.addWidget(CategoryLink("forward", plain("cp_task_create_account"), self.create_account, w, 16))
        lay.addSpacing(12)
        lay.addWidget(BigTitle(plain("ua_or_pick")))
        grid = QGridLayout()
        for i, p in enumerate(accounts()):
            grid.addWidget(AccountTile(p, self.show_account), i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        self._page(w)

    def show_account(self, p):
        self._pane(back=True)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(10)
        mine = p.pw_uid == os.getuid()
        lay.addWidget(BigTitle(plain("ua_what_change_mine") if mine else tr("ua_what_change", p.pw_name)))
        row = QHBoxLayout()
        v = QVBoxLayout()

        def link(key, cb):
            v.addWidget(CategoryLink("forward", plain(key).replace("&", ""), cb, w, 16))

        link("ua_change_name", lambda: self.change_name(p))
        if mine:
            link("ua_change_password", self.change_password)
        else:
            link("ua_set_password", lambda: self.set_password(p))
            link("ua_remove_password", lambda: self.remove_password(p))
        link("ua_change_picture", lambda: self.show_picture(p))
        link("ua_change_type", lambda: self.change_type(p))
        link("ua_groups", lambda: self.show_groups(p))
        if not mine:
            link("ua_delete", lambda: self.delete_account(p))
        v.addStretch(1)
        row.addLayout(v, 1)
        row.addWidget(AccountTile(p, lambda *_: None), 0, Qt.AlignTop)
        lay.addLayout(row)
        lay.addStretch(1)
        self._page(w)

    def show_picture(self, p):
        self._pane(back=True)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.addWidget(BigTitle(plain("ua_pick_picture")))
        lay.addWidget(QLabel(plain("ua_picture_desc")))
        grid = QGridLayout()
        for i, a in enumerate(AVATARS):
            b = QPushButton()
            b.setIcon(iconcache.icon("avatar_" + a))
            b.setIconSize(QSize(48, 48))
            b.setFixedSize(60, 60)
            b.clicked.connect(lambda _=False, a=a: self._set_picture("builtin:" + a, p))
            grid.addWidget(b, i // 6, i % 6)
        lay.addLayout(grid)
        lay.addWidget(CategoryLink("search", plain("ua_browse_pictures"), lambda: self._browse_picture(p), w, 16))
        lay.addStretch(1)
        self._page(w)

    def _browse_picture(self, p=None):
        f = dialogs.open_file(self, plain("ua_browse_pictures"), config.user_dir("PICTURES"), plain("dp_wallpaper_filter"))
        if not f:
            return
        if p is None or p.pw_uid == os.getuid():
            dest = os.path.join(config.DATA_DIR, "user-picture" + os.path.splitext(f)[1].lower())
            os.makedirs(config.DATA_DIR, exist_ok=True)
            shutil.copy2(f, dest)
            self._set_picture(dest, p)
        else:
            self._set_picture(f, p)

    def _set_picture(self, pic, p=None):
        me = pwd.getpwuid(os.getuid())
        p = p or me
        if pic.startswith("builtin:"):
            pm = iconcache.pixmap("avatar_" + pic.split(":", 1)[1], 96)
        else:
            pm = QPixmap(pic).scaled(96, 96, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        tmp = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or config.CACHE_DIR, f"face-{p.pw_name}.png")
        pm.save(tmp, "PNG")
        os.chmod(tmp, 0o644)
        if p.pw_uid == me.pw_uid:
            config.set("user_picture", pic)
            # ~/.face jest używany przez menedżery logowania
            try:
                shutil.copyfile(tmp, os.path.expanduser("~/.face"))
            except OSError:
                pass
            accounts_service_icon(self, p, tmp)
        else:
            if not accounts_service_icon(self, p, tmp):
                root_sh(self, 'install -m 644 "$1" "$2/.face" && chown "$3" "$2/.face"', tmp, p.pw_dir, p.pw_name)
        self.show_account(pwd.getpwnam(p.pw_name))

    def change_name(self, p):
        cur = p.pw_gecos.split(",")[0] or p.pw_name
        new = dialogs.ask_text(self, plain("user_accounts"), plain("ua_new_name"), cur)
        if new and new != cur:
            ok, _ = run_privileged(["usermod", "-c", new, p.pw_name], self)
            if ok:
                self.show_account(pwd.getpwnam(p.pw_name))

    def change_type(self, p):
        admin = is_admin_user(p.pw_name)
        from ...common.window import HDialog
        d = HDialog(plain("ua_change_type"), "users", self)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(12, 12, 12, 12)
        r1 = QRadioButton(plain("ua_admin"))
        r2 = QRadioButton(plain("ua_limited"))
        (r1 if admin else r2).setChecked(True)
        lay.addWidget(r1)
        lay.addWidget(QLabel("   " + plain("ua_admin_desc")))
        lay.addWidget(r2)
        lay.addWidget(QLabel("   " + plain("ua_limited_desc")))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        lay.addLayout(row)
        if d.exec() and r1.isChecked() != admin:
            if r1.isChecked():
                run_privileged(["usermod", "-aG", "wheel", p.pw_name], self)
            else:
                run_privileged(["gpasswd", "-d", p.pw_name, "wheel"], self)
            self.show_account(p)

    def set_password(self, p):
        from ...common.window import HDialog
        d = HDialog(plain("ua_set_password").replace("&", ""), "lock", self)
        g = QGridLayout(d.body())
        g.setContentsMargins(12, 12, 12, 12)
        info = QLabel(tr("ua_set_password_warn", p.pw_name))
        info.setWordWrap(True)
        g.addWidget(info, 0, 0, 1, 2)
        new1, new2 = QLineEdit(), QLineEdit()
        for i, (lab, le) in enumerate(((plain("ua_new_password"), new1), (plain("ua_confirm_password"), new2))):
            le.setEchoMode(QLineEdit.Password)
            g.addWidget(QLabel(lab), i + 1, 0)
            g.addWidget(le, i + 1, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ua_set_password").replace("&", ""))
        ok.setDefault(True)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        g.addLayout(row, 3, 0, 1, 2)

        def go():
            if new1.text() != new2.text():
                dialogs.message(d, plain("user_accounts"), plain("ua_mismatch"), "error")
                return
            if set_password_as_root(d, p.pw_name, new1.text()):
                dialogs.message(d, plain("user_accounts"), plain("ua_password_changed"), "info")
                d.accept()
        ok.clicked.connect(go)
        d.setFixedWidth(400)
        d.exec()

    def remove_password(self, p):
        if dialogs.message(self, plain("user_accounts"), tr("ua_remove_password_q", p.pw_name), "question", ("yes", "no")) == "yes":
            ok, _ = run_privileged(["passwd", "-d", p.pw_name], self)
            if ok:
                dialogs.message(self, plain("user_accounts"), plain("ua_password_removed"), "info")

    def delete_account(self, p):
        if is_admin_user(p.pw_name) and len(admins()) <= 1:
            dialogs.message(self, plain("user_accounts"), plain("ua_last_admin"), "warning")
            return
        from ...common.window import HDialog
        d = HDialog(plain("ua_delete"), "users", self, help_button=False)
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(14, 14, 14, 12)
        lay.addWidget(BigTitle(tr("ua_keep_files_q", p.pw_name)))
        t = QLabel(tr("ua_keep_files_desc", p.pw_name))
        t.setWordWrap(True)
        lay.addWidget(t)
        res = {"v": None}
        row = QHBoxLayout()
        row.addStretch(1)
        for key, val in (("ua_keep_files", "keep"), ("ua_delete_files", "delete"), ("cancel", None)):
            b = QPushButton(plain(key))
            b.clicked.connect(lambda _=False, v=val: (res.__setitem__("v", v), d.accept()))
            row.addWidget(b)
        lay.addLayout(row)
        d.setFixedWidth(460)
        d.exec()
        if res["v"] is None:
            return
        if res["v"] == "keep":
            # pliki trafiają do folderu na pulpicie bieżącego użytkownika, jak w klasycznym systemie
            dest = os.path.join(config.user_dir("DESKTOP"), p.pw_name)
            me = pwd.getpwuid(os.getuid()).pw_name
            ok, _ = root_sh(self, 'pkill -KILL -u "$1" 2>/dev/null; cp -a "$2" "$3" && chown -R "$4": "$3" && userdel -r "$1"',
                            p.pw_name, p.pw_dir, dest, me)
        else:
            ok, _ = root_sh(self, 'pkill -KILL -u "$1" 2>/dev/null; userdel -r "$1"', p.pw_name)
        if ok:
            self.show_home()

    def show_groups(self, p):
        self._pane(back=True)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.addWidget(BigTitle(tr("ua_groups_title", p.pw_name)))
        d = QLabel(plain("ua_groups_desc"))
        d.setWordWrap(True)
        lay.addWidget(d)
        from PySide6.QtWidgets import QCheckBox
        known = {"wheel": "ua_g_wheel", "audio": "ua_g_audio", "video": "ua_g_video", "dialout": "ua_g_dialout",
                 "lp": "ua_g_lp", "docker": "ua_g_docker", "libvirt": "ua_g_libvirt", "kvm": "ua_g_kvm",
                 "input": "ua_g_input", "plugdev": "ua_g_plugdev", "wireshark": "ua_g_wireshark"}
        member = {g.gr_name for g in grp.getgrall() if p.pw_name in g.gr_mem}
        boxes = []
        names = [g.gr_name for g in grp.getgrall() if g.gr_name in known or (g.gr_gid >= 1000 and g.gr_gid < 60000
                                                                                and g.gr_name != p.pw_name)]
        for name in sorted(set(names)):
            cb = QCheckBox(f"{name} — {plain(known[name])}" if name in known else name)
            cb.setChecked(name in member)
            cb._group = name
            boxes.append(cb)
            lay.addWidget(cb)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(plain("apply"))

        def go():
            add = [c._group for c in boxes if c.isChecked() and c._group not in member]
            rem = [c._group for c in boxes if not c.isChecked() and c._group in member]
            if not add and not rem:
                return
            script = 'u="$1"; shift; for g in "$@"; do case "$g" in +*) gpasswd -a "$u" "${g#+}";; -*) gpasswd -d "$u" "${g#-}";; esac || exit 1; done'
            ok, _ = root_sh(self, script, p.pw_name, *(["+" + g for g in add] + ["-" + g for g in rem]))
            if ok:
                dialogs.message(self, plain("user_accounts"), plain("ua_groups_saved"), "info")
                self.show_groups(pwd.getpwnam(p.pw_name))
        b.clicked.connect(go)
        row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)
        self._page(w)

    def change_password(self):
        from ...common.window import HDialog
        d = HDialog(plain("ua_change_password").replace("&", ""), "lock", self)
        g = QGridLayout(d.body())
        g.setContentsMargins(12, 12, 12, 12)
        cur, new1, new2 = QLineEdit(), QLineEdit(), QLineEdit()
        for i, (lab, le) in enumerate(((plain("ua_cur_password"), cur), (plain("ua_new_password"), new1),
                                       (plain("ua_confirm_password"), new2))):
            le.setEchoMode(QLineEdit.Password)
            g.addWidget(QLabel(lab), i, 0)
            g.addWidget(le, i, 1)
        g.addWidget(QLabel(plain("ua_password_hint")), 3, 0, 1, 2)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ua_change_password").replace("&", ""))
        ok.setDefault(True)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        g.addLayout(row, 4, 0, 1, 2)

        def go():
            if new1.text() != new2.text():
                dialogs.message(d, plain("user_accounts"), plain("ua_mismatch"), "error")
                return
            ok_, msg = change_password_pty(cur.text(), new1.text())
            if ok_:
                dialogs.message(d, plain("user_accounts"), plain("ua_password_changed"), "info")
                d.accept()
            else:
                dialogs.message(d, plain("user_accounts"), msg or plain("ua_password_failed"), "error")
        ok.clicked.connect(go)
        d.setFixedWidth(380)
        d.exec()

    def create_account(self):
        from ...common.window import HDialog
        d = HDialog(plain("cp_task_create_account"), "users", self)
        g = QGridLayout(d.body())
        g.setContentsMargins(12, 12, 12, 12)
        full, login, pw = QLineEdit(), QLineEdit(), QLineEdit()
        pw.setEchoMode(QLineEdit.Password)
        g.addWidget(QLabel(plain("ua_full_name")), 0, 0)
        g.addWidget(full, 0, 1)
        g.addWidget(QLabel(plain("ua_login")), 1, 0)
        g.addWidget(login, 1, 1)
        g.addWidget(QLabel(plain("ua_new_password")), 2, 0)
        g.addWidget(pw, 2, 1)
        r1 = QRadioButton(plain("ua_admin"))
        r2 = QRadioButton(plain("ua_limited"))
        r2.setChecked(True)
        g.addWidget(r1, 3, 0, 1, 2)
        g.addWidget(r2, 4, 0, 1, 2)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(plain("ua_create"))
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        row.addWidget(ok)
        row.addWidget(ca)
        g.addLayout(row, 5, 0, 1, 2)
        full.textChanged.connect(lambda t: login.setText("".join(c for c in t.lower().split(" ")[0] if c.isalnum())))

        def go():
            name = login.text().strip()
            import re
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", name):
                dialogs.message(d, plain("user_accounts"), plain("ua_bad_login"), "error")
                return
            secret = _secret_file(f"{name}:{pw.text()}\n") if pw.text() else ""
            script = ('useradd -m -c "$2" ${3:+-G "$3"} "$1" || exit 1; '
                      'if [ -n "$4" ]; then chpasswd < "$4" || exit 1; else passwd -d "$1" >/dev/null; fi')
            try:
                ok_, _ = root_sh(d, script, name, full.text(), "wheel" if r1.isChecked() else "", secret)
            finally:
                if secret:
                    try:
                        os.remove(secret)
                    except OSError:
                        pass
            if ok_:
                d.accept()
                self.show_home()
        ok.clicked.connect(go)
        d.setFixedWidth(380)
        d.exec()


def change_password_pty(current_pw, new_pw):
    """Zmiana hasła przez `passwd` w pseudoterminalu. Zwraca (powodzenie, komunikat)."""
    if not shutil.which("passwd"):
        return False, "passwd"
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("passwd", ["passwd"])
    out = b""
    answers = [current_pw, new_pw, new_pw]
    deadline = time.time() + 20
    try:
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.5)
            if fd in r:
                try:
                    chunk = os.read(fd, 1024)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                low = chunk.lower()
                if (b"password" in low or b"has\xc5\x82o" in low or b"haslo" in low) and low.rstrip().endswith(b":") and answers:
                    os.write(fd, (answers.pop(0) + "\n").encode())
    finally:
        _, status = os.waitpid(pid, 0)
    text = out.decode("utf-8", "replace")
    lines = [l.strip() for l in text.splitlines() if l.strip() and ":" not in l[-2:]]
    return os.WEXITSTATUS(status) == 0, "\n".join(lines[-3:])


def open_users(page=None, parent=None):
    return UsersWindow(page)
