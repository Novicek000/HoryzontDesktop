"""Lista okien dla paska zadań.

Na Waylandzie korzystamy z protokołu wlr-foreign-toplevel-management,
który obsługuje labwc (i inne kompozytory oparte na wlroots).
"""
import os
import struct
import sys

from PySide6.QtCore import QObject, QSocketNotifier, Signal


class Toplevel:
    _next = 1

    def __init__(self, handle=None):
        self.uid = Toplevel._next
        Toplevel._next += 1
        self.handle = handle
        self.title = ""
        self.app_id = ""
        self.maximized = False
        self.minimized = False
        self.activated = False
        self.fullscreen = False
        self.parent = None
        self.done = False

    def __repr__(self):
        return f"<Toplevel {self.uid} {self.app_id!r} {self.title!r}{' A' if self.activated else ''}{' m' if self.minimized else ''}>"


class Backend(QObject):
    added = Signal(object)
    removed = Signal(object)
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.toplevels = []

    available = False

    def activate(self, tl):
        pass

    def minimize(self, tl):
        pass

    def unminimize(self, tl):
        pass

    def maximize(self, tl):
        pass

    def unmaximize(self, tl):
        pass

    def close(self, tl):
        pass

    def active(self):
        for t in self.toplevels:
            if t.activated:
                return t
        return None


class _Handle:
    """Uchwyt okna zwlr_foreign_toplevel_handle_v1."""

    def __init__(self, conn, oid):
        self.conn = conn
        self.oid = oid

    def _req(self, opcode, payload=b""):
        self.conn.request(self.oid, opcode, payload)

    def set_maximized(self):
        self._req(0)

    def unset_maximized(self):
        self._req(1)

    def set_minimized(self):
        self._req(2)

    def unset_minimized(self):
        self._req(3)

    def activate(self, seat):
        self._req(4, struct.pack("=I", seat))

    def close(self):
        self._req(5)

    def destroy(self):
        self._req(7)


class WaylandBackend(Backend):
    """Lista okien przez wlr-foreign-toplevel-management (własny klient Wayland, bez pywayland)."""

    def __init__(self):
        super().__init__()
        from . import wlclient
        self._wl = wlclient
        self.conn = wlclient.Connection()
        self.manager = None
        self.seat = None
        self._by_id = {}
        self._globals = {}

        def on_registry(opcode, r):
            if opcode == 0:
                name, iface, version = r.uint(), r.string(), r.uint()
                self._globals[name] = (iface, version)

        self.registry = self.conn.get_registry(on_registry)
        self.conn.roundtrip()
        for name, (iface, version) in self._globals.items():
            if iface == "zwlr_foreign_toplevel_manager_v1" and self.manager is None:
                self.manager = self.conn.bind(self.registry, name, iface, min(version, 3), self._on_manager)
            elif iface == "wl_seat" and self.seat is None:
                self.seat = self.conn.bind(self.registry, name, iface, min(version, 5), lambda op, r: None)
        if self.manager is None:
            self.conn.close()
            raise RuntimeError("kompozytor nie obsługuje wlr-foreign-toplevel-management")
        self.conn.roundtrip()
        self._notifier = QSocketNotifier(self.conn.fileno(), QSocketNotifier.Read)
        self._notifier.activated.connect(self._dispatch)
        self.available = True

    def _dispatch(self, *_):
        try:
            self.conn.read_events()
            self.conn.flush()
        except Exception as e:
            print("horyzont: błąd połączenia Wayland:", e, file=sys.stderr)
            self._notifier.setEnabled(False)
            for tl in list(self.toplevels):
                self.toplevels.remove(tl)
                self.removed.emit(tl)

    def _on_manager(self, opcode, r):
        if opcode == 0:
            oid = r.uint()
            self._new_toplevel(oid)

    def _new_toplevel(self, oid):
        tl = Toplevel(_Handle(self.conn, oid))
        self._by_id[oid] = tl

        def on_event(opcode, r):
            if opcode == 0:
                tl.title = r.string() or ""
            elif opcode == 1:
                tl.app_id = r.string() or ""
            elif opcode == 4:
                raw = r.array()
                vals = list(struct.unpack(f"={len(raw) // 4}I", raw)) if raw else []
                tl.maximized = 0 in vals
                tl.minimized = 1 in vals
                tl.activated = 2 in vals
                tl.fullscreen = 3 in vals
            elif opcode == 5:
                if not tl.done:
                    tl.done = True
                    self.toplevels.append(tl)
                    self.added.emit(tl)
                else:
                    self.changed.emit(tl)
            elif opcode == 6:
                if tl in self.toplevels:
                    self.toplevels.remove(tl)
                    self.removed.emit(tl)
                self._by_id.pop(oid, None)
                try:
                    tl.handle.destroy()
                except Exception:
                    pass
                self.conn.handlers.pop(oid, None)
            elif opcode == 7:
                pid = r.uint()
                tl.parent = self._by_id.get(pid) if pid else None

        self.conn.handlers[oid] = on_event

    def _req(self, fn):
        try:
            fn()
            self.conn.flush()
        except Exception as e:
            print("horyzont: żądanie Wayland nie powiodło się:", e, file=sys.stderr)

    def activate(self, tl):
        if self.seat is not None:
            def go():
                if tl.minimized:
                    tl.handle.unset_minimized()
                tl.handle.activate(self.seat)
            self._req(go)

    def minimize(self, tl):
        self._req(tl.handle.set_minimized)

    def unminimize(self, tl):
        self._req(tl.handle.unset_minimized)

    def maximize(self, tl):
        self._req(tl.handle.set_maximized)

    def unmaximize(self, tl):
        self._req(tl.handle.unset_maximized)

    def close(self, tl):
        self._req(tl.handle.close)


class FakeBackend(Backend):
    """Do testów i zrzutów ekranu: okna z HORYZONT_FAKE_WINDOWS="Tytuł|app_id;..."."""

    def __init__(self, spec):
        super().__init__()
        self.available = True
        for i, part in enumerate(s for s in spec.split(";") if s):
            title, _, app = part.partition("|")
            tl = Toplevel()
            tl.title, tl.app_id = title, app
            tl.done = True
            tl.activated = i == 0
            self.toplevels.append(tl)

    def activate(self, tl):
        for t in self.toplevels:
            t.activated = t is tl
            self.changed.emit(t)
        tl.minimized = False

    def minimize(self, tl):
        tl.minimized = True
        tl.activated = False
        self.changed.emit(tl)

    def unminimize(self, tl):
        tl.minimized = False
        self.changed.emit(tl)

    def close(self, tl):
        self.toplevels.remove(tl)
        self.removed.emit(tl)


def create():
    spec = os.environ.get("HORYZONT_FAKE_WINDOWS")
    if spec is not None:
        return FakeBackend(spec)
    if os.environ.get("WAYLAND_DISPLAY"):
        try:
            return WaylandBackend()
        except Exception as e:
            print("horyzont: brak listy okien:", e, file=sys.stderr)
    return Backend()
