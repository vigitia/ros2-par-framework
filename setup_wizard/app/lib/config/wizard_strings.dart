// Written by Claude Code
//
// Every text the wizard shows to the user, in one place: labels, hints, messages and the sentences around
// values. A text with a value in it is a function of that value. Texts the backend writes (names, error
// details) arrive as data and are not here; neither are console logs, JSON keys and API paths.

abstract final class WizardStrings {
  // App
  static const String appTitle = 'ROS 2 PAR Framework';

  // Buttons and texts shared by several screens
  static const String cancelButtonLabel = 'Cancel';
  static const String tryAgainButtonLabel = 'Try again';
  static const String retryButtonLabel = 'Retry';
  static const String backButtonLabel = 'Back';
  static const String nextButtonLabel = 'Next';
  static const String addButtonLabel = 'Add';
  static const String removeButtonLabel = 'Remove';
  static const String deleteButtonLabel = 'Delete';
  static const String disableButtonLabel = 'Disable';
  static const String stopButtonLabel = 'Stop';
  static const String closeButtonLabel = 'Close';
  static const String refreshButtonLabel = 'Refresh';
  static const String calibrateButtonLabel = 'Calibrate';
  static const String calibrateAgainButtonLabel = 'Calibrate again';
  static const String measuringText = 'Measuring …';
  static const String waitingForFirstFrameText = 'Waiting for the first frame …';
  static const String savingText = 'Saving …';
  static const String warningIconSemanticLabel = 'Warning';

  // Backend errors
  static const String backendNotAnsweringErrorText =
      'The Backend is currently not available. Check that it is switched on and its setup service is running, then try '
      'again.';
  static const String backendInvalidInputErrorText = 'That input is not valid. Please check it and try again.';
  static const String backendNotFoundErrorText = 'Not found. Go back, reload and try again.';
  static const String backendBusyErrorText =
      'That is not possible right now. Wait until what is running has finished, then try again.';
  static const String backendNotReadyErrorText = 'The camera or service is not ready yet. Wait a moment and try again.';
  static const String backendUnknownErrorText = 'Something went wrong. Please try again.';
  static const String profileMissingErrorText =
      'This profile does not exist any more. Choose another one in the Overview.';
  static const String profileFileUnreadableErrorText =
      'This profile\'s file cannot be read. It may contain a mistake from editing it by hand.';

  // Profiles: hub, selector and overview
  static String getStoreProfileSelectionErrorText({required String backendErrorText}) {
    return 'Could not remember the selection for the next start. $backendErrorText';
  }

  static String getProfileCreatedText({required String createdProfileName}) {
    return 'Created profile $createdProfileName.';
  }

  static String getDeleteProfileDialogTitle({required String profileName}) {
    return 'Delete profile $profileName?';
  }

  static const String deleteProfileDialogText =
      'The profile and its camera poses and projector calibration are moved to config/profiles/.deleted/ and '
      'disappear from the app. They can be restored by hand from there. The cameras\' lens calibrations stay.';
  static String getProfileDeletedText({required String profileName, required String deletedProfileFolderPath}) {
    return 'Deleted $profileName. Its files are in $deletedProfileFolderPath';
  }

  static String getDeleteProfileErrorText({required String profileName, required String backendErrorText}) {
    return 'Could not delete $profileName. $backendErrorText';
  }

  static const String noProfileYetText =
      'There is no profile yet. Create one with New profile in the menu at the top right.';
  static const String overviewNavigationLabel = 'Overview';
  static const String projectorsNavigationLabel = 'Projectors';
  static const String camerasNavigationLabel = 'Cameras';
  static const String sensorNodesNavigationLabel = 'Sensor nodes';
  static const String appsNavigationLabel = 'Apps';
  static const String noProfileTitle = 'Profile: none yet';
  static String getProfileTitle({required String shownProfileName}) {
    return 'Profile: $shownProfileName';
  }

  static const String newProfileMenuLabel = 'New profile';
  static String getDeleteProfileMenuLabel({required String deletableProfileName}) {
    return 'Delete $deletableProfileName …';
  }

  static const String profilesMenuTooltip = 'Profiles';
  static const String profileCannotBeShownText = 'This profile cannot be shown.';
  static String getLensCalibrationTitle({required String cameraName}) {
    return '$cameraName: lens calibration (intrinsics)';
  }

  static const String cameraPoseMissingText =
      'Its camera pose is missing: without it, the wizard does not know where the camera is above the table.';
  static const String cameraPoseFileUnusableText =
      'Its camera pose file cannot be used. Measure the camera pose again.';
  static const String overviewProjectorTitle = 'Projector';
  static String getOverviewProjectorTitle({required String projectorTitleText}) {
    return 'Projector $projectorTitleText';
  }

