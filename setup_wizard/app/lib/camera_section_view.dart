// Written by Claude Code
//
// One section of a camera in a saved profile: its images and settings, its lens calibration, its camera pose or the
// projector calibration against it. Holds the rule which of them run under a black projector: the lens calibration
// and the camera pose, so projector light does not disturb the board; the projector calibration needs the light, and
// the camera image may be tuned under it. Used by the profile's Cameras area and the new-profile wizard's pages.

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'camera_preview_with_settings_view.dart';
import 'extrinsics_calibration_view.dart';
import 'intrinsics_calibration_view.dart';
import 'projector_blackout_holder.dart';
import 'setup_wizard_backend_client.dart';

/// What can be shown for a camera; each starts the camera itself, so only one is shown at a time.
enum CameraSection { imageAndSettings, lensCalibration, cameraPose, projectorCalibration }

/// A camera of the profile, by its name, and the section to open for it.
typedef CameraSectionRequest = ({String cameraName, CameraSection cameraSection});

class CameraSectionView extends StatelessWidget {
  const CameraSectionView({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.cameraName,
    required this.cameraSection,
    required this.projectorDisplayId,
  });

  final SetupWizardBackendClient backendClient;

  /// The saved profile the camera starts with and its calibrations are stored in.
  final String profileName;

  /// The camera's name in the profile (par_launch.cameras).
  final String cameraName;
  final CameraSection cameraSection;

  /// The projector's display, kept black during the lens calibration and the camera pose; null when none is known.
  final int? projectorDisplayId;

  @override
  Widget build(BuildContext context) {
    final List<Widget> sectionRows = [];
    final bool needsBlackProjector =
        cameraSection == CameraSection.lensCalibration || cameraSection == CameraSection.cameraPose;
    if (needsBlackProjector) {
      sectionRows.add(ProjectorBlackoutHolder(backendClient: backendClient, projectorDisplayId: projectorDisplayId));
    }
    // Keyed by section, so e.g. the camera pose and the projector calibration (the same view type) each start
    // afresh, while the blackout above stays on between the lens calibration and the camera pose
    sectionRows.add(KeyedSubtree(key: ValueKey<CameraSection>(cameraSection), child: _buildSectionContent()));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: sectionRows);
  }

  PreviewCameraChoice _createPreviewCamera() {
    return PreviewCameraChoice.profileCamera(profileName: profileName, cameraName: cameraName);
  }

  Widget _buildSectionContent() {
    switch (cameraSection) {
      case CameraSection.imageAndSettings:
        return CameraPreviewWithSettingsView(
          backendClient: backendClient,
          previewCamera: _createPreviewCamera(),
          isSettingsListShown: true,
        );
      case CameraSection.lensCalibration:
        return IntrinsicsCalibrationView(
          backendClient: backendClient,
          previewCamera: _createPreviewCamera(),
        );
      case CameraSection.cameraPose:
        return ExtrinsicsCalibrationView(
          backendClient: backendClient,
          profileName: profileName,
          cameraName: cameraName,
          calibrationTopic: ExtrinsicsCalibrationTopic.cameraPose,
        );
      case CameraSection.projectorCalibration:
        return ExtrinsicsCalibrationView(
          backendClient: backendClient,
          profileName: profileName,
          cameraName: cameraName,
          calibrationTopic: ExtrinsicsCalibrationTopic.projectorMapping,
        );
    }
  }
}
