# Architecture du Data Lake médical

> Document de référence. Il explique **quoi** on construit et **pourquoi** on a
> choisi chaque technologie. À lire en premier si tu reprends le projet.

---

## 1. La vision en une phrase

On construit une **plateforme** capable d'ingérer des signaux physiologiques
(ECG, EEG) et un flux d'API, de les transformer, d'y appliquer un modèle de
Machine Learning, et d'exposer le tout via une API simple et un dashboard.

Le mot important est **plateforme** : on n'écrit pas "un script pour l'ECG"
puis "un script pour l'EEG". On écrit **une seule chaîne de traitement
partagée** dans laquelle on *branche* des sources différentes. Ajouter l'EEG
après l'ECG ne demande presque aucun code nouveau. C'est ça qui fait la
différence entre un TP et un vrai projet d'ingénieur.

---

## 2. Les 4 zones (l'usine à données)

On utilise l'architecture classique dite **medallion** (raw → staging →
curated). Imagine une usine avec 4 postes à la chaîne :

| Zone | Rôle | Analogie | Techno |
|------|------|----------|--------|
| **raw** | Stocker les fichiers bruts, jamais modifiés | L'entrepôt de réception | MinIO (S3) |
| **staging** | Nettoyer et extraire les "features" | L'atelier de transformation | MinIO (Parquet) |
| **curated** | Données propres + résultat du modèle ML | Le rayon final, prêt à vendre | PostgreSQL |
| **serving** | Exposer les données au monde extérieur | Le comptoir | FastAPI + Streamlit |

**Pourquoi garder le brut intact en zone raw ?** Parce que si un jour on se
rend compte qu'on a mal nettoyé les données, on peut tout recalculer depuis la
source. On ne perd jamais l'original. C'est une règle d'or du data engineering.

---

## 3. Le stack technique et sa justification

Chaque choix est fait pour être **gratuit, réaliste en entreprise, et bon pour
le portfolio**.

- **MinIO** (zone raw + staging) — c'est un "S3 maison". S3 est le service de
  stockage de fichiers d'Amazon, le standard mondial. MinIO parle le même
  langage mais tourne sur ta machine, gratuitement, dans Docker. Le sujet
  impose S3 ou Elasticsearch pour le raw : MinIO coche la case S3.

- **PostgreSQL** (zone curated) — la base de données relationnelle la plus
  respectée. Parfaite pour ranger des données structurées (une ligne = un
  enregistrement analysé). *Option d'évolution : TimescaleDB, une extension de
  Postgres spécialisée dans les séries temporelles — on la garde en réserve.*

- **wfdb / scipy / neurokit2** (traitement ECG) — `wfdb` est LA librairie pour
  lire les fichiers de PhysioNet. `neurokit2` calcule les features cardiaques.

- **MNE-Python** (traitement EEG) — la référence mondiale pour traiter des
  signaux EEG (filtrage, suppression d'artefacts, découpage en fenêtres).

- **Apache Airflow** (orchestration) — le "chef d'atelier". Il déclenche les
  tâches automatiquement, à intervalle régulier, et gère les dépendances entre
  elles. Le sujet le mentionne explicitement (scheduling, XCom).

- **FastAPI** (API Gateway) — pour créer les endpoints web (`/raw`, `/curated`,
  `/ingest`...). Rapide à écrire, moderne, et supporte l'asynchrone — ce qui
  nous servira pour le `/ingest_fast` du niveau avancé.

- **Streamlit** (dashboard) — pour construire l'appli de visualisation en
  quelques lignes de Python, sans savoir faire du web. Upgrade possible en
  React si on veut un vrai look "moniteur hôpital".

- **Docker / docker-compose** — permet de lancer MinIO + PostgreSQL + Airflow
  d'une seule commande, sur n'importe quelle machine. Indispensable pour que le
  correcteur puisse builder ton projet sans galère.

---

## 4. Le pattern "processeur enfichable" (le cœur du projet)

Voici comment ECG et EEG partagent la même infra. On définit un **contrat
commun** (une classe de base) et une **implémentation par domaine** :

```
SignalProcessor (classe de base, écrite UNE fois)
   |-- load_raw()      -> lire le fichier brut depuis MinIO
   |-- to_features()   -> extraire les features (spécifique au domaine)
   |-- run()           -> enchaîne tout : logique PARTAGÉE
   |
   |-- ECGProcessor   (wfdb + neurokit2)
   |-- EEGProcessor   (MNE-Python)
```

La méthode `run()`, le stockage, l'écriture en base, l'API : tout est écrit une
seule fois. Seul le "quoi extraire" change entre ECG et EEG. Ajouter une
nouvelle source = écrire une nouvelle petite classe, rien d'autre.

---

## 5. Les endpoints de l'API (le comptoir)

| Endpoint | Ce qu'il fait |
|----------|---------------|
| `GET /raw` | Liste/récupère les données brutes |
| `GET /staging` | Récupère les features intermédiaires |
| `GET /curated` | Récupère les résultats finaux + prédictions ML |
| `GET /health` | Vérifie que les services tournent |
| `GET /stats` | Métriques : combien de fichiers, taille des buckets... |
| `POST /ingest` | (Niveau avancé) Ingérer des données envoyées en JSON |
| `POST /ingest_fast` | (Niveau avancé) Version optimisée, >30% plus rapide |

---

## 6. Glossaire pour débuter

- **Data lake** : un grand réservoir où on stocke des données de tous types
  (fichiers, JSON, images...) avant de les valoriser.
- **Feature** : une valeur chiffrée calculée à partir de données brutes, qui
  résume une information utile (ex : la fréquence cardiaque moyenne d'un ECG).
- **Bucket** : un "dossier" de stockage dans MinIO/S3.
- **Container (Docker)** : une mini-machine virtuelle légère et jetable qui
  contient un logiciel prêt à tourner (MinIO, Postgres...). On les allume et
  éteint à volonté.
- **Parquet** : un format de fichier optimisé pour stocker des tableaux de
  données de façon compacte et rapide à lire.
- **Endpoint** : une adresse web (URL) qu'on peut appeler pour obtenir ou
  envoyer des données.
- **Pipeline** : la chaîne de traitement qui fait passer une donnée d'une zone
  à la suivante.
- **Orchestration** : le fait de déclencher et coordonner automatiquement les
  étapes du pipeline (le rôle d'Airflow).