  static String getProjectionMappingMissingText({required String cameraName}) {
    return 'Its projector calibration with $cameraName is missing: '
        'without it, the wizard does not know where the projected image lies on the table.';
  }

  static const String projectorPositionTitle = 'Projector position (projector centre)';
  static const String projectorPositionMissingText =
      'Only the projected image is drawn, not the projector itself. Its position needs a '
      'depth camera: open one under Cameras, then measure it in its Projector section. Only the projection '
      'mask uses it.';
  static String getOptionalCalibrationTitle({required String titleText}) {
    return '$titleText (optional)';
  }

  static const String openProjectorsButtonLabel = 'Open Projectors';
  static String getSetupGeometryErrorText({required String setupGeometryErrorText}) {
    return 'Cannot read the setup\'s calibration: $setupGeometryErrorText';
  }

  static const String notInDrawingHeading = 'Not in the drawing yet';
  static const String calibrationHeading = 'Calibration';
  static const String allCalibrationsDoneText = 'All calibrations are done.';
  static const String nothingMissingText = 'Nothing else is missing.';
  static String getGeometryErrorText({required String geometryErrorText}) {
    return 'Cannot read $geometryErrorText';
  }

  static const String leftSideViewLabel = 'Left';
  static const String frontSideViewLabel = 'Front';
  static const String rightSideViewLabel = 'Right';
  static String getDrawingHeightText({required String heightText}) {
    return 'height $heightText m';
  }

  static String getProjectorDrawingLabel({required String heightText}) {
    return 'projector\n$heightText';
  }

  static const String projectedAreaLabel = 'projected area';
  static String getProjectedAreaSizeLabel({required double widthM, required double heightM}) {
    return 'projected area\n${widthM.toStringAsFixed(2)} × ${heightM.toStringAsFixed(2)} m';
  }

  // Running a profile
  static String getRunStateReadErrorText({required String pollErrorText}) {
    return 'Cannot read whether the profile runs: $pollErrorText';
  }

  static const String profileStoppedByItselfText =
      'The profile stopped by itself. Check that the profile\'s camera is connected, then run it again.';
  static String getAppListForRunErrorText({required String backendErrorText}) {
    return 'Cannot list the apps. $backendErrorText';
  }

  static const String startProfileErrorText = 'Could not start the profile.';
  static const String runWithoutAppMenuLabel = 'No app (camera and sensor nodes only)';
  static const String addAppsUnderAppsMenuLabel = 'Add apps to this profile under Apps';
  static const String stopProfileErrorText = 'Could not stop the profile.';
  static const String runButtonLabel = 'Run';
  static const String runButtonTooltip = 'Choose the app on the projector and start this profile.';
  static String getStopOtherProfileButtonLabel({required String? profileName}) {
    return 'Stop $profileName';
  }

  static String getOtherProfileRunningTooltip({required String? profileName}) {
    return 'The profile $profileName is running. Stop it before running this one.';
  }

  static const String stopThisProfileTooltip = 'This profile is running. Stop it.';

  // New profile wizard
  static const String hardwareStepTitle = 'Hardware';
  static const String cameraSetupStepTitle = 'Camera setup & focus';
  static const String projectorStepTitle = 'Projector';
  static const String intrinsicsStepTitle = 'Intrinsics';
  static const String cameraPoseStepTitle = 'Camera pose';
  static const String projectorCalibrationStepTitle = 'Projector calibration';
  static const String addCameraFirstText = 'Add a camera in the Hardware step first.';
  static String getCreateProfileErrorText({required String? createProfileErrorText}) {
    return 'Could not create the profile: $createProfileErrorText';
  }

  static const String newProfileScreenTitle = 'New profile';
  static String getCameraProgressText({required int cameraInstanceIndex, required int cameraCount}) {
    return 'Camera ${cameraInstanceIndex + 1} of $cameraCount';
  }

  static String getSameCameraUnitText({required String cameraType}) {
    return 'Every $cameraType shows the same camera for now: choosing which unit belongs to which '
        'camera comes later.';
  }

  static const String noCameraForImageText =
      'No camera was chosen in the Hardware step, so there is no camera image to set up.';
  static const String noCameraToCalibrateText =
      'No camera was chosen in the Hardware step, so there is nothing to calibrate.';
  static const String finishButtonLabel = 'Finish';
  static String getSaveProfileNextButtonLabel({required String nextPageLabelText}) {
    return 'Save profile, next: $nextPageLabelText';
  }

  static String getNextPageButtonLabel({required String nextPageLabelText}) {
    return 'Next: $nextPageLabelText';
  }

