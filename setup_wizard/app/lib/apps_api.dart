// Written by Claude Code
//
// The app's calls for the app on the projector: the installed apps (setup_wizard/backend/apps_api.py) and the
// profile's choice among them, par_launch.projector_app (setup_wizard/backend/profiles_api.py).

import 'setup_wizard_backend_client.dart';

/// par_launch.projector_app when no app runs on the projector (launch_helpers.PROJECTOR_APP_NONE).
const String projectorAppNone = 'none';

extension AppsApi on SetupWizardBackendClient {
  /// Returns the installed apps that can own the projector.
  Future<List<ProjectorApp>> fetchProjectorApps() async {
    final Map<String, dynamic> appListJson = await getJson('/api/apps') as Map<String, dynamic>;
    final List<ProjectorApp> projectorApps = [];
    for (final dynamic appJson in appListJson['projector_apps'] as List<dynamic>) {
      projectorApps.add(ProjectorApp.fromJson(appJson as Map<String, dynamic>));
    }
    return projectorApps;
  }

  /// Stores appName (an app's appName, or projectorAppNone) as the app the profile starts on the projector.
  Future<void> setProfileProjectorApp({required String profileName, required String appName}) async {
    await sendJson('PUT', '/api/profiles/${Uri.encodeComponent(profileName)}/projector-app', {'app_name': appName});
  }
}

class ProjectorApp {
  const ProjectorApp({
    required this.appName,
    required this.displayName,
    required this.description,
    required this.entryErrorText,
  });

  factory ProjectorApp.fromJson(Map<String, dynamic> appJson) {
    return ProjectorApp(
      appName: appJson['app_name'] as String,
      displayName: appJson['display_name'] as String,
      description: appJson['description'] as String,
      entryErrorText: appJson['entry_error_text'] as String?,
    );
  }

  /// The value of par_launch.projector_app that starts the app: its package name.
  final String appName;
  final String displayName;
  final String description;

  /// Set when the app's entry is malformed, so the framework would refuse to start it.
  final String? entryErrorText;
}
