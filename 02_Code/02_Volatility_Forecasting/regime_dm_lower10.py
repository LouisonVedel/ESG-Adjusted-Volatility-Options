import pandas as pd, numpy as np
from pathlib import Path
import statsmodels.api as sm
ROOT=Path(r'C:\ThesisRebuild')
OOS=ROOT/'03_Volatility_OOS_LOWER10_FULL'/'final'/'oos_volatility_345_v3.csv'
RET=ROOT/'05_Returns'/'returns_log_pct_345_wide.csv'
OUT=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Outputs\Tables'); OUT.mkdir(parents=True,exist_ok=True)
r=pd.read_csv(RET,parse_dates=['Date']); cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
if 'ticker' not in r.columns: r=r.rename(columns={r.columns[1]:'ticker'}); cols=[c for c in r.columns if c not in ('Date','ticker','RIC')]
l=r.melt(id_vars='Date',value_vars=cols,var_name='ticker',value_name='ret').sort_values(['ticker','Date']); l['ret']=pd.to_numeric(l.ret,errors='coerce')
l['rv21']=l.groupby('ticker').ret.transform(lambda x:x.pow(2).rolling(21,min_periods=21).mean()); mk=l.groupby('Date').rv21.median().dropna(); q1,q2=mk.quantile([1/3,2/3]); reg=pd.cut(mk,[-np.inf,q1,q2,np.inf],labels=['Low','Medium','High'])
o=pd.read_csv(OOS,parse_dates=['Date']); o=o.merge(l[['Date','ticker','ret']],on=['Date','ticker'],how='left'); o=o.merge(reg.rename('regime'),left_on='Date',right_index=True,how='left'); o['loss']=(o.ret.pow(2)-o.forecast_var_pct2).pow(2)
pairs=[('GARCH','ESG-GARCH'),('GARCH','ESG-GARCH(E)'),('GARCH','ESG-GARCH(S)'),('GARCH','ESG-GARCH(G)'),('GJR-GARCH','ESG-GJR-GARCH'),('GJR-GARCH','ESG-GJR-GARCH(E)'),('GJR-GARCH','ESG-GJR-GARCH(S)'),('GJR-GARCH','ESG-GJR-GARCH(G)'),('EGARCH','ESG-EGARCH'),('EGARCH','ESG-EGARCH(E)'),('EGARCH','ESG-EGARCH(S)'),('EGARCH','ESG-EGARCH(G)')]
rows=[]
for rg in ['Low','Medium','High']:
 z=o[o.regime==rg]
 for base,esg in pairs:
  a=z[z.model==base][['Date','ticker','loss']].rename(columns={'loss':'b'}); b=z[z.model==esg][['Date','ticker','loss']].rename(columns={'loss':'e'}); d=a.merge(b,on=['Date','ticker']); diff=d.e-d.b
  # HAC(21) mean-difference test, positive means ESG worse.
  X=np.ones((len(diff),1)); fit=sm.OLS(diff.to_numpy(),X).fit(cov_type='HAC',cov_kwds={'maxlags':21}); rows.append([rg,base,esg,len(diff),diff.mean(),fit.tvalues[0],fit.pvalues[0],(diff<0).mean()])
res=pd.DataFrame(rows,columns=['regime','baseline','esg_model','N','mean_loss_diff','DM_t_HAC21','p_value','share_ESG_better']); res.to_csv(OUT/'regime_dm_esg_vs_baseline_lower10.csv',index=False)
print(res.to_string(index=False)); print('THRESHOLDS',q1,q2)
