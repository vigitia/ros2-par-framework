// Written by Claude Code
//
// The setup wizard's home: the hardware setup (profile) used last time, opened right away (the first profile when that
// one no longer exists); the app bar reads "Profile: <name>". A bar below it leads to the overview (the setup
// drawing and the missing calibration steps), the projector's display, the profile's cameras with their calibrations,
// the profile's sensor processing nodes and the profile's apps; the Run button sits in the bottom right
// corner of the Overview. The profile menu (hamburger icon, top right of the app bar) switches profiles, starts
// the new-profile wizard, copies and deletes a profile; the hub remembers the choice for the next start. Without any profile
// the Overview shows only a hint, Projectors and the Run button are disabled. Each area lives in its own
// file and gets only the backend client and the profile name, so the areas can be built independently; switching
// profiles builds them afresh. Without a profile, Cameras, Sensor nodes and Apps list what is installed and what can
// be installed (OfferCatalogView), so a fresh installation gets its parts before the first profile. The Overview's requests to open a camera section or the Projectors area pass through
// the hub.

import 'package:flutter/material.dart';

import '../cameras/camera_section_view.dart';
import '../core/ui/profile_run_view.dart';
import 'profile_selector_view.dart';
import '../core/ui/top_aligned_page_content.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../apps/apps_screen.dart';
import '../cameras/cameras_screen.dart';
import '../new_profile/new_profile_hardware_step.dart';
import '../new_profile/new_profile_wizard_screen.dart';
import 'copy_profile_dialog.dart';
import 'profile_overview_screen.dart';
import '../../data/services/install_api.dart';
import '../install/offer_catalog_view.dart';
import '../projectors/projectors_screen.dart';
import '../sensor_nodes/sensor_nodes_screen.dart';
import '../../config/wizard_strings.dart';

/// Height of the bar with the areas below the app bar's title.
const double areaBarHeightLogicalPx = 64;

class ProfileHubScreen extends StatefulWidget {
  const ProfileHubScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<ProfileHubScreen> createState() => _ProfileHubScreenState();
}

class _ProfileHubScreenState extends State<ProfileHubScreen> {
  static const int overviewAreaIndex = 0;
  static const int projectorsAreaIndex = 1;
  static const int camerasAreaIndex = 2;
  static const int sensorNodesAreaIndex = 3;
  static const int appsAreaIndex = 4;

  bool _isLoadingProfileList = true;

  /// Why the profiles cannot be listed, written for the user; null while they can.
  String? _profileListErrorText;
  List<String> _profileNames = [];

  /// The profile the areas show; null only when there is no profile at all.
  String? _shownProfileName;

  int _selectedAreaIndex = overviewAreaIndex;

  /// The camera section the Cameras area opens with, after the Overview asked for it; null otherwise.
  CameraSectionRequest? _requestedCameraSection;

  /// Raised when the Run menu stored another app, so the shown area reads the profile again.
  int _storedAppChangeCount = 0;

  @override
  void initState() {
    super.initState();
    _loadProfileList();
  }

  Future<void> _loadProfileList() async {
    setState(() {
      _isLoadingProfileList = true;
      _profileListErrorText = null;
    });
    try {
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      if (!mounted) {
        return;
      }
      final List<String> profileNames = [];
      for (final ProfileSummary profileSummary in profileList.profileSummaries) {
        profileNames.add(profileSummary.profileName);
      }
      setState(() {
        _profileNames = profileNames;
        _shownProfileName = _chooseShownProfileName(profileNames, profileList.lastSelectedProfileName);
        if (_shownProfileName == null && _selectedAreaIndex == projectorsAreaIndex) {
          // Disabled without a profile
          _selectedAreaIndex = overviewAreaIndex;
        }
        _isLoadingProfileList = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _profileListErrorText = describeBackendErrorForUser(error);
        _isLoadingProfileList = false;
      });
    }
  }

  /// The shown profile when it still exists, else the last used one, else the first; null without profiles.
  String? _chooseShownProfileName(List<String> profileNames, String? lastSelectedProfileName) {
    if (profileNames.contains(_shownProfileName)) {
      return _shownProfileName;
    }
    if (profileNames.contains(lastSelectedProfileName)) {
      return lastSelectedProfileName;
    }
    return profileNames.firstOrNull;
  }

  /// Shows the profile and remembers it for the next start.
  Future<void> _selectProfile(String profileName) async {
    setState(() {
      _shownProfileName = profileName;
      _requestedCameraSection = null;
    });
    try {
      await widget.backendClient.setLastSelectedProfile(profileName);
    } catch (error) {
      _showMessage(
        WizardStrings.getStoreProfileSelectionErrorText(backendErrorText: describeBackendErrorForUser(error)),
      );
    }
  }

