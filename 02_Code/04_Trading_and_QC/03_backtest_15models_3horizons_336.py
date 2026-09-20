# This code was developed with the assistance of an AI.

import csv, os, math, collections, time
BASE=r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis"
SIG=os.path.join(BASE,"strategy_signals_vega_hedge_full_336.csv")
QUOTE=os.path.join(BASE,"trade_contract_quotes_2010_2019.csv")
PRICE=os.path.join(BASE,"underlying_prices_2010_2019_279.csv")
OUT=os.path.join(BASE,"backtest_trades_15models_3horizons_279.csv")
SUM=os.path.join(BASE,"backtest_summary_15models_3horizons_279.csv")
AUD=os.path.join(BASE,"backtest_audit_15models_3horizons_279.csv")
HORIZONS=(5,10,20); MULT=100.0
# 1) load signals and relevant exact contract keys
signals=[]; keys=set(); tickers=set()
with open(SIG,newline="",encoding="utf-8") as f:
    for r in csv.DictReader(f):
        r["signal"]=float(r["signal"]); r["vega_ratio"]=float(r["vega_ratio"])
        r["target_strike"]=float(r["target_strike"]); r["strike_price"]=float(r["strike_price"])
        signals.append(r); tickers.add(r["ticker"])
        keys.add((r["ticker"],r["target_exdate"],r["target_strike"],"C"))
        keys.add((r["ticker"],r["target_exdate"],r["target_strike"],"P"))
        keys.add((r["ticker"],r["exdate"],r["strike_price"],"C"))
        keys.add((r["ticker"],r["exdate"],r["strike_price"],"P"))
print("signals",len(signals),"tickers",len(tickers),"contract_keys",len(keys),flush=True)

# 2) one pass through 370MB quote file; retain only exact contracts used by signals
quotes=collections.defaultdict(dict); qrows=0; kept=0
with open(QUOTE,newline="",encoding="utf-8") as f:
    for r in csv.DictReader(f):
        qrows+=1
        k=(r["ticker"],r["exdate"],float(r["strike_price"]),r["cp_flag"])
        if k in keys:
            quotes[k][r["date"]]=r; kept+=1
print("quote_rows_scanned",qrows,"relevant_quote_rows",kept,"contract_groups",len(quotes),flush=True)

# 3) load underlying prices
prices=collections.defaultdict(dict)
with open(PRICE,newline="",encoding="utf-8") as f:
    for r in csv.DictReader(f):
        prices[r["ticker"]][r["Date"]]=float(r["price"])
print("price_tickers",len(prices),flush=True)

def px(q, side):
    return float(q["best_offer"] if side>0 else q["best_bid"])
def stval(ticker,date,ex,k,side):
    c=quotes[(ticker,ex,k,"C")][date]; p=quotes[(ticker,ex,k,"P")][date]
    return px(c,side)+px(p,side)
def delta(ticker,date,ex,k):
    return float(quotes[(ticker,ex,k,"C")][date]["delta"])+float(quotes[(ticker,ex,k,"P")][date]["delta"])
def allq(ticker,date,ex,k):
    return (ticker,ex,k,"C") in quotes and date in quotes[(ticker,ex,k,"C")] and (ticker,ex,k,"P") in quotes and date in quotes[(ticker,ex,k,"P")]
