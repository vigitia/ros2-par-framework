// Written by Claude Code
//
// One camera's camera pose or projector calibration in a saved profile: what the profile has stored, the camera's
// live image, and a run of the framework's calibration launch with its result. Used by the wizard steps "Camera
// pose" and "Projector calibration" and by a profile's overview.
//
// A run's launch starts the camera itself and replaces the preview's camera in the backend, so the preview below
// keeps showing the live image during the run; after the run the preview is started again. The result comes from
// the file the calibration stored, a failure shows the launch's error lines as they are.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'camera_preview_view.dart';
import 'extrinsics_api.dart';
import 'intrinsics_calibration_view.dart';
import 'setup_wizard_backend_client.dart';

/// Pause between two progress requests while a run goes.
const Duration extrinsicsRunProgressPollInterval = Duration(milliseconds: 500);

/// Pause between two state requests while no run goes: the calibrations offered depend on what the previewed
/// camera publishes (e.g. depth), known only once it runs.
const Duration extrinsicsStatePollInterval = Duration(seconds: 2);

/// Below this width the controls go under the image instead of next to it.
const double extrinsicsSideBySideMinimumWidthLogicalPx = 900;

/// Friendly names of the quality figures the calibrators store; others are shown by their key.
const Map<String, String> poseQualityFigureLabelByName = {
  'board_reprojection_error_px': 'Board corners off the fitted board (px)',
  'board_normal_spread_deg': 'Tilt spread between frames (°)',
  'board_frames': 'Frames averaged',
  'table_fraction': 'Share of the image on the table plane',
  'table_rms_mm': 'Table plane fit error (mm)',
  'method': 'Method',
};

/// Which of the two calibrations the view shows.
enum ExtrinsicsCalibrationTopic { cameraPose, projectorMapping }

class ExtrinsicsCalibrationView extends StatefulWidget {
  const ExtrinsicsCalibrationView({
    super.key,
    required this.backendClient,
    required this.profileName,
    required this.cameraName,
    required this.calibrationTopic,
  });

  final SetupWizardBackendClient backendClient;

  /// A saved profile: the calibration is stored in its extrinsics folder.
  final String profileName;

  /// A name from launch_helpers.CAMERA_DRIVER_REMAPPINGS.
  final String cameraName;
  final ExtrinsicsCalibrationTopic calibrationTopic;

  @override
  State<ExtrinsicsCalibrationView> createState() => _ExtrinsicsCalibrationViewState();
}

class _ExtrinsicsCalibrationViewState extends State<ExtrinsicsCalibrationView> {
  /// Increased whenever the shown camera changes or the view goes away, so loops for an old camera stop.
  int _viewGeneration = 0;

  /// Increased after a run, so the preview starts the camera again (the run's launch stopped it).
  int _previewStartCount = 0;

  ExtrinsicsState? _extrinsicsState;
  String? _extrinsicsStateErrorText;

  final TextEditingController _boardColumnsController =
      TextEditingController(text: '$defaultBoardInnerCornerColumns');
  final TextEditingController _boardRowsController = TextEditingController(text: '$defaultBoardInnerCornerRows');
  final TextEditingController _squareSizeMmController = TextEditingController();
  String? _boardInputErrorText;

  /// The running run's preview id, null while none runs.
  int? _runningRunPreviewId;
  ExtrinsicsCalibrationKind? _runningCalibrationKind;

  /// The end of the latest run, shown until the next one starts.
  ExtrinsicsRunProgress? _finishedRunProgress;
  String? _runErrorText;
  bool _isRequestPending = false;

  @override
  void initState() {
    super.initState();
    _pollExtrinsicsState(_viewGeneration);
  }

  @override
  void didUpdateWidget(ExtrinsicsCalibrationView oldWidget) {
    super.didUpdateWidget(oldWidget);
    final bool isOtherCamera =
        oldWidget.cameraName != widget.cameraName || oldWidget.profileName != widget.profileName;
    if (isOtherCamera || oldWidget.calibrationTopic != widget.calibrationTopic) {
      _stopRunQuietly();
      _viewGeneration += 1;
      setState(() {
        _extrinsicsState = null;
        _extrinsicsStateErrorText = null;
        _finishedRunProgress = null;
        _runErrorText = null;
      });
      _pollExtrinsicsState(_viewGeneration);
    }
  }

