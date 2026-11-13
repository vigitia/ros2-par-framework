// Written by Claude Code
//
// Hub area "Sensor nodes" of a profile: one tab per sensor processing node the profile starts on at least one camera
// (par_launch.<package>: [<camera>, ...]), "Add sensor node" for the installed ones it does not start yet; an added
// node runs on the main camera. A node's tab shows what it is, Disable (not for a node another enabled one needs,
// which comes along with it), with several cameras a chip per camera choosing where it runs and a switch choosing the
// camera whose settings and debug view the tab shows, and its settings on that camera
// (/cameras/<camera>/<package>_node). The settings are read once from the node and saved into the profile without a
// run (NodeSettingsEditorView). The floating "Debug node" button starts the profile's cameras with their nodes,
// without the projector app and with their debug parameter on, so each node opens its own preview window on the PAR
// machine; the tab in front then shows the chosen camera's image and its node's outputs there (image outputs as
// frames, the others as their latest message), and saving settings meanwhile starts the run again with them.

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

/// Pause between the answer to one run state request and the next request while a run goes.
const Duration sensorNodesRunStatePollInterval = Duration(seconds: 1);

/// Pause between two requests for a node's latest output message.
const Duration sensorNodeOutputPollInterval = Duration(milliseconds: 500);

/// Height of the camera image and of a node's image output.
const double sensorNodesCameraImageHeightLogicalPx = 360;
const double sensorNodeImageOutputHeightLogicalPx = 240;

