"""Montowanie obrazów płyt (.iso, .img) jako wirtualnej stacji CD.

Używa udisks2 (udisksctl loop-setup + mount) — w sesji lokalnej nie wymaga hasła,
a jeśli polkit o nie poprosi, pojawia się okno uwierzytelniania Horyzontu.
Bez udisks2 montujemy przez pkexec (mount -o loop,ro).
"""
import glob
import os
import re
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

MOUNTABLE = (".iso", ".img")
DISC_FS = ("iso9660", "udf")


# ------------------------------------------------------------------ odczyt stanu
def _unescape(s):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


def mounts():
    """Lista (urządzenie, punkt montowania, system plików) z /proc/self/mountinfo."""
    out = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                try:
                    i = parts.index("-")
                except ValueError:
                    continue
                out.append((_unescape(parts[i + 2]), _unescape(parts[4]), parts[i + 1]))
    except OSError:
        pass
    return out


def is_mountable(path):
    return os.path.splitext(path)[1].lower() in MOUNTABLE and os.path.isfile(path)


def available():
    return bool(shutil.which("udisksctl") or shutil.which("pkexec"))


def loop_base(dev):
    """/dev/loop3p1 → /dev/loop3; dla innych urządzeń None."""
    m = re.match(r"^/dev/(loop\d+)", dev or "")
    return "/dev/" + m.group(1) if m else None


def backing_file(dev):
    """Plik obrazu podpięty pod urządzenie loop (albo None)."""
    base = loop_base(dev)
    if not base:
        return None
    try:
        with open(f"/sys/block/{os.path.basename(base)}/loop/backing_file", encoding="utf-8") as f:
            p = f.read().strip()
    except OSError:
        return None
    return p[:-10] if p.endswith(" (deleted)") else p


def loop_for(path):
    """Urządzenie loop, pod które podpięto dany plik (albo None)."""
    real = os.path.realpath(path)
    for d in sorted(glob.glob("/sys/block/loop*")):
        try:
            with open(os.path.join(d, "loop", "backing_file"), encoding="utf-8") as f:
                if os.path.realpath(f.read().strip()) == real:
                    return "/dev/" + os.path.basename(d)
        except OSError:
            continue
    return None


def mountpoints_of(loop):
    if not loop:
        return []
    return [mp for dev, mp, _fs in mounts() if dev == loop or (dev.startswith(loop + "p") and dev[len(loop) + 1:].isdigit())]


def mountpoint_for(path):
    mps = mountpoints_of(loop_for(path))
    return mps[0] if mps else None


def disc_mount(path):
    """Jeśli path to punkt montowania płyty lub obrazu — zwraca urządzenie, inaczej None."""
    path = os.path.realpath(path)
    for dev, mp, fs in mounts():
        if mp == path and (loop_base(dev) or fs in DISC_FS or dev.startswith("/dev/sr")):
            return dev
    return None


def setup_program(root):
    """Program instalacyjny płyty: open= z autorun.inf albo setup.exe/install.exe (bez względu na wielkość liter)."""
    try:
        names = {n.lower(): n for n in os.listdir(root)}
    except OSError:
        return None
    if "autorun.inf" in names:
        try:
            with open(os.path.join(root, names["autorun.inf"]), encoding="latin-1") as f:
                for line in f:
                    k, _, v = line.partition("=")
                    if k.strip().lower() == "open" and v.strip():
                        exe = v.strip().strip('"').split('" ')[0].split(" ")[0].replace("\\", "/")
                        cand = _find_ci(root, exe)
                        if cand:
                            return cand
        except OSError:
            pass
    for n in ("setup.exe", "install.exe", "autorun.exe", "setup.msi"):
        if n in names:
            return os.path.join(root, names[n])
    return None


def _find_ci(root, rel):
    cur = root
    for part in [p for p in rel.split("/") if p]:
        try:
            m = {n.lower(): n for n in os.listdir(cur)}
        except OSError:
            return None
        if part.lower() not in m:
            return None
        cur = os.path.join(cur, m[part.lower()])
    return cur if os.path.isfile(cur) else None


# ------------------------------------------------------------------ montowanie
def _run(args, timeout=180):
    try:
        # nowa sesja bez terminala: udisksctl nie próbuje pytać o hasło w konsoli, tylko przez agenta polkit Horyzontu
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           start_new_session=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def _candidates(loop):
    """Urządzenia z systemem plików: najpierw sam obraz płyty, potem partycje (obrazy hybrydowe)."""
    code, out = _run(["lsblk", "-nrpo", "NAME,FSTYPE", loop], 10)
    rows = []
    if code == 0:
        for line in out.splitlines():
            p = line.split()
            if len(p) >= 2:
                rows.append((p[0], p[1]))
    if not rows:
        rows = [(loop, "")]
    if not any(fs for _d, fs in rows):
        # brak bazy udev (lsblk nie zna systemów plików) — próbujemy po kolei: cały obraz, potem partycje
        return [d for d, _fs in rows]
    disc = [d for d, fs in rows if fs in DISC_FS]
    other = [d for d, fs in rows if fs and fs not in DISC_FS and fs not in ("swap", "LVM2_member", "crypto_LUKS")]
    return disc + other


