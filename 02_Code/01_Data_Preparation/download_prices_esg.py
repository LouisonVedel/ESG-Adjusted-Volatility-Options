"""
=============================================================================
TÉLÉCHARGEMENT & RÉPARATION DONNÉES PANEL — PRIX (DAILY + INTRADAY) & ESG
=============================================================================
Ce fichier fusionne deux scripts qui étaient séparés. Les deux étapes
s'enchaînent automatiquement à chaque lancement (F5), sans rien à
configurer :

  ÉTAPE 1 : téléchargement complet du panel depuis options_panel.csv
            (prix daily/intraday + ESG, 17 champs), avec skip automatique
            des fichiers déjà complets. C'est l'ancien
            download_prices_esg.py, inchangé.

  ÉTAPE 2 : réparation ciblée E_Pillar sur ce qui vient d'être écrit dans
            02_Processed\\ESG — filet de sécurité pour tout ticker qui
            ressortirait encore sans E_Pillar après l'étape 1 (throttling,
            champ ponctuellement indisponible, etc.). C'est l'ancien
            fill_e_pillar.py, inchangé. Ne touche pas à 01_Raw\\ESG.

-----------------------------------------------------------------------------
Source   : options_panel.csv  (in_panel=True, 375 tickers)  [mode full_download]
Connexion: refinitiv.data (LSEG Workspace ouvert en arrière-plan)

Logique RIC : même cascade que options_panel.py
  uid_used  →  CUSIP:cusip9  →  CUSIP:cusip8  →  TICKER suffixes

Outputs — FORMAT STANDARD (mode full_download)
─────────────────────────────────────────────────────────
  Prices\  {TICKER}_{secid}_prices_daily.xlsx
             Onglet "Daily_OHLCV"
             Colonnes : Date | Open | High | Low | Close | Volume
             Index    : Date (YYYY-MM-DD), une ligne par jour de bourse
             Période  : 2017-01-01 → price_end

           {TICKER}_{secid}_prices_intraday_{interval}.xlsx
             Onglet "Intraday_{interval}"
             Colonnes : Datetime | Open | High | Low | Close | Volume
             Index    : Datetime (YYYY-MM-DD HH:MM:SS), une ligne par barre
             Période  : 2017-01-01 → price_end  [M2]

  ESG\     {TICKER}_{secid}_esg.xlsx
             Onglet "ESG_Scores"  ← format long, une ligne par année
             Colonnes : Year | ticker | secid | issuer |
                        ESG_Score | ESG_Date |
                        E_Pillar | S_Pillar | G_Pillar |
                        ResourceUse | Emissions | EnvInnovation |
                        Workforce | HumanRights | Community |
                        ProductResponsibility | Management |
                        Shareholders | CSRStrategy |
                        ESGC_Score | ESGC_Grade
             Index    : Year (int), ESG_YEAR_START → ESG_YEAR_END

Relancez autant de fois que nécessaire : les fichiers déjà présents sont
ignorés automatiquement (skip), le script reprend où il s'était arrêté.

=============================================================================
HISTORIQUE DES MODIFICATIONS (mode full_download)
=============================================================================
  [M1] PANEL_START : "2015-01-01" → "2017-01-01"
  [M2] download_intraday() : suppression du plancher 2021-01-01
  [M3] ESG_START = "2017-01-01" : nouvelle constante globale
  [M5] Groupe B supprimé : seuls les tickers in_panel=True sont traités
  [D1]-[D4] Logs de diagnostic sur le pipeline ESG (colonnes reçues à
       chaque étape) — laissés en place, ne coûtent rien.
  [FIX] Root cause E_Pillar trouvée via les logs [D1]-[D4] : LSEG renvoie
       "Environmental Pillar Score" (avec "al"), pas "Environment Pillar
       Score" comme le mapping l'attendait. Corrigé dans ESG_COL_MAP.
  [FIX] Un fichier ESG existant n'est skippé que s'il est complet ET a
       E_Pillar rempli (_esg_file_has_e_pillar), sinon retéléchargé.
  [FIX régression] Retry avec pause de 5s en cas d'échec total sur un
       ticker (throttling LSEG transitoire observé après un pic de ~650
       requêtes en une session).

MODE fill_e_pillar : ajouté suite à la découverte que forcer le
retéléchargement complet (17 champs) de 323 tickers déjà bons pour
récupérer un seul champ manquant causait un throttling LSEG massif (62
tickers passés en échec total). Ce mode ne demande que E_Pillar, en
partant de la liste réelle des fichiers dans 02_Processed\\ESG plutôt que
du CSV brut — volume de requêtes ~17x plus faible.

=============================================================================
[FIX FENÊTRE ESG] 2017-2023 → 2016-2022, VRAIMENT découplée de la fenêtre Prix
=============================================================================
Besoin : predictive_esg_regression.py teste ESG_{y-1} → volatilité_y sur
toute la fenêtre Prix (2017-2023). Le dernier ESG nécessaire comme
prédicteur est donc celui de 2022 (pour prédire la volatilité de 2023) —
pas besoin d'ESG_2023 du tout, et il faut ESG_2016 pour prédire la
volatilité 2017 (premier point du panel).

Bug trouvé : la constante ESG_START était déjà changée à "2016-01-01"
dans le fichier fourni, mais elle n'est utilisée QUE dans l'affichage du
log — la vraie logique de filtrage avait 2017 codé EN DUR à deux autres
endroits (_expected_esg_years et _standardise_esg), et l'année de fin
était calculée depuis price_end (2023, la fenêtre Prix) au lieu d'une
borne ESG indépendante. Changer ESG_START seul n'aurait donc rien changé
du tout.

Corrigé : deux nouvelles constantes explicites, ESG_YEAR_START=2016 et
ESG_YEAR_END=2022, utilisées PARTOUT où l'ancien code utilisait 2017 ou
price_end pour borner l'ESG — la fenêtre ESG est maintenant entièrement
indépendante de la fenêtre Prix (qui reste 2017-2023, inchangée).
=============================================================================
"""

import csv
import sys
import time
import logging
import warnings
from pathlib import Path
from collections import Counter

