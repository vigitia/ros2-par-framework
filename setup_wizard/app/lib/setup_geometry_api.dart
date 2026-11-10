// Written by Claude Code
//
// The app's call to the backend's setup geometry (setup_wizard/backend/setup_geometry_api.py): where a profile's
// cameras and projector are, in metres in world (the table plane is z = 0).

import 'setup_wizard_backend_client.dart';

extension SetupGeometryApi on SetupWizardBackendClient {
  Future<SetupGeometry> fetchSetupGeometry(String profileName) async {
    final Map<String, dynamic> geometryJson =
        await getJson('/api/profiles/${Uri.encodeComponent(profileName)}/setup-geometry') as Map<String, dynamic>;
    return SetupGeometry.fromJson(geometryJson);
  }
}

/// A point in world, in metres.
class WorldPointM {
  const WorldPointM({required this.xM, required this.yM, required this.zM});

  /// From [x, y, z], or [x, y] on the table (z = 0).
  factory WorldPointM.fromJson(List<dynamic> coordinatesJson) {
    double zM = 0;
    if (coordinatesJson.length > 2) {
      zM = (coordinatesJson[2] as num).toDouble();
    }
    return WorldPointM(
      xM: (coordinatesJson[0] as num).toDouble(),
      yM: (coordinatesJson[1] as num).toDouble(),
      zM: zM,
    );
  }

  final double xM;
  final double yM;
  final double zM;
}

List<WorldPointM>? _readOptionalPoints(dynamic pointsJson) {
  if (pointsJson == null) {
    return null;
  }
  final List<WorldPointM> points = [];
  for (final dynamic pointJson in pointsJson as List<dynamic>) {
    points.add(WorldPointM.fromJson(pointJson as List<dynamic>));
  }
  return points;
}

WorldPointM? _readOptionalPoint(dynamic pointJson) {
  if (pointJson == null) {
    return null;
  }
  return WorldPointM.fromJson(pointJson as List<dynamic>);
}

class CameraGeometry {
  const CameraGeometry({
    required this.cameraId,
    required this.cameraType,
    required this.serial,
    required this.isMainCamera,
    required this.isPoseMeasured,
    required this.positionM,
    required this.opticalAxisTableHitM,
    required this.tableFootprintM,
  });

  factory CameraGeometry.fromJson(Map<String, dynamic> cameraJson) {
    return CameraGeometry(
      cameraId: cameraJson['camera_id'] as String,
      cameraType: cameraJson['camera_type'] as String,
      serial: cameraJson['serial'] as String,
      isMainCamera: cameraJson['is_main_camera'] as bool,
      isPoseMeasured: cameraJson['is_pose_measured'] as bool,
      positionM: WorldPointM.fromJson(cameraJson['position_m'] as List<dynamic>),
      opticalAxisTableHitM: _readOptionalPoint(cameraJson['optical_axis_table_hit_m']),
      tableFootprintM: _readOptionalPoints(cameraJson['table_footprint_m']),
    );
  }

  /// The unit's identifier, e.g. 'blackfly_22260470'.
  final String cameraId;

  /// Type and serial of the unit, as the Cameras area selects it; serial is empty for a camera without one.
  final String cameraType;
  final String serial;

  /// The unit a run of the profile starts.
  final bool isMainCamera;

  /// False: the placeholder pose from the parameter files.
  final bool isPoseMeasured;
  final WorldPointM positionM;

  /// Where the optical axis meets the table; null when it points away from it.
  final WorldPointM? opticalAxisTableHitM;

  /// The field of view's outline on the table; null without intrinsics (e.g. factory intrinsics).
  final List<WorldPointM>? tableFootprintM;
}

class ProjectorGeometry {
  const ProjectorGeometry({required this.projectionAreaM, required this.centerM, required this.mappingCameraId});

  factory ProjectorGeometry.fromJson(Map<String, dynamic> projectorJson) {
    return ProjectorGeometry(
      projectionAreaM: _readOptionalPoints(projectorJson['projection_area_m']) ?? [],
      centerM: _readOptionalPoint(projectorJson['center_m']),
      mappingCameraId: projectorJson['mapping_camera_id'] as String,
    );
  }

  /// The projector image's corners on the table.
  final List<WorldPointM> projectionAreaM;

  /// The projector's optical centre; null until measured.
  final WorldPointM? centerM;

  /// The camera unit whose projection mapping this is.
  final String mappingCameraId;
}

class SetupGeometry {
  const SetupGeometry({
    required this.cameras,
    required this.projector,
    required this.frontViewRightDirection,
    required this.frontViewReferenceText,
    required this.geometryErrorTexts,
  });

  factory SetupGeometry.fromJson(Map<String, dynamic> geometryJson) {
    final List<CameraGeometry> cameras = [];
    for (final dynamic cameraJson in geometryJson['cameras'] as List<dynamic>) {
      cameras.add(CameraGeometry.fromJson(cameraJson as Map<String, dynamic>));
    }
    ProjectorGeometry? projector;
    final dynamic projectorJson = geometryJson['projector'];
    if (projectorJson != null) {
      projector = ProjectorGeometry.fromJson(projectorJson as Map<String, dynamic>);
    }
    final List<double> frontViewRightDirection = [];
    for (final dynamic coordinateJson in geometryJson['front_view_right_direction'] as List<dynamic>) {
      frontViewRightDirection.add((coordinateJson as num).toDouble());
    }
    return SetupGeometry(
      cameras: cameras,
      projector: projector,
      frontViewRightDirection: frontViewRightDirection,
      frontViewReferenceText: geometryJson['front_view_reference_text'] as String,
      geometryErrorTexts: (geometryJson['geometry_error_texts'] as List<dynamic>).cast<String>(),
    );
  }

  final List<CameraGeometry> cameras;

  /// null without a projection mapping of the selected camera.
  final ProjectorGeometry? projector;

  /// Left to right as seen from the front: a unit [x, y] on the table, along the projected image's rows.
  final List<double> frontViewRightDirection;

  /// What frontViewRightDirection follows, e.g. 'the projected image'.
  final String frontViewReferenceText;

  /// Why a camera or the mapping is left out.
  final List<String> geometryErrorTexts;
}
