// Written by Claude Code
//
// Hub area "Sensor nodes" of a profile: which sensor processing nodes the profile starts, and their settings.
// The nodes are the ones installed (registered in the ament index); a node's required nodes are selected along
// with it. "Start" runs the profile's camera with the selected nodes and shows the camera image, each node's image
// outputs as frames and its other outputs as their latest message. A node applies no setting while it runs, so
// "Apply" saves the changed settings into the profile and starts the run again.

import 'dart:async';

import 'package:flutter/material.dart';

import '../camera_preview_api.dart';
import '../camera_preview_view.dart';
import '../sensor_nodes_api.dart';
import '../setting_row_view.dart';
import '../setup_wizard_backend_client.dart';

/// Pause between two run state requests while a run goes.
const Duration sensorNodesRunStatePollInterval = Duration(seconds: 1);

/// Pause between two requests for a node's latest output message.
const Duration sensorNodeOutputPollInterval = Duration(milliseconds: 500);

/// Pause before asking a starting node for its settings again.
const Duration sensorNodeSettingsRetryInterval = Duration(seconds: 2);

/// Height of the camera image and of a node's image output.
const double sensorNodesCameraImageHeightLogicalPx = 360;
const double sensorNodeImageOutputHeightLogicalPx = 240;

class SensorNodesScreen extends StatefulWidget {
  const SensorNodesScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<SensorNodesScreen> createState() => _SensorNodesScreenState();
}

class _SensorNodesScreenState extends State<SensorNodesScreen> {
  SensorNodeList? _sensorNodeList;
  String? _listErrorText;

  /// The profile's stored selection, with the nodes the selected ones need.
  Set<String> _selectedPackageNames = {};
  bool _isSavingSelection = false;
  String? _selectionErrorText;

  /// The running run's preview id; null while none runs.
  int? _runPreviewId;

  /// Increased with every start, so the image and settings views of an earlier run are built anew.
  int _runStartCount = 0;
  SensorNodesRunState? _runState;
  String? _runErrorText;
  bool _isStartingRun = false;
  Timer? _runStatePollTimer;

  @override
  void initState() {
    super.initState();
    _loadSensorNodeList();
  }

  @override
  void dispose() {
    _runStatePollTimer?.cancel();
    _stopRunQuietly();
    super.dispose();
  }

