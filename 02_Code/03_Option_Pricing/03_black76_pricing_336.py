# This code was developed with the assistance of an AI.

import os
import numpy as np
import pandas as pd
from scipy.special import ndtr

BASE = r'C:\ThesisRebuild\04_Options_Analysis'
OPT = os.path.join(BASE, 'atm30_callput_options_342.csv')
OOS = os.path.join(BASE, 'oos_options_merged_342.csv')
RF = os.path.join(BASE, 'US10Y_risk_free_rate_2010_2019.xlsx')
OUT = os.path.join(BASE, 'black76_pricing_336.csv')
SUMMARY = os.path.join(BASE, 'black76_pricing_summary_336.csv')

print('Loading Call/Put observations...')
opt = pd.read_csv(OPT, parse_dates=['date','exdate'])
opt['date'] = pd.to_datetime(opt['date'])
opt['dte'] = pd.to_numeric(opt['dte'], errors='coerce')
opt['strike_price'] = pd.to_numeric(opt['strike_price'], errors='coerce')
opt['fwd'] = pd.to_numeric(opt['fwd'], errors='coerce')
opt['mid'] = pd.to_numeric(opt['mid'], errors='coerce')
opt['cp_flag'] = opt['cp_flag'].astype(str).str.upper()

# Pivot the observed premiums so each firm-date has a simultaneous call and put.
key = ['ticker','date','exdate','strike_price']
pv = opt.pivot_table(index=key, columns='cp_flag', values=['mid','iv','oi','spread_rel'], aggfunc='first').reset_index()
pv.columns = [f'{c[0]}_{c[1]}'.strip('_') if isinstance(c, tuple) else str(c) for c in pv.columns]
# Recover common contract metadata from the original rows.
meta = opt.groupby(key, as_index=False).agg(dte=('dte','first'), fwd=('fwd','first'))
pv = pv.merge(meta, on=key, how='inner')
for c in ['mid_C','mid_P','iv_C','iv_P','oi_C','oi_P','spread_rel_C','spread_rel_P']:
    if c not in pv: pv[c] = np.nan
pv = pv.dropna(subset=['mid_C','mid_P','fwd','strike_price','dte'])
pv = pv[(pv['mid_C']>0)&(pv['mid_P']>0)&(pv['fwd']>0)&(pv['strike_price']>0)&(pv['dte']>0)].copy()
print('Observed straddles:', len(pv), 'rows;', pv.ticker.nunique(), 'tickers')

# Exact-date risk-free rate: no interpolation or look-ahead filling.
rf = pd.read_excel(RF, usecols=['Date','yield_decimal'])
rf['date'] = pd.to_datetime(rf['Date'])
rf['r'] = pd.to_numeric(rf['yield_decimal'], errors='coerce')
rf = rf[['date','r']].dropna().drop_duplicates('date')
pv = pv.merge(rf, on='date', how='inner')
print('After exact risk-free match:', len(pv), 'rows; missing RF dates:', pv.r.isna().sum())

# Merge OOS forecasts model-by-model. The OOS file already contains all 15 models.
use = ['ticker','date','model','forecast_vol','esg_spec']
parts=[]
for ch in pd.read_csv(OOS, usecols=use, chunksize=500000):
    ch['date'] = pd.to_datetime(ch['date'])
    parts.append(ch)
oos = pd.concat(parts, ignore_index=True)
oos['forecast_vol'] = pd.to_numeric(oos['forecast_vol'], errors='coerce')
oos = oos.dropna(subset=['forecast_vol'])

m = pv.merge(oos, on=['ticker','date'], how='inner')
print('Pricing panel:', len(m), 'rows;', m.ticker.nunique(), 'tickers;', m.model.nunique(), 'models')

T = m['dte'].to_numpy(dtype=float) / 365.0
F = m['fwd'].to_numpy(dtype=float)
K = m['strike_price'].to_numpy(dtype=float)
r = m['r'].to_numpy(dtype=float)
sig = m['forecast_vol'].to_numpy(dtype=float)
sqrtT = np.sqrt(T)
valid = (T>0)&(F>0)&(K>0)&(sig>0)&np.isfinite(r)
m = m.loc[valid].copy()
T=T[valid]; F=F[valid]; K=K[valid]; r=r[valid]; sig=sig[valid]; sqrtT=sqrtT[valid]

disc = np.exp(-r*T)
d1 = (np.log(F/K) + 0.5*sig*sig*T)/(sig*sqrtT)
d2 = d1 - sig*sqrtT
N1 = ndtr(d1); N2 = ndtr(d2)
phi = np.exp(-0.5*d1*d1)/np.sqrt(2*np.pi)
call = disc*(F*N1 - K*N2)
put = disc*(K*ndtr(-d2) - F*ndtr(-d1))
call_delta = disc*N1
put_delta = -disc*ndtr(-d1)
vega = disc*F*phi*sqrtT

m['rf']=r
m['T']=T
m['df']=disc
m['d1']=d1
m['d2']=d2
m['bs76_call']=call
m['bs76_put']=put
m['bs76_straddle']=call+put
m['observed_straddle']=m['mid_C']+m['mid_P']
m['straddle_mispricing']=m['observed_straddle']-m['bs76_straddle']
m['straddle_mispricing_pct']=m['straddle_mispricing']/m['bs76_straddle'].replace(0,np.nan)
m['call_delta']=call_delta
m['put_delta']=put_delta
m['straddle_delta']=call_delta+put_delta
m['call_vega']=vega
m['put_vega']=vega
m['straddle_vega']=2*vega
m['iv_midpoint']=(m['iv_C']+m['iv_P'])/2
m['observed_spread_rel_mean']=(m['spread_rel_C']+m['spread_rel_P'])/2

cols=['ticker','date','model','esg_spec','exdate','dte','strike_price','fwd','rf','T','df','mid_C','mid_P','iv_C','iv_P','iv_midpoint','oi_C','oi_P','observed_spread_rel_mean','forecast_vol','d1','d2','bs76_call','bs76_put','bs76_straddle','observed_straddle','straddle_mispricing','straddle_mispricing_pct','call_delta','put_delta','straddle_delta','call_vega','put_vega','straddle_vega']
m[cols].to_csv(OUT,index=False)
summary=(m.groupby('model').agg(N=('straddle_mispricing','size'),Tickers=('ticker','nunique'),Observed_Straddle=('observed_straddle','mean'),Model_Straddle=('bs76_straddle','mean'),Mispricing_Mean=('straddle_mispricing','mean'),Mispricing_Median=('straddle_mispricing','median'),Mispricing_Std=('straddle_mispricing','std'),Mispricing_Q05=('straddle_mispricing',lambda x:x.quantile(.05)),Mispricing_Q95=('straddle_mispricing',lambda x:x.quantile(.95)),Forecast_Vol=('forecast_vol','mean')).reset_index())
summary.to_csv(SUMMARY,index=False)
print('WROTE',len(m),'pricing rows;',m.ticker.nunique(),'tickers;',m.model.nunique(),'models')
print('OUTPUT',OUT)
print('SUMMARY',SUMMARY)
