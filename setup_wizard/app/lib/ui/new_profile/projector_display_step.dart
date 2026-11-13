// Written by Claude Code
//
// New-profile step "Projector": the connected displays as cards (ProjectorDisplayChoiceView); clicking one makes it
// the projector. One projector for now; the draft holds a list for setups with several. Next stays disabled until a
// display is chosen, because the calibration steps that follow project onto it.

import 'package:flutter/material.dart';

import '../projectors/projector_display_choice_view.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';
import '../../config/wizard_strings.dart';

class ProjectorDisplayStep extends StatefulWidget {
  const ProjectorDisplayStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.onCanContinueChanged,
  });

  final SetupWizardBackendClient backendClient;

  /// Receives the chosen display in projectorDisplayIds.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed: only with a display chosen.
  final ValueChanged<bool> onCanContinueChanged;

  @override
  State<ProjectorDisplayStep> createState() => _ProjectorDisplayStepState();
}

class _ProjectorDisplayStepState extends State<ProjectorDisplayStep> {
  @override
  void initState() {
    super.initState();
    // Not during build: the wizard rebuilds itself when told.
    WidgetsBinding.instance.addPostFrameCallback((Duration timeStamp) => _reportCanContinue());
  }

  void _reportCanContinue() {
    widget.onCanContinueChanged(widget.newProfileDraft.projectorDisplayIds.isNotEmpty);
  }

  /// Simplification: one projector per profile for now, so choosing a display replaces the earlier choice.
  /// Upgrade for several projectors: toggle the display in projectorDisplayIds instead.
  void _chooseProjectorDisplay(int displayId) {
    setState(() {
      widget.newProfileDraft.projectorDisplayIds = [displayId];
    });
    _reportCanContinue();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(WizardStrings.chooseProjectorDisplayText),
        const SizedBox(height: 8),
        ProjectorDisplayChoiceView(
          backendClient: widget.backendClient,
          chosenDisplayId: widget.newProfileDraft.projectorDisplayIds.firstOrNull,
          onDisplayChosen: _chooseProjectorDisplay,
        ),
      ],
    );
  }
}
