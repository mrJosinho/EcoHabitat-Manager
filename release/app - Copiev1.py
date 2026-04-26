import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import pickle

st.set_page_config(page_title="Espace Commissions ECOHABITAT", layout="wide")
st.title("🚀 Espace Commissions - ECOHABITAT")
st.markdown(
    "**Logique :** CA Total = CONFIRM | CA OK = BONLIVR | "
    "CA en attente = Total − OK | Remise % = Remise PP hors OPC / Total avant remise hors OPC"
)

HISTORIQUE_DIR = Path("historique")
HISTORIQUE_DIR.mkdir(exist_ok=True)

# ====================== FONCTIONS ======================

def normalize_key(s):
    if pd.isna(s):
        return ""
    return str(s).strip().upper().replace(" ", "").replace(chr(160), "")


def is_excluded_from_evp(nom):
    k = normalize_key(nom)
    return k in [
        "LAVISSEGUILLAUME",
        "LAVISSEFABIEN",
        "LUCCHINJOSEPH",
        "LUCCHINIJOSEPH",
        "PETITLILIAN"
    ]


def calculate_commission(ca_ok, remise_pct):
    if ca_ok >= 60000:
        base = 14
    elif ca_ok >= 50000:
        base = 12
    elif ca_ok >= 40000:
        base = 10
    elif ca_ok >= 30000:
        base = 9
    elif ca_ok >= 20000:
        base = 8
    elif ca_ok >= 15000:
        base = 6
    elif ca_ok >= 10000:
        base = 3
    else:
        base = 0

    if remise_pct > 25:
        base = 0
        points = 0
    elif remise_pct > 16:
        points = int(np.floor(remise_pct - 15))
    else:
        points = 0

    comm_def = max(0, base - points)
    commission = round(ca_ok * comm_def / 100, 2)

    return base, points, comm_def, commission


def find_col(df, includes=None, excludes=None):
    includes = includes or []
    excludes = excludes or []

    for col in df.columns:
        c = str(col).upper()
        if all(i.upper() in c for i in includes) and not any(e.upper() in c for e in excludes):
            return col
    return None


def vendeur_mask(df, vendeur, colonnes_commerciaux):
    mask = pd.Series(False, index=df.index)

    for col in colonnes_commerciaux:
        if col and col in df.columns:
            mask |= df[col].apply(normalize_key) == normalize_key(vendeur)

    return mask


def make_affaire_key(row, key_cols):
    return "|".join(normalize_key(row.get(c, "")) for c in key_cols)


def is_opc(row, col_op):
    if not col_op or col_op not in row.index:
        return False

    valeur = str(row.get(col_op, "")).strip().upper()
    return valeur in ["OUI", "YES", "1", "TRUE", "VRAI"]


def safe_filename(name):
    return (
        str(name)
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace("?", "-")
        .replace('"', "-")
        .replace("<", "-")
        .replace(">", "-")
        .replace("|", "-")
        .strip()
    )


def save_periode(periode, data):
    file_path = HISTORIQUE_DIR / f"{safe_filename(periode)}.pkl"
    with open(file_path, "wb") as f:
        pickle.dump(data, f)


def load_periode(periode):
    file_path = HISTORIQUE_DIR / f"{safe_filename(periode)}.pkl"
    if file_path.exists():
        with open(file_path, "rb") as f:
            return pickle.load(f)
    return None


def list_periodes():
    return sorted([f.stem for f in HISTORIQUE_DIR.glob("*.pkl")])


# ====================== SIDEBAR ======================

st.sidebar.header("📤 Import ProDevis")

f_confirm = st.sidebar.file_uploader(
    "Fichier CONFIRM (Commandes totales)",
    type=["xlsx"],
    key="upload_confirm"
)

f_ok = st.sidebar.file_uploader(
    "Fichier BONLIVR (Commandes OK)",
    type=["xlsx"],
    key="upload_ok"
)

periode = st.sidebar.text_input(
    "📅 Période",
    value="Avril 2026",
    key="periode_input"
)

st.sidebar.markdown("---")
st.sidebar.subheader("📂 Historique")

periodes_dispo = list_periodes()

