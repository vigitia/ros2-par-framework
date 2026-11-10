// Written by Claude Code
//
// Hub area "Overview" of a profile: the projector's warnings (not connected, display id or mode changed since it was
// chosen) with the way to the Projectors area, the setup seen from the front (SetupSideView) and the calibration
// steps the profile still misses. Each missing step that can run has a button that opens it in the Cameras area
// (cameras_screen.dart, through the hub); a step that cannot run yet says what it needs. Clicking a camera in the
// drawing opens its images and settings in the Cameras area, clicking the projector opens the Projectors area. The
// Run button floats over this area (profile_hub_screen.dart).

import 'package:flutter/material.dart';

import '../camera_section_view.dart';
import '../profile_run_view.dart';
import '../projector_display_status_view.dart';
import '../setup_geometry_api.dart';
import '../setup_side_view.dart';
import '../profile_summary_loading.dart';
import '../setup_wizard_backend_client.dart';

/// A calibration the profile misses: what it is, and either the camera section that performs it or why it cannot
/// run yet.
class _MissingCalibrationStep {
  const _MissingCalibrationStep({
    required this.titleText,
    this.cameraSectionRequest,
    this.blockedReasonText,
    this.isOptional = false,
  });

  final String titleText;

  /// Where the step runs; null when it cannot run yet.
  final CameraSectionRequest? cameraSectionRequest;

  /// What the step needs before it can run; null when it can run.
  final String? blockedReasonText;

  /// True for a step the framework works without, e.g. the projector's position.
  final bool isOptional;
}

class ProfileOverviewScreen extends StatefulWidget {
  const ProfileOverviewScreen({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.onCameraSectionRequested,
    required this.onProjectorClicked,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// Called with a camera unit and the section to open for it: a camera clicked in the drawing, or a missing
  /// calibration step started.
  final ValueChanged<CameraSectionRequest> onCameraSectionRequested;

  /// Called when the projector was clicked in the drawing or a projector warning's button, to open the Projectors
  /// area.
  final VoidCallback onProjectorClicked;

  @override
  State<ProfileOverviewScreen> createState() => _ProfileOverviewScreenState();
}

class _ProfileOverviewScreenState extends State<ProfileOverviewScreen>
    with ProfileSummaryLoading<ProfileOverviewScreen> {
  /// The drawing and the projector's calibration state; null while loading or when it cannot be read.
  SetupGeometry? _setupGeometry;
  String? _setupGeometryErrorText;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    await loadProfileSummary(widget.backendClient, widget.profileName);
    if (!mounted) {
      return;
    }
    await _loadSetupGeometry();
  }

  /// Apart from the profile, so the app choice still shows when only the geometry cannot be read.
  Future<void> _loadSetupGeometry() async {
    setState(() {
      _setupGeometryErrorText = null;
    });
    try {
      final SetupGeometry setupGeometry = await widget.backendClient.fetchSetupGeometry(widget.profileName);
      if (!mounted) {
        return;
      }
      setState(() {
        _setupGeometry = setupGeometry;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _setupGeometryErrorText = describeBackendErrorForUser(error);
      });
    }
  }

  void _openCameraInCamerasArea(CameraGeometry camera) {
    widget.onCameraSectionRequested((
      cameraType: camera.cameraType,
      serial: camera.serial,
      cameraSection: CameraSection.imageAndSettings,
    ));
  }

  /// The profile's missing calibrations, camera by camera, then the projector's (they belong to the selected camera).
  List<_MissingCalibrationStep> _createMissingCalibrationSteps(
    ProfileSummary profileSummary,
    SetupGeometry setupGeometry,
  ) {
    final List<_MissingCalibrationStep> missingSteps = [];
    CameraCalibrationSummary? selectedCamera;
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      if (camera.isSelected) {
        selectedCamera = camera;
      }
      // The capture camera has no preview of its own, so none of the camera sections can open it
      final bool canBeOpened = camera.previewCameraName != null;
      const String notOpenableReasonText =
          'This camera only starts together with the selected camera, so the wizard cannot calibrate it yet.';
      if (camera.intrinsicsState == IntrinsicsCalibrationState.missing) {
        final String titleText = '${camera.cameraDisplayName}: lens calibration (intrinsics)';
        if (canBeOpened) {
          missingSteps.add(_MissingCalibrationStep(
            titleText: titleText,
            cameraSectionRequest: (
              cameraType: camera.cameraType,
              serial: camera.serial,
              cameraSection: CameraSection.lensCalibration,
            ),
          ));
        } else {
          missingSteps.add(_MissingCalibrationStep(titleText: titleText, blockedReasonText: notOpenableReasonText));
        }
      }
      if (camera.poseState == CameraPoseState.placeholder || camera.poseState == CameraPoseState.invalid) {
        String titleText = '${camera.cameraDisplayName}: camera pose';
        if (camera.poseState == CameraPoseState.invalid) {
          titleText = '${camera.cameraDisplayName}: camera pose (its file cannot be used)';
        }
        missingSteps.add(_MissingCalibrationStep(
          titleText: titleText,
          cameraSectionRequest: (
            cameraType: camera.cameraType,
            serial: camera.serial,
            cameraSection: CameraSection.cameraPose,
          ),
        ));
      }
    }

    if (selectedCamera == null) {
      return missingSteps;
    }
    final ProjectorGeometry? projector = setupGeometry.projector;
    if (projector == null) {
      missingSteps.add(_MissingCalibrationStep(
        titleText: 'Projector calibration (projector to table, with ${selectedCamera.cameraDisplayName})',
        cameraSectionRequest: (
          cameraType: selectedCamera.cameraType,
          serial: selectedCamera.serial,
          cameraSection: CameraSection.projectorCalibration,
        ),
      ));
    } else if (projector.centerM == null) {
      // Simplification: whether a camera delivers depth is known only while it runs (extrinsics_api.py), so this
      // step never gets a button here. Upgrade: a depth flag per camera in the profile summary, then a button to
      // the Projector section of a depth camera.
      missingSteps.add(const _MissingCalibrationStep(
        titleText: 'Projector position (projector centre)',
        blockedReasonText: 'Needs a depth camera: select one under Cameras, then measure it in its Projector '
            'section. Only the projection mask uses it.',
        isOptional: true,
      ));
    }
    return missingSteps;
  }