  static const String profileSavedStepsLockedText =
      'The profile is saved, so the steps before cannot be changed here any more.';
  static const String profileNameMissingText = 'Enter a profile name.';
  static String getProfileExistsText({required String internalProfileName}) {
    return 'The profile "$internalProfileName" exists already, perhaps from a setup that was not finished. '
        'To continue it, open it from the Profiles menu (top right) and calibrate in its Cameras area. To start '
        'over, open it there and delete it. Or choose another name.';
  }

  static const String camerasHeading = 'Cameras';
  static const String addCamerasHintText = 'Add as many of each as the setup has, or none.';
  static const String profileNameLabel = 'Profile name';
  static const String profileNameHint = 'Lab';
  static String getHardwareLoadErrorText({required String? backendErrorText}) {
    return 'Could not load the cameras and profiles: $backendErrorText';
  }

  static const String noCameraDriverInstalledText = 'No camera driver is installed.';
  static String getCamerasNotInstalledText({required Iterable<String> notInstalledCameraNames}) {
    return 'Not installed: ${notInstalledCameraNames.join(', ')}';
  }

  static String getCameraWithSerialText({required String cameraText, required String serial}) {
    return '$cameraText (serial $serial)';
  }

  static String getCamerasInSetupText({required Iterable<String> cameraTexts}) {
    return 'In this setup: ${cameraTexts.join(', ')}';
  }

  static String getRemoveOneCameraTooltip({required String cameraType}) {
    return 'Remove one $cameraType';
  }

  static String getAddCameraOfTypeTooltip({required String cameraType}) {
    return 'Add a $cameraType';
  }

  static const String cameraImageStepText =
      'First adjust the image settings (e.g. exposure, gain, brightness) until the scene is clearly visible, then '
      'set the focus. How the focus is set depends on the camera: a setting in the list, a ring on the lens, or a '
      'control on the device itself. If the camera focuses automatically, switch that off once the image is '
      'sharp, so the focus stays where it is. A camera with a fixed focus needs no focusing.';
  static String getCameraSettingsStepTitle({required String cameraName}) {
    return 'Camera settings: $cameraName';
  }

  static const String profileWithoutNameText = 'The profile has no name yet: go back to the Hardware step.';
  static const String measureCameraPoseIntroText = 'Measure where this camera sits above the table.';
  static const String calibrateProjectorIntroText =
      'Calibrate the projector against this camera, so projected content lands where the camera '
      'sees it. This runs at the table, with the projector on.';
  static const String calibrateLensIntroText = 'Calibrate the lens of this camera, if it needs it.';
  static const String chooseProjectorDisplayText = 'Which display is the projector? Click its card.';

  // Cameras
  static String getAddCameraErrorText({required String backendErrorText}) {
    return 'Could not add the camera. $backendErrorText';
  }

  static String getRemoveCameraDialogTitle({required String cameraName}) {
    return 'Remove $cameraName?';
  }

  static const String removeCameraDialogText =
      'The camera leaves this profile together with its lens calibration, camera pose and projector calibration. '
      'The files are moved to config/profiles/.deleted/ and can be restored by hand from there.';
  static String getRemoveCameraErrorText({required String backendErrorText}) {
    return 'Could not remove the camera. $backendErrorText';
  }

  static const String addCameraButtonLabel = 'Add camera';
  static const String noCameraInProfileText = 'The profile has no camera. Add one with "Add camera".';
  static String getCameraUnitSerialText({required String unitText, required String serial}) {
    return '$unitText, serial $serial';
  }

  static String getMainCameraUnitText({required String unitText}) {
    return '$unitText · main camera (the sensor nodes use it)';
  }

  static const String lastCameraRemoveTooltip = 'A profile needs a camera to run: add another one first.';
  static const String removeCameraTooltip = 'Remove this camera and its calibrations from the profile.';
  static const String cameraImageSettingsTabLabel = 'Image & settings';
  static const String cameraIntrinsicsTabLabel = 'Intrinsics';
  static const String cameraPoseTabLabel = 'Camera pose';
  static const String cameraProjectorTabLabel = 'Projector';
  static const String cameraNameRuleText = 'Lower case letters, digits and _, starting with a letter';
  static const String cameraNameTakenText = 'The profile has a camera of this name already';
  static const String allCamerasInProfileText = 'Every camera whose driver is installed is in this profile already.';
  static const String addCameraDialogTitle = 'Add camera';
  static String getCameraUnitsListErrorText({required String cameraType, required String loadErrorText}) {
    return 'Could not list the connected $cameraType cameras. $loadErrorText';
  }

  static String getAddCameraOfTypeDialogTitle({required String cameraType}) {
    return 'Add a $cameraType';
  }

  static String getNoOtherCameraUnitText({required String cameraType}) {
    return 'No other connected $cameraType was found. Connect it, or type its serial number.';
  }

