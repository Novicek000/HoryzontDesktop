"""Rejestr apletów i kategorii Panelu sterowania."""
import importlib

# klucz: (nazwa, opis, ikona, moduł, funkcja)
APPLETS = {
    "access": ("ap_access", "ap_desc_access", "accessibility", "applets_misc", "accessibility"),
    "addremove": ("ap_addremove", "ap_desc_addremove", "addremove", "addremove", "open_addremove"),
    "admin": ("ap_admin", "ap_desc_admin", "admin", "admintools", "open_admin"),
    "datetime": ("ap_datetime", "ap_desc_datetime", "datetime", "applets_basic", "datetime"),
    "display": ("ap_display", "ap_desc_display", "display", "display", "open_display"),
    "folder_options": ("ap_folder_options", "ap_desc_folder_options", "folder_options", "applets_misc", "folder_options"),
    "fonts": ("ap_fonts", "ap_desc_fonts", "fonts", "fonts", "open_fonts"),
    "keyboard": ("ap_keyboard", "ap_desc_keyboard", "keyboard", "applets_basic", "keyboard"),
    "mouse": ("ap_mouse", "ap_desc_mouse", "mouse", "applets_basic", "mouse"),
    "network": ("ap_network", "ap_desc_network", "network_conn", "network", "open_network"),
    "power": ("ap_power", "ap_desc_power", "power", "applets_misc", "power"),
    "printers": ("ap_printers", "ap_desc_printers", "printer", "printers", "open_printers"),
    "regional": ("ap_regional", "ap_desc_regional", "regional", "applets_misc", "regional"),
    "scheduled": ("ap_scheduled", "ap_desc_scheduled", "scheduled", "admintools", "open_scheduled"),
    "security": ("ap_security", "ap_desc_security", "security", "applets_misc", "security"),
    "sound": ("ap_sound", "ap_desc_sound", "sound", "applets_basic", "sound"),
    "system": ("ap_system", "ap_desc_system", "system", "system", "open_system"),
    "taskbar": ("ap_taskbar", "ap_desc_taskbar", "taskbar_props", "applets_misc", "taskbar"),
    "users": ("ap_users", "ap_desc_users", "users", "users", "open_users"),
    "wifi": ("ap_wifi", "ap_desc_wifi", "network_wireless", "wifi", "open_wifi"),
    "bluetooth": ("ap_bluetooth", "ap_desc_bluetooth", "bluetooth", "bluetooth", "open_bluetooth"),
    "updates": ("ap_updates", "ap_desc_updates", "updates", "updates", "open_updates"),
    "auto_updates": ("ap_auto_updates", "ap_desc_auto_updates", "auto_updates", "updates", "open_auto_updates"),
}

# aliasy używane z wiersza poleceń / okna Uruchamianie
ALIASES = {"services": ("admintools", "open_services"), "events": ("admintools", "open_events"),
           "disks": ("admintools", "open_disks"), "devmgmt": ("devmgr", "open_device_manager")}

# kategoria: (nazwa, ikona, [zadania (klucz tekstu, akcja)], [aplety])
CATEGORIES = [
    ("appearance", "cp_cat_appearance", "display",
     [("cp_task_change_theme", ("display", "themes")), ("cp_task_change_bg", ("display", "desktop")),
      ("cp_task_screensaver", ("display", "screensaver")), ("cp_task_resolution", ("display", "settings"))],
     ["display", "folder_options", "taskbar"]),
    ("printers", "cp_cat_printers", "printer",
     [("cp_task_add_printer", ("printers", "add")), ("cp_task_add_bt", ("bluetooth", "add"))],
     ["printers", "mouse", "keyboard", "bluetooth"]),
    ("network", "cp_cat_network", "network",
     [("nc_create", ("network", "new")), ("cp_task_network_setup", ("network", None)), ("cp_task_wifi", ("wifi", None))],
     ["network", "wifi"]),
    ("users", "cp_cat_users", "users",
     [("cp_task_change_account", ("users", None)), ("cp_task_change_picture", ("users", "picture"))],
     ["users"]),
    ("addremove", "cp_cat_addremove", "addremove", None, ["addremove"]),
    ("regional", "cp_cat_regional", "regional",
     [("cp_task_datetime", ("datetime", None)), ("cp_task_regional", ("regional", None))],
     ["datetime", "regional"]),
    ("sound", "cp_cat_sound", "sound",
     [("cp_task_volume", ("sound", None))],
     ["sound"]),
    ("access", "cp_cat_access", "accessibility",
     [("cp_task_access_display", ("access", None))],
     ["access"]),
    ("performance", "cp_cat_performance", "system",
     [("cp_task_sysinfo", ("system", None)), ("cp_task_free_space", ("admin", "disks"))],
     ["admin", "power", "scheduled", "system"]),
    ("security", "cp_cat_security", "security",
     [("cp_task_updates", ("updates", None)), ("cp_task_auto_updates", ("updates", "settings"))],
     ["security", "updates", "auto_updates"]),
]


def open_applet(key, page=None, parent=None):
    if key in ALIASES:
        mod, fn = ALIASES[key]
    elif key in APPLETS:
        mod, fn = APPLETS[key][3], APPLETS[key][4]
    else:
        return None
    m = importlib.import_module(f"horyzont.apps.control.{mod}")
    return getattr(m, fn)(page, parent)
