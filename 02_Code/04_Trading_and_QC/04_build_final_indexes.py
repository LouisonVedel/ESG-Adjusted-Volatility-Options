# This code was developed with the assistance of an AI.

import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "03_Data_and_Results" / "02_Final_Summaries"
FIGURES = ROOT / "04_Figures"

# Large intermediate artifacts are intentionally kept outside the public repository.
# Their presence is documented as EXTERNAL; repository-level summaries remain versioned.
files = [
    ("Forecast/OOS", "oos_volatility_345_v3.csv", "EXTERNAL", "", "344 usable tickers; 15 models; ticker-level OOS forecasts are versioned in 04_OOS_Forecasts_By_Ticker"),
    ("Options", "options_panel_342_LOCKED_2026-09-17.csv", "PRESENT", "342 integrated option tickers"),
    ("Merge", "oos_options_merged_342.csv", "EXTERNAL", "", "Large intermediate merge; 3,005,230 observations; 342 tickers; 15 models"),
    ("Pricing", "black76_pricing_336.csv", "EXTERNAL", "", "Large intermediate pricing file; 2,172,421 observations; 336 tickers; 15 models"),
    ("Strategy", "strategy_signals_336.csv", "EXTERNAL", "", "Large intermediate signal file; 308,603 baseline signals"),
    ("Vega", "strategy_signals_vega_hedge_full_336.csv", "EXTERNAL", "", "Large intermediate hedge file; 286,634 paired vega-hedged signals"),
    ("Trades", "backtest_trades_15models_3horizons_278.csv", "EXTERNAL", "", "Large trade-level artifact; 555,659 realised baseline trades; 278 tickers"),
    ("Capital", "portfolio_capital_1m_metrics_15models_3horizons_278.csv", "PRESENT", "USD 1m reference capital"),
    ("Risk", "risk_metrics_1m_15models_3horizons_278.csv", "PRESENT", "45 model-horizon cells"),
    ("Robustness", "robustness_thresholds_1p0_1p5_2p0.csv", "PRESENT", "thresholds 1.0/1.5/2.0"),
    ("Paired P&L", "trade_pnl_paired_esg_vs_benchmark_thresholds.csv", "PRESENT", "216 paired cells; Holm correction"),
]

rows = []
for stage, name, expected_status, notes in files:
    p = SUMMARY / name
    if expected_status == "PRESENT":
        status = "PRESENT" if p.exists() else "MISSING"
        size = p.stat().st_size if p.exists() else ""
    else:
        status = "EXTERNAL"
        size = ""
    rows.append([stage, name, status, size, notes])

out = SUMMARY / "FINAL_EMPIRICAL_RESULTS_INDEX_2026-09-20.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["stage", "file", "status", "bytes", "notes"])
    w.writerows(rows)

figs = sorted(x.name for x in FIGURES.glob("Figure_*.svg"))
out2 = SUMMARY / "FINAL_FIGURE_INDEX_2026-09-20.csv"
with out2.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["figure", "status", "bytes"])
    for name in figs:
        p = FIGURES / name
        w.writerow([name, "VALID_NONEMPTY" if p.stat().st_size > 0 else "EMPTY", p.stat().st_size])

print("RESULT_INDEX", out)
print("FIGURE_INDEX", out2)
print("FIGURES", len(figs))
print("MISSING_LOCAL", sum(r[2] == "MISSING" for r in rows))