periode_load = st.sidebar.selectbox(
    "Charger une période sauvegardée",
    [""] + periodes_dispo
)

if st.sidebar.button("📥 Charger la période"):
    if not periode_load:
        st.warning("Sélectionne une période à charger.")
    else:
        saved_data = load_periode(periode_load)

        if saved_data:
            st.session_state.update(saved_data)
            st.success(f"✅ Période {periode_load} chargée.")
        else:
            st.error("❌ Impossible de charger cette période.")


# ====================== TRAITEMENT ======================

if st.sidebar.button("🚀 Lancer le traitement", type="primary"):

    if not f_confirm or not f_ok:
        st.error("❌ Charge les deux fichiers : CONFIRM et BONLIVR.")
        st.stop()

    df_confirm = pd.read_excel(f_confirm, skiprows=28, header=0)
    df_ok = pd.read_excel(f_ok, skiprows=28, header=0)

    for df in [df_confirm, df_ok]:
        df.columns = [str(col).replace("\n", " ").strip() for col in df.columns]

    df_confirm["Statut"] = "⏳ En attente"
    df_ok["Statut"] = "✅ OK"

    col_vente = find_col(df_confirm, includes=["TOTAL VENTE"])
    col_vente_avant = find_col(df_confirm, includes=["TOTAL VENTES AVANT REMISE"])

    col_client = find_col(df_confirm, includes=["CLIENT"], excludes=["RÉFÉRENCE", "REFERENCE"])

    col_ref_affaire = (
        find_col(df_confirm, includes=["RÉFÉRENCE AFFAIRE"])
        or find_col(df_confirm, includes=["REFERENCE AFFAIRE"])
    )

    col_doc = find_col(df_confirm, includes=["N° DOCUMENT"])
    col_date = find_col(df_confirm, includes=["DATE DOCUMENT"])

    col_com1 = find_col(df_confirm, includes=["COMMERCIAL"], excludes=["2", "3"])
    col_com2 = find_col(df_confirm, includes=["COMMERCIAL 2"])
    col_com3 = find_col(df_confirm, includes=["COMMERCIAL 3"])

    col_rem = find_col(df_confirm, includes=["REMISE PP"])
    col_op = find_col(df_confirm, includes=["OPERATION COMMERCIALE"])

    if not col_vente:
        st.error("❌ Impossible de trouver la colonne TOTAL VENTE.")
        st.stop()

    if not col_vente_avant:
        st.error("❌ Impossible de trouver la colonne TOTAL VENTES AVANT REMISE.")
        st.stop()

    if not col_rem:
        st.error("❌ Impossible de trouver la colonne REMISE PP.")
        st.stop()

    colonnes_commerciaux = [col_com1, col_com2, col_com3]

    key_cols = []

    for c in [col_doc, col_ref_affaire, col_client]:
        if c and c in df_confirm.columns and c in df_ok.columns and c not in key_cols:
            key_cols.append(c)

    vendors = {}

    # ====================== CONFIRM = CA TOTAL ======================

    for _, row in df_confirm.iterrows():

        vente = pd.to_numeric(row.get(col_vente), errors="coerce")
        vente = float(vente) if pd.notna(vente) else 0.0

        if vente <= 0:
            continue

        for col in colonnes_commerciaux:

            if not col or col not in df_confirm.columns:
                continue

            nom = row.get(col)

            if pd.isna(nom):
                continue

            nom = str(nom).strip()

            if not nom:
                continue

            k = normalize_key(nom)

            if k not in vendors:
                vendors[k] = {
                    "nom": nom,
                    "total": 0.0,
                    "ok": 0.0,
                    "rem_hors_opc": 0.0,
                    "avant_hors_opc": 0.0
                }

            vendors[k]["total"] += vente

    # ====================== BONLIVR = CA OK ======================

    for _, row in df_ok.iterrows():

        vente = pd.to_numeric(row.get(col_vente), errors="coerce")
        vente = float(vente) if pd.notna(vente) else 0.0

        if vente <= 0:
            continue

        rem = pd.to_numeric(row.get(col_rem), errors="coerce")
        rem = float(rem) if pd.notna(rem) else 0.0

        avant = pd.to_numeric(row.get(col_vente_avant), errors="coerce")
        avant = float(avant) if pd.notna(avant) else 0.0

        opc = is_opc(row, col_op)

        for col in colonnes_commerciaux:

            if not col or col not in df_ok.columns:
                continue

            nom = row.get(col)

            if pd.isna(nom):
                continue

            nom = str(nom).strip()

            if not nom:
                continue

            k = normalize_key(nom)

            if k not in vendors:
                vendors[k] = {
                    "nom": nom,
                    "total": 0.0,
                    "ok": 0.0,
                    "rem_hors_opc": 0.0,
                    "avant_hors_opc": 0.0
                }

            vendors[k]["ok"] += vente

            if not opc:
                vendors[k]["rem_hors_opc"] += rem
                vendors[k]["avant_hors_opc"] += avant

    # ====================== RÉSULTATS ======================

    results = []

    for _, v in vendors.items():

        if is_excluded_from_evp(v["nom"]):
            continue

        remise_moy = (
            v["rem_hors_opc"] / v["avant_hors_opc"] * 100
            if v["avant_hors_opc"] > 0
            else 0
        )

        ca_attente = max(0, v["total"] - v["ok"])
        base_comm, points, comm_def, euro = calculate_commission(v["ok"], remise_moy)

        results.append({
            "Commercial": v["nom"],
            "CA OK": round(v["ok"], 2),
            "CA en attente": round(ca_attente, 2),
            "CA Total": round(v["total"], 2),
            "Remise moy. % hors OPC": round(remise_moy, 2),
            "Base commission %": base_comm,
            "Points perdus": points,
            "% Commission": comm_def,
            "Commission €": euro
        })

    df_com = pd.DataFrame(results)

    if df_com.empty:
        st.error("❌ Aucun commercial trouvé.")
        st.stop()

    data_to_save = {
        "data": df_com,
        "df_ok": df_ok,
        "df_c": df_confirm,
        "col_client": col_client,
        "col_ref_affaire": col_ref_affaire,
        "col_doc": col_doc,
        "col_date": col_date,
        "col_vente": col_vente,
        "col_vente_avant": col_vente_avant,
        "col_rem": col_rem,
        "col_op": col_op,
        "col_com1": col_com1,
        "col_com2": col_com2,
        "col_com3": col_com3,
        "key_cols": key_cols,
        "periode": periode
    }

    st.session_state.update(data_to_save)
    save_periode(periode, data_to_save)

    st.success(f"✅ {periode} chargé et sauvegardé avec succès !")


