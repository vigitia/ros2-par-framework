// Written by Claude Code
//
// What every hub area of a profile does first: load the profile's summary, show a spinner meanwhile and, when it
// fails, the reason with a button to try again. A mixin, so each area keeps its own flow around the load (e.g. the
// Cameras area selects a requested camera once the profile is there).

import 'package:flutter/material.dart';

import 'top_aligned_page_content.dart';
import 'setup_wizard_backend_client.dart';

mixin ProfileSummaryLoading<T extends StatefulWidget> on State<T> {
  bool isLoadingProfile = true;

  /// Why the profile cannot be shown, written for the user; null while it can.
  String? profileErrorText;

  /// The last summary loaded; it stays while a reload is on its way.
  ProfileSummary? profileSummary;

  /// isSpinnerShown false reloads in the background, so what is shown stays while the answer is on its way.
  Future<void> loadProfileSummary(
    SetupWizardBackendClient backendClient,
    String profileName, {
    bool isSpinnerShown = true,
  }) async {
    if (isSpinnerShown) {
      setState(() {
        isLoadingProfile = true;
        profileErrorText = null;
      });
    }
    try {
      final ProfileSummary loadedProfileSummary = await backendClient.fetchProfileSummary(profileName);
      if (!mounted) {
        return;
      }
      setState(() {
        profileSummary = loadedProfileSummary;
        profileErrorText = null;
        isLoadingProfile = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        profileErrorText = describeBackendErrorForUser(error);
        isLoadingProfile = false;
      });
    }
  }

  /// The profile to show; null while loading or when loading failed (show buildProfileLoadStateView then).
  ProfileSummary? getShownProfileSummary() {
    if (isLoadingProfile || profileErrorText != null) {
      return null;
    }
    return profileSummary;
  }

  /// The spinner while loading, else the reason the profile cannot be shown and a retry button.
  Widget buildProfileLoadStateView({required VoidCallback onRetryClicked}) {
    if (isLoadingProfile) {
      return const TopAlignedPageContent(child: CircularProgressIndicator());
    }
    final String? shownErrorText = profileErrorText;
    return TopAlignedPageContent(
      child: Column(
        mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            shownErrorText ?? 'This profile cannot be shown.',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
            textAlign: TextAlign.start,
          ),
          TextButton(onPressed: onRetryClicked, child: const Text('Try again')),
        ],
      ),
    );
  }
}
