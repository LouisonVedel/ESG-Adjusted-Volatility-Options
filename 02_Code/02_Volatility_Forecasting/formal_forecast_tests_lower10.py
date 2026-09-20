import pandas as pd, numpy as np, glob
from pathlib import Path
import statsmodels.api as sm
base=Path(r'C:\ThesisRebuild\03_Volatility_OOS_LOWER10_FULL')
out=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Outputs\Tables'); out.mkdir(parents=True,exist_ok=True)
files=glob.glob(str(base/'blocks'/'block_*'/'*.csv'))
ret=pd.read_csv(r'C:\ThesisRebuild\05_Returns\returns_log_pct_345_wide.csv')
ret['Date']=pd.to_datetime(ret['Date'],errors='coerce')
rl=ret.melt(id_vars='Date',var_name='RIC',value_name='r_pct'); rl['r_pct']=pd.to_numeric(rl.r_pct,errors='coerce'); rl['rv']=rl.r_pct**2
parts=[]
for f in files:
 b=pd.read_csv(f); b['Date']=pd.to_datetime(b.Date,errors='coerce'); b['forecast_var_pct2']=pd.to_numeric(b['forecast_var_pct2'],errors='coerce'); b=b.dropna(subset=['Date'])
 m=b.merge(rl,on=['Date','RIC'],how='left').dropna(subset=['r_pct','forecast_var_pct2'])
 m=m[np.isfinite(m['forecast_var_pct2'])&(m['forecast_var_pct2']>0)]
 parts.append(m[['ticker','RIC','Date','model','forecast_var_pct2','rv']])
df=pd.concat(parts,ignore_index=True); assert not df.duplicated(['ticker','Date','model']).any()
piv=df.pivot_table(index=['ticker','RIC','Date'],columns='model',values='forecast_var_pct2',aggfunc='first'); y=df.groupby(['ticker','RIC','Date']).rv.first(); common=pd.concat([y.rename('rv'),piv],axis=1)
pairs={'ESG-GARCH':'GARCH','ESG-GJR-GARCH':'GJR-GARCH','ESG-EGARCH':'EGARCH','ESG-GARCH(E)':'GARCH','ESG-GARCH(S)':'GARCH','ESG-GARCH(G)':'GARCH','ESG-GJR-GARCH(E)':'GJR-GARCH','ESG-GJR-GARCH(S)':'GJR-GARCH','ESG-GJR-GARCH(G)':'GJR-GARCH','ESG-EGARCH(E)':'EGARCH','ESG-EGARCH(S)':'EGARCH','ESG-EGARCH(G)':'EGARCH'}
r2=[]; DM=[]; ENC=[]
for em,bm in pairs.items():
 z=common[['rv',em,bm]].dropna(); e=(z.rv-z[em])**2; b=(z.rv-z[bm])**2; r2.append([em,bm,len(z),1-e.sum()/b.sum(),e.mean(),b.mean()])
 d=e-b; fit=sm.OLS(d.to_numpy(),np.ones((len(d),1))).fit(cov_type='HAC',cov_kwds={'maxlags':21}); DM.append([em,bm,len(d),d.mean(),float(fit.tvalues[0]),float(fit.pvalues[0])])
 X=sm.add_constant(z[[bm,em]]); ef=sm.OLS(z.rv,X).fit(cov_type='HAC',cov_kwds={'maxlags':21}); ENC.append([em,bm,len(z),ef.params.get('const',np.nan),ef.params.get(bm,np.nan),ef.params.get(em,np.nan),ef.tvalues.get(em,np.nan),ef.pvalues.get(em,np.nan),ef.rsquared])
pd.DataFrame(r2,columns=['ESG_model','Baseline','N','OOS_R2_vs_baseline','ESG_MSE','Baseline_MSE']).to_csv(out/'oos_r2_esg_vs_baseline_lower10.csv',index=False)
pd.DataFrame(DM,columns=['ESG_model','Baseline','N','Mean_loss_diff_ESG_minus_base','DM_t_HAC21','p_value']).to_csv(out/'dm_esg_vs_baseline_sqerror_lower10.csv',index=False)
pd.DataFrame(ENC,columns=['ESG_model','Baseline','N','alpha','beta_baseline','gamma_ESG','t_gamma_HAC21','p_gamma_HAC21','R2']).to_csv(out/'encompassing_esg_vs_baseline_lower10.csv',index=False)
print('ROWS',len(df),'MODELS',df.model.nunique()); print(pd.DataFrame(r2,columns=['ESG_model','Baseline','N','OOS_R2_vs_baseline','ESG_MSE','Baseline_MSE']).to_string(index=False)); print(pd.DataFrame(DM,columns=['ESG_model','Baseline','N','Mean_loss_diff_ESG_minus_base','DM_t_HAC21','p_value']).to_string(index=False)); print(pd.DataFrame(ENC,columns=['ESG_model','Baseline','N','alpha','beta_baseline','gamma_ESG','t_gamma_HAC21','p_gamma_HAC21','R2']).to_string(index=False))
