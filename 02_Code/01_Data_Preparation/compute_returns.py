r"""
compute_returns.py

Calcule les rendements journaliers (simples et logarithmiques) à partir des
323 fichiers Prix déjà standardisés dans 02_Processed\Prices, et écrit un
fichier par ticker dans 02_Processed\Prices\Returns — même principe que
les étapes précédentes (ESG, Prix, Options) : une base par ticker.

Pour chaque fichier {TICKER}_{SECID}_prices_daily.xlsx (colonnes Date,
Open, High, Low, Close, Volume), calcule à partir de Close, trié par date :
  - simple_return = (Close_t / Close_{t-1}) - 1
  - log_return    = ln(Close_t / Close_{t-1})
La première ligne (pas de rendement calculable) est retirée — 1760 lignes
de prix donnent donc 1759 lignes de rendements.

Sortie : {TICKER}_{SECID}_returns.xlsx dans Prices\Returns, colonnes
Date, Close, simple_return, log_return.

[Alignement] Comme pour ESG/Prix/Options, le dossier Returns est reconstruit
à chaque run à partir de ce qui existe RÉELLEMENT dans Prices — tout fichier
Returns dont le ticker n'a plus de fichier Prix correspondant est retiré,
pour ne jamais accumuler de doublons stale d'un run précédent.

Usage : F5 dans VS Code. Dépendances : pandas, openpyxl (déjà présentes).
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
PRICES_DIR  = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Prices")
RETURNS_DIR = PRICES_DIR / "Returns"

PRICE_SUFFIX   = "_prices_daily.xlsx"
RETURNS_SUFFIX = "_returns.xlsx"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def file_key(path: Path, suffix: str) -> str:
    name = path.name
    return name[: -len(suffix)] if name.endswith(suffix) else path.stem


def compute_returns(path: Path) -> pd.DataFrame | None:
    df = pd.read_excel(path)
    if df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    out = pd.DataFrame()
    out["Date"] = df["Date"]
    out["Close"] = df["Close"]
    out["simple_return"] = df["Close"].pct_change()
    out["log_return"] = np.log(df["Close"] / df["Close"].shift(1))

    out = out.iloc[1:].reset_index(drop=True)  # première ligne sans rendement
    return out if not out.empty else None


def main():
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)

    price_files = sorted(PRICES_DIR.glob(f"*{PRICE_SUFFIX}"))
    valid_keys = {file_key(f, PRICE_SUFFIX) for f in price_files}

    log.info("=" * 74)
    log.info(f"  {len(price_files)} fichiers Prix détectés dans 02_Processed\\Prices")
    log.info("=" * 74)

    # ── Purge des fichiers Returns dont le Prix source n'existe plus ────────
    existing = list(RETURNS_DIR.glob(f"*{RETURNS_SUFFIX}"))
    stale = [f for f in existing if file_key(f, RETURNS_SUFFIX) not in valid_keys]
    if stale:
        log.info(f"  🧹  {len(stale)} fichier(s) Returns orphelin(s) retiré(s) :")
        for f in stale:
            log.info(f"      - {f.name}")
            f.unlink()
        log.info("")

    ok, failed = [], []
    for f in price_files:
        key = file_key(f, PRICE_SUFFIX)
        try:
            out = compute_returns(f)
        except Exception as e:
            failed.append((key, str(e)))
            continue
        if out is None:
            failed.append((key, "fichier_prix_illisible_ou_incomplet"))
            continue
        out.to_excel(RETURNS_DIR / f"{key}{RETURNS_SUFFIX}", index=False)
        ok.append(key)

    log.info("")
    log.info("  RAPPORT FINAL")
    log.info("=" * 74)
    log.info(f"  Fichiers Returns créés : {len(ok)}/{len(price_files)}")
    if failed:
        log.warning(f"  ⚠️  {len(failed)} échec(s) :")
        for key, msg in failed:
            log.warning(f"      - {key:<20} [{msg}]")
    n_final = len(list(RETURNS_DIR.glob(f"*{RETURNS_SUFFIX}")))
    if n_final == len(price_files):
        log.info(f"  ✅  Alignement confirmé : {n_final} fichiers Returns == {len(price_files)} fichiers Prix.")
    else:
        log.warning(f"  ⚠️  Décompte différent ({n_final} Returns vs {len(price_files)} Prix).")
    log.info("=" * 74)


if __name__ == "__main__":
    main()
