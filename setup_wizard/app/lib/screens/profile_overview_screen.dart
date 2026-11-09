// Written by Claude Code
//
// Hub area "Overview" of a profile: the Run button, which starts and stops the profile, and the one app the profile
// starts on the projector. Still to come: a summary of the profile's calibration state. The cameras have their own
// area (cameras_screen.dart).

import 'package:flutter/material.dart';

import '../apps_api.dart';
import '../profile_run_view.dart';
import '../projector_app_choice_view.dart';
import '../setup_wizard_backend_client.dart';

class ProfileOverviewScreen extends StatefulWidget {
  const ProfileOverviewScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<ProfileOverviewScreen> createState() => _ProfileOverviewScreenState();
}

class _ProfileOverviewScreenState extends State<ProfileOverviewScreen> {
  bool _isLoadingProfile = true;
  String? _profileErrorText;
  ProfileSummary? _profileSummary;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() {
      _isLoadingProfile = true;
      _profileErrorText = null;
    });
    try {
      final ProfileList profileList = await widget.backendClient.fetchProfileList();
      ProfileSummary? foundProfileSummary;
      for (final ProfileSummary profileSummary in profileList.profileSummaries) {
        if (profileSummary.profileName == widget.profileName) {
          foundProfileSummary = profileSummary;
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _profileSummary = foundProfileSummary;
        if (foundProfileSummary == null) {
          _profileErrorText = 'This profile does not exist any more. Go back to the start screen.';
        } else {
          final String? summaryErrorText = foundProfileSummary.profileErrorText;
          if (summaryErrorText != null) {
            debugPrint('[ProfileOverviewScreen]: cannot read profile ${widget.profileName}: $summaryErrorText');
            _profileErrorText = 'This profile\'s file cannot be read. It may contain a mistake from editing it by hand.';
          } else {
            _profileErrorText = null;
          }
        }
        _isLoadingProfile = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _profileErrorText = describeBackendErrorForUser(error);
        _isLoadingProfile = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingProfile) {
      return const Center(child: CircularProgressIndicator());
    }
    final String? profileErrorText = _profileErrorText;
    final ProfileSummary? profileSummary = _profileSummary;
    if (profileErrorText != null || profileSummary == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Cannot show this profile: $profileErrorText', style: TextStyle(color: Theme.of(context).colorScheme.error)),
            TextButton(onPressed: _loadProfile, child: const Text('Retry')),
          ],
        ),
      );
    }

    // ProfileSummary.appNames holds par_launch.projector_app unless it is none
    final String storedProjectorAppName = profileSummary.appNames.firstOrNull ?? projectorAppNone;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ProfileRunView(backendClient: widget.backendClient, profileName: widget.profileName),
          const SizedBox(height: 24),
          ProjectorAppChoiceView(
            backendClient: widget.backendClient,
            profileName: widget.profileName,
            storedAppName: storedProjectorAppName,
          ),
        ],
      ),
    );
  }
}
