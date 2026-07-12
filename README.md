# 🫀 Data Lake médical — ECG, EEG & qualité de l'air

> **Projet final — Data Lakes & Data Integration (EFREI 2025-2026)**
> Un data lake de bout en bout : de l'ingestion de signaux physiologiques bruts
> jusqu'à leur exposition par une API et un dashboard.

---

## Ce que fait ce projet

Nous avons construit une infrastructure capable d'absorber **trois sources de
données qui n'ont rien en commun**, de les transformer, de leur appliquer un
modèle de Machine Learning, et d'exposer le tout :

| Source | Type | Contenu |
|---|---|---|
| **ECG** (MIT-BIH) | Fichier binaire | Signal cardiaque, 360 Hz, annoté par des cardiologues |
| **EEG** (CHB-MIT) | Fichier binaire, 23 canaux | Signal cérébral d'un enfant épileptique, crises horodatées |
| **Qualité de l'air** (OpenAQ) | API temps réel | Mesures de pollution autour de Paris, ingérées chaque heure |

Le pari : **une seule chaîne de traitement** pour les trois, extensible sans
réécriture.

---

## 🚀 Démarrage rapide

### Prérequis

| Outil | Pourquoi |
|---|---|
| **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** | Lance l'entrepôt, la base et Airflow |
| **Python 3.10+** | Exécute le pipeline |
| **Une clé API OpenAQ** (gratuite) | [S'inscrire ici](https://explore.openaq.org/register) |

> ⚠️ Prévoyez **~3 Go d'espace disque** (images Docker) et **~200 Mo** pour les
> données EEG.

### 1. Configuration

```bash
cp .env.example .env        # Windows : copiez le fichier et renommez-le
```

Ouvrez `.env` et collez votre clé OpenAQ :

```
OPENAQ_API_KEY=votre_cle_ici
```

### 2. Lancer l'infrastructure

```bash
docker-compose up -d
```

⏳ **Le premier démarrage prend 3 à 5 minutes** (téléchargement des images).

Vérifiez que tout tourne :

```bash
docker-compose ps
```

| Service | Adresse | Identifiants |
|---|---|---|
| MinIO (entrepôt) | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Airflow (orchestrateur) | http://localhost:8080 | `airflow` / `airflow` |
| PostgreSQL (base) | `localhost:5432` | `datalake` / `datalake` |

### 3. Installer les dépendances Python

```bash
pip install -r requirements.txt
```

### 4. Exécuter les pipelines

**Option A — à la main** (recommandé la première fois, pour voir ce qui se passe) :

```bash
python -m src.storage.minio_client      # crée les buckets raw et staging

# --- Domaine ECG ---
python -m src.ingestion.ingest_ecg      # télécharge MIT-BIH  → zone raw
python -m src.pipelines.run_ecg         # extrait les features → zone staging
python -m src.models.train_ecg          # entraîne le modèle   → zone curated

# --- Source API (qualité de l'air) ---
python -m src.ingestion.ingest_air      # interroge OpenAQ     → zone raw
python -m src.pipelines.run_air         # aplatit le JSON      → zone staging

# --- Domaine EEG (⏳ ~170 Mo à télécharger, comptez 20-30 min) ---
python -m src.ingestion.ingest_eeg      # télécharge CHB-MIT   → zone raw
python -m src.pipelines.run_eeg         # bandes de fréquence  → zone staging
python -m src.models.train_eeg          # détecteur de crises  → zone curated
```

**Option B — via Airflow** : rendez-vous sur http://localhost:8080, activez les
DAGs (`pipeline_ecg`, `pipeline_eeg`, `pipeline_air_quality`) et déclenchez-les
avec le bouton ▶️.

### 5. Lancer l'API et le dashboard

Dans **deux terminaux distincts** :

```bash
# Terminal 1 — l'API
uvicorn src.api.main:app
```

```bash
# Terminal 2 — le dashboard
streamlit run src/dashboard/dashboard.py
```

| | Adresse |
|---|---|
| 📖 Documentation interactive de l'API | http://localhost:8000/docs |
| 📊 **Dashboard** | http://localhost:8501 |

---

## 🏗️ L'architecture

```
   ECG (fichier)  ─┐
   EEG (fichier)  ─┼──▶  RAW  ──▶  STAGING  ──▶  CURATED  ──▶  API  ──▶  Dashboard
   Air (API)      ─┘    MinIO      MinIO         PostgreSQL    FastAPI    Streamlit
                        (brut)     (Parquet)     (+ modèle)
                                    ▲
                              Airflow orchestre
```

### Les trois zones

| Zone | Rôle | Règle d'or |
|---|---|---|
| **raw** | Les fichiers tels que reçus | **On ne modifie jamais l'original** — on peut toujours tout recalculer |
| **staging** | Le signal devient des caractéristiques exploitables | Format Parquet, compact et rapide |
| **curated** | Les données propres + la prédiction du modèle | Une ligne = un événement analysé |

### Le pattern « processeur enfichable »

Le cœur du projet. Une classe abstraite décrit le pipeline **une seule fois** ;
chaque domaine ne remplit que deux méthodes.

```
SignalProcessor          ← écrit UNE fois, partagé
  ├─ load_raw()          ← « comment lis-tu ton signal ? »   à remplir
  ├─ to_features()       ← « qu'en extrais-tu ? »            à remplir
  └─ run()               ← l'enchaînement complet            DÉJÀ ÉCRIT

ECGProcessor  →  découpe par battement, mesure les intervalles
EEGProcessor  →  filtre, découpe en fenêtres, mesure les fréquences
AirProcessor  →  aplatit le JSON de l'API
```

**Résultat concret :** ajouter l'EEG a demandé 5 fichiers nouveaux et
**aucune réécriture** de l'entrepôt, de l'API ou de l'orchestrateur.

---

## 🔌 L'API Gateway

| Endpoint | Rôle |
|---|---|
| `GET /health` | Vérifie que MinIO et PostgreSQL répondent |
| `GET /raw` | Liste les fichiers bruts |
| `GET /staging` | Liste les fichiers de caractéristiques |
| `GET /curated` | Renvoie les analyses + prédictions (filtres : `source`, `record_id`, pagination) |
| `GET /stats` | Métriques de remplissage des buckets et de la base |
| `POST /ingest` | **Niveau avancé** — ingestion JSON (version naïve) |
| `POST /ingest_fast` | **Niveau avancé** — version optimisée |

Exemples :

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/curated?source=ecg&record_id=102&limit=5"
curl http://localhost:8000/stats
```

---

## ⚡ Niveau avancé — les performances

Mesurer le gain (l'API doit tourner) :

```bash
python -m src.api.benchmark
```

**Nos résultats** (moyenne sur 5 essais, après préchauffage) :

| Taille du lot | `/ingest` | `/ingest_fast` | Gain |
|---|---|---|---|
| 1 élément | 123,53 ms | 163,56 ms | **− 32,4 %** ⚠️ |
| 100 éléments | 4 608,97 ms | 169,56 ms | **+ 96,3 %** (27× plus rapide) |

### Les trois optimisations

1. **Mise en cache** — le modèle est chargé une fois, pas à chaque appel
2. **Vectorisation NumPy** — tout le lot est traité d'un coup, pas élément par élément
3. **Insertion groupée** — 100 insertions SQL deviennent une seule requête

### Le résultat contre-intuitif

Sur un lot **d'un seul élément**, notre version « optimisée » est **plus lente**.
Ce n'est pas un bug : nos trois optimisations sont des optimisations *de lot*.
Sur un élément unique, elles ajoutent le coût de leur machinerie sans en tirer le
bénéfice, et le temps est dominé par des frais fixes (réseau, connexion à la base)
que la vectorisation ne touche pas.

> **Une optimisation n'est jamais bonne dans l'absolu : elle est bonne pour un
> régime d'utilisation donné.**

---

## 🧠 Les résultats des modèles (sans les embellir)

| | **ECG** — battements anormaux | **EEG** — crises d'épilepsie |
|---|---|---|
| Anomalies dans les données | 33,6 % | **1,53 %** |
| Accuracy (baseline naïve) | 66,4 % | **97,5 %** |
| Accuracy (notre modèle) | 90,9 % | 97,8 % |
| **Rappel** (ce qui compte) | **85,3 %** ✅ | **16,7 %** ❌ |

### Ce que ce tableau raconte

**L'accuracy est un piège.** Sur l'EEG, un modèle qui ne détecte *rien* atteint
97,5 %. Le nôtre fait 97,8 % — un gain réel de **0,3 point**. Nous regardons donc
le **rappel** : sur toutes les crises réelles, combien en attrapons-nous ?

**Notre modèle EEG échoue, et nous l'assumons.** Il retrouve 3 fenêtres de crise
sur 18, sur un enregistrement jamais vu. Pourquoi ?

- **Trop peu d'exemples** — 26 fenêtres de crise pour apprendre.
- **Nous avons trop écrasé le signal** — nous moyennons les **23 canaux en un
  seul**, alors qu'une crise démarre dans une zone *précise* du cerveau. Nous
  avons détruit l'information dont le modèle avait besoin.
- **Un test volontairement sévère** — nous validons sur un enregistrement jamais
  vu, et non sur un découpage aléatoire qui aurait gonflé les scores.

**Le sur-apprentissage, pris en flagrant délit.** Sur les enregistrements
d'entraînement, le modèle semble excellent. Sur celui qu'il n'a jamais vu, il
s'effondre. Il a *mémorisé* au lieu de comprendre — et sans la distinction
entraînement/test, nous aurions conclu qu'il fonctionnait.

---

## 📂 Structure du projet

```
medical-datalake/
├── docker-compose.yml       # MinIO + PostgreSQL + Airflow (6 services)
├── requirements.txt
├── .env.example             # à copier en .env
│
├── dags/                    # Les DAGs Airflow
│   ├── dag_ecg.py           #   ECG   : manuel
│   ├── dag_eeg.py           #   EEG   : manuel
│   └── dag_air.py           #   Air   : planifié chaque heure + XCom
│
├── src/
│   ├── config.py            # tous les réglages, au même endroit
│   ├── storage/
│   │   ├── minio_client.py      # l'entrepôt (raw & staging)
│   │   └── postgres_client.py   # la base (curated)
│   ├── processors/
│   │   ├── base.py          # ⭐ le contrat commun SignalProcessor
│   │   ├── ecg.py           #   → battements et intervalles
│   │   ├── eeg.py           #   → filtrage et bandes de fréquence
│   │   └── air.py           #   → aplatissement du JSON
│   ├── ingestion/           # les scripts qui remplissent la zone raw
│   ├── pipelines/           # raw → staging
│   ├── models/              # staging → modèle → curated
│   ├── api/
│   │   ├── main.py          # les 5 endpoints obligatoires
│   │   ├── ingest.py        # /ingest et /ingest_fast (niveau avancé)
│   │   └── benchmark.py     # la mesure des performances
│   └── dashboard/
│       └── dashboard.py     # le moniteur (6 pages)
│
├── ARCHITECTURE.md          # les choix techniques et leurs raisons
├── GUIDE.md                 # le rôle de chaque fichier, expliqué
└── SPECS.md                 # la feuille de route du projet
```

---

## 🛠️ Dépannage

<details>
<summary><b>Airflow redémarre en boucle</b></summary>

Vérifiez qu'aucune version de SQLAlchemy n'est forcée dans
`_PIP_ADDITIONAL_REQUIREMENTS` (docker-compose.yml). Airflow 2.10 impose
**SQLAlchemy 1.4** ; le surcharger avec la 2.x le casse au démarrage.
</details>

<details>
<summary><b>Docker : « input/output error » ou « read-only file system »</b></summary>

Votre disque est plein. Airflow a besoin de ~3 Go. Libérez de l'espace, ou
déplacez le stockage Docker : *Docker Desktop → Settings → Resources → Advanced
→ Disk image location*.
</details>

<details>
<summary><b>Le téléchargement PhysioNet est très lent</b></summary>

C'est normal — PhysioNet est un serveur académique gratuit et souvent saturé.
Comptez 20 à 30 minutes pour les 170 Mo d'EEG. C'est un coût unique : les
fichiers restent ensuite dans MinIO.
</details>

<details>
<summary><b>Le dashboard affiche « API hors ligne »</b></summary>

L'API doit tourner en parallèle, dans un autre terminal :
`uvicorn src.api.main:app`
</details>

<details>
<summary><b>« Modèle introuvable » lors du benchmark</b></summary>

Entraînez d'abord le modèle : `python -m src.models.train_ecg`, puis
**redémarrez l'API**.
</details>

---


## 🎓 Ce que ce projet nous a appris

1. **La difficulté ne vient pas du code, mais des données.** Notre architecture a
   absorbé l'EEG sans broncher. C'est le *modèle* qui a échoué — parce qu'un
   événement représentant 1,5 % du signal est structurellement difficile à
   apprendre.

2. **Sur des données déséquilibrées, l'accuracy est un mensonge poli.** 97,8 %
   sonne bien, jusqu'à ce qu'on découvre qu'une baseline qui ne détecte rien fait
   97,5 %.

3. **Une moyenne peut ne décrire personne.** Notre taux global de 33 % d'anomalies
   cardiaques venait presque entièrement d'un seul patient porteur d'un
   stimulateur (95 % d'anomalies), quand les deux autres en avaient moins de 2 %.

4. **Une optimisation dépend de son régime d'usage.** 27× plus rapide sur 100
   éléments, et 32 % plus *lente* sur un seul.
