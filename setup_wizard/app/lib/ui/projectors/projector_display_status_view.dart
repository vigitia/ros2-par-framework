// Written by Claude Code
//
// The profile's projector in the Projectors area: the connected displays as cards with the projector's display
// selected, which says enough while all is well; text appears only for a problem (no projector chosen, or something
// changed since it was chosen). Clicking another card chooses it. The profile stores the choice: the display id, the projector's identity (EDID make, model, serial,
// connector) and the display mode (resolution, refresh rate). Launches find the projector by its identity, so a
// changed display id only needs saving to keep the profile tidy; a changed display mode means the projector
// calibration, measured in projector pixels, may no longer fit. getProjectorWarningTexts is shared with the Overview.

import 'package:flutter/material.dart';

import '../../data/services/displays_api.dart';
import 'projector_display_choice_view.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';

/// Why the stored projector cannot be trusted as it is, one sentence each; empty when all is as chosen.
List<String> getProjectorWarningTexts(ProfileSummary profileSummary) {
  final List<String> warningTexts = [];
  final int? storedDisplayId = profileSummary.storedProjectorDisplayId;
  String projectorNameInSentence = profileSummary.projectorTitleText;
  String projectorNameAtSentenceStart = profileSummary.projectorTitleText;
  if (profileSummary.projectorTitleText.isEmpty) {
    projectorNameInSentence = WizardStrings.projectorInSentenceText;
    projectorNameAtSentenceStart = WizardStrings.projectorAtSentenceStartText;
  }
  // What the saved number points to now
  String storedDisplayText = WizardStrings.getNothingOnStoredDisplayText(storedDisplayId: storedDisplayId);
  if (profileSummary.storedDisplayTitleText.isNotEmpty) {
    storedDisplayText = WizardStrings.getStoredDisplayNowText(
      storedDisplayId: storedDisplayId,
      storedDisplayTitleText: profileSummary.storedDisplayTitleText,
    );
  }
  switch (profileSummary.projectorDisplayState) {
    case ProjectorDisplayState.notSet:
    case ProjectorDisplayState.connected:
      break;
    case ProjectorDisplayState.moved:
      warningTexts.add(
        WizardStrings.getProjectorDisplayMovedText(
          projectorNameAtSentenceStart: projectorNameAtSentenceStart,
          projectorDisplayId: profileSummary.projectorDisplayId,
          storedDisplayId: storedDisplayId,
          storedDisplayText: storedDisplayText,
        ),
      );
    case ProjectorDisplayState.notConnected:
      warningTexts.add(
        WizardStrings.getProjectorNotConnectedText(
          projectorNameAtSentenceStart: projectorNameAtSentenceStart,
          storedDisplayText: storedDisplayText,
        ),
      );
    case ProjectorDisplayState.ambiguous:
      warningTexts.add(WizardStrings.getProjectorAmbiguousText(projectorNameInSentence: projectorNameInSentence));
    case ProjectorDisplayState.unidentified:
      warningTexts.add(
        WizardStrings.getProjectorNotIdentifiedText(
          storedDisplayId: storedDisplayId,
          storedDisplayText: storedDisplayText,
        ),
      );
    case ProjectorDisplayState.displaysUnreadable:
      warningTexts.add(WizardStrings.getDisplaysUnreadableText(storedDisplayId: storedDisplayId));
  }
  if (profileSummary.isDisplayModeChanged) {
    warningTexts.add(
      WizardStrings.getDisplayModeChangedText(
        projectorNameAtSentenceStart: projectorNameAtSentenceStart,
        currentDisplayModeText: profileSummary.currentDisplayModeText,
        storedDisplayModeText: profileSummary.storedDisplayModeText,
      ),
    );
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
      viewRows.add(const Text(WizardStrings.noProjectorChosenText));
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
        child: Text(WizardStrings.getSaveProjectorDisplayButtonLabel(foundProjectorDisplayId: foundProjectorDisplayId)),
      ));
    }

    if (_isSavingDisplay) {
      viewRows.add(const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()));
    }
    final String? saveErrorText = _saveErrorText;
    if (saveErrorText != null) {
      viewRows.add(
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            WizardStrings.getSaveProjectorErrorText(saveErrorText: saveErrorText),
            style: TextStyle(color: colorScheme.error),
          ),
        ),
      );
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
          Icon(
            Icons.warning_amber_rounded,
            color: colorScheme.onErrorContainer,
            semanticLabel: WizardStrings.warningIconSemanticLabel,
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(warningText, style: TextStyle(color: colorScheme.onErrorContainer))),
        ],
      ),
    );
  }
}
