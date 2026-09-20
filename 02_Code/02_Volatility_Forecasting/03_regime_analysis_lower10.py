# This code was developed with the assistance of an AI.

import pandas as pd, numpy as np, os
from pathlib import Path
ROOT=Path(r'C:\ThesisRebuild')
OOS=ROOT/'03_Volatility_OOS_LOWER10_FULL'/'final'/'oos_volatility_345_v3.csv'
RET=ROOT/'05_Returns'/'returns_log_pct_345_wide.csv'
OUT=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Outputs')
TAB=OUT/'Tables'; FIG=OUT/'Figures'
TAB.mkdir(parents=True,exist_ok=True); FIG.mkdir(parents=True,exist_ok=True)
# Returns are percentage units; build ex-post descriptive market-volatility regime.
r=pd.read_csv(RET,parse_dates=['Date'])
ret_cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
if 'ticker' not in r.columns:
    r=r.rename(columns={r.columns[1]:'ticker'})
ret_cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
long=r.melt(id_vars=['Date'],value_vars=ret_cols,var_name='ticker',value_name='ret')
long['ret']=pd.to_numeric(long['ret'],errors='coerce')
long=long.sort_values(['ticker','Date'])
long['rv21']=long.groupby('ticker')['ret'].transform(lambda x:x.pow(2).rolling(21,min_periods=21).mean())
market=long.groupby('Date')['rv21'].median().dropna()
q1,q2=market.quantile([1/3,2/3])
market_reg=pd.cut(market,[-np.inf,q1,q2,np.inf],labels=['Low','Medium','High'])
print('REGIME THRESHOLDS',q1,q2)
o=pd.read_csv(OOS,parse_dates=['Date'])
o=o.merge(long[['Date','ticker','ret']],on=['Date','ticker'],how='left',validate='many_to_one')
o=o.merge(market_reg.rename('regime'),left_on='Date',right_index=True,how='left')
o['rv']=o['ret'].pow(2); o['err2']=(o['rv']-o['forecast_var_pct2']).pow(2)
o['abs_err_var']=(o['rv']-o['forecast_var_pct2']).abs()
o['abs_err_vol']=(np.sqrt(o['rv'].clip(lower=0))-o['forecast_vol'].abs()).abs()
models=sorted(o['model'].dropna().unique())
rows=[]
for reg in ['Low','Medium','High']:
    z=o[o.regime==reg]
    for m in models:
        x=z[z.model==m]
        rows.append([reg,m,len(x),x.err2.mean(),x.abs_err_var.mean(),x.abs_err_vol.mean(),x.forecast_vol.mean(),x.rv.mean()])
res=pd.DataFrame(rows,columns=['regime','model','N','MSE_var','MAE_var','MAE_vol','Mean_forecast_vol','Mean_realized_var'])
res.to_csv(TAB/'regime_forecast_performance_lower10.csv',index=False)
# Family/pillar comparison: ESG vs matching baseline within each regime.
pairs=[('GARCH','ESG-GARCH'),('GARCH','ESG-GARCH(E)'),('GARCH','ESG-GARCH(S)'),('GARCH','ESG-GARCH(G)'),('GJR-GARCH','ESG-GJR-GARCH'),('GJR-GARCH','ESG-GJR-GARCH(E)'),('GJR-GARCH','ESG-GJR-GARCH(S)'),('GJR-GARCH','ESG-GJR-GARCH(G)'),('EGARCH','ESG-EGARCH'),('EGARCH','ESG-EGARCH(E)'),('EGARCH','ESG-EGARCH(S)'),('EGARCH','ESG-EGARCH(G)')]
rows=[]
for reg in ['Low','Medium','High']:
    z=o[o.regime==reg]
    for base,esg in pairs:
        a=z[z.model==base][['Date','ticker','err2']].rename(columns={'err2':'base_loss'})
        b=z[z.model==esg][['Date','ticker','err2']].rename(columns={'err2':'esg_loss'})
        d=a.merge(b,on=['Date','ticker'],how='inner'); diff=d.esg_loss-d.base_loss
        rows.append([reg,base,esg,len(d),diff.mean(),diff.median(),(diff<0).mean()])
pairres=pd.DataFrame(rows,columns=['regime','baseline','esg_model','N','mean_loss_diff','median_loss_diff','share_ESG_better'])
pairres.to_csv(TAB/'regime_esg_vs_baseline_lower10.csv',index=False)
print(res.sort_values(['regime','MSE_var']).groupby('regime').head(5).to_string(index=False))
print(pairres.to_string(index=False))
