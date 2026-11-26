import unicodedata

import pandas as pd


AGENCY_TOTALS_RULE_VERSION = 1
GERANTS = (
    "LUCCHINI JOSEPH",
    "PETIT LILIAN",
    "LAVISSE GUILLAUME",
    "LAVISSE FABIEN",
)


def _name(value):
    if pd.isna(value):
        return ""
    return " ".join(str(value).split())


def gerant_name(value):
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", _name(value).upper())
        if unicodedata.category(char) != "Mn"
    )
    for name in GERANTS:
        if normalized in (name, " ".join(reversed(name.split()))):
            return name
    if normalized in ("LUCCHIN JOSEPH", "JOSEPH LUCCHIN"):
        return "LUCCHINI JOSEPH"
    return ""


def agency_sale_shares(df, seller_columns):
    """Keep the original equal split; never redistribute a manager's share."""
    seller_count = pd.Series(0, index=df.index, dtype="int64")
    manager_count = seller_count.copy()
    for column in dict.fromkeys(seller_columns or []):
        if column and column in df.columns:
            names = df[column].map(_name)
            seller_count += names.ne("").astype(int)
            manager_count += names.map(gerant_name).ne("").astype(int)
    return 1.0 - manager_count / seller_count.replace(0, 1)


def eligible_agency_sales(df, seller_columns, amount_columns):
    """Return agency-only inputs without changing imported or seller data."""
    shares = agency_sale_shares(df, seller_columns)
    retained = shares.gt(0)
    out = df.loc[retained].copy()
    for column in dict.fromkeys(amount_columns):
        if column and column in out.columns:
            amounts = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
            out[column] = amounts * shares[retained]
    return out


def agency_detail_rows(df, seller_columns, include_gerants=False):
    """Filter display/export rows only; shared seller totals stay unchanged."""
    if include_gerants or df.empty:
        return df.copy()
    columns = [c for c in dict.fromkeys(seller_columns or []) if c and c in df.columns]
    if not columns:
        return df.iloc[0:0].copy()
    visible = pd.Series(True, index=df.index)
    for column in columns:
        visible &= df[column].map(gerant_name).eq("")
    return df.loc[visible].copy()


def agency_sale_breakdown(df, seller_columns, amount_column):
    out = df.copy()
    shares = agency_sale_shares(df, seller_columns)
    amounts = (
        pd.to_numeric(df[amount_column], errors="coerce").fillna(0.0)
        if amount_column and amount_column in df.columns
        else pd.Series(0.0, index=df.index)
    )
    columns = [c for c in dict.fromkeys(seller_columns or []) if c and c in df.columns]
    out["gerants"] = [
        " / ".join(dict.fromkeys(filter(None, (gerant_name(row[c]) for c in columns))))
        for _, row in df.iterrows()
    ]
    out["agency_amount_ht"] = amounts * shares
    out["manager_amount_ht"] = amounts - out["agency_amount_ht"]
    return out
