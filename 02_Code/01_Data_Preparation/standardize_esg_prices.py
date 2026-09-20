"""
standardize_esg_prices.py

Structure des fichiers (constatée sur CDNS_102602_esg.xlsx /
CDNS_102602_prices_daily.xlsx) :

  ESG    : colonnes [Year, ticker, secid, issuer, ESG_Score, S_Pillar, G_Pillar]
           1 ligne par année, "Year" est un entier (pas une date à parser).
  Prix   : colonnes [Date, Open, High, Low, Close, Volume], 1 ligne par jour.
  Nommage: {TICKER}_{SECID}_esg.xlsx  et  {TICKER}_{SECID}_prices_daily.xlsx
           → le préfixe "{TICKER}_{SECID}" est la clé commune entre les
           deux dossiers, utilisée pour faire correspondre ESG et Prix.

Objectif
--------
Produire un jeu de données final où 02_Processed\\ESG et 02_Processed\\Prices
contiennent EXACTEMENT le même ensemble de tickers (donc le même nombre de
fichiers), en alignant les deux sens :

1. ESG : ne garder que les lignes Year in [2017, 2023]. Si une année en trop
   existe (avant 2017 ou après 2023), la ligne est retirée automatiquement
   par ce filtre. Si, après filtrage, il manque une ou plusieurs années dans
   la fenêtre, le ticker est marqué "esg_incomplete".
2. Prix : contrôle du nombre de lignes (1760 attendu). Si différent ou vide,
   le ticker est marqué "price_invalid".
3. [NOUVEAU] Un ticker n'est écrit dans les dossiers Processed QUE si les
   DEUX côtés sont valides (ESG complet ET Prix conforme). Un ticker valide
   d'un seul côté n'est plus recopié — auparavant seul le sens ESG→Prix
   était géré (prix exclu si ESG invalide), pas l'inverse (ESG valide mais
   prix invalide restait tout de même copié). C'est cette dissymétrie qui
   pouvait produire un nombre de fichiers différent entre les deux dossiers
   Processed. Désormais les fichiers Prix validés sont copiés dans
   02_Processed\\Prices, en miroir exact de 02_Processed\\ESG.
4. Rien n'est jamais supprimé : les fichiers Prix exclus sont déplacés de
   01_Raw\\Prices vers 01_Raw\\Prices\\_exclus_alignement (remplace l'ancien
   _exclus_esg_incomplet, renommé pour refléter les deux sens d'exclusion
   possibles). Les fichiers ESG bruts ne sont jamais déplacés — un ESG
   incomplet ou orphelin reste visible tel quel dans 01_Raw\\ESG pour
   inspection manuelle.

Usage : ouvrir dans VS Code et lancer avec F5. Dépendances : pandas, openpyxl.
"""

import shutil
import logging
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
RAW_ESG_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\ESG")
RAW_PRICES_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\Prices")
PROCESSED_ESG_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\ESG")
PROCESSED_PRICES_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Prices")
EXCLUDED_PRICES_DIR = RAW_PRICES_DIR / "_exclus_alignement"

ESG_SUFFIX = "_esg.xlsx"
PRICE_SUFFIX = "_prices_daily.xlsx"

YEAR_START = 2016
YEAR_END = 2022
EXPECTED_YEARS = YEAR_END - YEAR_START + 1  # 7
EXPECTED_PRICE_ROWS = 1760

