// Written by Claude Code
//
// One camera's lens (intrinsic) calibration: where its intrinsics come from now (no camera_info, uncalibrated,
// calibration file, the camera itself), and, if the driver can store one, a calibration with a printed
// checkerboard. A camera that brings its own calibration (e.g. from the factory) is never offered one, so it cannot
// be replaced by accident. While it collects views, the live image with the detected board replaces the preview and bars show
// how much of the needed variety (left-right, top-bottom, distance, tilt) the views cover; "Calibrate" unlocks once
// there are enough. The result is saved by the driver itself (set_camera_info). The preview stays mounted
// underneath, so the camera keeps running. With a profile, the camera starts with it and the driver stores the
// calibration in that profile's intrinsics folder.

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../data/services/camera_preview_api.dart';
import '../cameras/camera_preview_view.dart';
import '../../data/services/intrinsics_api.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';

/// Pause between two requests for the image with the detected board.
const Duration intrinsicsFramePollInterval = Duration(milliseconds: 150);

/// Every this many frame requests, the progress is fetched too.
const int intrinsicsProgressPollEveryFrameCount = 3;

/// Pause before asking again while the camera does not report its intrinsics yet.
const Duration intrinsicsStateRetryInterval = Duration(seconds: 1);

/// Below this width the controls go under the image instead of next to it.
const double intrinsicsSideBySideMinimumWidthLogicalPx = 900;

/// Inner corners the board fields start with, until the user enters those of their own printed board.
const int defaultBoardInnerCornerColumns = 8;
const int defaultBoardInnerCornerRows = 6;

/// The checkerboard last typed on a calibration page (lens or camera pose), so the next page, e.g. the next camera,
/// starts with it instead of the defaults. Simplification: kept only while the app runs. Upgrade: store it in the
/// profile if the same board should come back after a restart.
class RememberedCheckerboard {
  static String innerCornerColumnsText = '$defaultBoardInnerCornerColumns';
  static String innerCornerRowsText = '$defaultBoardInnerCornerRows';
  static String squareSizeMmText = '';

  /// Fills the three fields with the remembered board and remembers every later change of them.
  static void connectFields(
    TextEditingController columnsController,
    TextEditingController rowsController,
    TextEditingController squareSizeMmController,
  ) {
    columnsController.text = innerCornerColumnsText;
    rowsController.text = innerCornerRowsText;
    squareSizeMmController.text = squareSizeMmText;
    columnsController.addListener(() {
      innerCornerColumnsText = columnsController.text;
    });
    rowsController.addListener(() {
      innerCornerRowsText = rowsController.text;
    });
    squareSizeMmController.addListener(() {
      squareSizeMmText = squareSizeMmController.text;
    });
  }
}

/// How cameracalibrator names the variety of board poses, and how the app explains it.
const Map<String, String> poseParameterLabelByName = {
  'X': WizardStrings.poseCoverageLeftRightLabel,
  'Y': WizardStrings.poseCoverageTopBottomLabel,
  'Size': WizardStrings.poseCoverageNearFarLabel,
  'Skew': WizardStrings.poseCoverageTiltLabel,
};

class IntrinsicsCalibrationView extends StatefulWidget {
  const IntrinsicsCalibrationView({
    super.key,
    required this.backendClient,
    required this.previewCamera,
  });

  final SetupWizardBackendClient backendClient;

  /// The camera to calibrate. A profile's camera stores its calibration in the profile's intrinsics folder, a unit
  /// without a profile in the shared one.
  final PreviewCameraChoice previewCamera;

  @override
  State<IntrinsicsCalibrationView> createState() => _IntrinsicsCalibrationViewState();
}

class _IntrinsicsCalibrationViewState extends State<IntrinsicsCalibrationView> {
  // Keeps the preview, and with it the running camera, when the layout switches between side by side and stacked.
  final GlobalKey _cameraPreviewViewKey = GlobalKey();

  /// Increased whenever the shown camera changes or the view goes away, so loops for an old camera stop.
  int _viewGeneration = 0;

  CameraIntrinsicsState? _cameraIntrinsicsState;
  String? _intrinsicsStateErrorText;

  final TextEditingController _boardColumnsController = TextEditingController();
  final TextEditingController _boardRowsController = TextEditingController();
  final TextEditingController _squareSizeMmController = TextEditingController();
  String? _boardInputErrorText;

  /// True from starting a calibration until it is closed or the camera changes.
  bool _isCalibrationRunning = false;
  IntrinsicsCalibrationProgress? _calibrationProgress;
  Uint8List? _calibrationFrameJpegBytes;
  String? _calibrationActionErrorText;
  String? _savedStatusText;
  bool _isRequestPending = false;

