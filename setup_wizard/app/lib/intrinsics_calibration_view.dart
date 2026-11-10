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

import 'camera_preview_view.dart';
import 'intrinsics_api.dart';
import 'setup_wizard_backend_client.dart';

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

/// How cameracalibrator names the variety of board poses, and how the app explains it.
const Map<String, String> poseParameterLabelByName = {
  'X': 'Left – right',
  'Y': 'Top – bottom',
  'Size': 'Near – far',
  'Skew': 'Tilt',
};

class IntrinsicsCalibrationView extends StatefulWidget {
  const IntrinsicsCalibrationView({
    super.key,
    required this.backendClient,
    required this.cameraName,
    this.profileName,
  });

  final SetupWizardBackendClient backendClient;

  /// A name from launch_helpers.CAMERA_DRIVER_REMAPPINGS.
  final String cameraName;

  /// The saved profile the camera starts with, which decides where its calibration file is; null for the shared
  /// intrinsics folder of launches without a profile.
  final String? profileName;

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

  final TextEditingController _boardColumnsController =
      TextEditingController(text: '$defaultBoardInnerCornerColumns');
  final TextEditingController _boardRowsController = TextEditingController(text: '$defaultBoardInnerCornerRows');
  final TextEditingController _squareSizeMmController = TextEditingController();
  String? _boardInputErrorText;

  /// True from starting a calibration until it is saved, discarded or the camera changes.
  bool _isCalibrationRunning = false;
  IntrinsicsCalibrationProgress? _calibrationProgress;
  Uint8List? _calibrationFrameJpegBytes;
  String? _calibrationActionErrorText;
  String? _savedStatusText;
  bool _isRequestPending = false;

  @override
  void initState() {
    super.initState();
    _loadCameraIntrinsicsState(_viewGeneration);
  }

  @override
  void didUpdateWidget(IntrinsicsCalibrationView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.cameraName != widget.cameraName || oldWidget.profileName != widget.profileName) {
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
      _endCalibrationQuietly();
      setState(() {
        _savedStatusText = saveStatusText.isEmpty ? 'Saved.' : 'Saved: $saveStatusText';
        _cameraIntrinsicsState = null;
      });
      // The driver now publishes the new calibration; show where it comes from.
      _loadCameraIntrinsicsState(_viewGeneration);
    });
  }

  void _discardCalibration() {
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
      cameraName: widget.cameraName,
      profileName: widget.profileName,
    );
    final List<Widget> imageLayers = [Offstage(offstage: _isCalibrationRunning, child: previewView)];
    if (_isCalibrationRunning) {
      final Uint8List? calibrationFrameJpegBytes = _calibrationFrameJpegBytes;
      Widget calibrationImage = const Text('Waiting for the first frame …');
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
      String waitingText = 'Checking the camera\'s lens calibration …';
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
        stateText = 'This camera publishes no camera_info, so a lens calibration does not apply.';
      case IntrinsicsSource.uncalibrated:
        stateIcon = Icon(Icons.cancel, color: colorScheme.error);
        stateText = 'Needs a calibration: the camera has no lens calibration yet.';
      case IntrinsicsSource.calibrationFile:
        stateIcon = Icon(Icons.check_circle, color: Colors.green.shade400);
        stateText = 'Calibrated (${cameraIntrinsicsState.calibrationFileModifiedIso.replaceFirst('T', ' ')}).';
      case IntrinsicsSource.camera:
        stateIcon = Icon(Icons.check_circle_outline, color: Colors.green.shade400);
        stateText = 'Uses the calibration the camera reports itself (e.g. from the factory).';
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
        'This camera brings its own lens calibration (e.g. from the factory). It is protected: the app does not '
        'offer to replace it.',
        style: TextStyle(color: colorScheme.onSurfaceVariant),
      ));
    } else if (!cameraIntrinsicsState.canStoreCalibration) {
      // Special case: a driver without set_camera_info (e.g. the Azure Kinect's) cannot store a calibration.
      controlRows.add(Text(
        'This camera\'s driver cannot store a calibration (it offers no set_camera_info service), so it cannot be '
        'calibrated from here.',
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
    String startButtonText = 'Start calibration';
    if (cameraIntrinsicsState.intrinsicsSource != IntrinsicsSource.uncalibrated) {
      startButtonText = 'Calibrate again';
    }
    final List<Widget> formRows = [
      Text('Checkerboard', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      const Text('Inner corners are where four squares meet: a board of 9 × 7 squares has 8 × 6.'),
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
      return [const Text('Starting the calibration …')];
    }
    switch (calibrationProgress.phase) {
      case IntrinsicsCalibrationPhase.collecting:
        return _buildCollectingRows(calibrationProgress);
      case IntrinsicsCalibrationPhase.calibrating:
        return [
          const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Text('Computing the calibration from ${calibrationProgress.sampleCount} views …'),
        ];
      case IntrinsicsCalibrationPhase.calibrated:
        return _buildCalibratedRows(calibrationProgress);
      case IntrinsicsCalibrationPhase.failed:
        return [
          Text(calibrationProgress.errorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _discardCalibration, child: const Text('Back')),
        ];
    }
  }

  List<Widget> _buildCollectingRows(IntrinsicsCalibrationProgress calibrationProgress) {
    final List<Widget> collectingRows = [
      const Text(
        'Hold the board in front of the camera and move it: to every edge and corner of the image, near and far, '
        'and tilted. A view counts when the board is found and differs from the earlier ones.',
      ),
      const SizedBox(height: 12),
    ];
    for (final MapEntry<String, String> poseParameterLabel in poseParameterLabelByName.entries) {
      final double progressFraction =
          calibrationProgress.progressFractionByPoseParameter[poseParameterLabel.key] ?? 0;
      collectingRows.add(_buildCoverageBar(poseParameterLabel.value, progressFraction));
    }
    collectingRows.add(const SizedBox(height: 8));
    collectingRows.add(Text('${calibrationProgress.sampleCount} views'));
    collectingRows.add(const SizedBox(height: 12));
    collectingRows.add(Row(
      children: [
        FilledButton(
          onPressed: calibrationProgress.isGoodEnough && !_isRequestPending
              ? () => _runCalibrationAction(widget.backendClient.calibrateIntrinsics)
              : null,
          child: const Text('Calibrate'),
        ),
        const SizedBox(width: 12),
        TextButton(onPressed: _discardCalibration, child: const Text('Cancel')),
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
    String linearErrorText = 'Hold the board in view to check the result.';
    if (linearErrorPx != null) {
      linearErrorText = 'Straightness of the board\'s lines now: ${linearErrorPx.toStringAsFixed(2)} px off '
          '(smaller is better).';
    }
    final List<Widget> calibratedRows = [
      Text('Calibrated from ${calibrationProgress.sampleCount} views.', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      const Text('The image is shown undistorted now: straight edges should look straight.'),
      const SizedBox(height: 8),
    ];
    if (focalLengthXPx != null && focalLengthYPx != null) {
      calibratedRows.add(Text(
        'Focal length: ${focalLengthXPx.toStringAsFixed(1)} × ${focalLengthYPx.toStringAsFixed(1)} px',
      ));
    }
    calibratedRows.add(Text(linearErrorText));
    calibratedRows.add(const SizedBox(height: 12));
    calibratedRows.add(Row(
      children: [
        FilledButton(onPressed: _isRequestPending ? null : _saveCalibration, child: const Text('Save')),
        const SizedBox(width: 12),
        TextButton(onPressed: _discardCalibration, child: const Text('Discard')),
      ],
    ));
    return calibratedRows;
  }
}
