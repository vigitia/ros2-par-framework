// Written by Claude Code
//
// Start screen of the PAR setup wizard: one question, which hardware setup (profile) to use. Every profile is a
// card listing its cameras (with how far each is calibrated), sensor nodes and apps; the one chosen last time is
// preselected, and a last card starts a new profile. The backend connection is shown at the bottom.

import 'package:flutter/material.dart';

import '../projector_background.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';
import 'profile_hub_screen.dart';

/// Selection value of the "New profile" card. Empty, because no profile can have an empty name.
const String newProfileSelectionValue = '';

const double profileCardWidth = 320;

class SetupWizardStartScreen extends StatefulWidget {
  const SetupWizardStartScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<SetupWizardStartScreen> createState() => _SetupWizardStartScreenState();
}

class _SetupWizardStartScreenState extends State<SetupWizardStartScreen> {
  bool _isLoadingFromBackend = true;
  String? _backendErrorText;
  SetupWizardBackendStatus? _backendStatus;
  List<ProfileSummary> _profileSummaries = [];

  /// A profile name, or newProfileSelectionValue.
  String _selectedProfileValue = newProfileSelectionValue;

  @override
  void initState() {
    super.initState();
    _loadFromBackend();
  }

  Future<void> _loadFromBackend() async {
    setState(() {
      _isLoadingFromBackend = true;
      _backendErrorText = null;
    });
    try {
      final SetupWizardBackendStatus backendStatus = await widget.backendClient.fetchBackendStatus();
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      setState(() {
        _backendStatus = backendStatus;
        _profileSummaries = profileList.profileSummaries;
        _selectedProfileValue = _getPreselectedProfileValue(profileList);
        _isLoadingFromBackend = false;
      });
    } catch (error) {
      setState(() {
        _backendStatus = null;
        _backendErrorText = error.toString();
        _isLoadingFromBackend = false;
      });
    }
  }

  /// The profile chosen last time, else the first profile, else "New profile" when there is none yet.
  String _getPreselectedProfileValue(ProfileList profileList) {
    final String? lastSelectedProfileName = profileList.lastSelectedProfileName;
    if (lastSelectedProfileName != null) {
      return lastSelectedProfileName;
    }
    if (profileList.profileSummaries.isNotEmpty) {
      return profileList.profileSummaries.first.profileName;
    }
    return newProfileSelectionValue;
  }

