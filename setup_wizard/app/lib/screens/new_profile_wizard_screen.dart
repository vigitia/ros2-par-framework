// Written by Claude Code
//
// Step-by-step wizard for a new hardware setup (profile): hardware, camera image, projector, intrinsics, camera
// pose, projector calibration. Each step lives in its own file and only talks to this shell through NewProfileDraft
// and onCanContinueChanged, so the steps can be built independently. The projector is chosen before the
// calibrations, since they project onto it. The profile is created when leaving the Projector step, because every
// calibration after it (intrinsics, camera pose, projector calibration) is stored per profile. The step after them
// (camera to sensor node mapping) is decided on the card "Setup Wizard" but not built yet.

import 'package:flutter/material.dart';

import '../camera_preview_api.dart';
import '../setup_wizard_backend_client.dart';
import '../extrinsics_calibration_view.dart';
import 'camera_image_step.dart';
import 'extrinsics_calibration_step.dart';
import 'intrinsics_calibration_step.dart';
import 'new_profile_hardware_step.dart';
import 'projector_display_step.dart';

/// Room one step needs in the horizontal stepper's header (number, title, connecting line). Below stepCount times
/// this, the steps are listed vertically instead, so the header does not overflow in narrow windows.
const double horizontalStepperWidthPerStepLogicalPx = 220;

/// What the steps have decided so far for the new profile. Steps write into it; later steps read it.
class NewProfileDraft {
  /// Name shown to the user, e.g. 'Labor Neu'.
  String? profileDisplayName;

  /// Internal name, e.g. 'labor_neu': the file `config/profiles/<profileName>.yaml` and `profile:=<profileName>`.
  String? profileName;

  /// The profile's cameras: none, one or several, also several of one type (e.g. two Brios), while the framework
  /// still launches one camera at a time.
  List<CameraInstanceDraft> cameraInstances = [];

  /// The displays the projectors are connected to, as the framework's display_id (SDL's display index). A list
  /// for setups with several projectors; the projector step picks one for now.
  List<int> projectorDisplayIds = [];

  int countCameraInstancesOfType(String cameraType) {
    int instanceCount = 0;
    for (final CameraInstanceDraft cameraInstance in cameraInstances) {
      if (cameraInstance.cameraType == cameraType) {
        instanceCount += 1;
      }
    }
    return instanceCount;
  }

  /// Adds a camera of cameraType named `<type>_<n>` with the lowest number not taken, e.g. 'brio_2'.
  void addCameraInstance(String cameraType) {
    final Set<String> takenInstanceNames = {};
    for (final CameraInstanceDraft cameraInstance in cameraInstances) {
      takenInstanceNames.add(cameraInstance.instanceName);
    }
    int instanceNumber = 1;
    while (takenInstanceNames.contains('${cameraType}_$instanceNumber')) {
      instanceNumber += 1;
    }
    cameraInstances.add(CameraInstanceDraft(cameraType: cameraType, instanceName: '${cameraType}_$instanceNumber'));
  }

  /// Removes the camera of cameraType added last, like lowering the count in a shopping cart.
  void removeLastCameraInstance(String cameraType) {
    final int lastIndex = cameraInstances.lastIndexWhere(
      (CameraInstanceDraft cameraInstance) => cameraInstance.cameraType == cameraType,
    );
    if (lastIndex >= 0) {
      cameraInstances.removeAt(lastIndex);
    }
  }
}

/// One camera of the new profile: which driver (type) and its name within the profile.
class CameraInstanceDraft {
  CameraInstanceDraft({required this.cameraType, required this.instanceName});

  /// A key of launch_helpers.CAMERA_DRIVER_REMAPPINGS, e.g. 'brio'.
  final String cameraType;

  /// Unique within the profile, e.g. 'brio_2'; used for namespaces, TF frames and calibration file names.
  /// Suggested as `<type>_<n>` (decision on the card: editable when added, fixed afterwards).
  String instanceName;
}

class NewProfileWizardScreen extends StatefulWidget {
  const NewProfileWizardScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<NewProfileWizardScreen> createState() => _NewProfileWizardScreenState();
}

class _NewProfileWizardScreenState extends State<NewProfileWizardScreen> {
  static const int stepCount = 6;

  /// Leaving this step (Projector) creates the profile; the calibrations after it store into the saved profile.
  static const int profileCreatingStepIndex = 2;

  final NewProfileDraft _newProfileDraft = NewProfileDraft();
  int _currentStepIndex = 0;

