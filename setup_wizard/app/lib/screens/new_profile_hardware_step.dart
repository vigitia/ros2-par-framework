// Written by Claude Code
//
// New profile, step 1: the camera and the output displays (projectors) of the new hardware setup.

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class NewProfileHardwareStep extends StatelessWidget {
  const NewProfileHardwareStep({
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
      'Choose the camera and the projector display(s). Not built yet: see the card "Finish setup wizard UI", "Page 2 (new profile): Hardware" and its sketch.',
    );
  }
}
