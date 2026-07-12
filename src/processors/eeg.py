"""
eeg.py — le processeur EEG (détection de crises d'épilepsie)
-------------------------------------------------------------
👉 TROISIÈME domaine branché sur la MÊME infrastructure.

Regarde encore une fois : cette classe hérite du même SignalProcessor, remplit
les mêmes 2 trous (load_raw / to_features), et ne demande AUCUNE modification
du stockage, de la base, de l'API ou d'Airflow.

Pourtant, le traitement du signal n'a rien à voir avec l'ECG :

  ECG                                EEG
  ---                                ---
  1 canal                            23 canaux (23 électrodes)
  360 Hz                             256 Hz
  on découpe par BATTEMENT           on découpe en FENÊTRES de 5 secondes
  features = rythme + amplitude      features = puissance par bande de fréquence
  ~1 à 30 % d'anomalies              ~1 à 2 % de crises (bien pire !)


=== LES BANDES DE FRÉQUENCE (le concept clé de l'EEG) ===

Le cerveau produit des ondes électriques à différentes fréquences. Les
neurologues les regroupent en 5 bandes, chacune associée à un état mental :

  Delta (0.5–4 Hz)   : sommeil profond
  Theta (4–8 Hz)     : somnolence, méditation
  Alpha (8–13 Hz)    : éveil calme, yeux fermés
  Beta  (13–30 Hz)   : concentration, activité mentale
  Gamma (30–45 Hz)   : traitement cognitif intense

Pendant une CRISE D'ÉPILEPSIE, les neurones se déchargent de façon synchrone et
anormale. Ça se traduit par un changement brutal de la répartition d'énergie
entre ces bandes. C'est donc exactement ce qu'on va mesurer pour chaque fenêtre
de 5 secondes : combien d'énergie dans chaque bande ?

C'est ça, notre "feature engineering" pour l'EEG.
"""

import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from minio.error import S3Error
from scipy import signal as sp_signal

from src.config import config
from src.storage.minio_client import get_client
from src.processors.base import SignalProcessor

# Les 5 bandes de fréquence cérébrales (nom -> (fréquence min, fréquence max)).
BANDES = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta": (13, 30),
    "gamma": (30, 45),
}

SUMMARY_FILE = "chb01-summary.txt"


