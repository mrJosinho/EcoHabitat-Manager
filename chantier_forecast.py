import math
import os
import pickle
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations
from datetime import datetime
from pathlib import Path

import pandas as pd


FACTURATION_COLUMNS = [
    "invoice_no",
    "order_no",
    "invoice_date",
    "client_ref",
    "agency",
    "seller_1",
    "seller_2",
    "seller_3",
    "amount_ht",
    "sale_month_label",
    "is_deposit",
]


def clean_text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def normalize_text(value):
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def is_deposit_reference(value):
    return "ACOMPTE" in normalize_text(value).split()


def ensure_invoice_flags(invoices):
    if not isinstance(invoices, pd.DataFrame):
        return pd.DataFrame(columns=FACTURATION_COLUMNS)
    invoices = invoices.copy()
    detected = invoices.get("client_ref", pd.Series("", index=invoices.index)).map(
        is_deposit_reference
    )
    if "is_deposit" in invoices.columns:
        existing = invoices["is_deposit"].fillna(False).astype(bool)
        invoices["is_deposit"] = existing | detected
    else:
        invoices["is_deposit"] = detected
    return invoices


def _find_column(df, includes, excludes=None):
    excludes = excludes or []
    for column in df.columns:
        normalized = normalize_text(column)
        if all(normalize_text(part) in normalized for part in includes) and not any(
            normalize_text(part) in normalized for part in excludes
        ):
            return column
    return None


def _column_at(df, one_based_index):
    if 1 <= one_based_index <= len(df.columns):
        return df.columns[one_based_index - 1]
    return None


def read_facturation_export(source, source_name=""):
    df = pd.read_excel(source, skiprows=28, header=0)
    df.columns = [clean_text(column) for column in df.columns]

    col_client = _column_at(df, 1)
    col_seller_1 = _column_at(df, 2)
    col_seller_2 = _column_at(df, 3)
    col_seller_3 = _column_at(df, 4)
    col_date = _column_at(df, 6)
    col_invoice = _column_at(df, 7)
    col_amount = _find_column(df, ["TOTAL HT VENTES"]) or _column_at(df, 16)
    col_agency = _find_column(df, ["AGENCE"]) or _column_at(df, 50)
    col_sale_month = _find_column(df, ["MOIS", "VENTE"]) or _column_at(df, 49)
    col_order = (
        _find_column(df, ["COMMANDE", "CORRESPONDANT"])
        or _find_column(df, ["NUM", "COMMANDE"])
    )
    fallback_order_column = _column_at(df, 52)
    if (
        not col_order
        and fallback_order_column
        and "COMMANDE" in normalize_text(fallback_order_column)
    ):
        col_order = fallback_order_column

    required = {
        "Client / référence affaire": col_client,
        "Date document": col_date,
        "N° document": col_invoice,
        "Montant HT": col_amount,
        "Agence": col_agency,
    }
    missing = [label for label, column in required.items() if not column]
    if missing:
        raise ValueError("Colonnes de facturation introuvables : " + ", ".join(missing))

    parsed = pd.DataFrame({
        "invoice_no": df[col_invoice].map(clean_text),
        "order_no": df[col_order].map(clean_text) if col_order else "",
        "invoice_date": pd.to_datetime(df[col_date], errors="coerce"),
        "client_ref": df[col_client].map(clean_text),
        "agency": df[col_agency].map(clean_text).str.upper(),
        "seller_1": df[col_seller_1].map(clean_text) if col_seller_1 else "",
        "seller_2": df[col_seller_2].map(clean_text) if col_seller_2 else "",
        "seller_3": df[col_seller_3].map(clean_text) if col_seller_3 else "",
        "amount_ht": pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0),
        "sale_month_label": df[col_sale_month].map(clean_text) if col_sale_month else "",
    })

    parsed = parsed[
        parsed["invoice_no"].str.match(r"^(FACT|AVOIR)", case=False, na=False)
        & parsed["invoice_date"].notna()
        & parsed["client_ref"].ne("")
    ].copy()
    parsed["invoice_date"] = parsed["invoice_date"].dt.normalize()
    parsed["source_file"] = clean_text(source_name)
    parsed["is_credit"] = parsed["amount_ht"] < 0
    parsed["is_deposit"] = parsed["client_ref"].map(is_deposit_reference)
    parsed["client_key"] = parsed["client_ref"].map(normalize_text)
    parsed["agency_key"] = parsed["agency"].map(normalize_text)
    parsed["match_key"] = parsed["client_key"] + "|" + parsed["agency_key"]
    parsed["order_key"] = parsed["order_no"].map(normalize_text)
    parsed.loc[
        ~parsed["order_key"].str.match(r"^CD", case=False, na=False),
        ["order_no", "order_key"],
    ] = ""
    parsed = parsed.drop_duplicates(subset=["invoice_no"], keep="last").reset_index(drop=True)

    if parsed.empty:
        raise ValueError("Aucune facture exploitable n'a été trouvée dans ce fichier.")
    return parsed


