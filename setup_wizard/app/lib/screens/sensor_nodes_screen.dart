// Written by Claude Code
//
// Hub area "Sensor nodes" of a profile: one tab per sensor processing node the profile starts (par_launch.<package>:
// true), "Add sensor node" for the installed ones it does not start yet. A node's tab shows what it is, Disable (not
// for a node another enabled one needs, which comes along with it) and its settings. The settings are read once from
// the node and saved into the profile without a run (NodeSettingsEditorView). The floating "Debug node" button
// starts the profile's camera with the enabled nodes, without the projector app and with their debug parameter on,
// so each node opens its own preview window on the PAR machine; the tab in front then shows the camera image and
// its node's outputs (image outputs as frames, the others as their latest message), and saving
// settings meanwhile starts the run again with them.

import 'dart:async';

import 'package:flutter/material.dart';

import '../addable_tabs_view.dart';
import '../camera_preview_api.dart';
import '../camera_preview_view.dart';
import '../node_settings_api.dart';
import '../node_settings_editor_view.dart';
import '../profile_run_view.dart';
import '../sensor_nodes_api.dart';
import '../top_aligned_page_content.dart';
import '../setup_wizard_backend_client.dart';

/// Pause between two run state requests while a run goes.
const Duration sensorNodesRunStatePollInterval = Duration(seconds: 1);

/// Pause between two requests for a node's latest output message.
const Duration sensorNodeOutputPollInterval = Duration(milliseconds: 500);

/// Height of the camera image and of a node's image output.
const double sensorNodesCameraImageHeightLogicalPx = 360;
const double sensorNodeImageOutputHeightLogicalPx = 240;

/// par.launch.py names each sensor node `<package>_node`, without a namespace.
const String sensorNodeNameSuffix = '_node';

