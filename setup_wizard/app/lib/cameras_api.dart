// Written by Claude Code
//
// The backend's cameras API (setup_wizard/backend/cameras_api.py and the camera endpoints of profiles_api.py): the
// installed camera types with what their entries say, their connected units, and a profile's cameras by name.

import 'setup_wizard_backend_client.dart';

/// What a camera name may hold, as the backend checks it (launch_helpers.CAMERA_NAME_PATTERN): it becomes part of
/// `/cameras/<name>`, TF frames and calibration file names.
final RegExp cameraNamePattern = RegExp(r'^[a-z][a-z0-9_]*$');

/// The entry's serial: units of the type have no serial numbers (one per profile).
const String serialSourceNone = 'none';

/// The entry's serial: the units are listed by the backend (and can be typed too).
const String serialSourceListed = 'listed';

/// An installed camera type, as listed by GET /api/cameras.
class CameraType {
  const CameraType({
    required this.cameraType,
    required this.displayName,
    required this.description,
    required this.isInstalled,
    required this.serialSource,
    required this.entryErrorText,
  });

  factory CameraType.fromJson(Map<String, dynamic> cameraTypeJson) {
    return CameraType(
      cameraType: cameraTypeJson['camera_type'] as String,
      displayName: cameraTypeJson['display_name'] as String,
      description: cameraTypeJson['description'] as String,
      isInstalled: cameraTypeJson['is_installed'] as bool,
      serialSource: cameraTypeJson['serial_source'] as String,
      entryErrorText: cameraTypeJson['entry_error_text'] as String?,
    );
  }

  /// The type's name, as in par_launch.cameras, e.g. 'brio'.
  final String cameraType;
  final String displayName;
  final String description;

  /// True when every package the type's launch file needs (e.g. a released driver) is installed, so the type can be
  /// started.
  final bool isInstalled;

  /// none, typed or listed: whether units have serial numbers and whether the backend lists the connected ones.
  final String serialSource;

  /// Set when the type's entry cannot be read; the type cannot be used then.
  final String? entryErrorText;

  bool get hasSerials => serialSource != serialSourceNone;

  /// True when the type can be added to a profile.
  bool get isUsable => isInstalled && entryErrorText == null;
}

/// Returns the name suggested for a new camera of cameraType: the type itself, else `<type>_2`, `<type>_3`, ... the
/// first one not taken.
String suggestCameraName(String cameraType, Iterable<String> takenCameraNames) {
  final Set<String> takenCameraNameSet = takenCameraNames.toSet();
  if (!takenCameraNameSet.contains(cameraType)) {
    return cameraType;
  }
  int cameraNumber = 2;
  while (takenCameraNameSet.contains('${cameraType}_$cameraNumber')) {
    cameraNumber += 1;
  }
  return '${cameraType}_$cameraNumber';
}

extension CamerasApi on SetupWizardBackendClient {
  /// Fetches every installed camera type with what its entry says.
  Future<List<CameraType>> fetchCameraTypes() async {
    final Map<String, dynamic> cameraTypeListJson = await getJson('/api/cameras') as Map<String, dynamic>;
    final List<CameraType> cameraTypes = [];
    for (final dynamic cameraTypeJson in cameraTypeListJson['camera_types'] as List<dynamic>) {
      cameraTypes.add(CameraType.fromJson(cameraTypeJson as Map<String, dynamic>));
    }
    return cameraTypes;
  }

  /// Adds a camera to the profile's par_launch.cameras under cameraName; every run of the profile starts it. serial
  /// is empty for a type without serial numbers.
  Future<void> addProfileCamera({
    required String profileName,
    required String cameraName,
    required String cameraType,
    String serial = '',
  }) async {
    await sendJson('POST', '/api/profiles/${Uri.encodeComponent(profileName)}/cameras',
        {'camera_name': cameraName, 'camera_type': cameraType, 'serial': serial});
  }

  /// Removes a camera from the profile; its calibrations are moved to the profiles' .deleted folder.
  Future<void> removeProfileCamera({required String profileName, required String cameraName}) async {
    final String cameraPath =
        '/api/profiles/${Uri.encodeComponent(profileName)}/cameras/${Uri.encodeComponent(cameraName)}';
    await sendJson('DELETE', cameraPath, null);
  }

  /// The serials of the connected units of a camera type, as far as its entry says how to find them.
  Future<ConnectedCameraUnits> fetchConnectedCameraUnits(String cameraType) async {
    final Map<String, dynamic> unitsJson =
        await getJson('/api/cameras/${Uri.encodeComponent(cameraType)}/units') as Map<String, dynamic>;
    return ConnectedCameraUnits(
      serialSource: unitsJson['serial_source'] as String,
      serials: (unitsJson['serials'] as List<dynamic>).cast<String>(),
    );
  }
}

class ConnectedCameraUnits {
  const ConnectedCameraUnits({required this.serialSource, required this.serials});

  /// none, typed or listed, as in CameraType.
  final String serialSource;

  /// The connected units' serials; only filled for listed.
  final List<String> serials;

  bool get hasSerials => serialSource != serialSourceNone;
  bool get isListingSupported => serialSource == serialSourceListed;
}
