"""
options_panel.py
────────────────
Lance autant de fois que nécessaire. À chaque run :
  1. Scan des 42 fichiers CSV  (~30 min, inévitable)
  2. Lecture du checkpoint Excel existant  → skip des CUSIP déjà traités
  3. Fetch LSEG des CUSIP restants, sauvegarde ligne par ligne dans le CSV
  4. À la fin : fusion CSV → Excel

Aucune reconnexion automatique, aucune pause automatique.
Si LSEG coupe → le programme finit proprement ce qu'il a fetch,
sauvegarde tout, et s'arrête. Tu relances, il reprend où il s'était arrêté.
"""

import argparse
import sys
import time
import warnings
from pathlib import Path
from collections import Counter

warnings.filterwarnings("ignore", category=FutureWarning, module=r"refinitiv\.data")
warnings.filterwarnings("ignore", category=UserWarning, module=r"openpyxl")

import pandas as pd
pd.set_option("future.no_silent_downcasting", True)

import refinitiv.data as rd

# ── Constantes ────────────────────────────────────────────────────────────────
OPTIONS_FOLDER = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\Options"
DATE_START     = "2010-01-04"
DATE_END       = "2023-12-29"
ESG_FIELD      = "TR.TRESGScore"
ESG_YEAR_MIN   = 2000
ESG_YEAR_START = 2002
ESG_YEAR_END   = 2023
SLEEP          = 0.25

WANTED_COLS       = {"secid", "cusip", "ticker", "issuer", "index_flag", "date"}
CHUNKSIZE         = 200_000
EXCHANGE_SUFFIXES = [".O", ".N", ".A", ".P", ".OQ"]
SKIP_SHEET_PREFIXES = ("00_",)
SKIP_SHEET_SUFFIXES = ("_TICKERS",)

# [FIX doublons ticker] Un candidat (secid, cusip8) n'est considéré comme
# potentiellement pertinent pour le panel 2017-2023 que si ses propres
# contrats d'options ont coté jusqu'à au moins cette date. Une société dont
# la dernière option observée date d'avant ce seuil (ex: Crestar Financial,
# racheté en 2000) est structurellement hors-jeu, quel que soit le ticker
# qu'elle partage avec une société encore active aujourd'hui.
PANEL_RELEVANCE_START = "20160101"

COL_ORDER = [
    "secid", "cusip8", "cusip9", "ticker", "issuer", "uid_used",
    "price_start", "price_start_date", "price_start_year",
    "price_end", "price_end_date",
    "esg_first_year", "esg_first_score", "esg_2023_score",
    "date_min", "date_max", "dedup_status",
    "in_panel", "source_files",
]


# ─────────────────────────────────────────────────────────────────────────────
# Lecture fichiers
# ─────────────────────────────────────────────────────────────────────────────

def _is_data_sheet(name):
    for p in SKIP_SHEET_PREFIXES:
        if name.startswith(p): return False
    for s in SKIP_SHEET_SUFFIXES:
        if name.endswith(s):   return False
    return True


def _normalize_cusip8(raw):
    c = str(raw).strip()
    return c.zfill(8) if len(c) < 8 else c[:8]


def _process_df(df, fname):
    df.columns = [c.strip().lower() for c in df.columns]
    if "cusip" not in df.columns: return None
    if "index_flag" in df.columns:
        df = df[df["index_flag"].astype(str).str.strip() != "1"]
    if df.empty: return None
    sub = pd.DataFrame()
    sub["secid"]  = df["secid"].str.strip()              if "secid"  in df.columns else ""
    sub["cusip8"] = df["cusip"].astype(str).str.strip().apply(_normalize_cusip8)
    sub["ticker"] = df["ticker"].str.strip().str.upper() if "ticker" in df.columns else ""
    sub["issuer"] = df["issuer"].str.strip()             if "issuer" in df.columns else ""
    # [FIX doublons ticker] "date" (YYYYMMDD, cotation de l'option) est la
    # seule information du fichier brut qui permette de savoir si un
    # candidat (secid, cusip8) était encore actif près de la fenêtre du
    # panel — jusqu'ici entièrement ignorée par WANTED_COLS.
    if "date" in df.columns:
        d = df["date"].astype(str).str.strip()
        sub["date"] = d.replace("", pd.NA)
    else:
        sub["date"] = pd.NA
    sub["source"] = fname
    sub = sub.dropna(subset=["cusip8"])
    sub = sub[sub["cusip8"].str.len() == 8]
    return sub if not sub.empty else None


