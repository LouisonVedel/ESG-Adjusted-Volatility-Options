# ESG-Adjusted Volatility Forecasts and Equity Option Trading

Clean reproducibility package for the final thesis empirical pipeline, dated 20 September 2026.

## Empirical pipeline

The research universe is defined first from the options dataset, which contains 404 initial tickers. These firms are then subjected to LSEG identity/mapping, historical-identity, price-availability and ESG-availability checks before the forecasting panel is frozen.

The final sequence is:

404 option tickers → LSEG mapping and identity checks → price/ESG availability → 345-candidate master panel → EVHC exclusion → 344-firm forecasting panel → returns and ESG(t−1) alignment → 15-model OOS volatility forecasting → 342-firm option panel → 336-firm Black-76 pricing sample → realised trading sample → vega-hedged backtest and QC.

## Final configuration

- Initial options universe: 404 tickers
- Candidate master panel: 345 firms
- Final forecasting panel: 344 usable firms
- Integrated option panel: 342 firms
- Black-76 pricing sample: 336 firms
- Realised trading sample: 278 firms
- Volatility specifications: 15
- Minimum history: 252 observations
- Refit frequency: every 21 trading days
- OOS window: 12 January 2010 to 28 June 2019
- Option source: OptionMetrics
- Equity/market data: Refinitiv Eikon / LSEG
- LSEG forward price used directly in Black-76
- Baseline threshold: |Z| >= 1.5
- Baseline completed trades: 555,659

## Structure

- 00_Documentation — reproducibility, provenance and repository scope
- 01_Thesis — final thesis document
- 02_Code — final research-pipeline code, ordered by empirical stage
- 03_Data_and_Results — compact audits, summaries, provenance and authoritative outputs
- 04_Figures — final empirical figures

The code in 02_Code is intentionally restricted to the scripts corresponding to the established final pipeline. Pilot, superseded, patch, debugging and one-off repair scripts remain in the local thesis working directory and are not part of this clean package.

Each packaged Python script begins with a short provenance note indicating that the code was developed with the assistance of AI.

Raw licensed OptionMetrics, LSEG and other restricted source data are not redistributed. Large derived datasets are likewise excluded where repository limits make redistribution impractical; their local provenance is documented in the manifest.

The authoritative empirical index is dated 20 September 2026. Final backtest QC reports 555,659 baseline trades, no duplicates, no critical nulls and no non-finite numeric observations.
