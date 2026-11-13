// Written by Claude Code
//
// The app's calls for the apps: the installed apps (setup_wizard/backend/apps_api.py), the apps a profile offers
// (par_launch.apps), the one it puts on the projector (par_launch.projector_app) and the cameras their inputs read
// (par_launch.app_inputs), all three in setup_wizard/backend/profiles_api.py. Their settings are read and saved by node_settings_api.dart.

import 'setup_wizard_backend_client.dart';

/// par_launch.projector_app when no app runs on the projector (launch_helpers.PROJECTOR_APP_NONE).
const String projectorAppNone = 'none';

extension AppsApi on SetupWizardBackendClient {
  /// Returns the installed apps that can own the projector.
  Future<List<InstalledApp>> fetchInstalledApps() async {
    final Map<String, dynamic> appListJson = await getJson('/api/apps') as Map<String, dynamic>;
    final List<InstalledApp> installedApps = [];
    for (final dynamic appJson in appListJson['installed_apps'] as List<dynamic>) {
      installedApps.add(InstalledApp.fromJson(appJson as Map<String, dynamic>));
    }
    return installedApps;
  }

  /// Stores appName (an app's appName, or projectorAppNone) as the app the profile starts on the projector.
  Future<void> setProfileProjectorApp({required String profileName, required String appName}) async {
    await sendJson('PUT', '/api/profiles/${Uri.encodeComponent(profileName)}/projector-app', {'app_name': appName});
  }

  /// Stores which of the profile's cameras each input of appName reads; an input left out reads the only camera of a
  /// run.
  Future<void> setProfileAppInputs({
    required String profileName,
    required String appName,
    required Map<String, String> cameraNameByInput,
  }) async {
    await sendJson('PUT', '/api/profiles/${Uri.encodeComponent(profileName)}/app-inputs', {
      'app_name': appName,
      'camera_name_by_input': cameraNameByInput,
    });
  }

  /// Stores which installed apps the profile offers (par_launch.apps), in this order; an app no longer among them
  /// stops being the profile's projector app.
  Future<void> setProfileEnabledApps({required String profileName, required List<String> appNames}) async {
    await sendJson('PUT', '/api/profiles/${Uri.encodeComponent(profileName)}/apps', {'app_names': appNames});
  }
}

class InstalledApp {
  const InstalledApp({
    required this.appName,
    required this.displayName,
    required this.description,
    required this.usesProjector,
    required this.settingsNodeNames,
    required this.inputNames,
    required this.requiredSensorNodeDisplayNames,
    required this.entryErrorText,
  });

  factory InstalledApp.fromJson(Map<String, dynamic> appJson) {
    return InstalledApp(
      appName: appJson['app_name'] as String,
      displayName: appJson['display_name'] as String,
      description: appJson['description'] as String,
      usesProjector: appJson['uses_projector'] as bool,
      settingsNodeNames: (appJson['settings_node_names'] as List<dynamic>).cast<String>(),
      inputNames: (appJson['input_names'] as List<dynamic>).cast<String>(),
      requiredSensorNodeDisplayNames: (appJson['required_sensor_node_display_names'] as List<dynamic>).cast<String>(),
      entryErrorText: appJson['entry_error_text'] as String?,
    );
  }

  /// The value of par_launch.projector_app that starts the app: its package name. For an app that does not use the
  /// projector, the par_launch switch that starts it.
  final String appName;
  final String displayName;
  final String description;

  /// False for an app that runs next to the app on the projector (RViz) instead of being chosen as that app.
  final bool usesProjector;

  /// The app's nodes whose settings the Apps area edits (full node names); empty when the app declares none.
  final List<String> settingsNodeNames;

  /// The inputs of the app's entry, each reading one of the profile's cameras; empty for an app that reads none.
  final List<String> inputNames;

  /// The sensor nodes the framework starts for the app on the cameras it reads, by display name; they show under
  /// Sensor nodes while the profile offers the app.
  final List<String> requiredSensorNodeDisplayNames;

  /// Set when the app's entry is malformed, so the framework would refuse to start it.
  final String? entryErrorText;
}
