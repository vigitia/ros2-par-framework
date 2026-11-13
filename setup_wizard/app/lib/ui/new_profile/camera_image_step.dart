// Written by Claude Code
//
// New-profile page "Camera setup & focus" of one camera: the live preview with the focus help (sharpness and the
// enlarged image centre) and every setting its driver reports. Image settings and focus share one page because they
// depend on each other: an image that is too dark or too bright cannot be focused, so brightness or exposure often
// has to be set first. Exposure and gain with projector test light come later.

import 'package:flutter/material.dart';

import '../cameras/camera_preview_with_settings_view.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';
import '../../config/wizard_strings.dart';

class CameraSetupStep extends StatelessWidget {
  const CameraSetupStep({super.key, required this.backendClient, required this.cameraInstance});

  final SetupWizardBackendClient backendClient;

  /// The camera this page is about.
  final CameraInstanceDraft cameraInstance;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          WizardStrings.cameraImageStepText,
        ),
        const SizedBox(height: 12),
        CameraPreviewWithSettingsView(
          backendClient: backendClient,
          previewCamera: cameraInstance.createUnitPreviewCamera(),
          settingsTitleText: WizardStrings.getCameraSettingsStepTitle(cameraName: cameraInstance.cameraName),
        ),
      ],
    );
  }
}
