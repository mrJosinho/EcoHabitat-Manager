import ast
import copy
from datetime import datetime
from pathlib import Path
import re
import unicodedata
import unittest

import numpy as np
import pandas as pd

from agency_source import (
    GERANTS,
    agency_detail_rows,
    agency_sale_breakdown,
    agency_sale_shares,
    eligible_agency_sales,
    gerant_name,
)
from commission_source import normalize_commission_columns


SELLERS = ["Commercial", "Commercial 2", "Commercial 3"]
AMOUNTS = ["CA", "Vente", "Catalogue", "Remise"]


def sale(document, names, amount=30000, agency="HARFLEUR", opc="NON"):
    return {
        "Doc": document, "Client": document, "Agence": agency,
        "CA": amount, "Vente": amount / max(1, len(names)),
        "Catalogue": amount * 1.1, "Remise": amount * 0.1, "OPC": opc,
        **dict(zip(SELLERS, list(names) + [""] * (3 - len(names)))),
    }


def load_app_functions(*names, overrides=None):
    # Load the real calculation functions without starting the Streamlit app.
    tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
    definitions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    months = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "MOIS_FR" for target in node.targets))
    namespace = {
        "pd": pd, "np": np, "unicodedata": unicodedata, "copy": copy, "datetime": datetime,
        "re": re,
        "agency_detail_rows": agency_detail_rows,
        "eligible_agency_sales": eligible_agency_sales,
        "agency_sale_breakdown": agency_sale_breakdown,
        "gerant_name": gerant_name,
        "normalize_commission_columns": normalize_commission_columns,
        "MOIS_FR": ast.literal_eval(months),
        "directeur_result_agences_for_period": lambda name, period: ["HARFLEUR"],
        **(overrides or {}),
    }
    selected = {}
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in selected or name in namespace:
            continue
        node = copy.deepcopy(definitions[name])
        node.decorator_list = []
        selected[name] = node
        pending.extend(
            reference.id for reference in ast.walk(node)
            if isinstance(reference, ast.Name) and reference.id in definitions
        )
    module = ast.Module(body=list(selected.values()), type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "app_calculations", "exec"), namespace)
    return namespace


class GerantAffairesAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load_app_functions(
            "can_access_gerant_affaires", "can_access_agence_detail", "build_detail_agence_pdf",
        )

    def test_four_manager_admin_sessions_have_access(self):
        for name in GERANTS:
            with self.subTest(name=name):
                self.assertTrue(self.functions["can_access_gerant_affaires"]({
                    "nom": name.title(), "role": "admin",
                }))

    def test_other_administrators_have_no_access(self):
        for name in ["Administrateur", "AYACHE Adel", "EL GHAZOUANI Nahim", "GELLY Gaetan", ""]:
            with self.subTest(name=name):
                self.assertFalse(self.functions["can_access_gerant_affaires"]({
                    "nom": name, "role": "admin",
                }))

    def test_non_admin_and_missing_sessions_have_no_access(self):
        for role in ["vendeur", "directeur_agence", "secretaire", ""]:
            self.assertFalse(self.functions["can_access_gerant_affaires"]({
                "nom": "LUCCHINI JOSEPH", "role": role,
            }))
        for session in [None, {}, "admin", {"role": "admin"}]:
            self.assertFalse(self.functions["can_access_gerant_affaires"](session))

    def test_report_and_download_are_inside_the_access_guard(self):
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
        annual = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "afficher_annuel")
        guard = next(node for node in ast.walk(annual) if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Call)
                     and isinstance(node.test.func, ast.Name)
                     and node.test.func.id == "can_access_gerant_affaires")
        calls = [node for node in ast.walk(guard) if isinstance(node, ast.Call)]
        self.assertTrue(any(isinstance(call.func, ast.Name)
                            and call.func.id == "load_gerant_affaires_cached" for call in calls))
        self.assertTrue(any(isinstance(call.func, ast.Attribute)
                            and call.func.attr == "download_button" for call in calls))

    def test_agency_detail_is_guarded_after_the_totals_and_before_any_details(self):
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
        agency = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == "afficher_agence")
        body = agency.body[0].body
        guard_index = next(i for i, node in enumerate(body) if isinstance(node, ast.If)
                           and isinstance(node.test, ast.UnaryOp)
                           and isinstance(node.test.operand, ast.Call)
                           and isinstance(node.test.operand.func, ast.Name)
                           and node.test.operand.func.id == "can_access_agence_detail")
        self.assertIsInstance(body[guard_index].body[0], ast.Return)
        before = ast.Module(body=body[:guard_index], type_ignores=[])
        after = ast.Module(body=body[guard_index + 1:], type_ignores=[])
        self.assertTrue(any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                            and call.func.id == "card" for call in ast.walk(before)))
        self.assertFalse(any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                             and call.func.attr == "download_button" for call in ast.walk(before)))
        self.assertTrue(any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "download_button" for call in ast.walk(after)))

    def test_agency_pdf_rejects_unauthorized_sessions_before_reading_any_data(self):
        for session in [None, {}, {"nom": "AUTRE ADMINISTRATEUR", "role": "admin"},
                        {"nom": "AYACHE ADEL", "role": "directeur_agence"}]:
            with self.subTest(session=session):
                self.assertEqual(self.functions["build_detail_agence_pdf"](
                    "HARFLEUR", {}, None, None, [], {}, "Janvier 2026", user_data=session,
                ), (None, None))

    def test_four_managers_can_still_get_agency_pdfs(self):
        df = pd.DataFrame([sale("A", ["LAVISSE Fabien", "SCOLAN Marc"])])
        cols = {
            "client": "Client", "doc": "Doc", "date": None, "agence": "Agence",
            "vente": "Vente", "ca_magasin": "CA", "catalogue": "Catalogue",
            "rem": "Remise", "op": "OPC", "commerciaux": SELLERS,
        }
        for name in GERANTS:
            detail, metrics = self.functions["build_detail_agence_pdf"](
                "HARFLEUR", {}, df, df.iloc[:0], ["Doc"], cols, "Janvier 2026",
                user_data={"nom": name, "role": "admin"},
            )
            self.assertEqual(len(detail), 1)
            self.assertEqual(detail.iloc[0]["CA retenu agence HT"], 15000)
            self.assertIn("CA OK agence", metrics)

    def test_bulk_agency_pdf_call_is_guarded_and_has_the_authenticated_user(self):
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "build_detail_agence_pdf"]
        self.assertTrue(calls)
        for call in calls:
            self.assertTrue(any(keyword.arg == "user_data" and isinstance(keyword.value, ast.Name)
                                and keyword.value.id == "user" for keyword in call.keywords))
            ancestors = []
            node = call
            while node in parents:
                node = parents[node]
                ancestors.append(node)
            self.assertTrue(any(isinstance(node, ast.If)
                                and "can_access_gerant_affaires(user)" in ast.unparse(node.test)
                                for node in ancestors))


class DirectorAgencyDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load_app_functions("can_access_agence_detail", "build_detail_agence_pdf")

    def test_nahim_only_has_his_period_agencies(self):
        session = {"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"}
        allowed = self.functions["can_access_agence_detail"]
        self.assertTrue(allowed(session, "HARFLEUR", "Octobre 2026"))
        self.assertTrue(allowed(session, "MAROMME", "Octobre 2026"))
        self.assertFalse(allowed(session, "YVETOT", "Octobre 2026"))
        self.assertFalse(allowed(session, "BOURG ACHARD", "Octobre 2026"))
        self.assertFalse(allowed(session, "MAROMME", "Mai 2026"))
        self.assertTrue(allowed(session, "MAROMME", "Juin 2026"))

    def test_other_directors_keep_their_own_scope(self):
        allowed = self.functions["can_access_agence_detail"]
        adel = {"nom": "AYACHE Adel", "role": "directeur_agence"}
        self.assertTrue(allowed(adel, "MAROMME", "Mai 2026"))
        self.assertTrue(allowed(adel, "YVETOT", "Octobre 2026"))
        self.assertFalse(allowed(adel, "MAROMME", "Octobre 2026"))
        gaetan = {"nom": "GELLY Gaetan", "role": "directeur_agence"}
        self.assertTrue(allowed(gaetan, "BOURG ACHARD", "Octobre 2026"))
        self.assertFalse(allowed(gaetan, "HARFLEUR", "Octobre 2026"))

    def test_configured_director_scope_and_missing_session_are_fail_closed(self):
        allowed = self.functions["can_access_agence_detail"]
        configured = {"nom": "NOUVEAU Directeur", "role": "directeur_agence", "agences": "Harfleur; Yvetot"}
        self.assertTrue(allowed(configured, "yvetot", "Octobre 2026"))
        self.assertFalse(allowed(configured, "MAROMME", "Octobre 2026"))
        self.assertFalse(allowed(configured, "", "Octobre 2026"))
        self.assertFalse(allowed(configured, "HARFLEUR", ""))
        self.assertFalse(allowed({"role": "directeur_agence"}, "HARFLEUR", "Octobre 2026"))
        for session in [None, {}, "admin", {"nom": "SCOLAN Marc", "role": "vendeur"},
                        {"nom": "AUTRE ADMIN", "role": "admin"}, {"role": "secretaire"}]:
            with self.subTest(session=session):
                self.assertFalse(allowed(session, "HARFLEUR", "Octobre 2026"))

    def test_director_pdf_hides_solo_and_shared_manager_jobs_for_ok_and_pending(self):
        columns = list(sale("A", ["SCOLAN Marc"]))
        ok = pd.DataFrame([
            sale("solo", ["LUCCHINI Joseph"]),
            sale("shared", ["SCOLAN Marc", "PETIT Lilian"]),
            sale("visible_ok", ["SCOLAN Marc"]),
            sale("other_agency", ["SCOLAN Marc"], agency="YVETOT"),
        ], columns=columns)
        pending = pd.DataFrame([
            sale("shared_pending", ["SCOLAN Marc", "GELLY Gaetan", "LAVISSE Guillaume"]),
            sale("solo_pending", ["LAVISSE Fabien"]),
            sale("visible_pending", ["GELLY Gaetan"]),
        ], columns=columns)
        originals = [frame.copy(deep=True) for frame in (ok, pending)]
        cols = {"client": "Client", "doc": "Doc", "date": None, "agence": "Agence", "vente": "Vente",
                "ca_magasin": "CA", "catalogue": "Catalogue", "rem": "Remise", "op": "OPC", "commerciaux": SELLERS}
        detail, metrics = self.functions["build_detail_agence_pdf"](
            "HARFLEUR", {"ca_ok": 45000}, ok, pending, ["Doc"], cols, "Octobre 2026",
            user_data={"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"},
        )
        self.assertEqual(set(detail["Doc"]), {"visible_ok", "visible_pending"})
        self.assertEqual(set(detail["Statut"]), {"OK", "En attente"})
        self.assertEqual(metrics["CA OK agence"], "45,000.00 EUR")
        for original, frame in zip(originals, (ok, pending)):
            pd.testing.assert_frame_equal(original, frame)

    def test_director_cannot_request_another_agency_pdf(self):
        self.assertEqual(self.functions["build_detail_agence_pdf"](
            "YVETOT", {}, None, None, [], {}, "Octobre 2026",
            user_data={"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"},
        ), (None, None))

    def test_all_hidden_jobs_return_no_pdf_instead_of_an_empty_private_report(self):
        df = pd.DataFrame([sale("secret", ["PETIT Lilian", "SCOLAN Marc"])])
        cols = {"client": "Client", "doc": "Doc", "date": None, "agence": "Agence", "vente": "Vente",
                "ca_magasin": "CA", "catalogue": "Catalogue", "rem": "Remise", "op": "OPC", "commerciaux": SELLERS}
        self.assertEqual(self.functions["build_detail_agence_pdf"](
            "HARFLEUR", {}, df, df.iloc[:0], ["Doc"], cols, "Octobre 2026",
            user_data={"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"},
        ), (None, None))


