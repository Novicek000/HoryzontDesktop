"""Konfiguracja kompozytora labwc dla sesji Horyzont.

Pliki trafiają do ~/.config/horyzont/labwc (osobno od ewentualnej
konfiguracji labwc użytkownika) i są generowane na nowo przy każdym starcie
sesji oraz po zmianie ustawień myszy/klawiatury.
"""
import os
import shlex
import signal
import sys
from xml.sax.saxutils import escape, quoteattr

from .. import config
from ..theme.builtin import SCHEMES

LABWC_DIR = os.path.join(config.CONFIG_DIR, "labwc")
THEME_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "themes",
                         "Horyzont", "openbox-3")


def _cmd(*args):
    """Polecenie uruchamiające moduł horyzont tym samym interpreterem."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    py = shlex.quote(sys.executable)
    fast = " -S" if args and args[0] == "shell-cmd" else ""   # bez site: krótszy start skrótów klawiszowych
    return f"env PYTHONPATH={shlex.quote(root)} {py}{fast} -m horyzont " + " ".join(shlex.quote(a) for a in args)


PLACEMENT_FILE = os.path.join(config.CACHE_DIR, "placement.json")


def load_placement():
    import json
    try:
        with open(PLACEMENT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_placement(screen_w, screen_h, taskbar_h, windows):
    """Zapamiętuje rozmiar ekranu i pozycje okien powłoki (menu Start, Uruchamianie)
    — reguły okien labwc ustawiają je dokładnie tam, gdzie w klasycznym pulpicie."""
    import json
    data = {"screen": [screen_w, screen_h], "taskbar_h": taskbar_h,
            "windows": {k: [int(v[0]), int(v[1])] for k, v in windows.items()}}
    if data == load_placement():
        return False
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(PLACEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return True


def _placed_rules(windows):
    out = ""
    for title, (x, y) in windows.items():
        on_top = title == "horyzont-startmenu"
        skip = ' skipTaskbar="yes" skipWindowSwitcher="yes"' if on_top else ""
        top = '\n      <action name="ToggleAlwaysOnTop"/>' if on_top else ""
        out += (f'\n    <windowRule identifier="horyzont-shell" title={quoteattr(title)}{skip} serverDecoration="no">'
                f'\n      <action name="MoveTo" x="{x}" y="{y}"/>{top}'
                f'\n    </windowRule>')
    return out


def rc_xml(screen_w=None, screen_h=None, taskbar_h=None):
    pl = load_placement()
    if not screen_w or not screen_h:
        screen_w, screen_h = (pl.get("screen") or [None, None])[:2]
    if taskbar_h is None:
        taskbar_h = pl.get("taskbar_h", 30)
    dbl = int(config.get("mouse_double_click", 500))
    speed = float(config.get("mouse_speed", 0.0))
    natural = "yes" if config.get("mouse_natural_scroll", False) else "no"
    left = "yes" if config.get("mouse_left_handed", False) else "no"
    rate = int(config.get("keyboard_repeat_rate", 25))
    delay = int(config.get("keyboard_repeat_delay", 600))
    layout = config.get("keyboard_layout", "")
    tb_rules = ""
    if screen_w and screen_h:
        tb_rules = f"""
    <windowRule identifier="horyzont-shell" title="horyzont-taskbar" skipTaskbar="yes" skipWindowSwitcher="yes"
                fixedPosition="yes" serverDecoration="no" ignoreFocusRequest="yes">
      <action name="MoveTo" x="0" y="{screen_h - taskbar_h}"/>
      <action name="ToggleAlwaysOnTop"/>
      <action name="ToggleOmnipresent"/>
    </windowRule>
    <windowRule identifier="horyzont-shell" title="horyzont-desktop" skipTaskbar="yes" skipWindowSwitcher="yes"
                fixedPosition="yes" serverDecoration="no">
      <action name="MoveTo" x="0" y="0"/>
      <action name="ToggleAlwaysOnBottom"/>
      <action name="ToggleOmnipresent"/>
    </windowRule>""" + _placed_rules(pl.get("windows", {}))
    margin_bottom = 0 if config.get("taskbar_autohide", False) else taskbar_h
    font = escape(config.get("labwc_font", "Tahoma"))
    return f"""<?xml version="1.0"?>
