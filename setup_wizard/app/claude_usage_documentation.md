
## 2026-11-06 — Setup wizard: page files for the new-profile wizard and the profile hub

**What:** The app's screens moved to `lib/screens/`. New: the new-profile wizard (`new_profile_wizard_screen.dart`,
a horizontal `Stepper` with `NewProfileDraft`) with placeholder steps for hardware, camera image and intrinsics, and
the hub of an existing profile (`profile_hub_screen.dart`, a `NavigationRail`) with placeholder areas Overview,
Store and Running. The start screen opens them. The backend's profile code moved to `profiles_api.py` (an
`APIRouter`); the client got generic `getJson` and `sendJson`.

**Why:** Each page can now be built on its own, also by parallel agents, without two of them editing the same file.

**Decisions and rejected alternatives:**
- Fixed interfaces between shell and pages: a step gets the backend client, the `NewProfileDraft` and a callback
  that tells the wizard whether Next is allowed, so validation stays in the step's file; a hub area gets the client
  and the profile name. Rejected: the shell deciding from the draft when a step is complete (every step change
  would edit the shell).
- One backend module per area with its own `APIRouter`, included by one line in `setup_wizard_backend.py`; the
  app's calls per area as a Dart `extension` on `SetupWizardBackendClient` in the area's own file. Rejected: all
  endpoints in one backend file and all calls in the client (parallel edits would collide).
- Overview, Store and Running as hub areas; the overview covers the card's "Setup" and "Calibrate" together, as in
  the overview sketch.
- No files for the steps after intrinsics: they are not specified yet. Store and Running only describe what they
  will show, because what an app is (catalog format) is still open.
- Finishing the wizard saves nothing yet and returns to the start screen; the hub always uses a navigation rail
  (both marked as simplifications).

## 2026-11-10 — Setup wizard: cameras by name (multi-camera step 6c)

**What changed:**
- Cameras are named by role when added. The add dialog (`add_camera_dialog.dart`) ends with the camera's name,
  suggested from its type (`brio`, then `brio_2`, `suggestCameraName`) and checked like the backend
  (`cameraNamePattern`, unique in the profile). A type with serial numbers can also be added without one while it is
  not in the profile yet (the driver opens the first unit it finds). The Hardware step of a new profile uses the same
  dialog for every camera; the profile is created with all its cameras in one request.
- `PreviewCameraChoice` (`camera_preview_api.dart`) names what a preview starts: a saved profile's camera by name, or
  a unit no profile names yet by type and serial (the new-profile pages before the profile exists). The preview,
  settings and lens calibration views take it instead of camera name, profile and serial; it also gives the camera's
  image topic `/cameras/<name>/image_raw` for the focus frame and the sensor run's image.
- Cameras area: one tab per camera, titled with its name, in the profile's order; every camera can be shown and
  calibrated on its own. Gone: the main-camera switch on tab change, the capture camera's tab and the Overview's
  "only starts together with the main camera" steps (`blockedReasonText`). The first camera is marked as the main
  camera, which the sensor nodes use.
- `CameraType` replaces `SupportedCamera` (display name, description, serial source from the type's entry);
  `CameraCalibrationSummary`, `CameraGeometry` and `CameraSectionRequest` identify cameras by `cameraName`.

**Why:** step 6 of the multi-camera plan: the backend now addresses every camera by its name in
`par_launch.cameras`, and several cameras run together, so there is no main camera to switch to before a camera can
be shown.

**Alternatives considered:** one `cameraName` string meaning a profile camera with a profile and a type without one
(ambiguous, the bug the old code had); two optional fields on every view (both could be filled by mistake); keeping
`<type>_<n>` names generated in the Hardware step (the plan decided names are chosen when added; the type itself is
the natural first name).

## 2026-11-10 — Setup wizard: the Overview always shows the drawing

**What changed:** the Overview shows the setup drawing also before anything is measured: the bare table around the
world origin, at the drawing's minimum width (`_SideViewLayout.create` no longer returns null; `hasSetupDrawing` is
gone).

**Why:** the steps below the drawing are titled "Not in the drawing yet", which reads as a mistake when there is no
drawing at all; the empty table shows where the devices will appear.

