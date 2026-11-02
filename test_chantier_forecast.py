import unittest

import pandas as pd

from chantier_forecast import match_invoices_to_orders, normalize_text


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
