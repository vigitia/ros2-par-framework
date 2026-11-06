// Written by Claude Code
//
// Hub area "Running": the table map with the detected pages and their apps, the running apps, their nodes'
// health and a log.

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';

class RunningAppsScreen extends StatelessWidget {
  const RunningAppsScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        'Running apps. Not built yet: see the card "Finish setup wizard UI", the Running sketch; starting apps depends on the open app catalog decision.',
      ),
    );
  }
}
