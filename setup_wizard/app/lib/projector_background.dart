// Written by Claude Code
//
// Decorative background: a simplified grey projector seen from above, fixed at the top centre with its back part
// cut off by the window's top edge, shining a yellow light cone down that reaches the window's edges. Only the
// cone turns slightly towards the mouse cursor. Drawn from a few shapes so it scales with the window and needs no
// image file.

import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// Shows child in front of the projector background. Wraps the content instead of sitting behind it, so the
/// cone also follows the mouse while the cursor is over the content.
class ProjectorBackground extends StatefulWidget {
  const ProjectorBackground({super.key, required this.child});

  final Widget child;

  @override
  State<ProjectorBackground> createState() => _ProjectorBackgroundState();
}

class _ProjectorBackgroundState extends State<ProjectorBackground> {
  /// Mouse position in this widget's coordinates, null while the cursor is outside. A notifier instead of
  /// setState, so a mouse move repaints only the background, not the content.
  final ValueNotifier<Offset?> _mousePositionNotifier = ValueNotifier<Offset?>(null);

  @override
  void dispose() {
    _mousePositionNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      // Also receives the cursor while it is over the content.
      hitTestBehavior: HitTestBehavior.translucent,
      onHover: (PointerHoverEvent event) {
        _mousePositionNotifier.value = event.localPosition;
      },
      onExit: (PointerExitEvent event) {
        _mousePositionNotifier.value = null;
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          CustomPaint(painter: _ProjectorBackgroundPainter(mousePositionNotifier: _mousePositionNotifier)),
          widget.child,
        ],
      ),
    );
  }
}

class _ProjectorBackgroundPainter extends CustomPainter {
  _ProjectorBackgroundPainter({required this.mousePositionNotifier}) : super(repaint: mousePositionNotifier);

  final ValueNotifier<Offset?> mousePositionNotifier;

  // Sizes in Flutter's logical pixels. Seen from above: the body is wider than deep, the lens barrel sticks out of
  // its front edge towards the bottom of the window.
  static const double bodyWidthLogicalPx = 120;
  static const double bodyDepthLogicalPx = 64;
  static const double bodyCornerRadiusLogicalPx = 10;
  static const double lensWidthLogicalPx = 30;
  static const double lensLengthLogicalPx = 14;
  static const double lensGlassThicknessLogicalPx = 4;
  static const double ventLineLengthLogicalPx = 30;
  static const double ventLineSpacingLogicalPx = 8;
  static const double ventLineThicknessLogicalPx = 2;
  static const int ventLineCount = 3;

  /// Share of the projector's total height (body and lens) above the window's top edge, i.e. cut off.
  static const double hiddenAboveWindowFraction = 0.25;

  /// Half the opening angle of the light cone.
  static const double coneHalfAngleRad = 30 * math.pi / 180;

  /// How strongly the cone turns towards the cursor: 0.25 turns it a quarter of the angle to the cursor.
  static const double mouseFollowFraction = 0.25;

  /// The cone never turns further than this from straight down.
  static const double maximumConeTiltRad = 12 * math.pi / 180;

  // Faint, so text over the cone stays readable; fades out with the distance from the lens.
  static const double coneLensOpacity = 0.22;
  static const double coneFarOpacity = 0.02;

  @override
  void paint(Canvas canvas, Size size) {
    // The cone is drawn longer than the window and cut off at its edges; the projector's back too.
    canvas.clipRect(Offset.zero & size);

    final double centreX = size.width / 2;
    const double projectorTotalHeight = bodyDepthLogicalPx + lensLengthLogicalPx;
    const double bodyTopY = -projectorTotalHeight * hiddenAboveWindowFraction;
    const double lensTopY = bodyTopY + bodyDepthLogicalPx;
    const double lensExitY = lensTopY + lensLengthLogicalPx;
    final Offset lensExitPoint = Offset(centreX, lensExitY);

    // The cone first, so the projector covers its start.
    _paintLightCone(canvas, size, lensExitPoint);

    final Paint bodyPaint = Paint()..color = Colors.grey.shade600;
    final Rect bodyRect = Rect.fromLTWH(centreX - bodyWidthLogicalPx / 2, bodyTopY, bodyWidthLogicalPx,
        bodyDepthLogicalPx);
    canvas.drawRRect(RRect.fromRectAndRadius(bodyRect, const Radius.circular(bodyCornerRadiusLogicalPx)), bodyPaint);

    _paintVentLines(canvas, bodyRect);

    final Paint lensPaint = Paint()..color = Colors.grey.shade800;
    final Rect lensRect = Rect.fromLTWH(centreX - lensWidthLogicalPx / 2, lensTopY, lensWidthLogicalPx,
        lensLengthLogicalPx);
    canvas.drawRect(lensRect, lensPaint);

    final Paint lensGlassPaint = Paint()..color = Colors.yellow.shade200;
    final Rect lensGlassRect = Rect.fromLTWH(centreX - lensWidthLogicalPx / 2,
        lensExitY - lensGlassThicknessLogicalPx, lensWidthLogicalPx, lensGlassThicknessLogicalPx);
    canvas.drawRect(lensGlassRect, lensGlassPaint);
  }

