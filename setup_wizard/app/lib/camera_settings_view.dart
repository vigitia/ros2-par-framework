// Written by Claude Code
//
// Read-only list of the previewed camera's settings as its driver node reports them: name, current value,
// allowed range and description. Shown next to the camera preview; the camera must be running, so the list waits
// and retries while the camera is still starting.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

/// How long to wait before asking again while the camera's driver does not answer yet.
const Duration cameraSettingsRetryInterval = Duration(seconds: 2);

class CameraSettingsView extends StatefulWidget {
  const CameraSettingsView({super.key, required this.backendClient, required this.cameraName});

  final SetupWizardBackendClient backendClient;

  /// The camera whose preview runs; its settings are read from the running driver.
  final String cameraName;

  @override
  State<CameraSettingsView> createState() => _CameraSettingsViewState();
}

class _CameraSettingsViewState extends State<CameraSettingsView> {
  List<CameraSetting>? _cameraSettings;
  String? _lastErrorText;
  Timer? _retryTimer;

  /// Increased on every new load, so an answer for a camera that is no longer shown is dropped.
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _loadCameraSettings();
  }

  @override
  void didUpdateWidget(CameraSettingsView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.cameraName != widget.cameraName) {
      setState(() {
        _cameraSettings = null;
        _lastErrorText = null;
      });
      _loadCameraSettings();
    }
  }

  @override
  void dispose() {
    _retryTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadCameraSettings() async {
    _retryTimer?.cancel();
    _loadGeneration += 1;
    final int loadGeneration = _loadGeneration;
    try {
      final List<CameraSetting> cameraSettings = await widget.backendClient.fetchCameraPreviewSettings();
      if (!mounted || loadGeneration != _loadGeneration) {
        return;
      }
      setState(() {
        _cameraSettings = cameraSettings;
        _lastErrorText = null;
      });
    } catch (error) {
      if (!mounted || loadGeneration != _loadGeneration) {
        return;
      }
      // Usually the camera is still starting; ask again until its driver answers.
      setState(() {
        _lastErrorText = error.toString();
      });
      _retryTimer = Timer(cameraSettingsRetryInterval, _loadCameraSettings);
    }
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color mutedTextColor = Theme.of(context).colorScheme.onSurfaceVariant;
    final List<CameraSetting>? cameraSettings = _cameraSettings;

    final List<Widget> rows = [Text('Settings: ${widget.cameraName}', style: textTheme.titleMedium)];
    if (cameraSettings == null) {
      String waitingText = 'Waiting for the camera to report its settings …';
      if (_lastErrorText != null) {
        waitingText = '$waitingText\n$_lastErrorText';
      }
      rows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(waitingText, style: TextStyle(color: mutedTextColor)),
      ));
    } else if (cameraSettings.isEmpty) {
      rows.add(Text('The driver reports no settings to show.', style: TextStyle(color: mutedTextColor)));
    } else {
      for (final CameraSetting cameraSetting in cameraSettings) {
        rows.add(_buildSettingRow(cameraSetting, textTheme, mutedTextColor));
      }
      rows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text('Read-only for now; values come from par_setup.yaml.', style: TextStyle(color: mutedTextColor)),
      ));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  Widget _buildSettingRow(CameraSetting cameraSetting, TextTheme textTheme, Color mutedTextColor) {
    final List<String> detailParts = [];
    final String? rangeText = _formatRange(cameraSetting);
    if (rangeText != null) {
      detailParts.add(rangeText);
    }
    detailParts.add(cameraSetting.typeName);
    if (cameraSetting.isReadOnly) {
      detailParts.add('fixed by the driver');
    }

    final List<Widget> rowLines = [
      Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Expanded(child: Text(cameraSetting.settingName, style: textTheme.bodyMedium)),
          Text(_formatValue(cameraSetting.settingValue), style: textTheme.titleSmall),
        ],
      ),
      Text(detailParts.join(' · '), style: textTheme.bodySmall?.copyWith(color: mutedTextColor)),
    ];
    if (cameraSetting.description.isNotEmpty) {
      rowLines.add(Text(cameraSetting.description, style: textTheme.bodySmall?.copyWith(color: mutedTextColor)));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: rowLines),
    );
  }

  /// E.g. '0 – 255, step 1' or '0.1 – 100'; null when the driver declares no range.
  String? _formatRange(CameraSetting cameraSetting) {
    final double? minimumValue = cameraSetting.minimumValue;
    final double? maximumValue = cameraSetting.maximumValue;
    if (minimumValue == null || maximumValue == null) {
      return null;
    }
    final String rangeText = '${_formatNumber(minimumValue)} – ${_formatNumber(maximumValue)}';
    final double? stepValue = cameraSetting.stepValue;
    if (stepValue == null || stepValue == 0) {
      return rangeText;
    }
    return '$rangeText, step ${_formatNumber(stepValue)}';
  }

  /// Whole numbers without '.0', so integer ranges read as integers.
  String _formatNumber(double number) {
    if (number == number.roundToDouble()) {
      return number.toInt().toString();
    }
    return number.toString();
  }

  String _formatValue(Object? settingValue) {
    if (settingValue == null) {
      return 'not set';
    }
    if (settingValue is List) {
      return settingValue.join(', ');
    }
    return settingValue.toString();
  }
}