  static String getConnectedCameraUnitsText({required String cameraType}) {
    return 'Connected $cameraType cameras:';
  }

  static String getCameraUnitsNotListableText({required String cameraType}) {
    return 'The units of a $cameraType cannot be listed. Type the serial number printed on the camera.';
  }

  static const String serialNumberLabel = 'Serial number';
  static const String serialNumberHelperText = 'Letters, digits, _ and - only';
  static String getWithoutSerialTooltip({required String cameraType}) {
    return 'The driver opens the first $cameraType it finds.';
  }

  static const String withoutSerialButtonLabel = 'Without serial';
  static String getCameraUnitText({required String cameraType}) {
    return 'A $cameraType.';
  }

  static String getCameraUnitWithSerialText({required String cameraType, required String serial}) {
    return 'The $cameraType with serial $serial.';
  }

  static String getNameCameraDialogTitle({required String cameraType}) {
    return 'Name the $cameraType';
  }

  static String getCameraNameExplanationText({required String unitText}) {
    return '$unitText Name it after its role in the setup, e.g. overhead. Topics, frames and calibration files '
        'are named after it, so it stays fixed once added.';
  }

  static const String cameraNameLabel = 'Camera name';
  static String getCameraPreviewErrorText({required String runningCameraName, required String previewErrorText}) {
    return 'No preview of $runningCameraName: $previewErrorText';
  }

  static String getCameraPreviewStartingText({required String runningCameraName}) {
    return 'Starting $runningCameraName …';
  }

  static const String lensCalibrationNotNeededText =
      'Nothing to do for this camera: it brings its own lens calibration (e.g. from the factory).';
  static String getCameraSettingsSavedText({
    required String profileName,
    required Iterable<String> writtenSettingNames,
  }) {
    return 'Saved in $profileName: ${writtenSettingNames.join(', ')}.';
  }

  static String getCameraSettingsResetText({required Iterable<String> removedSettingNames}) {
    return 'Back to the defaults of par_setup.yaml: ${removedSettingNames.join(', ')}.';
  }

  static const String nothingToSaveText = 'Nothing to save.';
  static const String cameraSettingsNewProfileText =
      'Changes apply to the running camera at once and are saved with the new profile when you finish.';
  static String getCameraSettingsSavedRightAwayText({required String profileName}) {
    return 'Changes apply to the running camera at once and are saved in $profileName right away.';
  }

  static String getSavingCameraSettingsText({required String profileName}) {
    return 'Saving in $profileName …';
  }

  static String getCameraSettingsSaveErrorText({required String profileName, required String saveErrorText}) {
    return 'Could not save in $profileName: $saveErrorText';
  }

  static String getCameraSettingsNotSavedText({required String profileName, required String unsavedSettingNamesText}) {
    return 'Not saved in $profileName yet: $unsavedSettingNamesText.';
  }

  static const String saveNowButtonLabel = 'Save now';
  static String getCameraSettingsTitle({required String runningCameraName}) {
    return 'Settings: $runningCameraName';
  }

  static const String waitingForCameraSettingsText = 'Waiting for the camera to report its settings …';
  static const String driverReportsNoSettingsText = 'The driver reports no settings to show.';
  static const String fixedByDriverText = 'Fixed by the driver';
  static const String fixedByDriverLockedText = 'fixed by the driver';
  static const String focusHeading = 'Focus';
  static const String focusInstructionsText =
      'Put something with fine, high-contrast detail (printed text, a marker sheet) under the image centre. Change '
      'the focus until the bar reaches the best mark and gets no higher. The value only compares focus settings of '
      'one scene; light and content change it.';
  static String getFocusMeasurementErrorText({required String measurementErrorText}) {
    return 'Waiting for the camera image: $measurementErrorText';
  }

  static String getSharpnessText({required double sharpness, required double peakSharpness}) {
    return 'Sharpness ${sharpness.toStringAsFixed(0)}, best so far ${peakSharpness.toStringAsFixed(0)}';
  }

  static const String resetBestSharpnessButtonLabel = 'Reset best';
  static const String sharpnessSemanticLabel = 'Sharpness';
  static String getSharpnessPercentText({required double sharpness, required double peakSharpness}) {
    return '${(sharpness / peakSharpness * 100).toStringAsFixed(0)} percent of the best so far';
  }

  static const String imageCenterPlaceholderText = 'Image centre';
  static const String enlargedImageCenterSemanticLabel = 'Enlarged image centre, where the sharpness is measured';
  static const String enlargedImageCenterHeading = 'Image centre, enlarged';

  // Checkerboard input, shared by both calibrations
  static const String boardInnerCornersInvalidErrorText = 'The inner corners must be whole numbers of at least 2.';
  static const String boardSquareSizeMissingErrorText =
      'Measure one square of the printed board and enter its size in millimetres.';
  static const String boardInnerCornersAcrossLabel = 'Inner corners across';
  static const String boardInnerCornersDownLabel = 'Inner corners down';
  static const String boardSquareSizeMmLabel = 'Square size in mm (measured on the print)';

