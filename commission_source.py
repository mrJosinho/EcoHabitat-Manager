import pandas as pd


def normalize_commission_columns(
    df,
    col_vente,
    col_ca_magasin,
    col_catalogue,
    col_remise,
    seller_columns,
):
    """Rebuild seller commission inputs from the complete sale amount."""
    if not isinstance(df, pd.DataFrame):
        return df

    out = df.copy()
    if (
        out.empty
        or not col_vente
        or col_vente not in out.columns
        or not col_ca_magasin
        or col_ca_magasin not in out.columns
    ):
        return out

    seller_count = pd.Series(0, index=out.index, dtype="int64")
    for column in seller_columns or []:
        if column and column in out.columns:
            seller_count += out[column].fillna("").astype(str).str.strip().ne("").astype(int)
    complete_sale = pd.to_numeric(out[col_ca_magasin], errors="coerce")
    valid_sale = complete_sale.notna() & complete_sale.gt(0) & seller_count.gt(0)
    out.loc[valid_sale, col_vente] = complete_sale[valid_sale] / seller_count[valid_sale]

    if (
        col_catalogue
        and col_catalogue in out.columns
        and col_remise
        and col_remise in out.columns
    ):
        discount = pd.to_numeric(out[col_remise], errors="coerce").fillna(0.0)
        out.loc[valid_sale, col_catalogue] = complete_sale[valid_sale] + discount[valid_sale]

    return out
