// Written by Claude Code
//
// The previewed camera's settings as its driver node reports them (name, current value, allowed range,
// description), each with a control chosen from its descriptor (SettingRowView), so it works for any driver;
// read-only ones have none. Changeable settings come first. A change is sent to the running driver, which may
// refuse it with a reason; the list is read again afterwards, since one setting can change others (e.g. automatic
// exposure). The camera must be running, so the list waits and retries while the camera is still starting.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'setting_row_view.dart';
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

  /// Where changes can be saved: the saved profile the camera runs with; null without one.
  String? _profileName;
  List<String> _unsavedSettingNames = [];
  bool _isSavingToProfile = false;

  /// The result of the last save, or why it failed.
  String? _saveStatusText;
  String? _saveErrorText;
  String? _lastErrorText;
  Timer? _retryTimer;

  /// Increased on every new load, so an answer for a camera that is no longer shown is dropped.
  int _loadGeneration = 0;

  /// Why the driver refused the last change of a setting; by setting name.
  final Map<String, String> _changeErrorTextByName = {};

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
        _profileName = null;
        _unsavedSettingNames = [];
        _saveStatusText = null;
        _saveErrorText = null;
        _changeErrorTextByName.clear();
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
      final CameraSettingsReport cameraSettingsReport = await widget.backendClient.fetchCameraPreviewSettings();
      if (!mounted || loadGeneration != _loadGeneration) {
        return;
      }
      setState(() {
        _cameraSettings = cameraSettingsReport.cameraSettings;
        _profileName = cameraSettingsReport.profileName;
        _unsavedSettingNames = cameraSettingsReport.unsavedSettingNames;
        _lastErrorText = null;
      });
    } catch (error) {
      if (!mounted || loadGeneration != _loadGeneration) {
        return;
      }
      // Usually the camera is still starting; ask again until its driver answers.
      setState(() {
        _lastErrorText = describeBackendErrorForUser(error);
      });
      _retryTimer = Timer(cameraSettingsRetryInterval, _loadCameraSettings);
    }
  }

  Future<void> _changeSetting(String settingName, Object settingValue) async {
    String? changeErrorText;
    try {
      await widget.backendClient.changeCameraPreviewSetting(settingName, settingValue);
    } catch (error) {
      changeErrorText = describeBackendErrorForUser(error);
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _saveStatusText = null;
      if (changeErrorText == null) {
        _changeErrorTextByName.remove(settingName);
      } else {
        _changeErrorTextByName[settingName] = changeErrorText;
      }
    });
    await _loadCameraSettings();
  }

  Future<void> _saveSettingsToProfile() async {
    setState(() {
      _isSavingToProfile = true;
      _saveStatusText = null;
      _saveErrorText = null;
    });
    String? saveStatusText;
    String? saveErrorText;
    try {
      final CameraSettingsSaveResult saveResult = await widget.backendClient.saveCameraPreviewSettingsToProfile();
      saveStatusText = _describeSaveResult(saveResult);
    } catch (error) {
      saveErrorText = describeBackendErrorForUser(error);
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isSavingToProfile = false;
      _saveStatusText = saveStatusText;
      _saveErrorText = saveErrorText;
    });
    await _loadCameraSettings();
  }

  String _describeSaveResult(CameraSettingsSaveResult saveResult) {
    final List<String> sentences = [];
    if (saveResult.writtenSettingNames.isNotEmpty) {
      sentences.add('Saved in ${saveResult.profileName}: ${saveResult.writtenSettingNames.join(', ')}.');
    }
    if (saveResult.removedSettingNames.isNotEmpty) {
      sentences.add('Back to the defaults of par_setup.yaml: ${saveResult.removedSettingNames.join(', ')}.');
    }
    if (sentences.isEmpty) {
      return 'Nothing to save.';
    }
    return sentences.join(' ');
  }

  /// Whether changes are kept, and the button that writes them into the profile.
  Widget _buildSaveRow(Color mutedTextColor) {
    final String? profileName = _profileName;
    if (profileName == null) {
      return Text(
        'Changes apply to the running camera at once and are saved with the new profile when you finish.',
        style: TextStyle(color: mutedTextColor),
      );
    }

    final int unsavedSettingCount = _unsavedSettingNames.length;
    String saveStateText = 'Changes apply to the running camera at once; save them to keep them in $profileName.';
    if (unsavedSettingCount == 1) {
      saveStateText = '1 change not saved in $profileName yet.';
    } else if (unsavedSettingCount > 1) {
      saveStateText = '$unsavedSettingCount changes not saved in $profileName yet.';
    }
    final bool canSave = unsavedSettingCount > 0 && !_isSavingToProfile;
    final List<Widget> lines = [
      Row(children: [
        Expanded(child: Text(saveStateText, style: TextStyle(color: mutedTextColor))),
        const SizedBox(width: 12),
        FilledButton.tonal(
          onPressed: canSave ? _saveSettingsToProfile : null,
          child: Text(_isSavingToProfile ? 'Saving …' : 'Save to profile'),
        ),
      ]),
    ];
    final String? saveStatusText = _saveStatusText;
    if (saveStatusText != null) {
      lines.add(Text(saveStatusText, style: TextStyle(color: mutedTextColor)));
    }
    final String? saveErrorText = _saveErrorText;
    if (saveErrorText != null) {
      lines.add(Text(saveErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: lines);
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
      rows.add(Padding(padding: const EdgeInsets.only(top: 4), child: _buildSaveRow(mutedTextColor)));
      // The ones that can be changed first: they are what the user came for.
      final List<CameraSetting> fixedCameraSettings = [];
      for (final CameraSetting cameraSetting in cameraSettings) {
        if (cameraSetting.isReadOnly) {
          fixedCameraSettings.add(cameraSetting);
        } else {
          rows.add(_buildSettingRow(cameraSetting));
        }
      }
      if (fixedCameraSettings.isNotEmpty) {
        rows.add(Padding(
          padding: const EdgeInsets.only(top: 20),
          child: Text('Fixed by the driver', style: textTheme.titleSmall),
        ));
        for (final CameraSetting cameraSetting in fixedCameraSettings) {
          rows.add(_buildSettingRow(cameraSetting));
        }
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  Widget _buildSettingRow(CameraSetting cameraSetting) {
    return SettingRowView(
      key: ValueKey<String>(cameraSetting.settingName),
      cameraSetting: cameraSetting,
      shownValue: cameraSetting.settingValue,
      isEditable: !cameraSetting.isReadOnly,
      lockedText: 'fixed by the driver',
      errorText: _changeErrorTextByName[cameraSetting.settingName],
      onSettingChanged: _changeSetting,
    );
  }
}
