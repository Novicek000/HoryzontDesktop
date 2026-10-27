"""Pomocnicze funkcje systemowe: głośność, sieć, zasilanie, informacje o systemie."""
import os
import platform
import re
import shutil
import socket
import subprocess


def _run(args, timeout=3):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)


# ------------------------------------------------------------------ głośność
def volume_get():
    """Zwraca (głośność 0-100, wyciszony) albo None, gdy brak sterowania dźwiękiem."""
    if shutil.which("wpctl"):
        rc, out, _ = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        m = re.search(r"Volume:\s*([\d.]+)", out)
        if rc == 0 and m:
            return int(round(float(m.group(1)) * 100)), "MUTED" in out
    if shutil.which("pactl"):
        rc, out, _ = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        m = re.search(r"(\d+)%", out)
        rc2, out2, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
        if rc == 0 and m:
            return int(m.group(1)), "yes" in out2.lower() or "tak" in out2.lower()
    return None


def volume_set(value):
    value = max(0, min(100, int(value)))
    if shutil.which("wpctl"):
        _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value / 100:.2f}"])
    elif shutil.which("pactl"):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"])


def volume_mute(muted):
    if shutil.which("wpctl"):
        _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if muted else "0"])
    elif shutil.which("pactl"):
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"])


def audio_devices():
    """Lista (nazwa urządzenia wyjściowego, nazwa wejściowego)."""
    out_name = in_name = "—"
    if shutil.which("wpctl"):
        rc, out, _ = _run(["wpctl", "status"])
        sect = None
        for line in out.splitlines():
            if "Sinks:" in line:
                sect = "sink"
                continue
            if "Sources:" in line:
                sect = "source"
                continue
            if "Filters:" in line or "Streams:" in line:
                sect = None
            m = re.search(r"\*\s+\d+\.\s+(.+?)(\s+\[vol.*)?$", line)
            if m and sect == "sink":
                out_name = m.group(1).strip()
            elif m and sect == "source":
                in_name = m.group(1).strip()
    return out_name, in_name


# ------------------------------------------------------------------ sieć
def network_state():
    """'connected', 'disconnected' albo None (nieznany)."""
    if shutil.which("nmcli"):
        rc, out, _ = _run(["nmcli", "-t", "-f", "STATE", "general"])
        if rc == 0:
            s = out.strip()
            return "connected" if s.startswith("connected") else "disconnected"
    try:
        import psutil
        for name, st in psutil.net_if_stats().items():
            if name != "lo" and st.isup:
                return "connected"
        return "disconnected"
    except Exception:
        return None


def network_connections():
    """Lista słowników: name, type, device, state, ip."""
    out = []
    if shutil.which("nmcli"):
        rc, txt, _ = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
        for line in txt.splitlines():
            parts = line.split(":")
            if len(parts) < 4 or parts[1] in ("loopback", "bridge", "tun", "wifi-p2p"):
                continue
            out.append({"device": parts[0], "type": parts[1], "state": parts[2], "name": parts[3] or parts[0]})
    else:
        try:
            import psutil
            stats = psutil.net_if_stats()
            for name, st in stats.items():
                if name == "lo":
                    continue
                out.append({"device": name, "type": "wifi" if name.startswith("wl") else "ethernet",
                            "state": "connected" if st.isup else "disconnected", "name": name})
        except Exception:
            pass
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        for c in out:
            for a in addrs.get(c["device"], []):
                if a.family == socket.AF_INET:
                    c["ip"] = a.address
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ zasilanie i sesja
def battery():
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return None
        return int(b.percent), bool(b.power_plugged)
    except Exception:
        return None


def _play_and_wait(event, seconds=1.6):
    """Dźwięk zamykania/wylogowania — krótko czekamy, żeby zdążył zabrzmieć."""
    try:
        from . import sounds
        p = sounds.sound_for(event)
        if p:
            sounds.play_file(p)
            import time
            time.sleep(seconds)
    except Exception:
        pass


def power_action(action):
    if action in ("turnoff", "restart"):
        _play_and_wait("shutdown")
    cmds = {
        "standby": [["systemctl", "suspend"], ["loginctl", "suspend"]],
        "turnoff": [["systemctl", "poweroff"], ["loginctl", "poweroff"]],
        "restart": [["systemctl", "reboot"], ["loginctl", "reboot"]],
        "hibernate": [["systemctl", "hibernate"]],
    }[action]
    for c in cmds:
        if shutil.which(c[0]):
            subprocess.Popen(c, start_new_session=True)
            return True
    return False


def logoff():
    """Kończy sesję labwc (wylogowanie)."""
    _play_and_wait("logoff", 1.2)
    pid = os.environ.get("LABWC_PID")
    if pid:
        try:
            os.kill(int(pid), 15)
            return True
        except Exception:
            pass
    if shutil.which("labwc"):
        subprocess.Popen(["labwc", "--exit"], start_new_session=True)
        return True
    sid = os.environ.get("XDG_SESSION_ID")
    if sid and shutil.which("loginctl"):
        subprocess.Popen(["loginctl", "terminate-session", sid], start_new_session=True)
        return True
    return False


def lock_screen():
    for c in (["swaylock", "-f", "-c", "1f5f6a"], ["gtklock"], ["waylock"], ["loginctl", "lock-session"]):
        if shutil.which(c[0]):
            subprocess.Popen(c, start_new_session=True)
            return True
    return False


def switch_user():
    for c in (["gdmflexiserver"], ["dm-tool", "switch-to-greeter"], ["qdbus", "org.kde.ksmserver"]):
        if shutil.which(c[0]):
            subprocess.Popen(c, start_new_session=True)
            return True
    return lock_screen()


# ------------------------------------------------------------------ informacje
def os_release():
    info = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    info[k] = v.strip('"')
    except OSError:
        pass
    return info


def os_name():
    r = os_release()
    return r.get("PRETTY_NAME") or r.get("NAME") or platform.system()


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def mem_total():
    try:
        import psutil
        return psutil.virtual_memory().total
    except Exception:
        return 0


def hostname():
    return socket.gethostname()


def user_full_name():
    import pwd
    try:
        pw = pwd.getpwuid(os.getuid())
        name = pw.pw_gecos.split(",")[0].strip()
        return name or pw.pw_name
    except Exception:
        return os.environ.get("USER", "user")


def user_login():
    import pwd
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return os.environ.get("USER", "user")


def is_admin():
    import grp
    try:
        groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
        return os.getuid() == 0 or "wheel" in groups or "sudo" in groups or "admin" in groups
    except Exception:
        return False


def human_size(n, short=False):
    """Rozmiar w formacie '1,23 GB' (przecinek dziesiętny w polskiej wersji)."""
    from ..i18n import lang_code
    units = ["bajtów", "KB", "MB", "GB", "TB"] if lang_code() == "pl" else ["bytes", "KB", "MB", "GB", "TB"]
    n = float(n)
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    if i == 0:
        s = f"{int(n)} {units[0]}"
    elif n >= 100:
        s = f"{n:.0f} {units[i]}"
    elif n >= 10:
        s = f"{n:.1f} {units[i]}"
    else:
        s = f"{n:.2f} {units[i]}"
    if lang_code() == "pl":
        s = s.replace(".", ",")
    return s


def group_digits(n):
    from ..i18n import lang_code
    s = f"{int(n):,}"
    return s.replace(",", " " if lang_code() == "pl" else ",")