  /// Per step whether Next is allowed. A step reports false while its input is incomplete, by calling its
  /// onCanContinueChanged (not during build: e.g. from initState through WidgetsBinding.addPostFrameCallback).
  final List<bool> _canContinueByStepIndex = List<bool>.filled(stepCount, true);

  /// True while the backend creates the profile.
  bool _isCreatingProfile = false;

  /// Why creating the profile failed; shown below the step's buttons.
  String? _createProfileErrorText;

  /// The saved profile's name once it is created; null before.
  String? _createdProfileName;

  @override
  void initState() {
    super.initState();
    // Setting changes of an abandoned earlier wizard must not end up in this profile.
    widget.backendClient.discardNewProfileSettings().catchError((Object error) {
      // An unreachable backend shows up in the steps themselves.
    });
  }

  void _setCanContinue(int stepIndex, bool canContinue) {
    if (_canContinueByStepIndex[stepIndex] == canContinue) {
      return;
    }
    setState(() {
      _canContinueByStepIndex[stepIndex] = canContinue;
    });
  }

  Future<void> _goToNextStep() async {
    if (!_canContinueByStepIndex[_currentStepIndex]) {
      return;
    }
    if (_currentStepIndex == stepCount - 1) {
      Navigator.of(context).pop(_createdProfileName);
      return;
    }
    if (_currentStepIndex == profileCreatingStepIndex && _createdProfileName == null) {
      final bool isProfileCreated = await _createProfile();
      if (!isProfileCreated || !mounted) {
        return;
      }
    }
    setState(() {
      _currentStepIndex += 1;
    });
  }

  /// Creates the profile from the draft; returns false and shows why when that fails.
  Future<bool> _createProfile() async {
    final String? profileName = _newProfileDraft.profileName;
    final String profileDisplayName = _newProfileDraft.profileDisplayName ?? '';
    final List<CameraInstanceDraft> cameraInstances = _newProfileDraft.cameraInstances;
    if (profileName == null || cameraInstances.isEmpty) {
      setState(() {
        _createProfileErrorText = 'Add a camera in the Hardware step first.';
      });
      return false;
    }
    // Simplification: the framework launches one camera at a time, so the profile gets the first one. Upgrade:
    // send every camera instance once launch_helpers starts several (card "Setup Wizard").
    final String cameraName = cameraInstances.first.cameraType;
    int? projectorDisplayId;
    if (_newProfileDraft.projectorDisplayIds.isNotEmpty) {
      projectorDisplayId = _newProfileDraft.projectorDisplayIds.first;
    }

    setState(() {
      _isCreatingProfile = true;
      _createProfileErrorText = null;
    });
    String? createProfileErrorText;
    try {
      await widget.backendClient.createProfile(
        profileName: profileName,
        profileDisplayName: profileDisplayName,
        cameraName: cameraName,
        projectorDisplayId: projectorDisplayId,
      );
    } catch (error) {
      createProfileErrorText = describeBackendErrorForUser(error);
    }
    if (!mounted) {
      return false;
    }
    if (createProfileErrorText != null) {
      setState(() {
        _isCreatingProfile = false;
        _createProfileErrorText = 'Could not create the profile: $createProfileErrorText';
      });
      return false;
    }
    setState(() {
      _isCreatingProfile = false;
      _createdProfileName = profileName;
    });
    return true;
  }

  /// Whether Back may leave the current step: not back into the steps the saved profile was created from.
  bool _canGoBackFrom(int stepIndex) {
    // Simplification: a saved profile is not updated from the earlier steps, so they are closed once it exists.
    // Upgrade: write hardware and projector changes into the saved profile (POST /api/profiles only creates).
    return _createdProfileName == null || stepIndex > profileCreatingStepIndex + 1;
  }

