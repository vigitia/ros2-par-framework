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

/// A profile that cannot be shown: it no longer exists, or its files cannot be read. userText is written for the user.
class ProfileUnavailableException implements Exception {
  const ProfileUnavailableException(this.userText);

  final String userText;

  @override
  String toString() => 'Profile unavailable: $userText';
}

/// A sentence for the user about a failed backend call, without technical words; the real error goes to the console.
/// isBackendDetailShown: the backend's own sentence for answers that are the user's to fix (e.g. a camera that is in
/// the profile already). Only for calls whose backend texts are written for users.
String describeBackendErrorForUser(Object error, {bool isBackendDetailShown = false}) {
  debugPrint('[SetupWizardBackendClient]: $error');
  if (error is ProfileUnavailableException) {
    return error.userText;
  }
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

  /// Fetches what one profile runs. Throws ProfileUnavailableException when it no longer exists or its files cannot
  /// be read, and the usual errors when the backend is unreachable.
  Future<ProfileSummary> fetchProfileSummary(String profileName) async {
    final ProfileList profileList = await fetchProfileList();
    for (final ProfileSummary profileSummary in profileList.profileSummaries) {
      if (profileSummary.profileName != profileName) {
        continue;
      }
      final String? profileErrorText = profileSummary.profileErrorText;
      if (profileErrorText != null) {
        debugPrint('[SetupWizardBackendClient]: cannot read profile $profileName: $profileErrorText');
        throw const ProfileUnavailableException(
          'This profile\'s file cannot be read. It may contain a mistake from editing it by hand.',
        );
      }
      return profileSummary;
    }
    throw const ProfileUnavailableException(
      'This profile does not exist any more. Choose another one in the Overview.',
    );
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

  /// Tells the backend which profile was chosen, so the wizard opens it next time.
  Future<void> setLastSelectedProfile(String profileName) async {
    await sendJson('PUT', '/api/profiles/last-selected', {'profile_name': profileName});
  }

  /// Creates `config/profiles/<profileName>.yaml` with its cameras (in their order, the first is the main camera),
  /// the projector's display and the setting changes made in the new-profile wizard, each camera's under its name.
  /// Throws with the backend's reason, e.g. when the name is taken.
  Future<void> createProfile({
    required String profileName,
    required String profileDisplayName,
    required List<ProfileCameraUnit> cameras,
    required int? projectorDisplayId,
  }) async {
    await sendJson('POST', '/api/profiles', {
      'profile_name': profileName,
      'profile_display_name': profileDisplayName,
      'cameras': [
        for (final ProfileCameraUnit camera in cameras)
          {'camera_name': camera.cameraName, 'camera_type': camera.cameraType, 'serial': camera.serial},
      ],
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
    required this.enabledAppNames,
    required this.cameraNameByInputByApp,
    required this.projectorDisplayId,
    required this.storedProjectorDisplayId,
    required this.projectorDisplayState,
    required this.projectorTitleText,
    required this.storedDisplayTitleText,
    required this.storedDisplayModeText,
    required this.currentDisplayModeText,
    required this.isDisplayModeChanged,
    required this.profileErrorText,
  });

  factory ProfileSummary.fromJson(Map<String, dynamic> profileSummaryJson) {
    return ProfileSummary(
      profileName: profileSummaryJson['profile_name'] as String,
      cameras: _readCameraCalibrationSummaries(profileSummaryJson['cameras'] as List<dynamic>),
      sensorNodeNames: (profileSummaryJson['sensor_node_names'] as List<dynamic>).cast<String>(),
      appNames: (profileSummaryJson['app_names'] as List<dynamic>).cast<String>(),
      enabledAppNames: (profileSummaryJson['enabled_app_names'] as List<dynamic>).cast<String>(),
      cameraNameByInputByApp: _readCameraNameByInputByApp(
        profileSummaryJson['camera_name_by_input_by_app'] as Map<String, dynamic>,
      ),
      projectorDisplayId: profileSummaryJson['projector_display_id'] as int?,
      storedProjectorDisplayId: profileSummaryJson['stored_projector_display_id'] as int?,
      projectorDisplayState: ProjectorDisplayState.fromBackendName(profileSummaryJson['projector_display_state'] as String),
      projectorTitleText: profileSummaryJson['projector_title_text'] as String,
      storedDisplayTitleText: profileSummaryJson['stored_display_title_text'] as String,
      storedDisplayModeText: profileSummaryJson['stored_display_mode_text'] as String,
      currentDisplayModeText: profileSummaryJson['current_display_mode_text'] as String,
      isDisplayModeChanged: profileSummaryJson['is_display_mode_changed'] as bool,
      profileErrorText: profileSummaryJson['profile_error_text'] as String?,
    );
  }

  final String profileName;
  final List<CameraCalibrationSummary> cameras;
  final List<String> sensorNodeNames;
  final List<String> appNames;

  /// The apps the profile offers (par_launch.apps), in its order; the projector app is one of them.
  final List<String> enabledAppNames;

  /// par_launch.app_inputs: per app, the camera bound to each input; an input left out reads the only camera of a
  /// run.
  final Map<String, Map<String, String>> cameraNameByInputByApp;

  /// The display to use for the projector now (the framework's display_id): found by the projector's stored
  /// identity, else the stored id; null when the profile sets none or the projector is not found.
  final int? projectorDisplayId;

  /// par_launch.projector_display_id as written in the profile.
  final int? storedProjectorDisplayId;

  /// Whether the projector is at the stored display id; launches find it by its identity either way.
  final ProjectorDisplayState projectorDisplayState;

  /// The stored projector's name, e.g. 'EPS EB-680'; empty without a stored identity.
  final String projectorTitleText;

  /// The display at the stored id now, e.g. 'eDP-1 15"'; empty when none is or the displays cannot be read.
  final String storedDisplayTitleText;

  /// The display mode the projector was chosen with, e.g. '3840 × 2160 at 60 Hz'; empty when none is stored.
  final String storedDisplayModeText;

  /// The projector's display mode now; empty while it is not found.
  final String currentDisplayModeText;

  /// True when both modes are known and differ: the projector calibration may no longer fit.
  final bool isDisplayModeChanged;

  /// Set when the backend could not read the profile's files; the lists are empty then.
  final String? profileErrorText;

  static Map<String, Map<String, String>> _readCameraNameByInputByApp(Map<String, dynamic> appInputsJson) {
    final Map<String, Map<String, String>> cameraNameByInputByApp = {};
    for (final MapEntry<String, dynamic> appInputsEntry in appInputsJson.entries) {
      final Map<String, dynamic> cameraNameByInputJson = appInputsEntry.value as Map<String, dynamic>;
      cameraNameByInputByApp[appInputsEntry.key] = cameraNameByInputJson.cast<String, String>();
    }
    return cameraNameByInputByApp;
  }

  static List<CameraCalibrationSummary> _readCameraCalibrationSummaries(List<dynamic> camerasJson) {
    final List<CameraCalibrationSummary> cameras = [];
    for (final dynamic cameraJson in camerasJson) {
      cameras.add(CameraCalibrationSummary.fromJson(cameraJson as Map<String, dynamic>));
    }
    return cameras;
  }
}

/// A camera of a profile by its name, type and unit (serial empty when none is named), e.g. for a new profile or
/// the add dialog.
typedef ProfileCameraUnit = ({String cameraName, String cameraType, String serial});

/// A camera of a profile with the state of its intrinsics and its pose, as the backend reports them.
class CameraCalibrationSummary {
  const CameraCalibrationSummary({
    required this.cameraName,
    required this.cameraType,
    required this.serial,
    required this.isMainCamera,
    required this.intrinsicsState,
    required this.poseState,
  });

  factory CameraCalibrationSummary.fromJson(Map<String, dynamic> cameraJson) {
    return CameraCalibrationSummary(
      cameraName: cameraJson['camera_name'] as String,
      cameraType: cameraJson['camera_type'] as String,
      serial: cameraJson['serial'] as String,
      isMainCamera: cameraJson['is_main_camera'] as bool,
      intrinsicsState: IntrinsicsCalibrationState.fromBackendName(cameraJson['intrinsics_state'] as String),
      poseState: CameraPoseState.fromBackendName(cameraJson['pose_state'] as String),
    );
  }

  /// The camera's name in par_launch.cameras, e.g. 'overhead': its topics are `/cameras/<cameraName>/`.
  final String cameraName;

  /// Its type, a camera entry's name, e.g. 'brio'.
  final String cameraType;

  /// The unit's serial number; empty when the profile names none.
  final String serial;

  /// True for the first camera of the profile, the one the framework nodes use.
  final bool isMainCamera;

  final IntrinsicsCalibrationState intrinsicsState;
  final CameraPoseState poseState;
}

/// Whether a camera unit has its lens calibration (backend profiles_api.INTRINSICS_STATE_*).
enum IntrinsicsCalibrationState {
  /// A calibration file in the profile's intrinsics folder.
  calibrated('calibrated'),

  /// The camera publishes its own factory calibration.
  factory('factory'),
  missing('missing'),

  /// The wizard cannot calibrate this camera (yet).
  unsupported('unsupported');

  const IntrinsicsCalibrationState(this.backendName);

  final String backendName;

  static IntrinsicsCalibrationState fromBackendName(String backendName) {
    for (final IntrinsicsCalibrationState intrinsicsState in IntrinsicsCalibrationState.values) {
      if (intrinsicsState.backendName == backendName) {
        return intrinsicsState;
      }
    }
    throw FormatException('Unknown intrinsics state from the backend: $backendName');
  }
}

/// Whether the profile has a measured pose for a camera unit (backend profiles_api.POSE_STATE_*).
enum CameraPoseState {
  measured('measured'),

  /// No pose file: launches use the placeholder pose of the parameter files.
  placeholder('placeholder'),

  /// A pose file that cannot be used, e.g. one edited by hand that lacks a key.
  invalid('invalid');

  const CameraPoseState(this.backendName);

  final String backendName;

  static CameraPoseState fromBackendName(String backendName) {
    for (final CameraPoseState poseState in CameraPoseState.values) {
      if (poseState.backendName == backendName) {
        return poseState;
      }
    }
    throw FormatException('Unknown camera pose state from the backend: $backendName');
  }
}

/// Whether a profile's projector is at its stored display id (backend profiles_api.PROJECTOR_DISPLAY_STATE_*).
enum ProjectorDisplayState {
  notSet('not_set'),

  /// A display id without a stored identity (written by hand): nothing to check it against.
  unidentified('unidentified'),
  connected('connected'),

  /// Connected, but under another display id than the stored one.
  moved('moved'),
  notConnected('not_connected'),

  /// Several displays match the stored identity (identical projectors without a serial).
  ambiguous('ambiguous'),
  displaysUnreadable('displays_unreadable');

  const ProjectorDisplayState(this.backendName);

  final String backendName;

  static ProjectorDisplayState fromBackendName(String backendName) {
    for (final ProjectorDisplayState projectorDisplayState in ProjectorDisplayState.values) {
      if (projectorDisplayState.backendName == backendName) {
        return projectorDisplayState;
      }
    }
    throw FormatException('Unknown projector display state from the backend: $backendName');
  }
}