/// par.launch.py names each sensor node `<package>_node`, in its camera's namespace.
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

  /// The profile's stored selection: the cameras each node runs on, with the nodes the listed ones need on the same
  /// camera; only nodes that run on a camera.
  Map<String, List<String>> _cameraNamesByPackage = {};
  bool _isSavingSelection = false;
  String? _selectionErrorText;

  /// The node whose tab comes to the front when the tabs change, e.g. one just added.
  String? _shownTabPackageName;

  /// Per node, the camera whose settings and debug view its tab shows, once one was chosen.
  final Map<String, String> _shownCameraNameByPackage = {};

  /// The running try's preview id; null while none runs.
  int? _runPreviewId;

  /// Increased with every start, so the image views of an earlier run are built anew and the run state requests of
  /// an earlier run stop and their answers are dropped.
  int _runStartCount = 0;
  SensorNodesRunState? _runState;
  String? _runErrorText;

  /// Why the running try's state cannot be read (e.g. the backend stopped answering); null after the next answer.
  String? _runStateErrorText;
  bool _isStartingRun = false;

  @override
  void initState() {
    super.initState();
    _loadSensorNodeList();
  }

  @override
  void dispose() {
    _stopRunQuietly();
    super.dispose();
  }

  Future<void> _loadSensorNodeList() async {
    try {
      final SensorNodeList sensorNodeList = await widget.backendClient.fetchSensorNodeList(widget.profileName);
      if (!mounted) {
        return;
      }
      final Map<String, List<String>> cameraNamesByPackage = {};
      for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
        if (sensorNode.cameraNames.isNotEmpty) {
          cameraNamesByPackage[sensorNode.packageName] = sensorNode.cameraNames;
        }
      }
      setState(() {
        _sensorNodeList = sensorNodeList;
        _cameraNamesByPackage = cameraNamesByPackage;
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

  /// Sets the cameras the node runs on; none disables it. A node just enabled comes to the front as its tab.
  Future<void> _setSensorNodeCameras(String packageName, List<String> cameraNames) async {
    final Map<String, List<String>> requestedCameraNamesByPackage = Map<String, List<String>>.of(_cameraNamesByPackage);
    final bool isNewlyEnabled = cameraNames.isNotEmpty && !_cameraNamesByPackage.containsKey(packageName);
    if (cameraNames.isEmpty) {
      requestedCameraNamesByPackage.remove(packageName);
    } else {
      requestedCameraNamesByPackage[packageName] = cameraNames;
    }
    setState(() {
      _isSavingSelection = true;
      _selectionErrorText = null;
      if (isNewlyEnabled) {
        _shownTabPackageName = packageName;
      }
    });
    try {
      final Map<String, List<String>> storedCameraNamesByPackage = await widget.backendClient.saveSensorNodeSelection(
        profileName: widget.profileName,
        cameraNamesByPackage: requestedCameraNamesByPackage,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _cameraNamesByPackage = storedCameraNamesByPackage;
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
      _runStateErrorText = null;
      _isStartingRun = false;
    });
    _pollRunState(_runStartCount);
  }

  /// Whether the run started as start number runStartCount is still the one shown.
  bool _isCurrentRun(int runStartCount) {
    return mounted && _runPreviewId != null && runStartCount == _runStartCount;
  }

  /// Asks for the run's state, one request at a time, until the run ends, is stopped or replaced by a new start, or
  /// the screen is gone. A failed request is shown and the next one tries again.
  Future<void> _pollRunState(int runStartCount) async {
    while (_isCurrentRun(runStartCount)) {
      bool isLaunchRunning = true;
      try {
        final SensorNodesRunState runState = await widget.backendClient.fetchSensorNodesRunState(widget.profileName);
        if (!_isCurrentRun(runStartCount)) {
          return;
        }
        isLaunchRunning = runState.isLaunchRunning;
        setState(() {
          _runState = runState;
          _runStateErrorText = null;
        });
      } catch (error) {
        if (!_isCurrentRun(runStartCount)) {
          return;
        }
        setState(() {
          _runStateErrorText = describeBackendErrorForUser(error);
        });
      }
      if (!isLaunchRunning) {
        // Ended by itself (e.g. a node failed): keep showing why, stop asking
        return;
      }
      await Future<void>.delayed(sensorNodesRunStatePollInterval);
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
    _stopRunQuietly();
    setState(() {
      _runState = null;
      _runStateErrorText = null;
    });
  }

  /// The enabled nodes in the order the backend lists them.
  List<SensorNodeSummary> _getEnabledSensorNodes(SensorNodeList sensorNodeList) {
    final List<SensorNodeSummary> enabledSensorNodes = [];
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      if (_cameraNamesByPackage.containsKey(sensorNode.packageName)) {
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
      debugButton = _buildDebugButton();
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

  /// Starts the cameras with their enabled nodes, or stops that run.
  Widget _buildDebugButton() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (_runPreviewId != null) {
      return FloatingActionButton.extended(
        heroTag: sensorNodesDebugButtonHeroTag,
        onPressed: _stopRun,
        tooltip: 'Stop the cameras and the sensor nodes.',
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
      tooltip: 'Start the cameras with their enabled nodes, as the profile does but without the projector app and '
          'with debug on (each node opens its preview window on the PAR machine), and show what the node in front '
          'publishes on the camera its tab shows.',
      icon: icon,
      label: const Text('Debug node'),
    );
  }

  /// An added node runs on the main camera; its tab chooses further ones.
  List<Widget> _buildAddMenuEntries(SensorNodeList sensorNodeList) {
    final List<Widget> addMenuEntries = [];
    for (final SensorNodeSummary sensorNode in sensorNodeList.sensorNodes) {
      if (_cameraNamesByPackage.containsKey(sensorNode.packageName)) {
        continue;
      }
      // A broken entry cannot be started, and a profile without a camera has nothing to run it on
      VoidCallback? onPressed;
      final bool canBeAdded =
          sensorNode.entryErrorText.isEmpty && sensorNodeList.cameraNames.isNotEmpty && !_isSavingSelection;
      if (canBeAdded) {
        final String mainCameraName = sensorNodeList.cameraNames.first;
        onPressed = () => _setSensorNodeCameras(sensorNode.packageName, [mainCameraName]);
      }
      addMenuEntries.add(MenuItemButton(onPressed: onPressed, child: Text(sensorNode.displayName)));
    }
    return addMenuEntries;
  }

  /// The nodes on cameraName that need packageName there, e.g. page_locator for fiducials_detector.
  List<String> _getNodesNeedingOnCamera(String packageName, String cameraName) {
    final List<String> needingNodeNames = [];
    for (final SensorNodeSummary sensorNode in _sensorNodeList?.sensorNodes ?? <SensorNodeSummary>[]) {
      final List<String> nodeCameraNames = _cameraNamesByPackage[sensorNode.packageName] ?? <String>[];
      if (nodeCameraNames.contains(cameraName) && sensorNode.requiredSensorNodes.contains(packageName)) {
        needingNodeNames.add(sensorNode.displayName);
      }
    }
    return needingNodeNames;
  }

  /// The camera whose settings and debug view the node's tab shows: the chosen one while the node runs on it, else
  /// the first camera it runs on.
  String _getShownCameraName(String packageName) {
    final List<String> nodeCameraNames = _cameraNamesByPackage[packageName] ?? <String>[];
    final String? chosenCameraName = _shownCameraNameByPackage[packageName];
    if (chosenCameraName != null && nodeCameraNames.contains(chosenCameraName)) {
      return chosenCameraName;
    }
    return nodeCameraNames.first;
  }

  Widget _buildSensorNodeTab(SensorNodeSummary sensorNode, bool isShownTab) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextStyle mutedTextStyle = TextStyle(color: colorScheme.onSurfaceVariant);
    final List<String> nodeCameraNames = _cameraNamesByPackage[sensorNode.packageName] ?? <String>[];
    final Set<String> needingNodeNames = {};
    for (final String cameraName in nodeCameraNames) {
      needingNodeNames.addAll(_getNodesNeedingOnCamera(sensorNode.packageName, cameraName));
    }
    final List<String> descriptionParts = [sensorNode.description];
    if (sensorNode.requiredSensorNodes.isNotEmpty) {
      descriptionParts.add('Needs ${sensorNode.requiredSensorNodes.join(', ')}, which starts along with it on the '
          'same camera.');
    }
    VoidCallback? onDisableClicked;
    String disableTooltipText = 'The profile no longer starts this node, on any camera.';
    if (needingNodeNames.isNotEmpty) {
      disableTooltipText = 'Needed by ${needingNodeNames.join(', ')}: disable that first.';
    } else if (!_isSavingSelection) {
      onDisableClicked = () => _setSensorNodeCameras(sensorNode.packageName, []);
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
    // With one camera, Disable is the only choice; the camera chips and the camera switch need several
    final List<String> profileCameraNames = _sensorNodeList?.cameraNames ?? <String>[];
    if (profileCameraNames.length > 1) {
      tabRows.add(const SizedBox(height: 12));
      tabRows.add(_buildCameraChipsRow(sensorNode, profileCameraNames, nodeCameraNames));
    }
    final String? selectionErrorText = _selectionErrorText;
    if (selectionErrorText != null) {
      tabRows.add(Text(selectionErrorText, style: TextStyle(color: colorScheme.error)));
    }
    final String shownCameraName = _getShownCameraName(sensorNode.packageName);
    if (nodeCameraNames.length > 1) {
      tabRows.add(const SizedBox(height: 12));
      tabRows.add(Row(children: [
        Text('Settings and debug view for', style: mutedTextStyle),
        const SizedBox(width: 12),
        SegmentedButton<String>(
          segments: [
            for (final String cameraName in nodeCameraNames)
              ButtonSegment<String>(value: cameraName, label: Text(cameraName)),
          ],
          selected: {shownCameraName},
          onSelectionChanged: (Set<String> selectedCameraNames) {
            setState(() {
              _shownCameraNameByPackage[sensorNode.packageName] = selectedCameraNames.first;
            });
          },
        ),
      ]));
    }
    tabRows.add(const SizedBox(height: 16));
    // Only the tab in front shows the live image, so hidden tabs do not ask for frames
    if (isShownTab) {
      final List<Widget> debugRows = _buildDebugRows(sensorNode, shownCameraName);
      if (debugRows.isNotEmpty) {
        tabRows.addAll(debugRows);
        tabRows.add(const SizedBox(height: 24));
      }
    }
    tabRows.add(NodeSettingsEditorView(
      // Built anew for another camera: its values are that camera's
      key: ValueKey<String>('${sensorNode.packageName}_$shownCameraName'),
      backendClient: widget.backendClient,
      profileName: widget.profileName,
      nodeKind: SettingsNodeKind.sensorNode,
      packageName: sensorNode.packageName,
      fullNodeName: '$camerasNamespace/$shownCameraName/${sensorNode.packageName}$sensorNodeNameSuffix',
      onSettingsSaved: _restartRunningDebugRun,
    ));
    return SingleChildScrollView(
      // Room below the content, so the floating button does not cover its end
      padding: const EdgeInsets.fromLTRB(24, 16, 24, runButtonClearanceLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: tabRows),
    );
  }

  /// A chip per camera of the profile, selected where the node runs; one the node is needed on stays selected.
  Widget _buildCameraChipsRow(SensorNodeSummary sensorNode, List<String> profileCameraNames,
      List<String> nodeCameraNames) {
    final List<Widget> cameraChips = [];
    for (final String cameraName in profileCameraNames) {
      final bool isRunningOnCamera = nodeCameraNames.contains(cameraName);
      final List<String> needingNodeNames = _getNodesNeedingOnCamera(sensorNode.packageName, cameraName);
      String chipTooltipText = 'Run this node on $cameraName, in /cameras/$cameraName.';
      ValueChanged<bool>? onSelected;
      if (isRunningOnCamera && needingNodeNames.isNotEmpty) {
        chipTooltipText = 'Needed by ${needingNodeNames.join(', ')} on $cameraName: remove that first.';
      } else if (!_isSavingSelection) {
        onSelected = (bool isSelected) {
          final List<String> requestedCameraNames = [];
          for (final String profileCameraName in profileCameraNames) {
            final bool isKept = profileCameraName != cameraName && nodeCameraNames.contains(profileCameraName);
            final bool isAdded = profileCameraName == cameraName && isSelected;
            if (isKept || isAdded) {
              requestedCameraNames.add(profileCameraName);
            }
          }
          _setSensorNodeCameras(sensorNode.packageName, requestedCameraNames);
        };
      }
      cameraChips.add(FilterChip(
        label: Text(cameraName),
        selected: isRunningOnCamera,
        tooltip: chipTooltipText,
        onSelected: onSelected,
      ));
    }
    return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Text('Runs on', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
      const SizedBox(width: 12),
      Expanded(child: Wrap(spacing: 8, runSpacing: 8, children: cameraChips)),
    ]);
  }

  /// A running debug run starts again, so the nodes read the saved settings.
  void _restartRunningDebugRun() {
    if (_runPreviewId != null) {
      _startRun();
    }
  }

  /// The live view while debugging: the camera's image and this node's outputs on it; nothing while no run goes.
  List<Widget> _buildDebugRows(SensorNodeSummary sensorNode, String cameraName) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> debugRows = [];
    if (_runPreviewId == null) {
      final String? runErrorText = _runErrorText;
      if (runErrorText != null) {
        debugRows.add(Text('Could not start debugging: $runErrorText', style: TextStyle(color: colorScheme.error)));
      }
      return debugRows;
    }
    debugRows.add(Text('Debugging on $cameraName', style: Theme.of(context).textTheme.titleMedium));
    debugRows.addAll([
      if (_isStartingRun) const Text('Starting again …'),
      const SizedBox(height: 8),
      SizedBox(
        height: sensorNodesCameraImageHeightLogicalPx,
        child: Align(
          alignment: Alignment.topLeft,
          child: CameraFeedImage(
            key: ValueKey<String>('camera_${cameraName}_$_runStartCount'),
            backendClient: widget.backendClient,
            // The run starts every camera of the profile; this one is the node's run shown in the tab
            feedTopicName: PreviewCameraChoice.profileCamera(
              profileName: widget.profileName,
              cameraName: cameraName,
            ).imageTopicName,
          ),
        ),
      ),
    ]);
    final String? runStateErrorText = _runStateErrorText;
    if (runStateErrorText != null) {
      final String runStateErrorLineText = 'Cannot read the state of the nodes: $runStateErrorText';
      debugRows.add(Text(runStateErrorLineText, style: TextStyle(color: colorScheme.error)));
    }
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
      final bool isShownRun =
          runningSensorNode.packageName == sensorNode.packageName && runningSensorNode.cameraName == cameraName;
      if (!isShownRun) {
        continue;
      }
      debugRows.add(const SizedBox(height: 16));
      debugRows.add(_SensorNodeOutputsView(
        key: ValueKey<String>('${runningSensorNode.packageName}_${cameraName}_$_runStartCount'),
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
