// Written by Claude Code
//
// One camera's live feeds with, if wanted, its settings next to them (below them in narrow windows), and the focus
// help below the feeds, which frames its measured area on the camera image. The settings scroll in an area of their
// own, so the feeds stay in place while the user goes through them. Shared by the wizard's per-camera steps and a
// profile's overview.

import 'package:flutter/material.dart';

import 'camera_preview_view.dart';
import 'camera_settings_view.dart';
import 'focus_api.dart';
import 'focus_assist_view.dart';
import 'setup_wizard_backend_client.dart';

/// Below this width the settings go under the feeds instead of next to them.
const double sideBySideSettingsMinimumWidthLogicalPx = 1000;

/// Height of the settings' scroll area next to the feeds: as high as a single feed.
const double sideBySideSettingsHeightLogicalPx = singleFeedHeightLogicalPx;

/// Height of the settings' scroll area below the feeds, small enough to keep the feeds in view.
const double stackedSettingsHeightLogicalPx = 320;

class CameraPreviewWithSettingsView extends StatefulWidget {
  const CameraPreviewWithSettingsView({
    super.key,
    required this.backendClient,
    required this.cameraName,
    required this.isSettingsListShown,
    this.profileName,
  });

  final SetupWizardBackendClient backendClient;

  /// A name from launch_helpers.CAMERA_DRIVER_REMAPPINGS.
  final String cameraName;

  /// Starts the camera with this saved profile's settings; null for par_setup.yaml's.
  final String? profileName;

  final bool isSettingsListShown;

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
      focusMeasuredArea: _focusMeasuredAreaNotifier,
    );
    final Widget previewView = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        cameraPreviewView,
        const SizedBox(height: 16),
        FocusAssistView(
          key: _focusAssistViewKey,
          backendClient: widget.backendClient,
          measuredAreaNotifier: _focusMeasuredAreaNotifier,
        ),
      ],
    );
    if (!widget.isSettingsListShown) {
      return previewView;
    }

    return LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      if (constraints.maxWidth < sideBySideSettingsMinimumWidthLogicalPx) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [previewView, const SizedBox(height: 16), _buildSettingsArea(stackedSettingsHeightLogicalPx)],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: previewView),
          const SizedBox(width: 24),
          Expanded(flex: 2, child: _buildSettingsArea(sideBySideSettingsHeightLogicalPx)),
        ],
      );
    });
  }

  Widget _buildSettingsArea(double areaHeightLogicalPx) {
    // The scroll area with its scroll position moves with the key too.
    return _ScrollingSettingsArea(
      key: _cameraSettingsViewKey,
      areaHeightLogicalPx: areaHeightLogicalPx,
      settingsView: CameraSettingsView(backendClient: widget.backendClient, cameraName: widget.cameraName),
    );
  }
}

/// The settings in a scroll area of fixed height with a visible scroll bar, so they scroll without moving the feeds.
class _ScrollingSettingsArea extends StatefulWidget {
  const _ScrollingSettingsArea({super.key, required this.areaHeightLogicalPx, required this.settingsView});

  final double areaHeightLogicalPx;
  final Widget settingsView;

  @override
  State<_ScrollingSettingsArea> createState() => _ScrollingSettingsAreaState();
}

class _ScrollingSettingsAreaState extends State<_ScrollingSettingsArea> {
  // An own controller, so the always visible scroll bar and the scroll view agree on the position.
  final ScrollController _settingsScrollController = ScrollController();

  @override
  void dispose() {
    _settingsScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.areaHeightLogicalPx,
      child: Scrollbar(
        controller: _settingsScrollController,
        thumbVisibility: true,
        child: SingleChildScrollView(
          controller: _settingsScrollController,
          // Room for the scroll bar, so it does not cover the values.
          padding: const EdgeInsets.only(right: 16),
          child: widget.settingsView,
        ),
      ),
    );
  }
}
