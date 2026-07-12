"""
ingest.py — NIVEAU AVANCÉ : /ingest et /ingest_fast
---------------------------------------------------
Le sujet demande deux endpoints d'ingestion :
  - /ingest      : accepte des données JSON et les propage dans le pipeline,
                   avec chronométrage (batch de 1, puis de 100).
  - /ingest_fast : la MÊME chose, mais au moins 30 % plus rapide.

=== LA PHILOSOPHIE (à comprendre, c'est le cœur du niveau avancé) ===

/ingest est écrit "naïvement" : c'est ce qu'un développeur écrit spontanément
quand il ne pense pas encore à la performance. Il est CORRECT, mais lent.

Trois choses le ralentissent, et ce sont les 3 grands classiques :

  1. BOUCLE PYTHON : il traite les battements UN PAR UN. Python est lent en
     boucle. NumPy sait faire la même chose sur tout le lot d'un coup.

  2. MODÈLE RECHARGÉ : il relit le modèle depuis le disque À CHAQUE APPEL.
     Lire un fichier, c'est lent. On peut le garder en mémoire (cache).

  3. INSERTIONS UNE PAR UNE : 100 battements = 100 requêtes SQL, chacune avec
     son aller-retour réseau. On peut tout insérer en UNE seule requête.

/ingest_fast corrige ces 3 points. Le gain est réel, pas artificiel : on ne
ralentit pas /ingest exprès, on écrit juste la version que ferait un ingénieur
attentif à la performance.
"""

import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.storage import postgres_client as pg

router = APIRouter()

MODEL_PATH = Path("models") / "ecg_model.joblib"

# Les features attendues, dans l'ordre exact où le modèle les a apprises.
FEATURE_COLS = ["rr_prev", "rr_next", "amp_max", "amp_min", "amp_range"]

# --- LE CACHE (optimisation n°2) ---
# On garde le modèle en mémoire une fois chargé. La 1re requête paie le coût du
# chargement, toutes les suivantes sont gratuites.
_model_cache = None


def get_model_cached():
    """Charge le modèle UNE SEULE FOIS, puis le garde en mémoire."""
    global _model_cache
    if _model_cache is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Modèle introuvable ({MODEL_PATH}). "
                "Lance d'abord : python -m src.models.train_ecg"
            )
        _model_cache = joblib.load(MODEL_PATH)
    return _model_cache


def get_model_from_disk():
    """Recharge le modèle depuis le disque À CHAQUE FOIS (version naïve)."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle introuvable ({MODEL_PATH}). "
            "Lance d'abord : python -m src.models.train_ecg"
        )
    return joblib.load(MODEL_PATH)


# ----------------------------------------------------------------------
# Le format des données attendues (validé automatiquement par FastAPI)
# ----------------------------------------------------------------------
class Beat(BaseModel):
    """Un battement cardiaque à analyser."""
    rr_prev: float = Field(..., description="Temps depuis le battement précédent (s)")
    rr_next: float = Field(..., description="Temps jusqu'au battement suivant (s)")
    amp_max: float = Field(..., description="Amplitude max autour du battement")
    amp_min: float = Field(..., description="Amplitude min autour du battement")


class IngestPayload(BaseModel):
    """
    Le corps de la requête. Format :
        { "data": { "beats": [ {...}, {...} ] } }
    """
    data: dict = Field(
        ...,
        json_schema_extra={
            "example": {
                "beats": [
                    {"rr_prev": 0.81, "rr_next": 0.79, "amp_max": 1.2, "amp_min": -0.3}
                ]
            }
        },
    )


def _extract_beats(payload: IngestPayload) -> list[dict]:
    """Récupère et valide la liste des battements envoyés."""
    beats = payload.data.get("beats")
    if not beats:
        raise HTTPException(
            status_code=400,
            detail="Le payload doit contenir data.beats (une liste non vide).",
        )
    if not isinstance(beats, list):
        raise HTTPException(status_code=400, detail="data.beats doit être une liste.")
    return beats


# ======================================================================
#  /ingest  — LA VERSION NAÏVE
# ======================================================================
@router.post("/ingest", tags=["Niveau avancé"])
def ingest(payload: IngestPayload):
    """
    Ingère des battements et les fait passer dans le pipeline (version naïve).

    Ce qui la rend lente (volontairement représentatif du code "spontané") :
      - le modèle est rechargé depuis le disque à chaque appel,
      - les battements sont traités un par un dans une boucle Python,
      - chaque battement donne lieu à sa propre requête SQL d'insertion.
    """
    start = time.perf_counter()
    beats = _extract_beats(payload)

    try:
        # ❌ LENT #1 : on relit le modèle depuis le disque à chaque requête.
        model = get_model_from_disk()

        pg.ensure_table()
        engine = pg.get_engine()

        results = []
        # ❌ LENT #2 : boucle Python, un battement à la fois.
        for beat in beats:
            amp_range = beat["amp_max"] - beat["amp_min"]

            # Le modèle est appelé une fois PAR BATTEMENT (très coûteux).
            features = pd.DataFrame([{
                "rr_prev": beat["rr_prev"],
                "rr_next": beat["rr_next"],
                "amp_max": beat["amp_max"],
                "amp_min": beat["amp_min"],
                "amp_range": amp_range,
            }])[FEATURE_COLS]

            predicted = int(model.predict(features)[0])
            proba = float(model.predict_proba(features)[0][1])

            # ❌ LENT #3 : une requête SQL par battement.
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO curated_beats
                        (source_type, record_id, rr_prev, rr_next, amp_range,
                         predicted, proba)
                    VALUES ('ecg', 'api_ingest', :rr_prev, :rr_next, :amp_range,
                            :predicted, :proba)
                """), {
                    "rr_prev": beat["rr_prev"], "rr_next": beat["rr_next"],
                    "amp_range": amp_range, "predicted": predicted, "proba": proba,
                })

            results.append({"predicted": predicted, "proba": round(proba, 3)})

    except FileNotFoundError as err:
        raise HTTPException(status_code=503, detail=str(err))
    except KeyError as err:
        raise HTTPException(status_code=400, detail=f"Champ manquant : {err}")
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Erreur pipeline : {err}")

    duree_ms = (time.perf_counter() - start) * 1000
    return {
        "endpoint": "/ingest",
        "version": "naive",
        "n_battements": len(beats),
        "duree_ms": round(duree_ms, 2),
        "resultats": results,
    }