  /// True once the running calibration's result was sent for saving, so it is saved once.
  bool _isCalibrationResultSaveStarted = false;

  @override
  void initState() {
    super.initState();
    RememberedCheckerboard.connectFields(_boardColumnsController, _boardRowsController, _squareSizeMmController);
    _loadCameraIntrinsicsState(_viewGeneration);
  }

  @override
  void didUpdateWidget(IntrinsicsCalibrationView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.previewCamera != widget.previewCamera) {
      _endCalibrationQuietly();
      _viewGeneration += 1;
      setState(() {
        _cameraIntrinsicsState = null;
        _intrinsicsStateErrorText = null;
        _savedStatusText = null;
      });
      _loadCameraIntrinsicsState(_viewGeneration);
    }
  }

  @override
  void dispose() {
    _endCalibrationQuietly();
    _viewGeneration += 1;
    _boardColumnsController.dispose();
    _boardRowsController.dispose();
    _squareSizeMmController.dispose();
    super.dispose();
  }

  bool _isStillCurrent(int viewGeneration) {
    return mounted && viewGeneration == _viewGeneration;
  }

  /// Asks until the running camera reports where its intrinsics come from.
  Future<void> _loadCameraIntrinsicsState(int viewGeneration) async {
    while (_isStillCurrent(viewGeneration)) {
      try {
        final CameraIntrinsicsState? cameraIntrinsicsState = await widget.backendClient.fetchCameraIntrinsicsState();
        if (!_isStillCurrent(viewGeneration)) {
          return;
        }
        if (cameraIntrinsicsState != null) {
          setState(() {
            _cameraIntrinsicsState = cameraIntrinsicsState;
            _intrinsicsStateErrorText = null;
          });
          return;
        }
      } catch (error) {
        // Usually the preview has not started the camera yet; ask again.
        if (!_isStillCurrent(viewGeneration)) {
          return;
        }
        setState(() {
          _intrinsicsStateErrorText = describeBackendErrorForUser(error);
        });
      }
      await Future<void>.delayed(intrinsicsStateRetryInterval);
    }
  }

  /// Ends a running calibration in the backend without waiting; nothing to do when none runs.
  void _endCalibrationQuietly() {
    if (!_isCalibrationRunning) {
      return;
    }
    _isCalibrationRunning = false;
    widget.backendClient.stopIntrinsicsCalibration().catchError((Object error) {
      // The backend may already be gone, or the calibration ended with the camera.
    });
  }

  Future<void> _startCalibration() async {
    final int? boardColumns = int.tryParse(_boardColumnsController.text.trim());
    final int? boardRows = int.tryParse(_boardRowsController.text.trim());
    final double? squareSizeMm = double.tryParse(_squareSizeMmController.text.trim().replaceAll(',', '.'));
    if (boardColumns == null || boardRows == null || boardColumns < 2 || boardRows < 2) {
      setState(() {
        _boardInputErrorText = WizardStrings.boardInnerCornersInvalidErrorText;
      });
      return;
    }
    if (squareSizeMm == null || squareSizeMm <= 0) {
      setState(() {
        _boardInputErrorText = WizardStrings.boardSquareSizeMissingErrorText;
      });
      return;
    }
    setState(() {
      _boardInputErrorText = null;
      _calibrationActionErrorText = null;
      _savedStatusText = null;
      _isRequestPending = true;
    });
    final int viewGeneration = _viewGeneration;
    try {
      await widget.backendClient.startIntrinsicsCalibration(
        boardInnerCornerColumns: boardColumns,
        boardInnerCornerRows: boardRows,
        squareSizeM: squareSizeMm / 1000,
      );
    } catch (error) {
      if (_isStillCurrent(viewGeneration)) {
        setState(() {
          _calibrationActionErrorText = describeBackendErrorForUser(error);
          _isRequestPending = false;
        });
      }
      return;
    }
    if (!_isStillCurrent(viewGeneration)) {
      return;
    }
    setState(() {
      _isCalibrationRunning = true;
      _isCalibrationResultSaveStarted = false;
      _calibrationProgress = null;
      _calibrationFrameJpegBytes = null;
      _isRequestPending = false;
    });
    await _pollCalibration(viewGeneration);
  }

  /// Fetches the image with the detected board and, less often, the progress, while the calibration runs.
  Future<void> _pollCalibration(int viewGeneration) async {
    int frameRequestCount = 0;
    while (_isStillCurrent(viewGeneration) && _isCalibrationRunning) {
      try {
        final Uint8List? calibrationFrameJpegBytes = await widget.backendClient.fetchIntrinsicsCalibrationFrame();
        IntrinsicsCalibrationProgress? calibrationProgress;
        if (frameRequestCount % intrinsicsProgressPollEveryFrameCount == 0) {
          calibrationProgress = await widget.backendClient.fetchIntrinsicsCalibrationProgress();
        }
        frameRequestCount += 1;
        if (!_isStillCurrent(viewGeneration) || !_isCalibrationRunning) {
          return;
        }
        setState(() {
          if (calibrationFrameJpegBytes != null) {
            _calibrationFrameJpegBytes = calibrationFrameJpegBytes;
          }
          if (calibrationProgress != null) {
            _calibrationProgress = calibrationProgress;
          }
        });
        // Saved as soon as it is computed, like the camera pose; the result stays shown for checking
        final bool isResultToSave = calibrationProgress?.phase == IntrinsicsCalibrationPhase.calibrated;
        if (isResultToSave && !_isCalibrationResultSaveStarted) {
          _isCalibrationResultSaveStarted = true;
          _saveCalibration();
        }
      } catch (error) {
        if (_isStillCurrent(viewGeneration)) {
          setState(() {
            _isCalibrationRunning = false;
            _calibrationActionErrorText = describeBackendErrorForUser(error);
          });
        }
        return;
      }
      await Future<void>.delayed(intrinsicsFramePollInterval);
    }
  }

  Future<void> _runCalibrationAction(Future<void> Function() calibrationAction) async {
    setState(() {
      _calibrationActionErrorText = null;
      _isRequestPending = true;
    });
    try {
      await calibrationAction();
    } catch (error) {
      if (mounted) {
        setState(() {
          _calibrationActionErrorText = describeBackendErrorForUser(error);
        });
      }
    }
    if (mounted) {
      setState(() {
        _isRequestPending = false;
      });
    }
  }

  Future<void> _saveCalibration() async {
    await _runCalibrationAction(() async {
      final String saveStatusText = await widget.backendClient.saveIntrinsicsCalibration();
      if (!mounted) {
        return;
      }
      setState(() {
        _savedStatusText = saveStatusText.isEmpty
            ? WizardStrings.lensCalibrationSavedText
            : WizardStrings.getLensCalibrationSavedText(saveStatusText: saveStatusText);
        _cameraIntrinsicsState = null;
      });
      // The driver now publishes the new calibration; show where it comes from.
      _loadCameraIntrinsicsState(_viewGeneration);
    });
  }

  void _closeCalibration() {
    _endCalibrationQuietly();
    setState(() {
      _calibrationProgress = null;
      _calibrationFrameJpegBytes = null;
      _calibrationActionErrorText = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> viewRows = [_buildIntrinsicsStateRow(), const SizedBox(height: 12)];
    final Widget imageArea = _buildImageArea();
    final Widget controlsArea = _buildControlsArea();
    viewRows.add(LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      if (constraints.maxWidth < intrinsicsSideBySideMinimumWidthLogicalPx) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [imageArea, const SizedBox(height: 16), controlsArea],
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
    }));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: viewRows);
  }

  /// The camera's preview, replaced by the image with the detected board while a calibration runs. The preview
  /// stays mounted (Offstage), so it keeps the camera running.
  Widget _buildImageArea() {
    final Widget previewView = CameraPreviewView(
      key: _cameraPreviewViewKey,
      backendClient: widget.backendClient,
      previewCamera: widget.previewCamera,
    );
    final List<Widget> imageLayers = [Offstage(offstage: _isCalibrationRunning, child: previewView)];
    if (_isCalibrationRunning) {
      final Uint8List? calibrationFrameJpegBytes = _calibrationFrameJpegBytes;
      Widget calibrationImage = const Text(WizardStrings.waitingForFirstFrameText);
      if (calibrationFrameJpegBytes != null) {
        calibrationImage = Image.memory(calibrationFrameJpegBytes, gaplessPlayback: true, fit: BoxFit.contain);
      }
      imageLayers.add(SizedBox(height: singleFeedHeightLogicalPx, child: Align(alignment: Alignment.topLeft, child: calibrationImage)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: imageLayers);
  }

  /// Where the intrinsics come from, with an icon that differs in shape as well as colour.
  Widget _buildIntrinsicsStateRow() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final CameraIntrinsicsState? cameraIntrinsicsState = _cameraIntrinsicsState;
    if (cameraIntrinsicsState == null) {
      String waitingText = WizardStrings.checkingLensCalibrationText;
      final String? intrinsicsStateErrorText = _intrinsicsStateErrorText;
      if (intrinsicsStateErrorText != null) {
        waitingText = '$waitingText ($intrinsicsStateErrorText)';
      }
      return Text(waitingText, style: TextStyle(color: colorScheme.onSurfaceVariant));
    }

    final Icon stateIcon;
    final String stateText;
    switch (cameraIntrinsicsState.intrinsicsSource) {
      case IntrinsicsSource.noCameraInfo:
        stateIcon = Icon(Icons.block, color: colorScheme.onSurfaceVariant);
        stateText = WizardStrings.cameraWithoutCameraInfoText;
      case IntrinsicsSource.uncalibrated:
        stateIcon = Icon(Icons.cancel, color: colorScheme.error);
        stateText = WizardStrings.lensNeedsCalibrationText;
      case IntrinsicsSource.calibrationFile:
        stateIcon = Icon(Icons.check_circle, color: Colors.green.shade400);
        stateText = WizardStrings.getLensCalibratedText(
          calibrationFileModifiedIso: cameraIntrinsicsState.calibrationFileModifiedIso,
        );
      case IntrinsicsSource.camera:
        stateIcon = Icon(Icons.check_circle_outline, color: Colors.green.shade400);
        stateText = WizardStrings.lensCalibrationFromCameraText;
    }
    final List<Widget> stateRows = [
      Row(children: [stateIcon, const SizedBox(width: 8), Expanded(child: Text(stateText))]),
    ];
    final String? savedStatusText = _savedStatusText;
    if (savedStatusText != null) {
      stateRows.add(Text(savedStatusText, style: TextStyle(color: Colors.green.shade400)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: stateRows);
  }

  Widget _buildControlsArea() {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> controlRows = [];
    final CameraIntrinsicsState? cameraIntrinsicsState = _cameraIntrinsicsState;
    if (_isCalibrationRunning) {
      controlRows.addAll(_buildCalibrationProgressRows());
    } else if (cameraIntrinsicsState == null) {
      // The state row says what is happening.
    } else if (cameraIntrinsicsState.intrinsicsSource == IntrinsicsSource.noCameraInfo) {
      // Nothing to calibrate.
    } else if (cameraIntrinsicsState.intrinsicsSource == IntrinsicsSource.camera) {
      // Never offered: a stored calibration would replace the camera's own for good (the backend refuses too).
      controlRows.add(Text(
        WizardStrings.lensCalibrationProtectedText,
        style: TextStyle(color: colorScheme.onSurfaceVariant),
      ));
    } else if (!cameraIntrinsicsState.canStoreCalibration) {
      // Special case: a driver without set_camera_info (e.g. the Azure Kinect's) cannot store a calibration.
      controlRows.add(Text(
        WizardStrings.lensCalibrationNotStorableText,
        style: TextStyle(color: colorScheme.onSurfaceVariant),
      ));
    } else {
      controlRows.addAll(_buildBoardFormRows(cameraIntrinsicsState));
    }
    final String? calibrationActionErrorText = _calibrationActionErrorText;
    if (calibrationActionErrorText != null) {
      controlRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(calibrationActionErrorText, style: TextStyle(color: colorScheme.error)),
      ));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: controlRows);
  }

  List<Widget> _buildBoardFormRows(CameraIntrinsicsState cameraIntrinsicsState) {
    String startButtonText = WizardStrings.startCalibrationButtonLabel;
    if (cameraIntrinsicsState.intrinsicsSource != IntrinsicsSource.uncalibrated) {
      startButtonText = WizardStrings.calibrateAgainButtonLabel;
    }
    final List<Widget> formRows = [
      Text(WizardStrings.checkerboardHeading, style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      const Text(WizardStrings.checkerboardInnerCornersText),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(child: _buildNumberField(_boardColumnsController, WizardStrings.boardInnerCornersAcrossLabel)),
          const SizedBox(width: 12),
          Expanded(child: _buildNumberField(_boardRowsController, WizardStrings.boardInnerCornersDownLabel)),
        ],
      ),
      const SizedBox(height: 12),
      _buildNumberField(_squareSizeMmController, WizardStrings.boardSquareSizeMmLabel),
    ];
    final String? boardInputErrorText = _boardInputErrorText;
    if (boardInputErrorText != null) {
      formRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(boardInputErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ));
    }
    formRows.add(const SizedBox(height: 12));
    formRows.add(FilledButton(onPressed: _isRequestPending ? null : _startCalibration, child: Text(startButtonText)));
    return formRows;
  }

  Widget _buildNumberField(TextEditingController fieldController, String fieldLabel) {
    return TextField(
      controller: fieldController,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: fieldLabel, border: const OutlineInputBorder(), isDense: true),
    );
  }

  List<Widget> _buildCalibrationProgressRows() {
    final IntrinsicsCalibrationProgress? calibrationProgress = _calibrationProgress;
    if (calibrationProgress == null) {
      return [const Text(WizardStrings.startingCalibrationText)];
    }
    switch (calibrationProgress.phase) {
      case IntrinsicsCalibrationPhase.collecting:
        return _buildCollectingRows(calibrationProgress);
      case IntrinsicsCalibrationPhase.calibrating:
        return [
          const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Text(WizardStrings.getComputingCalibrationText(sampleCount: calibrationProgress.sampleCount)),
        ];
      case IntrinsicsCalibrationPhase.calibrated:
        return _buildCalibratedRows(calibrationProgress);
      case IntrinsicsCalibrationPhase.failed:
        return [
          Text(calibrationProgress.errorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _closeCalibration, child: const Text(WizardStrings.backButtonLabel)),
        ];
    }
  }

  List<Widget> _buildCollectingRows(IntrinsicsCalibrationProgress calibrationProgress) {
    final List<Widget> collectingRows = [
      const Text(
        WizardStrings.moveBoardInstructionsText,
      ),
      const SizedBox(height: 12),
    ];
    for (final MapEntry<String, String> poseParameterLabel in poseParameterLabelByName.entries) {
      final double progressFraction =
          calibrationProgress.progressFractionByPoseParameter[poseParameterLabel.key] ?? 0;
      collectingRows.add(_buildCoverageBar(poseParameterLabel.value, progressFraction));
    }
    collectingRows.add(const SizedBox(height: 8));
    collectingRows.add(Text(WizardStrings.getCalibrationViewCountText(sampleCount: calibrationProgress.sampleCount)));
    collectingRows.add(const SizedBox(height: 12));
    collectingRows.add(Row(
      children: [
        FilledButton(
          onPressed: calibrationProgress.isGoodEnough && !_isRequestPending
              ? () => _runCalibrationAction(widget.backendClient.calibrateIntrinsics)
              : null,
          child: const Text(WizardStrings.calibrateButtonLabel),
        ),
        const SizedBox(width: 12),
        TextButton(onPressed: _closeCalibration, child: const Text(WizardStrings.cancelButtonLabel)),
      ],
    ));
    return collectingRows;
  }

  /// A label, a bar, and a check once this kind of variety is covered.
  Widget _buildCoverageBar(String barLabel, double progressFraction) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final bool isCovered = progressFraction >= 1;
    final Color barColor = isCovered ? Colors.green.shade400 : colorScheme.error;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(width: 110, child: Text(barLabel)),
          Expanded(child: LinearProgressIndicator(value: progressFraction, color: barColor, minHeight: 8)),
          const SizedBox(width: 8),
          Icon(isCovered ? Icons.check : Icons.more_horiz, size: 18, color: barColor),
        ],
      ),
    );
  }

  List<Widget> _buildCalibratedRows(IntrinsicsCalibrationProgress calibrationProgress) {
    final double? focalLengthXPx = calibrationProgress.focalLengthXPx;
    final double? focalLengthYPx = calibrationProgress.focalLengthYPx;
    final double? linearErrorPx = calibrationProgress.linearErrorPx;
    String linearErrorText = WizardStrings.holdBoardToCheckText;
    if (linearErrorPx != null) {
      linearErrorText = WizardStrings.getLineStraightnessText(linearErrorPx: linearErrorPx);
    }
    final List<Widget> calibratedRows = [
      Text(
        WizardStrings.getCalibratedFromViewsText(sampleCount: calibrationProgress.sampleCount),
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const SizedBox(height: 4),
      const Text(WizardStrings.undistortedImageText),
      const SizedBox(height: 8),
    ];
    if (focalLengthXPx != null && focalLengthYPx != null) {
      calibratedRows.add(Text(
        WizardStrings.getFocalLengthText(focalLengthXPx: focalLengthXPx, focalLengthYPx: focalLengthYPx),
      ));
    }
    calibratedRows.add(Text(linearErrorText));
    if (_isRequestPending) {
      calibratedRows.add(const Text(WizardStrings.savingCalibrationText));
    }
    calibratedRows.add(const SizedBox(height: 12));
    calibratedRows.add(FilledButton(onPressed: _closeCalibration, child: const Text(WizardStrings.closeButtonLabel)));
    return calibratedRows;
  }
}
