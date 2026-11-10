// Written by Claude Code
//
// Dialog "Add camera", in three steps: the camera type (installed types only), for a type with serial numbers the
// unit (picked from the connected ones or typed), and the camera's name in the profile, suggested from the type
// (`brio`, then `brio_2`) and fixed once added, since topics, frames and calibration files are named after it. A
// type without serial numbers can be in a profile only once, so it is offered only while it is missing. Opened for
// one camera type (cameraTypeToAdd), it starts with the unit or the name.

import 'package:flutter/material.dart';

import 'cameras_api.dart';
import 'setup_wizard_backend_client.dart';

/// What the user chose to add: the camera's name, its type and, for types with serial numbers, the unit's serial
/// (empty: the driver opens the unit it finds first).
class AddCameraChoice {
  const AddCameraChoice({required this.cameraName, required this.cameraType, required this.serial});

  final String cameraName;
  final String cameraType;
  final String serial;
}

/// Letters, digits, _ and -, what the backend accepts in a serial (it becomes part of file names).
final RegExp serialPattern = RegExp(r'^[A-Za-z0-9_-]+$');

class AddCameraDialog extends StatefulWidget {
  const AddCameraDialog({
    super.key,
    required this.backendClient,
    required this.profileCameras,
    this.cameraTypeToAdd,
  });

  final SetupWizardBackendClient backendClient;

  /// The profile's cameras now, to offer only what can still be added and to suggest a free name.
  final List<ProfileCameraUnit> profileCameras;

  /// A camera type to add, skipping the choice of the type; null starts with the types.
  final String? cameraTypeToAdd;

  @override
  State<AddCameraDialog> createState() => _AddCameraDialogState();
}

class _AddCameraDialogState extends State<AddCameraDialog> {
  bool _isLoading = true;
  String? _loadErrorText;
  List<CameraType> _usableCameraTypes = [];

  /// The connected units of the chosen type, once loaded.
  ConnectedCameraUnits? _connectedUnits;

  /// The chosen type; null while the types are listed.
  String? _chosenCameraType;

  /// The chosen unit's serial ('' for none); null while the unit is being chosen.
  String? _chosenSerial;