**Alternatives considered:** keeping the drawing hidden and renaming the heading (a new profile would then never show
what the Overview is for).

## 2026-11-10 — Setup wizard: own hero tags for the floating buttons

**What changed:** the Run button (`profileRunButtonHeroTag`) and the Sensor nodes' debug button
(`sensorNodesDebugButtonHeroTag`) each get their own `heroTag`.

**Why:** a `FloatingActionButton` takes part in Flutter's hero animation (a widget flying from one page to the next)
with one default tag shared by all of them; with both buttons on screen during a page change, Flutter's debug check
reported two heroes with the same tag.

**Alternatives considered:** `heroTag: null` (switches the animation off for that button; a named tag keeps it and
says which button it is).

## 2026-11-10: Sensor nodes area per camera (multi-camera step 8b)

**What changed:** the Sensor nodes area keeps on which cameras each node runs (`SensorNodeSummary.cameraNames`,
`saveSensorNodeSelection` with `cameraNamesByPackage`). An added node runs on the main camera. With several cameras, a
node's tab shows a chip per camera ("Runs on") and a switch for the camera whose settings and debug view it shows; the
settings editor is that camera's (`/cameras/<camera>/<package>_node`), and the debug view shows that camera's image and
the node's outputs there. A chip stays on while another node needs this one on that camera; Disable removes the node
from every camera.

**Why:** step 8 runs sensor nodes per camera; the plan replaced the on/off switch with a checkbox per camera.

**Alternatives considered:** a settings editor per camera stacked in the tab (twice as long with two cameras, and the
debug view would still need one camera); adding a node on every camera (with several cameras, a node usually belongs to
one, e.g. markers on the RGB camera). With one camera, chips and switch are hidden, so the area looks as before.

## 2026-11-11: One wizard page per camera for image settings and focus

**What changed:** the new-profile wizard's two pages per camera, "Focus" (only the settings named `*focus*`, with the
focus help) and "Image settings" (all other settings), are one page "Camera setup & focus" with every setting and the
focus help. `CameraImagePageTopic`, `isFocusSettingName` and `isNotFocusSettingName` are gone. The instructions no
longer assume a lens ring: the focus may be a driver setting, a ring on the lens or a control on the device, and a
fixed-focus camera needs no focusing.

**Why:** focus and image settings depend on each other. An image that is too dark or too bright cannot be focused, so
exposure, gain or brightness often has to be set first. With Focus as the first page, those settings were only
reachable afterwards.

**Alternatives considered:** swapping the two pages (image settings first) still separates them, and a focus change
can call for another brightness change; showing the focus settings on both pages would list them twice. The Cameras
area already showed both on one screen ("Image & settings"), so the wizard now matches it.

## 2026-11-11: Projector choice shows the real resolution and warns about desktop scaling

**What changed:** `ConnectedDisplay` carries the size apps draw at (`sdlWidthPx`, `sdlHeightPx`) next to the real
mode (`widthPx`, `heightPx`); `isScaledByDesktop()` compares them. Each display card has a row "Desktop scale" ("None",
or the size apps draw at in the error colour, wrapped over several lines so it is never cut off), and every scaled display gets a full warning below the cards with the
fix (scale 100 % in the display settings, then Refresh).

**Why:** the backend now reports the real mode; when the desktop scales a projector, the projected image is resampled
and fine content such as markers blurs, which is easy to miss.

**Alternatives considered:** only a tooltip on the card (not readable without hovering, and the cards are one line per
row); a warning only for the chosen display (the scaling should be fixed before choosing, so it shows for all).

## 2026-11-11: Apps area chooses the camera of each app input

**What changed:** an app tab shows a "Cameras" section for an app whose entry names inputs. With several cameras,
each input gets a dropdown of the profile's cameras (`setProfileAppInputs`, stored in `par_launch.app_inputs`); an
unbound input, or one bound to a camera the profile no longer has, is marked, since the profile cannot start the app
on the projector until it is bound. With one camera, the section only says which camera the app reads.
`InstalledApp.inputNames` and `ProfileSummary.cameraNameByInputByApp` carry the data.

