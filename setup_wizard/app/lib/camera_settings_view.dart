// Written by Claude Code
//
// The previewed camera's settings as its driver node reports them (name, current value, allowed range,
// description), each with a control chosen from its descriptor (SettingRowView), so it works for any driver;
// read-only ones have none. Changeable settings come first. A change is sent to the running driver, which may
// refuse it with a reason; the list is read again afterwards, since one setting can change others (e.g. automatic
// exposure). The camera must be running, so the list waits and retries while the camera is still starting. For a
// camera of a saved profile, every change the driver accepted is saved into the profile right away, like the node
// settings (NodeSettingsEditorView); without a saved profile (new-profile wizard) the backend keeps the changes until
// the profile is created.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'setting_row_view.dart';
import 'setup_wizard_backend_client.dart';

/// How long to wait before asking again while the camera's driver does not answer yet.
const Duration cameraSettingsRetryInterval = Duration(seconds: 2);

class CameraSettingsView extends StatefulWidget {
  const CameraSettingsView({
    super.key,
    required this.backendClient,
    required this.previewCamera,
    this.titleText,
  });

  final SetupWizardBackendClient backendClient;

  /// The camera whose preview runs; its settings are read from the running driver. A change means another camera,
  /// whose settings are loaded afresh.
  final PreviewCameraChoice previewCamera;

  /// Shown above the list; null for `Settings: <running camera name>`.
  final String? titleText;

  @override
  State<CameraSettingsView> createState() => _CameraSettingsViewState();
}

class _CameraSettingsViewState extends State<CameraSettingsView> {
  List<NodeSetting>? _cameraSettings;

  /// Where changes are saved: the saved profile the camera runs with; null without one.
  String? _profileName;
  List<String> _unsavedSettingNames = [];
  bool _isSavingToProfile = false;

  /// Set when a change arrives while a save is on its way, so one more save follows and writes it too.
  bool _isSaveRepeatNeeded = false;

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
    final bool isOtherCamera = oldWidget.previewCamera.runningCameraName != widget.previewCamera.runningCameraName ||
        oldWidget.previewCamera.profileName != widget.previewCamera.profileName;
    if (isOtherCamera) {
      setState(() {
        _cameraSettings = null;
        _lastErrorText = null;
        _profileName = null;
        _unsavedSettingNames = [];
        _isSaveRepeatNeeded = false;
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
      // The backend answers for the camera running now: the previous one while this camera's start is still on
      // its way. Its settings must never be shown (or changed) as this camera's, so ask again.
      final bool isReportOfThisCamera =
          cameraSettingsReport.cameraName == widget.previewCamera.runningCameraName &&
          cameraSettingsReport.profileName == widget.previewCamera.profileName;
      if (!isReportOfThisCamera) {
        _retryTimer = Timer(cameraSettingsRetryInterval, _loadCameraSettings);
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

  /// Sends the change to the driver; once it accepted it, a saved profile gets it right away.
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
    final bool isSavedToProfile = changeErrorText == null && _profileName != null;
    if (isSavedToProfile) {
      await _saveSettingsToProfile();
    } else {
      await _loadCameraSettings();
    }
  }

  /// Writes every change not saved yet into the profile; one save at a time, a change meanwhile adds one more.
  Future<void> _saveSettingsToProfile() async {
    if (_isSavingToProfile) {
      _isSaveRepeatNeeded = true;
      return;
    }
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
    if (_isSaveRepeatNeeded) {
      _isSaveRepeatNeeded = false;
      await _saveSettingsToProfile();
      return;
    }
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

  /// Whether changes are kept and the result of the last save. Changes still unsaved (the save failed, or an
  /// earlier visit left them) are named with the reason and a button to save them.
  Widget _buildSaveRow(Color mutedTextColor) {
    final String? profileName = _profileName;
    if (profileName == null) {
      return Text(
        'Changes apply to the running camera at once and are saved with the new profile when you finish.',
        style: TextStyle(color: mutedTextColor),
      );
    }

    String saveStateText = 'Changes apply to the running camera at once and are saved in $profileName right away.';
    if (_isSavingToProfile) {
      saveStateText = 'Saving in $profileName …';
    }
    final List<Widget> lines = [Text(saveStateText, style: TextStyle(color: mutedTextColor))];
    final String? saveStatusText = _saveStatusText;
    if (saveStatusText != null) {
      lines.add(Text(saveStatusText, style: TextStyle(color: mutedTextColor)));
    }
    final Color errorColor = Theme.of(context).colorScheme.error;
    final String? saveErrorText = _saveErrorText;
    if (saveErrorText != null) {
      lines.add(Text('Could not save in $profileName: $saveErrorText', style: TextStyle(color: errorColor)));
    }
    final bool hasUnsavedSettings = _unsavedSettingNames.isNotEmpty;
    if (hasUnsavedSettings && !_isSavingToProfile) {
      final String unsavedSettingNamesText = _unsavedSettingNames.join(', ');
      lines.add(Text('Not saved in $profileName yet: $unsavedSettingNamesText.', style: TextStyle(color: errorColor)));
      lines.add(TextButton(onPressed: _saveSettingsToProfile, child: const Text('Save now')));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: lines);
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color mutedTextColor = Theme.of(context).colorScheme.onSurfaceVariant;
    final List<NodeSetting>? cameraSettings = _cameraSettings;
    final String titleText = widget.titleText ?? 'Settings: ${widget.previewCamera.runningCameraName}';

    final List<Widget> rows = [Text(titleText, style: textTheme.titleMedium)];
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
      final List<NodeSetting> fixedCameraSettings = [];
      for (final NodeSetting nodeSetting in cameraSettings) {
        if (nodeSetting.isReadOnly) {
          fixedCameraSettings.add(nodeSetting);
        } else {
          rows.add(_buildSettingRow(nodeSetting));
        }
      }
      if (fixedCameraSettings.isNotEmpty) {
        rows.add(Padding(
          padding: const EdgeInsets.only(top: 20),
          child: Text('Fixed by the driver', style: textTheme.titleSmall),
        ));
        for (final NodeSetting nodeSetting in fixedCameraSettings) {
          rows.add(_buildSettingRow(nodeSetting));
        }
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  Widget _buildSettingRow(NodeSetting nodeSetting) {
    return SettingRowView(
      key: ValueKey<String>(nodeSetting.settingName),
      nodeSetting: nodeSetting,
      shownValue: nodeSetting.settingValue,
      isEditable: !nodeSetting.isReadOnly,
      lockedText: 'fixed by the driver',
      errorText: _changeErrorTextByName[nodeSetting.settingName],
      onSettingChanged: _changeSetting,
      onResetToDefault: _createResetToDefault(nodeSetting),
    );
  }

  /// Sets par_setup.yaml's value on the driver; saving it then removes the profile's own value.
  VoidCallback? _createResetToDefault(NodeSetting nodeSetting) {
    final Object? defaultValue = nodeSetting.defaultValue;
    if (!nodeSetting.hasDefaultValue || defaultValue == null) {
      return null;
    }
    return () => _changeSetting(nodeSetting.settingName, defaultValue);
  }
}