def _aggregate_by_secid_cusip(sub: pd.DataFrame) -> pd.DataFrame:
    """Agrège des lignes brutes (une par contrat d'option) au niveau
    (secid, cusip8) : ticker/issuer les plus fréquents, et bornes de dates
    (date_min/date_max) pour la résolution des doublons de ticker."""
    def mf(s):
        v = s[s.astype(str).str.strip() != ""].dropna()
        return v.mode().iloc[0] if not v.empty else ""
    return (sub.groupby(["secid", "cusip8"], as_index=False)
               .agg(ticker=("ticker", mf),
                    issuer=("issuer", mf),
                    source=("source", "first"),
                    date_min=("date", "min"),
                    date_max=("date", "max")))


def _detect_sep_and_cols(fpath):
    for sep in (",", ";", "\t", "|"):
        try:
            h = pd.read_csv(fpath, sep=sep, nrows=5, dtype=str,
                            engine="c", on_bad_lines="skip")
            if h.shape[1] < 2: continue
            cols_lower   = {c.strip().lower(): c for c in h.columns}
            wanted_found = [orig for lc, orig in cols_lower.items()
                            if lc in WANTED_COLS]
            return sep, (wanted_found or None)
        except Exception: continue
    return ",", None


def _read_csv_fast(fpath, fname):
    sep, usecols = _detect_sep_and_cols(fpath)
    records = []
    for chunk in pd.read_csv(fpath, sep=sep, usecols=usecols, dtype=str,
                              chunksize=CHUNKSIZE, engine="c", on_bad_lines="skip"):
        sub = _process_df(chunk, fname)
        if sub is not None: records.append(sub)
    if not records: return []
    combined = pd.concat(records, ignore_index=True)
    return [_aggregate_by_secid_cusip(combined)]


def _read_excel_file(fpath):
    engine = "openpyxl" if fpath.suffix.lower() == ".xlsx" else "xlrd"
    xf     = pd.ExcelFile(fpath, engine=engine)
    return [pd.read_excel(fpath, sheet_name=s, dtype=str, engine=engine)
            for s in xf.sheet_names if _is_data_sheet(s)]


def scan_files(folder):
    files = sorted(list(folder.glob("*.xlsx")) +
                   list(folder.glob("*.xls"))  +
                   list(folder.glob("*.csv")))
    if not files: sys.exit(f"❌  Aucun fichier dans : {folder}")

    print(f"  📁 {len(files)} fichiers trouvés\n")
    records, t0 = [], time.time()

    for fi, fpath in enumerate(files, 1):
        fname = fpath.name; ext = fpath.suffix.lower(); t1 = time.time()
        try:
            raw = _read_csv_fast(fpath, fname) if ext == ".csv" \
                  else _read_excel_file(fpath)
            n, processed = set(), []
            for df in raw:
                if ext == ".csv":
                    sub = df  # déjà agrégé (secid,cusip8) par _read_csv_fast
                else:
                    row_level = _process_df(df, fname)
                    sub = _aggregate_by_secid_cusip(row_level) if row_level is not None else None
                if sub is None or sub.empty: continue
                n.update(sub["cusip8"].unique()); processed.append(sub)
            print(f"  [{fi:>2}/{len(files)}] ✅  {fname:<52}  "
                  f"{len(n):>4} CUSIP  ({time.time()-t1:.1f}s)")
            records.extend(processed)
        except Exception as e:
            print(f"  [{fi:>2}/{len(files)}] ❌  {fname:<52}  {e}")

    if not records: sys.exit("❌  Aucun CUSIP extrait.")
    all_df = pd.concat(records, ignore_index=True)
    def mf(s):
        v = s[s.astype(str).str.strip() != ""].dropna()
        return v.mode().iloc[0] if not v.empty else ""
    deduped = (all_df.groupby(["secid","cusip8"], as_index=False)
               .agg(ticker      =("ticker", mf),
                    issuer      =("issuer", mf),
                    source_files=("source", lambda s: "|".join(sorted(s.unique()))),
                    date_min    =("date_min", "min"),
                    date_max    =("date_max", "max")))
    deduped["cusip9"] = deduped["cusip8"] + "0"
    print(f"\n  ─── {len(deduped)} CUSIP uniques  |  {time.time()-t0:.0f}s\n")
    return deduped


