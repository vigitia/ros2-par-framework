// Written by Claude Code
//
// The installed and available offers of one kind (apps, cameras or sensor processing nodes) from the framework's
// catalog (setup_wizard/backend/install/install_api.py), one row each with its description and, right-aligned, its version.
// Used as the page of the Apps, Cameras and Sensor nodes areas while there is no profile, and as the dialog behind
// their "Add …" buttons (OfferPickerDialog).
//
// Clicking an available offer shows what installing it adds (repositories and ROS packages, each with what needs it)
// and Install. The view then follows the build: its last output lines, the one sudo command to run in a terminal
// when system packages are missing (Continue builds again), and the backend's restart after a successful build.
// Clicking an installed offer, or Done after its install, hands it to onInstalledOfferChosen where the owner adds it
// to the profile. "Check for new versions" downloads the catalog again; "Add repository" adds the user's own
// repository by its git URL, and repositories that cannot be read are listed at the end, the user's own with Remove.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../config/wizard_strings.dart';
import '../../config/wizard_icons.dart';
import '../../data/services/install_api.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import '../core/ui/top_aligned_page_content.dart';

/// How often the view asks for the state of a running refresh or install.
const Duration installStatePollInterval = Duration(seconds: 1);

/// How long the view waits for the backend to answer again after a successful build restarted it.
const Duration backendRestartTimeout = Duration(seconds: 120);

class OfferCatalogView extends StatefulWidget {
  const OfferCatalogView({
    super.key,
    required this.backendClient,
    required this.offerKind,
    this.onInstalledOfferChosen,
    this.blockedTextByOfferName = const {},
  });

  final SetupWizardBackendClient backendClient;

  /// One of the offerKind* values: the offers this view lists.
  final String offerKind;

  /// Called with an installed offer the user clicked, or one just installed; null: installed offers cannot be
  /// clicked (e.g. no profile to add them to).
  final ValueChanged<CatalogOffer>? onInstalledOfferChosen;

  /// Installed offers that cannot be chosen, by name, with the reason shown in their row (e.g. "In this profile").
  final Map<String, String> blockedTextByOfferName;

  @override
  State<OfferCatalogView> createState() => _OfferCatalogViewState();
}

class _OfferCatalogViewState extends State<OfferCatalogView> {
  NodeCatalog? _nodeCatalog;
  String? _catalogLoadErrorText;
  bool _isCatalogRefreshing = false;
  Timer? _catalogRefreshPollTimer;

  /// The available offer the user clicked; null while the list is shown.
  CatalogOffer? _offerToInstall;
  InstallPlan? _installPlan;
  String? _installPlanErrorText;

  /// The latest install's state; null while no install is shown.
  InstallState? _installState;
  String? _installStartErrorText;
  bool _isInstallStarting = false;
  Timer? _installStatePollTimer;

  /// Set while the backend does not answer during an install, which it does while it restarts.
  DateTime? _backendUnreachableSince;
  bool _hasBackendRestartTimedOut = false;

  @override
  void initState() {
    super.initState();
    _loadCatalogAndInstallState();
  }

