// Written by Claude Code
//
// The profile's setup seen from the front or from a side, simplified and flat like a drawing: the table, the
// projector with the light it throws onto the table, and each camera with its viewing direction and, where its
// intrinsics are known, its field of view. The front is where people read the projected image (its bottom edge), so
// left to right is the projected image's left to right (or the camera image's without a projector calibration, see
// SetupGeometry.frontViewReferenceText); the left and right views look from the projected image's left and right
// edges. Up is the height above the table. Metres are drawn to scale, the same in both directions, and the drawing
// grows in height with its width, so the setup fills the width. Only measured positions are drawn: a camera without a
// measured pose is left out (getDrawnCameras), and the caller says below the drawing what it still needs. Cameras and
// the projector have shapes of their own (a camera body with a lens barrel along its view; paintDownwardProjector's
// projector pointing down, its lens exit at the optical centre), a label with their name and, below it, their height
// above the table, and can be clicked to adjust that device. The caller fetches the data from the backend
// (SetupGeometryApi).

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'projector_drawing.dart';
import '../../data/services/setup_geometry_api.dart';
import '../../config/wizard_strings.dart';

/// The drawing's height follows its width (same scale both ways), within these limits: at least the minimum, and at
/// most this share of the window's height, so the steps below stay in reach.
const double setupDrawingMinimumHeightLogicalPx = 280;
const double setupDrawingMaximumWindowHeightRatio = 0.65;

/// Where the drawing looks from: the front (where people read the projected image) or its left or right edge.
enum SetupDrawingViewSide { left, front, right }

/// Room around the drawing for labels: above the highest device, beside the outermost ones, below for the legs.
const double setupDrawingLabelMarginTopLogicalPx = 72;
const double setupDrawingSideMarginLogicalPx = 90;
const double setupDrawingTableMarginBottomLogicalPx = 52;

/// A hovered device's field of view or projector light: fill opacity and outline width.
const double hoveredFrustumFillAlpha = 0.32;
const double hoveredFrustumOutlineWidthLogicalPx = 3;
const double setupDrawingTableThicknessLogicalPx = 8;
const double setupDrawingTableLegLengthLogicalPx = 24;

/// The table is drawn this much wider than what lies on it, as a fraction of that width.
const double setupDrawingTableOverhangRatio = 0.08;

/// Smallest width and height shown, so a single point or a flat setup still gets a sensible scale.
const double setupDrawingMinimumSpanM = 0.3;

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
  return 'camera:${camera.cameraName}';
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