def resolve_ticker_duplicates_by_date(deduped: pd.DataFrame) -> pd.DataFrame:
    """
    [FIX doublons ticker] Un même symbole ticker peut avoir été porté par
    plusieurs sociétés distinctes depuis 1996 (recyclage des symboles
    boursiers) — ex: "CF" = Charter One Financial (racheté 2004) OU
    CF Industries Holdings (active) OU Crestar Financial (racheté 2000),
    tous distingués uniquement par leur (secid, cusip8) dans les fichiers
    d'options bruts. Résultat concret observé : CF_5976_esg.xlsx labellisé
    "CRESTAR FINANCIAL CORP" au lieu de CF Industries.

    Résolution PUREMENT hors-ligne (aucun appel LSEG) : pour chaque groupe
    de candidats partageant un ticker, seuls ceux dont date_max (dernière
    cotation d'option observée dans les 58 Go) atteint au moins
    PANEL_RELEVANCE_START sont conservés — une société dont plus aucune
    option n'a coté depuis avant 2016 ne peut pas être la bonne
    contrepartie pour un panel 2017-2023, quel que soit le volume
    d'options qu'elle a généré dans le passé.

      - 1 seul survivant  → doublon résolu, gardé, dedup_status="resolu_date"
      - 0 survivant       → cas dégénéré (tous obsolètes) : le plus récent
                             des candidats est gardé quand même, marqué
                             "resolu_date_aucun_recent" pour vérification
      - 2+ survivants      → la date ne suffit pas à trancher (les deux
                             candidats ont coté près de la fenêtre du
                             panel) : tous conservés, marqués
                             "ambigu_date_ne_tranche_pas" — à confirmer via
                             dedupe_options_panel.py (LSEG) avant de lancer
                             le téléchargement.
    """
    deduped = deduped.copy()
    deduped["dedup_status"] = "unique"

    dupe_counts = deduped["ticker"].value_counts()
    dupe_tickers = dupe_counts[dupe_counts > 1].index.tolist()
    if not dupe_tickers:
        return deduped

    print(f"  🔎  {len(dupe_tickers)} tickers avec plusieurs secid candidats "
          f"— résolution par date_max >= {PANEL_RELEVANCE_START} :\n")

    keep_idx, drop_idx = [], []
    for ticker in dupe_tickers:
        group = deduped[deduped["ticker"] == ticker]
        recent = group[group["date_max"].fillna("") >= PANEL_RELEVANCE_START]

        if len(recent) == 1:
            row = recent.iloc[0]
            print(f"    ✅  {ticker:<8} → conservé secid={row['secid']} "
                  f"('{row['issuer']}', date_max={row['date_max']})")
            keep_idx.append(recent.index[0])
            deduped.loc[recent.index[0], "dedup_status"] = "resolu_date"
            drop_idx.extend(i for i in group.index if i != recent.index[0])

        elif len(recent) == 0:
            fallback = group.sort_values("date_max", ascending=False).iloc[[0]]
            print(f"    ⚠️  {ticker:<8} → AUCUN candidat récent (tous < "
                  f"{PANEL_RELEVANCE_START}) — garde le plus récent quand "
                  f"même : secid={fallback.iloc[0]['secid']} "
                  f"('{fallback.iloc[0]['issuer']}'), à vérifier")
            keep_idx.append(fallback.index[0])
            deduped.loc[fallback.index[0], "dedup_status"] = "resolu_date_aucun_recent"
            drop_idx.extend(i for i in group.index if i != fallback.index[0])

        else:
            print(f"    ❓  {ticker:<8} → {len(recent)} candidats encore actifs "
                  f"près de la fenêtre du panel, la date ne tranche pas — "
                  f"CONSERVÉS TOUS, à confirmer via dedupe_options_panel.py "
                  f"(LSEG) avant le téléchargement")
            for i in recent.index:
                deduped.loc[i, "dedup_status"] = "ambigu_date_ne_tranche_pas"
            drop_idx.extend(i for i in group.index if i not in recent.index)

    resolved = deduped.drop(index=drop_idx).reset_index(drop=True)
    n_ambigu = (resolved["dedup_status"] == "ambigu_date_ne_tranche_pas").sum()
    print(f"\n  ─── {len(deduped)} → {len(resolved)} lignes après résolution "
          f"({len(drop_idx)} doublons écartés, {n_ambigu} tickers encore "
          f"ambigus)\n")
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint
# ─────────────────────────────────────────────────────────────────────────────

