// Written by Claude Code
//
// The app's calls to the backend's camera preview (setup_wizard/backend/cameras/camera_preview_api.py): start a camera,
// list its feeds (image topics), fetch a feed's latest frame as JPEG, read and change its settings, stop it.

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'setup_wizard_backend_client.dart';

/// Starting stops a camera that still runs first, which the backend allows up to 3 x 10 s (SIGINT, SIGTERM,
/// SIGKILL), so these requests wait longer than backendRequestTimeout.
const Duration cameraPreviewStartStopTimeout = Duration(seconds: 35);

/// The namespace every camera runs in, `/cameras/<camera name>` (par_launch_cameras.CAMERAS_NAMESPACE).
const String camerasNamespace = '/cameras';

/// The camera a preview starts: a saved profile's camera by its name; it starts with the profile's settings.
@immutable
class PreviewCameraChoice {
  const PreviewCameraChoice({required this.profileName, required this.cameraName});

  final String profileName;

  /// Its name in par_launch.cameras, which its topics are named after.
  final String cameraName;

  /// The camera's image, the feed the focus is measured on.
  String get imageTopicName => '$camerasNamespace/$cameraName/image_raw';

  Map<String, dynamic> toStartJson() {
    return {'profile_name': profileName, 'camera_name': cameraName};
  }

  @override
  bool operator ==(Object other) {
    return other is PreviewCameraChoice && other.profileName == profileName && other.cameraName == cameraName;
  }

  @override
  int get hashCode => Object.hash(profileName, cameraName);
}

extension CameraPreviewApi on SetupWizardBackendClient {
  /// Starts the camera for the preview and returns the preview's id; a preview that runs is stopped first.
  Future<int> startCameraPreview(PreviewCameraChoice previewCamera) async {
    final http.Response response = await _sendCameraPreviewJson(
      'POST',
      '/api/camera-preview/start',
      previewCamera.toStartJson(),
    );
    final Map<String, dynamic> startJson = jsonDecode(response.body) as Map<String, dynamic>;
    return startJson['preview_id'] as int;
  }

  /// Stops the preview, but only while the preview with previewId runs (null stops any): a view closing after
  /// another one started its preview, even of the same camera, must not end that one.
  Future<void> stopCameraPreview({int? previewId}) async {
    await _sendCameraPreviewJson('POST', '/api/camera-preview/stop', {'preview_id': previewId});
  }

  /// Returns the image topics the previewed camera's driver publishes (e.g. colour, depth, infrared), or null
  /// while the driver is not up yet. Throws when no preview runs or the camera stopped.
  Future<List<String>?> fetchCameraPreviewFeedTopicNames() async {
    final Uri feedsUri = Uri.parse('$backendBaseUrl/api/camera-preview/feeds');
    final http.Response response = await http.get(feedsUri).timeout(backendRequestTimeout);
    if (response.statusCode == 503) {
      return null;
    }
    if (response.statusCode != 200) {
      throw BackendRequestException.fromResponse(response);
    }
    final Map<String, dynamic> feedsJson = jsonDecode(response.body) as Map<String, dynamic>;
    final List<String> feedTopicNames = [];
    for (final dynamic feedJson in feedsJson['feeds'] as List<dynamic>) {
      feedTopicNames.add((feedJson as Map<String, dynamic>)['topic_name'] as String);
    }
    return feedTopicNames;
  }

  /// Returns the latest frame of the feed feedTopicName as JPEG bytes, or null while it has not sent one yet.
  /// Throws when no preview runs or the camera stopped, with the backend's explanation.
  Future<Uint8List?> fetchCameraPreviewFrame(String feedTopicName) async {
    final Uri frameUri = Uri.parse('$backendBaseUrl/api/camera-preview/frame')
        .replace(queryParameters: {'topic_name': feedTopicName});
    final http.Response response = await http.get(frameUri).timeout(backendRequestTimeout);
    if (response.statusCode == 204) {
      return null;
    }
    if (response.statusCode != 200) {
      throw BackendRequestException.fromResponse(response);
    }
    return response.bodyBytes;
  }

  /// Returns the previewed camera's settings as its driver reports them, and which changes are not saved in the
  /// profile yet. Throws while no preview runs or the driver does not answer yet (e.g. still starting).
  Future<CameraSettingsReport> fetchCameraPreviewSettings() async {
    final Map<String, dynamic> settingsJson =
        await getJson('/api/camera-preview/settings') as Map<String, dynamic>;
    final List<NodeSetting> cameraSettings = [];
    for (final dynamic settingJson in settingsJson['settings'] as List<dynamic>) {
      cameraSettings.add(NodeSetting.fromJson(settingJson as Map<String, dynamic>));
    }
    return CameraSettingsReport(
      cameraSettings: cameraSettings,
      cameraName: settingsJson['camera_name'] as String,
      profileName: settingsJson['profile_name'] as String?,
      unsavedSettingNames: (settingsJson['unsaved_setting_names'] as List<dynamic>).cast<String>(),
    );
  }