def save_facturation_store(path, invoices, metadata=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "invoices": invoices.copy(),
        "metadata": metadata or {},
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as handle:
        pickle.dump(payload, handle)
    os.replace(tmp_path, path)


def load_facturation_store(path):
    path = Path(path)
    if not path.exists():
        return {"invoices": pd.DataFrame(columns=FACTURATION_COLUMNS), "metadata": {}}
    with open(path, "rb") as handle:
        payload = pickle.load(handle)
    if isinstance(payload, pd.DataFrame):
        return {"invoices": ensure_invoice_flags(payload), "metadata": {}}
    if not isinstance(payload, dict):
        return {"invoices": pd.DataFrame(columns=FACTURATION_COLUMNS), "metadata": {}}
    invoices = payload.get("invoices", pd.DataFrame(columns=FACTURATION_COLUMNS))
    if not isinstance(invoices, pd.DataFrame):
        invoices = pd.DataFrame(columns=FACTURATION_COLUMNS)
    return {
        "invoices": ensure_invoice_flags(invoices),
        "metadata": payload.get("metadata", {}),
    }


def replace_facturation_years(existing, imported):
    imported = ensure_invoice_flags(imported)
    if existing is None or not isinstance(existing, pd.DataFrame) or existing.empty:
        return imported.copy().reset_index(drop=True)
    existing = ensure_invoice_flags(existing)
    years = set(imported["invoice_date"].dropna().dt.year.astype(int).tolist())
    existing_dates = pd.to_datetime(existing.get("invoice_date"), errors="coerce")
    kept = existing[~existing_dates.dt.year.isin(years)].copy()
    merged = pd.concat([kept, imported], ignore_index=True)
    return merged.drop_duplicates(subset=["invoice_no"], keep="last").reset_index(drop=True)


def _canonical_order_rows(period_data, period_name, source_key="df_c"):
    source_df = period_data.get(source_key, pd.DataFrame())
    if not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return pd.DataFrame()

    col_client = period_data.get("col_client")
    col_doc = period_data.get("col_doc")
    col_date = period_data.get("col_date")
    col_agency = period_data.get("col_agence")
    col_amount = period_data.get("col_ca_magasin") or period_data.get("col_vente")
    seller_cols = [
        period_data.get("col_com1"),
        period_data.get("col_com2"),
        period_data.get("col_com3"),
    ]
    if not all(column in source_df.columns for column in [col_client, col_date, col_agency, col_amount]):
        return pd.DataFrame()

    canonical = pd.DataFrame({
        "order_no": source_df[col_doc].map(clean_text) if col_doc in source_df.columns else "",
        "sale_date": pd.to_datetime(source_df[col_date], errors="coerce"),
        "client_ref": source_df[col_client].map(clean_text),
        "agency": source_df[col_agency].map(clean_text).str.upper(),
        "amount_ht": pd.to_numeric(source_df[col_amount], errors="coerce").fillna(0.0),
        "seller_1": source_df[seller_cols[0]].map(clean_text) if seller_cols[0] in source_df.columns else "",
        "seller_2": source_df[seller_cols[1]].map(clean_text) if seller_cols[1] in source_df.columns else "",
        "seller_3": source_df[seller_cols[2]].map(clean_text) if seller_cols[2] in source_df.columns else "",
        "source_period": clean_text(period_name),
    })
    canonical = canonical[
        canonical["client_ref"].ne("")
        & canonical["sale_date"].notna()
        & canonical["amount_ht"].gt(0)
    ].copy()
    canonical["sale_date"] = canonical["sale_date"].dt.normalize()
    canonical["client_key"] = canonical["client_ref"].map(normalize_text)
    canonical["agency_key"] = canonical["agency"].map(normalize_text)
    canonical["match_key"] = canonical["client_key"] + "|" + canonical["agency_key"]
    canonical["order_key"] = canonical["order_no"].map(normalize_text)
    missing_order = canonical["order_key"].eq("")
    canonical.loc[missing_order, "order_key"] = canonical.loc[missing_order].apply(
        lambda row: "ROW|" + "|".join([
            row["client_key"],
            row["agency_key"],
            row["sale_date"].strftime("%Y-%m-%d"),
            f"{row['amount_ht']:.2f}",
        ]),
        axis=1,
    )
    return canonical


def build_orders_from_periods(period_items, source_key="df_c"):
    frames = []
    for period_name, period_data in period_items:
        if isinstance(period_data, dict):
            frame = _canonical_order_rows(period_data, period_name, source_key=source_key)
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=[
            "order_no", "sale_date", "client_ref", "agency", "amount_ht",
            "seller_1", "seller_2", "seller_3", "source_period", "match_key", "order_key",
        ])
    orders = pd.concat(frames, ignore_index=True)
    orders = orders.sort_values(["sale_date", "source_period"])
    orders = orders.drop_duplicates(subset=["order_key"], keep="last").reset_index(drop=True)
    return orders


