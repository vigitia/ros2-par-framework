// Written by Claude Code
//
// The profile's setup seen from the front, simplified and flat like a drawing: the table, the projector with the
// light it throws onto the table, and each camera with its viewing direction and, where its intrinsics are known,
// its field of view. Seen from the front: from where people read the projected image (its bottom edge), so left to
// right is the projected image's left to right (or the camera image's without a projector calibration, see
// SetupGeometry.frontViewReferenceText); up is the height above the table. Metres are drawn to scale, the same in both
// directions. Only measured positions are drawn: a camera without a measured pose is left out (getDrawnCameras), and
// the caller says below the drawing what it still needs. Cameras and the projector have shapes of their own (a
// camera body with a lens barrel along its view; paintDownwardProjector's projector pointing down, its lens exit at
// the optical centre) and can be clicked to adjust that device. The caller fetches the data from the backend
// (SetupGeometryApi).

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'projector_drawing.dart';
import 'setup_geometry_api.dart';

const double setupSideViewHeightLogicalPx = 340;

/// Room around the drawing for labels: above the highest device, beside the outermost ones, below for the legs.
const double sideViewLabelMarginTopLogicalPx = 56;
const double sideViewSideMarginLogicalPx = 90;
const double sideViewTableMarginBottomLogicalPx = 36;
const double sideViewTableThicknessLogicalPx = 8;
const double sideViewTableLegLengthLogicalPx = 24;

/// The table is drawn this much wider than what lies on it, as a fraction of that width.
const double sideViewTableOverhangRatio = 0.08;

/// Smallest width and height shown, so a single point or a flat setup still gets a sensible scale.
const double sideViewMinimumSpanM = 0.3;

/// Half the size of a camera icon, which labels keep clear of.
const double cameraIconRadiusLogicalPx = 16;

/// A click or hover this close to a camera's icon counts as on the camera.
const double cameraHitRadiusLogicalPx = 26;

/// A click or hover this far around the projector's housing still counts as on the projector.
const double projectorHitMarginLogicalPx = 8;
const double dashLengthLogicalPx = 6;
const double dashGapLogicalPx = 4;

/// The projector is paintDownwardProjector's (projector_drawing.dart), drawn at this fraction of its size.
const double projectorDrawingScale = 0.4;

/// Device key of the projector, for hover and click; cameras have one each (_createCameraDeviceKey).
const String projectorDeviceKey = 'projector';

String _createCameraDeviceKey(CameraGeometry camera) {
  return 'camera:${camera.cameraId}';
}

/// The cameras the drawing shows: those with a measured pose. A placeholder pose says nothing about where the camera
/// really is.
List<CameraGeometry> getDrawnCameras(SetupGeometry setupGeometry) {
  final List<CameraGeometry> drawnCameras = [];
  for (final CameraGeometry camera in setupGeometry.cameras) {
    if (camera.isPoseMeasured) {
      drawnCameras.add(camera);
    }
  }
  return drawnCameras;
}

/// False when neither a camera nor the projector's image can be drawn, so the drawing would be empty.
bool hasSetupDrawing(SetupGeometry setupGeometry) {
  return getDrawnCameras(setupGeometry).isNotEmpty || setupGeometry.projector != null;
}

class SetupSideView extends StatefulWidget {
  const SetupSideView({
    super.key,
    required this.setupGeometry,
    required this.onCameraClicked,
    required this.onProjectorClicked,
  });

  final SetupGeometry setupGeometry;

  /// Called with the camera unit the user clicked in the drawing, to adjust it.
  final ValueChanged<CameraGeometry> onCameraClicked;

  /// Called when the user clicked the projector in the drawing, to adjust it.
  final VoidCallback onProjectorClicked;

  @override
  State<SetupSideView> createState() => _SetupSideViewState();
}

class _SetupSideViewState extends State<SetupSideView> {
  /// The device under the mouse pointer (a device key), null for none.
  String? _hoveredDeviceKey;

