// Written by Claude Code
//
// Hub area "Store": the portal for installing what a setup does not have yet: camera nodes (drivers), sensor
// processing nodes and apps, each with its requirements, installed with a click. Installed apps are set up in the
// Apps area.

import 'package:flutter/material.dart';

import '../top_aligned_page_content.dart';
import '../setup_wizard_backend_client.dart';

class AppStoreScreen extends StatelessWidget {
  const AppStoreScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  Widget build(BuildContext context) {
    return const TopAlignedPageContent(
      child: Text(
        'Store for new camera nodes, sensor nodes and apps. Not built yet: the catalog of what can be installed '
        'is still open (card "Setup Wizard").',
      ),
    );
  }
}
