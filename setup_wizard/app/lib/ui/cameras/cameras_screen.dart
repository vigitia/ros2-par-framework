// Written by Claude Code
//
// Hub area "Cameras" of a profile: one tab per camera, like the Sensor nodes area, titled with the camera's name and
// in the profile's order (the first is the main camera, which the framework nodes use). A camera's tab offers, on
// request, its images and settings (changed on the running camera), its lens calibration, camera pose or projector
// calibration (CameraSectionView, which also keeps the projector black where needed), and Remove, which moves the
// camera's calibrations away after a confirmation. "Add camera" adds a named camera (AddCameraDialog). Every camera
// can be shown and calibrated on its own; a run of the profile starts all of them. Opened with a requested camera
// section (a camera clicked in the Overview's drawing, or a missing calibration step started there), the area brings
// that camera's tab to the front and opens the section at once.

import 'package:flutter/material.dart';

import 'add_camera_dialog.dart';
import '../core/ui/addable_tabs_view.dart';
import 'camera_section_view.dart';
import '../../data/services/cameras_api.dart';
import '../core/ui/profile_run_view.dart';
import '../core/ui/profile_summary_loading.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';

class CamerasScreen extends StatefulWidget {
  const CamerasScreen({
    super.key,
    required this.backendClient,
    required this.profileName,
    this.requestedCameraSection,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// A camera and section to open right away, e.g. a camera clicked in the Overview's drawing; null opens the area
  /// as usual.
  final CameraSectionRequest? requestedCameraSection;

  @override
  State<CamerasScreen> createState() => _CamerasScreenState();
}

class _CamerasScreenState extends State<CamerasScreen> with ProfileSummaryLoading<CamerasScreen> {
  /// Null until the user opens one, so no camera starts unasked.
  CameraSection? _shownCameraSection;

  /// The tab to bring to the front, by camera name: the requested camera, or one just added; null keeps the shown
  /// one.
  String? _requestedTabCameraName;

  @override
  void initState() {
    super.initState();
    final CameraSectionRequest? requestedCameraSection = widget.requestedCameraSection;
    if (requestedCameraSection != null) {
      _requestedTabCameraName = requestedCameraSection.cameraName;
      _shownCameraSection = requestedCameraSection.cameraSection;
    }
    _loadProfile();
  }

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> _loadProfile({bool isSpinnerShown = true}) {
    return loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: isSpinnerShown);
  }

  Future<void> _addCamera(List<CameraCalibrationSummary> profileCameras) async {
    final List<ProfileCameraUnit> profileCameraUnits = [
      for (final CameraCalibrationSummary camera in profileCameras)
        (cameraName: camera.cameraName, cameraType: camera.cameraType, serial: camera.serial),
    ];
    final AddCameraChoice? choice = await showDialog<AddCameraChoice>(
      context: context,
      builder: (BuildContext dialogContext) =>
          AddCameraDialog(backendClient: widget.backendClient, profileCameras: profileCameraUnits),
    );
    if (choice == null) {
      return;
    }
    try {
      await widget.backendClient.addProfileCamera(
        profileName: widget.profileName,
        cameraName: choice.cameraName,
        cameraType: choice.cameraType,
        serial: choice.serial,
      );
    } catch (error) {
      _showMessage(
        WizardStrings.getAddCameraErrorText(
          backendErrorText: describeBackendErrorForUser(error, isBackendDetailShown: true),
        ),
      );
      return;
    }
    await _loadProfile(isSpinnerShown: false);
    if (mounted) {
      setState(() {
        _requestedTabCameraName = choice.cameraName;
      });
    }
  }

  /// Asks first: the camera's calibrations leave the profile with it (they are moved to a folder they can be
  /// restored from by hand).
  Future<void> _confirmAndRemoveCamera(CameraCalibrationSummary camera) async {
    final bool? isRemovalConfirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text(WizardStrings.getRemoveCameraDialogTitle(cameraName: camera.cameraName)),
        content: const Text(
          WizardStrings.removeCameraDialogText,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(WizardStrings.cancelButtonLabel),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(dialogContext).colorScheme.error),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(WizardStrings.removeButtonLabel),
          ),
        ],
      ),
    );
    if (isRemovalConfirmed != true) {
      return;
    }
    try {
      await widget.backendClient.removeProfileCamera(profileName: widget.profileName, cameraName: camera.cameraName);
    } catch (error) {
      _showMessage(
        WizardStrings.getRemoveCameraErrorText(
          backendErrorText: describeBackendErrorForUser(error, isBackendDetailShown: true),
        ),
      );
      return;
    }
    await _loadProfile(isSpinnerShown: false);
  }

  void _showMessage(String messageText) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messageText)));
  }

  @override
  Widget build(BuildContext context) {
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary == null) {
      return buildProfileLoadStateView(onRetryClicked: _loadProfile);
    }

    final List<CameraCalibrationSummary> cameras = profileSummary.cameras;
    final List<String> tabTitles = [];
    for (final CameraCalibrationSummary camera in cameras) {
      tabTitles.add(camera.cameraName);
    }
    return AddableTabsView(
      tabTitles: tabTitles,
      shownTabTitle: _requestedTabCameraName,
      addButtonText: WizardStrings.addCameraButtonLabel,
      addMenuEntries: const [],
      onAddPressed: () => _addCamera(cameras),
      noTabsText: WizardStrings.noCameraInProfileText,
      // The user's own choice wins from now on, also when the tabs change later (e.g. a camera removed)
      onShownTabChanged: (int tabIndex) => _requestedTabCameraName = null,
      buildTabContent: (int tabIndex, bool isShownTab) =>
          _buildCameraTab(cameras[tabIndex], cameras.length, profileSummary, isShownTab),
    );
  }

  Widget _buildCameraTab(
    CameraCalibrationSummary camera,
    int cameraCount,
    ProfileSummary profileSummary,
    bool isShownTab,
  ) {
    final List<Widget> tabRows = [];
    String unitText = camera.cameraType;
    if (camera.serial.isNotEmpty) {
      unitText = WizardStrings.getCameraUnitSerialText(unitText: unitText, serial: camera.serial);
    }
    if (camera.isMainCamera) {
      unitText = WizardStrings.getMainCameraUnitText(unitText: unitText);
    }
    tabRows.add(Text(unitText, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)));
    tabRows.add(const SizedBox(height: 12));
    tabRows.add(Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Expanded(child: Align(alignment: Alignment.topLeft, child: _buildCameraSectionChoice())),
      const SizedBox(width: 12),
      _buildRemoveButton(camera, cameraCount),
    ]));
    final CameraSection? shownCameraSection = _shownCameraSection;
    // Only in the tab in front, so a hidden tab never keeps a camera running
    if (shownCameraSection != null && isShownTab) {
      tabRows.add(const SizedBox(height: 16));
      tabRows.add(_buildCameraSection(shownCameraSection, camera, profileSummary));
    }
    return SingleChildScrollView(
      // Room below the content, so a floating button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 16, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: tabRows),
    );
  }

  /// Removes the camera; disabled for the profile's only camera, since a profile needs one to run.
  Widget _buildRemoveButton(CameraCalibrationSummary camera, int cameraCount) {
    VoidCallback? onRemoveClicked;
    String removeTooltipText = WizardStrings.lastCameraRemoveTooltip;
    if (cameraCount > 1) {
      removeTooltipText = WizardStrings.removeCameraTooltip;
      onRemoveClicked = () => _confirmAndRemoveCamera(camera);
    }
    return Tooltip(
      message: removeTooltipText,
      child: OutlinedButton.icon(
        onPressed: onRemoveClicked,
        icon: const Icon(Icons.remove_circle_outline),
        label: const Text(WizardStrings.removeButtonLabel),
      ),
    );
  }

  Widget _buildCameraSectionChoice() {
    return SegmentedButton<CameraSection>(
      emptySelectionAllowed: true,
      segments: const [
        ButtonSegment<CameraSection>(
          value: CameraSection.imageAndSettings,
          icon: Icon(Icons.tune),
          label: Text(WizardStrings.cameraImageSettingsTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.lensCalibration,
          icon: Icon(Icons.center_focus_strong),
          label: Text(WizardStrings.cameraIntrinsicsTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.cameraPose,
          icon: Icon(Icons.straighten),
          label: Text(WizardStrings.cameraPoseTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.projectorCalibration,
          icon: Icon(Icons.video_label),
          label: Text(WizardStrings.cameraProjectorTabLabel),
        ),
      ],
      selected: {?_shownCameraSection},
      onSelectionChanged: (Set<CameraSection> selectedSections) {
        setState(() {
          _shownCameraSection = selectedSections.firstOrNull;
        });
      },
    );
  }

  /// The section of the camera; the key makes another camera start afresh.
  Widget _buildCameraSection(
    CameraSection cameraSection,
    CameraCalibrationSummary camera,
    ProfileSummary profileSummary,
  ) {
    return CameraSectionView(
      key: ValueKey<String>(camera.cameraName),
      backendClient: widget.backendClient,
      profileName: widget.profileName,
      cameraName: camera.cameraName,
      cameraSection: cameraSection,
      projectorDisplayId: profileSummary.projectorDisplayId,
    );
  }
}
