import os, glob, math
import pandas as pd

PANEL=r'C:\ThesisRebuild\04_Options_Analysis\options_panel_342_LOCKED_2026-09-17.csv'
ROOT=r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Options_Clean'
OUT=r'C:\ThesisRebuild\04_Options_Analysis\atm30_callput_options_342.csv'
cols=['date','exdate','cp_flag','strike_price','best_bid','best_offer','open_interest','impl_volatility','forward_price']
panel=pd.read_csv(PANEL)
tickers=panel['ticker'].astype(str).str.upper().tolist()
print(f'Starting pricing extraction: {len(tickers)} tickers',flush=True)
rows=[]; done=0; missing=[]
for ticker in tickers:
    files=glob.glob(os.path.join(ROOT,ticker+'_*_options.csv'))
    if not files: missing.append(ticker); continue
    parts=[]
    for ch in pd.read_csv(files[0],usecols=cols,dtype=str,chunksize=250000,on_bad_lines='skip'):
        ch['date']=pd.to_datetime(ch['date'],format='%Y%m%d',errors='coerce')
        ch['exdate']=pd.to_datetime(ch['exdate'],format='%Y%m%d',errors='coerce')
        for c in ['strike_price','best_bid','best_offer','open_interest','impl_volatility','forward_price']:
            ch[c]=pd.to_numeric(ch[c],errors='coerce')
        ch['strike_price']/=1000.0
        ch['dte']=(ch['exdate']-ch['date']).dt.days
        ch['mid']=(ch['best_bid']+ch['best_offer'])/2
        ch['spread_rel']=(ch['best_offer']-ch['best_bid'])/ch['mid']
        m=(ch.dte.between(15,60)&(ch.forward_price>0)&(ch.strike_price>0)&(ch.impl_volatility>0)&(ch.mid>0)&(ch.open_interest>=100)&(ch.spread_rel<=0.15)&ch.cp_flag.isin(['C','P']))
        x=ch.loc[m,['date','exdate','cp_flag','strike_price','forward_price','impl_volatility','mid','open_interest','spread_rel']].copy()
        if len(x): parts.append(x)
    if parts:
        x=pd.concat(parts,ignore_index=True)
        g=x.groupby(['date','exdate','strike_price','cp_flag'],as_index=False).agg(
            fwd=('forward_price','median'),iv=('impl_volatility','mean'),mid=('mid','mean'),
            oi=('open_interest','sum'),spread_rel=('spread_rel','mean'),n_contracts=('strike_price','size'))
        # Retain only strikes/expiries for which both call and put sides are available.
        sides=g.groupby(['date','exdate','strike_price'])['cp_flag'].nunique().reset_index(name='n_cp')
        g=g.merge(sides,on=['date','exdate','strike_price'],how='left')
        g=g[g.n_cp==2].copy()
        if len(g):
            fwd_ref=g.groupby(['date','exdate','strike_price'],as_index=False)['fwd'].median().rename(columns={'fwd':'fwd_ref'})
            g=g.merge(fwd_ref,on=['date','exdate','strike_price'],how='left')
            g['moneyness']=(g['strike_price']/g['fwd_ref']).abs().map(lambda z: abs(math.log(z)) if z>0 else float('nan'))
            g['dte']=(g.exdate-g.date).dt.days
            g['dte_dist']=(g.dte-30).abs()
            # Select one common expiry/strike per date, then keep both C and P.
            key=g[['date','exdate','strike_price','dte','dte_dist','moneyness','fwd_ref']].drop_duplicates()
            key=key.sort_values(['date','dte_dist','moneyness']).drop_duplicates('date')
            g=g.merge(key[['date','exdate','strike_price','dte','fwd_ref']],on=['date','exdate','strike_price'],how='inner')
            g['ticker']=ticker
            rows.append(g[['ticker','date','exdate','dte_x','strike_price','fwd','fwd_ref_x','cp_flag','iv','mid','oi','n_contracts','spread_rel']].rename(columns={'dte_x':'dte','fwd_ref_x':'fwd_ref'}))
    done+=1
    if done%25==0: print(f'{done}/{len(tickers)} tickers',flush=True)
if missing: print('MISSING:',missing,flush=True)
if rows:
    out=pd.concat(rows,ignore_index=True).sort_values(['ticker','date','cp_flag'])
    out.to_csv(OUT,index=False,date_format='%Y-%m-%d')
    print(f'WROTE {len(out):,} rows; {out.ticker.nunique()} tickers -> {OUT}',flush=True)
else: print('NO ROWS WRITTEN',flush=True)
