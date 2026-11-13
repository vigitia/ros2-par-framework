// Written by Claude Code
//
// New profile, step 1: the profile's name and its cameras. The user enters a friendly name (e.g. 'Lab');
// the internal name for files and profile:= (e.g. 'labor_neu') is generated from it and not shown, and a name whose
// profile exists already is refused. Below, the cameras whose driver packages are installed, each with a count
// like in a shopping cart, so a setup can have none, one or several cameras, also several of one type (e.g. two
// Brios). Adding a camera asks for its name in the profile and, for a type with serial numbers, which connected unit
// it is (AddCameraDialog), so the previews of the next steps open that unit and the profile stores its serial.
// Previews and settings follow in the next step.

import 'package:flutter/material.dart';

import '../cameras/add_camera_dialog.dart';
import '../../data/services/cameras_api.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';
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

class NewProfileHardwareStep extends StatefulWidget {
  const NewProfileHardwareStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.onCanContinueChanged,
  });

  final SetupWizardBackendClient backendClient;

  /// What earlier steps decided; this step adds its own choices.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed (see NewProfileWizardScreen for when to call it).
  final ValueChanged<bool> onCanContinueChanged;

  @override
  State<NewProfileHardwareStep> createState() => _NewProfileHardwareStepState();
}

class _NewProfileHardwareStepState extends State<NewProfileHardwareStep> {
  final TextEditingController _profileDisplayNameController = TextEditingController();

  /// Errors are shown only after the user started typing, not on an empty new form.
  bool _hasUserTyped = false;

  bool _isLoadingFromBackend = true;
  String? _backendErrorText;
  Set<String> _existingProfileNames = {};
  List<CameraType> _cameraTypes = [];

  @override
  void initState() {
    super.initState();
    // The stepper rebuilds the step when the user comes back to it, so start from what the draft holds.
    final String profileDisplayName = widget.newProfileDraft.profileDisplayName ?? '';
    _profileDisplayNameController.text = profileDisplayName;
    _hasUserTyped = profileDisplayName.isNotEmpty;
    // Not during build: reporting to the wizard rebuilds it.
    WidgetsBinding.instance.addPostFrameCallback((Duration timeStamp) => _reportCanContinue());
    _loadFromBackend();
  }

  @override
  void dispose() {
    _profileDisplayNameController.dispose();
    super.dispose();
  }

  Future<void> _loadFromBackend() async {
    setState(() {
      _isLoadingFromBackend = true;
      _backendErrorText = null;
    });
    try {
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      final List<CameraType> cameraTypes = await widget.backendClient.fetchCameraTypes();
      if (!mounted) {
        return;
      }
      final Set<String> existingProfileNames = {};
      for (final ProfileSummary profileSummary in profileList.profileSummaries) {
        existingProfileNames.add(profileSummary.profileName);
      }
      setState(() {
        _existingProfileNames = existingProfileNames;
        _cameraTypes = cameraTypes;
        _isLoadingFromBackend = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _backendErrorText = describeBackendErrorForUser(error);
        _isLoadingFromBackend = false;
      });
    }
    _reportCanContinue();
  }

  String? _getProfileDisplayNameErrorText() {
    final String profileDisplayName = _profileDisplayNameController.text.trim();
    if (profileDisplayName.isEmpty) {
      return WizardStrings.profileNameMissingText;
    }
    // Compared by internal name, so 'Labor Neu' and 'labor-neu' count as the same profile.
    final String internalProfileName = createInternalProfileName(profileDisplayName);
    if (_existingProfileNames.contains(internalProfileName)) {
      // The wizard saves the profile before its calibration pages, so a setup left before Finish leaves one behind
      return WizardStrings.getProfileExistsText(internalProfileName: internalProfileName);
    }
    return null;
  }

  /// Next needs a profile name that is not taken, so the existing profiles must have loaded.
  void _reportCanContinue() {
    if (!mounted) {
      return;
    }
    final bool haveExistingProfilesLoaded = !_isLoadingFromBackend && _backendErrorText == null;
    final bool isProfileDisplayNameValid = _getProfileDisplayNameErrorText() == null;
    widget.onCanContinueChanged(haveExistingProfilesLoaded && isProfileDisplayNameValid);
  }

  void _onProfileDisplayNameChanged(String profileDisplayName) {
    setState(() {
      _hasUserTyped = true;
    });
    _writeNamesToDraft();
    _reportCanContinue();
  }

  void _writeNamesToDraft() {
    final String profileDisplayName = _profileDisplayNameController.text.trim();
    widget.newProfileDraft.profileDisplayName = profileDisplayName;
    widget.newProfileDraft.profileName = createInternalProfileName(profileDisplayName);
  }

