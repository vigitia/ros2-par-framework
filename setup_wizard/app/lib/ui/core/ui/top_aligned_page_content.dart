// Written by Claude Code
//
// Content that stands alone on a page (a spinner while loading, an error with a retry button, a short note), placed
// at the page's top left with the page's padding, like every other page content, instead of in the middle.

import 'package:flutter/material.dart';

class TopAlignedPageContent extends StatelessWidget {
  const TopAlignedPageContent({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topLeft,
      child: Padding(padding: const EdgeInsets.all(24), child: child),
    );
  }
}
