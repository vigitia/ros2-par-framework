# Written by Claude Code
"""
Setup wizard for the PAR framework on the host.

Pages: profile, projector, camera, calibration, nodes, start. Every choice is stored in the chosen
profile (par_setup.yaml or profiles/<name>.yaml); calibrations, launches and builds run as
subprocesses whose output goes to the log below the pages. Start it with ./scripts/wizard.sh,
which sources the workspace.
"""

from datetime import datetime
import json
import os
import signal
import subprocess
import sys

from par_framework_core.launch_helpers import (CAMERA_IMAGE, config_file, DRIVER_REMAPPINGS,
                                               EXTRINSICS, INTRINSICS)
from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox,
                               QSplitter, QVBoxLayout, QWidget, QWizard, QWizardPage)
import rclpy
from rclpy.signals import SignalHandlerOptions
from shiboken6 import isValid

from . import profiles
from .hardware import CAMERAS, detect_cameras
from .preview import Preview

PAGE_PROFILE, PAGE_PROJECTOR, PAGE_CAMERA, PAGE_CALIBRATION, PAGE_NODES, PAGE_START = range(6)
# par_launch switches and their labels
NODES = {'object_detector': 'Object detector', 'fiducials_detector': 'Fiducials detector',
         'hand_landmarks': 'Hand landmarks', 'page_locator': 'Page locator (needs fiducials)',
         'gesture_detector': 'Gesture detector (needs hand landmarks)',
         'projection_mask': 'Projection mask (needs depth camera and calibration)',
         'rviz': 'RViz (with rviz_bridge)'}
# Nodes that open a window on the projector
DISPLAY_NODES = ('surface_selector_node', 'projection_calibrator_node', 'projection_mask_node')
# A new profile has these instead of a display and a camera, so the wizard asks for both anew
NO_DISPLAY = -1
NO_CAMERA = ''
IDENTIFY_MS = 4000
STOP_TIMEOUT_MS = 10000
PREVIEW_PERIOD_MS = 100
SIGNAL_CHECK_MS = 200
# The generic webcam's v4l2_camera node
WEBCAM_NODE = '/camera/webcam/webcam_node'
# A camera's intrinsics, shared by all profiles (launch_helpers sets each camera's camera_info_url)
CAMERA_CALIBRATION = INTRINSICS + '/camera_info_{}.yaml'
# Square size of scripts/checkerboard.png as printed for the setup, in metres
DEFAULT_SQUARE_M = 0.031

# Azure Kinect driver settings (k4a_ros_device_node), with the driver's defaults. Choices: the
# value stored, and its label; the value's type is the parameter's type, which the driver
# insists on
KINECT_NODE = 'k4a_ros_device_node'
KINECT_CHOICES = {
    'color_resolution': ('Colour resolution', '720P', [(r, r) for r in (
        '720P', '1080P', '1440P', '1536P', '2160P', '3072P')]),
    # PASSIVE_IR is left out: it has no depth, which the detectors use
    'depth_mode': ('Depth mode', 'NFOV_UNBINNED', [
        ('NFOV_2X2BINNED', 'NFOV 2x2 binned (narrow, 0.5-5.5 m)'),
        ('NFOV_UNBINNED', 'NFOV unbinned (narrow, 0.5-3.9 m)'),
        ('WFOV_2X2BINNED', 'WFOV 2x2 binned (wide, 0.25-2.9 m)'),
        ('WFOV_UNBINNED', 'WFOV unbinned (wide, 0.25-2.2 m, max. 15 fps)')]),
    'fps': ('Frame rate', 5, [(5, '5 fps'), (15, '15 fps'), (30, '30 fps')]),
    'exposure_control_mode': ('Exposure', 'manual', [('auto', 'auto'), ('manual', 'manual')]),
    'white_balance_control_mode': ('White balance', 'auto',
                                   [('auto', 'auto'), ('manual', 'manual')]),
    'powerline_frequency': ('Powerline frequency', 2, [(1, '50 Hz'), (2, '60 Hz')]),
}
# The colour camera's ranges (Azure Kinect SDK); white balance in steps of 10 K
KINECT_NUMBERS = {
    'exposure_time_absolute': ('Exposure time (µs)', 16670, 500, 133330, 10),
    'white_balance': ('White balance (K)', 4500, 2500, 12500, 10),
    'brightness': ('Brightness', 128, 0, 255, 1),
    'contrast': ('Contrast', 5, 0, 10, 1),
    'saturation': ('Saturation', 32, 0, 63, 1),
    'sharpness': ('Sharpness', 2, 0, 4, 1),
    'gain': ('Gain', 0, 0, 255, 1),
}
# Switches: bool parameters, except backlight_compensation, an int 0/1 in the driver
KINECT_SWITCHES = {
    'backlight_compensation': ('Backlight compensation', 0),
    'point_cloud': ('Point cloud on /points2 (CPU heavy)', True),
    'rgb_point_cloud': ('Colour in the point cloud', False),
}
# The Kinect cannot run these at 30 fps
KINECT_MAX_15_FPS = {'depth_mode': 'WFOV_UNBINNED', 'color_resolution': '3072P'}


