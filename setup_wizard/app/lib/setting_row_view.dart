// Written by Claude Code
//
// One setting of a ROS node (a parameter as its node reports it: name, value, allowed range, description) with a
// control chosen from its descriptor alone, so it works for any node: a switch for a bool, a dropdown for an integer
// with few allowed values or a menu, a slider for other numbers with a range, a text field for everything else,
// nothing when it may not be changed. A change is handed to the owner (onSettingChanged), which decides what it
// means: CameraSettingsView sends it to the running driver, the sensor node settings collect it until Apply.

import 'package:flutter/material.dart';

import 'camera_preview_api.dart';

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

class SettingRowView extends StatefulWidget {
  const SettingRowView({
    super.key,
    required this.cameraSetting,
    required this.shownValue,
    required this.isEditable,
    required this.onSettingChanged,
    this.lockedText,
    this.errorText,
  });

  /// The setting with its descriptor, as the node reports it.
  final CameraSetting cameraSetting;

  /// The value to show: the node's, or a change the owner has not applied yet.
  final Object? shownValue;

  /// False: shown without a control, e.g. a read-only driver setting.
  final bool isEditable;
  final void Function(String settingName, Object settingValue) onSettingChanged;

  /// Why it cannot be changed, shown next to the type, e.g. 'fixed by the driver'.
  final String? lockedText;

  /// Why the owner's last change of this setting failed; null otherwise.
  final String? errorText;

  @override
  State<SettingRowView> createState() => _SettingRowViewState();
}

class _SettingRowViewState extends State<SettingRowView> {
  /// The slider's position while it is dragged, until the owner shows the new value.
  double? _draggedSliderValue;

  /// Why the typed text is no valid value; null otherwise.
  String? _textErrorText;

  @override
  void didUpdateWidget(SettingRowView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The owner shows a new value or an error: the dragged position has served its purpose
    if (oldWidget.shownValue != widget.shownValue || oldWidget.errorText != widget.errorText) {
      _draggedSliderValue = null;
    }
  }

  void _reportChange(String settingName, Object settingValue) {
    setState(() {
      _textErrorText = null;
    });
    widget.onSettingChanged(settingName, settingValue);
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color mutedTextColor = Theme.of(context).colorScheme.onSurfaceVariant;
    return _buildSettingRow(widget.cameraSetting, textTheme, mutedTextColor);
  }

  Widget _buildSettingRow(CameraSetting cameraSetting, TextTheme textTheme, Color mutedTextColor) {
    final TextStyle? mutedSmallTextStyle = textTheme.bodySmall?.copyWith(color: mutedTextColor);
    final List<String> detailParts = [];
    final String? rangeText = _formatRange(cameraSetting);
    if (rangeText != null) {
      detailParts.add(rangeText);
    }
    detailParts.add(cameraSetting.typeName);
    final String? lockedText = widget.lockedText;
    if (!widget.isEditable && lockedText != null) {
      detailParts.add(lockedText);
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
    final bool isMenuInDropdown = widget.isEditable && _readMenuOptions(cameraSetting) != null;
    if (cameraSetting.additionalConstraints.isNotEmpty && !isMenuInDropdown) {
      rowLines.add(Text('Allowed: ${cameraSetting.additionalConstraints}', style: mutedSmallTextStyle));
    }
    final String? changeErrorText = _textErrorText ?? widget.errorText;
    if (changeErrorText != null) {
      rowLines.add(Text(changeErrorText, style: textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.error)));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: rowLines),
    );
  }

  /// The slider position while dragged, otherwise the value the owner shows.
  Object? _getShownValue(CameraSetting cameraSetting) {
    final double? draggedSliderValue = _draggedSliderValue;
    if (draggedSliderValue == null) {
      return widget.shownValue;
    }
    if (cameraSetting.typeName == 'integer') {
      return draggedSliderValue.round();
    }
    return draggedSliderValue;
  }

  /// The control for changing the setting, chosen from its descriptor; null when it cannot be changed.
  Widget? _buildSettingControl(CameraSetting cameraSetting) {
    if (!widget.isEditable) {
      return null;
    }
    final Object? settingValue = widget.shownValue;
    if (cameraSetting.typeName == 'bool' && settingValue is bool) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Switch(
          value: settingValue,
          onChanged: (bool isOn) => _reportChange(cameraSetting.settingName, isOn),
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
          _reportChange(cameraSetting.settingName, chosenValue);
        }
      },
    );
  }

  Widget _buildSettingSlider(CameraSetting cameraSetting, double settingValue, double minimumValue, double maximumValue) {
    final String settingName = cameraSetting.settingName;
    final double sliderValue = (_draggedSliderValue ?? settingValue).clamp(minimumValue, maximumValue);
    return Slider(
      value: sliderValue,
      min: minimumValue,
      max: maximumValue,
      divisions: _computeSliderDivisionCount(cameraSetting, minimumValue, maximumValue),
      onChanged: (double draggedValue) {
        setState(() {
          _draggedSliderValue = draggedValue;
        });
      },
      // Sent once on release: every intermediate value would make the driver reconfigure the camera.
      onChangeEnd: (double releasedValue) {
        if (cameraSetting.typeName == 'integer') {
          _reportChange(settingName, releasedValue.round());
        } else {
          _reportChange(settingName, releasedValue);
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
    final String valueText = _formatValue(widget.shownValue);
    return TextFormField(
      // Rebuilt with the shown value after every change, so the field never shows a stale value.
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
        _textErrorText = '"$enteredText" is not a valid ${cameraSetting.typeName} value.';
      });
      return;
    }
    _reportChange(cameraSetting.settingName, parsedValue);
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