**Why:** step 9 of the multi-camera plan: apps bind their inputs to cameras, chosen in the Apps area.

**Alternatives considered:** a dropdown with one camera too (nothing to choose; launch binds the only camera itself);
binding all inputs of an app at once to the main camera when it is added (with several cameras the main camera is
often the wrong one, e.g. for a capture input).

## 2026-11-11: Review fixes: polling, camera settings saved at once, dead code, profile endpoint

**What changed:**
- Every repeated request now runs as an async loop that sends the next request only after the previous answer and
  ends once its view is gone: the profile's Run button, the projector blackout and the Sensor nodes' run state (which
  used `Timer.periodic`) follow the loop pattern the camera preview and calibration views already used.
- Sensor nodes: the run state loop belongs to one start (`_runStartCount`); it ends on a new start or Stop, and an
  answer arriving after either is dropped. A failed request shows a lasting error in the debug view until the next
  answer.
- Camera settings of a saved profile are written into the profile right after the driver accepted a change (the
  existing save-to-profile call, one save at a time; a change during a save triggers one more). The "Save to profile"
  button is gone; a failed save shows the reason, and settings still unsaved are named with a "Save now" button.
  Without a saved profile (new-profile wizard) nothing changes.
- `fetchProfileSummary` asks `GET /api/profiles/{name}` for the one profile instead of loading the whole list; 404
  and an unreadable profile keep their texts.
- The extrinsics state shows why a stored projection mapping file cannot be used (`mappingFileErrorText`), like the
  camera pose.
- Removed what nothing used: `isFocusAssistShown`, `isSettingsListShown`, `isSettingShown`, `noShownSettingsText`
  and the fields `ProfileSummary.sensorNodeNames`, `CameraIntrinsicsState.calibrationFilePath`,
  `ProjectorGeometry.mappingCameraName`, `CameraType.requiredPackageNames`.
- The generic 409 text no longer blames the camera. Renames: `CameraSetupStep`, `cameraSetupStepIndex`,
  `_getTextOrUnknown`.

**Why:** a periodic timer starts a new request while the previous one may still wait for its answer, so answers
overlap and an old one can overwrite a newer state; silent errors left a frozen view. Camera settings were the only
settings that needed a manual save, which is easy to forget. Loading every profile to show one is wasted work.

**Alternatives considered:** a shared polling helper (the loops differ in what ends them: a start count, a run id, a
running calibration; a helper would only move a three-line `while` loop); cancelling the periodic timer while a request
is on its way (still two mechanisms side by side); saving camera settings only when leaving the page (a crash or a
closed window would lose them). SensorNodesScreen keeps loading its own list without the `ProfileSummaryLoading`
mixin: it does not use the profile summary, its sensor node list already carries the profile's cameras.

## 2026-11-12: Lens calibration page without a camera start for factory-calibrated cameras

**What changed:** the lens calibration section of `CameraSectionView` (Cameras area and new-profile Intrinsics page)
first reads the profile summary. For a camera whose intrinsics state is `factory` it shows only a note that nothing
needs to be done and does not start the camera; otherwise, or when the profile cannot be read, it shows
`IntrinsicsCalibrationView` as before. The section is keyed by camera name: it reads the state once, and the
wizard's next Intrinsics page (another camera) would otherwise reuse it with the previous camera's state.

**Why:** a camera that brings its own calibration offers nothing to do on this page, so starting it and showing its
preview only costs time and suggests there is something to do.

**Alternatives considered:** passing the intrinsics state in from both callers (the new-profile wizard holds no
profile summary, so it would need the same request in a second place); deciding inside `IntrinsicsCalibrationView`
(it is built around a running camera; the choice whether to start one belongs above it). Simplification: the
projector is still blacked out on this page for such a camera, because the blackout is shared with the camera pose
section so it does not flicker between the two.

## 2026-11-12: Clearer refusal of an existing profile name; hint "Lab"

**What changed:** the new-profile name field names the existing profile when it refuses a name, says it may come
from a setup that was not finished, and points to the Profiles menu to continue it (Cameras area) or delete it; the
error text may wrap. The field's hint is "Lab".

