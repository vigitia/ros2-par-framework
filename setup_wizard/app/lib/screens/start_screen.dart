// Written by Claude Code
//
// Start screen of the PAR setup wizard: the hardware setup (profile) opened last time, as one centered card
// listing its cameras (with how far each is calibrated), sensor nodes and apps; clicking the card opens that
// profile. The card stands on a dark table at the bottom, the surface a PAR setup projects onto. Profiles are
// switched rarely, so the other profiles and "New profile" sit in a menu in the bottom left corner, on the table's
// front face. The backend connection is mentioned only when it fails: then a plain message with a Retry button
// replaces the card.

import 'package:flutter/material.dart';

import '../projector_background.dart';
import '../setup_wizard_backend_client.dart';
import '../tabletop_shape.dart';
import 'new_profile_wizard_screen.dart';
import 'profile_hub_screen.dart';

const double profileCardWidth = 320;

/// Where the card stands on the tabletop: 0 at its front edge, 1 at its back edge.
const double cardStandingDepthFraction = 0.5;

class SetupWizardStartScreen extends StatefulWidget {
  const SetupWizardStartScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<SetupWizardStartScreen> createState() => _SetupWizardStartScreenState();
}

class _SetupWizardStartScreenState extends State<SetupWizardStartScreen> {
  bool _isLoadingFromBackend = true;
  SetupWizardBackendStatus? _backendStatus;
  List<ProfileSummary> _profileSummaries = [];

  /// The profile whose card is shown: the one opened last time, or the one picked in the profile menu since. Null
  /// only when there is no profile at all.
  String? _shownProfileName;

  @override
  void initState() {
    super.initState();
    _loadFromBackend();
  }

  Future<void> _loadFromBackend() async {
    setState(() {
      _isLoadingFromBackend = true;
    });
    try {
      final SetupWizardBackendStatus backendStatus = await widget.backendClient.fetchBackendStatus();
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      setState(() {
        _backendStatus = backendStatus;
        _profileSummaries = profileList.profileSummaries;
        _shownProfileName = _chooseShownProfileName(profileList);
        _isLoadingFromBackend = false;
      });
    } catch (error) {
      // The screen shows a plain message; the technical reason is only for whoever looks at the console.
      debugPrint('[SetupWizardStartScreen]: backend not reachable at ${widget.backendClient.backendBaseUrl}: $error');
      setState(() {
        _backendStatus = null;
        _isLoadingFromBackend = false;
      });
    }
  }

  /// The last opened profile when it still exists, otherwise the first one; null without profiles.
  String? _chooseShownProfileName(ProfileList profileList) {
    final String? lastSelectedProfileName = profileList.lastSelectedProfileName;
    for (final ProfileSummary profileSummary in profileList.profileSummaries) {
      if (profileSummary.profileName == lastSelectedProfileName) {
        return lastSelectedProfileName;
      }
    }
    if (profileList.profileSummaries.isEmpty) {
      return null;
    }
    return profileList.profileSummaries.first.profileName;
  }