  Future<void> _loadSensorNodeList() async {
    try {
      final SensorNodeList sensorNodeList = await widget.backendClient.fetchSensorNodeList(widget.profileName);
      if (!mounted) {
        return;
      }
      final Set<String> selectedPackageNames = {};
      for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
        if (sensorNode.isSelected) {
          selectedPackageNames.add(sensorNode.packageName);
        }
      }
      setState(() {
        _sensorNodeList = sensorNodeList;
        _selectedPackageNames = selectedPackageNames;
        _listErrorText = null;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _listErrorText = describeBackendErrorForUser(error);
        });
      }
    }
  }

  /// The selected nodes that need packageName, e.g. page_locator for fiducials_detector.
  List<String> _getSelectedNodesNeeding(String packageName) {
    final List<String> needingNodeNames = [];
    final SensorNodeList? sensorNodeList = _sensorNodeList;
    if (sensorNodeList == null) {
      return needingNodeNames;
    }
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      final bool isSelected = _selectedPackageNames.contains(sensorNode.packageName);
      if (isSelected && sensorNode.requiredSensorNodes.contains(packageName)) {
        needingNodeNames.add(sensorNode.displayName);
      }
    }
    return needingNodeNames;
  }

  Future<void> _toggleSensorNode(String packageName, bool isSelected) async {
    final Set<String> requestedPackageNames = Set<String>.of(_selectedPackageNames);
    if (isSelected) {
      requestedPackageNames.add(packageName);
    } else {
      requestedPackageNames.remove(packageName);
    }
    setState(() {
      _isSavingSelection = true;
      _selectionErrorText = null;
    });
    try {
      final List<String> storedPackageNames = await widget.backendClient.saveSensorNodeSelection(
        profileName: widget.profileName,
        selectedPackageNames: requestedPackageNames.toList(),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedPackageNames = storedPackageNames.toSet();
        _isSavingSelection = false;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _selectionErrorText = describeBackendErrorForUser(error);
          _isSavingSelection = false;
        });
      }
      return;
    }
    // A running run still has the old nodes; start it again with the new ones
    if (_runPreviewId != null) {
      await _startRun();
    }
  }

  Future<void> _startRun() async {
    setState(() {
      _isStartingRun = true;
      _runErrorText = null;
    });
    try {
      final int runPreviewId = await widget.backendClient.startSensorNodesRun(widget.profileName);
      _setRunningPreviewId(runPreviewId);
    } catch (error) {
      if (mounted) {
        setState(() {
          _runErrorText = describeBackendErrorForUser(error);
          _isStartingRun = false;
        });
      }
    }
  }

  /// Shows the run with this preview id, after a start or after Apply started it again.
  void _setRunningPreviewId(int runPreviewId) {
    if (!mounted) {
      // Gone meanwhile: nobody will watch this run
      widget.backendClient.stopCameraPreview(previewId: runPreviewId).catchError((Object error) {});
      return;
    }
    setState(() {
      _runPreviewId = runPreviewId;
      _runStartCount += 1;
      _runState = null;
      _isStartingRun = false;
    });
    _runStatePollTimer?.cancel();
    _runStatePollTimer = Timer.periodic(sensorNodesRunStatePollInterval, (Timer pollTimer) => _loadRunState());
    _loadRunState();
  }

  Future<void> _loadRunState() async {
    try {
      final SensorNodesRunState runState = await widget.backendClient.fetchSensorNodesRunState(widget.profileName);
      if (!mounted || _runPreviewId == null) {
        return;
      }
      setState(() {
        _runState = runState;
      });
      if (!runState.isLaunchRunning) {
        // Ended by itself (e.g. a node failed) or stopped: keep showing why, stop asking
        _runStatePollTimer?.cancel();
      }
    } catch (error) {
      // One slow answer must not end the view; the next request tries again
    }
  }

  void _stopRunQuietly() {
    final int? runPreviewId = _runPreviewId;
    if (runPreviewId == null) {
      return;
    }
    _runPreviewId = null;
    widget.backendClient.stopCameraPreview(previewId: runPreviewId).catchError((Object error) {
      // The backend may already be gone; its watchdog ends the run then.
    });
  }

  void _stopRun() {
    _runStatePollTimer?.cancel();
    _stopRunQuietly();
    setState(() {
      _runState = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final SensorNodeList? sensorNodeList = _sensorNodeList;
    if (sensorNodeList == null) {
      final String? listErrorText = _listErrorText;
      if (listErrorText != null) {
        return Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('Cannot list the sensor nodes: $listErrorText',
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
            TextButton(onPressed: _loadSensorNodeList, child: const Text('Retry')),
          ]),
        );
      }
      return const Center(child: CircularProgressIndicator());
    }
    final List<Widget> screenRows = [
      Text('Sensor processing nodes', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        'Choose what the profile starts on its camera (${sensorNodeList.cameraName}). A node that reads another '
        'one\'s output brings that one along.',
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 8),
      ..._buildSelectionRows(sensorNodeList),
      const SizedBox(height: 24),
      ..._buildRunRows(),
    ];
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: screenRows),
    );
  }

  List<Widget> _buildSelectionRows(SensorNodeList sensorNodeList) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (sensorNodeList.sensorNodes.isEmpty) {
      return [
        const Text('No sensor processing node is installed. Add their repos to config/nodes.list and run '
            './scripts/local_build.sh.'),
      ];
    }
    final List<Widget> selectionRows = [];
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      final List<String> needingNodeNames = _getSelectedNodesNeeding(sensorNode.packageName);
      final bool isNeeded = needingNodeNames.isNotEmpty;
      final List<String> subtitleParts = [sensorNode.description];
      if (sensorNode.requiredSensorNodes.isNotEmpty) {
        subtitleParts.add('Needs ${sensorNode.requiredSensorNodes.join(', ')}.');
      }
      if (isNeeded) {
        subtitleParts.add('Needed by ${needingNodeNames.join(', ')}.');
      }
      final bool hasEntryError = sensorNode.entryErrorText.isNotEmpty;
      if (hasEntryError) {
        subtitleParts.add(sensorNode.entryErrorText);
      }
      // A node another selected one needs stays on; a broken entry cannot be started
      final bool canToggle = !_isSavingSelection && !isNeeded && !hasEntryError;
      selectionRows.add(CheckboxListTile(
        value: _selectedPackageNames.contains(sensorNode.packageName),
        onChanged: canToggle ? (bool? isChecked) => _toggleSensorNode(sensorNode.packageName, isChecked ?? false) : null,
        title: Text(sensorNode.displayName),
        subtitle: Text(subtitleParts.join(' '), style: TextStyle(color: hasEntryError ? colorScheme.error : null)),
        controlAffinity: ListTileControlAffinity.leading,
        contentPadding: EdgeInsets.zero,
      ));
    }
    final String? selectionErrorText = _selectionErrorText;
    if (selectionErrorText != null) {
      selectionRows.add(Text(selectionErrorText, style: TextStyle(color: colorScheme.error)));
    }
    return selectionRows;
  }

  List<Widget> _buildRunRows() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final int? runPreviewId = _runPreviewId;
    final List<Widget> runRows = [Text('Try and adjust', style: Theme.of(context).textTheme.titleMedium)];
    if (runPreviewId == null) {
      runRows.addAll([
        const SizedBox(height: 4),
        const Text('Starts the camera with the selected nodes, as the profile does, without the projector app.'),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: _selectedPackageNames.isEmpty || _isStartingRun ? null : _startRun,
          child: Text(_isStartingRun ? 'Starting …' : 'Start'),
        ),
      ]);
      final String? runErrorText = _runErrorText;
      if (runErrorText != null) {
        runRows.add(Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(runErrorText, style: TextStyle(color: colorScheme.error)),
        ));
      }
      return runRows;
    }

    runRows.addAll([
      const SizedBox(height: 8),
      Row(children: [
        OutlinedButton(onPressed: _stopRun, child: const Text('Stop')),
        const SizedBox(width: 12),
        if (_isStartingRun) const Text('Starting again …'),
      ]),
      const SizedBox(height: 12),
      SizedBox(
        height: sensorNodesCameraImageHeightLogicalPx,
        child: Align(
          alignment: Alignment.topLeft,
          child: CameraFeedImage(
            key: ValueKey<String>('camera_$_runStartCount'),
            backendClient: widget.backendClient,
            feedTopicName: '/camera/image_raw',
          ),
        ),
      ),
    ]);
    final SensorNodesRunState? runState = _runState;
    if (runState == null) {
      runRows.add(const Text('Starting the nodes …'));
      return runRows;
    }
    if (!runState.isLaunchRunning) {
      runRows.add(Text('The run ended. Its last output:', style: TextStyle(color: colorScheme.error)));
      runRows.add(SelectableText(
        runState.launchLogLines.join('\n'),
        style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
      ));
      runRows.add(const SizedBox(height: 8));
      runRows.add(FilledButton(onPressed: _isStartingRun ? null : _startRun, child: const Text('Start again')));
      return runRows;
    }
    for (final RunningSensorNode runningSensorNode in runState.runningSensorNodes) {
      runRows.add(const SizedBox(height: 16));
      runRows.add(_SensorNodeRunCard(
        key: ValueKey<String>('${runningSensorNode.packageName}_$_runStartCount'),
        backendClient: widget.backendClient,
        profileName: widget.profileName,
        runningSensorNode: runningSensorNode,
        displayName: _getDisplayName(runningSensorNode.packageName),
        onRunRestarted: _setRunningPreviewId,
      ));
    }
    return runRows;
  }

  String _getDisplayName(String packageName) {
    for (final SensorNodeSummary sensorNode in _sensorNodeList?.sensorNodes ?? <SensorNodeSummary>[]) {
      if (sensorNode.packageName == packageName) {
        return sensorNode.displayName;
      }
    }
    return packageName;
  }
}