  @override
  void dispose() {
    // Leaving the screen ends a run: nobody would see its result
    _stopRunQuietly();
    _viewGeneration += 1;
    _boardColumnsController.dispose();
    _boardRowsController.dispose();
    _squareSizeMmController.dispose();
    super.dispose();
  }

  bool _isStillCurrent(int viewGeneration) {
    return mounted && viewGeneration == _viewGeneration;
  }

  /// Fetches the stored calibration and the offered kinds, again and again while no run goes.
  Future<void> _pollExtrinsicsState(int viewGeneration) async {
    while (_isStillCurrent(viewGeneration)) {
      if (_runningRunPreviewId == null) {
        await _loadExtrinsicsState(viewGeneration);
      }
      await Future<void>.delayed(extrinsicsStatePollInterval);
    }
  }

  Future<void> _loadExtrinsicsState(int viewGeneration) async {
    try {
      final ExtrinsicsState extrinsicsState = await widget.backendClient.fetchExtrinsicsState(
        profileName: widget.profileName,
        cameraName: widget.cameraName,
      );
      if (!_isStillCurrent(viewGeneration)) {
        return;
      }
      setState(() {
        _extrinsicsState = extrinsicsState;
        _extrinsicsStateErrorText = null;
      });
    } catch (error) {
      if (!_isStillCurrent(viewGeneration)) {
        return;
      }
      setState(() {
        _extrinsicsStateErrorText = describeBackendErrorForUser(error);
      });
    }
  }

  /// Ends a running run in the backend without waiting; nothing to do when none runs.
  void _stopRunQuietly() {
    final int? runningRunPreviewId = _runningRunPreviewId;
    if (runningRunPreviewId == null) {
      return;
    }
    _runningRunPreviewId = null;
    widget.backendClient.stopCameraPreview(previewId: runningRunPreviewId).catchError((Object error) {
      // The backend may already be gone, or the run ended meanwhile.
    });
  }

  Future<void> _startPoseWithBoard() async {
    final int? boardColumns = int.tryParse(_boardColumnsController.text.trim());
    final int? boardRows = int.tryParse(_boardRowsController.text.trim());
    final double? squareSizeMm = double.tryParse(_squareSizeMmController.text.trim().replaceAll(',', '.'));
    if (boardColumns == null || boardRows == null || boardColumns < 2 || boardRows < 2) {
      setState(() {
        _boardInputErrorText = 'The inner corners must be whole numbers of at least 2.';
      });
      return;
    }
    if (squareSizeMm == null || squareSizeMm <= 0) {
      setState(() {
        _boardInputErrorText = 'Measure one square of the printed board and enter its size in millimetres.';
      });
      return;
    }
    setState(() {
      _boardInputErrorText = null;
    });
    await _startRun(
      ExtrinsicsCalibrationKind.poseBoard,
      boardInnerCornerColumns: boardColumns,
      boardInnerCornerRows: boardRows,
      squareSizeM: squareSizeMm / 1000,
    );
  }