  // Lens calibration (intrinsics)
  static const String poseCoverageLeftRightLabel = 'Left – right';
  static const String poseCoverageTopBottomLabel = 'Top – bottom';
  static const String poseCoverageNearFarLabel = 'Near – far';
  static const String poseCoverageTiltLabel = 'Tilt';
  static const String lensCalibrationSavedText = 'Saved.';
  static String getLensCalibrationSavedText({required String saveStatusText}) {
    return 'Saved: $saveStatusText';
  }

  static const String checkingLensCalibrationText = 'Checking the camera\'s lens calibration …';
  static const String cameraWithoutCameraInfoText =
      'This camera publishes no camera_info, so a lens calibration does not apply.';
  static const String lensNeedsCalibrationText = 'Needs a calibration: the camera has no lens calibration yet.';
  static String getLensCalibratedText({required String calibrationFileModifiedIso}) {
    return 'Calibrated (${calibrationFileModifiedIso.replaceFirst('T', ' ')}).';
  }

  static const String lensCalibrationFromCameraText =
      'Uses the calibration the camera reports itself (e.g. from the factory).';
  static const String lensCalibrationProtectedText =
      'This camera brings its own lens calibration (e.g. from the factory). It is protected: the app does not '
      'offer to replace it.';
  static const String lensCalibrationNotStorableText =
      'This camera\'s driver cannot store a calibration (it offers no set_camera_info service), so it cannot be '
      'calibrated from here.';
  static const String startCalibrationButtonLabel = 'Start calibration';
  static const String checkerboardHeading = 'Checkerboard';
  static const String checkerboardInnerCornersText =
      'Inner corners are where four squares meet: a board of 9 × 7 squares has 8 × 6.';
  static const String startingCalibrationText = 'Starting the calibration …';
  static String getComputingCalibrationText({required int sampleCount}) {
    return 'Computing the calibration from $sampleCount views …';
  }

  static const String moveBoardInstructionsText =
      'Hold the board in front of the camera and move it: to every edge and corner of the image, near and far, '
      'and tilted. A view counts when the board is found and differs from the earlier ones.';
  static String getCalibrationViewCountText({required int sampleCount}) {
    return '$sampleCount views';
  }

  static const String holdBoardToCheckText = 'Hold the board in view to check the result.';
  static String getLineStraightnessText({required double linearErrorPx}) {
    return 'Straightness of the board\'s lines now: ${linearErrorPx.toStringAsFixed(2)} px off '
        '(smaller is better).';
  }

  static String getCalibratedFromViewsText({required int sampleCount}) {
    return 'Calibrated from $sampleCount views.';
  }

  static const String undistortedImageText = 'The image is shown undistorted now: straight edges should look straight.';
  static String getFocalLengthText({required double focalLengthXPx, required double focalLengthYPx}) {
    return 'Focal length: ${focalLengthXPx.toStringAsFixed(1)} × ${focalLengthYPx.toStringAsFixed(1)} px';
  }

  static const String savingCalibrationText = 'Saving the calibration …';

  // Camera pose and projector calibration (extrinsics)
  static const String qualityFigureBoardReprojectionErrorLabel = 'Board corners off the fitted board (px)';
  static const String qualityFigureBoardNormalSpreadLabel = 'Tilt spread between frames (°)';
  static const String qualityFigureBoardFramesLabel = 'Frames averaged';
  static const String qualityFigureTableFractionLabel = 'Share of the image on the table plane';
  static const String qualityFigureTableRmsLabel = 'Table plane fit error (mm)';
  static const String qualityFigureMethodLabel = 'Method';
  static const String readingProfileCalibrationText = 'Reading the profile\'s calibration …';
  static const String cameraPoseNotMeasuredText = 'Not measured: the profile uses the placeholder pose.';
  static const String cameraPoseMeasuredText = 'Measured';
  static String getCameraHeightAboveTableText({required double heightAboveTableM}) {
    return '${heightAboveTableM.toStringAsFixed(3)} m above the table';
  }

  static String getCameraTiltText({required double tiltFromVerticalDeg}) {
    return 'tilted ${tiltFromVerticalDeg.toStringAsFixed(1)}° from straight down';
  }

  static const String projectionMappingNotCalibratedText =
      'Not calibrated: projected content does not line up with the table yet.';
  static const String projectionMappingCalibratedText = 'Calibrated';
  static String getProjectionMappingErrorText({required String mappingText, required double reprojectionErrorPx}) {
    return '$mappingText: markers ${reprojectionErrorPx.toStringAsFixed(2)} projector px off on average.';
  }

