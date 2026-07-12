"""
ecg.py — ÉTAPE 1 (2/3) : le processeur ECG
------------------------------------------
On remplit ici les 2 "trous" laissés par la classe SignalProcessor (base.py) :
  - load_raw()    : récupérer le signal brut depuis l'entrepôt et le lire
  - to_features() : transformer ce signal en un tableau de features exploitables

Rappel du principe : la méthode run() (qui enchaîne tout) est héritée de la
classe de base, on ne la réécrit PAS. On ne fournit que la partie spécifique à
l'ECG. Le jour où on fera l'EEG, on créera un EEGProcessor exactement sur le
même modèle.

Ce que sont les features ici : pour chaque battement cardiaque annoté, on
calcule quelques valeurs qui résument son rythme et sa forme, plus une étiquette
"normal / anormal". Ce tableau servira ensuite à entraîner un modèle (étape 3/3).
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb

from src.config import config
from src.storage.minio_client import download_file
from src.processors.base import SignalProcessor

# --- Étiquetage des battements (standard MIT-BIH) ---
# Chaque battement est annoté par un symbole. Ceux-ci correspondent à des
# battements NORMAUX (norme médicale AAMI). Tout autre symbole de battement est
# considéré comme anormal.
NORMAL_SYMBOLS = {"N", "L", "R", "e", "j"}

# Symboles qui ne sont PAS des battements (changement de rythme, bruit, etc.).
# On les ignore : ils n'ont pas de sens comme "battement à classer".
NON_BEAT_SYMBOLS = {"+", "~", "|", "!", "[", "]", '"', "x"}


class ECGProcessor(SignalProcessor):
    """Processeur spécialisé pour les signaux ECG du dataset MIT-BIH."""

    # Nom court de la source : sert à ranger les données et à tracer l'origine.
    source_type = "ecg"

    # Taille de la fenêtre (en secondes) autour d'un battement pour mesurer sa
    # "forme". 0.09 s de chaque côté couvre bien un complexe QRS.
    WINDOW_SECONDS = 0.09

    def load_raw(self, record_id: str):
        """
        Récupère les 3 fichiers de l'enregistrement depuis la zone raw de MinIO,
        puis les lit avec wfdb.

        Renvoie un dictionnaire contenant :
          - signal : le tracé ECG (tableau de nombres)
          - fs     : la fréquence d'échantillonnage (nb de points par seconde)
          - ann_samples : les positions (en points) de chaque battement
          - ann_symbols : le symbole (étiquette) de chaque battement
        """
        # Dossier temporaire local pour y déposer les fichiers le temps de les lire.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # On télécharge les 3 fichiers depuis MinIO (raw/ecg/...).
            for ext in (".dat", ".hea", ".atr"):
                object_name = f"ecg/{record_id}{ext}"
                local_path = tmp_dir / f"{record_id}{ext}"
                download_file(config.BUCKET_RAW, object_name, str(local_path))

            # wfdb lit l'enregistrement à partir du chemin SANS extension.
            record_path = str(tmp_dir / record_id)
            record = wfdb.rdrecord(record_path)      # le signal + ses infos
            annotation = wfdb.rdann(record_path, "atr")  # les annotations

            return {
                # On prend le 1er canal du signal (MIT-BIH en a 2, un suffit ici).
                "signal": record.p_signal[:, 0],
                "fs": record.fs,
                "ann_samples": annotation.sample,
                "ann_symbols": annotation.symbol,
            }

    def to_features(self, raw) -> pd.DataFrame:
        """
        Transforme le signal + ses annotations en un tableau : une ligne par
        battement, avec ses features et son étiquette normal/anormal.
        """
        signal = raw["signal"]
        fs = raw["fs"]
        samples = raw["ann_samples"]
        symbols = raw["ann_symbols"]

        # Nombre de points correspondant à notre fenêtre autour d'un battement.
        window = int(self.WINDOW_SECONDS * fs)

        rows = []
        for i, (pos, sym) in enumerate(zip(samples, symbols)):
            # On saute ce qui n'est pas un battement.
            if sym in NON_BEAT_SYMBOLS:
                continue

            # --- Features de RYTHME : distances au battement précédent/suivant ---
            # (converties en secondes pour être lisibles et indépendantes de fs)
            rr_prev = (pos - samples[i - 1]) / fs if i > 0 else np.nan
            rr_next = (samples[i + 1] - pos) / fs if i < len(samples) - 1 else np.nan

            # --- Features de FORME : amplitude du signal autour du battement ---
            start = max(0, pos - window)
            end = min(len(signal), pos + window)
            segment = signal[start:end]
            if len(segment) == 0:
                continue  # cas limite : battement tout au bord du signal

            amp_max = float(np.max(segment))
            amp_min = float(np.min(segment))

            rows.append({
                "beat_index": i,
                "position_sec": pos / fs,     # à quel instant se produit le battement
                "rr_prev": rr_prev,           # temps depuis le battement précédent
                "rr_next": rr_next,           # temps jusqu'au battement suivant
                "amp_max": amp_max,           # pic max autour du battement
                "amp_min": amp_min,           # creux min autour du battement
                "amp_range": amp_max - amp_min,  # amplitude totale
                "symbol": sym,                # l'étiquette brute du cardiologue
                # La cible à prédire : 0 = normal, 1 = anormal.
                "is_abnormal": 0 if sym in NORMAL_SYMBOLS else 1,
            })

        # On assemble tout dans un tableau pandas propre.
        return pd.DataFrame(rows)
