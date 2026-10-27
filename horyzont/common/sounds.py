"""Oryginalny zestaw dźwięków systemowych syntetyzowany w locie (bez cudzych nagrań)."""
import math
import os
import random
import shutil
import struct
import subprocess
import wave

from .. import config

RATE = 22050

EVENTS = ["startup", "shutdown", "logon", "logoff", "error", "exclamation", "question", "notify", "balloon",
          "recycle", "menu", "device_connect", "device_disconnect", "battery_low"]
EVENT_LABELS = {
    "startup": ("Uruchamianie systemu", "Start Horyzont"),
    "shutdown": ("Zamykanie systemu", "Exit Horyzont"),
    "logon": ("Logowanie", "Logon"),
    "logoff": ("Wylogowanie", "Logoff"),
    "error": ("Błąd krytyczny", "Critical Stop"),
    "exclamation": ("Wykrzyknik", "Exclamation"),
    "question": ("Pytanie", "Question"),
    "notify": ("Powiadomienie", "Notify"),
    "balloon": ("Dymek powiadomienia", "Notification Balloon"),
    "recycle": ("Opróżnianie Kosza", "Empty Recycle Bin"),
    "menu": ("Polecenie menu", "Menu Command"),
    "device_connect": ("Podłączenie urządzenia", "Device Connect"),
    "device_disconnect": ("Odłączenie urządzenia", "Device Disconnect"),
    "battery_low": ("Niski poziom baterii", "Low Battery Alarm"),
}

# nazwy dźwięków w motywach freedesktop (np. /usr/share/sounds/freedesktop)
FD_NAMES = {
    "startup": ["desktop-login", "service-login"],
    "shutdown": ["desktop-logout", "service-logout"],
    "logon": ["desktop-login"],
    "logoff": ["desktop-logout"],
    "error": ["dialog-error", "suspend-error"],
    "exclamation": ["dialog-warning", "bell"],
    "question": ["dialog-question", "dialog-information"],
    "notify": ["message-new-instant", "dialog-information", "message"],
    "balloon": ["message", "dialog-information"],
    "recycle": ["trash-empty"],
    "menu": ["menu-click", "button-pressed"],
    "device_connect": ["device-added"],
    "device_disconnect": ["device-removed"],
    "battery_low": ["battery-low", "power-unplug"],
}

# warianty wbudowanych schematów: (przesunięcie wysokości dźwięku, głośność)
VARIANTS = {"horyzont": (1.0, 1.0), "zatoka": (0.75, 0.7), "krysztal": (1.5, 0.8)}


def _env(n, attack=0.01, release=0.3):
    out = []
    a = int(attack * RATE)
    r = int(release * RATE)
    for i in range(n):
        if i < a:
            v = i / max(1, a)
        elif i > n - r:
            v = max(0.0, (n - i) / max(1, r))
        else:
            v = 1.0
        out.append(v)
    return out


def _tone(freq, dur, vol=0.35, harmonics=(1.0, 0.35, 0.12), attack=0.01, release=None, bell=False):
    freq = freq * _PITCH[0]
    n = int(dur * RATE)
    env = _env(n, attack, release if release is not None else dur * 0.7)
    out = []
    for i in range(n):
        t = i / RATE
        decay = math.exp(-3.2 * t / dur) if bell else 1.0
        s = sum(h * math.sin(2 * math.pi * freq * (k + 1) * t) for k, h in enumerate(harmonics))
        out.append(s * env[i] * decay * vol)
    return out


def _mix(parts, total):
    buf = [0.0] * int(total * RATE)
    for start, samples in parts:
        o = int(start * RATE)
        for i, s in enumerate(samples):
            if o + i < len(buf):
                buf[o + i] += s
    return buf


_PITCH = [1.0]


def _synth(event, variant="horyzont"):
    pitch, vol = VARIANTS.get(variant, (1.0, 1.0))
    _PITCH[0] = pitch
    out = _synth_base(event)
    _PITCH[0] = 1.0
    return [x * vol for x in out]


