import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import pickle

st.set_page_config(page_title="Espace Commissions ECOHABITAT", layout="wide")
st.title("🚀 Espace Commissions - ECOHABITAT")
st.markdown(
    "**Logique VBA :** Vendeurs + Agences | "
    "Vendeurs = TOTAL VENTE divisé | "
    "Agences = Vente HT hors acompte | "
    "Remise commission hors OPC | "
    "Comm. magasin directeurs = 1% CA agence + prime"
)

HISTORIQUE_DIR = Path("historique")
HISTORIQUE_DIR.mkdir(exist_ok=True)

# ====================== FONCTIONS ======================

def normalize_key(s):
    if pd.isna(s):
        return ""
    t = str(s).replace(chr(160), " ").replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return " ".join(t.strip().upper().split())


def clean_visible(s):
    if pd.isna(s):
        return ""
    return " ".join(str(s).replace(chr(160), " ").split()).strip()


def is_excluded_from_evp(nom):
    k = normalize_key(nom)
    return k in [
        "LAVISSE GUILLAUME",
        "LAVISSE FABIEN",
        "LUCCHINI JOSEPH",
        "LUCCHIN JOSEPH",
        "PETIT LILIAN"
    ]


def prime_magasin(ca_ht):
    if ca_ht >= 300000:
        return 1000
    elif ca_ht >= 250000:
        return 750
    elif ca_ht >= 200000:
        return 500
    return 0


def calculate_commission(ca_ok, remise_pct):
    if ca_ok < 10000:
        base = 0
    elif ca_ok < 15000:
        base = 3
    elif ca_ok < 20000:
        base = 6
    elif ca_ok < 30000:
        base = 8
    elif ca_ok < 40000:
        base = 9
    elif ca_ok < 50000:
        base = 10
    elif ca_ok < 60000:
        base = 12
    else:
        base = 14

    if remise_pct <= 16:
        points = 0
    elif remise_pct > 25:
        base = 0
        points = 0
    else:
        points = int(np.floor(remise_pct - 15))

    commission_pct = max(0, base - points)
    commission_euro = round(ca_ok * commission_pct / 100, 2)

    return base, points, commission_pct, commission_euro


def find_col(df, includes=None, excludes=None):
    includes = includes or []
    excludes = excludes or []

    for col in df.columns:
        c = str(col).upper()
        if all(i.upper() in c for i in includes) and not any(e.upper() in c for e in excludes):
            return col
    return None


def get_col_by_excel_position(df, index_1_based):
    idx = index_1_based - 1
    if 0 <= idx < len(df.columns):
        return df.columns[idx]
    return None


def is_opc(row, col_op):
    if not col_op or col_op not in row.index:
        return False
    valeur = normalize_key(row.get(col_op, ""))
    return valeur in ["OUI", "YES", "1", "TRUE", "VRAI"]


def vendeur_mask(df, vendeur, colonnes_commerciaux):
    mask = pd.Series(False, index=df.index)
    for col in colonnes_commerciaux:
        if col and col in df.columns:
            mask |= df[col].apply(normalize_key) == normalize_key(vendeur)
    return mask


def agence_mask(df, agence, col_agence):
    if not col_agence or col_agence not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col_agence].apply(normalize_key) == normalize_key(agence)


def make_affaire_key(row, key_cols):
    return "|".join(normalize_key(row.get(c, "")) for c in key_cols)


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


def format_df_vendeurs(df):
    return df.rename(columns={
        "ca_ok": "CA OK",
        "ca_attente": "CA en attente",
        "ca_total": "CA Total",
        "remise_hors_opc_pct": "Remise moy. % hors OPC",
        "base_commission_pct": "Base commission %",
        "points_perdus": "Points perdus",
        "commission_pct": "% Commission",
        "commission_eur": "Commission €",
    })


def format_df_agences(df):
    return df.rename(columns={
        "agence": "Agence",
        "ca_ok": "CA OK",
        "ca_attente": "CA en attente",
        "ca_total": "CA Total",
        "ca_magasin_ok": "CA magasin OK",
        "remise_pct": "Remise moyenne %",
        "nb_ok": "Nb affaires OK",
        "nb_total": "Nb affaires total",
    })


def format_df_directeurs(df):
    return df.rename(columns={
        "directeur": "Directeur",
        "agence": "Agence",
        "ca_magasin_ok": "CA magasin OK",
        "un_pourcent_ca": "1% CA",
        "prime_palier": "Prime palier",
        "commission_magasin_eur": "Commission magasin €",
    })


