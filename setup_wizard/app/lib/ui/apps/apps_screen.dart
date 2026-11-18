// Written by Claude Code
//
// Hub area "Apps" of a profile: one tab per app the profile offers (par_launch.apps), "Add app" for the installed
// ones it does not offer yet, and the ones that can be installed (an available one is installed first). A tab shows what the app is and which sensor nodes it needs (they show under Sensor
// nodes while the profile offers it), Disable, which camera each input of the app reads
// (par_launch.app_inputs, chosen here when the profile has several cameras), and the settings of the nodes its
// ament index entry names (settings_node_names), read once from the app and saved into the profile without running it
// (NodeSettingsEditorView). Run (profile_run_view.dart) starts the profile with the shown tab's app on the projector;
// on a tab whose app does not use the projector, or without tabs, it opens the menu to choose one. Disabling the
// profile's projector app leaves the projector without one. An app that does not use the
// projector (RViz) starts with every run of the profile while it has a tab here.

import 'package:flutter/material.dart';

import '../core/ui/addable_tabs_view.dart';
import '../../data/services/apps_api.dart';
import '../../data/services/install_api.dart';
import '../install/offer_picker_dialog.dart';
import '../../data/services/node_settings_api.dart';
import '../core/ui/node_settings_editor_view.dart';
import '../core/ui/profile_run_view.dart';
import '../core/ui/profile_summary_loading.dart';
import '../core/ui/top_aligned_page_content.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';
import '../../config/wizard_icons.dart';

class AppsScreen extends StatefulWidget {
  const AppsScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<AppsScreen> createState() => _AppsScreenState();
}

class _AppsScreenState extends State<AppsScreen> with ProfileSummaryLoading<AppsScreen> {
  List<InstalledApp>? _installedApps;
  String? _appListErrorText;
  bool _isSavingEnabledApps = false;
  String? _enabledAppsErrorText;
  bool _isSavingAppInputs = false;
  String? _appInputsErrorText;

  /// The app whose tab is in front: the one the user brought to the front, or one just added.
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
      final List<InstalledApp> installedApps = await widget.backendClient.fetchInstalledApps();
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

