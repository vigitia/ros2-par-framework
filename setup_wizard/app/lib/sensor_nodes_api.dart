// Written by Claude Code
//
// The app's calls to the backend's sensor processing nodes (setup_wizard/backend/sensor_nodes_api.py): the
// installed nodes and the profile's selection, a run of the profile's camera with the selected nodes, what each
// node publishes, and its settings, applied by saving them into the profile and starting the run again. A run is
// stopped like a preview (stopCameraPreview with the run's preview id).

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

extension SensorNodesApi on SetupWizardBackendClient {
  Future<SensorNodeList> fetchSensorNodeList(String profileName) async {
    final Uri listUri = Uri.parse('$backendBaseUrl/api/sensor-nodes').replace(queryParameters: {'profile_name': profileName});
    final http.Response response = await http.get(listUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return SensorNodeList.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Stores which nodes the profile starts; returns the stored selection, with the nodes the selected ones need.
  Future<List<String>> saveSensorNodeSelection({
    required String profileName,
    required List<String> selectedPackageNames,
  }) async {
    final Map<String, dynamic> selectionJson = await sendJson('PUT', '/api/sensor-nodes/selection', {
      'profile_name': profileName,
      'selected_package_names': selectedPackageNames,
    }) as Map<String, dynamic>;
    return (selectionJson['selected_package_names'] as List<dynamic>).cast<String>();
  }

  /// Starts the profile's camera with its selected nodes, replacing the running preview; returns the run's preview
  /// id.
  Future<int> startSensorNodesRun(String profileName) async {
    final http.Response response = await _postSensorNodesJson('/api/sensor-nodes/run/start', {
      'profile_name': profileName,
    });
    return (jsonDecode(response.body) as Map<String, dynamic>)['preview_id'] as int;
  }

  Future<SensorNodesRunState> fetchSensorNodesRunState(String profileName) async {
    final Uri stateUri =
        Uri.parse('$backendBaseUrl/api/sensor-nodes/run/state').replace(queryParameters: {'profile_name': profileName});
    final http.Response response = await http.get(stateUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return SensorNodesRunState.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// The running node's settings; null while it does not answer yet.
  Future<List<CameraSetting>?> fetchSensorNodeSettings(String packageName) async {
    final Uri settingsUri =
        Uri.parse('$backendBaseUrl/api/sensor-nodes/settings').replace(queryParameters: {'package_name': packageName});
    final http.Response response = await http.get(settingsUri).timeout(backendRequestTimeout * 2);
    if (response.statusCode == 503) {
      return null;
    }
    _throwOnError(response);
    final List<CameraSetting> settings = [];
    final Map<String, dynamic> settingsJson = jsonDecode(response.body) as Map<String, dynamic>;
    for (final dynamic settingJson in settingsJson['settings'] as List<dynamic>) {
      settings.add(CameraSetting.fromJson(settingJson as Map<String, dynamic>));
    }
    return settings;
  }

  /// Saves the changed settings into the profile and starts the run again; returns the new run's preview id and
  /// what was written.
  Future<SensorNodeSettingsApplyResult> applySensorNodeSettings({
    required String profileName,
    required String packageName,
    required Map<String, Object> settingValueByName,
  }) async {
    final http.Response response = await _postSensorNodesJson('/api/sensor-nodes/settings/apply', {
      'profile_name': profileName,
      'package_name': packageName,
      'setting_value_by_name': settingValueByName,
    });
    final Map<String, dynamic> applyJson = jsonDecode(response.body) as Map<String, dynamic>;
    return SensorNodeSettingsApplyResult(
      previewId: applyJson['preview_id'] as int,
      writtenSettingNames: (applyJson['written_setting_names'] as List<dynamic>).cast<String>(),
      removedSettingNames: (applyJson['removed_setting_names'] as List<dynamic>).cast<String>(),
    );
  }

  /// The latest message on a node's output topic as text.
  Future<SensorNodeOutputMessage> fetchSensorNodeOutputMessage(String topicName) async {
    final Uri messageUri = Uri.parse('$backendBaseUrl/api/sensor-nodes/output-message')
        .replace(queryParameters: {'topic_name': topicName});
    final http.Response response = await http.get(messageUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    final Map<String, dynamic> messageJson = jsonDecode(response.body) as Map<String, dynamic>;
    return SensorNodeOutputMessage(
      typeName: messageJson['type_name'] as String,
      messageText: messageJson['message_text'] as String,
      receivedAgeS: (messageJson['received_age_s'] as num?)?.toDouble(),
    );
  }

  Future<http.Response> _postSensorNodesJson(String apiPath, Map<String, Object?> requestJson) async {
    final http.Request request = http.Request('POST', Uri.parse('$backendBaseUrl$apiPath'));
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode(requestJson);
    // Starting stops the running preview or run first, which may take a while
    final http.StreamedResponse streamedResponse = await request.send().timeout(cameraPreviewStartStopTimeout);
    final http.Response response = await http.Response.fromStream(streamedResponse);
    _throwOnError(response);
    return response;
  }

  void _throwOnError(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw BackendRequestException.fromResponse(response);
    }
  }
}

class SensorNodeList {
  const SensorNodeList({required this.cameraName, required this.sensorNodes});

  factory SensorNodeList.fromJson(Map<String, dynamic> listJson) {
    final List<SensorNodeSummary> sensorNodes = [];
    for (final dynamic sensorNodeJson in listJson['sensor_nodes'] as List<dynamic>) {
      sensorNodes.add(SensorNodeSummary.fromJson(sensorNodeJson as Map<String, dynamic>));
    }
    return SensorNodeList(cameraName: listJson['camera_name'] as String, sensorNodes: sensorNodes);
  }

  /// The camera the nodes run on.
  final String cameraName;
  final List<SensorNodeSummary> sensorNodes;
}

class SensorNodeSummary {
  const SensorNodeSummary({
    required this.packageName,
    required this.displayName,
    required this.description,
    required this.requiredSensorNodes,
    required this.isSelected,
    required this.entryErrorText,
  });

  factory SensorNodeSummary.fromJson(Map<String, dynamic> sensorNodeJson) {
    return SensorNodeSummary(
      packageName: sensorNodeJson['package_name'] as String,
      displayName: sensorNodeJson['display_name'] as String,
      description: sensorNodeJson['description'] as String,
      requiredSensorNodes: (sensorNodeJson['required_sensor_nodes'] as List<dynamic>).cast<String>(),
      isSelected: sensorNodeJson['is_selected'] as bool,
      entryErrorText: sensorNodeJson['entry_error_text'] as String,
    );
  }

  /// Also its par_launch switch, e.g. 'page_locator'.
  final String packageName;
  final String displayName;
  final String description;

  /// Nodes whose output it reads; selected along with it.
  final List<String> requiredSensorNodes;
  final bool isSelected;

  /// Why its entry in the ament index cannot be used; empty otherwise.
  final String entryErrorText;
}

class SensorNodesRunState {
  const SensorNodesRunState({required this.isLaunchRunning, required this.launchLogLines, required this.runningSensorNodes});

  factory SensorNodesRunState.fromJson(Map<String, dynamic> stateJson) {
    final List<RunningSensorNode> runningSensorNodes = [];
    for (final dynamic sensorNodeJson in stateJson['sensor_nodes'] as List<dynamic>) {
      runningSensorNodes.add(RunningSensorNode.fromJson(sensorNodeJson as Map<String, dynamic>));
    }
    return SensorNodesRunState(
      isLaunchRunning: stateJson['is_launch_running'] as bool,
      launchLogLines: (stateJson['launch_log_lines'] as List<dynamic>).cast<String>(),
      runningSensorNodes: runningSensorNodes,
    );
  }

  final bool isLaunchRunning;

  /// The launch's last output lines once it has ended.
  final List<String> launchLogLines;
  final List<RunningSensorNode> runningSensorNodes;
}

class RunningSensorNode {
  const RunningSensorNode({required this.packageName, required this.isRunning, required this.outputTopics});

  factory RunningSensorNode.fromJson(Map<String, dynamic> sensorNodeJson) {
    final List<SensorNodeOutputTopic> outputTopics = [];
    for (final dynamic outputTopicJson in sensorNodeJson['output_topics'] as List<dynamic>) {
      final Map<String, dynamic> outputTopicEntry = outputTopicJson as Map<String, dynamic>;
      outputTopics.add(SensorNodeOutputTopic(
        topicName: outputTopicEntry['topic_name'] as String,
        typeName: outputTopicEntry['type_name'] as String,
        isImage: outputTopicEntry['is_image'] as bool,
      ));
    }
    return RunningSensorNode(
      packageName: sensorNodeJson['package_name'] as String,
      isRunning: sensorNodeJson['is_running'] as bool,
      outputTopics: outputTopics,
    );
  }

  final String packageName;

  /// In the ROS graph; false while it starts, or after it ended.
  final bool isRunning;
  final List<SensorNodeOutputTopic> outputTopics;
}

class SensorNodeOutputTopic {
  const SensorNodeOutputTopic({required this.topicName, required this.typeName, required this.isImage});

  final String topicName;
  final String typeName;

  /// A sensor_msgs/Image, shown as frames.
  final bool isImage;
}

class SensorNodeSettingsApplyResult {
  const SensorNodeSettingsApplyResult({
    required this.previewId,
    required this.writtenSettingNames,
    required this.removedSettingNames,
  });

  final int previewId;
  final List<String> writtenSettingNames;
  final List<String> removedSettingNames;
}

class SensorNodeOutputMessage {
  const SensorNodeOutputMessage({required this.typeName, required this.messageText, required this.receivedAgeS});

  final String typeName;

  /// The latest message as YAML, long arrays cut; empty before the first one.
  final String messageText;

  /// How long ago it arrived; null before the first one.
  final double? receivedAgeS;
}
