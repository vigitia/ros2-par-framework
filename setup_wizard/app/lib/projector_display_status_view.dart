// Written by Claude Code
//
// The profile's projector in the Projectors area: the connected displays as cards with the projector's display
// selected, which says enough while all is well; text appears only for a problem (no projector chosen, or something
// changed since it was chosen). Clicking another card chooses it. The profile stores the choice: the display id, the projector's identity (EDID make, model, serial,
// connector) and the display mode (resolution, refresh rate). Launches find the projector by its identity, so a
// changed display id only needs saving to keep the profile tidy; a changed display mode means the projector
// calibration, measured in projector pixels, may no longer fit. getProjectorWarningTexts is shared with the Overview.

import 'package:flutter/material.dart';

import 'displays_api.dart';
import 'projector_display_choice_view.dart';
import 'setup_wizard_backend_client.dart';

/// Why the stored projector cannot be trusted as it is, one sentence each; empty when all is as chosen.
List<String> getProjectorWarningTexts(ProfileSummary profileSummary) {
  final List<String> warningTexts = [];
  final int? storedDisplayId = profileSummary.storedProjectorDisplayId;
  String projectorNameInSentence = profileSummary.projectorTitleText;
  String projectorNameAtSentenceStart = profileSummary.projectorTitleText;
  if (profileSummary.projectorTitleText.isEmpty) {
    projectorNameInSentence = 'the projector';
    projectorNameAtSentenceStart = 'The projector';
  }
  // What the saved number points to now
  String storedDisplayText = 'Nothing is connected as display $storedDisplayId now.';
  if (profileSummary.storedDisplayTitleText.isNotEmpty) {
    storedDisplayText = 'Display $storedDisplayId is ${profileSummary.storedDisplayTitleText} now.';
  }
  switch (profileSummary.projectorDisplayState) {
    case ProjectorDisplayState.notSet:
    case ProjectorDisplayState.connected:
      break;
    case ProjectorDisplayState.moved:
      warningTexts.add('$projectorNameAtSentenceStart is display ${profileSummary.projectorDisplayId} now, not the '
          'saved display $storedDisplayId: displays were plugged in or out. $storedDisplayText Starting the profile '
          'finds the projector by itself; save the new number to update the profile.');
    case ProjectorDisplayState.notConnected:
      warningTexts.add('$projectorNameAtSentenceStart is not connected. $storedDisplayText Starting the profile with '
          'an app on the projector fails until the projector is connected or another display is chosen.');
    case ProjectorDisplayState.ambiguous:
      warningTexts.add('Several displays look like $projectorNameInSentence, so starting the profile cannot tell '
          'which one it is. Choose the projector below.');
    case ProjectorDisplayState.unidentified:
      warningTexts.add('The profile saves only the display number ($storedDisplayId), not which projector it is, so '
          'a changed number would go unnoticed. $storedDisplayText Choose the projector once below to store it.');
    case ProjectorDisplayState.displaysUnreadable:
      warningTexts.add('The displays could not be read, so the wizard cannot check that display $storedDisplayId is '
          'still the projector.');
  }
  if (profileSummary.isDisplayModeChanged) {
    warningTexts.add('$projectorNameAtSentenceStart runs at ${profileSummary.currentDisplayModeText} now, but was '
        'chosen at ${profileSummary.storedDisplayModeText}. The projector calibration may no longer fit: set the '
        'display back in the desktop\'s display settings, or save the new mode and calibrate the projector again.');
  }
  return warningTexts;
}

class ProjectorDisplayStatusView extends StatefulWidget {
  const ProjectorDisplayStatusView({
    super.key,
    required this.backendClient,
    required this.profileSummary,
    required this.onProjectorDisplayChanged,
  });

  final SetupWizardBackendClient backendClient;
  final ProfileSummary profileSummary;

  /// Called after a display was stored, so the caller reads the profile again.
  final VoidCallback onProjectorDisplayChanged;

  @override
  State<ProjectorDisplayStatusView> createState() => _ProjectorDisplayStatusViewState();
}

class _ProjectorDisplayStatusViewState extends State<ProjectorDisplayStatusView> {
  bool _isSavingDisplay = false;
  String? _saveErrorText;

  /// Raised after each save, so the display cards are read again with the new state.
  int _savedDisplayCount = 0;

  Future<void> _storeProjectorDisplay(int displayId) async {
    setState(() {
      _isSavingDisplay = true;
      _saveErrorText = null;
    });
    String? saveErrorText;
    try {
      await widget.backendClient.setProfileProjectorDisplay(
        profileName: widget.profileSummary.profileName,
        displayId: displayId,
      );
    } catch (error) {
      saveErrorText = describeBackendErrorForUser(error);
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isSavingDisplay = false;
      _saveErrorText = saveErrorText;
      if (saveErrorText == null) {
        _savedDisplayCount += 1;
      }
    });
    if (saveErrorText == null) {
      widget.onProjectorDisplayChanged();
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final ProfileSummary profileSummary = widget.profileSummary;
    final List<Widget> viewRows = [];
    if (profileSummary.projectorDisplayState == ProjectorDisplayState.notSet) {
      viewRows.add(const Text('No projector chosen yet: click its display below.'));
      viewRows.add(const SizedBox(height: 8));
    }
    for (final String warningText in getProjectorWarningTexts(profileSummary)) {
      viewRows.add(ProjectorWarningBox(warningText: warningText));
      viewRows.add(const SizedBox(height: 8));
    }

    // Saving the display the projector is found on now updates the stored id and mode
    final int? foundProjectorDisplayId = profileSummary.projectorDisplayId;
    final bool isMoved = profileSummary.projectorDisplayState == ProjectorDisplayState.moved;
    if (foundProjectorDisplayId != null && (isMoved || profileSummary.isDisplayModeChanged)) {
      VoidCallback? onSavePressed;
      if (!_isSavingDisplay) {
        onSavePressed = () => _storeProjectorDisplay(foundProjectorDisplayId);
      }
      viewRows.add(FilledButton(
        onPressed: onSavePressed,
        child: Text('Save display $foundProjectorDisplayId as it is now'),
      ));
    }

    if (_isSavingDisplay) {
      viewRows.add(const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()));
    }
    final String? saveErrorText = _saveErrorText;
    if (saveErrorText != null) {
      viewRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text('Could not save the projector: $saveErrorText', style: TextStyle(color: colorScheme.error)),
      ));
    }
    viewRows.add(const SizedBox(height: 8));
    viewRows.add(ProjectorDisplayChoiceView(
      key: ValueKey<int>(_savedDisplayCount),
      backendClient: widget.backendClient,
      chosenDisplayId: profileSummary.projectorDisplayId,
      onDisplayChosen: _storeProjectorDisplay,
    ));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: viewRows);
  }
}

/// A warning about the projector on the error colour, with a warning icon.
class ProjectorWarningBox extends StatelessWidget {
  const ProjectorWarningBox({super.key, required this.warningText});

  final String warningText;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.warning_amber_rounded, color: colorScheme.onErrorContainer, semanticLabel: 'Warning'),
          const SizedBox(width: 8),
          Expanded(child: Text(warningText, style: TextStyle(color: colorScheme.onErrorContainer))),
        ],
      ),
    );
  }
}
