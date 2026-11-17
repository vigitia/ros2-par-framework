// Written by Claude Code
//
// The hardware setup (profile) chooser: a menu button (hamburger icon) in the top right corner of the app bar, whose
// menu switches to another profile, starts the new-profile wizard, copies or deletes the shown profile. It only
// reports the choice; the hub (profile_hub_screen.dart) remembers it, runs the wizard, asks for the copy's name and
// asks before deleting.

import 'package:flutter/material.dart';
import '../../config/wizard_strings.dart';

/// Space between the menu and the window's edge, and around the entries inside it.
const double profileMenuOuterMarginLogicalPx = 8;
const double profileMenuInnerPaddingLogicalPx = 8;
const double profileMenuEntryHorizontalPaddingLogicalPx = 16;

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

  /// A menu entry with side padding, so its icon and text are not flush with the menu's edge.
  Widget _buildMenuEntry({required Widget leadingIcon, required VoidCallback onPressed, required Widget child}) {
    return MenuItemButton(
      leadingIcon: leadingIcon,
      onPressed: onPressed,
      style: MenuItemButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: profileMenuEntryHorizontalPaddingLogicalPx),
      ),
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> menuEntries = [];
    for (final String profileName in profileNames) {
      // An empty box instead of the check keeps every name at the same indent
      Widget leadingIcon = const SizedBox(width: 24);
      if (profileName == shownProfileName) {
        leadingIcon = const Icon(Icons.check);
      }
      menuEntries.add(_buildMenuEntry(
        leadingIcon: leadingIcon,
        onPressed: () => onProfileSelected(profileName),
        child: Text(profileName),
      ));
    }
    if (menuEntries.isNotEmpty) {
      menuEntries.add(const Divider(height: profileMenuInnerPaddingLogicalPx * 2));
    }
    menuEntries.add(_buildMenuEntry(
      leadingIcon: const Icon(Icons.add),
      onPressed: onNewProfileClicked,
      child: const Text(WizardStrings.newProfileMenuLabel),
    ));
    final String? copyableProfileName = shownProfileName;
    if (copyableProfileName != null) {
      menuEntries.add(_buildMenuEntry(
        leadingIcon: const Icon(Icons.copy),
        onPressed: () => onCopyProfileClicked(copyableProfileName),
        child: Text(WizardStrings.getCopyProfileMenuLabel(copyableProfileName: copyableProfileName)),
      ));
    }
    final String? deletableProfileName = shownProfileName;
    if (deletableProfileName != null) {
      final Color deleteColor = Theme.of(context).colorScheme.error;
      menuEntries.add(
        _buildMenuEntry(
          leadingIcon: Icon(Icons.delete_outline, color: deleteColor),
          onPressed: () => onDeleteProfileClicked(deletableProfileName),
          child: Text(
            WizardStrings.getDeleteProfileMenuLabel(deletableProfileName: deletableProfileName),
            style: TextStyle(color: deleteColor),
          ),
        ),
      );
    }

    return MenuAnchor(
      menuChildren: menuEntries,
      // Below the button and off the window's right edge (the menu is moved left to fit the window)
      alignmentOffset: const Offset(-profileMenuOuterMarginLogicalPx, profileMenuOuterMarginLogicalPx),
      style: const MenuStyle(
        padding: WidgetStatePropertyAll(EdgeInsets.symmetric(vertical: profileMenuInnerPaddingLogicalPx)),
      ),
      builder: (BuildContext context, MenuController menuController, Widget? child) {
        return IconButton(
          tooltip: WizardStrings.profilesMenuTooltip,
          onPressed: () {
            if (menuController.isOpen) {
              menuController.close();
            } else {
              menuController.open();
            }
          },
          icon: const Icon(Icons.menu),
        );
      },
    );
  }
}
