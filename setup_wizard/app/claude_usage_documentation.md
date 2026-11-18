
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

## 2026-11-13 — Setup wizard: feature folders and all user texts in `WizardStrings`

**What changed:** `lib/` follows the package structure of Flutter's architecture guide
(https://docs.flutter.dev/app-architecture/case-study): `ui/<feature>/` (`profiles`, `new_profile`, `cameras`,
`calibration`, `projectors`, `sensor_nodes`, `apps`) for screens and the widgets only they use, `ui/core/ui/` for
widgets shared by several features (`profile_run_view`, `addable_tabs_view`, `setting_row_view`,
`node_settings_editor_view`, …), `data/services/` for the backend client and every `*_api.dart`. `lib/screens/` is gone.
Every text shown to the user is in `lib/config/wizard_strings.dart`: `abstract final class WizardStrings` with
`static const String` for fixed texts and a `get…Text`/`get…Label` function with named parameters for each text with
a value in it (number formatting such as `toStringAsFixed` moves along with the text). Texts used in several places
(`Cancel`, `Try again`, the checkerboard fields) are one constant. Not moved: texts the backend writes (they arrive as
data), console logs (`debugPrint`), exception messages for developers (`FormatException`, `toString`), JSON keys, API
paths, widget keys, and pure format strings without words (e.g. `'$titleText: $cameraName'`).

**Why:** Vitus' request: texts in one place to review and change, and a folder per feature instead of 39 flat files.

**Decisions and rejected alternatives:**
- Dart constants class instead of Flutter's localisation workflow (ARB files in `lib/l10n/` plus `gen-l10n` and
  `AppLocalizations.of(context)`, https://docs.flutter.dev/ui/accessibility-and-internationalization/internationalization):
  that one is Flutter's documented way, but needs two more dependencies (`flutter_localizations`, `intl`) and a
  `BuildContext` for every text, which the backend client building its error sentences does not have. It pays off only
  once the wizard is translated; moving the class's entries into an ARB file then is mechanical.
- The strings file lives in `lib/config/`, not `lib/ui/core/`: `data/services/` uses it too (user-facing error
  sentences), and data should not import from ui.
- Folders sorted by feature (Flutter's guide) rather than by type (`screens/`, `widgets/`, `services/`): a feature's
  screen and its widgets stay together. The guide's `view_models/` and `widgets/` subfolders per feature are left out,
  the wizard has no view models, so a second level would hold a single folder. The `*_api.dart` files keep their data
  classes; splitting them into `domain/models/` would be a separate refactor.
- Names follow Effective Dart (`lowerCamelCase` constants, no `k` prefix); functions returning a text start with `get`.
- The literals were replaced by a script that parses Dart strings (adjacent literals, nested interpolations) and a
  hand-written name table, so no text was retyped. Long call sites were wrapped with `dart format`'s result for only
  those statements, because formatting whole files would have rewrapped untouched code.

## 2026-11-13 — Setup wizard: Store area removed for now

**What changed:** the profile hub has five areas (Overview, Projectors, Cameras, Sensor nodes, Apps); the Store tab,
its placeholder screen `app_store_screen.dart` and its texts are gone. The hint for "no app installed" points only to
`config/nodes.list` and `./scripts/local_build.sh`, like the sensor nodes' hint.

**Why:** Vitus' request: the Store was only a placeholder (its catalog is still undecided), and a tab that does
nothing distracts.

**Decisions and rejected alternatives:**
- Deleted the screen instead of only hiding the tab: an unused file would go stale, and git keeps it for when the
  Store is built.
- Store was the last area, so the other area indices stay unchanged.

## 2026-11-13 — Setup wizard: sensor nodes the projector app needs

**What changed:** The Sensor nodes area shows the nodes the profile's projector app needs (from the backend's
`camera_names_needed_by_projector_app`) together with the profile's own selection: as tabs, on their cameras, marked
"Needed by <app>" with Disable and the camera chip locked, as for a node another node needs. The selection the area
saves holds only the user's own cameras; the camera chips build their request from it. A broken app binding (e.g. an
unbound input with several cameras) shows as an error line above the tabs. The Apps area's tab says which sensor nodes
the app starts on the camera it reads and that their settings are under Sensor nodes.