  /// A few short dark lines on the body's top, left of the lens, to read as a projector's air vents.
  void _paintVentLines(Canvas canvas, Rect bodyRect) {
    final Paint ventLinePaint = Paint()
      ..color = Colors.grey.shade800
      ..strokeWidth = ventLineThicknessLogicalPx;
    final double ventLineStartX = bodyRect.left + 14;
    final double ventLineEndX = ventLineStartX + ventLineLengthLogicalPx;
    // Below the part hidden above the window, above the front edge.
    final double lowestVentLineY = bodyRect.bottom - 14;
    for (int ventLineIndex = 0; ventLineIndex < ventLineCount; ventLineIndex++) {
      final double ventLineY = lowestVentLineY - ventLineIndex * ventLineSpacingLogicalPx;
      canvas.drawLine(Offset(ventLineStartX, ventLineY), Offset(ventLineEndX, ventLineY), ventLinePaint);
    }
  }

  /// Tilt of the cone from straight down in radians, positive towards the right; 0 while the cursor is outside.
  double _computeConeTiltTowardsMouse(Offset lensExitPoint) {
    final Offset? mousePosition = mousePositionNotifier.value;
    if (mousePosition == null) {
      return 0;
    }
    final Offset lensToMouse = mousePosition - lensExitPoint;
    // Angle from the downward direction: atan2 of the sideways over the downward distance.
    final double angleToMouseRad = math.atan2(lensToMouse.dx, lensToMouse.dy);
    final double followedAngleRad = angleToMouseRad * mouseFollowFraction;
    return followedAngleRad.clamp(-maximumConeTiltRad, maximumConeTiltRad);
  }

  /// Paints the cone from the lens exit, tilted towards the mouse, long enough to reach every window edge.
  void _paintLightCone(Canvas canvas, Size size, Offset lensExitPoint) {
    final double coneTiltRad = _computeConeTiltTowardsMouse(lensExitPoint);
    final double coneLength = size.width + size.height;
    final double lensHalfWidth = lensWidthLogicalPx / 2;
    final double coneFarHalfWidth = lensHalfWidth + coneLength * math.tan(coneHalfAngleRad);

    // In the cone's own frame: origin at the lens exit, +y along the light. Canvas.rotate turns clockwise on
    // screen, so a tilt to the right (positive) needs the negative angle.
    canvas.save();
    canvas.translate(lensExitPoint.dx, lensExitPoint.dy);
    canvas.rotate(-coneTiltRad);

    final Path conePath = Path()
      ..moveTo(-lensHalfWidth, 0)
      ..lineTo(lensHalfWidth, 0)
      ..lineTo(coneFarHalfWidth, coneLength)
      ..lineTo(-coneFarHalfWidth, coneLength)
      ..close();
    final RadialGradient coneGradient = RadialGradient(
      colors: [
        Colors.yellow.withValues(alpha: coneLensOpacity),
        Colors.yellow.withValues(alpha: coneFarOpacity),
      ],
    );
    final Rect gradientBounds = Rect.fromCircle(center: Offset.zero, radius: coneLength);
    final Paint conePaint = Paint()..shader = coneGradient.createShader(gradientBounds);
    canvas.drawPath(conePath, conePaint);

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _ProjectorBackgroundPainter oldPainter) {
    // Mouse moves repaint through the notifier passed as repaint.
    return oldPainter.mousePositionNotifier != mousePositionNotifier;
  }
}
