"""
base.py
-------
Le CŒUR de l'architecture : le "contrat commun" que tous les processeurs de
signal doivent respecter (ECG, EEG, et toute source future).

L'idée (très importante) :
  - La méthode `run()` décrit les ÉTAPES du pipeline (lire -> transformer ->
    ranger). Elle est écrite UNE SEULE FOIS ici et partagée par tous.
  - Les méthodes `load_raw()` et `to_features()` sont laissées VIDES ici
    (abstraites). Chaque domaine (ECG, EEG) les remplira à sa façon.

Résultat : ajouter un nouveau type de signal = créer une petite classe qui
hérite de SignalProcessor et remplit juste ces 2 trous. Rien d'autre à toucher.
C'est ça qui rend le data lake "extensible".
"""

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class SignalProcessor(ABC):
    """
    Modèle (template) commun à tous les processeurs de signal.

    `ABC` veut dire "Abstract Base Class" : une classe qu'on ne peut pas
    utiliser directement, seulement en créer des versions spécialisées.
    """

    # Chaque sous-classe donnera un nom court, ex: "ecg" ou "eeg".
    # Il servira à ranger les données dans les bons sous-dossiers.
    source_type: str = "base"

    # ------------------------------------------------------------------
    # Les 2 "trous" à remplir par chaque domaine (méthodes abstraites)
    # ------------------------------------------------------------------

    @abstractmethod
    def load_raw(self, record_id: str) -> Any:
        """
        Lit un enregistrement brut depuis la zone raw (MinIO) et le renvoie
        sous une forme exploitable (ex: un tableau de valeurs du signal).

        À implémenter dans ECGProcessor, EEGProcessor, etc.
        """
        ...

    @abstractmethod
    def to_features(self, raw_signal: Any) -> pd.DataFrame:
        """
        Transforme le signal brut en un tableau de "features" (les valeurs
        chiffrées utiles). Chaque domaine a sa propre recette :
          - ECG : détection des battements, intervalles R-R...
          - EEG : puissance par bande de fréquence, filtrage...

        Renvoie un tableau pandas (une ligne = un événement analysé).
        """
        ...

    # ------------------------------------------------------------------
    # La logique PARTAGÉE : écrite une fois, valable pour tous
    # ------------------------------------------------------------------

    def run(self, record_id: str) -> pd.DataFrame:
        """
        Enchaîne les étapes du pipeline pour un enregistrement donné.
        C'est ici que se joue la "chaîne de montage" commune.
        """
        print(f"[{self.source_type}] traitement de '{record_id}'...")

        # Étape 1 : lire le signal brut (méthode spécifique au domaine)
        raw_signal = self.load_raw(record_id)

        # Étape 2 : extraire les features (méthode spécifique au domaine)
        features = self.to_features(raw_signal)

        # On ajoute des colonnes communes à toutes les sources, pour savoir
        # d'où vient chaque ligne une fois rangée dans la base curated.
        features["source_type"] = self.source_type
        features["record_id"] = record_id

        print(f"[{self.source_type}] {len(features)} lignes de features extraites.")
        return features
