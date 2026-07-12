# 📚 Guide du projet — comprendre chaque fichier

> Ce document explique **à quoi sert chaque fichier** qu'on a créé, comme si tu
> découvrais tout pour la première fois. Le but n'est pas de rendre le projet
> bêtement, mais que tu comprennes vraiment ce que fait chaque morceau.
>
> Lis-le tranquillement. Chaque section répond à 3 questions :
> **C'est quoi ?** · **Pourquoi on en a besoin ?** · **Comment ça marche ?**

---

## 🗺️ D'abord, la vue d'ensemble

Notre projet est une "usine à données" en 4 postes. Une donnée médicale entre
d'un côté, ressort analysée de l'autre :

```
   FICHIER ECG/EEG                                      TOI, dans le navigateur
   ou FLUX API                                                  ▲
        │                                                       │
        ▼                                                       │
  ┌───────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────┐
  │   RAW     │ ──▶ │  STAGING  │ ──▶ │  CURATED  │ ──▶ │  API + DASH  │
  │ entrepôt  │     │  atelier  │     │ rayon fin │     │  le comptoir │
  │ (MinIO)   │     │  (MinIO)  │     │(PostgreS) │     │(FastAPI/...)│
  └───────────┘     └───────────┘     └───────────┘     └──────────────┘
   on stocke le      on nettoie et     on range propre    on expose au
   fichier brut      on extrait les    + résultat du      monde extérieur
   sans y toucher    "features"        modèle d'IA
```

Chaque fichier du projet sert **un** de ces postes, ou bien fait le lien entre
eux. Voyons-les un par un.

---

## 📁 Les fichiers d'infrastructure (le décor)

Ces fichiers ne contiennent pas de "logique métier". Ils préparent le terrain :
ils disent quels logiciels lancer et avec quels réglages.

### `docker-compose.yml`

**C'est quoi ?** Une liste de "machines" à démarrer, écrite dans un format que
Docker comprend.

**Pourquoi on en a besoin ?** Notre projet a besoin de deux logiciels qui
tournent en permanence : MinIO (l'entrepôt) et PostgreSQL (la base). Les
installer à la main sur ta machine serait long et différent sur Windows/Mac/
Linux. Docker règle ça : une seule commande, `docker-compose up`, et les deux
démarrent, identiques partout.

**Comment ça marche ?** Le fichier décrit 2 "services". Pour chacun, il dit :
quelle image de logiciel utiliser (`minio/minio`, `postgres:16`), quels ports
ouvrir (des "portes" numérotées pour communiquer), et où garder les données.

> 💡 **Container** = une mini-machine jetable qui contient un logiciel prêt à
> l'emploi. On l'allume, on l'éteint, sans rien salir sur ton ordi.

### `.env.example` (à copier en `.env`)

**C'est quoi ?** Un fichier de mots de passe et d'adresses.

**Pourquoi ?** On ne met JAMAIS les mots de passe en dur dans le code (ce serait
visible par tous sur GitHub). On les range à part, dans `.env`, que Git ignore.

**Comment ça marche ?** Le code lit ces valeurs au démarrage. Si demain tu
changes un mot de passe, tu le changes ici uniquement.

### `requirements.txt`

**C'est quoi ?** La liste des "librairies" Python dont le projet a besoin.

**Pourquoi ?** Une librairie = du code déjà écrit par d'autres qu'on réutilise
(ex : `wfdb` sait lire les fichiers médicaux, on ne va pas le réécrire). Cette
liste permet à n'importe qui de tout installer d'un coup avec
`pip install -r requirements.txt`.

**Comment ça marche ?** Chaque ligne = une librairie + sa version exacte. Fixer
la version évite que le projet casse le jour où une librairie change.

### `.gitignore`

**C'est quoi ?** Une liste de fichiers que Git doit **ignorer** (ne pas envoyer
sur GitHub).