warnings.filterwarnings("ignore", category=FutureWarning, module=r"refinitiv\.data")
warnings.filterwarnings("ignore", category=UserWarning,   module=r"openpyxl")

import pandas as pd
pd.set_option("future.no_silent_downcasting", True)

import refinitiv.data as rd

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

CSV_PATH    = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\00_Tickers\options_panel.csv"
PRICE_OUT   = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\Prices")
ESG_OUT     = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\ESG")

# [M1] Fenêtre principale (PRIX uniquement) : 2017 → 2023 — inchangée
PANEL_START = "2017-01-01"
PANEL_END   = "2023-12-31"

# [FIX FENÊTRE ESG] Fenêtre ESG, INDÉPENDANTE de la fenêtre Prix ci-dessus —
# 2016-2022 pour servir de prédicteur décalé d'un an à predictive_esg_regression.py
# (ESG_{y-1} → volatilité_y sur 2017-2023 ⇒ besoin d'ESG_2016 à ESG_2022).
ESG_YEAR_START = 2016
ESG_YEAR_END   = 2022
ESG_START      = f"{ESG_YEAR_START}-01-01"   # conservé pour l'affichage du log uniquement

# Diagnostic terminé — run complet sur tout le panel par défaut.
DEBUG_TICKER_LIMIT = None

INTRADAY_CANDIDATES = ["5min", "10min", "30min", "1H"]
SLEEP               = 0.25    # pause inter-appels LSEG
DELAY_TICKER        = 1.0     # pause inter-tickers
EXCHANGE_SUFX       = [".O", ".N", ".A", ".P", ".OQ"]

ESG_FIELDS = [
    "TR.TRESGScore", "TR.TRESGScore.Date",
    "TR.EnvironmentPillarScore", "TR.SocialPillarScore", "TR.GovernancePillarScore",
    "TR.ResourceUseScore", "TR.EmissionsScore", "TR.EnvironmentalInnovationScore",
    "TR.WorkforceScore", "TR.HumanRightsScore", "TR.CommunityScore",
    "TR.ProductResponsibilityScore", "TR.ManagementScore",
    "TR.ShareholdersScore", "TR.CSRStrategyScore",
    "TR.TRESGCScore", "TR.TRESGCScoreGrade",
]

# ── Config propre au mode fill_e_pillar ─────────────────────────────────────
ESG_PROCESSED_DIR = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\ESG")
ESG_PROCESSED_SUFFIX = "_esg.xlsx"
FILL_EXCHANGE_SUFX = ["", ".O", ".N", ".A", ".P", ".OQ"]
FILL_SLEEP = 0.3
FILL_RETRY_PAUSE = 5.0
E_PILLAR_FIELD = "TR.EnvironmentPillarScore"
E_PILLAR_NAME_VARIANTS = ["E_Pillar", "TR.EnvironmentPillarScore",
                           "Environment Pillar Score", "Environmental Pillar Score"]

# ─────────────────────────────────────────────────────────────────────────────
#  Les deux étapes s'enchaînent automatiquement au lancement (voir tout en
#  bas du fichier) : téléchargement complet du panel, puis passe de
#  réparation ciblée E_Pillar sur ce qui vient d'être écrit dans
#  02_Processed\ESG. Rien à configurer.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("download_prices_esg.log", encoding="utf-8", mode="w"),
    ],
)
log = logging.getLogger(__name__)


def _log_cols(label: str, df: pd.DataFrame | None, ticker: str = "") -> None:
    """[DIAGNOSTIC] Log compact des colonnes d'un DataFrame, avec présence
    explicite de E_Pillar / TR.EnvironmentPillarScore / variantes de nom."""
    if df is None:
        log.info(f"      🔍 [{label}] {ticker} → DataFrame = None")
        return
    cols = list(df.columns)
    e_variants = ["E_Pillar", "TR.EnvironmentPillarScore",
                  "Environment Pillar Score", "Environmental Pillar Score"]
    present_e = [c for c in e_variants if c in cols]
    log.info(f"      🔍 [{label}] {ticker} → {len(cols)} colonnes : {cols}")
    if present_e:
        sample_col = present_e[0]
        n_non_null = df[sample_col].notna().sum() if sample_col in df.columns else 0
        log.info(f"      🔍 [{label}] {ticker} → E_Pillar PRÉSENT ({present_e}), "
                 f"{n_non_null}/{len(df)} valeurs non-nulles")
    else:
        log.info(f"      🔍 [{label}] {ticker} → E_Pillar ABSENT de ces colonnes")


# ═══════════════════════════════════════════════════════════════════════════
#  MODE "full_download"  —  ancien download_prices_esg.py, inchangé
# ═══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
#  RÉSOLUTION RIC  —  aligné sur options_panel.py
# ─────────────────────────────────────────────────────────────────────────────

def _build_id_list(uid_used: str, cusip9: str, cusip8: str, ticker: str) -> list[str]:
    ids = []
    uid = uid_used.strip() if uid_used else ""
    c9  = cusip9.strip()   if cusip9  else ""
    c8  = cusip8.strip()   if cusip8  else ""
    tk  = ticker.strip().upper() if ticker else ""
    if uid and uid != "—":
        ids.append(uid)
    if c9:
        ids.append(f"CUSIP:{c9}")
    if c8 and c8 != c9:
        ids.append(f"CUSIP:{c8}")
    if tk and len(tk) <= 10:
        ids.append(tk)
        for sfx in EXCHANGE_SUFX:
            ids.append(f"{tk}{sfx}")
    return ids


def _call_lseg(uid: str, fields: list, params: dict, label: str = ""):
    """Appel rd.get_data() avec logging systématique des échecs."""
    try:
        resp = rd.get_data(universe=[uid], fields=fields, parameters=params)
        if resp is None:
            log.info(f"      ↳ {label} [{uid}] → réponse None")
            return None
        if resp.empty:
            log.info(f"      ↳ {label} [{uid}] → DataFrame vide (0 lignes)")
            return None
        non_id = [c for c in resp.columns if c != "Instrument"]
        if not non_id or not resp[non_id].notna().any().any():
            log.info(f"      ↳ {label} [{uid}] → colonnes toutes NaN")
            return None
        if "esg" in label.lower():
            _log_cols(f"_call_lseg/{label}", resp, uid)
        return resp
    except Exception as e:
        log.info(f"      ↳ {label} [{uid}] → EXCEPTION : {type(e).__name__}: {e}")
        return None
    finally:
        time.sleep(SLEEP)