**Why:** the wizard saves the profile before its calibration pages, which need it, so a setup left before Finish
leaves a real profile behind. The old text ("exists already") gave no hint of that, so the name looked blocked by
something that did not exist.

**Alternatives considered (decided by Vitus):** marking a profile unfinished until Finish and letting a new setup of
the same name replace it (a marker in the profile file and more code for a rare case); moving the half-made profile
to `.deleted/` when the wizard is left without Finish (a crash or closed window would still leave it behind).

## 2026-11-12: Camera settings never show another camera's settings

**What changed:** `CameraSettingsView` takes the `PreviewCameraChoice` instead of a display name, and
`CameraSettingsReport` carries the backend's `camera_name`. An answer whose camera name or profile differs from the
view's camera is dropped and asked again after `cameraSettingsRetryInterval`, like an answer from a camera that is
still starting.

**Why:** the camera page starts its camera and loads the settings independently. The backend answers a settings
request for the camera running at that moment, and handles requests in parallel, so right after switching pages the
settings request could be answered before the new camera's start had stopped the old one. The page then listed the
previous camera's settings under the new camera's name (seen: a Kinect's `tf_prefix` on a Blackfly page), and a
change would have gone to whichever camera ran.

**Alternatives considered:** loading the settings only after the preview's start returned (needs the start's
completion passed from `CameraPreviewView` to its siblings; the identity check also catches a late answer from
any other cause); refusing such requests in the backend while a start is pending (the backend cannot know a start
is coming when the settings request arrives first). The profile is compared as well, because a unit preview and a
profile camera may share a name (`kinect`) but not their settings.

## 2026-11-12: Resizing the wizard keeps entered values and the running camera

**What changed:** the new-profile wizard gives each page a `GlobalKey` (`_pageContentKeyById`, one per topic and
camera). `ExtrinsicsCalibrationView` keeps its camera preview under a `GlobalKey` too, replaced only after a run and
for another camera (it replaces the `_previewStartCount` key).

**Why:** the Stepper switches between horizontal and vertical with the window width and then places the page content
elsewhere in the widget tree; without a GlobalKey Flutter builds the page afresh, so entered values (e.g. the
checkerboard) were lost and the camera restarted. The pose and projector calibration pages also move the preview
between a stacked and a side-by-side layout, which restarted the camera there. A scratch widget test confirmed both
ways: without the key the page was built three times over two switches, with it once and the typed value stayed.

**Alternatives considered:** keeping the entered values in `NewProfileDraft` (the wizard's own state) instead of in the
views (only covers the wizard, not the camera restart, and every field would need its own copy); one fixed Stepper
type (avoids the switch, but a narrow window would get a cramped horizontal bar).

## 2026-11-12: Calibration pages: remembered board, automatic intrinsics save, focus crop, error reasons

**What changed:**
- `RememberedCheckerboard` (in `intrinsics_calibration_view.dart`) holds the last typed inner corners and square size;
  the lens and camera pose views fill their fields from it and update it on every change, so the next camera's page
  starts with the same board.
- The lens calibration is saved as soon as it is computed (once per run, `_isCalibrationResultSaveStarted`); the
  result stays shown for checking until "Close". Save and Discard are gone.
- `FocusAssistView` takes the previewed camera and clears its measurement and centre crop when the camera changes;
  a missing crop (none measured for the running camera yet) clears the shown one instead of keeping it.
- Camera previews and the focus help show the backend's reason for a refused request (e.g. that the camera stopped,
  with its last output) instead of the generic sentence.

**Why:** typing the same board on every page was needed several times per setup; the lens calibration was the only
calibration that needed a manual save, which the camera pose does not; the previous camera's enlarged centre stayed
on screen until the next camera's first frame; and "That is not possible right now" hid why a camera image was
missing.

