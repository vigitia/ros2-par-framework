// Written by Claude Code
//
// Entry point of the PAR setup wizard.

import 'package:flutter/material.dart';

import 'setup_wizard_backend_client.dart';
import 'screens/start_screen.dart';

void main() {
  runApp(const SetupWizardApp());
}

class SetupWizardApp extends StatelessWidget {
  const SetupWizardApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Dark always, not following the desktop: projection setups usually run in dimmed rooms.
    final ThemeData darkTheme = ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo, brightness: Brightness.dark),
    );
    return MaterialApp(
      title: 'ROS 2 PAR Framework',
      darkTheme: darkTheme,
      themeMode: ThemeMode.dark,
      home: SetupWizardStartScreen(backendClient: SetupWizardBackendClient()),
    );
  }
}
