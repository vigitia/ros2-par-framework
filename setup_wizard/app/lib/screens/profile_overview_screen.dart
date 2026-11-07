// Written by Claude Code
//
// Hub area "Overview" of a profile. Built so far: the profile's cameras; clicking one starts it with the profile's
// settings and shows all its feeds (e.g. colour, depth and infrared of a depth camera) with its settings, which can
// be changed on the running camera. Still to come: every calibration with its state and a button to (re)do it, and
// the profile's apps with a Start button.

import 'package:flutter/material.dart';

import '../camera_preview_with_settings_view.dart';
import '../setup_wizard_backend_client.dart';

class ProfileOverviewScreen extends StatefulWidget {
  const ProfileOverviewScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<ProfileOverviewScreen> createState() => _ProfileOverviewScreenState();
}

class _ProfileOverviewScreenState extends State<ProfileOverviewScreen> {
  bool _isLoadingProfile = true;
  String? _profileErrorText;
  ProfileSummary? _profileSummary;

  /// The camera whose preview runs; null until the user clicks one, so no camera starts unasked.
  CameraCalibrationSummary? _previewedCamera;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _isLoadingProfile = true;
      _profileErrorText = null;
    });
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
          _profileErrorText = 'The profile ${widget.profileName} no longer exists.';
        } else {
          _profileErrorText = foundProfileSummary.profileErrorText;
        }
        _isLoadingProfile = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _profileErrorText = error.toString();
        _isLoadingProfile = false;
      });
    }
  }

  void _togglePreviewedCamera(CameraCalibrationSummary camera) {
    setState(() {
      if (identical(_previewedCamera, camera)) {
        _previewedCamera = null;
      } else {
        _previewedCamera = camera;
      }
    });
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
            Text('Cannot show this profile: $profileErrorText', style: TextStyle(color: Theme.of(context).colorScheme.error)),
            TextButton(onPressed: _loadProfile, child: const Text('Retry')),
          ],
        ),
      );
    }

    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> overviewRows = [
      Text('Cameras', style: textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        'Click a camera to see its images and settings.',
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 8),
      _buildCameraChoice(profileSummary.cameras),
    ];
    final CameraCalibrationSummary? previewedCamera = _previewedCamera;
    final String? previewCameraName = previewedCamera?.previewCameraName;
    if (previewCameraName != null) {
      overviewRows.add(const SizedBox(height: 16));
      overviewRows.add(CameraPreviewWithSettingsView(
        backendClient: widget.backendClient,
        cameraName: previewCameraName,
        profileName: widget.profileName,
        isSettingsListShown: true,
      ));
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: overviewRows),
    );
  }

  Widget _buildCameraChoice(List<CameraCalibrationSummary> cameras) {
    if (cameras.isEmpty) {
      return const Text('This profile has no camera.');
    }
    final List<Widget> cameraChips = [];
    for (final CameraCalibrationSummary camera in cameras) {
      final bool canBePreviewed = camera.previewCameraName != null;
      Widget cameraChip = ChoiceChip(
        avatar: const Icon(Icons.videocam_outlined),
        label: Text(camera.cameraDisplayName),
        selected: identical(_previewedCamera, camera),
        onSelected: canBePreviewed ? (bool isSelected) => _togglePreviewedCamera(camera) : null,
      );
      if (!canBePreviewed) {
        cameraChip = Tooltip(
          message: 'This camera only starts together with the main camera, so it has no preview of its own yet.',
          child: cameraChip,
        );
      }
      cameraChips.add(cameraChip);
    }
    return Wrap(spacing: 8, runSpacing: 8, children: cameraChips);
  }
}
