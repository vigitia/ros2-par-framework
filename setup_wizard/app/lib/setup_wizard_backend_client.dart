// Written by Claude Code
//
// Talks to the setup wizard backend (setup_wizard/backend/setup_wizard_backend.py), which runs on the PAR machine
// and does everything that touches it. Screens call these methods instead of building URLs themselves.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Where the backend listens: on this machine only, as long as the app runs on the PAR machine itself.
const String defaultSetupWizardBackendUrl = 'http://127.0.0.1:8800';

/// How long a request may take before the backend counts as unreachable.
const Duration backendRequestTimeout = Duration(seconds: 3);

/// An error answer of the backend. Its text is meant for the log; screens show describeBackendErrorForUser instead.
class BackendRequestException implements Exception {
  const BackendRequestException({required this.statusCode, required this.detailText});

  /// Takes the backend's "detail" text, or the whole body when the answer has none.
  factory BackendRequestException.fromResponse(http.Response response) {
    String detailText = response.body;
    try {
      final Map<String, dynamic> errorJson = jsonDecode(response.body) as Map<String, dynamic>;
      final Object? errorDetail = errorJson['detail'];
      if (errorDetail is String) {
        detailText = errorDetail;
      }
    } on FormatException {
      // Not JSON: the raw body stays
    } on TypeError {
      // JSON, but not an object with a detail
    }
    return BackendRequestException(statusCode: response.statusCode, detailText: detailText);
  }

  final int statusCode;
  final String detailText;

  @override
  String toString() => 'Backend answered $statusCode: $detailText';
}

/// A sentence for the user about a failed backend call, without technical words; the real error goes to the console.
/// isBackendDetailShown: the backend's own sentence for answers that are the user's to fix (e.g. a camera that is in
/// the profile already). Only for calls whose backend texts are written for users.
String describeBackendErrorForUser(Object error, {bool isBackendDetailShown = false}) {
  debugPrint('[SetupWizardBackendClient]: $error');
  if (error is http.ClientException || error is TimeoutException) {
    return 'The PAR machine does not answer. Check that it is switched on and its setup service is running, then try '
        'again.';
  }
  if (error is BackendRequestException) {
    final int statusCode = error.statusCode;
    final bool isUserFixable = statusCode == 409 || statusCode == 422;
    if (isBackendDetailShown && isUserFixable) {
      return error.detailText;
    }
    if (statusCode == 400 || statusCode == 422) {
      return 'That input is not valid. Please check it and try again.';
    }
    if (statusCode == 404) {
      return 'The PAR machine could not find it. Go back, reload and try again.';
    }
    if (statusCode == 409) {
      return 'That is not possible right now. Something else may be using the camera: stop it and try again.';
    }
    if (statusCode == 503 || statusCode == 504) {
      return 'The camera or service is not ready yet. Wait a moment and try again.';
    }
  }
  return 'Something went wrong on the PAR machine. Please try again.';
}

/// What the backend reports about itself.
class SetupWizardBackendStatus {
  const SetupWizardBackendStatus({required this.machineName});

  /// Host name of the machine the backend runs on, i.e. the machine this UI controls.
  final String machineName;
}

/// Calls the backend's API. Each screen adds the calls it needs as an extension on this class in its own file
/// (e.g. `extension IntrinsicsCalibrationApi on SetupWizardBackendClient`), built on getJson and sendJson, so
/// screens do not all edit this file.
class SetupWizardBackendClient {
  SetupWizardBackendClient({this.backendBaseUrl = defaultSetupWizardBackendUrl});

  final String backendBaseUrl;

  /// GETs apiPath (e.g. '/api/profiles') and returns the decoded JSON answer. Throws when the backend is
  /// unreachable or answers with an error.
  Future<dynamic> getJson(String apiPath) async {
    final Uri apiUri = Uri.parse('$backendBaseUrl$apiPath');
    final http.Response response = await http.get(apiUri).timeout(backendRequestTimeout);
    return _decodeJsonResponse(response, apiUri);
  }

