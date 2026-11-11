
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
