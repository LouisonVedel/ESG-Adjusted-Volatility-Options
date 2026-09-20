import os, time, pandas as pd
import lseg.data as ld
BASE=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\00_Master"
OUT=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\02_Prices"
os.makedirs(OUT,exist_ok=True)
master=pd.read_csv(os.path.join(BASE,"master_panel_345.csv"))
ld.open_session()
parts=[]
for i in range(0,len(master),20):
    rs=master.RIC.iloc[i:i+20].tolist(); t=time.time()
    try:
        x=ld.get_history(universe=rs,fields=["TRDPRC_1"],interval="1D",start="2009-01-01",end="2019-06-28")
        x.index=pd.to_datetime(x.index); x.columns=[str(c) for c in x.columns]
        parts.append(x); print(f"BATCH {i}:{i+len(rs)} OK shape={x.shape} sec={time.time()-t:.1f}",flush=True)
    except Exception as e:
        print(f"BATCH {i}:{i+len(rs)} ERROR {e}",flush=True)
if parts:
    wide=pd.concat(parts,axis=1); wide=wide.loc[:,~wide.columns.duplicated()]
    wide.to_csv(os.path.join(OUT,"prices_lseg_345_wide.csv"))
    print("FINAL",wide.shape,"nonmissing",int(wide.notna().sum().sum()),flush=True)
ld.close_session()