def describe_time(timestamp):
    """Return a timestamp as e.g. '2 hours ago (today at 17:16)'."""
    then, now = datetime.fromtimestamp(timestamp), datetime.now()
    seconds = (now - then).total_seconds()
    ago = 'just now'
    for unit, size in (('day', 86400), ('hour', 3600), ('minute', 60)):
        if seconds >= size:
            count = int(seconds // size)
            ago = f'{count} {unit}{"" if count == 1 else "s"} ago'
            break
    days = (now.date() - then.date()).days
    if days == 0:
        day = 'today'
    elif days == 1:
        day = 'yesterday'
    else:
        day = f'on {then:%-d %b}' + ('' if then.year == now.year else f' {then.year}')
    return f'{ago} ({day} at {then:%H:%M})'


def describe_display(display):
    """
    Return one line about an SDL display (displays.py list): its name and size from SDL.

    Qt adds the model, refresh rate and whether it is the primary display, for the screen at the
    same position; SDL and Qt count the displays differently, the position is the same.
    """
    screen = next((s for s in QGuiApplication.screens()
                   if (s.geometry().x(), s.geometry().y()) == (display['x'], display['y'])), None)
    size = f"{display['width']} x {display['height']}"
    parts = [display['name'] or 'unnamed']
    if screen is not None:
        parts.append(screen.model() or screen.manufacturer() or screen.name())
        size += f' @ {screen.refreshRate():.0f} Hz'
    parts.append(size)
    if display['x'] is not None:
        parts.append(f"at {display['x']},{display['y']}")
    if screen is not None and screen == QGuiApplication.primaryScreen():
        parts.append('primary')
    return ' · '.join(parts)


def set_up(profile):
    """Return whether profile has a projector display and a camera, i.e. can be started."""
    return (profile.value('par_launch', 'camera', NO_CAMERA) != NO_CAMERA
            and profile.value('projection_calibrator_node', 'display_id', NO_DISPLAY) >= 0)


def file_status(path):
    """Return 'Done <when>' when path exists, else 'Not done yet'."""
    if not os.path.exists(path):
        return 'Not done yet'
    return f'Done {describe_time(os.path.getmtime(path))}'


class Processes:
    """Runs commands in the repository root, logs their output, ends them like Ctrl-C does."""

    def __init__(self, log):
        self.log = log
        self.running = []
        self.environment = QProcessEnvironment.systemEnvironment()
        # Colour codes would show up as garbage in the log; unbuffered Python prints at once
        self.environment.insert('RCUTILS_COLORIZED_OUTPUT', '0')
        self.environment.insert('PYTHONUNBUFFERED', '1')

    def start(self, label, command, on_finished=None):
        """Start command (a list), logged under label; on_finished(exit_code) when it ends."""
        # The log as parent keeps it alive for a pending kill timer after Python dropped it
        process = QProcess(self.log)
        process.setWorkingDirectory(profiles.repo_root())
        process.setProcessEnvironment(self.environment)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self.__append(label, process))
        process.finished.connect(
            lambda code, _: self.__finished(label, process, code, on_finished))
        self.log.appendPlainText(f'[{label}] $ {" ".join(command)}')
        process.start(command[0], command[1:])
        self.running.append(process)
        return process

    def __append(self, label, process):
        text = bytes(process.readAllStandardOutput()).decode(errors='replace')
        for line in text.splitlines():
            self.log.appendPlainText(f'[{label}] {line}')

    def __finished(self, label, process, code, on_finished):
        if process in self.running:
            self.running.remove(process)
        self.log.appendPlainText(f'[{label}] ended with exit code {code}')
        if on_finished:
            on_finished(code)

    def stop(self, process):
        """End process with SIGINT, so ros2 launch stops its nodes cleanly; kill it if it hangs."""
        if process.state() == QProcess.NotRunning:
            return
        os.kill(process.processId(), signal.SIGINT)
        QTimer.singleShot(STOP_TIMEOUT_MS, process.kill)

    def stop_all(self):
        """Stop every running process and wait for them (when the wizard closes)."""
        processes = list(self.running)
        for process in processes:
            self.stop(process)
        for process in processes:
            if not process.waitForFinished(STOP_TIMEOUT_MS):
                process.kill()


