// Written by Claude Code
//
// Tabs for what a profile has (cameras, sensor nodes, apps), with an "Add …" button next to them: a menu that offers
// what can still be added, or the owner's own way of adding (onAddPressed). A tab's content is built the first time the tab is shown and then kept, so unsaved changes in
// it survive switching tabs, and opening the area does not load every tab at once. Without any tab, only the add
// button and a hint are shown.

import 'package:flutter/material.dart';

class AddableTabsView extends StatefulWidget {
  const AddableTabsView({
    super.key,
    required this.tabTitles,
    required this.buildTabContent,
    required this.addButtonText,
    required this.addMenuEntries,
    required this.noTabsText,
    this.shownTabTitle,
    this.onAddPressed,
    this.onShownTabChanged,
  });

  /// One per tab, unique; they also identify the tabs when the list changes.
  final List<String> tabTitles;

  /// Builds the tab's content; isShownTab is false while another tab is in front.
  final Widget Function(int tabIndex, bool isShownTab) buildTabContent;
  final String addButtonText;

  /// What the add menu offers; empty disables the button.
  final List<Widget> addMenuEntries;
  final String noTabsText;

  /// The tab to bring to the front when the tabs or this title change, e.g. one just added; null keeps the shown
  /// one.
  final String? shownTabTitle;

  /// Set: the add button calls this instead of opening the menu, e.g. to ask in a dialog what to add.
  final VoidCallback? onAddPressed;

  /// Called with the tab's index when the user brings another tab to the front.
  final ValueChanged<int>? onShownTabChanged;

  @override
  State<AddableTabsView> createState() => _AddableTabsViewState();
}

class _AddableTabsViewState extends State<AddableTabsView> with TickerProviderStateMixin {
  TabController? _tabController;

  /// Tabs shown at least once, whose content stays built.
  final Set<String> _visitedTabTitles = {};

  /// The tab in front as the owner knows it, so onShownTabChanged is called once per change and only for the user's.
  int _reportedTabIndex = 0;

  @override
  void initState() {
    super.initState();
    _createTabController(_getIndexOfTitle(widget.shownTabTitle) ?? 0);
  }

  @override
  void didUpdateWidget(AddableTabsView oldWidget) {
    super.didUpdateWidget(oldWidget);
    final bool haveTabsChanged = oldWidget.tabTitles.join('\n') != widget.tabTitles.join('\n');
    if (!haveTabsChanged) {
      final int? requestedTabIndex = _getIndexOfTitle(widget.shownTabTitle);
      final TabController? tabController = _tabController;
      final bool isOtherTabRequested = widget.shownTabTitle != oldWidget.shownTabTitle;
      if (isOtherTabRequested && requestedTabIndex != null && tabController != null) {
        // After this build: the tab bar rebuilds when the index changes
        WidgetsBinding.instance.addPostFrameCallback((Duration frameTimestamp) {
          if (!mounted || _tabController != tabController || requestedTabIndex >= tabController.length) {
            return;
          }
          // The owner asked for it, so it is not reported back
          _reportedTabIndex = requestedTabIndex;
          tabController.index = requestedTabIndex;
        });
      }
      return;
    }
    // Keep the tab that was in front, unless another one is asked for
    String? previousTabTitle;
    final TabController? previousTabController = _tabController;
    if (previousTabController != null && previousTabController.index < oldWidget.tabTitles.length) {
      previousTabTitle = oldWidget.tabTitles[previousTabController.index];
    }
    final int shownTabIndex = _getIndexOfTitle(widget.shownTabTitle) ?? _getIndexOfTitle(previousTabTitle) ?? 0;
    previousTabController?.dispose();
    _createTabController(shownTabIndex);
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }

  int? _getIndexOfTitle(String? tabTitle) {
    if (tabTitle == null) {
      return null;
    }
    final int tabIndex = widget.tabTitles.indexOf(tabTitle);
    if (tabIndex < 0) {
      return null;
    }
    return tabIndex;
  }

  void _createTabController(int shownTabIndex) {
    if (widget.tabTitles.isEmpty) {
      _tabController = null;
      return;
    }
    final TabController tabController = TabController(
      length: widget.tabTitles.length,
      initialIndex: shownTabIndex.clamp(0, widget.tabTitles.length - 1),
      vsync: this,
    );
    _reportedTabIndex = tabController.index;
    tabController.addListener(() {
      if (!mounted) {
        return;
      }
      setState(() {});
      if (tabController.index != _reportedTabIndex) {
        _reportedTabIndex = tabController.index;
        widget.onShownTabChanged?.call(tabController.index);
      }
    });
    _tabController = tabController;
  }

  Widget _buildAddButton() {
    final VoidCallback? onAddPressed = widget.onAddPressed;
    if (onAddPressed != null) {
      return OutlinedButton.icon(
        onPressed: onAddPressed,
        icon: const Icon(Icons.add),
        label: Text(widget.addButtonText),
      );
    }
    return MenuAnchor(
      menuChildren: widget.addMenuEntries,
      builder: (BuildContext context, MenuController menuController, Widget? child) {
        VoidCallback? onPressed;
        if (widget.addMenuEntries.isNotEmpty) {
          onPressed = () {
            if (menuController.isOpen) {
              menuController.close();
            } else {
              menuController.open();
            }
          };
        }
        return OutlinedButton.icon(
          onPressed: onPressed,
          icon: const Icon(Icons.add),
          label: Text(widget.addButtonText),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final TabController? tabController = _tabController;
    if (tabController == null) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildAddButton(),
            const SizedBox(height: 16),
            Text(widget.noTabsText, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
      );
    }

    final int shownTabIndex = tabController.index;
    _visitedTabTitles.add(widget.tabTitles[shownTabIndex]);
    final List<Widget> tabContents = [];
    for (int tabIndex = 0; tabIndex < widget.tabTitles.length; tabIndex++) {
      if (_visitedTabTitles.contains(widget.tabTitles[tabIndex])) {
        // Keyed by title, so a tab's content follows it when tabs before it come or go
        tabContents.add(KeyedSubtree(
          key: ValueKey<String>(widget.tabTitles[tabIndex]),
          child: widget.buildTabContent(tabIndex, tabIndex == shownTabIndex),
        ));
      } else {
        tabContents.add(const SizedBox.shrink());
      }
    }
    final List<Widget> tabs = [];
    for (final String tabTitle in widget.tabTitles) {
      tabs.add(Tab(text: tabTitle));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 8, 24, 0),
          child: Row(children: [
            Expanded(
              child: TabBar(
                controller: tabController,
                isScrollable: true,
                tabAlignment: TabAlignment.start,
                tabs: tabs,
              ),
            ),
            const SizedBox(width: 12),
            _buildAddButton(),
          ]),
        ),
        Expanded(child: IndexedStack(index: shownTabIndex, sizing: StackFit.expand, children: tabContents)),
      ],
    );
  }
}