  /// Opens the wizard; a profile it created becomes the shown one, also for the next start.
  Future<void> _openNewProfileWizard() async {
    final String? createdProfileName = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (BuildContext context) => NewProfileWizardScreen(backendClient: widget.backendClient),
      ),
    );
    if (!mounted || createdProfileName == null) {
      return;
    }
    await _selectProfile(createdProfileName);
    _showMessage(WizardStrings.getProfileCreatedText(createdProfileName: createdProfileName));
    await _loadProfileList();
  }

  /// Asks for the copy's name, copies the profile with its calibrations and shows the copy, also for the next start.
  Future<void> _askNameAndCopyProfile(String sourceProfileName) async {
    final String? newProfileDisplayName = await showDialog<String>(
      context: context,
      builder: (BuildContext dialogContext) => CopyProfileDialog(
        sourceProfileName: sourceProfileName,
        existingProfileNames: _profileNames,
      ),
    );
    if (newProfileDisplayName == null || !mounted) {
      return;
    }
    final String newProfileName = createInternalProfileName(newProfileDisplayName);
    try {
      await widget.backendClient.copyProfile(
        sourceProfileName: sourceProfileName,
        newProfileName: newProfileName,
        newProfileDisplayName: newProfileDisplayName,
      );
    } catch (error) {
      _showMessage(WizardStrings.getCopyProfileErrorText(
        sourceProfileName: sourceProfileName,
        backendErrorText: describeBackendErrorForUser(error),
      ));
      return;
    }
    await _selectProfile(newProfileName);
    _showMessage(WizardStrings.getProfileCopiedText(sourceProfileName: sourceProfileName, newProfileName: newProfileName));
    await _loadProfileList();
  }

  /// Asks first, since deleting removes the profile from the app; the backend keeps its files in a folder from
  /// which they can be restored by hand.
  Future<void> _confirmAndDeleteProfile(String profileName) async {
    final bool? isDeletionConfirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text(WizardStrings.getDeleteProfileDialogTitle(profileName: profileName)),
        content: const Text(
          WizardStrings.deleteProfileDialogText,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(WizardStrings.cancelButtonLabel),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(dialogContext).colorScheme.error),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(WizardStrings.deleteButtonLabel),
          ),
        ],
      ),
    );
    if (isDeletionConfirmed != true || !mounted) {
      return;
    }
    String resultText;
    try {
      final String deletedProfileFolderPath = await widget.backendClient.deleteProfile(profileName);
      resultText = WizardStrings.getProfileDeletedText(
        profileName: profileName,
        deletedProfileFolderPath: deletedProfileFolderPath,
      );
    } catch (error) {
      resultText = WizardStrings.getDeleteProfileErrorText(
        profileName: profileName,
        backendErrorText: describeBackendErrorForUser(error),
      );
    }
    _showMessage(resultText);
    // The list no longer holds the deleted profile, so another one is shown
    await _loadProfileList();
  }

  void _showMessage(String messageText) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messageText)));
  }

  void _openCameraSection(CameraSectionRequest cameraSectionRequest) {
    setState(() {
      _requestedCameraSection = cameraSectionRequest;
      _selectedAreaIndex = camerasAreaIndex;
    });
  }

  void _openProjectorsArea() {
    setState(() {
      _selectedAreaIndex = projectorsAreaIndex;
    });
  }

  Widget _buildProfileSelector() {
    return ProfileSelectorView(
      profileNames: _profileNames,
      shownProfileName: _shownProfileName,
      onProfileSelected: _selectProfile,
      onNewProfileClicked: _openNewProfileWizard,
      onCopyProfileClicked: _askNameAndCopyProfile,
      onDeleteProfileClicked: _confirmAndDeleteProfile,
    );
  }

  /// The Overview without a profile: only a hint to the menu that creates the first one.
  Widget _buildNoProfileOverview() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Text(
        WizardStrings.noProfileYetText,
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
    );
  }

  /// Without a profile: the parts the three areas can install, else the Overview's hint.
  Widget _buildNoProfileArea() {
    final Key areaKey = ValueKey<String>('no-profile-$_selectedAreaIndex');
    switch (_selectedAreaIndex) {
      case camerasAreaIndex:
        return OfferCatalogView(key: areaKey, backendClient: widget.backendClient, offerKind: offerKindCamera);
      case sensorNodesAreaIndex:
        return OfferCatalogView(key: areaKey, backendClient: widget.backendClient, offerKind: offerKindSensorNode);
      case appsAreaIndex:
        return OfferCatalogView(key: areaKey, backendClient: widget.backendClient, offerKind: offerKindApp);
      default:
        return _buildNoProfileOverview();
    }
  }

  Widget _buildSelectedArea(String? shownProfileName) {
    if (shownProfileName == null) {
      return _buildNoProfileArea();
    }
    // Keyed by the profile, so switching profiles builds the area afresh with the new profile's state
    final Key areaKey = ValueKey<String>('$shownProfileName-$_selectedAreaIndex-$_storedAppChangeCount');
    switch (_selectedAreaIndex) {
      case projectorsAreaIndex:
        return ProjectorsScreen(
          key: areaKey,
          backendClient: widget.backendClient,
          profileName: shownProfileName,
        );
      case camerasAreaIndex:
        return CamerasScreen(
          key: areaKey,
          backendClient: widget.backendClient,
          profileName: shownProfileName,
          requestedCameraSection: _requestedCameraSection,
        );
      case sensorNodesAreaIndex:
        return SensorNodesScreen(key: areaKey, backendClient: widget.backendClient, profileName: shownProfileName);
      case appsAreaIndex:
        return AppsScreen(key: areaKey, backendClient: widget.backendClient, profileName: shownProfileName);
      default:
        return ProfileOverviewScreen(
          key: areaKey,
          backendClient: widget.backendClient,
          profileName: shownProfileName,
          onCameraSectionRequested: _openCameraSection,
          onProjectorClicked: _openProjectorsArea,
        );
    }
  }

  /// The areas as a horizontal bar below the app bar's title; without a profile Projectors cannot be chosen.
  PreferredSizeWidget _buildAreaBar({required bool isProfileShown}) {
    // Simplification: one bar for every window width; with six short labels it fits desktop windows and phones in
    // landscape. Upgrade for phones: icons only below a width threshold.
    return PreferredSize(
      preferredSize: const Size.fromHeight(areaBarHeightLogicalPx),
      child: NavigationBar(
        height: areaBarHeightLogicalPx,
        selectedIndex: _selectedAreaIndex,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (int areaIndex) {
          setState(() {
            _selectedAreaIndex = areaIndex;
            // Chosen in the bar: the areas open as usual
            _requestedCameraSection = null;
          });
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            label: WizardStrings.overviewNavigationLabel,
          ),
          NavigationDestination(
            icon: const Icon(Icons.video_label),
            label: WizardStrings.projectorsNavigationLabel,
            enabled: isProfileShown,
          ),
          // Without a profile they list what can be installed
          const NavigationDestination(
            icon: Icon(Icons.videocam_outlined),
            label: WizardStrings.camerasNavigationLabel,
          ),
          const NavigationDestination(
            icon: Icon(Icons.sensors),
            label: WizardStrings.sensorNodesNavigationLabel,
          ),
          const NavigationDestination(
            icon: Icon(Icons.apps),
            label: WizardStrings.appsNavigationLabel,
          ),
        ],
      ),
    );
  }

  /// Shown instead of the areas while the profiles cannot be listed, e.g. when the PAR machine does not answer.
  Widget _buildProfileListErrorView(String profileListErrorText) {
    return TopAlignedPageContent(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.cloud_off, size: 48),
          const SizedBox(height: 12),
          Text(profileListErrorText),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _loadProfileList,
            icon: const Icon(Icons.refresh),
            label: const Text(WizardStrings.tryAgainButtonLabel),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final String? shownProfileName = _shownProfileName;
    String titleText = WizardStrings.noProfileTitle;
    if (shownProfileName != null) {
      titleText = WizardStrings.getProfileTitle(shownProfileName: shownProfileName);
    }

    Widget body;
    final String? profileListErrorText = _profileListErrorText;
    if (_isLoadingProfileList) {
      body = const TopAlignedPageContent(child: CircularProgressIndicator());
    } else if (profileListErrorText != null) {
      body = _buildProfileListErrorView(profileListErrorText);
    } else {
      body = _buildSelectedArea(shownProfileName);
    }

    // Only once the profiles are listed: the menu offers them
    final List<Widget> profileMenuActions = [];
    if (!_isLoadingProfileList && profileListErrorText == null) {
      profileMenuActions.add(_buildProfileSelector());
    }

    // Only on the Overview; other areas may have a floating button of their own (e.g. Debug node)
    Widget? runButton;
    final bool isOverviewShown = _selectedAreaIndex == overviewAreaIndex;
    if (shownProfileName != null && profileListErrorText == null && isOverviewShown) {
      runButton = ProfileRunView(
        key: ValueKey<String>(shownProfileName),
        backendClient: widget.backendClient,
        profileName: shownProfileName,
        onProjectorAppStored: () => setState(() => _storedAppChangeCount += 1),
      );
    }
    PreferredSizeWidget? areaBar;
    if (!_isLoadingProfileList && profileListErrorText == null) {
      areaBar = _buildAreaBar(isProfileShown: shownProfileName != null);
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(titleText),
        actions: profileMenuActions,
        // Keeps the menu button off the window's right edge
        actionsPadding: const EdgeInsets.only(right: profileMenuOuterMarginLogicalPx),
        bottom: areaBar,
      ),
      floatingActionButton: runButton,
      body: body,
    );
  }
}
