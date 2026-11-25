import unittest

import pandas as pd

from chantier_forecast import (
    build_chantier_forecast,
    find_potential_invoice_matches,
    merge_potential_invoice_matches,
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


def set_agency(row, agency):
    row["agency"] = agency
    row["agency_key"] = normalize_text(agency)
    row["match_key"] = f"{row['client_key']}|{row['agency_key']}"


class CrossAgencyInvoiceMatchingTests(unittest.TestCase):
    def setUp(self):
        self.order = order_row(
            "CDPERT04075", "LEBAILLY devis menuiserie", "2026-04-16"
        )
        self.order.update({"amount_ht": 5213.27, "seller_1": "PERTUISEL Jeremy"})
        set_agency(self.order, "HARFLEUR")
        self.invoice = invoice_row("", "LEBAILLY devis menuiserie")
        self.invoice.update({
            "invoice_no": "FACT03987",
            "invoice_date": pd.Timestamp("2026-07-20"),
            "amount_ht": 5213.27,
            "seller_1": "PERTUISEL Jeremy",
        })
        set_agency(self.invoice, "SIEGE")

    def test_lebailly_matches_with_missing_zero_or_unknown_order_number(self):
        for order_no in ("", "0", "CD99999"):
            with self.subTest(order_no=order_no):
                invoice = dict(self.invoice, order_no=order_no, order_key=order_no)
                forecast, matches, unmatched = build_chantier_forecast(
                    pd.DataFrame([self.order]), pd.DataFrame([invoice]),
                    today="2026-11-25",
                )

                self.assertTrue(bool(forecast.iloc[0]["is_installed"]))
                self.assertTrue(unmatched.empty)
                self.assertEqual(matches.iloc[0]["order_no"], "CDPERT04075")
                self.assertIn("agence", matches.iloc[0]["confidence"])

    def test_cross_agency_match_rejects_insufficient_or_conflicting_clues(self):
        cases = [
            {"seller_1": "Autre vendeur"},
            {"seller_1": ""},
            {"amount_ht": 5213.28},
            {"amount_ht": 0.0},
            {"amount_ht": -5213.27},
            {"is_credit": True},
            {"invoice_date": pd.Timestamp("2026-04-15")},
            {"invoice_date": pd.NaT},
            {"sale_month_label": "CH"},
            {"sale_month_label": "AVRIL 25"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                invoice = dict(self.invoice, **changes)
                matches, unmatched = match_invoices_to_orders(
                    pd.DataFrame([self.order]), pd.DataFrame([invoice])
                )
                self.assertTrue(matches.empty)
                self.assertEqual(len(unmatched), 1)

    def test_cross_agency_match_requires_the_full_client_reference(self):
        invoice = invoice_row("", "LEBAILLY devis portail")
        invoice.update({"amount_ht": 5213.27, "seller_1": "PERTUISEL Jeremy"})
        set_agency(invoice, "SIEGE")

        matches, unmatched = match_invoices_to_orders(
            pd.DataFrame([self.order]), pd.DataFrame([invoice])
        )

        self.assertTrue(matches.empty)
        self.assertEqual(len(unmatched), 1)

    def test_two_identical_candidates_in_different_agencies_remain_unmatched(self):
        other = dict(self.order, order_no="CDPERT09999", order_key="CDPERT09999")
        set_agency(other, "YVETOT")

        matches, unmatched = match_invoices_to_orders(
            pd.DataFrame([self.order, other]), pd.DataFrame([self.invoice])
        )

        self.assertTrue(matches.empty)
        self.assertEqual(len(unmatched), 1)

    def test_known_order_number_has_priority_over_cross_agency_fallback(self):
        other = order_row("CDPERT09999", "AUTRE CLIENT PORTAIL")
        invoice = dict(self.invoice, order_no="CDPERT09999", order_key="CDPERT09999")

        matches, unmatched = match_invoices_to_orders(
            pd.DataFrame([self.order, other]), pd.DataFrame([invoice])
        )

        self.assertTrue(unmatched.empty)
        self.assertEqual(matches.iloc[0]["order_no"], "CDPERT09999")
        self.assertEqual(matches.iloc[0]["confidence"], "N\u00b0 commande")

    def test_cross_agency_deposit_does_not_mark_order_installed(self):
        invoice = dict(self.invoice, is_deposit=True)

        forecast, matches, unmatched = build_chantier_forecast(
            pd.DataFrame([self.order]), pd.DataFrame([invoice]), today="2026-11-25"
        )

        self.assertFalse(bool(forecast.iloc[0]["is_installed"]))
        self.assertTrue(bool(forecast.iloc[0]["has_deposit"]))
        self.assertEqual(len(matches), 1)
        self.assertTrue(unmatched.empty)

    def test_common_seller_in_second_position_and_normalized_reference_match(self):
        invoice = invoice_row("", "LEBAILLY\nDEVIS   MENUISERIE")
        invoice.update({
            "amount_ht": 5213.270000000001,
            "seller_1": "Autre vendeur",
            "seller_2": "PERTUISEL Jeremy",
        })
        set_agency(invoice, "SIEGE")

        matches, unmatched = match_invoices_to_orders(
            pd.DataFrame([self.order]), pd.DataFrame([invoice])
        )

        self.assertTrue(unmatched.empty)
        self.assertEqual(matches.iloc[0]["order_no"], "CDPERT04075")

    def test_manual_validation_is_not_overridden_by_new_automatic_match(self):
        other = order_row("CDPERT09999", "LEBAILLY autre chantier")

        forecast, matches, unmatched = build_chantier_forecast(
            pd.DataFrame([self.order, other]), pd.DataFrame([self.invoice]),
            today="2026-11-25",
            manual_invoice_matches={"FACT03987": ["CDPERT09999"]},
        )

        self.assertEqual(matches.iloc[0]["order_no"], "CDPERT09999")
        self.assertEqual(matches.iloc[0]["confidence"], "Validation manuelle")
        self.assertFalse(bool(forecast.iloc[0]["is_installed"]))
        self.assertTrue(bool(forecast.iloc[1]["is_installed"]))
        self.assertTrue(unmatched.empty)

    def test_invalid_manual_validation_does_not_suppress_automatic_match(self):
        _, matches, unmatched = build_chantier_forecast(
            pd.DataFrame([self.order]), pd.DataFrame([self.invoice]),
            today="2026-11-25",
            manual_invoice_matches={"FACT03987": ["CD_UNKNOWN"]},
        )

        self.assertEqual(matches.iloc[0]["order_no"], "CDPERT04075")
        self.assertTrue(unmatched.empty)

    def test_new_match_archives_notes_from_global_and_month_tabs(self):
        from chantier_google_sheet import build_tracking_payload

        forecast, matches, _ = build_chantier_forecast(
            pd.DataFrame([self.order]), pd.DataFrame([self.invoice]),
            today="2026-11-25",
        )
        old_row = [
            "Avril 2026", "CDPERT04075", "LEBAILLY devis menuiserie", "MEN",
            "Pose possible", 5213.27, "16/04/2026", "16/06/2026", "HARFLEUR",
            "PERTUISEL Jeremy", "Reference affaire", "MOYENNE",
            "Note du rapport conservee", "-",
        ]
        month_row = list(old_row)
        month_row[12:] = [
            "Aucune note retrouvee dans le rapport", "Question Joseph conservee",
        ]
        headers = [["TITLE"], ["SUBTITLE"], [], ["headers"]]

        payload = build_tracking_payload(
            forecast, matches, headers + [old_row], [], now="2026-11-25",
            additional_note_rows=[headers + [month_row]],
        )

        self.assertEqual(payload["active_rows"], [])
        self.assertEqual(len(payload["new_archive_rows"]), 1)
        self.assertEqual(payload["new_archive_rows"][0][12:15], [
            "Note du rapport conservee", "Question Joseph conservee", "FACT03987",
        ])

    def test_close_amount_with_different_agency_is_suggested_not_auto_matched(self):
        invoice = dict(self.invoice, amount_ht=5210.0)
        forecast, matches, unmatched = build_chantier_forecast(
            pd.DataFrame([self.order]), pd.DataFrame([invoice]), today="2026-11-25"
        )

        potential = find_potential_invoice_matches(forecast, unmatched)

        self.assertTrue(matches.empty)
        self.assertEqual(len(potential), 1)
        self.assertEqual(potential.iloc[0]["candidate_order_no"], "CDPERT04075")
        self.assertIn("SIEGE", potential.iloc[0]["non_match_reason"])
        self.assertIn("HARFLEUR", potential.iloc[0]["non_match_reason"])
        self.assertIn("montant", potential.iloc[0]["non_match_reason"].lower())

    def test_different_agency_without_common_seller_is_not_suggested(self):
        invoice = dict(self.invoice, seller_1="Autre vendeur")
        forecast, _, unmatched = build_chantier_forecast(
            pd.DataFrame([self.order]), pd.DataFrame([invoice]), today="2026-11-25"
        )

        self.assertTrue(find_potential_invoice_matches(forecast, unmatched).empty)


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


class ExtendedPotentialMatchingTests(unittest.TestCase):
    def proposals(self, orders, invoices):
        forecast, matches, _ = build_chantier_forecast(
            pd.DataFrame(orders), pd.DataFrame(invoices), today="2026-11-25"
        )
        potential = find_potential_invoice_matches(
            forecast[~forecast["is_installed"]], pd.DataFrame(invoices), forecast
        )
        return potential, forecast, matches

    def test_already_assigned_invoice_suggests_old_dubuc_and_piednoel_orders(self):
        for client, old_no, new_no, old_amount, new_amount in [
            ("DUBUC menuiserie", "CDGELL03917", "CDGELL04141", 7488.15, 8056.87),
            ("PIEDNOEL PORTE D'ENTREE", "CDPRIE04254", "CDPRIE04320", 4586.29, 4142.18),
        ]:
            with self.subTest(client=client):
                old = dict(order_row(old_no, client), amount_ht=old_amount)
                new = dict(order_row(new_no, client), amount_ht=new_amount)
                invoice = dict(invoice_row(new_no, client), amount_ht=new_amount)
                result, forecast, _ = self.proposals([old, new], [invoice])
                self.assertEqual(len(result), 1)
                row = result.iloc[0]
                self.assertEqual(row["candidate_order_no"], old_no)
                self.assertEqual(row["existing_order_no"], new_no)
                self.assertIn("doublon", row["potential_kind"])
                self.assertEqual(set(row["validation_matches"]["FACT_TEST"]), {old_no, new_no})
                self.assertFalse(bool(forecast.iloc[0]["is_installed"]))

    def test_alexandre_extra_is_suggested_with_already_billed_initial_order(self):
        main = dict(order_row("CDGELL04273", "ALEXANDRE ISOLATION EXTERIEURE"), amount_ht=23849.33)
        extra = dict(order_row("CDGELL04613", "ALEXANDRE PLUS VALUE ITE"), amount_ht=8530.82)
        invoice = dict(invoice_row("CDGELL04612", main["client_ref"]), amount_ht=32701.40)
        result, forecast, _ = self.proposals([main, extra], [invoice])
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertIn("Regroupement", row["potential_kind"])
        self.assertAlmostEqual(row["candidate_amount_ht"], 32380.15)
        self.assertAlmostEqual(row["amount_difference_ht"], 321.25)
        self.assertEqual(set(row["candidate_order_keys"].split("|")), {"CDGELL04273", "CDGELL04613"})
        self.assertFalse(bool(forecast.iloc[1]["is_installed"]))

    def papon_documents(self):
        carport = dict(order_row("CDSCOL04214", "PAPON car port"), amount_ht=27166.25)
        window = dict(order_row("CDPERT03986", "PAPON fenetre"), amount_ht=4454.98)
        copy = dict(order_row("CDSCOL04214b", "PAPON car port + fenetre test POUR PAYE", "2026-06-11"), amount_ht=32349.97)
        first = dict(invoice_row("CDSCOL04214", "PAPON car port", "CH"), invoice_no="FACT04327", amount_ht=27166.25, invoice_date=pd.Timestamp("2026-11-13"))
        second = dict(invoice_row("CDPERT03986", "PAPON fenetre"), invoice_no="FACT03883", amount_ht=4454.98, invoice_date=pd.Timestamp("2026-06-09"))
        return [carport, window, copy], [first, second]

    def test_papon_groups_two_invoices_without_using_notes(self):
        orders, invoices = self.papon_documents()
        result, forecast, _ = self.proposals(orders, invoices)
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["candidate_order_no"], "CDSCOL04214b")
        self.assertEqual(set(row["validation_matches"]), {"FACT04327", "FACT03883"})
        self.assertAlmostEqual(row["invoice_amount_ht"], 31621.23)
        self.assertAlmostEqual(row["amount_difference_ht"], 728.74)
        self.assertIn("chronologie", row["non_match_reason"])
        self.assertIn("CDSCOL04214", row["validation_matches"]["FACT04327"])
        self.assertIn("CDPERT03986", row["validation_matches"]["FACT03883"])
        self.assertFalse(bool(forecast.iloc[2]["is_installed"]))

    def test_group_validation_uses_real_invoice_numbers_and_keeps_other_links(self):
        orders, invoices = self.papon_documents()
        potential, _, _ = self.proposals(orders, invoices)
        existing = {"FACT_OTHER": ["CD_OTHER"], "FACT04327": ["CD_CUSTOM"]}
        saved = merge_potential_invoice_matches(existing, potential.to_dict("records"))
        self.assertEqual(set(saved), {"FACT_OTHER", "FACT04327", "FACT03883"})
        self.assertEqual(set(saved["FACT04327"]), {"CD_CUSTOM", "CDSCOL04214", "CDSCOL04214B"})
        self.assertEqual(existing, {"FACT_OTHER": ["CD_OTHER"], "FACT04327": ["CD_CUSTOM"]})

    def test_validating_group_does_not_reopen_previously_installed_orders(self):
        orders, invoices = self.papon_documents()
        potential, _, _ = self.proposals(orders, invoices)
        saved = merge_potential_invoice_matches({}, potential.to_dict("records"))
        forecast, matches, _ = build_chantier_forecast(
            pd.DataFrame(orders), pd.DataFrame(invoices), today="2026-11-25",
            manual_invoice_matches=saved,
        )
        self.assertTrue(forecast["is_installed"].all())
        self.assertEqual(len(matches), 4)

    def test_two_selected_proposals_for_same_invoice_are_merged(self):
        result = merge_potential_invoice_matches({}, [
            {"validation_matches": {"FACT1": ["CD1", "CD2"]}},
            {"validation_matches": {"FACT1": ["CD1", "CD3"]}},
        ])
        self.assertEqual(result, {"FACT1": ["CD1", "CD2", "CD3"]})

    def test_notes_do_not_influence_results(self):
        orders, invoices = self.papon_documents()
        expected, _, _ = self.proposals(orders, invoices)
        for order in orders:
            order.update({"report_note": "annule / facture", "joseph_note": "pose"})
        actual, _, _ = self.proposals(orders, invoices)
        pd.testing.assert_frame_equal(expected, actual)

    def test_ebran_other_product_is_not_suggested_even_with_close_amount(self):
        old = dict(order_row("CD03820", "EBRAN pe fe vr solaire velux"), amount_ht=33080.57)
        remaining = dict(order_row("CDBOCQ04286", "EBRAN RAVAL ITE RESINE"), amount_ht=33203.79)
        invoice = dict(invoice_row("CD03820", old["client_ref"]), amount_ht=33080.57)
        result, _, _ = self.proposals([old, remaining], [invoice])
        self.assertTrue(result.empty)

    def test_assigned_invoice_requires_a_common_seller(self):
        old = order_row("CD1", "CLIENT menuiserie")
        current = order_row("CD2", "CLIENT menuiserie")
        invoice = invoice_row("CD2", "CLIENT menuiserie")
        old["seller_1"] = "OTHER SELLER"
        result, _, _ = self.proposals([old, current], [invoice])
        self.assertTrue(result.empty)

    def test_deposits_credits_and_empty_inputs_do_not_generate_proposals(self):
        order = order_row("CD1", "CLIENT fenetre")
        for invoice in [
            dict(invoice_row("CD2", "CLIENT acompte fenetre"), is_deposit=True),
            dict(invoice_row("CD2", "CLIENT fenetre"), amount_ht=-10000),
            dict(invoice_row("CD2", "CLIENT fenetre"), is_credit=True),
        ]:
            with self.subTest(invoice=invoice):
                self.assertTrue(find_potential_invoice_matches(pd.DataFrame([order]), pd.DataFrame([invoice])).empty)
        self.assertTrue(find_potential_invoice_matches(pd.DataFrame(), pd.DataFrame()).empty)

    def test_n1_and_dates_are_not_relaxed_without_a_copy_number(self):
        orders, invoices = self.papon_documents()
        orders[-1]["order_no"] = orders[-1]["order_key"] = "CD_NEW"
        result, _, _ = self.proposals(orders, invoices)
        self.assertTrue(result.empty)

    def test_explicit_old_year_is_not_bundled_even_with_copy_number(self):
        orders, invoices = self.papon_documents()
        invoices[0]["sale_month_label"] = "JUIN 25"
        result, _, _ = self.proposals(orders, invoices)
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