  Future<void> _startRun(
    ExtrinsicsCalibrationKind calibrationKind, {
    int? boardInnerCornerColumns,
    int? boardInnerCornerRows,
    double? squareSizeM,
  }) async {
    setState(() {
      _isRequestPending = true;
      _runErrorText = null;
      _finishedRunProgress = null;
    });
    final int viewGeneration = _viewGeneration;
    final int runPreviewId;
    try {
      runPreviewId = await widget.backendClient.startExtrinsicsCalibration(
        profileName: widget.profileName,
        cameraName: widget.cameraName,
        calibrationKind: calibrationKind,
        boardInnerCornerColumns: boardInnerCornerColumns,
        boardInnerCornerRows: boardInnerCornerRows,
        squareSizeM: squareSizeM,
      );
    } catch (error) {
      if (_isStillCurrent(viewGeneration)) {
        setState(() {
          _runErrorText = describeBackendErrorForUser(error);
          _isRequestPending = false;
        });
      }
      return;
    }
    if (!_isStillCurrent(viewGeneration)) {
      // Gone meanwhile: nobody will watch this run
      widget.backendClient.stopCameraPreview(previewId: runPreviewId).catchError((Object error) {});
      return;
    }
    setState(() {
      _runningRunPreviewId = runPreviewId;
      _runningCalibrationKind = calibrationKind;
      _isRequestPending = false;
    });
    await _pollRunProgress(viewGeneration, runPreviewId);
  }

  Future<void> _pollRunProgress(int viewGeneration, int runPreviewId) async {
    while (_isStillCurrent(viewGeneration) && _runningRunPreviewId == runPreviewId) {
      await Future<void>.delayed(extrinsicsRunProgressPollInterval);
      final ExtrinsicsRunProgress runProgress;
      try {
        runProgress = await widget.backendClient.fetchExtrinsicsRunProgress();
      } catch (error) {
        // One slow answer must not end the run; the next request tries again
        continue;
      }
      if (!_isStillCurrent(viewGeneration) || _runningRunPreviewId != runPreviewId) {
        return;
      }
      if (runProgress.phase == ExtrinsicsRunPhase.running) {
        continue;
      }
      setState(() {
        _runningRunPreviewId = null;
        _finishedRunProgress = runProgress;
        _previewStartCount += 1;
      });
      await _loadExtrinsicsState(viewGeneration);
      return;
    }
  }

