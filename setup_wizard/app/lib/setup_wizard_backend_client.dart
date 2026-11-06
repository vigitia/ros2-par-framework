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
      throw Exception('Backend answered ${response.statusCode} on $apiUri: ${response.body}');
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
    required this.profileErrorText,
  });

  factory ProfileSummary.fromJson(Map<String, dynamic> profileSummaryJson) {
    return ProfileSummary(
      profileName: profileSummaryJson['profile_name'] as String,
      cameras: _readCameraCalibrationSummaries(profileSummaryJson['cameras'] as List<dynamic>),
      sensorNodeNames: (profileSummaryJson['sensor_node_names'] as List<dynamic>).cast<String>(),
      appNames: (profileSummaryJson['app_names'] as List<dynamic>).cast<String>(),
      profileErrorText: profileSummaryJson['profile_error_text'] as String?,
    );
  }

  final String profileName;
  final List<CameraCalibrationSummary> cameras;
  final List<String> sensorNodeNames;
  final List<String> appNames;

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
    required this.intrinsicsState,
    required this.poseState,
  });

  factory CameraCalibrationSummary.fromJson(Map<String, dynamic> cameraJson) {
    return CameraCalibrationSummary(
      cameraDisplayName: cameraJson['camera_display_name'] as String,
      intrinsicsState: cameraJson['intrinsics_state'] as String,
      poseState: cameraJson['pose_state'] as String,
    );
  }

  final String cameraDisplayName;

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