# ====================== AFFICHAGE ======================

if st.session_state.get("data") is not None:

    df_com = st.session_state.data
    periode = st.session_state.get("periode", "Mois inconnu")

    st.subheader(f"📅 Période : **{periode}**")

    tab1, tab2, tab3 = st.tabs([
        "📊 Dashboard Global",
        "👤 Par Vendeur",
        "📋 Liste complète"
    ])

    # ====================== DASHBOARD ======================

    with tab1:

        total_ok = df_com["CA OK"].sum()
        total_attente = df_com["CA en attente"].sum()
        total_global = df_com["CA Total"].sum()
        total_commissions = df_com["Commission €"].sum()

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("✅ CA OK", f"{total_ok:,.2f} €")
        c2.metric("⏳ CA en attente", f"{total_attente:,.2f} €")
        c3.metric("📌 CA Total", f"{total_global:,.2f} €")
        c4.metric("💰 Total Commissions", f"{total_commissions:,.2f} €")

        st.dataframe(
            df_com.sort_values("Commission €", ascending=False).reset_index(drop=True),
            use_container_width=True
        )

    # ====================== PAR VENDEUR ======================

    with tab2:

        vendeur = st.selectbox(
            "Sélectionner un commercial",
            sorted(df_com["Commercial"]),
            key="vendeur_select"
        )

        if vendeur:

            data = df_com[df_com["Commercial"] == vendeur].iloc[0]

            c1, c2, c3, c4 = st.columns(4)

            c1.metric("✅ CA OK", f"{data['CA OK']:,.2f} €")
            c2.metric("⏳ CA en attente", f"{data['CA en attente']:,.2f} €")
            c3.metric("📌 CA Total", f"{data['CA Total']:,.2f} €")
            c4.metric("💰 Commission", f"{data['Commission €']:,.2f} €")

            st.write(
                f"Remise moyenne hors OPC : **{data['Remise moy. % hors OPC']} %** | "
                f"Base commission : **{data['Base commission %']} %** | "
                f"Points perdus : **{data['Points perdus']}** | "
                f"Commission définitive : **{data['% Commission']} %**"
            )

            st.subheader(f"📋 Détail des affaires de **{vendeur}**")

            df_ok = st.session_state.df_ok.copy()
            df_c = st.session_state.df_c.copy()

            col_client = st.session_state.col_client
            col_ref_affaire = st.session_state.col_ref_affaire
            col_doc = st.session_state.col_doc
            col_date = st.session_state.col_date
            col_vente = st.session_state.col_vente
            col_vente_avant = st.session_state.col_vente_avant
            col_rem = st.session_state.col_rem
            col_op = st.session_state.col_op

            colonnes_commerciaux = [
                st.session_state.col_com1,
                st.session_state.col_com2,
                st.session_state.col_com3
            ]

            key_cols = st.session_state.key_cols

            ok_detail = df_ok[vendeur_mask(df_ok, vendeur, colonnes_commerciaux)].copy()
            attente_detail = df_c[vendeur_mask(df_c, vendeur, colonnes_commerciaux)].copy()

            # Retirer du CONFIRM les affaires déjà présentes dans BONLIVR
            if key_cols:

                ok_detail["_AFFAIRE_KEY_"] = ok_detail.apply(
                    lambda row: make_affaire_key(row, key_cols),
                    axis=1
                )

                attente_detail["_AFFAIRE_KEY_"] = attente_detail.apply(
                    lambda row: make_affaire_key(row, key_cols),
                    axis=1
                )

                ok_keys = set(ok_detail["_AFFAIRE_KEY_"])

                attente_detail = attente_detail[
                    ~attente_detail["_AFFAIRE_KEY_"].isin(ok_keys)
                ]

                ok_detail = ok_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")
                attente_detail = attente_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")

            ok_detail["Statut"] = "✅ OK"
            attente_detail["Statut"] = "⏳ En attente"

            detail = pd.concat([ok_detail, attente_detail], ignore_index=True)

            if not detail.empty:

                cols_show = [
                    col_client,
                    col_ref_affaire,
                    col_doc,
                    col_date,
                    "Statut",
                    col_vente,
                    col_vente_avant,
                    col_rem,
                    col_op
                ]

                cols_show = list(dict.fromkeys(
                    [c for c in cols_show if c and c in detail.columns]
                ))

                detail_affichage = detail[cols_show].copy()

                for c in [col_vente, col_vente_avant, col_rem]:
                    if c and c in detail_affichage.columns:
                        detail_affichage[c] = pd.to_numeric(
                            detail_affichage[c],
                            errors="coerce"
                        ).fillna(0).round(2)

                sort_cols = []

                if "Statut" in detail_affichage.columns:
                    sort_cols.append("Statut")

                if col_date and col_date in detail_affichage.columns:
                    sort_cols.append(col_date)

                if sort_cols:
                    detail_affichage = detail_affichage.sort_values(
                        sort_cols,
                        ascending=[True] + [False] * (len(sort_cols) - 1)
                    )

                st.dataframe(
                    detail_affichage,
                    use_container_width=True,
                    height=600
                )

            else:
                st.info("Aucune affaire trouvée pour ce vendeur.")

    # ====================== LISTE COMPLÈTE ======================

    with tab3:

        st.dataframe(
            df_com.sort_values("Commission €", ascending=False),
            use_container_width=True
        )

    # ====================== EXPORT CSV ======================

    csv = df_com.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        "📥 Télécharger commissions",
        csv,
        f"commissions_{periode}.csv",
        "text/csv"
    )

else:
    st.info("👉 Charge tes deux fichiers puis clique sur « Lancer le traitement »")

st.caption("✅ Version complète avec historique + OPC • Avril 2026")