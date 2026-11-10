// Written by Claude Code
//
// One camera's live feeds with, if wanted, its settings next to them (below them in narrow windows), and, if wanted,
// the focus help below the feeds, which frames its measured area on the camera image. The settings can be limited to
// some of them (e.g. only the focus settings on the wizard's Focus page). The settings take the height they need and
// scroll with the page, which has the only scroll bar on the screen. Shared by the wizard's per-camera steps and a
// profile's Cameras area.

import 'package:flutter/material.dart';

import 'camera_preview_view.dart';
import 'camera_settings_view.dart';
import 'focus_api.dart';
import 'focus_assist_view.dart';
import 'setup_wizard_backend_client.dart';

/// Below this width the settings go under the feeds instead of next to them.
const double sideBySideSettingsMinimumWidthLogicalPx = 1000;

class CameraPreviewWithSettingsView extends StatefulWidget {
  const CameraPreviewWithSettingsView({
    super.key,
    required this.backendClient,
    required this.cameraName,
    required this.isSettingsListShown,
    this.profileName,
    this.serial = '',
    this.isFocusAssistShown = true,
    this.settingsTitleText,
    this.isSettingShown,
    this.noShownSettingsText,
  });

  final SetupWizardBackendClient backendClient;

  /// A name from launch_helpers.CAMERA_DRIVER_REMAPPINGS.
  final String cameraName;

  /// Starts the camera with this saved profile's settings; null for par_setup.yaml's.
  final String? profileName;

  /// The unit to open while no saved profile names it yet; empty opens the unit the parameter files name.
  final String serial;

  final bool isSettingsListShown;
  final bool isFocusAssistShown;

  /// Passed on to CameraSettingsView; null for its defaults (every setting, titled with the camera name).
  final String? settingsTitleText;
  final bool Function(String settingName)? isSettingShown;
  final String? noShownSettingsText;

  @override
  State<CameraPreviewWithSettingsView> createState() => _CameraPreviewWithSettingsViewState();
}

class _CameraPreviewWithSettingsViewState extends State<CameraPreviewWithSettingsView> {
  // Keep feeds and settings when the layout switches between side by side and stacked (window resized): with a
  // GlobalKey Flutter moves a widget to its new place instead of disposing it and starting a new one, so the
  // camera keeps running.
  final GlobalKey _cameraPreviewViewKey = GlobalKey();
  final GlobalKey _cameraSettingsViewKey = GlobalKey();
  final GlobalKey _focusAssistViewKey = GlobalKey();

  /// Where the focus help measures, from FocusAssistView to the frame drawn on the camera image.
  final ValueNotifier<FocusMeasuredArea?> _focusMeasuredAreaNotifier = ValueNotifier<FocusMeasuredArea?>(null);

  @override
  void didUpdateWidget(CameraPreviewWithSettingsView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Without the focus help, the preview must not keep framing its last measured area
    if (!widget.isFocusAssistShown) {
      _focusMeasuredAreaNotifier.value = null;
    }
  }

  @override
  void dispose() {
    _focusMeasuredAreaNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // One view for every camera: switching cameras updates it (didUpdateWidget) instead of disposing it.
    final Widget cameraPreviewView = CameraPreviewView(
      key: _cameraPreviewViewKey,
      backendClient: widget.backendClient,
      cameraName: widget.cameraName,
      profileName: widget.profileName,
      serial: widget.serial,
      focusMeasuredArea: _focusMeasuredAreaNotifier,
    );
    final List<Widget> previewRows = [cameraPreviewView];
    if (widget.isFocusAssistShown) {
      previewRows.add(const SizedBox(height: 16));
      previewRows.add(FocusAssistView(
        key: _focusAssistViewKey,
        backendClient: widget.backendClient,
        measuredAreaNotifier: _focusMeasuredAreaNotifier,
      ));
    }
    final Widget previewView = Column(crossAxisAlignment: CrossAxisAlignment.start, children: previewRows);
    if (!widget.isSettingsListShown) {
      return previewView;
    }

    return LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      if (constraints.maxWidth < sideBySideSettingsMinimumWidthLogicalPx) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [previewView, const SizedBox(height: 16), _buildSettingsView()],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: previewView),
          const SizedBox(width: 24),
          Expanded(flex: 2, child: _buildSettingsView()),
        ],
      );
    });
  }

  Widget _buildSettingsView() {
    // The key keeps the settings and their unsaved changes when the layout switches between beside and below
    return CameraSettingsView(
      key: _cameraSettingsViewKey,
      backendClient: widget.backendClient,
      cameraName: widget.cameraName,
      titleText: widget.settingsTitleText,
      isSettingShown: widget.isSettingShown,
      noShownSettingsText: widget.noShownSettingsText,
    );
  }
}
