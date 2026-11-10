// Written by Claude Code
//
// Live preview of one camera: starts it through the backend, shows every feed its driver publishes (e.g. colour,
// depth and infrared of a depth camera), and stops it again when the view goes away. Used by the wizard's
// per-camera steps and by a profile's overview. Can frame the area the focus is measured in (FocusAssistView) on the
// camera image.

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'focus_api.dart';
import 'setup_wizard_backend_client.dart';

/// The framework's neutral camera image topic (launch_helpers.DEFAULT_TOPIC_NAME_CAMERA_IMAGE), the feed the focus
/// is measured on.
const String cameraImageTopicName = '/camera/image_raw';

/// Pause between two frame requests of a feed: about 10 frames per second.
const Duration cameraPreviewFramePollInterval = Duration(milliseconds: 100);

/// Pause before asking for a frame again after a request failed, e.g. timed out while the machine is busy.
const Duration cameraPreviewFrameRetryInterval = Duration(seconds: 1);

/// Pause between two questions for the feeds while the camera's driver is still starting.
const Duration cameraPreviewFeedsPollInterval = Duration(milliseconds: 500);

/// Height of a camera with one feed; several feeds share the width in two columns instead.
const double singleFeedHeightLogicalPx = 480;
const double feedTileSpacingLogicalPx = 12;

/// Typical camera image shape, for the feed tiles before their first frame arrives.
const double feedTileAspectRatio = 4 / 3;

class CameraPreviewView extends StatefulWidget {
  const CameraPreviewView({
    super.key,
    required this.backendClient,
    required this.cameraName,
    this.profileName,
    this.serial = '',
    this.focusMeasuredArea,
  });

  final SetupWizardBackendClient backendClient;

  /// The camera to show, a name from launch_helpers.CAMERA_DRIVER_REMAPPINGS. Changing it switches the preview.
  final String cameraName;

  /// Starts the camera with this saved profile's settings; null for par_setup.yaml's (a profile not saved yet).
  final String? profileName;

  /// The unit to open while no saved profile names it yet; empty opens the unit the parameter files name.
  /// Changing it switches the preview.
  final String serial;

  /// Where the focus is measured, framed on the camera image while set; null frames nothing.
  final ValueListenable<FocusMeasuredArea?>? focusMeasuredArea;

  @override
  State<CameraPreviewView> createState() => _CameraPreviewViewState();
}

class _CameraPreviewViewState extends State<CameraPreviewView> {
  /// Counts preview starts. A waiting loop stops as soon as a newer start (another camera, Retry) or dispose
  /// changes it, so two loops never run at once.
  int _previewGeneration = 0;

  /// The backend's id of the preview this view started, null until the start has been answered.
  int? _runningPreviewId;

  /// The camera's image topics; null until its driver is up.
  List<String>? _feedTopicNames;
  String? _previewErrorText;

  @override
  void initState() {
    super.initState();
    _startPreview();
  }

  @override
  void didUpdateWidget(CameraPreviewView oldWidget) {
    super.didUpdateWidget(oldWidget);
    final bool isOtherCamera = oldWidget.cameraName != widget.cameraName || oldWidget.serial != widget.serial;
    if (isOtherCamera || oldWidget.profileName != widget.profileName) {
      _startPreview();
    }
  }

  @override
  void dispose() {
    _previewGeneration += 1;
    // A start still waiting for its answer stops its preview itself once answered (see _startPreview).
    final int? runningPreviewId = _runningPreviewId;
    if (runningPreviewId != null) {
      _stopPreviewQuietly(widget.backendClient, runningPreviewId);
    }
    super.dispose();
  }

  /// Names the preview, so a stop arriving after another view started a preview, even of the same camera, does
  /// not end that one. Takes the client, since after dispose the widget must not be read any more.
  void _stopPreviewQuietly(SetupWizardBackendClient backendClient, int previewId) {
    backendClient.stopCameraPreview(previewId: previewId).catchError((Object error) {
      // The backend may already be gone; nothing left to stop then.
    });
  }

  bool _isStillWaitingFor(int previewGeneration) {
    return mounted && previewGeneration == _previewGeneration;
  }

  Future<void> _startPreview() async {
    _previewGeneration += 1;
    final int previewGeneration = _previewGeneration;
    final SetupWizardBackendClient backendClient = widget.backendClient;
    _runningPreviewId = null;
    setState(() {
      _feedTopicNames = null;
      _previewErrorText = null;
    });
    final int previewId;
    try {
      previewId = await backendClient.startCameraPreview(
        widget.cameraName,
        profileName: widget.profileName,
        serial: widget.serial,
      );
    } catch (error) {
      _showPreviewError(previewGeneration, error);
      return;
    }
    if (!_isStillWaitingFor(previewGeneration)) {
      // Disposed meanwhile: nobody else will stop this preview. After a newer start of this view the backend has
      // already replaced it and ignores the stop.
      _stopPreviewQuietly(backendClient, previewId);
      return;
    }
    _runningPreviewId = previewId;
    await _waitForFeeds(previewGeneration);
  }

