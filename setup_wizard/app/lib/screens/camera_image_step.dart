// Written by Claude Code
//
// New profile, step 2: the camera image. The user goes through the profile's cameras one by one and sees the live
// preview of the selected one next to its settings, as its driver reports them, with the focus help below the
// preview (sharpness and the enlarged image centre). Exposure and gain with projector test light come later. The
// profile overview shows the same view.

import 'package:flutter/material.dart';

import '../camera_instance_preview_panel.dart';
import '../camera_preview_with_settings_view.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class CameraImageStep extends StatelessWidget {
  const CameraImageStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.onCanContinueChanged,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this step reads the chosen cameras.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it). Not called: Next
  /// stays allowed, since the settings are read-only for now.
  final ValueChanged<bool> onCanContinueChanged;

  @override
  Widget build(BuildContext context) {
    if (newProfileDraft.cameraInstances.isEmpty) {
      return const Text('No camera was chosen in the hardware step, so there is no camera image to set up.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text("Focus each camera and check its image and settings, one after the other."),
        const SizedBox(height: 12),
        CameraInstancePreviewPanel(
          backendClient: backendClient,
          cameraInstances: newProfileDraft.cameraInstances,
          buildSelectedCameraContent: (CameraInstanceDraft selectedInstance) => CameraPreviewWithSettingsView(
            backendClient: backendClient,
            cameraName: selectedInstance.cameraType,
            isSettingsListShown: true,
          ),
        ),
      ],
    );
  }
}
