import os, glob, time
import numpy as np
import pandas as pd
from scipy.stats import norm

BASE = r"C:\ThesisRebuild\04_Options_Analysis"
RAW = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Options_Clean"
RF = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\RiskFree\US10Y_risk_free_rate.xlsx"
OOS = os.path.join(BASE, "oos_options_merged_342.csv")
ATM = os.path.join(BASE, "atm30_options_342.csv")
OUT = os.path.join(BASE, "bs_pricing_342.csv")

# Canonical option date/exdate/strike selection comes from the locked ATM30 dataset.
atm = pd.read_csv(ATM, parse_dates=["date", "exdate"])
atm["key"] = (atm["date"].dt.strftime("%Y%m%d") + "|" +
               atm["exdate"].dt.strftime("%Y%m%d") + "|" +
               atm["strike_price"].round(6).astype(str))
keys = {t: set(g["key"]) for t, g in atm.groupby("ticker")}
print(f"Canonical ATM30 rows: {len(atm):,} / {atm.ticker.nunique()} tickers")

# Risk-free rate: exact date when available; otherwise backward as-of (never future information).
rf = pd.read_excel(RF)
rf["Date"] = pd.to_datetime(rf["Date"])
rf["yield_decimal"] = pd.to_numeric(rf["yield_decimal"], errors="coerce")
rf = rf[["Date", "yield_decimal"]].dropna().drop_duplicates("Date").sort_values("Date")
rf = rf.rename(columns={"Date":"date", "yield_decimal":"rf"})

# Extract separate call and put mids for the exact canonical contract selected above.
rows = []
files = glob.glob(os.path.join(RAW, "*_options.csv"))
for i, f in enumerate(files, 1):
    ticker = os.path.basename(f).split("_")[0]
    if ticker not in keys:
        continue
    wanted = keys[ticker]
    found = []
    try:
        for ch in pd.read_csv(f, usecols=["date","exdate","cp_flag","strike_price","best_bid","best_offer"],
                              dtype=str, chunksize=250000, engine="python", on_bad_lines="skip"):
            ch["date"] = pd.to_datetime(ch["date"], format="%Y%m%d", errors="coerce")
            ch["exdate"] = pd.to_datetime(ch["exdate"], format="%Y%m%d", errors="coerce")
            ch["strike_price"] = pd.to_numeric(ch["strike_price"], errors="coerce") / 1000.0
            ch["bid"] = pd.to_numeric(ch["best_bid"], errors="coerce")
            ch["ask"] = pd.to_numeric(ch["best_offer"], errors="coerce")
            ch["mid"] = (ch["bid"] + ch["ask"]) / 2.0
            ch = ch[ch["mid"] > 0].copy()
            ch["key"] = (ch["date"].dt.strftime("%Y%m%d") + "|" +
                          ch["exdate"].dt.strftime("%Y%m%d") + "|" +
                          ch["strike_price"].round(6).astype(str))
            ch = ch[ch["key"].isin(wanted)]
            if len(ch):
                found.append(ch[["date","exdate","strike_price","cp_flag","mid"]])
        if found:
            g = pd.concat(found, ignore_index=True)
            g["cp"] = g["cp_flag"].str.upper().map({"C":"call","P":"put"})
            g = g.dropna(subset=["cp"])
            # If multiple records exist for the same contract, average the available quoted mids.
            g = g.groupby(["date","exdate","strike_price","cp"], as_index=False)["mid"].mean()
            p = g.pivot_table(index=["date","exdate","strike_price"], columns="cp", values="mid", aggfunc="first").reset_index()
            p.columns.name = None
            p["ticker"] = ticker
            rows.append(p)
    except Exception as e:
        print(f"ERROR {ticker}: {e}")
    if i % 25 == 0:
        print(f"Processed raw files: {i}/{len(files)} | matched tickers: {len(rows)}")

opt = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
if opt.empty:
    raise RuntimeError("No call/put observations recovered")
opt = opt.merge(atm[["ticker","date","exdate","strike_price","dte","fwd","iv","oi","n_contracts","n_cp","spread_rel"]],
                on=["ticker","date","exdate","strike_price"], how="inner")
# Require both legs for a genuine straddle; no synthetic/imputed missing leg.
opt = opt.dropna(subset=["call","put","fwd","dte"])

# Risk-free rate: backward as-of join by date.
opt = opt.sort_values("date")
opt = pd.merge_asof(opt, rf, on="date", direction="backward", tolerance=pd.Timedelta(days=7))
opt = opt.dropna(subset=["rf"])
opt["T"] = opt["dte"] / 365.0
opt["df"] = np.exp(-opt["rf"] * opt["T"])

# Attach all 15 OOS forecasts at the same ticker/date.
oos = pd.read_csv(OOS, parse_dates=["date"])
oos = oos[["ticker","date","model","forecast_vol","RIC","esg_spec","refit_date"]]
opt = opt.merge(oos, on=["ticker","date"], how="inner")
opt = opt[opt["forecast_vol"] > 0].copy()

# Black-76 / forward Black-Scholes formulation, appropriate when a forward is directly observed.
# C = DF [F N(d1) - K N(d2)], P = DF [K N(-d2) - F N(-d1)].
sigma = opt["forecast_vol"].to_numpy(float)
F = opt["fwd"].to_numpy(float)
K = opt["strike_price"].to_numpy(float)
T = opt["T"].to_numpy(float)
DF = opt["df"].to_numpy(float)
sqrtT = np.sqrt(T)
d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * sqrtT)
d2 = d1 - sigma * sqrtT
Nd1, Nd2 = norm.cdf(d1), norm.cdf(d2)
call_bs = DF * (F * Nd1 - K * Nd2)
put_bs = DF * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
opt["bs_call"] = call_bs
opt["bs_put"] = put_bs
opt["obs_straddle"] = opt["call"] + opt["put"]
opt["bs_straddle"] = opt["bs_call"] + opt["bs_put"]
opt["call_mispricing"] = opt["call"] - opt["bs_call"]
opt["put_mispricing"] = opt["put"] - opt["bs_put"]
opt["straddle_mispricing"] = opt["obs_straddle"] - opt["bs_straddle"]
opt["straddle_mispricing_pct"] = opt["straddle_mispricing"] / opt["bs_straddle"].replace(0, np.nan)

# Forward-model Greeks for future hedging work.
opt["delta_call"] = DF * Nd1
opt["delta_put"] = DF * (Nd1 - 1.0)
opt["vega"] = DF * F * norm.pdf(d1) * sqrtT

keep = ["ticker","date","exdate","dte","strike_price","fwd","rf","T","df","iv","call","put","obs_straddle",
        "model","forecast_vol","esg_spec","refit_date","bs_call","bs_put","bs_straddle","call_mispricing","put_mispricing",
        "straddle_mispricing","straddle_mispricing_pct","delta_call","delta_put","vega","oi","n_contracts","n_cp","spread_rel"]
opt[keep].to_csv(OUT, index=False)

print("\nFINAL BS PRICING")
print(f"Rows: {len(opt):,}")
print(f"Tickers: {opt.ticker.nunique()}")
print(f"Models: {opt.model.nunique()}")
print(f"Dates: {opt.date.min().date()} -> {opt.date.max().date()}")
print(f"Mean observed straddle: {opt.obs_straddle.mean():.6f}")
print(f"Mean BS straddle: {opt.bs_straddle.mean():.6f}")
print(f"Mean straddle mispricing: {opt.straddle_mispricing.mean():.6f}")
print(f"Output: {OUT}")
