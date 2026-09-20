import csv
import os
import lseg.data as ld

ROOT = r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse"
SRC = os.path.join(ROOT, r"Data\03_Rebuild\00_Master\universe_options_404.csv")
DST = os.path.join(ROOT, r"Data\03_Rebuild\00_Master\universe_lseg_mapping.csv")

with open(SRC, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
tickers = [r["ticker"] for r in rows]

ld.open_session()
parts = []
print(f"Converting {len(tickers)} option tickers to LSEG RICs...")
for i, ticker in enumerate(tickers, 1):
    try:
        df = ld.discovery.convert_symbols(
            [ticker],
            from_symbol_type="TickerSymbol",
            to_symbol_types="RIC",
            preferred_country_code="USA",
        )
        if len(df):
            x = df.iloc[0]
            parts.append({
                "ticker_input": ticker,
                "RIC": str(x.get("RIC", "") or ""),
                "DocumentTitle": str(x.get("DocumentTitle", "") or ""),
            })
        else:
            parts.append({"ticker_input": ticker, "RIC": "", "DocumentTitle": ""})
        if i % 20 == 0:
            print(f"{i}/{len(tickers)} done", flush=True)
    except Exception as exc:
        parts.append({"ticker_input": ticker, "RIC": "", "DocumentTitle": f"ERROR: {exc}"})
        print(f"ERROR {ticker}: {exc}", flush=True)

ld.close_session()
mp = {p["ticker_input"].upper(): p for p in parts if p["ticker_input"]}
out = []
for r in rows:
    p = mp.get(r["ticker"].upper(), {})
    out.append({
        **r,
        "RIC": p.get("RIC", ""),
        "DocumentTitle": p.get("DocumentTitle", ""),
        "mapping_status": "MAPPED" if p.get("RIC") else "UNMAPPED",
    })
fields = list(out[0].keys())
with open(DST, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

mapped = sum(x["mapping_status"] == "MAPPED" for x in out)
print(f"Saved {DST}")
print(f"Mapped={mapped}; Unmapped={len(out)-mapped}")
