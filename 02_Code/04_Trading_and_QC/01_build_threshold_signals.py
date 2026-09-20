# This code was developed with the assistance of an AI.

import pandas as pd, numpy as np, os, sys

BASE=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis"
SRC=os.path.join(BASE,"black76_pricing_336.csv")
TH=float(sys.argv[1])
tag=str(TH).replace(".","p")
OUT=os.path.join(BASE, "strategy_signals_336.csv" if abs(TH-1.5) < 1e-12 else f"strategy_signals_threshold_{tag}_336.csv")

df=pd.read_csv(SRC)
df["date"]=pd.to_datetime(df.date)
df=df.sort_values(["ticker","model","date"]).copy()
df["gap"]=df.forecast_vol-df.iv_midpoint
df["gap_sd"]=df.groupby(["ticker","model"])["gap"].transform(
    lambda s:s.shift(1).rolling(252,min_periods=126).std()
)
df["z"]=df.gap/df.gap_sd
df["signal"]=np.where(df.z>=TH,1,np.where(df.z<=-TH,-1,0))
df=df[df.signal!=0].copy()
df["direction"]=np.where(df.signal>0,"LONG_VOL","SHORT_VOL")
df["target_exdate"]=df.exdate
df["target_strike"]=df.strike_price
df["target_dte"]=df.dte
df["target_fwd"]=df.fwd
df["target_vega"]=df.straddle_vega
df["vega_ratio"]=np.nan
df["hedge_units"]=np.nan
cols=["ticker","date","model","direction","exdate","strike_price","dte","fwd",
      "straddle_vega","signal","z","rf","target_exdate","target_strike",
      "target_dte","target_fwd","target_vega","vega_ratio","hedge_units"]
df[cols].to_csv(OUT,index=False)
print("OUT",OUT,"ROWS",len(df),"TICKERS",df.ticker.nunique())
