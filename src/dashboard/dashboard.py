"""
dashboard.py — Le moniteur du data lake médical
================================================
Six pages, dans l'ordre de notre raisonnement :

    1. Notre projet         — le problème et notre réponse
    2. L'architecture       — comment les données circulent
    3. Le lake en direct    — l'état réel du système
    4. Cœur (ECG)           — notre premier domaine
    5. Cerveau (EEG)        — notre second domaine, bien plus difficile
    6. Ce que nous retenons — le bilan, sans embellir

⚠️ PRINCIPE D'ARCHITECTURE :
Ce dashboard ne va JAMAIS chercher les données lui-même dans l'entrepôt ou la
base. Il les DEMANDE à l'API Gateway, qui va les chercher pour lui — comme un
client au restaurant commande au serveur plutôt que d'aller en cuisine.
Conséquence : si nous remplacions PostgreSQL par une autre base, seule l'API
changerait. Ce fichier ne bougerait pas d'une ligne.

Pour le lancer (l'API doit tourner en parallèle) :
    Terminal 1 :  uvicorn src.api.main:app
    Terminal 2 :  streamlit run src/dashboard/dashboard.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = "http://localhost:8000"

# Dossier contenant l'instantané des données, utilisé quand l'API est
# injoignable (typiquement : le dashboard déployé sur Streamlit Cloud, qui ne
# peut évidemment pas joindre le « localhost » de notre machine).
DOSSIER_DEMO = Path(__file__).resolve().parents[2] / "demo_data"

# Palette : sobre, clinique. Un seul rouge, réservé à ce qui alerte.
ENCRE = "#14213D"
ARDOISE = "#8D99AE"
SIGNAL = "#C1121F"
PAPIER = "#FFFFFF"
FOND = "#F7F8FA"

st.set_page_config(page_title="Data Lake médical", page_icon="🫀", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: {FOND}; }}
    h1, h2, h3, h4 {{ color: {ENCRE} !important; letter-spacing: -0.01em; }}
    p, li, span, label {{ color: #2B3245; }}

    div[data-testid="stMetricValue"] {{ color: {ENCRE} !important; font-weight: 650; }}
    div[data-testid="stMetricLabel"] p {{
        color: #5A6478 !important; font-size: 0.80rem !important;
        text-transform: uppercase; letter-spacing: 0.04em;
    }}
    div[data-testid="stMetricDelta"] {{ color: #5A6478 !important; }}
    div[data-testid="stMetric"] {{
        background: {PAPIER}; padding: 1rem 1.2rem;
        border: 1px solid #E4E7EE; border-radius: 6px;
    }}

    .note {{
        background: {PAPIER}; border-left: 3px solid {ENCRE};
        padding: 1rem 1.2rem; margin: 0.8rem 0 1.4rem 0;
        color: #2B3245; font-size: 0.94rem; line-height: 1.6;
        border-radius: 0 4px 4px 0;
    }}
    .note strong {{ color: {ENCRE}; }}

    .alerte {{
        background: #FFF5F6; border-left: 3px solid {SIGNAL};
        padding: 1rem 1.2rem; margin: 0.8rem 0 1.4rem 0;
        color: #5E1E26; font-size: 0.94rem; line-height: 1.6;
        border-radius: 0 4px 4px 0;
    }}
    .alerte strong {{ color: {SIGNAL}; }}

    .etape {{
        background: {PAPIER}; border: 1px solid #E4E7EE;
        border-radius: 6px; padding: 1.1rem 1.3rem; height: 100%;
    }}
    .etape .num {{ color: {SIGNAL}; font-size: 0.76rem; font-weight: 700;
                   letter-spacing: 0.1em; margin-bottom: 0.35rem; }}
    .etape .titre {{ color: {ENCRE}; font-weight: 650; margin-bottom: 0.4rem; }}
    .etape .texte {{ color: #5A6478; font-size: 0.87rem; line-height: 1.55; }}

    section[data-testid="stSidebar"] {{ background-color: {PAPIER}; }}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Accès à l'API
# ----------------------------------------------------------------------
@st.cache_data(ttl=30)
def api_disponible() -> bool:
    """L'API répond-elle ? Détermine si nous sommes en direct ou en mode démo."""
    try:
        requests.get(f"{API_URL}/health", timeout=5).raise_for_status()
        return True
    except Exception:
        return False


