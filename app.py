
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import pickle
import json
from datetime import datetime

# ====================== CONFIG ======================

st.set_page_config(page_title="Espace Commissions ECOHABITAT", layout="wide")

# ====================== CSS DESIGN ======================

st.markdown("""
<style>

/* GLOBAL */
.stApp {
    background: #F6F8F4;
    color: #1F2933;
}

html, body, [class*="css"] {
    color: #1F2933 !important;
}

/* SIDEBAR */
[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E5E5E5;
}

[data-testid="stSidebar"] * {
    color: #1F2933 !important;
}

/* TEXTES */
h1, h2, h3, h4, h5, h6,
p, label {
    color: #1F2933 !important;
}

/* MARKDOWN + TABLEAUX */
[data-testid="stMarkdownContainer"] * {
    color: #1F2933 !important;
}

[data-testid="stDataFrame"] * {
    color: inherit !important;
}

/* HEADER */
.eco-header {
    background: white;
    padding: 22px;
    border-radius: 16px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.06);
    margin-bottom: 20px;
    border-left: 6px solid #66B32E;
}

.eco-title {
    font-size: 32px;
    font-weight: 800;
    color: #1F2933 !important;
}

.eco-subtitle {
    color: #66B32E !important;
    font-size: 15px;
    font-weight: 600;
}

/* TABS */
button[data-baseweb="tab"] {
    font-weight: 700;
    color: #1F2933 !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #66B32E !important;
}

/* BOUTONS */
.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    background: #1F2933;
    color: white !important;
}

.stButton > button[kind="primary"] {
    background-color: #66B32E !important;
}

/* ALERTES */
[data-testid="stAlert"] * {
    color: #1F2933 !important;
}

/* TABLEAUX */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}

/* CARDS */
.eco-card {
    background: white;
    padding: 20px;
    border-radius: 14px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.06);
    border-left: 6px solid #66B32E;
    text-align: center;
    min-height: 105px;
}

.eco-card-title {
    font-size: 14px;
    color: #6B7280 !important;
    font-weight: 600;
}

.eco-card-value {
    font-size: 24px;
    font-weight: 800;
    color: #1F2933 !important;
    margin-top: 8px;
}

/* CORRECTION BOUTONS SIDEBAR */
[data-testid="stSidebar"] .stButton > button {
    background: #FFFFFF !important;
    color: #1F2933 !important;
    border: 1px solid #D1D5DB !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: #66B32E !important;
    color: white !important;
    border: 1px solid #66B32E !important;
}

[data-testid="stSidebar"] .stButton > button * {
    color: inherit !important;
}

/* INPUT LOGIN / TEXT INPUT */
input[type="text"],
input[type="password"],
textarea,
select {
    background-color: #FFFFFF !important;
    color: #1F2933 !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 8px !important;
}

input:focus, textarea:focus, select:focus {
    border-color: #66B32E !important;
    box-shadow: 0 0 0 1px #66B32E !important;
}

::placeholder {
    color: #9CA3AF !important;
}

</style>
""", unsafe_allow_html=True)


# ====================== STOCKAGE LOCAL / RENDER / OVH ======================

DATA_DIR = Path("/data") if Path("/data").exists() else Path(".")

HISTORIQUE_DIR = DATA_DIR / "historique"
HISTORIQUE_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"


# ====================== USERS ======================

def load_users():
    if USERS_FILE.exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    default_users = {
        "joseph": {
            "password": "admin123",
            "role": "admin",
            "nom": "LUCCHINI JOSEPH",
            "agence": None
        }
    }

    save_users(default_users)
    return default_users


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)


# ====================== FONCTIONS DESIGN ======================