class ProfilePage(QWizardPage):
    """Choose or create the profile, start it directly, or rebuild the workspace."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Profile')
        self.setSubTitle('A profile is one parameter file: par_setup.yaml (default) or '
                         'profiles/<name>.yaml. Start one directly, or press Next to set it up; '
                         'every page stores its choices in it.')
        self.processes = wizard.processes
        self.quick_start = False

        self.profiles = QListWidget()
        self.profiles.itemDoubleClicked.connect(lambda *_: self.start_now())
        start_button = QPushButton('Start selected profile')
        start_button.clicked.connect(lambda *_: self.start_now())
        new_button = QPushButton('New profile…')
        new_button.clicked.connect(lambda *_: self.new_profile())
        self.delete_button = QPushButton('Delete profile…')
        self.delete_button.clicked.connect(lambda *_: self.delete_profile())
        # The default profile is tracked in git and the template for new ones
        self.profiles.currentRowChanged.connect(lambda *_: self.delete_button.setEnabled(
            self.profiles.currentItem() is not None
            and self.selected() != profiles.DEFAULT_PROFILE))
        build_button = QPushButton('Rebuild workspace (scripts/local_build.sh)')
        build_button.clicked.connect(
            lambda *_: self.processes.start('build', ['./scripts/local_build.sh']))

        buttons = QHBoxLayout()
        buttons.addWidget(start_button)
        buttons.addWidget(new_button)
        buttons.addWidget(self.delete_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.profiles)
        layout.addLayout(buttons)
        layout.addWidget(QLabel('After changing node code or pulling node updates:'))
        layout.addWidget(build_button)
        self.refresh()

    def refresh(self, selected=profiles.DEFAULT_PROFILE):
        self.profiles.clear()
        names = profiles.list_profiles()
        self.profiles.addItems(names)
        self.profiles.setCurrentRow(names.index(selected))

    def selected(self):
        return self.profiles.currentItem().text()

    def new_profile(self):
        name, ok = QInputDialog.getText(self, 'New profile',
                                        'Name (it starts from the defaults in par_setup.yaml, '
                                        'with nothing chosen yet):')
        if not ok or not name:
            return
        try:
            profiles.create_profile(name, profiles.DEFAULT_PROFILE)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, 'New profile', str(e))
            return
        # The choices the wizard asks for are unset; camera tuning, QoS etc. stay the defaults
        profile = profiles.Profile(name)
        for node in DISPLAY_NODES:
            profile.set_value(node, 'display_id', NO_DISPLAY)
        profile.set_value('par_launch', 'camera', NO_CAMERA)
        for node in NODES:
            profile.set_value('par_launch', node, False)
        profile.save()
        self.refresh(name)

    def delete_profile(self):
        name = self.selected()
        if QMessageBox.question(
                self, 'Delete profile',
                f'Delete profile "{name}" ({os.path.basename(profiles.profile_path(name))})? '
                'The calibrations are shared by all profiles and stay.') != QMessageBox.Yes:
            return
        profiles.delete_profile(name)
        self.refresh()

    def start_now(self):
        """Jump to the Start page and start the selected profile there."""
        profile = profiles.Profile(self.selected())
        if not set_up(profile):
            QMessageBox.information(self, 'Start',
                                    f'Profile "{profile.name}" is not set up yet: press Next to '
                                    'choose the projector, the camera and the nodes.')
            return
        self.quick_start = True
        wizard = self.wizard()
        wizard.next()
        if wizard.currentId() == PAGE_START:
            wizard.page(PAGE_START).toggle()

    def initializePage(self):
        self.quick_start = False

    def validatePage(self):
        self.wizard().profile = profiles.Profile(self.selected())
        # Automatic or manual is asked anew for every profile
        self.wizard().page(PAGE_CALIBRATION).reset_mode()
        return True

    def nextId(self):
        return PAGE_START if self.quick_start else PAGE_PROJECTOR


class ProjectorPage(QWizardPage):
    """Choose the projector's display, as pygame counts them (display_id)."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Projector')
        self.setSubTitle('Choose the display the projector is connected to. Identify shows each '
                         "display's number on it.")
        self.processes = wizard.processes
        self.pattern = None

        self.displays = QListWidget()
        self.displays.currentRowChanged.connect(lambda *_: self.completeChanged.emit())
        identify_button = QPushButton('Identify')
        identify_button.clicked.connect(lambda *_: self.identify())
        self.pattern_button = QPushButton('Show test pattern')
        self.pattern_button.clicked.connect(lambda *_: self.toggle_pattern())
        buttons = QHBoxLayout()
        buttons.addWidget(identify_button)
        buttons.addWidget(self.pattern_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.displays)
        layout.addLayout(buttons)

    def initializePage(self):
        # pygame's list, in a process of its own; its last output line is the JSON
        result = subprocess.run([sys.executable, '-m', 'par_setup_wizard.displays', 'list'],
                                capture_output=True, text=True, timeout=30)
        displays = json.loads(result.stdout.strip().splitlines()[-1])
        self.displays.clear()
        for index, display in enumerate(displays):
            self.displays.addItem(f'Display {index}: {describe_display(display)}')
        current = self.wizard().profile.value('projection_calibrator_node', 'display_id',
                                              NO_DISPLAY)
        # Nothing selected for a new profile (or a display that is gone): Next waits for a choice
        self.displays.setCurrentRow(current if 0 <= current < len(displays) else -1)

    def isComplete(self):
        return self.displays.currentRow() >= 0

    def show_on_display(self, mode, index):
        return self.processes.start(f'display {index}', [
            sys.executable, '-m', 'par_setup_wizard.displays', mode, str(index)])

    def identify(self):
        shown = [self.show_on_display('number', index) for index in range(self.displays.count())]
        QTimer.singleShot(IDENTIFY_MS, lambda: [self.processes.stop(p) for p in shown])

    def toggle_pattern(self):
        if self.pattern is None and self.displays.currentRow() < 0:
            return
        if self.pattern is None:
            self.pattern = self.show_on_display('grid', self.displays.currentRow())
            self.pattern.finished.connect(lambda *_: self.pattern_ended())
            self.pattern_button.setText('Hide test pattern')
        else:
            self.processes.stop(self.pattern)

    def pattern_ended(self):
        self.pattern = None
        self.pattern_button.setText('Show test pattern')

    def cleanupPage(self):
        if self.pattern is not None:
            self.processes.stop(self.pattern)

    def validatePage(self):
        self.cleanupPage()
        profile = self.wizard().profile
        for node in DISPLAY_NODES:
            profile.set_value(node, 'display_id', self.displays.currentRow())
        profile.save()
        return True


