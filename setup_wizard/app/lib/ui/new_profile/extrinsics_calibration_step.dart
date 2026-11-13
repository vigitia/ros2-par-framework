// Written by Claude Code
//
// New-profile pages "Camera pose" and "Projector calibration" of one camera: its stored calibration and a run of the
// framework's calibration launch (see ExtrinsicsCalibrationView). They run on the saved profile, which the wizard
// creates when leaving the Projector page. During the camera pose the chosen projector shows black, so its light
// does not disturb the board; the projector calibration needs it. Optional: the framework also runs with the
// placeholder pose and without a projector calibration, so Next stays allowed.

import 'package:flutter/material.dart';

import '../cameras/camera_section_view.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';
import '../../config/wizard_strings.dart';

class ExtrinsicsCalibrationStep extends StatelessWidget {
  const ExtrinsicsCalibrationStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.cameraInstance,
    required this.cameraSection,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this page reads the saved profile's name and the projector.
  final NewProfileDraft newProfileDraft;

  /// The camera this page calibrates.
  final CameraInstanceDraft cameraInstance;
  /// CameraSection.cameraPose or CameraSection.projectorCalibration.
  final CameraSection cameraSection;

  @override
  Widget build(BuildContext context) {
    final String? profileName = newProfileDraft.profileName;
    if (profileName == null) {
      return const Text(WizardStrings.profileWithoutNameText);
    }
    String introductionText = WizardStrings.measureCameraPoseIntroText;
    if (cameraSection == CameraSection.projectorCalibration) {
      introductionText = WizardStrings.calibrateProjectorIntroText;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(introductionText),
        const SizedBox(height: 12),
        CameraSectionView(
          backendClient: backendClient,
          profileName: profileName,
          cameraName: cameraInstance.cameraName,
          cameraSection: cameraSection,
          projectorDisplayId: newProfileDraft.projectorDisplayIds.firstOrNull,
        ),
      ],
    );
  }
}