/// One running node: its outputs and its settings with Apply.
class _SensorNodeRunCard extends StatefulWidget {
  const _SensorNodeRunCard({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.runningSensorNode,
    required this.displayName,
    required this.onRunRestarted,
  });

  final SetupWizardBackendClient backendClient;
  final String profileName;
  final RunningSensorNode runningSensorNode;
  final String displayName;

  /// Called with the new run's preview id after Apply started the run again.
  final ValueChanged<int> onRunRestarted;

  @override
  State<_SensorNodeRunCard> createState() => _SensorNodeRunCardState();
}

class _SensorNodeRunCardState extends State<_SensorNodeRunCard> {
  List<CameraSetting>? _nodeSettings;
  String? _settingsErrorText;
  Timer? _settingsRetryTimer;

  /// Changes not applied yet, by setting name.
  final Map<String, Object> _pendingValueByName = {};
  bool _isApplying = false;
  String? _applyErrorText;

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

  /// Asks until the node answers; it may still be starting.
  Future<void> _loadNodeSettings() async {
    try {
      final List<CameraSetting>? nodeSettings =
          await widget.backendClient.fetchSensorNodeSettings(widget.runningSensorNode.packageName);
      if (!mounted) {
        return;
      }
      if (nodeSettings == null) {
        _settingsRetryTimer = Timer(sensorNodeSettingsRetryInterval, _loadNodeSettings);
        return;
      }
      setState(() {
        _nodeSettings = nodeSettings;
        _settingsErrorText = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _settingsErrorText = describeBackendErrorForUser(error);
      });
      _settingsRetryTimer = Timer(sensorNodeSettingsRetryInterval, _loadNodeSettings);
    }
  }