**Pourquoi ?** Deux raisons : les secrets (`.env`) ne doivent pas fuiter, et les
données médicales (fichiers lourds) n'ont rien à faire dans le code.

---

## 🧠 Le code du projet (le cerveau)

Ici commence la vraie logique. Tout est dans le dossier `src/`.

### `src/config.py`

**C'est quoi ?** Le "tableau de bord" du projet : un seul endroit qui rassemble
tous les réglages.

**Pourquoi ?** Sans ça, l'adresse de MinIO ou le nom de la base seraient écrits
un peu partout dans le code. Le jour où tu changes quelque chose, tu devrais
chercher dans 15 fichiers. Là, tout est au même endroit.

**Comment ça marche ?** Il lit le fichier `.env` et range chaque valeur dans un
objet `config`. Le reste du code écrira simplement `config.MINIO_ENDPOINT` pour
récupérer l'adresse. Propre et centralisé.

### `src/storage/minio_client.py`

**C'est quoi ?** Un petit assistant qui sait parler à l'entrepôt MinIO.

**Pourquoi ?** Déposer ou récupérer un fichier dans MinIO demande plusieurs
lignes de code techniques. Plutôt que de les réécrire partout, on les range ici
sous forme de fonctions simples : `upload_file(...)`, `download_file(...)`.

**Comment ça marche ?** Il contient 4 fonctions :
- `get_client()` : ouvre la connexion à MinIO.
- `ensure_buckets()` : crée les "dossiers" `raw` et `staging` s'ils manquent.
- `upload_file()` : dépose un fichier dans l'entrepôt.
- `download_file()` : récupère un fichier de l'entrepôt.

> 💡 **Bucket** = un grand dossier de rangement dans l'entrepôt. On en a un pour
> le brut (`raw`) et un pour le transformé (`staging`).

### `src/processors/base.py` ⭐ (le fichier le plus important)

**C'est quoi ?** Le "moule" commun que devront respecter TOUS les traitements de
signal, que ce soit l'ECG ou l'EEG.

**Pourquoi ?** C'est le cœur de l'astuce qui rend ton projet impressionnant.
L'idée : au lieu d'écrire un gros programme séparé pour l'ECG et un autre pour
l'EEG (avec plein de code copié-collé), on écrit **la partie commune une seule
fois**, et on laisse juste 2 petits "trous" à remplir pour chaque type de
signal.

**Comment ça marche ? (le concept clé, prends ton temps ici)**

Imagine une **recette de cuisine à trous** :

> 1. Sortir l'ingrédient du frigo *(à préciser : lequel ?)*
> 2. Le transformer en plat *(à préciser : comment ?)*
> 3. Le servir dans l'assiette *(toujours pareil)*

L'étape 3 est **toujours identique** : on la écrit une fois. Les étapes 1 et 2
changent selon le plat : pour l'ECG on sort un signal cardiaque et on compte les
battements ; pour l'EEG on sort un signal cérébral et on calcule des fréquences.

Dans le code, ça donne :
- `run()` = la recette complète (les 3 étapes enchaînées). **Écrite une fois.**
- `load_raw()` et `to_features()` = les 2 trous, laissés vides ici.

Ces "trous" s'appellent des **méthodes abstraites**. Une classe qui a des trous
s'appelle une **classe abstraite** (`ABC` en Python). On ne peut pas l'utiliser
telle quelle : il faut d'abord en faire une version qui remplit les trous.

Ces versions, ce seront `ECGProcessor` et `EEGProcessor` (on les créera aux
étapes 1 et 3). On dit qu'elles **héritent** de `SignalProcessor` : elles
récupèrent gratuitement la recette commune (`run()`) et n'ont qu'à remplir les
2 trous.

> 💡 **Pourquoi c'est malin ?** Le jour où tu ajoutes l'EEG, tu écris ~30 lignes
> (juste les 2 trous). Tu ne touches PAS au stockage, ni à la base, ni à l'API.
> C'est exactement ce qu'un correcteur ou un recruteur veut voir : une archi
> pensée pour grandir. C'est ce qui sépare un projet d'école d'un vrai projet.

