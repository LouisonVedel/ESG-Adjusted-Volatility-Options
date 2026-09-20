import pandas as pd, numpy as np
from scipy.stats import norm
src=r'C:\ThesisRebuild\04_Options_Analysis\strategy_signals_336.csv'; hp=r'C:\ThesisRebuild\04_Options_Analysis\atm60_callput_options_342.csv'; out=r'C:\ThesisRebuild\04_Options_Analysis\strategy_signals_vega_hedge_336.csv'
s=pd.read_csv(src); h=pd.read_csv(hp)
s['date']=pd.to_datetime(s.date); h['date']=pd.to_datetime(h.date); h['exdate']=pd.to_datetime(h.exdate)
hpv=h.pivot_table(index=['ticker','date','exdate','strike_price'],columns='cp_flag',values=['fwd','iv','mid','oi','spread_rel'],aggfunc='first').reset_index()
hpv.columns=['_'.join([str(x) for x in c if str(x)!='']) if isinstance(c,tuple) else c for c in hpv.columns]
hpv=hpv.rename(columns={'fwd_C':'fwd','iv_C':'iv_C','iv_P':'iv_P','mid_C':'mid_C','mid_P':'mid_P','oi_C':'oi_C','oi_P':'oi_P','spread_rel_C':'spread_C','spread_rel_P':'spread_P'})
hpv=hpv.dropna(subset=['mid_C','mid_P','iv_C','iv_P'])
hpv['dte']=(hpv.exdate-hpv.date).dt.days; hpv['target_distance']=(hpv.dte-60).abs()
c=s[['ticker','date','model','direction','exdate','strike_price','dte','fwd','straddle_vega','signal','z','rf']].copy()
c=c.rename(columns={'exdate':'target_exdate','strike_price':'target_strike','dte':'target_dte','fwd':'target_fwd','straddle_vega':'target_vega'})
m=c.merge(hpv,on=['ticker','date'],how='left'); m=m[m.exdate>m.target_exdate].copy()
m['strike_dist']=(np.log(m.strike_price/m.target_fwd)).abs()
m=m.sort_values(['ticker','date','model','target_exdate','target_strike','target_dte','target_distance','strike_dist']).drop_duplicates(['ticker','date','model'],keep='first')
m['iv_h']=(m.iv_C+m.iv_P)/2; T=m.dte/365; sig=m.iv_h; F=m.fwd; K=m.strike_price
m['d1_h']=(np.log(F/K)+0.5*sig**2*T)/(sig*np.sqrt(T)); m['hedge_vega']=np.exp(-m.rf*T)*F*norm.pdf(m.d1_h)*np.sqrt(T)
m['vega_ratio']=m.target_vega/m.hedge_vega; m['hedge_units']=-m['signal']*m['vega_ratio']
m.to_csv(out,index=False)
print('SIGNALS',len(s),'PAIRED',len(m),'TICKERS',m.ticker.nunique())
print('UNPAIRED',s.merge(m[['ticker','date','model']],on=['ticker','date','model'],how='left',indicator=True)['_merge'].eq('left_only').sum())
print('RATIO',m.vega_ratio.describe()[['count','mean','50%','min','max']].to_dict()); print('OUT',out)