def _synth_base(event):
    if event == "device_connect":
        return _mix([(0.0, _tone(523.25, 0.3, 0.22, bell=True)), (0.12, _tone(783.99, 0.4, 0.22, bell=True))], 0.6)
    if event == "device_disconnect":
        return _mix([(0.0, _tone(783.99, 0.3, 0.22, bell=True)), (0.12, _tone(523.25, 0.4, 0.22, bell=True))], 0.6)
    if event == "logoff":
        return _mix([(0.0, _tone(987.77, 0.8, 0.2, bell=True)), (0.15, _tone(659.25, 0.9, 0.2, bell=True))], 1.1)
    if event == "balloon":
        return _mix([(0.0, _tone(1318.5, 0.25, 0.16, bell=True)), (0.08, _tone(1567.98, 0.35, 0.14, bell=True))], 0.45)
    if event == "battery_low":
        return _mix([(t, _tone(1046.5, 0.14, 0.22, (1.0, 0.3))) for t in (0.0, 0.2, 0.4)], 0.6)
    if event == "startup":
        notes = [(0.0, 392.0), (0.18, 523.25), (0.36, 659.25), (0.54, 783.99), (0.72, 1046.5)]
        parts = [(t, _tone(f, 1.6 - t, 0.18, (1.0, 0.4, 0.2, 0.08), bell=True)) for t, f in notes]
        parts.append((0.0, _tone(130.81, 2.2, 0.12, (1.0, 0.5), attack=0.3, release=1.2)))
        return _mix(parts, 2.3)
    if event == "shutdown":
        notes = [(0.0, 1046.5), (0.2, 783.99), (0.4, 659.25), (0.6, 523.25)]
        return _mix([(t, _tone(f, 1.3 - t, 0.2, (1.0, 0.3, 0.1), bell=True)) for t, f in notes], 1.5)
    if event == "logon":
        return _mix([(0.0, _tone(659.25, 0.9, 0.22, bell=True)), (0.15, _tone(987.77, 0.9, 0.2, bell=True))], 1.1)
    if event == "error":
        return _mix([(0.0, _tone(220, 0.22, 0.3, (1.0, 0.6, 0.3))), (0.26, _tone(185, 0.3, 0.3, (1.0, 0.6, 0.3)))], 0.6)
    if event == "exclamation":
        return _mix([(0.0, _tone(880, 0.5, 0.25, (1.0, 0.3), bell=True)), (0.05, _tone(1318.5, 0.45, 0.12, bell=True))], 0.55)
    if event == "question":
        return _mix([(0.0, _tone(587.33, 0.3, 0.22, bell=True)), (0.16, _tone(880, 0.45, 0.22, bell=True))], 0.65)
    if event == "notify":
        return _tone(1174.66, 0.45, 0.22, (1.0, 0.2), bell=True)
    if event == "recycle":
        rnd = random.Random(1)
        n = int(0.5 * RATE)
        env = _env(n, 0.005, 0.3)
        return [(rnd.uniform(-1, 1) * 0.25 * env[i] * (0.5 + 0.5 * math.sin(i / 300.0))) for i in range(n)]
    if event == "menu":
        return _tone(1760, 0.06, 0.12, (1.0,), release=0.04)
    return _tone(880, 0.2)


def path_for(event, variant="horyzont"):
    d = os.path.join(config.CACHE_DIR, "sounds")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{event}-{variant}-v2.wav")
    if not os.path.exists(p):
        samples = _synth(event, variant)
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples))
    return p


# ------------------------------------------------------------------ schematy
def fd_themes():
    """Motywy dźwiękowe freedesktop zainstalowane w systemie: {katalog: nazwa}."""
    out = {}
    for base in ("/usr/share/sounds", "/usr/local/share/sounds", os.path.expanduser("~/.local/share/sounds")):
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            idx = os.path.join(base, d, "index.theme")
            if os.path.isfile(idx):
                name = d
                try:
                    with open(idx, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.startswith("Name="):
                                name = line.split("=", 1)[1].strip()
                                break
                except OSError:
                    pass
                out[os.path.join(base, d)] = name
    return out


def _fd_lookup(theme_dir, event, depth=0):
    for name in FD_NAMES.get(event, []):
        for sub in ("stereo", "mono", ""):
            for ext in (".oga", ".ogg", ".wav", ".flac"):
                p = os.path.join(theme_dir, sub, name + ext)
                if os.path.exists(p):
                    return p
    if depth < 3:
        try:
            with open(os.path.join(theme_dir, "index.theme"), encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("Inherits="):
                        for parent in line.split("=", 1)[1].strip().split(","):
                            pd = os.path.join(os.path.dirname(theme_dir), parent.strip())
                            r = _fd_lookup(pd, event, depth + 1)
                            if r:
                                return r
        except OSError:
            pass
    return None


def schemes():
    """[(klucz, nazwa)] dostępnych schematów."""
    from ..i18n import plain
    out = [("none", plain("snd_scheme_none")), ("horyzont", plain("snd_scheme_default")),
           ("zatoka", plain("snd_scheme_zatoka")), ("krysztal", plain("snd_scheme_krysztal"))]
    for d, name in fd_themes().items():
        out.append(("fd:" + d, name))
    for name in sorted(config.get("sound_schemes", {})):
        out.append(("user:" + name, name))
    return out


def scheme_sound(scheme, event):
    """Plik dźwięku zdarzenia w schemacie ('' = brak dźwięku)."""
    if scheme == "none":
        return ""
    if scheme.startswith("fd:"):
        return _fd_lookup(scheme[3:], event) or ""
    if scheme.startswith("user:"):
        return config.get("sound_schemes", {}).get(scheme[5:], {}).get(event, "")
    try:
        return path_for(event, scheme if scheme in VARIANTS else "horyzont")
    except OSError:
        return ""


def sound_for(event):
    """Dźwięk zdarzenia: wybór użytkownika (sound_events) albo schemat."""
    custom = config.get("sound_events", {})
    if event in custom:
        c = custom[event]
        return c if (c == "" or os.path.exists(c)) else scheme_sound(config.get("sound_scheme", "horyzont"), event)
    return scheme_sound(config.get("sound_scheme", "horyzont"), event)


def play_file(p):
    if not p or not os.path.exists(p):
        return
    for player in (["pw-play"], ["paplay"], ["aplay", "-q"]):
        if shutil.which(player[0]):
            if player[0] == "aplay" and not p.endswith(".wav"):
                continue
            try:
                subprocess.Popen(player + [p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                continue
            return


def play(event, force=False):
    """force — odtwarzaj także przy schemacie „Brak dźwięków” (podgląd w Panelu sterowania)."""
    p = sound_for(event)
    if not p and force:
        p = scheme_sound("horyzont", event)
    play_file(p)


def label(event):
    from ..i18n import lang_code
    l = EVENT_LABELS.get(event, (event, event))
    return l[0] if lang_code() == "pl" else l[1]