  /// Asks for the camera's feeds until its driver is up and publishes at least one.
  Future<void> _waitForFeeds(int previewGeneration) async {
    while (_isStillWaitingFor(previewGeneration)) {
      final List<String>? feedTopicNames;
      try {
        feedTopicNames = await widget.backendClient.fetchCameraPreviewFeedTopicNames();
      } catch (error) {
        _showPreviewError(previewGeneration, error);
        return;
      }
      if (!_isStillWaitingFor(previewGeneration)) {
        return;
      }
      if (feedTopicNames != null && feedTopicNames.isNotEmpty) {
        setState(() {
          _feedTopicNames = feedTopicNames;
        });
        return;
      }
      await Future<void>.delayed(cameraPreviewFeedsPollInterval);
    }
  }

  void _showPreviewError(int previewGeneration, Object error) {
    if (!_isStillWaitingFor(previewGeneration)) {
      return;
    }
    setState(() {
      _previewErrorText = describeBackendErrorForUser(error);
    });
  }

  @override
  Widget build(BuildContext context) {
    final String? previewErrorText = _previewErrorText;
    if (previewErrorText != null) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'No preview of ${widget.cameraName}: $previewErrorText',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _startPreview, child: const Text('Retry')),
        ],
      );
    }

    final List<String>? feedTopicNames = _feedTopicNames;
    if (feedTopicNames == null) {
      return _buildWaitingRow('Starting ${widget.cameraName} …');
    }
    return LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      final List<Widget> feedTiles = [];
      if (feedTopicNames.length == 1) {
        feedTiles.add(_buildFeedTile(feedTopicNames.first, constraints.maxWidth, singleFeedHeightLogicalPx));
      } else {
        final double tileWidthLogicalPx = (constraints.maxWidth - feedTileSpacingLogicalPx) / 2;
        final double imageHeightLogicalPx = tileWidthLogicalPx / feedTileAspectRatio;
        for (final String feedTopicName in feedTopicNames) {
          feedTiles.add(_buildFeedTile(feedTopicName, tileWidthLogicalPx, imageHeightLogicalPx));
        }
      }
      return Wrap(spacing: feedTileSpacingLogicalPx, runSpacing: feedTileSpacingLogicalPx, children: feedTiles);
    });
  }

  /// The feed's topic name above its live image, which keeps its aspect ratio within the box.
  Widget _buildFeedTile(String feedTopicName, double tileWidthLogicalPx, double imageHeightLogicalPx) {
    return SizedBox(
      width: tileWidthLogicalPx,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(feedTopicName, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 4),
          SizedBox(
            height: imageHeightLogicalPx,
            child: Align(
              alignment: Alignment.topLeft,
              // Keyed by topic, so a feed keeps its polling loop when the list around it changes.
              child: CameraFeedImage(
                key: ValueKey<String>(feedTopicName),
                backendClient: widget.backendClient,
                feedTopicName: feedTopicName,
                focusMeasuredArea: feedTopicName == cameraImageTopicName ? widget.focusMeasuredArea : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

Widget _buildWaitingRow(String waitingText) {
  return Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      const SizedBox(width: 12),
      Flexible(child: Text(waitingText)),
    ],
  );
}


/// The latest frame of one feed, fetched again and again while shown.
class CameraFeedImage extends StatefulWidget {
  const CameraFeedImage({
    super.key,
    required this.backendClient,
    required this.feedTopicName,
    this.focusMeasuredArea,
  });

  final SetupWizardBackendClient backendClient;
  final String feedTopicName;

  /// Where the focus is measured in this feed's frames, framed on the image while set.
  final ValueListenable<FocusMeasuredArea?>? focusMeasuredArea;

  @override
  State<CameraFeedImage> createState() => _CameraFeedImageState();
}

class _CameraFeedImageState extends State<CameraFeedImage> {
  Uint8List? _latestFrameJpegBytes;
  String? _feedErrorText;

  @override
  void initState() {
    super.initState();
    _pollFrames();
  }

  /// Simplification: fetches single JPEGs about 10 times per second, one request per frame. Upgrade: stream the
  /// frames over a WebSocket or as MJPEG, which saves a request per frame and the poll delay.
  ///
  /// Keeps asking after a failed request, showing the error until frames arrive again: one timeout must not end
  /// the preview, and the backend stops a camera nobody asks frames from.
  Future<void> _pollFrames() async {
    while (mounted) {
      final Uint8List? frameJpegBytes;
      try {
        frameJpegBytes = await widget.backendClient.fetchCameraPreviewFrame(widget.feedTopicName);
      } catch (error) {
        if (!mounted) {
          return;
        }
        setState(() {
          _feedErrorText = describeBackendErrorForUser(error);
        });
        await Future<void>.delayed(cameraPreviewFrameRetryInterval);
        continue;
      }
      if (!mounted) {
        return;
      }
      if (frameJpegBytes != null) {
        setState(() {
          _latestFrameJpegBytes = frameJpegBytes;
          _feedErrorText = null;
        });
      }
      await Future<void>.delayed(cameraPreviewFramePollInterval);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String? feedErrorText = _feedErrorText;
    if (feedErrorText != null) {
      return Text(feedErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error));
    }
    final Uint8List? latestFrameJpegBytes = _latestFrameJpegBytes;
    if (latestFrameJpegBytes == null) {
      return _buildWaitingRow('Waiting for the first frame …');
    }
    // gaplessPlayback keeps the previous frame on screen while the next one is decoded, so the image does not
    // flicker.
    final Widget frameImage = Image.memory(latestFrameJpegBytes, gaplessPlayback: true, fit: BoxFit.contain);
    final ValueListenable<FocusMeasuredArea?>? focusMeasuredArea = widget.focusMeasuredArea;
    if (focusMeasuredArea == null) {
      return frameImage;
    }
    return ValueListenableBuilder<FocusMeasuredArea?>(
      valueListenable: focusMeasuredArea,
      builder: (BuildContext context, FocusMeasuredArea? measuredArea, Widget? child) {
        if (measuredArea == null) {
          return frameImage;
        }
        // The preview JPEG is the frame scaled down, so a box of the frame's shape lines the area up with the image.
        return AspectRatio(
          aspectRatio: measuredArea.frameWidthPx / measuredArea.frameHeightPx,
          child: CustomPaint(
            foregroundPainter: _FocusMeasuredAreaPainter(
              measuredArea: measuredArea,
              frameColor: Theme.of(context).colorScheme.tertiary,
            ),
            child: Image.memory(latestFrameJpegBytes, gaplessPlayback: true, fit: BoxFit.fill),
          ),
        );
      },
    );
  }
}

/// Draws the square the focus is measured in as a dashed frame onto the camera image.
class _FocusMeasuredAreaPainter extends CustomPainter {
  _FocusMeasuredAreaPainter({required this.measuredArea, required this.frameColor});

  final FocusMeasuredArea measuredArea;
  final Color frameColor;

  static const double dashLengthLogicalPx = 8;
  static const double frameLineWidthLogicalPx = 2;

  @override
  void paint(Canvas canvas, Size size) {
    final double scaleX = size.width / measuredArea.frameWidthPx;
    final double scaleY = size.height / measuredArea.frameHeightPx;
    final Rect areaRect = Rect.fromLTWH(
      measuredArea.cropLeftPx * scaleX,
      measuredArea.cropTopPx * scaleY,
      measuredArea.cropSidePx * scaleX,
      measuredArea.cropSidePx * scaleY,
    );
    final Paint framePaint = Paint()
      ..color = frameColor
      ..strokeWidth = frameLineWidthLogicalPx
      ..style = PaintingStyle.stroke;
    final List<List<Offset>> edges = [
      [areaRect.topLeft, areaRect.topRight],
      [areaRect.topRight, areaRect.bottomRight],
      [areaRect.bottomRight, areaRect.bottomLeft],
      [areaRect.bottomLeft, areaRect.topLeft],
    ];
    for (final List<Offset> edge in edges) {
      _drawDashedLine(canvas, edge[0], edge[1], framePaint);
    }
  }

  void _drawDashedLine(Canvas canvas, Offset start, Offset end, Paint linePaint) {
    final double lineLengthLogicalPx = (end - start).distance;
    if (lineLengthLogicalPx == 0) {
      return;
    }
    final Offset direction = (end - start) / lineLengthLogicalPx;
    double dashStartLogicalPx = 0;
    while (dashStartLogicalPx < lineLengthLogicalPx) {
      double dashEndLogicalPx = dashStartLogicalPx + dashLengthLogicalPx;
      if (dashEndLogicalPx > lineLengthLogicalPx) {
        dashEndLogicalPx = lineLengthLogicalPx;
      }
      canvas.drawLine(start + direction * dashStartLogicalPx, start + direction * dashEndLogicalPx, linePaint);
      dashStartLogicalPx += 2 * dashLengthLogicalPx;
    }
  }

  @override
  bool shouldRepaint(_FocusMeasuredAreaPainter oldDelegate) {
    return oldDelegate.measuredArea != measuredArea || oldDelegate.frameColor != frameColor;
  }
}
