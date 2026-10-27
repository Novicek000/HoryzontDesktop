"""Minimalna implementacja protokołu D-Bus w czystym Pythonie, zintegrowana z pętlą zdarzeń Qt.

Wystarcza powłoce do: obsługi powiadomień (org.freedesktop.Notifications), zasobnika
programów (org.kde.StatusNotifierWatcher / StatusNotifierItem) i menu com.canonical.dbusmenu.
Nie wymaga żadnych dodatkowych pakietów (dbus-python, jeepney itp.).
"""
import os
import select
import socket
import struct

# ------------------------------------------------------------------ typy
METHOD_CALL, METHOD_RETURN, ERROR, SIGNAL = 1, 2, 3, 4
NO_REPLY_EXPECTED = 0x1

ALIGN = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8, "s": 4, "o": 4, "g": 1,
         "a": 4, "(": 8, "{": 8, "v": 1, "h": 4}
FIXED = {"y": "B", "b": "I", "n": "h", "q": "H", "i": "i", "u": "I", "x": "q", "t": "Q", "d": "d", "h": "I"}


class DBusError(Exception):
    def __init__(self, name, message=""):
        super().__init__(f"{name}: {message}")
        self.name = name
        self.message = message


class Variant:
    __slots__ = ("sig", "value")

    def __init__(self, sig, value):
        self.sig = sig
        self.value = value

    def __repr__(self):
        return f"Variant({self.sig!r}, {self.value!r})"


def split_sig(sig):
    """'a{sv}ias' -> ['a{sv}', 'i', 'as']"""
    out, i = [], 0
    while i < len(sig):
        j = _one(sig, i)
        out.append(sig[i:j])
        i = j
    return out


def _one(sig, i):
    c = sig[i]
    if c == "a":
        return _one(sig, i + 1)
    if c in "({":
        depth, j = 0, i
        while j < len(sig):
            if sig[j] in "({":
                depth += 1
            elif sig[j] in ")}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        raise ValueError("niepoprawna sygnatura: " + sig)
    return i + 1


def guess_sig(v):
    if isinstance(v, Variant):
        return "v"
    if isinstance(v, bool):
        return "b"
    if isinstance(v, int):
        return "i"
    if isinstance(v, float):
        return "d"
    if isinstance(v, str):
        return "s"
    if isinstance(v, (bytes, bytearray)):
        return "ay"
    if isinstance(v, dict):
        return "a{sv}"
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, str) for x in v):
            return "as"
        return "av"
    return "s"


# ------------------------------------------------------------------ zapis
class Writer:
    def __init__(self, start=0):
        self.buf = bytearray()
        self.start = start

    def pad(self, n):
        pos = self.start + len(self.buf)
        self.buf += b"\0" * ((-pos) % n)

    def write(self, sig, value):
        c = sig[0]
        if c in FIXED:
            self.pad(ALIGN[c])
            if c == "b":
                value = 1 if value else 0
            self.buf += struct.pack("<" + FIXED[c], value)
        elif c in "so":
            b = value.encode("utf-8")
            self.pad(4)
            self.buf += struct.pack("<I", len(b)) + b + b"\0"
        elif c == "g":
            b = value.encode("ascii")
            self.buf += struct.pack("<B", len(b)) + b + b"\0"
        elif c == "v":
            if not isinstance(value, Variant):
                value = Variant(guess_sig(value), value)
            self.write("g", value.sig)
            self.write(value.sig, value.value)
        elif c == "a":
            inner = sig[1:]
            self.pad(4)
            lpos = len(self.buf)
            self.buf += b"\0\0\0\0"
            self.pad(ALIGN[inner[0]])
            start = len(self.buf)
            if inner[0] == "{":
                ksig, vsig = split_sig(inner[1:-1])
                items = value.items() if isinstance(value, dict) else value
                for k, v in items:
                    self.pad(8)
                    self.write(ksig, k)
                    self.write(vsig, v)
            elif inner == "y" and isinstance(value, (bytes, bytearray)):
                self.buf += bytes(value)
            else:
                for v in value:
                    self.write(inner, v)
            struct.pack_into("<I", self.buf, lpos, len(self.buf) - start)
        elif c == "(":
            self.pad(8)
            for s, v in zip(split_sig(sig[1:-1]), value):
                self.write(s, v)
        else:
            raise ValueError("nieobsługiwany typ " + sig)


