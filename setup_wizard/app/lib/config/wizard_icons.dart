// Written by Claude Code
//
// Every icon the setup wizard shows, named by what it stands for, so an icon is changed in one place. Screens use
// these instead of Icons.* directly. Two names may share a glyph (e.g. Copy in two menus) while each can change alone.

import 'package:flutter/material.dart';

class WizardIcons {
  // Areas of the hub's tab bar
  static const IconData overviewAreaIcon = Icons.dashboard_outlined;
  static const IconData projectorsAreaIcon = Icons.video_stable;
  static const IconData camerasAreaIcon = Icons.videocam_outlined;
  static const IconData sensorNodesAreaIcon = Icons.sensors;
  static const IconData appsAreaIcon = Icons.apps;

  // Sections of a camera in the Cameras area
  static const IconData cameraImageAndSettingsSectionIcon = Icons.tune;
  static const IconData lensCalibrationSectionIcon = Icons.center_focus_strong;
  static const IconData cameraPoseSectionIcon = Icons.straighten;
  static const IconData projectorCalibrationSectionIcon = Icons.video_stable;

  // Buttons and menu entries
  static const IconData addButtonIcon = Icons.add;
  static const IconData disableButtonIcon = Icons.remove_circle_outline;
  static const IconData retryButtonIcon = Icons.refresh;
  static const IconData refreshListButtonIcon = Icons.refresh;
  static const IconData closeDialogButtonIcon = Icons.close;
  static const IconData copyCommandButtonIcon = Icons.copy;
  static const IconData copyProfileMenuIcon = Icons.copy;
  static const IconData deleteProfileMenuIcon = Icons.delete_outline;
  static const IconData profileMenuButtonIcon = Icons.menu;
  static const IconData chosenMenuEntryIcon = Icons.check;
  static const IconData resetToDefaultButtonIcon = Icons.restart_alt;
  static const IconData runButtonIcon = Icons.play_arrow;
  static const IconData stopButtonIcon = Icons.stop;
  static const IconData debugNodeButtonIcon = Icons.bug_report_outlined;
  static const IconData installButtonIcon = Icons.download;
  static const IconData addRepositoryButtonIcon = Icons.add_link;

  // States of steps, calibrations and offers
  static const IconData doneStateIcon = Icons.check_circle;
  static const IconData doneOutlinedStateIcon = Icons.check_circle_outline;
  static const IconData toDoStateIcon = Icons.radio_button_unchecked;
  static const IconData optionalStepStateIcon = Icons.info_outline;
  static const IconData failedStateIcon = Icons.cancel;
  static const IconData unavailableStateIcon = Icons.block;
  static const IconData warningStateIcon = Icons.warning_amber;
  static const IconData projectorDisplayWarningIcon = Icons.warning_amber_rounded;
  static const IconData chosenProjectorDisplayIcon = Icons.check_circle;
  static const IconData calibrationRegionCoveredIcon = Icons.check;
  static const IconData calibrationRegionMissingIcon = Icons.more_horiz;
  static const IconData sensorNodeRunningIcon = Icons.play_circle;
  static const IconData sensorNodeStartingIcon = Icons.hourglass_empty;
  static const IconData installedOfferIcon = Icons.check_circle_outline;
  static const IconData availableOfferIcon = Icons.download_outlined;
  static const IconData projectorBlackedOutIcon = Icons.dark_mode_outlined;
  static const IconData backendUnreachableIcon = Icons.cloud_off;

  // Devices in lists
  static const IconData cameraTypeIcon = Icons.videocam_outlined;
  static const IconData usbCameraUnitIcon = Icons.usb;
}
