// Written by Claude Code
//
// Helps focus the previewed camera: a sharpness bar with a mark at the best value so far, and the image centre where
// the sharpness is measured, enlarged with every camera pixel as a block, to judge single-pixel edges by eye. Works
// however the camera's focus is changed (a driver setting, a ring on the lens, a control on the device): change the
// focus until the bar reaches the mark and gets no higher. The camera itself is started by the preview next to it (CameraPreviewView).

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../data/services/camera_preview_api.dart';
import '../../data/services/focus_api.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../../config/wizard_strings.dart';

/// Pause between two measurements: often enough to follow a turning lens ring without flooding the backend.
const Duration focusMeasurementPollInterval = Duration(milliseconds: 200);

/// Pause before measuring again after a request failed, e.g. while the camera is still starting.
const Duration focusMeasurementRetryInterval = Duration(seconds: 1);

/// The bar's full length as a multiple of the best value, so the best mark sits at 80 % and a sharper image has room
/// to grow past it.
const double focusBarFullScaleToPeakRatio = 1.25;

/// Side of the enlarged centre crop on screen.
const double focusCenterCropSideLogicalPx = 360;

class FocusAssistView extends StatefulWidget {
  const FocusAssistView({
    super.key,
    required this.backendClient,
    required this.previewCamera,
    this.measuredAreaNotifier,
  });

  final SetupWizardBackendClient backendClient;

  /// The camera being measured; another camera clears the shown measurement and crop.
  final PreviewCameraChoice previewCamera;

  /// Receives where the sharpness is measured, so the preview can frame that area in the camera image.
  final ValueNotifier<FocusMeasuredArea?>? measuredAreaNotifier;

  @override
  State<FocusAssistView> createState() => _FocusAssistViewState();
}

class _FocusAssistViewState extends State<FocusAssistView> {
  FocusMeasurement? _focusMeasurement;
  Uint8List? _centerCropPngBytes;

  /// Set while measuring fails, e.g. before the camera runs; the view keeps trying.
  String? _measurementErrorText;

  @override
  void initState() {
    super.initState();
    _pollMeasurements();
  }

  @override
  void didUpdateWidget(FocusAssistView oldWidget) {
    super.didUpdateWidget(oldWidget);
    final bool isOtherCamera = oldWidget.previewCamera.runningCameraName != widget.previewCamera.runningCameraName ||
        oldWidget.previewCamera.profileName != widget.previewCamera.profileName;
    if (isOtherCamera) {
      widget.measuredAreaNotifier?.value = null;
      setState(() {
        _focusMeasurement = null;
        _centerCropPngBytes = null;
      });
    }
  }

  /// Simplification: polls the backend like the preview frames. Upgrade: push measurements over a WebSocket.
  Future<void> _pollMeasurements() async {
    while (mounted) {
      final FocusMeasurement focusMeasurement;
      final Uint8List? centerCropPngBytes;
      try {
        focusMeasurement = await widget.backendClient.fetchFocusMeasurement();
        centerCropPngBytes = await widget.backendClient.fetchFocusCenterCrop();
      } catch (error) {
        if (!mounted) {
          return;
        }
        setState(() {
          _measurementErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
        });
        await Future<void>.delayed(focusMeasurementRetryInterval);
        continue;
      }
      if (!mounted) {
        return;
      }
      widget.measuredAreaNotifier?.value = focusMeasurement.measuredArea;
      setState(() {
        _focusMeasurement = focusMeasurement;
        _measurementErrorText = null;
        // Null: no crop measured for the running camera yet (e.g. a new camera before its first frame), so the
        // last one, possibly of another camera, must not stay
        _centerCropPngBytes = centerCropPngBytes;
      });
      await Future<void>.delayed(focusMeasurementPollInterval);
    }
  }

  Future<void> _resetPeak() async {
    try {
      await widget.backendClient.resetFocusPeak();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _measurementErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> scoreRows = [
      Text(WizardStrings.focusHeading, style: textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        WizardStrings.focusInstructionsText,
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 12),
      ..._buildScoreRows(context),
    ];
    final String? measurementErrorText = _measurementErrorText;
    if (measurementErrorText != null) {
      scoreRows.add(const SizedBox(height: 8));
      scoreRows.add(Text(
        WizardStrings.getFocusMeasurementErrorText(measurementErrorText: measurementErrorText),
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ));
    }
    return Wrap(
      spacing: 24,
      runSpacing: 16,
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: scoreRows),
        ),
        _buildCenterCrop(context),
      ],
    );
  }

  List<Widget> _buildScoreRows(BuildContext context) {
    final double? sharpness = _focusMeasurement?.sharpness;
    final double? peakSharpness = _focusMeasurement?.peakSharpness;
    if (sharpness == null || peakSharpness == null) {
      return [const Text(WizardStrings.measuringText)];
    }
    return [
      _buildSharpnessBar(context, sharpness, peakSharpness),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(
            child: Text(WizardStrings.getSharpnessText(sharpness: sharpness, peakSharpness: peakSharpness)),
          ),
          TextButton.icon(
            onPressed: _resetPeak,
            icon: const Icon(Icons.restart_alt),
            label: const Text(WizardStrings.resetBestSharpnessButtonLabel),
          ),
        ],
      ),
    ];
  }

  Widget _buildSharpnessBar(BuildContext context, double sharpness, double peakSharpness) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final double barFullScale = peakSharpness * focusBarFullScaleToPeakRatio;
    double barFraction = 0;
    if (barFullScale > 0) {
      barFraction = (sharpness / barFullScale).clamp(0.0, 1.0);
    }
    const double peakMarkFraction = 1 / focusBarFullScaleToPeakRatio;
    return Semantics(
      label: WizardStrings.sharpnessSemanticLabel,
      value: WizardStrings.getSharpnessPercentText(sharpness: sharpness, peakSharpness: peakSharpness),
      child: SizedBox(
        height: 24,
        child: LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
          final double barWidthLogicalPx = constraints.maxWidth;
          return Stack(
            children: [
              Positioned.fill(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(value: barFraction, minHeight: 24),
                ),
              ),
              // The best value so far
              Positioned(
                left: barWidthLogicalPx * peakMarkFraction - 2,
                top: 0,
                bottom: 0,
                child: Container(width: 4, color: colorScheme.tertiary),
              ),
            ],
          );
        }),
      ),
    );
  }

  Widget _buildCenterCrop(BuildContext context) {
    final Uint8List? centerCropPngBytes = _centerCropPngBytes;
    Widget cropContent = const Center(child: Text(WizardStrings.imageCenterPlaceholderText));
    if (centerCropPngBytes != null) {
      // FilterQuality.none enlarges without smoothing, so each camera pixel stays a sharp-edged block.
      cropContent = Image.memory(
        centerCropPngBytes,
        gaplessPlayback: true,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.none,
        semanticLabel: WizardStrings.enlargedImageCenterSemanticLabel,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(WizardStrings.enlargedImageCenterHeading, style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: 4),
        DecoratedBox(
          decoration: BoxDecoration(border: Border.all(color: Theme.of(context).colorScheme.tertiary, width: 2)),
          child: SizedBox.square(dimension: focusCenterCropSideLogicalPx, child: cropContent),
        ),
      ],
    );
  }
}
