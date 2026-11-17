// Written by Claude Code
//
// Dialog behind the "Add app", "Add camera" and "Add sensor node" buttons: the installed and available offers of one
// kind (OfferCatalogView). Picking an installed offer, or installing an available one, closes it with that offer,
// which the area then adds to the profile.

import 'package:flutter/material.dart';

import '../../config/wizard_strings.dart';
import '../../data/services/install_api.dart';
import '../../data/services/setup_wizard_backend_client.dart';
import 'offer_catalog_view.dart';

/// The dialog's size on a desktop; smaller windows shrink it (Dialog keeps a margin around it).
const double offerPickerDialogWidthLogicalPx = 760;
const double offerPickerDialogHeightLogicalPx = 680;

/// Opens the dialog; returns the chosen offer, null when it was closed without one.
Future<CatalogOffer?> showOfferPickerDialog({
  required BuildContext context,
  required SetupWizardBackendClient backendClient,
  required String offerKind,
  required String dialogTitle,
  Map<String, String> blockedTextByOfferName = const {},
}) {
  return showDialog<CatalogOffer>(
    context: context,
    builder: (BuildContext dialogContext) => Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: offerPickerDialogWidthLogicalPx,
          maxHeight: offerPickerDialogHeightLogicalPx,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 16, 8, 0),
              child: Row(
                children: [
                  Expanded(child: Text(dialogTitle, style: Theme.of(dialogContext).textTheme.headlineSmall)),
                  IconButton(
                    tooltip: WizardStrings.closeButtonLabel,
                    onPressed: () => Navigator.of(dialogContext).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            Flexible(
              child: OfferCatalogView(
                backendClient: backendClient,
                offerKind: offerKind,
                blockedTextByOfferName: blockedTextByOfferName,
                onInstalledOfferChosen: (CatalogOffer chosenOffer) => Navigator.of(dialogContext).pop(chosenOffer),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
