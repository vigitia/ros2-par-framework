// Written by Claude Code
//
// New-profile steps "Camera pose" and "Projector calibration": one camera after the other, each with its stored
// calibration and a run of the framework's calibration launch (see ExtrinsicsCalibrationView). They run on the
// saved profile, which the wizard creates when leaving the Intrinsics step. During the camera pose the chosen
// projector shows black, so its light does not disturb the board; the projector calibration needs it. Optional:
// the framework also runs with the placeholder pose and without a projector calibration, so Next stays allowed.

import 'package:flutter/material.dart';

import '../camera_instance_preview_panel.dart';
import '../extrinsics_calibration_view.dart';
import '../projector_blackout_holder.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

class ExtrinsicsCalibrationStep extends StatelessWidget {
  const ExtrinsicsCalibrationStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.calibrationTopic,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this step reads the saved profile's name and the chosen cameras.
  final NewProfileDraft newProfileDraft;
  final ExtrinsicsCalibrationTopic calibrationTopic;

  @override
  Widget build(BuildContext context) {
    final String? profileName = newProfileDraft.profileName;
    if (profileName == null) {
      return const Text('The profile has no name yet: go back to the Hardware step.');
    }
    if (newProfileDraft.cameraInstances.isEmpty) {
      return const Text('No camera was chosen in the hardware step, so there is nothing to calibrate.');
    }
    String introductionText = 'Measure where each camera sits above the table, one after the other.';
    if (calibrationTopic == ExtrinsicsCalibrationTopic.projectorMapping) {
      introductionText = 'Calibrate the projector against each camera, so projected content lands where the camera '
          'sees it. This runs at the table, with the projector on.';
    }
    final List<Widget> stepRows = [Text(introductionText), const SizedBox(height: 12)];
    if (calibrationTopic == ExtrinsicsCalibrationTopic.cameraPose) {
      stepRows.add(ProjectorBlackoutHolder(
        backendClient: backendClient,
        projectorDisplayId: newProfileDraft.projectorDisplayIds.firstOrNull,
      ));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...stepRows,
        CameraInstancePreviewPanel(
          backendClient: backendClient,
          cameraInstances: newProfileDraft.cameraInstances,
          buildSelectedCameraContent: (CameraInstanceDraft selectedInstance) => ExtrinsicsCalibrationView(
            backendClient: backendClient,
            profileName: profileName,
            cameraName: selectedInstance.cameraType,
            calibrationTopic: calibrationTopic,
          ),
        ),
      ],
    );
  }
}
