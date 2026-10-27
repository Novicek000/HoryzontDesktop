"""Uprawnienia administratora: własne okno hasła dla polkit, bez zewnętrznego agenta.

Jak to działa
-------------
polkit ma wbudowanego agenta tekstowego (``pkttyagent`` oraz ten w ``pkexec``),
który pyta o hasło na terminalu. Gdy program graficzny wywołuje ``pkexec`` bez
terminala i bez agenta sesji, pojawia się błąd::

    Error creating textual authentication agent: Error opening current
    controlling terminal for the process (/dev/tty)

Horyzont uruchamia tych agentów w pseudoterminalu (pty), którym sam steruje:
czyta pytania (np. „Password:”), pokazuje okno hasła w stylu pulpitu i wpisuje
odpowiedź. Dzięki temu:

* powłoka uruchamia ``pkttyagent`` jako agenta całej sesji — działa to także dla
  innych programów (np. menedżerów pakietów, ustawień sieci),
* ``run_privileged`` uruchamia ``pkexec`` w pty — działa nawet wtedy, gdy agent
  sesji nie wystartował.
"""
import fcntl
import os
import pty
import re
import shutil
import signal
import struct
import termios

from PySide6.QtCore import QEventLoop, QObject, QSocketNotifier, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from ..i18n import plain, tr
from ..theme import iconcache

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")
IDENT_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


def _agent_env():
    env = dict(os.environ)
    env.pop("LC_ALL", None)
    env["LC_MESSAGES"] = "C"      # znaczniki agenta po angielsku — łatwe do rozpoznania
    env["TERM"] = "dumb"
    return env


class PtyProcess(QObject):
    """Proces w pseudoterminalu: odczyt wyjścia i zapis na wejście."""

    data = Signal(str)
    finished = Signal(int)

    def __init__(self, argv, env=None, parent=None):
        super().__init__(parent)
        self.argv = argv
        self.pid, self.fd = pty.fork()
        if self.pid == 0:   # proces potomny
            try:
                os.execvpe(argv[0], argv, env or os.environ)
            except Exception:
                os._exit(127)
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 200, 0, 0))
        except OSError:
            pass
        os.set_blocking(self.fd, False)
        self._done = False
        self._notifier = QSocketNotifier(self.fd, QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._read)

    def _read(self, *_):
        chunks = []
        while True:
            try:
                b = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                b = b""
            if not b:
                if chunks:
                    self.data.emit(b"".join(chunks).decode("utf-8", "replace"))
                self._finish()
                return
            chunks.append(b)
            if len(b) < 65536:
                break
        if chunks:
            self.data.emit(b"".join(chunks).decode("utf-8", "replace"))

    def _finish(self):
        if self._done:
            return
        self._done = True
        self._notifier.setEnabled(False)
        code = -1
        try:
            _, status = os.waitpid(self.pid, 0)
            code = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.finished.emit(code)

    def write(self, text):
        if self._done:
            return
        try:
            os.write(self.fd, text.encode("utf-8"))
        except OSError:
            pass

    def interrupt(self):
        """Ctrl+C — przerwanie (np. anulowanie uwierzytelniania)."""
        self.write("\x03")
        QTimer.singleShot(800, self._kill_if_alive)

    def _kill_if_alive(self):
        if not self._done:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except OSError:
                pass

    def running(self):
        return not self._done


