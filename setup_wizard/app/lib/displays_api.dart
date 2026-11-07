// Written by Claude Code
//
// The app's call to the backend's display list (setup_wizard/backend/displays_api.py): the connected displays with
// the ids the framework uses, to pick the projector from.

import 'setup_wizard_backend_client.dart';

extension DisplaysApi on SetupWizardBackendClient {
  /// Fetches the connected displays in the framework's display_id order.
  Future<List<ConnectedDisplay>> fetchConnectedDisplays() async {
    final Map<String, dynamic> displaysJson = await getJson('/api/displays') as Map<String, dynamic>;
    final List<ConnectedDisplay> connectedDisplays = [];
    for (final dynamic displayJson in displaysJson['displays'] as List<dynamic>) {
      connectedDisplays.add(ConnectedDisplay.fromJson(displayJson as Map<String, dynamic>));
    }
    return connectedDisplays;
  }
}

/// One connected display (projector or monitor) as SDL and its EDID describe it.
class ConnectedDisplay {
  const ConnectedDisplay({
    required this.displayId,
    required this.sdlDisplayName,
    required this.connectorName,
    required this.manufacturerId,
    required this.modelName,
    required this.serialText,
    required this.widthPx,
    required this.heightPx,
    required this.refreshRateHz,
    required this.positionXPx,
    required this.positionYPx,
  });

  factory ConnectedDisplay.fromJson(Map<String, dynamic> displayJson) {
    return ConnectedDisplay(
      displayId: displayJson['display_id'] as int,
      sdlDisplayName: displayJson['sdl_display_name'] as String,
      connectorName: displayJson['connector_name'] as String,
      manufacturerId: displayJson['manufacturer_id'] as String,
      modelName: displayJson['model_name'] as String,
      serialText: displayJson['serial_text'] as String,
      widthPx: displayJson['width_px'] as int,
      heightPx: displayJson['height_px'] as int,
      refreshRateHz: displayJson['refresh_rate_hz'] as int?,
      positionXPx: displayJson['position_x_px'] as int,
      positionYPx: displayJson['position_y_px'] as int,
    );
  }

  /// The framework's display_id (par_setup.yaml, --display-id of the rendering manager).
  final int displayId;

  /// SDL's name, usually the connector plus the size, e.g. 'eDP-1 15"'.
  final String sdlDisplayName;

  /// e.g. 'HDMI-A-1'; empty when unknown.
  final String connectorName;

  /// From the display's EDID, e.g. 'EPS' for Epson; empty when it reports none.
  final String manufacturerId;
  final String modelName;
  final String serialText;

  final int widthPx;
  final int heightPx;

  /// null when the driver does not report it.
  final int? refreshRateHz;

  /// Top left corner on the desktop.
  final int positionXPx;
  final int positionYPx;

  /// The model when the display reports one, e.g. 'EPS EB-680', otherwise SDL's name.
  String getTitleText() {
    final List<String> titleParts = [];
    if (manufacturerId.isNotEmpty) {
      titleParts.add(manufacturerId);
    }
    if (modelName.isNotEmpty) {
      titleParts.add(modelName);
    }
    if (modelName.isEmpty) {
      titleParts.add(sdlDisplayName);
    }
    return titleParts.join(' ');
  }
}
