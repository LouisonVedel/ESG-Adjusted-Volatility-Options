r"""
download_risk_free_rate.py

TÃ©lÃ©charge le taux sans risque US (10-Year Treasury Note, RIC
"US10YT=RR") depuis LSEG, sur la fenÃªtre convenue du panel (2010-2019).
Pas de marge de dates ici : contrairement Ã  l'ESG, un taux obligataire
cotÃ© en continu n'a aucun dÃ©calage de publication, donc aucune raison
d'Ã©largir la fenÃªtre.

Champ de rendement : plusieurs champs de yield sont demandÃ©s en cascade
(YLDTOMAT, puis MID_YLD_1, puis BID) â€” un fil de la communautÃ© LSEG
signale que le champ "Close Yield" est parfois vide sur les RIC
obligataires (bug cÃ´tÃ© plateforme, dÃ©jÃ  rencontrÃ© avec TR.EnvironmentPillarScore
sur l'ESG) ; YLDTOMAT (Yield To Maturity) est le plus directement
interprÃ©table comme taux sans risque annualisÃ©.

Sortie : un seul fichier (pas un par ticker, c'est une sÃ©rie macro unique)
US10Y_risk_free_rate.xlsx dans 01_Raw\RiskFree, colonnes Date,
yield_pct (ex: 2.45 = 2.45%) et yield_decimal (0.0245).

Usage : F5 dans VS Code. NÃ©cessite refinitiv-data et une session active.
"""

import logging
from pathlib import Path

import pandas as pd
import refinitiv.data as rd

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
RIC          = "US10YT=RR"
START_DATE   = "2010-01-01"
END_DATE     = "2019-06-28"
YIELD_FIELDS = ["YLDTOMAT", "MID_YLD_1", "BID"]   # cascade, dans cet ordre de prÃ©fÃ©rence

OUTPUT_DIR  = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\ThÃ¨se\Data\01_Raw\RiskFree")
OUTPUT_FILE = OUTPUT_DIR / "US10Y_risk_free_rate.xlsx"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=" * 74)
    log.info(f"  TÃ©lÃ©chargement {RIC}  ({START_DATE} â†’ {END_DATE})")
    log.info("=" * 74)

    rd.open_session()
    try:
        raw = rd.get_history(universe=RIC, fields=YIELD_FIELDS,
                              interval="1D", start=START_DATE, end=END_DATE)
    finally:
        rd.close_session()

    if raw is None or raw.empty:
        log.error("  âŒ  Aucune donnÃ©e reÃ§ue de LSEG â€” vÃ©rifier le RIC et l'entitlement.")
        return

    # get_history renvoie un MultiIndex de colonnes (RIC, champ) si un seul
    # RIC est demandÃ© avec plusieurs champs â€” on aplatit proprement.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(-1)

    present_fields = [f for f in YIELD_FIELDS if f in raw.columns]
    if not present_fields:
        log.error(f"  âŒ  Aucun des champs {YIELD_FIELDS} n'est prÃ©sent dans la rÃ©ponse "
                  f"(colonnes reÃ§ues : {list(raw.columns)})")
        return

    log.info(f"  ðŸ“ˆ  Champs reÃ§us : {present_fields}  (cascade de prÃ©fÃ©rence : {YIELD_FIELDS})")

    # Cascade ligne par ligne : premier champ non-null dans l'ordre de prÃ©fÃ©rence
    yield_pct = raw[present_fields[0]].copy()
    used_fallback = pd.Series(False, index=raw.index)
    for f in present_fields[1:]:
        mask = yield_pct.isna() & raw[f].notna()
        if mask.any():
            yield_pct[mask] = raw.loc[mask, f]
            used_fallback |= mask

    out = pd.DataFrame({
        "Date": raw.index,
        "yield_pct": yield_pct.values,
        "yield_decimal": (yield_pct / 100).values,
    }).dropna(subset=["yield_pct"]).reset_index(drop=True)

    n_fallback = int(used_fallback.sum())
    if n_fallback:
        log.info(f"  â†³  {n_fallback} date(s) complÃ©tÃ©e(s) via un champ de repli "
                 f"(le champ principal {present_fields[0]} Ã©tait vide ces jours-lÃ )")

    out.to_excel(OUTPUT_FILE, index=False)

    log.info("")
    log.info("  RAPPORT FINAL")
    log.info("=" * 74)
    log.info(f"  Lignes Ã©crites : {len(out)}")
    log.info(f"  PÃ©riode        : {out['Date'].min()} â†’ {out['Date'].max()}")
    log.info(f"  Fichier        : {OUTPUT_FILE}")
    log.info("=" * 74)


if __name__ == "__main__":
    main()
