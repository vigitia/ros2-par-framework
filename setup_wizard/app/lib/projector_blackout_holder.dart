// Written by Claude Code
//
// Keeps the projector black while shown, and says so in one line: for calibration steps that do not need the
// projector, so its light does not disturb the camera image (e.g. glare on a checkerboard). Leaving the screen ends
// the blackout; the backend also ends it on its own once the requests stop.

import 'package:flutter/material.dart';

import 'projector_blackout_api.dart';
import 'setup_wizard_backend_client.dart';

/// Pause between the answer to one blackout request and the next request; the backend ends the blackout after a few
/// seconds without a request, so this pause plus the longest request (backendRequestTimeout) must stay below that.
const Duration projectorBlackoutKeepInterval = Duration(seconds: 2);

class ProjectorBlackoutHolder extends StatefulWidget {
  const ProjectorBlackoutHolder({super.key, required this.backendClient, required this.projectorDisplayId});

  final SetupWizardBackendClient backendClient;

  /// The projector's display (the framework's display_id); null when no projector was chosen, then nothing shows.
  final int? projectorDisplayId;

  @override
  State<ProjectorBlackoutHolder> createState() => _ProjectorBlackoutHolderState();
}

class _ProjectorBlackoutHolderState extends State<ProjectorBlackoutHolder> {
  /// Names this screen in the backend, so its late stop does not end a blackout the next screen holds.
  final String _holderId = 'blackout_${DateTime.now().microsecondsSinceEpoch}';
  ProjectorBlackoutState? _blackoutState;
  String? _blackoutErrorText;

  @override
  void initState() {
    super.initState();
    _keepBlackoutWhileShown();
  }

  @override
  void dispose() {
    widget.backendClient.stopProjectorBlackout(holderId: _holderId).catchError((Object error) {
      // The backend may already be gone; its watchdog ends the window then.
    });
    super.dispose();
  }

  /// Asks for the blackout again and again until the screen is gone; one request at a time.
  Future<void> _keepBlackoutWhileShown() async {
    while (mounted) {
      await _keepBlackout();
      await Future<void>.delayed(projectorBlackoutKeepInterval);
    }
  }

  Future<void> _keepBlackout() async {
    final int? projectorDisplayId = widget.projectorDisplayId;
    if (projectorDisplayId == null) {
      return;
    }
    try {
      final ProjectorBlackoutState blackoutState =
          await widget.backendClient.keepProjectorBlackout(displayId: projectorDisplayId, holderId: _holderId);
      if (!mounted) {
        return;
      }
      setState(() {
        _blackoutState = blackoutState;
        _blackoutErrorText = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _blackoutErrorText = describeBackendErrorForUser(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final int? projectorDisplayId = widget.projectorDisplayId;
    if (projectorDisplayId == null) {
      return const SizedBox.shrink();
    }
    final Color mutedColor = Theme.of(context).colorScheme.onSurfaceVariant;
    String blackoutText = 'Switching the projector (display $projectorDisplayId) to black …';
    final ProjectorBlackoutState? blackoutState = _blackoutState;
    final String? blackoutErrorText = _blackoutErrorText;
    if (blackoutErrorText != null) {
      blackoutText = 'Could not switch the projector to black: $blackoutErrorText';
    } else if (blackoutState != null && blackoutState.isShown) {
      blackoutText = 'The projector (display $projectorDisplayId) shows black during this step, so its light does '
          'not disturb the camera image.';
    } else if (blackoutState != null) {
      blackoutText = 'The projector is not switched to black: ${blackoutState.reasonText}';
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(Icons.dark_mode_outlined, size: 18, color: mutedColor),
          const SizedBox(width: 8),
          Expanded(child: Text(blackoutText, style: TextStyle(color: mutedColor))),
        ],
      ),
    );
  }
}
