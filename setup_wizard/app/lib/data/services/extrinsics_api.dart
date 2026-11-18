// Written by Claude Code
//
// The app's calls to the backend's camera pose and projector calibration (setup_wizard/backend/calibration/extrinsics_api.py):
// what a profile has stored for a camera, starting a calibration run on it, and the run's progress. A run is
// stopped like a preview (stopCameraPreview with the run's preview id), since its launch runs as the preview's
// camera.

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

/// What a run calibrates (backend CALIBRATION_KIND_*).
enum ExtrinsicsCalibrationKind { poseBoard, poseDepth, projectionMapping, projectorCenter }

/// Phase of a run (backend RUN_PHASE_*).
enum ExtrinsicsRunPhase { running, stored, failed, stopped }

const Map<ExtrinsicsCalibrationKind, String> extrinsicsCalibrationKindTextByKind = {
  ExtrinsicsCalibrationKind.poseBoard: 'pose_board',
  ExtrinsicsCalibrationKind.poseDepth: 'pose_depth',
  ExtrinsicsCalibrationKind.projectionMapping: 'projection_mapping',
  ExtrinsicsCalibrationKind.projectorCenter: 'projector_center',
};

extension ExtrinsicsApi on SetupWizardBackendClient {
  Future<ExtrinsicsState> fetchExtrinsicsState({required String profileName, required String cameraName}) async {
    final Uri stateUri = Uri.parse('$backendBaseUrl/api/extrinsics/state')
        .replace(queryParameters: {'profile_name': profileName, 'camera_name': cameraName});
    final http.Response response = await http.get(stateUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return ExtrinsicsState.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Starts a calibration run on the camera, replacing the preview that runs now, and returns the run's preview
  /// id. The board values are needed for poseBoard only.
  Future<int> startExtrinsicsCalibration({
    required String profileName,
    required String cameraName,
    required ExtrinsicsCalibrationKind calibrationKind,
    int? boardInnerCornerColumns,
    int? boardInnerCornerRows,
    double? squareSizeM,
  }) async {
    final http.Request request = http.Request('POST', Uri.parse('$backendBaseUrl/api/extrinsics/run/start'));
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode({
      'profile_name': profileName,
      'camera_name': cameraName,
      'calibration_kind': extrinsicsCalibrationKindTextByKind[calibrationKind],
      'board_inner_corner_columns': boardInnerCornerColumns,
      'board_inner_corner_rows': boardInnerCornerRows,
      'square_size_m': squareSizeM,
    });
    // Starting stops the running preview first, which may take a while
    final http.StreamedResponse streamedResponse = await request.send().timeout(cameraPreviewStartStopTimeout);
    final http.Response response = await http.Response.fromStream(streamedResponse);
    _throwOnError(response);
    final Map<String, dynamic> startJson = jsonDecode(response.body) as Map<String, dynamic>;
    return startJson['preview_id'] as int;
  }

  Future<ExtrinsicsRunProgress> fetchExtrinsicsRunProgress() async {
    final Uri progressUri = Uri.parse('$backendBaseUrl/api/extrinsics/run/progress');
    final http.Response response = await http.get(progressUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return ExtrinsicsRunProgress.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  void _throwOnError(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw BackendRequestException.fromResponse(response);
    }
  }
}

ExtrinsicsCalibrationKind? _parseCalibrationKind(String calibrationKindText) {
  for (final MapEntry<ExtrinsicsCalibrationKind, String> kindEntry in extrinsicsCalibrationKindTextByKind.entries) {
    if (kindEntry.value == calibrationKindText) {
      return kindEntry.key;
    }
  }
  // A kind a newer backend offers and this app does not know is left out
  return null;
}

/// The profile's stored camera pose and projector calibration for one camera, and what can be calibrated now.
class ExtrinsicsState {
  const ExtrinsicsState({
    required this.cameraPose,
    required this.projectionMapping,
    required this.availableCalibrationKinds,
    required this.missingPackageTextByCalibrationKind,
  });

  factory ExtrinsicsState.fromJson(Map<String, dynamic> stateJson) {
    final Set<ExtrinsicsCalibrationKind> availableCalibrationKinds = {};
    for (final dynamic calibrationKindJson in stateJson['available_calibration_kinds'] as List<dynamic>) {
      final ExtrinsicsCalibrationKind? calibrationKind = _parseCalibrationKind(calibrationKindJson as String);
      if (calibrationKind != null) {
        availableCalibrationKinds.add(calibrationKind);
      }
    }
    final Map<ExtrinsicsCalibrationKind, String> missingPackageTextByCalibrationKind = {};
    final Map<String, dynamic> missingPackagesJson =
        stateJson['missing_package_text_by_calibration_kind'] as Map<String, dynamic>;
    for (final MapEntry<String, dynamic> missingPackagesEntry in missingPackagesJson.entries) {
      final ExtrinsicsCalibrationKind? calibrationKind = _parseCalibrationKind(missingPackagesEntry.key);
      if (calibrationKind != null) {
        missingPackageTextByCalibrationKind[calibrationKind] = missingPackagesEntry.value as String;
      }
    }
    return ExtrinsicsState(
      cameraPose: CameraPoseSummary.fromJson(stateJson['camera_pose'] as Map<String, dynamic>),
      projectionMapping: ProjectionMappingSummary.fromJson(stateJson['projection_mapping'] as Map<String, dynamic>),
      availableCalibrationKinds: availableCalibrationKinds,
      missingPackageTextByCalibrationKind: missingPackageTextByCalibrationKind,
    );
  }

  final CameraPoseSummary cameraPose;
  final ProjectionMappingSummary projectionMapping;
  final Set<ExtrinsicsCalibrationKind> availableCalibrationKinds;

  /// Which packages a kind needs that are not installed, with the command that installs them.
  final Map<ExtrinsicsCalibrationKind, String> missingPackageTextByCalibrationKind;
}

class CameraPoseSummary {
  const CameraPoseSummary({
    required this.isMeasured,
    required this.poseFileErrorText,
    required this.measuredText,
    required this.heightAboveTableM,
    required this.tiltFromVerticalDeg,
    required this.qualityFigureByName,
  });

  factory CameraPoseSummary.fromJson(Map<String, dynamic> poseJson) {
    final Map<String, String> qualityFigureByName = {};
    final Map<String, dynamic> qualityFiguresJson = poseJson['quality_figures'] as Map<String, dynamic>;
    for (final MapEntry<String, dynamic> qualityFigureEntry in qualityFiguresJson.entries) {
      qualityFigureByName[qualityFigureEntry.key] = '${qualityFigureEntry.value}';
    }
    return CameraPoseSummary(
      isMeasured: poseJson['is_measured'] as bool,
      poseFileErrorText: poseJson['pose_file_error_text'] as String,
      measuredText: poseJson['measured_text'] as String,
      heightAboveTableM: (poseJson['height_above_table_m'] as num?)?.toDouble(),
      tiltFromVerticalDeg: (poseJson['tilt_from_vertical_deg'] as num?)?.toDouble(),
      qualityFigureByName: qualityFigureByName,
    );
  }

  /// False while the profile uses par_setup.yaml's placeholder pose.
  final bool isMeasured;

  /// Why the stored pose file cannot be used; empty otherwise.
  final String poseFileErrorText;

  /// When it was measured, as the file says (an ISO time or a hand-written note).
  final String measuredText;
  final double? heightAboveTableM;

  /// Angle between the camera's viewing direction and straight down.
  final double? tiltFromVerticalDeg;

  /// The measuring method's own figures, e.g. 'board_reprojection_error_px' → '0.15'.
  final Map<String, String> qualityFigureByName;
}

class ProjectionMappingSummary {
  const ProjectionMappingSummary({
    required this.isCalibrated,
    required this.mappingFileErrorText,
    required this.measuredText,
    required this.reprojectionErrorPx,
    required this.projectorWidthPx,
    required this.projectorHeightPx,
    required this.hasProjectorCenter,
    required this.isOlderThanCameraPose,
  });

  factory ProjectionMappingSummary.fromJson(Map<String, dynamic> mappingJson) {
    return ProjectionMappingSummary(
      isCalibrated: mappingJson['is_calibrated'] as bool,
      mappingFileErrorText: mappingJson['mapping_file_error_text'] as String,
      measuredText: mappingJson['measured_text'] as String,
      reprojectionErrorPx: (mappingJson['reprojection_error_px'] as num?)?.toDouble(),
      projectorWidthPx: mappingJson['projector_width_px'] as int?,
      projectorHeightPx: mappingJson['projector_height_px'] as int?,
      hasProjectorCenter: mappingJson['has_projector_center'] as bool,
      isOlderThanCameraPose: mappingJson['is_older_than_camera_pose'] as bool,
    );
  }

  final bool isCalibrated;

  /// Why the stored mapping file cannot be used; empty otherwise.
  final String mappingFileErrorText;
  final String measuredText;

  /// How far the projected markers lie from where the fitted homography puts them.
  final double? reprojectionErrorPx;
  final int? projectorWidthPx;
  final int? projectorHeightPx;
  final bool hasProjectorCenter;

  /// Measured before the current camera pose, i.e. on the old table plane: calibrate again.
  final bool isOlderThanCameraPose;
}

class ExtrinsicsRunProgress {
  const ExtrinsicsRunProgress({required this.phase, required this.calibrationKind, required this.logLines});

  factory ExtrinsicsRunProgress.fromJson(Map<String, dynamic> progressJson) {
    final List<String> logLines = [];
    for (final dynamic logLineJson in progressJson['log_lines'] as List<dynamic>) {
      logLines.add(logLineJson as String);
    }
    return ExtrinsicsRunProgress(
      phase: ExtrinsicsRunPhase.values.byName(progressJson['phase'] as String),
      calibrationKind: _parseCalibrationKind(progressJson['calibration_kind'] as String),
      logLines: logLines,
    );
  }

  final ExtrinsicsRunPhase phase;
  final ExtrinsicsCalibrationKind? calibrationKind;

  /// For failed and stopped runs: the error lines of the launch's output, as they are.
  final List<String> logLines;
}