<!-- Wygenerowane przez Horyzont — zmiany zostaną nadpisane przy następnym starcie sesji -->
<labwc_config>
  <core>
    <decoration>server</decoration>
    <gap>0</gap>
  </core>
  <placement><policy>cascade</policy></placement>
  <theme>
    <name>Horyzont</name>
    <cornerRadius>{0 if config.get('visual_style') == 'classic' else 7}</cornerRadius>
    <keepBorder>no</keepBorder>
    <font place="ActiveWindow"><name>{font}</name><size>9</size><weight>bold</weight></font>
    <font place="InactiveWindow"><name>{font}</name><size>9</size><weight>bold</weight></font>
    <font place="MenuItem"><name>{font}</name><size>8</size></font>
    <font place="OnScreenDisplay"><name>{font}</name><size>9</size></font>
  </theme>
  <windowSwitcher show="yes" preview="yes" outlines="yes">
    <fields>
      <field content="title" width="100%"/>
    </fields>
  </windowSwitcher>
  <margin bottom="{margin_bottom}"/>
  <keyboard>
    <default/>
    <repeatRate>{rate}</repeatRate>
    <repeatDelay>{delay}</repeatDelay>
    <keybind key="Super_L" onRelease="yes"><action name="Execute" command={quoteattr(_cmd('shell-cmd', 'start-menu'))}/></keybind>
    <keybind key="W-e"><action name="Execute" command={quoteattr(_cmd('explorer', 'horyzont:computer'))}/></keybind>
    <keybind key="W-r"><action name="Execute" command={quoteattr(_cmd('shell-cmd', 'run'))}/></keybind>
    <keybind key="W-d"><action name="Execute" command={quoteattr(_cmd('shell-cmd', 'show-desktop'))}/></keybind>
    <keybind key="W-m"><action name="Execute" command={quoteattr(_cmd('shell-cmd', 'show-desktop'))}/></keybind>
    <keybind key="W-l"><action name="Execute" command={quoteattr(_cmd('shell-cmd', 'lock'))}/></keybind>
    <keybind key="W-f"><action name="Execute" command={quoteattr(_cmd('explorer', '--search'))}/></keybind>
    <keybind key="W-Pause"><action name="Execute" command={quoteattr(_cmd('control', 'system'))}/></keybind>
    <keybind key="C-S-Escape"><action name="Execute" command={quoteattr(_cmd('taskmgr'))}/></keybind>
    <keybind key="C-A-Delete"><action name="Execute" command={quoteattr(_cmd('taskmgr'))}/></keybind>
    <keybind key="Print"><action name="Execute" command="sh -c 'mkdir -p ~/Pictures &amp;&amp; grim ~/Pictures/zrzut-$(date +%Y%m%d-%H%M%S).png'"/></keybind>
    <keybind key="A-F4"><action name="Close"/></keybind>
    <keybind key="A-space"><action name="ShowMenu" menu="client-menu"/></keybind>
  </keyboard>
  <mouse>
    <default/>
    <doubleClickTime>{dbl}</doubleClickTime>
  </mouse>
  <libinput>
    <device category="default">
      <pointerSpeed>{speed:.2f}</pointerSpeed>
      <naturalScroll>{natural}</naturalScroll>
      <leftHanded>{left}</leftHanded>
      <accelProfile>{"flat" if config.get("mouse_accel_flat", False) else "adaptive"}</accelProfile>
      <tap>{"yes" if config.get("touchpad_tap", True) else "no"}</tap>
    </device>
  </libinput>
  <windowRules>
    <windowRule identifier="horyzont-*" serverDecoration="no"/>{tb_rules}
  </windowRules>
