// Written by Claude Code
//
// Entry point of the PAR setup wizard. For now it only shows whether the backend is reachable; the start screen
// with the profile dropdown comes next.

import 'package:flutter/material.dart';

import 'setup_wizard_backend_client.dart';

void main() {
  runApp(const SetupWizardApp());
}

class SetupWizardApp extends StatelessWidget {
  const SetupWizardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PAR setup wizard',
      home: SetupWizardStartScreen(backendClient: SetupWizardBackendClient()),
    );
  }
}

class SetupWizardStartScreen extends StatefulWidget {
  const SetupWizardStartScreen({super.key, required this.backendClient});

  final SetupWizardBackendClient backendClient;

  @override
  State<SetupWizardStartScreen> createState() => _SetupWizardStartScreenState();
}

class _SetupWizardStartScreenState extends State<SetupWizardStartScreen> {
  late Future<SetupWizardBackendStatus> _backendStatusFuture;

  @override
  void initState() {
    super.initState();
    _backendStatusFuture = widget.backendClient.fetchBackendStatus();
  }

  void _retryBackendConnection() {
    setState(() {
      _backendStatusFuture = widget.backendClient.fetchBackendStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: const Center(child: Text('PAR setup wizard')),
      // At the bottom, so it is always clear which machine the UI controls (matters once phones connect too).
      bottomNavigationBar: FutureBuilder<SetupWizardBackendStatus>(
        future: _backendStatusFuture,
        builder: _buildBackendConnectionBar,
      ),
    );
  }

  Widget _buildBackendConnectionBar(BuildContext context, AsyncSnapshot<SetupWizardBackendStatus> snapshot) {
    final Widget connectionText;
    Widget? retryButton;
    if (snapshot.connectionState != ConnectionState.done) {
      connectionText = Text('Connecting to ${widget.backendClient.backendBaseUrl} …');
    } else if (snapshot.hasError) {
      connectionText = Text(
        'Backend not reachable at ${widget.backendClient.backendBaseUrl}. Start it with: '
        '.venv/bin/python setup_wizard/backend/setup_wizard_backend.py',
      );
      retryButton = TextButton(onPressed: _retryBackendConnection, child: const Text('Retry'));
    } else {
      connectionText = Text('Connected to ${snapshot.data!.machineName} (${widget.backendClient.backendBaseUrl})');
    }

    final List<Widget> barChildren = [Expanded(child: connectionText)];
    if (retryButton != null) {
      barChildren.add(retryButton);
    }
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(children: barChildren),
      ),
    );
  }
}