def _resolve_ric(cusip9: str, cusip8: str, ref_date: str | None = None) -> str | None:
    """
    Résout le vrai RIC LSEG à partir du CUSIP, via rd.get_data(TR.RIC).
    [FIX] ref_date : résolution "à la date" via SDate/EDate, pour retrouver
    le RIC archivé des tickers rachetés/délistés depuis la fin du panel.
    """
    uids = [f"CUSIP:{cusip9}", f"CUSIP:{cusip8}"]
    params_variants = [{}]
    if ref_date:
        params_variants = [{"SDate": ref_date, "EDate": ref_date}, {}]

    for uid in uids:
        for params in params_variants:
            resp = _call_lseg(uid, ["TR.RIC"], params, label="resolve_ric")
            if resp is None:
                continue
            for col in ["RIC", "TR.RIC"]:
                if col not in resp.columns:
                    continue
                val = resp.iloc[0][col]
                if val and str(val) not in ("nan", "None", ""):
                    ric = str(val).strip()
                    tag = f"@{ref_date}" if params else "@actif"
                    log.info(f"      ↳ resolve_ric [{uid}{tag}] → RIC trouvé : {ric!r}")
                    return ric
    return None


def _get_cascade(uid_used, cusip9, cusip8, ticker, fields, params, label=""):
    """Cascade get_data() — utilisée pour l'ESG (fallback) et les tests."""
    for uid in _build_id_list(uid_used, cusip9, cusip8, ticker):
        resp = _call_lseg(uid, fields, params, label=label)
        if resp is not None:
            return resp, uid
    return None, ""


def _get_history_with_ric_fallback(
    info: dict,
    fields: list[str],
    interval: str,
    start: str,
    end: str,
    label: str,
) -> tuple[pd.DataFrame | None, str]:
    """
    Tente rd.get_history() sur toute la cascade d'identifiants. Si tout
    échoue, résout le vrai RIC via TR.RIC (_resolve_ric) et retente.
    """
    attempts = _build_id_list(info["uid_used"], info["cusip9"],
                              info["cusip8"], info["ticker"])
    for uid in attempts:
        try:
            df = rd.get_history(
                universe=uid, fields=fields,
                interval=interval, start=start, end=end,
            )
            if df is not None and not df.empty:
                if "esg" in label.lower():
                    _log_cols(f"get_history/{label}", df, uid)
                return df, uid
            log.info(f"      ↳ {label} [{uid}] → vide/None "
                     f"(start={start}, end={end})")
        except Exception as e:
            log.info(f"      ↳ {label} [{uid}] → EXCEPTION : "
                     f"{type(e).__name__}: {e}")
        finally:
            time.sleep(SLEEP)

    log.info(f"      ↳ {label} — cascade échouée ({len(attempts)} uid), "
             f"tentative _resolve_ric (ref_date={end})...")
    ric = _resolve_ric(info["cusip9"], info["cusip8"], ref_date=end)
    if ric:
        try:
            df = rd.get_history(
                universe=ric, fields=fields,
                interval=interval, start=start, end=end,
            )
            if df is not None and not df.empty:
                log.info(f"      ↳ {label} [RIC:{ric}] → ✅ données trouvées")
                if "esg" in label.lower():
                    _log_cols(f"get_history/{label}(RIC)", df, ric)
                return df, f"RIC:{ric}"
            log.info(f"      ↳ {label} [RIC:{ric}] → vide/None après résolution")
        except Exception as e:
            log.info(f"      ↳ {label} [RIC:{ric}] → EXCEPTION : "
                     f"{type(e).__name__}: {e}")
        finally:
            time.sleep(SLEEP)
    else:
        log.info(f"      ↳ {label} — _resolve_ric n'a rien retourné")

    log.info(f"      ↳ {label} — TOUTES tentatives échouées "
             f"({len(attempts)+1} uid essayés : {attempts + [ric or 'None']})")
    return None, ""


# ─────────────────────────────────────────────────────────────────────────────
#  CHARGEMENT DU PANEL
# ─────────────────────────────────────────────────────────────────────────────

def load_panel_tickers(csv_path: str) -> list[dict]:
    """Charge uniquement les tickers in_panel=True du CSV."""
    panel = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("in_panel") or "").strip() != "True":
                continue
            sid = (row.get("secid") or "").strip()
            if not sid:
                continue
            panel.append({
                "ticker":      (row.get("ticker")         or "").strip(),
                "secid":       sid,
                "cusip8":      (row.get("cusip8")         or "").strip(),
                "cusip9":      (row.get("cusip9")         or "").strip(),
                "issuer":      (row.get("issuer")         or "").strip(),
                "uid_used":    (row.get("uid_used")       or "—").strip(),
                "esg_start":   str(ESG_YEAR_START),
                "price_start": max(PANEL_START,
                                   (row.get("price_start_date") or PANEL_START)[:10]),
                "price_end":   PANEL_END,
                "group":       "PANEL",
                "cat":         "PANEL",
                "note":        "",
            })

    log.info(f"Panel (in_panel=True) : {len(panel)} tickers chargés")
    log.info(f"Période prix          : {PANEL_START}  →  {PANEL_END}")
    log.info(f"Période ESG           : {ESG_YEAR_START}  →  {ESG_YEAR_END}\n")

    if DEBUG_TICKER_LIMIT is not None:
        panel = panel[:DEBUG_TICKER_LIMIT]
        log.info(f"[DIAGNOSTIC] DEBUG_TICKER_LIMIT actif → {len(panel)} ticker(s) "
                 f"seulement pour ce run : {[t['ticker'] for t in panel]}\n")

    return panel


# ─────────────────────────────────────────────────────────────────────────────
#  TEST INTRADAY
# ─────────────────────────────────────────────────────────────────────────────

_INTRADAY_FRQ = {"5min":"PT5M","10min":"PT10M","30min":"PT30M","1H":"PT1H"}


