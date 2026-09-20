# This code was developed with the assistance of an AI.

import pandas as pd
import numpy as np
from scipy.stats import ttest_rel, wilcoxon
import statsmodels.formula.api as smf

ROOT=r"C:\ThesisRebuild\04_Options_Analysis"
IN=ROOT+r"\black76_pricing_336.csv"
OUT1=ROOT+r"\formal_mispricing_paired_336.csv"
OUT2=ROOT+r"\formal_mispricing_regression_336.csv"

df=pd.read_csv(IN)
df["abs_mispricing"]=df["straddle_mispricing"].abs()
print("READ",len(df),df["ticker"].nunique(),df["model"].nunique())

pairs={
"GARCH":["ESG-GARCH","ESG-GARCH(E)","ESG-GARCH(G)","ESG-GARCH(S)"],
"GJR-GARCH":["ESG-GJR-GARCH","ESG-GJR-GARCH(E)","ESG-GJR-GARCH(G)","ESG-GJR-GARCH(S)"],
"EGARCH":["ESG-EGARCH","ESG-EGARCH(E)","ESG-EGARCH(G)","ESG-EGARCH(S)"]}
rows=[]
for base,esgs in pairs.items():
    b=df[df.model==base][["ticker","date","straddle_mispricing","abs_mispricing"]].rename(columns={"straddle_mispricing":"b_mis","abs_mispricing":"b_abs"})
    for m in esgs:
        e=df[df.model==m][["ticker","date","straddle_mispricing","abs_mispricing"]].rename(columns={"straddle_mispricing":"e_mis","abs_mispricing":"e_abs"})
        z=b.merge(e,on=["ticker","date"],how="inner")
        diff=z.e_mis-z.b_mis
        adiff=z.e_abs-z.b_abs
        tt=ttest_rel(z.e_mis,z.b_mis,nan_policy="omit")
        try: wx=wilcoxon(diff,zero_method="wilcox",alternative="two-sided")
        except Exception: wx=type("W",(),{"statistic":np.nan,"pvalue":np.nan})()
        rows.append([base,m,len(z),z.ticker.nunique(),diff.mean(),diff.median(),adiff.mean(),adiff.median(),tt.statistic,tt.pvalue,wx.statistic,wx.pvalue])

pd.DataFrame(rows,columns=["benchmark","esg_model","N","Tickers","Mean_diff_mispricing","Median_diff_mispricing","Mean_diff_abs","Median_diff_abs","Paired_t","p_t","Wilcoxon","p_wilcoxon"]).to_csv(OUT1,index=False)
print("PAIRED",len(rows),OUT1)
# Cross-sectional/time-series regression with firm and date fixed effects.
# Main dependent variable: absolute pricing deviation. Model indicators compare
# ESG specifications against the conventional family baseline.
models=[]
for base,esgs in pairs.items():
    cols=["ticker","date","straddle_mispricing","iv_midpoint","dte","observed_spread_rel_mean","oi_C","oi_P","model"]
    x=df[df.model.isin([base]+esgs)][cols].copy()
    x["esg"]=x.model.ne(base).astype(int)
    x["abs_mispricing"]=x.straddle_mispricing.abs()
    x["spread_rel"]=x.observed_spread_rel_mean
    x["oi"]=x[["oi_C","oi_P"]].mean(axis=1)
    # Firm and date fixed effects; two-way clustered covariance is handled below.
    try:
        fit=smf.ols("abs_mispricing ~ esg + iv_midpoint + dte + spread_rel + np.log1p(oi) + C(ticker) + C(date)",data=x).fit(cov_type="cluster",cov_kwds={"groups":x[["ticker","date"]]})
        models.append([base,len(x),x.ticker.nunique(),fit.params.get("esg",np.nan),fit.bse.get("esg",np.nan),fit.pvalues.get("esg",np.nan),fit.rsquared])
    except Exception as ex:
        print("REG_FAIL",base,repr(ex))
        models.append([base,len(x),x.ticker.nunique(),np.nan,np.nan,np.nan,np.nan])

pd.DataFrame(models,columns=["benchmark_family","N","Tickers","ESG_coef_abs_mispricing","SE","p_value","R2"]).to_csv(OUT2,index=False)
print("REG",len(models),OUT2)
print("DONE")
