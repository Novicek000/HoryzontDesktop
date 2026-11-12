"""Systemowy układ XKB. Nazwy keymap konsoli (np. pl2) nie są nazwami XKB."""
import os
from pathlib import Path
import re
import shlex

VCONSOLE = "/etc/vconsole.conf"
XORG = "/etc/X11/xorg.conf.d/00-keyboard.conf"
DEBIAN = "/etc/default/keyboard"
LOCALE = "/etc/locale.conf"
FIELDS = {"layout": "XKBLAYOUT", "model": "XKBMODEL", "variant": "XKBVARIANT", "options": "XKBOPTIONS"}


def assignments(path):
    values = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and re.fullmatch(r"[A-Z_]+", key.strip()):
                parts = shlex.split(value, comments=True)
                values[key.strip()] = " ".join(parts)
    except (OSError, ValueError):
        pass
    return values


def _xkb(values):
    return {field: values.get(key, "") for field, key in FIELDS.items()}


def system_settings():
    """Najpierw jawne ustawienia XKB instalatora/localed, potem konwersja konsoli."""
    console = assignments(VCONSOLE)
    if console.get("XKBLAYOUT"):
        return _xkb(console)
    try:
        text = Path(XORG).read_text(encoding="utf-8")
        values = dict(re.findall(r'^\s*Option\s+"(Xkb\w+)"\s+"([^"]*)"', text, re.M | re.I))
        values = {key.upper(): value for key, value in values.items()}
        if values.get("XKBLAYOUT"):
            return _xkb(values)
    except OSError:
        pass
    values = assignments(DEBIAN)
    if values.get("XKBLAYOUT"):
        return _xkb(values)
    keymap = console.get("KEYMAP", "")
    known = {"pl2": ("pl", ""), "pl3": ("pl", "qwertz"), "pl": ("pl", ""),
             "uk": ("gb", ""), "us": ("us", ""), "de-latin1-nodeadkeys": ("de", "nodeadkeys")}
    if keymap in known:
        layout, variant = known[keymap]
    else:
        prefix = keymap.split("-", 1)[0]
        if prefix in {"de", "fr", "es", "it", "cz", "sk", "ua", "ru", "lt", "hu", "gb"}:
            layout, variant = prefix, ""
        else:
            locale = assignments(LOCALE).get("LANG") or os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG", "")
            language = locale.split("_", 1)[0].split(".", 1)[0]
            language = {"cs": "cz", "uk": "ua"}.get(language, language)
            layout = "gb" if locale.startswith("en_GB") else language if language in {"pl", "de", "fr", "es", "it", "cz", "sk", "ua", "ru", "lt", "hu"} else "us"
            variant = ""
    return {"layout": layout, "variant": variant, "model": "", "options": ""}


def effective_settings(layout=""):
    # Ręczny wybór nie może odziedziczyć wariantu innego układu, np. polskiego qwertz.
    return {"layout": layout, "model": "", "variant": "", "options": ""} if layout else system_settings()
