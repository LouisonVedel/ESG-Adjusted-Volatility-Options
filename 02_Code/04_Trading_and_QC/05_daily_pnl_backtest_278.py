# This code was developed with the assistance of an AI.

import csv, collections, pathlib
BASE=pathlib.Path(__file__).resolve().parent
TRADE=BASE/'backtest_trades_15models_3horizons_279.csv'; QUOTES=BASE/'trade_contract_quotes_2010_2019.csv'; PRICES=BASE/'underlying_prices_2010_2019_279.csv'
OUT=BASE/'portfolio_daily_pnl_15models_3horizons_279.csv'; SUM=BASE/'portfolio_daily_pnl_summary_15models_3horizons_279.csv'
print('BASE',BASE)
trades=[]; contracts=set()
with open(TRADE,newline='',encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if r.get('status')!='OK': continue
        trades.append(r); contracts.update([(r['ticker'],r['target_exdate'],r['target_strike'],'C'),(r['ticker'],r['target_exdate'],r['target_strike'],'P'),(r['ticker'],r['hedge_exdate'],r['hedge_strike'],'C'),(r['ticker'],r['hedge_exdate'],r['hedge_strike'],'P')])
print('TRADES',len(trades),'CONTRACTS',len(contracts))
q=collections.defaultdict(dict); nq=0
with open(QUOTES,newline='',encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if (r['ticker'],r['exdate'],r['strike_price'],r['cp_flag']) in contracts:
            try: q[(r['ticker'],r['exdate'],r['strike_price'],r['cp_flag'])][r['date']]=(float(r['best_bid']),float(r['best_offer']),float(r['mid']),float(r['delta'])); nq+=1
            except: pass
print('QUOTE_MARKS',nq,'KEYS',len(q))
px=collections.defaultdict(dict); np=0
with open(PRICES,newline='',encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try: px[r['ticker']][r['Date']]=float(r['price']); np+=1
        except: pass
print('UNDERLYING_MARKS',np,'TICKERS',len(px))

def pair(t,e,s,d):
    c=q.get((t,e,s,'C'),{}).get(d); p=q.get((t,e,s,'P'),{}).get(d)
    if c is None or p is None: return None
    return (c[0]+p[0],c[1]+p[1],c[2]+p[2],c[3]+p[3])
daily=collections.defaultdict(lambda:[0.0,0]); valid=invalid=0
for i,r in enumerate(trades,1):
    t=r['ticker']; entry=r['date']; exitd=r['exit_date']; dsgn=1.0 if r['direction']=='LONG_VOL' else -1.0; hu=float(r['hedge_units'])
    te,ts=r['target_exdate'],r['target_strike']; he,hs=r['hedge_exdate'],r['hedge_strike']
    dates=sorted(d for d in px.get(t,{}) if entry<=d<=exitd)
    if not dates or dates[0]!=entry or dates[-1]!=exitd: invalid+=1; continue
    seq=[]; ok=True
    for d in dates:
        tm=pair(t,te,ts,d); hm=pair(t,he,hs,d)
        if tm is None or hm is None: ok=False; break
        seq.append((d,tm,hm,px[t][d]))
    if not ok: invalid+=1; continue
    shares=-(dsgn*seq[0][1][3]+hu*seq[0][2][3])
    contrib=[]; prev_t,prev_h,prev_px=seq[0][1],seq[0][2],seq[0][3]
    for d,tm,hm,spot in seq[1:]:
        day=dsgn*(tm[2]-prev_t[2])+hu*(hm[2]-prev_h[2])+shares*(spot-prev_px)
        if d==exitd:
            tx=(tm[0] if dsgn<0 else tm[1]); hx=(hm[0] if -dsgn<0 else hm[1])
            day += dsgn*(tx-tm[2])+hu*(hx-hm[2])
        contrib.append((d,day)); shares=-(dsgn*tm[3]+hu*hm[3]); prev_t,prev_h,prev_px=tm,hm,spot
    for d,day in contrib: daily[(r['model'],r['horizon'],d)][0]+=day; daily[(r['model'],r['horizon'],d)][1]+=1
    valid+=1
    if i%50000==0: print('PROGRESS',i,'valid',valid,'invalid',invalid)
print('DAILY_DONE valid',valid,'invalid',invalid,'keys',len(daily))
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['model','horizon','date','daily_pnl','trade_count'])
    for (m,h,d),(p,n) in sorted(daily.items()): w.writerow([m,h,d,p,n])
by=collections.defaultdict(list)
for (m,h,d),(p,n) in daily.items(): by[(m,h)].append((d,p,n))
with open(SUM,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['model','horizon','days','mean_daily_pnl','std_daily_pnl','ann_mean_pnl','ann_vol_pnl','sharpe_like','cum_pnl','max_drawdown'])
    for (m,h),vals in sorted(by.items()):
        vals.sort(); xs=[x[1] for x in vals]; mean=sum(xs)/len(xs); sd=(sum((x-mean)**2 for x in xs)/(len(xs)-1))**0.5 if len(xs)>1 else 0
        cum=peak=mdd=0
        for x in xs:
            cum+=x; peak=max(peak,cum); mdd=min(mdd,cum-peak)
        ann_mean=mean*252; ann_vol=sd*(252**0.5); sh=ann_mean/ann_vol if ann_vol else 0
        w.writerow([m,h,len(xs),mean,sd,ann_mean,ann_vol,sh,cum,mdd])
print('WROTE',OUT); print('WROTE',SUM)
