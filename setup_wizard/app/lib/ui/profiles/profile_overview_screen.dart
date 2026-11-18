// Written by Claude Code
//
// Hub area "Overview" of a profile: the projector's warnings (not connected, display id or mode changed since it was
// chosen) with the way to the Projectors area, the setup seen from the front or a side (SetupDrawingView, once a
// camera pose or the projection is calibrated), and below it the "To do" list: what the profile still needs, in the
// order it is best done (add a camera, choose the projector, per camera lens calibration and camera pose, the
// projector calibration, the apps). Each step that can run has a button that opens its area (through the hub); a
// step that needs another one first says which. Clicking a camera in the drawing opens its images and settings in
// the Cameras area, clicking the projector opens the Projectors area. The Run button floats over this area
// (profile_hub_screen.dart).

import 'package:flutter/material.dart';

import '../cameras/camera_section_view.dart';
import '../core/ui/profile_run_view.dart';
import '../projectors/projector_display_status_view.dart';
import '../../data/services/setup_geometry_api.dart';
import 'setup_drawing_view.dart';
import '../core/ui/profile_summary_loading.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';
import '../../config/wizard_icons.dart';

/// A step the profile still needs: what it is, why, and the button that opens where it is done.
class _MissingSetupStep {
  const _MissingSetupStep({
    required this.titleText,
    this.explanationText,
    this.buttonLabel = WizardStrings.calibrateButtonLabel,
    this.onButtonPressed,
    this.isOptional = false,
  });

  final String titleText;

  /// Below the title: what the step is for, or what it needs first.
  final String? explanationText;
  final String buttonLabel;

  /// Opens where the step is done; null when it cannot run yet (explanationText says why).
  final VoidCallback? onButtonPressed;

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
    required this.onAddCameraRequested,
    required this.onAppsAreaRequested,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// Called with a camera unit and the section to open for it: a camera clicked in the drawing, or a missing
  /// calibration step started.
  final ValueChanged<CameraSectionRequest> onCameraSectionRequested;

  /// Called when the projector was clicked in the drawing or a projector warning's button, to open the Projectors
  /// area.
  final VoidCallback onProjectorClicked;

  /// Called to open the Cameras area with its Add camera dialog.
  final VoidCallback onAddCameraRequested;

  /// Called to open the Apps area.
  final VoidCallback onAppsAreaRequested;

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

  void _requestCameraSection(String cameraName, CameraSection cameraSection) {
    widget.onCameraSectionRequested((cameraName: cameraName, cameraSection: cameraSection));
  }

  /// What the profile still needs, in the order it is best done: a camera, the projector, each camera's lens
  /// calibration and pose, then the projector calibration (it belongs to the main camera, the profile's first, which
  /// the framework nodes use) and the apps.
  List<_MissingSetupStep> _createMissingSetupSteps(ProfileSummary profileSummary, SetupGeometry setupGeometry) {
    final List<_MissingSetupStep> missingSteps = [];
    if (profileSummary.cameras.isEmpty) {
      missingSteps.add(_MissingSetupStep(
        titleText: WizardStrings.addCameraToDoTitle,
        explanationText: WizardStrings.addCameraToDoText,
        buttonLabel: WizardStrings.addCameraButtonLabel,
        onButtonPressed: widget.onAddCameraRequested,
      ));
    }
    final bool isProjectorChosen = profileSummary.projectorDisplayState != ProjectorDisplayState.notSet;
    if (!isProjectorChosen) {
      missingSteps.add(_MissingSetupStep(
        titleText: WizardStrings.chooseProjectorToDoTitle,
        explanationText: WizardStrings.chooseProjectorToDoText,
        buttonLabel: WizardStrings.chooseButtonLabel,
        onButtonPressed: widget.onProjectorClicked,
      ));
    }

    CameraCalibrationSummary? mainCamera;
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      if (camera.isMainCamera) {
        mainCamera = camera;
      }
      missingSteps.addAll(_createMissingCameraSteps(camera));
    }

    if (mainCamera != null) {
      missingSteps.addAll(_createMissingProjectorSteps(profileSummary, setupGeometry, mainCamera, isProjectorChosen));
    }

