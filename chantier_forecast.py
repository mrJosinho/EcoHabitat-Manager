import math
import os
import pickle
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

import pandas as pd


FACTURATION_COLUMNS = [
    "invoice_no",
    "invoice_date",
    "client_ref",
    "agency",
    "seller_1",
    "seller_2",
    "seller_3",
    "amount_ht",
    "sale_month_label",
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
    parsed["client_key"] = parsed["client_ref"].map(normalize_text)
    parsed["agency_key"] = parsed["agency"].map(normalize_text)
    parsed["match_key"] = parsed["client_key"] + "|" + parsed["agency_key"]
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
        return {"invoices": payload, "metadata": {}}
    if not isinstance(payload, dict):
        return {"invoices": pd.DataFrame(columns=FACTURATION_COLUMNS), "metadata": {}}
    invoices = payload.get("invoices", pd.DataFrame(columns=FACTURATION_COLUMNS))
    if not isinstance(invoices, pd.DataFrame):
        invoices = pd.DataFrame(columns=FACTURATION_COLUMNS)
    return {"invoices": invoices, "metadata": payload.get("metadata", {})}


def replace_facturation_years(existing, imported):
    if existing is None or not isinstance(existing, pd.DataFrame) or existing.empty:
        return imported.copy().reset_index(drop=True)
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
        return pd.DataFrame(columns=["invoice_no", "order_key", "confidence"]), unmatched

    matches = []
    unmatched_rows = []
    grouped_orders = {key: group for key, group in orders.groupby("match_key", dropna=False)}

    for _, invoice in invoices.iterrows():
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
            scored = [(_candidate_score(invoice, candidate), idx, candidate) for idx, candidate in candidates.iterrows()]
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
            "invoice_date": invoice.get("invoice_date"),
            "invoice_amount_ht": float(invoice.get("amount_ht", 0.0)),
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


def build_chantier_forecast(orders, invoices, today=None, delivery_months=2):
    today = pd.Timestamp(today or datetime.today()).normalize()
    matches, unmatched = match_invoices_to_orders(orders, invoices)
    matched_keys = set(matches["order_key"].dropna()) if not matches.empty else set()
    matched_invoice_map = (
        matches.groupby("order_key")["invoice_no"].apply(lambda values: " / ".join(sorted(set(values)))).to_dict()
        if not matches.empty else {}
    )

    forecast = orders.copy()
    forecast["earliest_install_date"] = forecast["sale_date"] + pd.DateOffset(months=int(delivery_months))
    forecast["days_until_eligible"] = (forecast["earliest_install_date"] - today).dt.days
    forecast["invoice_no"] = forecast["order_key"].map(matched_invoice_map).fillna("")
    forecast["is_installed"] = forecast["order_key"].isin(matched_keys)

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