  final TextEditingController _serialController = TextEditingController();
  final TextEditingController _cameraNameController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadCameraTypes();
  }

  @override
  void dispose() {
    _serialController.dispose();
    _cameraNameController.dispose();
    super.dispose();
  }

  Future<void> _loadCameraTypes() async {
    setState(() {
      _isLoading = true;
      _loadErrorText = null;
    });
    try {
      final List<CameraType> cameraTypes = await widget.backendClient.fetchCameraTypes();
      if (!mounted) {
        return;
      }
      setState(() {
        _usableCameraTypes = [
          for (final CameraType cameraType in cameraTypes)
            if (cameraType.isUsable) cameraType,
        ];
        _isLoading = false;
      });
      final String? cameraTypeToAdd = widget.cameraTypeToAdd;
      if (cameraTypeToAdd != null) {
        await _chooseCameraType(cameraTypeToAdd);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadErrorText = describeBackendErrorForUser(error);
        _isLoading = false;
      });
    }
  }

  bool _isUnitInProfile(String cameraType, String serial) {
    for (final ProfileCameraUnit profileCamera in widget.profileCameras) {
      if (profileCamera.cameraType == cameraType && profileCamera.serial == serial) {
        return true;
      }
    }
    return false;
  }

  bool _isTypeInProfile(String cameraType) {
    for (final ProfileCameraUnit profileCamera in widget.profileCameras) {
      if (profileCamera.cameraType == cameraType) {
        return true;
      }
    }
    return false;
  }

  Future<void> _chooseCameraType(String cameraType) async {
    setState(() {
      _chosenCameraType = cameraType;
      _connectedUnits = null;
      _chosenSerial = null;
      _serialController.clear();
      _loadErrorText = null;
    });
    final ConnectedCameraUnits connectedUnits;
    try {
      connectedUnits = await widget.backendClient.fetchConnectedCameraUnits(cameraType);
    } catch (error) {
      if (mounted) {
        setState(() {
          _loadErrorText = describeBackendErrorForUser(error);
        });
      }
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _connectedUnits = connectedUnits;
    });
    if (!connectedUnits.hasSerials) {
      _chooseSerial('');
    }
  }

  void _chooseSerial(String serial) {
    final List<String> takenCameraNames = [
      for (final ProfileCameraUnit profileCamera in widget.profileCameras) profileCamera.cameraName,
    ];
    setState(() {
      _chosenSerial = serial;
      _cameraNameController.text = suggestCameraName(_chosenCameraType!, takenCameraNames);
    });
  }

  String? _getCameraNameErrorText(String cameraName) {
    if (!cameraNamePattern.hasMatch(cameraName)) {
      return 'Lower case letters, digits and _, starting with a letter';
    }
    for (final ProfileCameraUnit profileCamera in widget.profileCameras) {
      if (profileCamera.cameraName == cameraName) {
        return 'The profile has a camera of this name already';
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final String? chosenCameraType = _chosenCameraType;
    final ConnectedCameraUnits? connectedUnits = _connectedUnits;
    final String? chosenSerial = _chosenSerial;
    if (chosenCameraType == null || _isLoading) {
      return _buildTypeChoice(context);
    }
    if (connectedUnits == null) {
      return _buildWaitingForUnits(context, chosenCameraType);
    }
    if (chosenSerial == null) {
      return _buildUnitChoice(context, chosenCameraType, connectedUnits);
    }
    return _buildNameChoice(context, chosenCameraType, chosenSerial);
  }

  /// Back to the step before, or Cancel where the dialog started.
  Widget _buildBackButton({required bool isFirstStep, required VoidCallback onBackPressed}) {
    if (isFirstStep) {
      return TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel'));
    }
    return TextButton(onPressed: onBackPressed, child: const Text('Back'));
  }

  Widget _buildTypeChoice(BuildContext context) {
    final String? loadErrorText = _loadErrorText;
    Widget content;
    if (_isLoading) {
      content = const SizedBox(height: 80, child: Center(child: CircularProgressIndicator()));
    } else if (loadErrorText != null) {
      content = Text(loadErrorText);
    } else {
      final List<Widget> typeOptions = [];
      for (final CameraType cameraType in _usableCameraTypes) {
        final bool isOffered = cameraType.hasSerials || !_isTypeInProfile(cameraType.cameraType);
        if (isOffered) {
          typeOptions.add(ListTile(
            leading: const Icon(Icons.videocam_outlined),
            title: Text(cameraType.displayName),
            subtitle: Text(cameraType.cameraType),
            onTap: () => _chooseCameraType(cameraType.cameraType),
          ));
        }
      }
      if (typeOptions.isEmpty) {
        content = const Text('Every camera whose driver is installed is in this profile already.');
      } else {
        content = SizedBox(width: 360, child: ListView(shrinkWrap: true, children: typeOptions));
      }
    }
    return AlertDialog(
      title: const Text('Add camera'),
      content: content,
      actions: [
        if (loadErrorText != null) TextButton(onPressed: _loadCameraTypes, child: const Text('Try again')),
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
      ],
    );
  }

  Widget _buildWaitingForUnits(BuildContext context, String cameraType) {
    final String? loadErrorText = _loadErrorText;
    Widget content = const SizedBox(height: 80, child: Center(child: CircularProgressIndicator()));
    if (loadErrorText != null) {
      content = Text('Could not list the connected $cameraType cameras. $loadErrorText');
    }
    return AlertDialog(
      title: Text('Add a $cameraType'),
      content: content,
      actions: [
        if (loadErrorText != null)
          TextButton(onPressed: () => _chooseCameraType(cameraType), child: const Text('Try again')),
        _buildBackButton(
          isFirstStep: widget.cameraTypeToAdd != null,
          onBackPressed: () => setState(() => _chosenCameraType = null),
        ),
      ],
    );
  }

  Widget _buildUnitChoice(BuildContext context, String cameraType, ConnectedCameraUnits connectedUnits) {
    final List<Widget> unitRows = [];
    if (connectedUnits.isListingSupported) {
      final List<String> addableSerials = [
        for (final String serial in connectedUnits.serials)
          if (!_isUnitInProfile(cameraType, serial)) serial,
      ];
      unitRows.add(Text(addableSerials.isEmpty
          ? 'No other connected $cameraType was found. Connect it, or type its serial number.'
          : 'Connected $cameraType cameras:'));
      for (final String serial in addableSerials) {
        unitRows.add(ListTile(
          leading: const Icon(Icons.usb),
          title: Text(serial),
          onTap: () => _chooseSerial(serial),
        ));
      }
    } else {
      unitRows.add(Text('The units of a $cameraType cannot be listed. Type the serial number printed on the camera.'));
    }
    unitRows.add(const SizedBox(height: 12));
    unitRows.add(TextField(
      controller: _serialController,
      decoration: const InputDecoration(
        labelText: 'Serial number',
        helperText: 'Letters, digits, _ and - only',
        border: OutlineInputBorder(),
        isDense: true,
      ),
      onChanged: (String typedText) => setState(() {}),
    ));
    final String typedSerial = _serialController.text.trim();
    final bool isTypedSerialValid = serialPattern.hasMatch(typedSerial) && !_isUnitInProfile(cameraType, typedSerial);
    // Only the first camera of a type may go without a serial: the backend could not tell a second one apart
    final bool canAddWithoutSerial = !_isTypeInProfile(cameraType);
    return AlertDialog(
      title: Text('Add a $cameraType'),
      content: SizedBox(width: 360, child: ListView(shrinkWrap: true, children: unitRows)),
      actions: [
        _buildBackButton(
          isFirstStep: widget.cameraTypeToAdd != null,
          onBackPressed: () => setState(() => _chosenCameraType = null),
        ),
        if (canAddWithoutSerial)
          Tooltip(
            message: 'The driver opens the first $cameraType it finds.',
            child: TextButton(onPressed: () => _chooseSerial(''), child: const Text('Without serial')),
          ),
        FilledButton(
          onPressed: isTypedSerialValid ? () => _chooseSerial(typedSerial) : null,
          child: const Text('Next'),
        ),
      ],
    );
  }

  Widget _buildNameChoice(BuildContext context, String cameraType, String serial) {
    final String cameraName = _cameraNameController.text.trim();
    final String? cameraNameErrorText = _getCameraNameErrorText(cameraName);
    String unitText = 'A $cameraType.';
    if (serial.isNotEmpty) {
      unitText = 'The $cameraType with serial $serial.';
    }
    final bool hasUnitStep = _connectedUnits?.hasSerials ?? false;
    return AlertDialog(
      title: Text('Name the $cameraType'),
      content: SizedBox(
        width: 360,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$unitText Name it after its role in the setup, e.g. overhead. Topics, frames and calibration files '
                'are named after it, so it stays fixed once added.'),
            const SizedBox(height: 12),
            TextField(
              controller: _cameraNameController,
              autofocus: true,
              decoration: InputDecoration(
                labelText: 'Camera name',
                border: const OutlineInputBorder(),
                isDense: true,
                errorText: cameraNameErrorText,
              ),
              onChanged: (String typedText) => setState(() {}),
            ),
          ],
        ),
      ),
      actions: [
        _buildBackButton(
          isFirstStep: widget.cameraTypeToAdd != null && !hasUnitStep,
          onBackPressed: () => setState(() {
            if (hasUnitStep) {
              _chosenSerial = null;
            } else {
              _chosenCameraType = null;
            }
          }),
        ),
        FilledButton(
          onPressed: cameraNameErrorText == null
              ? () => Navigator.of(context)
                  .pop(AddCameraChoice(cameraName: cameraName, cameraType: cameraType, serial: serial))
              : null,
          child: const Text('Add'),
        ),
      ],
    );
  }
}
