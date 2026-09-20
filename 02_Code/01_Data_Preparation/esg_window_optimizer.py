"""
esg_window_optimizer.py
=======================
Trouve la fenêtre temporelle [start_year, end_year] commune qui maximise
le nombre de tickers disposant à la fois de données ESG et de données de prix
sur toute la période.

Logique de couverture
---------------------
Un ticker est considéré "couvert" sur une fenêtre [S, E] si et seulement si :
    max(esg_first_year, price_start_year) <= S   (les données démarrent avant ou à S)
    price_end_year >= E                           (les données vont jusqu'à E au moins)
"""

import csv
from itertools import product


# ===========================================================================
# PARAMÈTRES — modifier ici avant de lancer (F5 dans VS Code)
# ===========================================================================

FILE        = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\00_Tickers\options_panel.csv"   # Chemin vers le fichier CSV (absolu ou relatif)
MIN_DURATION = 5                    # Durée minimale de la fenêtre en années
TOP_N        = 5                    # Nombre de fenêtres à afficher dans le classement
EXPORT       = ""                   # Chemin export CSV (laisser "" pour ne pas exporter)
                                    # Exemple : "results.csv" ou "C:/Users/toi/results.csv"

# ===========================================================================


# ---------------------------------------------------------------------------
# 1. Chargement et nettoyage des données
# ---------------------------------------------------------------------------

def load_tickers(filepath: str) -> list[dict]:
    """
    Charge le CSV et retourne la liste des tickers exploitables,
    c'est-à-dire ceux qui ont au moins esg_first_year, price_start_year
    et price_end_date renseignés.
    """
    tickers = []
    skipped = 0

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                esg_start   = int(row["esg_first_year"])
                price_start = int(row["price_start_year"])
                price_end   = int(row["price_end_date"][:4])
            except (ValueError, TypeError, KeyError):
                skipped += 1
                continue

            # La fenêtre de données complètes commence au plus tard des deux sources
            data_start = max(esg_start, price_start)
            data_end   = price_end

            if data_end <= data_start:
                skipped += 1
                continue

            tickers.append({
                "secid":       row.get("secid", ""),
                "ticker":      row.get("ticker", ""),
                "issuer":      row.get("issuer", ""),
                "esg_start":   esg_start,
                "price_start": price_start,
                "data_start":  data_start,   # max(esg, price_start)
                "data_end":    data_end,
            })

    print(f"  Tickers chargés    : {len(tickers)}")
    print(f"  Tickers ignorés    : {skipped}  (données manquantes ou incohérentes)")
    return tickers


# ---------------------------------------------------------------------------
# 2. Calcul de la couverture pour toutes les fenêtres possibles
# ---------------------------------------------------------------------------

def compute_all_windows(tickers: list[dict], min_duration: int = 1) -> list[dict]:
    """
    Pour chaque combinaison (start_year, end_year) avec end - start >= min_duration,
    calcule le nombre de tickers couverts.

    Retourne une liste de dicts triée par (count DESC, duration DESC).
    """
    # Plage d'années à explorer
    all_starts = sorted(set(t["data_start"] for t in tickers))
    all_ends   = sorted(set(t["data_end"]   for t in tickers))

    results = []

    for start, end in product(all_starts, all_ends):
        duration = end - start
        if duration < min_duration:
            continue

        count = sum(
            1 for t in tickers
            if t["data_start"] <= start and t["data_end"] >= end
        )

        if count == 0:
            continue

        results.append({
            "start_year":  start,
            "end_year":    end,
            "duration":    duration,
            "n_tickers":   count,
            "coverage_pct": round(count / len(tickers) * 100, 2),
        })

    results.sort(key=lambda r: (-r["n_tickers"], -r["duration"]))
    return results


# ---------------------------------------------------------------------------
# 3. Affichage des résultats
# ---------------------------------------------------------------------------

def print_results(results: list[dict], total: int, top_n: int = 5) -> None:
    """Affiche le tableau des meilleures fenêtres."""

    if not results:
        print("\n  Aucune fenêtre trouvée pour cette durée minimale.")
        return

    best = results[0]
    print(f"\n{'='*60}")
    print(f"  FENÊTRE OPTIMALE")
    print(f"{'='*60}")
    print(f"  Période        : {best['start_year']} – {best['end_year']}")
    print(f"  Durée          : {best['duration']} an(s)")
    print(f"  Tickers couverts: {best['n_tickers']} / {total}  ({best['coverage_pct']}%)")
    print(f"{'='*60}")

    print(f"\n  Top {top_n} fenêtres :")
    print(f"  {'Période':<16} {'Durée':>6}  {'Tickers':>8}  {'Couverture':>10}")
    print(f"  {'-'*46}")
    for r in results[:top_n]:
        period = f"{r['start_year']} – {r['end_year']}"
        print(
            f"  {period:<16} {r['duration']:>5}a  "
            f"{r['n_tickers']:>8}  {r['coverage_pct']:>9.1f}%"
        )


# ---------------------------------------------------------------------------
# 4. Export CSV optionnel
# ---------------------------------------------------------------------------

def export_results(results: list[dict], filepath: str) -> None:
    """Exporte tous les résultats dans un fichier CSV."""
    if not results:
        return
    fields = ["start_year", "end_year", "duration", "n_tickers", "coverage_pct"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Résultats exportés : {filepath}  ({len(results)} fenêtres)")


# ---------------------------------------------------------------------------
# 5. Point d'entrée
# ---------------------------------------------------------------------------

print(f"\nChargement : {FILE}")
tickers = load_tickers(FILE)

print(f"\nCalcul des fenêtres (durée minimale = {MIN_DURATION} an(s))...")
results = compute_all_windows(tickers, min_duration=MIN_DURATION)

print_results(results, total=len(tickers), top_n=TOP_N)

if EXPORT:
    export_results(results, EXPORT)

print()