**Why:** Object teaching needs Hand landmarks and Gesture detector, which the framework starts with it, but the wizard
did not show them, so their settings could not be found or tuned. They are derived from the app, never saved, so
removing the app or binding it to another camera moves them along (decided with Vitus, 2026-11-13).

**Decisions and rejected alternatives:**
- The app is one more "needing node" in `_getNodesNeedingOnCamera`, so the existing locks and texts apply; a separate
  lock and text for apps would duplicate that logic.
- The note in the app's tab instead of a message shown once when the app is chosen: the projector app is chosen in the
  Run menu, apart from the app's tab, and a permanent line is still there when the user looks for the nodes later.
- Not sending the app's cameras when saving, instead of filtering them in the backend: the backend cannot tell an app
  camera from one the user also chose.

## 2026-11-13 — Setup wizard: sensor nodes of every offered app

**What changed:** The Sensor nodes area shows the nodes every app of the profile needs (offered under Apps, or on the
projector), from the backend's `needing_app_names_by_camera`; "Needed by" names the apps per camera, and each app whose
binding is broken gets its own error line. The note in the app's tab no longer says "On the projector".

**Why:** Adding an app under Apps did not make its nodes appear, because only the projector app (chosen later in the
Run menu) counted. Vitus chose to show the nodes of every offered app, so they can be tuned right after adding it.

**Decisions and rejected alternatives:**
- App names per camera instead of one list of cameras: two apps may need the same node on the same camera, and the
  tooltip names both.

## 2026-11-17 — Setup wizard: installing apps, cameras and sensor nodes from their areas

**What changed:**
- New `lib/ui/install/offer_catalog_view.dart` (`OfferCatalogView`): the installed and available offers of one kind
  from the backend's catalog (`install_api.py`), grouped "Installed" / "Available", one row each with name,
  description and, right-aligned, the package.xml version ("0.1.0 installed", "0.2.0 available", or both when they
  differ). Clicking an available offer shows what installing adds (repositories and ROS packages, "for …"), then
  Install follows the build: progress and last output lines; the sudo command with Copy and Continue (the same start
  again); failure with Try again; "restarts …" while the backend is gone (120 s, then a hint to the log); Installed
  and Done. "Check for new versions" downloads the catalog again (also by itself on a first start with nothing
  downloaded); "Add repository" adds the user's own repository by git URL and optional branch. Repositories that
  cannot be read, or user repositories offering nothing, are listed at the end, the user's own with Remove.
- New `lib/ui/install/offer_picker_dialog.dart`: the view as a dialog; an installed offer, or one installed in it,
  closes it with that offer.
- "Add app", "Add sensor node" and "Add camera" open that dialog instead of a menu of installed ones. Installed
  offers the profile has (or with a broken entry, or sensor nodes without a camera in the profile) show why and
  cannot be chosen. After the choice the area reloads its list (an install restarts the backend) and adds it as
  before; for a camera the chosen type goes to `AddCameraDialog` (`cameraTypeToAdd`), which continues with the unit
  and the name.
- Without a profile, Cameras, Sensor nodes and Apps are enabled and show `OfferCatalogView` as their page, without
  choosing; only Projectors and the Run button stay disabled. The no-profile hint says to install there first.
- `install_api.dart`: catalog, refresh, plan, install start/state, user repositories (add/remove).
- The "No app / sensor node installed" hints point to the Add buttons.

**Why:** Vitus wants to see and install what is available where it is used, with versions, and to add own
repositories; a separate Install area was rejected by him.

**Decisions and rejected alternatives (Vitus chose in a dialog):**
- *Installing through the Add buttons* instead of a fixed "All apps" tab or one combined list: the profile tabs stay
  as they are, and installing is one step before adding.
- *Areas usable without a profile, list only*, instead of creating a profile first: a fresh installation needs its
  cameras before the new-profile wizard can choose one.
- *User repositories in each list, stored in the gitignored `config/user_catalog.list`* instead of one entry in the
  profile menu: the user adds them where they are looked for; what a repository offers appears in every matching
  area.
- One offer per install (the row clicked) instead of tick boxes for several: the add flows add one thing at a time,
  and what an offer needs comes along anyway.
- The sudo command is shown to copy, not run from the app: running it would need a password prompt in the app
  (planned for later with `pkexec`).
- A camera shows its driver's version (first `required_packages`, else its launch file's package): for the
  framework's own camera types the launch package is `par_framework_core`, the same for every camera.
