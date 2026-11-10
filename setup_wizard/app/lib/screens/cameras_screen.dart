// Written by Claude Code
//
// Hub area "Cameras" of a profile: its cameras as chips; exactly one is the selected camera, the one the next run of
// the profile starts. Clicking another chip selects it. For the selected camera the user can open, on request, its
// images and settings (changed on the running camera), its lens calibration, camera pose or projector calibration
// (CameraSectionView, which also keeps the projector black where needed). "Add camera" adds a camera unit (several
// units of one type are told apart by their serial number), and a camera that is not selected can be removed, which
// moves its calibrations away after a confirmation. Only the selected camera is ever started here, so the driver
// always opens the unit the profile names and calibrations land in that unit's files. Opened with a requested camera
// section (a camera clicked in the Overview's drawing, or a missing calibration step started there), the area selects
// that camera and opens the section at once.

import 'package:flutter/material.dart';

import '../add_camera_dialog.dart';
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
  /// becomes the selected camera like a click on its chip. null opens the area as usual.
  final CameraSectionRequest? requestedCameraSection;

  @override
  State<CamerasScreen> createState() => _CamerasScreenState();
}

class _CamerasScreenState extends State<CamerasScreen> with ProfileSummaryLoading<CamerasScreen> {
  /// Null until the user opens one, so no camera starts unasked.
  CameraSection? _shownCameraSection;

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
    // Only cameras that can be selected (not the capture camera)
    if (requestedCamera == null || requestedCamera.previewCameraName == null) {
      return;
    }
    if (!requestedCamera.isSelected) {
      await _selectCamera(requestedCamera);
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

  CameraCalibrationSummary? _findSelectedCamera(ProfileSummary profileSummary) {
    for (final CameraCalibrationSummary camera in profileSummary.cameras) {
      if (camera.isSelected) {
        return camera;
      }
    }
    return null;
  }

  Future<void> _selectCamera(CameraCalibrationSummary camera) async {
    try {
      await widget.backendClient
          .selectProfileCamera(profileName: widget.profileName, cameraName: camera.cameraType, serial: camera.serial);
    } catch (error) {
      _showMessage('Could not select the camera. ${describeBackendErrorForUser(error, isBackendDetailShown: true)}');
      return;
    }
    await _loadProfile(isSpinnerShown: false);
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
  /// restored from by hand).
  Future<void> _confirmAndRemoveCamera(CameraCalibrationSummary camera) async {
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

    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> cameraRows = [
      Text('Selected camera', style: textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        'The camera the next run of this profile starts. Click another camera to select it.',
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 8),
      _buildCameraChoice(profileSummary.cameras),
    ];
    final CameraCalibrationSummary? selectedCamera = _findSelectedCamera(profileSummary);
    if (selectedCamera != null) {
      cameraRows.add(const SizedBox(height: 16));
      cameraRows.add(_buildCameraSectionChoice());
      final CameraSection? shownCameraSection = _shownCameraSection;
      if (shownCameraSection != null) {
        cameraRows.add(const SizedBox(height: 16));
        cameraRows.add(_buildCameraSection(shownCameraSection, selectedCamera, profileSummary));
      }
    }
    return SingleChildScrollView(
      // Room below the content, so the hub's Run button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 24, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: cameraRows),
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

  /// The section of the selected camera; the key makes a newly selected camera start afresh.
  Widget _buildCameraSection(
    CameraSection cameraSection,
    CameraCalibrationSummary selectedCamera,
    ProfileSummary profileSummary,
  ) {
    return CameraSectionView(
      key: ValueKey<String>('${selectedCamera.cameraType}-${selectedCamera.serial}'),
      backendClient: widget.backendClient,
      profileName: widget.profileName,
      cameraName: selectedCamera.cameraType,
      cameraSection: cameraSection,
      projectorDisplayId: profileSummary.projectorDisplayId,
    );
  }

  Widget _buildCameraChoice(List<CameraCalibrationSummary> cameras) {
    final List<Widget> cameraChips = [];
    for (final CameraCalibrationSummary camera in cameras) {
      if (camera.previewCameraName == null) {
        // The capture camera: it starts together with the selected camera and cannot be chosen or removed
        cameraChips.add(Tooltip(
          message: 'This camera starts together with the selected camera.',
          child: Chip(avatar: const Icon(Icons.videocam_outlined), label: Text(camera.cameraDisplayName)),
        ));
        continue;
      }
      // The selected camera stays: a profile always has one to run
      final VoidCallback? onRemoveClicked = camera.isSelected ? null : () => _confirmAndRemoveCamera(camera);
      cameraChips.add(InputChip(
        avatar: const Icon(Icons.videocam_outlined),
        label: Text(camera.cameraDisplayName),
        selected: camera.isSelected,
        onSelected: camera.isSelected ? null : (bool isSelected) => _selectCamera(camera),
        onDeleted: onRemoveClicked,
        deleteButtonTooltipMessage: 'Remove this camera',
      ));
    }
    cameraChips.add(ActionChip(
      avatar: const Icon(Icons.add),
      label: const Text('Add camera'),
      onPressed: () => _addCamera(cameras),
    ));
    return Wrap(spacing: 8, runSpacing: 8, children: cameraChips);
  }
}
