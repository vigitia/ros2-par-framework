
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
