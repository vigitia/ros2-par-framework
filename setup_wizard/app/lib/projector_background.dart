// Written by Claude Code
//
// Decorative background: a simplified grey projector hanging at the top centre and looking down, shining a yellow
// light cone that reaches the window's edges. The projector tilts somewhat towards the mouse cursor. Drawn from a
// few shapes so it scales with the window and needs no image file.

import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// Shows child in front of the projector background. Wraps the content instead of sitting behind it, so the
/// projector also follows the mouse while the cursor is over the content.
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

  // Sizes in Flutter's logical pixels. The body hangs vertically below the mount, the lens points down.
  static const double mountWidthLogicalPx = 10;
  static const double mountHeightLogicalPx = 16;
  static const double bodyWidthLogicalPx = 36;
  static const double bodyLengthLogicalPx = 64;
  static const double bodyCornerRadiusLogicalPx = 8;
  static const double lensWidthLogicalPx = 20;
  static const double lensLengthLogicalPx = 8;
  static const double lensGlassThicknessLogicalPx = 3;

  /// Half the opening angle of the light cone.
  static const double coneHalfAngleRad = 30 * math.pi / 180;

  /// How strongly the projector turns towards the cursor: 0.5 turns it half the angle to the cursor.
  static const double mouseFollowFraction = 0.5;

  /// The projector never tilts further than this from straight down.
  static const double maximumTiltRad = 25 * math.pi / 180;

  // Faint, so text over the cone stays readable; fades out with the distance from the lens.
  static const double coneLensOpacity = 0.22;
  static const double coneFarOpacity = 0.02;

  @override
  void paint(Canvas canvas, Size size) {
    // The cone is drawn longer than the window and cut off at its edges.
    canvas.clipRect(Offset.zero & size);

    final Offset pivotPoint = Offset(size.width / 2, mountHeightLogicalPx);
    final double tiltRad = _computeTiltTowardsMouse(pivotPoint);

    final Paint mountPaint = Paint()..color = Colors.grey.shade700;
    final Rect mountRect = Rect.fromLTWH(pivotPoint.dx - mountWidthLogicalPx / 2, 0, mountWidthLogicalPx,
        mountHeightLogicalPx);
    canvas.drawRect(mountRect, mountPaint);

    // From here on in the projector's own frame: origin at the pivot, +y along the optical axis.
    // Canvas.rotate turns clockwise on screen, so a tilt to the right (positive) needs the negative angle.
    canvas.save();
    canvas.translate(pivotPoint.dx, pivotPoint.dy);
    canvas.rotate(-tiltRad);

    final double lensExitY = bodyLengthLogicalPx + lensLengthLogicalPx;
    // Long enough to reach every window edge from the pivot.
    final double coneLength = size.width + size.height;
    _paintLightCone(canvas, lensExitY, coneLength);

    final Paint bodyPaint = Paint()..color = Colors.grey.shade600;
    final Rect bodyRect = Rect.fromLTWH(-bodyWidthLogicalPx / 2, 0, bodyWidthLogicalPx, bodyLengthLogicalPx);
    canvas.drawRRect(RRect.fromRectAndRadius(bodyRect, const Radius.circular(bodyCornerRadiusLogicalPx)), bodyPaint);

    final Paint lensPaint = Paint()..color = Colors.grey.shade800;
    final Rect lensRect = Rect.fromLTWH(-lensWidthLogicalPx / 2, bodyLengthLogicalPx, lensWidthLogicalPx,
        lensLengthLogicalPx);
    canvas.drawRect(lensRect, lensPaint);

    final Paint lensGlassPaint = Paint()..color = Colors.yellow.shade200;
    final Rect lensGlassRect = Rect.fromLTWH(-lensWidthLogicalPx / 2, lensExitY - lensGlassThicknessLogicalPx,
        lensWidthLogicalPx, lensGlassThicknessLogicalPx);
    canvas.drawRect(lensGlassRect, lensGlassPaint);

    canvas.restore();
  }

  /// Tilt from straight down in radians, positive towards the right; 0 while the cursor is outside.
  double _computeTiltTowardsMouse(Offset pivotPoint) {
    final Offset? mousePosition = mousePositionNotifier.value;
    if (mousePosition == null) {
      return 0;
    }
    final Offset pivotToMouse = mousePosition - pivotPoint;
    // Angle from the downward direction: atan2 of the sideways over the downward distance.
    final double angleToMouseRad = math.atan2(pivotToMouse.dx, pivotToMouse.dy);
    final double followedAngleRad = angleToMouseRad * mouseFollowFraction;
    return followedAngleRad.clamp(-maximumTiltRad, maximumTiltRad);
  }

  /// Paints the cone in the projector's frame, from the lens along +y over coneLength.
  void _paintLightCone(Canvas canvas, double lensExitY, double coneLength) {
    final double lensHalfWidth = lensWidthLogicalPx / 2;
    final double coneFarHalfWidth = lensHalfWidth + coneLength * math.tan(coneHalfAngleRad);
    final Path conePath = Path()
      ..moveTo(-lensHalfWidth, lensExitY)
      ..lineTo(lensHalfWidth, lensExitY)
      ..lineTo(coneFarHalfWidth, lensExitY + coneLength)
      ..lineTo(-coneFarHalfWidth, lensExitY + coneLength)
      ..close();

    final Offset lensExitPoint = Offset(0, lensExitY);
    final RadialGradient coneGradient = RadialGradient(
      colors: [
        Colors.yellow.withValues(alpha: coneLensOpacity),
        Colors.yellow.withValues(alpha: coneFarOpacity),
      ],
    );
    final Rect gradientBounds = Rect.fromCircle(center: lensExitPoint, radius: coneLength);
    final Paint conePaint = Paint()..shader = coneGradient.createShader(gradientBounds);
    canvas.drawPath(conePath, conePaint);
  }

  @override
  bool shouldRepaint(covariant _ProjectorBackgroundPainter oldPainter) {
    // Mouse moves repaint through the notifier passed as repaint.
    return oldPainter.mousePositionNotifier != mousePositionNotifier;
  }
}