def _seller_keys(row):
    return {
        normalize_text(row.get(column, ""))
        for column in ["seller_1", "seller_2", "seller_3"]
        if normalize_text(row.get(column, ""))
    }


def _candidate_score(invoice, order):
    score = 0
    invoice_sellers = _seller_keys(invoice)
    order_sellers = _seller_keys(order)
    if invoice_sellers and order_sellers and invoice_sellers.intersection(order_sellers):
        score += 3
    order_amount = abs(float(order.get("amount_ht", 0.0)))
    invoice_amount = abs(float(invoice.get("amount_ht", 0.0)))
    tolerance = max(5.0, order_amount * 0.02)
    if abs(order_amount - invoice_amount) <= tolerance:
        score += 3
    if pd.notna(order.get("sale_date")) and pd.notna(invoice.get("invoice_date")):
        if order["sale_date"] <= invoice["invoice_date"]:
            score += 1
    return score


def _safe_label_candidates(invoice, orders):
    same_agency = orders[orders["agency_key"] == invoice.get("agency_key", "")]
    invoice_sellers = _seller_keys(invoice)
    invoice_amount = abs(float(invoice.get("amount_ht", 0.0)))
    candidates = []
    for _, order in same_agency.iterrows():
        order_amount = abs(float(order.get("amount_ht", 0.0)))
        amount_tolerance = max(5.0, order_amount * 0.02)
        amount_matches = abs(order_amount - invoice_amount) <= amount_tolerance
        seller_matches = bool(invoice_sellers.intersection(_seller_keys(order)))
        date_matches = (
            pd.notna(order.get("sale_date"))
            and pd.notna(invoice.get("invoice_date"))
            and order["sale_date"] <= invoice["invoice_date"]
        )
        label_similarity = SequenceMatcher(
            None,
            clean_text(invoice.get("client_key", "")),
            clean_text(order.get("client_key", "")),
        ).ratio()
        if amount_matches and seller_matches and date_matches and label_similarity >= 0.65:
            candidates.append((label_similarity, order))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return None
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.10:
        return None
    return candidates[0][1]