  /// Writes the settings changed on the running camera into the profile it was started with. Returns what was
  /// written; throws with the backend's reason, e.g. when no camera runs.
  Future<CameraSettingsSaveResult> saveCameraPreviewSettingsToProfile() async {
    final http.Response response =
        await _sendCameraPreviewJson('POST', '/api/camera-preview/settings/save-to-profile', {});
    final Map<String, dynamic> saveJson = jsonDecode(response.body) as Map<String, dynamic>;
    return CameraSettingsSaveResult(
      profileName: saveJson['profile_name'] as String,
      writtenSettingNames: (saveJson['written_setting_names'] as List<dynamic>).cast<String>(),
      removedSettingNames: (saveJson['removed_setting_names'] as List<dynamic>).cast<String>(),
    );
  }

  /// Sets one setting on the running driver. Throws with the driver's reason when it refuses the value (e.g. out
  /// of range) or the value does not fit the setting's type.
  Future<void> changeCameraPreviewSetting(String settingName, Object settingValue) async {
    await _sendCameraPreviewJson('PUT', '/api/camera-preview/settings', {
      'setting_name': settingName,
      'setting_value': settingValue,
    });
  }

  /// Sends requestJson with httpMethod ('POST', 'PUT') and returns the backend's answer; throws with its
  /// explanation when it answers with an error.
  Future<http.Response> _sendCameraPreviewJson(
    String httpMethod,
    String apiPath,
    Map<String, Object?> requestJson,
  ) async {
    final http.Request request = http.Request(httpMethod, Uri.parse('$backendBaseUrl$apiPath'));
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode(requestJson);
    final http.StreamedResponse streamedResponse = await request.send().timeout(cameraPreviewStartStopTimeout);
    final http.Response response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw BackendRequestException.fromResponse(response);
    }
    return response;
  }
}

/// The running camera's settings, and where and which changes can still be saved.
class CameraSettingsReport {
  const CameraSettingsReport({
    required this.cameraSettings,
    required this.cameraName,
    required this.profileName,
    required this.unsavedSettingNames,
  });

  final List<NodeSetting> cameraSettings;

  /// The running camera the settings belong to, by its name in the profile.
  final String cameraName;

  /// The profile the camera runs with; null when it stopped while the settings were read.
  final String? profileName;

  /// Settings changed on the running driver and not yet written into the profile.
  final List<String> unsavedSettingNames;
}

/// What saving changed in the profile.
class CameraSettingsSaveResult {
  const CameraSettingsSaveResult({
    required this.profileName,
    required this.writtenSettingNames,
    required this.removedSettingNames,
  });

  final String profileName;

  /// Written, since they differ from par_setup.yaml.
  final List<String> writtenSettingNames;

  /// Removed from the profile, since par_setup.yaml has the same value.
  final List<String> removedSettingNames;
}

/// One setting (ROS parameter) of a camera's driver node, with what its descriptor says about it.
class NodeSetting {
  const NodeSetting({
    required this.settingName,
    required this.settingValue,
    required this.typeName,
    required this.description,
    required this.minimumValue,
    required this.maximumValue,
    required this.stepValue,
    required this.additionalConstraints,
    required this.isReadOnly,
    this.hasDefaultValue = false,
    this.defaultValue,
  });

  factory NodeSetting.fromJson(Map<String, dynamic> settingJson) {
    return NodeSetting(
      settingName: settingJson['setting_name'] as String,
      settingValue: settingJson['setting_value'],
      typeName: settingJson['type_name'] as String,
      description: settingJson['description'] as String,
      minimumValue: (settingJson['minimum_value'] as num?)?.toDouble(),
      maximumValue: (settingJson['maximum_value'] as num?)?.toDouble(),
      stepValue: (settingJson['step_value'] as num?)?.toDouble(),
      additionalConstraints: settingJson['additional_constraints'] as String,
      isReadOnly: settingJson['is_read_only'] as bool,
      hasDefaultValue: settingJson['has_default_value'] as bool? ?? false,
      defaultValue: settingJson['default_value'],
    );
  }

  final String settingName;

  /// bool, int, double, String, a list of those, or null while the parameter is not set.
  final Object? settingValue;
  final String typeName;
  final String description;

  /// The allowed range from the driver's descriptor; null without one.
  final double? minimumValue;
  final double? maximumValue;

  /// 0 means any value in the range.
  final double? stepValue;

  /// The descriptor's free text on allowed values, e.g. a menu's options ('1 - Manual Mode, 3 - ...'); ROS gives
  /// it no fixed format, so it is only shown. Empty without one.
  final String additionalConstraints;
  final bool isReadOnly;

  /// Whether "Reset to default" knows a value: par_setup.yaml's for a camera driver, the node's own value without a
  /// profile for a sensor node or app.
  final bool hasDefaultValue;
  final Object? defaultValue;
}
