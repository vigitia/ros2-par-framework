// Written by Claude Code
//
// Helps focus the previewed camera: a sharpness bar with a mark at the best value so far, and the image centre where
// the sharpness is measured, enlarged with every camera pixel as a block, to judge single-pixel edges by eye. Works
// for a lens ring turned by hand and for a focus setting alike: change the focus until the bar reaches the mark and
// gets no higher. The camera itself is started by the preview next to it (CameraPreviewView).

import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'focus_api.dart';
import 'setup_wizard_backend_client.dart';

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
  const FocusAssistView({super.key, required this.backendClient, this.measuredAreaNotifier});

  final SetupWizardBackendClient backendClient;

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
          _measurementErrorText = describeBackendErrorForUser(error);
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
        if (centerCropPngBytes != null) {
          _centerCropPngBytes = centerCropPngBytes;
        }
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
        _measurementErrorText = describeBackendErrorForUser(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final List<Widget> scoreRows = [
      Text('Focus', style: textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
        'Put something with fine, high-contrast detail (printed text, a marker sheet) under the image centre. Change '
        'the focus until the bar reaches the best mark and gets no higher. The value only compares focus settings of '
        'one scene; light and content change it.',
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 12),
      ..._buildScoreRows(context),
    ];
    final String? measurementErrorText = _measurementErrorText;
    if (measurementErrorText != null) {
      scoreRows.add(const SizedBox(height: 8));
      scoreRows.add(Text(
        'Waiting for the camera image: $measurementErrorText',
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
      return [const Text('Measuring …')];
    }
    return [
      _buildSharpnessBar(context, sharpness, peakSharpness),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(
            child: Text('Sharpness ${sharpness.toStringAsFixed(0)}, best so far ${peakSharpness.toStringAsFixed(0)}'),
          ),
          TextButton.icon(
            onPressed: _resetPeak,
            icon: const Icon(Icons.restart_alt),
            label: const Text('Reset best'),
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
      label: 'Sharpness',
      value: '${(sharpness / peakSharpness * 100).toStringAsFixed(0)} percent of the best so far',
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
    Widget cropContent = const Center(child: Text('Image centre'));
    if (centerCropPngBytes != null) {
      // FilterQuality.none enlarges without smoothing, so each camera pixel stays a sharp-edged block.
      cropContent = Image.memory(
        centerCropPngBytes,
        gaplessPlayback: true,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.none,
        semanticLabel: 'Enlarged image centre, where the sharpness is measured',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Image centre, enlarged', style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: 4),
        DecoratedBox(
          decoration: BoxDecoration(border: Border.all(color: Theme.of(context).colorScheme.tertiary, width: 2)),
          child: SizedBox.square(dimension: focusCenterCropSideLogicalPx, child: cropContent),
        ),
      ],
    );
  }
}
