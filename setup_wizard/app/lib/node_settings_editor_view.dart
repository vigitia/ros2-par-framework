// Written by Claude Code
//
// The settings (ROS parameters) of one sensor node or app node, each saved into the profile as soon as it is changed
// (the node reads it at its next start). The backend reads a node's settings once by starting it alone for a moment
// and caches them, so no camera, profile or projector has to run; the first request waits for that. "Read again"
// asks the backend to read the node anew, e.g. after its code changed. Shared by the Sensor nodes and the Apps
// areas.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'node_settings_api.dart';
import 'setting_row_view.dart';
import 'setup_wizard_backend_client.dart';

/// Pause before asking again while the backend still reads a node's settings.
const Duration nodeSettingsRetryInterval = Duration(seconds: 2);

class NodeSettingsEditorView extends StatefulWidget {
  const NodeSettingsEditorView({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.nodeKind,
    required this.packageName,
    required this.fullNodeName,
    this.onSettingsSaved,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;
  final SettingsNodeKind nodeKind;
  final String packageName;

  /// The node's name with its namespace, e.g. /fiducials_detector_node.
  final String fullNodeName;

  /// Called after a change was stored, e.g. to start a running debug run of the node again with it.
  final VoidCallback? onSettingsSaved;

  @override
  State<NodeSettingsEditorView> createState() => _NodeSettingsEditorViewState();
}

class _NodeSettingsEditorViewState extends State<NodeSettingsEditorView> {
  List<NodeSetting>? _nodeSettings;
  String? _settingsErrorText;
  Timer? _settingsRetryTimer;

  /// Values on their way into the profile, shown until the stored ones are read back; null resets to the default.
  final Map<String, Object?> _savingValueByName = {};

  /// Why saving a setting failed, by setting name.
  final Map<String, String> _saveErrorTextByName = {};

  @override
  void initState() {
    super.initState();
    _loadNodeSettings();
  }

  @override
  void dispose() {
    _settingsRetryTimer?.cancel();
    super.dispose();
  }

  /// Asks until the backend has read the node; the first read starts the node for a moment.
  Future<void> _loadNodeSettings() async {
    _settingsRetryTimer?.cancel();
    try {
      final List<NodeSetting>? nodeSettings = await widget.backendClient.fetchNodeSettings(
        profileName: widget.profileName,
        nodeKind: widget.nodeKind,
        packageName: widget.packageName,
        fullNodeName: widget.fullNodeName,
      );
      if (!mounted) {
        return;
      }
      if (nodeSettings == null) {
        _settingsRetryTimer = Timer(nodeSettingsRetryInterval, _loadNodeSettings);
        return;
      }
      setState(() {
        _nodeSettings = nodeSettings;
        _settingsErrorText = null;
      });
    } catch (error) {
      // A failed read stays failed until "Read again", so asking once more would not help
      if (mounted) {
        setState(() {
          _settingsErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
        });
      }
    }
  }

  Future<void> _readNodeAgain() async {
    setState(() {
      _nodeSettings = null;
      _settingsErrorText = null;
      _savingValueByName.clear();
      _saveErrorTextByName.clear();
    });
    try {
      await widget.backendClient.refreshNodeSettings(nodeKind: widget.nodeKind, packageName: widget.packageName);
    } catch (error) {
      if (mounted) {
        setState(() {
          _settingsErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
        });
      }
      return;
    }
    await _loadNodeSettings();
  }

  /// Saves one setting into the profile; settingValue null resets it to its default.
  Future<void> _saveSetting(String settingName, Object? settingValue) async {
    setState(() {
      _savingValueByName[settingName] = settingValue;
      _saveErrorTextByName.remove(settingName);
    });
    try {
      await widget.backendClient.saveNodeSettings(
        profileName: widget.profileName,
        nodeKind: widget.nodeKind,
        packageName: widget.packageName,
        fullNodeName: widget.fullNodeName,
        settingValueByName: {settingName: settingValue},
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _savingValueByName.remove(settingName);
          _saveErrorTextByName[settingName] = describeBackendErrorForUser(error, isBackendDetailShown: true);
        });
      }
      return;
    }
    // Shows the value as the profile now stores it
    await _loadNodeSettings();
    if (!mounted) {
      return;
    }
    setState(() {
      _savingValueByName.remove(settingName);
    });
    widget.onSettingsSaved?.call();
  }

  /// A value on its way into the profile (a reset shows the default), else the profile's value.
  Object? _getShownValue(NodeSetting nodeSetting) {
    if (!_savingValueByName.containsKey(nodeSetting.settingName)) {
      return nodeSetting.settingValue;
    }
    return _savingValueByName[nodeSetting.settingName] ?? nodeSetting.defaultValue;
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final List<NodeSetting>? nodeSettings = _nodeSettings;
    final List<Widget> settingsRows = [
      Row(children: [
        Expanded(child: Text('Settings of ${widget.fullNodeName}', style: Theme.of(context).textTheme.titleSmall)),
        TextButton(onPressed: _readNodeAgain, child: const Text('Read again')),
      ]),
    ];
    final String? settingsErrorText = _settingsErrorText;
    if (settingsErrorText != null) {
      settingsRows.add(SelectableText(settingsErrorText, style: TextStyle(color: colorScheme.error)));
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: settingsRows);
    }
    if (nodeSettings == null) {
      settingsRows.add(const LinearProgressIndicator());
      // Simplification: reading starts an app as it would run, see node_settings_api.py
      String readingText = 'Reading the settings: the node starts once for a moment …';
      if (widget.nodeKind == SettingsNodeKind.app) {
        readingText = 'Reading the settings: the app starts once for a moment and may show its window meanwhile …';
      }
      settingsRows.add(Text(readingText, style: mutedTextStyle));
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: settingsRows);
    }
    if (nodeSettings.isEmpty) {
      settingsRows.add(Text('The node reports no settings.', style: mutedTextStyle));
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: settingsRows);
    }
    settingsRows.add(Text(
      'Changes are saved in the profile right away; the node reads them when it starts next.',
      style: mutedTextStyle,
    ));
    for (final NodeSetting nodeSetting in nodeSettings) {
      final String settingName = nodeSetting.settingName;
      // read_only means "not changed while running"; the node reads a saved value at its next start
      settingsRows.add(SettingRowView(
        key: ValueKey<String>(settingName),
        nodeSetting: nodeSetting,
        shownValue: _getShownValue(nodeSetting),
        isEditable: true,
        errorText: _saveErrorTextByName[settingName],
        onSettingChanged: _saveSetting,
        onResetToDefault: () => _saveSetting(settingName, null),
      ));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: settingsRows);
  }
}