  void _keepPendingChange(String settingName, Object settingValue) {
    setState(() {
      _pendingValueByName[settingName] = settingValue;
      _applyErrorText = null;
    });
  }

  Future<void> _applySettings() async {
    setState(() {
      _isApplying = true;
      _applyErrorText = null;
    });
    try {
      final SensorNodeSettingsApplyResult applyResult = await widget.backendClient.applySensorNodeSettings(
        profileName: widget.profileName,
        packageName: widget.runningSensorNode.packageName,
        settingValueByName: Map<String, Object>.of(_pendingValueByName),
      );
      // The run starts anew, which rebuilds this card with the node's new values
      widget.onRunRestarted(applyResult.previewId);
    } catch (error) {
      if (mounted) {
        setState(() {
          _applyErrorText = describeBackendErrorForUser(error);
          _isApplying = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextTheme textTheme = Theme.of(context).textTheme;
    final RunningSensorNode runningSensorNode = widget.runningSensorNode;
    final List<Widget> cardRows = [
      Row(children: [
        Icon(
          runningSensorNode.isRunning ? Icons.play_circle : Icons.hourglass_empty,
          color: runningSensorNode.isRunning ? Colors.green.shade400 : colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 8),
        Expanded(child: Text(widget.displayName, style: textTheme.titleMedium)),
        Text(runningSensorNode.isRunning ? 'running' : 'starting …', style: TextStyle(color: colorScheme.onSurfaceVariant)),
      ]),
    ];
    if (runningSensorNode.isRunning && runningSensorNode.outputTopics.isEmpty) {
      cardRows.add(Text('Publishes nothing yet.', style: TextStyle(color: colorScheme.onSurfaceVariant)));
    }
    for (final SensorNodeOutputTopic outputTopic in runningSensorNode.outputTopics) {
      cardRows.add(const SizedBox(height: 8));
      cardRows.add(Text('${outputTopic.topicName} (${outputTopic.typeName})', style: textTheme.labelMedium));
      if (outputTopic.isImage) {
        cardRows.add(SizedBox(
          height: sensorNodeImageOutputHeightLogicalPx,
          child: Align(
            alignment: Alignment.topLeft,
            child: CameraFeedImage(backendClient: widget.backendClient, feedTopicName: outputTopic.topicName),
          ),
        ));
      } else {
        cardRows.add(_SensorNodeOutputText(backendClient: widget.backendClient, topicName: outputTopic.topicName));
      }
    }
    cardRows.add(const SizedBox(height: 12));
    cardRows.addAll(_buildSettingsRows());
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: cardRows),
      ),
    );
  }

  List<Widget> _buildSettingsRows() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<CameraSetting>? nodeSettings = _nodeSettings;
    final List<Widget> settingsRows = [Text('Settings', style: Theme.of(context).textTheme.titleSmall)];
    if (nodeSettings == null) {
      String waitingText = 'Waiting for the node to report its settings …';
      final String? settingsErrorText = _settingsErrorText;
      if (settingsErrorText != null) {
        waitingText = '$waitingText ($settingsErrorText)';
      }
      settingsRows.add(Text(waitingText, style: TextStyle(color: colorScheme.onSurfaceVariant)));
      return settingsRows;
    }
    if (nodeSettings.isEmpty) {
      settingsRows.add(Text('The node reports no settings.', style: TextStyle(color: colorScheme.onSurfaceVariant)));
      return settingsRows;
    }
    settingsRows.add(Text(
      'The node reads its settings when it starts: Apply saves the changes into the profile and starts it again.',
      style: TextStyle(color: colorScheme.onSurfaceVariant),
    ));
    final int pendingChangeCount = _pendingValueByName.length;
    settingsRows.add(const SizedBox(height: 8));
    settingsRows.add(Row(children: [
      FilledButton(
        onPressed: pendingChangeCount == 0 || _isApplying ? null : _applySettings,
        child: Text(_isApplying ? 'Applying …' : 'Apply'),
      ),
      const SizedBox(width: 12),
      TextButton(
        onPressed: pendingChangeCount == 0 || _isApplying
            ? null
            : () => setState(() {
                  _pendingValueByName.clear();
                }),
        child: const Text('Discard'),
      ),
      const SizedBox(width: 12),
      Text('$pendingChangeCount not applied', style: TextStyle(color: colorScheme.onSurfaceVariant)),
    ]));
    final String? applyErrorText = _applyErrorText;
    if (applyErrorText != null) {
      settingsRows.add(Text(applyErrorText, style: TextStyle(color: colorScheme.error)));
    }
    for (final CameraSetting nodeSetting in nodeSettings) {
      final String settingName = nodeSetting.settingName;
      // read_only means "not changed while running"; the node reads a new value at its restart
      settingsRows.add(SettingRowView(
        key: ValueKey<String>(settingName),
        cameraSetting: nodeSetting,
        shownValue: _pendingValueByName[settingName] ?? nodeSetting.settingValue,
        isEditable: !_isApplying,
        onSettingChanged: _keepPendingChange,
      ));
    }
    return settingsRows;
  }
}