# ====================== SIDEBAR ======================

st.sidebar.header("📤 Import ProDevis")

f_confirm = st.sidebar.file_uploader("Fichier CONFIRM", type=["xlsx"], key="upload_confirm")
f_ok = st.sidebar.file_uploader("Fichier BONLIVR", type=["xlsx"], key="upload_ok")

periode = st.sidebar.text_input("📅 Période", value="Avril 2026", key="periode_input")

st.sidebar.markdown("---")
st.sidebar.subheader("📂 Historique")

periodes_dispo = list_periodes()

periode_load = st.sidebar.selectbox("Charger une période sauvegardée", [""] + periodes_dispo)

if st.sidebar.button("📥 Charger la période"):
    if not periode_load:
        st.warning("Sélectionne une période.")
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

    # Colonnes selon VBA
    col_client = get_col_by_excel_position(df_confirm, 1)      # A
    col_com1 = get_col_by_excel_position(df_confirm, 2)        # B
    col_com2 = get_col_by_excel_position(df_confirm, 3)        # C
    col_com3 = get_col_by_excel_position(df_confirm, 4)        # D
    col_date = get_col_by_excel_position(df_confirm, 6)        # F
    col_doc = get_col_by_excel_position(df_confirm, 7)         # G
    col_op = get_col_by_excel_position(df_confirm, 8)          # H
    col_ca_magasin = get_col_by_excel_position(df_confirm, 9)  # I = Vente HT hors acompte
    col_vente = get_col_by_excel_position(df_confirm, 17)      # Q = Total vente divisé
    col_rem = get_col_by_excel_position(df_confirm, 24)        # X
    col_catalogue = get_col_by_excel_position(df_confirm, 25)  # Y
    col_agence = get_col_by_excel_position(df_confirm, 50)     # AX

    # Fallbacks
    col_vente = col_vente or find_col(df_confirm, includes=["TOTAL VENTE"])
    col_catalogue = col_catalogue or find_col(df_confirm, includes=["TOTAL VENTES AVANT REMISE"])
    col_rem = col_rem or find_col(df_confirm, includes=["REMISE PP"])
    col_op = col_op or find_col(df_confirm, includes=["OPERATION COMMERCIALE"])
    col_agence = col_agence or find_col(df_confirm, includes=["AGENCE"])
    col_ca_magasin = col_ca_magasin or find_col(df_confirm, includes=["VENTE HT"])

    if not col_vente:
        st.error("❌ Colonne vendeur introuvable : Q / TOTAL VENTE.")
        st.stop()

    if not col_ca_magasin:
        st.error("❌ Colonne agence introuvable : I / Vente HT hors acompte.")
        st.stop()

    if not col_catalogue:
        st.error("❌ Colonne catalogue introuvable : Y / TOTAL VENTES AVANT REMISE.")
        st.stop()

    if not col_rem:
        st.error("❌ Colonne remise PP introuvable : X / REMISE PP.")
        st.stop()

    if not col_agence:
        st.error("❌ Colonne agence introuvable : AX.")
        st.stop()

    colonnes_commerciaux = [col_com1, col_com2, col_com3]

    key_cols = []
    for c in [col_client, col_date, col_doc]:
        if c and c in df_confirm.columns and c in df_ok.columns and c not in key_cols:
            key_cols.append(c)

    # ====================== VENDEURS ======================

    vendors = {}

    # CONFIRM = CA total vendeur, colonne Q
    for _, row in df_confirm.iterrows():

        vente = pd.to_numeric(row.get(col_vente), errors="coerce")
        vente = float(vente) if pd.notna(vente) else 0.0

        if vente <= 0:
            continue

        for col in colonnes_commerciaux:
            if not col or col not in df_confirm.columns:
                continue

            nom = clean_visible(row.get(col))

            if not nom:
                continue

            k = normalize_key(nom)

            if k not in vendors:
                vendors[k] = {
                    "nom": nom,
                    "total": 0.0,
                    "ok": 0.0,
                    "rem_hors_opc": 0.0,
                    "catalogue_hors_opc": 0.0
                }

            vendors[k]["total"] += vente

    # BONLIVR = CA OK vendeur, colonne Q + remise hors OPC
    for _, row in df_ok.iterrows():

        vente = pd.to_numeric(row.get(col_vente), errors="coerce")
        vente = float(vente) if pd.notna(vente) else 0.0

        if vente <= 0:
            continue

        rem = pd.to_numeric(row.get(col_rem), errors="coerce")
        rem = float(rem) if pd.notna(rem) else 0.0

        catalogue = pd.to_numeric(row.get(col_catalogue), errors="coerce")
        catalogue = float(catalogue) if pd.notna(catalogue) else 0.0

        opc = is_opc(row, col_op)

        for col in colonnes_commerciaux:
            if not col or col not in df_ok.columns:
                continue

            nom = clean_visible(row.get(col))

            if not nom:
                continue

            k = normalize_key(nom)

            if k not in vendors:
                vendors[k] = {
                    "nom": nom,
                    "total": 0.0,
                    "ok": 0.0,
                    "rem_hors_opc": 0.0,
                    "catalogue_hors_opc": 0.0
                }

            vendors[k]["ok"] += vente

            if not opc:
                vendors[k]["rem_hors_opc"] += rem
                vendors[k]["catalogue_hors_opc"] += catalogue

    vendeur_results = []

    for _, v in vendors.items():

        if is_excluded_from_evp(v["nom"]):
            continue

        remise_commission = (
            v["rem_hors_opc"] / v["catalogue_hors_opc"] * 100
            if v["catalogue_hors_opc"] > 0
            else 0
        )

        ca_attente = max(0, v["total"] - v["ok"])
        base_comm, points, comm_def, euro = calculate_commission(v["ok"], remise_commission)

        vendeur_results.append({
            "Commercial": v["nom"],
            "ca_ok": round(v["ok"], 2),
            "ca_attente": round(ca_attente, 2),
            "ca_total": round(v["total"], 2),
            "remise_hors_opc_pct": round(remise_commission, 2),
            "base_commission_pct": base_comm,
            "points_perdus": points,
            "commission_pct": comm_def,
            "commission_eur": euro
        })

    df_vendeurs = pd.DataFrame(vendeur_results)

    # ====================== AGENCES ======================
    # IMPORTANT : pour les agences, on utilise la colonne I = Vente HT hors acompte
    # et non la colonne Q qui est divisée par nombre de vendeurs.

    agences = {}

    # CONFIRM = CA total agence, colonne I
    for _, row in df_confirm.iterrows():

        agence = clean_visible(row.get(col_agence))
        if not agence:
            continue

        k = normalize_key(agence)

        ca_agence = pd.to_numeric(row.get(col_ca_magasin), errors="coerce")
        ca_agence = float(ca_agence) if pd.notna(ca_agence) else 0.0

        if k not in agences:
            agences[k] = {
                "agence": agence,
                "total": 0.0,
                "ok": 0.0,
                "rem": 0.0,
                "catalogue": 0.0,
                "nb_confirm": 0,
                "nb_ok": 0
            }

        agences[k]["total"] += ca_agence
        agences[k]["nb_confirm"] += 1

    # BONLIVR = CA OK agence, colonne I
    for _, row in df_ok.iterrows():

        agence = clean_visible(row.get(col_agence))
        if not agence:
            continue

        k = normalize_key(agence)

        ca_agence = pd.to_numeric(row.get(col_ca_magasin), errors="coerce")
        ca_agence = float(ca_agence) if pd.notna(ca_agence) else 0.0

        rem = pd.to_numeric(row.get(col_rem), errors="coerce")
        rem = float(rem) if pd.notna(rem) else 0.0

        catalogue = pd.to_numeric(row.get(col_catalogue), errors="coerce")
        catalogue = float(catalogue) if pd.notna(catalogue) else 0.0

        if k not in agences:
            agences[k] = {
                "agence": agence,
                "total": 0.0,
                "ok": 0.0,
                "rem": 0.0,
                "catalogue": 0.0,
                "nb_confirm": 0,
                "nb_ok": 0
            }

        agences[k]["ok"] += ca_agence
        agences[k]["rem"] += rem
        agences[k]["catalogue"] += catalogue
        agences[k]["nb_ok"] += 1

    agence_results = []

    for _, a in agences.items():

        remise_agence = (a["rem"] / a["catalogue"] * 100) if a["catalogue"] > 0 else 0
        ca_attente = max(0, a["total"] - a["ok"])

        agence_results.append({
            "agence": a["agence"],
            "ca_ok": round(a["ok"], 2),
            "ca_attente": round(ca_attente, 2),
            "ca_total": round(a["total"], 2),
            "ca_magasin_ok": round(a["ok"], 2),
            "remise_pct": round(remise_agence, 2),
            "nb_ok": a["nb_ok"],
            "nb_total": a["nb_confirm"]
        })

    df_agences = pd.DataFrame(agence_results)

    # ====================== DIRECTEURS ======================

    rules_directeurs = [
        {"directeur": "VUE JONATHAN", "agence": "BOURG ACHARD"},
        {"directeur": "AYACHE ADEL", "agence": "MAROMME"},
        {"directeur": "EL GHAZOUANI NAHIM", "agence": "HARFLEUR"},
    ]

    directeur_results = []

    ca_by_agence = {
        normalize_key(row["agence"]): row["ca_magasin_ok"]
        for _, row in df_agences.iterrows()
    } if not df_agences.empty else {}

    for rule in rules_directeurs:
        ag_key = normalize_key(rule["agence"])
        ca = ca_by_agence.get(ag_key, 0.0)
        prime = prime_magasin(ca)
        comm_magasin = round((ca * 0.01) + prime, 2) if ca > 0 else 0.0

        directeur_results.append({
            "directeur": rule["directeur"],
            "agence": rule["agence"],
            "ca_magasin_ok": round(ca, 2),
            "un_pourcent_ca": round(ca * 0.01, 2),
            "prime_palier": prime,
            "commission_magasin_eur": comm_magasin
        })

    df_directeurs = pd.DataFrame(directeur_results)

    if df_vendeurs.empty:
        st.error("❌ Aucun vendeur trouvé.")
        st.stop()

    data_to_save = {
        "df_vendeurs": df_vendeurs,
        "df_agences": df_agences,
        "df_directeurs": df_directeurs,
        "df_ok": df_ok,
        "df_c": df_confirm,
        "col_client": col_client,
        "col_doc": col_doc,
        "col_date": col_date,
        "col_op": col_op,
        "col_ca_magasin": col_ca_magasin,
        "col_vente": col_vente,
        "col_rem": col_rem,
        "col_catalogue": col_catalogue,
        "col_agence": col_agence,
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

if st.session_state.get("df_vendeurs") is not None:

    required_keys = [
        "df_ok", "df_c",
        "col_client", "col_doc", "col_date",
        "col_op", "col_ca_magasin", "col_vente",
        "col_rem", "col_catalogue",
        "col_agence", "col_com1", "col_com2", "col_com3",
        "key_cols"
    ]

    missing_keys = [k for k in required_keys if k not in st.session_state]

    if missing_keys:
        st.warning(
            "⚠️ Cette période a été sauvegardée avec une ancienne version du programme. "
            "Recharge les fichiers CONFIRM et BONLIVR puis clique sur « Lancer le traitement »."
        )
        st.stop()

    df_vendeurs = st.session_state.df_vendeurs
    df_agences = st.session_state.get("df_agences", pd.DataFrame())
    df_directeurs = st.session_state.get("df_directeurs", pd.DataFrame())
    periode = st.session_state.get("periode", "Mois inconnu")

    st.subheader(f"📅 Période : **{periode}**")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard",
        "👤 Par Vendeur",
        "🏢 Par Agence",
        "👔 Directeurs",
        "📋 Listes complètes"
    ])

    with tab1:
        total_ok = df_vendeurs["ca_ok"].sum()
        total_attente = df_vendeurs["ca_attente"].sum()
        total_global = df_vendeurs["ca_total"].sum()
        total_commissions = df_vendeurs["commission_eur"].sum()

        total_comm_magasin = (
            df_directeurs["commission_magasin_eur"].sum()
            if not df_directeurs.empty and "commission_magasin_eur" in df_directeurs.columns
            else 0
        )

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("✅ CA OK vendeurs", f"{total_ok:,.2f} €")
        c2.metric("⏳ CA attente vendeurs", f"{total_attente:,.2f} €")
        c3.metric("📌 CA Total vendeurs", f"{total_global:,.2f} €")
        c4.metric("💰 Commissions vendeurs", f"{total_commissions:,.2f} €")
        c5.metric("🏢 Comm. magasin", f"{total_comm_magasin:,.2f} €")

        st.divider()

        st.subheader("🏆 Classement vendeurs")
        st.dataframe(
            format_df_vendeurs(df_vendeurs).sort_values("Commission €", ascending=False).reset_index(drop=True),
            use_container_width=True
        )

        if not df_agences.empty:
            st.subheader("🏢 Classement agences")
            st.dataframe(
                format_df_agences(df_agences).sort_values("CA OK", ascending=False).reset_index(drop=True),
                use_container_width=True
            )

    with tab2:
        vendeur = st.selectbox("Sélectionner un commercial", sorted(df_vendeurs["Commercial"]), key="vendeur_select")

        if vendeur:
            data = df_vendeurs[df_vendeurs["Commercial"] == vendeur].iloc[0]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ CA OK", f"{data['ca_ok']:,.2f} €")
            c2.metric("⏳ CA en attente", f"{data['ca_attente']:,.2f} €")
            c3.metric("📌 CA Total", f"{data['ca_total']:,.2f} €")
            c4.metric("💰 Commission", f"{data['commission_eur']:,.2f} €")

            st.write(
                f"Remise commission hors OPC : **{data.get('remise_hors_opc_pct', 0)} %** | "
                f"Base commission : **{data.get('base_commission_pct', 0)} %** | "
                f"Points perdus : **{data.get('points_perdus', 0)}** | "
                f"Commission définitive : **{data.get('commission_pct', 0)} %**"
            )

            st.subheader(f"📋 Détail des affaires de **{vendeur}**")

            df_ok = st.session_state.df_ok.copy()
            df_c = st.session_state.df_c.copy()

            colonnes_commerciaux = [
                st.session_state.col_com1,
                st.session_state.col_com2,
                st.session_state.col_com3
            ]

            key_cols = st.session_state.key_cols

            ok_detail = df_ok[vendeur_mask(df_ok, vendeur, colonnes_commerciaux)].copy()
            attente_detail = df_c[vendeur_mask(df_c, vendeur, colonnes_commerciaux)].copy()

            if key_cols:
                ok_detail["_AFFAIRE_KEY_"] = ok_detail.apply(lambda row: make_affaire_key(row, key_cols), axis=1)
                attente_detail["_AFFAIRE_KEY_"] = attente_detail.apply(lambda row: make_affaire_key(row, key_cols), axis=1)

                ok_keys = set(ok_detail["_AFFAIRE_KEY_"])
                attente_detail = attente_detail[~attente_detail["_AFFAIRE_KEY_"].isin(ok_keys)]

                ok_detail = ok_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")
                attente_detail = attente_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")

            ok_detail["Statut"] = "✅ OK"
            attente_detail["Statut"] = "⏳ En attente"

            detail = pd.concat([ok_detail, attente_detail], ignore_index=True)

            if not detail.empty:
                cols_show = [
                    st.session_state.col_client,
                    st.session_state.col_doc,
                    st.session_state.col_date,
                    "Statut",
                    st.session_state.col_agence,
                    st.session_state.col_vente,
                    st.session_state.col_ca_magasin,
                    st.session_state.col_catalogue,
                    st.session_state.col_rem,
                    st.session_state.col_op
                ]

                cols_show = list(dict.fromkeys([c for c in cols_show if c and c in detail.columns]))
                detail_affichage = detail[cols_show].copy()

                for c in [
                    st.session_state.col_vente,
                    st.session_state.col_ca_magasin,
                    st.session_state.col_catalogue,
                    st.session_state.col_rem
                ]:
                    if c and c in detail_affichage.columns:
                        detail_affichage[c] = pd.to_numeric(detail_affichage[c], errors="coerce").fillna(0).round(2)

                st.dataframe(detail_affichage, use_container_width=True, height=600)
            else:
                st.info("Aucune affaire trouvée pour ce vendeur.")

    with tab3:
        if df_agences.empty:
            st.info("Aucune agence trouvée.")
        else:
            agence = st.selectbox("Sélectionner une agence", sorted(df_agences["agence"]), key="agence_select")

            if agence:
                data = df_agences[df_agences["agence"] == agence].iloc[0]

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("✅ CA OK agence", f"{data['ca_ok']:,.2f} €")
                c2.metric("⏳ CA en attente agence", f"{data['ca_attente']:,.2f} €")
                c3.metric("📌 CA Total agence", f"{data['ca_total']:,.2f} €")
                c4.metric("🏢 CA magasin OK", f"{data['ca_magasin_ok']:,.2f} €")

                st.write(
                    f"Remise moyenne agence : **{data['remise_pct']} %** | "
                    f"Affaires OK : **{data['nb_ok']}**"
                )

                st.subheader(f"📋 Détail des affaires de l’agence **{agence}**")

                df_ok = st.session_state.df_ok.copy()
                df_c = st.session_state.df_c.copy()
                col_agence = st.session_state.col_agence
                key_cols = st.session_state.key_cols

                ok_detail = df_ok[agence_mask(df_ok, agence, col_agence)].copy()
                attente_detail = df_c[agence_mask(df_c, agence, col_agence)].copy()

                if key_cols:
                    ok_detail["_AFFAIRE_KEY_"] = ok_detail.apply(lambda row: make_affaire_key(row, key_cols), axis=1)
                    attente_detail["_AFFAIRE_KEY_"] = attente_detail.apply(lambda row: make_affaire_key(row, key_cols), axis=1)

                    ok_keys = set(ok_detail["_AFFAIRE_KEY_"])
                    attente_detail = attente_detail[~attente_detail["_AFFAIRE_KEY_"].isin(ok_keys)]

                    ok_detail = ok_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")
                    attente_detail = attente_detail.drop(columns=["_AFFAIRE_KEY_"], errors="ignore")

                ok_detail["Statut"] = "✅ OK"
                attente_detail["Statut"] = "⏳ En attente"

                detail = pd.concat([ok_detail, attente_detail], ignore_index=True)

                if not detail.empty:
                    cols_show = [
                        st.session_state.col_client,
                        st.session_state.col_doc,
                        st.session_state.col_date,
                        "Statut",
                        st.session_state.col_agence,
                        st.session_state.col_ca_magasin,
                        st.session_state.col_vente,
                        st.session_state.col_catalogue,
                        st.session_state.col_rem,
                        st.session_state.col_op
                    ]

                    cols_show = list(dict.fromkeys([c for c in cols_show if c and c in detail.columns]))
                    detail_affichage = detail[cols_show].copy()

                    for c in [
                        st.session_state.col_ca_magasin,
                        st.session_state.col_vente,
                        st.session_state.col_catalogue,
                        st.session_state.col_rem
                    ]:
                        if c and c in detail_affichage.columns:
                            detail_affichage[c] = pd.to_numeric(detail_affichage[c], errors="coerce").fillna(0).round(2)

                    st.dataframe(detail_affichage, use_container_width=True, height=600)
                else:
                    st.info("Aucune affaire trouvée pour cette agence.")

    with tab4:
        if df_directeurs.empty:
            st.info("Aucune commission magasin calculée.")
        else:
            st.dataframe(
                format_df_directeurs(df_directeurs).sort_values("Commission magasin €", ascending=False),
                use_container_width=True
            )

    with tab5:
        st.subheader("👤 Vendeurs")
        st.dataframe(format_df_vendeurs(df_vendeurs).sort_values("Commission €", ascending=False), use_container_width=True)

        st.subheader("🏢 Agences")
        if not df_agences.empty:
            st.dataframe(format_df_agences(df_agences).sort_values("CA OK", ascending=False), use_container_width=True)

        st.subheader("👔 Directeurs")
        if not df_directeurs.empty:
            st.dataframe(format_df_directeurs(df_directeurs).sort_values("Commission magasin €", ascending=False), use_container_width=True)

    st.divider()

    col_export1, col_export2, col_export3 = st.columns(3)

    csv_vendeurs = format_df_vendeurs(df_vendeurs).to_csv(index=False, sep=";").encode("utf-8-sig")
    col_export1.download_button("📥 Export vendeurs", csv_vendeurs, f"commissions_vendeurs_{periode}.csv", "text/csv")

    if not df_agences.empty:
        csv_agences = format_df_agences(df_agences).to_csv(index=False, sep=";").encode("utf-8-sig")
        col_export2.download_button("📥 Export agences", csv_agences, f"agences_{periode}.csv", "text/csv")

    if not df_directeurs.empty:
        csv_directeurs = format_df_directeurs(df_directeurs).to_csv(index=False, sep=";").encode("utf-8-sig")
        col_export3.download_button("📥 Export directeurs", csv_directeurs, f"commissions_directeurs_{periode}.csv", "text/csv")

else:
    st.info("👉 Charge tes deux fichiers puis clique sur « Lancer le traitement »")

st.caption("✅ Version Streamlit complète • Vendeurs + Agences colonne I + OPC + Historique")