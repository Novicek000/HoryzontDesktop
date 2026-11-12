"""Transkrypcje bluetoothctl i układ klawiatury instalacji HoryzontOS."""
import ctypes
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from horyzont.common.app import make_app
from horyzont.common import keyboard
from horyzont.session import labwc
from horyzont.apps.control import bluetooth as bt

APP = QApplication.instance() or make_app("test", [])
MAC = "20:E0:B2:00:08:05"


class FakePty(QObject):
    data = Signal(str)
    finished = Signal(int)

    def __init__(self, *args):
        super().__init__()
        self.commands = []
        self.interrupted = False

    def write(self, text):
        self.commands.append(text.strip())

    def interrupt(self):
        self.interrupted = True


class BluetoothTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(bt, "PtyProcess", FakePty)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_agent_confirmation_split_over_chunks_and_display_pin(self):
        session = bt.BtSession()
        self.addCleanup(session.close)
        self.assertNotIn("default-agent", session.proc.commands)
        session._data("Agent registered\n")
        self.assertIn("default-agent", session.proc.commands)
        with patch.object(bt.dialogs, "message", return_value="yes") as dialog:
            session._data("[X2Pro]# [agent] Confirm passkey 123")
            dialog.assert_not_called()
            session._data("456 (yes/no): ")
            self.assertEqual(session.proc.commands[-1], "yes")
            self.assertEqual(dialog.call_count, 1)
            session._data("[agent] PIN code: 112233\n")
            self.assertEqual(dialog.call_count, 2)
        self.assertEqual(session.proc.commands.count("yes"), 1)

    def test_cancel_pin_terminates_client_without_guessing_code(self):
        session = bt.BtSession()
        session.waiting = (None, None, 90000)
        results = []
        session.done.connect(lambda ok, msg: results.append(ok))
        with patch.object(bt.dialogs, "ask_text", return_value=None):
            session._data("[bluetooth]# [agent] Enter PIN code: ")
        self.assertTrue(session.closed)
        self.assertTrue(session.proc.interrupted)
        self.assertNotIn("0000", session.proc.commands)
        self.assertEqual(results, [False])
        self.assertIsNone(session.waiting)

    def wizard(self):
        wizard = bt.AddDeviceWizard()
        wizard.stack.setCurrentIndex(2)
        wizard.mac, wizard.dev_name = MAC, "X2Pro"
        self.addCleanup(wizard._cleanup)
        self.addCleanup(wizard.deleteLater)
        return wizard

    def test_pair_with_scan_and_retry_only_once_after_connection_failure(self):
        wizard = self.wizard()
        wizard._pair()
        session = wizard.session
        self.assertIn("scan on", session.proc.commands)
        self.assertNotIn("scan off", session.proc.commands)
        session._data("Failed to pair: org.bluez.Error.ConnectionAttemptFailed\n")
        self.assertTrue(wizard._retry_timer.isActive())
        wizard._retry_timer.stop()
        wizard._attempt_pair()
        self.assertEqual(session.proc.commands.count("pair " + MAC), 2)
        session._data("Failed to pair: org.bluez.Error.ConnectionAttemptFailed\n")
        self.assertFalse(wizard._retry_timer.isActive())
        self.assertIsNone(wizard._paired)
        self.assertFalse(wizard.retry_btn.isHidden())
        self.assertFalse(any(cmd.startswith("remove ") for cmd in session.proc.commands))

    def test_pair_success_trusts_connects_then_stops_discovery(self):
        wizard = self.wizard()
        wizard._pair()
        session = wizard.session
        session._data("Pairing successful\n")
        self.assertEqual(session.proc.commands[-1], "trust " + MAC)
        session._data("Changing " + MAC + " trust succeeded\n")
        self.assertEqual(wizard._paired, MAC)
        self.assertEqual(session.proc.commands[-2:], ["connect " + MAC, "scan off"])

    def test_authentication_error_not_retried_and_cleanup_stops_timeout(self):
        wizard = self.wizard()
        wizard._pair()
        session = wizard.session
        session._data("Failed to pair: org.bluez.Error.AuthenticationFailed\n")
        self.assertFalse(wizard._retry_timer.isActive())
        wizard._pair()
        self.assertTrue(session._timer.isActive())
        wizard._cleanup()
        self.assertFalse(session._timer.isActive())
        self.assertTrue(session.closed)


class SystemKeyboardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for key in ("VCONSOLE", "XORG", "DEBIAN", "LOCALE"):
            p = patch.object(keyboard, key, str(self.root / key))
            p.start()
            self.addCleanup(p.stop)

    def test_installer_polish_console_pl2_graphical_pl_and_variant(self):
        (self.root / "VCONSOLE").write_text('KEYMAP="pl2"\nXKBLAYOUT="pl"\nXKBVARIANT=""\n')
        self.assertEqual(keyboard.system_settings()["layout"], "pl")
        with patch.object(labwc.config, "get", side_effect=lambda key, default=None: default):
            env = labwc.environment_file()
        self.assertIn("XKB_DEFAULT_LAYOUT=pl\n", env)
        self.assertNotIn("XKB_DEFAULT_LAYOUT=pl2", env)
        (self.root / "VCONSOLE").write_text('KEYMAP="us"\nXKBLAYOUT="pl"\nXKBVARIANT="qwertz"\nXKBOPTIONS="grp:alt_shift_toggle"\n')
        settings = keyboard.system_settings()
        self.assertEqual(settings["layout"], "pl")
        self.assertEqual(settings["variant"], "qwertz")
        self.assertEqual(settings["options"], "grp:alt_shift_toggle")
        self.assertEqual(keyboard.effective_settings("us"), {"layout": "us", "variant": "", "model": "", "options": ""})

    def test_xorg_precedes_console_and_legacy_pl2_is_converted(self):
        (self.root / "VCONSOLE").write_text('KEYMAP="pl2"\n')
        self.assertEqual(keyboard.system_settings()["layout"], "pl")
        (self.root / "XORG").write_text('Section "InputClass"\nOption "XkbLayout" "de"\nOption "XkbVariant" "nodeadkeys"\nEndSection\n')
        settings = keyboard.system_settings()
        self.assertEqual(settings["layout"], "de")
        self.assertEqual(settings["variant"], "nodeadkeys")

    def test_system_locale_fallback_and_keyboard_panel_resolved_label(self):
        from horyzont.apps.control import applets_basic
        (self.root / "LOCALE").write_text('LANG="pl_PL.UTF-8"\n')
        self.assertEqual(keyboard.system_settings()["layout"], "pl")
        with patch.object(applets_basic, "input_devices", return_value=[]):
            panel = applets_basic.KeyboardProperties()
            self.assertIn("[pl]", panel.layout_combo.itemText(0))
            panel.deleteLater()

    def test_resolved_polish_layout_produces_aogonek_in_real_xkb(self):
        (self.root / "VCONSOLE").write_text('KEYMAP="pl2"\nXKBLAYOUT="pl"\n')

        class Names(ctypes.Structure):
            _fields_ = [(name, ctypes.c_char_p) for name in ("rules", "model", "layout", "variant", "options")]

        try:
            lib = ctypes.CDLL("libxkbcommon.so.0")
        except OSError:
            self.skipTest("libxkbcommon unavailable")
        lib.xkb_context_new.argtypes, lib.xkb_context_new.restype = [ctypes.c_int], ctypes.c_void_p
        lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(Names), ctypes.c_int]
        lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        lib.xkb_keymap_key_get_syms_by_level.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32))]
        lib.xkb_keysym_to_utf32.argtypes, lib.xkb_keysym_to_utf32.restype = [ctypes.c_uint32], ctypes.c_uint32
        lib.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
        lib.xkb_context_unref.argtypes = [ctypes.c_void_p]
        context = lib.xkb_context_new(0)
        names = Names(None, None, keyboard.system_settings()["layout"].encode(), None, None)
        keymap = lib.xkb_keymap_new_from_names(context, ctypes.byref(names), 0)
        try:
            self.assertTrue(keymap)
            symbols = ctypes.POINTER(ctypes.c_uint32)()
            n = lib.xkb_keymap_key_get_syms_by_level(keymap, 38, 0, 2, ctypes.byref(symbols))
            self.assertGreater(n, 0)
            self.assertEqual(chr(lib.xkb_keysym_to_utf32(symbols[0])), "ą")  # AltGr+A
        finally:
            if keymap:
                lib.xkb_keymap_unref(keymap)
            lib.xkb_context_unref(context)


if __name__ == "__main__":
    unittest.main()
