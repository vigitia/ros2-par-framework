// Written by Claude Code
//
// Live preview of one camera: starts it through the backend, shows its frames, and stops it again when the view
// goes away. Used by the wizard's per-camera steps.

import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

/// Pause between two frame requests: about 10 frames per second.
const Duration cameraPreviewFramePollInterval = Duration(milliseconds: 100);

class CameraPreviewView extends StatefulWidget {
  const CameraPreviewView({super.key, required this.backendClient, required this.cameraName});

  final SetupWizardBackendClient backendClient;

  /// The camera to show, a name from launch_helpers.CAMERA_DRIVER_REMAPPINGS. Changing it switches the preview.
  final String cameraName;

  @override
  State<CameraPreviewView> createState() => _CameraPreviewViewState();
}

class _CameraPreviewViewState extends State<CameraPreviewView> {
  /// Counts preview starts. A polling loop stops as soon as a newer start (another camera, Retry) or dispose
  /// changes it, so two loops never run at once.
  int _previewGeneration = 0;
  Uint8List? _latestFrameJpegBytes;
  String? _previewErrorText;

  @override
  void initState() {
    super.initState();
    _startPreview();
  }

  @override
  void didUpdateWidget(CameraPreviewView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.cameraName != widget.cameraName) {
      _startPreview();
    }
  }

  @override
  void dispose() {
    _previewGeneration += 1;
    // Names the camera, so a stop arriving after another view started its camera does not end that one.
    widget.backendClient.stopCameraPreview(cameraName: widget.cameraName).catchError((Object error) {
      // The backend may already be gone; nothing left to stop then.
    });
    super.dispose();
  }

  Future<void> _startPreview() async {
    _previewGeneration += 1;
    final int previewGeneration = _previewGeneration;
    setState(() {
      _latestFrameJpegBytes = null;
      _previewErrorText = null;
    });
    try {
      await widget.backendClient.startCameraPreview(widget.cameraName);
    } catch (error) {
      _showPreviewError(previewGeneration, error);
      return;
    }
    await _pollFrames(previewGeneration);
  }

  /// Simplification: fetches single JPEGs about 10 times per second, one request per frame. Upgrade: stream the
  /// frames over a WebSocket or as MJPEG, which saves a request per frame and the poll delay.
  Future<void> _pollFrames(int previewGeneration) async {
    while (mounted && previewGeneration == _previewGeneration) {
      final Uint8List? frameJpegBytes;
      try {
        frameJpegBytes = await widget.backendClient.fetchCameraPreviewFrame();
      } catch (error) {
        _showPreviewError(previewGeneration, error);
        return;
      }
      if (!mounted || previewGeneration != _previewGeneration) {
        return;
      }
      if (frameJpegBytes != null) {
        setState(() {
          _latestFrameJpegBytes = frameJpegBytes;
        });
      }
      await Future<void>.delayed(cameraPreviewFramePollInterval);
    }
  }

  void _showPreviewError(int previewGeneration, Object error) {
    if (!mounted || previewGeneration != _previewGeneration) {
      return;
    }
    String errorText = error.toString();
    const String exceptionPrefix = 'Exception: ';
    if (errorText.startsWith(exceptionPrefix)) {
      errorText = errorText.substring(exceptionPrefix.length);
    }
    setState(() {
      _previewErrorText = errorText;
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

    final Uint8List? latestFrameJpegBytes = _latestFrameJpegBytes;
    if (latestFrameJpegBytes == null) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: 12),
          Text('Starting ${widget.cameraName} …'),
        ],
      );
    }
    // gaplessPlayback keeps the previous frame on screen while the next one is decoded, so the image does not
    // flicker.
    return Image.memory(latestFrameJpegBytes, gaplessPlayback: true, fit: BoxFit.contain);
  }
}
