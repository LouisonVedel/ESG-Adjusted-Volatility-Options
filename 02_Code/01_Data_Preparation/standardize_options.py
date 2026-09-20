from pathlib import Path
import json, logging, re, time
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

OOS = Path(r"C:\ThesisRebuild\03_Volatility_OOS\final\oos_volatility_345_v3.csv")
RAW = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\01_Raw\Options")
OUT = Path(r"C:\Users\Louison Vedel\OneDrive - Audencia\Thèse\Data\02_Processed\Options_Clean")
CK = OUT / "_checkpoint_missing_tickers.json"
log = logging.getLogger("options")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

def targets():
    # Missing OOS tickers to recover from the raw 58 GB option universe.
    return set([
        "CDNS", "CI", "ILMN", "IR", "JNJ", "JNPR", "KHC", "NLSN", "NVDA",
        "PPL", "SCG", "SLB", "SNA", "SPG", "STT", "SWK", "TRIP", "TSCO",
        "TSS", "TWX", "TXT", "UAA", "VIAB", "WAT", "WBA", "WLTW", "XEC"
    ])

def out_ticker(p):
    m = re.match(r"^(.+?)_\d+_options\.csv$", p.name)
    return m.group(1).upper() if m else None

def checkpoint():
    return set(json.loads(CK.read_text())) if CK.exists() else set()

def save(s):
    CK.write_text(json.dumps(sorted(s), indent=2))

def ticker_scan(src, wanted):
    """Read ONLY the ticker column. No conversion of the other columns."""
    reader = pacsv.open_csv(src,
        read_options=pacsv.ReadOptions(use_threads=True, block_size=1 << 22,
                                       column_names=None),
        convert_options=pacsv.ConvertOptions(include_columns=["ticker"],
                                              column_types={"ticker": pa.string()}))
    found = set()
    while True:
        try:
            b = reader.read_next_batch()
        except StopIteration:
            break
        if b is None or b.num_rows == 0:
            break
        vals = set(x.as_py().upper() for x in b["ticker"] if x.as_py())
        found |= (vals & wanted)
        if found == wanted:
            break
    return found

def extract_file(src, wanted):
    """Only files identified by ticker_scan are parsed fully."""
    columns = ["secid", "date", "exdate", "cp_flag", "strike_price", "best_bid", "best_offer",
               "volume", "open_interest", "impl_volatility", "delta", "gamma", "optionid",
               "forward_price", "cusip", "ticker", "index_flag", "issuer", "exercise_style"]
    types = {c: pa.string() for c in columns}
    reader = pacsv.open_csv(src,
        read_options=pacsv.ReadOptions(use_threads=True, block_size=1 << 22),
        convert_options=pacsv.ConvertOptions(include_columns=columns, column_types=types))
    handles = {}
    counts = {}
    while True:
        try:
            b = reader.read_next_batch()
        except StopIteration:
            break
        if b is None or b.num_rows == 0:
            break
        pdf = pa.Table.from_batches([b]).to_pandas()
        pdf["ticker"] = pdf["ticker"].str.upper()
        pdf = pdf[pdf["ticker"].isin(wanted)]
        pdf = pdf[pdf["index_flag"].fillna("") != "1"]
        pdf = pdf[pdf["date"].fillna("").between("20100101", "20191231")]
        if pdf.empty:
            continue
        for ticker, g in pdf.groupby("ticker", sort=False):
            secids = g["secid"].dropna().unique()
            secid = secids[0] if len(secids) else "0"
            out = OUT / f"{ticker}_{secid}_options.csv"
            if ticker not in handles:
                handles[ticker] = open(out, "a", encoding="utf-8", newline="")
                if out.stat().st_size == 0:
                    g.head(0).to_csv(handles[ticker], index=False)
            g.to_csv(handles[ticker], index=False, header=False)
            handles[ticker].flush()
            counts[ticker] = counts.get(ticker, 0) + len(g)
    for h in handles.values():
        h.close()
    return counts

def validate(wanted):
    files = {out_ticker(f): f for f in OUT.glob("*_options.csv") if out_ticker(f)}
    present = set(files)
    missing = sorted(wanted - present)
    extra = sorted(present - wanted)
    empty = sorted(t for t, f in files.items() if f.stat().st_size == 0)
    log.info("FINAL: %d/%d tickers", len(present), len(wanted))
    log.info("Missing: %s", missing)
    log.info("Extra: %s", extra)
    log.info("Empty: %s", empty)
    return not missing and not extra and not empty

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = targets()
    present = {out_ticker(f) for f in OUT.glob("*_options.csv") if out_ticker(f)}
    missing = wanted
    log.info("TARGET RECOVERY MODE")
    log.info("OOS missing universe = %d tickers", len(wanted))
    log.info("Tickers: %s", ", ".join(sorted(wanted)))
    log.info("Already present among targets = %d", len(present & wanted))
    log.info("To recover = %d", len(missing))
    if not missing:
        log.info("Nothing to recover.")
        return 0

    raws = sorted(RAW.glob("options *.csv"))
    # Intentionally ignore the previous checkpoint: this run must scan the full raw universe.
    done = set()
    log.info("PASS 1: scanning ticker column across ALL %d raw files", len(raws))
    file_hits = {}
    for i, src in enumerate(raws, 1):
        t0 = time.time()
        try:
            hit = ticker_scan(src, missing)
        except Exception as e:
            log.error("SCAN ERROR %s: %s", src.name, e)
            hit = set()
        if hit:
            file_hits[src] = hit
            log.info("FOUND %s -> %s (%.1fs)", src.name, ", ".join(sorted(hit)), time.time() - t0)
        log.info("SCAN %d/%d | %.1fs | recovered targets=%d/%d", i, len(raws),
                 time.time() - t0, len(set().union(*file_hits.values())) if file_hits else 0, len(missing))

    covered = set().union(*file_hits.values()) if file_hits else set()
    log.info("Ticker scan found %d/%d missing tickers", len(covered), len(missing))
    if covered != missing:
        log.warning("Not all missing tickers were located. Missing after scan: %s",
                    ", ".join(sorted(missing - covered)))

    log.info("PASS 2: full extraction ONLY for files containing target tickers")
    for src, hit in file_hits.items():
        t0 = time.time()
        counts = extract_file(src, hit)
        log.info("EXTRACT %s -> %s (%.1fs)", src.name,
                 ", ".join(f"{k}:{v:,}" for k, v in sorted(counts.items())), time.time() - t0)

    ok = validate(wanted)
    if not ok:
        raise RuntimeError("Options_Clean validation failed")
    log.info("SUCCESS: exact target option universe recovered.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