/// The debug button's own hero tag, distinct from the Run button's (profileRunButtonHeroTag), which is on screen too.
const String sensorNodesDebugButtonHeroTag = 'sensor_nodes_debug_button';

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
  Set<String> _enabledPackageNames = {};
  bool _isSavingSelection = false;
  String? _selectionErrorText;

  /// The node whose tab comes to the front when the tabs change, e.g. one just added.
  String? _shownTabPackageName;

  /// The running try's preview id; null while none runs.
  int? _runPreviewId;

  /// Increased with every start, so the image views of an earlier run are built anew.
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
        _enabledPackageNames = selectedPackageNames;
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

  /// Enables or disables the node; an enabled one comes to the front as its tab.
  Future<void> _setSensorNodeEnabled(String packageName, bool isEnabled) async {
    final Set<String> requestedPackageNames = Set<String>.of(_enabledPackageNames);
    if (isEnabled) {
      requestedPackageNames.add(packageName);
    } else {
      requestedPackageNames.remove(packageName);
    }
    setState(() {
      _isSavingSelection = true;
      _selectionErrorText = null;
      if (isEnabled) {
        _shownTabPackageName = packageName;
      }
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
        _enabledPackageNames = storedPackageNames.toSet();
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

  /// The enabled nodes in the order the backend lists them.
  List<SensorNodeSummary> _getEnabledSensorNodes(SensorNodeList sensorNodeList) {
    final List<SensorNodeSummary> enabledSensorNodes = [];
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      if (_enabledPackageNames.contains(sensorNode.packageName)) {
        enabledSensorNodes.add(sensorNode);
      }
    }
    return enabledSensorNodes;
  }

  @override
  Widget build(BuildContext context) {
    final SensorNodeList? sensorNodeList = _sensorNodeList;
    if (sensorNodeList == null) {
      final String? listErrorText = _listErrorText;
      if (listErrorText != null) {
        return TopAlignedPageContent(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Cannot list the sensor nodes: $listErrorText',
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
            TextButton(onPressed: _loadSensorNodeList, child: const Text('Try again')),
          ]),
        );
      }
      return const TopAlignedPageContent(child: CircularProgressIndicator());
    }

    final List<SensorNodeSummary> enabledSensorNodes = _getEnabledSensorNodes(sensorNodeList);
    final List<String> tabTitles = [];
    String? shownTabTitle;
    for (final SensorNodeSummary enabledSensorNode in enabledSensorNodes) {
      tabTitles.add(enabledSensorNode.displayName);
      if (enabledSensorNode.packageName == _shownTabPackageName) {
        shownTabTitle = enabledSensorNode.displayName;
      }
    }
    String noTabsText = 'The profile starts no sensor node. Add one with "Add sensor node".';
    if (sensorNodeList.sensorNodes.isEmpty) {
      noTabsText = 'No sensor processing node is installed. Add their repos to config/nodes.list and run '
          './scripts/local_build.sh.';
    }
    Widget? debugButton;
    if (enabledSensorNodes.isNotEmpty) {
      debugButton = _buildDebugButton(sensorNodeList.cameraName);
    }
    // A Scaffold of its own, so the button floats in this area's bottom right corner
    return Scaffold(
      floatingActionButton: debugButton,
      body: AddableTabsView(
        tabTitles: tabTitles,
        shownTabTitle: shownTabTitle,
        addButtonText: 'Add sensor node',
        addMenuEntries: _buildAddMenuEntries(sensorNodeList),
        noTabsText: noTabsText,
        buildTabContent: (int tabIndex, bool isShownTab) =>
            _buildSensorNodeTab(enabledSensorNodes[tabIndex], isShownTab),
      ),
    );
  }

  /// Starts the camera with the enabled nodes, or stops that run.
  Widget _buildDebugButton(String cameraName) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (_runPreviewId != null) {
      return FloatingActionButton.extended(
        heroTag: sensorNodesDebugButtonHeroTag,
        onPressed: _stopRun,
        tooltip: 'Stop the camera and the sensor nodes.',
        backgroundColor: colorScheme.error,
        foregroundColor: colorScheme.onError,
        icon: const Icon(Icons.stop),
        label: const Text('Stop debugging'),
      );
    }
    Widget icon = const Icon(Icons.bug_report_outlined);
    VoidCallback? onPressed = _startRun;
    if (_isStartingRun) {
      onPressed = null;
      icon = const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2));
    }
    return FloatingActionButton.extended(
      heroTag: sensorNodesDebugButtonHeroTag,
      onPressed: onPressed,
      tooltip: 'Start the camera ($cameraName) with the enabled nodes, as the profile does but without the projector '
          'app and with debug on (each node opens its preview window on the PAR machine), and show what the node '
          'in front publishes.',
      icon: icon,
      label: const Text('Debug node'),
    );
  }

  List<Widget> _buildAddMenuEntries(SensorNodeList sensorNodeList) {
    final List<Widget> addMenuEntries = [];
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      if (_enabledPackageNames.contains(sensorNode.packageName)) {
        continue;
      }
      // A broken entry cannot be started
      VoidCallback? onPressed;
      if (sensorNode.entryErrorText.isEmpty && !_isSavingSelection) {
        onPressed = () => _setSensorNodeEnabled(sensorNode.packageName, true);
      }
      addMenuEntries.add(MenuItemButton(onPressed: onPressed, child: Text(sensorNode.displayName)));
    }
    return addMenuEntries;
  }

  /// The selected nodes that need packageName, e.g. page_locator for fiducials_detector.
  List<String> _getSelectedNodesNeeding(String packageName) {
    final List<String> needingNodeNames = [];
    for (final SensorNodeSummary sensorNode in _sensorNodeList?.sensorNodes ?? <SensorNodeSummary>[]) {
      final bool isSelected = _enabledPackageNames.contains(sensorNode.packageName);
      if (isSelected && sensorNode.requiredSensorNodes.contains(packageName)) {
        needingNodeNames.add(sensorNode.displayName);
      }
    }
    return needingNodeNames;
  }

  Widget _buildSensorNodeTab(SensorNodeSummary sensorNode, bool isShownTab) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final List<String> needingNodeNames = _getSelectedNodesNeeding(sensorNode.packageName);
    final List<String> descriptionParts = [sensorNode.description];
    if (sensorNode.requiredSensorNodes.isNotEmpty) {
      descriptionParts.add('Needs ${sensorNode.requiredSensorNodes.join(', ')}, which starts along with it.');
    }
    VoidCallback? onDisableClicked;
    String disableTooltipText = 'The profile no longer starts this node.';
    if (needingNodeNames.isNotEmpty) {
      disableTooltipText = 'Needed by ${needingNodeNames.join(', ')}: disable that first.';
    } else if (!_isSavingSelection) {
      onDisableClicked = () => _setSensorNodeEnabled(sensorNode.packageName, false);
    }
    final List<Widget> tabRows = [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: Text(descriptionParts.join(' '), style: mutedTextStyle)),
        const SizedBox(width: 12),
        Tooltip(
          message: disableTooltipText,
          child: OutlinedButton.icon(
            onPressed: onDisableClicked,
            icon: const Icon(Icons.remove_circle_outline),
            label: const Text('Disable'),
          ),
        ),
      ]),
    ];
    final String? selectionErrorText = _selectionErrorText;
    if (selectionErrorText != null) {
      tabRows.add(Text(selectionErrorText, style: TextStyle(color: colorScheme.error)));
    }
    tabRows.add(const SizedBox(height: 16));
    // Only the tab in front shows the live image, so hidden tabs do not ask for frames
    if (isShownTab) {
      final List<Widget> debugRows = _buildDebugRows(sensorNode);
      if (debugRows.isNotEmpty) {
        tabRows.addAll(debugRows);
        tabRows.add(const SizedBox(height: 24));
      }
    }
    tabRows.add(NodeSettingsEditorView(
      backendClient: widget.backendClient,
      profileName: widget.profileName,
      nodeKind: SettingsNodeKind.sensorNode,
      packageName: sensorNode.packageName,
      fullNodeName: '/${sensorNode.packageName}$sensorNodeNameSuffix',
      onSettingsSaved: _restartRunningDebugRun,
    ));
    return SingleChildScrollView(
      // Room below the content, so the floating button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 16, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: tabRows),
    );
  }

  /// A running debug run starts again, so the nodes read the saved settings.
  void _restartRunningDebugRun() {
    if (_runPreviewId != null) {
      _startRun();
    }
  }

  /// The live view while debugging: the camera image and this node's outputs; nothing while no run goes.
  List<Widget> _buildDebugRows(SensorNodeSummary sensorNode) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> debugRows = [];
    if (_runPreviewId == null) {
      final String? runErrorText = _runErrorText;
      if (runErrorText != null) {
        debugRows.add(Text('Could not start debugging: $runErrorText', style: TextStyle(color: colorScheme.error)));
      }
      return debugRows;
    }
    debugRows.add(Text('Debugging', style: Theme.of(context).textTheme.titleMedium));
    debugRows.addAll([
      if (_isStartingRun) const Text('Starting again …'),
      const SizedBox(height: 8),
      SizedBox(
        height: sensorNodesCameraImageHeightLogicalPx,
        child: Align(
          alignment: Alignment.topLeft,
          child: CameraFeedImage(
            key: ValueKey<String>('camera_$_runStartCount'),
            backendClient: widget.backendClient,
            // The run shows the main camera, the one the sensor nodes use
            feedTopicName: PreviewCameraChoice.profileCamera(
              profileName: widget.profileName,
              cameraName: _sensorNodeList?.cameraName ?? '',
            ).imageTopicName,
          ),
        ),
      ),
    ]);
    final SensorNodesRunState? runState = _runState;
    if (runState == null) {
      debugRows.add(const Text('Starting the nodes …'));
      return debugRows;
    }
    if (!runState.isLaunchRunning) {
      debugRows.add(Text('The run ended. Its last output:', style: TextStyle(color: colorScheme.error)));
      debugRows.add(SelectableText(
        runState.launchLogLines.join('\n'),
        style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
      ));
      debugRows.add(const SizedBox(height: 8));
      debugRows.add(FilledButton(onPressed: _isStartingRun ? null : _startRun, child: const Text('Start again')));
      return debugRows;
    }
    for (final RunningSensorNode runningSensorNode in runState.runningSensorNodes) {
      if (runningSensorNode.packageName != sensorNode.packageName) {
        continue;
      }
      debugRows.add(const SizedBox(height: 16));
      debugRows.add(_SensorNodeOutputsView(
        key: ValueKey<String>('${runningSensorNode.packageName}_$_runStartCount'),
        backendClient: widget.backendClient,
        runningSensorNode: runningSensorNode,
      ));
    }
    return debugRows;
  }
}