@st.cache_data(ttl=30)
def api_get(chemin: str, params: dict | None = None):
    """
    Interroge l'API Gateway.

    Si l'API ne répond pas (cas du dashboard déployé en ligne), bascule
    automatiquement sur l'instantané figé dans demo_data/.
    """
    try:
        r = requests.get(f"{API_URL}{chemin}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:
        pass  # on passe en mode démo

    # --- MODE DÉMO ---
    if chemin == "/health":
        return {"status": "demo",
                "services": {"minio": "démo", "postgresql": "démo"}}

    if chemin == "/stats":
        fichier = DOSSIER_DEMO / "stats.json"
        if fichier.exists():
            return json.loads(fichier.read_text(encoding="utf-8"))

    return None


@st.cache_data(ttl=30)
def charger_domaine(source: str) -> pd.DataFrame:
    """
    Récupère TOUTES les lignes d'un domaine.

    ⚠️ Pourquoi paginer ? L'API plafonne à 1000 lignes par appel (une sécurité
    pour ne pas saturer le réseau). Sans pagination, nous ne recevions que les
    1000 premières lignes — soit un seul patient ! C'était un vrai bug : les
    autres patients semblaient ne pas exister.

    Si l'API est injoignable, on lit l'instantané de demo_data/.
    """
    if not api_disponible():
        fichier = DOSSIER_DEMO / f"curated_{source}.parquet"
        return pd.read_parquet(fichier) if fichier.exists() else pd.DataFrame()

    morceaux, offset = [], 0
    while True:
        rep = api_get("/curated", {"source": source, "limit": 1000, "offset": offset})
        if not rep or not rep.get("donnees"):
            break
        morceaux.append(pd.DataFrame(rep["donnees"]))
        if len(rep["donnees"]) < 1000:
            break
        offset += 1000
        if offset > 50000:   # garde-fou
            break
    return pd.concat(morceaux, ignore_index=True) if morceaux else pd.DataFrame()


def note(t): st.markdown(f'<div class="note">{t}</div>', unsafe_allow_html=True)
def alerte(t): st.markdown(f'<div class="alerte">{t}</div>', unsafe_allow_html=True)


def etape(num, titre, texte):
    st.markdown(
        f'<div class="etape"><div class="num">{num}</div>'
        f'<div class="titre">{titre}</div>'
        f'<div class="texte">{texte}</div></div>', unsafe_allow_html=True)


def styler(fig, hauteur=340):
    """Style commun : texte toujours lisible, quel que soit le thème."""
    fig.update_layout(
        plot_bgcolor=PAPIER, paper_bgcolor=PAPIER,
        height=hauteur, margin=dict(t=50, b=45, l=65, r=25),
        font=dict(color=ENCRE, size=13),
        xaxis=dict(gridcolor="#EDEFF3", linecolor="#D5D9E2",
                   tickfont=dict(color="#5A6478"),
                   title_font=dict(color=ENCRE, size=13)),
        yaxis=dict(gridcolor="#EDEFF3", linecolor="#D5D9E2",
                   tickfont=dict(color="#5A6478"),
                   title_font=dict(color=ENCRE, size=13)),
        legend=dict(orientation="h", y=1.14, x=0,
                    font=dict(color=ENCRE, size=12), bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ----------------------------------------------------------------------
# Navigation + voyant de santé
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🫀 Data Lake médical")
    st.caption("Cours Data Lakes & Data Integration")
    page = st.radio("Navigation", [
        "1 · Notre projet", "2 · L'architecture", "3 · Le lake en direct",
        "4 · Cœur (ECG)", "5 · Cerveau (EEG)", "6 · Air (API temps réel)",
        "7 · Ce que nous retenons",
    ], label_visibility="collapsed")

    st.divider()
    st.markdown("**État des services**")

    if api_disponible():
        sante = api_get("/health")
        s = sante.get("services", {})
        vivant = sante.get("status") == "healthy"
        st.caption("Interrogé en direct sur `/health`.")
        st.markdown(f"### {'🟢' if vivant else '🟠'} {'Tout répond' if vivant else 'Dégradé'}")
        st.caption(f"Entrepôt de fichiers (MinIO) · **{s.get('minio', '?')}**")
        st.caption(f"Base de données (PostgreSQL) · **{s.get('postgresql', '?')}**")
    else:
        st.markdown("### 🔵 Mode démonstration")
        st.caption(
            "L'infrastructure (MinIO, PostgreSQL, Airflow) tourne en local via "
            "Docker et n'est pas joignable depuis un serveur distant. Ce "
            "dashboard affiche donc un **instantané figé** des résultats.\n\n"
            "Pour la version en direct, clonez le dépôt et suivez le README."
        )


# ======================================================================
# PAGE 1 — NOTRE PROJET
# ======================================================================
if page.startswith("1"):
    st.title("Un data lake pour des signaux vitaux")
    st.markdown("##### Peut-on construire une seule infrastructure capable "
                "d'absorber des données médicales qui n'ont rien en commun ?")

    note(
        "Un hôpital ne produit pas <em>un</em> type de données. Il produit des tracés "
        "cardiaques, des enregistrements cérébraux, des relevés d'environnement — des "
        "formats, des fréquences et des volumes radicalement différents. "
        "<strong>Notre pari : écrire une chaîne de traitement unique, capable de les "
        "avaler toutes, sans être réécrite à chaque nouvelle source.</strong>"
    )

    st.subheader("Les trois sources que nous avons branchées")
    c1, c2, c3 = st.columns(3)
    with c1:
        etape("SOURCE 01", "Le cœur — ECG",
              "Dataset MIT-BIH. Un signal cardiaque continu, 360 mesures par seconde, "
              "annoté battement par battement par des cardiologues."
              "<br><br><em>Fichier binaire, un seul canal.</em>")
    with c2:
        etape("SOURCE 02", "Le cerveau — EEG",
              "Dataset CHB-MIT. 23 électrodes sur le crâne d'enfants épileptiques, "
              "avec l'horaire exact de chaque crise."
              "<br><br><em>Fichier binaire, 23 canaux.</em>")
    with c3:
        etape("SOURCE 03", "L'air — API temps réel",
              "API OpenAQ. La qualité de l'air autour de Paris — un facteur de risque "
              "cardio-respiratoire reconnu."
              "<br><br><em>JSON géolocalisé, interrogé chaque heure.</em>")

    st.markdown("")
    note(
        "Ces trois sources sont volontairement <strong>incompatibles</strong>. C'est le "
        "test : si notre architecture les absorbe sans se déformer, elle est bonne. Si "
        "elle craque, c'est qu'elle était taillée pour un seul cas."
    )

    st.subheader("Notre démarche, en cinq temps")
    d = st.columns(5)
    plan = [
        ("ÉTAPE 1", "Poser le socle",
         "Un entrepôt, une base, et surtout un <em>contrat de traitement</em> commun à "
         "tous les domaines."),
        ("ÉTAPE 2", "Prouver sur l'ECG",
         "Faire circuler un premier signal de bout en bout, jusqu'à un modèle qui "
         "détecte les battements anormaux."),
        ("ÉTAPE 3", "Automatiser",
         "Confier l'enchaînement à un orchestrateur, pour que le pipeline tourne sans "
         "nous."),
        ("ÉTAPE 4", "Brancher l'EEG",
         "Ajouter un domaine radicalement différent — et vérifier que rien ne casse."),
        ("ÉTAPE 5", "Mesurer, puis accélérer",
         "Exposer les données par une API, rendre l'ingestion rapide, et regarder nos "
         "résultats en face."),
    ]
    for col, (n, t, x) in zip(d, plan):
        with col:
            etape(n, t, x)


# ======================================================================
# PAGE 2 — ARCHITECTURE
# ======================================================================
elif page.startswith("2"):
    st.title("Comment les données circulent")

    note(
        "Nous avons découpé le traitement en <strong>trois zones successives</strong>. "
        "La règle est stricte : on avance toujours dans le même sens, et "
        "<strong>on ne modifie jamais l'original</strong>."
    )

    z1, z2, z3 = st.columns(3)
    with z1:
        etape("ZONE 01 — RAW", "On garde tout, tel quel",
              "Les fichiers sont stockés <strong>sans la moindre modification</strong>, "
              "dans un entrepôt compatible S3.<br><br>"
              "Pourquoi ? Si nous découvrons demain une erreur dans notre traitement, "
              "nous pouvons tout recalculer depuis la source. "
              "<strong>L'original n'est jamais perdu.</strong>")
    with z2:
        etape("ZONE 02 — STAGING", "Le signal devient des chiffres",
              "C'est ici qu'a lieu le travail scientifique. Un tracé cardiaque devient "
              "une liste d'intervalles entre battements. Un signal cérébral devient une "
              "répartition d'énergie par fréquence.<br><br>"
              "Nous passons de <strong>168 Mo à moins d'1 Mo</strong> — mais attention, "
              "<strong>c'est une perte d'information volontaire</strong>, pas un simple "
              "nettoyage.")
    with z3:
        etape("ZONE 03 — CURATED", "Les données parlent",
              "Nos modèles s'appliquent et écrivent leur verdict en base.<br><br>"
              "Chaque ligne porte à la fois <strong>la vérité</strong> (ce que dit le "
              "médecin) et <strong>la prédiction</strong> (ce que dit notre modèle). "
              "C'est ce qui permet de mesurer honnêtement.")

    st.markdown("")
    st.subheader("Le choix qui rend tout cela possible")

    note(
        "Nous aurions pu écrire un programme pour l'ECG, puis un autre pour l'EEG. Nous "
        "avons fait l'inverse : <strong>un contrat unique</strong>, que chaque domaine "
        "remplit à sa façon."
    )

    st.code("""
SignalProcessor  ←  écrit UNE fois, partagé par tous les domaines
│
├─ load_raw()      «  comment lis-tu ton signal ?  »   ← à remplir
├─ to_features()   «  qu'en extrais-tu ?           »   ← à remplir
└─ run()           l'enchaînement complet              ← DÉJÀ ÉCRIT

              chaque domaine ne remplit que les deux trous
                                ↓
ECGProcessor   →   découpe par battement, mesure les intervalles
EEGProcessor   →   filtre, découpe en fenêtres, mesure les fréquences
AirProcessor   →   aplatit le JSON reçu de l'API
    """, language=None)

    note(
        "Résultat concret : <strong>ajouter l'EEG nous a demandé cinq fichiers "
        "nouveaux</strong> (lecture du signal, ingestion, transformation, modèle, "
        "orchestration) — et <strong>aucune réécriture</strong> de l'entrepôt, de "
        "l'API ou de l'orchestrateur.<br><br>"
        "Soyons précis, car il serait malhonnête de prétendre que <em>rien</em> n'a "
        "bougé : la <strong>table finale a dû être étendue</strong> (les colonnes de "
        "l'EEG n'existaient pas) et l'API a dû apprendre à les renvoyer. Nous l'avons "
        "fait par <em>migration</em>, sans détruire les données ECG déjà présentes. "
        "C'est le prix normal d'un nouveau domaine — et il est resté faible."
    )

    st.subheader("Pourquoi ce dashboard ne touche jamais à la base")
    note(
        "Ce dashboard <strong>ne va jamais chercher les données lui-même</strong>. Il "
        "les demande à l'API, qui va les chercher pour lui — comme un client au "
        "restaurant commande au serveur plutôt que d'entrer en cuisine.<br><br>"
        "L'intérêt : si nous remplacions demain PostgreSQL par une autre base, "
        "<strong>seule l'API changerait</strong>. Le dashboard, lui, ne bougerait pas "
        "d'une ligne. Les couches restent indépendantes."
    )

    st.subheader("Les outils, et nos raisons")
    st.dataframe(pd.DataFrame({
        "Outil": ["MinIO", "PostgreSQL", "MNE-Python", "Apache Airflow",
                  "FastAPI", "Streamlit", "Docker"],
        "Rôle": [
            "L'entrepôt de fichiers (zones raw et staging)",
            "La base finale (zone curated)",
            "Le traitement du signal cérébral",
            "L'orchestrateur : il déclenche les tâches sans nous",
            "L'API qui expose le lake",
            "Ce dashboard",
            "Tout lancer d'une seule commande",
        ],
        "Notre raison": [
            "Compatible S3 (imposé par le sujet), gratuit, tourne en local",
            "Robuste, et adapté aux données structurées",
            "La référence mondiale du traitement EEG",
            "Sait déclencher l'ingestion de l'API à intervalle régulier",
            "Moderne, asynchrone, et documenté automatiquement",
            "Écrit en Python : aucun code web à maintenir",
            "Reproductibilité — le correcteur lance tout sans galérer",
        ],
    }), use_container_width=True, hide_index=True)


# ======================================================================
# PAGE 3 — LE LAKE EN DIRECT
# ======================================================================
elif page.startswith("3"):
    st.title("L'état réel du lake")
    st.caption("Chiffres lus en direct depuis l'API. Ils changent à chaque ingestion.")

    stats = api_get("/stats")
    if not stats:
        st.error(
            "Aucune donnée disponible. Lancez l'API (`uvicorn src.api.main:app`), "
            "ou générez l'instantané de démo (`python -m src.dashboard.export_demo`)."
        )
        st.stop()

    raw = stats.get("buckets", {}).get("raw", {})
    stg = stats.get("buckets", {}).get("staging", {})
    cur = stats.get("curated", {})

    c1, c2, c3 = st.columns(3)
    c1.metric("Zone raw", f"{raw.get('n_objets', 0)} fichiers",
              f"{raw.get('taille_totale_mo', 0)} Mo de signal brut")
    c2.metric("Zone staging", f"{stg.get('n_objets', 0)} fichiers",
              f"{stg.get('taille_totale_mo', 0)} Mo de caractéristiques")
    c3.metric("Zone curated", f"{cur.get('total_rows', 0)} lignes",
              "analysées par nos modèles")

    # La réduction de volume : le vrai travail du pipeline.
    mo_raw = raw.get("taille_totale_mo", 0) or 0
    mo_stg = stg.get("taille_totale_mo", 0) or 0
    if mo_raw > 0:
        st.subheader("Ce que fait vraiment un pipeline : réduire")
        fig = go.Figure(go.Bar(
            x=[mo_raw, mo_stg], y=["Signal brut (raw)", "Caractéristiques (staging)"],
            orientation="h", marker_color=[ARDOISE, ENCRE],
            text=[f"{mo_raw} Mo", f"{mo_stg} Mo"], textposition="outside",
            textfont=dict(color=ENCRE, size=14),
        ))
        fig.update_layout(xaxis_title="Volume (Mo)",
                          xaxis=dict(range=[0, mo_raw * 1.25]))
        st.plotly_chart(styler(fig, 260), use_container_width=True)

        if mo_stg > 0:
            note(
                f"Nous partons de <strong>{mo_raw} Mo de signal brut</strong> pour n'en "
                f"garder que <strong>{mo_stg} Mo</strong>, soit une réduction d'un "
                f"facteur <strong>{mo_raw/mo_stg:.0f}</strong>.<br><br>"
                "<strong>Attention à ne pas en tirer une fausse fierté.</strong> Ce "
                "n'est pas que « le reste était du bruit » : nous avons "
                "<em>délibérément écrasé de l'information</em>. Pour l'EEG, nous "
                "moyennons 23 canaux en un seul et résumons 1 280 mesures en cinq "
                "chiffres. C'est un choix — et c'est <strong>précisément ce choix qui "
                "explique en partie l'échec de notre modèle EEG</strong> (voir la page "
                "5). Réduire, oui ; mais chaque réduction est une information perdue."
            )

    par_source = cur.get("par_source", [])
    if par_source:
        st.subheader("Les domaines qui cohabitent dans la même table")
        noms = {"ecg": "Cœur (ECG)", "eeg": "Cerveau (EEG)", "air": "Air (API)"}
        df = pd.DataFrame(par_source)
        df["domaine"] = df["source_type"].map(lambda s: noms.get(s, s))

        fig = px.bar(df, x="domaine", y="n_rows", text="n_rows",
                     labels={"n_rows": "Lignes analysées", "domaine": ""},
                     color_discrete_sequence=[ENCRE])
        fig.update_traces(textposition="outside", textfont=dict(color=ENCRE, size=14),
                          cliponaxis=False)
        # On laisse de la marge au-dessus, sinon l'étiquette est coupée.
        fig.update_yaxes(range=[0, df["n_rows"].max() * 1.18])
        st.plotly_chart(styler(fig, 360), use_container_width=True)

        note(
            "Un signal cardiaque, un signal cérébral et un flux d'API atterrissent dans "
            "<strong>la même table</strong>, via <strong>la même chaîne</strong>. C'est "
            "précisément ce qu'un data lake doit savoir faire : absorber l'hétérogénéité "
            "sans se déformer."
        )

        st.subheader("Le détail par domaine")
        det = df[["domaine", "n_records", "n_rows",
                  "n_abnormal_reel", "n_abnormal_predit"]].copy()
        det.columns = ["Domaine", "Enregistrements", "Lignes",
                       "Anomalies réelles", "Anomalies prédites"]
        st.dataframe(det, use_container_width=True, hide_index=True)


# ======================================================================
# PAGE 4 — ECG
# ======================================================================
elif page.startswith("4"):
    st.title("Le cœur : détecter un battement anormal")

    note(
        "Un électrocardiogramme mesure l'activité électrique du cœur. Chaque battement "
        "laisse une trace. <strong>Notre travail : dire, pour chacun, s'il est normal ou "
        "pathologique.</strong> La vérité vient des annotations de cardiologues fournies "
        "avec le dataset ; notre modèle apprend à les reproduire."
    )

    with st.expander("Comment nous transformons un tracé en chiffres"):
        st.markdown("""
Un signal cardiaque brut n'est qu'une longue suite de valeurs. Inexploitable tel quel.

**Nous le découpons battement par battement**, et nous mesurons pour chacun :

- **Le rythme** — le temps écoulé depuis le battement précédent, et jusqu'au suivant.
  Un battement qui arrive trop tôt ou trop tard est suspect.
- **La forme** — l'amplitude du pic. Un battement pathologique a souvent une allure
  différente.

Ces quelques chiffres suffisent : notre modèle en tire un rappel de **85 %**.
        """)

    df = charger_domaine("ecg")
    if df.empty:
        st.info("Aucune donnée ECG. Lancez : `python -m src.models.train_ecg`")
        st.stop()

    patients = sorted(df["record_id"].dropna().unique())
    patient = st.selectbox(f"Choisissez un patient ({len(patients)} disponibles)",
                           patients)
    sd = df[df["record_id"] == patient].sort_values("position_sec")

    n = len(sd)
    reels = int(sd["is_abnormal"].fillna(0).sum())
    trouves = int(((sd["is_abnormal"] == 1) & (sd["predicted"] == 1)).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Battements analysés", f"{n:,}".replace(",", " "))
    c2.metric("Anormaux (vérité)", reels, f"{reels/n*100:.1f} % du total" if n else "")
    c3.metric("Anormaux détectés", trouves,
              f"{trouves/reels*100:.0f} % attrapés" if reels else "—")

    st.subheader("Chaque point est un battement")
    st.caption("En hauteur : le temps écoulé depuis le battement précédent. "
               "En rouge, ceux que les cardiologues ont marqués comme anormaux.")

    sd["Nature"] = sd["is_abnormal"].map({0: "Normal", 1: "Anormal"})
    fig = px.scatter(sd.head(500), x="position_sec", y="rr_prev", color="Nature",
                     color_discrete_map={"Normal": ARDOISE, "Anormal": SIGNAL},
                     labels={"position_sec": "Temps écoulé (secondes)",
                             "rr_prev": "Intervalle entre battements (s)"},
                     opacity=0.8)
    fig.update_traces(marker=dict(size=8, line=dict(width=0)))
    st.plotly_chart(styler(fig, 380), use_container_width=True)

    note(
        "On voit à l'œil nu ce que le modèle exploite : les battements anormaux se "
        "détachent du rythme régulier. <strong>C'est exactement l'information que nous "
        "lui fournissons.</strong> Un modèle ne devine pas — il faut lui présenter le "
        "bon signal."
    )

    # Les types de battements : la nuance médicale derrière le 0/1.
    if "symbol" in sd.columns and sd["symbol"].notna().any():
        st.subheader("Tous les battements anormaux ne se ressemblent pas")
        st.caption("Chaque symbole est un type de battement défini par la norme médicale.")

        legende = {
            "N": "Normal", "L": "Bloc de branche gauche", "R": "Bloc de branche droit",
            "V": "Extrasystole ventriculaire", "A": "Extrasystole auriculaire",
            "/": "Battement stimulé (pacemaker)", "f": "Fusion stimulé/normal",
            "F": "Fusion ventriculaire", "j": "Échappement jonctionnel",
            "e": "Échappement auriculaire",
        }
        comptes = sd["symbol"].value_counts().head(8).reset_index()
        comptes.columns = ["symbole", "nombre"]
        comptes["Type de battement"] = comptes["symbole"].map(
            lambda s: f"{legende.get(s, 'Autre')} ({s})")
        comptes["Nature"] = comptes["symbole"].map(
            lambda s: "Normal" if s in {"N", "L", "R", "e", "j"} else "Anormal")

        fig = px.bar(comptes, x="nombre", y="Type de battement", orientation="h",
                     color="Nature",
                     color_discrete_map={"Normal": ARDOISE, "Anormal": SIGNAL},
                     labels={"nombre": "Nombre de battements", "Type de battement": ""})
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(styler(fig, 320), use_container_width=True)

        note(
            "Derrière notre étiquette binaire « normal / anormal » se cache une "
            "classification médicale bien plus riche. <strong>Nous avons simplifié — "
            "c'est un choix, et une limite.</strong> Un vrai outil clinique dirait "
            "<em>quel type</em> d'anomalie, pas seulement qu'il y en a une."
        )

    if str(patient) == "102":
        alerte(
            "<strong>La découverte qui nous a fait revoir notre copie.</strong><br><br>"
            "Le patient 102 présente <strong>95 % de battements anormaux</strong>, quand "
            "les patients 100 et 101 en ont moins de 2 %. Il porte un stimulateur "
            "cardiaque : presque tous ses battements sont « non normaux » au sens de la "
            "classification médicale.<br><br>"
            "Conséquence : notre taux global de 33 % d'anomalies est un "
            "<strong>artefact de ce seul patient</strong>. La moyenne globale ne décrit "
            "aucun patient réel. Nous ne l'aurions jamais vu sans regarder les "
            "enregistrements un par un."
        )


# ======================================================================
# PAGE 5 — EEG
# ======================================================================
elif page.startswith("5"):
    st.title("Le cerveau : détecter une crise d'épilepsie")

    note(
        "Vingt-trois électrodes posées sur le crâne d'un enfant épileptique. Quelque part "
        "dans une heure d'enregistrement, une crise survient et dure moins d'une minute. "
        "<strong>Notre travail : la trouver.</strong>"
    )

    with st.expander("Les bandes de fréquence : ce que nous mesurons vraiment"):
        st.markdown("""
Le cerveau produit des ondes électriques à différentes fréquences. Les neurologues les
regroupent en cinq bandes, chacune associée à un état mental :

| Bande | Fréquence | État associé |
|---|---|---|
| **Delta** | 0,5 – 4 Hz | Sommeil profond |
| **Theta** | 4 – 8 Hz | Somnolence |
| **Alpha** | 8 – 13 Hz | Éveil calme |
| **Beta** | 13 – 30 Hz | Concentration |
| **Gamma** | 30 – 45 Hz | Activité intense |

Pendant une crise, les neurones se déchargent **de façon synchrone et anormale**. La
répartition de l'énergie entre ces bandes change brutalement.

**Notre méthode :** découper le signal en fenêtres de 5 secondes et mesurer, pour
chacune, la part d'énergie dans chaque bande. Ce sont ces chiffres — et eux seuls —
que voit notre modèle.
        """)

    df = charger_domaine("eeg")
    if df.empty:
        st.info("Aucune donnée EEG. Lancez : `python -m src.models.train_eeg`")
        st.stop()

    if "debut_sec" not in df.columns or df["debut_sec"].isna().all():
        st.warning("Les colonnes EEG n'arrivent pas de l'API. "
                   "Redémarrez-la : `uvicorn src.api.main:app`")
        st.stop()

    enrs = sorted(df["record_id"].dropna().unique())

    # ⚠️ LE POINT LE PLUS IMPORTANT DE CETTE PAGE.
    # Notre modèle s'entraîne sur tous les enregistrements SAUF LE DERNIER, qui
    # sert de test. Un score sur un enregistrement d'entraînement ne prouve
    # RIEN : le modèle l'a déjà vu, il peut l'avoir appris par cœur.
    # Sans cette distinction, le dashboard donnerait une impression totalement
    # fausse de la qualité du modèle.
    enr_test = enrs[-1] if enrs else None
    enrs_train = enrs[:-1]

    note(
        "<strong>Avant de regarder les chiffres, une précaution indispensable.</strong><br><br>"
        f"Notre modèle s'est entraîné sur <strong>{', '.join(enrs_train)}</strong> et "
        f"n'a <strong>jamais vu {enr_test}</strong>.<br><br>"
        "Conséquence : ses excellents scores sur les enregistrements d'entraînement "
        "<strong>ne prouvent rien</strong> — il les a déjà vus, il peut les avoir appris "
        f"par cœur. <strong>Seul {enr_test} constitue une mesure honnête.</strong> "
        "Comparez les deux : l'écart est notre résultat le plus instructif."
    )

    enr = st.selectbox(f"Choisissez un enregistrement ({len(enrs)} disponibles)", enrs)
    est_le_test = (enr == enr_test)

    if est_le_test:
        st.success(f"**{enr} — LE VRAI TEST.** Le modèle n'a jamais vu cet "
                   "enregistrement. Les chiffres ci-dessous sont les seuls qui comptent.")
    else:
        st.warning(f"**{enr} — enregistrement d'ENTRAÎNEMENT.** Le modèle l'a déjà vu. "
                   "De bons scores ici sont *attendus* et ne démontrent rien.")

    sd = df[df["record_id"] == enr].sort_values("debut_sec")

    n = len(sd)
    reelles = int(sd["is_seizure"].fillna(0).sum())
    trouvees = int(((sd["is_seizure"] == 1) & (sd["predicted"] == 1)).sum())
    fausses = int(((sd["is_seizure"] == 0) & (sd["predicted"] == 1)).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fenêtres de 5 s", n)
    c2.metric("En crise (vérité)", reelles,
              f"{reelles/n*100:.2f} % du signal" if n else "")
    c3.metric("Fenêtres retrouvées", trouvees,
              f"{trouvees/reelles*100:.0f} % de la crise" if reelles else "—")
    c4.metric("Fausses alertes", fausses)

    st.subheader("La crise, vue par le modèle")
    st.caption("La bande rouge est la crise réelle. La courbe bleue est la probabilité "
               "de crise estimée par notre modèle, seconde après seconde.")

    fig = go.Figure()

    # Les vraies crises : des zones rouges en fond.
    en_crise = sd[sd["is_seizure"] == 1]
    if len(en_crise):
        # On repère les blocs contigus de crise.
        blocs, debut = [], None
        precedent = None
        for _, r in en_crise.iterrows():
            if debut is None:
                debut = r["debut_sec"]
            elif r["debut_sec"] - precedent > 10:
                blocs.append((debut, precedent + 5))
                debut = r["debut_sec"]
            precedent = r["debut_sec"]
        if debut is not None:
            blocs.append((debut, precedent + 5))

        for i, (d, f) in enumerate(blocs):
            fig.add_vrect(
                x0=d, x1=f, fillcolor=SIGNAL, opacity=0.22, line_width=0,
                annotation_text="CRISE" if i == 0 else "",
                annotation_position="top left",
                annotation_font=dict(color=SIGNAL, size=12),
            )

    # La probabilité prédite : la courbe qui compte vraiment.
    fig.add_trace(go.Scatter(
        x=sd["debut_sec"], y=sd["proba"], mode="lines",
        name="Probabilité de crise (modèle)",
        line=dict(color=ENCRE, width=2),
        fill="tozeroy", fillcolor="rgba(20,33,61,0.12)",
    ))
    # Le seuil de décision.
    fig.add_hline(y=0.5, line=dict(color=ARDOISE, width=1, dash="dash"),
                  annotation_text="seuil de décision (0,5)",
                  annotation_font=dict(color="#5A6478", size=11))

    fig.update_layout(xaxis_title="Temps écoulé (secondes)",
                      yaxis_title="Probabilité de crise",
                      yaxis=dict(range=[0, 1.05]))
    st.plotly_chart(styler(fig, 400), use_container_width=True)

    note(
        "Ce graphe est plus honnête qu'un simple « oui / non » : il montre "
        "<strong>l'hésitation du modèle</strong>. Pour qu'il déclenche une alerte, il "
        "faut que la courbe bleue dépasse le seuil en pointillé, à l'intérieur d'une "
        "bande rouge. <strong>Regardez comme cela arrive rarement.</strong>"
    )

    if reelles:
        ratees = reelles - trouvees
        part = trouvees / reelles

        if not est_le_test:
            # Enregistrement d'entraînement : les bons scores sont un piège.
            note(
                f"Le modèle retrouve <strong>{trouvees} des {reelles} fenêtres</strong> "
                f"de crise, avec {fausses} fausse(s) alerte(s). "
                f"<strong>C'est très bon — et cela ne prouve rien.</strong><br><br>"
                "Cet enregistrement faisait partie de son entraînement : il l'a "
                "<em>déjà vu</em>. Lui demander de le reconnaître, c'est faire passer un "
                f"examen à un élève en lui laissant le corrigé. Regardez plutôt "
                f"<strong>{enr_test}</strong> — le seul qu'il n'a jamais vu."
            )
        elif part < 0.5:
            # Le vrai test, et il échoue.
            alerte(
                f"<strong>Voici la seule mesure honnête — et elle est mauvaise.</strong>"
                f"<br><br>Sur cet enregistrement jamais vu, le modèle ne retrouve que "
                f"<strong>{trouvees} des {reelles} fenêtres</strong> de la crise "
                f"(il en manque {ratees}).<br><br>"
                "<strong>Le contraste est brutal.</strong> Sur les enregistrements "
                "d'entraînement, il frôlait les 100 %. Face à un signal inconnu, il "
                "s'effondre. C'est la définition même du <em>sur-apprentissage</em> : "
                "il a mémorisé au lieu de comprendre.<br><br>"
                "<strong>Nuance importante, en toute honnêteté :</strong> regardez le "
                "graphe — sa probabilité <em>monte</em> pendant la crise, il la « sent » "
                "passer. Il ne reste simplement pas assez longtemps au-dessus du seuil. "
                "Un système d'alerte clinique déclencherait donc peut-être quand même. "
                "Mais 3 fenêtres sur 18, c'est trop fragile pour qu'on prétende le "
                "contraire."
            )
        else:
            alerte(
                f"Sur cet enregistrement jamais vu, le modèle retrouve "
                f"<strong>{trouvees} des {reelles} fenêtres</strong> de crise "
                f"({fausses} fausse(s) alerte(s)). C'est la seule mesure qui compte."
            )

    ratios = [c for c in sd.columns if c.startswith("ratio_")]
    if ratios and reelles:
        st.subheader("Où va l'énergie du cerveau ?")
        st.caption("Comparaison entre les fenêtres calmes et les fenêtres de crise.")

        calme = sd[sd["is_seizure"] == 0][ratios].mean()
        crise = sd[sd["is_seizure"] == 1][ratios].mean()
        comp = pd.DataFrame({
            "Bande": [c.replace("ratio_", "").capitalize() for c in ratios],
            "Repos": calme.values, "Crise": crise.values,
        }).melt(id_vars="Bande", var_name="État", value_name="Part de l'énergie")

        fig = px.bar(comp, x="Bande", y="Part de l'énergie", color="État",
                     barmode="group",
                     color_discrete_map={"Repos": ARDOISE, "Crise": SIGNAL})
        st.plotly_chart(styler(fig, 340), use_container_width=True)

        ecart = float((crise - calme).abs().max())
        note(
            f"Voilà tout ce que voit notre modèle. L'écart le plus marqué entre repos et "
            f"crise atteint <strong>{ecart:.2f}</strong>. "
            "<strong>Si les barres rouges et grises se ressemblent trop, nos "
            "caractéristiques ne capturent pas assez la différence</strong> — et cela "
            "explique en grande partie l'échec du modèle. La littérature utilise des "
            "réseaux de neurones sur des spectrogrammes complets, pas cinq valeurs "
            "moyennées sur vingt-trois canaux."
        )


# ======================================================================
# PAGE 6 — LA SOURCE API : QUALITÉ DE L'AIR
# ======================================================================
elif page.startswith("6"):
    st.title("La troisième source : la qualité de l'air")

    note(
        "Le sujet impose deux sources : un dataset fichier et une source issue "
        "d'une API. Nous avons choisi <strong>OpenAQ</strong>, qui expose en temps "
        "réel les mesures de pollution relevées par les stations du monde entier. "
        "Nous interrogeons celles situées dans un rayon de 25 km autour de Paris."
    )

    note(
        "<strong>Pourquoi cette source, et pas une autre ?</strong><br><br>"
        "D'abord pour la cohérence : la pollution de l'air est un "
        "<strong>facteur de risque cardio-respiratoire reconnu</strong>. Elle "
        "complète naturellement des signaux cardiaques et cérébraux.<br><br>"
        "Ensuite — et surtout — parce qu'elle est <strong>radicalement différente</strong> "
        "des deux autres. L'ECG et l'EEG sont des fichiers binaires, statiques, "
        "téléchargés une fois. OpenAQ renvoie du JSON imbriqué, géolocalisé, qui "
        "change en permanence. C'est le vrai test de notre architecture."
    )

    with st.expander("Ce que le pipeline fait de ce flux"):
        st.markdown("""
**Zone raw** — Nous stockons la réponse JSON **telle quelle**, dans un fichier
horodaté. Chaque exécution crée un *nouvel* instantané sans écraser les précédents :
nous construisons ainsi un **historique** de la qualité de l'air.

**Zone staging** — Le JSON d'OpenAQ est imbriqué en poupées russes : chaque station
contient une liste de capteurs, chacun mesurant un polluant. Notre `AirQualityProcessor`
**l'aplatit** en un tableau — une ligne = un capteur, d'un polluant, à un endroit.

**Zone curated** — Les mesures sont rangées en base, interrogeables par l'API.

**Orchestration** — Contrairement aux DAGs ECG et EEG (déclenchés à la main, car les
datasets sont statiques), celui-ci est **planifié toutes les heures**. C'est le seul
qui exploite réellement le scheduling d'Airflow.
        """)

    stats = api_get("/stats")
    air = (stats or {}).get("air", {})

    if not air or air.get("n_rows", 0) == 0:
        st.info(
            "Aucune donnée de qualité de l'air. Lancez :\n\n"
            "`python -m src.ingestion.ingest_air`\n\n"
            "`python -m src.pipelines.run_air`"
        )
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mesures en base", air.get("n_rows", 0))
    c2.metric("Instantanés", air.get("n_snapshots", 0), "un par exécution")
    c3.metric("Stations", air.get("n_stations", 0), "autour de Paris")
    c4.metric("Polluants suivis", air.get("n_polluants", 0))

    reponse = api_get("/curated", {"source": "air", "limit": 1000})
    if not reponse or not reponse.get("donnees"):
        st.warning("L'API ne renvoie aucune mesure. Redémarrez-la après mise à jour.")
        st.stop()

    df = pd.DataFrame(reponse["donnees"])

    st.subheader("Que mesure-t-on, et combien de fois ?")
    st.caption("Chaque station ne mesure pas les mêmes polluants — le réseau est hétérogène.")

    comptes = df["parametre"].value_counts().reset_index()
    comptes.columns = ["Polluant", "Nombre de capteurs"]

    fig = px.bar(comptes, x="Polluant", y="Nombre de capteurs",
                 text="Nombre de capteurs", color_discrete_sequence=[ENCRE])
    fig.update_traces(textposition="outside", textfont=dict(color=ENCRE, size=13),
                      cliponaxis=False)
    fig.update_yaxes(range=[0, comptes["Nombre de capteurs"].max() * 1.2])
    st.plotly_chart(styler(fig, 340), use_container_width=True)

    note(
        "Ce graphe dit quelque chose d'important sur les données ouvertes : "
        "<strong>le réseau est très inégal</strong>. Certains polluants sont mesurés "
        "par de nombreuses stations, d'autres par une poignée. Une analyse sérieuse "
        "devrait en tenir compte plutôt que de traiter toutes les mesures sur un pied "
        "d'égalité."
    )

    if {"latitude", "longitude"}.issubset(df.columns):
        st.subheader("Où sont les stations ?")
        st.caption("Les capteurs OpenAQ situés dans un rayon de 25 km autour de Paris.")

        stations = df.dropna(subset=["latitude", "longitude"]).drop_duplicates("location_id")
        st.map(stations[["latitude", "longitude"]], size=120, color="#C1121F")

        note(
            f"<strong>{len(stations)} stations</strong> alimentent notre lake. Ce sont "
            "des données <em>spatiales</em> — une nature encore différente des séries "
            "temporelles de l'ECG et de l'EEG. Notre chaîne les a absorbées sans "
            "modification."
        )

    st.subheader("Les mesures brutes")
    apercu = df[["snapshot_id", "location_name", "parametre", "unite"]].head(20)
    apercu.columns = ["Instantané", "Station", "Polluant", "Unité"]
    st.dataframe(apercu, use_container_width=True, hide_index=True)

    alerte(
        "<strong>Ce que nous n'avons pas fait, et que nous assumons.</strong><br><br>"
        "Nous ingérons la qualité de l'air, nous la transformons, nous la stockons — "
        "mais nous ne l'avons <strong>pas encore croisée</strong> avec les signaux "
        "physiologiques. La question intéressante (la pollution influence-t-elle les "
        "mesures cardiaques ?) reste entière.<br><br>"
        "Pourquoi ? Parce que nos données ECG proviennent d'un hôpital de Boston dans "
        "les années 1980, et nos mesures d'air de Paris en 2026. <strong>Les croiser "
        "n'aurait aucun sens scientifique</strong>, et nous avons préféré ne pas "
        "fabriquer une corrélation artificielle pour faire joli. L'infrastructure est "
        "prête pour cette analyse ; il faudrait des données appariées pour la mener."
    )


# ======================================================================
# PAGE 7 — CE QUE NOUS RETENONS
# ======================================================================
else:
    st.title("Ce que nous retenons")
    st.markdown("##### Un même pipeline, deux résultats opposés — et ce que cela nous a appris.")

    note(
        "Le cœur et le cerveau traversent <strong>exactement le même code</strong> : même "
        "entrepôt, même contrat de traitement, même type de modèle, même orchestrateur. "
        "Seule change la nature du problème. Et les résultats n'ont rien à voir."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🫀 Cœur — ECG")
        st.metric("Rappel du modèle", "85,3 %", "il attrape la plupart des anomalies")
        st.metric("Anomalies dans les données", "33,6 %")
        st.metric("Gain face à une baseline naïve", "+24 points d'accuracy")
    with c2:
        st.markdown("#### 🧠 Cerveau — EEG")
        st.metric("Rappel du modèle", "16,7 %", "il rate 5 crises sur 6")
        st.metric("Crises dans les données", "1,53 %")
        st.metric("Gain face à une baseline naïve", "+0,3 point d'accuracy")

    st.divider()

    onglet_bien, onglet_moins, onglet_suite = st.tabs([
        "Ce qui a bien marché", "Ce qui a moins bien marché", "Ce que nous ferions autrement",
    ])

    with onglet_bien:
        st.markdown("""
##### L'architecture a tenu ses promesses

C'est le résultat dont nous sommes le plus satisfaits. Ajouter l'EEG — un signal à
23 canaux, dans un format binaire différent, avec une logique de traitement qui n'a
rien à voir — nous a demandé **cinq fichiers nouveaux** : la lecture du signal,
l'ingestion, la transformation, le modèle, et l'orchestration.

**Ce qui n'a pas eu à changer :** l'entrepôt de fichiers, l'API, l'orchestrateur, et
le contrat de traitement partagé.

**Ce qui a dû évoluer, en revanche :** la table finale, à laquelle nous avons ajouté
les colonnes propres à l'EEG, et l'API qui a dû apprendre à les renvoyer. Nous l'avons
fait par *migration*, sans détruire les données ECG déjà en base. Il serait malhonnête
de prétendre que rien n'a bougé — mais le coût est resté faible, et c'est exactement ce
que nous cherchions à démontrer.

##### L'optimisation a payé — mais pas partout

Notre endpoint d'ingestion optimisé est **27 fois plus rapide** que la version naïve sur
un lot de 100 éléments (4 609 ms → 170 ms), là où l'objectif demandé était de 30 %.

Trois leviers, tous simples : garder le modèle en mémoire au lieu de le relire à chaque
appel, traiter tout le lot d'un coup avec NumPy plutôt qu'un par un, et grouper les
100 insertions en une seule requête.

**Mais sur un lot d'un seul élément, notre gain est négatif (−32 %) : la version
« optimisée » est plus lente.** Ce n'est pas un échec, c'est une leçon : nos trois
optimisations sont des optimisations *de lot*. Sur un élément unique, elles ajoutent le
coût de leur machinerie sans jamais en tirer le bénéfice, et le temps est dominé par des
frais fixes (le réseau, la connexion à la base) que la vectorisation ne touche pas.

**Une optimisation n'est jamais bonne dans l'absolu. Elle est bonne pour un régime
d'utilisation donné.**

##### Le modèle ECG est solide

85 % de rappel avec quatre caractéristiques élémentaires. Nous n'avons pas eu besoin
d'un réseau de neurones : **la qualité de ce qu'on donne au modèle compte plus que la
sophistication du modèle**.
        """)

    with onglet_moins:
        st.markdown("""
##### Le sur-apprentissage, pris en flagrant délit

C'est notre découverte la plus parlante, et elle vaut d'être racontée précisément.

Notre modèle EEG obtient des scores **excellents** sur les enregistrements `chb01_03`,
`chb01_04` et `chb01_16` : il retrouve la quasi-totalité des fenêtres de crise, sans
fausse alerte. Vu comme ça, il a l'air brillant.

**Sauf que ce sont les trois enregistrements sur lesquels il s'est entraîné.** Il les a
déjà vus. Lui demander de les reconnaître revient à faire passer un examen à un élève en
lui laissant le corrigé sous les yeux.

Sur `chb01_18` — le seul qu'il n'a **jamais** vu — il ne retrouve plus que **3 fenêtres
sur 18**.

**C'est la définition du sur-apprentissage : il a mémorisé au lieu de comprendre.** Et
c'est précisément pour cela qu'on garde toujours des données de côté. Si nous avions
regardé les scores globaux sans distinguer entraînement et test, nous aurions conclu que
notre modèle fonctionnait — et nous aurions eu tort.

##### Le modèle EEG échoue, et nous l'assumons

Sur le seul enregistrement qui compte, il retrouve 17 % des fenêtres de crise.
Cliniquement, c'est trop fragile, et nous préférons l'écrire plutôt que de le noyer sous
une accuracy de 97,8 % qui ne veut rien dire.

**Une nuance en sa faveur, tout de même :** en regardant la courbe de probabilité, on
voit qu'il *sent* la crise passer — sa confiance monte nettement au bon moment. Il ne
reste simplement pas assez longtemps au-dessus du seuil de décision. Un système d'alerte
réel, avec un seuil abaissé, déclencherait peut-être quand même. Mais nous ne
surinterprétons pas : trois fenêtres sur dix-huit, c'est trop peu pour crier victoire.

**Nos explications :**

1. **Trop peu d'exemples.** 26 fenêtres de crise pour apprendre. C'est dérisoire.
2. **Nous avons trop écrasé le signal.** En passant de 168 Mo à 0,57 Mo, nous n'avons pas
   « retiré du bruit » : nous avons jeté de l'information. Nous **moyennons les 23 canaux
   en un seul** — donc nous perdons *où* la crise démarre dans le cerveau. Or une crise
   est justement un phénomène **localisé**. Nous avons détruit exactement l'information
   dont le modèle avait besoin.
3. **Un test volontairement dur.** Valider sur un enregistrement jamais vu est plus sévère
   qu'un découpage au hasard — mais c'est la seule mesure qui ait un sens.

##### L'accuracy nous a presque trompés

Notre premier réflexe, sur l'EEG, a été de regarder l'accuracy : **97,8 %**. Excellent,
en apparence.

Puis nous avons calculé celle d'un modèle qui répondrait *« jamais de crise »*, donc qui
ne détecte **rien** : **97,5 %**. Notre modèle n'apportait que **0,3 point**.

**Sur des données déséquilibrées, l'accuracy est un mensonge poli.**

##### Une moyenne peut ne décrire personne

Notre taux global de 33 % d'anomalies cardiaques semblait cohérent. En regardant patient
par patient, nous avons découvert que le patient 102 en a **95 %** (il porte un
stimulateur), quand les deux autres en ont moins de 2 %.

**La moyenne ne correspondait à aucun patient réel.**

##### Les frictions techniques

Notre code fonctionnait en local mais **échouait dans Airflow**, à cause d'un conflit de
versions de bibliothèque : Airflow impose les siennes, les nôtres les écrasaient et le
cassaient. Typique du data engineering — le code qui marche sur votre machine ne marche
pas forcément dans l'environnement d'exécution.
        """)

    with onglet_suite:
        st.markdown("""
##### Pour l'EEG : changer d'approche, pas de réglage

Ajuster les hyperparamètres du Random Forest ne servirait à rien. Le problème est en
amont, dans ce que nous donnons au modèle.

- **Un CNN sur spectrogrammes.** Traiter le signal comme une image temps-fréquence, en
  gardant l'information par canal. C'est ce que fait la littérature, et c'est là que se
  trouve le gain.
- **Beaucoup plus de patients.** Nous avons utilisé un seul patient. Le dataset en
  contient 23.
- **Rééchantillonner intelligemment.** Générer des exemples de crise synthétiques
  (SMOTE) ou sous-échantillonner les fenêtres calmes.
- **Déplacer le seuil de décision.** En médecine, on accepte volontiers des fausses
  alertes pour ne rater aucune crise. Abaisser le seuil sous 0,5 augmenterait le rappel
  — au prix de la précision. C'est un arbitrage clinique, pas technique.

##### Pour l'infrastructure

- **Des tests automatisés.** Nous avons vérifié à la main. Un vrai projet aurait une
  suite de tests qui tourne à chaque modification.
- **Un suivi des versions de modèle.** Aujourd'hui, entraîner écrase le modèle
  précédent. Il faudrait garder l'historique pour pouvoir revenir en arrière.
- **Croiser les sources.** Nous avons ingéré la qualité de l'air, mais nous ne l'avons
  pas encore reliée aux signaux physiologiques. C'est la suite naturelle : la pollution
  influence-t-elle les mesures cardiaques ? Le data lake est prêt pour cette question ;
  il ne manque que l'analyse.
        """)

    st.divider()
    st.caption(
        "Ce dashboard consomme uniquement l'API Gateway. Il ne connaît ni MinIO ni "
        "PostgreSQL — changer de base de données ne demanderait aucune modification ici."
    )
