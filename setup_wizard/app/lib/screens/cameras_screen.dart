// Written by Claude Code
//
// Hub area "Cameras" of a profile: its cameras as chips; exactly one is the selected camera, the one the next run of
// the profile starts. Clicking another chip selects it. For the selected camera the user can open, on request, its
// images and settings (changed on the running camera), its lens calibration, camera pose or projector calibration;
// during the lens calibration and the camera pose the projector shows black. "Add camera" adds a camera unit (several
// units of one type are told apart by their serial number), and a camera that is not selected can be removed, which
// moves its calibrations away after a confirmation. Only the selected camera is ever started here, so the driver
// always opens the unit the profile names and calibrations land in that unit's files.

import 'package:flutter/material.dart';

import '../add_camera_dialog.dart';
import '../camera_preview_with_settings_view.dart';
import '../cameras_api.dart';
import '../extrinsics_calibration_view.dart';
import '../intrinsics_calibration_view.dart';
import '../projector_blackout_holder.dart';
import '../setup_wizard_backend_client.dart';

/// What this area shows for the selected camera; each starts the camera itself, so only one is shown at a time.
enum CameraSection { imageAndSettings, lensCalibration, cameraPose, projectorCalibration }

class CamerasScreen extends StatefulWidget {
  const CamerasScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<CamerasScreen> createState() => _CamerasScreenState();
}

class _CamerasScreenState extends State<CamerasScreen> {
  bool _isLoadingProfile = true;
  String? _profileErrorText;
  ProfileSummary? _profileSummary;

  /// Null until the user opens one, so no camera starts unasked.
  CameraSection? _shownCameraSection;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> _loadProfile({bool isSpinnerShown = true}) async {
    if (isSpinnerShown) {
      setState(() {
        _isLoadingProfile = true;
        _profileErrorText = null;
      });
    }
    try {
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      ProfileSummary? foundProfileSummary;
      for (final ProfileSummary profileSummary in profileList.profileSummaries) {
        if (profileSummary.profileName == widget.profileName) {
          foundProfileSummary = profileSummary;
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _profileSummary = foundProfileSummary;
        if (foundProfileSummary == null) {
          _profileErrorText = 'This profile does not exist any more. Go back to the start screen.';
        } else {
          final String? summaryErrorText = foundProfileSummary.profileErrorText;
          if (summaryErrorText != null) {
            debugPrint('[CamerasScreen]: cannot read profile ${widget.profileName}: $summaryErrorText');
            _profileErrorText = 'This profile\'s file cannot be read. It may contain a mistake from editing it by hand.';
          } else {
            _profileErrorText = null;
          }
        }
        _isLoadingProfile = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _profileErrorText = describeBackendErrorForUser(error);
        _isLoadingProfile = false;
      });
    }
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
    if (_isLoadingProfile) {
      return const Center(child: CircularProgressIndicator());
    }
    final String? profileErrorText = _profileErrorText;
    final ProfileSummary? profileSummary = _profileSummary;
    if (profileErrorText != null || profileSummary == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(profileErrorText ?? 'This profile cannot be shown.',
                style: TextStyle(color: Theme.of(context).colorScheme.error), textAlign: TextAlign.center),
            TextButton(onPressed: _loadProfile, child: const Text('Try again')),
          ],
        ),
      );
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
        if (shownCameraSection == CameraSection.lensCalibration || shownCameraSection == CameraSection.cameraPose) {
          // The lens calibration and the pose need no projector light; the projector calibration needs it, the
          // camera image may be tuned under it
          cameraRows.add(ProjectorBlackoutHolder(
            backendClient: widget.backendClient,
            projectorDisplayId: profileSummary.projectorDisplayId,
          ));
        }
        cameraRows.add(_buildCameraSection(shownCameraSection, selectedCamera));
      }
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
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
  Widget _buildCameraSection(CameraSection cameraSection, CameraCalibrationSummary selectedCamera) {
    final Key sectionKey = ValueKey<String>('${selectedCamera.cameraType}-${selectedCamera.serial}-$cameraSection');
    final String cameraName = selectedCamera.cameraType;
    switch (cameraSection) {
      case CameraSection.imageAndSettings:
        return CameraPreviewWithSettingsView(
          key: sectionKey,
          backendClient: widget.backendClient,
          cameraName: cameraName,
          profileName: widget.profileName,
          isSettingsListShown: true,
        );
      case CameraSection.lensCalibration:
        return IntrinsicsCalibrationView(
          key: sectionKey,
          backendClient: widget.backendClient,
          cameraName: cameraName,
          profileName: widget.profileName,
        );
      case CameraSection.cameraPose:
        return ExtrinsicsCalibrationView(
          key: sectionKey,
          backendClient: widget.backendClient,
          profileName: widget.profileName,
          cameraName: cameraName,
          calibrationTopic: ExtrinsicsCalibrationTopic.cameraPose,
        );
      case CameraSection.projectorCalibration:
        return ExtrinsicsCalibrationView(
          key: sectionKey,
          backendClient: widget.backendClient,
          profileName: widget.profileName,
          cameraName: cameraName,
          calibrationTopic: ExtrinsicsCalibrationTopic.projectorMapping,
        );
    }
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
