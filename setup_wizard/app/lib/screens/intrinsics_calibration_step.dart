// Written by Claude Code
//
// New profile, step 3: the camera's intrinsic calibration with a checkerboard and a coverage view. Also opened
// from the profile overview to redo it.

import 'package:flutter/material.dart';

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

  /// What earlier steps decided; this step adds its own choices.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it).
  final ValueChanged<bool> onCanContinueChanged;

  @override
  Widget build(BuildContext context) {
    return const Text(
      'Calibrate the camera lens. Not built yet: see the card "Finish setup wizard UI", "Then: Intrinsic camera calibration" and the intrinsics sketch.',
    );
  }
}
