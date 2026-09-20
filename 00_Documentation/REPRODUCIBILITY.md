# Reproducibility and Data Provenance

The volatility stage uses the locked 344-firm forecasting panel and 15-model OOS output. The option stage uses the locked integrated option panel, merged forecast-option observations, Black-76 pricing outputs, signal construction, vega-hedged trade records, and final backtest/QC files.

Equity and market-data fields used in the rebuild were obtained through Refinitiv Eikon / LSEG. The option dataset is sourced from OptionMetrics, while the LSEG forward price is used directly in the Black-76 pricing stage. The USD 1 million capital figure is a reference notional used to express strategy performance on a common scale, not a broker margin requirement.

The final empirical index dated 20 September 2026 records the authoritative files for forecasting, option integration, pricing, strategy signals, vega hedging, realised trades, capital metrics, risk metrics, threshold robustness, and paired P&L tests.

The final backtest QC reports 555,659 baseline trades, no duplicates, no critical nulls, and no non-finite numeric observations.

Raw licensed source data and vendor-derived quote-level datasets are not redistributed. Their local provenance, file sizes, and SHA-256 hashes where practical are recorded in source_data_manifest.csv. Large authoritative outputs exceeding GitHub's single-file limit are retained locally and referenced by the manifest.