def _fetch_intraday_raw(uid: str, start: str, end: str, interval: str, verbose: bool = False):
    frq = _INTRADAY_FRQ.get(interval, interval)
    try:
        df = rd.get_history(
            universe=uid,
            fields=["OPEN_PRC","HIGH_PRC","LOW_PRC","TRDPRC_1","ACVOL_UNS"],
            interval=frq, start=start, end=end,
        )
        if verbose and (df is None or df.empty):
            log.info(f"      ↳ intraday [{uid}, {interval}] → réponse vide/None "
                     f"(start={start}, end={end})")
        return df
    except Exception as e:
        if verbose:
            log.info(f"      ↳ intraday [{uid}, {interval}] → EXCEPTION LSEG : "
                     f"{type(e).__name__}: {e}")
        else:
            log.debug(f"  _fetch_intraday_raw({uid},{interval}): {e}")
        return None
    finally:
        time.sleep(SLEEP)


def test_intraday_intervals(test_uid: str = "AAPL.O") -> str | None:
    log.info("═"*65)
    log.info("  TEST INTRADAY — sélection de l'intervalle optimal")
    log.info(f"  Ticker test : {test_uid}")
    log.info("═"*65)
    for interval in INTRADAY_CANDIDATES:
        df = _fetch_intraday_raw(test_uid, "2023-12-08", "2023-12-15", interval)
        if df is not None and not df.empty:
            log.info(f"  ✅  {interval:6s} → OK ({len(df)} barres) — retenu")
            return interval
        else:
            log.warning(f"  ❌  {interval:6s} → vide ou indisponible")
    log.error("  Aucun intervalle intraday disponible.\n")
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  TÉLÉCHARGEMENTS
# ─────────────────────────────────────────────────────────────────────────────

def download_daily(info: dict) -> pd.DataFrame | None:
    df, uid_ok = _get_history_with_ric_fallback(
        info=info,
        fields=["OPEN_PRC", "HIGH_PRC", "LOW_PRC", "TRDPRC_1", "ACVOL_UNS"],
        interval="1D",
        start=info["price_start"],
        end=info["price_end"],
        label="daily",
    )
    if df is None or df.empty:
        return None
    df.index.name = "Date"
    df.columns    = ["Open", "High", "Low", "Close", "Volume"]
    return df


def download_intraday(info: dict, interval: str) -> pd.DataFrame | None:
    i_start = info["price_start"]
    i_end   = info["price_end"]
    if i_start >= i_end:
        return None

    df_test, uid_ok = _get_history_with_ric_fallback(
        info=info,
        fields=["OPEN_PRC", "HIGH_PRC", "LOW_PRC", "TRDPRC_1", "ACVOL_UNS"],
        interval=_INTRADAY_FRQ.get(interval, interval),
        start="2023-12-08",
        end="2023-12-12",
        label=f"intraday_test({interval})",
    )
    if uid_ok == "":
        return None

    uid_final = uid_ok.removeprefix("RIC:") if uid_ok.startswith("RIC:") else uid_ok

    chunks       = []
    empty_chunks = []
    current = pd.Timestamp(i_start)
    end_dt  = pd.Timestamp(i_end)

    while current < end_dt:
        nxt = (pd.Timestamp(f"{current.year}-{current.month+1:02d}-01")
               if current.month < 12
               else pd.Timestamp(f"{current.year+1}-01-01"))
        chunk_end = min(nxt, end_dt)
        df_c = _fetch_intraday_raw(
            uid_final,
            current.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d"),
            interval,
        )
        if df_c is not None and not df_c.empty:
            chunks.append(df_c)
        else:
            empty_chunks.append(current.strftime("%Y-%m"))
        current = chunk_end

    if not chunks:
        log.info(f"      ↳ intraday [{uid_final}] — TOUS les mois vides "
                 f"({len(empty_chunks)} mois testés)")
        return None
    if empty_chunks:
        log.info(f"      ↳ intraday [{uid_final}] — {len(empty_chunks)} mois vides "
                 f"sur {len(empty_chunks)+len(chunks)} : {empty_chunks}")

    df = pd.concat(chunks).drop_duplicates()
    df.index.name = "Datetime"
    return df


def _expected_esg_years(info: dict) -> list[int]:
    """[FIX] Années ESG attendues = ESG_YEAR_START..ESG_YEAR_END, fenêtre
    ESG indépendante de la fenêtre Prix — ne dépend plus de price_start."""
    return list(range(ESG_YEAR_START, ESG_YEAR_END + 1))