# ======================================================================
#  /ingest_fast  — LA VERSION OPTIMISÉE
# ======================================================================
@router.post("/ingest_fast", tags=["Niveau avancé"])
def ingest_fast(payload: IngestPayload):
    """
    Même traitement, mais optimisé. Les 3 optimisations :

      ✅ CACHE : le modèle est chargé une seule fois puis gardé en mémoire.
      ✅ VECTORISATION : NumPy calcule les features de TOUS les battements
         d'un coup, et le modèle prédit sur tout le lot en un seul appel.
      ✅ INSERTION GROUPÉE (bulk insert) : une seule requête SQL pour tout
         le lot, au lieu d'une par battement.
    """
    start = time.perf_counter()
    beats = _extract_beats(payload)

    try:
        # ✅ RAPIDE #1 : modèle en cache (chargé au plus une fois).
        model = get_model_cached()

        pg.ensure_table()
        engine = pg.get_engine()

        # ✅ RAPIDE #2 : VECTORISATION.
        # On construit un seul tableau NumPy avec tous les battements, et on
        # calcule amp_range pour tous d'un coup (pas de boucle Python).
        arr = np.array(
            [[b["rr_prev"], b["rr_next"], b["amp_max"], b["amp_min"]] for b in beats],
            dtype=np.float64,
        )
        amp_range = arr[:, 2] - arr[:, 3]          # opération vectorisée
        features = np.column_stack([arr, amp_range])  # (n, 5)

        # Le modèle prédit sur TOUT le lot en UN SEUL appel (bien plus efficace
        # que n appels séparés : scikit-learn est optimisé pour les lots).
        features_df = pd.DataFrame(features, columns=FEATURE_COLS)
        predicted = model.predict(features_df).astype(int)
        proba = model.predict_proba(features_df)[:, 1]

        # ✅ RAPIDE #3 : INSERTION GROUPÉE.
        # Une seule requête, un seul aller-retour réseau, pour tout le lot.
        rows = [
            {
                "rr_prev": float(arr[i, 0]),
                "rr_next": float(arr[i, 1]),
                "amp_range": float(amp_range[i]),
                "predicted": int(predicted[i]),
                "proba": float(proba[i]),
            }
            for i in range(len(beats))
        ]
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO curated_beats
                    (source_type, record_id, rr_prev, rr_next, amp_range,
                     predicted, proba)
                VALUES ('ecg', 'api_ingest_fast', :rr_prev, :rr_next, :amp_range,
                        :predicted, :proba)
            """), rows)  # <- SQLAlchemy fait un executemany : 1 seul aller-retour

        results = [
            {"predicted": int(predicted[i]), "proba": round(float(proba[i]), 3)}
            for i in range(len(beats))
        ]

    except FileNotFoundError as err:
        raise HTTPException(status_code=503, detail=str(err))
    except KeyError as err:
        raise HTTPException(status_code=400, detail=f"Champ manquant : {err}")
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Erreur pipeline : {err}")

    duree_ms = (time.perf_counter() - start) * 1000
    return {
        "endpoint": "/ingest_fast",
        "version": "optimisee",
        "optimisations": [
            "modele en cache memoire",
            "vectorisation NumPy",
            "insertion SQL groupee (bulk)",
        ],
        "n_battements": len(beats),
        "duree_ms": round(duree_ms, 2),
        "resultats": results,
    }
