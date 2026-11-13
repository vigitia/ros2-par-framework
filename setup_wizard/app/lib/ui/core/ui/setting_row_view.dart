// Written by Claude Code
//
// One setting of a ROS node (a parameter as its node reports it: name, value, allowed range, description) with a
// control chosen from its descriptor alone, so it works for any node: a switch for a bool, a dropdown for an integer
// with few allowed values or a menu, a slider for other numbers with a range, a text field for everything else that
// accepts only what the setting's type allows and passes on every valid entry right away (shortly after the last
// keystroke), nothing when it may not be changed. A reset button appears while the value differs from the default.
// Name and control share one line when the row is wide enough, the name right-aligned so it sits next to its control;
// otherwise the control goes below the name. The value
// is written out only where no control shows it (read-only settings, next to a slider). A change is handed to the
// owner (onSettingChanged), which decides what it means: CameraSettingsView sends it to the running driver, the node
// settings collect it until Save.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../data/services/camera_preview_api.dart';
import '../../../config/wizard_strings.dart';

/// A slider with more positions than this would move in steps too small to hit; it then moves freely.
const int maximumSliderDivisionCount = 1000;

/// An integer setting with at most this many allowed values gets a dropdown instead of a slider.
const int maximumDropdownOptionCount = 12;

/// From this row width on, the name and the control share one line.
const double settingRowOneLineMinimumWidthLogicalPx = 560;

/// Room above each setting, so the rows read as separate settings.
const double settingRowTopSpacingLogicalPx = 20;

/// How long typing must pause before a valid entry is passed on, so not every keystroke reaches a driver.
const Duration typedValueReportDelay = Duration(milliseconds: 500);

/// Room for the value next to a slider.
const double sliderValueWidthLogicalPx = 72;

/// What a text field accepts while typing, by the setting's type name; a type not listed accepts any text.
final Map<String, RegExp> typedTextPatternByTypeName = {
  'integer': RegExp(r'^-?\d*$'),
  'double': RegExp(r'^-?\d*\.?\d*([eE]-?\d*)?$'),
  'bool': RegExp(r'^[a-z]*$'),
  'integer array': RegExp(r'^[-\d,\s]*$'),
  'double array': RegExp(r'^[-\d.eE,\s]*$'),
  'bool array': RegExp(r'^[a-z,\s]*$'),
};

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
    required this.nodeSetting,
    required this.shownValue,
    required this.isEditable,
    required this.onSettingChanged,
    this.lockedText,
    this.errorText,
    this.onResetToDefault,
  });

  /// The setting with its descriptor, as the node reports it.
  final NodeSetting nodeSetting;

  /// The value to show: the node's, or a change the owner has not applied yet.
  final Object? shownValue;

  /// False: shown without a control, e.g. a read-only driver setting.
  final bool isEditable;
  final void Function(String settingName, Object settingValue) onSettingChanged;

  /// Why it cannot be changed, shown below the name, e.g. 'fixed by the driver'.
  final String? lockedText;

  /// Why the owner's last change of this setting failed; null otherwise.
  final String? errorText;

  /// Sets the setting back to its default (nodeSetting.defaultValue); null when no default is known.
  final VoidCallback? onResetToDefault;

  @override
  State<SettingRowView> createState() => _SettingRowViewState();
}

class _SettingRowViewState extends State<SettingRowView> {
  /// The slider's position while it is dragged, until the owner shows the new value.
  double? _draggedSliderValue;

  /// Why the typed text is no valid value; null otherwise.
  String? _textErrorText;

  /// The text field's text and focus, kept across rebuilds so typing is not interrupted.
  late final TextEditingController _valueTextController = TextEditingController(text: _formatValue(widget.shownValue));
  final FocusNode _valueTextFocusNode = FocusNode();
  Timer? _typedValueReportTimer;

  @override
  void initState() {
    super.initState();
    _valueTextFocusNode.addListener(_onValueTextFocusChanged);
  }

  @override
  void didUpdateWidget(SettingRowView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The owner shows a new value or an error: the dragged position has served its purpose
    if (oldWidget.shownValue != widget.shownValue || oldWidget.errorText != widget.errorText) {
      _draggedSliderValue = null;
    }
    // While the user types, the field keeps what they type; otherwise it shows the owner's value
    if (!_valueTextFocusNode.hasFocus) {
      _valueTextController.text = _formatValue(widget.shownValue);
    }
  }

  @override
  void dispose() {
    _typedValueReportTimer?.cancel();
    _valueTextController.dispose();
    _valueTextFocusNode.dispose();
    super.dispose();
  }

