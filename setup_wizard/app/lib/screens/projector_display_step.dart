// Written by Claude Code
//
// New-profile step "Projector": the connected displays as cards (name, display id, connector, resolution, refresh
// rate, position on the desktop, serial); clicking one makes it the projector. One projector for now; the draft
// holds a list for setups with several. Next stays disabled until a display is chosen, because the calibration
// steps that follow project onto it.

import 'package:flutter/material.dart';

import '../displays_api.dart';
import '../setup_wizard_backend_client.dart';
import 'new_profile_wizard_screen.dart';

const double displayCardWidthLogicalPx = 300;

class ProjectorDisplayStep extends StatefulWidget {
  const ProjectorDisplayStep({
    super.key,
    required this.backendClient,
    required this.newProfileDraft,
    required this.onCanContinueChanged,
  });

  final SetupWizardBackendClient backendClient;

  /// Receives the chosen display in projectorDisplayIds.
  final NewProfileDraft newProfileDraft;

  /// Tells the wizard whether Next is allowed: only with a display chosen.
  final ValueChanged<bool> onCanContinueChanged;

  @override
  State<ProjectorDisplayStep> createState() => _ProjectorDisplayStepState();
}

class _ProjectorDisplayStepState extends State<ProjectorDisplayStep> {
  bool _isLoadingDisplays = true;
  String? _displaysErrorText;
  List<ConnectedDisplay> _connectedDisplays = [];

  @override
  void initState() {
    super.initState();
    // Not during build: the wizard rebuilds itself when told.
    WidgetsBinding.instance.addPostFrameCallback((Duration timeStamp) => _reportCanContinue());
    _loadDisplays();
  }

  void _reportCanContinue() {
    widget.onCanContinueChanged(widget.newProfileDraft.projectorDisplayIds.isNotEmpty);
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

  /// Simplification: one projector per profile for now, so choosing a display replaces the earlier choice.
  /// Upgrade for several projectors: toggle the display in projectorDisplayIds instead.
  void _chooseProjectorDisplay(int displayId) {
    setState(() {
      widget.newProfileDraft.projectorDisplayIds = [displayId];
    });
    _reportCanContinue();
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> stepRows = [
      Row(
        children: [
          const Expanded(child: Text('Which display is the projector? Click its card.')),
          TextButton.icon(
            onPressed: _isLoadingDisplays ? null : _loadDisplays,
            icon: const Icon(Icons.refresh),
            label: const Text('Search again'),
          ),
        ],
      ),
      const SizedBox(height: 12),
    ];

    if (_isLoadingDisplays) {
      stepRows.add(const LinearProgressIndicator());
    } else if (_displaysErrorText != null) {
      stepRows.add(Text('Could not list the displays: $_displaysErrorText', style: TextStyle(color: colorScheme.error)));
    } else if (_connectedDisplays.isEmpty) {
      stepRows.add(const Text('No display found. Is the projector connected and switched on?'));
    } else {
      final List<Widget> displayCards = [];
      for (final ConnectedDisplay connectedDisplay in _connectedDisplays) {
        displayCards.add(_buildDisplayCard(connectedDisplay, colorScheme));
      }
      stepRows.add(Wrap(spacing: 16, runSpacing: 16, children: displayCards));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: stepRows);
  }

  Widget _buildDisplayCard(ConnectedDisplay connectedDisplay, ColorScheme colorScheme) {
    final bool isChosen = widget.newProfileDraft.projectorDisplayIds.contains(connectedDisplay.displayId);
    final BorderSide cardBorder;
    if (isChosen) {
      cardBorder = BorderSide(color: colorScheme.primary, width: 2);
    } else {
      cardBorder = BorderSide(color: colorScheme.outlineVariant);
    }

    String refreshRateText = 'unknown';
    final int? refreshRateHz = connectedDisplay.refreshRateHz;
    if (refreshRateHz != null) {
      refreshRateText = '$refreshRateHz Hz';
    }
    final List<Widget> detailRows = [
      _buildDetailRow('Display id', '${connectedDisplay.displayId}'),
      _buildDetailRow('Resolution', '${connectedDisplay.widthPx} × ${connectedDisplay.heightPx} px'),
      _buildDetailRow('Refresh rate', refreshRateText),
      _buildDetailRow('Position', '${connectedDisplay.positionXPx}, ${connectedDisplay.positionYPx} px'),
    ];
    if (connectedDisplay.connectorName.isNotEmpty) {
      detailRows.add(_buildDetailRow('Connector', connectedDisplay.connectorName));
    }
    if (connectedDisplay.serialText.isNotEmpty) {
      detailRows.add(_buildDetailRow('Serial', connectedDisplay.serialText));
    }

    final List<Widget> titleRowItems = [
      Expanded(child: Text(connectedDisplay.getTitleText(), style: Theme.of(context).textTheme.titleMedium)),
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
          onTap: () => _chooseProjectorDisplay(connectedDisplay.displayId),
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

  Widget _buildDetailRow(String detailLabel, String detailText) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        children: [
          SizedBox(
            width: 100,
            child: Text(detailLabel, style: textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ),
          Expanded(child: Text(detailText, style: textTheme.bodyMedium)),
        ],
      ),
    );
  }
}