- Released packages (e.g. `v4l2_camera` from apt) show no available version: the catalog does not know them, and
  asking apt would mean mapping rosdep keys to apt names. Most framework packages are still `0.0.0`, so versions only
  tell something once repositories bump them.

## 2026-11-17 — Setup wizard: profile menu spacing, app icon

**What changed:**
- Profile menu (`profile_selector_view.dart`): the menu sits 8 px below the button and off the window's right edge
  (`alignmentOffset`), has 8 px above and below its entries (`MenuStyle.padding`) and 16 px at the sides of each
  entry (one `_buildMenuEntry` helper); the divider has room around it. The hub's app bar keeps the menu button
  8 px off the window's edge (`actionsPadding`).
- App icon: `assets/app_icon.svg`, a projector shining light onto a table. `scripts/start_setup_wizard.sh` writes
  `~/.local/share/applications/com.github.vigitia.par_setup_wizard.desktop` (`$XDG_DATA_HOME`) pointing to it, when
  missing or out of date (e.g. after the repository moved), with `NoDisplay=true`.

**Why:** Vitus' request: the menu touched the window's edge, and the app had no icon.

**Decisions and rejected alternatives:**
- *The icon through a .desktop file named after the app ID* instead of `gtk_window_set_icon` in the runner: Wayland
  desktops (GNOME) ignore a window's own icon and look it up by the app ID; the .desktop file works on X11 too.
- *`NoDisplay=true`* instead of a launcher in the application menu: the entry would start the app without its
  backend; starting stays with the start script.
- The icon is an SVG referenced by its path instead of copied into the icon theme folders: one file, no sizes to
  render.