def match_invoices_to_orders(orders, invoices):
    if orders.empty:
        unmatched = invoices.copy()
        unmatched["match_status"] = "Vente N-1 présumée"
        unmatched["matched_order_key"] = ""
        return pd.DataFrame(columns=[
            "invoice_no", "invoice_order_no", "order_key", "confidence"
        ]), unmatched

    matches = []
    unmatched_rows = []
    grouped_orders = {key: group for key, group in orders.groupby("match_key", dropna=False)}
    grouped_order_numbers = {
        key: group
        for key, group in orders[orders["order_key"].str.match(r"^CD", case=False, na=False)].groupby(
            "order_key", dropna=False
        )
    }

    for _, invoice in invoices.iterrows():
        invoice_order_key = normalize_text(
            invoice.get("order_key", "") or invoice.get("order_no", "")
        )
        if invoice_order_key.startswith("CD"):
            direct_candidates = grouped_order_numbers.get(invoice_order_key, pd.DataFrame())
            if direct_candidates.empty:
                inferred_status = infer_unmatched_invoice_status(invoice)
                fallback_candidates = grouped_orders.get(
                    invoice.get("match_key"), pd.DataFrame()
                )
                if not fallback_candidates.empty:
                    fallback_candidates = fallback_candidates[
                        fallback_candidates["sale_date"].notna()
                        & (fallback_candidates["sale_date"] <= invoice.get("invoice_date"))
                    ]
                if inferred_status != "Vente N-1 présumée" and len(fallback_candidates) == 1:
                    selected = fallback_candidates.iloc[0]
                    confidence = "Libellé exact (n° commande différent)"
                else:
                    row = invoice.to_dict()
                    row["match_status"] = (
                        inferred_status
                        if inferred_status == "Vente N-1 présumée"
                        else "N° commande introuvable"
                    )
                    row["matched_order_key"] = ""
                    unmatched_rows.append(row)
                    continue
            else:
                selected = direct_candidates.iloc[0]
                confidence = "N° commande"
        else:
            candidates = grouped_orders.get(invoice.get("match_key"), pd.DataFrame())
            if candidates.empty:
                unmatched_status = infer_unmatched_invoice_status(invoice)
                selected = None
                if unmatched_status != "Vente N-1 présumée":
                    selected = _safe_label_candidates(invoice, orders)
                if selected is None:
                    row = invoice.to_dict()
                    row["match_status"] = unmatched_status
                    row["matched_order_key"] = ""
                    unmatched_rows.append(row)
                    continue
                confidence = "Composite libellé"

            elif len(candidates) == 1:
                selected = candidates.iloc[0]
                confidence = "Automatique"
            else:
                scored = [
                    (_candidate_score(invoice, candidate), idx, candidate)
                    for idx, candidate in candidates.iterrows()
                ]
                scored.sort(key=lambda item: item[0], reverse=True)
                best_score = scored[0][0]
                tied = [item for item in scored if item[0] == best_score]
                if best_score < 3 or len(tied) != 1:
                    row = invoice.to_dict()
                    row["match_status"] = "Rapprochement ambigu"
                    row["matched_order_key"] = ""
                    unmatched_rows.append(row)
                    continue
                selected = scored[0][2]
                confidence = "Composite"

        matches.append({
            "invoice_no": invoice.get("invoice_no", ""),
            "invoice_order_no": invoice.get("order_no", ""),
            "invoice_date": invoice.get("invoice_date"),
            "invoice_amount_ht": float(invoice.get("amount_ht", 0.0)),
            "is_deposit": bool(
                invoice.get("is_deposit", is_deposit_reference(invoice.get("client_ref", "")))
            ),
            "order_key": selected.get("order_key", ""),
            "order_no": selected.get("order_no", ""),
            "confidence": confidence,
        })

    matches_df = pd.DataFrame(matches)
    unmatched_df = pd.DataFrame(unmatched_rows)
    return matches_df, unmatched_df


def infer_unmatched_invoice_status(invoice):
    label = normalize_text(invoice.get("sale_month_label", ""))
    invoice_date = pd.to_datetime(invoice.get("invoice_date"), errors="coerce")
    if label == "CH":
        return "Vente N-1 présumée"
    explicit_year = re.search(r"\b(20\d{2}|\d{2})\b", label)
    if explicit_year:
        year_text = explicit_year.group(1)
        year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
        if pd.notna(invoice_date) and year < invoice_date.year:
            return "Vente N-1 présumée"
        return "Facture non rapprochée"
    month_numbers = {
        "JANVIER": 1, "FEVRIER": 2, "MARS": 3, "AVRIL": 4,
        "MAI": 5, "JUIN": 6, "JUILLET": 7, "AOUT": 8,
        "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DECEMBRE": 12,
    }
    month = month_numbers.get(label)
    if month and pd.notna(invoice_date) and month > invoice_date.month:
        return "Vente N-1 présumée"
    return "Facture non rapprochée"


