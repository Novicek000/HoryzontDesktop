"""Jedna instancja procesu na aplikację: kolejne wywołania przekazują
argumenty do działającego procesu przez gniazdo lokalne (QLocalSocket)."""
import json
import os



def socket_name(app):
    """Ścieżka gniazda: w XDG_RUNTIME_DIR (prywatny katalog użytkownika), inaczej w /tmp."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, f"horyzont-{app}.sock")
    return f"horyzont-{app}-{os.getuid()}"


def forward_fast(app, args, timeout=0.5):
    """To samo co try_forward, ale bez Qt — używane przez skróty klawiszowe (szybki start)."""
    import socket
    name = socket_name(app)
    path = name if os.path.isabs(name) else os.path.join(os.environ.get("TMPDIR", "/tmp"), name)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(json.dumps({"args": list(args), "cwd": os.getcwd()}).encode("utf-8") + b"\n")
        s.close()
        return True
    except OSError:
        return False


def try_forward(app, args, timeout=300):
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(socket_name(app))
    if not s.waitForConnected(timeout):
        return False
    data = json.dumps({"args": list(args), "cwd": os.getcwd()}).encode("utf-8") + b"\n"
    s.write(data)
    s.flush()
    s.waitForBytesWritten(timeout)
    s.disconnectFromServer()
    return True


class Server:
    def __init__(self, app, handler):
        from PySide6.QtNetwork import QLocalServer
        self.handler = handler
        self.server = QLocalServer()
        name = socket_name(app)
        QLocalServer.removeServer(name)
        self.server.listen(name)
        self.server.newConnection.connect(self._on_conn)

    def _on_conn(self):
        while self.server.hasPendingConnections():
            c = self.server.nextPendingConnection()
            buf = bytearray()

            def ready(c=c, buf=buf):
                buf.extend(bytes(c.readAll()))
                if buf.endswith(b"\n"):
                    try:
                        msg = json.loads(buf.decode("utf-8"))
                        self.handler(msg.get("args", []))
                    except Exception as e:  # pragma: no cover
                        print("horyzont: błędny komunikat", e)
                    buf.clear()

            c.readyRead.connect(ready)
            c.disconnected.connect(c.deleteLater)