  /// Adds a camera of cameraType: the user chooses its unit (for a type with serial numbers) and its name.
  Future<void> _addCameraInstance(String cameraType) async {
    final AddCameraChoice? choice = await showDialog<AddCameraChoice>(
      context: context,
      builder: (BuildContext dialogContext) => AddCameraDialog(
        backendClient: widget.backendClient,
        profileCameras: widget.newProfileDraft.getProfileCameraUnits(),
        cameraTypeToAdd: cameraType,
      ),
    );
    if (choice == null || !mounted) {
      return;
    }
    setState(() {
      widget.newProfileDraft.cameraInstances.add(CameraInstanceDraft(
        cameraName: choice.cameraName,
        cameraType: choice.cameraType,
        serial: choice.serial,
      ));
    });
  }

  void _removeCameraInstance(String cameraType) {
    setState(() {
      widget.newProfileDraft.removeLastCameraInstance(cameraType);
    });
  }

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 560),
      child: _buildNameAndCameraChoice(context),
    );
  }

  Widget _buildNameAndCameraChoice(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildProfileDisplayNameField(),
        const SizedBox(height: 32),
        Text(WizardStrings.camerasHeading, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          WizardStrings.addCamerasHintText,
          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 8),
        _buildCameraChoice(context),
      ],
    );
  }

  Widget _buildProfileDisplayNameField() {
    String? profileDisplayNameErrorText;
    if (_hasUserTyped) {
      profileDisplayNameErrorText = _getProfileDisplayNameErrorText();
    }
    return TextField(
      controller: _profileDisplayNameController,
      autofocus: true,
      decoration: InputDecoration(
        labelText: WizardStrings.profileNameLabel,
        hintText: WizardStrings.profileNameHint,
        border: const OutlineInputBorder(),
        errorText: profileDisplayNameErrorText,
        errorMaxLines: 4,
      ),
      onChanged: _onProfileDisplayNameChanged,
    );
  }

  Widget _buildCameraChoice(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    if (_isLoadingFromBackend) {
      return const LinearProgressIndicator();
    }
    if (_backendErrorText != null) {
      return Row(
        children: [
          Expanded(
            child: Text(
              WizardStrings.getHardwareLoadErrorText(backendErrorText: _backendErrorText),
              style: TextStyle(color: colorScheme.error),
            ),
          ),
          TextButton(onPressed: _loadFromBackend, child: const Text(WizardStrings.retryButtonLabel)),
        ],
      );
    }

    final List<Widget> cameraRows = [];
    final List<String> notInstalledCameraNames = [];
    for (final CameraType cameraType in _cameraTypes) {
      if (!cameraType.isUsable) {
        notInstalledCameraNames.add(cameraType.cameraType);
        continue;
      }
      cameraRows.add(_buildCameraCountRow(cameraType));
    }
    if (cameraRows.isEmpty) {
      cameraRows.add(const Text(WizardStrings.noCameraDriverInstalledText));
    }
    if (notInstalledCameraNames.isNotEmpty) {
      cameraRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
          WizardStrings.getCamerasNotInstalledText(notInstalledCameraNames: notInstalledCameraNames),
          style: TextStyle(color: colorScheme.onSurfaceVariant),
        ),
      ));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: cameraRows);
  }

  /// One camera type with − count + like a shopping cart; the cameras it adds are listed below the name.
  Widget _buildCameraCountRow(CameraType cameraTypeSummary) {
    final String cameraType = cameraTypeSummary.cameraType;
    final int instanceCount = widget.newProfileDraft.countCameraInstancesOfType(cameraType);

    final List<String> cameraTexts = [];
    for (final CameraInstanceDraft cameraInstance in widget.newProfileDraft.cameraInstances) {
      if (cameraInstance.cameraType == cameraType) {
        String cameraText = cameraInstance.cameraName;
        if (cameraInstance.serial.isNotEmpty) {
          cameraText = WizardStrings.getCameraWithSerialText(cameraText: cameraText, serial: cameraInstance.serial);
        }
        cameraTexts.add(cameraText);
      }
    }
    String subtitleText = cameraTypeSummary.description;
    if (cameraTexts.isNotEmpty) {
      subtitleText = WizardStrings.getCamerasInSetupText(cameraTexts: cameraTexts);
    }
    // A type without serial numbers fits once: two units could not be told apart
    VoidCallback? onAddPressed = () => _addCameraInstance(cameraType);
    if (!cameraTypeSummary.hasSerials && instanceCount > 0) {
      onAddPressed = null;
    }

    VoidCallback? onRemovePressed;
    if (instanceCount > 0) {
      onRemovePressed = () => _removeCameraInstance(cameraType);
    }
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(cameraTypeSummary.displayName),
      subtitle: Text(subtitleText),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            onPressed: onRemovePressed,
            icon: const Icon(Icons.remove_circle_outline),
            tooltip: WizardStrings.getRemoveOneCameraTooltip(cameraType: cameraType),
          ),
          SizedBox(
            width: 28,
            child: Text('$instanceCount', textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
          ),
          IconButton(
            onPressed: onAddPressed,
            icon: const Icon(Icons.add_circle_outline),
            tooltip: WizardStrings.getAddCameraOfTypeTooltip(cameraType: cameraType),
          ),
        ],
      ),
    );
  }
}
