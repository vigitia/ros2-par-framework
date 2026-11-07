// Written by Claude Code
//
// The table of the start screen's background, the surface the framework projects onto: a dark tabletop seen
// slightly from the front (a trapezoid, narrower at the back), a darker apron along its front edge and two front
// legs down to the window's bottom edge. The front edge spans the whole width, as if the user stood at the table.
// The back legs would stand behind the tabletop in this view, so they are not drawn. This file holds its geometry
// and how it is painted; projector_background.dart paints it under the projector's light, which ends at its
// corners.

import 'package:flutter/material.dart';

/// Depth of the tabletop on screen, from its back edge to its front edge.
const double tabletopSurfaceDepthLogicalPx = 110;

/// Height of the apron, the strip below the tabletop's front edge that joins the legs.
const double tableApronHeightLogicalPx = 14;

/// Room between the apron and the Scaffold's bottom bar, which sits between the legs.
const double tableApronMarginAboveBottomBarLogicalPx = 8;

/// The front legs, seen from the front: their distance from the window's side edges and their width.
const double tableFrontLegInsetLogicalPx = 24;
const double tableFrontLegWidthLogicalPx = 16;

/// How far the legs reach in from each side edge; content below the table keeps clear of them.
const double tableFrontLegsOuterExtentLogicalPx = tableFrontLegInsetLogicalPx + tableFrontLegWidthLogicalPx;

/// Back edge width as a share of the full width; smaller values look like a steeper view from above.
const double tabletopBackEdgeWidthFraction = 0.8;

const double tabletopFrontEdgeLineThicknessLogicalPx = 2;

/// Height of the table below the tabletop's front edge: the apron and the visible length of the legs, between
/// which the Scaffold's bottom bar sits. Needs a context inside the Scaffold's body (with extendBody), where
/// MediaQuery's bottom padding is the bar's height.
double computeTableHeightBelowTabletopLogicalPx(BuildContext context) {
  return MediaQuery.paddingOf(context).bottom + tableApronMarginAboveBottomBarLogicalPx + tableApronHeightLogicalPx;
}

/// Where the table's corners are in an area of a given size, its legs standing on the area's bottom edge.
class TabletopGeometry {
  TabletopGeometry({required Size areaSize, required double heightBelowTabletopLogicalPx})
      : frontEdgeY = areaSize.height - heightBelowTabletopLogicalPx,
        backEdgeY = areaSize.height - heightBelowTabletopLogicalPx - tabletopSurfaceDepthLogicalPx,
        backEdgeLeftX = areaSize.width * (1 - tabletopBackEdgeWidthFraction) / 2,
        backEdgeRightX = areaSize.width * (1 + tabletopBackEdgeWidthFraction) / 2,
        areaWidth = areaSize.width,
        areaHeight = areaSize.height;

  final double frontEdgeY;
  final double backEdgeY;
  final double backEdgeLeftX;
  final double backEdgeRightX;
  final double areaWidth;
  final double areaHeight;

  Offset get backLeftCorner => Offset(backEdgeLeftX, backEdgeY);
  Offset get backRightCorner => Offset(backEdgeRightX, backEdgeY);
  Offset get frontLeftCorner => Offset(0, frontEdgeY);
  Offset get frontRightCorner => Offset(areaWidth, frontEdgeY);

  Path createTabletopPath() {
    return Path()
      ..moveTo(backLeftCorner.dx, backLeftCorner.dy)
      ..lineTo(backRightCorner.dx, backRightCorner.dy)
      ..lineTo(frontRightCorner.dx, frontRightCorner.dy)
      ..lineTo(frontLeftCorner.dx, frontLeftCorner.dy)
      ..close();
  }
}

/// Paints the tabletop, the apron and legs below it, and a light line along the front edge, which keeps the edge
/// visible in the dark theme.
void paintTabletop(Canvas canvas, TabletopGeometry tabletopGeometry, ColorScheme colorScheme) {
  canvas.drawPath(tabletopGeometry.createTabletopPath(), Paint()..color = colorScheme.surfaceContainerHigh);

  // Darker than the lit tabletop, as faces turned away from the light, but lighter than the background, so the
  // legs stand out against it.
  final Paint apronAndLegsPaint = Paint()..color = colorScheme.surfaceContainer;
  final double apronBottomY = tabletopGeometry.frontEdgeY + tableApronHeightLogicalPx;
  final Rect apronRect = Rect.fromLTRB(0, tabletopGeometry.frontEdgeY, tabletopGeometry.areaWidth, apronBottomY);
  canvas.drawRect(apronRect, apronAndLegsPaint);
  final Rect leftLegRect = Rect.fromLTRB(
      tableFrontLegInsetLogicalPx, apronBottomY, tableFrontLegsOuterExtentLogicalPx, tabletopGeometry.areaHeight);
  final Rect rightLegRect = Rect.fromLTRB(tabletopGeometry.areaWidth - tableFrontLegsOuterExtentLogicalPx,
      apronBottomY, tabletopGeometry.areaWidth - tableFrontLegInsetLogicalPx, tabletopGeometry.areaHeight);
  canvas.drawRect(leftLegRect, apronAndLegsPaint);
  canvas.drawRect(rightLegRect, apronAndLegsPaint);

  final Paint frontEdgePaint = Paint()
    ..color = colorScheme.outlineVariant
    ..strokeWidth = tabletopFrontEdgeLineThicknessLogicalPx;
  canvas.drawLine(tabletopGeometry.frontLeftCorner, tabletopGeometry.frontRightCorner, frontEdgePaint);
}
