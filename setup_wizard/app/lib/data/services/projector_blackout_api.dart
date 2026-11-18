// Written by Claude Code
//
// The app's calls to the backend's projector blackout (setup_wizard/backend/projectors/projector_blackout_api.py): a black
// fullscreen window on the projector while a calibration step does not need its light.

import 'setup_wizard_backend_client.dart';

extension ProjectorBlackoutApi on SetupWizardBackendClient {
  /// Shows black on the display, or keeps showing it; to be repeated every few seconds, since the backend ends the
  /// window when nobody asks any more. holderId names the screen asking, the same in all its requests.
  Future<ProjectorBlackoutState> keepProjectorBlackout({required int displayId, required String holderId}) async {
    final Map<String, dynamic> stateJson = await sendJson('POST', '/api/projector-blackout/keep', {
      'display_id': displayId,
      'holder_id': holderId,
    }) as Map<String, dynamic>;
    return ProjectorBlackoutState(
      isShown: stateJson['is_shown'] as bool,
      reasonText: stateJson['reason_text'] as String,
    );
  }

  /// Ends the black window, unless another screen has taken it over meanwhile.
  Future<void> stopProjectorBlackout({required String holderId}) async {
    await sendJson('POST', '/api/projector-blackout/stop', {'holder_id': holderId});
  }
}

class ProjectorBlackoutState {
  const ProjectorBlackoutState({required this.isShown, required this.reasonText});

  final bool isShown;

  /// Why it is not shown, e.g. the display is not connected; empty while shown.
  final String reasonText;
}
