import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

import pandas as pd


DEFAULT_SPREADSHEET_ID = "1iP0D1bP22QdHlD9gD_1eqyGCrmI4Wbpi00AluCpMr6w"
ACTIVE_SHEET = "Toutes commandes"
SUMMARY_SHEET = "Synthese"
ARCHIVE_PREFIX = "Factures au "
NO_REPORT_NOTE = "Aucune note retrouvee dans le rapport"
NO_JOSEPH_NOTE = "-"


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _key(value):
    text = unicodedata.normalize("NFKD", _clean(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def _number(value):
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    text = _clean(value).replace("\u202f", "").replace(" ", "").replace("EUR", "").replace("€", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _date_text(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.strftime("%d/%m/%Y") if pd.notna(parsed) else ""


def _period_sort(value):
    months = {
        "JANVIER": 1, "FEVRIER": 2, "MARS": 3, "AVRIL": 4,
        "MAI": 5, "JUIN": 6, "JUILLET": 7, "AOUT": 8,
        "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DECEMBRE": 12,
    }
    normalized = unicodedata.normalize("NFKD", _clean(value).upper())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    match = re.search(r"([A-Z]+)\s+(20\d{2})", normalized)
    if not match:
        return (9999, 99, normalized)
    return (int(match.group(2)), months.get(match.group(1), 99), normalized)


def google_sheet_config(secrets_map=None):
    spreadsheet_id = os.getenv("CHANTIER_TRACKING_SPREADSHEET_ID", "").strip()
    raw_credentials = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "").strip()

    if secrets_map is not None:
        try:
            spreadsheet_id = spreadsheet_id or _clean(
                secrets_map.get("CHANTIER_TRACKING_SPREADSHEET_ID", "")
            )
            if not raw_credentials:
                nested = secrets_map.get("google_service_account", None)
                if nested:
                    raw_credentials = dict(nested)
                else:
                    raw_credentials = secrets_map.get("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", "")
        except Exception:
            pass

    spreadsheet_id = spreadsheet_id or DEFAULT_SPREADSHEET_ID
    if not raw_credentials:
        return None, (
            "Connexion Google Sheets non configuree. Ajoute le secret "
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON sur Render, puis partage le tableau "
            "avec l'adresse e-mail du compte de service."
        )
    try:
        credentials = (
            raw_credentials
            if isinstance(raw_credentials, dict)
            else json.loads(str(raw_credentials))
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, f"Le secret Google Sheets n'est pas un JSON valide : {exc}"
    if not credentials.get("client_email") or not credentials.get("private_key"):
        return None, "Le secret Google Sheets ne contient pas client_email et private_key."
    return {
        "spreadsheet_id": spreadsheet_id,
        "credentials": credentials,
        "service_account_email": credentials.get("client_email", ""),
    }, ""


def _active_notes(rows):
    notes = {}
    for row in rows[4:]:
        if len(row) < 2 or not _clean(row[1]):
            continue
        order_key = _key(row[1])
        notes[order_key] = {
            "report": _clean(row[12]) if len(row) > 12 else NO_REPORT_NOTE,
            "joseph": _clean(row[13]) if len(row) > 13 else NO_JOSEPH_NOTE,
            "row": list(row),
        }
    return notes


def _normalize_existing_archive(rows):
    result = []
    for source in rows[4:]:
        row = list(source[:19]) + [""] * max(0, 19 - len(source))
        if not _clean(row[1]):
            continue
        row[5] = _number(row[5])
        row[16] = _number(row[16])
        result.append(row[:19])
    return result


def build_tracking_payload(forecast, matches, old_active_rows, old_archive_rows, now=None):
    now = pd.Timestamp(now or datetime.now()).normalize()
    active_notes = _active_notes(old_active_rows)
    archive_rows = _normalize_existing_archive(old_archive_rows)
    archived_keys = {_key(row[1]) for row in archive_rows}

    current = forecast[~forecast["is_installed"]].copy()
    current = current.sort_values(["sale_date", "client_ref"], na_position="last")
    active_rows = []
    for _, row in current.iterrows():
        order_no = _clean(row.get("order_no")) or _clean(row.get("order_key"))
        note = active_notes.get(_key(order_no), {})
        active_rows.append([
            _clean(row.get("source_period")),
            order_no,
            _clean(row.get("client_ref")),
            _clean(row.get("product_category")),
            _clean(row.get("status")),
            float(row.get("amount_ht", 0.0)),
            _date_text(row.get("sale_date")),
            _date_text(row.get("earliest_install_date")),
            _clean(row.get("agency")),
            _clean(row.get("sellers")),
            _clean(row.get("classification_source")),
            _clean(row.get("classification_confidence")),
            note.get("report") or NO_REPORT_NOTE,
            note.get("joseph") or NO_JOSEPH_NOTE,
        ])

    active_keys = {_key(row[1]) for row in active_rows}
    removed_keys = [key for key in active_notes if key not in active_keys and key not in archived_keys]

    forecast_lookup = {}
    for _, row in forecast.iterrows():
        displayed = _clean(row.get("order_no")) or _clean(row.get("order_key"))
        forecast_lookup[_key(displayed)] = row
    match_lookup = {}
    if isinstance(matches, pd.DataFrame) and not matches.empty:
        ordered_matches = matches.copy()
        ordered_matches["invoice_date"] = pd.to_datetime(
            ordered_matches.get("invoice_date"), errors="coerce"
        )
        ordered_matches = ordered_matches.sort_values("invoice_date")
        for _, match in ordered_matches.iterrows():
            order_key = _key(_clean(match.get("order_no")) or _clean(match.get("order_key")))
            match_lookup[order_key] = match

    new_archive_rows = []
    for order_key in removed_keys:
        old = active_notes[order_key]["row"]
        old = old + [""] * max(0, 14 - len(old))
        forecast_row = forecast_lookup.get(order_key)
        match = match_lookup.get(order_key)
        if forecast_row is None or match is None:
            continue
        new_archive_rows.append([
            _clean(old[0]), _clean(old[1]), _clean(old[2]), _clean(old[3]), _clean(old[4]),
            _number(old[5]), _clean(old[6]), _clean(old[7]), _clean(old[8]), _clean(old[9]),
            _clean(old[10]), _clean(old[11]),
            _clean(old[12]) or NO_REPORT_NOTE,
            _clean(old[13]) or NO_JOSEPH_NOTE,
            _clean(match.get("invoice_no")),
            _date_text(match.get("invoice_date")),
            float(match.get("invoice_amount_ht", 0.0)),
            "Nouvelle depuis la derniere mise a jour",
            now.strftime("%d/%m/%Y"),
        ])

    archive_rows.extend(new_archive_rows)
    archive_rows.sort(key=lambda row: (_period_sort(row[0]), _clean(row[2])))

    periods = sorted(
        {row[0] for row in active_rows}.union({row[0] for row in archive_rows}),
        key=_period_sort,
    )
    monthly = []
    chart_rows = []
    for period in periods:
        active_period = [row for row in active_rows if row[0] == period]
        archive_period = [row for row in archive_rows if row[0] == period]
        report_count = sum(
            1 for row in active_period
            if row[12] and not _key(row[12]).startswith(_key(NO_REPORT_NOTE))
        )
        joseph_count = sum(1 for row in active_period if row[13] and row[13] != NO_JOSEPH_NOTE)
        monthly.append([
            period,
            len(active_period),
            sum(_number(row[5]) for row in active_period),
            report_count,
            len(active_period) - report_count,
            joseph_count,
        ])
        chart_rows.append([
            period,
            sum(_number(row[5]) for row in active_period),
            sum(_number(row[16]) for row in archive_period),
        ])

    report_notes = sum(
        1 for row in active_rows
        if row[12] and not _key(row[12]).startswith(_key(NO_REPORT_NOTE))
    )
    joseph_notes = sum(1 for row in active_rows if row[13] and row[13] != NO_JOSEPH_NOTE)
    latest_invoice = ""
    if isinstance(matches, pd.DataFrame) and not matches.empty:
        latest = pd.to_datetime(matches.get("invoice_date"), errors="coerce").max()
        latest_invoice = _date_text(latest)

    return {
        "active_rows": active_rows,
        "archive_rows": archive_rows,
        "new_archive_rows": new_archive_rows,
        "periods": periods,
        "monthly": monthly,
        "chart_rows": chart_rows,
        "active_amount": sum(_number(row[5]) for row in active_rows),
        "archive_amount": sum(_number(row[16]) for row in archive_rows),
        "new_archive_amount": sum(_number(row[16]) for row in new_archive_rows),
        "report_notes": report_notes,
        "without_report_note": len(active_rows) - report_notes,
        "joseph_notes": joseph_notes,
        "latest_invoice": latest_invoice,
        "updated_at": now.strftime("%d/%m/%Y"),
    }


def _get_or_create_month_sheet(spreadsheet, title, template_sheet):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        if template_sheet is not None:
            return spreadsheet.duplicate_sheet(
                template_sheet.id,
                new_sheet_name=title,
            )
        return spreadsheet.add_worksheet(title=title, rows=150, cols=14)


def _write_tracking_worksheet(worksheet, title, subtitle, rows):
    headers = [
        "Mois commercial", "No commande", "Client / reference affaire", "Type de dossier",
        "Etat", "Montant HT", "Date document", "Pose possible a partir du", "Agence",
        "Commercial(aux)", "Origine du classement", "Confiance automatique",
        "Note du rapport", "Notes Joseph",
    ]
    worksheet.batch_clear(["A1:N400"])
    worksheet.update(values=[[title]], range_name="A1")
    worksheet.update(values=[[subtitle]], range_name="A2")
    worksheet.update(values=[headers], range_name="A4:N4")
    if rows:
        worksheet.update(
            values=rows,
            range_name=f"A5:N{len(rows) + 4}",
            value_input_option="USER_ENTERED",
        )


def _write_archive(worksheet, payload):
    headers = [
        "Mois commercial", "No commande", "Client / reference affaire", "Type de dossier",
        "Ancien etat", "Montant commande HT", "Date document", "Pose possible a partir du",
        "Agence", "Commercial(aux)", "Origine du classement", "Confiance automatique",
        "Note du rapport", "Notes Joseph", "No facture", "Date facture",
        "Montant facture HT", "Categorie du rapprochement", "Date de retrait",
    ]
    rows = payload["archive_rows"]
    worksheet.batch_clear(["A1:S500"])
    worksheet.update(values=[["CHANTIERS RETIRES DU SUIVI CAR FACTURES"]], range_name="A1")
    worksheet.update(values=[[
        f"{len(rows)} chantiers - {payload['archive_amount']:.2f} EUR HT factures - "
        f"Mise a jour du {payload['updated_at']}"
    ]], range_name="A2")
    worksheet.update(values=[headers], range_name="A4:S4")
    if rows:
        worksheet.update(
            values=rows,
            range_name=f"A5:S{len(rows) + 4}",
            value_input_option="USER_ENTERED",
        )


def _write_summary(worksheet, payload):
    active_count = len(payload["active_rows"])
    new_count = len(payload["new_archive_rows"])
    worksheet.batch_clear(["A1:I200"])
    worksheet.update(values=[["RAPPORT COMMANDES NON POSEES ET NOTES"]], range_name="A1")
    worksheet.update(values=[[
        f"Mise a jour facturation au {payload['updated_at']} - "
        "rapprochement par numero de commande"
    ]], range_name="A2")
    worksheet.update(values=[
        ["Indicateur", "Valeur", "", "Mise a jour facturation", "Valeur"],
        ["Commandes non posees", active_count, "", "Nouveaux chantiers factures", new_count],
        ["Montant total HT", payload["active_amount"], "", "Montant nouvellement facture HT", payload["new_archive_amount"]],
        ["Commandes avec note du rapport", payload["report_notes"], "", "Total retire du suivi", len(payload["archive_rows"])],
        ["Commandes sans note du rapport", payload["without_report_note"], "", "Montant total retire HT", payload["archive_amount"]],
        ["Commandes avec note Joseph", payload["joseph_notes"], "", "Derniere facture integree", payload["latest_invoice"]],
    ], range_name="A4:E9", value_input_option="USER_ENTERED")
    monthly = [["Mois", "Commandes", "Montant HT", "Avec note", "Sans note", "Notes Joseph"]]
    monthly.extend(payload["monthly"])
    chart = [["Mois commercial", "CA restant non pose HT", "CA facture recemment HT"]]
    chart.extend(payload["chart_rows"])
    worksheet.update(
        values=monthly,
        range_name=f"A12:F{11 + len(monthly)}",
        value_input_option="USER_ENTERED",
    )
    worksheet.update(
        values=chart,
        range_name=f"G12:I{11 + len(chart)}",
        value_input_option="USER_ENTERED",
    )


def _refresh_summary_charts(spreadsheet, worksheet, period_count):
    metadata = spreadsheet.fetch_sheet_metadata()
    sheet_metadata = next(
        (
            sheet for sheet in metadata.get("sheets", [])
            if sheet.get("properties", {}).get("sheetId") == worksheet.id
        ),
        {},
    )
    end_row = 12 + int(period_count)
    requests = []
    for chart in sheet_metadata.get("charts", []):
        chart_id = chart.get("chartId")
        title = _clean(chart.get("spec", {}).get("title"))
        if not chart_id:
            continue
        if title.startswith("Evolution du CA") or title == "Montant HT non pose par mois":
            requests.append({
                "updateChartSpec": {
                    "chartId": chart_id,
                    "spec": {
                        "title": "Evolution du CA restant non pose et facture recemment",
                        "hiddenDimensionStrategy": "SHOW_ALL",
                        "basicChart": {
                            "chartType": "COLUMN",
                            "stackedType": "NOT_STACKED",
                            "legendPosition": "BOTTOM_LEGEND",
                            "headerCount": 1,
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Mois commercial"},
                                {"position": "LEFT_AXIS", "title": "Montant HT"},
                            ],
                            "domains": [{
                                "domain": {"sourceRange": {"sources": [{
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 11,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": 6,
                                    "endColumnIndex": 7,
                                }]}}
                            }],
                            "series": [
                                {
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": worksheet.id,
                                        "startRowIndex": 11,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 7,
                                        "endColumnIndex": 8,
                                    }]}},
                                    "targetAxis": "LEFT_AXIS",
                                    "color": {"red": 0.88, "green": 0.60, "blue": 0.08},
                                },
                                {
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": worksheet.id,
                                        "startRowIndex": 11,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 8,
                                        "endColumnIndex": 9,
                                    }]}},
                                    "targetAxis": "LEFT_AXIS",
                                    "color": {"red": 0.18, "green": 0.50, "blue": 0.28},
                                },
                            ],
                        },
                    },
                }
            })
        elif title == "Suivi des notes par mois":
            requests.append({
                "updateChartSpec": {
                    "chartId": chart_id,
                    "spec": {
                        "title": title,
                        "basicChart": {
                            "chartType": "COLUMN",
                            "stackedType": "STACKED",
                            "legendPosition": "BOTTOM_LEGEND",
                            "headerCount": 1,
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Mois commercial"},
                                {"position": "LEFT_AXIS", "title": "Commandes"},
                            ],
                            "domains": [{
                                "domain": {"sourceRange": {"sources": [{
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 11,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 1,
                                }]}}
                            }],
                            "series": [
                                {
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": worksheet.id,
                                        "startRowIndex": 11,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 3,
                                        "endColumnIndex": 4,
                                    }]}},
                                    "targetAxis": "LEFT_AXIS",
                                    "color": {"red": 0.18, "green": 0.50, "blue": 0.28},
                                },
                                {
                                    "series": {"sourceRange": {"sources": [{
                                        "sheetId": worksheet.id,
                                        "startRowIndex": 11,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 4,
                                        "endColumnIndex": 5,
                                    }]}},
                                    "targetAxis": "LEFT_AXIS",
                                    "color": {"red": 0.82, "green": 0.35, "blue": 0.30},
                                },
                            ],
                        },
                    },
                }
            })
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": worksheet.id,
                "dimension": "COLUMNS",
                "startIndex": 6,
                "endIndex": 9,
            },
            "properties": {"hiddenByUser": True},
            "fields": "hiddenByUser",
        }
    })
    spreadsheet.batch_update({"requests": requests})


