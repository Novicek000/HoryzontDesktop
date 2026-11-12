"""Regresje restartu, cache aktualizacji i wyboru źródła Flatpaka."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QStackedWidget

from horyzont.common.app import make_app
from horyzont.common import launcher, privileged, single
from horyzont.common.window import HWindow
from horyzont.apps.control import addremove, updates
from horyzont.updates import core

APP = QApplication.instance() or make_app("test", [])


class RestartTest(unittest.TestCase):
    def test_shell_accepts_legacy_replace_ipc(self):
        from horyzont.shell.main import Shell
        shell = Shell.__new__(Shell)
        with patch.object(launcher, "start_builtin", return_value=True) as start:
            shell.command(["--replace"])
        start.assert_called_once_with("shell", ["--replace"])

    def test_replace_spawns_new_process_instead_of_forwarding_argument(self):
        with patch.object(single, "try_forward", return_value=True) as forward, patch.object(
                launcher, "_spawn", return_value=True) as spawn, patch.object(launcher, "note_program"):
            self.assertTrue(launcher.start_builtin("shell", ["--replace"]))
            forward.assert_not_called()
            self.assertEqual(spawn.call_args.args[0][-2:], ["shell", "--replace"])
            spawn.reset_mock()
            self.assertTrue(launcher.start_builtin("control", ["users"]))
            forward.assert_called_once_with("control", ["users"], 150)
            spawn.assert_not_called()

    def test_update_success_clears_status_then_restarts_and_closes_old_window(self):
        window = updates.UpdatesWindow()
        self.addCleanup(window.deleteLater)
        update = core.Update("horyzont", "horyzont", "Horyzont", "0.4.13", "0.4.14")
        window.updates = [update]
        with patch.object(window, "_selected", return_value=[update]), patch.object(
                window, "_install_horyzont", return_value=True), patch.object(window, "check"), patch.object(
                core, "add_history"), patch.object(core, "clear_completed_updates") as clear, patch.object(
                updates.dialogs, "message", return_value="yes"), patch.object(
                launcher, "start_builtin", return_value=True) as restart, patch.object(
                single, "try_forward"), patch.object(window, "close") as close:
            window.install_selected()
        clear.assert_called_once_with([update])
        restart.assert_called_once_with("shell", ["--replace"])
        close.assert_called_once()


class CachedStatusTest(unittest.TestCase):
    def test_future_environment_update_remains_visible(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, "USER_STATUS", str(Path(tmp)/"user.json")), patch.object(
                core, "SYSTEM_STATUS", str(Path(tmp)/"system.json")), patch.object(
                core, "installed_horyzont_version", return_value="0.4.14"):
            core.write_status([core.Update("horyzont", "horyzont", "Horyzont", "0.4.14", "0.4.15")], core.USER_STATUS)
            self.assertEqual(core.read_status()["count"], 1)

    def test_stale_agent_status_filtered_without_network_and_other_updates_kept(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, "USER_STATUS", str(Path(tmp)/"user.json")), patch.object(
                core, "SYSTEM_STATUS", str(Path(tmp)/"system.json")), patch.object(
                core, "installed_horyzont_version", return_value="0.4.14"):
            installed = core.Update("horyzont", "horyzont", "Horyzont", "0.4.13", "0.4.14")
            pending = core.Update("dnf", "kernel", "kernel", "1", "2")
            core.write_status([installed, pending], core.SYSTEM_STATUS)
            status = core.read_status()
            self.assertEqual(status["count"], 1)
            self.assertEqual(status["items"][0]["id"], "kernel")
            core.clear_completed_updates([pending])
            self.assertEqual(core.read_status()["count"], 0)

    def test_running_old_module_reads_installed_version_from_disk(self):
        with patch.object(core.config, "VERSION", "0.0.0"):
            self.assertNotEqual(core.installed_horyzont_version(), "0.0.0")
            with patch.object(core, "_latest", return_value=None) as latest:
                core.check_horyzont("Novicek000/HoryzontDesktop")
                self.assertEqual(latest.call_args.args[1], core.installed_horyzont_version())


SEARCH = ("org.mozilla.firefox\tFirefox\tWeb browser\t159.0.1\tf43\tfedora\n"
          "org.mozilla.firefox\tFirefox\tWeb browser\t124.0\tf41\tfedora\n"
          "org.mozilla.firefox\tFirefox\tWeb browser\t146.0\tstable\tflathub\n")


class SearchWorker(QObject):
    done = Signal(int, str)
    finished = Signal()
    commands = []

    def __init__(self, args):
        super().__init__()
        self.commands.append(args)

    def start(self):
        self.done.emit(0, SEARCH)
        self.finished.emit()


class FlatpakSourcesTest(unittest.TestCase):
    def setUp(self):
        self.window = addremove.AddRemoveWindow.__new__(addremove.AddRemoveWindow)
        HWindow.__init__(self.window, "Test", "flatpak")
        self.window.stack = QStackedWidget(self.window)
        self.window._build_flatpak()
        self.addCleanup(self.window.deleteLater)
        p = patch.object(addremove, "CommandWorker", SearchWorker)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(addremove, "run", side_effect=lambda args, *rest: (0, "fedora\nflathub\n") if args[1] == "remotes" else (0, ""))
        p.start()
        self.addCleanup(p.stop)
        SearchWorker.commands.clear()
        self.window.fp_q.setText("firefox")

    def test_one_app_with_explicit_origins_and_branches_and_exact_install(self):
        self.window._fp_search()
        self.assertEqual(self.window.fp_tree.topLevelItemCount(), 1)
        row = self.window.fp_tree.topLevelItem(0)
        combo = self.window.fp_tree.itemWidget(row, 3)
        self.assertEqual(combo.count(), 3)
        self.assertEqual(combo.currentData()["remote"], "flathub")
        row.setCheckState(0, Qt.Checked)
        index = next(i for i in range(combo.count()) if combo.itemData(i)["branch"] == "f43")
        combo.setCurrentIndex(index)
        self.assertEqual(row.text(2), "159.0.1")
        self.assertEqual(self.window._fp_cart["org.mozilla.firefox"]["remote"], "fedora")
        self.window._fp_search()
        row = self.window.fp_tree.topLevelItem(0)
        combo = self.window.fp_tree.itemWidget(row, 3)
        self.assertEqual(combo.currentData()["branch"], "f43")
        with patch.object(addremove, "run_job", return_value=(True, "")) as job, patch.object(
                addremove.desktopentry, "all_entries"):
            self.window._fp_primary()
        args = job.call_args.args[3]
        self.assertIn("--system", args)
        self.assertEqual(args[-2:], ["fedora", "org.mozilla.firefox//f43"])
        self.assertFalse(combo.isEnabled())

    def test_scope_switch_clears_cart_and_search_is_limited_to_scope(self):
        self.window._fp_search()
        self.window.fp_tree.topLevelItem(0).setCheckState(0, Qt.Checked)
        self.window.fp_scope.setCurrentIndex(1)
        self.assertEqual(self.window._fp_cart, {})
        self.window._fp_search()
        self.assertIn("--user", SearchWorker.commands[-1])

    def test_multiple_remotes_in_one_result_are_not_silently_truncated(self):
        result = addremove.flatpak_search_results("org.test.App\tApp\tDescription\t1.0\tstable\tfedora, flathub\n")
        self.assertEqual({s["remote"] for s in result[0]["sources"]}, {"fedora", "flathub"})

    def test_delayed_results_from_old_scope_are_ignored(self):
        class DeferredWorker(SearchWorker):
            def start(self):
                pass

        with patch.object(addremove, "CommandWorker", DeferredWorker):
            self.window._fp_search()
            worker = self.window._fp_worker
            self.window.fp_scope.setCurrentIndex(1)
            worker.done.emit(0, SEARCH)
            self.assertEqual(self.window.fp_tree.topLevelItemCount(), 0)
            self.assertEqual(self.window._fp_mode, "installed")
            worker.finished.emit()


class FlatpakSessionTest(unittest.TestCase):
    def test_system_install_keeps_session_bus_and_uses_flatpak_polkit_helper(self):
        class FakePty(QObject):
            data = Signal(str)
            finished = Signal(int)

            def __init__(self, argv, env, parent):
                super().__init__(parent)
                self.argv, self.env = argv, env

        with patch.dict(os.environ, {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}), patch.object(
                privileged, "PtyProcess", FakePty), patch.object(privileged.os, "geteuid", return_value=1000):
            job = privileged.PrivilegedJob(["flatpak", "install", "--system", "-y", "--noninteractive", "flathub", "org.mozilla.firefox"], root=True)
            job.start()
            self.assertEqual(job.proc.argv[0], "flatpak")
            self.assertNotIn("--noninteractive", job.proc.argv)
            self.assertIn("--system", job.proc.argv)
            self.assertEqual(job.proc.env["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/run/user/1000/bus")
            self.assertFalse(job.root)


if __name__ == "__main__":
    unittest.main()