  /// Sends requestJson with httpMethod ('POST', 'PUT', 'DELETE') to apiPath and returns the decoded JSON answer,
  /// null when the answer is empty. Throws when the backend is unreachable or answers with an error.
  Future<dynamic> sendJson(String httpMethod, String apiPath, Object? requestJson) async {
    final Uri apiUri = Uri.parse('$backendBaseUrl$apiPath');
    final http.Request request = http.Request(httpMethod, apiUri);
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode(requestJson);
    final http.StreamedResponse streamedResponse = await request.send().timeout(backendRequestTimeout);
    final http.Response response = await http.Response.fromStream(streamedResponse);
    return _decodeJsonResponse(response, apiUri);
  }

  dynamic _decodeJsonResponse(http.Response response, Uri apiUri) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw BackendRequestException.fromResponse(response);
    }
    if (response.body.isEmpty) {
      return null;
    }
    return jsonDecode(response.body);
  }

  /// Asks the backend whether it runs and on which machine. Throws when it is unreachable or answers with an error.
  Future<SetupWizardBackendStatus> fetchBackendStatus() async {
    final Map<String, dynamic> statusJson = await getJson('/api/status') as Map<String, dynamic>;
    return SetupWizardBackendStatus(machineName: statusJson['machine_name'] as String);
  }

  /// Fetches the hardware setups (profiles) with what each runs, and the one selected last time.
  Future<ProfileList> fetchProfileList() async {
    final Map<String, dynamic> profilesJson = await getJson('/api/profiles') as Map<String, dynamic>;
    final List<dynamic> profileSummariesJson = profilesJson['profiles'] as List<dynamic>;
    final List<ProfileSummary> profileSummaries = [];
    for (final dynamic profileSummaryJson in profileSummariesJson) {
      profileSummaries.add(ProfileSummary.fromJson(profileSummaryJson as Map<String, dynamic>));
    }
    return ProfileList(
      profileSummaries: profileSummaries,
      lastSelectedProfileName: profilesJson['last_selected_profile_name'] as String?,
    );
  }

  /// Tells the backend which profile was chosen, so the start screen preselects it next time.
  Future<void> setLastSelectedProfile(String profileName) async {
    await sendJson('PUT', '/api/profiles/last-selected', {'profile_name': profileName});
  }

  /// Creates `config/profiles/<profileName>.yaml` with the camera, the projector's display and the setting changes
  /// made in the new-profile wizard. Throws with the backend's reason, e.g. when the name is taken.
  Future<void> createProfile({
    required String profileName,
    required String profileDisplayName,
    required String cameraName,
    required int? projectorDisplayId,
  }) async {
    await sendJson('POST', '/api/profiles', {
      'profile_name': profileName,
      'profile_display_name': profileDisplayName,
      'camera_name': cameraName,
      'projector_display_id': projectorDisplayId,
    });
  }

  /// Deletes a profile: the backend moves its file and extrinsics into config/profiles/.deleted/, from where it can
  /// be restored by hand. Returns that folder.
  Future<String> deleteProfile(String profileName) async {
    final Map<String, dynamic> deletedJson =
        await sendJson('DELETE', '/api/profiles/${Uri.encodeComponent(profileName)}', null) as Map<String, dynamic>;
    return deletedJson['deleted_profile_folder_path'] as String;
  }
}

/// The hardware setups (profiles) on the PAR machine.
class ProfileList {
  const ProfileList({required this.profileSummaries, required this.lastSelectedProfileName});

  final List<ProfileSummary> profileSummaries;

  /// Null when nothing was selected yet, or that profile no longer exists.
  final String? lastSelectedProfileName;
}

/// What a profile runs: its cameras with their calibration, and the sensor nodes and apps switched on in its
/// par_launch section.
class ProfileSummary {
  const ProfileSummary({
    required this.profileName,
    required this.cameras,
    required this.sensorNodeNames,
    required this.appNames,
    required this.projectorDisplayId,
    required this.profileErrorText,
  });