def find_potential_invoice_matches(remaining_orders, unmatched_invoices):
    columns = [
        "invoice_no", "invoice_order_no", "invoice_date", "invoice_client",
        "invoice_amount_ht", "candidate_order_no", "candidate_client",
        "candidate_amount_ht", "amount_difference_ht", "confidence",
        "matching_clues", "non_match_reason", "candidate_order_keys",
    ]
    if remaining_orders.empty or unmatched_invoices.empty:
        return pd.DataFrame(columns=columns)

    orders = remaining_orders.copy()
    if "is_installed" in orders.columns:
        orders = orders[~orders["is_installed"]].copy()
    orders["sale_date"] = pd.to_datetime(orders.get("sale_date"), errors="coerce")
    orders["amount_ht"] = pd.to_numeric(orders.get("amount_ht"), errors="coerce").fillna(0.0)
    orders["surname_key"] = orders["client_ref"].map(
        lambda value: normalize_text(value).split(" ")[0]
    )
    orders["agency_key"] = orders["agency"].map(normalize_text)

    stop_words = {
        "DEVIS", "ENSEMBLE", "PLUS", "ET", "DE", "DES", "DU", "LA", "LE",
        "LES", "AVEC", "POUR", "FOURNITURE", "POSE",
    }

    def label_tokens(value):
        tokens = normalize_text(value).split()
        return {token for token in tokens[1:] if len(token) >= 3 and token not in stop_words}

    def label_similarity(invoice_label, order_label):
        invoice_tokens = label_tokens(invoice_label)
        order_tokens = label_tokens(order_label)
        token_score = (
            len(invoice_tokens.intersection(order_tokens))
            / max(len(invoice_tokens.union(order_tokens)), 1)
        )
        text_score = SequenceMatcher(
            None, normalize_text(invoice_label), normalize_text(order_label)
        ).ratio()
        return max(token_score, text_score)

    suggestions = []
    for _, invoice in unmatched_invoices.iterrows():
        if clean_text(invoice.get("match_status")) == "Vente N-1 présumée":
            continue
        invoice_date = pd.to_datetime(invoice.get("invoice_date"), errors="coerce")
        invoice_amount = abs(float(invoice.get("amount_ht", 0.0)))
        surname_key = normalize_text(invoice.get("client_ref", "")).split(" ")[0]
        agency_key = normalize_text(invoice.get("agency", ""))
        if len(surname_key) < 4 or invoice_amount <= 0:
            continue

        candidates = orders[
            (orders["surname_key"] == surname_key)
            & (orders["agency_key"] == agency_key)
        ].copy()
        if pd.notna(invoice_date):
            candidates = candidates[
                candidates["sale_date"].notna()
                & (candidates["sale_date"] <= invoice_date)
            ]
        if candidates.empty:
            continue

        possible = []
        for _, order in candidates.iterrows():
            order_amount = abs(float(order.get("amount_ht", 0.0)))
            difference = abs(invoice_amount - order_amount)
            difference_ratio = difference / invoice_amount
            similarity = label_similarity(
                invoice.get("client_ref", ""), order.get("client_ref", "")
            )
            if not (
                difference_ratio <= 0.08
                or (difference <= 750 and similarity >= 0.45)
            ):
                continue
            possible.append({
                "orders": [order],
                "amount": order_amount,
                "difference": difference,
                "difference_ratio": difference_ratio,
                "similarity": similarity,
                "is_group": False,
            })

        candidate_rows = [row for _, row in candidates.iterrows()]
        for group_size in range(2, min(4, len(candidate_rows)) + 1):
            for grouped_orders in combinations(candidate_rows, group_size):
                grouped_amount = sum(abs(float(row.get("amount_ht", 0.0))) for row in grouped_orders)
                difference = abs(invoice_amount - grouped_amount)
                difference_ratio = difference / invoice_amount
                if difference_ratio > 0.06 and difference > 1000:
                    continue
                possible.append({
                    "orders": list(grouped_orders),
                    "amount": grouped_amount,
                    "difference": difference,
                    "difference_ratio": difference_ratio,
                    "similarity": max(
                        label_similarity(invoice.get("client_ref", ""), row.get("client_ref", ""))
                        for row in grouped_orders
                    ),
                    "is_group": True,
                })

        if not possible:
            continue
        possible.sort(key=lambda item: (
            item["difference_ratio"],
            -item["similarity"],
            len(item["orders"]),
        ))
        best = possible[0]
        candidate_order_numbers = " + ".join(
            clean_text(order.get("order_no")) or clean_text(order.get("order_key"))
            for order in best["orders"]
        )
        candidate_clients = " + ".join(
            clean_text(order.get("client_ref")) for order in best["orders"]
        )
        if best["difference_ratio"] <= 0.03 and (
            best["is_group"] or best["similarity"] >= 0.35
        ):
            confidence = "ÉLEVÉE"
        else:
            confidence = "MOYENNE"

        invoice_order_no = clean_text(invoice.get("order_no"))
        if best["is_group"]:
            non_match_reason = (
                f"La facture indique {invoice_order_no or 'aucun n° de commande'}, alors que "
                f"le montant semble regrouper {len(best['orders'])} commandes ({candidate_order_numbers})."
            )
        elif invoice_order_no:
            non_match_reason = (
                f"Le n° de commande de la facture ({invoice_order_no}) diffère de la commande "
                f"candidate ({candidate_order_numbers}) et le libellé client n'est pas strictement identique."
            )
        else:
            non_match_reason = (
                "La facture ne contient aucun n° de commande exploitable et le libellé client "
                "n'est pas strictement identique."
            )
        matching_clues = (
            f"Même client principal et même agence ; écart de {best['difference']:.2f} € HT "
            f"({best['difference_ratio'] * 100:.2f} %)."
        )
        suggestions.append({
            "invoice_no": clean_text(invoice.get("invoice_no")),
            "invoice_order_no": invoice_order_no,
            "invoice_date": invoice_date,
            "invoice_client": clean_text(invoice.get("client_ref")),
            "invoice_amount_ht": invoice_amount,
            "candidate_order_no": candidate_order_numbers,
            "candidate_client": candidate_clients,
            "candidate_amount_ht": best["amount"],
            "amount_difference_ht": best["difference"],
            "confidence": confidence,
            "matching_clues": matching_clues,
            "non_match_reason": non_match_reason,
            "candidate_order_keys": "|".join(
                clean_text(order.get("order_key")) for order in best["orders"]
            ),
        })

    if not suggestions:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(suggestions, columns=columns).sort_values(
        ["confidence", "amount_difference_ht"],
        ascending=[True, True],
    ).reset_index(drop=True)