class KinectSettings(QGroupBox):
    """The Azure Kinect driver's settings, read from and stored in the profile."""

    def __init__(self):
        super().__init__('Azure Kinect settings')
        self.choices = {}
        self.numbers = {}
        self.switches = {}
        form = QFormLayout(self)
        for key, (label, _, options) in KINECT_CHOICES.items():
            combo = QComboBox()
            for value, text in options:
                combo.addItem(text, value)
            combo.currentIndexChanged.connect(lambda *_: self.update_constraints())
            self.choices[key] = combo
            form.addRow(label, combo)
        for key, (label, _, minimum, maximum, step) in KINECT_NUMBERS.items():
            box = QSpinBox(minimum=minimum, maximum=maximum, singleStep=step)
            self.numbers[key] = box
            form.addRow(label, box)
        for key, (label, _) in KINECT_SWITCHES.items():
            box = QCheckBox(label)
            box.toggled.connect(lambda *_: self.update_constraints())
            self.switches[key] = box
            form.addRow(box)

    def load(self, profile):
        for key, combo in self.choices.items():
            index = combo.findData(profile.value(KINECT_NODE, key, KINECT_CHOICES[key][1]))
            combo.setCurrentIndex(max(index, 0))
        for key, box in self.numbers.items():
            box.setValue(int(profile.value(KINECT_NODE, key, KINECT_NUMBERS[key][1])))
        for key, box in self.switches.items():
            box.setChecked(bool(profile.value(KINECT_NODE, key, KINECT_SWITCHES[key][1])))
        self.update_constraints()

    def store(self, profile):
        for key, combo in self.choices.items():
            profile.set_value(KINECT_NODE, key, combo.currentData())
        for key, box in self.numbers.items():
            profile.set_value(KINECT_NODE, key, box.value())
        for key, box in self.switches.items():
            # Each value keeps the type of the driver's parameter
            default = KINECT_SWITCHES[key][1]
            profile.set_value(KINECT_NODE, key, type(default)(box.isChecked()))

    def update_constraints(self):
        """Disable what the current choices rule out."""
        fps = self.choices['fps']
        max_15 = any(self.choices[key].currentData() == value
                     for key, value in KINECT_MAX_15_FPS.items())
        fps.model().item(fps.findData(30)).setEnabled(not max_15)
        if max_15 and fps.currentData() == 30:
            fps.setCurrentIndex(fps.findData(15))
        self.numbers['exposure_time_absolute'].setEnabled(
            self.choices['exposure_control_mode'].currentData() == 'manual')
        self.numbers['white_balance'].setEnabled(
            self.choices['white_balance_control_mode'].currentData() == 'manual')
        self.switches['rgb_point_cloud'].setEnabled(self.switches['point_cloud'].isChecked())
        if not self.switches['point_cloud'].isChecked():
            self.switches['rgb_point_cloud'].setChecked(False)


