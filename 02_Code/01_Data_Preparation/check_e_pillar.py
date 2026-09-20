r"""
check_e_pillar.py

Contrôle en lecture seule : parcourt les 323 fichiers de 02_Processed\ESG
et signale tout fichier où E_Pillar est absent ou totalement vide, après
le passage de fill_e_pillar.py. Rien n'est modifié.

Usage : F5 dans VS Code.
"""
from pathlib import Path
import pandas as pd

ESG_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\ESG")
ESG_SUFFIX = "_esg.xlsx"


def main():
    files = sorted(ESG_DIR.glob(f"*{ESG_SUFFIX}"))
    print(f"{len(files)} fichiers dans 02_Processed\\ESG\n")

    ok, missing_col, empty_col, partial = [], [], [], []

    for f in files:
        key = f.name[: -len(ESG_SUFFIX)]
        try:
            df = pd.read_excel(f)
        except Exception as e:
            missing_col.append((key, f"illisible ({e})"))
            continue

        if "E_Pillar" not in df.columns:
            missing_col.append((key, "colonne absente"))
            continue

        n_total = len(df)
        n_filled = df["E_Pillar"].notna().sum()

        if n_filled == 0:
            empty_col.append(key)
        elif n_filled < n_total:
            partial.append((key, n_filled, n_total))
        else:
            ok.append(key)

    print(f"✅  E_Pillar complet          : {len(ok)}/{len(files)}")
    print(f"⚠️  E_Pillar partiel          : {len(partial)}")
    print(f"❌  E_Pillar vide (0 valeur)  : {len(empty_col)}")
    print(f"❌  Colonne absente/illisible : {len(missing_col)}")

    if partial:
        print("\nPartiels (à vérifier) :")
        for k, n, tot in partial:
            print(f"  - {k:<20} {n}/{tot} années remplies")

    if empty_col:
        print("\nVides :")
        for k in empty_col:
            print(f"  - {k}")

    if missing_col:
        print("\nAbsents/illisibles :")
        for k, msg in missing_col:
            print(f"  - {k:<20} [{msg}]")

    if not partial and not empty_col and not missing_col:
        print("\n🎉  Tous les fichiers ont E_Pillar complet.")


if __name__ == "__main__":
    main()