  void _setHoveredDeviceKey(String? hoveredDeviceKey) {
    if (hoveredDeviceKey == _hoveredDeviceKey) {
      return;
    }
    setState(() {
      _hoveredDeviceKey = hoveredDeviceKey;
    });
  }

  void _openDevice(String? deviceKey) {
    if (deviceKey == null) {
      return;
    }
    if (deviceKey == projectorDeviceKey) {
      widget.onProjectorClicked();
      return;
    }
    for (final CameraGeometry camera in getDrawnCameras(widget.setupGeometry)) {
      if (_createCameraDeviceKey(camera) == deviceKey) {
        widget.onCameraClicked(camera);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final TextTheme textTheme = Theme.of(context).textTheme;
    final _SideViewColors sideViewColors = _SideViewColors(
      cameraColor: colorScheme.primary,
      // The projector's lamp light (projector_drawing.dart), so projector and light look the same everywhere
      projectorColor: projectorLightColor,
      tableColor: colorScheme.outline,
      tableFillColor: colorScheme.surfaceContainerHighest,
      highlightColor: colorScheme.onSurface,
    );
    final TextStyle labelTextStyle = textTheme.labelMedium ?? const TextStyle(fontSize: 12);
    return SizedBox(
      height: setupSideViewHeightLogicalPx,
      width: double.infinity,
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final Size drawingSize = Size(constraints.maxWidth, setupSideViewHeightLogicalPx);
          final _SideViewLayout? sideViewLayout = _SideViewLayout.create(
            widget.setupGeometry,
            drawingSize,
            labelTextStyle,
            sideViewColors,
          );
          if (sideViewLayout == null) {
            return const SizedBox.shrink();
          }
          MouseCursor mouseCursor = MouseCursor.defer;
          if (_hoveredDeviceKey != null) {
            mouseCursor = SystemMouseCursors.click;
          }
          return MouseRegion(
            cursor: mouseCursor,
            onHover: (PointerHoverEvent hoverEvent) =>
                _setHoveredDeviceKey(sideViewLayout.findDeviceKeyAt(hoverEvent.localPosition)),
            onExit: (PointerExitEvent exitEvent) => _setHoveredDeviceKey(null),
            child: GestureDetector(
              onTapUp: (TapUpDetails tapDetails) =>
                  _openDevice(sideViewLayout.findDeviceKeyAt(tapDetails.localPosition)),
              child: CustomPaint(
                size: drawingSize,
                painter: _SetupSideViewPainter(
                  sideViewLayout: sideViewLayout,
                  sideViewColors: sideViewColors,
                  hoveredDeviceKey: _hoveredDeviceKey,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// The drawing's colours, from the app's theme.
class _SideViewColors {
  const _SideViewColors({
    required this.cameraColor,
    required this.projectorColor,
    required this.tableColor,
    required this.tableFillColor,
    required this.highlightColor,
  });

  final Color cameraColor;
  final Color projectorColor;
  final Color tableColor;
  final Color tableFillColor;

  /// The ring around the device under the mouse pointer.
  final Color highlightColor;
}

/// Where a camera unit is drawn and where its label goes.
class _CameraPlacement {
  const _CameraPlacement({
    required this.camera,
    required this.positionPx,
    required this.viewAngleRad,
    required this.labelPainter,
    required this.labelTopLeftPx,
  });

  final CameraGeometry camera;
  final Offset positionPx;

  /// Direction the camera looks on the canvas (atan2 of y over x; pi / 2 is straight down).
  final double viewAngleRad;
  final TextPainter labelPainter;
  final Offset labelTopLeftPx;
}

/// Where the projector is drawn and where its label goes; only with a measured optical centre.
class _ProjectorPlacement {
  const _ProjectorPlacement({
    required this.lensCenterPx,
    required this.housingRect,
    required this.labelPainter,
    required this.labelTopLeftPx,
  });

  /// The optical centre, where the light starts.
  final Offset lensCenterPx;
  final Rect housingRect;
  final TextPainter labelPainter;
  final Offset labelTopLeftPx;
}

/// How the setup maps onto the canvas and where each device sits: shared by the painter and the hover and click
/// handling, so both always agree on what is where.
class _SideViewLayout {
  _SideViewLayout._({
    required this.setupGeometry,
    required this.scalePxPerM,
    required this.leftHorizontalM,
    required this.leftCanvasXPx,
    required this.tableTopCanvasYPx,
    required this.tableLeftM,
    required this.tableRightM,
  });

  final SetupGeometry setupGeometry;
  final double scalePxPerM;
  final double leftHorizontalM;
  final double leftCanvasXPx;
  final double tableTopCanvasYPx;
  final double tableLeftM;
  final double tableRightM;
  final List<_CameraPlacement> cameraPlacements = [];
  _ProjectorPlacement? projectorPlacement;

  /// The layout for a drawing of drawingSize; null when there is nothing to draw.
  static _SideViewLayout? create(
    SetupGeometry setupGeometry,
    Size drawingSize,
    TextStyle labelTextStyle,
    _SideViewColors sideViewColors,
  ) {
    final List<double> tableHorizontalsM = _collectTableHorizontalsM(setupGeometry);
    final List<double> deviceHorizontalsM = [];
    double highestZM = 0;
    for (final CameraGeometry camera in getDrawnCameras(setupGeometry)) {
      deviceHorizontalsM.add(_getHorizontalM(setupGeometry, camera.positionM));
      highestZM = math.max(highestZM, camera.positionM.zM);
    }
    final WorldPointM? projectorCenterM = setupGeometry.projector?.centerM;
    if (projectorCenterM != null) {
      deviceHorizontalsM.add(_getHorizontalM(setupGeometry, projectorCenterM));
      highestZM = math.max(highestZM, projectorCenterM.zM);
    }
    final List<double> allHorizontalsM = [...tableHorizontalsM, ...deviceHorizontalsM];
    if (allHorizontalsM.isEmpty) {
      return null;
    }

    // The table spans what lies on it (or below the devices when nothing does), with a little overhang
    List<double> tableSpanHorizontalsM = tableHorizontalsM;
    if (tableSpanHorizontalsM.isEmpty) {
      tableSpanHorizontalsM = deviceHorizontalsM;
    }
    final double spanLeftM = tableSpanHorizontalsM.reduce(math.min);
    final double spanRightM = tableSpanHorizontalsM.reduce(math.max);
    final double tableWidthM = math.max(spanRightM - spanLeftM, sideViewMinimumSpanM);
    final double tableCenterM = (spanLeftM + spanRightM) / 2;
    final double tableOverhangM = tableWidthM * sideViewTableOverhangRatio;
    final double tableLeftM = tableCenterM - tableWidthM / 2 - tableOverhangM;
    final double tableRightM = tableCenterM + tableWidthM / 2 + tableOverhangM;

    final double leftM = math.min(tableLeftM, allHorizontalsM.reduce(math.min));
    final double rightM = math.max(tableRightM, allHorizontalsM.reduce(math.max));
    final double heightM = math.max(highestZM, sideViewMinimumSpanM);
    final double drawableWidthPx = drawingSize.width - 2 * sideViewSideMarginLogicalPx;
    final double tableTopCanvasYPx = drawingSize.height - sideViewTableMarginBottomLogicalPx;
    final double drawableHeightPx = tableTopCanvasYPx - sideViewLabelMarginTopLogicalPx;
    // The same scale in both directions, so heights and widths compare as they are
    final double scalePxPerM = math.min(drawableWidthPx / (rightM - leftM), drawableHeightPx / heightM);
    final _SideViewLayout sideViewLayout = _SideViewLayout._(
      setupGeometry: setupGeometry,
      scalePxPerM: scalePxPerM,
      leftHorizontalM: leftM,
      leftCanvasXPx: (drawingSize.width - (rightM - leftM) * scalePxPerM) / 2,
      tableTopCanvasYPx: tableTopCanvasYPx,
      tableLeftM: tableLeftM,
      tableRightM: tableRightM,
    );
    // The projector first, so camera labels make room for its label
    sideViewLayout._placeProjector(labelTextStyle, sideViewColors);
    sideViewLayout._placeCameras(labelTextStyle, sideViewColors);
    return sideViewLayout;
  }

  /// Left to right as seen from the front, in metres along SetupGeometry.frontViewRightDirection.
  static double _getHorizontalM(SetupGeometry setupGeometry, WorldPointM pointM) {
    final List<double> rightDirection = setupGeometry.frontViewRightDirection;
    return pointM.xM * rightDirection[0] + pointM.yM * rightDirection[1];
  }

  /// The horizontal position of everything that lies on the table: projection area, fields of view, where the axes
  /// meet it.
  static List<double> _collectTableHorizontalsM(SetupGeometry setupGeometry) {
    final List<double> tableHorizontalsM = [];
    final ProjectorGeometry? projector = setupGeometry.projector;
    if (projector != null) {
      for (final WorldPointM cornerM in projector.projectionAreaM) {
        tableHorizontalsM.add(_getHorizontalM(setupGeometry, cornerM));
      }
    }
    for (final CameraGeometry camera in getDrawnCameras(setupGeometry)) {
      for (final WorldPointM footprintPointM in camera.tableFootprintM ?? const <WorldPointM>[]) {
        tableHorizontalsM.add(_getHorizontalM(setupGeometry, footprintPointM));
      }
      final WorldPointM? axisHitM = camera.opticalAxisTableHitM;
      if (axisHitM != null) {
        tableHorizontalsM.add(_getHorizontalM(setupGeometry, axisHitM));
      }
    }
    return tableHorizontalsM;
  }

  static TextPainter _createLabelPainter(String labelText, TextStyle labelTextStyle, Color labelColor) {
    final TextPainter labelPainter = TextPainter(
      text: TextSpan(
        text: labelText,
        style: labelTextStyle.copyWith(color: labelColor, fontWeight: FontWeight.w600),
      ),
      textDirection: TextDirection.ltr,
    );
    labelPainter.layout();
    return labelPainter;
  }

  double getHorizontalM(WorldPointM pointM) {
    return _getHorizontalM(setupGeometry, pointM);
  }

  Offset toCanvas(double horizontalM, double zM) {
    return Offset(leftCanvasXPx + (horizontalM - leftHorizontalM) * scalePxPerM, tableTopCanvasYPx - zM * scalePxPerM);
  }

  Offset toCanvasFromWorld(WorldPointM pointM) {
    return toCanvas(getHorizontalM(pointM), pointM.zM);
  }

  void _placeCameras(TextStyle labelTextStyle, _SideViewColors sideViewColors) {
    // What a camera label must not cover: the projector with its label and every camera icon. A label starts right
    // of its own icon, outside this square, so it never has to avoid that one
    final List<Rect> placedLabelRects = [];
    final _ProjectorPlacement? projector = projectorPlacement;
    if (projector != null) {
      placedLabelRects.add(projector.labelTopLeftPx & projector.labelPainter.size);
      placedLabelRects.add(projector.housingRect);
    }
    final List<CameraGeometry> drawnCameras = getDrawnCameras(setupGeometry);
    for (final CameraGeometry camera in drawnCameras) {
      placedLabelRects.add(
        Rect.fromCircle(center: toCanvasFromWorld(camera.positionM), radius: cameraIconRadiusLogicalPx),
      );
    }
    for (final CameraGeometry camera in drawnCameras) {
      final Offset positionPx = toCanvasFromWorld(camera.positionM);
      // Turned so the lens faces along the optical axis; straight down without one
      double viewAngleRad = math.pi / 2;
      final WorldPointM? axisHitM = camera.opticalAxisTableHitM;
      if (axisHitM != null) {
        final Offset axisDirectionPx = toCanvas(getHorizontalM(axisHitM), 0) - positionPx;
        viewAngleRad = math.atan2(axisDirectionPx.dy, axisDirectionPx.dx);
      }
      final String labelText = '${camera.cameraId} · ${camera.positionM.zM.toStringAsFixed(2)} m';
      final TextPainter labelPainter = _createLabelPainter(labelText, labelTextStyle, sideViewColors.cameraColor);
      final Offset labelTopLeftPx = _findFreeLabelTopLeft(
        positionPx + const Offset(22, -26),
        labelPainter.size,
        placedLabelRects,
      );
      placedLabelRects.add(labelTopLeftPx & labelPainter.size);
      cameraPlacements.add(
        _CameraPlacement(
          camera: camera,
          positionPx: positionPx,
          viewAngleRad: viewAngleRad,
          labelPainter: labelPainter,
          labelTopLeftPx: labelTopLeftPx,
        ),
      );
    }
  }

  /// Where a label of labelSize can go at or below wantedTopLeftPx without covering one placed before it.
  /// Simplification: moves labels down one line at a time and never sideways, so many cameras close together get a
  /// column of labels. Upgrade: try positions on all sides of the icon.
  static Offset _findFreeLabelTopLeft(Offset wantedTopLeftPx, Size labelSize, List<Rect> placedLabelRects) {
    Offset labelTopLeftPx = wantedTopLeftPx;
    bool isOverlapping = true;
    while (isOverlapping) {
      isOverlapping = false;
      final Rect labelRect = labelTopLeftPx & labelSize;
      for (final Rect placedLabelRect in placedLabelRects) {
        if (placedLabelRect.overlaps(labelRect)) {
          labelTopLeftPx = Offset(labelTopLeftPx.dx, placedLabelRect.bottom + 2);
          isOverlapping = true;
        }
      }
    }
    return labelTopLeftPx;
  }

  void _placeProjector(TextStyle labelTextStyle, _SideViewColors sideViewColors) {
    final WorldPointM? projectorCenterM = setupGeometry.projector?.centerM;
    if (projectorCenterM == null) {
      return;
    }
    final Offset lensCenterPx = toCanvasFromWorld(projectorCenterM);
    // The body above the lens, as paintDownwardProjector draws it
    final double bodyWidthPx = projectorBodyWidthLogicalPx * projectorDrawingScale;
    final double bodyDepthPx = projectorBodyDepthLogicalPx * projectorDrawingScale;
    final double lensLengthPx = projectorLensLengthLogicalPx * projectorDrawingScale;
    final Rect housingRect = Rect.fromLTWH(
      lensCenterPx.dx - bodyWidthPx / 2,
      lensCenterPx.dy - lensLengthPx - bodyDepthPx,
      bodyWidthPx,
      bodyDepthPx,
    );
    final String labelText = 'projector · ${projectorCenterM.zM.toStringAsFixed(2)} m';
    final TextPainter labelPainter = _createLabelPainter(labelText, labelTextStyle, sideViewColors.projectorColor);
    final Offset labelTopLeftPx = Offset(
      housingRect.center.dx - labelPainter.width / 2,
      housingRect.top - labelPainter.height - 6,
    );
    projectorPlacement = _ProjectorPlacement(
      lensCenterPx: lensCenterPx,
      housingRect: housingRect,
      labelPainter: labelPainter,
      labelTopLeftPx: labelTopLeftPx,
    );
  }

  /// The device whose icon or label is at canvasPointPx, as a device key; null for none. The projector wins over a
  /// camera at the same spot, and a camera drawn later over an earlier one, as they lie on top of each other.
  String? findDeviceKeyAt(Offset canvasPointPx) {
    final _ProjectorPlacement? projector = projectorPlacement;
    if (projector != null) {
      final Rect labelRect = projector.labelTopLeftPx & projector.labelPainter.size;
      final bool isOnHousing = projector.housingRect.inflate(projectorHitMarginLogicalPx).contains(canvasPointPx);
      final bool isOnLens = (canvasPointPx - projector.lensCenterPx).distance <= cameraHitRadiusLogicalPx / 2;
      if (isOnHousing || isOnLens || labelRect.contains(canvasPointPx)) {
        return projectorDeviceKey;
      }
    }
    for (final _CameraPlacement cameraPlacement in cameraPlacements.reversed) {
      final Rect labelRect = cameraPlacement.labelTopLeftPx & cameraPlacement.labelPainter.size;
      final bool isOnIcon = (canvasPointPx - cameraPlacement.positionPx).distance <= cameraHitRadiusLogicalPx;
      if (isOnIcon || labelRect.contains(canvasPointPx)) {
        return _createCameraDeviceKey(cameraPlacement.camera);
      }
    }
    return null;
  }
}

class _SetupSideViewPainter extends CustomPainter {
  _SetupSideViewPainter({required this.sideViewLayout, required this.sideViewColors, required this.hoveredDeviceKey});

  final _SideViewLayout sideViewLayout;
  final _SideViewColors sideViewColors;

  /// The device to highlight, under the mouse pointer; null for none.
  final String? hoveredDeviceKey;

  @override
  void paint(Canvas canvas, Size size) {
    _paintProjectorLight(canvas);
    for (final _CameraPlacement cameraPlacement in sideViewLayout.cameraPlacements) {
      _paintCameraView(canvas, cameraPlacement);
    }
    _paintTable(canvas);
    for (final _CameraPlacement cameraPlacement in sideViewLayout.cameraPlacements) {
      _paintCamera(canvas, cameraPlacement);
    }
    _paintProjector(canvas);
  }

  void _paintProjectorLight(Canvas canvas) {
    final ProjectorGeometry? projector = sideViewLayout.setupGeometry.projector;
    if (projector == null || projector.projectionAreaM.isEmpty) {
      return;
    }
    final Color projectorColor = sideViewColors.projectorColor;
    final List<double> areaHorizontalsM = [];
    for (final WorldPointM cornerM in projector.projectionAreaM) {
      areaHorizontalsM.add(sideViewLayout.getHorizontalM(cornerM));
    }
    final Offset areaLeftPx = sideViewLayout.toCanvas(areaHorizontalsM.reduce(math.min), 0);
    final Offset areaRightPx = sideViewLayout.toCanvas(areaHorizontalsM.reduce(math.max), 0);
    final _ProjectorPlacement? projectorPlacement = sideViewLayout.projectorPlacement;
    if (projectorPlacement == null) {
      // Position unknown: only the lit stretch of the table
      final Paint areaPaint = Paint()
        ..color = projectorColor
        ..strokeWidth = 6
        ..strokeCap = StrokeCap.butt;
      canvas.drawLine(areaLeftPx, areaRightPx, areaPaint);
      final TextPainter areaLabelPainter = TextPainter(
        text: TextSpan(
          text: 'projected area',
          style: TextStyle(color: projectorColor, fontSize: 12),
        ),
        textDirection: TextDirection.ltr,
      );
      areaLabelPainter.layout();
      final double areaCenterXPx = (areaLeftPx.dx + areaRightPx.dx) / 2;
      areaLabelPainter.paint(canvas, Offset(areaCenterXPx - areaLabelPainter.width / 2, areaLeftPx.dy - 20));
      return;
    }
    // From both edges of the lens glass, as paintDownwardProjector draws the lens
    final Offset lensCenterPx = projectorPlacement.lensCenterPx;
    final double lensHalfWidthPx = projectorLensWidthLogicalPx * projectorDrawingScale / 2;
    final Path lightPath = Path()
      ..moveTo(lensCenterPx.dx - lensHalfWidthPx, lensCenterPx.dy)
      ..lineTo(areaLeftPx.dx, areaLeftPx.dy)
      ..lineTo(areaRightPx.dx, areaRightPx.dy)
      ..lineTo(lensCenterPx.dx + lensHalfWidthPx, lensCenterPx.dy)
      ..close();
    canvas.drawPath(lightPath, Paint()..color = projectorColor.withValues(alpha: 0.16));
    canvas.drawPath(
      lightPath,
      Paint()
        ..color = projectorColor.withValues(alpha: 0.7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
  }

  void _paintCameraView(Canvas canvas, _CameraPlacement cameraPlacement) {
    final CameraGeometry camera = cameraPlacement.camera;
    final Color cameraColor = sideViewColors.cameraColor;
    final Offset cameraPx = cameraPlacement.positionPx;
    final List<WorldPointM>? footprintM = camera.tableFootprintM;
    if (footprintM != null && footprintM.isNotEmpty) {
      final List<double> footprintHorizontalsM = [];
      for (final WorldPointM footprintPointM in footprintM) {
        footprintHorizontalsM.add(sideViewLayout.getHorizontalM(footprintPointM));
      }
      final Offset viewLeftPx = sideViewLayout.toCanvas(footprintHorizontalsM.reduce(math.min), 0);
      final Offset viewRightPx = sideViewLayout.toCanvas(footprintHorizontalsM.reduce(math.max), 0);
      final Path viewPath = Path()
        ..moveTo(cameraPx.dx, cameraPx.dy)
        ..lineTo(viewLeftPx.dx, viewLeftPx.dy)
        ..lineTo(viewRightPx.dx, viewRightPx.dy)
        ..close();
      canvas.drawPath(viewPath, Paint()..color = cameraColor.withValues(alpha: 0.10));
      _strokePath(canvas, viewPath, cameraColor, isDashed: false);
    }
    final WorldPointM? axisHitM = camera.opticalAxisTableHitM;
    if (axisHitM != null) {
      final Offset axisHitPx = sideViewLayout.toCanvas(sideViewLayout.getHorizontalM(axisHitM), 0);
      final Path axisPath = Path()
        ..moveTo(cameraPx.dx, cameraPx.dy)
        ..lineTo(axisHitPx.dx, axisHitPx.dy);
      _strokePath(canvas, axisPath, cameraColor.withValues(alpha: 0.8), isDashed: true, strokeWidthPx: 1);
    }
  }

  void _paintTable(Canvas canvas) {
    final Offset tableLeftPx = sideViewLayout.toCanvas(sideViewLayout.tableLeftM, 0);
    final Offset tableRightPx = sideViewLayout.toCanvas(sideViewLayout.tableRightM, 0);
    final Rect tableTopRect = Rect.fromLTRB(
      tableLeftPx.dx,
      tableLeftPx.dy,
      tableRightPx.dx,
      tableLeftPx.dy + sideViewTableThicknessLogicalPx,
    );
    canvas.drawRect(tableTopRect, Paint()..color = sideViewColors.tableFillColor);
    final Paint tablePaint = Paint()
      ..color = sideViewColors.tableColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawRect(tableTopRect, tablePaint);
    const double legInsetPx = 12;
    final double legTopYPx = tableTopRect.bottom;
    final double legBottomYPx = legTopYPx + sideViewTableLegLengthLogicalPx;
    canvas.drawLine(
      Offset(tableTopRect.left + legInsetPx, legTopYPx),
      Offset(tableTopRect.left + legInsetPx, legBottomYPx),
      tablePaint,
    );
    canvas.drawLine(
      Offset(tableTopRect.right - legInsetPx, legTopYPx),
      Offset(tableTopRect.right - legInsetPx, legBottomYPx),
      tablePaint,
    );
  }

  /// A camera seen from the side: a body with a lens barrel pointing along its view.
  void _paintCamera(Canvas canvas, _CameraPlacement cameraPlacement) {
    final CameraGeometry camera = cameraPlacement.camera;
    final Color cameraColor = sideViewColors.cameraColor;
    final Offset cameraPx = cameraPlacement.positionPx;
    if (hoveredDeviceKey == _createCameraDeviceKey(camera)) {
      _paintHighlightRing(canvas, cameraPx, cameraHitRadiusLogicalPx);
    }

    canvas.save();
    canvas.translate(cameraPx.dx, cameraPx.dy);
    // Drawn looking down (+y on the canvas), then turned onto the view angle
    canvas.rotate(cameraPlacement.viewAngleRad - math.pi / 2);
    final RRect bodyRect = RRect.fromRectAndRadius(
      Rect.fromCenter(center: const Offset(0, -6), width: 24, height: 16),
      const Radius.circular(4),
    );
    // Widening towards the front, like a lens hood
    final Path lensBarrelPath = Path()
      ..moveTo(-5, 2)
      ..lineTo(5, 2)
      ..lineTo(8, 11)
      ..lineTo(-8, 11)
      ..close();
    canvas.drawRRect(bodyRect, Paint()..color = cameraColor);
    canvas.drawPath(lensBarrelPath, Paint()..color = cameraColor);
    canvas.restore();

    cameraPlacement.labelPainter.paint(canvas, cameraPlacement.labelTopLeftPx);
  }

  /// The projector as paintDownwardProjector draws it, pointing down, its lens exit at the optical centre where the
  /// light starts.
  void _paintProjector(Canvas canvas) {
    final _ProjectorPlacement? projectorPlacement = sideViewLayout.projectorPlacement;
    if (projectorPlacement == null) {
      return;
    }
    final Rect housingRect = projectorPlacement.housingRect;
    if (hoveredDeviceKey == projectorDeviceKey) {
      _paintHighlightRing(canvas, housingRect.center, housingRect.width / 2 + projectorHitMarginLogicalPx);
    }
    paintDownwardProjector(canvas, projectorPlacement.lensCenterPx, projectorDrawingScale);

    projectorPlacement.labelPainter.paint(canvas, projectorPlacement.labelTopLeftPx);
  }

  void _paintHighlightRing(Canvas canvas, Offset centerPx, double radiusPx) {
    final Color highlightColor = sideViewColors.highlightColor;
    canvas.drawCircle(centerPx, radiusPx, Paint()..color = highlightColor.withValues(alpha: 0.08));
    canvas.drawCircle(
      centerPx,
      radiusPx,
      Paint()
        ..color = highlightColor.withValues(alpha: 0.5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
  }

  void _strokePath(Canvas canvas, Path path, Color color, {required bool isDashed, double strokeWidthPx = 1.5}) {
    final Paint strokePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidthPx;
    if (!isDashed) {
      canvas.drawPath(path, strokePaint);
      return;
    }
    // Flutter has no dashed stroke: draw the path piece by piece along its length
    for (final ui.PathMetric pathMetric in path.computeMetrics()) {
      double dashStartPx = 0;
      while (dashStartPx < pathMetric.length) {
        final double dashEndPx = math.min(dashStartPx + dashLengthLogicalPx, pathMetric.length);
        canvas.drawPath(pathMetric.extractPath(dashStartPx, dashEndPx), strokePaint);
        dashStartPx = dashEndPx + dashGapLogicalPx;
      }
    }
  }

  @override
  bool shouldRepaint(_SetupSideViewPainter oldDelegate) {
    return oldDelegate.sideViewLayout != sideViewLayout ||
        oldDelegate.hoveredDeviceKey != hoveredDeviceKey ||
        oldDelegate.sideViewColors.cameraColor != sideViewColors.cameraColor;
  }
}
