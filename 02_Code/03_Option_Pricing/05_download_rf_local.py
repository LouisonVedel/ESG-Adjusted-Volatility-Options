# This code was developed with the assistance of an AI.

import pandas as pd
from pathlib import Path
import refinitiv.data as rd
RIC='US10YT=RR'; START='2010-01-01'; END='2019-06-28'
out=Path(r'C:\ThesisRebuild\04_Options_Analysis\US10Y_risk_free_rate_2010_2019.xlsx')
rd.open_session()
try:
    raw=rd.get_history(universe=RIC,fields=['YLDTOMAT','MID_YLD_1','BID'],interval='1D',start=START,end=END)
finally: rd.close_session()
if isinstance(raw.columns,pd.MultiIndex): raw.columns=raw.columns.get_level_values(-1)
y=raw['YLDTOMAT'].copy(); fb=0
for f in ['MID_YLD_1','BID']:
    m=y.isna() & raw[f].notna(); fb += int(m.sum()); y.loc[m]=raw.loc[m,f]
outdf=pd.DataFrame({'Date':raw.index,'yield_pct':y.values,'yield_decimal':(y/100).values}).dropna(subset=['yield_pct']).reset_index(drop=True)
outdf.to_excel(out,index=False)
print('WROTE',len(outdf),outdf['Date'].min(),outdf['Date'].max(),'fallback',fb,'->',out,flush=True)
