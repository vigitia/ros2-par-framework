
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
