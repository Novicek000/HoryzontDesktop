"""Zestawy ikon .msicon — instalacja, lista, eksport szablonu i opis wszystkich nazw ikon.

Format .msicon to zwykłe archiwum ZIP ze zmienionym rozszerzeniem::

    manifest.ini            [Icon Pack] Name=..., Author=..., Version=..., Description=...
    icons/<nazwa>.svg       ikona wektorowa (zalecane)
    icons/<nazwa>.png       albo bitmapa (najlepiej 48x48 lub większa)
    icons/<nazwa>@16.png    opcjonalnie osobne rozmiary: 16, 24, 32, 48, 256
    icons/<nazwa>.ico       pliki .ico też są obsługiwane

Brakujące ikony są brane z wbudowanego zestawu Horyzont.
"""
import configparser
import os
import re
import shutil
import zipfile

from . import iconcache, icons

ALLOWED = (".svg", ".png", ".ico", ".xpm", ".bmp")

# nazwa ikony -> (kategoria, opis PL, opis EN)
CATEGORIES = [
    ("desktop", "Pulpit i foldery specjalne", "Desktop and special folders"),
    ("drives", "Napędy", "Drives"),
    ("files", "Typy plików", "File types"),
    ("apps", "Programy i aplety", "Programs and applets"),
    ("actions", "Polecenia i paski narzędzi", "Commands and toolbars"),
    ("session", "Menu Start i sesja", "Start menu and session"),
    ("messages", "Komunikaty", "Messages"),
    ("tray", "Obszar powiadomień (16x16)", "Notification area (16x16)"),
    ("users", "Obrazy kont użytkowników", "User account pictures"),
]

