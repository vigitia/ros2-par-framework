// Written by Claude Code
//
// Decorative background of the start screen, the scene of a PAR setup: a simplified grey projector seen from
// above, fixed at the top centre with its back part cut off by the window's top edge, shining a pale white light cone
// down onto a dark table at the bottom (tabletop_shape.dart). The cone's edges end at the tabletop's corners, so the
// light always covers exactly the tabletop. The rays that pass through the mouse cursor shine brighter, down onto
// the tabletop, while the cursor is inside the light. Drawn from a few shapes so it scales with the window and needs no image file.

import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'tabletop_shape.dart';

/// Shows child in front of the background. Wraps the content instead of sitting behind it, so the rays also
/// follow the mouse while the cursor is over the content. Must sit in a Scaffold's body with extendBody: the
/// table's legs reach behind the bottom bar (see computeTableHeightBelowTabletopLogicalPx).
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
    final CustomPaint scenePaint = CustomPaint(
      painter: _ProjectorBackgroundPainter(
        mousePositionNotifier: _mousePositionNotifier,
        tableHeightBelowTabletopLogicalPx: computeTableHeightBelowTabletopLogicalPx(context),
        colorScheme: Theme.of(context).colorScheme,
      ),
    );
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
        children: [scenePaint, widget.child],
      ),
    );
  }
}

/// Colour of the projector's light and lens glass: a pale, only slightly warm white, so the cone reads as a lamp's
/// light rather than as a yellow shape. Colder still: e.g. 0xFFF2F6FF, a white with a hint of blue.
const Color projectorLightColor = Color(0xFFFFF5D1);

class _ProjectorBackgroundPainter extends CustomPainter {
  _ProjectorBackgroundPainter({
    required this.mousePositionNotifier,
    required this.tableHeightBelowTabletopLogicalPx,
    required this.colorScheme,
  }) : super(repaint: mousePositionNotifier);

  final ValueNotifier<Offset?> mousePositionNotifier;
  final double tableHeightBelowTabletopLogicalPx;
  final ColorScheme colorScheme;

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

  // Faint, so text over the cone stays readable; fades out with the distance from the lens.
  static const double coneLensOpacity = 0.22;
  static const double coneFarOpacity = 0.02;

  /// Half the opening angle of the brighter rays through the cursor; they fade out towards both edges.
  static const double cursorRaysHalfAngleRad = 6 * math.pi / 180;

  /// Added to the cone's light at the cursor's angle, in the air and, on top of that, on the tabletop.
  static const double cursorRaysOpacity = 0.14;
  static const double cursorRaysOnTabletopOpacity = 0.22;

