# 🏥 Medical Data Lake — ECG & EEG

Un data lake de bout en bout pour signaux physiologiques médicaux : ingestion,
transformation, Machine Learning et exposition via API.

Projet réalisé dans le cadre du cours **Data Lakes & Data Integration**
(EFREI 2025-2026).

> 📖 Pour comprendre l'architecture et les choix techniques, lire
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> 🗺️ Pour suivre l'avancement et les étapes, voir [`SPECS.md`](./SPECS.md).

---

## 🎯 Ce que fait le projet

Le data lake ingère des signaux médicaux depuis deux types de sources
(fichiers PhysioNet + une API temps réel), les fait passer par 3 zones de
traitement (raw → staging → curated), applique un modèle de détection
d'anomalies, et expose le tout via une API et un dashboard.

Deux domaines partagent la **même infrastructure** :
- **ECG** (MIT-BIH) — détection de battements cardiaques anormaux
- **EEG** (CHB-MIT) — détection de crises d'épilepsie

---

## 🧰 Prérequis

Avant de commencer, installe ces deux outils :

1. **Docker Desktop** — pour lancer les services (entrepôt + base de données).
   👉 https://www.docker.com/products/docker-desktop/
2. **Python 3.10+** — pour le code.
   👉 https://www.python.org/downloads/

Pour vérifier qu'ils sont installés, ouvre un terminal et tape :
```bash
docker --version
python --version
```

---

## 🚀 Installation et lancement (étape 0)

### 1. Récupérer les identifiants

Copie le fichier d'exemple de configuration :
```bash
cp .env.example .env
```
(Sur Windows sans `cp` : copie-colle le fichier à la main et renomme-le `.env`.)

### 2. Lancer l'entrepôt et la base de données

Une seule commande allume MinIO (l'entrepôt) et PostgreSQL (la base) :
```bash
docker-compose up -d
```
Le `-d` veut dire "en arrière-plan" (le terminal reste libre).

### 3. Vérifier que ça marche

Ouvre ton navigateur sur **http://localhost:9001**
Tu devrais voir la console web de MinIO.
Identifiant : `minioadmin` — Mot de passe : `minioadmin`

✅ Si tu vois cette page, l'étape 0 est réussie !

### 4. Installer les librairies Python et créer les buckets

```bash
pip install -r requirements.txt
python -m src.storage.minio_client
```
La dernière commande crée les buckets `raw` et `staging` dans MinIO.
Rafraîchis la console web : ils devraient apparaître.

---

## 🛑 Arrêter les services

```bash
docker-compose down
```
(Les données sont conservées grâce aux volumes. Pour tout effacer :
`docker-compose down -v`.)

---

## 📂 Structure du projet

```
medical-datalake/
├── README.md              # ce fichier
├── ARCHITECTURE.md        # design & choix techniques
├── SPECS.md               # feuille de route
├── docker-compose.yml     # définit MinIO + PostgreSQL
├── requirements.txt       # librairies Python
├── .env.example           # modèle de configuration
└── src/
    ├── config.py          # paramètres centralisés
    ├── storage/
    │   └── minio_client.py    # dialogue avec l'entrepôt
    └── processors/
        └── base.py            # contrat commun ECG/EEG
```

---

## 🗺️ Prochaines étapes

Voir [`SPECS.md`](./SPECS.md). La suite immédiate : le pipeline ECG complet
(téléchargement MIT-BIH → raw → features → modèle → curated).
