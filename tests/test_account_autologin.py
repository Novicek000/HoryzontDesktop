"""Przebieg zmiany autologowania z panelu wybranego konta (bez zmian systemu)."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

from horyzont.common.app import make_app
from horyzont.apps.control import users

APP = QApplication.instance() or make_app("test", [])


class AutologinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "greeter.json"
        self.person = SimpleNamespace(pw_name="alice", pw_uid=12345, pw_gecos="Alice", pw_dir=self.tmp.name)
        for target, value in (("GREETER_SETTINGS", str(self.path)), ("accounts", lambda: [self.person])):
            p = patch.object(users, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(users.shutil, "which", return_value="/usr/local/bin/horyzont-greeter-config")
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(users, "run_privileged", side_effect=self.save)
        self.run = p.start()
        self.addCleanup(p.stop)
        p = patch.object(users.dialogs, "message")
        self.message = p.start()
        self.addCleanup(p.stop)
        self.window = users.UsersWindow()
        self.addCleanup(self.window.deleteLater)

    def write(self, user):
        self.path.write_text(json.dumps({"style": "classic", "autologin": {"user": user} if user else None}))

    def save(self, args, parent):
        data = json.loads(self.path.read_text()) if self.path.exists() else {"style": "classic"}
        data["autologin"] = {"user": args[2], "session": args[3]} if args[2] != "off" else None
        self.path.write_text(json.dumps(data))
        return True, "OK"

    def page(self):
        self.window.show_autologin(self.person)
        page = self.window.stack.currentWidget()
        return page.findChild(QCheckBox, "account_autologin"), page.findChild(QPushButton, "apply_autologin")

    def test_enable_then_disable_and_preserve_other_settings(self):
        cb, apply = self.page()
        self.assertFalse(cb.isChecked())
        cb.setChecked(True)
        apply.click()
        self.assertEqual(users.autologin_user(), "alice")
        self.assertEqual(self.run.call_args.args[0],
                         ["/usr/local/bin/horyzont-greeter-config", "autologin", "alice", "horyzont"])
        cb, apply = self.page()
        self.assertTrue(cb.isChecked())
        cb.setChecked(False)
        apply.click()
        self.assertEqual(users.autologin_user(), "")
        self.assertEqual(self.run.call_args.args[0][-2:], ["autologin", "off"])
        self.assertEqual(json.loads(self.path.read_text())["style"], "classic")

    def test_other_account_not_disabled_but_can_be_replaced(self):
        self.write("bob")
        cb, apply = self.page()
        self.assertFalse(cb.isChecked())
        apply.click()
        self.run.assert_not_called()
        self.assertEqual(users.autologin_user(), "bob")
        cb, apply = self.page()
        cb.setChecked(True)
        apply.click()
        self.assertEqual(users.autologin_user(), "alice")

    def test_reread_before_disabling(self):
        self.write("alice")
        cb, apply = self.page()
        cb.setChecked(False)
        self.write("bob")
        apply.click()
        self.run.assert_not_called()
        self.assertEqual(users.autologin_user(), "bob")

    def test_missing_helper_or_invalid_settings_disable_apply(self):
        with patch.object(users.shutil, "which", return_value=None):
            cb, apply = self.page()
            self.assertFalse(cb.isEnabled())
            self.assertFalse(apply.isEnabled())
        self.path.write_text("broken json")
        cb, apply = self.page()
        self.assertFalse(apply.isEnabled())
        self.run.assert_not_called()

    def test_failed_authorization_does_not_report_success(self):
        cb, apply = self.page()
        cb.setChecked(True)
        with patch.object(self.window, "show_account") as navigate, patch.object(
                users, "run_privileged", return_value=(False, "cancelled")):
            apply.click()
            navigate.assert_not_called()
        self.assertEqual(users.autologin_user(), "")


if __name__ == "__main__":
    unittest.main()