DESCRIPTIONS = {
    # pulpit i foldery
    "computer": ("desktop", "Mój komputer", "My Computer"),
    "documents": ("desktop", "Moje dokumenty", "My Documents"),
    "pictures": ("desktop", "Moje obrazy", "My Pictures"),
    "music": ("desktop", "Moja muzyka", "My Music"),
    "videos": ("desktop", "Moje wideo", "My Videos"),
    "downloads": ("desktop", "Pobrane", "Downloads"),
    "network": ("desktop", "Moje miejsca sieciowe", "My Network Places"),
    "recycle_empty": ("desktop", "Kosz (pusty)", "Recycle Bin (empty)"),
    "recycle_full": ("desktop", "Kosz (pełny)", "Recycle Bin (full)"),
    "folder": ("desktop", "Folder zamknięty", "Closed folder"),
    "folder_open": ("desktop", "Folder otwarty / Eksplorator", "Open folder / Explorer"),
    "folder_zip": ("desktop", "Folder skompresowany (ZIP, RAR, 7z)", "Compressed folder (ZIP, RAR, 7z)"),
    "desktop_folder": ("desktop", "Pulpit (folder)", "Desktop (folder)"),
    "home": ("desktop", "Folder domowy", "Home folder"),
    "recent": ("desktop", "Moje bieżące dokumenty", "My Recent Documents"),
    "fonts": ("desktop", "Folder Czcionki", "Fonts folder"),
    "new_folder": ("desktop", "Nowy folder", "New folder"),
    "shortcut_overlay": ("desktop", "Strzałka skrótu (nakładka, przezroczyste tło)", "Shortcut arrow (overlay, transparent)"),
    # napędy
    "drive_system": ("drives", "Dysk systemowy", "System drive"),
    "drive_hdd": ("drives", "Dysk twardy", "Hard disk"),
    "drive_cd": ("drives", "Napęd CD/DVD", "CD/DVD drive"),
    "drive_usb": ("drives", "Dysk wymienny (USB)", "Removable disk (USB)"),
    "drive_network": ("drives", "Dysk sieciowy", "Network drive"),
    "drive_floppy": ("drives", "Stacja dyskietek", "Floppy drive"),
    # pliki
    "file": ("files", "Plik nieznanego typu", "Unknown file"),
    "file_text": ("files", "Dokument tekstowy", "Text document"),
    "file_image": ("files", "Obraz", "Picture"),
    "file_audio": ("files", "Plik dźwiękowy", "Audio file"),
    "file_video": ("files", "Plik wideo", "Video file"),
    "file_archive": ("files", "Archiwum", "Archive"),
    "file_pdf": ("files", "Dokument PDF", "PDF document"),
    "file_html": ("files", "Strona HTML", "HTML page"),
    "file_doc": ("files", "Dokument edytora tekstu", "Word processor document"),
    "file_sheet": ("files", "Arkusz kalkulacyjny", "Spreadsheet"),
    "file_code": ("files", "Kod źródłowy / skrypt", "Source code / script"),
    "file_exe": ("files", "Program (plik wykonywalny)", "Program (executable)"),
    "file_font": ("files", "Plik czcionki", "Font file"),
    # programy i aplety
    "app": ("apps", "Program ogólny", "Generic program"),
    "browser": ("apps", "Przeglądarka internetowa", "Web browser"),
    "email": ("apps", "Poczta e-mail", "E-mail"),
    "notepad": ("apps", "Notatnik", "Notepad"),
    "wordpad": ("apps", "WordPad / dokument RTF", "WordPad / RTF document"),
    "paint": ("apps", "Paint", "Paint"),
    "calculator": ("apps", "Kalkulator", "Calculator"),
    "charmap": ("apps", "Tablica znaków", "Character Map"),
    "terminal": ("apps", "Terminal", "Terminal"),
    "cmd": ("apps", "Wiersz polecenia", "Command Prompt"),
    "taskmgr": ("apps", "Menedżer zadań", "Task Manager"),
    "image_viewer": ("apps", "Przeglądarka obrazów", "Picture viewer"),
    "media_player": ("apps", "Odtwarzacz multimediów", "Media player"),
    "recorder": ("apps", "Rejestrator dźwięku", "Sound Recorder"),
    "games": ("apps", "Gry", "Games"),
    "cards": ("apps", "Pasjans", "Solitaire"),
    "mines": ("apps", "Saper", "Minesweeper"),
    "accessories": ("apps", "Akcesoria", "Accessories"),
    "programs": ("apps", "Folder grupy programów", "Program group"),
    "control_panel": ("apps", "Panel sterowania", "Control Panel"),
    "display": ("apps", "Ekran", "Display"),
    "datetime": ("apps", "Data i godzina", "Date and Time"),
    "mouse": ("apps", "Mysz", "Mouse"),
    "keyboard": ("apps", "Klawiatura", "Keyboard"),
    "sound": ("apps", "Dźwięki i urządzenia audio", "Sounds and Audio Devices"),
    "sound_scheme": ("apps", "Schemat dźwiękowy", "Sound scheme"),
    "system": ("apps", "System", "System"),
    "sysinfo": ("apps", "Informacje o systemie", "System Information"),
    "addremove": ("apps", "Dodaj lub usuń programy", "Add or Remove Programs"),
    "package": ("apps", "Pakiet oprogramowania", "Software package"),
    "flatpak": ("apps", "Aplikacje Flatpak", "Flatpak apps"),
    "network_conn": ("apps", "Połączenia sieciowe", "Network Connections"),
    "network_wireless": ("apps", "Połączenie sieci bezprzewodowej", "Wireless Network Connection"),
    "wifi": ("apps", "Sieci bezprzewodowe (aplet)", "Wireless networks (applet)"),
    "bluetooth": ("apps", "Urządzenia Bluetooth", "Bluetooth Devices"),
    "printer": ("apps", "Drukarki i faksy", "Printers and Faxes"),
    "users": ("apps", "Konta użytkowników", "User Accounts"),
    "user": ("apps", "Konto użytkownika", "User account"),
    "user_add": ("apps", "Nowe konto", "New account"),
    "fonts_app": ("apps", "", ""),
    "taskbar_props": ("apps", "Pasek zadań i menu Start", "Taskbar and Start Menu"),
    "folder_options": ("apps", "Opcje folderów", "Folder Options"),
    "regional": ("apps", "Opcje regionalne i językowe", "Regional and Language Options"),
    "power": ("apps", "Opcje zasilania", "Power Options"),
    "accessibility": ("apps", "Opcje ułatwień dostępu", "Accessibility Options"),
    "security": ("apps", "Centrum zabezpieczeń", "Security Center"),
    "admin": ("apps", "Narzędzia administracyjne", "Administrative Tools"),
    "scheduled": ("apps", "Zaplanowane zadania", "Scheduled Tasks"),
    "disk_cleanup": ("apps", "Oczyszczanie dysku", "Disk Cleanup"),
    "updates": ("apps", "Horyzont Updates", "Horyzont Updates"),
    "auto_updates": ("apps", "Aktualizacje automatyczne", "Automatic Updates"),
    "cursor": ("apps", "Wskaźniki myszy", "Mouse pointers"),
    "icon_pack": ("apps", "Zestaw ikon", "Icon pack"),
    "wizard": ("apps", "Kreator", "Wizard"),
    "key": ("apps", "Uwierzytelnianie (hasło)", "Authentication (password)"),
    # polecenia
    "back": ("actions", "Wstecz", "Back"),
    "forward": ("actions", "Dalej", "Forward"),
    "up": ("actions", "W górę", "Up"),
    "go": ("actions", "Przejdź", "Go"),
    "search": ("actions", "Wyszukaj", "Search"),
    "folders_tree": ("actions", "Foldery (drzewo)", "Folders (tree)"),
    "views": ("actions", "Widoki", "Views"),
    "copy": ("actions", "Kopiuj", "Copy"),
    "cut": ("actions", "Wytnij", "Cut"),
    "paste": ("actions", "Wklej", "Paste"),
    "delete": ("actions", "Usuń", "Delete"),
    "undo": ("actions", "Cofnij", "Undo"),
    "refresh": ("actions", "Odśwież", "Refresh"),
    "properties": ("actions", "Właściwości", "Properties"),
    "extract": ("actions", "Wyodrębnij pliki", "Extract files"),
    "show_desktop": ("actions", "Pokaż pulpit", "Show Desktop"),
    "chevron_down": ("actions", "Strzałka rozwijania", "Expand arrow"),
    "star": ("actions", "Gwiazdka (ulubione, połączono)", "Star (favorites, connected)"),
    "signal_bars": ("actions", "Siła sygnału", "Signal strength"),
    # sesja
    "logo": ("session", "Logo Horyzont (przycisk Start, okno Informacje)", "Horyzont logo (Start button, About)"),
    "run": ("session", "Uruchom...", "Run..."),
    "help": ("session", "Pomoc i obsługa techniczna", "Help and Support"),
    "logoff": ("session", "Wyloguj", "Log Off"),
    "shutdown": ("session", "Wyłącz komputer", "Turn Off Computer"),
    "restart": ("session", "Uruchom ponownie", "Restart"),
    "standby": ("session", "Stan wstrzymania", "Stand By"),
    "switch_user": ("session", "Przełącz użytkownika", "Switch User"),
    "lock": ("session", "Zablokuj komputer", "Lock computer"),
    # komunikaty
    "info": ("messages", "Informacja", "Information"),
    "warning": ("messages", "Ostrzeżenie", "Warning"),
    "error": ("messages", "Błąd", "Error"),
    "question": ("messages", "Pytanie", "Question"),
    # zasobnik
    "volume": ("tray", "Głośność", "Volume"),
    "volume_muted": ("tray", "Głośność wyciszona", "Volume muted"),
    "tray_network": ("tray", "Sieć przewodowa — połączono", "Wired network — connected"),
    "tray_network_off": ("tray", "Sieć przewodowa — kabel odłączony", "Wired network — cable unplugged"),
    "tray_wifi_0": ("tray", "Wi-Fi — brak sygnału", "Wi-Fi — no signal"),
    "tray_wifi_1": ("tray", "Wi-Fi — sygnał słaby", "Wi-Fi — weak signal"),
    "tray_wifi_2": ("tray", "Wi-Fi — sygnał średni", "Wi-Fi — fair signal"),
    "tray_wifi_3": ("tray", "Wi-Fi — sygnał dobry", "Wi-Fi — good signal"),
    "tray_wifi_4": ("tray", "Wi-Fi — sygnał doskonały", "Wi-Fi — excellent signal"),
    "tray_wifi_off": ("tray", "Wi-Fi — niepołączono / wyłączone", "Wi-Fi — not connected / off"),
    "tray_bluetooth": ("tray", "Bluetooth włączony", "Bluetooth on"),
    "tray_bluetooth_off": ("tray", "Bluetooth wyłączony", "Bluetooth off"),
    "tray_updates": ("tray", "Dostępne aktualizacje", "Updates available"),
    "tray_battery": ("tray", "Bateria", "Battery"),
    # konta
    "avatar_kite": ("users", "Obraz konta: latawiec", "Account picture: kite"),
    "avatar_boat": ("users", "Obraz konta: łódka", "Account picture: boat"),
    "avatar_cat": ("users", "Obraz konta: kot", "Account picture: cat"),
    "avatar_flower": ("users", "Obraz konta: kwiat", "Account picture: flower"),
    "avatar_guitar": ("users", "Obraz konta: gitara", "Account picture: guitar"),
    "avatar_planet": ("users", "Obraz konta: planeta", "Account picture: planet"),
}
DESCRIPTIONS.pop("fonts_app", None)


