"""Regresje sesji: GTK, instalowanie aplikacji i montowanie nośników.

QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
"""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from horyzont.common import desktopentry
from horyzont.session import gtkdeco
from horyzont.shell import automount


from horyzont.common.app import make_app

APP = make_app("test", [])


class GtkButtonsTest(unittest.TestCase):
    def test_missing_either_button_is_repaired(self):
        for layout in ("appmenu:close", ":minimize,close", ":maximize,close"):
            self.assertEqual(gtkdeco.xp_layout(layout), "appmenu:minimize,maximize,close"
                             if layout.startswith("appmenu") else ":minimize,maximize,close")
        self.assertIsNone(gtkdeco.xp_layout("close:minimize,maximize"))

    def test_existing_gtk_settings_repaired_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gtk-4.0/settings.ini"
            path.parent.mkdir()
            path.write_text("[Settings]\ngtk-theme-name=Adwaita\ngtk-decoration-layout=:close\n")
            gtkdeco._settings_ini(str(path), "menu:" + gtkdeco.RIGHT)
            first = path.read_text()
            self.assertIn("gtk-theme-name=Adwaita", first)
            self.assertIn("gtk-decoration-layout=:minimize,maximize,close", first)
            gtkdeco._settings_ini(str(path), "menu:" + gtkdeco.RIGHT)
            self.assertEqual(first, path.read_text())


class ApplicationsTest(unittest.TestCase):
    def test_live_menu_install_edit_remove_and_new_export_directory(self):
        from horyzont.shell.startmenu import StartMenu
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktopentry, "data_dirs", return_value=[tmp]):
            desktopentry.all_entries(refresh=True)
            menu = StartMenu(Mock())
            menu._all_programs_menu = menu.build_all_programs(menu)
            old_menu = menu._all_programs_menu
            # Flatpak po raz pierwszy tworzy katalog eksportu już po zalogowaniu.
            path = Path(tmp) / "applications/vendor/test.desktop"
            path.parent.mkdir(parents=True)
            path.write_text("[Desktop Entry]\nType=Application\nName=New app\nExec=true\nCategories=Utility;\n")
            menu._check_apps()
            self.assertEqual(desktopentry.all_entries()["vendor-test.desktop"].name, "New app")
            menu.open_all_programs(menu.all_programs)
            self.assertIsNot(old_menu, menu._all_programs_menu)

            def labels(m):
                result = []
                for action in m.actions():
                    result.append(action.text())
                    if action.menu():
                        result.extend(labels(action.menu()))
                return result

            self.assertIn("New app", labels(menu._all_programs_menu))
            menu._all_programs_menu.close()
            path.write_text(path.read_text().replace("New app", "Edited app"))
            menu._check_apps()
            self.assertEqual(desktopentry.all_entries()["vendor-test.desktop"].name, "Edited app")
            path.unlink()
            menu._check_apps()
            self.assertNotIn("vendor-test.desktop", desktopentry.all_entries())
            menu._apps_timer.stop()
            menu.close()
            menu.deleteLater()
            QCoreApplication.processEvents()
        desktopentry.all_entries(refresh=True)

    def test_flatpak_export_symlink_target_replacement(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktopentry, "data_dirs", return_value=[tmp]):
            apps = Path(tmp) / "applications"
            apps.mkdir()
            target = Path(tmp) / "target"
            target.write_text("first")
            (apps / "app.desktop").symlink_to(target)
            first = desktopentry.applications_snapshot()
            replacement = Path(tmp) / "replacement"
            replacement.write_text("other")
            replacement.replace(target)
            self.assertNotEqual(first, desktopentry.applications_snapshot())


class AutomountTest(unittest.TestCase):
    def setUp(self):
        self.path = automount.ROOT + "/block_devices/sdb1"
        self.drive = automount.ROOT + "/drives/USB"
        self.objects = {
            self.path: {automount.BLOCK: {"Drive": self.drive, "IdUsage": "filesystem", "HintSystem": False},
                        automount.FILESYSTEM: {"MountPoints": []}},
            self.drive: {automount.DRIVE: {"ConnectionBus": "usb"}},
        }

    def test_usb_and_removable_media_but_no_system_fstab_loop_or_encrypted(self):
        self.assertEqual(list(automount.candidates(self.objects)), [self.path])
        for key, value in (("HintSystem", True), ("HintIgnore", True), ("HintAuto", False),
                           ("IdUsage", "crypto"), ("Drive", "/"), ("Configuration", [("fstab", {})])):
            objects = copy.deepcopy(self.objects)
            objects[self.path][automount.BLOCK][key] = value
            self.assertEqual(list(automount.candidates(objects)), [], key)
        self.objects[self.drive][automount.DRIVE] = {"MediaRemovable": True}
        self.assertEqual(list(automount.candidates(self.objects)), [self.path])

    def test_one_mount_per_connection_and_respect_manual_unmount(self):
        worker = automount.Automounter.__new__(automount.Automounter)
        worker.bus = Mock()
        worker.attempted = set()
        worker._objects([self.objects])
        worker._objects([self.objects])
        self.assertEqual(worker.bus.call.call_count, 1)
        self.assertTrue(worker.bus.call.call_args.args[5][0]["auth.no_user_interaction"].value)
        worker._objects([{}])
        worker._objects([self.objects])
        self.assertEqual(worker.bus.call.call_count, 2)

        # Nośnik zamontowany przed startem powłoki też można ręcznie odmontować.
        worker.attempted.clear()
        self.objects[self.path][automount.FILESYSTEM]["MountPoints"] = [b"/run/media/test/USB\0"]
        worker._objects([self.objects])
        self.objects[self.path][automount.FILESYSTEM]["MountPoints"] = []
        worker._objects([self.objects])
        self.assertEqual(worker.bus.call.call_count, 2)


    def test_udisks_message_roundtrip(self):
        from horyzont.common import dbus
        objects = copy.deepcopy(self.objects)
        block = objects[self.path][automount.BLOCK]
        for key, value in list(block.items()):
            block[key] = dbus.Variant("b" if isinstance(value, bool) else "o" if key == "Drive" else "s", value)
        objects[self.path][automount.FILESYSTEM]["MountPoints"] = dbus.Variant("aay", [])
        objects[self.drive][automount.DRIVE]["ConnectionBus"] = dbus.Variant("s", "usb")
        reply = dbus.Message(dbus.METHOD_RETURN, signature="a{oa{sa{sv}}}", body=[objects])
        decoded, consumed = dbus.Message.decode(reply.encode(1))
        self.assertEqual(list(automount.candidates(dbus.unwrap(decoded.body[0]))), [self.path])


if __name__ == "__main__":
    unittest.main()
