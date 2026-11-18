// Written by Claude Code
//
// The hardware setup (profile) chooser: a menu button (hamburger icon) in the top right corner of the app bar, whose
// menu switches to another profile, creates a new one, copies or deletes the shown profile. It only reports the
// choice; the hub (profile_hub_screen.dart) remembers it, asks for the new profile's or the copy's name and asks
// before deleting.

import 'package:flutter/material.dart';
import '../../config/wizard_strings.dart';
import '../../config/wizard_icons.dart';

/// Space between the menu button and the window's edge (the hub's app bar keeps it), and between the button and the
/// opened menu. The menu itself keeps PopupMenuButton's own distance from the window's edges.
const double profileMenuOuterMarginLogicalPx = 8;

class ProfileSelectorView extends StatelessWidget {
  const ProfileSelectorView({
    super.key,
    required this.profileNames,
    required this.shownProfileName,
    required this.onProfileSelected,
    required this.onNewProfileClicked,
    required this.onCopyProfileClicked,
    required this.onDeleteProfileClicked,
  });

  final List<String> profileNames;

  /// Null when there is no profile at all.
  final String? shownProfileName;
  final ValueChanged<String> onProfileSelected;
  final VoidCallback onNewProfileClicked;
  final ValueChanged<String> onCopyProfileClicked;
  final ValueChanged<String> onDeleteProfileClicked;

  /// A menu entry with its icon; choosing it runs onChosen once the menu has closed, so a dialog it opens is not
  /// closed with the menu.
  PopupMenuItem<VoidCallback> _buildMenuEntry({
    required Widget leadingIcon,
    required VoidCallback onChosen,
    required Widget child,
  }) {
    return PopupMenuItem<VoidCallback>(
      value: onChosen,
      child: Row(
        children: [
          leadingIcon,
          const SizedBox(width: 12),
          Flexible(child: child),
        ],
      ),
    );
  }

  List<PopupMenuEntry<VoidCallback>> _buildMenuEntries(BuildContext context) {
    final List<PopupMenuEntry<VoidCallback>> menuEntries = [];
    for (final String profileName in profileNames) {
      // An empty box instead of the check keeps every name at the same indent
      Widget leadingIcon = const SizedBox(width: 24);
      if (profileName == shownProfileName) {
        leadingIcon = const Icon(WizardIcons.chosenMenuEntryIcon);
      }
      menuEntries.add(_buildMenuEntry(
        leadingIcon: leadingIcon,
        onChosen: () => onProfileSelected(profileName),
        child: Text(profileName),
      ));
    }
    if (menuEntries.isNotEmpty) {
      menuEntries.add(const PopupMenuDivider());
    }
    menuEntries.add(_buildMenuEntry(
      leadingIcon: const Icon(WizardIcons.addButtonIcon),
      onChosen: onNewProfileClicked,
      child: const Text(WizardStrings.newProfileMenuLabel),
    ));
    final String? copyableProfileName = shownProfileName;
    if (copyableProfileName != null) {
      menuEntries.add(_buildMenuEntry(
        leadingIcon: const Icon(WizardIcons.copyProfileMenuIcon),
        onChosen: () => onCopyProfileClicked(copyableProfileName),
        child: Text(WizardStrings.getCopyProfileMenuLabel(copyableProfileName: copyableProfileName)),
      ));
    }
    final String? deletableProfileName = shownProfileName;
    if (deletableProfileName != null) {
      final Color deleteColor = Theme.of(context).colorScheme.error;
      menuEntries.add(_buildMenuEntry(
        leadingIcon: Icon(WizardIcons.deleteProfileMenuIcon, color: deleteColor),
        onChosen: () => onDeleteProfileClicked(deletableProfileName),
        child: Text(
          WizardStrings.getDeleteProfileMenuLabel(deletableProfileName: deletableProfileName),
          style: TextStyle(color: deleteColor),
        ),
      ));
    }
    return menuEntries;
  }

  @override
  Widget build(BuildContext context) {
    // PopupMenuButton instead of MenuAnchor: MenuAnchor puts a menu that would leave the window flush against its edge
    return PopupMenuButton<VoidCallback>(
      tooltip: WizardStrings.profilesMenuTooltip,
      icon: const Icon(WizardIcons.profileMenuButtonIcon),
      position: PopupMenuPosition.under,
      offset: const Offset(0, profileMenuOuterMarginLogicalPx),
      itemBuilder: _buildMenuEntries,
      onSelected: (VoidCallback onChosen) => onChosen(),
    );
  }
}