/// What a running node publishes: its image outputs as frames, the others as their latest message.
class _SensorNodeOutputsView extends StatelessWidget {
  const _SensorNodeOutputsView({super.key, required this.backendClient, required this.runningSensorNode});

  final SetupWizardBackendClient backendClient;
  final RunningSensorNode runningSensorNode;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> outputRows = [
      Row(children: [
        Icon(
          runningSensorNode.isRunning ? Icons.play_circle : Icons.hourglass_empty,
          color: runningSensorNode.isRunning ? Colors.green.shade400 : colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 8),
        Text(runningSensorNode.isRunning ? 'running' : 'starting …', style: TextStyle(color: colorScheme.onSurfaceVariant)),
      ]),
    ];
    if (runningSensorNode.isRunning && runningSensorNode.outputTopics.isEmpty) {
      outputRows.add(Text('Publishes nothing yet.', style: TextStyle(color: colorScheme.onSurfaceVariant)));
    }
    for (final SensorNodeOutputTopic outputTopic in runningSensorNode.outputTopics) {
      outputRows.add(const SizedBox(height: 8));
      outputRows.add(Text('${outputTopic.topicName} (${outputTopic.typeName})', style: textTheme.labelMedium));
      if (outputTopic.isImage) {
        outputRows.add(SizedBox(
          height: sensorNodeImageOutputHeightLogicalPx,
          child: Align(
            alignment: Alignment.topLeft,
            child: CameraFeedImage(backendClient: backendClient, feedTopicName: outputTopic.topicName),
          ),
        ));
      } else {
        outputRows.add(_SensorNodeOutputText(backendClient: backendClient, topicName: outputTopic.topicName));
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: outputRows);
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
      // Its full height, scrolling with the page; the backend cuts long messages and arrays
      SelectableText(outputMessage.messageText, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
    ]);
  }
}