YEAR_COLUMN_CANDIDATES = ["Year", "year", "periodenddate", "PeriodEndDate", "Date", "date"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def find_year_column(df: pd.DataFrame) -> str:
    for c in YEAR_COLUMN_CANDIDATES:
        if c in df.columns:
            return c
    for c in df.columns:
        cl = c.lower()
        if "year" in cl or "date" in cl or "period" in cl:
            return c
    raise ValueError("aucune colonne d'année/date trouvée")


def file_key(path: Path, suffix: str) -> str:
    """Extrait la clé '{TICKER}_{SECID}' à partir du nom de fichier."""
    name = path.name
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return path.stem


def build_esg_frame(path: Path) -> tuple[pd.DataFrame | None, str]:
    """Filtre un fichier ESG sur 2017-2023 sans rien écrire sur disque.
    Retourne (df_standardisé_ou_None, message)."""
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return None, f"lecture_impossible ({e})"

    if df.empty:
        return None, "esg_empty"

    try:
        year_col = find_year_column(df)
    except ValueError as e:
        return None, str(e)

    if pd.api.types.is_datetime64_any_dtype(df[year_col]):
        years = df[year_col].dt.year
    else:
        years = pd.to_numeric(df[year_col], errors="coerce")
        if years.isna().all():
            years = pd.to_datetime(df[year_col], errors="coerce").dt.year

    df = df.assign(_year=years).dropna(subset=["_year"])
    df["_year"] = df["_year"].astype(int)
    df = df[(df["_year"] >= YEAR_START) & (df["_year"] <= YEAR_END)]

    df = df.drop_duplicates(subset="_year", keep="last").sort_values("_year")

    years_present = sorted(df["_year"].unique().tolist())

    if len(years_present) < EXPECTED_YEARS:
        missing = sorted(set(range(YEAR_START, YEAR_END + 1)) - set(years_present))
        return None, f"esg_incomplete {missing}"

    df = df.drop(columns="_year")
    return df, "ok"


def check_price_file(path: Path) -> str:
    """Contrôle uniquement (aucune modification ni déplacement). Retourne un message."""
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return f"lecture_impossible ({e})"

    if df.empty:
        return "daily_empty"

    n = len(df)
    if n != EXPECTED_PRICE_ROWS:
        return f"lignes_inattendues ({n}/{EXPECTED_PRICE_ROWS})"

    return "ok"


def main():
    esg_files = sorted(RAW_ESG_DIR.glob(f"*{ESG_SUFFIX}"))
    price_files = sorted(RAW_PRICES_DIR.glob(f"*{PRICE_SUFFIX}"))

    log.info("=" * 74)
    log.info(f"  {len(esg_files)} fichiers ESG et {len(price_files)} fichiers Prix détectés")
    log.info("=" * 74)

    # --- Phase 1 : analyse pure, rien n'est écrit ni déplacé encore ---------
    esg_status: dict[str, tuple[pd.DataFrame | None, str]] = {}
    for f in esg_files:
        key = file_key(f, ESG_SUFFIX)
        esg_status[key] = build_esg_frame(f)

    price_status: dict[str, str] = {}
    price_paths: dict[str, Path] = {}
    for f in price_files:
        key = file_key(f, PRICE_SUFFIX)
        price_status[key] = check_price_file(f)
        price_paths[key] = f

    esg_keys = set(esg_status)
    price_keys = set(price_status)
    all_keys = esg_keys | price_keys

    # --- Phase 2 : décision d'alignement, ticker par ticker -----------------
    valid_keys, excluded = [], []  # excluded: list[(key, reason)]
    for key in sorted(all_keys):
        esg_df, esg_msg = esg_status.get(key, (None, "fichier_esg_absent"))
        price_msg = price_status.get(key, "fichier_prix_absent")

        esg_ok = esg_df is not None
        price_ok = (price_msg == "ok")

        if esg_ok and price_ok:
            valid_keys.append(key)
        elif esg_ok and not price_ok:
            excluded.append((key, f"esg_ok_mais_prix_invalide [{price_msg}]"))
        elif price_ok and not esg_ok:
            excluded.append((key, f"prix_ok_mais_{esg_msg}"))
        else:
            excluded.append((key, f"{esg_msg} ET prix:{price_msg}"))

    # --- Phase 3 : écriture — uniquement pour l'intersection valide ---------
    # [FIX] 02_Processed est un dossier dérivé, reconstruit à chaque run à
    # partir de 01_Raw — pas un dossier auquel on ajoute. Sans purge, un
    # fichier écrit par un run précédent (avec une logique différente, ou
    # pour un ticker désormais invalide) reste sur disque indéfiniment et
    # désynchronise à nouveau les deux dossiers Processed, exactement le
    # problème que Phase 3 est censée éviter.
    PROCESSED_ESG_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_PRICES_DIR.mkdir(parents=True, exist_ok=True)

    valid_keys_set = set(valid_keys)
    stale_esg = [f for f in PROCESSED_ESG_DIR.glob(f"*{ESG_SUFFIX}")
                 if file_key(f, ESG_SUFFIX) not in valid_keys_set]
    stale_price = [f for f in PROCESSED_PRICES_DIR.glob(f"*{PRICE_SUFFIX}")
                   if file_key(f, PRICE_SUFFIX) not in valid_keys_set]
    for f in stale_esg + stale_price:
        f.unlink()
    if stale_esg or stale_price:
        log.info(f"  🧹  Purge Processed (run précédent) : {len(stale_esg)} ESG + "
                 f"{len(stale_price)} Prix retirés avant réécriture")

    for key in valid_keys:
        esg_df, _ = esg_status[key]
        esg_df.to_excel(PROCESSED_ESG_DIR / f"{key}{ESG_SUFFIX}", index=False)
        shutil.copy2(price_paths[key], PROCESSED_PRICES_DIR / f"{key}{PRICE_SUFFIX}")

    # --- Phase 4 : déplacement (non destructif) des prix bruts écartés ------
    moved = []
    excluded_keys = {k for k, _ in excluded}
    if excluded_keys:
        EXCLUDED_PRICES_DIR.mkdir(parents=True, exist_ok=True)
        for key in excluded_keys:
            src = price_paths.get(key)
            if src is not None and src.exists():
                shutil.move(str(src), str(EXCLUDED_PRICES_DIR / src.name))
                moved.append(key)

    # --- Rapport final --------------------------------------------------------
    log.info("")
    log.info("  RAPPORT FINAL")
    log.info("=" * 74)
    log.info(f"  Tickers alignés (ESG complet ET Prix conforme) : {len(valid_keys)}")
    log.info(f"  02_Processed\\ESG    : {len(list(PROCESSED_ESG_DIR.glob(f'*{ESG_SUFFIX}')))} fichiers")
    log.info(f"  02_Processed\\Prices : {len(list(PROCESSED_PRICES_DIR.glob(f'*{PRICE_SUFFIX}')))} fichiers")
    log.info(f"  Tickers écartés : {len(excluded)}")
    log.info(f"  Fichiers Prix bruts déplacés vers _exclus_alignement : {len(moved)}")
    if excluded:
        log.info("")
        log.info("  Détail des tickers écartés :")
        for k, msg in sorted(excluded):
            log.info(f"    - {k:<16} [{msg}]")
    log.info("=" * 74)

    n_esg = len(list(PROCESSED_ESG_DIR.glob(f"*{ESG_SUFFIX}")))
    n_px = len(list(PROCESSED_PRICES_DIR.glob(f"*{PRICE_SUFFIX}")))
    if n_esg == n_px:
        log.info(f"  ✅  Alignement confirmé : {n_esg} fichiers de chaque côté.")
    else:
        log.warning(f"  ⚠️  Décompte différent après écriture ({n_esg} ESG vs {n_px} Prix) "
                    f"— ne devrait pas arriver, vérifier les doublons de clé.")


if __name__ == "__main__":
    main()