  @override
  void paint(Canvas canvas, Size size) {
    // The projector's back is cut off by the window's top edge.
    canvas.clipRect(Offset.zero & size);

    final double centreX = size.width / 2;
    const double projectorTotalHeight = bodyDepthLogicalPx + lensLengthLogicalPx;
    const double bodyTopY = -projectorTotalHeight * hiddenAboveWindowFraction;
    const double lensTopY = bodyTopY + bodyDepthLogicalPx;
    const double lensExitY = lensTopY + lensLengthLogicalPx;
    final Offset lensExitPoint = Offset(centreX, lensExitY);

    // Back to front: the table, the light falling onto it, the projector covering the light's start.
    final TabletopGeometry tabletopGeometry =
        TabletopGeometry(areaSize: size, heightBelowTabletopLogicalPx: tableHeightBelowTabletopLogicalPx);
    paintTabletop(canvas, tabletopGeometry, colorScheme);
    _paintLight(canvas, lensExitPoint, tabletopGeometry);

    final Paint bodyPaint = Paint()..color = Colors.grey.shade600;
    final Rect bodyRect = Rect.fromLTWH(centreX - bodyWidthLogicalPx / 2, bodyTopY, bodyWidthLogicalPx,
        bodyDepthLogicalPx);
    canvas.drawRRect(RRect.fromRectAndRadius(bodyRect, const Radius.circular(bodyCornerRadiusLogicalPx)), bodyPaint);

    _paintVentLines(canvas, bodyRect);

    final Paint lensPaint = Paint()..color = Colors.grey.shade800;
    final Rect lensRect = Rect.fromLTWH(centreX - lensWidthLogicalPx / 2, lensTopY, lensWidthLogicalPx,
        lensLengthLogicalPx);
    canvas.drawRect(lensRect, lensPaint);

    final Paint lensGlassPaint = Paint()..color = projectorLightColor;
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

  /// The light: from the lens exit to the tabletop's back corners, then over the whole tabletop to its front edge.
  /// The vertical front face stays dark, as under a projector shining down from above.
  Path _createLightPath(Offset lensExitPoint, TabletopGeometry tabletopGeometry) {
    const double lensHalfWidth = lensWidthLogicalPx / 2;
    return Path()
      ..moveTo(lensExitPoint.dx - lensHalfWidth, lensExitPoint.dy)
      ..lineTo(tabletopGeometry.backLeftCorner.dx, tabletopGeometry.backLeftCorner.dy)
      ..lineTo(tabletopGeometry.frontLeftCorner.dx, tabletopGeometry.frontLeftCorner.dy)
      ..lineTo(tabletopGeometry.frontRightCorner.dx, tabletopGeometry.frontRightCorner.dy)
      ..lineTo(tabletopGeometry.backRightCorner.dx, tabletopGeometry.backRightCorner.dy)
      ..lineTo(lensExitPoint.dx + lensHalfWidth, lensExitPoint.dy)
      ..close();
  }

  /// The light colour, fading from lensOpacity at the lens exit to farOpacity at fadeRadius from it.
  Shader _createFadingLightShader(Offset lensExitPoint, double fadeRadius, double lensOpacity, double farOpacity) {
    final RadialGradient lightGradient = RadialGradient(
      colors: [
        projectorLightColor.withValues(alpha: lensOpacity),
        projectorLightColor.withValues(alpha: farOpacity),
      ],
    );
    return lightGradient.createShader(Rect.fromCircle(center: lensExitPoint, radius: fadeRadius));
  }

  void _paintLight(Canvas canvas, Offset lensExitPoint, TabletopGeometry tabletopGeometry) {
    final Path lightPath = _createLightPath(lensExitPoint, tabletopGeometry);
    // The front corners are the farthest points the light reaches.
    final double lightReachLogicalPx = (tabletopGeometry.frontLeftCorner - lensExitPoint).distance;

    final Paint conePaint = Paint()
      ..shader = _createFadingLightShader(lensExitPoint, lightReachLogicalPx, coneLensOpacity, coneFarOpacity);
    canvas.drawPath(lightPath, conePaint);

    final Offset? mousePosition = mousePositionNotifier.value;
    if (mousePosition == null || !lightPath.contains(mousePosition)) {
      return;
    }
    _paintCursorRays(canvas, lensExitPoint, mousePosition, lightPath, tabletopGeometry);
  }

  /// Brighter rays from the lens exit through the cursor, fading out to both sides, down onto the tabletop, where
  /// they light a brighter strip. A sweep gradient around the lens is bright exactly at the cursor's angle, so the
  /// rays reach as far as the light does, whatever the window size.
  void _paintCursorRays(
      Canvas canvas, Offset lensExitPoint, Offset mousePosition, Path lightPath, TabletopGeometry tabletopGeometry) {
    final Offset lensToMouse = mousePosition - lensExitPoint;
    // A sweep gradient counts angles clockwise from the right on screen (y points down), as atan2(dy, dx) does.
    final double angleToMouseRad = math.atan2(lensToMouse.dy, lensToMouse.dx);
    final Rect sweepBounds = Rect.fromCircle(center: lensExitPoint, radius: tabletopGeometry.areaWidth + tabletopGeometry.areaHeight);

    canvas.save();
    canvas.clipPath(lightPath);
    canvas.drawRect(sweepBounds, Paint()..shader = _createCursorRaysShader(sweepBounds, angleToMouseRad, cursorRaysOpacity));
    // Where the rays meet the tabletop they light it up more than the air above it.
    canvas.clipPath(tabletopGeometry.createTabletopPath());
    canvas.drawRect(sweepBounds, Paint()..shader = _createCursorRaysShader(sweepBounds, angleToMouseRad, cursorRaysOnTabletopOpacity));
    canvas.restore();
  }

  /// Transparent outside the rays' angle, peakOpacity at the cursor's angle; outside the start and end angle the
  /// gradient keeps its transparent end colours.
  Shader _createCursorRaysShader(Rect sweepBounds, double angleToMouseRad, double peakOpacity) {
    final SweepGradient cursorRaysGradient = SweepGradient(
      startAngle: angleToMouseRad - cursorRaysHalfAngleRad,
      endAngle: angleToMouseRad + cursorRaysHalfAngleRad,
      colors: [
        projectorLightColor.withValues(alpha: 0),
        projectorLightColor.withValues(alpha: peakOpacity),
        projectorLightColor.withValues(alpha: 0),
      ],
    );
    return cursorRaysGradient.createShader(sweepBounds);
  }

  @override
  bool shouldRepaint(covariant _ProjectorBackgroundPainter oldPainter) {
    // Mouse moves repaint through the notifier passed as repaint.
    return oldPainter.mousePositionNotifier != mousePositionNotifier ||
        oldPainter.tableHeightBelowTabletopLogicalPx != tableHeightBelowTabletopLogicalPx ||
        oldPainter.colorScheme != colorScheme;
  }
}
