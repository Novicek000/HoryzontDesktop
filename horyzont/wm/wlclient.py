"""Minimalny klient protokołu Wayland w czystym Pythonie.

Wystarcza do obsługi listy okien (wlr-foreign-toplevel-management) bez
zewnętrznych modułów — nie wymaga pywayland ani kompilowanych rozszerzeń.
Obsługuje tylko argumenty bez deskryptorów plików, co dla tego protokołu
w zupełności wystarcza.
"""
import os
import socket
import struct

SERVER_ID_START = 0xFF000000


class WaylandError(Exception):
    pass


def _socket_path():
    name = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    if name.startswith("/"):
        return name
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise WaylandError("brak XDG_RUNTIME_DIR")
    return os.path.join(runtime, name)


def pack_string(s):
    if s is None:
        return struct.pack("=I", 0)
    b = s.encode("utf-8") + b"\0"
    pad = (4 - len(b) % 4) % 4
    return struct.pack("=I", len(b)) + b + b"\0" * pad


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def uint(self):
        v = struct.unpack_from("=I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def int(self):
        v = struct.unpack_from("=i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def string(self):
        n = self.uint()
        if n == 0:
            return None
        raw = self.data[self.pos:self.pos + n - 1]
        self.pos += (n + 3) & ~3
        return raw.decode("utf-8", "replace")

    def array(self):
        n = self.uint()
        raw = bytes(self.data[self.pos:self.pos + n])
        self.pos += (n + 3) & ~3
        return raw


class Connection:
    """Połączenie z kompozytorem: rejestr obiektów, wysyłanie żądań, odbiór zdarzeń."""

    def __init__(self):
        fd = os.environ.get("WAYLAND_SOCKET")
        if fd and fd.isdigit():
            self.sock = socket.socket(fileno=int(fd))
        else:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
            self.sock.connect(_socket_path())
        self.sock.setblocking(False)
        self._next_id = 2
        self.handlers = {1: self._display_event}   # id obiektu -> funkcja(opcode, Reader)
        self._buf = bytearray()
        self._out = bytearray()
        self.error = None
        self._callbacks = {}

    def fileno(self):
        return self.sock.fileno()

    # --- wysyłanie
    def new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def request(self, obj, opcode, payload=b""):
        size = 8 + len(payload)
        self._out += struct.pack("=II", obj, (size << 16) | opcode) + payload
        self.flush()

    def flush(self):
        while self._out:
            try:
                n = self.sock.send(self._out)
            except BlockingIOError:
                return
            except OSError as e:
                raise WaylandError(str(e))
            del self._out[:n]

    # --- wl_display
    def get_registry(self, handler):
        rid = self.new_id()
        self.handlers[rid] = handler
        self.request(1, 1, struct.pack("=I", rid))
        return rid

    def bind(self, registry, name, interface, version, handler):
        oid = self.new_id()
        self.handlers[oid] = handler
        self.request(registry, 0, struct.pack("=I", name) + pack_string(interface) + struct.pack("=II", version, oid))
        return oid

    def sync(self, callback):
        cid = self.new_id()
        self.handlers[cid] = lambda op, r: (self.handlers.pop(cid, None), callback())
        self.request(1, 0, struct.pack("=I", cid))
        return cid

    def _display_event(self, opcode, r):
        if opcode == 0:
            obj, code, msg = r.uint(), r.uint(), r.string()
            self.error = f"błąd protokołu (obiekt {obj}, kod {code}): {msg}"
            raise WaylandError(self.error)
        elif opcode == 1:
            self.handlers.pop(r.uint(), None)

    # --- odbiór
    def read_events(self):
        """Czyta dostępne dane i rozsyła zdarzenia. Zwraca False po rozłączeniu."""
        while True:
            try:
                chunk = self.sock.recv(65536)
            except BlockingIOError:
                break
            except OSError as e:
                raise WaylandError(str(e))
            if not chunk:
                raise WaylandError("kompozytor zamknął połączenie")
            self._buf += chunk
            if len(chunk) < 65536:
                break
        self._dispatch_buffer()
        return True

    def _dispatch_buffer(self):
        buf = self._buf
        pos = 0
        while len(buf) - pos >= 8:
            obj, word = struct.unpack_from("=II", buf, pos)
            size, opcode = word >> 16, word & 0xFFFF
            if size < 8:
                raise WaylandError("uszkodzona wiadomość")
            if len(buf) - pos < size:
                break
            body = bytes(buf[pos + 8:pos + size])
            pos += size
            h = self.handlers.get(obj)
            if h is not None:
                h(opcode, Reader(body))
        del buf[:pos]

    def roundtrip(self, timeout=2.0):
        """Wysyła sync i czeka (blokująco) na odpowiedź."""
        import select
        done = []
        self.sync(lambda: done.append(True))
        while not done:
            self.flush()
            r, _, _ = select.select([self.sock], [], [], timeout)
            if not r:
                raise WaylandError("brak odpowiedzi kompozytora")
            self.read_events()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