class SetupDrawingView extends StatefulWidget {
  const SetupDrawingView({
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
  State<SetupDrawingView> createState() => _SetupDrawingViewState();
}

class _SetupDrawingViewState extends State<SetupDrawingView> {
  /// The device under the mouse pointer (a device key), null for none.
  String? _hoveredDeviceKey;

  SetupDrawingViewSide _viewSide = SetupDrawingViewSide.front;

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
    final _SetupDrawingColors setupDrawingColors = _SetupDrawingColors(
      cameraColor: colorScheme.primary,
      // The projector's lamp light (projector_drawing.dart), so projector and light look the same everywhere
      projectorColor: projectorLightColor,
      tableColor: colorScheme.outline,
      tableFillColor: colorScheme.surfaceContainerHighest,
      highlightColor: colorScheme.onSurface,
    );
    final TextStyle labelTextStyle = textTheme.labelMedium ?? const TextStyle(fontSize: 12);
    final double maximumDrawingHeightPx = math.max(
      MediaQuery.sizeOf(context).height * setupDrawingMaximumWindowHeightRatio,
      setupDrawingMinimumHeightLogicalPx,
    );
    final Widget drawing = LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final _SetupDrawingLayout setupDrawingLayout = _SetupDrawingLayout.create(
          widget.setupGeometry,
          _getScreenRightDirection(),
          constraints.maxWidth,
          maximumDrawingHeightPx,
          labelTextStyle,
          setupDrawingColors,
        );
        final Size drawingSize = Size(constraints.maxWidth, setupDrawingLayout.drawingHeightPx);
        MouseCursor mouseCursor = MouseCursor.defer;
        if (_hoveredDeviceKey != null) {
          mouseCursor = SystemMouseCursors.click;
        }
        return MouseRegion(
          cursor: mouseCursor,
          onHover: (PointerHoverEvent hoverEvent) =>
              _setHoveredDeviceKey(setupDrawingLayout.findDeviceKeyAt(hoverEvent.localPosition)),
          onExit: (PointerExitEvent exitEvent) => _setHoveredDeviceKey(null),
          child: GestureDetector(
            onTapUp: (TapUpDetails tapDetails) => _openDevice(setupDrawingLayout.findDeviceKeyAt(tapDetails.localPosition)),
            child: CustomPaint(
              size: drawingSize,
              painter: _SetupDrawingPainter(
                setupDrawingLayout: setupDrawingLayout,
                setupDrawingColors: setupDrawingColors,
                hoveredDeviceKey: _hoveredDeviceKey,
              ),
            ),
          ),
        );
      },
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [drawing, const SizedBox(height: 8), _buildViewSideButtons()],
    );
  }

  Widget _buildViewSideButtons() {
    return SegmentedButton<SetupDrawingViewSide>(
      segments: const [
        ButtonSegment<SetupDrawingViewSide>(
          value: SetupDrawingViewSide.left,
          label: Text(WizardStrings.leftSideViewLabel),
        ),
        ButtonSegment<SetupDrawingViewSide>(
          value: SetupDrawingViewSide.front,
          label: Text(WizardStrings.frontSideViewLabel),
        ),
        ButtonSegment<SetupDrawingViewSide>(
          value: SetupDrawingViewSide.right,
          label: Text(WizardStrings.rightSideViewLabel),
        ),
      ],
      selected: {_viewSide},
      onSelectionChanged: (Set<SetupDrawingViewSide> selectedViewSides) {
        setState(() {
          _viewSide = selectedViewSides.first;
          // The device under the pointer is somewhere else in the other view
          _hoveredDeviceKey = null;
        });
      },
    );
  }

  /// The table direction drawn left to right, a unit [x, y]. From the front it is SetupGeometry.frontViewRightDirection
  /// (right); its forward direction, away from the viewer at the front, is up × right. Looking from the left edge
  /// (along right), the viewer's right is backwards towards the front; looking from the right edge, it is forward.
  List<double> _getScreenRightDirection() {
    final List<double> frontRightDirection = widget.setupGeometry.frontViewRightDirection;
    final List<double> forwardDirection = [-frontRightDirection[1], frontRightDirection[0]];
    switch (_viewSide) {
      case SetupDrawingViewSide.front:
        return frontRightDirection;
      case SetupDrawingViewSide.left:
        return [-forwardDirection[0], -forwardDirection[1]];
      case SetupDrawingViewSide.right:
        return forwardDirection;
    }
  }
}