  Future<void> _stopRun() async {
    final int? runningRunPreviewId = _runningRunPreviewId;
    if (runningRunPreviewId == null) {
      return;
    }
    setState(() {
      _isRequestPending = true;
    });
    try {
      await widget.backendClient.stopCameraPreview(previewId: runningRunPreviewId);
    } catch (error) {
      if (mounted) {
        setState(() {
          _runErrorText = describeBackendErrorForUser(error);
        });
      }
    }
    // The progress loop sees the run as stopped and shows it
    if (mounted) {
      setState(() {
        _isRequestPending = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final Widget imageArea = CameraPreviewView(
      key: ValueKey<String>('${widget.cameraName}_$_previewStartCount'),
      backendClient: widget.backendClient,
      cameraName: widget.cameraName,
      profileName: widget.profileName,
    );
    final Widget controlsArea = _buildControlsArea();
    return LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      if (constraints.maxWidth < extrinsicsSideBySideMinimumWidthLogicalPx) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [controlsArea, const SizedBox(height: 16), imageArea],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: imageArea),
          const SizedBox(width: 24),
          Expanded(flex: 2, child: controlsArea),
        ],
      );
    });
  }

  Widget _buildControlsArea() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final ExtrinsicsState? extrinsicsState = _extrinsicsState;
    final List<Widget> controlRows = [];
    if (extrinsicsState == null) {
      String waitingText = 'Reading the profile\'s calibration …';
      final String? extrinsicsStateErrorText = _extrinsicsStateErrorText;
      if (extrinsicsStateErrorText != null) {
        waitingText = '$waitingText ($extrinsicsStateErrorText)';
      }
      controlRows.add(Text(waitingText, style: TextStyle(color: colorScheme.onSurfaceVariant)));
    } else {
      if (widget.calibrationTopic == ExtrinsicsCalibrationTopic.cameraPose) {
        controlRows.addAll(_buildCameraPoseStateRows(extrinsicsState.cameraPose));
      } else {
        controlRows.addAll(_buildProjectionMappingStateRows(extrinsicsState.projectionMapping));
      }
      controlRows.add(const SizedBox(height: 16));
      if (_runningRunPreviewId != null) {
        controlRows.addAll(_buildRunningRows());
      } else if (widget.calibrationTopic == ExtrinsicsCalibrationTopic.cameraPose) {
        controlRows.addAll(_buildCameraPoseStartRows(extrinsicsState));
      } else {
        controlRows.addAll(_buildProjectorStartRows(extrinsicsState));
      }
    }
    controlRows.addAll(_buildFinishedRunRows());
    final String? runErrorText = _runErrorText;
    if (runErrorText != null) {
      controlRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(runErrorText, style: TextStyle(color: colorScheme.error)),
      ));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: controlRows);
  }

  /// A state line with an icon that differs in shape as well as colour.
  Widget _buildStateLine({required bool isGood, required String stateText}) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    Icon stateIcon = Icon(Icons.cancel, color: colorScheme.error);
    if (isGood) {
      stateIcon = Icon(Icons.check_circle, color: Colors.green.shade400);
    }
    return Row(children: [stateIcon, const SizedBox(width: 8), Expanded(child: Text(stateText))]);
  }

  List<Widget> _buildCameraPoseStateRows(CameraPoseSummary cameraPose) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (!cameraPose.isMeasured) {
      final List<Widget> placeholderRows = [
        _buildStateLine(isGood: false, stateText: 'Not measured: the profile uses the placeholder pose.'),
      ];
      if (cameraPose.poseFileErrorText.isNotEmpty) {
        placeholderRows.add(Text(cameraPose.poseFileErrorText, style: TextStyle(color: colorScheme.error)));
      }
      return placeholderRows;
    }
    String poseText = 'Measured';
    if (cameraPose.measuredText.isNotEmpty) {
      poseText = '$poseText (${cameraPose.measuredText.replaceFirst('T', ' ')})';
    }
    final double? heightAboveTableM = cameraPose.heightAboveTableM;
    final double? tiltFromVerticalDeg = cameraPose.tiltFromVerticalDeg;
    final List<String> poseValueTexts = [];
    if (heightAboveTableM != null) {
      poseValueTexts.add('${heightAboveTableM.toStringAsFixed(3)} m above the table');
    }
    if (tiltFromVerticalDeg != null) {
      poseValueTexts.add('tilted ${tiltFromVerticalDeg.toStringAsFixed(1)}° from straight down');
    }
    if (poseValueTexts.isNotEmpty) {
      poseText = '$poseText: ${poseValueTexts.join(', ')}.';
    }
    final List<Widget> poseRows = [_buildStateLine(isGood: true, stateText: poseText)];
    for (final MapEntry<String, String> qualityFigure in cameraPose.qualityFigureByName.entries) {
      final String qualityFigureLabel = poseQualityFigureLabelByName[qualityFigure.key] ?? qualityFigure.key;
      poseRows.add(Padding(
        padding: const EdgeInsets.only(left: 32),
        child: Text('$qualityFigureLabel: ${qualityFigure.value}', style: TextStyle(color: colorScheme.onSurfaceVariant)),
      ));
    }
    return poseRows;
  }

  List<Widget> _buildProjectionMappingStateRows(ProjectionMappingSummary projectionMapping) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (!projectionMapping.isCalibrated) {
      return [
        _buildStateLine(
          isGood: false,
          stateText: 'Not calibrated: projected content does not line up with the table yet.',
        ),
      ];
    }
    String mappingText = 'Calibrated';
    if (projectionMapping.measuredText.isNotEmpty) {
      mappingText = '$mappingText (${projectionMapping.measuredText.replaceFirst('T', ' ')})';
    }
    final double? reprojectionErrorPx = projectionMapping.reprojectionErrorPx;
    if (reprojectionErrorPx != null) {
      mappingText = '$mappingText: markers ${reprojectionErrorPx.toStringAsFixed(2)} projector px off on average.';
    }
    final List<Widget> mappingRows = [_buildStateLine(isGood: true, stateText: mappingText)];
    final List<String> detailTexts = [];
    final int? projectorWidthPx = projectionMapping.projectorWidthPx;
    final int? projectorHeightPx = projectionMapping.projectorHeightPx;
    if (projectorWidthPx != null && projectorHeightPx != null) {
      detailTexts.add('Projector $projectorWidthPx × $projectorHeightPx px');
    }
    if (projectionMapping.hasProjectorCenter) {
      detailTexts.add('Projector centre found');
    }
    for (final String detailText in detailTexts) {
      mappingRows.add(Padding(
        padding: const EdgeInsets.only(left: 32),
        child: Text(detailText, style: TextStyle(color: colorScheme.onSurfaceVariant)),
      ));
    }
    if (projectionMapping.isOlderThanCameraPose) {
      mappingRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Row(children: [
          Icon(Icons.warning_amber, color: colorScheme.error),
          const SizedBox(width: 8),
          const Expanded(
            child: Text('Measured before the current camera pose, on the old table plane: calibrate it again.'),
          ),
        ]),
      ));
    }
    return mappingRows;
  }

  /// The hint why a kind cannot start (packages missing), or null when it can.
  String? _getMissingPackageText(ExtrinsicsState extrinsicsState, ExtrinsicsCalibrationKind calibrationKind) {
    return extrinsicsState.missingPackageTextByCalibrationKind[calibrationKind];
  }

  List<Widget> _buildMissingPackageRows(String? missingPackageText) {
    if (missingPackageText == null) {
      return [];
    }
    return [
      const SizedBox(height: 8),
      Text('Not installed: $missingPackageText', style: TextStyle(color: Theme.of(context).colorScheme.error)),
    ];
  }

  List<Widget> _buildCameraPoseStartRows(ExtrinsicsState extrinsicsState) {
    final String? boardMissingPackageText =
        _getMissingPackageText(extrinsicsState, ExtrinsicsCalibrationKind.poseBoard);
    final bool canStartBoard = !_isRequestPending && boardMissingPackageText == null;
    final List<Widget> startRows = [
      Text('Measure with a checkerboard', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      const Text(
        'Lay the board flat on the table, completely in view, and keep it still. This measures the camera\'s '
        'height and tilt above the table; its position along the table and its turn about the vertical stay '
        'those of the placeholder pose. Needs the lens calibration.',
      ),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(child: _buildNumberField(_boardColumnsController, 'Inner corners across')),
          const SizedBox(width: 12),
          Expanded(child: _buildNumberField(_boardRowsController, 'Inner corners down')),
        ],
      ),
      const SizedBox(height: 12),
      _buildNumberField(_squareSizeMmController, 'Square size in mm (measured on the print)'),
    ];
    final String? boardInputErrorText = _boardInputErrorText;
    if (boardInputErrorText != null) {
      startRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(boardInputErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ));
    }
    startRows.add(const SizedBox(height: 12));
    startRows.add(FilledButton(
      onPressed: canStartBoard ? _startPoseWithBoard : null,
      child: Text(extrinsicsState.cameraPose.isMeasured ? 'Measure again' : 'Measure pose'),
    ));
    startRows.addAll(_buildMissingPackageRows(boardMissingPackageText));

    if (extrinsicsState.availableCalibrationKinds.contains(ExtrinsicsCalibrationKind.poseDepth)) {
      final String? depthMissingPackageText =
          _getMissingPackageText(extrinsicsState, ExtrinsicsCalibrationKind.poseDepth);
      final bool canStartDepth = !_isRequestPending && depthMissingPackageText == null;
      startRows.addAll([
        const SizedBox(height: 24),
        Text('Or measure with depth', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        const Text('Clear the table: the camera fits the table plane in its depth image, no board needed.'),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: canStartDepth ? () => _startRun(ExtrinsicsCalibrationKind.poseDepth) : null,
          child: const Text('Use depth instead'),
        ),
      ]);
      startRows.addAll(_buildMissingPackageRows(depthMissingPackageText));
    }
    return startRows;
  }

  List<Widget> _buildProjectorStartRows(ExtrinsicsState extrinsicsState) {
    final String? mappingMissingPackageText =
        _getMissingPackageText(extrinsicsState, ExtrinsicsCalibrationKind.projectionMapping);
    final bool canStartMapping = !_isRequestPending && mappingMissingPackageText == null;
    final List<Widget> startRows = [
      Text('Projector to table', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      const Text(
        'Clear the table. The projector shows a grid of markers on the profile\'s projector display; keep out '
        'of the light until it ends. Uses the camera pose, so measure that first.',
      ),
      const SizedBox(height: 12),
      FilledButton(
        onPressed: canStartMapping ? () => _startRun(ExtrinsicsCalibrationKind.projectionMapping) : null,
        child: Text(extrinsicsState.projectionMapping.isCalibrated ? 'Calibrate again' : 'Calibrate projector'),
      ),
    ];
    startRows.addAll(_buildMissingPackageRows(mappingMissingPackageText));

    if (extrinsicsState.availableCalibrationKinds.contains(ExtrinsicsCalibrationKind.projectorCenter)) {
      final String? centerMissingPackageText =
          _getMissingPackageText(extrinsicsState, ExtrinsicsCalibrationKind.projectorCenter);
      final bool canStartCenter = !_isRequestPending && centerMissingPackageText == null;
      startRows.addAll([
        const SizedBox(height: 24),
        Text('Projector centre (optional)', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        const Text(
          'Hold a flat board above the table and move it slowly through the projected markers, at different '
          'heights. Needed by the projection mask; calibrating the projector again clears it.',
        ),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: canStartCenter ? () => _startRun(ExtrinsicsCalibrationKind.projectorCenter) : null,
          child: const Text('Find projector centre'),
        ),
      ]);
      startRows.addAll(_buildMissingPackageRows(centerMissingPackageText));
    }
    return startRows;
  }

  List<Widget> _buildRunningRows() {
    String runningText = 'Measuring …';
    switch (_runningCalibrationKind) {
      case ExtrinsicsCalibrationKind.poseBoard:
        runningText = 'Measuring the pose from the board. Keep it still and in view.';
      case ExtrinsicsCalibrationKind.poseDepth:
        runningText = 'Measuring the pose from the table plane. Keep the table clear.';
      case ExtrinsicsCalibrationKind.projectionMapping:
        runningText = 'The projector shows the markers. Keep the table clear and out of the light.';
      case ExtrinsicsCalibrationKind.projectorCenter:
        runningText = 'Move the board slowly through the projected markers, at different heights.';
      case null:
        break;
    }
    return [
      const LinearProgressIndicator(),
      const SizedBox(height: 8),
      Text(runningText),
      const SizedBox(height: 12),
      OutlinedButton(onPressed: _isRequestPending ? null : _stopRun, child: const Text('Stop')),
    ];
  }

  List<Widget> _buildFinishedRunRows() {
    final ExtrinsicsRunProgress? finishedRunProgress = _finishedRunProgress;
    if (finishedRunProgress == null) {
      return [];
    }
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> finishedRows = [const SizedBox(height: 16)];
    switch (finishedRunProgress.phase) {
      case ExtrinsicsRunPhase.stored:
        finishedRows.add(Text('Stored in the profile.', style: TextStyle(color: Colors.green.shade400)));
        return finishedRows;
      case ExtrinsicsRunPhase.stopped:
        finishedRows.add(const Text('Stopped; nothing was stored.'));
      case ExtrinsicsRunPhase.failed:
        finishedRows.add(Text('Nothing was stored. The calibration said:', style: TextStyle(color: colorScheme.error)));
      case ExtrinsicsRunPhase.running:
        return [];
    }
    if (finishedRunProgress.logLines.isNotEmpty) {
      finishedRows.add(const SizedBox(height: 4));
      finishedRows.add(SelectableText(
        finishedRunProgress.logLines.join('\n'),
        style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
      ));
    }
    return finishedRows;
  }

  Widget _buildNumberField(TextEditingController fieldController, String fieldLabel) {
    return TextField(
      controller: fieldController,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: fieldLabel, border: const OutlineInputBorder(), isDense: true),
    );
  }
}
