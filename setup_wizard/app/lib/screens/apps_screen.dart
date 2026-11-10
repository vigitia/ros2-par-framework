// Written by Claude Code
//
// Hub area "Apps" of a profile: one tab per app the profile offers (par_launch.apps), "Add app" for the installed
// ones it does not offer yet. A tab shows what the app is, Disable, and the settings of the nodes its ament index
// entry names (settings_node_names), read once from the app and saved into the profile without running it
// (NodeSettingsEditorView). Which of the profile's apps goes on the projector is chosen in the Run menu
// (profile_run_view.dart); disabling that app leaves the projector without one. The Store area is for apps that are
// not installed yet.

import 'package:flutter/material.dart';

import '../addable_tabs_view.dart';
import '../apps_api.dart';
import '../node_settings_api.dart';
import '../node_settings_editor_view.dart';
import '../profile_run_view.dart';
import '../profile_summary_loading.dart';
import '../top_aligned_page_content.dart';
import '../setup_wizard_backend_client.dart';

class AppsScreen extends StatefulWidget {
  const AppsScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<AppsScreen> createState() => _AppsScreenState();
}

class _AppsScreenState extends State<AppsScreen> with ProfileSummaryLoading<AppsScreen> {
  List<ProjectorApp>? _installedApps;
  String? _appListErrorText;
  bool _isSavingEnabledApps = false;
  String? _enabledAppsErrorText;

  /// The app whose tab comes to the front when the tabs change, e.g. one just added.
  String? _shownTabAppName;

  @override
  void initState() {
    super.initState();
    _loadProfileAndApps();
  }

  Future<void> _loadProfileAndApps() async {
    await loadProfileSummary(widget.backendClient, widget.profileName);
    await _loadInstalledApps();
  }