</labwc_config>
"""


def environment_file():
    lines = [
        "XDG_CURRENT_DESKTOP=Horyzont:wlroots",
        "XDG_SESSION_DESKTOP=horyzont",
        "QT_QPA_PLATFORM=wayland;xcb",
        "QT_QPA_PLATFORMTHEME=",
        "MOZ_ENABLE_WAYLAND=1",
        "SDL_VIDEODRIVER=wayland,x11",
        "_JAVA_AWT_WM_NONREPARENTING=1",
    ]
    theme = config.get("cursor_theme") or ("Horyzont" if os.path.isdir(os.path.expanduser("~/.icons/Horyzont/cursors")) else "")
    if theme:
        lines.append(f"XCURSOR_THEME={theme}")
    lines.append(f"XCURSOR_SIZE={int(config.get('cursor_size', 24))}")
    layout = config.get("keyboard_layout", "")
    if layout:
        lines.append(f"XKB_DEFAULT_LAYOUT={layout}")
    else:
        lines.append("XKB_DEFAULT_LAYOUT=" + _system_layout())
    return "\n".join(lines) + "\n"


def _system_layout():
    """Układ klawiatury z ustawień systemu (localectl) — domyślnie 'pl'."""
    try:
        with open("/etc/vconsole.conf", encoding="utf-8") as f:
            for line in f:
                if line.startswith("KEYMAP="):
                    km = line.split("=", 1)[1].strip().strip('"')
                    return km.split("-")[0] or "pl"
    except OSError:
        pass
    return "pl" if os.environ.get("LANG", "").startswith("pl") else "us"


def autostart_file():
    return "\n".join([
        "# Horyzont — start powłoki",
        "mkdir -p \"${XDG_CACHE_HOME:-$HOME/.cache}/horyzont\"",
        _cmd("shell") + " >\"${XDG_CACHE_HOME:-$HOME/.cache}/horyzont/shell.log\" 2>&1 &",
        "# usługi pomocnicze, jeśli są zainstalowane",
        "# agent uwierzytelniania polkit uruchamia powłoka (okna hasła w stylu Horyzontu)",
        "# zasobnik programów (StatusNotifierItem) i powiadomienia (dymki) obsługuje powłoka",
        "command -v swayidle >/dev/null && " + swayidle_cmd() + " &",
        "dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP 2>/dev/null || true",
        "",
    ])


def swayidle_cmd():
    timeout = int(config.get("screensaver_timeout", 10)) * 60
    if not config.get("screensaver") or timeout <= 0:
        return "true"
    ss = _cmd("screensaver")
    return f"swayidle -w timeout {timeout} {shlex.quote(ss)}"


def menu_xml():
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<openbox_menu>
  <menu id="root-menu" label="">
    <item label="Eksplorator"><action name="Execute" command={quoteattr(_cmd('explorer'))}/></item>
    <item label="Menedżer zadań"><action name="Execute" command={quoteattr(_cmd('taskmgr'))}/></item>
    <item label="Uruchom ponownie powłokę"><action name="Execute" command={quoteattr(_cmd('shell', '--replace'))}/></item>
    <separator/>
    <item label="Wyloguj"><action name="Exit"/></item>
  </menu>
</openbox_menu>
"""


def themerc():
    """Motyw dekoracji labwc dla programów spoza Horyzontu, zgodny z bieżącym schematem."""
    sc = SCHEMES.get(config.get("color_scheme", "teal"), SCHEMES["teal"])
    cap, capi = sc["caption"], sc["caption_in"]
    return f"""# Horyzont — motyw dekoracji okien labwc (wygenerowany)
border.width: 4
padding.height: 5
titlebar.height: 24
window.active.border.color: {sc['border']}
window.inactive.border.color: {sc['border_in']}
window.active.title.bg.color: {cap[2]}
window.active.title.bg: Gradient Vertical
window.active.title.bg.colorTo: {cap[4]}
window.active.title.bg.color.split.to: {cap[0]}
window.active.title.bg.colorTo.split.to: {cap[2]}
window.inactive.title.bg.color: {capi[2]}
window.inactive.title.bg: Gradient Vertical
window.inactive.title.bg.colorTo: {capi[4]}
window.active.label.text.color: #ffffff
window.inactive.label.text.color: #f2f6f7
window.label.text.justify: left
window.active.button.unpressed.image.color: #ffffff
window.inactive.button.unpressed.image.color: #f2f6f7
window.active.shadow.size: 0
window.inactive.shadow.size: 0
menu.items.bg.color: #ffffff
menu.items.text.color: #000000
menu.items.active.bg.color: {sc['accent']}
menu.items.active.text.color: #ffffff
menu.border.width: 1
menu.border.color: #8a9b9e
menu.separator.color: #c5cfcf
osd.bg.color: #ebeee9
osd.border.color: {sc['accent_dark']}
osd.border.width: 1
osd.label.text.color: #000000
osd.window-switcher.width: 420
osd.window-switcher.item.active.border.color: {sc['accent']}
"""


