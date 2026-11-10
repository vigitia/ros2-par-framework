// Written by Claude Code
//
// New-profile page "Intrinsics" of one camera, its lens calibration: where its intrinsics come from now and, where
// the driver can store one, a calibration with a checkerboard (see IntrinsicsCalibrationView). The chosen projector
// shows black meanwhile, so its light does not disturb the board. Runs on the saved profile, whose intrinsics folder
// the calibration is stored in. Optional: the framework also runs uncalibrated, so Next stays allowed.

import 'package:flutter/material.dart';

import '../camera_section_view.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class IntrinsicsCalibrationStep extends StatelessWidget {
  const IntrinsicsCalibrationStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.cameraInstance,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this page reads the saved profile's name and the projector.
  final NewProfileDraft newProfileDraft;

  /// The camera this page calibrates.
  final CameraInstanceDraft cameraInstance;

  @override
  Widget build(BuildContext context) {
    // The wizard saved the profile when leaving the Projector page
    final String? profileName = newProfileDraft.profileName;
    if (profileName == null) {
      return const Text('The profile has no name yet: go back to the Hardware step.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Calibrate the lens of this camera, if it needs it.'),
        const SizedBox(height: 12),
        CameraSectionView(
          backendClient: backendClient,
          profileName: profileName,
          cameraName: cameraInstance.cameraType,
          cameraSection: CameraSection.lensCalibration,
          projectorDisplayId: newProfileDraft.projectorDisplayIds.firstOrNull,
        ),
      ],
    );
  }
}