  static String getProjectorResolutionText({required int projectorWidthPx, required int projectorHeightPx}) {
    return 'Projector $projectorWidthPx × $projectorHeightPx px';
  }

  static const String projectorCenterFoundText = 'Projector centre found';
  static const String projectionMappingOutdatedText =
      'Measured before the current camera pose, on the old table plane: calibrate it again.';
  static String getCalibrationNotInstalledText({required String missingPackageText}) {
    return 'Not installed: $missingPackageText';
  }

  static const String measureWithCheckerboardHeading = 'Measure with a checkerboard';
  static const String measureWithCheckerboardText =
      'Lay the board flat on the table, completely in view, and keep it still. This measures the camera\'s '
      'height and tilt above the table; its position along the table and its turn about the vertical stay '
      'those of the placeholder pose. Needs the lens calibration.';
  static const String measurePoseAgainButtonLabel = 'Measure again';
  static const String measurePoseButtonLabel = 'Measure pose';
  static const String measureWithDepthHeading = 'Or measure with depth';
  static const String measureWithDepthText =
      'Clear the table: the camera fits the table plane in its depth image, no board needed.';
  static const String useDepthButtonLabel = 'Use depth instead';
  static const String projectorToTableHeading = 'Projector to table';
  static const String projectorToTableText =
      'Clear the table. The projector shows a grid of markers on the profile\'s projector display; keep out '
      'of the light until it ends. Uses the camera pose, so measure that first.';
  static const String calibrateProjectorButtonLabel = 'Calibrate projector';
  static const String projectorCenterHeading = 'Projector centre (optional)';
  static const String projectorCenterText =
      'Hold a flat board above the table and move it slowly through the projected markers, at different '
      'heights. Needed by the projection mask; calibrating the projector again clears it.';
  static const String findProjectorCenterButtonLabel = 'Find projector centre';
  static const String measuringPoseFromBoardText = 'Measuring the pose from the board. Keep it still and in view.';
  static const String measuringPoseFromTablePlaneText =
      'Measuring the pose from the table plane. Keep the table clear.';
  static const String projectingMarkersText =
      'The projector shows the markers. Keep the table clear and out of the light.';
  static const String findingProjectorCenterText =
      'Move the board slowly through the projected markers, at different heights.';
  static const String calibrationStoredText = 'Stored in the profile.';
  static const String calibrationStoppedText = 'Stopped; nothing was stored.';
  static const String calibrationNothingStoredText = 'Nothing was stored. The calibration said:';
  static String getProjectorBlackoutStartingText({required int projectorDisplayId}) {
    return 'Switching the projector (display $projectorDisplayId) to black …';
  }

  static String getProjectorBlackoutErrorText({required String blackoutErrorText}) {
    return 'Could not switch the projector to black: $blackoutErrorText';
  }

  static String getProjectorBlackoutShownText({required int projectorDisplayId}) {
    return 'The projector (display $projectorDisplayId) shows black during this step, so its light does '
        'not disturb the camera image.';
  }

  static String getProjectorBlackoutNotShownText({required String reasonText}) {
    return 'The projector is not switched to black: $reasonText';
  }

  // Projectors
  /// Shown for a detail the display does not report, so every card keeps all rows.
  static const String unknownDisplayDetailText = '–';
  static String getDisplayListErrorText({required String? displaysErrorText}) {
    return 'Could not list the displays: $displaysErrorText';
  }

  static const String noDisplayFoundText = 'No display found. Is the projector connected and switched on?';
  static String getRefreshRateText({required int refreshRateHz}) {
    return '$refreshRateHz Hz';
  }

  static const String displayIdLabel = 'Display id';
  static const String resolutionLabel = 'Resolution';
  static String getDisplayResolutionText({required int widthPx, required int heightPx}) {
    return '$widthPx × $heightPx px';
  }

  static const String refreshRateLabel = 'Refresh rate';
  static const String positionLabel = 'Position';
  static String getDisplayPositionText({required int positionXPx, required int positionYPx}) {
    return '$positionXPx, $positionYPx px';
  }

  static const String connectorLabel = 'Connector';
  static const String serialLabel = 'Serial';
  static const String projectorIconSemanticLabel = 'Projector';
  static const String desktopScaleLabel = 'Desktop scale';
  static const String noDesktopScaleText = 'None';
  static String getAppsDrawSizeText({required int sdlWidthPx, required int sdlHeightPx}) {
    return 'Apps draw $sdlWidthPx × $sdlHeightPx px';
  }