  factory ProfileSummary.fromJson(Map<String, dynamic> profileSummaryJson) {
    return ProfileSummary(
      profileName: profileSummaryJson['profile_name'] as String,
      cameras: _readCameraCalibrationSummaries(profileSummaryJson['cameras'] as List<dynamic>),
      sensorNodeNames: (profileSummaryJson['sensor_node_names'] as List<dynamic>).cast<String>(),
      appNames: (profileSummaryJson['app_names'] as List<dynamic>).cast<String>(),
      projectorDisplayId: profileSummaryJson['projector_display_id'] as int?,
      profileErrorText: profileSummaryJson['profile_error_text'] as String?,
    );
  }

  final String profileName;
  final List<CameraCalibrationSummary> cameras;
  final List<String> sensorNodeNames;
  final List<String> appNames;

  /// The projector's display (the framework's display_id); null when the profile sets none.
  final int? projectorDisplayId;

  /// Set when the backend could not read the profile's files; the lists are empty then.
  final String? profileErrorText;

  static List<CameraCalibrationSummary> _readCameraCalibrationSummaries(List<dynamic> camerasJson) {
    final List<CameraCalibrationSummary> cameras = [];
    for (final dynamic cameraJson in camerasJson) {
      cameras.add(CameraCalibrationSummary.fromJson(cameraJson as Map<String, dynamic>));
    }
    return cameras;
  }
}

/// How far a camera is calibrated, combining its intrinsics and its pose.
enum CameraCalibrationLevel { complete, partial, none }

/// A camera of a profile with the state of its intrinsics and its pose, as the backend reports them.
class CameraCalibrationSummary {
  const CameraCalibrationSummary({
    required this.cameraDisplayName,
    required this.cameraType,
    required this.serial,
    required this.isSelected,
    required this.previewCameraName,
    required this.intrinsicsState,
    required this.poseState,
  });

  factory CameraCalibrationSummary.fromJson(Map<String, dynamic> cameraJson) {
    return CameraCalibrationSummary(
      cameraDisplayName: cameraJson['camera_display_name'] as String,
      cameraType: cameraJson['camera_type'] as String,
      serial: cameraJson['serial'] as String,
      isSelected: cameraJson['is_selected'] as bool,
      previewCameraName: cameraJson['preview_camera_name'] as String?,
      intrinsicsState: cameraJson['intrinsics_state'] as String,
      poseState: cameraJson['pose_state'] as String,
    );
  }

  final String cameraDisplayName;

  /// A camera name of launch_helpers.CAMERA_DRIVER_REMAPPINGS, e.g. 'brio'.
  final String cameraType;

  /// The unit's serial number; empty for a camera that has none.
  final String serial;

  /// True for the one camera the next run starts.
  final bool isSelected;

  /// The camera type to start for a preview (camera:= of par.launch.py); null when the camera cannot be started on
  /// its own for a preview yet.
  final String? previewCameraName;

  /// 'calibrated', 'factory', 'missing' or 'unsupported' (setup_wizard_backend.py, INTRINSICS_STATE_*).
  final String intrinsicsState;

  /// 'measured', 'placeholder', 'invalid' or 'unsupported' (setup_wizard_backend.py, POSE_STATE_*).
  final String poseState;

  /// Complete when every calibration the camera supports is done, none when none of them is.
  CameraCalibrationLevel getCalibrationLevel() {
    int supportedCalibrationCount = 0;
    int doneCalibrationCount = 0;
    if (intrinsicsState != 'unsupported') {
      supportedCalibrationCount += 1;
      if (intrinsicsState == 'calibrated' || intrinsicsState == 'factory') {
        doneCalibrationCount += 1;
      }
    }
    if (poseState != 'unsupported') {
      supportedCalibrationCount += 1;
      if (poseState == 'measured') {
        doneCalibrationCount += 1;
      }
    }

    if (doneCalibrationCount == supportedCalibrationCount) {
      return CameraCalibrationLevel.complete;
    }
    if (doneCalibrationCount == 0) {
      return CameraCalibrationLevel.none;
    }
    return CameraCalibrationLevel.partial;
  }
}