def _settle():
    if shutil.which("udevadm"):
        _run(["udevadm", "settle", "-t", "3"], 5)
    else:
        time.sleep(0.4)


def mount(path):
    """Podpina obraz i montuje go. Zwraca (punkt montowania, błąd). Wywoływać poza wątkiem okna."""
    path = os.path.realpath(path)
    if not shutil.which("udisksctl"):
        return None, "NO_UDISKS"
    loop = loop_for(path)
    if loop:
        mps = mountpoints_of(loop)
        if mps:
            return mps[0], ""
    else:
        code, out = _run(["udisksctl", "loop-setup", "-r", "-f", path])
        m = re.search(r"(/dev/loop\d+)", out)
        if code != 0 or not m:
            return None, out or "udisksctl loop-setup"
        loop = m.group(1)
    _settle()
    # menedżer nośników (np. gvfs) mógł już zamontować obraz sam
    for _ in range(3):
        mps = mountpoints_of(loop)
        if mps:
            return mps[0], ""
        time.sleep(0.15)
    errors = []
    for dev in _candidates(loop):
        code, out = _run(["udisksctl", "mount", "-b", dev])
        mps = mountpoints_of(loop)
        if mps:
            return mps[0], ""
        if code != 0:
            errors.append(out)
    _run(["udisksctl", "loop-delete", "-b", loop], 20)
    return None, "\n".join(e for e in errors if e) or "NO_FS"


def eject(dev_or_path):
    """Odmontowuje obraz i zwalnia urządzenie loop. Zwraca (ok, błąd)."""
    loop = loop_base(dev_or_path) or loop_for(dev_or_path)
    if not loop:
        for dev, mp, _fs in mounts():
            if mp == dev_or_path:
                loop = loop_base(dev)
                break
    if not loop:
        return False, "loop?"
    err = ""
    for dev, mp, _fs in mounts():
        if loop_base(dev) == loop:
            if shutil.which("udisksctl"):
                code, out = _run(["udisksctl", "unmount", "-b", dev], 60)
            else:
                code, out = 1, "NO_UDISKS"
            if code != 0:
                err = out
    if mountpoints_of(loop):
        return False, err or "busy"
    if shutil.which("udisksctl"):
        _run(["udisksctl", "loop-delete", "-b", loop], 20)
    return True, ""


# ------------------------------------------------------------------ bez udisks2: pkexec
def _fallback_dir(path):
    user = os.environ.get("USER") or os.path.basename(os.path.expanduser("~"))
    name = re.sub(r"[^\w.\- ]", "_", os.path.splitext(os.path.basename(path))[0])[:60] or "cdrom"
    return f"/run/media/{user}/{name}"


def mount_privileged(path, parent=None):
    """Montowanie przez pkexec (okno hasła Horyzontu). Wywoływać w wątku okna."""
    from .privileged import run_privileged
    mp = _fallback_dir(path)
    ok, out = run_privileged(["sh", "-c", 'mkdir -p "$1" && mount -o loop,ro "$2" "$1"', "sh", mp, os.path.realpath(path)],
                             parent, show_errors=False)
    return (mp, "") if ok else (None, out)


def eject_privileged(mountpoint, parent=None):
    from .privileged import run_privileged
    ok, out = run_privileged(["sh", "-c", 'umount "$1" && rmdir "$1" 2>/dev/null; true', "sh", mountpoint],
                             parent, show_errors=False)
    return ok, out


# ------------------------------------------------------------------ w tle
class _Worker(QObject):
    done = Signal(str, str)

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        # połączenie z metodą obiektu z wątku okna → sygnał z wątku roboczego trafia do kolejki zdarzeń
        self.done.connect(self._finish)

    @Slot(str, str)
    def _finish(self, mp, err):
        _ALIVE.discard(self)
        self.callback(mp, err)

    def start(self, fn, *args):
        def work():
            try:
                mp, err = fn(*args)
            except Exception as e:  # noqa: BLE001
                mp, err = None, str(e)
            self.done.emit(str(mp) if mp else "", err or "")
        threading.Thread(target=work, daemon=True).start()


_ALIVE = set()


def run_async(fn, args, callback):
    """Uruchamia fn(*args) → (wynik, błąd) w wątku; callback(wynik, błąd) w wątku okna."""
    w = _Worker(callback)
    _ALIVE.add(w)
    w.start(fn, *args)
