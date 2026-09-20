# This code was developed with the assistance of an AI.

import lseg.data as ld
import pandas as pd
from pathlib import Path
BASE=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild')
MAP=BASE/'00_Master'/'universe_lseg_mapping.csv'
OUT=BASE/'00_Master'/'permid_ric_history_audit.csv'
m=pd.read_csv(MAP)
rows=[]
ld.open_session()
for i,r in m.iterrows():
    ticker=str(r['ticker']); ric=str(r['RIC'])
    rec={'ticker':ticker,'input_ric':ric,'instrument_id':'','organization_id':'','historical_rics':'','status':'ERROR','notes':''}
    try:
        d=ld.get_data([ric],['TR.InstrumentID','TR.OrganizationID'])
        if d is None or len(d)==0: raise RuntimeError('no ID result')
        rec['instrument_id']=str(d.iloc[0].get('Instrument ID',''))
        rec['organization_id']=str(d.iloc[0].get('Organization ID',''))
        # Prefer instrument-level history: it follows the same listed instrument through RIC changes.
        pid=rec['instrument_id']
        if pid and pid.lower()!='nan':
            h=ld.get_history(universe=[pid],fields=['TR.RIC'],interval='1D',start='1990-01-01',end='2019-06-28')
            if h is not None and len(h):
                vals=[]
                for v in h.iloc[:,0].dropna().astype(str):
                    if v not in vals: vals.append(v)
                rec['historical_rics']=';'.join(vals)
        rec['status']='OK'
    except Exception as e:
        rec['status']='ERROR'; rec['notes']=str(e)[:250]
    rows.append(rec)
    if (i+1)%20==0: print('PROGRESS',i+1,'/',len(m))
ld.close_session()
pd.DataFrame(rows).to_csv(OUT,index=False)
print('WROTE',OUT,'ROWS',len(rows))
