# This code was developed with the assistance of an AI.

import csv,collections,os
p=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis\backtest_trades_15models_3horizons_279.csv"
n=0; dup=0; seen=set(); models=set(); hs=collections.Counter(); null=collections.Counter(); bad=0; tick=set()
with open(p,newline="",encoding="utf-8") as f:
    for r in csv.DictReader(f):
        n+=1; tick.add(r["ticker"]); models.add(r["model"]); hs[r["horizon"]]+=1
        k=(r["ticker"],r["date"],r["model"],r["horizon"])
        if k in seen: dup+=1
        else: seen.add(k)
        for c in ["target_entry_straddle","target_exit_straddle","hedge_entry_straddle","hedge_exit_straddle","total_pnl","initial_shares","final_shares"]:
            if r[c]=="": null[c]+=1
        try:
            vals=[float(r[c]) for c in ["target_entry_straddle","target_exit_straddle","hedge_entry_straddle","hedge_exit_straddle","total_pnl"]]
            if not all(map(lambda x: x==x and abs(x)<1e100,vals)): bad+=1
        except: bad+=1
print("rows",n,"tickers",len(tick),"models",len(models),"horizons",dict(hs),"dupes",dup,"null",dict(null),"bad",bad)
