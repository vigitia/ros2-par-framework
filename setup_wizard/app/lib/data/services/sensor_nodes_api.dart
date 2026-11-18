// Written by Claude Code
//
// The app's calls to the backend's sensor processing nodes (setup_wizard/backend/sensor_nodes/sensor_nodes_api.py): the
// installed nodes and on which cameras the profile starts each, a debug run of one node (with the nodes it requires)
// on one camera, what those nodes publish. Settings are read and saved by node_settings_api.dart. A run is stopped like a preview
// (stopCameraPreview with the run's preview id).

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

  /// Stores on which cameras the profile starts each node; returns the stored selection, with the nodes the listed
  /// ones need on the same camera, only for nodes that run on a camera.
  Future<Map<String, List<String>>> saveSensorNodeSelection({
    required String profileName,
    required Map<String, List<String>> cameraNamesByPackage,
  }) async {
    final Map<String, dynamic> selectionJson = await sendJson('PUT', '/api/sensor-nodes/selection', {
      'profile_name': profileName,
      'camera_names_by_package': cameraNamesByPackage,
    }) as Map<String, dynamic>;
    final Map<String, List<String>> storedCameraNamesByPackage = {};
    final Map<String, dynamic> cameraNamesJsonByPackage = selectionJson['camera_names_by_package'] as Map<String, dynamic>;
    for (final MapEntry<String, dynamic> packageEntry in cameraNamesJsonByPackage.entries) {
      storedCameraNamesByPackage[packageEntry.key] = (packageEntry.value as List<dynamic>).cast<String>();
    }
    return storedCameraNamesByPackage;
  }

  /// Starts one node with the nodes it requires on one camera of the profile, nothing else, replacing the running
  /// preview; returns the run's preview id.
  Future<int> startSensorNodesRun({
    required String profileName,
    required String packageName,
    required String cameraName,
  }) async {
    final http.Response response = await _postSensorNodesJson('/api/sensor-nodes/run/start', {
      'profile_name': profileName,
      'package_name': packageName,
      'camera_name': cameraName,
    });
    return (jsonDecode(response.body) as Map<String, dynamic>)['preview_id'] as int;
  }

  /// The state of the debug run of packageName on cameraName: whether it runs, and what its nodes publish.
  Future<SensorNodesRunState> fetchSensorNodesRunState({
    required String profileName,
    required String packageName,
    required String cameraName,
  }) async {
    final Uri stateUri = Uri.parse('$backendBaseUrl/api/sensor-nodes/run/state').replace(queryParameters: {
      'profile_name': profileName,
      'package_name': packageName,
      'camera_name': cameraName,
    });
    final http.Response response = await http.get(stateUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return SensorNodesRunState.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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
  const SensorNodeList({
    required this.cameraNames,
    required this.sensorNodes,
    required this.appRequirementErrorTexts,
  });

  factory SensorNodeList.fromJson(Map<String, dynamic> listJson) {
    final List<SensorNodeSummary> sensorNodes = [];
    for (final dynamic sensorNodeJson in listJson['sensor_nodes'] as List<dynamic>) {
      sensorNodes.add(SensorNodeSummary.fromJson(sensorNodeJson as Map<String, dynamic>));
    }
    return SensorNodeList(
      cameraNames: (listJson['camera_names'] as List<dynamic>).cast<String>(),
      sensorNodes: sensorNodes,
      appRequirementErrorTexts: (listJson['app_requirement_error_texts'] as List<dynamic>).cast<String>(),
    );
  }

  /// The profile's cameras (par_launch.cameras) in their order; the first is the main camera.
  final List<String> cameraNames;
  final List<SensorNodeSummary> sensorNodes;

  /// Per app of the profile whose sensor nodes cannot be placed (e.g. an input not bound to a camera): why.
  final List<String> appRequirementErrorTexts;
}

class SensorNodeSummary {
  const SensorNodeSummary({
    required this.packageName,
    required this.displayName,
    required this.description,
    required this.requiredSensorNodes,
    required this.cameraNames,
    required this.needingAppNamesByCamera,
    required this.entryErrorText,
  });

  factory SensorNodeSummary.fromJson(Map<String, dynamic> sensorNodeJson) {
    return SensorNodeSummary(
      packageName: sensorNodeJson['package_name'] as String,
      displayName: sensorNodeJson['display_name'] as String,
      description: sensorNodeJson['description'] as String,
      requiredSensorNodes: (sensorNodeJson['required_sensor_nodes'] as List<dynamic>).cast<String>(),
      cameraNames: (sensorNodeJson['camera_names'] as List<dynamic>).cast<String>(),
      needingAppNamesByCamera: _readNeedingAppNamesByCamera(sensorNodeJson['needing_app_names_by_camera']),
      entryErrorText: sensorNodeJson['entry_error_text'] as String,
    );
  }

  /// Also its par_launch key, e.g. 'page_locator'.
  final String packageName;
  final String displayName;
  final String description;

  /// Nodes whose output it reads; selected along with it, on the same camera.
  final List<String> requiredSensorNodes;

  /// The cameras the profile starts it on (`par_launch.<package>`); empty when it does not run.
  final List<String> cameraNames;

  /// The cameras it runs on because apps of the profile need it there, each with those apps' display names; not part
  /// of the profile's selection, so never sent back when the selection is saved.
  final Map<String, List<String>> needingAppNamesByCamera;

  static Map<String, List<String>> _readNeedingAppNamesByCamera(dynamic needingAppNamesByCameraJson) {
    final Map<String, List<String>> needingAppNamesByCamera = {};
    for (final MapEntry<String, dynamic> cameraEntry in (needingAppNamesByCameraJson as Map<String, dynamic>).entries) {
      needingAppNamesByCamera[cameraEntry.key] = (cameraEntry.value as List<dynamic>).cast<String>();
    }
    return needingAppNamesByCamera;
  }

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
  const RunningSensorNode({
    required this.packageName,
    required this.cameraName,
    required this.isRunning,
    required this.outputTopics,
  });

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
      cameraName: sensorNodeJson['camera_name'] as String,
      isRunning: sensorNodeJson['is_running'] as bool,
      outputTopics: outputTopics,
    );
  }

  final String packageName;

  /// The camera this run of the node reads, in whose namespace it runs.
  final String cameraName;

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

class SensorNodeOutputMessage {
  const SensorNodeOutputMessage({required this.typeName, required this.messageText, required this.receivedAgeS});

  final String typeName;

  /// The latest message as YAML, long arrays cut; empty before the first one.
  final String messageText;

  /// How long ago it arrived; null before the first one.
  final double? receivedAgeS;
}
