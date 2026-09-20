# This code was developed with the assistance of an AI.

import pandas as pd,numpy as np
from pathlib import Path
import statsmodels.api as sm
R=Path(r'C:\ThesisRebuild'); O=R/'03_Volatility_OOS_LOWER10_FULL'/'final'/'oos_volatility_345_v3.csv'; T=R/'05_Returns'/'returns_log_pct_345_wide.csv'; out=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Outputs\Tables')
r=pd.read_csv(T,parse_dates=['Date']); cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
if 'ticker' not in r.columns:r=r.rename(columns={r.columns[1]:'ticker'}); cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
l=r.melt(id_vars='Date',value_vars=cols,var_name='ticker',value_name='ret').sort_values(['ticker','Date']); l.ret=pd.to_numeric(l.ret,errors='coerce'); l['rv21']=l.groupby('ticker').ret.transform(lambda x:x.pow(2).rolling(21,min_periods=21).mean()); mk=l.groupby('Date').rv21.median().dropna(); a,b=mk.quantile([1/3,2/3]); reg=pd.cut(mk,[-np.inf,a,b,np.inf],labels=['Low','Medium','High'])
o=pd.read_csv(O,parse_dates=['Date']).merge(l[['Date','ticker','ret']],on=['Date','ticker'],how='left').merge(reg.rename('regime'),left_on='Date',right_index=True,how='left'); o['loss']=(o.ret.pow(2)-o.forecast_var_pct2).pow(2)
pairs=[('GARCH','ESG-GARCH'),('GARCH','ESG-GARCH(E)'),('GARCH','ESG-GARCH(S)'),('GARCH','ESG-GARCH(G)'),('GJR-GARCH','ESG-GJR-GARCH'),('GJR-GARCH','ESG-GJR-GARCH(E)'),('GJR-GARCH','ESG-GJR-GARCH(S)'),('GJR-GARCH','ESG-GJR-GARCH(G)'),('EGARCH','ESG-EGARCH'),('EGARCH','ESG-EGARCH(E)'),('EGARCH','ESG-EGARCH(S)'),('EGARCH','ESG-EGARCH(G)')]
rows=[]
for rg in ['Low','Medium','High']:
 z=o[o.regime==rg]
 for base,esg in pairs:
  d=z[z.model==esg][['Date','ticker','loss']].merge(z[z.model==base][['Date','ticker','loss']],on=['Date','ticker'],suffixes=('_e','_b')); daily=d.assign(diff=d.loss_e-d.loss_b).groupby('Date')['diff'].mean().dropna(); fit=sm.OLS(daily.values,np.ones((len(daily),1))).fit(cov_type='HAC',cov_kwds={'maxlags':21}); rows.append([rg,base,esg,len(daily),daily.mean(),fit.tvalues[0],fit.pvalues[0],(daily<0).mean()])
res=pd.DataFrame(rows,columns=['regime','baseline','esg_model','N_days','mean_daily_loss_diff','DM_t_HAC21','p_value','share_days_ESG_better']); res.to_csv(out/'regime_dm_daily_esg_vs_baseline_lower10.csv',index=False); print(res.to_string(index=False)); print('THRESHOLDS',a,b)