def _download_esg_once(info: dict) -> tuple[pd.DataFrame | None, list[int]]:
    """
    Télécharge les scores ESG annuels, filtrés à [ESG_YEAR_START, ESG_YEAR_END].

    Pourquoi fetch_start = 2 ans avant ESG_YEAR_START et fetch_end = 2 ans
    après ESG_YEAR_END :
      Les scores ESG d'une année N sont publiés par LSEG début N+1 (parfois
      plus tard). Une requête bornée exactement à [ESG_YEAR_START,
      ESG_YEAR_END] exclurait donc structurellement les scores des deux
      années limites. La marge de 2 ans de chaque côté capture les
      publications décalées ; _standardise_esg filtre ensuite strictement
      sur [ESG_YEAR_START, ESG_YEAR_END].

    [FIX] Les deux sources sont TOUJOURS interrogées, puis fusionnées (voir
    _merge_esg_sources) : get_history() souvent sparse (une ligne par
    évènement de publication détecté), get_data(Frq=FY) plus fiable pour
    la complétude année par année.

    Retourne (df_standardisé_ou_None, liste_des_années_manquantes).
    """
    fetch_start   = f"{ESG_YEAR_START - 2}-01-01"
    fetch_end     = f"{ESG_YEAR_END + 2}-12-31"
    expected      = _expected_esg_years(info)

    log.info(f"    [DIAGNOSTIC] download_esg({info['ticker']}) — "
             f"fetch_start={fetch_start}  fetch_end={fetch_end}  expected={expected}")

    # ── 1. get_history() avec fallback RIC ───────────────────────────────────
    raw_hist, _ = _get_history_with_ric_fallback(
        info=info, fields=ESG_FIELDS, interval="1Y",
        start=fetch_start, end=fetch_end, label="esg get_history",
    )
    _log_cols("download_esg/raw_hist(brut)", raw_hist, info["ticker"])
    std_hist = _standardise_esg(raw_hist, info) if raw_hist is not None else None
    _log_cols("download_esg/std_hist(apres standardise)", std_hist, info["ticker"])

    # ── 2. get_data() (SDate/EDate/Frq=FY) — TOUJOURS tenté ──────────────────
    raw_data, _ = _get_cascade(
        info["uid_used"], info["cusip9"], info["cusip8"], info["ticker"],
        fields=ESG_FIELDS,
        params={"SDate": fetch_start, "EDate": fetch_end, "Frq": "FY"},
        label="esg get_data",
    )
    _log_cols("download_esg/raw_data(brut)", raw_data, info["ticker"])
    std_data = _standardise_esg(raw_data, info) if raw_data is not None else None
    _log_cols("download_esg/std_data(apres standardise)", std_data, info["ticker"])

    if (std_hist is None or std_hist.empty) and (std_data is None or std_data.empty):
        log.info(f"      ↳ esg [{info['ticker']}] — TOUTES les tentatives échouées "
                 f"(get_history et get_data vides)")
        return None, expected

    # ── 3. Fusion des deux sources par année (priorité à get_data) ───────────
    merged = _merge_esg_sources(std_hist, std_data)
    _log_cols("download_esg/merged(final)", merged, info["ticker"])

    missing = sorted(set(expected) - set(merged.index.tolist())) if merged is not None else expected
    if missing:
        log.info(f"      ↳ esg [{info['ticker']}] → {len(merged) if merged is not None else 0}"
                 f"/{len(expected)} années obtenues après fusion, "
                 f"années manquantes : {missing}")

    return (merged if merged is not None and not merged.empty else None), missing


# [FIX régression] pause + 1 nouvel essai en cas d'échec total (throttling
# LSEG transitoire, observé après un pic de requêtes en une session).
ESG_RETRY_PAUSE = 5.0


def download_esg(info: dict) -> tuple[pd.DataFrame | None, list[int]]:
    df, missing = _download_esg_once(info)
    if df is None:
        log.info(f"      ↳ esg [{info['ticker']}] — échec total, pause "
                 f"{ESG_RETRY_PAUSE}s puis nouvelle tentative (throttling LSEG possible)...")
        time.sleep(ESG_RETRY_PAUSE)
        df, missing = _download_esg_once(info)
        if df is not None:
            log.info(f"      ↳ esg [{info['ticker']}] — ✅ réussi au 2e essai")
    return df, missing


def _merge_esg_sources(std_hist: pd.DataFrame | None,
                       std_data: pd.DataFrame | None) -> pd.DataFrame | None:
    """Fusionne deux DataFrames ESG standardisés (indexés par Year), en
    donnant priorité aux valeurs de std_data (get_data, Frq=FY)."""
    frames = [df for df in (std_hist, std_data) if df is not None and not df.empty]
    if not frames:
        return None
    if len(frames) == 1:
        log.info(f"      🔍 [_merge_esg_sources] une seule source disponible "
                 f"({'std_hist' if frames[0] is std_hist else 'std_data'}) — pas de fusion")
        return frames[0]

    combined = std_data.combine_first(std_hist)
    for col in ["ticker", "secid", "issuer"]:
        if col in std_data.columns:
            combined[col] = combined[col].combine_first(std_data[col]) if col in combined.columns else std_data[col]
    present = [c for c in ESG_FINAL_COLS if c != "Year" and c in combined.columns]
    log.info(f"      🔍 [_merge_esg_sources] E_Pillar dans std_hist : "
             f"{'E_Pillar' in std_hist.columns if std_hist is not None else 'N/A (None)'}  |  "
             f"dans std_data : {'E_Pillar' in std_data.columns if std_data is not None else 'N/A (None)'}  |  "
             f"dans combined avant filtre 'present' : {'E_Pillar' in combined.columns}")
    return combined[present].sort_index()


ESG_COL_MAP = {
    "TR.TRESGScore":                    "ESG_Score",
    "TR.TRESGScore.Date":               "ESG_Date",
    "TR.EnvironmentPillarScore":        "E_Pillar",
    "TR.SocialPillarScore":             "S_Pillar",
    "TR.GovernancePillarScore":         "G_Pillar",
    "TR.ResourceUseScore":              "ResourceUse",
    "TR.EmissionsScore":                "Emissions",
    "TR.EnvironmentalInnovationScore":  "EnvInnovation",
    "TR.WorkforceScore":                "Workforce",
    "TR.HumanRightsScore":             "HumanRights",
    "TR.CommunityScore":               "Community",
    "TR.ProductResponsibilityScore":   "ProductResponsibility",
    "TR.ManagementScore":              "Management",
    "TR.ShareholdersScore":            "Shareholders",
    "TR.CSRStrategyScore":             "CSRStrategy",
    "TR.TRESGCScore":                  "ESGC_Score",
    "TR.TRESGCScoreGrade":             "ESGC_Grade",
    "ESG Score":                       "ESG_Score",
    "Environment Pillar Score":        "E_Pillar",
    "Environmental Pillar Score":      "E_Pillar",   # [FIX] vrai nom renvoyé par LSEG (avec "al")
    "Social Pillar Score":             "S_Pillar",
    "Governance Pillar Score":         "G_Pillar",
}

ESG_FINAL_COLS = [
    "Year", "ticker", "secid", "issuer",
    "ESG_Score", "ESG_Date",
    "E_Pillar", "S_Pillar", "G_Pillar",
    "ResourceUse", "Emissions", "EnvInnovation",
    "Workforce", "HumanRights", "Community",
    "ProductResponsibility", "Management",
    "Shareholders", "CSRStrategy",
    "ESGC_Score", "ESGC_Grade",
]


