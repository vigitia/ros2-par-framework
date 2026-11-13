// Written by Claude Code
//
// The hardware setup (profile) chooser: a menu button (hamburger icon) in the top right corner of the app bar, whose
// menu switches to another profile, starts the new-profile wizard or deletes the shown profile. It only reports the
// choice; the hub (profile_hub_screen.dart) remembers it, runs the wizard and asks before deleting.

import 'package:flutter/material.dart';
import '../../config/wizard_strings.dart';

class ProfileSelectorView extends StatelessWidget {
  const ProfileSelectorView({
    super.key,
    required this.profileNames,
    required this.shownProfileName,
    required this.onProfileSelected,
    required this.onNewProfileClicked,
    required this.onDeleteProfileClicked,
  });

  final List<String> profileNames;

  /// Null when there is no profile at all.
  final String? shownProfileName;
  final ValueChanged<String> onProfileSelected;
  final VoidCallback onNewProfileClicked;
  final ValueChanged<String> onDeleteProfileClicked;

  @override
  Widget build(BuildContext context) {
    final List<Widget> menuEntries = [];
    for (final String profileName in profileNames) {
      // An empty box instead of the check keeps every name at the same indent
      Widget leadingIcon = const SizedBox(width: 24);
      if (profileName == shownProfileName) {
        leadingIcon = const Icon(Icons.check);
      }
      menuEntries.add(MenuItemButton(
        leadingIcon: leadingIcon,
        onPressed: () => onProfileSelected(profileName),
        child: Text(profileName),
      ));
    }
    if (menuEntries.isNotEmpty) {
      menuEntries.add(const Divider(height: 1));
    }
    menuEntries.add(MenuItemButton(
      leadingIcon: const Icon(Icons.add),
      onPressed: onNewProfileClicked,
      child: const Text(WizardStrings.newProfileMenuLabel),
    ));
    final String? deletableProfileName = shownProfileName;
    if (deletableProfileName != null) {
      final Color deleteColor = Theme.of(context).colorScheme.error;
      menuEntries.add(
        MenuItemButton(
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
