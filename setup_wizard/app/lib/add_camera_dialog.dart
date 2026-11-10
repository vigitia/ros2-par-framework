// Written by Claude Code
//
// Dialog "Add camera": the camera types whose driver is installed; a type with serial numbers goes on to the
// connected units, to pick the one to add or to type its serial, since several units of one type can be in a
// profile. A type without serial numbers can be in a profile only once, so it is offered only while it is missing.
// Opened for one camera type (unitChoiceCameraName), it only asks for the unit.

import 'package:flutter/material.dart';

import 'cameras_api.dart';
import 'setup_wizard_backend_client.dart';

/// What the user chose to add: a camera type and, for types with serial numbers, the unit's serial (else empty).
class AddCameraChoice {
  const AddCameraChoice({required this.cameraName, required this.serial});

  final String cameraName;
  final String serial;
}

/// Letters, digits, _ and -, what the backend accepts in a serial (it becomes part of file names).
final RegExp serialPattern = RegExp(r'^[A-Za-z0-9_-]+$');

class AddCameraDialog extends StatefulWidget {
  const AddCameraDialog({
    super.key,
    required this.backendClient,
    required this.profileUnits,
    this.unitChoiceCameraName,
  });

  final SetupWizardBackendClient backendClient;

  /// The profile's cameras now, as (camera type, serial), to offer only what can still be added.
  final List<({String cameraName, String serial})> profileUnits;

  /// A camera type with serial numbers whose unit is to be chosen, skipping the choice of the type; null starts
  /// with the types.
  final String? unitChoiceCameraName;

  @override
  State<AddCameraDialog> createState() => _AddCameraDialogState();
}

class _AddCameraDialogState extends State<AddCameraDialog> {
  bool _isLoading = true;
  String? _loadErrorText;
  final Map<String, ConnectedCameraUnits> _unitsByCameraName = {};

  /// The type whose unit is being chosen; null while the types are listed.
  String? _unitChoiceCameraName;
  final TextEditingController _serialController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _unitChoiceCameraName = widget.unitChoiceCameraName;
    _loadCameraTypes();
  }

  @override
  void dispose() {
    _serialController.dispose();
    super.dispose();
  }

  Future<void> _loadCameraTypes() async {
    setState(() {
      _isLoading = true;
      _loadErrorText = null;
    });
    try {
      final List<SupportedCamera> supportedCameras = await widget.backendClient.fetchSupportedCameras();
      final Map<String, ConnectedCameraUnits> unitsByCameraName = {};
      for (final SupportedCamera supportedCamera in supportedCameras) {
        if (supportedCamera.isInstalled) {
          unitsByCameraName[supportedCamera.cameraName] =
              await widget.backendClient.fetchConnectedCameraUnits(supportedCamera.cameraName);
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _unitsByCameraName
          ..clear()
          ..addAll(unitsByCameraName);
        _isLoading = false;
      });
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

  bool _isUnitInProfile(String cameraName, String serial) {
    for (final unit in widget.profileUnits) {
      if (unit.cameraName == cameraName && unit.serial == serial) {
        return true;
      }
    }
    return false;
  }

  bool _isTypeInProfile(String cameraName) {
    for (final unit in widget.profileUnits) {
      if (unit.cameraName == cameraName) {
        return true;
      }
    }
    return false;
  }

  void _chooseCameraType(String cameraName) {
    final ConnectedCameraUnits units = _unitsByCameraName[cameraName]!;
    if (!units.isSerialSupported) {
      Navigator.of(context).pop(AddCameraChoice(cameraName: cameraName, serial: ''));
      return;
    }
    setState(() {
      _unitChoiceCameraName = cameraName;
      _serialController.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final String? unitChoiceCameraName = _unitChoiceCameraName;
    // The units are known once the types have loaded
    if (unitChoiceCameraName != null && _unitsByCameraName.containsKey(unitChoiceCameraName)) {
      return _buildUnitChoice(context, unitChoiceCameraName);
    }
    return _buildTypeChoice(context);
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
      for (final MapEntry<String, ConnectedCameraUnits> entry in _unitsByCameraName.entries) {
        final bool isOffered = entry.value.isSerialSupported || !_isTypeInProfile(entry.key);
        if (isOffered) {
          typeOptions.add(ListTile(
            leading: const Icon(Icons.videocam_outlined),
            title: Text(entry.key),
            onTap: () => _chooseCameraType(entry.key),
          ));
        }
      }
      if (typeOptions.isEmpty) {
        content = const Text('Every camera whose driver is installed is in this profile already.');
      } else {
        content = SizedBox(width: 320, child: ListView(shrinkWrap: true, children: typeOptions));
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

  Widget _buildUnitChoice(BuildContext context, String cameraName) {
    final ConnectedCameraUnits units = _unitsByCameraName[cameraName]!;
    final List<Widget> unitRows = [];
    if (units.isListingSupported) {
      final List<String> addableSerials = [
        for (final String serial in units.serials)
          if (!_isUnitInProfile(cameraName, serial)) serial,
      ];
      unitRows.add(Text(addableSerials.isEmpty
          ? 'No other connected $cameraName was found. Connect it, or type its serial number.'
          : 'Connected $cameraName cameras:'));
      for (final String serial in addableSerials) {
        unitRows.add(ListTile(
          leading: const Icon(Icons.usb),
          title: Text(serial),
          onTap: () => Navigator.of(context).pop(AddCameraChoice(cameraName: cameraName, serial: serial)),
        ));
      }
    } else {
      unitRows.add(Text('The units of a $cameraName cannot be listed. Type the serial number printed on the camera.'));
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
    final bool isTypedSerialValid = serialPattern.hasMatch(typedSerial) && !_isUnitInProfile(cameraName, typedSerial);
    return AlertDialog(
      title: Text('Add a $cameraName'),
      content: SizedBox(width: 360, child: ListView(shrinkWrap: true, children: unitRows)),
      actions: [
        if (widget.unitChoiceCameraName == null)
          TextButton(onPressed: () => setState(() => _unitChoiceCameraName = null), child: const Text('Back'))
        else
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
        FilledButton(
          onPressed: isTypedSerialValid
              ? () => Navigator.of(context).pop(AddCameraChoice(cameraName: cameraName, serial: typedSerial))
              : null,
          child: const Text('Add'),
        ),
      ],
    );
  }
}
