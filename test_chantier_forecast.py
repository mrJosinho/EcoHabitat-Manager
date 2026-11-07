import unittest

import pandas as pd

from chantier_forecast import (
    build_chantier_forecast,
    find_potential_invoice_matches,
    is_deposit_reference,
    match_invoices_to_orders,
    normalize_text,
)


def order_row(order_no, client_ref, sale_date="2026-04-01"):
    client_key = normalize_text(client_ref)
    agency_key = normalize_text("YVETOT")
    return {
        "order_no": order_no,
        "order_key": normalize_text(order_no),
        "sale_date": pd.Timestamp(sale_date),
        "client_ref": client_ref,
        "client_key": client_key,
        "agency": "YVETOT",
        "agency_key": agency_key,
        "match_key": f"{client_key}|{agency_key}",
        "amount_ht": 10000.0,
        "seller_1": "VENDEUR TEST",
        "seller_2": "",
        "seller_3": "",
    }


def invoice_row(order_no, client_ref, sale_month_label="AVRIL 26"):
    client_key = normalize_text(client_ref)
    agency_key = normalize_text("YVETOT")
    return {
        "invoice_no": "FACT_TEST",
        "order_no": order_no,
        "order_key": normalize_text(order_no),
        "invoice_date": pd.Timestamp("2026-08-01"),
        "client_ref": client_ref,
        "client_key": client_key,
        "agency": "YVETOT",
        "agency_key": agency_key,
        "match_key": f"{client_key}|{agency_key}",
        "amount_ht": 12500.0,
        "sale_month_label": sale_month_label,
        "seller_1": "VENDEUR TEST",
        "seller_2": "",
        "seller_3": "",
    }


