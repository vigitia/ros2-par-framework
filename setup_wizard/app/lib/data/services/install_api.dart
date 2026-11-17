// Written by Claude Code
//
// The app's calls for the Install area (setup_wizard/backend/install_api.py): what the repositories of
// config/node_catalog.list offer, refreshing that from the network, what installing a choice needs, and the install
// itself with its state.

import 'setup_wizard_backend_client.dart';

/// Offer kinds, as the backend names them (node_catalog.OFFER_KIND_*).
const String offerKindApp = 'app';
const String offerKindCamera = 'camera';
const String offerKindSensorNode = 'sensor_node';

/// Install phases, as the backend names them (install_api.INSTALL_PHASE_*).
const String installPhaseIdle = 'idle';
const String installPhaseRunning = 'running';
const String installPhaseNeedsSudo = 'needs_sudo';
const String installPhaseFailed = 'failed';
const String installPhaseRestarting = 'restarting';
const String installPhaseInstalled = 'installed';

extension InstallApi on SetupWizardBackendClient {
  /// Returns every offer with its installed state, read from the repositories downloaded last.
  Future<NodeCatalog> fetchNodeCatalog() async {
    final Map<String, dynamic> catalogJson = await getJson('/api/catalog') as Map<String, dynamic>;
    return NodeCatalog.fromJson(catalogJson);
  }

  /// Starts downloading the catalog repositories' latest state; a refresh that runs already continues.
  Future<CatalogRefreshState> startCatalogRefresh() async {
    final dynamic refreshStateJson = await sendJson('POST', '/api/catalog/refresh', null);
    return CatalogRefreshState.fromJson(refreshStateJson as Map<String, dynamic>);
  }

  /// Adds a repository to the catalog by its git URL (branch null or empty: its default branch) and starts
  /// downloading the catalog. Throws with the backend's reason, e.g. for a URL that is no git URL.
  Future<CatalogRefreshState> addUserRepository({required String url, required String? branch}) async {
    final dynamic refreshStateJson = await sendJson('POST', '/api/catalog/repositories', {'url': url, 'branch': branch});
    return CatalogRefreshState.fromJson(refreshStateJson as Map<String, dynamic>);
  }

  /// Removes a repository the user added from the catalog; an installed copy stays installed.
  Future<void> removeUserRepository(String directoryName) async {
    await sendJson('DELETE', '/api/catalog/repositories/${Uri.encodeComponent(directoryName)}', null);
  }

  Future<CatalogRefreshState> fetchCatalogRefreshState() async {
    final dynamic refreshStateJson = await getJson('/api/catalog/refresh');
    return CatalogRefreshState.fromJson(refreshStateJson as Map<String, dynamic>);
  }

  /// Returns the repositories and released packages that installing chosenOffers needs.
  Future<InstallPlan> fetchInstallPlan(List<CatalogOffer> chosenOffers) async {
    final dynamic installPlanJson = await sendJson('POST', '/api/install/plan', _createChosenOffersJson(chosenOffers));
    return InstallPlan.fromJson(installPlanJson as Map<String, dynamic>);
  }

  /// Adds what chosenOffers need to the installation and builds it. Starting again with the same offers continues an
  /// install that needed a sudo command.
  Future<InstallState> startInstall(List<CatalogOffer> chosenOffers) async {
    final dynamic installStateJson = await sendJson('POST', '/api/install/start', _createChosenOffersJson(chosenOffers));
    return InstallState.fromJson(installStateJson as Map<String, dynamic>);
  }

  Future<InstallState> fetchInstallState() async {
    final dynamic installStateJson = await getJson('/api/install/state');
    return InstallState.fromJson(installStateJson as Map<String, dynamic>);
  }

  Map<String, dynamic> _createChosenOffersJson(List<CatalogOffer> chosenOffers) {
    final List<Map<String, String>> offerChoicesJson = [];
    for (final CatalogOffer chosenOffer in chosenOffers) {
      offerChoicesJson.add({'kind': chosenOffer.kind, 'name': chosenOffer.name});
    }
    return {'chosen_offers': offerChoicesJson};
  }
}

/// Something the installation can add: an app, a camera type or a sensor processing node.
class CatalogOffer {
  const CatalogOffer({
    required this.kind,
    required this.name,
    required this.displayName,
    required this.description,
    required this.repositoryDirectoryName,
    required this.isInstalled,
    required this.installedVersion,
    required this.availableVersion,
  });

  factory CatalogOffer.fromJson(Map<String, dynamic> offerJson) {
    return CatalogOffer(
      kind: offerJson['kind'] as String,
      name: offerJson['name'] as String,
      displayName: offerJson['display_name'] as String,
      description: offerJson['description'] as String,
      repositoryDirectoryName: offerJson['repository_directory_name'] as String?,
      isInstalled: offerJson['is_installed'] as bool,
      installedVersion: offerJson['installed_version'] as String?,
      availableVersion: offerJson['available_version'] as String?,
    );
  }

  /// One of the offerKind* values.
  final String kind;

  /// The entry's name: the app's or sensor node's package, the camera type.
  final String name;
  final String displayName;
  final String description;

  /// The catalog repository that brings it; null for a camera type of the framework's core.
  final String? repositoryDirectoryName;
  final bool isInstalled;

  /// The package.xml version of the offer's package (for a camera its driver) on this computer; null when that
  /// package is not installed, empty when its version cannot be read.
  final String? installedVersion;

  /// The package.xml version in the catalog repository, as downloaded last; null for a released package (e.g. a
  /// camera driver from apt), which the catalog does not know.
  final String? availableVersion;

  /// The display name, or the name when the entry has none.
  String get shownName => displayName.isEmpty ? name : displayName;
}

