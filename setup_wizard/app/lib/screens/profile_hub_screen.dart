// Written by Claude Code
//
// Hub of an existing hardware setup (profile): a navigation rail with the overview (the profile's app), the
// profile's cameras with their calibrations, the profile's sensor processing nodes, the app store and the running apps. Each area lives in its own file and gets only the backend
// client and the profile name, so the areas can be built independently.

import 'package:flutter/material.dart';

import '../setup_wizard_backend_client.dart';
import 'app_store_screen.dart';
import 'cameras_screen.dart';
import 'profile_overview_screen.dart';
import 'running_apps_screen.dart';
import 'sensor_nodes_screen.dart';

class ProfileHubScreen extends StatefulWidget {
  const ProfileHubScreen({super.key, required this.backendClient, required this.profileName});

  final SetupWizardBackendClient backendClient;
  final String profileName;

  @override
  State<ProfileHubScreen> createState() => _ProfileHubScreenState();
}

class _ProfileHubScreenState extends State<ProfileHubScreen> {
  int _selectedAreaIndex = 0;

  Widget _buildSelectedArea() {
    switch (_selectedAreaIndex) {
      case 1:
        return CamerasScreen(backendClient: widget.backendClient, profileName: widget.profileName);
      case 2:
        return SensorNodesScreen(backendClient: widget.backendClient, profileName: widget.profileName);
      case 3:
        return AppStoreScreen(backendClient: widget.backendClient, profileName: widget.profileName);
      case 4:
        return RunningAppsScreen(backendClient: widget.backendClient, profileName: widget.profileName);
      default:
        return ProfileOverviewScreen(backendClient: widget.backendClient, profileName: widget.profileName);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Simplification: always a navigation rail, made for desktop windows. Upgrade for phones: a NavigationBar at
    // the bottom below a width threshold (card "Finish setup wizard UI", phone sketch).
    return Scaffold(
      appBar: AppBar(title: Text('ROS 2 PAR Framework: ${widget.profileName}')),
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: _selectedAreaIndex,
            labelType: NavigationRailLabelType.all,
            onDestinationSelected: (int areaIndex) {
              setState(() {
                _selectedAreaIndex = areaIndex;
              });
            },
            destinations: const [
              NavigationRailDestination(icon: Icon(Icons.dashboard_outlined), label: Text('Overview')),
              NavigationRailDestination(icon: Icon(Icons.videocam_outlined), label: Text('Cameras')),
              NavigationRailDestination(icon: Icon(Icons.sensors), label: Text('Sensor nodes')),
              NavigationRailDestination(icon: Icon(Icons.storefront_outlined), label: Text('Store')),
              NavigationRailDestination(icon: Icon(Icons.play_circle_outline), label: Text('Running')),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: _buildSelectedArea()),
        ],
      ),
    );
  }
}
