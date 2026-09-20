# Repository Map

## 00_Documentation
Reproducibility, provenance, repository scope, and data-access notes.

## 01_Thesis
Final thesis document dated 20 September 2026.

## 02_Code
The code follows the empirical pipeline in the same order as the thesis:

1. 01_Data_Preparation — starts from the 404 options tickers, performs LSEG mapping and historical-identity checks, and downloads the 345-firm price panel used for the candidate master panel.
2. 02_Volatility_Forecasting — runs the locked 344-firm, 15-model OOS volatility stage with the final lower log-variance bound of -10 and upper bound of +5, plus the final forecast/regime tests.
3. 03_Option_Pricing — integrates the 342-firm option panel, extracts the canonical pricing observations, applies Black-76 using the LSEG forward, and runs the final mispricing tests on the 336-firm pricing sample.
4. 04_Trading_and_QC — constructs the baseline |Z| >= 1.5 signals, performs vega pairing, builds the realised backtest, capital/P&L outputs, final indexes and QC.

Only scripts corresponding to the established final pipeline are included. Pilot, superseded, patch, debugging and one-off repair utilities are excluded.

## 03_Data_and_Results
01_Master_Audits: 404-ticker universe, LSEG mapping/identity and availability audits, and the frozen 345-firm candidate panel.
02_Final_Summaries: authoritative compact empirical outputs.
03_Audit_and_Provenance: source-data manifest.
04_OOS_Forecasts_By_Ticker: authoritative lower-bound-10 OOS forecasts, split by ticker.

## 04_Figures
Final figures used in the empirical presentation.

The empirical counts documented by the final index are 404 initial option tickers, 345 candidate firms, 344 forecasting firms, 342 option-panel firms, 336 Black-76 pricing firms and 278 realised trading firms.