/// A catalog repository that could not be read, has entries that could not, or (added by the user) offers nothing.
class CatalogRepositoryProblem {
  const CatalogRepositoryProblem({
    required this.directoryName,
    required this.problemTexts,
    required this.isUserAdded,
  });

  final String directoryName;

  /// The backend's error texts (e.g. git's message), as they are; empty for a user's repository that offers
  /// nothing.
  final List<String> problemTexts;

  /// True for a repository the user added by URL, which the user can remove again.
  final bool isUserAdded;
}

class NodeCatalog {
  const NodeCatalog({required this.offers, required this.repositoryProblems, required this.catalogErrorText});

  factory NodeCatalog.fromJson(Map<String, dynamic> catalogJson) {
    final List<CatalogOffer> offers = [];
    for (final dynamic offerJson in catalogJson['offers'] as List<dynamic>) {
      offers.add(CatalogOffer.fromJson(offerJson as Map<String, dynamic>));
    }
    final List<CatalogRepositoryProblem> repositoryProblems = [];
    for (final dynamic repositoryJson in catalogJson['repositories'] as List<dynamic>) {
      final Map<String, dynamic> repositoryMap = repositoryJson as Map<String, dynamic>;
      final List<String> problemTexts = [];
      final String? repositoryErrorText = repositoryMap['error_text'] as String?;
      if (repositoryErrorText != null) {
        problemTexts.add(repositoryErrorText);
      }
      problemTexts.addAll((repositoryMap['entry_error_texts'] as List<dynamic>).cast<String>());
      final bool isUserAdded = repositoryMap['is_user_added'] as bool;
      final bool offersNothing = (repositoryMap['offers'] as List<dynamic>).isEmpty;
      if (problemTexts.isNotEmpty || (isUserAdded && offersNothing)) {
        repositoryProblems.add(CatalogRepositoryProblem(
          directoryName: repositoryMap['directory_name'] as String,
          problemTexts: problemTexts,
          isUserAdded: isUserAdded,
        ));
      }
    }
    return NodeCatalog(
      offers: offers,
      repositoryProblems: repositoryProblems,
      catalogErrorText: catalogJson['catalog_error_text'] as String?,
    );
  }

  final List<CatalogOffer> offers;
  final List<CatalogRepositoryProblem> repositoryProblems;

  /// Why the catalog list itself cannot be read; null when it can.
  final String? catalogErrorText;
}

class CatalogRefreshState {
  const CatalogRefreshState({required this.isRunning});

  factory CatalogRefreshState.fromJson(Map<String, dynamic> refreshStateJson) {
    return CatalogRefreshState(isRunning: refreshStateJson['phase'] == 'running');
  }

  final bool isRunning;
}

/// A repository or released package an install adds, with the names of what needs it.
class PlannedInstallItem {
  const PlannedInstallItem({required this.name, required this.neededByNames, required this.isPresent});

  /// The repository's directory, or the released package's rosdep key.
  final String name;

  /// Display names of the chosen offers or the repositories that need it.
  final List<String> neededByNames;

  /// True for a repository that is in src/ already (it is built, not downloaded).
  final bool isPresent;
}

class InstallPlan {
  const InstallPlan({required this.repositories, required this.rosPackages});

  factory InstallPlan.fromJson(Map<String, dynamic> installPlanJson) {
    final List<PlannedInstallItem> repositories = [];
    for (final dynamic repositoryJson in installPlanJson['repositories'] as List<dynamic>) {
      final Map<String, dynamic> repositoryMap = repositoryJson as Map<String, dynamic>;
      repositories.add(PlannedInstallItem(
        name: repositoryMap['directory_name'] as String,
        neededByNames: (repositoryMap['needed_by_names'] as List<dynamic>).cast<String>(),
        isPresent: repositoryMap['is_cloned'] as bool,
      ));
    }
    final List<PlannedInstallItem> rosPackages = [];
    for (final dynamic rosPackageJson in installPlanJson['ros_packages'] as List<dynamic>) {
      final Map<String, dynamic> rosPackageMap = rosPackageJson as Map<String, dynamic>;
      rosPackages.add(PlannedInstallItem(
        name: rosPackageMap['ros_package_name'] as String,
        neededByNames: (rosPackageMap['needed_by_names'] as List<dynamic>).cast<String>(),
        isPresent: false,
      ));
    }
    return InstallPlan(repositories: repositories, rosPackages: rosPackages);
  }

  final List<PlannedInstallItem> repositories;
  final List<PlannedInstallItem> rosPackages;

  bool get isEmpty => repositories.isEmpty && rosPackages.isEmpty;

  /// The planned repository with that directory name; null when the plan does not add it.
  PlannedInstallItem? findRepository(String directoryName) {
    for (final PlannedInstallItem repository in repositories) {
      if (repository.name == directoryName) {
        return repository;
      }
    }
    return null;
  }
}

class InstallState {
  const InstallState({
    required this.phase,
    required this.sudoCommandText,
    required this.exitCode,
    required this.logLines,
  });

  factory InstallState.fromJson(Map<String, dynamic> installStateJson) {
    return InstallState(
      phase: installStateJson['phase'] as String,
      sudoCommandText: installStateJson['sudo_command_text'] as String?,
      exitCode: installStateJson['exit_code'] as int?,
      logLines: (installStateJson['log_lines'] as List<dynamic>).cast<String>(),
    );
  }

  /// One of the installPhase* values.
  final String phase;

  /// For installPhaseNeedsSudo: the command to run in a terminal before continuing.
  final String? sudoCommandText;

  /// For installPhaseFailed: the build's exit code.
  final int? exitCode;

  /// The last lines of the build's output.
  final List<String> logLines;
}
