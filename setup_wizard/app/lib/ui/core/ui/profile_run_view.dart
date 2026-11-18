// Written by Claude Code
//
// "Run" for a profile, as the floating action button of the profile's Overview and Apps area: a menu opens above it to
// choose the app on the projector among the profile's apps (or none), or, in the Apps area, the app of the shown tab
// runs directly; the choice is stored as the profile's app
// (par_launch.projector_app) and the profile starts on the PAR machine as the framework (the profile's main camera,
// the switched-on sensor nodes and that app). While it runs, the button stops it again. The state is asked for every few
// seconds, so the button also shows a run that was started earlier, and a run that ends on its own is noticed. Only
// one profile runs at a time. What would not fit on the button (a run that ended on its own, a failed start or stop)
// is shown as a snack bar. A profile without a camera cannot run, so its button is disabled and says why.

import 'package:flutter/material.dart';

import '../../../data/services/apps_api.dart';
import '../../../data/services/run_api.dart';
import '../../../data/services/setup_wizard_backend_client.dart';
import '../../../config/wizard_strings.dart';
import '../../../config/wizard_icons.dart';

/// Pause between two questions for the run state.
const Duration runStatePollInterval = Duration(seconds: 3);

/// Space an area leaves free below its content, so the Run button floating over the bottom right does not cover it.
const double runButtonClearanceLogicalPx = 96;

/// Size of the progress circle that replaces the button's icon while a start or stop is on its way.
const double runProgressIndicatorSizeLogicalPx = 20;

/// Every floating button needs its own hero tag: Flutter animates buttons with the same tag from one page to the
/// next, and two of them on screen at once (e.g. Run and the Sensor nodes' debug button) are an error.
const String profileRunButtonHeroTag = 'profile_run_button';