class CameraPage(QWizardPage):
    """Choose the camera and its settings, with a live preview."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Camera')
        self.setSubTitle('Choose the camera. Preview starts it with these settings and shows its '
                         'image, to check that it sees the table.')
        self.processes = wizard.processes
        self.launch = None
        self.preview = None

        self.cameras = QListWidget()
        self.cameras.setMaximumHeight(80)
        self.cameras.currentRowChanged.connect(lambda *_: self.camera_changed())
        self.kinect_settings = KinectSettings()
        settings_area = QScrollArea()
        settings_area.setWidget(self.kinect_settings)
        settings_area.setWidgetResizable(True)
        self.settings_area = settings_area
        self.preview_button = QPushButton('Preview')
        self.preview_button.clicked.connect(lambda *_: self.toggle_preview())
        self.image = QLabel('No preview')
        self.image.setAlignment(Qt.AlignCenter)
        # Ignored: the label takes the space the layout gives it, and the frame is scaled to
        # fit, so a large frame can never grow the label beyond the window and get cropped
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setMinimumSize(320, 180)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.show_frame)

        left = QVBoxLayout()
        left.addWidget(self.cameras)
        left.addWidget(settings_area, 1)
        left.addWidget(self.preview_button)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 2)
        layout.addWidget(self.image, 3)

    def camera(self):
        return self.cameras.currentItem().data(Qt.UserRole)

    def initializePage(self):
        detected = detect_cameras()
        self.webcam = detected.get('webcam')
        self.cameras.clear()
        for camera, name in CAMERAS.items():
            item = QListWidgetItem(f'{name}: {detected.get(camera, "not connected")}')
            item.setData(Qt.UserRole, camera)
            self.cameras.addItem(item)
        self.kinect_settings.load(self.wizard().profile)
        camera = self.wizard().camera()
        # Nothing selected for a new profile: Next waits for a choice
        self.cameras.setCurrentRow(list(CAMERAS).index(camera) if camera else -1)
        self.camera_changed()

    def camera_changed(self):
        self.stop_preview()
        chosen = self.cameras.currentItem() is not None
        self.settings_area.setVisible(chosen and self.camera() == 'kinect')
        self.preview_button.setEnabled(chosen)
        self.completeChanged.emit()

    def isComplete(self):
        return self.cameras.currentItem() is not None

    def store(self):
        profile = self.wizard().profile
        profile.set_value('par_launch', 'camera', self.camera())
        if self.camera() == 'kinect':
            self.kinect_settings.store(profile)
        if self.camera() == 'webcam' and self.webcam:
            # The by-id path stays the same across replugs, unlike /dev/videoN
            profile.set_value(WEBCAM_NODE, 'video_device', f'/dev/v4l/by-id/{self.webcam}')
        profile.save()

    def toggle_preview(self):
        if self.launch is not None:
            self.stop_preview()
            return
        # par.launch.py takes the camera and its settings from the profile
        self.store()
        self.launch = self.processes.start('preview', self.wizard().launch_command(
            'par.launch.py', 'camera_only:=true'), lambda _: self.stop_preview())
        self.preview = Preview(CAMERA_IMAGE)
        self.timer.start(PREVIEW_PERIOD_MS)
        self.preview_button.setText('Stop preview')

    def show_frame(self):
        frame = self.preview.frame() if self.preview else None
        if frame is not None:
            height, width = frame.shape[:2]
            image = QImage(frame.data, width, height, 3 * width, QImage.Format_RGB888)
            self.image.setPixmap(QPixmap.fromImage(image).scaled(
                self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def stop_preview(self):
        self.timer.stop()
        if self.preview is not None:
            self.preview.stop()
            self.preview = None
        if self.launch is not None:
            launch, self.launch = self.launch, None
            self.processes.stop(launch)
        self.image.setText('No preview')
        self.preview_button.setText('Preview')

    def cleanupPage(self):
        self.stop_preview()

    def validatePage(self):
        self.stop_preview()
        self.store()
        return True


class CalibrationPage(QWizardPage):
    """Ask automatic or manual first, then the steps that apply, each with status and Run."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Calibration')
        self.setSubTitle('How do you want to calibrate the projection? The steps for your choice '
                         'appear below; run them in order.')
        self.processes = wizard.processes
        self.running = 0
        self.steps = None

        self.automatic = QRadioButton('Automatic: the camera pose is measured from the clear '
                                      'table (Azure Kinect), the projector shows markers')
        self.manual = QRadioButton("Manual: you enter the camera's distance and angle, then "
                                   'click the four corners of the projection area')
        self.mode = QButtonGroup(self)
        for button in (self.automatic, self.manual):
            self.mode.addButton(button)
            button.toggled.connect(lambda checked: checked and self.build_steps())
        self.page_layout = QVBoxLayout(self)
        self.page_layout.addWidget(self.automatic)
        self.page_layout.addWidget(self.manual)
        self.page_layout.addStretch()

    def initializePage(self):
        if self.mode.checkedButton() is not None:
            self.build_steps()

    def reset_mode(self):
        """Clear the automatic/manual choice and its steps."""
        # An exclusive group always keeps one button checked, so it is unchecked without it
        self.mode.setExclusive(False)
        for button in (self.automatic, self.manual):
            button.setChecked(False)
        self.mode.setExclusive(True)
        if self.steps is not None:
            self.steps.deleteLater()
            self.steps = None

    def build_steps(self):
        """Build the rows for the camera and the chosen mode."""
        if self.steps is not None:
            self.steps.deleteLater()
        self.steps = QWidget()
        self.grid = QGridLayout(self.steps)
        self.page_layout.insertWidget(2, self.steps)

        camera = self.wizard().camera()
        automatic = self.automatic.isChecked()
        if camera in ('brio', 'webcam'):
            intrinsics = config_file(CAMERA_CALIBRATION.format(camera))
            self.square = QDoubleSpinBox(decimals=4, minimum=0.001, maximum=1.0,
                                         singleStep=0.001, value=DEFAULT_SQUARE_M, suffix=' m')
            self.add_step('Camera intrinsics (checkerboard, square size:)',
                          lambda: file_status(intrinsics), self.start_intrinsics, self.square)
        if automatic and camera == 'kinect':
            self.add_step('Camera pose (measured from the clear table)',
                          lambda: self.pose_status(camera),
                          lambda done: self.start_launch(
                              'camera pose', 'camera_pose_calibration_kinect.launch.py', done))
        else:
            # Only the Kinect has depth, the others need their pose by hand even when automatic
            self.add_pose_form(camera)
        if automatic:
            mapping = config_file(f'{EXTRINSICS}/projection_mapping_{camera}.yaml')
            self.add_step('Projector mapping (projected markers, clear table)',
                          lambda: file_status(mapping),
                          lambda done: self.start_launch('projector mapping',
                                                         'projection_calibration.launch.py', done,
                                                         f'camera:={camera}'))
        else:
            corners = config_file(f'{EXTRINSICS}/projection_corners_{camera}.yaml')
            self.add_step('Projection corners (click the four corners; Esc cancels)',
                          lambda: file_status(corners),
                          lambda done: self.start_launch('projection corners',
                                                         'calibration.launch.py', done,
                                                         f'camera:={camera}'))

    def pose_status(self, camera):
        pose, source = profiles.current_pose(self.wizard().profile, camera)
        if source == 'placeholder':
            return 'Not done yet (placeholder from the profile)'
        when = describe_time(os.path.getmtime(profiles.pose_file(camera)))
        return f'{"Measured" if source == "measured" else "Entered by hand"} {when}'

    def step_running(self, change):
        """Count running steps; the mode can't change while one runs, its rows would go."""
        self.running += change
        for button in (self.automatic, self.manual):
            button.setEnabled(self.running == 0)

    def add_step(self, title, status, start, extra=None):
        """Add a row: title, extra widget, status(), and a Run/Stop button calling start(done)."""
        row = self.grid.rowCount()
        status_label = QLabel(status())
        button = QPushButton('Run')
        running = []

        def done(_code):
            running.clear()
            self.step_running(-1)
            # The rows are rebuilt when the page is entered again; this one may be gone
            if isValid(button):
                button.setText('Run')
                status_label.setText(status())

        def clicked():
            if running:
                self.processes.stop(running[0])
            else:
                running.append(start(done))
                self.step_running(+1)
                button.setText('Stop')

        button.clicked.connect(lambda *_: clicked())
        self.grid.addWidget(QLabel(title), row, 0)
        if extra is not None:
            self.grid.addWidget(extra, row, 1)
        self.grid.addWidget(status_label, row, 2)
        self.grid.addWidget(button, row, 3)

    def start_launch(self, label, launch_file, done, *arguments):
        return self.processes.start(label, self.wizard().launch_command(launch_file, *arguments),
                                    done)

    def start_intrinsics(self, done):
        calibrator = ['./scripts/run_cameracalibrator.sh',
                      f'{self.square.value()}']
        # Both cameras end up on the framework's /camera/... topics, where the calibrator works
        if self.wizard().camera() == 'webcam':
            # v4l2_camera publishes reliably already, as the calibrator needs it
            camera = self.processes.start('webcam', self.wizard().launch_command(
                'par.launch.py', 'camera_only:=true'))
        else:
            # The calibrator needs the Brio publishing reliably (see run_cameracalibrator.sh),
            # which a launch file cannot override, so it is started directly, remapped as the
            # launch files do (launch_helpers.logitech_brio_node)
            profile = self.wizard().profile
            remappings = [argument for source, target in DRIVER_REMAPPINGS['brio']
                          for argument in ('-r', f'{source}:={target}')]
            camera = self.processes.start('brio', [
                'ros2', 'run', 'logitech_brio', 'logitech_brio', '--ros-args', '--params-file',
                profile.path, '-p', 'qos_reliability:=reliable',
                '-p', self.wizard().brio_camera_info_url(), *remappings])

        def calibrator_done(code):
            self.processes.stop(camera)
            done(code)

        return self.processes.start('cameracalibrator', calibrator, calibrator_done)

    def add_pose_form(self, camera):
        """Add a row for the camera's pose by hand: distance to the table and angle."""
        pose, _ = profiles.current_pose(self.wizard().profile, camera)
        height, tilt = profiles.height_tilt_from_pose(pose)
        height_box = QDoubleSpinBox(decimals=3, minimum=0.1, maximum=5.0, singleStep=0.01,
                                    value=height, suffix=' m')
        tilt_box = QDoubleSpinBox(decimals=1, minimum=-60.0, maximum=60.0, value=tilt,
                                  suffix=' °')
        form = QWidget()
        fields = QFormLayout(form)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.addRow('Distance to the table', height_box)
        fields.addRow('Angle from straight down', tilt_box)
        status_label = QLabel(self.pose_status(camera))
        button = QPushButton('Save')

        def save():
            _, source = profiles.current_pose(self.wizard().profile, camera)
            if source == 'measured' and QMessageBox.question(
                    self, 'Camera pose', 'Replace the measured camera pose with the values '
                    'entered here?') != QMessageBox.Yes:
                return
            profiles.save_manual_pose(camera, pose, height_box.value(), tilt_box.value())
            status_label.setText(self.pose_status(camera))

        for box in (height_box, tilt_box):
            box.valueChanged.connect(lambda *_: status_label.setText('Not saved yet'))
        button.clicked.connect(lambda *_: save())
        row = self.grid.rowCount()
        self.grid.addWidget(QLabel('Camera pose (measure from the lens)'), row, 0)
        self.grid.addWidget(form, row, 1)
        self.grid.addWidget(status_label, row, 2)
        self.grid.addWidget(button, row, 3)