def all_names():
    if "key" not in icons.ICONS:
        icons._load_extra()
    return sorted(icons.ICONS)


def slug(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return s or "zestaw"


def read_manifest(path_or_dir):
    cp = configparser.ConfigParser()
    try:
        if os.path.isdir(path_or_dir):
            cp.read(os.path.join(path_or_dir, "manifest.ini"), encoding="utf-8")
        else:
            with zipfile.ZipFile(path_or_dir) as z:
                if "manifest.ini" in z.namelist():
                    cp.read_string(z.read("manifest.ini").decode("utf-8", "replace"))
    except Exception:
        pass
    sec = cp["Icon Pack"] if cp.has_section("Icon Pack") else {}
    return {"name": sec.get("Name", ""), "author": sec.get("Author", ""), "version": sec.get("Version", ""),
            "description": sec.get("Description", "")}


def installed():
    """[(klucz, metadane, liczba ikon)]"""
    out = []
    base = iconcache.packs_dir()
    if not os.path.isdir(base):
        return out
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d)
        if not os.path.isdir(p):
            continue
        meta = read_manifest(p)
        meta["name"] = meta["name"] or d
        n = len({os.path.splitext(f)[0].split("@")[0] for f in os.listdir(os.path.join(p, "icons"))}) \
            if os.path.isdir(os.path.join(p, "icons")) else 0
        out.append((d, meta, n))
    return out


