# This code was developed with the assistance of an AI.

import lseg.data as ld
import pandas as pd
from pathlib import Path

BASE=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild')
MAP=BASE/'00_Master'/'universe_lseg_mapping.csv'
OUT=BASE/'00_Master'/'historical_identity_audit.csv'

fields=['TR.RIC','TR.CommonName','TR.ExchangeName','TR.TickerSymbol','TR.ISIN','TR.IssuerOAPermID']

m=pd.read_csv(MAP)
rows=[]
ld.open_session()
for _,r in m.iterrows():
    ticker=r['ticker']; ric=r['RIC']
    rec={'ticker':ticker,'RIC':ric,'status':'UNTESTED','notes':''}
    try:
        d=ld.get_data([ric],fields)
        if d is not None and len(d):
            x=d.iloc[0]
            for f in fields: rec[f]=x.get(f)
            rec['status']='REFERENCE_OK'
        else: rec['status']='NO_REFERENCE'
    except Exception as e:
        rec['status']='REFERENCE_ERROR'; rec['notes']=str(e)[:300]
    rows.append(rec)
    print(ticker,ric,rec['status'])
ld.close_session()
pd.DataFrame(rows).to_csv(OUT,index=False)
print('WROTE',OUT)