class AgencyDetailRowsTests(unittest.TestCase):
    def test_all_four_managers_and_aliases_are_hidden_in_every_seller_position(self):
        for manager in [*GERANTS, "Joseph LUCCHIN", "Lilian PETIT"]:
            for position in range(3):
                names = ["SCOLAN Marc", "GELLY Gaetan"]
                names.insert(position, manager)
                with self.subTest(manager=manager, position=position):
                    self.assertTrue(agency_detail_rows(pd.DataFrame([sale("secret", names)]), SELLERS).empty)

    def test_ordinary_jobs_keep_their_values_and_null_sellers(self):
        df = pd.DataFrame([sale("A", ["SCOLAN Marc", "GELLY Gaetan", None]), sale("B", [])])
        pd.testing.assert_frame_equal(agency_detail_rows(df, SELLERS), df)

    def test_full_view_is_a_copy_and_input_is_never_mutated(self):
        df = pd.DataFrame([sale("A", ["LAVISSE Guillaume"]), sale("B", ["SCOLAN Marc"])])
        before = df.copy(deep=True)
        self.assertEqual(list(agency_detail_rows(df, SELLERS)["Doc"]), ["B"])
        full = agency_detail_rows(df, SELLERS, include_gerants=True)
        pd.testing.assert_frame_equal(full, before)
        full.loc[0, "CA"] = 0
        pd.testing.assert_frame_equal(df, before)

    def test_missing_commercial_columns_are_not_exposed_to_restricted_views(self):
        df = pd.DataFrame([{"Client": "Unknown seller", "CA": 20000}])
        self.assertTrue(agency_detail_rows(df, SELLERS).empty)
        self.assertTrue(agency_detail_rows(df, None).empty)
        pd.testing.assert_frame_equal(agency_detail_rows(df, None, include_gerants=True), df)
        self.assertTrue(agency_detail_rows(df.iloc[:0], SELLERS).empty)

    def test_duplicate_source_indices_are_kept_without_duplicate_or_hidden_rows(self):
        df = pd.DataFrame([sale("A", ["SCOLAN Marc"]), sale("B", ["PETIT Lilian"])], index=[4, 4])
        self.assertEqual(list(agency_detail_rows(df, SELLERS)["Doc"]), ["A"])

    def test_shared_seller_share_stays_in_totals_after_the_detail_is_filtered(self):
        df = pd.DataFrame([sale("solo", ["LUCCHINI Joseph"]),
                           sale("shared", ["PETIT Lilian", "SCOLAN Marc"]),
                           sale("visible", ["SCOLAN Marc"])])
        before = eligible_agency_sales(df, SELLERS, AMOUNTS)["CA"].sum()
        self.assertEqual(list(agency_detail_rows(df, SELLERS)["Doc"]), ["visible"])
        self.assertEqual(before, 45000)
        self.assertEqual(eligible_agency_sales(df, SELLERS, AMOUNTS)["CA"].sum(), before)


