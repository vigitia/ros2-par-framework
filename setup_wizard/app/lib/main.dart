// Written with the help of Claude Code
//
// Entry point of the PAR setup wizard.

import 'package:flutter/material.dart';

import 'ui/profiles/profile_hub_screen.dart';
import 'data/services/setup_wizard_backend_client.dart';
import 'config/wizard_strings.dart';
import 'config/wizard_colors.dart';

void main() {
  runApp(const SetupWizardApp());
}

class SetupWizardApp extends StatelessWidget {
  const SetupWizardApp({super.key});

  // Co-authored by Claude Code: the theme's seed colour comes from the wizard's colour config
  @override
  Widget build(BuildContext context) {
    // Dark theme by default
    final ThemeData darkTheme = ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: WizardColors.themeSeedColor, brightness: Brightness.dark),
    );
    return MaterialApp(
      title: WizardStrings.appTitle,
      debugShowCheckedModeBanner: false,  // Hide the debug text in the top right corner
      darkTheme: darkTheme,
      themeMode: ThemeMode.dark,
      home: ProfileHubScreen(backendClient: SetupWizardBackendClient()),
    );
  }
}
