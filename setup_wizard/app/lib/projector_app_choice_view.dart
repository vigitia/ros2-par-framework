// Written by Claude Code
//
// Chooses the one app a profile starts on the projector (par_launch.projector_app): none, or one of the installed
// apps, each from its entry in the ament index. A choice is stored in the profile at once and takes effect at the
// profile's next launch. An app with a broken entry is shown but cannot be chosen, since the framework would refuse
// to start it.

import 'package:flutter/material.dart';

import 'apps_api.dart';
import 'setup_wizard_backend_client.dart';

class ProjectorAppChoiceView extends StatefulWidget {
  const ProjectorAppChoiceView({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.storedAppName,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;

  /// The profile's par_launch.projector_app when the view was opened; the view keeps track of later choices itself,
  /// so the overview around it (and a running camera preview there) need not be reloaded.
  final String storedAppName;

  @override
  State<ProjectorAppChoiceView> createState() => _ProjectorAppChoiceViewState();
}

class _ProjectorAppChoiceViewState extends State<ProjectorAppChoiceView> {
  List<ProjectorApp>? _projectorApps;
  String? _appListErrorText;

  /// The choice stored in the profile.
  late String _chosenAppName = widget.storedAppName;

  /// Set while a choice is being stored; the choice is shown at once and the dropdown waits for the answer.
  String? _savingAppName;
  String? _saveErrorText;

  @override
  void initState() {
    super.initState();
    _loadProjectorApps();
  }

  Future<void> _loadProjectorApps() async {
    setState(() {
      _appListErrorText = null;
    });
    try {
      final List<ProjectorApp> projectorApps = await widget.backendClient.fetchProjectorApps();
      if (!mounted) {
        return;
      }
      setState(() {
        _projectorApps = projectorApps;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _appListErrorText = describeBackendErrorForUser(error);
      });
    }
  }

  Future<void> _chooseApp(String appName) async {
    setState(() {
      _savingAppName = appName;
      _saveErrorText = null;
    });
    String? saveErrorText;
    try {
      await widget.backendClient.setProfileProjectorApp(profileName: widget.profileName, appName: appName);
    } catch (error) {
      saveErrorText = describeBackendErrorForUser(error);
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _savingAppName = null;
      _saveErrorText = saveErrorText;
      if (saveErrorText == null) {
        _chosenAppName = appName;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> choiceRows = [
      Text('App on the projector', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        'The one app this profile starts on the projector. Takes effect at the next start of the profile.',
        style: TextStyle(color: colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 8),
    ];
    final String? appListErrorText = _appListErrorText;
    final List<ProjectorApp>? projectorApps = _projectorApps;
    if (appListErrorText != null) {
      choiceRows.add(Text('Cannot list the apps: $appListErrorText', style: TextStyle(color: colorScheme.error)));
      choiceRows.add(TextButton(onPressed: _loadProjectorApps, child: const Text('Retry')));
    } else if (projectorApps == null) {
      choiceRows.add(const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)));
    } else {
      choiceRows.add(_buildAppDropdown(projectorApps));
      final String shownAppName = _savingAppName ?? _chosenAppName;
      final String? shownAppDescription = _findAppDescription(projectorApps, shownAppName);
      if (shownAppDescription != null) {
        choiceRows.add(const SizedBox(height: 8));
        choiceRows.add(Text(shownAppDescription));
      }
    }
    final String? saveErrorText = _saveErrorText;
    if (saveErrorText != null) {
      choiceRows.add(const SizedBox(height: 8));
      choiceRows.add(Text('Could not store the choice: $saveErrorText', style: TextStyle(color: colorScheme.error)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: choiceRows);
  }

  /// A dropdown, since the profile starts only one app. An app with a broken entry is listed but cannot be picked.
  Widget _buildAppDropdown(List<ProjectorApp> projectorApps) {
    final String shownAppName = _savingAppName ?? _chosenAppName;
    final bool isSaving = _savingAppName != null;
    final List<DropdownMenuEntry<String>> appEntries = [
      const DropdownMenuEntry<String>(value: projectorAppNone, label: 'None'),
    ];
    bool isChosenAppInstalled = shownAppName == projectorAppNone;
    for (final ProjectorApp projectorApp in projectorApps) {
      if (projectorApp.appName == shownAppName) {
        isChosenAppInstalled = true;
      }
      final String? entryErrorText = projectorApp.entryErrorText;
      if (entryErrorText == null) {
        appEntries.add(DropdownMenuEntry<String>(value: projectorApp.appName, label: projectorApp.displayName));
      } else {
        appEntries.add(DropdownMenuEntry<String>(
          value: projectorApp.appName,
          label: '${projectorApp.displayName} (cannot be started)',
          enabled: false,
        ));
      }
    }
    if (!isChosenAppInstalled) {
      // E.g. written into the profile by hand, or the app was removed since: shown, so the user sees why the
      // launch would fail
      appEntries.add(DropdownMenuEntry<String>(
        value: shownAppName,
        label: '$shownAppName (not installed)',
        enabled: false,
      ));
    }
    return DropdownMenu<String>(
      // A new key per choice, so the menu shows the stored choice again if saving it failed
      key: ValueKey<String>('$shownAppName-$_saveErrorText'),
      initialSelection: shownAppName,
      dropdownMenuEntries: appEntries,
      enabled: !isSaving,
      requestFocusOnTap: false,
      onSelected: (String? appName) {
        if (appName != null && appName != _chosenAppName) {
          _chooseApp(appName);
        }
      },
    );
  }

  String? _findAppDescription(List<ProjectorApp> projectorApps, String appName) {
    for (final ProjectorApp projectorApp in projectorApps) {
      if (projectorApp.appName == appName && projectorApp.description.isNotEmpty) {
        return projectorApp.description;
      }
    }
    return null;
  }
}
