// Written by Claude Code
//
// Hub area "Overview" of a profile: the projector's warnings (not connected, display id or mode changed since it was
// chosen) with the way to the Projectors area, the setup seen from the front or a side (SetupDrawingView), below it the cameras
// and the projector the drawing cannot show yet with what each still needs, and the other calibration steps the
// profile misses. Each missing step that can run has a button that opens it in the Cameras area
// (cameras_screen.dart, through the hub); a step that cannot run yet says what it needs. Clicking a camera in the
// drawing opens its images and settings in the Cameras area, clicking the projector opens the Projectors area. The
// Run button floats over this area (profile_hub_screen.dart).

import 'package:flutter/material.dart';

import '../camera_section_view.dart';
import '../profile_run_view.dart';
import '../projector_display_status_view.dart';
import '../setup_geometry_api.dart';
import '../setup_drawing_view.dart';
import '../profile_summary_loading.dart';
import '../setup_wizard_backend_client.dart';

/// A calibration the profile misses: what it is, and the camera section that performs it where there is one.
class _MissingCalibrationStep {
  const _MissingCalibrationStep({
    required this.titleText,
    this.cameraSectionRequest,
    this.missingInDrawingText,
    this.isOptional = false,
  });

  final String titleText;

  /// Where the step runs; null when it cannot run yet.
  final CameraSectionRequest? cameraSectionRequest;

  /// Set for a step without which its device (titleText) is not in the drawing: what the drawing lacks.
  final String? missingInDrawingText;

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
      cameraName: camera.cameraName,
      cameraSection: CameraSection.imageAndSettings,
    ));
  }

  /// The profile's missing calibrations, camera by camera, then the projector's (they belong to the profile's main
  /// camera, its first, which the framework nodes use).
  List<_MissingCalibrationStep> _createMissingCalibrationSteps(
    ProfileSummary profileSummary,
    SetupGeometry setupGeometry,
  ) {
    final List<_MissingCalibrationStep> missingSteps = [];
    CameraCalibrationSummary? mainCamera;
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      if (camera.isMainCamera) {
        mainCamera = camera;
      }
      if (camera.intrinsicsState == IntrinsicsCalibrationState.missing) {
        missingSteps.add(_MissingCalibrationStep(
          titleText: '${camera.cameraName}: lens calibration (intrinsics)',
          cameraSectionRequest: (cameraName: camera.cameraName, cameraSection: CameraSection.lensCalibration),
        ));
      }
      if (camera.poseState == CameraPoseState.placeholder || camera.poseState == CameraPoseState.invalid) {
        String missingInDrawingText =
            'Its camera pose is missing: without it, the wizard does not know where the camera is above the table.';
        if (camera.poseState == CameraPoseState.invalid) {
          missingInDrawingText = 'Its camera pose file cannot be used. Measure the camera pose again.';
        }
        missingSteps.add(_MissingCalibrationStep(
          titleText: camera.cameraName,
          missingInDrawingText: missingInDrawingText,
          cameraSectionRequest: (cameraName: camera.cameraName, cameraSection: CameraSection.cameraPose),
        ));
      }
    }

    if (mainCamera == null) {
      return missingSteps;
    }
    final ProjectorGeometry? projector = setupGeometry.projector;
    if (projector == null) {
      String projectorTitleText = 'Projector';
      if (profileSummary.projectorTitleText.isNotEmpty) {
        projectorTitleText = 'Projector ${profileSummary.projectorTitleText}';
      }
      missingSteps.add(_MissingCalibrationStep(
        titleText: projectorTitleText,
        missingInDrawingText: 'Its projector calibration with ${mainCamera.cameraName} is missing: '
            'without it, the wizard does not know where the projected image lies on the table.',
        cameraSectionRequest: (cameraName: mainCamera.cameraName, cameraSection: CameraSection.projectorCalibration),
      ));
    } else if (projector.centerM == null) {
      // Simplification: whether a camera delivers depth is known only while it runs (extrinsics_api.py), so this
      // step never gets a button here. Upgrade: a depth flag per camera in the profile summary, then a button to
      // the Projector section of a depth camera.
      missingSteps.add(const _MissingCalibrationStep(
        titleText: 'Projector position (projector centre)',
        missingInDrawingText: 'Only the projected image is drawn, not the projector itself. Its position needs a '
            'depth camera: open one under Cameras, then measure it in its Projector section. Only the projection '
            'mask uses it.',
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
    final String? explanationText = missingStep.missingInDrawingText;
    if (explanationText != null) {
      subtitle = Text(explanationText);
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

    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> setupRows = [];
    // Also with nothing measured yet: the bare table, which the steps below fill
    setupRows.add(SetupDrawingView(
      setupGeometry: setupGeometry,
      onCameraClicked: _openCameraInCamerasArea,
      onProjectorClicked: widget.onProjectorClicked,
    ));
    setupRows.add(const SizedBox(height: 24));
    final List<_MissingCalibrationStep> missingSteps = _createMissingCalibrationSteps(profileSummary, setupGeometry);
    final List<_MissingCalibrationStep> stepsMissingInDrawing = [];
    final List<_MissingCalibrationStep> otherMissingSteps = [];
    for (final _MissingCalibrationStep missingStep in missingSteps) {
      if (missingStep.missingInDrawingText != null) {
        stepsMissingInDrawing.add(missingStep);
      } else {
        otherMissingSteps.add(missingStep);
      }
    }
    if (stepsMissingInDrawing.isNotEmpty) {
      setupRows.add(Text('Not in the drawing yet', style: textTheme.titleMedium));
      for (final _MissingCalibrationStep missingStep in stepsMissingInDrawing) {
        setupRows.add(_buildMissingCalibrationStepRow(missingStep));
      }
      setupRows.add(const SizedBox(height: 24));
    }
    setupRows.add(Text('Calibration', style: textTheme.titleMedium));
    if (missingSteps.isEmpty) {
      setupRows.add(ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(Icons.check_circle_outline, color: colorScheme.primary),
        title: const Text('All calibrations are done.'),
      ));
    } else if (otherMissingSteps.isEmpty) {
      setupRows.add(ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(Icons.info_outline, color: colorScheme.onSurfaceVariant),
        title: const Text('Nothing else is missing.'),
      ));
    }
    for (final _MissingCalibrationStep missingStep in otherMissingSteps) {
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
