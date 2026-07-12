"""
benchmark.py — NIVEAU AVANCÉ : la mesure des performances
---------------------------------------------------------
Le sujet demande de chronométrer et documenter le temps d'exécution du pipeline
pour un batch de 1 élément et un batch de 100, puis de comparer /ingest et
/ingest_fast (qui doit être au moins 30 % plus rapide).

Ce script fait la mesure proprement :
  - il lance plusieurs essais et prend la MOYENNE (une mesure unique n'est pas
    fiable : la machine a des à-coups),
  - il fait quelques appels "à blanc" (warm-up) avant de mesurer, pour ne pas
    fausser les résultats avec les coûts de démarrage,
  - il affiche un tableau récapitulatif prêt à recopier dans le rapport.

⚠️ L'API doit tourner AVANT de lancer ce script :
    Terminal 1 :  uvicorn src.api.main:app
    Terminal 2 :  python -m src.api.benchmark
"""

import statistics
import time

import httpx

API_URL = "http://localhost:8000"

# Nombre d'essais par mesure. Plus il y en a, plus la moyenne est fiable.
N_ESSAIS = 5

# Nombre d'appels "à blanc" avant de commencer à mesurer (warm-up).
N_WARMUP = 2


def make_beats(n: int) -> dict:
    """Fabrique un lot de n battements de test (valeurs réalistes)."""
    return {
        "data": {
            "beats": [
                {
                    "rr_prev": 0.80 + (i % 5) * 0.01,
                    "rr_next": 0.79 + (i % 3) * 0.01,
                    "amp_max": 1.20 + (i % 4) * 0.05,
                    "amp_min": -0.30 - (i % 3) * 0.02,
                }
                for i in range(n)
            ]
        }
    }


def mesurer(endpoint: str, n_beats: int) -> float:
    """
    Appelle un endpoint N_ESSAIS fois et renvoie la durée MOYENNE (en ms).
    """
    payload = make_beats(n_beats)
    url = f"{API_URL}{endpoint}"

    with httpx.Client(timeout=120.0) as client:
        # Warm-up : on jette ces appels, ils servent juste à "chauffer".
        for _ in range(N_WARMUP):
            client.post(url, json=payload)

        # Les vraies mesures.
        durees = []
        for _ in range(N_ESSAIS):
            debut = time.perf_counter()
            reponse = client.post(url, json=payload)
            duree_ms = (time.perf_counter() - debut) * 1000

            if reponse.status_code != 200:
                raise RuntimeError(
                    f"{endpoint} a renvoyé {reponse.status_code} : {reponse.text[:200]}"
                )
            durees.append(duree_ms)

    return statistics.mean(durees)


def main() -> None:
    print("=" * 70)
    print("BENCHMARK : /ingest  vs  /ingest_fast")
    print("=" * 70)
    print(f"Méthode : moyenne sur {N_ESSAIS} essais, après {N_WARMUP} appels de warm-up.\n")

    # On vérifie d'abord que l'API répond.
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{API_URL}/health")
            r.raise_for_status()
    except Exception as err:
        print("❌ L'API ne répond pas. Lance-la d'abord dans un autre terminal :")
        print("     uvicorn src.api.main:app")
        print(f"   (détail : {err})")
        return

    resultats = []
    for taille in (1, 100):
        print(f"--- Batch de {taille} élément(s) ---")

        t_naif = mesurer("/ingest", taille)
        print(f"  /ingest      : {t_naif:8.2f} ms")

        t_fast = mesurer("/ingest_fast", taille)
        print(f"  /ingest_fast : {t_fast:8.2f} ms")

        # Le gain : de combien de % on a réduit le temps.
        gain = (t_naif - t_fast) / t_naif * 100 if t_naif > 0 else 0
        # Le facteur d'accélération (ex: "3.2x plus rapide").
        acceleration = t_naif / t_fast if t_fast > 0 else float("inf")

        statut = "✅ objectif 30 % atteint" if gain >= 30 else "⚠️  sous les 30 %"
        print(f"  GAIN         : {gain:6.1f} %  ({acceleration:.1f}x plus rapide)  {statut}\n")

        resultats.append({
            "taille": taille, "naif": t_naif, "fast": t_fast,
            "gain": gain, "acceleration": acceleration,
        })

    # Tableau final, prêt à recopier dans le rapport.
    print("=" * 70)
    print("TABLEAU RÉCAPITULATIF (à recopier dans le rapport, section 6.3)")
    print("=" * 70)
    print(f"{'Taille du batch':<18}{'/ingest (ms)':>15}{'/ingest_fast (ms)':>20}{'Gain':>10}")
    print("-" * 70)
    for r in resultats:
        print(f"{str(r['taille']) + ' élément(s)':<18}"
              f"{r['naif']:>15.2f}{r['fast']:>20.2f}{r['gain']:>9.1f} %")
    print("=" * 70)


if __name__ == "__main__":
    main()
