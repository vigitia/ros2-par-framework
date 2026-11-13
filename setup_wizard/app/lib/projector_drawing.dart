// Written by Claude Code
//
// The wizard's projector, drawn from a few shapes so it scales and needs no image file: a grey body seen from above
// with air vents and its lens barrel pointing down, and the pale colour of its light and lens glass. The setup
// drawing (setup_drawing_view.dart) draws it at the projector's place.

import 'package:flutter/material.dart';

/// Colour of the projector's light and lens glass: a pale, only slightly warm white, so the cone reads as a lamp's
/// light rather than as a yellow shape. Colder still: e.g. 0xFFF2F6FF, a white with a hint of blue.
const Color projectorLightColor = Color(0xFFFFF5D1);

// The projector's shape at scale 1, in Flutter's logical pixels: a body wider than deep with its lens barrel pointing
// down, out of the body's lower edge.
const double projectorBodyWidthLogicalPx = 120;
const double projectorBodyDepthLogicalPx = 64;
const double projectorBodyCornerRadiusLogicalPx = 10;
const double projectorLensWidthLogicalPx = 30;
const double projectorLensLengthLogicalPx = 14;
const double projectorLensGlassThicknessLogicalPx = 4;
const double projectorVentLineLengthLogicalPx = 30;
const double projectorVentLineSpacingLogicalPx = 8;
const double projectorVentLineThicknessLogicalPx = 2;
const int projectorVentLineCount = 3;

/// Draws the projector pointing down, its lens exit (where the light leaves) at lensExitPoint, at scale (1 = the
/// sizes above). Returns the body's rectangle, e.g. for hit tests.
Rect paintDownwardProjector(Canvas canvas, Offset lensExitPoint, double scale) {
  final double bodyWidth = projectorBodyWidthLogicalPx * scale;
  final double bodyDepth = projectorBodyDepthLogicalPx * scale;
  final double lensWidth = projectorLensWidthLogicalPx * scale;
  final double lensLength = projectorLensLengthLogicalPx * scale;
  final double lensTopY = lensExitPoint.dy - lensLength;
  final double bodyTopY = lensTopY - bodyDepth;

  final Paint bodyPaint = Paint()..color = Colors.grey.shade600;
  final Rect bodyRect = Rect.fromLTWH(lensExitPoint.dx - bodyWidth / 2, bodyTopY, bodyWidth, bodyDepth);
  final Radius bodyCornerRadius = Radius.circular(projectorBodyCornerRadiusLogicalPx * scale);
  canvas.drawRRect(RRect.fromRectAndRadius(bodyRect, bodyCornerRadius), bodyPaint);

  _paintProjectorVentLines(canvas, bodyRect, scale);

  final Paint lensPaint = Paint()..color = Colors.grey.shade800;
  final Rect lensRect = Rect.fromLTWH(lensExitPoint.dx - lensWidth / 2, lensTopY, lensWidth, lensLength);
  canvas.drawRect(lensRect, lensPaint);

  final double lensGlassThickness = projectorLensGlassThicknessLogicalPx * scale;
  final Paint lensGlassPaint = Paint()..color = projectorLightColor;
  final Rect lensGlassRect = Rect.fromLTWH(lensExitPoint.dx - lensWidth / 2, lensExitPoint.dy - lensGlassThickness,
      lensWidth, lensGlassThickness);
  canvas.drawRect(lensGlassRect, lensGlassPaint);
  return bodyRect;
}

/// A few short dark lines on the body, left of the lens, to read as a projector's air vents.
void _paintProjectorVentLines(Canvas canvas, Rect bodyRect, double scale) {
  final Paint ventLinePaint = Paint()
    ..color = Colors.grey.shade800
    ..strokeWidth = projectorVentLineThicknessLogicalPx * scale;
  final double ventLineStartX = bodyRect.left + 14 * scale;
  final double ventLineEndX = ventLineStartX + projectorVentLineLengthLogicalPx * scale;
  // Above the lower edge, so they stay visible when the body's back part is cut off.
  final double lowestVentLineY = bodyRect.bottom - 14 * scale;
  for (int ventLineIndex = 0; ventLineIndex < projectorVentLineCount; ventLineIndex++) {
    final double ventLineY = lowestVentLineY - ventLineIndex * projectorVentLineSpacingLogicalPx * scale;
    canvas.drawLine(Offset(ventLineStartX, ventLineY), Offset(ventLineEndX, ventLineY), ventLinePaint);
  }
}
