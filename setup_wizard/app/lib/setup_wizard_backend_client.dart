// Written by Claude Code
//
// Talks to the setup wizard backend (setup_wizard/backend/setup_wizard_backend.py), which runs on the PAR machine
// and does everything that touches it. Screens call these methods instead of building URLs themselves.

import 'dart:convert';

import 'package:http/http.dart' as http;

/// Where the backend listens: on this machine only, as long as the app runs on the PAR machine itself.
const String defaultSetupWizardBackendUrl = 'http://127.0.0.1:8800';

/// How long a request may take before the backend counts as unreachable.
const Duration backendRequestTimeout = Duration(seconds: 3);

/// What the backend reports about itself.
class SetupWizardBackendStatus {
  const SetupWizardBackendStatus({required this.machineName});

  /// Host name of the machine the backend runs on, i.e. the machine this UI controls.
  final String machineName;
}

class SetupWizardBackendClient {
  SetupWizardBackendClient({this.backendBaseUrl = defaultSetupWizardBackendUrl});

  final String backendBaseUrl;

  /// Asks the backend whether it runs and on which machine. Throws when it is unreachable or answers with an error.
  Future<SetupWizardBackendStatus> fetchBackendStatus() async {
    final Uri statusUri = Uri.parse('$backendBaseUrl/api/status');
    final http.Response response = await http.get(statusUri).timeout(backendRequestTimeout);
    if (response.statusCode != 200) {
      throw Exception('Backend answered ${response.statusCode} on $statusUri');
    }
    final Map<String, dynamic> statusJson = jsonDecode(response.body) as Map<String, dynamic>;
    return SetupWizardBackendStatus(machineName: statusJson['machine_name'] as String);
  }
}