def install(path):
    """Instaluje plik .msicon (ZIP). Zwraca (klucz, liczba ikon, nieznane nazwy)."""
    if not zipfile.is_zipfile(path):
        raise ValueError("plik nie jest archiwum ZIP (.msicon)")
    meta = read_manifest(path)
    key = slug(meta["name"] or os.path.splitext(os.path.basename(path))[0])
    dest = os.path.join(iconcache.packs_dir(), key)
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "icons"), exist_ok=True)
    known = set(all_names())
    count, unknown = 0, []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            base = os.path.basename(name)
            if base.lower() in ("manifest.ini", "readme.txt", "license.txt", "licencja.txt"):
                with open(os.path.join(tmp, base.lower()), "wb") as f:
                    f.write(z.read(info))
                continue
            stem, ext = os.path.splitext(base)
            if ext.lower() not in ALLOWED or info.file_size > 8 * 1024 * 1024:
                continue
            icon_name = stem.split("@")[0]
            if icon_name not in known:
                unknown.append(icon_name)
            with open(os.path.join(tmp, "icons", base), "wb") as f:
                f.write(z.read(info))
            count += 1
    if count == 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("w archiwum nie ma żadnych ikon (SVG/PNG/ICO)")
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return key, count, sorted(set(unknown))


def remove(key):
    shutil.rmtree(os.path.join(iconcache.packs_dir(), key), ignore_errors=True)


def export_template(folder, lang="pl"):
    """Zapisuje wszystkie wbudowane ikony jako SVG + manifest + LISTA-IKON.txt — punkt wyjścia dla autora zestawu."""
    icons_dir = os.path.join(folder, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    for n in all_names():
        with open(os.path.join(icons_dir, n + ".svg"), "w", encoding="utf-8") as f:
            f.write(icons.svg_for(n))
    with open(os.path.join(folder, "manifest.ini"), "w", encoding="utf-8") as f:
        f.write("[Icon Pack]\nName=Mój zestaw ikon\nAuthor=\nVersion=1.0\nDescription=\n")
    with open(os.path.join(folder, "LISTA-IKON.txt"), "w", encoding="utf-8") as f:
        f.write(names_table(lang))
    return folder


def names_table(lang="pl", markdown=False):
    idx = 1 if lang == "pl" else 2
    lines = []
    names = all_names()
    for cat, pl, en in CATEGORIES:
        rows = [(n, DESCRIPTIONS[n][idx]) for n in names if DESCRIPTIONS.get(n, ("",))[0] == cat]
        if not rows:
            continue
        title = pl if lang == "pl" else en
        if markdown:
            lines += [f"### {title}", "", "| Plik | Ikona |", "|---|---|"]
            lines += [f"| `{n}.svg` | {d} |" for n, d in rows]
            lines.append("")
        else:
            lines += [title, "-" * len(title)]
            lines += [f"  {n:<22} {d}" for n, d in rows]
            lines.append("")
    other = [n for n in names if n not in DESCRIPTIONS]
    if other:
        title = "Pozostałe" if lang == "pl" else "Other"
        if markdown:
            lines += [f"### {title}", "", "| Plik | Ikona |", "|---|---|"] + [f"| `{n}.svg` | |" for n in other] + [""]
        else:
            lines += [title, "-" * len(title)] + [f"  {n}" for n in other] + [""]
    return "\n".join(lines)