class AuthParser(QObject):
    """Rozpoznaje pytania agenta tekstowego polkit w strumieniu z pty."""

    begin = Signal(str)                  # identyfikator akcji
    prompt = Signal(str, list, list)     # pytanie, linie opisu, tożsamości [(nr, nazwa)]
    result = Signal(bool)                # uwierzytelnianie zakończone: sukces?
    passthrough = Signal(str)            # zwykłe wyjście (np. uruchamianego polecenia)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buf = ""
        self.in_auth = False
        self.lines = []
        self.idents = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._check_prompt)

    def feed(self, text):
        self.buf += ANSI_RE.sub("", text)
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._line(line)
        if self.buf:
            self._timer.start()

    def _line(self, line):
        s = line.strip()
        if s.startswith("==== AUTHENTICATING FOR"):
            self.in_auth = True
            self.lines, self.idents = [], []
            action = s.replace("==== AUTHENTICATING FOR", "").strip(" =")
            self.begin.emit(action)
            return
        if s.startswith("==== AUTHENTICATION"):
            ok = "COMPLETE" in s
            self.in_auth = False
            self.result.emit(ok)
            return
        if self.in_auth:
            m = IDENT_RE.match(line)
            if m and self.lines and "identit" in self.lines[-1].lower() or (m and self.idents):
                self.idents.append((m.group(1), m.group(2).strip()))
            elif s:
                self.lines.append(s)
            return
        self.passthrough.emit(line + "\n")

    def _check_prompt(self):
        tail = self.buf
        if not tail:
            return
        if self.in_auth and tail.rstrip().endswith(":"):
            self.buf = ""
            desc = [l for l in self.lines if not l.lower().startswith("multiple identities")]
            self.prompt.emit(tail.strip(), desc, list(self.idents))
        elif not self.in_auth:
            # niepełna linia zwykłego wyjścia (np. pasek postępu)
            self.passthrough.emit(tail)
            self.buf = ""