    if (profileSummary.enabledAppNames.isEmpty) {
      missingSteps.add(_MissingSetupStep(
        titleText: WizardStrings.chooseAppsToDoTitle,
        explanationText: WizardStrings.chooseAppsToDoText,
        buttonLabel: WizardStrings.openAppsButtonLabel,
        onButtonPressed: widget.onAppsAreaRequested,
      ));
    }
    return missingSteps;
  }

  /// The camera's lens calibration and camera pose, where missing.
  List<_MissingSetupStep> _createMissingCameraSteps(CameraCalibrationSummary camera) {
    final List<_MissingSetupStep> missingSteps = [];
    if (camera.intrinsicsState == IntrinsicsCalibrationState.missing) {
      missingSteps.add(_MissingSetupStep(
        titleText: WizardStrings.getLensCalibrationTitle(cameraName: camera.cameraName),
        explanationText: WizardStrings.setFocusBeforeLensCalibrationText,
        onButtonPressed: () => _requestCameraSection(camera.cameraName, CameraSection.lensCalibration),
      ));
    }
    if (camera.poseState == CameraPoseState.placeholder || camera.poseState == CameraPoseState.invalid) {
      String explanationText = WizardStrings.cameraPoseMissingText;
      if (camera.poseState == CameraPoseState.invalid) {
        explanationText = WizardStrings.cameraPoseFileUnusableText;
      }
      missingSteps.add(_MissingSetupStep(
        titleText: WizardStrings.getCameraPoseTitle(cameraName: camera.cameraName),
        explanationText: explanationText,
        onButtonPressed: () => _requestCameraSection(camera.cameraName, CameraSection.cameraPose),
      ));
    }
    return missingSteps;
  }

  /// The projector calibration against the main camera, then the optional projector position.
  List<_MissingSetupStep> _createMissingProjectorSteps(
    ProfileSummary profileSummary,
    SetupGeometry setupGeometry,
    CameraCalibrationSummary mainCamera,
    bool isProjectorChosen,
  ) {
    final ProjectorGeometry? projector = setupGeometry.projector;
    if (projector == null) {
      String projectorTitleText = WizardStrings.overviewProjectorTitle;
      if (profileSummary.projectorTitleText.isNotEmpty) {
        projectorTitleText = WizardStrings.getOverviewProjectorTitle(
          projectorTitleText: profileSummary.projectorTitleText,
        );
      }
      String explanationText = WizardStrings.getProjectionMappingMissingText(cameraName: mainCamera.cameraName);
      VoidCallback? onCalibratePressed;
      if (isProjectorChosen) {
        onCalibratePressed = () => _requestCameraSection(mainCamera.cameraName, CameraSection.projectorCalibration);
      } else {
        explanationText = '$explanationText ${WizardStrings.chooseProjectorFirstText}';
      }
      return [
        _MissingSetupStep(
          titleText: projectorTitleText,
          explanationText: explanationText,
          onButtonPressed: onCalibratePressed,
        ),
      ];
    }
    if (projector.centerM == null) {
      // Simplification: whether a camera delivers depth is known only while it runs (extrinsics_api.py), so this
      // step never gets a button here. Upgrade: a depth flag per camera in the profile summary, then a button to
      // the Projector section of a depth camera.
      return [
        const _MissingSetupStep(
          titleText: WizardStrings.projectorPositionTitle,
          explanationText: WizardStrings.projectorPositionMissingText,
          isOptional: true,
        ),
      ];
    }
    return [];
  }

  Widget _buildMissingSetupStepRow(_MissingSetupStep missingStep) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    Icon stepIcon = Icon(WizardIcons.toDoStateIcon, color: colorScheme.error);
    String titleText = missingStep.titleText;
    if (missingStep.isOptional) {
      stepIcon = Icon(WizardIcons.optionalStepStateIcon, color: colorScheme.onSurfaceVariant);
      titleText = WizardStrings.getOptionalCalibrationTitle(titleText: titleText);
    }
    Widget? subtitle;
    final String? explanationText = missingStep.explanationText;
    if (explanationText != null) {
      subtitle = Text(explanationText);
    }
    Widget? trailingButton;
    final VoidCallback? onButtonPressed = missingStep.onButtonPressed;
    if (onButtonPressed != null) {
      trailingButton = FilledButton.tonal(onPressed: onButtonPressed, child: Text(missingStep.buttonLabel));
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
    warningRows.add(
      OutlinedButton(onPressed: widget.onProjectorClicked, child: const Text(WizardStrings.openProjectorsButtonLabel)),
    );
    warningRows.add(const SizedBox(height: 24));
    return warningRows;
  }

  /// The setup drawing, below it the To do list and the files the drawing had to leave out.
  List<Widget> _buildSetupDrawingAndToDoRows(ProfileSummary profileSummary) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final String? setupGeometryErrorText = _setupGeometryErrorText;
    final SetupGeometry? setupGeometry = _setupGeometry;
    if (setupGeometryErrorText != null) {
      return [
        Row(
          children: [
            Expanded(
              child: Text(
                WizardStrings.getSetupGeometryErrorText(setupGeometryErrorText: setupGeometryErrorText),
                style: TextStyle(color: colorScheme.error),
              ),
            ),
            TextButton(onPressed: _loadSetupGeometry, child: const Text(WizardStrings.retryButtonLabel)),
          ],
        ),
      ];
    }
    if (setupGeometry == null) {
      return [const LinearProgressIndicator()];
    }

    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> setupRows = [];
    // Once a camera pose is measured or the projection is calibrated: the table with what the steps below fill in.
    // Before, the bare table would push the To do list out of sight
    final bool hasSomethingToDraw = getDrawnCameras(setupGeometry).isNotEmpty || setupGeometry.projector != null;
    if (hasSomethingToDraw) {
      setupRows.add(SetupDrawingView(
        setupGeometry: setupGeometry,
        onCameraClicked: _openCameraInCamerasArea,
        onProjectorClicked: widget.onProjectorClicked,
      ));
      setupRows.add(const SizedBox(height: 24));
    }
    final List<_MissingSetupStep> missingSteps = _createMissingSetupSteps(profileSummary, setupGeometry);
    setupRows.add(Text(WizardStrings.toDoHeading, style: textTheme.titleMedium));
    if (missingSteps.isEmpty) {
      setupRows.add(ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(WizardIcons.doneOutlinedStateIcon, color: colorScheme.primary),
        title: const Text(WizardStrings.everythingSetUpText),
      ));
    }
    for (final _MissingSetupStep missingStep in missingSteps) {
      setupRows.add(_buildMissingSetupStepRow(missingStep));
    }
    // A file the drawing had to leave out, e.g. one edited by hand
    for (final String geometryErrorText in setupGeometry.geometryErrorTexts) {
      setupRows.add(
        Text(
          WizardStrings.getGeometryErrorText(geometryErrorText: geometryErrorText),
          style: TextStyle(color: colorScheme.error),
        ),
      );
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
        children: [..._buildProjectorWarningRows(profileSummary), ..._buildSetupDrawingAndToDoRows(profileSummary)],
      ),
    );
  }
}
