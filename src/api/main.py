"""
main.py — ÉTAPE 4 : l'API Gateway
----------------------------------
Le "comptoir" du data lake. Le but (dixit le sujet) : avoir une interface simple
qui permet de récupérer les données ingérées sans avoir à s'embêter avec MinIO
ou PostgreSQL directement.

Les 5 endpoints obligatoires :
    GET /health   -> les services répondent-ils ?
    GET /raw      -> ce qu'il y a dans la zone raw
    GET /staging  -> ce qu'il y a dans la zone staging
    GET /curated  -> les données finales + prédictions du modèle
    GET /stats    -> métriques de remplissage des buckets et de la base

(Les endpoints /ingest et /ingest_fast du niveau avancé viendront ensuite.)

Pour lancer l'API :
    uvicorn src.api.main:app --reload

Puis ouvrir dans le navigateur :
    http://localhost:8000/docs   <- documentation interactive, générée toute seule
"""

from fastapi import FastAPI, HTTPException, Query

from src.config import config
from src.storage import minio_client as mc
from src.storage import postgres_client as pg
from src.api.ingest import router as ingest_router

# On crée l'application. Le titre et la description apparaissent dans /docs.
app = FastAPI(
    title="Medical Data Lake API",
    description=(
        "API Gateway du data lake médical (ECG / EEG). "
        "Expose les zones raw, staging et curated du lake."
    ),
    version="1.0.0",
)

# On branche les endpoints du niveau avancé (/ingest et /ingest_fast).
app.include_router(ingest_router)


# ----------------------------------------------------------------------
# GET /  -> petit message d'accueil, pratique pour vérifier que ça tourne
# ----------------------------------------------------------------------
@app.get("/", tags=["Général"])
def racine():
    """Page d'accueil de l'API."""
    return {
        "message": "Medical Data Lake API",
        "documentation": "/docs",
        "endpoints": ["/health", "/raw", "/staging", "/curated", "/stats"],
    }


# ----------------------------------------------------------------------
# GET /health  -> vérification de l'état des services
# ----------------------------------------------------------------------
@app.get("/health", tags=["Général"])
def health():
    """
    Vérifie que les deux services du data lake répondent :
      - MinIO (l'entrepôt de fichiers)
      - PostgreSQL (la base curated)

    Renvoie "healthy" si les deux répondent, "degraded" sinon.
    """
    minio_ok = mc.ping()
    postgres_ok = pg.ping()
    tout_va_bien = minio_ok and postgres_ok

    return {
        "status": "healthy" if tout_va_bien else "degraded",
        "services": {
            "minio": "up" if minio_ok else "down",
            "postgresql": "up" if postgres_ok else "down",
        },
    }


# ----------------------------------------------------------------------
# GET /raw  -> le contenu de la zone raw
# ----------------------------------------------------------------------
@app.get("/raw", tags=["Zones du lake"])
def get_raw(
    source: str | None = Query(None, description="Filtrer par source, ex: 'ecg'"),
):
    """
    Liste les fichiers bruts stockés dans la zone raw (MinIO).
    On peut filtrer par source (ex: /raw?source=ecg).
    """
    prefix = f"{source}/" if source else ""
    try:
        objets = mc.list_objects(config.BUCKET_RAW, prefix=prefix)
    except Exception as err:
        # On renvoie une vraie erreur HTTP explicite plutôt que de planter.
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de joindre MinIO : {err}",
        )

    return {
        "zone": "raw",
        "bucket": config.BUCKET_RAW,
        "filtre_source": source,
        "n_objets": len(objets),
        "objets": objets,
    }


# ----------------------------------------------------------------------
# GET /staging  -> le contenu de la zone staging
# ----------------------------------------------------------------------
@app.get("/staging", tags=["Zones du lake"])
def get_staging(
    source: str | None = Query(None, description="Filtrer par source, ex: 'ecg'"),
):
    """
    Liste les fichiers de features (.parquet) de la zone staging (MinIO).
    """
    prefix = f"{source}/" if source else ""
    try:
        objets = mc.list_objects(config.BUCKET_STAGING, prefix=prefix)
    except Exception as err:
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de joindre MinIO : {err}",
        )

    return {
        "zone": "staging",
        "bucket": config.BUCKET_STAGING,
        "filtre_source": source,
        "n_objets": len(objets),
        "objets": objets,
    }


# ----------------------------------------------------------------------
# GET /curated  -> les données finales + les prédictions du modèle
# ----------------------------------------------------------------------
@app.get("/curated", tags=["Zones du lake"])
def get_curated(
    source: str | None = Query(None, description="Filtrer par source, ex: 'ecg'"),
    record_id: str | None = Query(None, description="Filtrer par enregistrement, ex: '100'"),
    limit: int = Query(100, ge=1, le=1000, description="Nb max de lignes (1-1000)"),
    offset: int = Query(0, ge=0, description="Décalage, pour la pagination"),
):
    """
    Récupère les battements analysés depuis la zone curated (PostgreSQL),
    avec leur vérité terrain (is_abnormal) et la prédiction du modèle (predicted).

    Exemples :
      /curated?limit=10
      /curated?source=ecg&record_id=102
    """
    try:
        # La qualité de l'air vit dans sa propre table (schéma très différent
        # des signaux physiologiques). On aiguille donc vers la bonne requête.
        if source == "air":
            lignes = pg.fetch_air(limit=limit)
        else:
            lignes = pg.fetch_rows(
                source_type=source, record_id=record_id, limit=limit, offset=offset
            )
    except Exception as err:
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de joindre PostgreSQL : {err}",
        )

    return {
        "zone": "curated",
        "filtres": {"source": source, "record_id": record_id},
        "pagination": {"limit": limit, "offset": offset},
        "n_lignes": len(lignes),
        "donnees": lignes,
    }


# ----------------------------------------------------------------------
# GET /stats  -> métriques de remplissage du data lake
# ----------------------------------------------------------------------
@app.get("/stats", tags=["Général"])
def get_stats():
    """
    Métriques sur le remplissage des buckets (MinIO) et de la base (PostgreSQL).
    C'est la vue d'ensemble de l'état du data lake.

    Cet endpoint est volontairement TOLÉRANT AUX PANNES : si un service est
    injoignable, il renvoie quand même les infos de l'autre, avec un champ
    "erreur" explicite. Un endpoint de monitoring qui plante quand un service
    tombe serait un contresens (c'est justement là qu'on en a besoin !).
    """
    # --- Côté MinIO ---
    try:
        buckets = {
            "raw": mc.bucket_stats(config.BUCKET_RAW),
            "staging": mc.bucket_stats(config.BUCKET_STAGING),
        }
    except Exception as err:
        buckets = {"erreur": f"MinIO injoignable : {err}"}

    # --- Côté PostgreSQL ---
    try:
        curated = pg.get_stats()
    except Exception as err:
        curated = {"erreur": f"PostgreSQL injoignable : {err}"}

    # --- La source API (qualité de l'air), dans sa propre table ---
    try:
        air = pg.stats_air()
    except Exception as err:
        air = {"erreur": f"PostgreSQL injoignable : {err}"}

    return {"buckets": buckets, "curated": curated, "air": air}
