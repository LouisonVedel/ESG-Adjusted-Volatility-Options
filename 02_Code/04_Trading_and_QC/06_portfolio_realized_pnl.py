# This code was developed with the assistance of an AI.

import csv, math, os
from collections import defaultdict
BASE=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis"
INP=os.path.join(BASE,"backtest_trades_15models_3horizons_279.csv")
OUT=os.path.join(BASE,"portfolio_realized_pnl_15models_3horizons_279.csv")
groups=defaultdict(lambda: defaultdict(float))
counts=defaultdict(int)
wins=defaultdict(int)
with open(INP,newline="",encoding="utf-8-sig") as f:
    rd=csv.DictReader(f)
    for r in rd:
        k=(r["model"],r["horizon"])
        d=r["exit_date"]
        pnl=float(r["total_pnl"])
        groups[k][d]+=pnl
        counts[k]+=1
        if pnl>0: wins[k]+=1
rows=[]
for (model,h), daily in groups.items():
    eq=0.0; peak=0.0; maxdd=0.0
    vals=[]
    for d in sorted(daily):
        pnl=daily[d]; eq+=pnl; peak=max(peak,eq); maxdd=max(maxdd,peak-eq); vals.append(pnl)
        rows.append((model,h,d,pnl,eq,peak-eq))
    mean=sum(vals)/len(vals)
    sd=math.sqrt(sum((x-mean)**2 for x in vals)/(len(vals)-1)) if len(vals)>1 else 0
    sharpe=mean/sd*math.sqrt(252) if sd>0 else float("nan")
    print(model,h,"days",len(vals),"trades",counts[(model,h)],"total",round(sum(vals),2),"mean_daily",round(mean,4),"sharpe",round(sharpe,3),"maxDD",round(maxdd,2),"win_trade",round(wins[(model,h)]/counts[(model,h)],4))
with open(OUT,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["model","horizon","date","daily_realized_pnl","cum_pnl","drawdown"]); w.writerows(rows)
print("WROTE",OUT,len(rows))
# Portfolio convention: realized trade P&L is recognized on each exact exit date.
# This is a realized-P&L curve, not a mark-to-market capital NAV.
# It is used to inspect temporal concentration/drawdown; overlapping trades remain additive.
