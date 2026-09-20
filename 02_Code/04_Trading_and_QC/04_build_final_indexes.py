# This code was developed with the assistance of an AI.

import os,csv
base=r'C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\03_Rebuild\04_Options_Analysis'
files=[
('Forecast/OOS',r'..\03_Volatility_OOS\final\oos_volatility_345_v3.csv','344 usable tickers; 15 models; strict OOS'),
('Options','options_panel_342_LOCKED_2026-09-17.csv','342 integrated option tickers'),
('Merge','oos_options_merged_342.csv','3,005,230 observations; 342 tickers; 15 models'),
('Pricing','black76_pricing_336.csv','2,172,421 observations; 336 tickers; 15 models'),
('Strategy','strategy_signals_336.csv','308,603 baseline signals'),
('Vega','strategy_signals_vega_hedge_full_336.csv','286,634 paired vega-hedged signals'),
('Trades','backtest_trades_15models_3horizons_279.csv','555,659 realised baseline trades; 278 tickers'),
('Capital','portfolio_capital_1m_metrics_15models_3horizons_279.csv','USD 1m reference capital'),
('Risk','risk_metrics_1m_15models_3horizons_279.csv','45 model-horizon cells'),
('Robustness','robustness_thresholds_1p0_1p5_2p0.csv','thresholds 1.0/1.5/2.0'),
('Paired P&L','trade_pnl_paired_esg_vs_benchmark_thresholds.csv','216 paired cells; Holm correction'),
]
rows=[]
for stage,name,notes in files:
 p=os.path.join(base,name); rows.append([stage,name,'PRESENT' if os.path.exists(p) else 'MISSING',os.path.getsize(p) if os.path.exists(p) else '',notes])
out=os.path.join(base,'FINAL_EMPIRICAL_RESULTS_INDEX_2026-09-20.csv')
with open(out,'w',newline='',encoding='utf-8') as f:
 w=csv.writer(f); w.writerow(['stage','file','status','bytes','notes']); w.writerows(rows)
figs=sorted(x for x in os.listdir(base) if x.lower().endswith('.svg') and x.startswith('Figure_'))
out2=os.path.join(base,'FINAL_FIGURE_INDEX_2026-09-20.csv')
with open(out2,'w',newline='',encoding='utf-8') as f:
 w=csv.writer(f); w.writerow(['figure','status','bytes']);
 for x in figs: w.writerow([x,'VALID_NONEMPTY' if os.path.getsize(os.path.join(base,x))>0 else 'EMPTY',os.path.getsize(os.path.join(base,x))])
print('RESULT_INDEX',out); print('FIGURE_INDEX',out2); print('FIGURES',len(figs)); print('MISSING',sum(r[2]=='MISSING' for r in rows))
