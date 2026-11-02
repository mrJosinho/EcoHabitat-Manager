import unittest

import pandas as pd

from chantier_google_sheet import (
    _find_equivalent_worksheet,
    _get_or_create_month_sheet,
    _is_month_sheet_title,
    _write_summary,
    _write_tracking_worksheet,
    build_tracking_payload,
)


class FakeWorksheet:
    def __init__(self, title, worksheet_id=1):
        self.title = title
        self.id = worksheet_id
        self.clear_calls = []
        self.update_calls = []

    def batch_clear(self, ranges):
        self.clear_calls.append(ranges)

    def update(self, **kwargs):
        self.update_calls.append(kwargs)


class FakeSpreadsheet:
    def __init__(self, worksheets):
        self._worksheets = worksheets
        self.duplicate_calls = 0
        self.add_calls = 0

    def worksheets(self):
        return list(self._worksheets)

    def worksheet(self, title):
        raise RuntimeError(f"Exact worksheet not found: {title}")

    def duplicate_sheet(self, *_args, **_kwargs):
        self.duplicate_calls += 1
        raise AssertionError("An equivalent worksheet must not be duplicated")

    def add_worksheet(self, *_args, **_kwargs):
        self.add_calls += 1
        raise AssertionError("An equivalent worksheet must not be created")


class TrackingPayloadTests(unittest.TestCase):
    def test_notes_are_kept_and_new_invoice_is_archived(self):
        forecast = pd.DataFrame([
            {
                "order_key": "CD001", "order_no": "CD001", "source_period": "Janvier 2026",
                "client_ref": "Client reste", "product_category": "MEN",
                "status": "Pose possible", "amount_ht": 100.0,
                "sale_date": "2026-01-10", "earliest_install_date": "2026-03-10",
                "agency": "HARFLEUR", "sellers": "Vendeur 1",
                "classification_source": "Reference affaire",
                "classification_confidence": "MOYENNE", "is_installed": False,
            },
            {
                "order_key": "CD002", "order_no": "CD002", "source_period": "Fevrier 2026",
                "client_ref": "Client facture", "product_category": "MEN",
                "status": "Pose", "amount_ht": 200.0,
                "sale_date": "2026-02-10", "earliest_install_date": "2026-04-10",
                "agency": "HARFLEUR", "sellers": "Vendeur 2",
                "classification_source": "Reference affaire",
                "classification_confidence": "MOYENNE", "is_installed": True,
            },
            {
                "order_key": "CD003", "order_no": "CD003", "source_period": "Fevrier 2026",
                "client_ref": "Nouveau client", "product_category": "PRODUIT EXTERIEUR",
                "status": "Attente livraison", "amount_ht": 300.0,
                "sale_date": "2026-02-20", "earliest_install_date": "2026-04-20",
                "agency": "YVETOT", "sellers": "Vendeur 3",
                "classification_source": "Reference affaire",
                "classification_confidence": "MOYENNE", "is_installed": False,
            },
        ])
        matches = pd.DataFrame([{
            "order_key": "CD002", "order_no": "CD002", "invoice_no": "FACT002",
            "invoice_date": "2026-10-12", "invoice_amount_ht": 199.5,
        }])
        old_active = [
            ["TITLE"], ["SUBTITLE"], [], ["headers"],
            ["Janvier 2026", "CD001", "Client reste", "MEN", "Pose possible", 100,
             "10/01/2026", "10/03/2026", "HARFLEUR", "Vendeur 1", "Reference affaire",
             "MOYENNE", "Note rapport conservee", "-"],
            ["Fevrier 2026", "CD002", "Client facture", "MEN", "Pose possible", 200,
             "10/02/2026", "10/04/2026", "HARFLEUR", "Vendeur 2", "Reference affaire",
             "MOYENNE", "Note facture conservee", "Question Joseph"],
        ]
        old_archive = [
            ["TITLE"], ["SUBTITLE"], [], ["headers"],
            ["Janvier 2026", "CD000", "Ancien", "MEN", "Pose possible", 50,
             "01/01/2026", "01/03/2026", "HARFLEUR", "Vendeur", "Reference affaire",
             "MOYENNE", "Ancienne note", "-", "FACT000", "01/10/2026", 50,
             "Historique", "06/10/2026"],
        ]

        payload = build_tracking_payload(
            forecast, matches, old_active, old_archive, now="2026-10-12"
        )

        self.assertEqual(len(payload["active_rows"]), 2)
        self.assertEqual(len(payload["new_archive_rows"]), 1)
        self.assertEqual(payload["active_rows"][0][12], "Note rapport conservee")
        self.assertEqual(payload["new_archive_rows"][0][13], "Question Joseph")
        self.assertEqual(payload["new_archive_rows"][0][14], "FACT002")
        self.assertAlmostEqual(payload["new_archive_amount"], 199.5)
        self.assertEqual(payload["chart_rows"][0], ["Janvier 2026", 100.0, 50.0])
        self.assertEqual(payload["chart_rows"][1], ["Fevrier 2026", 300.0, 199.5])

        worksheet = FakeWorksheet("Synthese")
        _write_summary(worksheet, payload)
        self.assertEqual(len(worksheet.clear_calls), 1)
        self.assertEqual(len(worksheet.update_calls), 1)
        summary_values = worksheet.update_calls[0]["values"]
        self.assertEqual(summary_values[0][0], "RAPPORT COMMANDES NON POSEES ET NOTES")
        self.assertEqual(summary_values[11][:6], [
            "Mois", "Commandes", "Montant HT", "Avec note", "Sans note", "Notes Joseph",
        ])
        self.assertEqual(summary_values[11][6:], [
            "Mois commercial", "CA restant non pose HT", "CA facture recemment HT",
        ])


class WorksheetLookupTests(unittest.TestCase):
    def test_tracking_sheet_is_written_with_one_update_request(self):
        worksheet = FakeWorksheet("Janvier 2026")
        row = ["Janvier 2026"] + [""] * 13

        _write_tracking_worksheet(worksheet, "Titre", "Sous-titre", [row])

        self.assertEqual(len(worksheet.clear_calls), 1)
        self.assertEqual(len(worksheet.update_calls), 1)
        self.assertEqual(worksheet.update_calls[0]["range_name"], "A1:N5")
        self.assertEqual(worksheet.update_calls[0]["values"][4], row)

    def test_equivalent_month_title_ignores_accents_case_and_spaces(self):
        worksheet = FakeWorksheet("  FÉVRIER\u00a02026 ")

        self.assertIs(
            _find_equivalent_worksheet([worksheet], "Fevrier 2026"),
            worksheet,
        )
        self.assertTrue(_is_month_sheet_title(worksheet.title))

    def test_existing_equivalent_sheet_is_reused_before_duplicate(self):
        worksheet = FakeWorksheet("Janvier 2026 ")
        spreadsheet = FakeSpreadsheet([worksheet])

        result = _get_or_create_month_sheet(
            spreadsheet,
            "Janvier 2026",
            template_sheet=FakeWorksheet("Mars 2026", worksheet_id=2),
        )

        self.assertIs(result, worksheet)
        self.assertEqual(spreadsheet.duplicate_calls, 0)
        self.assertEqual(spreadsheet.add_calls, 0)


if __name__ == "__main__":
    unittest.main()
