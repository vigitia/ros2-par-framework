// Written by Claude Code
//
// New-profile pages "Focus" and "Image settings" of one camera. Focus: the live preview with the focus help
// (sharpness and the enlarged image centre) and only the camera's focus settings. Image settings: the live preview
// with every other setting, as its driver reports them. The wizard shows the two pages of one camera one after the
// other, and this widget stays in place between them, so the camera keeps running. Exposure and gain with projector
// test light come later. The profile's Cameras area shows all of it on one screen.

import 'package:flutter/material.dart';

import '../camera_preview_with_settings_view.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

enum CameraImagePageTopic { focus, imageSettings }

/// Whether a camera setting is about the lens focus.
/// Special case: ROS has no convention that marks a parameter as the focus, so it is recognised by its name, as
/// drivers usually call it (e.g. v4l2_camera's focus_absolute and focus_automatic_continuous).
bool isFocusSettingName(String settingName) {
  return settingName.toLowerCase().contains('focus');
}

bool isNotFocusSettingName(String settingName) {
  return !isFocusSettingName(settingName);
}

class CameraImageStep extends StatelessWidget {
  const CameraImageStep({
    super.key,
    required this.backendClient,
    required this.cameraInstance,
    required this.cameraImagePageTopic,
  });

  final SetupWizardBackendClient backendClient;

  /// The camera this page is about.
  final CameraInstanceDraft cameraInstance;
  final CameraImagePageTopic cameraImagePageTopic;

  @override
  Widget build(BuildContext context) {
    final String cameraName = cameraInstance.cameraType;
    final bool isFocusPage = cameraImagePageTopic == CameraImagePageTopic.focus;
    String introductionText = 'Adjust exposure, gain and the other image settings while you watch the live image.';
    String settingsTitleText = 'Image settings: $cameraName';
    bool Function(String settingName) isSettingShown = isNotFocusSettingName;
    String noShownSettingsText = 'The driver reports no other settings.';
    if (isFocusPage) {
      introductionText = 'Change the focus until the sharpness bar reaches its best mark and gets no higher. Switch '
          'automatic focus off first, so the focus stays where you set it.';
      settingsTitleText = 'Focus settings: $cameraName';
      isSettingShown = isFocusSettingName;
      noShownSettingsText = 'This camera has no focus setting: turn the lens ring by hand while you watch the bar.';
    }
    // The same widgets on both pages, so the preview keeps running from Focus to Image settings
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(introductionText),
        const SizedBox(height: 12),
        CameraPreviewWithSettingsView(
          backendClient: backendClient,
          cameraName: cameraName,
          isSettingsListShown: true,
          isFocusAssistShown: isFocusPage,
          settingsTitleText: settingsTitleText,
          isSettingShown: isSettingShown,
          noShownSettingsText: noShownSettingsText,
        ),
      ],
    );
  }
}