class InvoiceMatchingTests(unittest.TestCase):
    def test_deposit_word_is_detected_without_false_partial_match(self):
        self.assertTrue(is_deposit_reference("CHERFILS Acompte : fenetre"))
        self.assertFalse(is_deposit_reference("ACOMPTESSE TEST"))

    def test_deposit_invoice_keeps_order_to_install(self):
        orders = pd.DataFrame([order_row("CDSCOL04639", "CHERFILS FENETRE")])
        invoice = invoice_row("CDSCOL04639", "CHERFILS Acompte : fenetre")
        invoice.update({
            "invoice_no": "FACT04306",
            "amount_ht": 6673.15,
            "is_deposit": True,
        })

        forecast, matches, unmatched = build_chantier_forecast(
            orders, pd.DataFrame([invoice]), today="2026-11-07"
        )

        self.assertFalse(bool(forecast.iloc[0]["is_installed"]))
        self.assertTrue(bool(forecast.iloc[0]["has_deposit"]))
        self.assertEqual(forecast.iloc[0]["billing_status"], "Acompte facturé")
        self.assertAlmostEqual(forecast.iloc[0]["deposit_invoiced_ht"], 6673.15)
        self.assertEqual(forecast.iloc[0]["deposit_invoice_no"], "FACT04306")
        self.assertEqual(len(matches), 1)
        self.assertTrue(unmatched.empty)

    def test_final_invoice_after_deposit_marks_order_installed(self):
        orders = pd.DataFrame([order_row("CDSCOL04639", "CHERFILS FENETRE")])
        deposit = invoice_row("CDSCOL04639", "CHERFILS Acompte : fenetre")
        deposit.update({
            "invoice_no": "FACT04306",
            "amount_ht": 6673.15,
            "is_deposit": True,
        })
        balance = invoice_row("CDSCOL04639", "CHERFILS FENETRE")
        balance.update({
            "invoice_no": "FACT04399",
            "amount_ht": 15570.69,
            "is_deposit": False,
        })

        forecast, matches, unmatched = build_chantier_forecast(
            orders, pd.DataFrame([deposit, balance]), today="2026-11-07"
        )

        self.assertTrue(bool(forecast.iloc[0]["is_installed"]))
        self.assertEqual(
            forecast.iloc[0]["billing_status"], "Acompte + solde facturés / posé"
        )
        self.assertEqual(forecast.iloc[0]["invoice_no"], "FACT04399")
        self.assertAlmostEqual(forecast.iloc[0]["deposit_invoiced_ht"], 6673.15)
        self.assertEqual(len(matches), 2)
        self.assertTrue(unmatched.empty)

    def test_manual_match_can_install_two_orders_from_one_invoice(self):
        orders = pd.DataFrame([
            order_row("CDGHRI04170", "NAPPE REVETEMENT", sale_date="2026-05-27"),
            order_row("CDGHRI04171", "NAPPE MOTORISATION", sale_date="2026-05-27"),
        ])
        invoice = invoice_row("CDGHRI04182", "NAPPE ENSEMBLE")
        invoice.update({
            "invoice_no": "FACT04227",
            "invoice_date": pd.Timestamp("2026-10-19"),
            "amount_ht": 25909.09,
        })

        forecast, matches, unmatched = build_chantier_forecast(
            orders,
            pd.DataFrame([invoice]),
            today="2026-11-02",
            manual_invoice_matches={
                "FACT04227": [
                    normalize_text("CDGHRI04170"),
                    normalize_text("CDGHRI04171"),
                ]
            },
        )

        self.assertTrue(forecast["is_installed"].all())
        self.assertEqual(len(matches), 2)
        self.assertTrue((matches["confidence"] == "Validation manuelle").all())
        self.assertTrue(unmatched.empty)

    def test_potential_match_explains_different_order_number(self):
        orders = pd.DataFrame([
            order_row("CD03829", "LEROUGE SOIN TOITURE", sale_date="2026-02-24")
        ])
        orders["amount_ht"] = 8272.78
        orders["is_installed"] = False
        invoice = invoice_row("CDAYAC04596", "LEROUGE RESINE")
        invoice.update({
            "invoice_no": "FACT04223",
            "invoice_date": pd.Timestamp("2026-10-19"),
            "amount_ht": 8272.74,
            "match_status": "N° commande introuvable",
        })

        result = find_potential_invoice_matches(orders, pd.DataFrame([invoice]))

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["candidate_order_no"], "CD03829")
        self.assertEqual(result.iloc[0]["confidence"], "ÉLEVÉE")
        self.assertIn("diffère", result.iloc[0]["non_match_reason"])

    def test_potential_match_can_group_two_orders(self):
        orders = pd.DataFrame([
            order_row("CDGHRI04170", "NAPPE REVETEMENT", sale_date="2026-05-27"),
            order_row("CDGHRI04171", "NAPPE MOTORISATION", sale_date="2026-05-27"),
        ])
        orders["amount_ht"] = [21727.27, 3545.45]
        orders["agency"] = "MAROMME"
        orders["agency_key"] = normalize_text("MAROMME")
        orders["is_installed"] = False
        invoice = invoice_row("CDGHRI04182", "NAPPE ENSEMBLE")
        invoice.update({
            "invoice_no": "FACT04227",
            "invoice_date": pd.Timestamp("2026-10-19"),
            "amount_ht": 25909.09,
            "agency": "MAROMME",
            "agency_key": normalize_text("MAROMME"),
            "match_status": "N° commande introuvable",
        })

        result = find_potential_invoice_matches(orders, pd.DataFrame([invoice]))

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result.iloc[0]["candidate_order_no"],
            "CDGHRI04170 + CDGHRI04171",
        )
        self.assertIn("regrouper 2 commandes", result.iloc[0]["non_match_reason"])

    def test_unknown_invoice_order_number_uses_unique_exact_label(self):
        orders = pd.DataFrame([order_row("CD01234", "DUPONT MENUISERIE")])
        invoices = pd.DataFrame([invoice_row("CD09999", "DUPONT MENUISERIE")])

        matches, unmatched = match_invoices_to_orders(orders, invoices)

        self.assertEqual(len(matches), 1)
        self.assertTrue(unmatched.empty)
        self.assertEqual(matches.iloc[0]["order_no"], "CD01234")
        self.assertEqual(
            matches.iloc[0]["confidence"],
            "Libellé exact (n° commande différent)",
        )

    def test_unknown_invoice_order_number_stays_unmatched_when_ambiguous(self):
        orders = pd.DataFrame([
            order_row("CD01234", "DUPONT MENUISERIE"),
            order_row("CD05678", "DUPONT MENUISERIE", sale_date="2026-05-01"),
        ])
        invoices = pd.DataFrame([invoice_row("CD09999", "DUPONT MENUISERIE")])

        matches, unmatched = match_invoices_to_orders(orders, invoices)

        self.assertTrue(matches.empty)
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched.iloc[0]["match_status"], "N° commande introuvable")

    def test_n_minus_one_invoice_does_not_fallback_to_current_order(self):
        orders = pd.DataFrame([order_row("CD01234", "DUPONT MENUISERIE")])
        invoices = pd.DataFrame([
            invoice_row("CD09999", "DUPONT MENUISERIE", sale_month_label="CH")
        ])

        matches, unmatched = match_invoices_to_orders(orders, invoices)

        self.assertTrue(matches.empty)
        self.assertEqual(unmatched.iloc[0]["match_status"], "Vente N-1 présumée")


if __name__ == "__main__":
    unittest.main()
