// Written by Claude Code
//
// The connected displays as cards of one size (name, display id, resolution, refresh rate, position on the desktop,
// connector, serial; "–" where a display reports nothing); clicking one chooses it as the projector. Shared by the
// new-profile wizard's Projector step and a profile's Projectors area.

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
    VoidCallback? onSearchAgainPressed;
    if (!_isLoadingDisplays) {
      onSearchAgainPressed = _loadDisplays;
    }
    final List<Widget> viewRows = [
      TextButton.icon(
        onPressed: onSearchAgainPressed,
        icon: const Icon(Icons.refresh),
        label: const Text('Search again'),
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

    // Every card has the same rows, each one line high, so all cards have the same size
    String refreshRateText = unknownDetailText;
    final int? refreshRateHz = connectedDisplay.refreshRateHz;
    if (refreshRateHz != null) {
      refreshRateText = '$refreshRateHz Hz';
    }
    final List<Widget> detailRows = [
      _buildDetailRow('Display id', '${connectedDisplay.displayId}'),
      _buildDetailRow('Resolution', '${connectedDisplay.widthPx} × ${connectedDisplay.heightPx} px'),
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

  String _textOrUnknown(String detailText) {
    if (detailText.isEmpty) {
      return unknownDetailText;
    }
    return detailText;
  }

  Widget _buildDetailRow(String detailLabel, String detailText) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color labelColor = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        children: [
          SizedBox(width: 100, child: Text(detailLabel, style: textTheme.bodySmall?.copyWith(color: labelColor))),
          Expanded(child: Text(detailText, style: textTheme.bodyMedium, maxLines: 1, overflow: TextOverflow.ellipsis)),
        ],
      ),
    );
  }
}