class EEGProcessor(SignalProcessor):
    """Processeur pour les signaux EEG du dataset CHB-MIT (crises d'épilepsie)."""

    source_type = "eeg"

    # On découpe le signal en fenêtres de 5 secondes.
    # Pourquoi 5 s ? Assez long pour estimer un spectre de fréquences fiable,
    # assez court pour localiser précisément une crise (qui dure ~40-90 s).
    FENETRE_SECONDES = 5.0

    def load_raw(self, record_id: str) -> dict:
        """
        Récupère le fichier EEG (.edf) et les annotations depuis la zone raw,
        puis les lit.

        Renvoie :
          - signal   : tableau (n_canaux, n_points)
          - fs       : fréquence d'échantillonnage (256 Hz)
          - crises   : liste des intervalles de crise [(début_s, fin_s), ...]
        """
        # On importe MNE ici (et pas en haut) car c'est une grosse librairie :
        # inutile de la charger si on ne traite pas d'EEG.
        import mne

        client = get_client()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # --- 1. Le fichier EEG ---
            edf_local = tmp_dir / f"{record_id}.edf"
            try:
                client.fget_object(
                    config.BUCKET_RAW, f"eeg/{record_id}.edf", str(edf_local)
                )
            except S3Error as err:
                raise RuntimeError(
                    f"Fichier EEG introuvable dans raw : {record_id}.edf ({err.code}). "
                    "As-tu lancé : python -m src.ingestion.ingest_eeg ?"
                )

            # --- 2. Les annotations (horaires des crises) ---
            summary_local = tmp_dir / SUMMARY_FILE
            try:
                client.fget_object(
                    config.BUCKET_RAW, f"eeg/{SUMMARY_FILE}", str(summary_local)
                )
            except S3Error as err:
                raise RuntimeError(f"Annotations introuvables ({err.code}).")

            crises = self._parser_crises(summary_local.read_text(), record_id)

            # --- 3. Lecture du signal avec MNE-Python ---
            # (verbose="ERROR" pour ne pas noyer le terminal de messages)
            raw = mne.io.read_raw_edf(str(edf_local), preload=True, verbose="ERROR")

            # FILTRAGE PASSE-BANDE (0.5–45 Hz) : on garde uniquement les
            # fréquences qui nous intéressent. Ça élimine :
            #   - la dérive lente du signal (< 0.5 Hz, due aux électrodes)
            #   - le bruit du secteur électrique et les artefacts (> 45 Hz)
            raw.filter(0.5, 45.0, verbose="ERROR")

            return {
                "signal": raw.get_data(),        # (n_canaux, n_points)
                "fs": raw.info["sfreq"],         # 256 Hz
                "crises": crises,
                "record_id": record_id,
            }

    @staticmethod
    def _parser_crises(texte_summary: str, record_id: str) -> list[tuple[float, float]]:
        """
        Extrait les horaires de crise d'un fichier chbNN-summary.txt.

        Le fichier ressemble à ça :
            File Name: chb01_03.edf
            Number of Seizures in File: 1
            Seizure Start Time: 2996 seconds
            Seizure End Time: 3036 seconds

        On cherche le bloc correspondant à notre enregistrement, et on en tire
        les intervalles (début, fin) en secondes.
        """
        crises = []
        # On isole le bloc de texte qui concerne notre fichier.
        lignes = texte_summary.splitlines()
        dans_le_bon_bloc = False

        for ligne in lignes:
            if ligne.startswith("File Name:"):
                # Un nouveau bloc commence : est-ce le nôtre ?
                dans_le_bon_bloc = f"{record_id}.edf" in ligne
                continue

            if not dans_le_bon_bloc:
                continue

            # On récupère les temps de début et de fin.
            debut = re.search(r"Seizure.*Start Time:\s*(\d+)\s*seconds", ligne)
            if debut:
                crises.append([float(debut.group(1)), None])
                continue

            fin = re.search(r"Seizure.*End Time:\s*(\d+)\s*seconds", ligne)
            if fin and crises and crises[-1][1] is None:
                crises[-1][1] = float(fin.group(1))

        # On ne garde que les intervalles complets.
        resultat = [(d, f) for d, f in crises if f is not None]

        if resultat:
            duree_totale = sum(f - d for d, f in resultat)
            print(f"[eeg] {record_id} : {len(resultat)} crise(s), "
                  f"{duree_totale:.0f} s au total.")
        else:
            print(f"[eeg] {record_id} : aucune crise annotée.")

        return resultat

    def to_features(self, raw: dict) -> pd.DataFrame:
        """
        Découpe le signal en fenêtres de 5 s et calcule, pour chacune, la
        puissance dans chaque bande de fréquence.

        Une ligne du tableau final = une fenêtre de 5 secondes, avec :
          - la puissance moyenne dans les 5 bandes (delta, theta, alpha, beta, gamma)
          - l'écart-type du signal (mesure simple de l'amplitude)
          - l'étiquette : cette fenêtre tombe-t-elle pendant une crise ?
        """
        signal = raw["signal"]     # (n_canaux, n_points)
        fs = raw["fs"]
        crises = raw["crises"]

        n_canaux, n_points = signal.shape
        taille_fenetre = int(self.FENETRE_SECONDES * fs)
        n_fenetres = n_points // taille_fenetre

        print(f"[eeg] {n_canaux} canaux, {n_points/fs:.0f} s de signal "
              f"-> {n_fenetres} fenêtres de {self.FENETRE_SECONDES:.0f} s.")

        lignes = []
        for i in range(n_fenetres):
            debut_pt = i * taille_fenetre
            fin_pt = debut_pt + taille_fenetre
            fenetre = signal[:, debut_pt:fin_pt]   # (n_canaux, taille_fenetre)

            # Les instants (en secondes) couverts par cette fenêtre.
            debut_s = debut_pt / fs
            fin_s = fin_pt / fs

            # --- CALCUL DU SPECTRE (méthode de Welch) ---
            # Welch estime comment l'énergie du signal se répartit selon la
            # fréquence. On l'applique à chaque canal, puis on moyenne.
            freqs, psd = sp_signal.welch(
                fenetre, fs=fs, nperseg=min(256, taille_fenetre), axis=-1
            )
            psd_moyenne = psd.mean(axis=0)   # moyenne sur les 23 canaux

            # --- PUISSANCE PAR BANDE ---
            ligne = {
                "fenetre_index": i,
                "debut_sec": debut_s,
                "fin_sec": fin_s,
            }
            puissance_totale = 0.0
            for nom, (f_min, f_max) in BANDES.items():
                # On somme l'énergie des fréquences comprises dans la bande.
                # (On utilise np.sum plutôt que np.trapz, qui a été supprimé
                #  dans NumPy 2.x — un piège de compatibilité classique.)
                masque = (freqs >= f_min) & (freqs < f_max)
                puissance = float(np.sum(psd_moyenne[masque]))
                ligne[f"puissance_{nom}"] = puissance
                puissance_totale += puissance

            # Amplitude globale du signal sur la fenêtre.
            ligne["amplitude_std"] = float(np.std(fenetre))

            # Puissances RELATIVES : quelle PART de l'énergie totale va dans
            # chaque bande ? Souvent plus informatif que la valeur brute, car
            # ça normalise les différences d'amplitude entre patients.
            for nom in BANDES:
                if puissance_totale > 0:
                    ligne[f"ratio_{nom}"] = ligne[f"puissance_{nom}"] / puissance_totale
                else:
                    ligne[f"ratio_{nom}"] = 0.0

            # --- L'ÉTIQUETTE : cette fenêtre est-elle une crise ? ---
            # On dit "oui" si la fenêtre chevauche un intervalle de crise.
            est_crise = any(
                debut_s < fin_crise and fin_s > debut_crise
                for debut_crise, fin_crise in crises
            )
            ligne["is_seizure"] = 1 if est_crise else 0

            lignes.append(ligne)

        df = pd.DataFrame(lignes)

        if not df.empty:
            n_crises = int(df["is_seizure"].sum())
            pct = n_crises / len(df) * 100
            print(f"[eeg] {len(df)} fenêtres, dont {n_crises} en crise "
                  f"({pct:.1f} %) -> déséquilibre TRÈS marqué.")

        return df