/// The drawing's colours, from the app's theme.
class _SetupDrawingColors {
  const _SetupDrawingColors({
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
class _SetupDrawingLayout {
  _SetupDrawingLayout._({
    required this.setupGeometry,
    required this.screenRightDirection,
    required this.drawingWidthPx,
    required this.drawingHeightPx,
    required this.scalePxPerM,
    required this.leftHorizontalM,
    required this.leftCanvasXPx,
    required this.tableTopCanvasYPx,
    required this.tableLeftM,
    required this.tableRightM,
  });

  final SetupGeometry setupGeometry;

  /// The table direction drawn left to right, a unit [x, y]: the chosen view's.
  final List<double> screenRightDirection;

  /// The drawing's height, from its width (see create).
  final double drawingWidthPx;
  final double drawingHeightPx;
  final double scalePxPerM;
  final double leftHorizontalM;
  final double leftCanvasXPx;
  final double tableTopCanvasYPx;
  final double tableLeftM;
  final double tableRightM;
  final List<_CameraPlacement> cameraPlacements = [];
  _ProjectorPlacement? projectorPlacement;

  /// The layout for a drawing drawingWidthPx wide, looking along screenRightDirection; with nothing measured yet, the
  /// bare table. Its height is what fills the width at the same scale both ways, within
  /// setupDrawingMinimumHeightLogicalPx and maximumDrawingHeightPx (beyond that, the setup gets narrower).
  static _SetupDrawingLayout create(
    SetupGeometry setupGeometry,
    List<double> screenRightDirection,
    double drawingWidthPx,
    double maximumDrawingHeightPx,
    TextStyle labelTextStyle,
    _SetupDrawingColors setupDrawingColors,
  ) {
    final List<double> tableHorizontalsM = _collectTableHorizontalsM(setupGeometry, screenRightDirection);
    final List<double> deviceHorizontalsM = [];
    double highestZM = 0;
    for (final CameraGeometry camera in getDrawnCameras(setupGeometry)) {
      deviceHorizontalsM.add(_getHorizontalM(screenRightDirection, camera.positionM));
      highestZM = math.max(highestZM, camera.positionM.zM);
    }
    final WorldPointM? projectorCenterM = setupGeometry.projector?.centerM;
    if (projectorCenterM != null) {
      deviceHorizontalsM.add(_getHorizontalM(screenRightDirection, projectorCenterM));
      highestZM = math.max(highestZM, projectorCenterM.zM);
    }
    final List<double> allHorizontalsM = [...tableHorizontalsM, ...deviceHorizontalsM];
    // Nothing measured yet: the bare table around the world origin, so the drawing shows where devices will appear
    if (allHorizontalsM.isEmpty) {
      allHorizontalsM.add(0.0);
    }

    // The table spans what lies on it (or below the devices when nothing does), with a little overhang
    List<double> tableSpanHorizontalsM = tableHorizontalsM;
    if (tableSpanHorizontalsM.isEmpty) {
      tableSpanHorizontalsM = allHorizontalsM;
    }
    final double spanLeftM = tableSpanHorizontalsM.reduce(math.min);
    final double spanRightM = tableSpanHorizontalsM.reduce(math.max);
    final double tableWidthM = math.max(spanRightM - spanLeftM, setupDrawingMinimumSpanM);
    final double tableCenterM = (spanLeftM + spanRightM) / 2;
    final double tableOverhangM = tableWidthM * setupDrawingTableOverhangRatio;
    final double tableLeftM = tableCenterM - tableWidthM / 2 - tableOverhangM;
    final double tableRightM = tableCenterM + tableWidthM / 2 + tableOverhangM;

    final double leftM = math.min(tableLeftM, allHorizontalsM.reduce(math.min));
    final double rightM = math.max(tableRightM, allHorizontalsM.reduce(math.max));
    final double heightM = math.max(highestZM, setupDrawingMinimumSpanM);
    final double drawableWidthPx = drawingWidthPx - 2 * setupDrawingSideMarginLogicalPx;
    final double verticalMarginsPx = setupDrawingLabelMarginTopLogicalPx + setupDrawingTableMarginBottomLogicalPx;
    final double widthFillingHeightPx = heightM * drawableWidthPx / (rightM - leftM) + verticalMarginsPx;
    final double drawingHeightPx = widthFillingHeightPx.clamp(
      setupDrawingMinimumHeightLogicalPx,
      math.max(maximumDrawingHeightPx, setupDrawingMinimumHeightLogicalPx),
    );
    final double tableTopCanvasYPx = drawingHeightPx - setupDrawingTableMarginBottomLogicalPx;
    final double drawableHeightPx = tableTopCanvasYPx - setupDrawingLabelMarginTopLogicalPx;
    // The same scale in both directions, so heights and widths compare as they are
    final double scalePxPerM = math.min(drawableWidthPx / (rightM - leftM), drawableHeightPx / heightM);
    final _SetupDrawingLayout setupDrawingLayout = _SetupDrawingLayout._(
      setupGeometry: setupGeometry,
      screenRightDirection: screenRightDirection,
      drawingWidthPx: drawingWidthPx,
      drawingHeightPx: drawingHeightPx,
      scalePxPerM: scalePxPerM,
      leftHorizontalM: leftM,
      leftCanvasXPx: (drawingWidthPx - (rightM - leftM) * scalePxPerM) / 2,
      tableTopCanvasYPx: tableTopCanvasYPx,
      tableLeftM: tableLeftM,
      tableRightM: tableRightM,
    );
    // The projector first, so camera labels make room for its label
    setupDrawingLayout._placeProjector(labelTextStyle, setupDrawingColors);
    setupDrawingLayout._placeCameras(labelTextStyle, setupDrawingColors);
    return setupDrawingLayout;
  }

  /// A device's height above the table, 'height 1.43 m', for the line below its name.
  static String _createHeightText(WorldPointM positionM) {
    final String heightText = positionM.zM.toStringAsFixed(2);
    return WizardStrings.getDrawingHeightText(heightText: heightText);
  }

  /// Left to right in the drawing, in metres along screenRightDirection.
  static double _getHorizontalM(List<double> screenRightDirection, WorldPointM pointM) {
    return pointM.xM * screenRightDirection[0] + pointM.yM * screenRightDirection[1];
  }

  /// The horizontal position of everything that lies on the table: projection area, fields of view, where the axes
  /// meet it.
  static List<double> _collectTableHorizontalsM(SetupGeometry setupGeometry, List<double> screenRightDirection) {
    final List<double> tableHorizontalsM = [];
    final ProjectorGeometry? projector = setupGeometry.projector;
    if (projector != null) {
      for (final WorldPointM cornerM in projector.projectionAreaM) {
        tableHorizontalsM.add(_getHorizontalM(screenRightDirection, cornerM));
      }
    }
    for (final CameraGeometry camera in getDrawnCameras(setupGeometry)) {
      for (final WorldPointM footprintPointM in camera.tableFootprintM ?? const <WorldPointM>[]) {
        tableHorizontalsM.add(_getHorizontalM(screenRightDirection, footprintPointM));
      }
      final WorldPointM? axisHitM = camera.opticalAxisTableHitM;
      if (axisHitM != null) {
        tableHorizontalsM.add(_getHorizontalM(screenRightDirection, axisHitM));
      }
    }
    return tableHorizontalsM;
  }

  /// A device's label: its name, and its position in the line below. textAlign centres the lines of a label that is
  /// itself centred on its device.
  static TextPainter _createLabelPainter(
    String labelText,
    TextStyle labelTextStyle,
    Color labelColor, {
    TextAlign textAlign = TextAlign.left,
  }) {
    final TextPainter labelPainter = TextPainter(
      text: TextSpan(
        text: labelText,
        style: labelTextStyle.copyWith(color: labelColor, fontWeight: FontWeight.w600),
      ),
      textAlign: textAlign,
      textDirection: TextDirection.ltr,
    );
    labelPainter.layout();
    return labelPainter;
  }

  double getHorizontalM(WorldPointM pointM) {
    return _getHorizontalM(screenRightDirection, pointM);
  }

  Offset toCanvas(double horizontalM, double zM) {
    return Offset(leftCanvasXPx + (horizontalM - leftHorizontalM) * scalePxPerM, tableTopCanvasYPx - zM * scalePxPerM);
  }

  Offset toCanvasFromWorld(WorldPointM pointM) {
    return toCanvas(getHorizontalM(pointM), pointM.zM);
  }

  void _placeCameras(TextStyle labelTextStyle, _SetupDrawingColors setupDrawingColors) {
    // What a camera label must not cover: the projector with its label and every camera icon. A label starts beside
    // its own icon, outside this square, so it never has to avoid that one
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
      final String labelText = '${camera.cameraName}\n${_createHeightText(camera.positionM)}';
      final TextPainter labelPainter = _createLabelPainter(labelText, labelTextStyle, setupDrawingColors.cameraColor);
      // Right of the icon, or left of it where the label would run off the drawing's right edge
      Offset wantedLabelTopLeftPx = positionPx + const Offset(22, -26);
      if (wantedLabelTopLeftPx.dx + labelPainter.width > drawingWidthPx) {
        wantedLabelTopLeftPx = positionPx + Offset(-22 - labelPainter.width, -26);
      }
      final Offset labelTopLeftPx = _findFreeLabelTopLeft(wantedLabelTopLeftPx, labelPainter.size, placedLabelRects);
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

  void _placeProjector(TextStyle labelTextStyle, _SetupDrawingColors setupDrawingColors) {
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
    final String labelText = WizardStrings.getProjectorDrawingLabel(heightText: _createHeightText(projectorCenterM));
    final TextPainter labelPainter = _createLabelPainter(
      labelText,
      labelTextStyle,
      setupDrawingColors.projectorColor,
      textAlign: TextAlign.center,
    );
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

class _SetupDrawingPainter extends CustomPainter {
  _SetupDrawingPainter({required this.setupDrawingLayout, required this.setupDrawingColors, required this.hoveredDeviceKey});

  final _SetupDrawingLayout setupDrawingLayout;
  final _SetupDrawingColors setupDrawingColors;

  /// The device to highlight, under the mouse pointer; null for none.
  final String? hoveredDeviceKey;

  @override
  void paint(Canvas canvas, Size size) {
    _paintProjectorLight(canvas);
    for (final _CameraPlacement cameraPlacement in setupDrawingLayout.cameraPlacements) {
      _paintCameraView(canvas, cameraPlacement);
    }
    _paintTable(canvas);
    _paintProjectionArea(canvas);
    for (final _CameraPlacement cameraPlacement in setupDrawingLayout.cameraPlacements) {
      _paintCamera(canvas, cameraPlacement);
    }
    _paintProjector(canvas);
  }

  void _paintProjectorLight(Canvas canvas) {
    final ProjectorGeometry? projector = setupDrawingLayout.setupGeometry.projector;
    if (projector == null || projector.projectionAreaM.isEmpty) {
      return;
    }
    final Color projectorColor = setupDrawingColors.projectorColor;
    final List<double> areaHorizontalsM = [];
    for (final WorldPointM cornerM in projector.projectionAreaM) {
      areaHorizontalsM.add(setupDrawingLayout.getHorizontalM(cornerM));
    }
    final Offset areaLeftPx = setupDrawingLayout.toCanvas(areaHorizontalsM.reduce(math.min), 0);
    final Offset areaRightPx = setupDrawingLayout.toCanvas(areaHorizontalsM.reduce(math.max), 0);
    final _ProjectorPlacement? projectorPlacement = setupDrawingLayout.projectorPlacement;
    // Position unknown: _paintProjectionArea shows the lit stretch of the table alone
    if (projectorPlacement == null) {
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
    // Stronger while the pointer is on the projector, so its light stands out from the camera views
    final bool isProjectorHovered = hoveredDeviceKey == projectorDeviceKey;
    double lightFillAlpha = 0.16;
    double lightOutlineWidthPx = 1.5;
    if (isProjectorHovered) {
      lightFillAlpha = hoveredFrustumFillAlpha;
      lightOutlineWidthPx = hoveredFrustumOutlineWidthLogicalPx;
    }
    canvas.drawPath(lightPath, Paint()..color = projectorColor.withValues(alpha: lightFillAlpha));
    canvas.drawPath(
      lightPath,
      Paint()
        ..color = projectorColor.withValues(alpha: 0.7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = lightOutlineWidthPx,
    );
  }

  /// The lit stretch of the table, on top of the table and the light, so the camera views never hide it.
  void _paintProjectionArea(Canvas canvas) {
    final ProjectorGeometry? projector = setupDrawingLayout.setupGeometry.projector;
    if (projector == null || projector.projectionAreaM.isEmpty) {
      return;
    }
    final Color projectorColor = setupDrawingColors.projectorColor;
    final List<double> areaHorizontalsM = [];
    for (final WorldPointM cornerM in projector.projectionAreaM) {
      areaHorizontalsM.add(setupDrawingLayout.getHorizontalM(cornerM));
    }
    final Offset areaLeftPx = setupDrawingLayout.toCanvas(areaHorizontalsM.reduce(math.min), 0);
    final Offset areaRightPx = setupDrawingLayout.toCanvas(areaHorizontalsM.reduce(math.max), 0);
    final Paint areaPaint = Paint()
      ..color = projectorColor
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.butt;
    canvas.drawLine(areaLeftPx, areaRightPx, areaPaint);
    final TextPainter areaLabelPainter = TextPainter(
      text: TextSpan(
        text: _createProjectionAreaLabelText(projector.projectionAreaM),
        style: TextStyle(color: projectorColor, fontSize: 12),
      ),
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
    );
    areaLabelPainter.layout();
    final double areaCenterXPx = (areaLeftPx.dx + areaRightPx.dx) / 2;
    // Below the table top, where neither the light nor the camera views are drawn
    final double labelTopYPx = areaLeftPx.dy + setupDrawingTableThicknessLogicalPx + 4;
    areaLabelPainter.paint(canvas, Offset(areaCenterXPx - areaLabelPainter.width / 2, labelTopYPx));
  }

  /// 'projected area' and below it '1.23 × 0.69 m': the image's width and height on the table, each the mean of its two opposite
  /// edges, since perspective makes them differ a little. Corners clockwise from the image's top left.
  static String _createProjectionAreaLabelText(List<WorldPointM> projectionAreaM) {
    if (projectionAreaM.length != 4) {
      return WizardStrings.projectedAreaLabel;
    }
    final WorldPointM topLeftM = projectionAreaM[0];
    final WorldPointM topRightM = projectionAreaM[1];
    final WorldPointM bottomRightM = projectionAreaM[2];
    final WorldPointM bottomLeftM = projectionAreaM[3];
    final double widthM = (_getTableDistanceM(topLeftM, topRightM) + _getTableDistanceM(bottomLeftM, bottomRightM)) / 2;
    final double heightM = (_getTableDistanceM(topLeftM, bottomLeftM) + _getTableDistanceM(topRightM, bottomRightM)) / 2;
    return WizardStrings.getProjectedAreaSizeLabel(widthM: widthM, heightM: heightM);
  }

  static double _getTableDistanceM(WorldPointM firstPointM, WorldPointM secondPointM) {
    final double deltaXM = secondPointM.xM - firstPointM.xM;
    final double deltaYM = secondPointM.yM - firstPointM.yM;
    return math.sqrt(deltaXM * deltaXM + deltaYM * deltaYM);
  }

  void _paintCameraView(Canvas canvas, _CameraPlacement cameraPlacement) {
    final CameraGeometry camera = cameraPlacement.camera;
    final Color cameraColor = setupDrawingColors.cameraColor;
    final Offset cameraPx = cameraPlacement.positionPx;
    final List<WorldPointM>? footprintM = camera.tableFootprintM;
    if (footprintM != null && footprintM.isNotEmpty) {
      final List<double> footprintHorizontalsM = [];
      for (final WorldPointM footprintPointM in footprintM) {
        footprintHorizontalsM.add(setupDrawingLayout.getHorizontalM(footprintPointM));
      }
      final Offset viewLeftPx = setupDrawingLayout.toCanvas(footprintHorizontalsM.reduce(math.min), 0);
      final Offset viewRightPx = setupDrawingLayout.toCanvas(footprintHorizontalsM.reduce(math.max), 0);
      final Path viewPath = Path()
        ..moveTo(cameraPx.dx, cameraPx.dy)
        ..lineTo(viewLeftPx.dx, viewLeftPx.dy)
        ..lineTo(viewRightPx.dx, viewRightPx.dy)
        ..close();
      // Stronger while the pointer is on this camera, so its view stands out where several overlap
      final bool isCameraHovered = hoveredDeviceKey == _createCameraDeviceKey(camera);
      double viewFillAlpha = 0.10;
      double viewOutlineWidthPx = 1.5;
      if (isCameraHovered) {
        viewFillAlpha = hoveredFrustumFillAlpha;
        viewOutlineWidthPx = hoveredFrustumOutlineWidthLogicalPx;
      }
      canvas.drawPath(viewPath, Paint()..color = cameraColor.withValues(alpha: viewFillAlpha));
      _strokePath(canvas, viewPath, cameraColor, isDashed: false, strokeWidthPx: viewOutlineWidthPx);
    }
    final WorldPointM? axisHitM = camera.opticalAxisTableHitM;
    if (axisHitM != null) {
      final Offset axisHitPx = setupDrawingLayout.toCanvas(setupDrawingLayout.getHorizontalM(axisHitM), 0);
      final Path axisPath = Path()
        ..moveTo(cameraPx.dx, cameraPx.dy)
        ..lineTo(axisHitPx.dx, axisHitPx.dy);
      _strokePath(canvas, axisPath, cameraColor.withValues(alpha: 0.8), isDashed: true, strokeWidthPx: 1);
    }
  }

  void _paintTable(Canvas canvas) {
    final Offset tableLeftPx = setupDrawingLayout.toCanvas(setupDrawingLayout.tableLeftM, 0);
    final Offset tableRightPx = setupDrawingLayout.toCanvas(setupDrawingLayout.tableRightM, 0);
    final Rect tableTopRect = Rect.fromLTRB(
      tableLeftPx.dx,
      tableLeftPx.dy,
      tableRightPx.dx,
      tableLeftPx.dy + setupDrawingTableThicknessLogicalPx,
    );
    canvas.drawRect(tableTopRect, Paint()..color = setupDrawingColors.tableFillColor);
    final Paint tablePaint = Paint()
      ..color = setupDrawingColors.tableColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawRect(tableTopRect, tablePaint);
    const double legInsetPx = 12;
    final double legTopYPx = tableTopRect.bottom;
    final double legBottomYPx = legTopYPx + setupDrawingTableLegLengthLogicalPx;
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
    final Color cameraColor = setupDrawingColors.cameraColor;
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
    final _ProjectorPlacement? projectorPlacement = setupDrawingLayout.projectorPlacement;
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
    final Color highlightColor = setupDrawingColors.highlightColor;
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
  bool shouldRepaint(_SetupDrawingPainter oldDelegate) {
    return oldDelegate.setupDrawingLayout != setupDrawingLayout ||
        oldDelegate.hoveredDeviceKey != hoveredDeviceKey ||
        oldDelegate.setupDrawingColors.cameraColor != setupDrawingColors.cameraColor;
  }
}
