// Written by Claude Code
//
// One section of a camera in a saved profile: its images and settings, its lens calibration, its camera pose or the
// projector calibration against it. Holds the rule which of them run under a black projector: the lens calibration
// and the camera pose, so projector light does not disturb the board; the projector calibration needs the light, and
// the camera image may be tuned under it. Used by the profile's Cameras area and the new-profile wizard's pages.

import 'package:flutter/material.dart';

import '../../data/services/camera_preview_api.dart';
import 'camera_preview_view.dart';
import 'camera_preview_with_settings_view.dart';
import '../calibration/extrinsics_calibration_view.dart';
import '../calibration/intrinsics_calibration_view.dart';
import '../calibration/projector_blackout_holder.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';

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
        );
      case CameraSection.lensCalibration:
        return _LensCalibrationSection(
          // It reads the camera's state once, so another camera (the next wizard page) needs a new one
          key: ValueKey<String>(cameraName),
          backendClient: backendClient,
          profileName: profileName,
          cameraName: cameraName,
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

/// The lens calibration of a camera, or for a camera that brings its own (its entry says factory) a note above its
/// preview: the preview keeps the camera running while its tab is open, as the camera's other sections do.
class _LensCalibrationSection extends StatefulWidget {
  const _LensCalibrationSection({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.cameraName,
    required this.previewCamera,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;
  final String cameraName;
  final PreviewCameraChoice previewCamera;

  @override
  State<_LensCalibrationSection> createState() => _LensCalibrationSectionState();
}

class _LensCalibrationSectionState extends State<_LensCalibrationSection> {
  /// Null until the profile has been read.
  IntrinsicsCalibrationState? _intrinsicsState;

  /// Set when the profile could not be read; the calibration view is shown then, which checks the camera itself.
  bool _hasReadFailed = false;

  @override
  void initState() {
    super.initState();
    _readIntrinsicsState();
  }

  Future<void> _readIntrinsicsState() async {
    IntrinsicsCalibrationState? intrinsicsState;
    try {
      final ProfileSummary profileSummary = await widget.backendClient.fetchProfileSummary(widget.profileName);
      for (final CameraCalibrationSummary camera in profileSummary.cameras) {
        if (camera.cameraName == widget.cameraName) {
          intrinsicsState = camera.intrinsicsState;
        }
      }
    } catch (error) {
      intrinsicsState = null;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _intrinsicsState = intrinsicsState;
      _hasReadFailed = intrinsicsState == null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final IntrinsicsCalibrationState? intrinsicsState = _intrinsicsState;
    if (intrinsicsState == null && !_hasReadFailed) {
      return const LinearProgressIndicator();
    }
    if (intrinsicsState == IntrinsicsCalibrationState.factory) {
      final Widget factoryCalibrationNote = Row(children: [
        Icon(Icons.check_circle_outline, color: Colors.green.shade400),
        const SizedBox(width: 8),
        const Expanded(
          child: Text(WizardStrings.lensCalibrationNotNeededText),
        ),
      ]);
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          factoryCalibrationNote,
          const SizedBox(height: 12),
          CameraPreviewView(backendClient: widget.backendClient, previewCamera: widget.previewCamera),
        ],
      );
    }
    return IntrinsicsCalibrationView(backendClient: widget.backendClient, previewCamera: widget.previewCamera);
  }
}
