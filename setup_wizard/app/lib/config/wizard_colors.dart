// Written by Claude Code
//
// The setup wizard's own colours, so they are changed in one place. Most colours come from the theme's colour scheme
// (Theme.of(context).colorScheme), which is derived from themeSeedColor; only colours the scheme has no role for are
// listed here.

import 'package:flutter/material.dart';

class WizardColors {
  /// The colour the dark theme's whole colour scheme is derived from (ColorScheme.fromSeed).
  static const Color themeSeedColor = Colors.green;

  /// Something done or running: a stored calibration, a covered image region, a running sensor node (Material green
  /// 400, readable on the dark theme's surfaces).
  static const Color doneColor = Color(0xFF66BB6A);

  /// The drawn projector's light and lens glass: a pale, only slightly warm white, so the cone reads as a lamp's light
  /// rather than as a yellow shape. Colder still: e.g. 0xFFF2F6FF, a white with a hint of blue.
  static const Color projectorLightColor = Color(0xFFFFF5D1);

  /// The drawn projector's body (Material grey 600).
  static const Color projectorBodyColor = Color(0xFF757575);

  /// The drawn projector's lens barrel and air vents, darker than its body (Material grey 800).
  static const Color projectorLensAndVentsColor = Color(0xFF424242);
}
