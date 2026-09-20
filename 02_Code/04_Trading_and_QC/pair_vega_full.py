import pandas as pd, numpy as np
from scipy.stats import norm
src=r'C:\ThesisRebuild\04_Options_Analysis\strategy_signals_336.csv'; hp=r'C:\ThesisRebuild\04_Options_Analysis\vega_candidates_all_expiries_342.csv'; out=r'C:\ThesisRebuild\04_Options_Analysis\strategy_signals_vega_hedge_full_336.csv'
s=pd.read_csv(src); h=pd.read_csv(hp); s['date']=pd.to_datetime(s.date); s['exdate']=pd.to_datetime(s.exdate); h['date']=pd.to_datetime(h.date); h['exdate']=pd.to_datetime(h.exdate)
exp=h[['ticker','date','exdate']].drop_duplicates().sort_values(['ticker','date','exdate']); expiry_map={(t,d):g.exdate.to_numpy() for (t,d),g in exp.groupby(['ticker','date'],sort=False)}
def nxt(row):
 a=expiry_map.get((row.ticker,row.date))
 if a is None:return pd.NaT
 i=np.searchsorted(a,row.target_exdate.to_datetime64(),side='right'); return a[i] if i<len(a) else pd.NaT
c=s[['ticker','date','model','direction','exdate','strike_price','dte','fwd','straddle_vega','signal','z','rf']].rename(columns={'exdate':'target_exdate','strike_price':'target_strike','dte':'target_dte','fwd':'target_fwd','straddle_vega':'target_vega'}).copy(); c['exdate']=c.apply(nxt,axis=1); c=c.dropna(subset=['exdate']); c['exdate']=pd.to_datetime(c.exdate)
h2=h.merge(c[['ticker','date','exdate']].drop_duplicates(),on=['ticker','date','exdate'],how='inner'); h2['strike_dist']=np.abs(np.log(h2.strike_price/h2.fwd)); h2=h2.sort_values(['ticker','date','exdate','strike_dist']).drop_duplicates(['ticker','date','exdate'],keep='first')
idx=h2.set_index(['ticker','date','exdate','strike_price']).index; pv=h[h.set_index(['ticker','date','exdate','strike_price']).index.isin(idx)].copy(); pv=pv.pivot_table(index=['ticker','date','exdate','strike_price'],columns='cp_flag',values=['fwd','iv','mid','oi','spread_rel'],aggfunc='first').reset_index(); pv.columns=[(x[0]+'_'+x[1]) if isinstance(x,tuple) and x[1] else x[0] for x in pv.columns]; pv=pv.dropna(subset=['iv_C','iv_P']).rename(columns={'fwd_C':'hedge_fwd'})
# Merge only on the selected hedge expiry; strike_price belongs to the hedge, not the target signal.
m=c.merge(pv,on=['ticker','date','exdate'],how='inner'); m['iv_h']=(m.iv_C+m.iv_P)/2; T=(m.exdate-m.date).dt.days/365; F=m.hedge_fwd; K=m.strike_price; sig=m.iv_h; m['d1_h']=(np.log(F/K)+.5*sig**2*T)/(sig*np.sqrt(T)); m['hedge_vega']=np.exp(-m.rf*T)*F*norm.pdf(m.d1_h)*np.sqrt(T); m=m[np.isfinite(m.hedge_vega)&(m.hedge_vega>0)&np.isfinite(m.target_vega)].copy(); m['vega_ratio']=m.target_vega/m.hedge_vega; m['hedge_units']=-m.signal*m.vega_ratio
keys=['ticker','date','model']; paired=m[keys].drop_duplicates(); chk=s.merge(paired,on=keys,how='left',indicator=True); print('SIGNALS',len(s),'PAIRED',len(paired),'TICKERS',paired.ticker.nunique(),'UNPAIRED',int((chk._merge=='left_only').sum())); print('RATIO',m.vega_ratio.describe()[['count','mean','50%','min','max']].to_dict()); m.to_csv(out,index=False); print('OUT',out)