  void _goToPreviousStep() {
    if (_currentStepIndex == 0) {
      Navigator.of(context).pop();
      return;
    }
    if (!_canGoBackFrom(_currentStepIndex)) {
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
        content: _buildOnlyWhenCurrentStep(
          0,
          NewProfileHardwareStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            onCanContinueChanged: (bool canContinue) => _setCanContinue(0, canContinue),
          ),
        ),
      ),
      Step(
        title: const Text('Camera image'),
        state: _getStepState(1),
        isActive: _currentStepIndex >= 1,
        content: _buildOnlyWhenCurrentStep(
          1,
          CameraImageStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            onCanContinueChanged: (bool canContinue) => _setCanContinue(1, canContinue),
          ),
        ),
      ),
      Step(
        title: const Text('Projector'),
        state: _getStepState(2),
        isActive: _currentStepIndex >= 2,
        content: _buildOnlyWhenCurrentStep(
          2,
          ProjectorDisplayStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            onCanContinueChanged: (bool canContinue) => _setCanContinue(2, canContinue),
          ),
        ),
      ),
      Step(
        title: const Text('Intrinsics'),
        state: _getStepState(3),
        isActive: _currentStepIndex >= 3,
        content: _buildOnlyWhenCurrentStep(
          3,
          IntrinsicsCalibrationStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            onCanContinueChanged: (bool canContinue) => _setCanContinue(3, canContinue),
          ),
        ),
      ),
      Step(
        title: const Text('Camera pose'),
        state: _getStepState(4),
        isActive: _currentStepIndex >= 4,
        content: _buildOnlyWhenCurrentStep(
          4,
          ExtrinsicsCalibrationStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            calibrationTopic: ExtrinsicsCalibrationTopic.cameraPose,
          ),
        ),
      ),
      Step(
        title: const Text('Projector calibration'),
        state: _getStepState(5),
        isActive: _currentStepIndex >= 5,
        content: _buildOnlyWhenCurrentStep(
          5,
          ExtrinsicsCalibrationStep(
            backendClient: widget.backendClient,
            newProfileDraft: _newProfileDraft,
            calibrationTopic: ExtrinsicsCalibrationTopic.projectorMapping,
          ),
        ),
      ),
    ];

    // Once the profile is saved, leaving the wizard in any way hands it to the start screen, which shows it
    return PopScope<String>(
      canPop: _createdProfileName == null,
      onPopInvokedWithResult: (bool didPop, String? popResult) {
        if (!didPop) {
          Navigator.of(context).pop(_createdProfileName);
        }
      },
      child: _buildWizardScaffold(context, wizardSteps),
    );
  }

  Widget _buildWizardScaffold(BuildContext context, List<Step> wizardSteps) {
    return Scaffold(
      appBar: AppBar(title: const Text('New profile')),
      body: Stepper(
        type: _chooseStepperType(context),
        currentStep: _currentStepIndex,
        steps: wizardSteps,
        onStepContinue: _goToNextStep,
        onStepCancel: _goToPreviousStep,
        controlsBuilder: _buildStepControls,
      ),
    );
  }

  /// Flutter's Stepper keeps every step's content alive, hidden ones included, so a hidden step's camera preview
  /// would run and fight the shown one over the camera. Only the current step gets its content; a step coming
  /// back restores itself from NewProfileDraft.
  Widget _buildOnlyWhenCurrentStep(int stepIndex, Widget stepContent) {
    if (stepIndex != _currentStepIndex) {
      return const SizedBox.shrink();
    }
    return stepContent;
  }

  StepperType _chooseStepperType(BuildContext context) {
    final double windowWidthLogicalPx = MediaQuery.sizeOf(context).width;
    if (windowWidthLogicalPx < stepCount * horizontalStepperWidthPerStepLogicalPx) {
      return StepperType.vertical;
    }
    return StepperType.horizontal;
  }

  Widget _buildStepControls(BuildContext context, ControlsDetails controlsDetails) {
    final int stepIndex = controlsDetails.stepIndex;
    final bool isLastStep = stepIndex == stepCount - 1;
    final bool canContinue = _canContinueByStepIndex[stepIndex];
    final bool isProfileCreatingStep = stepIndex == profileCreatingStepIndex && _createdProfileName == null;
    String nextButtonText = 'Next';
    if (isLastStep) {
      nextButtonText = 'Finish';
    } else if (isProfileCreatingStep) {
      nextButtonText = 'Save profile and continue';
    }
    if (_isCreatingProfile) {
      nextButtonText = 'Saving …';
    }
    final String backButtonText = stepIndex == 0 ? 'Cancel' : 'Back';

    VoidCallback? onNextPressed;
    if (canContinue && !_isCreatingProfile) {
      onNextPressed = controlsDetails.onStepContinue;
    }
    VoidCallback? onBackPressed;
    if (_canGoBackFrom(stepIndex)) {
      onBackPressed = controlsDetails.onStepCancel;
    }
    final List<Widget> controlRows = [
      Row(
        children: [
          FilledButton(onPressed: onNextPressed, child: Text(nextButtonText)),
          const SizedBox(width: 12),
          TextButton(onPressed: onBackPressed, child: Text(backButtonText)),
        ],
      ),
    ];
    if (onBackPressed == null) {
      controlRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
          'The profile is saved, so the steps before cannot be changed here any more.',
          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ));
    }
    final String? createProfileErrorText = _createProfileErrorText;
    if (stepIndex == profileCreatingStepIndex && createProfileErrorText != null) {
      controlRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(createProfileErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: controlRows),
    );
  }
}
