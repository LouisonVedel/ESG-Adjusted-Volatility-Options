r"""
remove_incomplete_esg_tickers.py

Retire définitivement les tickers dont le scoring ESG (E_Pillar) est
resté incomplet après vérification et nouvelle tentative via LSEG. 
Pas d'interpolation, pas de donnée inventée : ces tickers
sortent purement et simplement de la base de travail.

Supprime les fichiers correspondants dans les trois dossiers alignés :
  - 02_Processed\ESG           {TICKER}_{SECID}_esg.xlsx
  - 02_Processed\Prices        {TICKER}_{SECID}_prices_daily.xlsx
  - 02_Processed\Prices\Returns {TICKER}_{SECID}_returns.xlsx

Nouvelle base de travail après ce script : 323 - 5 = 318 tickers.

Usage : F5 dans VS Code.
"""

from pathlib import Path

ESG_DIR     = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\ESG")
PRICES_DIR  = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Prices")
RETURNS_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Prices\Returns")
OPTIONS_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Options_Clean")

# Tickers à exclure, identifiés par leur clé exacte {TICKER}_{SECID}
# (confirmés via check_e_pillar.py : E_Pillar partiel malgré retry LSEG)
TICKERS_TO_REMOVE = [
    "CI_102525",
    "KHC_207608",
    "PPL_108649",
    "SPG_110188",
    "STT_110490",
    "UAA_125183",
    "WAT_111902",
]

def main():
    targets = [
        (ESG_DIR,     "_esg.xlsx"),
        (PRICES_DIR,  "_prices_daily.xlsx"),
        (RETURNS_DIR, "_returns.xlsx"),
        (OPTIONS_DIR, "_options.csv")
    ]

    print(f"Suppression de {len(TICKERS_TO_REMOVE)} tickers (ESG E_Pillar incomplet) :")
    print(f"  {TICKERS_TO_REMOVE}\n")

    removed, missing = [], []

    for key in TICKERS_TO_REMOVE:
        for folder, suffix in targets:
            path = folder / f"{key}{suffix}"
            if path.exists():
                path.unlink()
                removed.append(str(path))
            else:
                missing.append(str(path))

    print(f"✅  {len(removed)} fichier(s) supprimé(s) :")
    for p in removed:
        print(f"    - {p}")

    if missing:
        print(f"\n⚠️  {len(missing)} fichier(s) attendu(s) mais introuvable(s) (déjà absents ?) :")
        for p in missing:
            print(f"    - {p}")

    n_esg     = len(list(ESG_DIR.glob("*_esg.xlsx")))
    n_prices  = len(list(PRICES_DIR.glob("*_prices_daily.xlsx")))
    n_returns = len(list(RETURNS_DIR.glob("*_returns.xlsx")))
    n_options = len(list(OPTIONS_DIR.glob('*_options.csv')))

    print(f"\nRESTANT :")
    print(f"  ESG     : {n_esg}")
    print(f"  Prices  : {n_prices}")
    print(f"  Returns : {n_returns}")
    print(f"  Options : {n_options}")

    if n_esg == n_prices == n_returns:
        print(f"\n✅  Base de travail alignée : {n_esg} tickers.")
    else:
        print(f"\n⚠️  Décompte différent entre les trois dossiers — à vérifier.")


if __name__ == "__main__":
    main()
