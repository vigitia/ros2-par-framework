// Written by Claude Code
//
// New-profile step "Intrinsics": the cameras' lens calibration, one camera after the other. Each shows where its
// intrinsics come from now and, where the driver can store one, a calibration with a checkerboard (see
// IntrinsicsCalibrationView). Optional: the framework also runs uncalibrated, so Next stays allowed.

import 'package:flutter/material.dart';

import '../camera_instance_preview_panel.dart';
import '../intrinsics_calibration_view.dart';
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

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it). Not called: the
  /// calibration is optional, so Next stays allowed.
  final ValueChanged<bool> onCanContinueChanged;

  @override
  Widget build(BuildContext context) {
    if (newProfileDraft.cameraInstances.isEmpty) {
      return const Text('No camera was chosen in the hardware step, so there is nothing to calibrate.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Calibrate the lens of each camera that needs it, one after the other.'),
        const SizedBox(height: 12),
        CameraInstancePreviewPanel(
          backendClient: backendClient,
          cameraInstances: newProfileDraft.cameraInstances,
          buildSelectedCameraContent: (CameraInstanceDraft selectedInstance) => IntrinsicsCalibrationView(
            backendClient: backendClient,
            cameraName: selectedInstance.cameraType,
          ),
        ),
      ],
    );
  }
}