  static String getDesktopScaleWarningText({
    required String displayTitleText,
    required int sdlWidthPx,
    required int sdlHeightPx,
    required int widthPx,
    required int heightPx,
  }) {
    return '$displayTitleText: the desktop scales this display, so apps draw at '
        '$sdlWidthPx × $sdlHeightPx px and the image is resampled to its real '
        '$widthPx × $heightPx px. A projector should show every pixel as drawn, '
        'or projected markers and fine content get blurred. Set this display\'s scale to 100 % in the desktop\'s '
        'display settings, then press Refresh. If the warning stays, the desktop scales all displays alike (e.g. GNOME '
        'for older X11 apps): set the other displays to 100 % too.';
  }

  static const String projectorInSentenceText = 'the projector';
  static const String projectorAtSentenceStartText = 'The projector';
  static String getNothingOnStoredDisplayText({required int? storedDisplayId}) {
    return 'Nothing is connected as display $storedDisplayId now.';
  }

  static String getStoredDisplayNowText({required int? storedDisplayId, required String storedDisplayTitleText}) {
    return 'Display $storedDisplayId is $storedDisplayTitleText now.';
  }

  static String getProjectorDisplayMovedText({
    required String projectorNameAtSentenceStart,
    required int? projectorDisplayId,
    required int? storedDisplayId,
    required String storedDisplayText,
  }) {
    return '$projectorNameAtSentenceStart is display $projectorDisplayId now, not the '
        'saved display $storedDisplayId: displays were plugged in or out. $storedDisplayText Starting the profile '
        'finds the projector by itself; save the new number to update the profile.';
  }

  static String getProjectorNotConnectedText({
    required String projectorNameAtSentenceStart,
    required String storedDisplayText,
  }) {
    return '$projectorNameAtSentenceStart is not connected. $storedDisplayText Starting the profile with '
        'an app on the projector fails until the projector is connected or another display is chosen.';
  }

  static String getProjectorAmbiguousText({required String projectorNameInSentence}) {
    return 'Several displays look like $projectorNameInSentence, so starting the profile cannot tell '
        'which one it is. Choose the projector below.';
  }

  static String getProjectorNotIdentifiedText({required int? storedDisplayId, required String storedDisplayText}) {
    return 'The profile saves only the display number ($storedDisplayId), not which projector it is, so '
        'a changed number would go unnoticed. $storedDisplayText Choose the projector once below to store it.';
  }

  static String getDisplaysUnreadableText({required int? storedDisplayId}) {
    return 'The displays could not be read, so the wizard cannot check that display $storedDisplayId is '
        'still the projector.';
  }

  static String getDisplayModeChangedText({
    required String projectorNameAtSentenceStart,
    required String currentDisplayModeText,
    required String storedDisplayModeText,
  }) {
    return '$projectorNameAtSentenceStart runs at $currentDisplayModeText now, but was '
        'chosen at $storedDisplayModeText. The projector calibration may no longer fit: set the '
        'display back in the desktop\'s display settings, or save the new mode and calibrate the projector again.';
  }

  static const String noProjectorChosenText = 'No projector chosen yet: click its display below.';
  static String getSaveProjectorDisplayButtonLabel({required int foundProjectorDisplayId}) {
    return 'Save display $foundProjectorDisplayId as it is now';
  }

  static String getSaveProjectorErrorText({required String saveErrorText}) {
    return 'Could not save the projector: $saveErrorText';
  }

  // Sensor nodes and node settings
  static String getSensorNodeListErrorText({required String listErrorText}) {
    return 'Cannot list the sensor nodes: $listErrorText';
  }

  static const String noSensorNodeInProfileText = 'The profile starts no sensor node. Add one with "Add sensor node".';
  static const String noSensorNodeInstalledText =
      'No sensor processing node is installed. Add their repos to config/nodes.list and run '
      './scripts/local_build.sh.';
  static const String addSensorNodeButtonLabel = 'Add sensor node';
  static const String stopDebuggingTooltip = 'Stop the cameras and the sensor nodes.';
  static const String stopDebuggingButtonLabel = 'Stop debugging';
  static const String debugNodeTooltip =
      'Start the cameras with their enabled nodes, as the profile does but without the projector app and '
      'with debug on (each node opens its preview window on the PAR machine), and show what the node in front '
      'publishes on the camera its tab shows.';
  static const String debugNodeButtonLabel = 'Debug node';
  static String getRequiredSensorNodesText({required Iterable<String> requiredSensorNodes}) {
    return 'Needs ${requiredSensorNodes.join(', ')}, which starts along with it on the '
        'same camera.';
  }

  static const String disableSensorNodeTooltip = 'The profile no longer starts this node, on any camera.';
  static String getAppSensorNodesErrorText({required String errorText}) {
    return 'The sensor nodes of an app cannot be shown: $errorText';
  }

  static String getSensorNodeNeededByText({required Iterable<String> needingNodeNames}) {
    return 'Needed by ${needingNodeNames.join(', ')}: disable that first.';
  }