  Future<void> _loadInstalledApps() async {
    try {
      final List<ProjectorApp> installedApps = await widget.backendClient.fetchProjectorApps();
      if (!mounted) {
        return;
      }
      setState(() {
        _installedApps = installedApps;
        _appListErrorText = null;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _appListErrorText = describeBackendErrorForUser(error);
        });
      }
    }
  }

  /// Stores the profile's apps; an added one comes to the front as its tab.
  Future<void> _saveEnabledApps(List<String> enabledAppNames, {String? addedAppName}) async {
    setState(() {
      _isSavingEnabledApps = true;
      _enabledAppsErrorText = null;
      if (addedAppName != null) {
        _shownTabAppName = addedAppName;
      }
    });
    try {
      await widget.backendClient.setProfileEnabledApps(profileName: widget.profileName, appNames: enabledAppNames);
    } catch (error) {
      if (mounted) {
        setState(() {
          _enabledAppsErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
          _isSavingEnabledApps = false;
        });
      }
      return;
    }
    await loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: false);
    if (mounted) {
      setState(() {
        _isSavingEnabledApps = false;
      });
    }
  }

  ProjectorApp? _findInstalledApp(String appName) {
    for (final ProjectorApp installedApp in _installedApps ?? <ProjectorApp>[]) {
      if (installedApp.appName == appName) {
        return installedApp;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary == null) {
      return buildProfileLoadStateView(onRetryClicked: _loadProfileAndApps);
    }
    final String? appListErrorText = _appListErrorText;
    final List<ProjectorApp>? installedApps = _installedApps;
    if (appListErrorText != null) {
      return TopAlignedPageContent(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Cannot list the apps: $appListErrorText', style: TextStyle(color: Theme.of(context).colorScheme.error)),
          TextButton(onPressed: _loadInstalledApps, child: const Text('Try again')),
        ]),
      );
    }
    if (installedApps == null) {
      return const TopAlignedPageContent(child: CircularProgressIndicator());
    }

    final List<String> enabledAppNames = profileSummary.enabledAppNames;
    final List<String> tabTitles = [];
    String? shownTabTitle;
    for (final String enabledAppName in enabledAppNames) {
      // An app the profile names but that is not installed (any more) keeps its tab, to be disabled there
      final String tabTitle = _findInstalledApp(enabledAppName)?.displayName ?? enabledAppName;
      tabTitles.add(tabTitle);
      if (enabledAppName == _shownTabAppName) {
        shownTabTitle = tabTitle;
      }
    }
    String noTabsText = 'The profile offers no app. Add one with "Add app"; the Run menu then offers it.';
    if (installedApps.isEmpty) {
      noTabsText = 'No app is installed. The Store will offer them; for now add their repos to config/nodes.list and '
          'run ./scripts/local_build.sh.';
    }
    return AddableTabsView(
      tabTitles: tabTitles,
      shownTabTitle: shownTabTitle,
      addButtonText: 'Add app',
      addMenuEntries: _buildAddMenuEntries(installedApps, enabledAppNames),
      noTabsText: noTabsText,
      buildTabContent: (int tabIndex, bool isShownTab) => _buildAppTab(enabledAppNames[tabIndex], enabledAppNames),
    );
  }

  List<Widget> _buildAddMenuEntries(List<ProjectorApp> installedApps, List<String> enabledAppNames) {
    final List<Widget> addMenuEntries = [];
    for (final ProjectorApp installedApp in installedApps) {
      if (enabledAppNames.contains(installedApp.appName)) {
        continue;
      }
      // A broken entry cannot be started
      VoidCallback? onPressed;
      if (installedApp.entryErrorText == null && !_isSavingEnabledApps) {
        onPressed = () => _saveEnabledApps([...enabledAppNames, installedApp.appName], addedAppName: installedApp.appName);
      }
      addMenuEntries.add(MenuItemButton(onPressed: onPressed, child: Text(installedApp.displayName)));
    }
    return addMenuEntries;
  }

  Widget _buildAppTab(String appName, List<String> enabledAppNames) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final ProjectorApp? installedApp = _findInstalledApp(appName);
    String descriptionText = 'Not installed (any more): disable it, or install it again.';
    if (installedApp != null) {
      descriptionText = installedApp.description;
    }
    VoidCallback? onDisableClicked;
    if (!_isSavingEnabledApps) {
      onDisableClicked = () {
        final List<String> remainingAppNames = List<String>.of(enabledAppNames)..remove(appName);
        _saveEnabledApps(remainingAppNames);
      };
    }
    final List<Widget> tabRows = [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: Text(descriptionText, style: mutedTextStyle)),
        const SizedBox(width: 12),
        Tooltip(
          message: 'The profile no longer offers this app in the Run menu.',
          child: OutlinedButton.icon(
            onPressed: onDisableClicked,
            icon: const Icon(Icons.remove_circle_outline),
            label: const Text('Disable'),
          ),
        ),
      ]),
    ];
    final String? enabledAppsErrorText = _enabledAppsErrorText;
    if (enabledAppsErrorText != null) {
      tabRows.add(Text(enabledAppsErrorText, style: TextStyle(color: colorScheme.error)));
    }
    tabRows.add(const SizedBox(height: 16));
    final String? entryErrorText = installedApp?.entryErrorText;
    if (entryErrorText != null) {
      tabRows.add(Text('Its entry cannot be used: $entryErrorText', style: TextStyle(color: colorScheme.error)));
    } else if (installedApp != null && installedApp.settingsNodeNames.isEmpty) {
      tabRows.add(Text('This app declares no settings (settings_node_names in its entry).', style: mutedTextStyle));
    } else if (installedApp != null) {
      // Simplification: reading starts the app as it would run, see node_settings_api.py
      tabRows.add(Text(
        'Reading the settings the first time starts the app for a moment; it may show its window meanwhile.',
        style: mutedTextStyle,
      ));
      for (final String settingsNodeName in installedApp.settingsNodeNames) {
        tabRows.add(const SizedBox(height: 12));
        tabRows.add(NodeSettingsEditorView(
          backendClient: widget.backendClient,
          profileName: widget.profileName,
          nodeKind: SettingsNodeKind.app,
          packageName: appName,
          fullNodeName: settingsNodeName,
        ));
      }
    }
    return SingleChildScrollView(
      // Room below the content, so the hub's Run button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 16, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: tabRows),
    );
  }
}
