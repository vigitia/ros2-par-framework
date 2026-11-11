// Written by Claude Code
//
// The connected displays as cards (name, display id, real resolution, desktop scaling, refresh rate, position on the
// desktop, connector, serial; "–" where a display reports nothing); clicking one chooses it as the projector. A
// display the desktop scales gets a warning below the cards, since the projected image is then resampled. Shared by
// the new-profile wizard's Projector step and a profile's Projectors area.

import 'package:flutter/material.dart';

import 'displays_api.dart';
import 'setup_wizard_backend_client.dart';

const double displayCardWidthLogicalPx = 300;

/// Shown for a detail the display does not report, so every card keeps all rows.
const String unknownDetailText = '–';

class ProjectorDisplayChoiceView extends StatefulWidget {
  const ProjectorDisplayChoiceView({
    super.key,
    required this.backendClient,
    required this.chosenDisplayId,
    required this.onDisplayChosen,
  });

  final SetupWizardBackendClient backendClient;

  /// The display marked as the projector; null when none is chosen.
  final int? chosenDisplayId;

  /// Called with the display_id of the clicked card.
  final ValueChanged<int> onDisplayChosen;

  @override
  State<ProjectorDisplayChoiceView> createState() => _ProjectorDisplayChoiceViewState();
}

class _ProjectorDisplayChoiceViewState extends State<ProjectorDisplayChoiceView> {
  bool _isLoadingDisplays = true;
  String? _displaysErrorText;
  List<ConnectedDisplay> _connectedDisplays = [];

  @override
  void initState() {
    super.initState();
    _loadDisplays();
  }

