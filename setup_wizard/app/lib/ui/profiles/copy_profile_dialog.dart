// Written by Claude Code
//
// The dialog that names the copy of a profile: one name field, filled with "<profile> copy", checked against the
// existing profiles as the new-profile wizard checks a name (by the internal name the file gets). It only returns
// the typed name; the hub makes the copy.

import 'package:flutter/material.dart';

import '../new_profile/new_profile_hardware_step.dart';
import '../../config/wizard_strings.dart';

class CopyProfileDialog extends StatefulWidget {
  const CopyProfileDialog({super.key, required this.sourceProfileName, required this.existingProfileNames});

  final String sourceProfileName;

  /// Internal names, as the profile list has them.
  final List<String> existingProfileNames;

  @override
  State<CopyProfileDialog> createState() => _CopyProfileDialogState();
}

class _CopyProfileDialogState extends State<CopyProfileDialog> {
  late final TextEditingController _newProfileDisplayNameController = TextEditingController(
    text: WizardStrings.getCopiedProfileDefaultDisplayName(sourceProfileName: widget.sourceProfileName),
  );

  @override
  void dispose() {
    _newProfileDisplayNameController.dispose();
    super.dispose();
  }

  /// Why the typed name cannot be used; null when it can.
  String? _getNewProfileNameErrorText() {
    final String newProfileDisplayName = _newProfileDisplayNameController.text.trim();
    if (newProfileDisplayName.isEmpty) {
      return WizardStrings.profileNameMissingText;
    }
    // Compared by internal name, so 'Lab copy' and 'lab-copy' count as the same profile
    final String newProfileName = createInternalProfileName(newProfileDisplayName);
    if (widget.existingProfileNames.contains(newProfileName)) {
      return WizardStrings.getCopyProfileNameTakenText(newProfileName: newProfileName);
    }
    return null;
  }

  void _confirmCopy() {
    if (_getNewProfileNameErrorText() != null) {
      return;
    }
    Navigator.of(context).pop(_newProfileDisplayNameController.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    final String? newProfileNameErrorText = _getNewProfileNameErrorText();
    // Disabled while the name cannot be used
    VoidCallback? onCopyPressed;
    if (newProfileNameErrorText == null) {
      onCopyPressed = _confirmCopy;
    }
    return AlertDialog(
      title: Text(WizardStrings.getCopyProfileDialogTitle(sourceProfileName: widget.sourceProfileName)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(WizardStrings.copyProfileDialogText),
          const SizedBox(height: 16),
          TextField(
            controller: _newProfileDisplayNameController,
            autofocus: true,
            decoration: InputDecoration(
              labelText: WizardStrings.profileNameLabel,
              border: const OutlineInputBorder(),
              errorText: newProfileNameErrorText,
              errorMaxLines: 3,
            ),
            // Rebuilt on every keystroke, so the error shows while typing
            onChanged: (String typedText) => setState(() {}),
            onSubmitted: (String typedText) => _confirmCopy(),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text(WizardStrings.cancelButtonLabel),
        ),
        FilledButton(
          onPressed: onCopyPressed,
          child: const Text(WizardStrings.copyButtonLabel),
        ),
      ],
    );
  }
}
