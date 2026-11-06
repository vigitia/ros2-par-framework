// Written by Claude Code
//
// Step-by-step wizard for a new hardware setup (profile): hardware, camera image, intrinsics. Each step lives in
// its own file and only talks to this shell through NewProfileDraft and onCanContinueChanged, so the steps can be
// built independently. The steps after intrinsics are not specified yet (card "Finish setup wizard UI").

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';
import 'camera_image_step.dart';
import 'intrinsics_calibration_step.dart';
import 'new_profile_hardware_step.dart';

/// What the steps have decided so far for the new profile. Steps write into it; later steps read it.
class NewProfileDraft {
  String? profileName;

  /// One camera per profile for now (decision of 2026-11-06), a name from launch_helpers.CAMERA_DRIVER_REMAPPINGS.
  String? cameraName;

  /// The output displays the projectors are connected to.
  List<String> projectorDisplayNames = [];
}

class NewProfileWizardScreen extends StatefulWidget {
  const NewProfileWizardScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<NewProfileWizardScreen> createState() => _NewProfileWizardScreenState();
}

class _NewProfileWizardScreenState extends State<NewProfileWizardScreen> {
  static const int stepCount = 3;

  final NewProfileDraft _newProfileDraft = NewProfileDraft();
  int _currentStepIndex = 0;

  /// Per step whether Next is allowed. A step reports false while its input is incomplete, by calling its
  /// onCanContinueChanged (not during build: e.g. from initState through WidgetsBinding.addPostFrameCallback).
  final List<bool> _canContinueByStepIndex = List<bool>.filled(stepCount, true);

  void _setCanContinue(int stepIndex, bool canContinue) {
    if (_canContinueByStepIndex[stepIndex] == canContinue) {
      return;
    }
    setState(() {
      _canContinueByStepIndex[stepIndex] = canContinue;
    });
  }

  void _goToNextStep() {
    if (!_canContinueByStepIndex[_currentStepIndex]) {
      return;
    }
    if (_currentStepIndex == stepCount - 1) {
      // Simplification: nothing is saved yet, finishing returns to the start screen. Upgrade: create the profile
      // in the backend from _newProfileDraft, then open its hub.
      Navigator.of(context).pop();
      return;
    }
    setState(() {
      _currentStepIndex += 1;
    });
  }

  void _goToPreviousStep() {
    if (_currentStepIndex == 0) {
      Navigator.of(context).pop();
      return;
    }
    setState(() {
      _currentStepIndex -= 1;
    });
  }

  StepState _getStepState(int stepIndex) {
    if (stepIndex < _currentStepIndex) {
      return StepState.complete;
    }
    if (stepIndex == _currentStepIndex) {
      return StepState.editing;
    }
    return StepState.indexed;
  }

  @override
  Widget build(BuildContext context) {
    final List<Step> wizardSteps = [
      Step(
        title: const Text('Hardware'),
        state: _getStepState(0),
        isActive: _currentStepIndex >= 0,
        content: NewProfileHardwareStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          onCanContinueChanged: (bool canContinue) => _setCanContinue(0, canContinue),
        ),
      ),
      Step(
        title: const Text('Camera image'),
        state: _getStepState(1),
        isActive: _currentStepIndex >= 1,
        content: CameraImageStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          onCanContinueChanged: (bool canContinue) => _setCanContinue(1, canContinue),
        ),
      ),
      Step(
        title: const Text('Intrinsics'),
        state: _getStepState(2),
        isActive: _currentStepIndex >= 2,
        content: IntrinsicsCalibrationStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          onCanContinueChanged: (bool canContinue) => _setCanContinue(2, canContinue),
        ),
      ),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('New profile')),
      body: Stepper(
        type: StepperType.horizontal,
        currentStep: _currentStepIndex,
        steps: wizardSteps,
        onStepContinue: _goToNextStep,
        onStepCancel: _goToPreviousStep,
        controlsBuilder: _buildStepControls,
      ),
    );
  }

  Widget _buildStepControls(BuildContext context, ControlsDetails controlsDetails) {
    final bool isLastStep = controlsDetails.stepIndex == stepCount - 1;
    final bool canContinue = _canContinueByStepIndex[controlsDetails.stepIndex];
    final String nextButtonText = isLastStep ? 'Finish' : 'Next';
    final String backButtonText = controlsDetails.stepIndex == 0 ? 'Cancel' : 'Back';

    VoidCallback? onNextPressed;
    if (canContinue) {
      onNextPressed = controlsDetails.onStepContinue;
    }
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Row(
        children: [
          FilledButton(onPressed: onNextPressed, child: Text(nextButtonText)),
          const SizedBox(width: 12),
          TextButton(onPressed: controlsDetails.onStepCancel, child: Text(backButtonText)),
        ],
      ),
    );
  }
}