def sync_tracking_spreadsheet(forecast, matches, config, now=None):
    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError(
            "La dependance gspread n'est pas installee. Relance le deploiement Render."
        ) from exc

    client = gspread.service_account_from_dict(config["credentials"])
    spreadsheet = client.open_by_key(config["spreadsheet_id"])
    active_sheet = spreadsheet.worksheet(ACTIVE_SHEET)
    summary_sheet = spreadsheet.worksheet(SUMMARY_SHEET)
    old_active_rows = active_sheet.get_all_values()

    archive_candidates = [
        worksheet for worksheet in spreadsheet.worksheets()
        if worksheet.title.startswith(ARCHIVE_PREFIX)
    ]
    if archive_candidates:
        archive_sheet = archive_candidates[-1]
        old_archive_rows = archive_sheet.get_all_values()
    else:
        archive_sheet = spreadsheet.add_worksheet(
            title=f"{ARCHIVE_PREFIX}{datetime.now().strftime('%d-%m-%Y')}",
            rows=500,
            cols=19,
        )
        old_archive_rows = []

    payload = build_tracking_payload(
        forecast,
        matches,
        old_active_rows,
        old_archive_rows,
        now=now,
    )
    subtitle = f"Mise a jour facturation du {payload['updated_at']}"
    _write_tracking_worksheet(
        active_sheet,
        "COMMANDES NON POSEES - TOUTES PERIODES",
        subtitle,
        payload["active_rows"],
    )

    month_sheets = {
        worksheet.title: worksheet
        for worksheet in spreadsheet.worksheets()
        if re.match(r"^[A-Za-z]+ 20\d{2}$", worksheet.title)
    }
    template_sheet = next(iter(month_sheets.values()), None)
    for period in payload["periods"]:
        period_sheet = month_sheets.get(period) or _get_or_create_month_sheet(
            spreadsheet, period, template_sheet
        )
        period_rows = [row for row in payload["active_rows"] if row[0] == period]
        _write_tracking_worksheet(
            period_sheet,
            f"COMMANDES NON POSEES - {period.upper()}",
            subtitle,
            period_rows,
        )

    archive_title = f"{ARCHIVE_PREFIX}{pd.Timestamp(now or datetime.now()).strftime('%d-%m-%Y')}"
    if archive_sheet.title != archive_title:
        try:
            archive_sheet.update_title(archive_title)
        except Exception:
            pass
    _write_archive(archive_sheet, payload)
    _write_summary(summary_sheet, payload)
    _refresh_summary_charts(spreadsheet, summary_sheet, len(payload["periods"]))
    return payload
