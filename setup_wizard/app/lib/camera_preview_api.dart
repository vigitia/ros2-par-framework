// Written by Claude Code
//
// The app's calls to the backend's camera preview (setup_wizard/backend/camera_preview_api.py): start a camera,
// fetch its latest frame as JPEG and its settings, stop it.

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'setup_wizard_backend_client.dart';

/// Starting stops a camera that still runs first, which the backend allows up to 3 x 10 s (SIGINT, SIGTERM,
/// SIGKILL), so these requests wait longer than backendRequestTimeout.
const Duration cameraPreviewStartStopTimeout = Duration(seconds: 35);

extension CameraPreviewApi on SetupWizardBackendClient {
  /// Starts cameraName for the preview; a preview of another camera is stopped first.
  Future<void> startCameraPreview(String cameraName) async {
    await _postCameraPreviewJson('/api/camera-preview/start', {'camera_name': cameraName});
  }

  /// Stops the preview, but only while cameraName is the camera that runs (null stops any).
  Future<void> stopCameraPreview({String? cameraName}) async {
    await _postCameraPreviewJson('/api/camera-preview/stop', {'camera_name': cameraName});
  }

  /// Returns the latest frame as JPEG bytes, or null while the camera has not sent a frame yet. Throws when no
  /// preview runs or the camera stopped, with the backend's explanation.
  Future<Uint8List?> fetchCameraPreviewFrame() async {
    final Uri frameUri = Uri.parse('$backendBaseUrl/api/camera-preview/frame');
    final http.Response response = await http.get(frameUri).timeout(backendRequestTimeout);
    if (response.statusCode == 204) {
      return null;
    }
    if (response.statusCode != 200) {
      throw Exception(_readErrorDetail(response));
    }
    return response.bodyBytes;
  }

  /// Returns the previewed camera's settings as its driver reports them. Throws while no preview runs or the
  /// driver does not answer yet (e.g. still starting).
  Future<List<CameraSetting>> fetchCameraPreviewSettings() async {
    final Map<String, dynamic> settingsJson =
        await getJson('/api/camera-preview/settings') as Map<String, dynamic>;
    final List<CameraSetting> cameraSettings = [];
    for (final dynamic settingJson in settingsJson['settings'] as List<dynamic>) {
      cameraSettings.add(CameraSetting.fromJson(settingJson as Map<String, dynamic>));
    }
    return cameraSettings;
  }

  Future<void> _postCameraPreviewJson(String apiPath, Map<String, Object?> requestJson) async {
    final Uri apiUri = Uri.parse('$backendBaseUrl$apiPath');
    final http.Response response = await http
        .post(apiUri, headers: {'Content-Type': 'application/json'}, body: jsonEncode(requestJson))
        .timeout(cameraPreviewStartStopTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(_readErrorDetail(response));
    }
  }
}

/// The backend's "detail" text of an error answer, or the whole body when it has none.
String _readErrorDetail(http.Response response) {
  try {
    final Map<String, dynamic> errorJson = jsonDecode(response.body) as Map<String, dynamic>;
    final Object? errorDetail = errorJson['detail'];
    if (errorDetail is String) {
      return errorDetail;
    }
  } on FormatException {
    // Not JSON: fall through to the raw body
  } on TypeError {
    // JSON, but not an object with a detail
  }
  return 'Backend answered ${response.statusCode}: ${response.body}';
}

/// One setting (ROS parameter) of a camera's driver node, with what its descriptor says about it.
class CameraSetting {
  const CameraSetting({
    required this.settingName,
    required this.settingValue,
    required this.typeName,
    required this.description,
    required this.minimumValue,
    required this.maximumValue,
    required this.stepValue,
    required this.isReadOnly,
  });

  factory CameraSetting.fromJson(Map<String, dynamic> settingJson) {
    return CameraSetting(
      settingName: settingJson['setting_name'] as String,
      settingValue: settingJson['setting_value'],
      typeName: settingJson['type_name'] as String,
      description: settingJson['description'] as String,
      minimumValue: (settingJson['minimum_value'] as num?)?.toDouble(),
      maximumValue: (settingJson['maximum_value'] as num?)?.toDouble(),
      stepValue: (settingJson['step_value'] as num?)?.toDouble(),
      isReadOnly: settingJson['is_read_only'] as bool,
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
  final bool isReadOnly;
}