**Found on the way:** the release build reused an old trimmed icon font (`build/flutter_assets`), so icons added
since were blank, among them "Add repository"'s. A build with `--no-tree-shake-icons` writes the full font; `flutter
clean` once resets the stale build cache. A fresh clone is not affected.

## 2026-11-17 — Setup wizard: new profile without the step-by-step wizard

**What changed:**
- "New profile" in the profile menu opens a name dialog (`ui/profiles/profile_name_dialog.dart`, which the copy uses
  too; it replaces `copy_profile_dialog.dart` and holds the friendly-to-internal name helpers). The profile is
  created without cameras and projector, selected, and the hub shows its Overview.
- The Overview's missing calibrations became one "To do" list (`_MissingSetupStep`): add a camera, choose the
  projector, per camera lens calibration (with the hint to set focus and exposure first) and camera pose, the
  projector calibration on the main camera, the apps, the optional projector position. Each row has a button into
  its area; the projector calibration without a chosen projector says to choose it first and has no button.
- Cameras area: each section button shows done (check) or still to do (empty circle) where the step is tracked
  (lens: calibrated or factory; pose: measured; projector: a mapping exists, needed only on the main camera). A
  camera just added opens on Image & settings. Opened from the To do list's "Add camera", the area starts with the
  Add camera dialog. Remove works for the last camera too. The projector section without a projector says to choose
  it first; the lens section shows the focus hint while the lens is uncalibrated.
- Run is disabled with a tooltip while the profile has no camera.
- Removed: `ui/new_profile/` (stepper, hardware, camera image, projector, intrinsics and extrinsics steps), its
  strings, `createProfile`'s camera and projector arguments, `discardNewProfileSettings`.
- Renamed: `_MissingCalibrationStep` → `_MissingSetupStep`, `_buildSetupRows` → `_buildSetupDrawingAndToDoRows`,
  `choice` → `addCameraChoice` (cameras_screen.dart).

**Why:** Vitus' request: a new profile should land on its Overview at once and say what to do, instead of leading
through fixed steps.

**Decisions and rejected alternatives:**
- *Focus as a hint on the lens calibration to-do* (Vitus) instead of an own to-do ticked when settings are saved,
  which would need a stored "focus done" flag per camera.
- *The app choice is a to-do, sensor nodes are not* (Vitus).
- *Done/to-do marks on the section buttons* (Vitus) instead of also opening the next missing section by itself after
  a calibration is saved. A just-added camera opens Image & settings rather than its first uncalibrated section,
  since focus and exposure come before the lens calibration.
- *One To do list* instead of the former two headings ("Not in the drawing yet", "Calibration"): adding a camera and
  choosing the projector or apps are not calibrations, and one ordered list says what comes next.
- *Marks refresh when another section is chosen* (`Simplification:` none in code; noted here): a calibration saved
  inside a section shows as done once the user switches sections or reopens the area.

## 2026-11-17 — Setup wizard: profile menu keeps a gap to the window's right edge

**What changed:** the profile menu (`profile_selector_view.dart`) is a `PopupMenuButton` instead of a `MenuAnchor`;
each entry is a `PopupMenuItem` whose value is the action, run in `onSelected` after the menu has closed.

**Why:** Vitus' report: the opened menu still touched the window's right edge. `MenuAnchor` moves a menu that would
leave the window to the edge of the window minus `MediaQuery.padding`, read in its overlay, so its `alignmentOffset`
is undone and a `MediaQuery` around the anchor does not reach it; its `reservedPadding` only limits the menu's size.
`PopupMenuButton` keeps every menu 8 px from the window's edges.

**Decisions and rejected alternatives:**
- *Actions as menu values, run in `onSelected`*, instead of `PopupMenuItem.onTap`: `onSelected` runs after the
  menu's route is gone, so the name and delete dialogs it opens are not closed with it.
- Rejected: a negative `alignmentOffset` sized to the menu (the menu's width depends on the profile names);
  mirroring the anchor with right-to-left text direction (the entries would need flipping back).

## 2026-11-17 — Setup wizard: dead code removed

**What changed:** `PreviewCameraChoice` is a profile camera only (one constructor with `profileName` and
`cameraName`; `.unit`, `cameraType`, `serial` and `runningCameraName` are gone, the strings take `cameraName`).
`CameraSettingsView` saves into `previewCamera.profileName` instead of a profile read from the backend's answer,
which removes its "running without a profile" branch and string. `PlannedInstall.findRepository` is removed.

**Why:** Vitus asked to check the wizard for dead code and remove it; nothing starts a preview without a profile
since the step-by-step new-profile wizard is gone, and nothing called `findRepository`.

**Decisions and rejected alternatives:**
- *The settings report's `profileName` stays nullable* and is still compared with the shown camera's: the backend
  answers for whatever camera runs, also none, so a report of another or a stopped camera is still recognised.

## 2026-11-18 — Setup wizard: Run in the Apps area, colour and icon config, projector icon

**What changed:**
- The Apps area has the Run button too (its own `Scaffold`, like the Sensor nodes area's Debug button).
  `ProfileRunView` takes an optional `appToRunDirectly`: then the button reads "Run <app>" and starts the profile with
  that app on the projector without the menu. The Apps area passes the shown tab's app when it uses the projector and
  its entry is valid; on RViz's tab, a broken entry or without tabs, Run opens the menu as on the Overview.
  `onProjectorAppStored` became optional (the Apps area shows no projector-app choice to refresh).
- New `lib/config/wizard_icons.dart` (`WizardIcons`): every icon the wizard shows, named by purpose
  (`runButtonIcon`, `projectorsAreaIcon`, …); all screens use it instead of `Icons.*`.
- New `lib/config/wizard_colors.dart` (`WizardColors`): theme seed, the green "done" colour, the drawn projector's
  body, lens and light colours (`projectorLightColor` moved there from `projector_drawing.dart`). Colours from the
  theme's colour scheme stay where they are.
- Projectors area and the cameras' projector calibration section: `Icons.video_stable` instead of `video_label`.

**Why:** Vitus asked for Run on the Apps page (run the app being looked at), one place for colours and icons, and a
projector icon that reads as a projector.

**Decisions and rejected alternatives:**
- Icons named by purpose, not by glyph: two uses of the same glyph (Copy in two menus, Refresh as retry and as reload)
  can change apart. Same idea as `WizardStrings`.
- The Apps area tracks its tab in front itself (`onShownTabChanged`, the added app, else the first tab, matching what
  `AddableTabsView` shows) and hosts its own button. Rejected: the hub tracking the Apps area's tab to configure its
  single Run button; the area already knows its tab.
- Projector icon: Flutter's Material icons have no projector. `video_stable` chosen by Vitus; rejected: a drawn glyph,
  `highlight`, `co_present`, and an icon package (new dependency).
- Colours as `const Color(0xFF…)` with the Material palette name in the comment, since `Colors.green.shade400` is not
  a compile-time constant.
