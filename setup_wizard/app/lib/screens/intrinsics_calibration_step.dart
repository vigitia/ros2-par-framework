// Written by Claude Code
//
// New profile, step 3: the cameras' intrinsic calibration. The user goes through the profile's cameras one by one
// and sees a live preview of the selected one. The calibration itself (checkerboard, coverage view) comes later.
// Also to be opened from the profile overview to redo it.

import 'package:flutter/material.dart';

import '../camera_instance_preview_panel.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class IntrinsicsCalibrationStep extends StatelessWidget {
  const IntrinsicsCalibrationStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.onCanContinueChanged,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this step reads the chosen cameras.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it). Not called yet:
  /// Next stays allowed until the calibration itself is built.
  final ValueChanged<bool> onCanContinueChanged;

  @override
  Widget build(BuildContext context) {
    if (newProfileDraft.cameraInstances.isEmpty) {
      return const Text('No camera was chosen in the hardware step, so there is nothing to calibrate.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Calibrate the cameras one after the other.'),
        const SizedBox(height: 12),
        CameraInstancePreviewPanel(
          backendClient: backendClient,
          cameraInstances: newProfileDraft.cameraInstances,
          isSettingsListShown: false,
        ),
      ],
    );
  }
}
