// Written by Claude Code
//
// Hub area "Store": all known apps with their requirements, installed or not, installed with a click.

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';

class AppStoreScreen extends StatelessWidget {
  const AppStoreScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        'App store. Not built yet, and blocked: what an app is and the catalog format are still open on the card "Finish setup wizard UI".',
      ),
    );
  }
}