  static const String settingsAndDebugViewHeading = 'Settings and debug view for';
  static String getRunNodeOnCameraTooltip({required String cameraName}) {
    return 'Run this node on $cameraName, in /cameras/$cameraName.';
  }

  static String getSensorNodeNeededOnCameraText({
    required Iterable<String> needingNodeNames,
    required String cameraName,
  }) {
    return 'Needed by ${needingNodeNames.join(', ')} on $cameraName: remove that first.';
  }

  static const String runsOnLabel = 'Runs on';
  static String getDebugStartErrorText({required String runErrorText}) {
    return 'Could not start debugging: $runErrorText';
  }

  static String getDebuggingOnCameraText({required String cameraName}) {
    return 'Debugging on $cameraName';
  }

  static const String startingAgainText = 'Starting again …';
  static String getSensorNodeRunStateErrorText({required String runStateErrorText}) {
    return 'Cannot read the state of the nodes: $runStateErrorText';
  }

  static const String startingNodesText = 'Starting the nodes …';
  static const String runEndedText = 'The run ended. Its last output:';
  static const String startAgainButtonLabel = 'Start again';
  static const String sensorNodeRunningText = 'running';
  static const String sensorNodeStartingText = 'starting …';
  static const String publishesNothingYetText = 'Publishes nothing yet.';
  static const String noMessageYetText = 'No message yet.';
  static String getMessageAgeText({required double receivedAgeS}) {
    return '${receivedAgeS.toStringAsFixed(1)} s ago';
  }

  static String getNodeSettingsTitle({required String fullNodeName}) {
    return 'Settings of $fullNodeName';
  }

  static const String readNodeAgainButtonLabel = 'Read again';
  static const String readingNodeSettingsText = 'Reading the settings: the node starts once for a moment …';
  static const String readingAppSettingsText =
      'Reading the settings: the app starts once for a moment and may show its window meanwhile …';
  static const String nodeWithoutSettingsText = 'The node reports no settings.';
  static const String nodeSettingsSavedRightAwayText =
      'Changes are saved in the profile right away; the node reads them when it starts next.';
  static String getSettingInputErrorText({required String expectedInputText}) {
    return 'Enter $expectedInputText.';
  }

  static String getSettingAllowedValuesText({required String additionalConstraints}) {
    return 'Allowed: $additionalConstraints';
  }

  static String getResetSettingTooltip({required String defaultValueText}) {
    return 'Reset to default ($defaultValueText)';
  }

  static const String expectedWholeNumberText = 'a whole number';
  static const String expectedNumberText = 'a number, e.g. 2.5';
  static const String expectedBoolText = 'true or false';
  static const String expectedWholeNumbersText = 'whole numbers separated by commas';
  static const String expectedNumbersText = 'numbers separated by commas';
  static const String expectedBoolsText = 'true or false, separated by commas';
  static const String expectedValidValueText = 'a valid value';
  static String getSettingRangeWithStepText({required String rangeText, required String stepText}) {
    return '$rangeText, step $stepText';
  }

  static const String settingNotSetText = 'not set';

  // Apps
  static String getAppListErrorText({required String appListErrorText}) {
    return 'Cannot list the apps: $appListErrorText';
  }

  static const String noAppInProfileText =
      'The profile offers no app. Add one with "Add app"; the Run menu then offers it.';
  static const String noAppInstalledText =
      'No app is installed. Add their repos to config/nodes.list and run ./scripts/local_build.sh.';
  static const String addAppButtonLabel = 'Add app';
  static const String appNotInstalledText = 'Not installed (any more): disable it, or install it again.';
  static const String disableAppOfferTooltip = 'The profile no longer offers this app in the Run menu.';
  static const String disableAppStartTooltip = 'The profile no longer starts this app.';
  static String getAppEntryErrorText({required String entryErrorText}) {
    return 'Its entry cannot be used: $entryErrorText';
  }

  static String getAppRequiredSensorNodesText({required Iterable<String> requiredSensorNodeNames}) {
    return 'It needs ${requiredSensorNodeNames.join(' and ')} on the camera it reads; they start with it, and '
        'their settings are under Sensor nodes.';
  }

  static const String appWithoutSettingsText = 'This app declares no settings (settings_node_names in its entry).';
  static const String appCamerasHeading = 'Cameras';
  static String getAppSingleCameraText({required String cameraName}) {
    return 'The app reads the camera $cameraName.';
  }

  static const String appInputCameraChoiceText = 'Choose the camera each input of the app reads.';
  static const String chooseCameraHint = 'Choose a camera';
  static const String appInputWithoutCameraText =
      'An input without a camera stops the profile from starting this app on the projector.';
}
