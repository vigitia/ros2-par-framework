// Written by Claude Code
//
// New profile, step 2: the camera image, focus first, then exposure, gain and white balance, while the projector
// shows black, white or app content. Also opened from the profile overview to redo it.

import 'package:flutter/material.dart';

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

  /// What earlier steps decided; this step adds its own choices.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it).
  final ValueChanged<bool> onCanContinueChanged;

  @override
  Widget build(BuildContext context) {
    return const Text(
      'Set focus, exposure and gain. Not built yet: see the card "Finish setup wizard UI", "Page 3 and following: Camera image" and its sketch.',
    );
  }
}
