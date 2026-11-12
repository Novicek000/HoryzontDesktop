"""Migracja istniejących profili GTK oraz rzeczywiste położenie i źródło dymków Qt."""
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from horyzont.common.app import make_app
from horyzont.session import gtkdeco
from horyzont.shell.balloon import BalloonQueue
from horyzont.shell.taskbar import Tray

APP = QApplication.instance() or make_app("test", [])


class GtkMigrationTest(unittest.TestCase):
    def test_existing_flatpak_profiles_new_apps_and_later_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = root / ".config/gtk-3.0/settings.ini"
            sandbox = root / ".var/app/org.test.Existing/config/gtk-4.0/settings.ini"
            for path in (host, sandbox):
                path.parent.mkdir(parents=True)
                path.write_text("[Settings]\ngtk-theme-name=Custom\ngtk-decoration-layout=close:minimize,maximize\n")
            state = {"gtk_xp_buttons": False}  # dawne ustawienie też podlega migracji
            gsettings = {"value": "appmenu:close"}

            def call(*args):
                if args[0] == "get":
                    return repr(gsettings["value"])
                gsettings["value"] = args[-1]
                return ""

            with patch.dict(os.environ, {"HOME": tmp, "XDG_CONFIG_HOME": str(root / ".config")}), patch.object(
                    gtkdeco.config, "get", side_effect=lambda key, default=None: state.get(key, default)), patch.object(
                    gtkdeco.config, "set", side_effect=lambda key, value: state.__setitem__(key, value)), patch.object(
                    gtkdeco.shutil, "which", return_value="/usr/bin/gsettings"), patch.object(gtkdeco, "_gsettings", side_effect=call):
                gtkdeco.apply()
                for path in (host, sandbox):
                    self.assertIn("gtk-decoration-layout=" + gtkdeco.LAYOUT, path.read_text())
                    self.assertIn("gtk-theme-name=Custom", path.read_text())
                self.assertEqual(gsettings["value"], gtkdeco.LAYOUT)
                new = root / ".var/app/org.test.New/config/gtk-3.0/settings.ini"
                new.parent.mkdir(parents=True)
                host.write_text("[Settings]\ngtk-decoration-layout=:close\n")
                gsettings["value"] = ":close"
                gtkdeco.apply()
                self.assertIn(gtkdeco.LAYOUT, host.read_text())
                self.assertIn(gtkdeco.LAYOUT, new.read_text())
                self.assertEqual(gsettings["value"], gtkdeco.LAYOUT)
                gtkdeco.restore()
                self.assertIn("gtk-decoration-layout=close:minimize,maximize", host.read_text())
                self.assertNotIn("gtk-decoration-layout", new.read_text())
                self.assertEqual(gsettings["value"], "appmenu:close")

    def test_only_settings_section_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.ini"
            path.write_text("[Other]\ngtk-decoration-layout=keep\n[Settings]\ngtk-decoration-layout=:close\n"
                            "gtk-theme-name=Custom\ngtk-decoration-layout=menu:maximize,close\n")
            gtkdeco._settings_ini(str(path), gtkdeco.LAYOUT)
            text = path.read_text()
            self.assertIn("[Other]\ngtk-decoration-layout=keep", text)
            self.assertEqual(text.count("gtk-decoration-layout="), 2)
            self.assertIn("gtk-theme-name=Custom", text)
            self.assertIn(gtkdeco.LAYOUT, text)

    def test_xsettings_migration_preserves_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = gtkdeco.SettingsManager.__new__(gtkdeco.SettingsManager)
            manager.xsettings_file = str(Path(tmp) / "xsettingsd.conf")
            with patch.dict(os.environ, {"DISPLAY": ":test"}), patch.object(
                    gtkdeco.config, "CONFIG_DIR", tmp), patch.object(gtkdeco.shutil, "which", return_value="tool"), patch.object(
                    gtkdeco.subprocess, "run", return_value=Mock(returncode=0, stdout='Net/ThemeName "Custom"\nGtk/DecorationLayout "close"\n')):
                manager._prepare_xsettings()
            text = Path(manager.xsettings_file).read_text()
            self.assertIn('Net/ThemeName "Custom"', text)
            self.assertIn('Gtk/DecorationLayout "' + gtkdeco.LAYOUT + '"', text)
            self.assertEqual(text.count("Gtk/DecorationLayout"), 1)

    def test_user_portal_override_preserves_case_and_other_backends(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            path = Path(tmp) / "xdg-desktop-portal/horyzont-portals.conf"
            path.parent.mkdir()
            path.write_text("[preferred]\norg.freedesktop.impl.portal.Settings=none\norg.freedesktop.impl.portal.ScreenCast=wlr\n")
            gtkdeco._portal_config()
            self.assertIn("org.freedesktop.impl.portal.Settings=gnome;gtk", path.read_text())
            self.assertIn("org.freedesktop.impl.portal.ScreenCast=wlr", path.read_text())


class BalloonPlacementTest(unittest.TestCase):
    def setUp(self):
        self.bar = QWidget()
        screen = APP.primaryScreen().geometry()
        self.bar.setGeometry(screen.left(), screen.bottom() - 29, screen.width(), 30)
        self.bar.balloons = BalloonQueue(self.bar)
        # Rzeczywisty widget Tray bez uruchamiania usług sieci/audio w testach.
        self.tray = Tray.__new__(Tray)
        QWidget.__init__(self.tray, self.bar)
        self.tray.bar = self.bar
        self.tray.sni = None
        self.tray._icons = []
        self.tray._all_icons = []
        self.tray._known_items = lambda icons: None
        self.tray._filter_hidden = lambda icons: icons
        self.tray.state = {"volume": (50, False), "updates": {"count": 0}}
        self.bar.tray = self.tray

        def relayout():
            size = self.tray.sizeHint()
            self.tray.setGeometry(self.bar.width() - size.width(), 0, size.width(), self.bar.height())

        self.bar.relayout = relayout
        self.tray._rebuild()
        self.bar.show()
        APP.processEvents()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.bar.balloons._close_current(None)
        self.bar.close()
        self.bar.deleteLater()

    def test_update_balloon_points_to_new_shield_not_volume(self):
        self.tray._on_status({"volume": (50, False), "updates": {"count": 2}})
        APP.processEvents()
        self.bar.balloons.reposition()
        entry, balloon = self.bar.balloons.current
        shield, volume = self.tray.icon_x("updates"), self.tray.icon_x("vol")
        self.assertEqual(balloon.tail_x, shield)
        self.assertNotEqual(balloon.tail_x, volume)
        self.assertIs(balloon.windowHandle().transientParent(), self.bar.windowHandle())
        # Piksele końcówki ogonka muszą leżeć nad ikoną źródłową.
        img = balloon.grab().toImage().scaled(balloon.width(), balloon.height())
        pixels = [x for x in range(img.width()) if img.pixelColor(x, img.height() - 3).alpha() > 100]
        self.assertTrue(pixels)
        self.assertLessEqual(abs((min(pixels) + max(pixels)) / 2 + balloon.x() - shield), 2)
        previous = balloon.x()
        self.tray.move(self.tray.x() - 80, self.tray.y())
        self.bar.balloons.reposition()
        self.assertEqual(balloon.tail_x, self.tray.icon_x("updates"))
        self.assertLess(balloon.x(), previous)

    def test_unknown_source_has_no_arrow_and_body_is_centered(self):
        anchor = self.bar.x() + self.bar.width() // 2
        self.bar.balloons.show({"title": "Test", "text": "Dymek", "anchor": lambda: anchor, "sound": False})
        _, balloon = self.bar.balloons.current
        self.assertLessEqual(abs(balloon.geometry().center().x() - anchor), 1)
        self.bar.balloons._close_current(None)
        self.bar.balloons.show({"title": "Test", "text": "Bez ikony", "sound": False})
        _, balloon = self.bar.balloons.current
        self.assertIsNone(balloon.tail_x)

    def test_hidden_icon_points_to_chevron_and_completed_update_has_shield(self):
        self.tray._all_icons = [(None, "", None, None, "updates")]
        self.tray._icons = [(None, "", None, None, "chevron")]
        self.assertEqual(self.tray.icon_x("updates"), self.tray.icon_x("chevron"))
        self.tray._on_status({"volume": (50, False), "updates": {"count": 0, "message": "Gotowe"}})
        self.assertIsNotNone(self.tray.icon_x("updates"))
        self.assertEqual(self.bar.balloons.current[1].tail_x, self.tray.icon_x("updates"))


if __name__ == "__main__":
    unittest.main()