class ProfileRunView extends StatefulWidget {
  const ProfileRunView({
    super.key,
    required this.backendClient,
    required this.profileName,
    this.onProjectorAppStored,
    this.appToRunDirectly,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// Called after the menu stored another app as the profile's app, so views showing the choice read it again.
  final VoidCallback? onProjectorAppStored;

  /// Set: the button runs this app on the projector without the menu, e.g. the app of the Apps area's shown tab. Only
  /// for an app that uses the projector and can be started; null opens the menu.
  final InstalledApp? appToRunDirectly;

  @override
  State<ProfileRunView> createState() => _ProfileRunViewState();
}

class _ProfileRunViewState extends State<ProfileRunView> {
  RunState? _runState;

  /// Set while a start or stop is on its way, so the button cannot be pressed twice.
  bool _isChangingRun = false;

  /// Why the run state cannot be read; shown once as a snack bar when it first appears, and in the tooltip.
  String? _pollErrorText;

  final MenuController _appMenuController = MenuController();

  /// The profile's apps (par_launch.apps) the menu offers, read each time it opens, so a change in the Apps area
  /// shows.
  List<InstalledApp> _menuApps = [];
  String _storedAppName = projectorAppNone;
  bool _isLoadingAppMenu = false;

  /// Whether the profile has a camera; null until read. Read once: the button is built anew whenever the Overview
  /// is shown, e.g. after a camera was added in the Cameras area.
  bool? _hasProfileCamera;

  @override
  void initState() {
    super.initState();
    _loadHasProfileCamera();
    _pollRunStateWhileShown();
  }

  Future<void> _loadHasProfileCamera() async {
    bool? hasProfileCamera;
    try {
      final ProfileSummary profileSummary = await widget.backendClient.fetchProfileSummary(widget.profileName);
      hasProfileCamera = profileSummary.cameras.isNotEmpty;
    } catch (error) {
      // Unknown: the button stays usable, and a start without camera is refused by the backend with the reason
      hasProfileCamera = null;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _hasProfileCamera = hasProfileCamera;
    });
  }

  /// Asks for the run state until the view is gone; one request at a time, so a slow answer is never overtaken.
  Future<void> _pollRunStateWhileShown() async {
    while (mounted) {
      await _loadRunState();
      await Future<void>.delayed(runStatePollInterval);
    }
  }

  void _showMessage(String messageText, {bool isError = false}) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    Color? backgroundColor;
    if (isError) {
      backgroundColor = colorScheme.error;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messageText), backgroundColor: backgroundColor));
  }

  Future<void> _loadRunState() async {
    if (_isChangingRun) {
      return;
    }
    try {
      final RunState runState = await widget.backendClient.fetchRunState();
      if (!mounted || _isChangingRun) {
        return;
      }
      _reportRunEndedOnItsOwn(_runState, runState);
      setState(() {
        _runState = runState;
        _pollErrorText = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      final String pollErrorText = describeBackendErrorForUser(error);
      if (_pollErrorText == null) {
        _showMessage(WizardStrings.getRunStateReadErrorText(pollErrorText: pollErrorText), isError: true);
      }
      setState(() {
        _pollErrorText = pollErrorText;
      });
    }
  }

  /// Tells the user once when this profile's run ended without being stopped, e.g. the camera was unplugged.
  void _reportRunEndedOnItsOwn(RunState? previousRunState, RunState runState) {
    final bool hasJustEnded = runState.hasEndedOnItsOwn && previousRunState?.hasEndedOnItsOwn != true;
    // Not on the first answer: a run that ended before this screen opened was reported already
    if (previousRunState == null || !hasJustEnded || runState.profileName != widget.profileName) {
      return;
    }
    _showMessage(
      WizardStrings.profileStoppedByItselfText,
      isError: true,
    );
  }

  /// Reads the installed apps and the profile's app, then opens the menu to choose one.
  Future<void> _openAppMenu() async {
    setState(() {
      _isLoadingAppMenu = true;
    });
    try {
      final List<InstalledApp> installedApps = await widget.backendClient.fetchInstalledApps();
      final ProfileSummary profileSummary = await widget.backendClient.fetchProfileSummary(widget.profileName);
      if (!mounted) {
        return;
      }
      final List<InstalledApp> profileApps = [];
      for (final String enabledAppName in profileSummary.enabledAppNames) {
        for (final InstalledApp installedApp in installedApps) {
          // An app that does not use the projector starts with every run, so it is no choice here
          if (installedApp.appName == enabledAppName && installedApp.usesProjector) {
            profileApps.add(installedApp);
          }
        }
      }
      setState(() {
        _menuApps = profileApps;
        // ProfileSummary.appNames holds par_launch.projector_app unless it is none
        _storedAppName = profileSummary.appNames.firstOrNull ?? projectorAppNone;
        _isLoadingAppMenu = false;
      });
      _appMenuController.open();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isLoadingAppMenu = false;
      });
      _showMessage(
        WizardStrings.getAppListForRunErrorText(backendErrorText: describeBackendErrorForUser(error)),
        isError: true,
      );
    }
  }

  /// Stores appName as the profile's app when it changed, then starts the profile.
  Future<void> _runWithApp(String appName) async {
    await _changeRun(() async {
      if (appName != _storedAppName) {
        await widget.backendClient.setProfileProjectorApp(profileName: widget.profileName, appName: appName);
        _storedAppName = appName;
        widget.onProjectorAppStored?.call();
      }
      return widget.backendClient.startRun(widget.profileName);
    }, WizardStrings.startProfileErrorText);
  }

  /// One entry per app of the profile, the projector app checked.
  List<Widget> _buildAppMenuEntries() {
    // Simplification: offers every app of the profile that is installed; only a broken entry is disabled. Upgrade:
    // offer only apps whose requirements are installed too (required sensor nodes, calibrations), once requirements
    // are checked.
    final List<Widget> menuEntries = [
      _buildAppMenuEntry(projectorAppNone, WizardStrings.runWithoutAppMenuLabel, true),
    ];
    for (final InstalledApp menuApp in _menuApps) {
      menuEntries.add(_buildAppMenuEntry(menuApp.appName, menuApp.displayName, menuApp.entryErrorText == null));
    }
    if (_menuApps.isEmpty) {
      menuEntries.add(const MenuItemButton(child: Text(WizardStrings.addAppsUnderAppsMenuLabel)));
    }
    return menuEntries;
  }

  Widget _buildAppMenuEntry(String appName, String entryText, bool canBeStarted) {
    // An empty box instead of the check keeps every name at the same indent
    Widget leadingIcon = const SizedBox(width: 24);
    if (appName == _storedAppName) {
      leadingIcon = const Icon(WizardIcons.chosenMenuEntryIcon);
    }
    VoidCallback? onPressed;
    if (canBeStarted) {
      onPressed = () => _runWithApp(appName);
    }
    return MenuItemButton(leadingIcon: leadingIcon, onPressed: onPressed, child: Text(entryText));
  }

  Future<void> _stopRun() async {
    await _changeRun(() => widget.backendClient.stopRun(), WizardStrings.stopProfileErrorText);
  }

  Future<void> _changeRun(Future<RunState> Function() changeRun, String failureText) async {
    setState(() {
      _isChangingRun = true;
    });
    RunState? runState;
    String? errorText;
    try {
      runState = await changeRun();
    } catch (error) {
      errorText = '$failureText ${describeBackendErrorForUser(error)}';
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isChangingRun = false;
      if (runState != null) {
        _runState = runState;
      }
    });
    if (errorText != null) {
      _showMessage(errorText, isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final RunState? runState = _runState;
    final bool isRunning = runState?.isRunning ?? false;
    final bool isOtherProfileRunning = isRunning && runState?.profileName != widget.profileName;

    String labelText = WizardStrings.runButtonLabel;
    String tooltipText = WizardStrings.runButtonTooltip;
    Widget icon = const Icon(WizardIcons.runButtonIcon);
    Color backgroundColor = colorScheme.primaryContainer;
    Color foregroundColor = colorScheme.onPrimaryContainer;
    VoidCallback? onPressed = _openAppMenu;
    final InstalledApp? appToRunDirectly = widget.appToRunDirectly;
    if (appToRunDirectly != null) {
      labelText = WizardStrings.getRunAppButtonLabel(appDisplayName: appToRunDirectly.displayName);
      tooltipText = WizardStrings.runAppButtonTooltip;
      onPressed = () => _runWithApp(appToRunDirectly.appName);
    }
    if (isOtherProfileRunning) {
      // Only one profile runs at a time, so the button stops the other one first
      labelText = WizardStrings.getStopOtherProfileButtonLabel(profileName: runState?.profileName);
      tooltipText = WizardStrings.getOtherProfileRunningTooltip(profileName: runState?.profileName);
    } else if (isRunning) {
      labelText = WizardStrings.stopButtonLabel;
      tooltipText = WizardStrings.stopThisProfileTooltip;
    }
    if (isRunning) {
      icon = const Icon(WizardIcons.stopButtonIcon);
      backgroundColor = colorScheme.error;
      foregroundColor = colorScheme.onError;
      onPressed = _stopRun;
    }
    final String? pollErrorText = _pollErrorText;
    if (pollErrorText != null) {
      tooltipText = WizardStrings.getRunStateReadErrorText(pollErrorText: pollErrorText);
    }
    final bool isMissingCamera = _hasProfileCamera == false && !isRunning;
    if (isMissingCamera) {
      tooltipText = WizardStrings.runNeedsCameraTooltip;
    }
    // Pressable only once the state is known, with a camera to start, and not twice in a row
    if (_isChangingRun || _isLoadingAppMenu || runState == null || isMissingCamera) {
      onPressed = null;
      backgroundColor = colorScheme.surfaceContainerHighest;
      foregroundColor = colorScheme.onSurfaceVariant;
    }
    if (_isChangingRun || _isLoadingAppMenu) {
      icon = SizedBox.square(
        dimension: runProgressIndicatorSizeLogicalPx,
        child: CircularProgressIndicator(strokeWidth: 2, color: foregroundColor),
      );
    }

    return MenuAnchor(
      controller: _appMenuController,
      menuChildren: _buildAppMenuEntries(),
      child: FloatingActionButton.extended(
        heroTag: profileRunButtonHeroTag,
        onPressed: onPressed,
        tooltip: tooltipText,
        backgroundColor: backgroundColor,
        foregroundColor: foregroundColor,
        icon: icon,
        label: Text(labelText),
      ),
    );
  }
}