  /// Leaving the field: an unfinished entry (e.g. only "-") is named, a finished one shown as the owner has it.
  void _onValueTextFocusChanged() {
    if (_valueTextFocusNode.hasFocus) {
      return;
    }
    final Object? parsedValue = _parseSettingText(widget.nodeSetting.typeName, _valueTextController.text);
    if (parsedValue == null) {
      setState(() {
        _textErrorText = WizardStrings.getSettingInputErrorText(
          expectedInputText: _describeExpectedInput(widget.nodeSetting.typeName),
        );
      });
    }
  }

  void _resetToDefault() {
    _typedValueReportTimer?.cancel();
    // So the field shows the default the owner sets instead of keeping the typed text
    _valueTextFocusNode.unfocus();
    setState(() {
      _textErrorText = null;
    });
    widget.onResetToDefault?.call();
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
    return _buildSettingRow(widget.nodeSetting, textTheme, mutedTextColor);
  }

  Widget _buildSettingRow(NodeSetting nodeSetting, TextTheme textTheme, Color mutedTextColor) {
    final TextStyle? mutedSmallTextStyle = textTheme.bodySmall?.copyWith(color: mutedTextColor);
    final List<String> detailParts = [];
    final String? rangeText = _formatRange(nodeSetting);
    if (rangeText != null) {
      detailParts.add(rangeText);
    }
    final String? lockedText = widget.lockedText;
    if (!widget.isEditable && lockedText != null) {
      detailParts.add(lockedText);
    }

    final Widget nameText = Text(nodeSetting.settingName, style: textTheme.bodyMedium);
    final Widget? settingControl = _buildSettingControl(nodeSetting);
    // Without a control, the value is written out next to the name
    Widget? valueText;
    if (settingControl == null) {
      // Wraps instead of overflowing: values can be long, e.g. a file URL, and must stay readable in full.
      valueText = Text(_formatValue(_getShownValue(nodeSetting)), style: textTheme.titleSmall, textAlign: TextAlign.end);
    }
    final Widget nameAndControl = LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      Widget valueOrControl = settingControl ?? Align(alignment: Alignment.centerRight, child: valueText);
      final Widget? resetButton = _buildResetButton(nodeSetting);
      if (resetButton != null) {
        valueOrControl = Row(children: [Expanded(child: valueOrControl), resetButton]);
      }
      if (constraints.maxWidth >= settingRowOneLineMinimumWidthLogicalPx) {
        final Widget rightAlignedNameText =
            Text(nodeSetting.settingName, style: textTheme.bodyMedium, textAlign: TextAlign.end);
        return Row(children: [
          Expanded(flex: 2, child: rightAlignedNameText),
          const SizedBox(width: 12),
          Expanded(flex: 3, child: valueOrControl),
        ]);
      }
      if (settingControl == null) {
        return Row(children: [Expanded(child: nameText), const SizedBox(width: 12), Flexible(child: valueOrControl)]);
      }
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [nameText, settingControl]);
    });

    final List<Widget> rowLines = [nameAndControl];
    if (detailParts.isNotEmpty) {
      rowLines.add(Text(detailParts.join(' · '), style: mutedSmallTextStyle));
    }
    if (nodeSetting.description.isNotEmpty) {
      rowLines.add(Text(nodeSetting.description, style: mutedSmallTextStyle));
    }
    // A menu read into a dropdown already shows its options.
    final bool isMenuInDropdown = widget.isEditable && _readMenuOptions(nodeSetting) != null;
    if (nodeSetting.additionalConstraints.isNotEmpty && !isMenuInDropdown) {
      rowLines.add(
        Text(
          WizardStrings.getSettingAllowedValuesText(additionalConstraints: nodeSetting.additionalConstraints),
          style: mutedSmallTextStyle,
        ),
      );
    }
    final String? changeErrorText = _textErrorText ?? widget.errorText;
    if (changeErrorText != null) {
      rowLines.add(Text(changeErrorText, style: textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.error)));
    }
    return Padding(
      padding: const EdgeInsets.only(top: settingRowTopSpacingLogicalPx),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: rowLines),
    );
  }

  /// "Reset to default" while the shown value differs from the default; null otherwise.
  Widget? _buildResetButton(NodeSetting nodeSetting) {
    if (!widget.isEditable || widget.onResetToDefault == null || !nodeSetting.hasDefaultValue) {
      return null;
    }
    if (_isSameValue(_getShownValue(nodeSetting), nodeSetting.defaultValue)) {
      return null;
    }
    return IconButton(
      onPressed: _resetToDefault,
      tooltip: WizardStrings.getResetSettingTooltip(defaultValueText: _formatValue(nodeSetting.defaultValue)),
      icon: const Icon(Icons.restart_alt),
    );
  }

  /// Equal values, also an int and a double of the same number and lists element by element.
  bool _isSameValue(Object? firstValue, Object? secondValue) {
    if (firstValue is num && secondValue is num) {
      return firstValue == secondValue;
    }
    if (firstValue is List && secondValue is List) {
      if (firstValue.length != secondValue.length) {
        return false;
      }
      for (int elementIndex = 0; elementIndex < firstValue.length; elementIndex++) {
        if (!_isSameValue(firstValue[elementIndex], secondValue[elementIndex])) {
          return false;
        }
      }
      return true;
    }
    return firstValue == secondValue;
  }

  /// The slider position while dragged, otherwise the value the owner shows.
  Object? _getShownValue(NodeSetting nodeSetting) {
    final double? draggedSliderValue = _draggedSliderValue;
    if (draggedSliderValue == null) {
      return widget.shownValue;
    }
    if (nodeSetting.typeName == 'integer') {
      return draggedSliderValue.round();
    }
    return draggedSliderValue;
  }

  /// The control for changing the setting, chosen from its descriptor; null when it cannot be changed.
  Widget? _buildSettingControl(NodeSetting nodeSetting) {
    if (!widget.isEditable) {
      return null;
    }
    final Object? settingValue = widget.shownValue;
    if (nodeSetting.typeName == 'bool' && settingValue is bool) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Switch(
          value: settingValue,
          onChanged: (bool isOn) => _reportChange(nodeSetting.settingName, isOn),
        ),
      );
    }
    final List<SettingDropdownOption>? dropdownOptions = _getDropdownOptions(nodeSetting);
    if (dropdownOptions != null && settingValue is int) {
      return _buildSettingDropdown(nodeSetting, settingValue, dropdownOptions);
    }
    final bool isNumber = nodeSetting.typeName == 'integer' || nodeSetting.typeName == 'double';
    final double? minimumValue = nodeSetting.minimumValue;
    final double? maximumValue = nodeSetting.maximumValue;
    if (isNumber && settingValue is num && minimumValue != null && maximumValue != null && minimumValue < maximumValue) {
      return _buildSettingSlider(nodeSetting, settingValue.toDouble(), minimumValue, maximumValue);
    }
    return _buildSettingTextField(nodeSetting);
  }

  /// The choices of a discrete integer setting: a menu's labelled options, or every value of a small range; null
  /// for a setting that is not discrete.
  List<SettingDropdownOption>? _getDropdownOptions(NodeSetting nodeSetting) {
    if (nodeSetting.typeName != 'integer') {
      return null;
    }
    final List<SettingDropdownOption>? menuOptions = _readMenuOptions(nodeSetting);
    if (menuOptions != null) {
      return menuOptions;
    }
    final double? minimumValue = nodeSetting.minimumValue;
    final double? maximumValue = nodeSetting.maximumValue;
    if (minimumValue == null || maximumValue == null || minimumValue >= maximumValue) {
      return null;
    }
    double stepValue = nodeSetting.stepValue ?? 1;
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
  List<SettingDropdownOption>? _readMenuOptions(NodeSetting nodeSetting) {
    if (nodeSetting.typeName != 'integer' || nodeSetting.additionalConstraints.isEmpty) {
      return null;
    }
    final List<SettingDropdownOption> menuOptions = [];
    for (final String optionText in nodeSetting.additionalConstraints.split(',')) {
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

  Widget _buildSettingDropdown(NodeSetting nodeSetting, int settingValue, List<SettingDropdownOption> dropdownOptions) {
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
          _reportChange(nodeSetting.settingName, chosenValue);
        }
      },
    );
  }

  Widget _buildSettingSlider(NodeSetting nodeSetting, double settingValue, double minimumValue, double maximumValue) {
    final String settingName = nodeSetting.settingName;
    final double sliderValue = (_draggedSliderValue ?? settingValue).clamp(minimumValue, maximumValue);
    final Widget slider = Slider(
      value: sliderValue,
      min: minimumValue,
      max: maximumValue,
      divisions: _computeSliderDivisionCount(nodeSetting, minimumValue, maximumValue),
      onChanged: (double draggedValue) {
        setState(() {
          _draggedSliderValue = draggedValue;
        });
      },
      // Sent once on release: every intermediate value would make the driver reconfigure the camera.
      onChangeEnd: (double releasedValue) {
        if (nodeSetting.typeName == 'integer') {
          _reportChange(settingName, releasedValue.round());
        } else {
          _reportChange(settingName, releasedValue);
        }
      },
    );
    // A slider does not show its value, so it is written out next to it
    return Row(children: [
      Expanded(child: slider),
      SizedBox(
        width: sliderValueWidthLogicalPx,
        child: Text(
          _formatValue(_getShownValue(nodeSetting)),
          style: Theme.of(context).textTheme.titleSmall,
          textAlign: TextAlign.end,
        ),
      ),
    ]);
  }

  /// One slider position per allowed value: per step when the range has one, per whole number for an integer;
  /// null (free movement) for a double without a step, or when there would be too many positions to hit.
  int? _computeSliderDivisionCount(NodeSetting nodeSetting, double minimumValue, double maximumValue) {
    double? stepValue = nodeSetting.stepValue;
    if (stepValue == null || stepValue <= 0) {
      if (nodeSetting.typeName != 'integer') {
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

  /// A text field holding the value, which accepts only what the type allows and passes on every valid entry. Lists are
  /// written comma-separated, e.g. "640, 480".
  Widget _buildSettingTextField(NodeSetting nodeSetting) {
    final List<TextInputFormatter> inputFormatters = [];
    final RegExp? typedTextPattern = typedTextPatternByTypeName[nodeSetting.typeName];
    if (typedTextPattern != null) {
      // Keeps the text as it was when a keystroke would make it something the type cannot be
      inputFormatters.add(TextInputFormatter.withFunction((TextEditingValue oldValue, TextEditingValue newValue) {
        if (typedTextPattern.hasMatch(newValue.text)) {
          return newValue;
        }
        return oldValue;
      }));
    }
    TextInputType keyboardType = TextInputType.text;
    if (nodeSetting.typeName == 'integer') {
      keyboardType = const TextInputType.numberWithOptions(signed: true);
    } else if (nodeSetting.typeName == 'double') {
      keyboardType = const TextInputType.numberWithOptions(signed: true, decimal: true);
    }
    return TextField(
      controller: _valueTextController,
      focusNode: _valueTextFocusNode,
      inputFormatters: inputFormatters,
      keyboardType: keyboardType,
      decoration: const InputDecoration(isDense: true),
      onChanged: (String typedText) => _onSettingTextTyped(nodeSetting, typedText),
    );
  }

  /// Passes a valid entry on shortly after the last keystroke; an unfinished one waits for more typing.
  void _onSettingTextTyped(NodeSetting nodeSetting, String typedText) {
    _typedValueReportTimer?.cancel();
    if (_textErrorText != null) {
      setState(() {
        _textErrorText = null;
      });
    }
    final Object? parsedValue = _parseSettingText(nodeSetting.typeName, typedText);
    if (parsedValue == null) {
      return;
    }
    _typedValueReportTimer = Timer(typedValueReportDelay, () {
      if (mounted) {
        _reportChange(nodeSetting.settingName, parsedValue);
      }
    });
  }

  /// What a text field expects, in words, e.g. 'a whole number'.
  String _describeExpectedInput(String typeName) {
    switch (typeName) {
      case 'integer':
        return WizardStrings.expectedWholeNumberText;
      case 'double':
        return WizardStrings.expectedNumberText;
      case 'bool':
        return WizardStrings.expectedBoolText;
      case 'integer array':
        return WizardStrings.expectedWholeNumbersText;
      case 'double array':
        return WizardStrings.expectedNumbersText;
      case 'bool array':
        return WizardStrings.expectedBoolsText;
      default:
        return WizardStrings.expectedValidValueText;
    }
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
  String? _formatRange(NodeSetting nodeSetting) {
    final double? minimumValue = nodeSetting.minimumValue;
    final double? maximumValue = nodeSetting.maximumValue;
    if (minimumValue == null || maximumValue == null) {
      return null;
    }
    final String rangeText = '${_formatNumber(minimumValue)} – ${_formatNumber(maximumValue)}';
    final double? stepValue = nodeSetting.stepValue;
    if (stepValue == null || stepValue == 0) {
      return rangeText;
    }
    return WizardStrings.getSettingRangeWithStepText(rangeText: rangeText, stepText: _formatNumber(stepValue));
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
      return WizardStrings.settingNotSetText;
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
