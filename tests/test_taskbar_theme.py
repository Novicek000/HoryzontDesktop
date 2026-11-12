"""Geometria, przeciąganie, animacja i renderowanie bez sesji Wayland.

Wszystkie obrazy motywu są tworzone w teście; nie zawierają zasobów Windows.
"""
import io
import json
import os
import sys
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal, QProcess, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from horyzont import config
from horyzont.common import taskbarlayout
from horyzont.session import labwc
from horyzont.shell import taskbar
from horyzont.shell.balloon import Balloon, BalloonQueue
from horyzont.theme.builtin import HoryzontTheme
from horyzont.theme.msstyles import MsStylesTheme
from horyzont.updates import core

APP = QApplication.instance() or QApplication([])


class GeometryTest(unittest.TestCase):
    def test_four_edges_and_compositor_margins(self):
        screen = QRect(100, 50, 800, 600)
        for edge, expected in [('bottom', QRect(100, 590, 800, 60)), ('top', QRect(100, 50, 800, 60)),
                               ('left', QRect(100, 50, 160, 600)), ('right', QRect(740, 50, 160, 600))]:
            values = {'taskbar_edge': edge, 'taskbar_rows': 2, 'taskbar_width': 160}
            with patch.object(config, 'get', side_effect=lambda k, d=None: values.get(k, d)), patch.object(labwc, 'load_placement', return_value={}):
                bar = taskbarlayout.geometry(screen, 30)
                self.assertEqual(bar, expected)
                popup = QRect(taskbarlayout.popup_position(bar, QSize(300, 200), screen), QSize(300, 200))
                self.assertTrue(screen.contains(popup))
                thickness = bar.width() if taskbarlayout.vertical() else bar.height()
                xml = labwc.rc_xml(800, 600, thickness)
                self.assertIn(f'<margin {edge}="{thickness-1}"/>', xml)
                values['taskbar_autohide'] = True
                self.assertIn(f'<margin {edge}="0"/>', labwc.rc_xml(800, 600, thickness))


class Backend(QObject):
    added, removed, changed = Signal(object), Signal(object), Signal(object)
    toplevels = []


class FakeTray(QWidget):
    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar
        self.status = Mock()
    def sizeHint(self):
        return QSize(100, 50 if taskbarlayout.vertical() else 30)
    def refresh_status(self):
        pass


