# This code was developed with the assistance of an AI.

import pandas as pd, glob, os, csv
from pathlib import Path

BASE=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis')
SIG=BASE/'strategy_signals_vega_hedge_full_336.csv'
ROOT=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Options_Clean')
OUT=BASE/'trade_contract_quotes_2010_2019.csv'
AUD=BASE/'trade_contract_quotes_2010_2019_audit.csv'

s=pd.read_csv(SIG,usecols=['ticker','date','target_exdate','target_strike','exdate','strike_price'])
s['date']=pd.to_datetime(s['date'],errors='coerce')
s=s[(s.date>='2010-01-01')&(s.date<='2019-06-28')].copy()
a=s[['ticker','date','target_exdate','target_strike']].rename(columns={'target_exdate':'exdate','target_strike':'strike_price'})
b=s[['ticker','date','exdate','strike_price']]
k=pd.concat([a,b],ignore_index=True).drop_duplicates()
k['exdate']=pd.to_datetime(k['exdate'],errors='coerce')
k['strike_price']=pd.to_numeric(k['strike_price'],errors='coerce')
by={}
for t,g in k.groupby('ticker'):
    by[t]=(set(zip(g.exdate.dt.strftime('%Y%m%d'),g.strike_price.round(6))),g.date.min(),min(g.date.max()+pd.Timedelta(days=35),pd.Timestamp('2019-06-28')))

files={os.path.basename(f).split('_')[0]:f for f in glob.glob(str(ROOT/'*_options.csv'))}
fields=['ticker','date','exdate','strike_price','cp_flag','best_bid','best_offer','mid','open_interest','iv','delta','forward_price']
# Resume safely: completed tickers are recorded in the audit file.
done=set()
if AUD.exists():
    old=pd.read_csv(AUD)
    if 'status' in old.columns: done=set(old.loc[old.status.eq('DONE'),'ticker'])

new_header=not OUT.exists() or OUT.stat().st_size==0
with open(AUD,'a',newline='',encoding='utf-8') as af:
    aw=csv.writer(af)
    if not AUD.exists() or AUD.stat().st_size==0: aw.writerow(['ticker','status','rows','error'])
    for i,t in enumerate(sorted(by),1):
        if t in done:
            print('SKIP_DONE',i,t,flush=True); continue
        keys,dmin,dmax=by[t]
        f=files.get(t)
        if not f:
            aw.writerow([t,'NO_FILE',0,'missing options file']); af.flush(); print('NO_FILE',i,t,flush=True); continue
        try:
            parts=[]
            for ch in pd.read_csv(f,usecols=['date','exdate','cp_flag','strike_price','best_bid','best_offer','open_interest','impl_volatility','delta','forward_price'],dtype=str,chunksize=150000,on_bad_lines='skip'):
                ch['date']=pd.to_datetime(ch.date,format='%Y%m%d',errors='coerce')
                ch['exdate']=pd.to_datetime(ch.exdate,format='%Y%m%d',errors='coerce')
                ch['strike_price']=pd.to_numeric(ch.strike_price,errors='coerce')/1000
                m=(ch.date>=dmin)&(ch.date<=dmax)&ch.cp_flag.isin(['C','P'])
                ch=ch.loc[m]
                if ch.empty: continue
                mask=[x in keys for x in zip(ch.exdate.dt.strftime('%Y%m%d'),ch.strike_price.round(6))]
                ch=ch.loc[mask]
                if not ch.empty: parts.append(ch)
            q=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
            if not q.empty:
                q['ticker']=t
                q['best_bid']=pd.to_numeric(q.best_bid,errors='coerce'); q['best_offer']=pd.to_numeric(q.best_offer,errors='coerce')
                q['mid']=(q.best_bid+q.best_offer)/2
                q['open_interest']=pd.to_numeric(q.open_interest,errors='coerce')
                q['delta']=pd.to_numeric(q.delta,errors='coerce'); q['iv']=pd.to_numeric(q.impl_volatility,errors='coerce'); q['forward_price']=pd.to_numeric(q.forward_price,errors='coerce')
                q=q[['ticker','date','exdate','strike_price','cp_flag','best_bid','best_offer','mid','open_interest','iv','delta','forward_price']]
                q.to_csv(OUT,index=False,mode='a',header=new_header); new_header=False
            n=len(q)
            aw.writerow([t,'DONE',n,'']); af.flush()
            print('DONE',i,t,'rows',n,flush=True)
        except Exception as e:
            aw.writerow([t,'ERROR',0,repr(e)]); af.flush(); print('ERROR',i,t,repr(e),flush=True)
print('EXTRACTION_COMPLETE')