# ------------------------------------------------------------------ odczyt
class Reader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def align(self, n):
        self.pos += (-self.pos) % n

    def read(self, sig):
        c = sig[0]
        if c in FIXED:
            self.align(ALIGN[c])
            fmt = "<" + FIXED[c]
            v = struct.unpack_from(fmt, self.data, self.pos)[0]
            self.pos += struct.calcsize(fmt)
            return bool(v) if c == "b" else v
        if c in "so":
            self.align(4)
            n = struct.unpack_from("<I", self.data, self.pos)[0]
            self.pos += 4
            s = bytes(self.data[self.pos:self.pos + n]).decode("utf-8", "replace")
            self.pos += n + 1
            return s
        if c == "g":
            n = self.data[self.pos]
            self.pos += 1
            s = bytes(self.data[self.pos:self.pos + n]).decode("ascii", "replace")
            self.pos += n + 1
            return s
        if c == "v":
            s = self.read("g")
            return Variant(s, self.read(s))
        if c == "a":
            inner = sig[1:]
            self.align(4)
            n = struct.unpack_from("<I", self.data, self.pos)[0]
            self.pos += 4
            self.align(ALIGN[inner[0]])
            end = self.pos + n
            if inner == "y":
                v = bytes(self.data[self.pos:end])
                self.pos = end
                return v
            if inner[0] == "{":
                ksig, vsig = split_sig(inner[1:-1])
                out = {}
                while self.pos < end:
                    self.align(8)
                    k = self.read(ksig)
                    out[k] = self.read(vsig)
                return out
            out = []
            while self.pos < end:
                out.append(self.read(inner))
            return out
        if c == "(":
            self.align(8)
            return tuple(self.read(s) for s in split_sig(sig[1:-1]))
        raise ValueError("nieobsługiwany typ " + sig)


def unwrap(v):
    """Rekurencyjnie usuwa Variant (wygodne dla właściwości)."""
    if isinstance(v, Variant):
        return unwrap(v.value)
    if isinstance(v, dict):
        return {k: unwrap(x) for k, x in v.items()}
    if isinstance(v, list):
        return [unwrap(x) for x in v]
    if isinstance(v, tuple):
        return tuple(unwrap(x) for x in v)
    return v


class Message:
    __slots__ = ("type", "flags", "serial", "path", "interface", "member", "error_name", "reply_serial",
                 "destination", "sender", "signature", "body")

    def __init__(self, type_=METHOD_CALL, **kw):
        self.type = type_
        self.flags = 0
        self.serial = 0
        self.path = self.interface = self.member = self.error_name = None
        self.reply_serial = None
        self.destination = self.sender = None
        self.signature = ""
        self.body = []
        for k, v in kw.items():
            setattr(self, k, v)

    def encode(self, serial):
        self.serial = serial
        body = Writer(0)
        for s, v in zip(split_sig(self.signature), self.body):
            body.write(s, v)
        fields = []
        for code, sig, val in ((1, "o", self.path), (2, "s", self.interface), (3, "s", self.member),
                               (4, "s", self.error_name), (5, "u", self.reply_serial), (6, "s", self.destination),
                               (7, "s", self.sender), (8, "g", self.signature or None)):
            if val is not None:
                fields.append((code, Variant(sig, val)))
        hdr = Writer(0)
        hdr.buf += struct.pack("<cBBBII", b"l", self.type, self.flags, 1, len(body.buf), serial)
        hdr.write("a(yv)", fields)
        hdr.pad(8)
        return bytes(hdr.buf) + bytes(body.buf)

    @classmethod
    def decode(cls, data):
        """(Message, zużyte bajty) albo (None, 0), gdy danych jest za mało."""
        if len(data) < 16:
            return None, 0
        if data[0:1] != b"l":
            raise DBusError("org.horyzont.Error", "obsługujemy tylko little-endian")
        typ, flags, ver, blen, serial, flen = struct.unpack_from("<BBBIII", data, 1)
        hlen = 16 + flen
        hlen += (-hlen) % 8
        total = hlen + blen
        if len(data) < total:
            return None, 0
        m = cls(typ)
        m.flags, m.serial = flags, serial
        r = Reader(data, 12)
        for code, var in r.read("a(yv)"):
            name = {1: "path", 2: "interface", 3: "member", 4: "error_name", 5: "reply_serial",
                    6: "destination", 7: "sender", 8: "signature"}.get(code)
            if name:
                setattr(m, name, var.value)
        m.signature = m.signature or ""
        br = Reader(data[hlen:total], 0)
        m.body = [br.read(s) for s in split_sig(m.signature)]
        return m, total


def _bus_address(kind):
    if kind == "system":
        return os.environ.get("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/run/dbus/system_bus_socket")
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if not addr:
        rt = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        addr = f"unix:path={rt}/bus"
    return addr


