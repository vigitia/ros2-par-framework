// Written by Claude Code
//
// "Run" for a profile: starts it on the PAR machine as the framework (the selected camera, the switched-on sensor
// nodes and the app on the projector) and stops it again. The state is asked for every few seconds, so the button
// also shows a run that was started earlier, and a run that ends on its own is noticed. Only one profile runs at a
// time.

import 'dart:async';

import 'package:flutter/material.dart';

import 'run_api.dart';
import 'setup_wizard_backend_client.dart';

/// Pause between two questions for the run state.
const Duration runStatePollInterval = Duration(seconds: 3);

class ProfileRunView extends StatefulWidget {
  const ProfileRunView({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<ProfileRunView> createState() => _ProfileRunViewState();
}

class _ProfileRunViewState extends State<ProfileRunView> {
  RunState? _runState;

  /// Set while a start or stop is on its way, so the button cannot be pressed twice.
  bool _isChangingRun = false;
  String? _errorText;
  Timer? _pollTimer;

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

  Future<void> _pollRunState() async {
    if (_isChangingRun) {
      return;
    }
    try {
      final RunState runState = await widget.backendClient.fetchRunState();
      if (!mounted || _isChangingRun) {
        return;
      }
      setState(() {
        _runState = runState;
        _errorText = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorText = describeBackendErrorForUser(error);
      });
    }
  }

  Future<void> _startRun() async {
    await _changeRun(() => widget.backendClient.startRun(widget.profileName), 'Could not start the profile.');
  }

  Future<void> _stopRun() async {
    await _changeRun(() => widget.backendClient.stopRun(), 'Could not stop the profile.');
  }

  Future<void> _changeRun(Future<RunState> Function() changeRun, String failureText) async {
    setState(() {
      _isChangingRun = true;
      _errorText = null;
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
      _errorText = errorText;
      if (runState != null) {
        _runState = runState;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final RunState? runState = _runState;
    final bool isRunning = runState?.isRunning ?? false;
    final bool isOtherProfileRunning = isRunning && runState?.profileName != widget.profileName;

    final Widget runButton;
    if (isRunning) {
      runButton = FilledButton.icon(
        style: FilledButton.styleFrom(backgroundColor: colorScheme.error),
        onPressed: _isChangingRun ? null : _stopRun,
        icon: const Icon(Icons.stop),
        label: const Text('Stop'),
      );
    } else {
      runButton = FilledButton.icon(
        onPressed: _isChangingRun || runState == null ? null : _startRun,
        icon: const Icon(Icons.play_arrow),
        label: const Text('Run'),
      );
    }

    String? statusText;
    if (isOtherProfileRunning) {
      statusText = 'The profile ${runState?.profileName} is running. Stop it before running this one.';
    } else if (isRunning) {
      statusText = 'This profile is running.';
    } else if (runState != null && runState.hasEndedOnItsOwn && runState.profileName == widget.profileName) {
      statusText = 'The profile stopped by itself. Check that the selected camera is connected, then run it again.';
    }

    final List<Widget> rows = [
      Text('Run', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Row(
        children: [
          runButton,
          const SizedBox(width: 16),
          if (_isChangingRun) const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
        ],
      ),
    ];
    if (statusText != null) {
      rows.add(const SizedBox(height: 8));
      rows.add(Text(statusText, style: TextStyle(color: runState?.hasEndedOnItsOwn == true ? colorScheme.error : null)));
    }
    final String? errorText = _errorText;
    if (errorText != null) {
      rows.add(const SizedBox(height: 8));
      rows.add(Text(errorText, style: TextStyle(color: colorScheme.error)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }
}