# 4) build trades
trade_rows=[]; audit=collections.Counter(); t0=time.time()
for j,s in enumerate(signals,1):
    ticker=s["ticker"]; entry=s["date"]; direction=s["signal"]
    tex=s["target_exdate"]; tk=s["target_strike"]; hex=s["exdate"]; hk=s["strike_price"]
    hedge_units=-direction*s["vega_ratio"]
    pdates=sorted(d for d in prices.get(ticker,{}) if d>=entry)
    if entry not in pdates:
        audit["NO_ENTRY_PRICE"]+=1; continue
    i=pdates.index(entry)
    for h in HORIZONS:
        if i+h>=len(pdates):
            audit[f"NO_EXIT_PRICE_{h}"]+=1
            continue
        path=pdates[i:i+h+1]; exitd=path[-1]
        if not all(allq(ticker,d,tex,tk) and allq(ticker,d,hex,hk) for d in path):
            audit[f"NO_EXACT_QUOTES_{h}"]+=1
            continue
        try:
            # entry execution: target follows signal; vega hedge is opposite
            target_entry=stval(ticker,entry,tex,tk,direction)
            hedge_entry=stval(ticker,entry,hex,hk,hedge_units)
            netd=direction*delta(ticker,entry,tex,tk)+hedge_units*delta(ticker,entry,hex,hk)
            shares=-MULT*netd
            stock_pnl=0.0
            for prev,d in zip(path,path[1:]):
                stock_pnl += shares*(prices[ticker][d]-prices[ticker][prev])
                netd=direction*delta(ticker,d,tex,tk)+hedge_units*delta(ticker,d,hex,hk)
                shares=-MULT*netd
            target_exit=stval(ticker,exitd,tex,tk,direction)
            hedge_exit=stval(ticker,exitd,hex,hk,hedge_units)
            target_pnl=MULT*direction*(target_exit-target_entry)
            hedge_pnl=MULT*hedge_units*(hedge_exit-hedge_entry)
            total=target_pnl+hedge_pnl+stock_pnl
            entry_gross=MULT*(abs(target_entry)+abs(hedge_units*hedge_entry))
            trade_rows.append({
                "ticker":ticker,"date":entry,"model":s["model"],"horizon":h,
                "direction":("LONG_VOL" if direction>0 else "SHORT_VOL"),
                "target_exdate":tex,"target_strike":tk,"hedge_exdate":hex,"hedge_strike":hk,
                "target_vega":float(s["target_vega"]),"hedge_vega":float(s["hedge_vega"]),
                "vega_ratio":s["vega_ratio"],"hedge_units":hedge_units,
                "z":float(s["z"]),"rf":float(s["rf"]),
                "exit_date":exitd,"target_entry_straddle":target_entry,"target_exit_straddle":target_exit,
                "hedge_entry_straddle":hedge_entry,"hedge_exit_straddle":hedge_exit,
                "initial_shares":-MULT*(direction*delta(ticker,entry,tex,tk)+hedge_units*delta(ticker,entry,hex,hk)),
                "final_shares":shares,"target_pnl":target_pnl,"vega_hedge_pnl":hedge_pnl,
                "stock_hedge_pnl":stock_pnl,"total_pnl":total,"gross_entry_premium":entry_gross,
                "status":"OK"
            })
            audit[f"OK_{h}"]+=1
        except Exception as e:
            audit[f"ERROR_{h}"]+=1
    if j%25000==0: print("processed",j,"trades",len(trade_rows),"elapsed",round(time.time()-t0,1),flush=True)
print("TRADE_BUILD_DONE",len(trade_rows),dict(audit),flush=True)
# 5) write trade-level output
fields=["ticker","date","model","horizon","direction","target_exdate","target_strike","hedge_exdate","hedge_strike","target_vega","hedge_vega","vega_ratio","hedge_units","z","rf","exit_date","target_entry_straddle","target_exit_straddle","hedge_entry_straddle","hedge_exit_straddle","initial_shares","final_shares","target_pnl","vega_hedge_pnl","stock_hedge_pnl","total_pnl","gross_entry_premium","status"]
with open(OUT,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(trade_rows)

# 6) summaries
grp=collections.defaultdict(list)
for r in trade_rows: grp[(r["model"],r["horizon"])].append(float(r["total_pnl"]))
sumrows=[]
for (model,h),vals in sorted(grp.items()):
    n=len(vals); mean=sum(vals)/n; win=sum(v>0 for v in vals)/n
    var=sum((v-mean)**2 for v in vals)/(n-1) if n>1 else 0
    sd=math.sqrt(var); sharpe=mean/sd*math.sqrt(252/h) if sd>0 else None
    sumrows.append({"model":model,"horizon":h,"n_trades":n,"mean_pnl":mean,"median_pnl":sorted(vals)[n//2],"win_rate":win,"std_pnl":sd,"sharpe_type":sharpe,"total_pnl":sum(vals)})
sf=list(sumrows[0].keys()) if sumrows else []
with open(SUM,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=sf); w.writeheader(); w.writerows(sumrows)

with open(AUD,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["metric","value"])
    for k,v in sorted(audit.items()): w.writerow([k,v])
    w.writerow(["signals_input",len(signals)]); w.writerow(["tickers_input",len(tickers)])
    w.writerow(["trade_rows_output",len(trade_rows)])
print("FULL_BACKTEST_COMPLETE",OUT,SUM,AUD,flush=True)