class NodesPage(QWizardPage):
    """Switch the framework's nodes on and off."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Nodes')
        self.setSubTitle('Choose what runs. With the Azure Kinect the detectors use its depth as '
                         'well.')
        self.boxes = {node: QCheckBox(label) for node, label in NODES.items()}
        layout = QVBoxLayout(self)
        for box in self.boxes.values():
            layout.addWidget(box)
        layout.addStretch()

    def initializePage(self):
        for node, box in self.boxes.items():
            box.setChecked(bool(self.wizard().profile.value('par_launch', node, False)))

    def validatePage(self):
        profile = self.wizard().profile
        for node, box in self.boxes.items():
            profile.set_value('par_launch', node, box.isChecked())
        profile.save()
        return True


class StartPage(QWizardPage):
    """Start and stop the framework with the profile."""

    def __init__(self, wizard):
        super().__init__()
        self.setTitle('Start')
        self.processes = wizard.processes
        self.launch = None
        self.summary = QLabel()
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.button = QPushButton('Start')
        self.button.clicked.connect(lambda *_: self.toggle())
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.button)
        layout.addWidget(QLabel('Closing the wizard stops everything it started.'))
        layout.addStretch()

    def initializePage(self):
        profile = self.wizard().profile
        nodes = [label for node, label in NODES.items()
                 if profile.value('par_launch', node, False)]
        self.setSubTitle(f'Profile "{profile.name}": {profile.path}')
        self.summary.setText(
            f'Camera: {CAMERAS[self.wizard().camera()]}\n'
            f'Projector display: {profile.value("projection_calibrator_node", "display_id")}\n'
            f'Nodes: {", ".join(nodes) or "none"}')

    def toggle(self):
        if self.launch is not None:
            self.processes.stop(self.launch)
            return
        # A preview or calibration still running would hold the camera
        self.processes.stop_all()
        self.launch = self.processes.start('framework',
                                           self.wizard().launch_command('par.launch.py'),
                                           self.ended)
        self.button.setText('Stop')

    def ended(self, _code):
        self.launch = None
        self.button.setText('Start')


class SetupWizard(QWizard):
    """The pages, the chosen profile and the processes they start."""

    def __init__(self, processes):
        super().__init__()
        self.setWindowTitle('PAR framework setup')
        # The window's close button ends the wizard (and stops what it started)
        self.setOption(QWizard.NoCancelButton, True)
        # Back only where it does something. QWizard enables it after each page change, so its
        # visibility follows once that is done
        self.currentIdChanged.connect(lambda *_: QTimer.singleShot(0, self.update_back_button))
        self.processes = processes
        self.profile = None
        for page_id, page in enumerate((ProfilePage, ProjectorPage, CameraPage, CalibrationPage,
                                        NodesPage, StartPage)):
            self.setPage(page_id, page(self))

    def update_back_button(self):
        back = self.button(QWizard.BackButton)
        back.setVisible(back.isEnabled())

    def camera(self):
        """Return the profile's camera, or None while none is chosen."""
        return self.profile.value('par_launch', 'camera', NO_CAMERA) or None

    def brio_camera_info_url(self):
        """Return the Brio calibration as a camera_info_url parameter, for a Brio run directly."""
        # The launch files set it themselves (launch_helpers.logitech_brio_node)
        calibration = config_file(CAMERA_CALIBRATION.format('brio'))
        return f'camera_info_url:=file://{calibration}'

    def launch_command(self, launch_file, *arguments):
        """Return ros2 launch of par_framework_core's launch_file with the profile."""
        return ['ros2', 'launch', 'par_framework_core', launch_file,
                f'params_file:={self.profile.path}', *arguments]