  ProfileSummary? _getShownProfileSummary() {
    for (final ProfileSummary profileSummary in _profileSummaries) {
      if (profileSummary.profileName == _shownProfileName) {
        return profileSummary;
      }
    }
    return null;
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
    try {
      await widget.backendClient.setLastSelectedProfile(createdProfileName);
    } catch (error) {
      // The profile exists anyway; it is only not preselected next time.
    }
    setState(() {
      _shownProfileName = createdProfileName;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Created profile $createdProfileName.')));
    }
    await _loadFromBackend();
  }

  /// Remembers the profile as the last used one, then opens its hub.
  /// Asks first, since deleting removes the profile from the app; the backend keeps its files in a folder from
  /// which they can be restored by hand.
  Future<void> _confirmAndDeleteProfile(String profileName) async {
    final bool? isDeletionConfirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: Text('Delete the profile $profileName?'),
        content: const Text(
          'The profile and its camera poses and projector calibration are moved to config/profiles/.deleted/ and '
          'disappear from the app. They can be restored by hand from there. The cameras\' lens calibrations stay.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(dialogContext).colorScheme.error),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Delete'),
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
      resultText = 'Deleted $profileName. Its files are in $deletedProfileFolderPath';
    } catch (error) {
      resultText = 'Could not delete $profileName. ${describeBackendErrorForUser(error)}';
    }
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(resultText)));
    await _loadFromBackend();
  }

  Future<void> _openProfile(String profileName) async {
    try {
      await widget.backendClient.setLastSelectedProfile(profileName);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not remember the selection. ${describeBackendErrorForUser(error)}')),
        );
      }
      return;
    }
    setState(() {
      _shownProfileName = profileName;
    });
    _openScreen(ProfileHubScreen(backendClient: widget.backendClient, profileName: profileName));
  }

  void _openScreen(Widget screen) {
    if (!mounted) {
      return;
    }
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (BuildContext context) => screen));
  }

  @override
  Widget build(BuildContext context) {
    // No title bar: the projector hangs at the window's top edge, and the window's own title names the app.
    return Scaffold(
      // The body, and with it the table, reaches behind the connection bar down to the window's bottom edge.
      extendBody: true,
      // A Builder, so the body reads the bar heights the Scaffold reports below itself (MediaQuery padding); the
      // State's own context sits above the Scaffold and would see none.
      body: ProjectorBackground(
        child: Builder(builder: (BuildContext bodyContext) => _buildProfileChoiceOnTable(bodyContext)),
      ),
      bottomNavigationBar: _buildProfileMenuBar(),
    );
  }

  /// The profile choice above the table's front edge, so the card stands on the tabletop.
  Widget _buildProfileChoiceOnTable(BuildContext context) {
    // Room the system needs at the top (e.g. a phone's status bar); none in a desktop window.
    final double systemTopInsetLogicalPx = MediaQuery.paddingOf(context).top;
    final double cardBottomAboveWindowBottomLogicalPx = computeTableHeightBelowTabletopLogicalPx(context) +
        tabletopSurfaceDepthLogicalPx * cardStandingDepthFraction;

    return Padding(
      padding: EdgeInsets.only(top: systemTopInsetLogicalPx, bottom: cardBottomAboveWindowBottomLogicalPx),
      child: _buildProfileChoice(context),
    );
  }

  Widget _buildProfileChoice(BuildContext context) {
    if (_isLoadingFromBackend) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_backendStatus == null) {
      return _buildConnectionFailedMessage(context);
    }

    // Without any profile, the only useful step is creating one.
    final ProfileSummary? shownProfileSummary = _getShownProfileSummary();
    final Widget shownCard;
    if (shownProfileSummary == null) {
      shownCard = _buildNewProfileCard(context);
    } else {
      shownCard = _buildProfileCard(context, shownProfileSummary);
    }

    // The card's bottom edge rests on the table; the scroll view keeps it reachable in a window lower than the card.
    return Align(
      alignment: Alignment.bottomCenter,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
        child: shownCard,
      ),
    );
  }

  /// Shown instead of the card while the PAR machine does not answer.
  Widget _buildConnectionFailedMessage(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48),
            const SizedBox(height: 12),
            Text('Cannot reach the PAR machine', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text(
              'Make sure the PAR machine is switched on and its setup service is running, then try again.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _loadFromBackend,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ],
        ),
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
      debugPrint('[SetupWizardStartScreen]: cannot read profile ${profileSummary.profileName}: $profileErrorText');
      cardRows.add(Text(
        'This profile\'s file cannot be read. It may contain a mistake from editing it by hand.',
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ));
    } else {
      cardRows.add(_buildCameraRow(context, profileSummary.cameras));
      cardRows.add(_buildNameListRow(context, 'Sensor nodes', profileSummary.sensorNodeNames));
      cardRows.add(_buildNameListRow(context, 'Apps', profileSummary.appNames));
    }

    return _buildClickableCard(
      context: context,
      onCardTapped: () => _openProfile(profileSummary.profileName),
      cardContent: Column(crossAxisAlignment: CrossAxisAlignment.start, children: cardRows),
    );
  }

  Widget _buildNewProfileCard(BuildContext context) {
    return _buildClickableCard(
      context: context,
      onCardTapped: _openNewProfileWizard,
      cardContent: Row(
        children: [
          const Icon(Icons.add),
          const SizedBox(width: 8),
          Text('New profile', style: Theme.of(context).textTheme.titleMedium),
        ],
      ),
    );
  }

  /// A framed card that runs onCardTapped when clicked.
  Widget _buildClickableCard({
    required BuildContext context,
    required VoidCallback onCardTapped,
    required Widget cardContent,
  }) {
    final BorderSide cardBorder = BorderSide(color: Theme.of(context).colorScheme.primary, width: 2);

    return SizedBox(
      width: profileCardWidth,
      child: Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: cardBorder),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onCardTapped,
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

  /// A button naming the shown profile; its menu switches the shown card to another profile or starts a new one.
  /// Picking a profile only shows its card, clicking the card opens it.
  Widget _buildProfileMenu() {
    final List<Widget> menuEntries = [];
    for (final ProfileSummary profileSummary in _profileSummaries) {
      final String profileName = profileSummary.profileName;
      // An empty box instead of the check keeps every name at the same indent.
      final Widget leadingIcon;
      if (profileName == _shownProfileName) {
        leadingIcon = const Icon(Icons.check);
      } else {
        leadingIcon = const SizedBox(width: 24);
      }
      menuEntries.add(MenuItemButton(
        leadingIcon: leadingIcon,
        onPressed: () => setState(() => _shownProfileName = profileName),
        child: Text(profileName),
      ));
    }
    if (menuEntries.isNotEmpty) {
      menuEntries.add(const Divider(height: 1));
    }
    menuEntries.add(MenuItemButton(
      leadingIcon: const Icon(Icons.add),
      onPressed: _openNewProfileWizard,
      child: const Text('New profile'),
    ));
    final String? shownProfileName = _shownProfileName;
    if (shownProfileName != null) {
      final Color deleteColor = Theme.of(context).colorScheme.error;
      menuEntries.add(MenuItemButton(
        leadingIcon: Icon(Icons.delete_outline, color: deleteColor),
        onPressed: () => _confirmAndDeleteProfile(shownProfileName),
        child: Text('Delete $shownProfileName …', style: TextStyle(color: deleteColor)),
      ));
    }

    final String buttonText = _shownProfileName ?? 'No profile yet';
    return MenuAnchor(
      menuChildren: menuEntries,
      builder: (BuildContext context, MenuController menuController, Widget? child) {
        return OutlinedButton.icon(
          onPressed: () {
            if (menuController.isOpen) {
              menuController.close();
            } else {
              menuController.open();
            }
          },
          icon: const Icon(Icons.swap_horiz),
          label: Text(buttonText),
        );
      },
    );
  }

  /// The profile menu once the backend answered; nothing before, since a failed connection is explained in the
  /// middle of the screen.
  Widget _buildProfileMenuBar() {
    if (_backendStatus == null) {
      return const SizedBox.shrink();
    }
    // Between the table's legs, which stand behind the bar
    const double barSidePaddingLogicalPx = tableFrontLegsOuterExtentLogicalPx + 12;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: barSidePaddingLogicalPx, vertical: 8),
        child: Row(children: [_buildProfileMenu()]),
      ),
    );
  }
}
