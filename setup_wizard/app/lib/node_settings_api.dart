// Written by Claude Code
//
// The app's calls to the backend's node settings (setup_wizard/backend/node_settings_api.py): the settings of a
// sensor node or an app's node, read once by starting the node alone and cached, shown with the profile's values,
// and saved into the profile without a running node.

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

/// What a node belongs to (backend NODE_KIND_*).
enum SettingsNodeKind {
  sensorNode('sensor_node'),
  app('app');

  const SettingsNodeKind(this.backendName);

  final String backendName;
}

extension NodeSettingsApi on SetupWizardBackendClient {
  /// The node's settings with the profile's values; null while the backend reads them for the first time.
  Future<List<NodeSetting>?> fetchNodeSettings({
    required String profileName,
    required SettingsNodeKind nodeKind,
    required String packageName,
    required String fullNodeName,
  }) async {
    final String query = Uri(queryParameters: {
      'profile_name': profileName,
      'node_kind': nodeKind.backendName,
      'package_name': packageName,
      'full_node_name': fullNodeName,
    }).query;
    final Map<String, dynamic> settingsJson;
    try {
      settingsJson = await getJson('/api/node-settings?$query') as Map<String, dynamic>;
    } on BackendRequestException catch (error) {
      if (error.statusCode == 503) {
        return null;
      }
      rethrow;
    }
    final List<NodeSetting> settings = [];
    for (final dynamic settingJson in settingsJson['settings'] as List<dynamic>) {
      settings.add(NodeSetting.fromJson(settingJson as Map<String, dynamic>));
    }
    return settings;
  }

  /// Saves the changed values into the profile; the node reads them at its next start. A null value removes the
  /// profile's value, so the node uses its default again.
  Future<void> saveNodeSettings({
    required String profileName,
    required SettingsNodeKind nodeKind,
    required String packageName,
    required String fullNodeName,
    required Map<String, Object?> settingValueByName,
  }) async {
    await sendJson('POST', '/api/node-settings/save', {
      'profile_name': profileName,
      'node_kind': nodeKind.backendName,
      'package_name': packageName,
      'full_node_name': fullNodeName,
      'setting_value_by_name': settingValueByName,
    });
  }

  /// Forgets what was read for the package, so the next fetch reads it again from the node.
  Future<void> refreshNodeSettings({required SettingsNodeKind nodeKind, required String packageName}) async {
    await sendJson('POST', '/api/node-settings/refresh', {
      'node_kind': nodeKind.backendName,
      'package_name': packageName,
    });
  }
}