def build_chantier_forecast(
    orders,
    invoices,
    today=None,
    delivery_months=2,
    manual_invoice_matches=None,
):
    today = pd.Timestamp(today or datetime.today()).normalize()
    matches, unmatched = match_invoices_to_orders(orders, invoices)
    manual_invoice_matches = (
        manual_invoice_matches if isinstance(manual_invoice_matches, dict) else {}
    )
    manual_rows = []
    automatic_invoice_numbers = (
        set(matches["invoice_no"].map(clean_text)) if not matches.empty else set()
    )
    for invoice_no, order_keys in manual_invoice_matches.items():
        invoice_no = clean_text(invoice_no)
        if not invoice_no or invoice_no in automatic_invoice_numbers:
            continue
        if not isinstance(order_keys, list):
            order_keys = [order_keys]
        invoice_candidates = invoices[invoices["invoice_no"].map(clean_text) == invoice_no]
        if invoice_candidates.empty:
            continue
        invoice = invoice_candidates.iloc[-1]
        for order_key in order_keys:
            normalized_order_key = normalize_text(order_key)
            order_candidates = orders[orders["order_key"].map(normalize_text) == normalized_order_key]
            if order_candidates.empty:
                continue
            selected = order_candidates.iloc[-1]
            manual_rows.append({
                "invoice_no": invoice_no,
                "invoice_order_no": clean_text(invoice.get("order_no")),
                "invoice_date": invoice.get("invoice_date"),
                "invoice_amount_ht": float(invoice.get("amount_ht", 0.0)),
                "is_deposit": bool(
                    invoice.get(
                        "is_deposit",
                        is_deposit_reference(invoice.get("client_ref", "")),
                    )
                ),
                "order_key": selected.get("order_key", ""),
                "order_no": selected.get("order_no", ""),
                "confidence": "Validation manuelle",
            })
    if manual_rows:
        matches = pd.concat([matches, pd.DataFrame(manual_rows)], ignore_index=True)
        manual_invoice_numbers = {row["invoice_no"] for row in manual_rows}
        if not unmatched.empty:
            unmatched = unmatched[
                ~unmatched["invoice_no"].map(clean_text).isin(manual_invoice_numbers)
            ].copy()

    if not matches.empty:
        if "is_deposit" not in matches.columns:
            matches["is_deposit"] = False
        matches["is_deposit"] = matches["is_deposit"].fillna(False).astype(bool)
        final_matches = matches[~matches["is_deposit"]].copy()
        deposit_matches = matches[matches["is_deposit"]].copy()
    else:
        final_matches = matches.copy()
        deposit_matches = matches.copy()

    matched_keys = (
        set(final_matches["order_key"].dropna()) if not final_matches.empty else set()
    )
    matched_invoice_map = (
        final_matches.groupby("order_key")["invoice_no"]
        .apply(lambda values: " / ".join(sorted(set(values))))
        .to_dict()
        if not final_matches.empty else {}
    )
    deposit_invoice_map = (
        deposit_matches.groupby("order_key")["invoice_no"]
        .apply(lambda values: " / ".join(sorted(set(values))))
        .to_dict()
        if not deposit_matches.empty else {}
    )
    deposit_amount_map = (
        deposit_matches.groupby("order_key")["invoice_amount_ht"].sum().to_dict()
        if not deposit_matches.empty else {}
    )

    forecast = orders.copy()
    forecast["earliest_install_date"] = forecast["sale_date"] + pd.DateOffset(months=int(delivery_months))
    forecast["days_until_eligible"] = (forecast["earliest_install_date"] - today).dt.days
    forecast["invoice_no"] = forecast["order_key"].map(matched_invoice_map).fillna("")
    forecast["deposit_invoice_no"] = forecast["order_key"].map(deposit_invoice_map).fillna("")
    forecast["deposit_invoiced_ht"] = (
        forecast["order_key"].map(deposit_amount_map).fillna(0.0).astype(float)
    )
    forecast["has_deposit"] = forecast["deposit_invoice_no"].ne("")
    forecast["is_installed"] = forecast["order_key"].isin(matched_keys)
    forecast["billing_status"] = "Aucune facture"
    forecast.loc[forecast["has_deposit"], "billing_status"] = "Acompte factur\u00e9"
    forecast.loc[forecast["is_installed"], "billing_status"] = "Factur\u00e9 / pos\u00e9"
    forecast.loc[
        forecast["is_installed"] & forecast["has_deposit"], "billing_status"
    ] = "Acompte + solde factur\u00e9s / pos\u00e9"

    def status_for(row):
        if row["is_installed"]:
            return "Posé"
        if pd.isna(row["sale_date"]):
            return "Date à contrôler"
        if today < row["earliest_install_date"]:
            return "Attente livraison"
        return "Pose possible"

    forecast["status"] = forecast.apply(status_for, axis=1)
    forecast["forecast_month"] = forecast["earliest_install_date"].dt.to_period("M").astype(str)
    forecast["sellers"] = forecast[["seller_1", "seller_2", "seller_3"]].apply(
        lambda row: " / ".join([clean_text(value) for value in row if clean_text(value)]), axis=1
    )
    return forecast, matches, unmatched
