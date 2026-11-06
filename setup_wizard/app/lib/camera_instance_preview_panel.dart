// Written by Claude Code
//
// The profile's cameras one by one: a selector over the camera instances ('brio_1', 'brio_2', ...), the live
// preview of the selected one and, if wanted, its settings next to the preview. Shared by the wizard steps that
// work through the cameras (camera image, intrinsics).

import 'package:flutter/material.dart';

import 'camera_preview_view.dart';
import 'camera_settings_view.dart';
import 'screens/new_profile_wizard_screen.dart';
import 'setup_wizard_backend_client.dart';

/// Height of the preview; the image keeps its aspect ratio within it.
const double cameraInstancePreviewHeightLogicalPx = 480;

/// Below this width the settings go under the preview instead of next to it.
const double sideBySideSettingsMinimumWidthLogicalPx = 1000;

class CameraInstancePreviewPanel extends StatefulWidget {
  const CameraInstancePreviewPanel({
    super.key,
    required this.backendClient,
    required this.cameraInstances,
    required this.isSettingsListShown,
  });

  final SetupWizardBackendClient backendClient;
  final List<CameraInstanceDraft> cameraInstances;

  /// Shows the selected camera's settings next to its preview.
  final bool isSettingsListShown;

  @override
  State<CameraInstancePreviewPanel> createState() => _CameraInstancePreviewPanelState();
}

class _CameraInstancePreviewPanelState extends State<CameraInstancePreviewPanel> {
  /// Index into cameraInstances of the camera shown.
  int _selectedInstanceIndex = 0;

  void _selectInstance(int instanceIndex) {
    setState(() {
      _selectedInstanceIndex = instanceIndex;
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<CameraInstanceDraft> cameraInstances = widget.cameraInstances;
    // The list may have shrunk after going back to the hardware step
    int selectedInstanceIndex = _selectedInstanceIndex;
    if (selectedInstanceIndex >= cameraInstances.length) {
      selectedInstanceIndex = 0;
    }
    final CameraInstanceDraft selectedInstance = cameraInstances[selectedInstanceIndex];

    final List<Widget> panelRows = [
      _buildInstanceChoiceRow(selectedInstanceIndex),
      const SizedBox(height: 8),
    ];
    final String? sameTypeNoteText = _getSameTypeNoteText(selectedInstance);
    if (sameTypeNoteText != null) {
      panelRows.add(Text(sameTypeNoteText, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)));
      panelRows.add(const SizedBox(height: 8));
    }
    panelRows.add(_buildPreviewAndSettings(selectedInstance));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: panelRows);
  }

  Widget _buildInstanceChoiceRow(int selectedInstanceIndex) {
    final List<CameraInstanceDraft> cameraInstances = widget.cameraInstances;
    final List<ButtonSegment<int>> instanceSegments = [];
    for (int instanceIndex = 0; instanceIndex < cameraInstances.length; instanceIndex += 1) {
      final String instanceName = cameraInstances[instanceIndex].instanceName;
      instanceSegments.add(ButtonSegment<int>(value: instanceIndex, label: Text(instanceName)));
    }

    final List<Widget> choiceRowItems = [
      SegmentedButton<int>(
        segments: instanceSegments,
        selected: {selectedInstanceIndex},
        onSelectionChanged: (Set<int> selectedIndices) => _selectInstance(selectedIndices.first),
      ),
      const SizedBox(width: 16),
      Text('Camera ${selectedInstanceIndex + 1} of ${cameraInstances.length}'),
    ];
    final bool hasNextInstance = selectedInstanceIndex < cameraInstances.length - 1;
    if (hasNextInstance) {
      choiceRowItems.add(const SizedBox(width: 8));
      choiceRowItems.add(TextButton(
        onPressed: () => _selectInstance(selectedInstanceIndex + 1),
        child: const Text('Next camera'),
      ));
    }
    return Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: choiceRowItems);
  }

  /// A note while the profile has several cameras of the selected one's type: they cannot be told apart yet.
  String? _getSameTypeNoteText(CameraInstanceDraft selectedInstance) {
    int sameTypeInstanceCount = 0;
    for (final CameraInstanceDraft cameraInstance in widget.cameraInstances) {
      if (cameraInstance.cameraType == selectedInstance.cameraType) {
        sameTypeInstanceCount += 1;
      }
    }
    if (sameTypeInstanceCount < 2) {
      return null;
    }
    // Simplification: the preview starts a camera by type with par_setup.yaml's settings, so every instance of a
    // type opens the same unit. Upgrade: choose the unit (serial or USB port) per instance.
    return 'Every ${selectedInstance.cameraType} shows the same camera for now: choosing which unit belongs to '
        'which instance comes later.';
  }

  Widget _buildPreviewAndSettings(CameraInstanceDraft selectedInstance) {
    final Widget previewBox = SizedBox(
      height: cameraInstancePreviewHeightLogicalPx,
      child: Align(
        alignment: Alignment.topLeft,
        // One view for every camera: switching cameras updates it (didUpdateWidget) instead of disposing it.
        child: CameraPreviewView(backendClient: widget.backendClient, cameraName: selectedInstance.cameraType),
      ),
    );
    if (!widget.isSettingsListShown) {
      return previewBox;
    }

    final Widget settingsList = CameraSettingsView(
      backendClient: widget.backendClient,
      cameraName: selectedInstance.cameraType,
    );
    return LayoutBuilder(builder: (BuildContext context, BoxConstraints constraints) {
      if (constraints.maxWidth < sideBySideSettingsMinimumWidthLogicalPx) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [previewBox, const SizedBox(height: 16), settingsList],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: previewBox),
          const SizedBox(width: 24),
          Expanded(flex: 2, child: settingsList),
        ],
      );
    });
  }
}