class AgencyDetailViewTests(unittest.TestCase):
    def render(self, session, generate_pdf=False):
        namespace = load_app_functions(
            "can_access_agence_detail", "agence_mask", "remove_attente_already_ok",
            "list_commerciaux_row", "safe_filename", "to_float",
        )
        rows = [sale("regular", ["SCOLAN Marc"]), sale("solo", ["PETIT Lilian"]),
                sale("shared", ["SCOLAN Marc", "LAVISSE Guillaume"])]
        pending = [sale("pending", ["SCOLAN Marc"]), sale("secret_pending", ["LAVISSE Fabien"])]
        captured = {"tables": [], "pdfs": [], "downloads": [], "alerts": []}

        class State(dict):
            __getattr__ = dict.__getitem__

        class Surface:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def columns(self, *args):
                return [self] * 5

            def container(self):
                return self

            def button(self, *args, **kwargs):
                return generate_pdf

            def download_button(self, label, payload, *args, **kwargs):
                captured["downloads"].append(payload)

            def caption(self, *args):
                pass

            info = subheader = write = caption

        ui = Surface()
        ui.session_state = State({
            "df_ok": pd.DataFrame(rows), "df_c": pd.DataFrame(pending),
            "col_client": "Client", "col_doc": "Doc", "col_date": None,
            "col_agence": "Agence", "col_vente": "Vente", "col_ca_magasin": "CA",
            "col_catalogue": "Catalogue", "col_rem": "Remise", "col_op": "OPC",
            "col_com1": SELLERS[0], "col_com2": SELLERS[1], "col_com3": SELLERS[2],
            "key_cols": ["Doc"],
            "pdf_cache_agence_HARFLEUR_Octobre 2026": b"legacy-private-pdf",
            "pdf_cache_agence_v2_gerants_HARFLEUR_Octobre 2026": b"manager-private-pdf",
        })

        def make_pdf(title, metrics, frame):
            captured["pdfs"].append(frame.copy())
            return b"filtered-pdf"

        namespace.update({
            "st": ui, "user": session, "role": session["role"], "periode": "Octobre 2026",
            "df_agences": pd.DataFrame([{"agence": "HARFLEUR", "ca_ok": 45000,
                                         "ca_attente": 30000, "ca_total": 75000,
                                         "remise_pct": 9.09, "nb_ok": 2}]),
            "card": lambda *args: None,
            "agence_is_result_for_directeur": lambda *args: True,
            "load_motifs_attente": lambda: {},
            "make_attente_tracking_key": lambda row, *args: row["Doc"],
            "afficher_alerte_hors_periode": lambda frame, *args: captured["alerts"].append(frame.copy()),
            "render_table_with_status_tooltips": lambda frame, **kwargs: captured["tables"].append(frame.copy()),
            "make_simple_pdf": make_pdf, "is_render_env": lambda: True,
        })
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
        view = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                    and node.name == "afficher_agence")
        exec(compile(ast.fix_missing_locations(ast.Module(body=[view], type_ignores=[])),
                     "agency_view", "exec"), namespace)
        namespace["afficher_agence"](ui, agence_forced="HARFLEUR")
        return captured, ui.session_state

    def test_nahim_table_alerts_and_pdf_only_receive_visible_jobs(self):
        captured, state = self.render({"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"}, True)
        for kind in ("tables", "pdfs", "alerts"):
            with self.subTest(kind=kind):
                self.assertEqual(len(captured[kind]), 1)
                self.assertEqual(set(captured[kind][0]["Doc"]), {"regular", "pending"})
        self.assertEqual(captured["downloads"], [b"filtered-pdf"])
        self.assertEqual(state["pdf_cache_agence_v2_hors_gerants_HARFLEUR_Octobre 2026"], b"filtered-pdf")
        self.assertEqual(len(state["df_ok"]), 3)
        self.assertEqual(len(state["df_c"]), 2)

    def test_old_or_full_manager_pdf_cache_is_not_reused_by_directors(self):
        captured, _ = self.render({"nom": "EL GHAZOUANI Nahim", "role": "directeur_agence"})
        self.assertEqual(captured["pdfs"], [])
        self.assertEqual(captured["downloads"], [])
        self.assertEqual(set(captured["tables"][0]["Doc"]), {"regular", "pending"})

    def test_manager_keeps_full_table_and_pdf(self):
        captured, state = self.render({"nom": "LUCCHINI Joseph", "role": "admin"}, True)
        expected = {"regular", "pending", "solo", "shared", "secret_pending"}
        self.assertEqual(set(captured["tables"][0]["Doc"]), expected)
        self.assertEqual(set(captured["pdfs"][0]["Doc"]), expected)
        self.assertEqual(state["pdf_cache_agence_v2_gerants_HARFLEUR_Octobre 2026"], b"filtered-pdf")

    def test_unrelated_director_does_not_receive_table_or_pdf(self):
        captured, _ = self.render({"nom": "AYACHE Adel", "role": "directeur_agence"}, True)
        self.assertEqual(captured["tables"], [])
        self.assertEqual(captured["pdfs"], [])
        self.assertEqual(captured["downloads"], [])