/// The latest message on an output topic as text, asked for again and again while shown.
class _SensorNodeOutputText extends StatefulWidget {
  const _SensorNodeOutputText({required this.backendClient, required this.topicName});

  final SetupWizardBackendClient backendClient;
  final String topicName;

  @override
  State<_SensorNodeOutputText> createState() => _SensorNodeOutputTextState();
}

class _SensorNodeOutputTextState extends State<_SensorNodeOutputText> {
  SensorNodeOutputMessage? _outputMessage;
  String? _outputErrorText;

  @override
  void initState() {
    super.initState();
    _pollOutputMessage();
  }

  Future<void> _pollOutputMessage() async {
    while (mounted) {
      try {
        final SensorNodeOutputMessage outputMessage =
            await widget.backendClient.fetchSensorNodeOutputMessage(widget.topicName);
        if (!mounted) {
          return;
        }
        setState(() {
          _outputMessage = outputMessage;
          _outputErrorText = null;
        });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setState(() {
          _outputErrorText = describeBackendErrorForUser(error);
        });
      }
      await Future<void>.delayed(sensorNodeOutputPollInterval);
    }
  }

  @override
  Widget build(BuildContext context) {
    final Color mutedColor = Theme.of(context).colorScheme.onSurfaceVariant;
    final String? outputErrorText = _outputErrorText;
    if (outputErrorText != null) {
      return Text(outputErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error));
    }
    final SensorNodeOutputMessage? outputMessage = _outputMessage;
    final double? receivedAgeS = outputMessage?.receivedAgeS;
    if (outputMessage == null || receivedAgeS == null) {
      return Text('No message yet.', style: TextStyle(color: mutedColor));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('${receivedAgeS.toStringAsFixed(1)} s ago', style: TextStyle(color: mutedColor, fontSize: 12)),
      ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 200),
        child: SingleChildScrollView(
          child: SelectableText(outputMessage.messageText, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
        ),
      ),
    ]);
  }
}
