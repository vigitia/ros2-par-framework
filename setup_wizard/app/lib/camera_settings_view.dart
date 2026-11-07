// Written by Claude Code
//
// The previewed camera's settings as its driver node reports them (name, current value, allowed range,
// description), each with a control chosen from its descriptor alone, so it works for any driver: a switch for a
// bool, a dropdown for an integer with few allowed values or a menu, a slider for other numbers with a range, a
// text field for everything else, nothing for a read-only one. Changeable settings come first. A
// change is sent to the running driver, which may refuse it with a reason; the list is read again afterwards,
// since one setting can change others (e.g. automatic exposure). The camera must be running, so the list waits
// and retries while the camera is still starting.

import 'dart:async';

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';
import 'setup_wizard_backend_client.dart';

/// How long to wait before asking again while the camera's driver does not answer yet.
const Duration cameraSettingsRetryInterval = Duration(seconds: 2);

/// A slider with more positions than this would move in steps too small to hit; it then moves freely.
const int maximumSliderDivisionCount = 1000;

/// An integer setting with at most this many allowed values gets a dropdown instead of a slider.
const int maximumDropdownOptionCount = 12;

/// One menu entry as v4l2_camera writes its menus into additional_constraints: '1 - Manual Mode'.
final RegExp menuOptionPattern = RegExp(r'^\s*(-?\d+)\s+-\s+(.+?)\s*$');

/// One choice of a dropdown: the value sent to the driver and what the user reads.
class SettingDropdownOption {
  const SettingDropdownOption({required this.optionValue, required this.optionLabel});

