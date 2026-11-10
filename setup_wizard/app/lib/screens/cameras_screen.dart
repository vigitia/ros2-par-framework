// Written by Claude Code
//
// Hub area "Cameras" of a profile: one tab per camera, like the Sensor nodes area. The camera in the tab in front is
// the profile's main camera, the one the next run of the profile starts: bringing another tab to the front stores
// that camera as the main one. Its tab offers, on request, its images and settings (changed on the running camera),
// its lens calibration, camera pose or projector calibration (CameraSectionView, which also keeps the projector
// black where needed), and Remove, which moves the camera's calibrations away after a confirmation. "Add camera" adds
// a camera unit (several units of one type are told apart by their serial number). Only the main camera is ever
// started here, so the driver always opens the unit the profile names and calibrations land in that unit's files.
// Opened with a requested camera section (a camera clicked in the Overview's drawing, or a missing calibration step
// started there), the area brings that camera to the front and opens the section at once.

import 'package:flutter/material.dart';

import '../add_camera_dialog.dart';
import '../addable_tabs_view.dart';
import '../camera_section_view.dart';
import '../cameras_api.dart';
import '../profile_run_view.dart';
import '../profile_summary_loading.dart';
import '../setup_wizard_backend_client.dart';


class CamerasScreen extends StatefulWidget {
  const CamerasScreen({
    super.key,
    required this.backendClient,
    required this.profileName,
    this.requestedCameraSection,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// A camera unit and section to open right away, e.g. a camera clicked in the Overview's drawing; the unit
  /// becomes the main camera like a click on its tab. null opens the area as usual.
  final CameraSectionRequest? requestedCameraSection;

  @override
  State<CamerasScreen> createState() => _CamerasScreenState();
}

class _CamerasScreenState extends State<CamerasScreen> with ProfileSummaryLoading<CamerasScreen> {
  /// Null until the user opens one, so no camera starts unasked.
  CameraSection? _shownCameraSection;

  /// True while a camera is stored as the main one, e.g. after its tab came to the front.
  bool _isSettingMainCamera = false;

  @override
  void initState() {
    super.initState();
    _loadProfileAndOpenRequestedCamera();
  }

  Future<void> _loadProfileAndOpenRequestedCamera() async {
    await _loadProfile();
    final CameraSectionRequest? requestedCameraSection = widget.requestedCameraSection;
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (!mounted || requestedCameraSection == null || profileSummary == null) {
      return;
    }
    CameraCalibrationSummary? requestedCamera;
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      final bool isSameType = camera.cameraType == requestedCameraSection.cameraType;
      if (isSameType && camera.serial == requestedCameraSection.serial) {
        requestedCamera = camera;
      }
    }
    // Only cameras that can be the main camera (not the capture camera)
    if (requestedCamera == null || requestedCamera.previewCameraName == null) {
      return;
    }
    if (!requestedCamera.isMainCamera) {
      await _setMainCamera(requestedCamera);
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _shownCameraSection = requestedCameraSection.cameraSection;
    });
  }

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> _loadProfile({bool isSpinnerShown = true}) {
    return loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: isSpinnerShown);
  }

  CameraCalibrationSummary? _findMainCamera(ProfileSummary profileSummary) {
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      if (camera.isMainCamera) {
        return camera;
      }
    }
    return null;
  }

  /// The cameras in the order of their tabs: by name, so a tab stays where it is when the main camera changes
  /// (the backend lists the main camera first).
  List<CameraCalibrationSummary> _getCamerasInTabOrder(ProfileSummary profileSummary) {
    final List<CameraCalibrationSummary> camerasInTabOrder = List<CameraCalibrationSummary>.of(profileSummary.cameras);
    camerasInTabOrder.sort(
      (CameraCalibrationSummary firstCamera, CameraCalibrationSummary secondCamera) =>
          firstCamera.cameraDisplayName.compareTo(secondCamera.cameraDisplayName),
    );
    return camerasInTabOrder;
  }

  /// Stores the camera as the profile's main camera, the one a run starts; false when that failed.
  Future<bool> _setMainCamera(CameraCalibrationSummary camera) async {
    setState(() {
      _isSettingMainCamera = true;
    });
    bool isCameraSelected = true;
    try {
      await widget.backendClient
          .setProfileMainCamera(profileName: widget.profileName, cameraName: camera.cameraType, serial: camera.serial);
    } catch (error) {
      isCameraSelected = false;
      _showMessage(
        'Could not switch to ${camera.cameraDisplayName}. '
        '${describeBackendErrorForUser(error, isBackendDetailShown: true)}',
      );
    }
    if (isCameraSelected) {
      await _loadProfile(isSpinnerShown: false);
    }
    if (mounted) {
      setState(() {
        _isSettingMainCamera = false;
      });
    }
    return isCameraSelected;
  }

  /// The camera whose tab the user brought to the front becomes the main camera.
  void _onCameraTabShown(CameraCalibrationSummary camera) {
    // The capture camera cannot be the main camera; its tab only says so
    if (camera.previewCameraName == null || camera.isMainCamera) {
      return;
    }
    _setMainCamera(camera);
  }

  Future<void> _addCamera(List<CameraCalibrationSummary> profileCameras) async {
    final List<({String cameraName, String serial})> profileUnits = [
      for (final CameraCalibrationSummary camera in profileCameras) (cameraName: camera.cameraType, serial: camera.serial),
    ];
    final AddCameraChoice? choice = await showDialog<AddCameraChoice>(
      context: context,
      builder: (BuildContext dialogContext) =>
          AddCameraDialog(backendClient: widget.backendClient, profileUnits: profileUnits),
    );
    if (choice == null) {
      return;
    }
    try {
      await widget.backendClient
          .addProfileCamera(profileName: widget.profileName, cameraName: choice.cameraName, serial: choice.serial);
    } catch (error) {
      _showMessage('Could not add the camera. ${describeBackendErrorForUser(error, isBackendDetailShown: true)}');
      return;
    }
    await _loadProfile(isSpinnerShown: false);
  }

  /// Asks first: the camera's calibrations leave the profile with it (they are moved to a folder they can be
  /// restored from by hand). The main camera hands its role to nextMainCamera before it goes, since a profile
  /// always has one camera to run.
  Future<void> _confirmAndRemoveCamera(
    CameraCalibrationSummary camera,
    CameraCalibrationSummary nextMainCamera,
  ) async {
    final bool? isRemovalConfirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text('Remove ${camera.cameraDisplayName}?'),
        content: const Text(
          'The camera leaves this profile together with its lens calibration, camera pose and projector calibration. '
          'The files are moved to config/profiles/.deleted/ and can be restored by hand from there.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(dialogContext).colorScheme.error),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (isRemovalConfirmed != true) {
      return;
    }
    if (camera.isMainCamera) {
      final bool isNextMainCameraSelected = await _setMainCamera(nextMainCamera);
      if (!isNextMainCameraSelected) {
        return;
      }
    }
    try {
      await widget.backendClient
          .removeProfileCamera(profileName: widget.profileName, cameraName: camera.cameraType, serial: camera.serial);
    } catch (error) {
      _showMessage('Could not remove the camera. ${describeBackendErrorForUser(error, isBackendDetailShown: true)}');
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

    final List<CameraCalibrationSummary> camerasInTabOrder = _getCamerasInTabOrder(profileSummary);
    final List<String> tabTitles = [];
    for (final CameraCalibrationSummary camera in camerasInTabOrder) {
      tabTitles.add(camera.cameraDisplayName);
    }
    return AddableTabsView(
      tabTitles: tabTitles,
      // The main camera's tab is in front when the area opens or the main camera changes
      shownTabTitle: _findMainCamera(profileSummary)?.cameraDisplayName,
      addButtonText: 'Add camera',
      addMenuEntries: const [],
      onAddPressed: () => _addCamera(profileSummary.cameras),
      noTabsText: 'The profile has no camera. Add one with "Add camera".',
      onShownTabChanged: (int tabIndex) => _onCameraTabShown(camerasInTabOrder[tabIndex]),
      buildTabContent: (int tabIndex, bool isShownTab) =>
          _buildCameraTab(camerasInTabOrder[tabIndex], camerasInTabOrder, profileSummary, isShownTab),
    );
  }

  Widget _buildCameraTab(
    CameraCalibrationSummary camera,
    List<CameraCalibrationSummary> camerasInTabOrder,
    ProfileSummary profileSummary,
    bool isShownTab,
  ) {
    final List<Widget> tabRows = [];
    if (camera.previewCameraName == null) {
      // The capture camera
      tabRows.add(Text(
        'This camera starts together with the profile\'s main camera. The wizard cannot show or calibrate it on its '
        'own yet.',
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ));
    } else if (!camera.isMainCamera) {
      // In front, but not stored as the main camera (yet): its sections would start another unit
      if (_isSettingMainCamera) {
        tabRows.add(const LinearProgressIndicator());
      } else {
        tabRows.add(const Text('Could not switch to this camera.'));
        tabRows.add(const SizedBox(height: 8));
        tabRows.add(OutlinedButton(onPressed: () => _setMainCamera(camera), child: const Text('Try again')));
      }
    } else {
      tabRows.add(Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: Align(alignment: Alignment.topLeft, child: _buildCameraSectionChoice())),
        const SizedBox(width: 12),
        _buildRemoveButton(camera, camerasInTabOrder),
      ]));
      final CameraSection? shownCameraSection = _shownCameraSection;
      // Only in the tab in front, so a hidden tab never keeps a camera running
      if (shownCameraSection != null && isShownTab) {
        tabRows.add(const SizedBox(height: 16));
        tabRows.add(_buildCameraSection(shownCameraSection, camera, profileSummary));
      }
    }
    return SingleChildScrollView(
      // Room below the content, so a floating button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 16, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: tabRows),
    );
  }

  /// Removes the camera; disabled for the profile's only camera that can run it.
  Widget _buildRemoveButton(CameraCalibrationSummary camera, List<CameraCalibrationSummary> camerasInTabOrder) {
    CameraCalibrationSummary? nextMainCamera;
    for (final CameraCalibrationSummary otherCamera in camerasInTabOrder) {
      final bool isOtherUnit = otherCamera.cameraDisplayName != camera.cameraDisplayName;
      if (isOtherUnit && otherCamera.previewCameraName != null && nextMainCamera == null) {
        nextMainCamera = otherCamera;
      }
    }
    VoidCallback? onRemoveClicked;
    String removeTooltipText = 'A profile needs a camera to run: add another one first.';
    if (nextMainCamera != null) {
      final CameraCalibrationSummary chosenNextMainCamera = nextMainCamera;
      removeTooltipText = 'Remove this camera and its calibrations from the profile.';
      if (!_isSettingMainCamera) {
        onRemoveClicked = () => _confirmAndRemoveCamera(camera, chosenNextMainCamera);
      }
    }
    return Tooltip(
      message: removeTooltipText,
      child: OutlinedButton.icon(
        onPressed: onRemoveClicked,
        icon: const Icon(Icons.remove_circle_outline),
        label: const Text('Remove'),
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
          label: Text('Image & settings'),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.lensCalibration,
          icon: Icon(Icons.center_focus_strong),
          label: Text('Intrinsics'),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.cameraPose,
          icon: Icon(Icons.straighten),
          label: Text('Camera pose'),
        ),
        ButtonSegment<CameraSection>(
          value: CameraSection.projectorCalibration,
          icon: Icon(Icons.video_label),
          label: Text('Projector'),
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

  /// The section of the main camera; the key makes another camera start afresh.
  Widget _buildCameraSection(
    CameraSection cameraSection,
    CameraCalibrationSummary mainCamera,
    ProfileSummary profileSummary,
  ) {
    return CameraSectionView(
      key: ValueKey<String>('${mainCamera.cameraType}-${mainCamera.serial}'),
      backendClient: widget.backendClient,
      profileName: widget.profileName,
      cameraName: mainCamera.cameraType,
      cameraSection: cameraSection,
      projectorDisplayId: profileSummary.projectorDisplayId,
    );
  }
}