### Les fichiers `__init__.py`

**C'est quoi ?** Des fichiers vides.

**Pourquoi ?** Leur simple présence dit à Python : "ce dossier est un module,
tu peux importer du code depuis ici". Sans eux, `from src.config import config`
ne marcherait pas. C'est une convention Python, rien de plus.

---

## 📖 Les fichiers de documentation (la notice)

### `README.md`

La porte d'entrée. La première chose que voit quelqu'un (prof, recruteur) qui
ouvre ton dépôt GitHub. Il explique ce qu'est le projet et comment le lancer.
Le sujet insiste : un bon README est noté.

### `ARCHITECTURE.md`

Le "pourquoi" des choix techniques. Pourquoi MinIO et pas autre chose, à quoi
sert chaque zone, etc. C'est le document qu'on relit pour se remettre dans le
bain.

### `SPECS.md`

La feuille de route avec les cases à cocher. Notre boussole : on sait toujours
où on en est et ce qui reste.

### `GUIDE.md`

Ce fichier-ci. 🙂 Le guide pédagogique qui explique chaque fichier.

---

## 🎯 Où on va : le niveau standard ET avancé

Pour que tu voies la destination complète, voici ce que le sujet demande.

### Niveau standard (obligatoire, 16-20/20 possible)

- Les 3 zones du data lake bien implémentées
- Des scripts de transformation **robustes** : gérer les cas bizarres, attraper
  les erreurs, renvoyer des messages clairs (le prof teste ça !)
- Un pipeline fiable (Airflow)
- L'API Gateway complète : `/raw`, `/staging`, `/curated`, `/health`, `/stats`
- Du code commenté et bien organisé

### Niveau avancé (optionnel, pour le t-shirt 👕)

- **`/ingest`** : une porte pour envoyer des données en JSON dans le pipeline.
  Il faut **chronométrer** le temps pour 1 élément puis 100 éléments.
- **`/ingest_fast`** : la même chose, mais **au moins 30% plus rapide**, grâce à
  des optimisations (vectorisation NumPy, asynchrone, cache, parallélisme...).
  Il faut **documenter le gain** avec des mesures précises.

L'idée du niveau avancé : prouver qu'on sait rendre un pipeline **performant**,
pas juste fonctionnel. C'est une compétence très recherchée en data engineering.

### Ce que le prof évalue

Qualité des 3 couches · robustesse (gestion des erreurs) · fiabilité du pipeline
· complétude de l'API · documentation · clarté du code. Et pour l'avancé : le
gain de perf mesuré, la créativité des optimisations, la qualité de leur
documentation, et en bonus l'originalité du domaine (le médical, c'est original,
bon point pour nous).

---

## ✅ En résumé : qui fait quoi

| Fichier | Rôle en une phrase |
|---------|--------------------|
| `docker-compose.yml` | Démarre l'entrepôt et la base d'une commande |
| `.env` | Range les mots de passe à l'abri |
| `requirements.txt` | Liste les librairies à installer |
| `.gitignore` | Empêche les secrets/données d'aller sur GitHub |
| `src/config.py` | Centralise tous les réglages |
| `src/storage/minio_client.py` | Parle à l'entrepôt (déposer/récupérer) |
| `src/processors/base.py` | Le moule commun ECG/EEG (le cœur) |
| `README.md` | Comment lancer le projet |
| `ARCHITECTURE.md` | Pourquoi ces choix techniques |
| `SPECS.md` | La feuille de route |
| `GUIDE.md` | Ce guide, fichier par fichier |

Quand un fichier de ce guide te semble flou, reviens ici, relis la section, et
si ça coince encore, demande-moi : on le reprend ensemble aussi lentement qu'il
faut.