class MainWindow(QSplitter):
    """The wizard above, the output of every process it starts below."""

    def __init__(self):
        super().__init__(Qt.Vertical)
        self.setWindowTitle('PAR framework setup')
        log = QPlainTextEdit(readOnly=True)
        log.setMaximumBlockCount(5000)
        log.setPlaceholderText('Nothing started yet. The output of builds, previews, '
                               'calibrations and the framework appears here.')
        self.processes = Processes(log)
        self.wizard = SetupWizard(self.processes)
        # Shown inside this window instead of as a dialog of its own
        self.wizard.setWindowFlags(Qt.Widget)
        self.wizard.finished.connect(self.close)
        output = QWidget()
        output_layout = QVBoxLayout(output)
        output_layout.addWidget(QLabel('<b>Output</b> of the processes the wizard starts'))
        output_layout.addWidget(log)
        self.addWidget(self.wizard)
        self.addWidget(output)
        self.resize(1100, 950)

    def closeEvent(self, event):
        for page_id in (PAGE_PROJECTOR, PAGE_CAMERA):
            self.wizard.page(page_id).cleanupPage()
        self.processes.stop_all()
        super().closeEvent(event)


def main():
    # Without rclpy's own SIGINT handler: it would only shut ROS down and leave the window open
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    app = QApplication(sys.argv)
    window = MainWindow()
    # Ctrl-C closes the window, which stops everything the wizard started
    signal.signal(signal.SIGINT, lambda *_: window.close())
    # Python runs signal handlers only between its own instructions; while Qt's event loop waits
    # in C++, this timer hands control back to Python regularly
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(SIGNAL_CHECK_MS)
    window.show()
    code = app.exec()
    rclpy.try_shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()