def _standardise_esg(raw: pd.DataFrame, info: dict) -> pd.DataFrame | None:
    if raw is None:
        return None

    df = raw.copy()

    e_raw_variants = ["TR.EnvironmentPillarScore", "Environment Pillar Score",
                       "Environmental Pillar Score"]
    present_before = [c for c in e_raw_variants if c in df.columns]
    log.info(f"      🔍 [_standardise_esg/{info['ticker']}] AVANT renommage : "
             f"{len(df.columns)} colonnes, variantes E_Pillar brutes présentes : {present_before}")

    df = df.rename(columns={k: v for k, v in ESG_COL_MAP.items() if k in df.columns})

    log.info(f"      🔍 [_standardise_esg/{info['ticker']}] APRÈS renommage : "
             f"E_Pillar présent = {'E_Pillar' in df.columns}  |  "
             f"colonnes = {list(df.columns)}")

    year_series = None
    if isinstance(df.index, pd.DatetimeIndex):
        year_series = df.index.year
    elif not isinstance(df.index, pd.DatetimeIndex):
        try:
            year_series = pd.to_datetime(df.index, errors="coerce").year
        except Exception:
            pass

    if year_series is None and "ESG_Date" in df.columns:
        try:
            year_series = pd.to_datetime(df["ESG_Date"], errors="coerce").dt.year
        except Exception:
            pass

    if year_series is None:
        log.debug(f"    _standardise_esg: impossible d'extraire l'année pour {info['ticker']}")
        return None

    df["Year"] = year_series.values

    # [FIX] Filtre sur la fenêtre ESG indépendante (2016-2022), plus sur
    # 2017..price_end comme avant.
    df = df[(df["Year"] >= ESG_YEAR_START) & (df["Year"] <= ESG_YEAR_END)].copy()

    if df.empty:
        return None

    df["ticker"] = info["ticker"]
    df["secid"]  = info["secid"]
    df["issuer"] = info["issuer"]

    present = [c for c in ESG_FINAL_COLS if c in df.columns]
    dropped_here = [c for c in df.columns if c not in ESG_FINAL_COLS]
    if dropped_here:
        log.info(f"      🔍 [_standardise_esg/{info['ticker']}] colonnes ÉCARTÉES car absentes "
                 f"de ESG_FINAL_COLS : {dropped_here}")
    df = df[present].copy()
    df = df.sort_values("Year").drop_duplicates(subset=["Year"]).reset_index(drop=True)
    df = df.set_index("Year")

    log.info(f"      🔍 [_standardise_esg/{info['ticker']}] SORTIE FINALE : "
             f"E_Pillar présent = {'E_Pillar' in df.columns}  |  {len(df)} lignes")

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  SAUVEGARDE EXCEL
# ─────────────────────────────────────────────────────────────────────────────

def _write_sheet(writer, df: pd.DataFrame, sheet_name: str,
                 col_widths: dict | None = None) -> None:
    from openpyxl.styles import PatternFill, Font, Alignment
    df.to_excel(writer, sheet_name=sheet_name, index=True)
    ws = writer.sheets[sheet_name]

    hdr_fill = PatternFill("solid", fgColor="1F3864")
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    for cell in ws[1]:
        cell.fill      = hdr_fill
        cell.font      = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for col_cells in ws.columns:
        header  = str(col_cells[0].value or "")
        if col_widths and header in col_widths:
            width = col_widths[header]
        else:
            mx = max((len(str(c.value)) for c in col_cells if c.value), default=8)
            width = min(mx + 2, 40)
        ws.column_dimensions[col_cells[0].column_letter].width = width

    ws.freeze_panes = "B2"


def save_prices(df_daily, df_intraday, path_daily, path_intraday, interval) -> tuple[bool, bool]:
    PRICE_COL_WIDTHS = {
        "Date":12, "Datetime":20,
        "Open":12, "High":12, "Low":12, "Close":12, "Volume":14,
    }

    ok_daily   = False
    ok_intraday = False

    if df_daily is not None and not df_daily.empty:
        try:
            path_daily.parent.mkdir(parents=True, exist_ok=True)
            with pd.ExcelWriter(str(path_daily), engine="openpyxl") as writer:
                _write_sheet(writer, df_daily, "Daily_OHLCV", PRICE_COL_WIDTHS)
            ok_daily = True
        except Exception as e:
            log.error(f"    Sauvegarde {path_daily.name}: {e}")

    if df_intraday is not None and not df_intraday.empty and path_intraday and interval:
        try:
            path_intraday.parent.mkdir(parents=True, exist_ok=True)
            with pd.ExcelWriter(str(path_intraday), engine="openpyxl") as writer:
                _write_sheet(writer, df_intraday,
                             f"Intraday_{interval}", PRICE_COL_WIDTHS)
            ok_intraday = True
        except Exception as e:
            log.error(f"    Sauvegarde {path_intraday.name}: {e}")

    return ok_daily, ok_intraday


