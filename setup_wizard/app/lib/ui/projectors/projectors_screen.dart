// Written by Claude Code
//
// Hub area "Projectors" of a profile: its projector, warnings when it changed since it was chosen, and the connected
// displays with the projector's selected (ProjectorDisplayStatusView). The projector's calibration belongs to a
// camera (its projection mapping), so it stays in the Cameras area.

import 'package:flutter/material.dart';

import '../core/ui/profile_run_view.dart';
import 'projector_display_status_view.dart';
import '../core/ui/profile_summary_loading.dart';
import '../../data/services/setup_wizard_backend_client.dart';

class ProjectorsScreen extends StatefulWidget {
  const ProjectorsScreen({
    super.key,
    required this.backendClient,
    required this.profileName,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<ProjectorsScreen> createState() => _ProjectorsScreenState();
}

class _ProjectorsScreenState extends State<ProjectorsScreen> with ProfileSummaryLoading<ProjectorsScreen> {
  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> _loadProfile({bool isSpinnerShown = true}) {
    return loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: isSpinnerShown);
  }

  @override
  Widget build(BuildContext context) {
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary == null) {
      return buildProfileLoadStateView(onRetryClicked: _loadProfile);
    }

    return SingleChildScrollView(
      // Room below the content, so the hub's Run button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 24, 24, runButtonClearanceLogicalPx),
      // The page's full width, so the scroll bar sits at the window's right edge however narrow the content is
      child: SizedBox(
        width: double.infinity,
        child: ProjectorDisplayStatusView(
          backendClient: widget.backendClient,
          profileSummary: profileSummary,
          onProjectorDisplayChanged: () => _loadProfile(isSpinnerShown: false),
        ),
      ),
    );
  }
}
