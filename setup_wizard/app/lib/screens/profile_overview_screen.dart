// Written by Claude Code
//
// Hub area "Overview" of a profile: its hardware, every calibration with its state and a button to (re)do it,
// and the profile's apps with a Start button.

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';

class ProfileOverviewScreen extends StatelessWidget {
  const ProfileOverviewScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        'Overview of the hardware setup. Not built yet: see the card "Finish setup wizard UI", "Overview of an existing setup" and its sketch.',
      ),
    );
  }
}
