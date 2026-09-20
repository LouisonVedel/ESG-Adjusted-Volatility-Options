# This code was developed with the assistance of an AI.

import pandas as pd
from pathlib import Path

BASE=Path(r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild')
PFILE=BASE/'02_Prices'/'prices_lseg_345_wide.csv'
MAP=BASE/'00_Master'/'universe_lseg_mapping.csv'
SIG=BASE/'04_Options_Analysis'/'strategy_signals_vega_hedge_full_336.csv'
OUT=BASE/'04_Options_Analysis'/'underlying_prices_2010_2019_279.csv'
AUD=BASE/'04_Options_Analysis'/'underlying_price_coverage_2010_2019.csv'

s=pd.read_csv(SIG,usecols=['ticker','date'])
s['date']=pd.to_datetime(s['date'],errors='coerce')
s=s[(s.date>='2010-01-01')&(s.date<='2019-06-28')]
tickers=sorted(s['ticker'].dropna().unique())
mp=pd.read_csv(MAP,usecols=['ticker','RIC'])
mp=mp.drop_duplicates('ticker')
sel=mp[mp.ticker.isin(tickers)].copy()
missing_map=sorted(set(tickers)-set(sel.ticker))
print(f'SIGNAL_TICKERS={len(tickers)} MAPPED={len(sel)} MISSING_MAPPING={missing_map}')
price=pd.read_csv(PFILE)
price['Date']=pd.to_datetime(price['Date'],errors='coerce')
price=price[(price.Date>='2010-01-01')&(price.Date<='2019-06-28')]
rows=[]
for _,m in sel.iterrows():
    ric=m.RIC
    if ric not in price.columns:
        rows.append((m.ticker,ric,0,None,None,0))
        continue
    z=price[['Date',ric]].rename(columns={ric:'price'}).copy()
    z['ticker']=m.ticker
    z=z[['ticker','Date','price']].dropna(subset=['price'])
    rows.append((m.ticker,ric,len(z),z.Date.min(),z.Date.max(),z.price.isna().sum()))
    z.to_csv(OUT,index=False,mode='a' if OUT.exists() else 'w',header=not OUT.exists())

aud=pd.DataFrame(rows,columns=['ticker','RIC','n_obs','first_date','last_date','null_price'])
aud.to_csv(AUD,index=False)
print('PRICE_ROWS',int(aud.n_obs.sum()),'TICKERS_WITH_PRICE',int((aud.n_obs>0).sum()))
print('NO_PRICE_COLUMNS',aud.loc[aud.n_obs.eq(0),['ticker','RIC']].to_dict('records'))