def button_svgs():
    """Przyciski paska tytułu labwc w stylu wbudowanego motywu."""
    def btn(glyph, fill1, fill2):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="21" height="21" viewBox="0 0 21 21">'
                f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{fill1}"/>'
                f'<stop offset="1" stop-color="{fill2}"/></linearGradient></defs>'
                f'<rect x="0.5" y="0.5" width="20" height="20" rx="3.5" fill="url(#g)" stroke="#ffffff"/>{glyph}</svg>')
    sc = SCHEMES.get(config.get("color_scheme", "teal"), SCHEMES["teal"])
    a1, a2 = sc["caption"][0], sc["caption"][3]
    glyphs = {
        "close": '<path d="M6 6 L15 15 M15 6 L6 15" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>',
        "iconify": '<rect x="6" y="13" width="7" height="2.6" fill="#fff"/>',
        "max": '<rect x="5.5" y="5.5" width="10" height="10" fill="none" stroke="#fff" stroke-width="1.4"/><rect x="5.5" y="5.5" width="10" height="2.6" fill="#fff"/>',
        "max_toggled": '<rect x="8.5" y="4.5" width="8" height="7" fill="none" stroke="#fff" stroke-width="1.3"/><rect x="4.5" y="9" width="8" height="7" fill="#3aa" stroke="#fff" stroke-width="1.3"/>',
        "menu": '<path d="M6 8 L10.5 13 L15 8" fill="none" stroke="#fff" stroke-width="2"/>',
    }
    out = {}
    for name, g in glyphs.items():
        if name == "close":
            out[name] = btn(g, "#f9967a", "#c8401c")
        else:
            out[name] = btn(g, a1, a2)
    return out


def write_all(screen_w=None, screen_h=None, taskbar_h=None):
    os.makedirs(LABWC_DIR, exist_ok=True)
    os.makedirs(THEME_DIR, exist_ok=True)
    files = {
        os.path.join(LABWC_DIR, "rc.xml"): rc_xml(screen_w, screen_h, taskbar_h),
        os.path.join(LABWC_DIR, "environment"): environment_file(),
        os.path.join(LABWC_DIR, "autostart"): autostart_file(),
        os.path.join(LABWC_DIR, "menu.xml"): menu_xml(),
        os.path.join(THEME_DIR, "themerc"): themerc(),
    }
    for name, svg in button_svgs().items():
        for state in ("active", "inactive"):
            files[os.path.join(THEME_DIR, f"{name}-{state}.svg")] = svg
    for path, content in files.items():
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == content:
                    continue
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    os.chmod(os.path.join(LABWC_DIR, "autostart"), 0o755)


def reconfigure():
    """Prosi działający labwc o ponowne wczytanie konfiguracji."""
    pid = os.environ.get("LABWC_PID")
    if pid:
        try:
            os.kill(int(pid), signal.SIGHUP)
            return True
        except (OSError, ValueError):
            pass
    return False


def apply_settings():
    """Wywoływane przez aplety po zmianie myszy/klawiatury/motywu."""
    write_all()   # rozmiar ekranu i pozycje okien z placement.json zapisanego przez powłokę
    reconfigure()