def load_checkpoint(out_xlsx):
    """
    Cherche le checkpoint dans cet ordre de priorité :
      1. CSV (out_xlsx avec extension .csv) — écrit après chaque ticker,
         résiste au SIGKILL, toujours plus à jour que l'Excel.
      2. Excel (out_xlsx) — fallback si le CSV n'existe pas.
      3. Rien → départ de zéro.
    Retourne (df_existant, set_cusip8_deja_traites).
    """
    out_csv = out_xlsx.with_suffix(".csv")

    # ── Priorité 1 : CSV ──────────────────────────────────────────────────
    if out_csv.exists():
        try:
            df = pd.read_csv(out_csv, dtype=str)
            for col in ["price_start","price_end","esg_first_score","esg_2023_score",
                        "price_start_year","esg_first_year"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "in_panel" in df.columns:
                df["in_panel"] = df["in_panel"].map(
                    {"True":True,"False":False,True:True,False:False}
                ).fillna(False).astype(bool)
            done = set(df["cusip8"].dropna().astype(str).str.strip())
            print(f"  📂  Checkpoint CSV : {len(done)} CUSIP déjà traités "
                  f"({out_csv.name}) → on reprend après.\n")
            return df, done
        except Exception as e:
            print(f"  ⚠️  CSV illisible ({e}) → tentative Excel...\n")

    # ── Priorité 2 : Excel ────────────────────────────────────────────────
    if out_xlsx.exists():
        try:
            df = pd.read_excel(out_xlsx, sheet_name="Options Panel", dtype=str)
            for col in ["price_start","price_end","esg_first_score","esg_2023_score",
                        "price_start_year","esg_first_year"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "in_panel" in df.columns:
                df["in_panel"] = df["in_panel"].map(
                    {"True":True,"False":False,True:True,False:False}
                ).fillna(False).astype(bool)
            done = set(df["cusip8"].dropna().astype(str).str.strip())
            print(f"  📂  Checkpoint Excel : {len(done)} CUSIP déjà traités "
                  f"({out_xlsx.name}) → on reprend après.\n")
            return df, done
        except Exception as e:
            print(f"  ⚠️  Excel illisible ({e}) → reprise de zéro.\n")

    # ── Priorité 3 : zéro ────────────────────────────────────────────────
    print("  📂  Aucun checkpoint trouvé — départ de zéro.\n")
    return pd.DataFrame(), set()


# ─────────────────────────────────────────────────────────────────────────────
# LSEG
# ─────────────────────────────────────────────────────────────────────────────

def _call_lseg(uid, fields, params):
    try:
        resp = rd.get_data(universe=[uid], fields=fields, parameters=params)
        if resp is None or resp.empty: return None
        non_id = [c for c in resp.columns if c != "Instrument"]
        if not non_id or not resp[non_id].notna().any().any(): return None
        return resp
    except Exception:
        return None
    finally:
        time.sleep(SLEEP)


def _build_id_list(cusip9, cusip8, ticker):
    ids, c9, c8 = [], cusip9.strip(), cusip8.strip()
    tk = ticker.strip().upper() if ticker else ""
    if c9: ids.append(f"CUSIP:{c9}")
    if c8 and c8 != c9: ids.append(f"CUSIP:{c8}")
    if tk and len(tk) <= 10:
        ids.append(tk)
        for sfx in EXCHANGE_SUFFIXES: ids.append(f"{tk}{sfx}")
    return ids


def _resolve_ric(cusip9, cusip8):
    for uid in [f"CUSIP:{cusip9}", f"CUSIP:{cusip8}"]:
        resp = _call_lseg(uid, ["TR.RIC"], {})
        if resp is None: continue
        for col in ["RIC","TR.RIC"]:
            if col not in resp.columns: continue
            val = resp.iloc[0][col]
            if val and str(val) not in ("nan","None",""): return str(val).strip()
    return None


def _get_cascade(cusip9, cusip8, ticker, fields, params, try_ric=True):
    for uid in _build_id_list(cusip9, cusip8, ticker):
        resp = _call_lseg(uid, fields, params)
        if resp is not None: return resp, uid
    if try_ric:
        ric = _resolve_ric(cusip9, cusip8)
        if ric:
            resp = _call_lseg(ric, fields, params)
            if resp is not None: return resp, f"RIC:{ric}"
    return None, ""


# ── Prix ──────────────────────────────────────────────────────────────────────

def _parse_price(resp):
    for pcol in ["Price Close","TR.PriceClose"]:
        if pcol not in resp.columns: continue
        val = resp.iloc[0][pcol]
        if val is None or str(val) in ("nan","None",""): continue
        d = ""
        for dcol in ["Date","TR.PriceClose.date"]:
            if dcol in resp.columns:
                v = resp.iloc[0][dcol]
                if v and str(v) not in ("nan","None",""):
                    try: d = str(pd.Timestamp(v).date())
                    except: pass
                break
        return round(float(val), 4), d
    return None, ""


def _price_window(cusip9, cusip8, ticker, date_str, window=14):
    dt = pd.Timestamp(date_str)
    s  = (dt - pd.Timedelta(days=window)).strftime("%Y-%m-%d")
    e  = (dt + pd.Timedelta(days=window)).strftime("%Y-%m-%d")
    resp, uid = _get_cascade(cusip9, cusip8, ticker,
                             ["TR.PriceClose","TR.PriceClose.date"],
                             {"SDate":s,"EDate":e})
    if resp is None: return None, "", ""
    p, d = _parse_price(resp)
    return p, d, uid


def get_start_price(cusip9, cusip8, ticker):
    p, d, uid = _price_window(cusip9, cusip8, ticker, DATE_START, 14)
    if p is not None: return p, d, uid
    for year in range(2010, 2024):
        for month in ["01-01","07-01"]:
            p, d, uid = _price_window(cusip9, cusip8, ticker, f"{year}-{month}", 90)
            if p is not None: return p, d, uid
    return None, "", ""


def get_end_price(cusip9, cusip8, ticker):
    return _price_window(cusip9, cusip8, ticker, DATE_END, 14)


# ── ESG ───────────────────────────────────────────────────────────────────────

def _valid_year(y):
    try: return ESG_YEAR_MIN <= int(y) <= ESG_YEAR_END
    except: return False


def _extract_score(df, col, target_year=None):
    DATE_COLS = ["Date","Period End Date","TR.TRESGScore.periodenddate"]
    for dc in DATE_COLS:
        if dc not in df.columns: continue
        try:
            tmp = df.copy()
            tmp["_d"] = pd.to_datetime(tmp[dc], errors="coerce")
            tmp = tmp.dropna(subset=["_d",col])
            tmp = tmp[tmp["_d"].dt.year >= ESG_YEAR_MIN].sort_values("_d")
            if target_year: tmp = tmp[tmp["_d"].dt.year == target_year]
            if tmp.empty: continue
            val = tmp.iloc[0][col]
            if val is None or str(val) in ("nan","None",""): continue
            return int(tmp.iloc[0]["_d"].year), round(float(val), 4)
        except: continue
    return None, None


def get_esg_data(cusip9, cusip8, ticker):
    fy = fs = f23 = None
    resp, _ = _get_cascade(cusip9, cusip8, ticker, [ESG_FIELD],
                           {"SDate":f"{ESG_YEAR_START}-01-01",
                            "EDate":f"{ESG_YEAR_END}-12-31","Frq":"FY"})
    if resp is not None:
        col = next((c for c in ["ESG Score","TR.TRESGScore"] if c in resp.columns), None)
        if col:
            clean = resp.dropna(subset=[col])
            if not clean.empty:
                yr, sc = _extract_score(clean, col)
                if yr and _valid_year(yr): fy, fs = yr, sc
                yr23, sc23 = _extract_score(clean, col, target_year=2023)
                if yr23 == 2023: f23 = sc23
    if fy is not None and f23 is not None: return fy, fs, f23

    for year in range(ESG_YEAR_START, ESG_YEAR_END+1):
        if fy is not None and year != 2023: continue
        resp, _ = _get_cascade(cusip9, cusip8, ticker, [ESG_FIELD],
                               {"SDate":f"{year}-01-01","EDate":f"{year}-12-31"},
                               try_ric=False)
        if resp is None: continue
        col = next((c for c in ["ESG Score","TR.TRESGScore"] if c in resp.columns), None)
        if not col: continue
        val = resp.iloc[0][col]
        if val is None or str(val) in ("nan","None",""): continue
        sv = round(float(val), 4)
        if fy is None and _valid_year(year): fy, fs = year, sv
        if year == 2023 and f23 is None: f23 = sv
    return fy, fs, f23


# ─────────────────────────────────────────────────────────────────────────────
# Export Excel
# ─────────────────────────────────────────────────────────────────────────────

def export_excel(df_out, path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("  ⚠️  openpyxl manquant → CSV uniquement"); return

    wb = Workbook(); ws = wb.active; ws.title = "Options Panel"
    hdr_fill  = PatternFill("solid", fgColor="1F3864")
    hdr_font  = Font(bold=True, color="FFFFFF", size=10)
    ok_fill   = PatternFill("solid", fgColor="FFFFFF")
    late_fill = PatternFill("solid", fgColor="FFF2CC")
    ko_fill   = PatternFill("solid", fgColor="FCE4D6")
    thin      = Side(style="thin", color="D0D0D0")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)
    ca        = Alignment(horizontal="center", vertical="center")
    la        = Alignment(horizontal="left",   vertical="center")

    headers = list(df_out.columns)
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill=hdr_fill; cell.font=hdr_font; cell.alignment=ca; cell.border=border

    for ri, row in enumerate(df_out.itertuples(index=False), 2):
        in_panel = bool(getattr(row,"in_panel",False))
        yr_start = getattr(row,"price_start_year",None)
        try:    late = int(yr_start) > 2010 if yr_start else False
        except: late = False
        fill = late_fill if (in_panel and late) else (ok_fill if in_panel else ko_fill)
        for ci, (h, val) in enumerate(zip(headers, row), 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.fill=fill; cell.border=border
            if   h in {"price_start","price_end"}:
                cell.number_format='#,##0.00'; cell.alignment=ca
            elif h in {"esg_first_score","esg_2023_score"}:
                cell.number_format='0.00'; cell.alignment=ca
            elif h in {"esg_first_year","price_start_year"}:
                cell.number_format='0'; cell.alignment=ca
            elif h in {"secid","cusip8","cusip9","ticker","uid_used","in_panel"}:
                cell.alignment=ca
            else:
                cell.alignment=la

    col_widths = {
        "secid":9,"cusip8":11,"cusip9":12,"ticker":9,"issuer":30,"uid_used":22,
        "price_start":13,"price_start_date":17,"price_start_year":15,
        "price_end":13,"price_end_date":15,
        "esg_first_year":14,"esg_first_score":15,"esg_2023_score":14,
        "in_panel":10,"source_files":50,
    }
    for ci, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = col_widths.get(h, 13)
    ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions

    leg = wb.create_sheet("Légende")
    for row_data, fill in [
        (("Blanc",      "Données complètes — prix dès 2010 + ESG"),  ok_fill),
        (("Jaune pâle", "IPO post-2010 — premier prix après 2010"),  late_fill),
        (("Rouge pâle", "Données insuffisantes — exclu du panel"),   ko_fill),
    ]:
        ri = leg.max_row + 1
        for ci, val in enumerate(row_data, 1):
            c = leg.cell(row=ri, column=ci, value=val); c.fill=fill
    leg.column_dimensions["A"].width=14; leg.column_dimensions["B"].width=55

    wb.save(path)
    print(f"  📊  Excel → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Sauvegarde checkpoint (CSV intermédiaire + Excel final)
# ─────────────────────────────────────────────────────────────────────────────

def save_all(df_existing, rows_new, out_xlsx, out_csv):
    """
    Fusionne df_existing + rows_new et sauvegarde CSV + Excel.
    Retourne le df fusionné.
    """
    df_new = pd.DataFrame(rows_new)
    for col in COL_ORDER:
        if col not in df_new.columns: df_new[col] = None
    df_new = df_new[COL_ORDER]

    if not df_existing.empty:
        for col in COL_ORDER:
            if col not in df_existing.columns: df_existing[col] = None
        df_existing = df_existing[COL_ORDER]
        df_out = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_out = df_new

    df_out = df_out.sort_values("secid", ignore_index=True)
    df_out.to_csv(out_csv, index=False)
    print(f"\n  💾  CSV → {out_csv}  ({len(df_out)} lignes total)")
    export_excel(df_out, out_xlsx)
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default=OPTIONS_FOLDER)
    parser.add_argument("--output", default=(
        r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data"
        r"\00_Tickers\options_panel.xlsx"))
    args = parser.parse_args()

    folder   = Path(args.folder)
    out_xlsx = Path(args.output)
    out_csv  = out_xlsx.with_suffix(".csv")

    if not folder.exists():
        sys.exit(f"❌  Dossier introuvable : {folder}")

    print()
    print("═"*115)
    print("  OPTIONS PANEL — checkpoint automatique")
    print(f"  Sortie : {out_xlsx}")
    print("═"*115); print()

    # ── 1. Scan ──────────────────────────────────────────────────────────
    print("  ── ÉTAPE 1 : Scan des fichiers ──\n")
    deduped = scan_files(folder)

    # ── 1bis. Résolution des doublons de ticker par couverture de date ─────
    print("  ── ÉTAPE 1bis : Résolution des doublons de ticker ──\n")
    deduped = resolve_ticker_duplicates_by_date(deduped)
    total   = len(deduped)

    # ── 2. Checkpoint ────────────────────────────────────────────────────
    print("  ── ÉTAPE 2 : Chargement checkpoint ──\n")
    df_existing, done = load_checkpoint(out_xlsx)

    # [FIX] Un run précédent (avant résolution par date) a pu écrire des
    # lignes pour des cusip8 que la résolution actuelle vient d'écarter
    # (doublons de ticker obsolètes, ex: Crestar Financial pour "CF"). Sans
    # ce nettoyage, ces cusip8 restent marqués "déjà traités" dans le
    # checkpoint → todo devient vide → le script sort immédiatement sans
    # jamais réécrire le CSV/Excel, laissant les doublons stales sur disque
    # malgré une résolution qui a pourtant fonctionné correctement.
    valid_cusip8 = set(deduped["cusip8"])
    if not df_existing.empty:
        before = len(df_existing)
        df_existing = df_existing[df_existing["cusip8"].isin(valid_cusip8)].reset_index(drop=True)
        removed = before - len(df_existing)
        if removed > 0:
            print(f"  🧹  {removed} ligne(s) du checkpoint écartée(s) par la résolution "
                  f"par date (doublons de ticker obsolètes) — CSV/Excel réécrits.\n")
            df_existing.to_csv(out_csv, index=False)
            export_excel(df_existing, out_xlsx)
            done = set(df_existing["cusip8"].astype(str).str.strip())

    todo = deduped[~deduped["cusip8"].isin(done)].reset_index(drop=True)
    n_todo = len(todo)

    if n_todo == 0:
        print("  ✅  Tous les tickers sont déjà traités.\n")
        return

    print(f"  📋  {total} CUSIP au total")
    print(f"  ✔   {len(done)} déjà traités (checkpoint)")
    print(f"  ▶   {n_todo} à fetch ce run\n")

    # ── 3. Fetch ─────────────────────────────────────────────────────────
    print("  ── ÉTAPE 3 : Fetch LSEG ──\n")
    try:
        rd.open_session()
    except Exception as e:
        print(f"  ⚠️  rd.open_session() : {e}")

    print(f"  {'#':<5} {'secid':<8} {'CUSIP8':<10} {'Ticker':<7} "
          f"{'Prix début':>11} {'Année':>5} {'Prix 2023':>11}  "
          f"{'ESG 1ère':>9} {'Score 1ère':>11} {'Score 23':>9}  "
          f"{'ID utilisé':<22}  Statut  [req/quota]")
    print("─"*125)

    stats     = Counter()
    esg_years = []
    req_count = 0      # compteur de requêtes de ce run

    # ── Sauvegarde incrémentale ───────────────────────────────────────────
    # Le CSV est écrit APRÈS CHAQUE TICKER via pandas.DataFrame.to_csv(mode='a')
    # Ainsi même un SIGKILL (bouton corbeille VS Code) ne perd qu'1 ticker max.
    # À la fin du run, on reconstruit l'Excel depuis le CSV complet.

    # En-tête CSV : écrit une seule fois si le fichier n'existe pas encore
    # ou si le checkpoint est vide (nouveau run).
    csv_header_needed = not out_csv.exists() or len(done) == 0

    try:
        for idx in range(n_todo):
            row    = todo.iloc[idx]
            num    = len(done) + idx + 1   # numéro global
            secid  = str(row["secid"]).strip()
            cusip8 = str(row["cusip8"]).strip()
            cusip9 = str(row["cusip9"]).strip()
            ticker = str(row["ticker"]).strip()
            issuer = str(row["issuer"]).strip()
            source = str(row["source_files"]).strip()

            p_start, d_start, uid_s = get_start_price(cusip9, cusip8, ticker)
            y_start  = int(d_start[:4]) if d_start else None
            p_end, d_end, uid_e     = get_end_price(cusip9, cusip8, ticker)
            esg_yr, esg_sc1, esg_sc23 = get_esg_data(cusip9, cusip8, ticker)

            uid_used   = uid_s or uid_e or "—"
            has_prices = p_start is not None and p_end is not None
            has_esg    = esg_yr is not None
            in_panel   = has_prices and has_esg
            late       = y_start is not None and y_start > 2010

            # Estimation requêtes : ~8 req/ticker (cascade prix + ESG)
            req_count += 8
            quota_pct  = round(100 * req_count / 9_500, 1)

            if in_panel and late:
                statut = f"✅ OK (IPO {y_start})"; stats["ok_late"] += 1
                esg_years.append(esg_yr)
            elif in_panel:
                statut = "✅ OK"; stats["ok"] += 1
                esg_years.append(esg_yr)
            elif not has_prices:
                statut = "⚠️  prix manquant"; stats["no_price"] += 1
            elif not has_esg:
                statut = "⚠️  ESG manquant";  stats["no_esg"] += 1
            else:
                statut = "❌ aucune donnée";   stats["no_data"] += 1

            print(f"  {num:<5} {secid:<8} {cusip8:<10} {ticker:<7} "
                  f"{str(round(p_start,2)) if p_start else '—':>11} "
                  f"{str(y_start) if y_start else '—':>5} "
                  f"{str(round(p_end,2)) if p_end else '—':>11}  "
                  f"{str(esg_yr) if esg_yr else '—':>9} "
                  f"{str(esg_sc1) if esg_sc1 else '—':>11} "
                  f"{str(esg_sc23) if esg_sc23 else '—':>9}  "
                  f"{uid_used:<22}  {statut}  "
                  f"[~{req_count} req / {quota_pct}% quota]")

            row_dict = {
                "secid": secid, "cusip8": cusip8, "cusip9": cusip9,
                "ticker": ticker, "issuer": issuer, "uid_used": uid_used,
                "price_start":      round(p_start,4) if p_start else None,
                "price_start_date": d_start,
                "price_start_year": y_start,
                "price_end":        round(p_end,4) if p_end else None,
                "price_end_date":   d_end,
                "esg_first_year":   esg_yr,
                "esg_first_score":  esg_sc1,
                "esg_2023_score":   esg_sc23,
                "date_min":         row.get("date_min"),
                "date_max":         row.get("date_max"),
                "dedup_status":     row.get("dedup_status"),
                "in_panel":         in_panel,
                "source_files":     source,
            }

            # ── Écriture immédiate sur disque (résiste au SIGKILL) ───────
            pd.DataFrame([row_dict]).to_csv(
                out_csv,
                mode   = "w" if csv_header_needed else "a",
                header = csv_header_needed,
                index  = False,
            )
            csv_header_needed = False   # en-tête écrit une seule fois

    except KeyboardInterrupt:
        print("\n  ⚠️  Interrompu manuellement — sauvegarde en cours...")

    finally:
        # ── 4. Reconstruction Excel depuis le CSV complet ─────────────────
        # Le CSV est déjà à jour (écrit après chaque ticker).
        # On relit le CSV complet (checkpoint précédent + ce run) et on
        # génère l'Excel final. Résiste au Ctrl+C ET au SIGKILL (corbeille).
        try: rd.close_session()
        except: pass

        if out_csv.exists():
            try:
                df_final = pd.read_csv(out_csv, dtype=str)
                for col in ["price_start","price_end","esg_first_score",
                            "esg_2023_score","price_start_year","esg_first_year"]:
                    if col in df_final.columns:
                        df_final[col] = pd.to_numeric(df_final[col], errors="coerce")
                if "in_panel" in df_final.columns:
                    df_final["in_panel"] = df_final["in_panel"].map(
                        {"True":True,"False":False,True:True,False:False}
                    ).fillna(False).astype(bool)
                df_final = df_final.sort_values("secid", ignore_index=True)
                export_excel(df_final, out_xlsx)
                tickers_in_csv = len(df_final)
                print(f"  ✅  Excel reconstruit depuis le CSV "
                      f"({tickers_in_csv} lignes au total)")
            except Exception as e:
                print(f"  ⚠️  Impossible de reconstruire l'Excel : {e}")
                df_final = pd.DataFrame()
        else:
            print("  ⚠️  Aucun CSV trouvé — rien à sauvegarder.")
            df_final = pd.DataFrame()

    # ── 5. Résumé ────────────────────────────────────────────────────────
    traites_total = len(df_final) if not df_final.empty else len(done)
    restants      = total - traites_total
    ok_total      = stats["ok"] + stats["ok_late"]

    print()
    print("═"*115)
    print("  RÉSUMÉ")
    print("─"*115)
    print(f"  Requêtes LSEG estimées ce run  : ~{req_count}")
    print(f"  ✅ OK (prix 2010 + ESG)         : {stats['ok']}")
    print(f"  ✅ OK (IPO post-2010 + ESG)     : {stats['ok_late']}")
    print(f"  ─── Total OK                   : {ok_total}")
    print(f"  ⚠️  Prix manquants               : {stats['no_price']}")
    print(f"  ⚠️  ESG manquant                 : {stats['no_esg']}")
    print(f"  ❌ Aucune donnée                 : {stats['no_data']}")
    print(f"\n  PROGRESSION : {traites_total} / {total} traités  "
          f"({restants} restants)")
    if restants > 0:
        print(f"  ▶  Relancez le script pour continuer les {restants} tickers restants.")
    else:
        print(f"  🎉  Panel complet — tous les tickers ont été traités.")

    if esg_years:
        ctr = Counter(esg_years)
        print("\n  Distribution 1ère année ESG :")
        cumul = 0
        for year in sorted(ctr.keys()):
            cumul += ctr[year]
            bar = "█" * min(ctr[year], 50)
            pct = 100 * cumul / len(esg_years)
            print(f"    {year}  {bar:<52}  {ctr[year]:>3} tickers  "
                  f"(cumulé {cumul}/{len(esg_years)} = {pct:.0f}%)")
        print()
        for thr in [0.80, 0.90, 0.95]:
            for year in sorted(ctr.keys()):
                n = sum(v for k,v in ctr.items() if k <= year)
                if n / len(esg_years) >= thr:
                    print(f"  → Seuil {int(thr*100)}% : {year}  "
                          f"({n}/{len(esg_years)}) → panel recommandé dès {year}")
                    break
    print("═"*115); print()


if __name__ == "__main__":
    main()