  /// Stores that inputName of appName reads cameraName, keeping the app's other bindings.
  Future<void> _saveAppInput(String appName, String inputName, String cameraName) async {
    final ProfileSummary? profileSummary = getShownProfileSummary();
    if (profileSummary == null) {
      return;
    }
    final Map<String, String> cameraNameByInput = Map<String, String>.of(
      profileSummary.cameraNameByInputByApp[appName] ?? <String, String>{},
    );
    cameraNameByInput[inputName] = cameraName;
    setState(() {
      _isSavingAppInputs = true;
      _appInputsErrorText = null;
    });
    try {
      await widget.backendClient.setProfileAppInputs(
        profileName: widget.profileName,
        appName: appName,
        cameraNameByInput: cameraNameByInput,
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _appInputsErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
          _isSavingAppInputs = false;
        });
      }
      return;
    }
    await loadProfileSummary(widget.backendClient, widget.profileName, isSpinnerShown: false);
    if (mounted) {
      setState(() {
        _isSavingAppInputs = false;
      });
    }
  }

  InstalledApp? _findInstalledApp(String appName) {
    for (final InstalledApp installedApp in _installedApps ?? <InstalledApp>[]) {
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
    final List<InstalledApp>? installedApps = _installedApps;
    if (appListErrorText != null) {
      return TopAlignedPageContent(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              WizardStrings.getAppListErrorText(appListErrorText: appListErrorText),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            TextButton(onPressed: _loadInstalledApps, child: const Text(WizardStrings.tryAgainButtonLabel)),
          ],
        ),
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
    String noTabsText = WizardStrings.noAppInProfileText;
    if (installedApps.isEmpty) {
      noTabsText = WizardStrings.noAppInstalledText;
    }
    // A Scaffold of its own, so the Run button floats in this area's bottom right corner
    return Scaffold(
      floatingActionButton: ProfileRunView(
        backendClient: widget.backendClient,
        profileName: widget.profileName,
        appToRunDirectly: _findAppToRunDirectly(enabledAppNames),
      ),
      body: AddableTabsView(
        tabTitles: tabTitles,
        shownTabTitle: shownTabTitle,
        addButtonText: WizardStrings.addAppButtonLabel,
        addMenuEntries: const [],
        onAddPressed: _isSavingEnabledApps ? null : () => _chooseAndAddApp(enabledAppNames),
        onShownTabChanged: (int tabIndex) => setState(() => _shownTabAppName = enabledAppNames[tabIndex]),
        noTabsText: noTabsText,
        buildTabContent: (int tabIndex, bool isShownTab) => _buildAppTab(enabledAppNames[tabIndex], enabledAppNames),
      ),
    );
  }

  /// The app of the tab in front when Run can start it directly: installed, on the projector and with a valid entry.
  /// Null otherwise, so Run opens its menu.
  InstalledApp? _findAppToRunDirectly(List<String> enabledAppNames) {
    if (enabledAppNames.isEmpty) {
      return null;
    }
    // The tab view keeps the tab in front while it exists and falls back to the first one otherwise
    String appNameInFront = enabledAppNames.first;
    final String? shownTabAppName = _shownTabAppName;
    if (shownTabAppName != null && enabledAppNames.contains(shownTabAppName)) {
      appNameInFront = shownTabAppName;
    }
    final InstalledApp? appInFront = _findInstalledApp(appNameInFront);
    if (appInFront == null || !appInFront.usesProjector || appInFront.entryErrorText != null) {
      return null;
    }
    return appInFront;
  }

  /// Lists installed and available apps (OfferPickerDialog); an available one is
  /// installed first. The chosen app is added to the profile and comes to the front.
  Future<void> _chooseAndAddApp(List<String> enabledAppNames) async {
    final Map<String, String> blockedTextByAppName = {};
    for (final String enabledAppName in enabledAppNames) {
      blockedTextByAppName[enabledAppName] = WizardStrings.offerInProfileText;
    }
    // A broken entry cannot be started
    for (final InstalledApp installedApp in _installedApps ?? <InstalledApp>[]) {
      final String? entryErrorText = installedApp.entryErrorText;
      if (entryErrorText != null) {
        blockedTextByAppName[installedApp.appName] = entryErrorText;
      }
    }
    final CatalogOffer? chosenOffer = await showOfferPickerDialog(
      context: context,
      backendClient: widget.backendClient,
      offerKind: offerKindApp,
      dialogTitle: WizardStrings.chooseAppDialogTitle,
      blockedTextByOfferName: blockedTextByAppName,
    );
    if (chosenOffer == null || !mounted) {
      return;
    }
    // An app installed just now is not in the list read before
    await _loadInstalledApps();
    final InstalledApp? chosenApp = _findInstalledApp(chosenOffer.name);
    if (chosenApp == null || chosenApp.entryErrorText != null) {
      if (mounted) {
        setState(() {
          _enabledAppsErrorText = chosenApp?.entryErrorText ?? WizardStrings.appNotInstalledText;
        });
      }
      return;
    }
    await _saveEnabledApps([...enabledAppNames, chosenApp.appName], addedAppName: chosenApp.appName);
  }

  Widget _buildAppTab(String appName, List<String> enabledAppNames) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final InstalledApp? installedApp = _findInstalledApp(appName);
    String descriptionText = WizardStrings.appNotInstalledText;
    if (installedApp != null) {
      descriptionText = installedApp.description;
    }
    String disableTooltipText = WizardStrings.disableAppOfferTooltip;
    if (installedApp != null && !installedApp.usesProjector) {
      disableTooltipText = WizardStrings.disableAppStartTooltip;
    }
    VoidCallback? onDisableClicked;
    if (!_isSavingEnabledApps) {
      onDisableClicked = () {
        final List<String> remainingAppNames = List<String>.of(enabledAppNames)..remove(appName);
        _saveEnabledApps(remainingAppNames);
      };
    }
    final List<String> descriptionParts = [descriptionText];
    if (installedApp != null && installedApp.requiredSensorNodeDisplayNames.isNotEmpty) {
      descriptionParts.add(WizardStrings.getAppRequiredSensorNodesText(
        requiredSensorNodeNames: installedApp.requiredSensorNodeDisplayNames,
      ));
    }
    final List<Widget> tabRows = [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: Text(descriptionParts.join(' '), style: mutedTextStyle)),
        const SizedBox(width: 12),
        Tooltip(
          message: disableTooltipText,
          child: OutlinedButton.icon(
            onPressed: onDisableClicked,
            icon: const Icon(WizardIcons.disableButtonIcon),
            label: const Text(WizardStrings.disableButtonLabel),
          ),
        ),
      ]),
    ];
    final String? enabledAppsErrorText = _enabledAppsErrorText;
    if (enabledAppsErrorText != null) {
      tabRows.add(Text(enabledAppsErrorText, style: TextStyle(color: colorScheme.error)));
    }
    tabRows.add(const SizedBox(height: 16));
    if (installedApp != null && installedApp.entryErrorText == null && installedApp.inputNames.isNotEmpty) {
      tabRows.addAll(_buildAppInputRows(installedApp));
      tabRows.add(const SizedBox(height: 16));
    }
    final String? entryErrorText = installedApp?.entryErrorText;
    if (entryErrorText != null) {
      tabRows.add(
        Text(
          WizardStrings.getAppEntryErrorText(entryErrorText: entryErrorText),
          style: TextStyle(color: colorScheme.error),
        ),
      );
    } else if (installedApp != null && !installedApp.usesProjector) {
      // Not a PAR app, so it has no entry that could name settings
    } else if (installedApp != null && installedApp.settingsNodeNames.isEmpty) {
      tabRows.add(Text(WizardStrings.appWithoutSettingsText, style: mutedTextStyle));
    } else if (installedApp != null) {
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

  /// Which camera each input of the app reads: a choice per input when the profile has several cameras.
  List<Widget> _buildAppInputRows(InstalledApp installedApp) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final List<String> cameraNames = [];
    for (final CameraCalibrationSummary camera in getShownProfileSummary()?.cameras ?? <CameraCalibrationSummary>[]) {
      cameraNames.add(camera.cameraName);
    }
    final Map<String, String> cameraNameByInput =
        getShownProfileSummary()?.cameraNameByInputByApp[installedApp.appName] ?? <String, String>{};
    final List<Widget> inputRows = [
      Text(WizardStrings.appCamerasHeading, style: Theme.of(context).textTheme.titleMedium),
    ];
    // With one camera every input reads it, so there is nothing to choose
    if (cameraNames.length == 1) {
      inputRows.add(Text(WizardStrings.getAppSingleCameraText(cameraName: cameraNames.first), style: mutedTextStyle));
      return inputRows;
    }
    inputRows.add(Text(WizardStrings.appInputCameraChoiceText, style: mutedTextStyle));
    bool hasUnboundInput = false;
    for (final String inputName in installedApp.inputNames) {
      String? boundCameraName = cameraNameByInput[inputName];
      // A binding to a camera the profile no longer has counts as unbound
      if (boundCameraName != null && !cameraNames.contains(boundCameraName)) {
        boundCameraName = null;
      }
      if (boundCameraName == null) {
        hasUnboundInput = true;
      }
      final List<DropdownMenuItem<String>> cameraItems = [];
      for (final String cameraName in cameraNames) {
        cameraItems.add(DropdownMenuItem<String>(value: cameraName, child: Text(cameraName)));
      }
      ValueChanged<String?>? onCameraChosen;
      if (!_isSavingAppInputs) {
        onCameraChosen = (String? cameraName) {
          if (cameraName != null && cameraName != boundCameraName) {
            _saveAppInput(installedApp.appName, inputName, cameraName);
          }
        };
      }
      inputRows.add(const SizedBox(height: 8));
      inputRows.add(Row(children: [
        SizedBox(width: 160, child: Text(inputName)),
        DropdownButton<String>(
          value: boundCameraName,
          hint: const Text(WizardStrings.chooseCameraHint),
          items: cameraItems,
          onChanged: onCameraChosen,
        ),
      ]));
    }
    if (hasUnboundInput) {
      inputRows.add(const SizedBox(height: 8));
      inputRows.add(Text(
        WizardStrings.appInputWithoutCameraText,
        style: TextStyle(color: colorScheme.error),
      ));
    }
    final String? appInputsErrorText = _appInputsErrorText;
    if (appInputsErrorText != null) {
      inputRows.add(const SizedBox(height: 8));
      inputRows.add(Text(appInputsErrorText, style: TextStyle(color: colorScheme.error)));
    }
    return inputRows;
  }
}