  Future<void> _continueWithSelectedProfile() async {
    if (_selectedProfileValue == newProfileSelectionValue) {
      _openScreen(NewProfileWizardScreen(backendClient: widget.backendClient));
      return;
    }

    final String selectedProfileName = _selectedProfileValue;
    try {
      await widget.backendClient.setLastSelectedProfile(selectedProfileName);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save the selection: $error')),
        );
      }
      return;
    }
    _openScreen(ProfileHubScreen(backendClient: widget.backendClient, profileName: selectedProfileName));
  }

  void _openScreen(Widget screen) {
    if (!mounted) {
      return;
    }
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (BuildContext context) => screen));
  }

  void _selectProfileValue(String profileValue) {
    setState(() {
      _selectedProfileValue = profileValue;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ROS 2 PAR Framework')),
      // The body, and with it the projector's light, reaches behind the connection bar to the window's bottom edge.
      extendBody: true,
      body: ProjectorBackground(child: _buildProfileChoice(context)),
      // At the bottom, so it is always clear which machine the UI controls (matters once phones connect too).
      bottomNavigationBar: _buildBackendConnectionBar(),
    );
  }

  Widget _buildProfileChoice(BuildContext context) {
    if (_isLoadingFromBackend) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_backendStatus == null) {
      return const Center(child: Text('No connection to the backend, see below.'));
    }

    final List<Widget> cards = [];
    for (final ProfileSummary profileSummary in _profileSummaries) {
      cards.add(_buildProfileCard(context, profileSummary));
    }
    cards.add(_buildNewProfileCard(context));

    // With extendBody, the Scaffold reports the connection bar's height as bottom padding: keep the last cards
    // and the Continue button above the bar.
    final double connectionBarHeight = MediaQuery.paddingOf(context).bottom;
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + connectionBarHeight),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Which hardware setup?', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 16),
          Wrap(spacing: 16, runSpacing: 16, children: cards),
          const SizedBox(height: 24),
          FilledButton(onPressed: _continueWithSelectedProfile, child: const Text('Continue')),
        ],
      ),
    );
  }

  Widget _buildProfileCard(BuildContext context, ProfileSummary profileSummary) {
    final List<Widget> cardRows = [
      Text(profileSummary.profileName, style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 12),
    ];
    final String? profileErrorText = profileSummary.profileErrorText;
    if (profileErrorText != null) {
      cardRows.add(Text(
        'Cannot read this profile: $profileErrorText',
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ));
    } else {
      cardRows.add(_buildCameraRow(context, profileSummary.cameras));
      cardRows.add(_buildNameListRow(context, 'Sensor nodes', profileSummary.sensorNodeNames));
      cardRows.add(_buildNameListRow(context, 'Apps', profileSummary.appNames));
    }

    return _buildSelectableCard(
      context: context,
      profileValue: profileSummary.profileName,
      cardContent: Column(crossAxisAlignment: CrossAxisAlignment.start, children: cardRows),
    );
  }

  Widget _buildNewProfileCard(BuildContext context) {
    return _buildSelectableCard(
      context: context,
      profileValue: newProfileSelectionValue,
      cardContent: Row(
        children: [
          const Icon(Icons.add),
          const SizedBox(width: 8),
          Text('New profile', style: Theme.of(context).textTheme.titleMedium),
        ],
      ),
    );
  }

  /// A card that selects profileValue when clicked, with a highlighted border while selected.
  Widget _buildSelectableCard({
    required BuildContext context,
    required String profileValue,
    required Widget cardContent,
  }) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final bool isSelected = profileValue == _selectedProfileValue;
    final BorderSide cardBorder;
    if (isSelected) {
      cardBorder = BorderSide(color: colorScheme.primary, width: 2);
    } else {
      cardBorder = BorderSide(color: colorScheme.outlineVariant);
    }

    return SizedBox(
      width: profileCardWidth,
      child: Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: cardBorder),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _selectProfileValue(profileValue),
          child: Padding(padding: const EdgeInsets.all(16), child: cardContent),
        ),
      ),
    );
  }

  /// The "Cameras" row of a profile card: a chip per camera with an icon for how far it is calibrated.
  Widget _buildCameraRow(BuildContext context, List<CameraCalibrationSummary> cameras) {
    final List<Widget> cameraChips = [];
    for (final CameraCalibrationSummary camera in cameras) {
      cameraChips.add(Tooltip(
        message: _getCalibrationTooltipText(camera),
        child: Chip(
          avatar: _buildCalibrationIcon(context, camera.getCalibrationLevel()),
          label: Text(camera.cameraDisplayName),
          visualDensity: VisualDensity.compact,
        ),
      ));
    }
    return _buildChipRow(context, 'Cameras', cameraChips);
  }

  /// Differs in shape as well as colour, so the state is readable without telling the colours apart.
  Widget _buildCalibrationIcon(BuildContext context, CameraCalibrationLevel calibrationLevel) {
    switch (calibrationLevel) {
      case CameraCalibrationLevel.complete:
        return Icon(Icons.check_circle, color: Colors.green.shade400);
      case CameraCalibrationLevel.partial:
        return Icon(Icons.warning_amber_rounded, color: Colors.amber.shade400);
      case CameraCalibrationLevel.none:
        return Icon(Icons.cancel, color: Theme.of(context).colorScheme.error);
    }
  }

  String _getCalibrationTooltipText(CameraCalibrationSummary camera) {
    final String intrinsicsText;
    switch (camera.intrinsicsState) {
      case 'calibrated':
        intrinsicsText = 'calibrated';
      case 'factory':
        intrinsicsText = 'from the camera (factory calibration)';
      case 'missing':
        intrinsicsText = 'missing';
      case 'unsupported':
        intrinsicsText = 'not possible for this camera yet';
      default:
        intrinsicsText = camera.intrinsicsState;
    }
    final String poseText;
    switch (camera.poseState) {
      case 'measured':
        poseText = 'measured';
      case 'placeholder':
        poseText = 'missing (placeholder pose in use)';
      case 'invalid':
        poseText = 'file is broken, a launch would stop on it';
      case 'unsupported':
        poseText = 'not used for this camera yet';
      default:
        poseText = camera.poseState;
    }
    return 'Intrinsics: $intrinsicsText\nCamera pose: $poseText';
  }

  /// One labelled row of a profile card with a plain chip per name, or "none".
  Widget _buildNameListRow(BuildContext context, String rowLabel, List<String> names) {
    final List<Widget> nameChips = [];
    for (final String name in names) {
      nameChips.add(Chip(label: Text(name), visualDensity: VisualDensity.compact));
    }
    return _buildChipRow(context, rowLabel, nameChips);
  }

  /// A label above its chips, or above "none" when there are no chips.
  Widget _buildChipRow(BuildContext context, String rowLabel, List<Widget> chips) {
    final Widget rowContent;
    if (chips.isEmpty) {
      rowContent = Text('none', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant));
    } else {
      rowContent = Wrap(spacing: 6, runSpacing: 6, children: chips);
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(rowLabel, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 4),
          rowContent,
        ],
      ),
    );
  }

  Widget _buildBackendConnectionBar() {
    final String backendBaseUrl = widget.backendClient.backendBaseUrl;
    final Widget connectionText;
    Widget? retryButton;
    if (_isLoadingFromBackend) {
      connectionText = Text('Connecting to $backendBaseUrl …');
    } else if (_backendStatus == null) {
      connectionText = Text(
        'Backend not reachable at $backendBaseUrl ($_backendErrorText). Start it from the repository root, '
        'with the workspace sourced: .venv/bin/python setup_wizard/backend/setup_wizard_backend.py',
      );
      retryButton = TextButton(onPressed: _loadFromBackend, child: const Text('Retry'));
    } else {
      connectionText = Text('Connected to ${_backendStatus!.machineName} ($backendBaseUrl)');
    }

    final List<Widget> barChildren = [Expanded(child: connectionText)];
    if (retryButton != null) {
      barChildren.add(retryButton);
    }
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(children: barChildren),
      ),
    );
  }
}