def card(title, value):
    st.markdown(f"""
    <div class="eco-card">
        <div class="eco-card-title">{title}</div>
        <div class="eco-card-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


# ====================== FONCTIONS OUTILS ======================

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


# ====================== FONCTIONS PÉRIODES / ANNUEL ======================

MOIS_FR = {
    "JANVIER": 1,
    "FEVRIER": 2,
    "FÉVRIER": 2,
    "MARS": 3,
    "AVRIL": 4,
    "MAI": 5,
    "JUIN": 6,
    "JUILLET": 7,
    "AOUT": 8,
    "AOÛT": 8,
    "SEPTEMBRE": 9,
    "OCTOBRE": 10,
    "NOVEMBRE": 11,
    "DECEMBRE": 12,
    "DÉCEMBRE": 12,
}


def periode_to_month_year(periode):
    if not periode:
        return None, None

    parts = str(periode).strip().upper().split()

    if len(parts) < 2:
        return None, None

    mois = MOIS_FR.get(parts[0])
    annee = None

    for p in parts[1:]:
        if p.isdigit() and len(p) == 4:
            annee = int(p)
            break

    return mois, annee


def periode_sort_key(periode):
    mois, annee = periode_to_month_year(periode)
    return (annee or 0, mois or 0)


def is_periode_comptable_annuelle(periode, annee_selectionnee, use_m2=True):
    mois, annee = periode_to_month_year(periode)

    if not mois or not annee:
        return False

    if annee != annee_selectionnee:
        return False

    if not use_m2:
        return True

    today = datetime.today()

    if annee < today.year:
        return True

    if annee > today.year:
        return False

    return mois <= today.month - 2


def load_all_historique():
    rows_vendeurs = []
    rows_agences = []
    rows_directeurs = []

    for periode in list_periodes():
        data = load_periode(periode)

        if not data:
            continue

        mois, annee = periode_to_month_year(periode)

        if "df_vendeurs" in data and isinstance(data["df_vendeurs"], pd.DataFrame):
            dfv = data["df_vendeurs"].copy()
            dfv["periode"] = periode
            dfv["mois_num"] = mois
            dfv["annee"] = annee
            rows_vendeurs.append(dfv)

        if "df_agences" in data and isinstance(data["df_agences"], pd.DataFrame):
            dfa = data["df_agences"].copy()
            dfa["periode"] = periode
            dfa["mois_num"] = mois
            dfa["annee"] = annee
            rows_agences.append(dfa)

        if "df_directeurs" in data and isinstance(data["df_directeurs"], pd.DataFrame):
            dfd = data["df_directeurs"].copy()
            dfd["periode"] = periode
            dfd["mois_num"] = mois
            dfd["annee"] = annee
            rows_directeurs.append(dfd)

    df_all_vendeurs = pd.concat(rows_vendeurs, ignore_index=True) if rows_vendeurs else pd.DataFrame()
    df_all_agences = pd.concat(rows_agences, ignore_index=True) if rows_agences else pd.DataFrame()
    df_all_directeurs = pd.concat(rows_directeurs, ignore_index=True) if rows_directeurs else pd.DataFrame()

    return df_all_vendeurs, df_all_agences, df_all_directeurs


# ====================== FORMAT TABLEAUX ======================

def format_df_vendeurs(df):
    if df.empty:
        return df
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
    if df.empty:
        return df
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
    if df.empty:
        return df
    return df.rename(columns={
        "directeur": "Directeur",
        "agence": "Agence",
        "ca_magasin_ok": "CA magasin OK",
        "un_pourcent_ca": "1% CA",
        "prime_palier": "Prime palier",
        "commission_magasin_eur": "Commission magasin €",
    })


# ====================== LOGIN ======================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Connexion - ECOHABITAT")

    username = st.text_input("Identifiant")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter", type="primary"):
        users = load_users()
        user = users.get(username.lower())

        if user and user.get("password") == password:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.session_state.username = username.lower()
            st.rerun()
        else:
            st.error("Identifiant ou mot de passe incorrect.")

    st.stop()

user = st.session_state.user
role = user["role"]


# ====================== HEADER ======================

st.markdown('<div class="eco-header">', unsafe_allow_html=True)

col1, col2 = st.columns([1, 6])

with col1:
    try:
        st.image("logo.png", width=90)
    except Exception:
        st.markdown("🏠")

with col2:
    st.markdown('<div class="eco-title">Espace Commissions EcoHabitat</div>', unsafe_allow_html=True)
    st.markdown('<div class="eco-subtitle">L’excellence au service de votre habitat</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

st.caption(
    "Logique : Vendeurs = colonne Q | Agences = colonne I | "
    "Remise commission hors OPC | Directeur agence = 1% CA agence + prime"
)

st.sidebar.success(f"Connecté : {user['nom']} ({role})")

if st.sidebar.button("🚪 Déconnexion"):
    for k in ["logged_in", "user", "username"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


# ====================== PARAMÈTRES TEST ======================

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Paramètres")

use_m2_rule = st.sidebar.checkbox(
    "Activer règle M-2",
    value=True
)

if not use_m2_rule:
    st.sidebar.warning("⚠️ Mode TEST : règle M-2 désactivée")


# ====================== SIDEBAR HISTORIQUE ======================

st.sidebar.markdown("---")
st.sidebar.subheader("📂 Historique")

periodes_dispo = sorted(list_periodes(), key=periode_sort_key)

periode_load = st.sidebar.selectbox(
    "Charger une période sauvegardée",
    [""] + periodes_dispo
)

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


# ====================== IMPORT ADMIN ======================

if role == "admin":

    st.sidebar.markdown("---")
    st.sidebar.header("📤 Import ProDevis")

    f_confirm = st.sidebar.file_uploader("Fichier CONFIRM", type=["xlsx"], key="upload_confirm")
    f_ok = st.sidebar.file_uploader("Fichier BONLIVR", type=["xlsx"], key="upload_ok")

    periode = st.sidebar.text_input("📅 Période", value="Avril 2026", key="periode_input")

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

        col_client = get_col_by_excel_position(df_confirm, 1)
        col_com1 = get_col_by_excel_position(df_confirm, 2)
        col_com2 = get_col_by_excel_position(df_confirm, 3)
        col_com3 = get_col_by_excel_position(df_confirm, 4)
        col_date = get_col_by_excel_position(df_confirm, 6)
        col_doc = get_col_by_excel_position(df_confirm, 7)
        col_op = get_col_by_excel_position(df_confirm, 8)
        col_ca_magasin = get_col_by_excel_position(df_confirm, 9)
        col_vente = get_col_by_excel_position(df_confirm, 17)
        col_rem = get_col_by_excel_position(df_confirm, 24)
        col_catalogue = get_col_by_excel_position(df_confirm, 25)
        col_agence = get_col_by_excel_position(df_confirm, 50)

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

        agences = {}

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


# ====================== BACK OFFICE USERS ======================

def afficher_admin_users():
    st.subheader("⚙️ Gestion des utilisateurs")

    users = load_users()

    st.write("### 👥 Utilisateurs existants")

    if users:
        df_users = pd.DataFrame.from_dict(users, orient="index")
        df_users.index.name = "Identifiant"
        st.dataframe(df_users, use_container_width=True)
    else:
        st.info("Aucun utilisateur.")

    st.divider()

    st.write("### ➕ Ajouter un utilisateur")

    col1, col2 = st.columns(2)

    with col1:
        new_user = st.text_input("Nouvel identifiant", key="new_user").lower().strip()
        new_password = st.text_input("Mot de passe", type="password", key="new_password")

    with col2:
        new_role = st.selectbox("Rôle", ["admin", "vendeur", "directeur_agence"], key="new_role")
        new_nom = st.text_input("Nom vendeur / utilisateur", key="new_nom").upper().strip()
        new_agence = st.text_input("Agence si directeur", key="new_agence").upper().strip()

    if st.button("Créer utilisateur", type="primary"):
        if not new_user or not new_password or not new_nom:
            st.error("Identifiant, mot de passe et nom sont obligatoires.")
        elif new_user in users:
            st.error("Cet utilisateur existe déjà.")
        else:
            users[new_user] = {
                "password": new_password,
                "role": new_role,
                "nom": new_nom,
                "agence": new_agence if new_role == "directeur_agence" else None
            }
            save_users(users)
            st.success("Utilisateur créé ✅")
            st.rerun()

    st.divider()

    st.write("### ✏️ Modifier un utilisateur")

    if users:
        user_edit = st.selectbox("Utilisateur à modifier", list(users.keys()), key="user_edit")

        if user_edit:
            u = users[user_edit]

            edit_password = st.text_input("Mot de passe", value=u.get("password", ""), type="password", key="edit_password")

            role_options = ["admin", "vendeur", "directeur_agence"]
            current_role = u.get("role", "vendeur")
            role_index = role_options.index(current_role) if current_role in role_options else 1

            edit_role = st.selectbox("Rôle", role_options, index=role_index, key="edit_role")
            edit_nom = st.text_input("Nom vendeur / utilisateur", value=u.get("nom", ""), key="edit_nom").upper().strip()
            edit_agence = st.text_input("Agence", value=u.get("agence") or "", key="edit_agence").upper().strip()

            if st.button("Enregistrer modification"):
                users[user_edit] = {
                    "password": edit_password,
                    "role": edit_role,
                    "nom": edit_nom,
                    "agence": edit_agence if edit_role == "directeur_agence" else None
                }
                save_users(users)

                if user_edit == st.session_state.get("username"):
                    st.session_state.user = users[user_edit]

                st.success("Utilisateur modifié ✅")
                st.rerun()

    st.divider()

    st.write("### ❌ Supprimer un utilisateur")

    users = load_users()

    if users:
        user_delete = st.selectbox("Utilisateur à supprimer", list(users.keys()), key="user_delete")

        if st.button("Supprimer utilisateur"):
            if user_delete == st.session_state.get("username"):
                st.error("Tu ne peux pas supprimer ton propre compte connecté.")
            elif user_delete == "joseph":
                st.error("Impossible de supprimer l’admin principal Joseph.")
            else:
                del users[user_delete]
                save_users(users)
                st.success("Utilisateur supprimé ✅")
                st.rerun()


# ====================== AFFICHAGE ANNUEL ======================

def afficher_annuel(tab):
    with tab:
        st.subheader("📆 Analyse annuelle")

        df_all_vendeurs, df_all_agences, df_all_directeurs = load_all_historique()

        if df_all_vendeurs.empty and df_all_agences.empty:
            st.info("Aucune période historique disponible pour construire l’analyse annuelle.")
            return

        annees_detectees = []
        for df_src in [df_all_vendeurs, df_all_agences]:
            if not df_src.empty and "annee" in df_src.columns:
                annees_detectees += [int(a) for a in df_src["annee"].dropna().unique()]

        annees = sorted(set(annees_detectees))

        if not annees:
            st.warning("Impossible de détecter les années depuis les périodes sauvegardées. Utilise un format du type : Avril 2026.")
            return

        default_year = datetime.today().year if datetime.today().year in annees else max(annees)

        annee_selectionnee = st.selectbox(
            "Année analysée",
            annees,
            index=annees.index(default_year)
        )

        periodes_comptables = [
            p for p in sorted(list_periodes(), key=periode_sort_key)
            if is_periode_comptable_annuelle(p, annee_selectionnee, use_m2_rule)
        ]

        if periodes_comptables:
            if use_m2_rule:
                st.caption("Mois comptabilisés selon la règle M-2 : " + ", ".join(periodes_comptables))
            else:
                st.warning("⚠️ Mode TEST actif : toutes les périodes de l’année sélectionnée sont comptabilisées.")
                st.caption("Mois comptabilisés : " + ", ".join(periodes_comptables))
        else:
            st.warning("Aucun mois comptabilisable pour cette année.")
            return

        df_v = df_all_vendeurs[
            df_all_vendeurs["periode"].isin(periodes_comptables)
        ].copy() if not df_all_vendeurs.empty else pd.DataFrame()

        df_a = df_all_agences[
            df_all_agences["periode"].isin(periodes_comptables)
        ].copy() if not df_all_agences.empty else pd.DataFrame()

        if role == "vendeur":
            df_v = df_v[
                df_v["Commercial"].apply(normalize_key) == normalize_key(user["nom"])
            ].copy() if not df_v.empty else pd.DataFrame()
            df_a = pd.DataFrame()

        elif role == "directeur_agence":
            df_v = df_v[
                df_v["Commercial"].apply(normalize_key) == normalize_key(user["nom"])
            ].copy() if not df_v.empty else pd.DataFrame()

            if not df_a.empty:
                df_a = df_a[
                    df_a["agence"].apply(normalize_key) == normalize_key(user["agence"])
                ].copy()

        total_ok_annuel = df_v["ca_ok"].sum() if not df_v.empty and "ca_ok" in df_v.columns else 0
        total_commissions_annuel = df_v["commission_eur"].sum() if not df_v.empty and "commission_eur" in df_v.columns else 0
        total_agence_ok_annuel = df_a["ca_ok"].sum() if not df_a.empty and "ca_ok" in df_a.columns else 0

        c1, c2, c3 = st.columns(3)

        with c1:
            card("✅ CA OK vendeurs annuel", f"{total_ok_annuel:,.2f} €")

        with c2:
            card("💰 Commissions vendeurs", f"{total_commissions_annuel:,.2f} €")

        with c3:
            card("🏢 CA OK agences annuel", f"{total_agence_ok_annuel:,.2f} €")

        st.divider()

        if not df_v.empty:
            df_classement_vendeurs = (
                df_v
                .groupby("Commercial", as_index=False)
                .agg({
                    "ca_ok": "sum",
                    "commission_eur": "sum"
                })
                .sort_values("ca_ok", ascending=False)
                .reset_index(drop=True)
            )

            df_classement_vendeurs.insert(0, "Rang", range(1, len(df_classement_vendeurs) + 1))

            st.subheader("🏆 Classement annuel vendeurs — CA OK")
            st.dataframe(
                df_classement_vendeurs.rename(columns={
                    "ca_ok": "CA OK annuel",
                    "commission_eur": "Commission annuelle"
                }),
                use_container_width=True
            )

            df_mensuel_vendeurs = (
                df_v
                .groupby(["periode", "mois_num"], as_index=False)
                .agg({
                    "ca_ok": "sum",
                    "commission_eur": "sum"
                })
                .sort_values("mois_num")
            )

            st.subheader("📈 Évolution mensuelle vendeurs")
            st.dataframe(
                df_mensuel_vendeurs.rename(columns={
                    "periode": "Période",
                    "ca_ok": "CA OK",
                    "commission_eur": "Commission"
                }).drop(columns=["mois_num"], errors="ignore"),
                use_container_width=True
            )
        else:
            st.info("Aucune donnée vendeur pour cette analyse annuelle.")

        if role in ["admin", "directeur_agence"]:
            st.divider()

            if not df_a.empty:
                df_classement_agences = (
                    df_a
                    .groupby("agence", as_index=False)
                    .agg({
                        "ca_ok": "sum",
                        "ca_magasin_ok": "sum",
                        "nb_ok": "sum",
                        "nb_total": "sum"
                    })
                    .sort_values("ca_ok", ascending=False)
                    .reset_index(drop=True)
                )

                df_classement_agences.insert(0, "Rang", range(1, len(df_classement_agences) + 1))

                st.subheader("🏢 Classement annuel agences — CA OK")
                st.dataframe(
                    df_classement_agences.rename(columns={
                        "agence": "Agence",
                        "ca_ok": "CA OK annuel",
                        "ca_magasin_ok": "CA magasin OK annuel",
                        "nb_ok": "Nb affaires OK",
                        "nb_total": "Nb affaires total"
                    }),
                    use_container_width=True
                )

                df_mensuel_agences = (
                    df_a
                    .groupby(["periode", "mois_num"], as_index=False)
                    .agg({
                        "ca_ok": "sum",
                        "ca_magasin_ok": "sum",
                        "nb_ok": "sum"
                    })
                    .sort_values("mois_num")
                )

                st.subheader("📈 Évolution mensuelle agences")
                st.dataframe(
                    df_mensuel_agences.rename(columns={
                        "periode": "Période",
                        "ca_ok": "CA OK",
                        "ca_magasin_ok": "CA magasin OK",
                        "nb_ok": "Nb affaires OK"
                    }).drop(columns=["mois_num"], errors="ignore"),
                    use_container_width=True
                )
            else:
                st.info("Aucune donnée agence pour cette analyse annuelle.")


# ====================== AFFICHAGE DONNÉES ======================

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
            "⚠️ Cette période a été sauvegardée avec une ancienne version. "
            "Demande à un admin de recharger les fichiers CONFIRM et BONLIVR puis de relancer le traitement."
        )
        st.stop()

    df_vendeurs_all = st.session_state.df_vendeurs.copy()
    df_agences_all = st.session_state.get("df_agences", pd.DataFrame()).copy()
    df_directeurs_all = st.session_state.get("df_directeurs", pd.DataFrame()).copy()
    periode = st.session_state.get("periode", "Mois inconnu")

    # ====================== FILTRAGE ROLE ======================

    if role == "vendeur":
        df_vendeurs = df_vendeurs_all[
            df_vendeurs_all["Commercial"].apply(normalize_key) == normalize_key(user["nom"])
        ].copy()

        df_agences = pd.DataFrame()
        df_directeurs = pd.DataFrame()

    elif role == "directeur_agence":
        df_vendeurs = df_vendeurs_all[
            df_vendeurs_all["Commercial"].apply(normalize_key) == normalize_key(user["nom"])
        ].copy()

        df_agences = df_agences_all[
            df_agences_all["agence"].apply(normalize_key) == normalize_key(user["agence"])
        ].copy() if not df_agences_all.empty else pd.DataFrame()

        df_directeurs = df_directeurs_all[
            df_directeurs_all["directeur"].apply(normalize_key) == normalize_key(user["nom"])
        ].copy() if not df_directeurs_all.empty else pd.DataFrame()

    else:
        df_vendeurs = df_vendeurs_all
        df_agences = df_agences_all
        df_directeurs = df_directeurs_all

    st.subheader(f"📅 Période : **{periode}**")

    if role == "admin":
        tabs = st.tabs([
            "📊 Dashboard",
            "📆 Annuel",
            "👤 Par Vendeur",
            "🏢 Par Agence",
            "👔 Directeurs",
            "📋 Listes complètes",
            "⚙️ Utilisateurs"
        ])

    elif role == "directeur_agence":
        tabs = st.tabs([
            "👤 Mes chiffres",
            "📆 Annuel",
            "🏢 Mon agence",
            "👔 Commission agence"
        ])

    else:
        tabs = st.tabs([
            "👤 Mes chiffres",
            "📆 Annuel"
        ])

    # ====================== FONCTIONS AFFICHAGE ======================

    def afficher_vendeur(tab, vendeur_forced=None):
        with tab:
            if df_vendeurs.empty:
                st.info("Aucune donnée vendeur disponible pour ce compte.")
                return

            if vendeur_forced:
                vendeur = vendeur_forced
            else:
                vendeur = st.selectbox("Sélectionner un commercial", sorted(df_vendeurs["Commercial"]), key="vendeur_select")

            data = df_vendeurs[df_vendeurs["Commercial"].apply(normalize_key) == normalize_key(vendeur)]

            if data.empty:
                st.info("Aucune donnée trouvée pour ce vendeur.")
                return

            data = data.iloc[0]

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                card("✅ CA OK", f"{data['ca_ok']:,.2f} €")

            with c2:
                card("⏳ CA en attente", f"{data['ca_attente']:,.2f} €")

            with c3:
                card("📌 CA Total", f"{data['ca_total']:,.2f} €")

            with c4:
                card("💰 Commission", f"{data['commission_eur']:,.2f} €")

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
                col_client = st.session_state.col_client
                col_doc = st.session_state.col_doc
                col_date = st.session_state.col_date
                col_agence = st.session_state.col_agence
                col_vente = st.session_state.col_vente
                col_ca_magasin = st.session_state.col_ca_magasin
                col_catalogue = st.session_state.col_catalogue
                col_rem = st.session_state.col_rem
                col_op = st.session_state.col_op

                detail_calc = detail.copy()

                for c in [col_vente, col_ca_magasin, col_catalogue, col_rem]:
                    if c and c in detail_calc.columns:
                        detail_calc[c] = pd.to_numeric(detail_calc[c], errors="coerce").fillna(0)

                def count_vendeurs_row(row):
                    nb = 0
                    for c in colonnes_commerciaux:
                        if c and c in row.index and clean_visible(row.get(c)):
                            nb += 1
                    return max(nb, 1)

                detail_calc["Nombre de vendeurs"] = detail_calc.apply(count_vendeurs_row, axis=1)

                if col_catalogue and col_catalogue in detail_calc.columns and col_rem and col_rem in detail_calc.columns:
                    detail_calc["Remise %"] = np.where(
                        detail_calc[col_catalogue] > 0,
                        detail_calc[col_rem] / detail_calc[col_catalogue] * 100,
                        0
                    )
                else:
                    detail_calc["Remise %"] = 0

                # Bonus / Malus par dossier :
                # base théorique = Total ventes avant remise avec 15 % de remise, réparti par nombre de vendeurs.
                # règle OPC : les remises OPC ne comptent pas dans la remise moyenne ;
                # pour le bonus/malus, on neutralise les malus OPC mais on conserve les bonus éventuels.
                if col_catalogue and col_catalogue in detail_calc.columns and col_vente and col_vente in detail_calc.columns:
                    objectif_15_par_vendeur = (detail_calc[col_catalogue] * 0.85) / detail_calc["Nombre de vendeurs"]
                    detail_calc["Bonus / Malus"] = detail_calc[col_vente] - objectif_15_par_vendeur
                else:
                    detail_calc["Bonus / Malus"] = 0

                if col_op and col_op in detail_calc.columns:
                    opc_mask = detail_calc.apply(lambda row: is_opc(row, col_op), axis=1)
                    detail_calc.loc[opc_mask & (detail_calc["Bonus / Malus"] < 0), "Bonus / Malus"] = 0
                    detail_calc["OPC"] = np.where(opc_mask, "OUI", "")
                else:
                    opc_mask = pd.Series(False, index=detail_calc.index)
                    detail_calc["OPC"] = ""

                remise_total_hors_opc = 0
                if col_catalogue and col_catalogue in detail_calc.columns and col_rem and col_rem in detail_calc.columns:
                    base_hors_opc = detail_calc.loc[~opc_mask, col_catalogue].sum()
                    rem_hors_opc = detail_calc.loc[~opc_mask, col_rem].sum()
                    remise_total_hors_opc = (rem_hors_opc / base_hors_opc * 100) if base_hors_opc > 0 else 0

                bonus_malus_valides = detail_calc.loc[
                    detail_calc["Statut"].astype(str).str.contains("OK", case=False, na=False),
                    "Bonus / Malus"
                ].sum()

                bonus_malus_global = detail_calc["Bonus / Malus"].sum()

                c_bonus1, c_bonus2, c_bonus3 = st.columns(3)
                with c_bonus1:
                    card("📉 Remise moyenne hors OPC", f"{remise_total_hors_opc:,.2f} %")
                with c_bonus2:
                    card("✅ Bonus / Malus validés", f"{bonus_malus_valides:,.2f} €")
                with c_bonus3:
                    card("📊 Bonus / Malus global", f"{bonus_malus_global:,.2f} €")

                cols_show = [
                    col_client,
                    col_doc,
                    col_date,
                    "Statut",
                    col_agence,
                    col_vente,
                    col_ca_magasin,
                    "Remise %",
                    "OPC",
                    "Bonus / Malus"
                ]

                cols_show = list(dict.fromkeys([c for c in cols_show if c and c in detail_calc.columns]))
                detail_affichage = detail_calc[cols_show].copy()

                rename_detail_cols = {}
                if col_client:
                    rename_detail_cols[col_client] = "Client / Référence affaire"
                if col_doc:
                    rename_detail_cols[col_doc] = "N° Document"
                if col_date:
                    rename_detail_cols[col_date] = "Date document"
                if col_agence:
                    rename_detail_cols[col_agence] = "Agence"
                if col_vente:
                    rename_detail_cols[col_vente] = "TOTAL VENTE"
                if col_ca_magasin:
                    rename_detail_cols[col_ca_magasin] = "Vente HT hors acompte"

                detail_affichage = detail_affichage.rename(columns=rename_detail_cols)

                for c in ["TOTAL VENTE", "Vente HT hors acompte", "Remise %", "Bonus / Malus"]:
                    if c in detail_affichage.columns:
                        detail_affichage[c] = pd.to_numeric(detail_affichage[c], errors="coerce").fillna(0).round(2)

                def color_bonus_malus(val):
                    try:
                        v = float(val)
                    except Exception:
                        return ""
                    if v > 0:
                        return "background-color: #D1FADF; color: #065F46; font-weight: 700"
                    if v < 0:
                        return "background-color: #FECACA; color: #991B1B; font-weight: 700"
                    return ""

                styled_detail = (
                    detail_affichage.style
                    .map(
                        color_bonus_malus,
                        subset=["Bonus / Malus"] if "Bonus / Malus" in detail_affichage.columns else []
                    )
                    .format({
                        "TOTAL VENTE": "{:,.2f} €",
                        "Vente HT hors acompte": "{:,.2f} €",
                        "Remise %": "{:.2f} %",
                        "Bonus / Malus": "{:,.2f} €",
                    })
                )

                st.dataframe(styled_detail, use_container_width=True, height=600)
            else:
                st.info("Aucune affaire trouvée pour ce vendeur.")

    def afficher_agence(tab, agence_forced=None):
        with tab:
            if df_agences.empty:
                st.info("Aucune donnée agence disponible pour ce compte.")
                return

            if agence_forced:
                agence = agence_forced
            else:
                agence = st.selectbox("Sélectionner une agence", sorted(df_agences["agence"]), key="agence_select")

            data = df_agences[df_agences["agence"].apply(normalize_key) == normalize_key(agence)]

            if data.empty:
                st.info("Aucune donnée trouvée pour cette agence.")
                return

            data = data.iloc[0]

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                card("✅ CA OK agence", f"{data['ca_ok']:,.2f} €")

            with c2:
                card("⏳ CA en attente agence", f"{data['ca_attente']:,.2f} €")

            with c3:
                card("📌 CA Total agence", f"{data['ca_total']:,.2f} €")

            with c4:
                card("🏢 CA magasin OK", f"{data['ca_magasin_ok']:,.2f} €")

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

    # ====================== AFFICHAGE SELON ROLE ======================

    if role == "admin":

        with tabs[0]:
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

            with c1:
                card("✅ CA OK vendeurs", f"{total_ok:,.2f} €")

            with c2:
                card("⏳ CA attente vendeurs", f"{total_attente:,.2f} €")

            with c3:
                card("📌 CA Total vendeurs", f"{total_global:,.2f} €")

            with c4:
                card("💰 Commissions vendeurs", f"{total_commissions:,.2f} €")

            with c5:
                card("🏢 Comm. magasin", f"{total_comm_magasin:,.2f} €")

            st.divider()

            st.subheader("🏆 Classement vendeurs")
            st.dataframe(
                format_df_vendeurs(df_vendeurs).sort_values("CA OK", ascending=False).reset_index(drop=True),
                use_container_width=True
            )

            if not df_agences.empty:
                st.subheader("🏢 Classement agences")
                st.dataframe(
                    format_df_agences(df_agences).sort_values("CA OK", ascending=False).reset_index(drop=True),
                    use_container_width=True
                )

        afficher_annuel(tabs[1])
        afficher_vendeur(tabs[2])
        afficher_agence(tabs[3])

        with tabs[4]:
            if df_directeurs.empty:
                st.info("Aucune commission magasin calculée.")
            else:
                st.dataframe(
                    format_df_directeurs(df_directeurs).sort_values("Commission magasin €", ascending=False),
                    use_container_width=True
                )

        with tabs[5]:
            st.subheader("👤 Vendeurs")
            st.dataframe(format_df_vendeurs(df_vendeurs).sort_values("CA OK", ascending=False), use_container_width=True)

            st.subheader("🏢 Agences")
            if not df_agences.empty:
                st.dataframe(format_df_agences(df_agences).sort_values("CA OK", ascending=False), use_container_width=True)

            st.subheader("👔 Directeurs")
            if not df_directeurs.empty:
                st.dataframe(format_df_directeurs(df_directeurs).sort_values("Commission magasin €", ascending=False), use_container_width=True)

        with tabs[6]:
            afficher_admin_users()

    elif role == "directeur_agence":
        afficher_vendeur(tabs[0], vendeur_forced=user["nom"])
        afficher_annuel(tabs[1])
        afficher_agence(tabs[2], agence_forced=user["agence"])

        with tabs[3]:
            if df_directeurs.empty:
                st.info("Aucune commission agence disponible.")
            else:
                st.dataframe(format_df_directeurs(df_directeurs), use_container_width=True)

    elif role == "vendeur":
        afficher_vendeur(tabs[0], vendeur_forced=user["nom"])
        afficher_annuel(tabs[1])

    # ====================== EXPORTS ADMIN ======================

    if role == "admin":
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
    st.info("👉 Charge une période sauvegardée depuis la barre latérale.")
    if role == "admin":
        st.info("Ou charge les fichiers CONFIRM / BONLIVR puis clique sur « Lancer le traitement ».")

        st.divider()

        tabs_empty = st.tabs(["📆 Annuel", "⚙️ Utilisateurs"])
        afficher_annuel(tabs_empty[0])

        with tabs_empty[1]:
            afficher_admin_users()

st.caption("✅ Version avec login + gestion utilisateurs • Admin / Vendeur / Directeur agence • Design EcoHabitat • Analyse annuelle M-2")
