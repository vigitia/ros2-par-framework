// Written by Claude Code
//
// The app's calls to the backend's focus measure (setup_wizard/backend/cameras/focus_api.py): the sharpness of the previewed
// camera's image centre with its best value so far, the centre crop itself, and resetting the best value.

import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'setup_wizard_backend_client.dart';

extension FocusApi on SetupWizardBackendClient {
  /// Measures the newest frame of the running preview. Throws while no preview runs.
  Future<FocusMeasurement> fetchFocusMeasurement() async {
    final Map<String, dynamic> stateJson = await getJson('/api/focus/state') as Map<String, dynamic>;
    return FocusMeasurement.fromJson(stateJson);
  }

  /// Forgets the best sharpness, e.g. after the camera or the scene under it moved.
  Future<void> resetFocusPeak() async {
    await sendJson('POST', '/api/focus/reset-peak', null);
  }

  /// Returns the last measured centre crop as PNG bytes at full camera resolution, or null before the first.
  Future<Uint8List?> fetchFocusCenterCrop() async {
    final Uri cropUri = Uri.parse('$backendBaseUrl/api/focus/center-crop');
    final http.Response response = await http.get(cropUri).timeout(backendRequestTimeout);
    if (response.statusCode == 204) {
      return null;
    }
    if (response.statusCode != 200) {
      throw BackendRequestException.fromResponse(response);
    }
    return response.bodyBytes;
  }
}

class FocusMeasurement {
  const FocusMeasurement({
    required this.sharpness,
    required this.peakSharpness,
    required this.measuredArea,
  });

  factory FocusMeasurement.fromJson(Map<String, dynamic> stateJson) {
    final int? frameWidthPx = stateJson['frame_width_px'] as int?;
    final int? frameHeightPx = stateJson['frame_height_px'] as int?;
    final int? cropLeftPx = stateJson['crop_left_px'] as int?;
    final int? cropTopPx = stateJson['crop_top_px'] as int?;
    final int? cropSidePx = stateJson['crop_side_px'] as int?;
    FocusMeasuredArea? measuredArea;
    if (frameWidthPx != null &&
        frameHeightPx != null &&
        cropLeftPx != null &&
        cropTopPx != null &&
        cropSidePx != null) {
      measuredArea = FocusMeasuredArea(
        frameWidthPx: frameWidthPx,
        frameHeightPx: frameHeightPx,
        cropLeftPx: cropLeftPx,
        cropTopPx: cropTopPx,
        cropSidePx: cropSidePx,
      );
    }
    return FocusMeasurement(
      sharpness: (stateJson['sharpness'] as num?)?.toDouble(),
      peakSharpness: (stateJson['peak_sharpness'] as num?)?.toDouble(),
      measuredArea: measuredArea,
    );
  }

  /// Averaged over the last frames; null until the first frame was measured.
  final double? sharpness;

  /// The highest sharpness since the preview started or the best value was reset.
  final double? peakSharpness;

  /// Where in the frame the sharpness is measured; null until the first frame was measured.
  final FocusMeasuredArea? measuredArea;
}

/// The square at the image centre the sharpness is measured in, in camera pixels.
class FocusMeasuredArea {
  const FocusMeasuredArea({
    required this.frameWidthPx,
    required this.frameHeightPx,
    required this.cropLeftPx,
    required this.cropTopPx,
    required this.cropSidePx,
  });

  final int frameWidthPx;
  final int frameHeightPx;
  final int cropLeftPx;
  final int cropTopPx;
  final int cropSidePx;

  @override
  bool operator ==(Object other) {
    return other is FocusMeasuredArea &&
        other.frameWidthPx == frameWidthPx &&
        other.frameHeightPx == frameHeightPx &&
        other.cropLeftPx == cropLeftPx &&
        other.cropTopPx == cropTopPx &&
        other.cropSidePx == cropSidePx;
  }

  @override
  int get hashCode => Object.hash(frameWidthPx, frameHeightPx, cropLeftPx, cropTopPx, cropSidePx);
}
