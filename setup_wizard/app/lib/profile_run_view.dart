// Written by Claude Code
//
// "Run" for a profile, as the floating action button of the profile's Overview: a menu opens above it to choose the
// app on the projector among the profile's apps (or none); the choice is stored as the profile's app
// (par_launch.projector_app) and the profile starts on the PAR machine as the framework (the selected camera, the
// switched-on sensor nodes and that app). While it runs, the button stops it again. The state is asked for every few
// seconds, so the button also shows a run that was started earlier, and a run that ends on its own is noticed. Only
// one profile runs at a time. What would not fit on the button (a run that ended on its own, a failed start or stop)
// is shown as a snack bar.

import 'dart:async';

import 'package:flutter/material.dart';

import 'apps_api.dart';
import 'run_api.dart';
import 'setup_wizard_backend_client.dart';

/// Pause between two questions for the run state.
const Duration runStatePollInterval = Duration(seconds: 3);

/// Space an area leaves free below its content, so the Run button floating over the bottom right does not cover it.
const double runButtonClearanceLogicalPx = 96;

/// Size of the progress circle that replaces the button's icon while a start or stop is on its way.
const double runProgressIndicatorSizeLogicalPx = 20;

class ProfileRunView extends StatefulWidget {
  const ProfileRunView({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.onProjectorAppStored,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// Called after the menu stored another app as the profile's app, so views showing the choice read it again.
  final VoidCallback onProjectorAppStored;

  @override
  State<ProfileRunView> createState() => _ProfileRunViewState();
}

class _ProfileRunViewState extends State<ProfileRunView> {
  RunState? _runState;

  /// Set while a start or stop is on its way, so the button cannot be pressed twice.
  bool _isChangingRun = false;

  /// Why the run state cannot be read; shown once as a snack bar when it first appears, and in the tooltip.
  String? _pollErrorText;
  Timer? _pollTimer;

  final MenuController _appMenuController = MenuController();

  /// The profile's apps (par_launch.apps) the menu offers, read each time it opens, so a change in the Apps area
  /// shows.
  List<ProjectorApp> _menuApps = [];
  String _storedAppName = projectorAppNone;
  bool _isLoadingAppMenu = false;

  @override
  void initState() {
    super.initState();
    _pollRunState();
    _pollTimer = Timer.periodic(runStatePollInterval, (Timer timer) => _pollRunState());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  void _showMessage(String messageText, {bool isError = false}) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    Color? backgroundColor;
    if (isError) {
      backgroundColor = colorScheme.error;
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messageText), backgroundColor: backgroundColor));
  }

  Future<void> _pollRunState() async {
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
        _showMessage('Cannot read whether the profile runs: $pollErrorText', isError: true);
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
      'The profile stopped by itself. Check that the selected camera is connected, then run it again.',
      isError: true,
    );
  }

  /// Reads the installed apps and the profile's app, then opens the menu to choose one.
  Future<void> _openAppMenu() async {
    setState(() {
      _isLoadingAppMenu = true;
    });
    try {
      final List<ProjectorApp> installedApps = await widget.backendClient.fetchProjectorApps();
      final ProfileSummary profileSummary = await widget.backendClient.fetchProfileSummary(widget.profileName);
      if (!mounted) {
        return;
      }
      final List<ProjectorApp> profileApps = [];
      for (final String enabledAppName in profileSummary.enabledAppNames) {
        for (final ProjectorApp installedApp in installedApps) {
          if (installedApp.appName == enabledAppName) {
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
      _showMessage('Cannot list the apps. ${describeBackendErrorForUser(error)}', isError: true);
    }
  }

  /// Stores appName as the profile's app when it changed, then starts the profile.
  Future<void> _runWithApp(String appName) async {
    await _changeRun(() async {
      if (appName != _storedAppName) {
        await widget.backendClient.setProfileProjectorApp(profileName: widget.profileName, appName: appName);
        _storedAppName = appName;
        widget.onProjectorAppStored();
      }
      return widget.backendClient.startRun(widget.profileName);
    }, 'Could not start the profile.');
  }

  /// One entry per app of the profile, the projector app checked.
  List<Widget> _buildAppMenuEntries() {
    // Simplification: offers every app of the profile that is installed; only a broken entry is disabled. Upgrade:
    // offer only apps whose requirements are installed too (required sensor nodes, calibrations), once requirements
    // are checked.
    final List<Widget> menuEntries = [
      _buildAppMenuEntry(projectorAppNone, 'No app (camera and sensor nodes only)', true),
    ];
    for (final ProjectorApp menuApp in _menuApps) {
      menuEntries.add(_buildAppMenuEntry(menuApp.appName, menuApp.displayName, menuApp.entryErrorText == null));
    }
    if (_menuApps.isEmpty) {
      menuEntries.add(const MenuItemButton(child: Text('Add apps to this profile under Apps')));
    }
    return menuEntries;
  }

  Widget _buildAppMenuEntry(String appName, String entryText, bool canBeStarted) {
    // An empty box instead of the check keeps every name at the same indent
    Widget leadingIcon = const SizedBox(width: 24);
    if (appName == _storedAppName) {
      leadingIcon = const Icon(Icons.check);
    }
    VoidCallback? onPressed;
    if (canBeStarted) {
      onPressed = () => _runWithApp(appName);
    }
    return MenuItemButton(leadingIcon: leadingIcon, onPressed: onPressed, child: Text(entryText));
  }

  Future<void> _stopRun() async {
    await _changeRun(() => widget.backendClient.stopRun(), 'Could not stop the profile.');
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

    String labelText = 'Run';
    String tooltipText = 'Choose the app on the projector and start this profile.';
    Widget icon = const Icon(Icons.play_arrow);
    Color backgroundColor = colorScheme.primaryContainer;
    Color foregroundColor = colorScheme.onPrimaryContainer;
    VoidCallback? onPressed = _openAppMenu;
    if (isOtherProfileRunning) {
      // Only one profile runs at a time, so the button stops the other one first
      labelText = 'Stop ${runState?.profileName}';
      tooltipText = 'The profile ${runState?.profileName} is running. Stop it before running this one.';
    } else if (isRunning) {
      labelText = 'Stop';
      tooltipText = 'This profile is running. Stop it.';
    }
    if (isRunning) {
      icon = const Icon(Icons.stop);
      backgroundColor = colorScheme.error;
      foregroundColor = colorScheme.onError;
      onPressed = _stopRun;
    }
    final String? pollErrorText = _pollErrorText;
    if (pollErrorText != null) {
      tooltipText = 'Cannot read whether the profile runs: $pollErrorText';
    }
    // Pressable only once the state is known, and not twice in a row
    if (_isChangingRun || _isLoadingAppMenu || runState == null) {
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
