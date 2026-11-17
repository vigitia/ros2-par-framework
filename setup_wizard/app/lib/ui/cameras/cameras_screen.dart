// Written by Claude Code
//
// Hub area "Cameras" of a profile: one tab per camera, like the Sensor nodes area, titled with the camera's name and
// in the profile's order (the first is the main camera, which the framework nodes use). A camera's tab offers, on
// request, its images and settings (changed on the running camera), its lens calibration, camera pose or projector
// calibration (CameraSectionView, which also keeps the projector black where needed), and Remove, which moves the
// camera's calibrations away after a confirmation. Each section button shows whether that step is done or still to
// do. "Add camera" lists the installed and available camera types (OfferPickerDialog; an available one is installed
// first), then adds a named camera of the chosen type (AddCameraDialog, from its unit step) and opens its first step.
// Every camera can be shown and calibrated on its own; a run of the profile starts all of them. Opened with a
// requested camera section (a camera clicked in the Overview's drawing, or a step started in its To do list), the
// area brings that camera's tab to the front and opens the section at once; opened to add a camera, it starts with
// Add camera.

import 'package:flutter/material.dart';

import 'add_camera_dialog.dart';
import '../core/ui/addable_tabs_view.dart';
import 'camera_section_view.dart';
import '../../data/services/cameras_api.dart';
import '../../data/services/install_api.dart';
import '../install/offer_picker_dialog.dart';
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
    this.isAddCameraDialogRequested = false,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// A camera and section to open right away, e.g. a camera clicked in the Overview's drawing; null opens the area
  /// as usual.
  final CameraSectionRequest? requestedCameraSection;

  /// True to start with Add camera, e.g. from the Overview's To do list.
  final bool isAddCameraDialogRequested;

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
    _loadProfileAndAddCameraIfRequested();
  }

  Future<void> _loadProfileAndAddCameraIfRequested() async {
    await _loadProfile();
    if (!mounted || !widget.isAddCameraDialogRequested) {
      return;
    }
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary != null) {
      await _addCamera(profileSummary.cameras);
    }
  }

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> _loadProfile({bool isSpinnerShown = true}) {
    return loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: isSpinnerShown);
  }

  /// Lists the installed and available camera types; returns the chosen one, installed first when it was not. A type
  /// without serial numbers that the profile has already, or whose entry is broken, cannot be chosen.
  Future<String?> _chooseCameraType(List<ProfileCameraUnit> profileCameraUnits) async {
    final Map<String, String> blockedTextByCameraType = {};
    try {
      for (final CameraType cameraType in await widget.backendClient.fetchCameraTypes()) {
        final String? entryErrorText = cameraType.entryErrorText;
        bool isTypeInProfile = false;
        for (final ProfileCameraUnit profileCameraUnit in profileCameraUnits) {
          if (profileCameraUnit.cameraType == cameraType.cameraType) {
            isTypeInProfile = true;
          }
        }
        if (entryErrorText != null) {
          blockedTextByCameraType[cameraType.cameraType] = entryErrorText;
        } else if (isTypeInProfile && !cameraType.hasSerials) {
          blockedTextByCameraType[cameraType.cameraType] = WizardStrings.offerInProfileText;
        }
      }
    } catch (error) {
      _showMessage(describeBackendErrorForUser(error));
      return null;
    }
    if (!mounted) {
      return null;
    }
    final CatalogOffer? chosenOffer = await showOfferPickerDialog(
      context: context,
      backendClient: widget.backendClient,
      offerKind: offerKindCamera,
      dialogTitle: WizardStrings.chooseCameraTypeDialogTitle,
      blockedTextByOfferName: blockedTextByCameraType,
    );
    return chosenOffer?.name;
  }

  Future<void> _addCamera(List<CameraCalibrationSummary> profileCameras) async {
    final List<ProfileCameraUnit> profileCameraUnits = [
      for (final CameraCalibrationSummary camera in profileCameras)
        (cameraName: camera.cameraName, cameraType: camera.cameraType, serial: camera.serial),
    ];
    final String? chosenCameraType = await _chooseCameraType(profileCameraUnits);
    if (chosenCameraType == null || !mounted) {
      return;
    }
    final AddCameraChoice? addCameraChoice = await showDialog<AddCameraChoice>(
      context: context,
      builder: (BuildContext dialogContext) => AddCameraDialog(
        backendClient: widget.backendClient,
        profileCameras: profileCameraUnits,
        cameraTypeToAdd: chosenCameraType,
      ),
    );
    if (addCameraChoice == null) {
      return;
    }
    try {
      await widget.backendClient.addProfileCamera(
        profileName: widget.profileName,
        cameraName: addCameraChoice.cameraName,
        cameraType: addCameraChoice.cameraType,
        serial: addCameraChoice.serial,
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
        _requestedTabCameraName = addCameraChoice.cameraName;
        // A new camera's first step: focus and exposure come before its lens calibration
        _shownCameraSection = CameraSection.imageAndSettings;
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
          _buildCameraTab(cameras[tabIndex], profileSummary, isShownTab),
    );
  }

  Widget _buildCameraTab(
    CameraCalibrationSummary camera,
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
      Expanded(child: Align(alignment: Alignment.topLeft, child: _buildCameraSectionChoice(camera))),
      const SizedBox(width: 12),
      _buildRemoveButton(camera),
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

  /// Removes the camera; also the last one, after which the profile cannot run until a camera is added.
  Widget _buildRemoveButton(CameraCalibrationSummary camera) {
    return Tooltip(
      message: WizardStrings.removeCameraTooltip,
      child: OutlinedButton.icon(
        onPressed: () => _confirmAndRemoveCamera(camera),
        icon: const Icon(Icons.remove_circle_outline),
        label: const Text(WizardStrings.removeButtonLabel),
      ),
    );
  }

  /// Whether the section's step is done for the camera: true, false (still to do) or null (nothing to track, e.g.
  /// the image settings, or a step the camera does not need).
  bool? _isCameraSectionDone(CameraSection cameraSection, CameraCalibrationSummary camera) {
    switch (cameraSection) {
      case CameraSection.imageAndSettings:
        return null;
      case CameraSection.lensCalibration:
        switch (camera.intrinsicsState) {
          case IntrinsicsCalibrationState.calibrated:
          case IntrinsicsCalibrationState.factory:
            return true;
          case IntrinsicsCalibrationState.missing:
            return false;
          case IntrinsicsCalibrationState.unsupported:
            return null;
        }
      case CameraSection.cameraPose:
        return camera.poseState == CameraPoseState.measured;
      case CameraSection.projectorCalibration:
        if (camera.hasProjectionMapping) {
          return true;
        }
        // Needed only against the main camera, whose mapping the framework nodes use
        if (camera.isMainCamera) {
          return false;
        }
        return null;
    }
  }

  /// The section's own icon, or a done or to-do mark where the section's step is tracked.
  Widget _buildCameraSectionIcon(CameraSection cameraSection, IconData sectionIconData, CameraCalibrationSummary camera) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final bool? isSectionDone = _isCameraSectionDone(cameraSection, camera);
    if (isSectionDone == true) {
      return Tooltip(
        message: WizardStrings.cameraSectionDoneTooltip,
        child: Icon(Icons.check_circle, color: colorScheme.primary),
      );
    }
    if (isSectionDone == false) {
      return Tooltip(
        message: WizardStrings.cameraSectionMissingTooltip,
        child: Icon(Icons.radio_button_unchecked, color: colorScheme.error),
      );
    }
    return Icon(sectionIconData);
  }

  Widget _buildCameraSectionChoice(CameraCalibrationSummary camera) {
    return SegmentedButton<CameraSection>(
      emptySelectionAllowed: true,
      // The marks replace the selected check, so done and to do stay visible on the open section
      showSelectedIcon: false,
      segments: [
        ButtonSegment<CameraSection>(
          value: CameraSection.imageAndSettings,
          icon: _buildCameraSectionIcon(CameraSection.imageAndSettings, Icons.tune, camera),
          label: const Text(WizardStrings.cameraImageSettingsTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.lensCalibration,
          icon: _buildCameraSectionIcon(CameraSection.lensCalibration, Icons.center_focus_strong, camera),
          label: const Text(WizardStrings.cameraIntrinsicsTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.cameraPose,
          icon: _buildCameraSectionIcon(CameraSection.cameraPose, Icons.straighten, camera),
          label: const Text(WizardStrings.cameraPoseTabLabel),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.projectorCalibration,
          icon: _buildCameraSectionIcon(CameraSection.projectorCalibration, Icons.video_label, camera),
          label: const Text(WizardStrings.cameraProjectorTabLabel),
        ),
      ],
      selected: {?_shownCameraSection},
      onSelectionChanged: (Set<CameraSection> selectedSections) {
        setState(() {
          _shownCameraSection = selectedSections.firstOrNull;
        });
        // A calibration saved in the section just left shows as done
        _loadProfile(isSpinnerShown: false);
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
