# ESG-Adjusted Volatility Forecasts and Equity Option Trading

Clean reproducibility package for the final thesis empirical pipeline.

Final configuration:
- Forecasting panel: 344 usable firms
- Integrated option panel: 342 firms
- Option pricing sample: 336 firms
- Trading sample: 278 firms
- 15 volatility specifications
- 252-observation minimum history
- 21-trading-day refit frequency
- OOS window: 12 January 2010 to 28 June 2019
- Option source: OptionMetrics
- LSEG forward price used in Black-76
- Baseline threshold: |Z| >= 1.5
- Baseline completed trades: 555,659

Structure:
00_Documentation ;
01_Thesis ;
02_Code ;
03_Data_and_Results ;
04_Figures ;

Raw licensed OptionMetrics, LSEG and other restricted source data are not redistributed. The source_data_manifest.csv records the authoritative local files, sizes and SHA-256 hashes where practical. Large derived datasets are also excluded because normal GitHub repository limits are not suitable for multi-hundred-megabyte or gigabyte files.

Temporary document-editing, debugging and one-off repair utilities are intentionally excluded from this clean research package. The local thesis working directory remains the historical archive.

The authoritative empirical index is dated 20 September 2026. Final backtest QC: 555,659 baseline trades, no duplicates, no critical nulls and no non-finite numeric observations.