  final int optionValue;
  final String optionLabel;
}

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

  /// A slider's position while it is dragged, before the value is sent; by setting name.
  final Map<String, double> _draggedSliderValueByName = {};

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
        _draggedSliderValueByName.clear();
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
        _lastErrorText = error.toString();
      });
      _retryTimer = Timer(cameraSettingsRetryInterval, _loadCameraSettings);
    }
  }

  Future<void> _changeSetting(String settingName, Object settingValue) async {
    String? changeErrorText;
    try {
      await widget.backendClient.changeCameraPreviewSetting(settingName, settingValue);
    } catch (error) {
      changeErrorText = error.toString().replaceFirst('Exception: ', '');
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _draggedSliderValueByName.remove(settingName);
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
      saveErrorText = error.toString().replaceFirst('Exception: ', '');
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
          rows.add(_buildSettingRow(cameraSetting, textTheme, mutedTextColor));
        }
      }
      if (fixedCameraSettings.isNotEmpty) {
        rows.add(Padding(
          padding: const EdgeInsets.only(top: 20),
          child: Text('Fixed by the driver', style: textTheme.titleSmall),
        ));
        for (final CameraSetting cameraSetting in fixedCameraSettings) {
          rows.add(_buildSettingRow(cameraSetting, textTheme, mutedTextColor));
        }
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  Widget _buildSettingRow(CameraSetting cameraSetting, TextTheme textTheme, Color mutedTextColor) {
    final TextStyle? mutedSmallTextStyle = textTheme.bodySmall?.copyWith(color: mutedTextColor);
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
          const SizedBox(width: 12),
          // Wraps instead of overflowing: values can be long, e.g. a file URL, and must stay readable in full.
          Flexible(
            child: Text(
              _formatValue(_getShownValue(cameraSetting)),
              style: textTheme.titleSmall,
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    ];
    final Widget? settingControl = _buildSettingControl(cameraSetting);
    if (settingControl != null) {
      rowLines.add(settingControl);
    }
    rowLines.add(Text(detailParts.join(' · '), style: mutedSmallTextStyle));
    if (cameraSetting.description.isNotEmpty) {
      rowLines.add(Text(cameraSetting.description, style: mutedSmallTextStyle));
    }
    // A menu read into a dropdown already shows its options.
    final bool isMenuInDropdown = !cameraSetting.isReadOnly && _readMenuOptions(cameraSetting) != null;
    if (cameraSetting.additionalConstraints.isNotEmpty && !isMenuInDropdown) {
      rowLines.add(Text('Allowed: ${cameraSetting.additionalConstraints}', style: mutedSmallTextStyle));
    }
    final String? changeErrorText = _changeErrorTextByName[cameraSetting.settingName];
    if (changeErrorText != null) {
      rowLines.add(Text(changeErrorText, style: textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.error)));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: rowLines),
    );
  }

  /// The slider position while dragged, otherwise the driver's value.
  Object? _getShownValue(CameraSetting cameraSetting) {
    final double? draggedSliderValue = _draggedSliderValueByName[cameraSetting.settingName];
    if (draggedSliderValue == null) {
      return cameraSetting.settingValue;
    }
    if (cameraSetting.typeName == 'integer') {
      return draggedSliderValue.round();
    }
    return draggedSliderValue;
  }

  /// The control for changing the setting, chosen from its descriptor; null when it cannot be changed.
  Widget? _buildSettingControl(CameraSetting cameraSetting) {
    if (cameraSetting.isReadOnly) {
      return null;
    }
    final Object? settingValue = cameraSetting.settingValue;
    if (cameraSetting.typeName == 'bool' && settingValue is bool) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Switch(
          value: settingValue,
          onChanged: (bool isOn) => _changeSetting(cameraSetting.settingName, isOn),
        ),
      );
    }
    final List<SettingDropdownOption>? dropdownOptions = _getDropdownOptions(cameraSetting);
    if (dropdownOptions != null && settingValue is int) {
      return _buildSettingDropdown(cameraSetting, settingValue, dropdownOptions);
    }
    final bool isNumber = cameraSetting.typeName == 'integer' || cameraSetting.typeName == 'double';
    final double? minimumValue = cameraSetting.minimumValue;
    final double? maximumValue = cameraSetting.maximumValue;
    if (isNumber && settingValue is num && minimumValue != null && maximumValue != null && minimumValue < maximumValue) {
      return _buildSettingSlider(cameraSetting, settingValue.toDouble(), minimumValue, maximumValue);
    }
    return _buildSettingTextField(cameraSetting);
  }

  /// The choices of a discrete integer setting: a menu's labelled options, or every value of a small range; null
  /// for a setting that is not discrete.
  List<SettingDropdownOption>? _getDropdownOptions(CameraSetting cameraSetting) {
    if (cameraSetting.typeName != 'integer') {
      return null;
    }
    final List<SettingDropdownOption>? menuOptions = _readMenuOptions(cameraSetting);
    if (menuOptions != null) {
      return menuOptions;
    }
    final double? minimumValue = cameraSetting.minimumValue;
    final double? maximumValue = cameraSetting.maximumValue;
    if (minimumValue == null || maximumValue == null || minimumValue >= maximumValue) {
      return null;
    }
    double stepValue = cameraSetting.stepValue ?? 1;
    if (stepValue <= 0) {
      stepValue = 1;
    }
    final int optionCount = ((maximumValue - minimumValue) / stepValue).round() + 1;
    if (optionCount > maximumDropdownOptionCount) {
      return null;
    }
    final List<SettingDropdownOption> rangeOptions = [];
    for (int optionIndex = 0; optionIndex < optionCount; optionIndex += 1) {
      final int optionValue = (minimumValue + optionIndex * stepValue).round();
      rangeOptions.add(SettingDropdownOption(optionValue: optionValue, optionLabel: '$optionValue'));
    }
    return rangeOptions;
  }

  /// A menu's options from the descriptor's free text, null when the text is not a menu.
  /// Special case: ROS gives additional_constraints no format; this reads the one v4l2_camera writes
  /// ('1 - Manual Mode, 3 - Aperture Priority Mode'). Other text stays a hint next to a number field.
  List<SettingDropdownOption>? _readMenuOptions(CameraSetting cameraSetting) {
    if (cameraSetting.typeName != 'integer' || cameraSetting.additionalConstraints.isEmpty) {
      return null;
    }
    final List<SettingDropdownOption> menuOptions = [];
    for (final String optionText in cameraSetting.additionalConstraints.split(',')) {
      final RegExpMatch? optionMatch = menuOptionPattern.firstMatch(optionText);
      if (optionMatch == null) {
        return null;
      }
      menuOptions.add(SettingDropdownOption(
        optionValue: int.parse(optionMatch.group(1)!),
        optionLabel: '${optionMatch.group(1)} – ${optionMatch.group(2)}',
      ));
    }
    return menuOptions;
  }

  Widget _buildSettingDropdown(CameraSetting cameraSetting, int settingValue, List<SettingDropdownOption> dropdownOptions) {
    final List<DropdownMenuItem<int>> dropdownItems = [];
    bool isCurrentValueAnOption = false;
    for (final SettingDropdownOption dropdownOption in dropdownOptions) {
      if (dropdownOption.optionValue == settingValue) {
        isCurrentValueAnOption = true;
      }
      dropdownItems.add(DropdownMenuItem<int>(value: dropdownOption.optionValue, child: Text(dropdownOption.optionLabel)));
    }
    // A driver may report a value outside its own list; it must still be shown, or the dropdown fails.
    if (!isCurrentValueAnOption) {
      dropdownItems.add(DropdownMenuItem<int>(value: settingValue, child: Text('$settingValue')));
    }
    return DropdownButton<int>(
      value: settingValue,
      isExpanded: true,
      items: dropdownItems,
      onChanged: (int? chosenValue) {
        if (chosenValue != null && chosenValue != settingValue) {
          _changeSetting(cameraSetting.settingName, chosenValue);
        }
      },
    );
  }

  Widget _buildSettingSlider(CameraSetting cameraSetting, double settingValue, double minimumValue, double maximumValue) {
    final String settingName = cameraSetting.settingName;
    final double sliderValue = (_draggedSliderValueByName[settingName] ?? settingValue).clamp(minimumValue, maximumValue);
    return Slider(
      value: sliderValue,
      min: minimumValue,
      max: maximumValue,
      divisions: _computeSliderDivisionCount(cameraSetting, minimumValue, maximumValue),
      onChanged: (double draggedValue) {
        setState(() {
          _draggedSliderValueByName[settingName] = draggedValue;
        });
      },
      // Sent once on release: every intermediate value would make the driver reconfigure the camera.
      onChangeEnd: (double releasedValue) {
        if (cameraSetting.typeName == 'integer') {
          _changeSetting(settingName, releasedValue.round());
        } else {
          _changeSetting(settingName, releasedValue);
        }
      },
    );
  }

  /// One slider position per allowed value: per step when the range has one, per whole number for an integer;
  /// null (free movement) for a double without a step, or when there would be too many positions to hit.
  int? _computeSliderDivisionCount(CameraSetting cameraSetting, double minimumValue, double maximumValue) {
    double? stepValue = cameraSetting.stepValue;
    if (stepValue == null || stepValue <= 0) {
      if (cameraSetting.typeName != 'integer') {
        return null;
      }
      stepValue = 1;
    }
    final int divisionCount = ((maximumValue - minimumValue) / stepValue).round();
    if (divisionCount < 1 || divisionCount > maximumSliderDivisionCount) {
      return null;
    }
    return divisionCount;
  }

  /// A text field holding the value; Enter sends it. Lists are written comma-separated, e.g. "640, 480".
  Widget _buildSettingTextField(CameraSetting cameraSetting) {
    final String valueText = _formatValue(cameraSetting.settingValue);
    return TextFormField(
      // Rebuilt with the driver's value after every reload, so the field never shows a stale value.
      key: ValueKey<String>('${cameraSetting.settingName}=$valueText'),
      initialValue: valueText,
      decoration: const InputDecoration(isDense: true, helperText: 'Enter applies the value'),
      onFieldSubmitted: (String enteredText) => _submitSettingText(cameraSetting, enteredText),
    );
  }

  void _submitSettingText(CameraSetting cameraSetting, String enteredText) {
    final Object? parsedValue = _parseSettingText(cameraSetting.typeName, enteredText);
    if (parsedValue == null) {
      setState(() {
        _changeErrorTextByName[cameraSetting.settingName] =
            '"$enteredText" is not a valid ${cameraSetting.typeName} value.';
      });
      return;
    }
    _changeSetting(cameraSetting.settingName, parsedValue);
  }

  /// The typed text as a value of the setting's type, null when it does not parse.
  Object? _parseSettingText(String typeName, String enteredText) {
    final String trimmedText = enteredText.trim();
    if (typeName == 'string') {
      return enteredText;
    }
    if (typeName == 'integer') {
      return int.tryParse(trimmedText);
    }
    if (typeName == 'double') {
      return double.tryParse(trimmedText);
    }
    if (typeName == 'bool') {
      return _parseBoolText(trimmedText);
    }
    if (!typeName.endsWith(' array')) {
      return null;
    }
    final String elementTypeName = typeName.substring(0, typeName.length - ' array'.length);
    final List<Object> parsedElements = [];
    if (trimmedText.isEmpty) {
      return parsedElements;
    }
    for (final String elementText in trimmedText.split(',')) {
      final Object? parsedElement = _parseSettingText(elementTypeName, elementText.trim());
      if (parsedElement == null) {
        return null;
      }
      parsedElements.add(parsedElement);
    }
    return parsedElements;
  }

  bool? _parseBoolText(String boolText) {
    if (boolText == 'true') {
      return true;
    }
    if (boolText == 'false') {
      return false;
    }
    return null;
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
    if (settingValue is double) {
      return _formatNumber(settingValue);
    }
    return settingValue.toString();
  }
}
