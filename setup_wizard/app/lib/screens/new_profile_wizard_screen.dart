// Written by Claude Code
//
// Step-by-step wizard for a new hardware setup (profile): hardware, camera image, projector, intrinsics, camera
// pose, projector calibration. Every step that works per camera has one page per camera, and the camera image has
// two (focus, then the other image settings), so each page handles one topic for one camera; Next names the page
// that follows. Each step lives in its own file and only talks to this shell through NewProfileDraft and
// onCanContinueChanged, so the steps can be built independently. The projector is chosen before the calibrations,
// since they project onto it. The profile is created when leaving the Projector page, because every calibration
// after it (intrinsics, camera pose, projector calibration) is stored per profile. The step after them (camera to
// sensor node mapping) is decided on the card "Setup Wizard" but not built yet.

import 'package:flutter/material.dart';

import '../camera_preview_api.dart';
import '../setup_wizard_backend_client.dart';
import '../camera_section_view.dart';
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

  /// Adds a camera of cameraType named `<type>_<n>` with the lowest number not taken, e.g. 'brio_2'. serial names
  /// the unit; empty for a camera type without serial numbers.
  void addCameraInstance(String cameraType, String serial) {
    final Set<String> takenInstanceNames = {};
    for (final CameraInstanceDraft cameraInstance in cameraInstances) {
      takenInstanceNames.add(cameraInstance.instanceName);
    }
    int instanceNumber = 1;
    while (takenInstanceNames.contains('${cameraType}_$instanceNumber')) {
      instanceNumber += 1;
    }
    cameraInstances.add(CameraInstanceDraft(
      cameraType: cameraType,
      serial: serial,
      instanceName: '${cameraType}_$instanceNumber',
    ));
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

/// One camera of the new profile: which driver (type), which unit of it and its name within the profile.
class CameraInstanceDraft {
  CameraInstanceDraft({required this.cameraType, required this.serial, required this.instanceName});

  /// A key of launch_helpers.CAMERA_DRIVER_REMAPPINGS, e.g. 'brio'.
  final String cameraType;

  /// The unit's serial number, chosen in the Hardware step; empty for a camera type without serial numbers.
  final String serial;

  /// Unique within the profile, e.g. 'brio_2'; used for namespaces, TF frames and calibration file names.
  /// Suggested as `<type>_<n>` (decision on the card: editable when added, fixed afterwards).
  String instanceName;
}

/// What one page of the wizard is about; several pages can belong to one stepper step.
enum WizardPageTopic {
  hardware('Hardware'),
  focus('Focus'),
  imageSettings('Image settings'),
  projector('Projector'),
  intrinsics('Intrinsics'),
  cameraPose('Camera pose'),
  projectorCalibration('Projector calibration');

  const WizardPageTopic(this.titleText);

  final String titleText;
}

/// One page: its topic, the stepper step it belongs to and, for per-camera topics, which camera.
class WizardPage {
  const WizardPage({required this.pageTopic, required this.stepIndex, this.cameraInstanceIndex});

  final WizardPageTopic pageTopic;
  final int stepIndex;

  /// Index into NewProfileDraft.cameraInstances; null for pages that are not per camera, and for a per-camera
  /// step while the profile has no camera (that page says so).
  final int? cameraInstanceIndex;
}

class NewProfileWizardScreen extends StatefulWidget {
  const NewProfileWizardScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<NewProfileWizardScreen> createState() => _NewProfileWizardScreenState();
}

class _NewProfileWizardScreenState extends State<NewProfileWizardScreen> {
  static const int stepCount = 6;
  static const int hardwareStepIndex = 0;
  static const int cameraImageStepIndex = 1;
  static const int projectorStepIndex = 2;
  static const int intrinsicsStepIndex = 3;
  static const int cameraPoseStepIndex = 4;
  static const int projectorCalibrationStepIndex = 5;

  final NewProfileDraft _newProfileDraft = NewProfileDraft();
  int _currentPageIndex = 0;

  /// Per step whether Next is allowed. A step reports false while its input is incomplete, by calling its
  /// onCanContinueChanged (not during build: e.g. from initState through WidgetsBinding.addPostFrameCallback).
  final List<bool> _canContinueByStepIndex = List<bool>.filled(stepCount, true);

  /// True while the backend creates the profile.
  bool _isCreatingProfile = false;

  /// Why creating the profile failed; shown below the page's buttons.
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

  /// The pages for the cameras chosen so far. Built again on every change, since the Hardware page changes the
  /// cameras; the pages after it only exist once it is left, so the current index stays valid.
  List<WizardPage> _createWizardPages() {
    final int cameraCount = _newProfileDraft.cameraInstances.length;
    final List<WizardPage> wizardPages = [
      const WizardPage(pageTopic: WizardPageTopic.hardware, stepIndex: hardwareStepIndex),
    ];
    // Focus and image settings of one camera follow each other, so its preview keeps running between them
    if (cameraCount == 0) {
      wizardPages.add(const WizardPage(pageTopic: WizardPageTopic.focus, stepIndex: cameraImageStepIndex));
    }
    for (int cameraInstanceIndex = 0; cameraInstanceIndex < cameraCount; cameraInstanceIndex += 1) {
      wizardPages.add(WizardPage(
        pageTopic: WizardPageTopic.focus,
        stepIndex: cameraImageStepIndex,
        cameraInstanceIndex: cameraInstanceIndex,
      ));
      wizardPages.add(WizardPage(
        pageTopic: WizardPageTopic.imageSettings,
        stepIndex: cameraImageStepIndex,
        cameraInstanceIndex: cameraInstanceIndex,
      ));
    }
    wizardPages.add(const WizardPage(pageTopic: WizardPageTopic.projector, stepIndex: projectorStepIndex));
    wizardPages.addAll(_createOnePagePerCamera(WizardPageTopic.intrinsics, intrinsicsStepIndex));
    wizardPages.addAll(_createOnePagePerCamera(WizardPageTopic.cameraPose, cameraPoseStepIndex));
    wizardPages.addAll(_createOnePagePerCamera(WizardPageTopic.projectorCalibration, projectorCalibrationStepIndex));
    return wizardPages;
  }

  /// One page per camera, or one page that says there is no camera.
  List<WizardPage> _createOnePagePerCamera(WizardPageTopic pageTopic, int stepIndex) {
    final int cameraCount = _newProfileDraft.cameraInstances.length;
    if (cameraCount == 0) {
      return [WizardPage(pageTopic: pageTopic, stepIndex: stepIndex)];
    }
    final List<WizardPage> cameraPages = [];
    for (int cameraInstanceIndex = 0; cameraInstanceIndex < cameraCount; cameraInstanceIndex += 1) {
      cameraPages.add(WizardPage(pageTopic: pageTopic, stepIndex: stepIndex, cameraInstanceIndex: cameraInstanceIndex));
    }
    return cameraPages;
  }

  int _findProjectorPageIndex(List<WizardPage> wizardPages) {
    return wizardPages.indexWhere((WizardPage wizardPage) => wizardPage.pageTopic == WizardPageTopic.projector);
  }

  void _setCanContinue(int stepIndex, bool canContinue) {
    if (_canContinueByStepIndex[stepIndex] == canContinue) {
      return;
    }
    setState(() {
      _canContinueByStepIndex[stepIndex] = canContinue;
    });
  }

  Future<void> _goToNextPage() async {
    final List<WizardPage> wizardPages = _createWizardPages();
    final WizardPage currentPage = wizardPages[_currentPageIndex];
    if (!_canContinueByStepIndex[currentPage.stepIndex]) {
      return;
    }
    if (_currentPageIndex == wizardPages.length - 1) {
      Navigator.of(context).pop(_createdProfileName);
      return;
    }
    if (currentPage.pageTopic == WizardPageTopic.projector && _createdProfileName == null) {
      final bool isProfileCreated = await _createProfile();
      if (!isProfileCreated || !mounted) {
        return;
      }
    }
    setState(() {
      _currentPageIndex += 1;
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
    final String cameraSerial = cameraInstances.first.serial;
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
        cameraSerial: cameraSerial,
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

  /// Whether Back may leave the page: not back into the pages the saved profile was created from.
  bool _canGoBackFrom(int pageIndex, List<WizardPage> wizardPages) {
    // Simplification: a saved profile is not updated from the earlier pages, so they are closed once it exists.
    // Upgrade: write hardware and projector changes into the saved profile (POST /api/profiles only creates).
    return _createdProfileName == null || pageIndex - 1 > _findProjectorPageIndex(wizardPages);
  }

  void _goToPreviousPage() {
    if (_currentPageIndex == 0) {
      Navigator.of(context).pop();
      return;
    }
    if (!_canGoBackFrom(_currentPageIndex, _createWizardPages())) {
      return;
    }
    setState(() {
      _currentPageIndex -= 1;
    });
  }

  StepState _getStepState(int stepIndex, int currentStepIndex) {
    if (stepIndex < currentStepIndex) {
      return StepState.complete;
    }
    if (stepIndex == currentStepIndex) {
      return StepState.editing;
    }
    return StepState.indexed;
  }

  @override
  Widget build(BuildContext context) {
    final List<WizardPage> wizardPages = _createWizardPages();
    final WizardPage currentPage = wizardPages[_currentPageIndex];
    const List<String> stepTitleTexts = [
      'Hardware',
      'Camera image',
      'Projector',
      'Intrinsics',
      'Camera pose',
      'Projector calibration',
    ];
    final List<Step> wizardSteps = [];
    for (int stepIndex = 0; stepIndex < stepCount; stepIndex += 1) {
      Widget stepContent = const SizedBox.shrink();
      // Flutter's Stepper keeps every step's content alive, hidden ones included, so a hidden step's camera preview
      // would run and fight the shown one over the camera. Only the current page gets built; a page coming back
      // restores itself from NewProfileDraft.
      if (stepIndex == currentPage.stepIndex) {
        stepContent = _buildPage(currentPage);
      }
      wizardSteps.add(Step(
        title: Text(stepTitleTexts[stepIndex]),
        state: _getStepState(stepIndex, currentPage.stepIndex),
        isActive: currentPage.stepIndex >= stepIndex,
        content: stepContent,
      ));
    }

    // Once the profile is saved, leaving the wizard in any way hands it to the hub, which shows it
    return PopScope<String>(
      canPop: _createdProfileName == null,
      onPopInvokedWithResult: (bool didPop, String? popResult) {
        if (!didPop) {
          Navigator.of(context).pop(_createdProfileName);
        }
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('New profile')),
        body: Stepper(
          type: _chooseStepperType(context),
          currentStep: currentPage.stepIndex,
          steps: wizardSteps,
          onStepContinue: _goToNextPage,
          onStepCancel: _goToPreviousPage,
          controlsBuilder: (BuildContext context, ControlsDetails controlsDetails) =>
              _buildPageControls(context, wizardPages),
        ),
      ),
    );
  }

  /// The page's header (topic and camera) above its content. Every page of a step has the same layout, so going
  /// from one page to the next of the same step updates its content instead of building it anew: the camera
  /// preview keeps running from Focus to Image settings.
  Widget _buildPage(WizardPage wizardPage) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildPageHeader(wizardPage),
        const SizedBox(height: 12),
        _buildPageContent(wizardPage),
      ],
    );
  }

  Widget _buildPageHeader(WizardPage wizardPage) {
    final int? cameraInstanceIndex = wizardPage.cameraInstanceIndex;
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color mutedTextColor = Theme.of(context).colorScheme.onSurfaceVariant;
    if (cameraInstanceIndex == null) {
      return Text(wizardPage.pageTopic.titleText, style: textTheme.titleLarge);
    }
    final List<CameraInstanceDraft> cameraInstances = _newProfileDraft.cameraInstances;
    final CameraInstanceDraft cameraInstance = cameraInstances[cameraInstanceIndex];
    final List<Widget> headerRows = [
      Text('${wizardPage.pageTopic.titleText}: ${cameraInstance.instanceName}', style: textTheme.titleLarge),
      Text('Camera ${cameraInstanceIndex + 1} of ${cameraInstances.length}', style: TextStyle(color: mutedTextColor)),
    ];
    final String? sameTypeNoteText = _getSameTypeNoteText(cameraInstance);
    if (sameTypeNoteText != null) {
      headerRows.add(Text(sameTypeNoteText, style: TextStyle(color: mutedTextColor)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: headerRows);
  }

  /// A note while the profile has several cameras of this one's type: they cannot be told apart yet.
  String? _getSameTypeNoteText(CameraInstanceDraft cameraInstance) {
    // With a serial, the preview opens this camera's own unit
    if (cameraInstance.serial.isNotEmpty) {
      return null;
    }
    if (_newProfileDraft.countCameraInstancesOfType(cameraInstance.cameraType) < 2) {
      return null;
    }
    // Simplification: a camera type without serial numbers is started by type, so every instance of it opens the
    // same unit. Upgrade: tell its units apart another way (e.g. by USB port).
    return 'Every ${cameraInstance.cameraType} shows the same camera for now: choosing which unit belongs to which '
        'camera comes later.';
  }

  Widget _buildPageContent(WizardPage wizardPage) {
    final int? cameraInstanceIndex = wizardPage.cameraInstanceIndex;
    CameraInstanceDraft? cameraInstance;
    if (cameraInstanceIndex != null) {
      cameraInstance = _newProfileDraft.cameraInstances[cameraInstanceIndex];
    }
    switch (wizardPage.pageTopic) {
      case WizardPageTopic.hardware:
        return NewProfileHardwareStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          onCanContinueChanged: (bool canContinue) => _setCanContinue(hardwareStepIndex, canContinue),
        );
      case WizardPageTopic.projector:
        return ProjectorDisplayStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          onCanContinueChanged: (bool canContinue) => _setCanContinue(projectorStepIndex, canContinue),
        );
      case WizardPageTopic.focus:
      case WizardPageTopic.imageSettings:
        if (cameraInstance == null) {
          return const Text('No camera was chosen in the Hardware step, so there is no camera image to set up.');
        }
        CameraImagePageTopic cameraImagePageTopic = CameraImagePageTopic.focus;
        if (wizardPage.pageTopic == WizardPageTopic.imageSettings) {
          cameraImagePageTopic = CameraImagePageTopic.imageSettings;
        }
        return CameraImageStep(
          backendClient: widget.backendClient,
          cameraInstance: cameraInstance,
          cameraImagePageTopic: cameraImagePageTopic,
        );
      case WizardPageTopic.intrinsics:
        if (cameraInstance == null) {
          return const Text('No camera was chosen in the Hardware step, so there is nothing to calibrate.');
        }
        return IntrinsicsCalibrationStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          cameraInstance: cameraInstance,
        );
      case WizardPageTopic.cameraPose:
      case WizardPageTopic.projectorCalibration:
        if (cameraInstance == null) {
          return const Text('No camera was chosen in the Hardware step, so there is nothing to calibrate.');
        }
        CameraSection cameraSection = CameraSection.cameraPose;
        if (wizardPage.pageTopic == WizardPageTopic.projectorCalibration) {
          cameraSection = CameraSection.projectorCalibration;
        }
        return ExtrinsicsCalibrationStep(
          backendClient: widget.backendClient,
          newProfileDraft: _newProfileDraft,
          cameraInstance: cameraInstance,
          cameraSection: cameraSection,
        );
    }
  }

  StepperType _chooseStepperType(BuildContext context) {
    final double windowWidthLogicalPx = MediaQuery.sizeOf(context).width;
    if (windowWidthLogicalPx < stepCount * horizontalStepperWidthPerStepLogicalPx) {
      return StepperType.vertical;
    }
    return StepperType.horizontal;
  }

  /// What Next leads to, e.g. 'Image settings: brio_1'.
  String _getPageLabelText(WizardPage wizardPage) {
    final int? cameraInstanceIndex = wizardPage.cameraInstanceIndex;
    if (cameraInstanceIndex == null) {
      return wizardPage.pageTopic.titleText;
    }
    final String instanceName = _newProfileDraft.cameraInstances[cameraInstanceIndex].instanceName;
    return '${wizardPage.pageTopic.titleText}: $instanceName';
  }

  Widget _buildPageControls(BuildContext context, List<WizardPage> wizardPages) {
    final WizardPage currentPage = wizardPages[_currentPageIndex];
    final bool isLastPage = _currentPageIndex == wizardPages.length - 1;
    final bool canContinue = _canContinueByStepIndex[currentPage.stepIndex];
    final bool isProfileCreatingPage = currentPage.pageTopic == WizardPageTopic.projector && _createdProfileName == null;
    String nextButtonText;
    if (_isCreatingProfile) {
      nextButtonText = 'Saving …';
    } else if (isLastPage) {
      nextButtonText = 'Finish';
    } else if (isProfileCreatingPage) {
      nextButtonText = 'Save profile, next: ${_getPageLabelText(wizardPages[_currentPageIndex + 1])}';
    } else {
      nextButtonText = 'Next: ${_getPageLabelText(wizardPages[_currentPageIndex + 1])}';
    }
    String backButtonText = 'Back';
    if (_currentPageIndex == 0) {
      backButtonText = 'Cancel';
    }

    VoidCallback? onNextPressed;
    if (canContinue && !_isCreatingProfile) {
      onNextPressed = _goToNextPage;
    }
    VoidCallback? onBackPressed;
    final bool canGoBack = _canGoBackFrom(_currentPageIndex, wizardPages);
    if (canGoBack) {
      onBackPressed = _goToPreviousPage;
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
    if (!canGoBack) {
      controlRows.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
          'The profile is saved, so the steps before cannot be changed here any more.',
          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ));
    }
    final String? createProfileErrorText = _createProfileErrorText;
    if (isProfileCreatingPage && createProfileErrorText != null) {
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
