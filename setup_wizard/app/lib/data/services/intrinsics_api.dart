// Written by Claude Code
//
// The app's calls to the backend's lens calibration (setup_wizard/backend/calibration/intrinsics_api.py): where the previewed
// camera's intrinsics come from, and the calibration on it (start, progress, frame with the detected board,
// calibrate, save, stop).

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'setup_wizard_backend_client.dart';

/// Saving waits for the driver to write its calibration file.
const Duration intrinsicsSaveTimeout = Duration(seconds: 15);

/// Where a camera's intrinsics come from (backend INTRINSICS_SOURCE_*).
enum IntrinsicsSource { noCameraInfo, uncalibrated, calibrationFile, camera }

/// Phase of a running calibration (backend CALIBRATION_PHASE_*).
enum IntrinsicsCalibrationPhase { collecting, calibrating, calibrated, failed }

extension IntrinsicsApi on SetupWizardBackendClient {
  /// Where the previewed camera's intrinsics come from; null while the camera is still starting.
  Future<CameraIntrinsicsState?> fetchCameraIntrinsicsState() async {
    final Uri stateUri = Uri.parse('$backendBaseUrl/api/intrinsics/camera-state');
    final http.Response response = await http.get(stateUri).timeout(backendRequestTimeout * 3);
    if (response.statusCode == 503) {
      return null;
    }
    _throwOnError(response);
    return CameraIntrinsicsState.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Starts collecting views of a checkerboard with the given inner corners and measured square size.
  Future<void> startIntrinsicsCalibration({
    required int boardInnerCornerColumns,
    required int boardInnerCornerRows,
    required double squareSizeM,
  }) async {
    await _postIntrinsicsJson('/api/intrinsics/calibration/start', {
      'board_inner_corner_columns': boardInnerCornerColumns,
      'board_inner_corner_rows': boardInnerCornerRows,
      'square_size_m': squareSizeM,
    });
  }

  Future<IntrinsicsCalibrationProgress> fetchIntrinsicsCalibrationProgress() async {
    final Uri progressUri = Uri.parse('$backendBaseUrl/api/intrinsics/calibration/progress');
    final http.Response response = await http.get(progressUri).timeout(backendRequestTimeout);
    _throwOnError(response);
    return IntrinsicsCalibrationProgress.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// The latest frame with the detected board drawn in, as JPEG; null before the first one.
  Future<Uint8List?> fetchIntrinsicsCalibrationFrame() async {
    final Uri frameUri = Uri.parse('$backendBaseUrl/api/intrinsics/calibration/frame');
    final http.Response response = await http.get(frameUri).timeout(backendRequestTimeout);
    if (response.statusCode == 204) {
      return null;
    }
    _throwOnError(response);
    return response.bodyBytes;
  }

  /// Starts computing the calibration; its end shows in the progress (phase calibrated or failed).
  Future<void> calibrateIntrinsics() async {
    await _postIntrinsicsJson('/api/intrinsics/calibration/calibrate', {});
  }

  /// Sends the calibration to the driver, which stores it; returns the driver's message.
  Future<String> saveIntrinsicsCalibration() async {
    final http.Response response = await _postIntrinsicsJson('/api/intrinsics/calibration/save', {});
    final Map<String, dynamic> saveJson = jsonDecode(response.body) as Map<String, dynamic>;
    return saveJson['status_message'] as String;
  }

  Future<void> stopIntrinsicsCalibration() async {
    await _postIntrinsicsJson('/api/intrinsics/calibration/stop', {});
  }

  Future<http.Response> _postIntrinsicsJson(String apiPath, Map<String, Object?> requestJson) async {
    final http.Response response = await http
        .post(
          Uri.parse('$backendBaseUrl$apiPath'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(requestJson),
        )
        .timeout(intrinsicsSaveTimeout);
    _throwOnError(response);
    return response;
  }

  void _throwOnError(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw BackendRequestException.fromResponse(response);
    }
  }
}

class CameraIntrinsicsState {
  const CameraIntrinsicsState({
    required this.intrinsicsSource,
    required this.canStoreCalibration,
    required this.calibrationFileModifiedIso,
  });

  factory CameraIntrinsicsState.fromJson(Map<String, dynamic> stateJson) {
    return CameraIntrinsicsState(
      intrinsicsSource: _parseIntrinsicsSource(stateJson['intrinsics_source'] as String),
      canStoreCalibration: stateJson['can_store_calibration'] as bool,
      calibrationFileModifiedIso: stateJson['calibration_file_modified_iso'] as String,
    );
  }

  final IntrinsicsSource intrinsicsSource;

  /// Whether the driver can store a new calibration (it offers set_camera_info).
  final bool canStoreCalibration;

  /// When the file was last written; empty when it does not exist.
  final String calibrationFileModifiedIso;
}

IntrinsicsSource _parseIntrinsicsSource(String intrinsicsSourceText) {
  switch (intrinsicsSourceText) {
    case 'no_camera_info':
      return IntrinsicsSource.noCameraInfo;
    case 'uncalibrated':
      return IntrinsicsSource.uncalibrated;
    case 'calibration_file':
      return IntrinsicsSource.calibrationFile;
    case 'camera':
      return IntrinsicsSource.camera;
  }
  throw FormatException('Unknown intrinsics source $intrinsicsSourceText');
}

class IntrinsicsCalibrationProgress {
  const IntrinsicsCalibrationProgress({
    required this.phase,
    required this.sampleCount,
    required this.progressFractionByPoseParameter,
    required this.isGoodEnough,
    required this.linearErrorPx,
    required this.focalLengthXPx,
    required this.focalLengthYPx,
    required this.errorText,
  });

  factory IntrinsicsCalibrationProgress.fromJson(Map<String, dynamic> progressJson) {
    final Map<String, double> progressFractionByPoseParameter = {};
    for (final dynamic coverageJson in progressJson['coverage'] as List<dynamic>) {
      final Map<String, dynamic> coverageEntry = coverageJson as Map<String, dynamic>;
      progressFractionByPoseParameter[coverageEntry['pose_parameter_name'] as String] =
          (coverageEntry['progress_fraction'] as num).toDouble();
    }
    return IntrinsicsCalibrationProgress(
      phase: IntrinsicsCalibrationPhase.values.byName(progressJson['phase'] as String),
      sampleCount: progressJson['sample_count'] as int,
      progressFractionByPoseParameter: progressFractionByPoseParameter,
      isGoodEnough: progressJson['is_good_enough'] as bool,
      linearErrorPx: (progressJson['linear_error_px'] as num?)?.toDouble(),
      focalLengthXPx: (progressJson['focal_length_x_px'] as num?)?.toDouble(),
      focalLengthYPx: (progressJson['focal_length_y_px'] as num?)?.toDouble(),
      errorText: progressJson['error_text'] as String,
    );
  }

  final IntrinsicsCalibrationPhase phase;
  final int sampleCount;

  /// 0 to 1 per 'X', 'Y', 'Size', 'Skew': how much of the needed variety of board poses the views cover.
  final Map<String, double> progressFractionByPoseParameter;

  /// Enough views to calibrate.
  final bool isGoodEnough;

  /// After calibrating, for the board in the latest frame: how far its undistorted corners are from straight
  /// lines; null without a board in view.
  final double? linearErrorPx;
  final double? focalLengthXPx;
  final double? focalLengthYPx;
  final String errorText;
}
