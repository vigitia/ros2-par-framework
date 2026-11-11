// Written by Claude Code
//
// New-profile page "Camera setup & focus" of one camera: the live preview with the focus help (sharpness and the
// enlarged image centre) and every setting its driver reports. Image settings and focus share one page because they
// depend on each other: an image that is too dark or too bright cannot be focused, so brightness or exposure often
// has to be set first. Exposure and gain with projector test light come later.

import 'package:flutter/material.dart';

import '../camera_preview_with_settings_view.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class CameraImageStep extends StatelessWidget {
  const CameraImageStep({super.key, required this.backendClient, required this.cameraInstance});

  final SetupWizardBackendClient backendClient;

  /// The camera this page is about.
  final CameraInstanceDraft cameraInstance;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'First adjust the image settings (e.g. exposure, gain, brightness) until the scene is clearly visible, then '
          'set the focus. How the focus is set depends on the camera: a setting in the list, a ring on the lens, or a '
          'control on the device itself. If the camera focuses automatically, switch that off once the image is '
          'sharp, so the focus stays where it is. A camera with a fixed focus needs no focusing.',
        ),
        const SizedBox(height: 12),
        CameraPreviewWithSettingsView(
          backendClient: backendClient,
          previewCamera: cameraInstance.createUnitPreviewCamera(),
          isSettingsListShown: true,
          settingsTitleText: 'Camera settings: ${cameraInstance.cameraName}',
        ),
      ],
    );
  }
}