def save_esg(df: pd.DataFrame, path: Path) -> bool:
    ESG_COL_WIDTHS = {
        "Year":6, "ticker":9, "secid":9, "issuer":30,
        "ESG_Score":11, "ESG_Date":14,
        "E_Pillar":10, "S_Pillar":10, "G_Pillar":10,
        "ResourceUse":13, "Emissions":11, "EnvInnovation":15,
        "Workforce":11, "HumanRights":13, "Community":11,
        "ProductResponsibility":21, "Management":12,
        "Shareholders":13, "CSRStrategy":13,
        "ESGC_Score":12, "ESGC_Grade":12,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
            _write_sheet(writer, df, "ESG_Scores", ESG_COL_WIDTHS)
        return True
    except Exception as e:
        log.error(f"    Sauvegarde {path.name}: {e}")
        return False


def _safe_name(ticker: str, secid: str) -> str:
    return f"{ticker.replace('/','_')}_{secid}"


def _esg_file_missing_years(path: Path, expected: list[int]) -> list[int] | None:
    try:
        df = pd.read_excel(path)
    except Exception:
        return None
    if df.empty or "Year" not in df.columns:
        return None
    years_present = set(pd.to_numeric(df["Year"], errors="coerce").dropna().astype(int))
    return sorted(set(expected) - years_present)


def _esg_file_has_e_pillar(path: Path) -> bool:
    """[FIX] Un fichier ESG téléchargé AVANT le correctif E_Pillar peut être
    complet en années mais avec E_Pillar totalement vide."""
    try:
        df = pd.read_excel(path)
    except Exception:
        return False
    if "E_Pillar" not in df.columns:
        return False
    return df["E_Pillar"].notna().any()


def main_full_download():
    log.info("═"*70)
    log.info("  TÉLÉCHARGEMENT PANEL — PRIX & ESG")
    log.info(f"  Période Prix  : {PANEL_START}  →  {PANEL_END}")
    log.info(f"  Période ESG   : {ESG_YEAR_START}  →  {ESG_YEAR_END}  (fenêtre indépendante)")
    log.info(f"  CSV           : {CSV_PATH}")
    log.info(f"  Sortie Prix   : {PRICE_OUT}")
    log.info(f"  Sortie ESG    : {ESG_OUT}")
    if DEBUG_TICKER_LIMIT is not None:
        log.info(f"  [DIAGNOSTIC] Limité à {DEBUG_TICKER_LIMIT} ticker(s) pour ce run")
    log.info("═"*70 + "\n")

    log.info("  ── ÉTAPE 1 : Connexion LSEG ──")
    try:
        rd.open_session()
        log.info("  ✅  Session ouverte\n")
    except Exception as e:
        log.warning(f"  ⚠️  rd.open_session(): {e}\n")

    log.info("  ── ÉTAPE 2 : Test des intervalles intraday ──")
    best_interval = test_intraday_intervals("AAPL.O")
    log.info("")

    log.info("  ── ÉTAPE 3 : Chargement du panel ──")
    tickers = load_panel_tickers(CSV_PATH)
    n       = len(tickers)

    log.info(f"  ── ÉTAPE 4 : Téléchargement ({n} tickers) ──\n")
    log.info(f"  {'#':>4}  {'Tk':7}  {'Issuer':36}  {'Daily':11}  {'Intraday':12}  {'ESG':8}")
    log.info("─"*90)

    stats  = Counter()
    failed = []
    i      = 0

    try:
        for i, info in enumerate(tickers, 1):
            ticker = info["ticker"]
            secid  = info["secid"]
            prefix = _safe_name(ticker, secid)
            issuer = info["issuer"][:36]

            daily_path = PRICE_OUT / f"{prefix}_prices_daily.xlsx"
            intra_path = (PRICE_OUT / f"{prefix}_prices_intraday_{best_interval}.xlsx"
                          if best_interval else None)
            esg_path   = ESG_OUT / f"{prefix}_esg.xlsx"

            daily_skip = daily_path.exists()
            intra_skip = (intra_path is not None and intra_path.exists())

            expected_years = _expected_esg_years(info)
            esg_skip = False
            if esg_path.exists():
                missing_on_disk = _esg_file_missing_years(esg_path, expected_years)
                esg_skip = (missing_on_disk == []) and _esg_file_has_e_pillar(esg_path)

            if not (daily_skip and intra_skip and esg_skip):
                log.info(f"  [{i}/{n}] {ticker} — uid_used={info['uid_used']!r}  "
                         f"période={info['price_start']}→{info['price_end']}")

            df_d = None
            df_i = None

            if not daily_skip:
                df_d = download_daily(info)

            if best_interval and not intra_skip:
                df_i = download_intraday(info, best_interval)

            if daily_skip:
                daily_st = "⏩ skip"; stats["daily_ok"] += 1
            elif df_d is not None and not df_d.empty:
                ok_d, _ = save_prices(df_d, None, daily_path, None, None)
                daily_st = f"✅ {len(df_d):>5}j" if ok_d else "❌ save"
                stats["daily_ok" if ok_d else "daily_fail"] += 1
                if not ok_d: failed.append((ticker, "daily_save"))
            else:
                daily_st = "⚠️  vide"; stats["daily_empty"] += 1
                failed.append((ticker, "daily_empty"))

            if not best_interval:
                intra_st = "n/a"
            elif intra_skip:
                intra_st = "⏩ skip"; stats["intra_ok"] += 1
            elif df_i is not None and not df_i.empty:
                _, ok_i = save_prices(None, df_i, daily_path, intra_path, best_interval)
                intra_st = f"✅ {len(df_i):>6}b" if ok_i else "❌ save"
                stats["intra_ok" if ok_i else "intra_fail"] += 1
                if not ok_i: failed.append((ticker, "intraday_save"))
            else:
                intra_st = "⚠️  vide"; stats["intra_empty"] += 1
                failed.append((ticker, "intraday_empty"))

            if esg_skip:
                esg_st = "⏩ skip"; stats["esg_ok"] += 1
            else:
                df_e, missing_years = download_esg(info)
                if df_e is not None and not df_e.empty:
                    ok_e = save_esg(df_e, esg_path)
                    if not ok_e:
                        esg_st = "❌ save"; stats["esg_fail"] += 1
                        failed.append((ticker, "esg_save"))
                    elif missing_years:
                        esg_st = f"⚠️ {len(df_e):>2}/{len(df_e)+len(missing_years)}y"
                        stats["esg_incomplete"] += 1
                        failed.append((ticker, f"esg_incomplete {missing_years}"))
                    else:
                        esg_st = f"✅ {len(df_e):>2}y"
                        stats["esg_ok"] += 1
                else:
                    esg_st = "⚠️  vide"; stats["esg_empty"] += 1
                    failed.append((ticker, "esg_empty"))

            log.info(f"  {i:>4}  {ticker:<7}  {issuer:<36}  "
                     f"{daily_st:>11}  {intra_st:>12}  {esg_st:>8}")
            time.sleep(DELAY_TICKER)

    except KeyboardInterrupt:
        log.warning("\n  ⚠️  Interruption manuelle — sauvegarde en cours...")

    finally:
        try:
            rd.close_session()
        except Exception:
            pass

    log.info(f"\n{'═'*70}")
    log.info("  RAPPORT FINAL")
    log.info(f"{'═'*70}")
    log.info(f"  Tickers traités        : {i}/{n}")
    log.info(f"  Prix daily   ✅:{stats['daily_ok']:3d}  ⚠️:{stats['daily_empty']:3d}  ❌:{stats['daily_fail']:3d}")
    if best_interval:
        log.info(f"  Intraday {best_interval:<5}✅:{stats['intra_ok']:3d}  ⚠️:{stats['intra_empty']:3d}  ❌:{stats['intra_fail']:3d}")
    log.info(f"  ESG          ✅:{stats['esg_ok']:3d}  ⚠️ incomplet:{stats['esg_incomplete']:3d}  "
             f"⚠️ vide:{stats['esg_empty']:3d}  ❌:{stats['esg_fail']:3d}")
    if failed:
        log.info(f"\n  Échecs ({len(failed)}) :")
        for tk, reason in failed:
            log.info(f"    - {tk:<7}  [{reason}]")
    if i < n:
        log.info(f"\n  ▶  {n-i} tickers restants — relancez le script.")
    else:
        log.info("\n  🎉  Tous les tickers ont été traités.")
    log.info(f"{'═'*70}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  MODE "fill_e_pillar"  —  ancien fill_e_pillar.py, inchangé
#  (auto-adapté : lit les années directement depuis chaque fichier existant,
#  donc suit automatiquement la nouvelle fenêtre 2016-2022 sans modification)
# ═══════════════════════════════════════════════════════════════════════════

def _fill_file_key(path: Path) -> str:
    return path.name[: -len(ESG_PROCESSED_SUFFIX)]


def _extract_e_pillar_col(df: pd.DataFrame) -> str | None:
    for c in E_PILLAR_NAME_VARIANTS:
        if c in df.columns:
            return c
    return None


def _fetch_e_pillar_once(ticker: str, fetch_start: str, fetch_end: str) -> dict[int, float]:
    """Retourne {année: valeur E_Pillar}, en tentant get_history puis
    get_data sur une cascade de suffixes de place."""
    for uid in [f"{ticker}{sfx}" for sfx in FILL_EXCHANGE_SUFX]:
        try:
            df = rd.get_history(universe=uid, fields=[E_PILLAR_FIELD],
                                 interval="1Y", start=fetch_start, end=fetch_end)
        except Exception as e:
            df = None
            log.debug(f"      get_history[{uid}] exception: {e}")
        finally:
            time.sleep(FILL_SLEEP)

        if df is not None and not df.empty:
            col = _extract_e_pillar_col(df)
            if col and isinstance(df.index, pd.DatetimeIndex):
                years = df.index.year
                vals = df[col]
                out = {int(y): v for y, v in zip(years, vals) if pd.notna(v)}
                if out:
                    return out

        try:
            df2 = rd.get_data(universe=[uid], fields=[E_PILLAR_FIELD],
                               parameters={"SDate": fetch_start, "EDate": fetch_end, "Frq": "FY"})
        except Exception as e:
            df2 = None
            log.debug(f"      get_data[{uid}] exception: {e}")
        finally:
            time.sleep(FILL_SLEEP)

        if df2 is not None and not df2.empty:
            col = _extract_e_pillar_col(df2)
            date_col = "Date" if "Date" in df2.columns else None
            if col and date_col:
                years = pd.to_datetime(df2[date_col], errors="coerce").dt.year
                vals = df2[col]
                out = {int(y): v for y, v in zip(years, vals) if pd.notna(y) and pd.notna(v)}
                if out:
                    return out

    return {}


def fetch_e_pillar(ticker: str, fetch_start: str, fetch_end: str) -> dict[int, float]:
    result = _fetch_e_pillar_once(ticker, fetch_start, fetch_end)
    if not result:
        log.info(f"      ↳ {ticker} — échec total, pause {FILL_RETRY_PAUSE}s puis nouvel essai...")
        time.sleep(FILL_RETRY_PAUSE)
        result = _fetch_e_pillar_once(ticker, fetch_start, fetch_end)
        if result:
            log.info(f"      ↳ {ticker} — ✅ réussi au 2e essai")
    return result


def main_fill_e_pillar():
    files = sorted(ESG_PROCESSED_DIR.glob(f"*{ESG_PROCESSED_SUFFIX}"))
    log.info("=" * 74)
    log.info(f"  {len(files)} fichiers dans 02_Processed\\ESG — ajout de E_Pillar")
    log.info("=" * 74)

    rd.open_session()

    ok, empty, already_had = [], [], []
    try:
        for i, f in enumerate(files, 1):
            key = _fill_file_key(f)
            ticker = key.rsplit("_", 1)[0]

            df = pd.read_excel(f)
            if "E_Pillar" in df.columns and df["E_Pillar"].notna().all():
                already_had.append(key)
                continue

            years_present = sorted(pd.to_numeric(df["Year"], errors="coerce").dropna().astype(int).tolist())
            fetch_start = f"{min(years_present) - 2}-01-01"
            fetch_end   = f"{max(years_present) + 2}-12-31"

            log.info(f"  [{i}/{len(files)}] {ticker} — fenêtre {fetch_start} → {fetch_end}")
            e_values = fetch_e_pillar(ticker, fetch_start, fetch_end)

            if not e_values:
                empty.append(key)
                log.warning(f"      ⚠️  {ticker} — aucune valeur E_Pillar récupérée")
                continue

            new_col = df["Year"].map(e_values)
            if "E_Pillar" in df.columns:
                df["E_Pillar"] = df["E_Pillar"].combine_first(new_col)
            else:
                df["E_Pillar"] = new_col
            cols = list(df.columns)
            cols.remove("E_Pillar")
            insert_at = cols.index("S_Pillar") if "S_Pillar" in cols else len(cols)
            cols.insert(insert_at, "E_Pillar")
            df = df[cols]

            df.to_excel(f, index=False)
            n_filled = df["E_Pillar"].notna().sum()
            ok.append(key)
            log.info(f"      ✅  {ticker} — E_Pillar rempli sur {n_filled}/{len(df)} années")

    finally:
        rd.close_session()

    log.info("")
    log.info("  RAPPORT FINAL")
    log.info("=" * 74)
    log.info(f"  Déjà rempli (ignoré)   : {len(already_had)}")
    log.info(f"  E_Pillar ajouté        : {len(ok)}")
    log.info(f"  Échec (aucune valeur)  : {len(empty)}")
    if empty:
        log.info("")
        log.info("  Tickers en échec :")
        for k in empty:
            log.info(f"    - {k}")
    log.info("=" * 74)


# ═══════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main_full_download()
    main_fill_e_pillar()