**Alternatives considered:** storing the board in the profile (survives restarts, but the profile does not exist yet
on the first pages and the board is a property of the printout, not of the setup); keeping Discard after an automatic
save (it could not undo the stored file; calibrating again replaces it); making the generic 409 text more specific
(it cannot know the reason; the backend's text does).

## 2026-11-13 — Overview drawing: projected area always shown

**What changed:** `setup_side_view.dart` draws the projected area as a coloured stretch on the table top
(`_paintProjectionArea`, after the table), labelled below the table top, whether or not the projector centre is
known. The light from the projector still starts at the lens when the centre is known.

**Why:** with a known centre only the faint light was drawn, painted first and then covered by the cameras' fields
of view and the table, so the projected area was not visible.

**Alternatives considered:** a stronger fill for the light (still hidden where several camera views overlap); the
label above the area as before (it collides with the light and the camera views there).

## 2026-11-13 — Overview drawing: area size, hover highlight; factory camera keeps running on its Intrinsics section

**What changed:**
- `setup_side_view.dart`: the projected area's label gives its size (`projected area 1.23 × 0.69 m`, width and height
  each the mean of the image's two opposite edges on the table). Hovering a camera draws its field of view, hovering
  the projector its light, with a stronger fill and outline (`hoveredFrustumFillAlpha`,
  `hoveredFrustumOutlineWidthLogicalPx`).
- `camera_section_view.dart`: the Intrinsics section of a camera with a factory calibration shows the camera's
  preview below its note.

**Why:** Vitus asked for the size and for telling overlapping fields of view apart. The preview keeps such a camera
running while its tab is open, as the other sections do (the backend keeps a running preview of the same camera).

**Alternatives considered:** the size from the bounding box of the corners (larger than the image when it is turned
on the table); dimming everything else on hover (the drawing loses its context).

## 2026-11-13 — Overview drawing: height follows the width; left, front and right views

**What changed:** `setup_side_view.dart`:
- The drawing's height is computed from its width (`_SideViewLayout.create`): the height at which the setup fills the
  width at the same scale both ways, at least `setupSideViewMinimumHeightLogicalPx` and at most
  `setupSideViewMaximumWindowHeightRatio` of the window's height.
- Buttons Left / Front / Right above the drawing (`SetupDrawingViewSide`). The layout takes the table direction drawn
  left to right (`screenRightDirection`): from the front `frontViewRightDirection`; from the projected image's left
  edge the direction back towards the front; from its right edge the direction away from it.

**Why:** with a fixed height the setup, about as tall as wide, filled the height and left most of the width empty.
Vitus asked for a wider drawing and for side views, e.g. to see the cameras' tilt along the projection's depth.

**Alternatives considered:** a larger fixed height (too tall in a narrow window, still narrow in a wide one); a
free-turning 3D view (much more code, and the 2D views answer where each device is).

## 2026-11-13 — Setup drawing: renamed, positions under the names, view buttons below

**What changed:**
- `setup_side_view.dart` is now `setup_drawing_view.dart`; `SetupSideView` → `SetupDrawingView`, `_SetupSideViewPainter`
  → `_SetupDrawingPainter`, `_SideViewLayout` → `_SetupDrawingLayout`, `_SideViewColors` → `_SetupDrawingColors`, the
  `sideView*` constants → `setupDrawing*` (call site: `profile_overview_screen.dart`).
- Every label has a second line: cameras and the projector their position in world (`x 0.03 · y 0.40 · height 1.43 m`,
  `_createPositionText`), the projected area its size. The projector's and the area's lines are centred; a camera
  label that would run off the right edge goes to the left of its icon. The top and bottom margins grew for the second
  line.
- The Left / Front / Right buttons sit centred below the drawing.

**Why:** Vitus asked for it; the drawing shows the front and the sides, so "side view" was misleading. The positions
make it possible to check a calibration against the real setup with a tape measure.

**Alternatives considered:** the distance between each camera and the projector instead of world coordinates (no
common reference to measure from on the table); placing labels freely around the icon (more code; the left-of-icon
case covers the label running off the edge).

## 2026-11-13 — Setup drawing: only the height below a device's name

**What changed:** the second label line of cameras and the projector shows only the height above the table
(`_createHeightText`, was `_createPositionText` with x and y).

**Why:** Vitus' choice; x and y relate to the projected image's corner, which is hard to read off the drawing, while
the height is what the front and side views show.
