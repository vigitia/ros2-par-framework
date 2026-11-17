// Written by Claude Code
//
// The dialog that names a profile, for a new profile and for the copy of one: one name field, checked against the
// existing profiles by the internal name the file gets (e.g. 'Labor Neu' -> 'labor_neu'). It only returns the typed
// name; the hub creates or copies the profile. Also holds how a friendly name becomes the internal one.

import 'package:flutter/material.dart';

import '../../config/wizard_strings.dart';

/// Used when nothing of the friendly name is left after deriving, e.g. for '!!!' or a name in another script.
const String fallbackInternalProfileName = 'profile';

/// Turns a friendly name into an internal one: 'Labor Neu' -> 'labor_neu', 'Büro Süd' -> 'buero_sued'. The result
/// holds only characters profile:= accepts (launch_helpers.FILE_NAME_PART_PATTERN), but may be empty.
String deriveInternalProfileName(String profileDisplayName) {
  String internalName = profileDisplayName.toLowerCase();
  internalName = internalName.replaceAll('ä', 'ae');
  internalName = internalName.replaceAll('ö', 'oe');
  internalName = internalName.replaceAll('ü', 'ue');
  internalName = internalName.replaceAll('ß', 'ss');
  internalName = internalName.replaceAll(RegExp(r'[^a-z0-9]+'), '_');
  internalName = internalName.replaceAll(RegExp(r'^_+|_+$'), '');
  return internalName;
}

/// The internal name for a friendly name: derived, or fallbackInternalProfileName when nothing usable is left.
String createInternalProfileName(String profileDisplayName) {
  final String derivedName = deriveInternalProfileName(profileDisplayName);
  if (derivedName.isEmpty) {
    return fallbackInternalProfileName;
  }
  return derivedName;
}

class ProfileNameDialog extends StatefulWidget {
  const ProfileNameDialog({
    super.key,
    required this.dialogTitle,
    required this.explanationText,
    required this.confirmButtonLabel,
    required this.existingProfileNames,
    this.initialProfileDisplayName = '',
  });

  final String dialogTitle;

  /// Above the name field: what happens with the name, e.g. what a copy takes over.
  final String explanationText;
  final String confirmButtonLabel;

  /// Internal names, as the profile list has them.
  final List<String> existingProfileNames;

  /// The name field's text when the dialog opens, e.g. 'Lab copy'.
  final String initialProfileDisplayName;

  @override
  State<ProfileNameDialog> createState() => _ProfileNameDialogState();
}

class _ProfileNameDialogState extends State<ProfileNameDialog> {
  late final TextEditingController _profileDisplayNameController = TextEditingController(
    text: widget.initialProfileDisplayName,
  );

  /// An empty field shows its error only once the user typed, not when a new profile's dialog opens.
  bool _hasUserTyped = false;

  @override
  void dispose() {
    _profileDisplayNameController.dispose();
    super.dispose();
  }

  /// Why the typed name cannot be used; null when it can.
  String? _getProfileNameErrorText() {
    final String profileDisplayName = _profileDisplayNameController.text.trim();
    if (profileDisplayName.isEmpty) {
      return WizardStrings.profileNameMissingText;
    }
    // Compared by internal name, so 'Lab copy' and 'lab-copy' count as the same profile
    final String profileName = createInternalProfileName(profileDisplayName);
    if (widget.existingProfileNames.contains(profileName)) {
      return WizardStrings.getProfileNameTakenText(profileName: profileName);
    }
    return null;
  }

  void _confirmProfileName() {
    if (_getProfileNameErrorText() != null) {
      return;
    }
    Navigator.of(context).pop(_profileDisplayNameController.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    final String? profileNameErrorText = _getProfileNameErrorText();
    String? shownProfileNameErrorText;
    if (_hasUserTyped || _profileDisplayNameController.text.isNotEmpty) {
      shownProfileNameErrorText = profileNameErrorText;
    }
    // Disabled while the name cannot be used
    VoidCallback? onConfirmPressed;
    if (profileNameErrorText == null) {
      onConfirmPressed = _confirmProfileName;
    }
    return AlertDialog(
      title: Text(widget.dialogTitle),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.explanationText),
            const SizedBox(height: 16),
            TextField(
              controller: _profileDisplayNameController,
              autofocus: true,
              decoration: InputDecoration(
                labelText: WizardStrings.profileNameLabel,
                hintText: WizardStrings.profileNameHint,
                border: const OutlineInputBorder(),
                errorText: shownProfileNameErrorText,
                errorMaxLines: 3,
              ),
              // Rebuilt on every keystroke, so the error shows while typing
              onChanged: (String typedText) => setState(() => _hasUserTyped = true),
              onSubmitted: (String typedText) => _confirmProfileName(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text(WizardStrings.cancelButtonLabel),
        ),
        FilledButton(
          onPressed: onConfirmPressed,
          child: Text(widget.confirmButtonLabel),
        ),
      ],
    );
  }
}