  Widget _buildMissingCalibrationStepRow(_MissingCalibrationStep missingStep) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    Icon stepIcon = Icon(Icons.error_outline, color: colorScheme.error);
    String titleText = missingStep.titleText;
    if (missingStep.isOptional) {
      stepIcon = Icon(Icons.info_outline, color: colorScheme.onSurfaceVariant);
      titleText = '$titleText (optional)';
    }
    Widget? subtitle;
    final String? blockedReasonText = missingStep.blockedReasonText;
    if (blockedReasonText != null) {
      subtitle = Text(blockedReasonText);
    }
    Widget? trailingButton;
    final CameraSectionRequest? cameraSectionRequest = missingStep.cameraSectionRequest;
    if (cameraSectionRequest != null) {
      trailingButton = FilledButton.tonal(
        onPressed: () => widget.onCameraSectionRequested(cameraSectionRequest),
        child: const Text('Calibrate'),
      );
    }
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: stepIcon,
      title: Text(titleText),
      subtitle: subtitle,
      trailing: trailingButton,
    );
  }

  /// The projector's warnings (not connected, display id or mode changed) with the way to the Projectors area.
  List<Widget> _buildProjectorWarningRows(ProfileSummary profileSummary) {
    final List<String> warningTexts = getProjectorWarningTexts(profileSummary);
    if (warningTexts.isEmpty) {
      return [];
    }
    final List<Widget> warningRows = [];
    for (final String warningText in warningTexts) {
      warningRows.add(ProjectorWarningBox(warningText: warningText));
      warningRows.add(const SizedBox(height: 8));
    }
    warningRows.add(OutlinedButton(onPressed: widget.onProjectorClicked, child: const Text('Open Projectors')));
    warningRows.add(const SizedBox(height: 24));
    return warningRows;
  }

  List<Widget> _buildSetupRows(ProfileSummary profileSummary) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final String? setupGeometryErrorText = _setupGeometryErrorText;
    final SetupGeometry? setupGeometry = _setupGeometry;
    if (setupGeometryErrorText != null) {
      return [
        Row(
          children: [
            Expanded(
              child: Text(
                'Cannot read the setup\'s calibration: $setupGeometryErrorText',
                style: TextStyle(color: colorScheme.error),
              ),
            ),
            TextButton(onPressed: _loadSetupGeometry, child: const Text('Retry')),
          ],
        ),
      ];
    }
    if (setupGeometry == null) {
      return [const LinearProgressIndicator()];
    }

    final List<Widget> setupRows = [
      SetupSideView(
        setupGeometry: setupGeometry,
        onCameraClicked: _openCameraInCamerasArea,
        onProjectorClicked: widget.onProjectorClicked,
      ),
      const SizedBox(height: 24),
      Text('Calibration', style: Theme.of(context).textTheme.titleMedium),
    ];
    final List<_MissingCalibrationStep> missingSteps = _createMissingCalibrationSteps(profileSummary, setupGeometry);
    if (missingSteps.isEmpty) {
      setupRows.add(ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(Icons.check_circle_outline, color: colorScheme.primary),
        title: const Text('All calibrations are done.'),
      ));
    }
    for (final _MissingCalibrationStep missingStep in missingSteps) {
      setupRows.add(_buildMissingCalibrationStepRow(missingStep));
    }
    // A file the drawing had to leave out, e.g. one edited by hand
    for (final String geometryErrorText in setupGeometry.geometryErrorTexts) {
      setupRows.add(Text('Cannot read $geometryErrorText', style: TextStyle(color: colorScheme.error)));
    }
    return setupRows;
  }

  @override
  Widget build(BuildContext context) {
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary == null) {
      return buildProfileLoadStateView(onRetryClicked: _loadProfile);
    }

    return SingleChildScrollView(
      // Room below the content, so the hub's Run button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 24, 24, runButtonClearanceLogicalPx),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [..._buildProjectorWarningRows(profileSummary), ..._buildSetupRows(profileSummary)],
      ),
    );
  }
}