class TaskbarTest(unittest.TestCase):
    def setUp(self):
        self.values = {'taskbar_quick_launch': True, 'quick_launch': ['show-desktop', 'explorer'], 'taskbar_locked': True}
        for ctx in (patch.object(config, 'get', side_effect=lambda k, d=None: self.values.get(k, d)),
                    patch.object(config, 'set', side_effect=lambda k, v: self.values.__setitem__(k, v)),
                    patch.object(config, 'watch', return_value=None), patch.object(taskbar, 'Tray', FakeTray)):
            ctx.start(); self.addCleanup(ctx.stop)
        self.shell = Mock()
        self.shell.screen_geometry.return_value = QRect(0, 0, 800, 600)
        self.bar = taskbar.Taskbar(Backend(), self.shell)
        self.bar.setFixedSize(800, 30)
        self.bar.show()
        APP.processEvents()
        self.addCleanup(self.bar.close)

    def test_lock_removes_both_band_handles(self):
        self.assertTrue(self.bar.quick_grip.isHidden())
        self.assertTrue(self.bar.tasks_grip.isHidden())
        self.values['taskbar_locked'] = False
        self.bar.relayout()
        self.assertFalse(self.bar.quick_grip.isHidden())
        self.assertFalse(self.bar.tasks_grip.isHidden())
        QTest.mousePress(self.bar.quick_grip, Qt.LeftButton)
        QTest.mouseMove(self.bar.quick_grip, QPoint(600, 10))
        QTest.mouseRelease(self.bar.quick_grip, Qt.LeftButton)
        self.assertTrue(self.values['taskbar_quick_after'])
        self.values['taskbar_locked'] = True
        self.bar.relayout()
        old = self.bar.quick.geometry()
        self.bar.move_band('quick', QPoint(100, 0))
        self.assertEqual(self.bar.quick.geometry(), old)

    def test_resize_border_and_drag_to_left(self):
        self.values['taskbar_locked'] = False
        self.bar.move(0, 570)
        self.bar.relayout()
        QTest.mousePress(self.bar.resize_handle, Qt.LeftButton, pos=QPoint(400, 1))
        QTest.mouseMove(self.bar.resize_handle, QPoint(400, -59))
        QTest.mouseRelease(self.bar.resize_handle, Qt.LeftButton)
        self.assertEqual(self.values['taskbar_rows'], 3)
        # Wolny obszar samego paska, a nie przycisk aplikacji.
        QTest.mousePress(self.bar, Qt.LeftButton, pos=QPoint(500, 15))
        QTest.mouseMove(self.bar, QPoint(2, -250))
        QTest.mouseRelease(self.bar, Qt.LeftButton)
        self.assertEqual(self.values['taskbar_edge'], 'left')

    def test_autohide_has_intermediate_frames_and_clears_surface(self):
        self.values['taskbar_autohide'] = True
        for edge in ('bottom', 'top', 'left', 'right'):
            self.values['taskbar_edge'] = edge
            self.bar._animation.stop()
            self.bar._slide = 0.0
            self.bar.collapsed = False
            self.bar.collapse()
            self.bar._animation.setCurrentTime(80)
            self.assertGreater(self.bar._slide, 0)
            self.assertLess(self.bar._slide, 1)
            self.bar._animation.setCurrentTime(200)
            image = self.bar.grab().toImage()
            self.assertEqual(image.pixelColor(image.width()//2, image.height()//2).alpha(), 0)
            self.bar.expand()
            self.bar._animation.setCurrentTime(200)
            self.assertEqual(self.bar._slide, 0)
            self.assertTrue(self.bar.start.isVisible())

    def test_vertical_tray_and_quick_sections_do_not_overlap(self):
        self.values.update(taskbar_edge='right', taskbar_quick_after=True, taskbar_locked=False)
        self.bar.setFixedSize(160, 600)
        self.bar.relayout()
        for widget in (self.bar.start, self.bar.quick, self.bar.task_area, self.bar.tray):
            self.assertTrue(self.bar.rect().contains(widget.geometry()))
        self.assertFalse(self.bar.quick.geometry().intersects(self.bar.task_area.geometry()))
        self.assertFalse(self.bar.tray.geometry().intersects(self.bar.quick.geometry()))


class VolumeTest(unittest.TestCase):
    def test_slow_audio_command_does_not_block_and_last_value_precedes_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, 'calls.jsonl')
            exe = Path(tmp, 'wpctl')
            exe.write_text('#!' + sys.executable + '\nimport sys,time,json\ntime.sleep(0.08)\nwith open(' + repr(str(log)) + ', "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
            exe.chmod(0o755)
            with patch.dict(os.environ, {'PATH': tmp+os.pathsep+os.environ['PATH']}), patch('horyzont.common.sounds.play') as sound:
                popup = taskbar.VolumePopup(vol=(50, False))
                popup.slider.setSliderDown(True)
                popup.slider.setValue(10)
                popup._flush()
                self.assertNotEqual(popup._process.state(), QProcess.NotRunning)
                beats = []
                QTimer.singleShot(10, lambda: beats.append(True))
                for value in (20, 40, 80, 97):
                    popup.slider.setValue(value)
                popup.slider.setSliderDown(False)
                deadline = time.monotonic()+3
                while (popup._process.state() != QProcess.NotRunning or popup._pending or not sound.called) and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertTrue(beats)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual([c[-1] for c in calls], ['0.10', '0.97'])
                sound.assert_called_once_with('volume', force=True)
                popup.close()
                popup.deleteLater()


class EdgeBalloonTest(unittest.TestCase):
    def test_tail_and_popup_follow_each_taskbar_edge(self):
        screen = APP.primaryScreen().geometry()
        bar = QWidget()
        queue = BalloonQueue(bar)
        try:
            for edge in ('bottom', 'top', 'left', 'right'):
                with patch.object(config, 'get', side_effect=lambda k, d=None: edge if k == 'taskbar_edge' else d):
                    bar.setGeometry(taskbarlayout.geometry(screen, 30))
                    point = bar.mapToGlobal(bar.rect().center())
                    balloon = Balloon('Test', 'Powiadomienie', parent=bar)
                    queue._place(balloon, {'anchor': lambda: point})
                    self.assertEqual(balloon.tail_side, edge)
                    self.assertEqual(balloon.tail_point, point)
                    self.assertTrue(screen.contains(balloon.geometry()))
                    if edge == 'bottom':
                        self.assertLess(balloon.geometry().bottom(), bar.y()+10)
                    elif edge == 'top':
                        self.assertGreater(balloon.y(), bar.geometry().bottom()-10)
                    elif edge == 'left':
                        self.assertGreater(balloon.x(), bar.geometry().right()-10)
                    else:
                        self.assertLess(balloon.geometry().right(), bar.x()+10)
                    balloon.close()
        finally:
            bar.close()


class ThemeTest(unittest.TestCase):
    def test_asymmetric_three_of_four_rows_remain_three_pixels(self):
        source = QImage(8, 4, QImage.Format_ARGB32)
        source.fill(Qt.white)
        for x in range(8):
            for y in range(3):
                source.setPixelColor(x, y, QColor('#ff8800'))
        result = QImage(50, 200, QImage.Format_ARGB32)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        MsStylesTheme._nine_render(painter, result.rect(), source, 2, 5, 3, 0)
        painter.end()
        self.assertEqual(result.pixelColor(25, 2).name(), '#ff8800')
        for y in (3, 50, 100, 199):
            self.assertEqual(result.pixelColor(25, y).name(), '#ffffff')

    def test_transparency_cache_is_specific_to_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = QImage(4, 4, QImage.Format_RGB32); image.fill(Qt.red)
            image.save(tmp+'/shared.png')
            Path(tmp, 'Normal.ini').write_text('[A]\nImageFile=shared.png\nTransparent=True\nTransparentColor=255 0 0\n[B]\nImageFile=shared.png\nTransparent=False\n')
            theme = MsStylesTheme(tmp, fallback=HoryzontTheme())
            self.assertEqual(theme.frame('A', 1).pixelColor(0, 0).alpha(), 0)
            self.assertEqual(theme.frame('B', 1).pixelColor(0, 0).alpha(), 255)


class DiscoveryTest(unittest.TestCase):
    def test_archival_release_does_not_hide_newer_main(self):
        release = {'tag_name': '0.4.2', 'name': 'old', 'tarball_url': 'old'}
        branch = {'tag_name': '0.4.15', 'name': '0.4.15 (main)', 'tarball_url': 'new'}
        with patch.object(core, '_github', return_value=release), patch.object(core, '_branch_version', return_value=branch):
            self.assertEqual(core._latest('owner/repo', '0.4.13')[:2], ('0.4.15', 'new'))

    def test_network_failure_is_an_error_not_no_updates(self):
        with patch.object(core, '_github', return_value=None), patch.object(core.urllib.request, 'urlopen', side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                core._latest('owner/repo', '0.4.13')

    def test_missing_repo_marker_uses_official_repo(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            self.assertEqual(core.default_repo(), 'Novicek000/HoryzontDesktop')

    def test_lightweight_check_keeps_system_items_and_schedule(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, 'USER_STATUS', tmp+'/user'), patch.object(core, 'SYSTEM_STATUS', tmp+'/system'), patch.object(core, 'SHELL_STATUS', tmp+'/shell'), patch.object(core, 'installed_horyzont_version', return_value='0.4.13'):
            Path(tmp, 'user').write_text(json.dumps({'checked': '2026-11-01', 'items': [{'source': 'dnf', 'id': 'kernel'}]}))
            Path(tmp, 'shell').write_text(json.dumps({'checked': '2026-11-12', 'items': [{'source': 'horyzont', 'id': 'horyzont', 'new': '0.4.15'}]}))
            state = core.read_status()
            self.assertEqual(state['checked'], '2026-11-01')
            self.assertEqual(state['count'], 2)


if __name__ == '__main__':
    unittest.main()