  @override
  void dispose() {
    _catalogRefreshPollTimer?.cancel();
    _installStatePollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadCatalogAndInstallState() async {
    try {
      final InstallState installState = await widget.backendClient.fetchInstallState();
      if (!mounted) {
        return;
      }
      // An install started earlier (e.g. before the dialog was closed) is shown until it is done
      if (installState.phase != installPhaseIdle && installState.phase != installPhaseInstalled) {
        setState(() {
          _installState = installState;
        });
        _scheduleInstallStatePoll();
      }
    } catch (error) {
      // The catalog request below reports an unreachable backend
    }
    await _loadCatalog(isRefreshStartedWhenEmpty: true);
  }

  /// Reads the catalog; when no repository has been downloaded yet (first start), starts a refresh.
  Future<void> _loadCatalog({bool isRefreshStartedWhenEmpty = false}) async {
    try {
      final NodeCatalog nodeCatalog = await widget.backendClient.fetchNodeCatalog();
      if (!mounted) {
        return;
      }
      setState(() {
        _nodeCatalog = nodeCatalog;
        _catalogLoadErrorText = null;
      });
      bool hasDownloadedOffer = false;
      for (final CatalogOffer offer in nodeCatalog.offers) {
        if (offer.repositoryDirectoryName != null) {
          hasDownloadedOffer = true;
        }
      }
      if (isRefreshStartedWhenEmpty && !hasDownloadedOffer && nodeCatalog.catalogErrorText == null) {
        await _startCatalogRefresh();
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _catalogLoadErrorText = describeBackendErrorForUser(error);
        });
      }
    }
  }

  Future<void> _startCatalogRefresh() async {
    setState(() {
      _isCatalogRefreshing = true;
    });
    try {
      await widget.backendClient.startCatalogRefresh();
    } catch (error) {
      if (mounted) {
        setState(() {
          _isCatalogRefreshing = false;
          _catalogLoadErrorText = describeBackendErrorForUser(error);
        });
      }
      return;
    }
    _scheduleCatalogRefreshPoll();
  }

  void _scheduleCatalogRefreshPoll() {
    _catalogRefreshPollTimer?.cancel();
    _catalogRefreshPollTimer = Timer(installStatePollInterval, _pollCatalogRefresh);
  }

  Future<void> _pollCatalogRefresh() async {
    try {
      final CatalogRefreshState refreshState = await widget.backendClient.fetchCatalogRefreshState();
      if (!mounted) {
        return;
      }
      if (refreshState.isRunning) {
        _scheduleCatalogRefreshPoll();
        return;
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _catalogLoadErrorText = describeBackendErrorForUser(error);
      });
    }
    setState(() {
      _isCatalogRefreshing = false;
    });
    await _loadCatalog();
  }

  /// Asks for the repository's URL and branch, adds it and downloads the catalog with it.
  Future<void> _askAndAddUserRepository() async {
    final _UserRepositoryChoice? repositoryChoice = await showDialog<_UserRepositoryChoice>(
      context: context,
      builder: (BuildContext dialogContext) => const _AddUserRepositoryDialog(),
    );
    if (repositoryChoice == null || !mounted) {
      return;
    }
    try {
      await widget.backendClient.addUserRepository(url: repositoryChoice.url, branch: repositoryChoice.branch);
    } catch (error) {
      _showMessage(WizardStrings.getAddRepositoryErrorText(
        backendErrorText: describeBackendErrorForUser(error, isBackendDetailShown: true),
      ));
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isCatalogRefreshing = true;
    });
    _scheduleCatalogRefreshPoll();
  }

  Future<void> _removeUserRepository(String directoryName) async {
    try {
      await widget.backendClient.removeUserRepository(directoryName);
    } catch (error) {
      _showMessage(describeBackendErrorForUser(error));
      return;
    }
    await _loadCatalog();
  }

  /// Shows what installing the offer adds, with Install.
  Future<void> _showInstallPlan(CatalogOffer offer) async {
    setState(() {
      _offerToInstall = offer;
      _installPlan = null;
      _installPlanErrorText = null;
      _installStartErrorText = null;
    });
    try {
      final InstallPlan installPlan = await widget.backendClient.fetchInstallPlan([offer]);
      if (mounted) {
        setState(() {
          _installPlan = installPlan;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _installPlanErrorText = describeBackendErrorForUser(error);
        });
      }
    }
  }

  /// Starts the install of the chosen offer; also continues one that needed a sudo command or failed.
  Future<void> _startInstall() async {
    final CatalogOffer? offerToInstall = _offerToInstall;
    setState(() {
      _isInstallStarting = true;
      _installStartErrorText = null;
      _hasBackendRestartTimedOut = false;
      _backendUnreachableSince = null;
    });
    try {
      // Without an offer (an install shown after reopening) the lists hold the entries already; it only builds
      final List<CatalogOffer> chosenOffers = offerToInstall == null ? [] : [offerToInstall];
      final InstallState installState = await widget.backendClient.startInstall(chosenOffers);
      if (!mounted) {
        return;
      }
      setState(() {
        _installState = installState;
        _isInstallStarting = false;
      });
      _scheduleInstallStatePoll();
    } catch (error) {
      if (mounted) {
        setState(() {
          _installStartErrorText = describeBackendErrorForUser(error, isBackendDetailShown: true);
          _isInstallStarting = false;
        });
      }
    }
  }

  void _scheduleInstallStatePoll() {
    _installStatePollTimer?.cancel();
    _installStatePollTimer = Timer(installStatePollInterval, _pollInstallState);
  }

  Future<void> _pollInstallState() async {
    InstallState installState;
    try {
      installState = await widget.backendClient.fetchInstallState();
    } catch (error) {
      if (!mounted) {
        return;
      }
      // Not answering during an install: the backend restarts after a successful build
      final DateTime unreachableSince = _backendUnreachableSince ?? DateTime.now();
      final bool hasTimedOut = DateTime.now().difference(unreachableSince) > backendRestartTimeout;
      setState(() {
        _backendUnreachableSince = unreachableSince;
        _hasBackendRestartTimedOut = hasTimedOut;
      });
      if (!hasTimedOut) {
        _scheduleInstallStatePoll();
      }
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _installState = installState;
      _backendUnreachableSince = null;
    });
    final String phase = installState.phase;
    if (phase == installPhaseRunning || phase == installPhaseRestarting) {
      _scheduleInstallStatePoll();
    }
  }

  /// Back to the list, which reads the catalog again (new offers show as installed); after a successful install
  /// the installed offer is handed to the owner.
  Future<void> _closeInstallView() async {
    final bool wasInstalled = _installState?.phase == installPhaseInstalled;
    final CatalogOffer? installedOffer = _offerToInstall;
    setState(() {
      _installState = null;
      _offerToInstall = null;
      _installPlan = null;
      _hasBackendRestartTimedOut = false;
      _backendUnreachableSince = null;
    });
    final ValueChanged<CatalogOffer>? onInstalledOfferChosen = widget.onInstalledOfferChosen;
    if (wasInstalled && installedOffer != null && onInstalledOfferChosen != null) {
      onInstalledOfferChosen(installedOffer);
      return;
    }
    await _loadCatalog();
  }

  void _startWaitingForBackendAgain() {
    setState(() {
      _hasBackendRestartTimedOut = false;
      _backendUnreachableSince = null;
    });
    _scheduleInstallStatePoll();
  }

  void _showMessage(String messageText) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(messageText)));
    }
  }

  Future<void> _copySudoCommand(String sudoCommandText) async {
    await Clipboard.setData(ClipboardData(text: sudoCommandText));
    _showMessage(WizardStrings.commandCopiedText);
  }

  @override
  Widget build(BuildContext context) {
    final InstallState? installState = _installState;
    if (installState != null) {
      return _buildInstallView(installState);
    }
    final CatalogOffer? offerToInstall = _offerToInstall;
    if (offerToInstall != null) {
      return _buildInstallPlanView(offerToInstall);
    }
    final String? catalogLoadErrorText = _catalogLoadErrorText;
    final NodeCatalog? nodeCatalog = _nodeCatalog;
    if (nodeCatalog == null) {
      if (catalogLoadErrorText != null) {
        return TopAlignedPageContent(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(catalogLoadErrorText, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              TextButton(onPressed: _loadCatalogAndInstallState, child: const Text(WizardStrings.tryAgainButtonLabel)),
            ],
          ),
        );
      }
      return const TopAlignedPageContent(child: CircularProgressIndicator());
    }
    return _buildOfferList(nodeCatalog);
  }

  Widget _buildOfferList(NodeCatalog nodeCatalog) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> children = [
      Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          OutlinedButton.icon(
            onPressed: _isCatalogRefreshing ? null : _startCatalogRefresh,
            icon: const Icon(WizardIcons.refreshListButtonIcon),
            label: const Text(WizardStrings.refreshCatalogButtonLabel),
          ),
          OutlinedButton.icon(
            onPressed: _isCatalogRefreshing ? null : _askAndAddUserRepository,
            icon: const Icon(WizardIcons.addRepositoryButtonIcon),
            label: const Text(WizardStrings.addRepositoryButtonLabel),
          ),
          if (_isCatalogRefreshing) ...[
            const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
            const Text(WizardStrings.catalogRefreshingText),
          ],
        ],
      ),
      const SizedBox(height: 8),
    ];
    for (final String? errorText in [_catalogLoadErrorText, nodeCatalog.catalogErrorText]) {
      if (errorText != null) {
        children.add(Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(errorText, style: TextStyle(color: colorScheme.error)),
        ));
      }
    }
    final List<CatalogOffer> installedOffers = [];
    final List<CatalogOffer> availableOffers = [];
    for (final CatalogOffer offer in nodeCatalog.offers) {
      if (offer.kind != widget.offerKind) {
        continue;
      }
      if (offer.isInstalled) {
        installedOffers.add(offer);
      } else {
        availableOffers.add(offer);
      }
    }
    children.add(_buildOfferGroup(WizardStrings.installedOffersTitle, installedOffers));
    children.add(_buildOfferGroup(WizardStrings.availableOffersTitle, availableOffers));
    if (nodeCatalog.repositoryProblems.isNotEmpty) {
      children.add(_buildRepositoryProblems(nodeCatalog.repositoryProblems));
    }
    return ListView(padding: const EdgeInsets.all(24), children: children);
  }

  Widget _buildOfferGroup(String groupTitle, List<CatalogOffer> offers) {
    final List<Widget> rows = [];
    for (final CatalogOffer offer in offers) {
      rows.add(_buildOfferRow(offer));
    }
    if (rows.isEmpty) {
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Text(
          WizardStrings.noOffersInGroupText,
          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(groupTitle, style: Theme.of(context).textTheme.titleMedium),
          ...rows,
        ],
      ),
    );
  }

  /// One offer: name and description, the version right-aligned. An available offer opens its install; an
  /// installed one is handed to the owner, unless the owner blocks it or takes none.
  Widget _buildOfferRow(CatalogOffer offer) {
    final List<String> subtitleLines = [];
    if (offer.description.isNotEmpty) {
      subtitleLines.add(offer.description);
    }
    VoidCallback? onTap;
    final String? blockedText = widget.blockedTextByOfferName[offer.name];
    final ValueChanged<CatalogOffer>? onInstalledOfferChosen = widget.onInstalledOfferChosen;
    if (!offer.isInstalled) {
      onTap = () => _showInstallPlan(offer);
    } else if (blockedText != null) {
      subtitleLines.add(blockedText);
    } else if (onInstalledOfferChosen != null) {
      onTap = () => onInstalledOfferChosen(offer);
    }
    return ListTile(
      contentPadding: EdgeInsets.zero,
      enabled: onTap != null || widget.onInstalledOfferChosen == null,
      onTap: onTap,
      leading: Icon(offer.isInstalled ? WizardIcons.installedOfferIcon : WizardIcons.availableOfferIcon),
      title: Text(offer.shownName),
      subtitle: subtitleLines.isEmpty ? null : Text(subtitleLines.join('\n')),
      trailing: Text(
        WizardStrings.getOfferVersionText(
          installedVersion: offer.installedVersion,
          availableVersion: offer.availableVersion,
        ),
        textAlign: TextAlign.end,
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
    );
  }

  Widget _buildRepositoryProblems(List<CatalogRepositoryProblem> repositoryProblems) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> rows = [];
    for (final CatalogRepositoryProblem repositoryProblem in repositoryProblems) {
      String problemText = repositoryProblem.problemTexts.join(' ');
      if (problemText.isEmpty) {
        problemText = WizardStrings.repositoryOffersNothingText;
      }
      Widget? removeButton;
      if (repositoryProblem.isUserAdded) {
        removeButton = TextButton(
          onPressed: () => _removeUserRepository(repositoryProblem.directoryName),
          child: const Text(WizardStrings.removeButtonLabel),
        );
      }
      rows.add(ListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(repositoryProblem.directoryName),
        subtitle: Text(problemText, style: TextStyle(color: colorScheme.error)),
        trailing: removeButton,
      ));
    }
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(WizardStrings.catalogProblemsTitle, style: Theme.of(context).textTheme.titleMedium),
          const Text(WizardStrings.catalogProblemsText),
          ...rows,
        ],
      ),
    );
  }

  /// What installing the offer adds, with Install and Back.
  Widget _buildInstallPlanView(CatalogOffer offerToInstall) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> children = [
      Text(
        WizardStrings.getInstallOfferTitle(offerName: offerToInstall.shownName),
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 12),
    ];
    final InstallPlan? installPlan = _installPlan;
    final String? installPlanErrorText = _installPlanErrorText;
    if (installPlanErrorText != null) {
      children.add(Text(installPlanErrorText, style: TextStyle(color: colorScheme.error)));
    } else if (installPlan == null) {
      children.add(const LinearProgressIndicator());
    } else {
      children.add(const Text(WizardStrings.installPlanTitle));
      for (final PlannedInstallItem repository in installPlan.repositories) {
        children.add(Text(WizardStrings.getPlannedRepositoryText(
          repositoryName: repository.name,
          neededByNames: repository.neededByNames,
          isPresent: repository.isPresent,
        )));
      }
      for (final PlannedInstallItem rosPackage in installPlan.rosPackages) {
        children.add(Text(WizardStrings.getPlannedRosPackageText(
          rosPackageName: rosPackage.name,
          neededByNames: rosPackage.neededByNames,
        )));
      }
      if (installPlan.isEmpty) {
        children.add(const Text(WizardStrings.installPlanEmptyText));
      }
    }
    final String? installStartErrorText = _installStartErrorText;
    if (installStartErrorText != null) {
      children.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(installStartErrorText, style: TextStyle(color: colorScheme.error)),
      ));
    }
    final bool canInstall = installPlan != null && !_isInstallStarting;
    children.add(_buildButtonRow([
      FilledButton.icon(
        onPressed: canInstall ? _startInstall : null,
        icon: const Icon(WizardIcons.installButtonIcon),
        label: const Text(WizardStrings.installButtonLabel),
      ),
      TextButton(
        onPressed: () => setState(() => _offerToInstall = null),
        child: const Text(WizardStrings.backButtonLabel),
      ),
    ]));
    return ListView(padding: const EdgeInsets.all(24), children: children);
  }

  /// The running or finished install: what it does now, what the user has to do, and its last output lines.
  Widget _buildInstallView(InstallState installState) {
    final ColorScheme colorScheme = Theme.of(context).colorScheme;
    final List<Widget> children = [];
    final String phase = installState.phase;
    final bool isBackendRestarting = _backendUnreachableSince != null || phase == installPhaseRestarting;
    if (_hasBackendRestartTimedOut) {
      children.add(Text(WizardStrings.backendRestartTimedOutText, style: TextStyle(color: colorScheme.error)));
      children.add(_buildButtonRow([
        FilledButton(onPressed: _startWaitingForBackendAgain, child: const Text(WizardStrings.tryAgainButtonLabel)),
      ]));
    } else if (isBackendRestarting) {
      children.add(const LinearProgressIndicator());
      children.add(const SizedBox(height: 12));
      children.add(const Text(WizardStrings.backendRestartingText));
    } else if (phase == installPhaseRunning) {
      children.add(const LinearProgressIndicator());
      children.add(const SizedBox(height: 12));
      children.add(const Text(WizardStrings.installRunningText));
    } else if (phase == installPhaseNeedsSudo) {
      children.addAll(_buildSudoCommandChildren(installState.sudoCommandText ?? ''));
    } else if (phase == installPhaseFailed) {
      children.add(Text(
        WizardStrings.getInstallFailedText(exitCode: installState.exitCode),
        style: TextStyle(color: colorScheme.error),
      ));
      children.add(_buildButtonRow([
        FilledButton(onPressed: _startInstall, child: const Text(WizardStrings.tryAgainButtonLabel)),
        TextButton(onPressed: _closeInstallView, child: const Text(WizardStrings.backButtonLabel)),
      ]));
    } else {
      children.add(const Text(WizardStrings.installDoneText));
      children.add(_buildButtonRow([
        FilledButton(onPressed: _closeInstallView, child: const Text(WizardStrings.doneButtonLabel)),
      ]));
    }
    final String? installStartErrorText = _installStartErrorText;
    if (installStartErrorText != null) {
      children.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(installStartErrorText, style: TextStyle(color: colorScheme.error)),
      ));
    }
    if (installState.logLines.isNotEmpty) {
      children.add(const SizedBox(height: 24));
      children.add(Text(WizardStrings.installOutputTitle, style: Theme.of(context).textTheme.titleMedium));
      children.add(const SizedBox(height: 8));
      children.add(Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        color: colorScheme.surfaceContainerHighest,
        child: SelectableText(
          installState.logLines.join('\n'),
          style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
        ),
      ));
    }
    String titleText = WizardStrings.installViewTitle;
    final CatalogOffer? offerToInstall = _offerToInstall;
    if (offerToInstall != null) {
      titleText = WizardStrings.getInstallOfferTitle(offerName: offerToInstall.shownName);
    }
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(titleText, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        ...children,
      ],
    );
  }

  List<Widget> _buildSudoCommandChildren(String sudoCommandText) {
    return [
      const Text(WizardStrings.installNeedsSudoText),
      const SizedBox(height: 12),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: SelectableText(sudoCommandText, style: const TextStyle(fontFamily: 'monospace')),
      ),
      _buildButtonRow([
        OutlinedButton.icon(
          onPressed: () => _copySudoCommand(sudoCommandText),
          icon: const Icon(WizardIcons.copyCommandButtonIcon),
          label: const Text(WizardStrings.copyCommandButtonLabel),
        ),
        FilledButton(
          onPressed: _isInstallStarting ? null : _startInstall,
          child: const Text(WizardStrings.continueInstallButtonLabel),
        ),
        TextButton(onPressed: _closeInstallView, child: const Text(WizardStrings.cancelButtonLabel)),
      ]),
    ];
  }

  Widget _buildButtonRow(List<Widget> buttons) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Wrap(spacing: 12, runSpacing: 8, children: buttons),
    );
  }
}