  Future<void> _loadDisplays() async {
    setState(() {
      _isLoadingDisplays = true;
      _displaysErrorText = null;
    });
    try {
      final List<ConnectedDisplay> connectedDisplays = await widget.backendClient.fetchConnectedDisplays();
      if (!mounted) {
        return;
      }
      setState(() {
        _connectedDisplays = connectedDisplays;
        _isLoadingDisplays = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _displaysErrorText = describeBackendErrorForUser(error);
        _isLoadingDisplays = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    VoidCallback? onRefreshPressed;
    if (!_isLoadingDisplays) {
      onRefreshPressed = _loadDisplays;
    }
    final List<Widget> viewRows = [
      TextButton.icon(
        onPressed: onRefreshPressed,
        icon: const Icon(Icons.refresh),
        label: const Text('Refresh'),
      ),
      const SizedBox(height: 12),
    ];

    if (_isLoadingDisplays) {
      viewRows.add(const LinearProgressIndicator());
    } else if (_displaysErrorText != null) {
      viewRows.add(Text('Could not list the displays: $_displaysErrorText', style: TextStyle(color: colorScheme.error)));
    } else if (_connectedDisplays.isEmpty) {
      viewRows.add(const Text('No display found. Is the projector connected and switched on?'));
    } else {
      final List<Widget> displayCards = [];
      for (final ConnectedDisplay connectedDisplay in _connectedDisplays) {
        displayCards.add(_buildDisplayCard(connectedDisplay, colorScheme));
      }
      viewRows.add(Wrap(spacing: 16, runSpacing: 16, children: displayCards));
      for (final ConnectedDisplay connectedDisplay in _connectedDisplays) {
        if (connectedDisplay.isScaledByDesktop()) {
          viewRows.add(const SizedBox(height: 12));
          viewRows.add(_buildDesktopScalingWarning(connectedDisplay, colorScheme));
        }
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: viewRows);
  }

  Widget _buildDisplayCard(ConnectedDisplay connectedDisplay, ColorScheme colorScheme) {
    final bool isChosen = widget.chosenDisplayId == connectedDisplay.displayId;
    final BorderSide cardBorder;
    if (isChosen) {
      cardBorder = BorderSide(color: colorScheme.primary, width: 2);
    } else {
      cardBorder = BorderSide(color: colorScheme.outlineVariant);
    }

    // Every card has the same rows, each one line high except a desktop scaling warning, so cards differ in height
    // only for a scaled display
    String refreshRateText = unknownDetailText;
    final int? refreshRateHz = connectedDisplay.refreshRateHz;
    if (refreshRateHz != null) {
      refreshRateText = '$refreshRateHz Hz';
    }
    final List<Widget> detailRows = [
      _buildDetailRow('Display id', '${connectedDisplay.displayId}'),
      _buildDetailRow('Resolution', '${connectedDisplay.widthPx} × ${connectedDisplay.heightPx} px'),
      _buildDesktopScalingRow(connectedDisplay, colorScheme),
      _buildDetailRow('Refresh rate', refreshRateText),
      _buildDetailRow('Position', '${connectedDisplay.positionXPx}, ${connectedDisplay.positionYPx} px'),
      _buildDetailRow('Connector', _textOrUnknown(connectedDisplay.connectorName)),
      _buildDetailRow('Serial', _textOrUnknown(connectedDisplay.serialText)),
    ];

    final String titleText = connectedDisplay.getTitleText();
    final List<Widget> titleRowItems = [
      Expanded(
        child: Tooltip(
          message: titleText,
          child: Text(
            titleText,
            style: Theme.of(context).textTheme.titleMedium,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
    ];
    if (isChosen) {
      titleRowItems.add(Icon(Icons.check_circle, color: colorScheme.primary, semanticLabel: 'Projector'));
    }

    return SizedBox(
      width: displayCardWidthLogicalPx,
      child: Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: cardBorder),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => widget.onDisplayChosen(connectedDisplay.displayId),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: titleRowItems),
                const SizedBox(height: 8),
                ...detailRows,
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// The size apps draw at, marked as a problem when the desktop scales the display.
  Widget _buildDesktopScalingRow(ConnectedDisplay connectedDisplay, ColorScheme colorScheme) {
    if (!connectedDisplay.isScaledByDesktop()) {
      return _buildDetailRow('Desktop scale', 'None');
    }
    final String drawnSizeText = 'Apps draw ${connectedDisplay.sdlWidthPx} × ${connectedDisplay.sdlHeightPx} px';
    return _buildDetailRow('Desktop scale', drawnSizeText, detailTextColor: colorScheme.error, isWrapped: true);
  }

  Widget _buildDesktopScalingWarning(ConnectedDisplay connectedDisplay, ColorScheme colorScheme) {
    final String warningText =
        '${connectedDisplay.getTitleText()}: the desktop scales this display, so apps draw at '
        '${connectedDisplay.sdlWidthPx} × ${connectedDisplay.sdlHeightPx} px and the image is resampled to its real '
        '${connectedDisplay.widthPx} × ${connectedDisplay.heightPx} px. A projector should show every pixel as drawn, '
        'or projected markers and fine content get blurred. Set this display\'s scale to 100 % in the desktop\'s '
        'display settings, then press Refresh. If the warning stays, the desktop scales all displays alike (e.g. GNOME '
        'for older X11 apps): set the other displays to 100 % too.';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.warning_amber, color: colorScheme.error),
        const SizedBox(width: 8),
        Expanded(child: Text(warningText)),
      ],
    );
  }

  String _textOrUnknown(String detailText) {
    if (detailText.isEmpty) {
      return unknownDetailText;
    }
    return detailText;
  }

  /// One label and its text; the text stays on one line (cut off with '…') unless isWrapped.
  Widget _buildDetailRow(String detailLabel, String detailText, {Color? detailTextColor, bool isWrapped = false}) {
    int? detailMaxLines = 1;
    TextOverflow detailOverflow = TextOverflow.ellipsis;
    if (isWrapped) {
      detailMaxLines = null;
      detailOverflow = TextOverflow.clip;
    }
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color labelColor = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 100, child: Text(detailLabel, style: textTheme.bodySmall?.copyWith(color: labelColor))),
          Expanded(
            child: Text(
              detailText,
              style: textTheme.bodyMedium?.copyWith(color: detailTextColor),
              maxLines: detailMaxLines,
              overflow: detailOverflow,
            ),
          ),
        ],
      ),
    );
  }
}
