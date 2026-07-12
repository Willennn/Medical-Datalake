# Feuille de route (SPECS)

> Notre boussole. On coche au fur et à mesure. À chaque séance, on regarde ici
> où on en est et ce qui reste.

Légende : `[ ]` à faire · `[x]` fait · `[~]` en cours

---

## Étape 0 — Fondations (setup)

Objectif : avoir l'entrepôt (MinIO) et la base (PostgreSQL) qui tournent, et la
structure du projet en place.

- [x] Structure des dossiers du projet
- [x] `ARCHITECTURE.md`, `SPECS.md` et `GUIDE.md`
- [x] `docker-compose.yml` (MinIO + PostgreSQL)
- [x] `requirements.txt` (librairies Python)
- [x] `config.py` (paramètres centralisés)
- [x] `src/storage/minio_client.py` (connexion à l'entrepôt + création des buckets)
- [x] `src/processors/base.py` (le contrat commun `SignalProcessor`)
- [ ] **À faire par toi** : installer Docker Desktop
- [ ] **À faire par toi** : lancer `docker-compose up` et voir MinIO dans le navigateur

**Critère de réussite de l'étape 0** : tu ouvres http://localhost:9001 dans ton
navigateur et tu vois la console web de MinIO.

---

## Étape 1 — Pipeline ECG complet (le squelette qui marche)

Objectif : faire passer un enregistrement ECG de bout en bout, raw → curated,
avec un modèle qui détecte les battements anormaux.

- [x] Script de téléchargement du dataset MIT-BIH (via `wfdb`)
- [x] Ingestion : déposer les fichiers bruts dans le bucket `raw` de MinIO
- [x] `ECGProcessor` : lire le signal, extraire les features (battements)
- [x] Écrire les features en zone `staging` (Parquet)
- [x] Créer la table `curated` dans PostgreSQL
- [x] Entraîner un premier modèle (classification battement normal/anormal)
- [x] Écrire les résultats (features + prédiction) en zone `curated`

**Critère de réussite** : une requête SQL sur la base curated renvoie des
battements avec leur prédiction.

---

## Étape 1bis — La source API (OBLIGATOIRE : le sujet impose 2 sources)

- [x] Choix de la source : OpenAQ (qualité de l'air, temps réel, gratuite)
- [x] `ingest_air.py` : appel de l'API -> instantané JSON horodaté en zone raw
- [x] `AirQualityProcessor` : aplatissement du JSON -> features (même contrat que l'ECG)
- [x] `run_air.py` : raw -> staging
- [ ] **À faire par toi** : créer un compte OpenAQ et coller la clé dans `.env`

---

## Étape 2 — Orchestration avec Airflow

Objectif : que le pipeline se déclenche tout seul, sans lancer les scripts à la
main.

- [x] Ajouter Airflow au `docker-compose.yml` (LocalExecutor)
- [x] DAG `pipeline_ecg` : ingestion → staging → curated (déclenché à la main)
- [x] DAG `pipeline_air_quality` : scheduling horaire de l'API OpenAQ
- [x] (Bonus) XCom : la tâche d'ingestion transmet l'instantané à la tâche staging

**Critère de réussite** : le DAG tourne en vert dans l'interface Airflow.

---

## Étape 3 — Brancher l'EEG (la partie qui impressionne)

Objectif : ajouter un second domaine sur la MÊME infra, pour prouver que
l'architecture est extensible.

- [x] Télécharger un sous-ensemble du dataset CHB-MIT (4 fichiers, ~170 Mo)
- [x] `EEGProcessor` : filtrage passe-bande + fenêtrage + puissances par bande (MNE + SciPy)
- [x] Gérer le déséquilibre des classes (class_weight + focus sur le rappel)
- [x] Modèle de détection de crises (Random Forest pondéré)
- [x] Séparation train/test PAR ENREGISTREMENT (pas au hasard : plus honnête)
- [x] Migration de schéma : la table curated accueille ECG ET EEG
- [x] DAG `pipeline_eeg`

**Critère de réussite** : ECG et EEG tournent tous deux sur la même
infrastructure, chacun avec son propre DAG.

---

## Étape 4 — API Gateway, niveau avancé et dashboard

Objectif : le comptoir + les optimisations qui font gagner des points bonus.

- [x] API FastAPI : `/raw`, `/staging`, `/curated`, `/health`, `/stats`
- [x] Endpoint `/ingest` (JSON) + mesure du temps (batch de 1 et de 100)
- [x] Endpoint `/ingest_fast` (>30% plus rapide : vectorisation, async, cache...)
- [ ] Documenter la comparaison de performances
- [x] Dashboard Streamlit : moniteur clinique (4 onglets, consomme l'API)
- [ ] README final complet (build + utilisation)

**Critère de réussite** : le correcteur lance le projet, appelle les endpoints,
et voit le dashboard afficher les données en direct.

---

## Livrables finaux (rappel du sujet)

- [ ] Dépôt GitHub avec tout le code
- [ ] Documentation technique (architecture, choix, install, perfs)
- [ ] README exhaustif : comment builder et utiliser le projet