/// The user's repository: its git URL and branch (null: the default branch).
class _UserRepositoryChoice {
  const _UserRepositoryChoice({required this.url, required this.branch});

  final String url;
  final String? branch;
}

/// Asks for a repository's git URL and, optionally, its branch.
class _AddUserRepositoryDialog extends StatefulWidget {
  const _AddUserRepositoryDialog();

  @override
  State<_AddUserRepositoryDialog> createState() => _AddUserRepositoryDialogState();
}

class _AddUserRepositoryDialogState extends State<_AddUserRepositoryDialog> {
  final TextEditingController _urlController = TextEditingController();
  final TextEditingController _branchController = TextEditingController();

  @override
  void dispose() {
    _urlController.dispose();
    _branchController.dispose();
    super.dispose();
  }

  void _confirm() {
    final String url = _urlController.text.trim();
    if (url.isEmpty) {
      return;
    }
    final String branch = _branchController.text.trim();
    Navigator.of(context).pop(_UserRepositoryChoice(url: url, branch: branch.isEmpty ? null : branch));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text(WizardStrings.addRepositoryDialogTitle),
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(WizardStrings.addRepositoryDialogText),
            const SizedBox(height: 12),
            TextField(
              controller: _urlController,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: WizardStrings.repositoryUrlLabel,
                hintText: WizardStrings.repositoryUrlHint,
              ),
              onChanged: (String url) => setState(() {}),
              onSubmitted: (String url) => _confirm(),
            ),
            TextField(
              controller: _branchController,
              decoration: const InputDecoration(
                labelText: WizardStrings.repositoryBranchLabel,
                hintText: WizardStrings.repositoryBranchHint,
              ),
              onSubmitted: (String branch) => _confirm(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text(WizardStrings.cancelButtonLabel),
        ),
        FilledButton(
          onPressed: _urlController.text.trim().isEmpty ? null : _confirm,
          child: const Text(WizardStrings.addButtonLabel),
        ),
      ],
    );
  }
}