class AgencySharesTests(unittest.TestCase):
    def test_only_the_four_managers_and_known_aliases_are_excluded(self):
        for name in GERANTS:
            with self.subTest(name=name):
                self.assertEqual(gerant_name(name.title()), name)
                self.assertEqual(gerant_name(" ".join(reversed(name.split()))), name)
        self.assertEqual(gerant_name(" LUCCHIN\u00a0Joseph "), "LUCCHINI JOSEPH")
        for name in ["AYACHE Adel", "EL GHAZOUANI Nahim", "GELLY Gaetan", "PETIT Lillian", ""]:
            self.assertEqual(gerant_name(name), "")

    def test_manager_only_is_not_counted_for_the_agency(self):
        for name in GERANTS:
            df = pd.DataFrame([sale("A", [name])])
            self.assertEqual(agency_sale_shares(df, SELLERS).iloc[0], 0)
            self.assertTrue(eligible_agency_sales(df, SELLERS, AMOUNTS).empty)

    def test_manager_in_each_position_keeps_one_original_seller_share(self):
        for names in [["PETIT Lilian", "SCOLAN Marc"], ["SCOLAN Marc", "PETIT Lilian"]]:
            with self.subTest(names=names):
                df = pd.DataFrame([sale("A", names)])
                result = eligible_agency_sales(df, SELLERS, AMOUNTS)
                self.assertEqual(result.iloc[0]["CA"], 15000)
                self.assertEqual(result.iloc[0]["Commercial"], names[0])

    def test_three_people_keep_two_thirds_without_redistribution(self):
        for position in range(3):
            names = ["SCOLAN Marc", "GELLY Gaetan"]
            names.insert(position, "LAVISSE Guillaume")
            result = eligible_agency_sales(pd.DataFrame([sale("A", names)]), SELLERS, AMOUNTS)
            self.assertAlmostEqual(result.iloc[0]["CA"], 20000)
            self.assertAlmostEqual(result.iloc[0]["Catalogue"], 22000)
            self.assertAlmostEqual(result.iloc[0]["Remise"], 2000)

    def test_two_managers_keep_only_one_seller_third(self):
        df = pd.DataFrame([sale("A", ["LUCCHINI Joseph", "SCOLAN Marc", "PETIT Lilian"])])
        self.assertAlmostEqual(eligible_agency_sales(df, SELLERS, AMOUNTS).iloc[0]["CA"], 10000)

    def test_regular_sales_and_missing_seller_data_keep_existing_values(self):
        df = pd.DataFrame([
            sale("A", ["AYACHE Adel", "SCOLAN Marc"]),
            sale("B", []),
        ])
        result = eligible_agency_sales(df, SELLERS, AMOUNTS)
        pd.testing.assert_frame_equal(result, df, check_dtype=False)
        pd.testing.assert_frame_equal(eligible_agency_sales(df, None, AMOUNTS), df, check_dtype=False)

    def test_null_sellers_do_not_dilute_the_remaining_share(self):
        df = pd.DataFrame([sale("A", ["PETIT Lilian", "SCOLAN Marc", None])])
        self.assertEqual(agency_sale_shares(df, SELLERS).iloc[0], 0.5)

    def test_empty_input_is_safe(self):
        self.assertTrue(eligible_agency_sales(pd.DataFrame(), SELLERS, AMOUNTS).empty)
        self.assertTrue(agency_sale_breakdown(pd.DataFrame(), SELLERS, "CA").empty)

    def test_inputs_and_seller_commission_fields_are_not_modified(self):
        df = pd.DataFrame([sale("A", ["LAVISSE Fabien", "SCOLAN Marc"])])
        original = df.copy(deep=True)
        eligible_agency_sales(df, SELLERS, AMOUNTS)
        breakdown = agency_sale_breakdown(df, SELLERS, "CA")
        pd.testing.assert_frame_equal(df, original)
        pd.testing.assert_frame_equal(breakdown[original.columns], original)
        self.assertEqual(breakdown.iloc[0]["manager_amount_ht"], 15000)
        self.assertEqual(breakdown.iloc[0]["agency_amount_ht"], 15000)

    def test_shared_negative_adjustment_uses_the_same_split(self):
        df = pd.DataFrame([sale("A", ["PETIT Lilian", "SCOLAN Marc"], amount=-1000)])
        self.assertEqual(eligible_agency_sales(df, SELLERS, AMOUNTS).iloc[0]["CA"], -500)

    def test_same_amount_column_is_scaled_only_once(self):
        df = pd.DataFrame([sale("A", ["PETIT Lilian", "SCOLAN Marc"])])
        self.assertEqual(eligible_agency_sales(df, SELLERS, ["CA", "CA"]).iloc[0]["CA"], 15000)

    def test_duplicate_source_indices_do_not_duplicate_the_shares(self):
        df = pd.DataFrame([
            sale("A", ["PETIT Lilian", "SCOLAN Marc"]),
            sale("B", ["LAVISSE Fabien", "GELLY Gaetan"]),
        ], index=[7, 7])
        self.assertEqual(list(eligible_agency_sales(df, SELLERS, AMOUNTS)["CA"]), [15000, 15000])


class AgencyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load_app_functions(
            "recompute_df_agences_attente", "recompute_saved_period",
            "build_gerant_affaires_for_period", "load_all_historique_cached",
            "load_gerant_affaires_cached",
            overrides={"list_periodes": lambda: [], "load_periode": lambda period: None},
        )

    def period(self, ok, confirm):
        columns = list(sale("A", ["SCOLAN Marc"]))
        return {
            "periode": "Janvier 2026",
            "df_ok": pd.DataFrame(ok, columns=columns),
            "df_c": pd.DataFrame(confirm, columns=columns),
            "df_agences": pd.DataFrame([{"agence": "HARFLEUR"}]),
            "df_vendeurs": pd.DataFrame([{"Commercial": "SCOLAN Marc"}]),
            "col_com1": SELLERS[0], "col_com2": SELLERS[1], "col_com3": SELLERS[2],
            "col_ca_magasin": "CA", "col_vente": "Vente", "col_catalogue": "Catalogue",
            "col_rem": "Remise", "col_agence": "Agence", "col_client": "Client",
            "col_doc": "Doc", "col_op": "OPC", "key_cols": ["Doc"],
        }

    def test_monthly_totals_director_base_and_counts_use_only_eligible_sales(self):
        rows = [sale("solo", ["LUCCHINI Joseph"]), sale("duo", ["PETIT Lilian", "SCOLAN Marc"])]
        pending = sale("trio", ["SCOLAN Marc", "GELLY Gaetan", "LAVISSE Guillaume"])
        period = self.period(rows, rows + [pending])
        original = copy.deepcopy(period)
        result = self.functions["recompute_saved_period"](copy.deepcopy(period))
        agency = result["df_agences"].iloc[0]
        self.assertEqual(agency.ca_ok, 15000)
        self.assertEqual(agency.ca_attente, 20000)
        self.assertEqual(agency.ca_total, 35000)
        self.assertEqual(agency.nb_ok, 1)
        self.assertEqual(agency.nb_total, 2)
        self.assertEqual(result["df_directeurs"].iloc[0].ca_magasin_ok, 15000)
        self.assertEqual(result["df_directeurs"].iloc[0].un_pourcent_ca, 150)
        for key in ("df_ok", "df_c", "df_vendeurs", "df_agences"):
            pd.testing.assert_frame_equal(period[key], original[key])
        self.assertEqual(result["df_vendeurs"].iloc[0].ca_ok, 15000)
        self.assertEqual(result["df_vendeurs"].iloc[0].ca_attente, 10000)

    def test_discounts_and_bonus_exclude_the_manager_only_job(self):
        manager = sale("solo", ["PETIT Lilian"], amount=50000, opc="OUI")
        seller = sale("duo", ["PETIT Lilian", "SCOLAN Marc"], amount=10000)
        result = self.functions["recompute_saved_period"](self.period([manager, seller], []))
        agency = result["df_agences"].iloc[0]
        self.assertAlmostEqual(agency.remise_pct, 9.09)
        self.assertAlmostEqual(agency.bonus_malus_ok, 162.5)
        self.assertEqual(agency.nb_opc_total, 0)

    def test_history_is_recomputed_for_annual_totals_without_overwriting_saved_data(self):
        periods = {
            "Janvier 2026": self.period([sale("A", ["PETIT Lilian", "SCOLAN Marc"])], []),
            "Fevrier 2026": self.period([sale("B", ["LAVISSE Fabien"])], []),
        }
        original = copy.deepcopy(periods)
        namespace = dict(self.functions)
        self.functions["list_periodes"] = lambda: list(periods)
        self.functions["load_periode"] = lambda name: periods[name]
        try:
            vendors, agencies, directors = self.functions["load_all_historique_cached"](("test",))
            self.assertEqual(agencies.ca_ok.sum(), 15000)
            self.assertEqual(directors.ca_magasin_ok.sum(), 30000)  # Two director rules in the fixture.
            self.assertEqual(vendors.ca_ok.sum(), 15000)
            for period in periods:
                for key in ("df_ok", "df_c", "df_vendeurs", "df_agences"):
                    pd.testing.assert_frame_equal(periods[period][key], original[period][key])
        finally:
            self.functions.update(namespace)

    def test_audit_lists_all_managers_once_per_period_and_keeps_the_regular_share(self):
        shared = sale("A", ["LAVISSE Guillaume", "SCOLAN Marc"])
        solo = sale("B", ["LUCCHINI Joseph"])
        regular = sale("C", ["AYACHE Adel"])
        period = self.period([shared, regular], [shared, regular, solo])
        report = self.functions["build_gerant_affaires_for_period"](period, "Janvier 2026")
        self.assertEqual(len(report), 2)
        self.assertEqual(report["Part gérants exclue HT"].sum(), 45000)
        self.assertEqual(report["CA retenu agence HT"].sum(), 15000)
        self.assertEqual(set(report.Statut), {"OK", "En attente"})

    def test_report_includes_recent_months_outside_the_m2_annual_cutoff(self):
        periods = {
            "Septembre 2026": self.period([], [sale("A", ["PETIT Lilian"])]),
            "Novembre 2026": self.period([], [sale("B", ["LAVISSE Fabien"])]),
            "Decembre 2025": self.period([], [sale("C", ["LUCCHINI Joseph"])]),
        }
        namespace = dict(self.functions)
        self.functions["list_periodes"] = lambda: list(periods)
        self.functions["load_periode"] = lambda name: periods[name]
        try:
            report = self.functions["load_gerant_affaires_cached"](("test",), 2026)
            self.assertEqual(list(report["Période"]), ["Septembre 2026", "Novembre 2026"])
        finally:
            self.functions.update(namespace)


if __name__ == "__main__":
    unittest.main()
