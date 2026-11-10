// Written by Claude Code
//
// The backend's cameras API (setup_wizard/backend/cameras_api.py): every camera the framework supports, with
// whether its driver packages are installed on the PAR machine.

import 'setup_wizard_backend_client.dart';

/// A camera the framework supports, as listed by GET /api/cameras.
class SupportedCamera {
  const SupportedCamera({required this.cameraName, required this.driverPackageNames, required this.isInstalled});

  factory SupportedCamera.fromJson(Map<String, dynamic> cameraJson) {
    return SupportedCamera(
      cameraName: cameraJson['camera_name'] as String,
      driverPackageNames: (cameraJson['driver_package_names'] as List<dynamic>).cast<String>(),
      isInstalled: cameraJson['is_installed'] as bool,
    );
  }

  /// The name launch files use (par_launch.camera, camera:=), e.g. 'brio'.
  final String cameraName;
  final List<String> driverPackageNames;

  /// True when every driver package is installed, so the camera can be started.
  final bool isInstalled;
}

extension CamerasApi on SetupWizardBackendClient {
  /// Fetches every supported camera with its installed state.
  Future<List<SupportedCamera>> fetchSupportedCameras() async {
    final Map<String, dynamic> cameraListJson = await getJson('/api/cameras') as Map<String, dynamic>;
    final List<dynamic> camerasJson = cameraListJson['cameras'] as List<dynamic>;
    final List<SupportedCamera> supportedCameras = [];
    for (final dynamic cameraJson in camerasJson) {
      supportedCameras.add(SupportedCamera.fromJson(cameraJson as Map<String, dynamic>));
    }
    return supportedCameras;
  }

  /// Adds a camera unit to the profile's cameras, to set up and calibrate it there. serial is empty for a camera
  /// that has none.
  Future<void> addProfileCamera({required String profileName, required String cameraName, String serial = ''}) async {
    await sendJson('POST', '/api/profiles/${Uri.encodeComponent(profileName)}/cameras',
        {'camera_name': cameraName, 'serial': serial});
  }

  /// Makes the camera unit the one the next run of the profile starts.
  Future<void> setProfileMainCamera({required String profileName, required String cameraName, String serial = ''}) async {
    await sendJson('PUT', '/api/profiles/${Uri.encodeComponent(profileName)}/main-camera',
        {'camera_name': cameraName, 'serial': serial});
  }

  /// Removes a camera unit that is not selected; its calibrations are moved to the profiles' .deleted folder.
  Future<void> removeProfileCamera({required String profileName, required String cameraName, String serial = ''}) async {
    final String query = 'camera_name=${Uri.encodeQueryComponent(cameraName)}&serial=${Uri.encodeQueryComponent(serial)}';
    await sendJson('DELETE', '/api/profiles/${Uri.encodeComponent(profileName)}/cameras?$query', null);
  }

  /// The serials of the connected units of a camera type. isListingSupported is false when the backend cannot list
  /// them, so the serial has to be typed.
  Future<ConnectedCameraUnits> fetchConnectedCameraUnits(String cameraName) async {
    final Map<String, dynamic> unitsJson =
        await getJson('/api/cameras/${Uri.encodeComponent(cameraName)}/units') as Map<String, dynamic>;
    return ConnectedCameraUnits(
      isSerialSupported: unitsJson['is_serial_supported'] as bool,
      isListingSupported: unitsJson['is_listing_supported'] as bool,
      serials: (unitsJson['serials'] as List<dynamic>).cast<String>(),
    );
  }
}

class ConnectedCameraUnits {
  const ConnectedCameraUnits({
    required this.isSerialSupported,
    required this.isListingSupported,
    required this.serials,
  });

  /// True for a camera type with serial numbers: several units of it can be in one profile.
  final bool isSerialSupported;

  final bool isListingSupported;
  final List<String> serials;
}
