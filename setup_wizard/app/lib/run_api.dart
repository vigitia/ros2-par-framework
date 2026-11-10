// Written by Claude Code
//
// Start and stop of a profile as the framework, on the PAR machine (backend run_api.py).

import 'setup_wizard_backend_client.dart';

/// What the backend reports about the run: 'idle' (not started, or stopped by the user), 'running', or 'ended' (the
/// launch ended on its own).
class RunState {
  const RunState({required this.phase, required this.profileName});

  factory RunState.fromJson(Map<String, dynamic> runStateJson) {
    return RunState(
      phase: runStateJson['phase'] as String,
      profileName: runStateJson['profile_name'] as String?,
    );
  }

  final String phase;

  /// The profile that runs or ran last; null before the first run.
  final String? profileName;

  bool get isRunning => phase == 'running';
  bool get hasEndedOnItsOwn => phase == 'ended';
}

extension RunApi on SetupWizardBackendClient {
  Future<RunState> startRun(String profileName) async {
    final dynamic runStateJson = await sendJson('POST', '/api/run/start', {'profile_name': profileName});
    return RunState.fromJson(runStateJson as Map<String, dynamic>);
  }

  Future<RunState> fetchRunState() async {
    final Map<String, dynamic> runStateJson = await getJson('/api/run/state') as Map<String, dynamic>;
    return RunState.fromJson(runStateJson);
  }

  Future<RunState> stopRun() async {
    final dynamic runStateJson = await sendJson('POST', '/api/run/stop', null);
    return RunState.fromJson(runStateJson as Map<String, dynamic>);
  }
}