class AuthDialog:
    """Okno „Wymagane uprawnienia administratora”."""

    def __init__(self, action, desc_lines, prompt, idents=None, parent=None, error=""):
        from .window import HDialog
        self._dlg = HDialog(plain("auth_title"), "key", parent, help_button=False)
        d = self._dlg
        lay = QVBoxLayout(d.body())
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(iconcache.pixmap("key", 48))
        top.addWidget(ic, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        head = QLabel(plain("auth_heading"))
        head.setStyleSheet("font-weight: bold;")
        head.setWordWrap(True)
        texts.addWidget(head)
        msg = [_translate_message(l) for l in desc_lines if not l.lower().startswith("authenticating as")]
        body = QLabel("\n".join(msg) if msg else plain("auth_generic"))
        body.setWordWrap(True)
        texts.addWidget(body)
        top.addLayout(texts, 1)
        lay.addLayout(top)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        self.combo = None
        row = 0
        who = ""
        for l in desc_lines:
            if l.lower().startswith("authenticating as"):
                who = l.split(":", 1)[1].strip()
        if idents:
            grid.addWidget(QLabel(plain("auth_user")), row, 0)
            self.combo = QComboBox()
            for num, name in idents:
                self.combo.addItem(iconcache.icon("user"), name, num)
            grid.addWidget(self.combo, row, 1)
            row += 1
        elif who:
            grid.addWidget(QLabel(plain("auth_user")), row, 0)
            ul = QLabel(who)
            grid.addWidget(ul, row, 1)
            row += 1
        self.pw = None
        if prompt:
            lbl = QLabel(_translate_prompt(prompt))
            grid.addWidget(lbl, row, 0)
            self.pw = QLineEdit()
            self.pw.setEchoMode(QLineEdit.Password)
            lbl.setBuddy(self.pw)
            grid.addWidget(self.pw, row, 1)
            row += 1
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        if error:
            el = QLabel(error)
            el.setStyleSheet("color: #b00000;")
            el.setWordWrap(True)
            lay.addWidget(el)
        if action:
            det = QLabel(f"<small>{plain('auth_action')} {action}</small>")
            det.setStyleSheet("color: #666;")
            lay.addWidget(det)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(plain("ok"))
        ok.setDefault(True)
        ok.clicked.connect(d.accept)
        ca = QPushButton(plain("cancel"))
        ca.clicked.connect(d.reject)
        btns.addWidget(ok)
        btns.addWidget(ca)
        lay.addLayout(btns)
        d.setFixedWidth(430)
        d.adjustSize()
        if self.pw is not None:
            self.pw.setFocus()

    def run(self):
        d = self._dlg
        d.show()
        d.raise_()
        d.activateWindow()
        ok = d.exec() == QDialog.Accepted
        return ok

    def answer(self):
        return self.pw.text() if self.pw is not None else ""

    def identity(self):
        return self.combo.currentData() if self.combo is not None else None


_RUN_AS_RE = re.compile(r"Authentication is needed to run [`'‘](.+?)['’] as the super user")


def _translate_message(line):
    from ..i18n import lang_code
    if lang_code() != "pl":
        return line
    m = _RUN_AS_RE.search(line)
    if m:
        return f"Uruchomienie programu „{m.group(1)}” jako administrator wymaga uwierzytelnienia."
    if line.startswith("Authentication is required"):
        return "Ta czynność wymaga uwierzytelnienia."
    return line


def _translate_prompt(p):
    low = p.lower().rstrip(": ")
    if low in ("password", "hasło"):
        return plain("auth_password")
    if low.startswith("choose identity"):
        return plain("auth_user")
    return p.rstrip(":") + ":"


class AuthHandler(QObject):
    """Łączy PtyProcess + AuthParser i obsługuje okna hasła."""

    output = Signal(str)
    auth_result = Signal(bool)

    def __init__(self, proc, parent_widget=None):
        super().__init__(proc)
        self.proc = proc
        self.parent_widget = parent_widget
        self.parser = AuthParser(self)
        self.action = ""
        self.cancelled = False
        self.failed_once = False
        proc.data.connect(self.parser.feed)
        self.parser.begin.connect(self._begin)
        self.parser.prompt.connect(self._prompt)
        self.parser.result.connect(self._result)
        self.parser.passthrough.connect(self.output.emit)
        self._pending_ident = None

    def _begin(self, action):
        self.action = action

    def _prompt(self, prompt, desc, idents):
        low = prompt.lower()
        if low.startswith("choose identity") and idents:
            # najpierw tożsamość — zapytamy o nią w tym samym oknie co hasło
            dlg = AuthDialog(self.action, desc, "Password:", idents, self.parent_widget,
                             error=plain("auth_failed") if self.failed_once else "")
            if not dlg.run():
                self._cancel()
                return
            self._pending_ident = dlg.answer()
            self.proc.write(str(dlg.identity()) + "\n")
            return
        if self._pending_ident is not None and ("password" in low or "hasło" in low):
            pw, self._pending_ident = self._pending_ident, None
            self.proc.write(pw + "\n")
            return
        dlg = AuthDialog(self.action, desc, prompt, None, self.parent_widget,
                         error=plain("auth_failed") if self.failed_once else "")
        if not dlg.run():
            self._cancel()
            return
        self.proc.write(dlg.answer() + "\n")

    def _cancel(self):
        self.cancelled = True
        self.proc.interrupt()

    def _result(self, ok):
        if not ok:
            self.failed_once = True
        self.auth_result.emit(ok)


# ---------------------------------------------------------------- agent sesji
EXTERNAL_AGENTS = [
    "/usr/libexec/lxqt-policykit-agent", "lxqt-policykit-agent", "lxpolkit",
    "/usr/libexec/polkit-mate-authentication-agent-1", "/usr/libexec/polkit-gnome-authentication-agent-1",
    "/usr/libexec/kf6/polkit-kde-authentication-agent-1", "/usr/libexec/kf5/polkit-kde-authentication-agent-1",
    "/usr/libexec/xfce-polkit", "/usr/libexec/hyprpolkitagent",
]


class SessionAgent(QObject):
    """pkttyagent jako agent uwierzytelniania sesji (uruchamiany przez powłokę).

    Okna hasła rysuje Horyzont. Gdy pkttyagent nie może się zarejestrować
    (np. sesja bez logind), uruchamiamy zainstalowanego agenta zewnętrznego.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.handler = None
        self.failures = 0
        self.external = False
        self.log = ""

    def _start_external(self):
        import subprocess
        for a in EXTERNAL_AGENTS:
            exe = a if os.path.isabs(a) and os.access(a, os.X_OK) else shutil.which(a) if not os.path.isabs(a) else None
            if exe:
                try:
                    subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                    self.external = True
                    return True
                except OSError:
                    continue
        return False

    def start(self):
        exe = shutil.which("pkttyagent")
        if not exe:
            return self._start_external()
        self.log = ""
        self.proc = PtyProcess([exe], _agent_env(), self)
        self.handler = AuthHandler(self.proc)
        self.handler.output.connect(self._out)
        self.proc.finished.connect(self._finished)
        return True

    def _out(self, text):
        self.log = (self.log + text)[-2000:]

    def _finished(self, code):
        restart = self.handler is not None and self.handler.cancelled
        if "already exists" in self.log:
            self.external = True   # działa inny agent (np. lxpolkit) — on obsłuży okna
            return
        self.failures += 0 if restart else 1
        if self.failures >= 3 and not restart:
            print("horyzont: pkttyagent nie działa:", self.log.strip()[-300:])
            self._start_external()
            return
        QTimer.singleShot(300 if restart else 2000, self.start)


# ---------------------------------------------------------------- polecenia jako root
def run_privileged(args, parent=None, show_errors=True, on_output=None, timeout_ms=0):
    """Uruchamia polecenie jako administrator przez pkexec (w pty, z oknem hasła Horyzont).

    Zwraca (ok, wyjście). Blokuje wywołującego, ale okna dalej się odświeżają.
    """
    pk = shutil.which("pkexec")
    if os.geteuid() == 0:
        argv = list(args)
    elif pk:
        argv = [pk] + list(args)
    else:
        if parent is not None and show_errors:
            from . import dialogs
            dialogs.message(parent, plain("error"), plain("auth_no_pkexec"), "error")
        return False, "pkexec"
    env = _agent_env()
    try:
        proc = PtyProcess(argv, env)
    except OSError as e:
        return False, str(e)
    handler = AuthHandler(proc, parent)
    out = []

    def got(t):
        out.append(t)
        if on_output:
            on_output(t)

    handler.output.connect(got)
    loop = QEventLoop()
    res = {"code": -1}

    def done(code):
        res["code"] = code
        loop.quit()

    proc.finished.connect(done)
    if timeout_ms:
        QTimer.singleShot(timeout_ms, proc.interrupt)
    loop.exec()
    text = "".join(out)
    ok = res["code"] == 0
    if not ok and handler.cancelled:
        return False, plain("auth_cancelled")
    if not ok and parent is not None and show_errors:
        from . import dialogs
        msg = text.strip()[-1500:] or tr("cp_cmd_failed", " ".join(args))
        if res["code"] in (126, 127) and not text.strip():
            msg = plain("auth_denied")
        dialogs.message(parent, plain("error"), msg, "error")
    return ok, text


class PrivilegedJob(QObject):
    """Asynchroniczne polecenie jako administrator — do długich operacji (dnf, flatpak)."""

    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, args, parent_widget=None, root=True):
        super().__init__()
        self.args = list(args)
        self.parent_widget = parent_widget
        self.root = root
        self.text = []
        self.proc = None
        self.handler = None

    def start(self):
        argv = list(self.args)
        if self.root and os.geteuid() != 0:
            pk = shutil.which("pkexec")
            if not pk:
                self.finished.emit(False, plain("auth_no_pkexec"))
                return
            argv = [pk] + argv
        env = _agent_env()
        env["TERM"] = "dumb"
        self.proc = PtyProcess(argv, env, self)
        self.handler = AuthHandler(self.proc, self.parent_widget)
        self.handler.output.connect(self._out)
        self.proc.finished.connect(self._done)

    def _out(self, t):
        self.text.append(t)
        self.output.emit(t)

    def _done(self, code):
        txt = "".join(self.text)
        if code != 0 and self.handler is not None and self.handler.cancelled:
            txt = plain("auth_cancelled")
        self.finished.emit(code == 0, txt)

    def cancel(self):
        if self.proc is not None and self.proc.running():
            self.proc.interrupt()