def _connect(addr):
    for part in addr.split(";"):
        if not part.startswith("unix:"):
            continue
        opts = dict(kv.split("=", 1) for kv in part[5:].split(",") if "=" in kv)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        try:
            if "path" in opts:
                s.connect(opts["path"])
            elif "abstract" in opts:
                s.connect("\0" + opts["abstract"])
            else:
                continue
            return s
        except OSError:
            s.close()
    raise OSError("nie można połączyć z magistralą D-Bus: " + addr)


# ------------------------------------------------------------------ połączenie
class Connection:
    """Połączenie z magistralą. Bez Qt działa synchronicznie; attach_qt() podpina je do pętli zdarzeń."""

    def __init__(self, kind="session"):
        self.sock = _connect(_bus_address(kind))
        self._auth()
        self._serial = 0
        self._buf = bytearray()
        self._pending = {}          # serial -> (callback, error_callback)
        self._sync_replies = {}
        self._objects = {}          # (path, interface) -> obiekt z metodą handle(member, args, msg)
        self._signal_handlers = []  # (filtr, funkcja)
        self._notifier = None
        self.unique_name = self.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                          "Hello")[0]

    def _auth(self):
        uid = str(os.getuid()).encode().hex()
        self.sock.sendall(b"\0AUTH EXTERNAL " + uid.encode() + b"\r\n")
        resp = b""
        while not resp.endswith(b"\r\n"):
            chunk = self.sock.recv(1024)
            if not chunk:
                raise OSError("D-Bus: rozłączono podczas uwierzytelniania")
            resp += chunk
        if not resp.startswith(b"OK"):
            raise OSError("D-Bus: uwierzytelnianie odrzucone: " + resp.decode(errors="replace"))
        self.sock.sendall(b"BEGIN\r\n")

    def fileno(self):
        return self.sock.fileno()

    def attach_qt(self):
        from PySide6.QtCore import QSocketNotifier
        self.sock.setblocking(False)
        self._notifier = QSocketNotifier(self.sock.fileno(), QSocketNotifier.Read)
        self._notifier.activated.connect(lambda *_: self.process())

    def _next_serial(self):
        self._serial += 1
        return self._serial

    def send(self, msg):
        serial = self._next_serial()
        data = msg.encode(serial)
        blocking = self.sock.getblocking()
        self.sock.setblocking(True)
        try:
            self.sock.sendall(data)
        finally:
            self.sock.setblocking(blocking)
        return serial

    # --- wywołania
    def call(self, dest, path, iface, member, sig="", args=(), callback=None, error=None):
        m = Message(METHOD_CALL, destination=dest, path=path, interface=iface, member=member, signature=sig,
                    body=list(args))
        if callback is None and error is None:
            m.flags = NO_REPLY_EXPECTED
        serial = self.send(m)
        if callback is not None or error is not None:
            self._pending[serial] = (callback, error)
        return serial

    def call_sync(self, dest, path, iface, member, sig="", args=(), timeout=5.0):
        m = Message(METHOD_CALL, destination=dest, path=path, interface=iface, member=member, signature=sig,
                    body=list(args))
        serial = self.send(m)
        import time
        deadline = time.monotonic() + timeout
        while serial not in self._sync_replies:
            left = deadline - time.monotonic()
            if left <= 0:
                raise DBusError("org.freedesktop.DBus.Error.Timeout", member)
            r, _, _ = select.select([self.sock], [], [], left)
            if r:
                self._read(sync_wait=serial)
        reply = self._sync_replies.pop(serial)
        if reply.type == ERROR:
            raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
        return reply.body

    def get_property(self, dest, path, iface, name, callback, error=None):
        self.call(dest, path, "org.freedesktop.DBus.Properties", "Get", "ss", (iface, name),
                  lambda body: callback(unwrap(body[0])), error)

    def get_all(self, dest, path, iface, callback, error=None):
        self.call(dest, path, "org.freedesktop.DBus.Properties", "GetAll", "s", (iface,),
                  lambda body: callback(unwrap(body[0])), error)

    def emit(self, path, iface, member, sig="", args=(), destination=None):
        self.send(Message(SIGNAL, path=path, interface=iface, member=member, signature=sig, body=list(args),
                          destination=destination))

    def request_name(self, name, flags=0x4):
        """flags 4 = DO_NOT_QUEUE. Zwraca True, gdy nazwa jest nasza."""
        res = self.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                             "RequestName", "su", (name, flags))[0]
        return res in (1, 4)

    def add_match(self, rule):
        self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", (rule,))

    def on_signal(self, callback, sender=None, path=None, interface=None, member=None):
        self._signal_handlers.append(((sender, path, interface, member), callback))

    def export(self, path, interface, obj):
        """obj.handle(member, args, msg) -> (sygnatura, [wartości]) albo None; obj.properties() -> dict sygnatur."""
        self._objects[(path, interface)] = obj

    # --- odbiór
    def process(self):
        try:
            self._read()
        except (OSError, DBusError) as e:
            print("horyzont: D-Bus:", e)
            if self._notifier is not None:
                self._notifier.setEnabled(False)

    def _read(self, sync_wait=None):
        while True:
            try:
                chunk = self.sock.recv(65536, socket.MSG_DONTWAIT)
            except (BlockingIOError, InterruptedError):
                break
            if not chunk:
                raise OSError("magistrala D-Bus zamknęła połączenie")
            self._buf += chunk
            if len(chunk) < 65536:
                break
        while True:
            m, n = Message.decode(self._buf)
            if m is None:
                break
            del self._buf[:n]
            self._dispatch(m, sync_wait)

    def _dispatch(self, m, sync_wait=None):
        if m.type in (METHOD_RETURN, ERROR):
            if m.reply_serial in self._pending:
                cb, err = self._pending.pop(m.reply_serial)
                try:
                    if m.type == ERROR:
                        if err:
                            err(m.error_name, m.body[0] if m.body else "")
                    elif cb:
                        cb(m.body)
                except Exception as e:  # pragma: no cover
                    print("horyzont: D-Bus callback:", e)
            else:
                self._sync_replies[m.reply_serial] = m
        elif m.type == SIGNAL:
            for (snd, path, iface, member), cb in list(self._signal_handlers):
                if (snd is None or snd == m.sender) and (path is None or path == m.path) and \
                        (iface is None or iface == m.interface) and (member is None or member == m.member):
                    try:
                        cb(m)
                    except Exception as e:  # pragma: no cover
                        print("horyzont: D-Bus sygnał:", e)
        elif m.type == METHOD_CALL:
            self._handle_call(m)

    def _reply(self, m, sig="", body=()):
        if m.flags & NO_REPLY_EXPECTED:
            return
        self.send(Message(METHOD_RETURN, reply_serial=m.serial, destination=m.sender, signature=sig, body=list(body)))

    def _error(self, m, name, text=""):
        if m.flags & NO_REPLY_EXPECTED:
            return
        self.send(Message(ERROR, reply_serial=m.serial, destination=m.sender, error_name=name, signature="s",
                          body=[text]))

    def _handle_call(self, m):
        iface = m.interface
        if iface == "org.freedesktop.DBus.Peer":
            if m.member == "Ping":
                return self._reply(m)
            return self._reply(m, "s", ["00000000000000000000000000000000"])
        if iface == "org.freedesktop.DBus.Introspectable":
            return self._reply(m, "s", [self._introspect(m.path)])
        if iface == "org.freedesktop.DBus.Properties":
            target = m.body[0] if m.body else ""
            obj = self._objects.get((m.path, target))
            if obj is None:
                return self._error(m, "org.freedesktop.DBus.Error.UnknownInterface", target)
            props = obj.properties()
            if m.member == "Get":
                name = m.body[1]
                if name not in props:
                    return self._error(m, "org.freedesktop.DBus.Error.UnknownProperty", name)
                sig, val = props[name]
                return self._reply(m, "v", [Variant(sig, val)])
            if m.member == "GetAll":
                return self._reply(m, "a{sv}", [{k: Variant(s, v) for k, (s, v) in props.items()}])
            return self._error(m, "org.freedesktop.DBus.Error.PropertyReadOnly", "")
        obj = self._objects.get((m.path, iface))
        if obj is None and iface is None:
            obj = next((o for (p, i), o in self._objects.items() if p == m.path), None)
        if obj is None:
            return self._error(m, "org.freedesktop.DBus.Error.UnknownMethod", f"{iface}.{m.member}")
        try:
            res = obj.handle(m.member, m.body, m)
        except DBusError as e:
            return self._error(m, e.name, e.message)
        except Exception as e:
            return self._error(m, "org.freedesktop.DBus.Error.Failed", str(e))
        if res is None:
            return self._reply(m)
        return self._reply(m, res[0], res[1])

    def _introspect(self, path):
        parts = ['<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN" '
                 '"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">', "<node>"]
        for (p, iface), obj in self._objects.items():
            if p == path:
                parts.append(getattr(obj, "INTROSPECT", f'<interface name="{iface}"/>'))
        # węzły potomne
        kids = {p[len(path):].strip("/").split("/")[0] for (p, _) in self._objects if p.startswith(path.rstrip("/") + "/") and p != path}
        for k in sorted(kids):
            if k:
                parts.append(f'<node name="{k}"/>')
        parts.append("</node>")
        return "".join(parts)
