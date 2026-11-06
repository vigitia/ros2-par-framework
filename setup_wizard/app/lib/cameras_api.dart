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
}
