"""
load_data.py - download annual statements, spread them into one standard
template, apply annual-report spot-check corrections, and load SQLite.

All amounts are stored in CAD millions (all three companies report in CAD).
"""
import os
import sqlite3

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
DB_PATH = os.path.join(ROOT, "data", "credit.db")
CONFIG_DIR = os.path.join(ROOT, "config")
SQL_PATH = os.path.join(ROOT, "sql", "ratios.sql")
N_YEARS = 4

# Standard spread line item -> (statement, list of yfinance labels tried in order)
SPREAD_MAP = {
    "revenue":             ("is", ["Total Revenue", "Operating Revenue"]),
    "ebitda":              ("is", ["EBITDA"]),
    "ebit":                ("is", ["EBIT", "Operating Income"]),
    "interest_expense":    ("is", ["Interest Expense", "Interest Expense Non Operating"]),
    "taxes":               ("is", ["Tax Provision"]),
    "capex":               ("cf", ["Capital Expenditure"]),
    "ocf":                 ("cf", ["Operating Cash Flow"]),
    "cash":                ("bs", ["Cash And Cash Equivalents"]),
    "current_assets":      ("bs", ["Current Assets"]),
    "current_liabilities": ("bs", ["Current Liabilities"]),
    "total_debt":          ("bs", ["Total Debt"]),
    "lease_liabilities":   ("bs", ["Capital Lease Obligations"]),
    "equity":              ("bs", ["Stockholders Equity", "Common Stock Equity"]),
    # reference only (not used in ratios): yfinance's EBITDA excluding unusual items
    "ebitda_normalized":   ("is", ["Normalized EBITDA"]),
}
ONE_OFF_GAP = 0.20   # reported vs normalized EBITDA gap that marks a year as distorted by one-offs
SPREAD_ITEMS = list(SPREAD_MAP)

_warnings = []


def warn(msg):
    _warnings.append(msg)
    print(f"  WARNING: {msg}")


def warnings():
    return list(_warnings)


def read_config(name):
    return pd.read_csv(os.path.join(CONFIG_DIR, name))


def assumptions():
    df = read_config("assumptions.csv")
    return dict(zip(df["key"], df["value"].astype(float)))


# ---------------------------------------------------------------- download
def fetch_statements(ticker, refresh=False):
    """Return {'is','bs','cf'} DataFrames (rows = labels, cols = period end). Cached to data/raw/."""
    os.makedirs(RAW_DIR, exist_ok=True)
    paths = {k: os.path.join(RAW_DIR, f"{ticker}_{k}.csv") for k in ("is", "bs", "cf")}
    if refresh or not all(os.path.exists(p) for p in paths.values()):
        import yfinance as yf
        print(f"  downloading {ticker} from yfinance")
        tk = yf.Ticker(ticker)
        frames = {"is": tk.income_stmt, "bs": tk.balance_sheet, "cf": tk.cashflow}
        for k, df in frames.items():
            if df is None or df.empty:
                raise RuntimeError(f"yfinance returned no {k} data for {ticker}")
            df.to_csv(paths[k])
    else:
        print(f"  using cached statements for {ticker}")
    out = {}
    for k, p in paths.items():
        df = pd.read_csv(p, index_col=0)
        df.columns = pd.to_datetime(df.columns)
        out[k] = df
    return out


# ---------------------------------------------------------------- spreading
def spread_company(ticker, stmts, flags):
    """Map raw yfinance statements to the standard template (CAD millions)."""
    inc = stmts["is"]
    periods = [c for c in sorted(inc.columns, reverse=True)
               if "Total Revenue" in inc.index and pd.notna(inc.loc["Total Revenue", c])][:N_YEARS]
    rows = []
    for p in periods:
        row = {"ticker": ticker, "fiscal_year": p.year, "period_end": p.date().isoformat()}
        for item, (stmt, labels) in SPREAD_MAP.items():
            df = stmts[stmt]
            val, used = None, None
            if p in df.columns:
                for lab in labels:
                    if lab in df.index and pd.notna(df.loc[lab, p]):
                        val, used = float(df.loc[lab, p]) / 1e6, lab
                        break
            if val is None:
                if item == "lease_liabilities":
                    val = 0.0  # no leases reported -> 0, not a data gap for the ratios
                    flags.append((ticker, p.year, item, "Not reported by yfinance; treated as 0 (no separate lease line)."))
                elif item == "ebitda_normalized":
                    flags.append((ticker, p.year, item, "Not reported; one-off check skipped for this year (reference item only)."))
                else:
                    flags.append((ticker, p.year, item, "Missing in yfinance; left blank. Ratios using it are blank for this year."))
            elif used != labels[0]:
                flags.append((ticker, p.year, item, f"Primary label missing; used yfinance '{used}' instead."))
            if item == "capex" and val is not None:
                val = abs(val)  # yfinance reports capex as a negative cash flow
            row[item] = val
        e, n = row.get("ebitda"), row.get("ebitda_normalized")
        row["one_off_year"] = int(e is not None and n not in (None, 0) and abs(e / n - 1) > ONE_OFF_GAP)
        if row["one_off_year"]:
            flags.append((ticker, p.year, "ebitda",
                          f"Reported EBITDA {e:,.1f} differs from yfinance normalized EBITDA {n:,.1f} by {e / n - 1:+.0%}: "
                          "year distorted by unusual items. Ratios use reported EBITDA (conservative, consistent); "
                          "memo trend statements skip this year."))
        rows.append(row)
    return rows


def apply_spot_checks(spreads, spot, materiality, flags):
    """Compare latest-year yfinance values to annual-report values; replace if the gap is material."""
    records = []
    for _, s in spot.iterrows():
        mask = (spreads["ticker"] == s["ticker"]) & (spreads["fiscal_year"] == s["fiscal_year"])
        yf_val = spreads.loc[mask, s["spread_item"]].iloc[0] if mask.any() else None
        ar = float(s["annual_report_value"])
        diff = None if yf_val is None or pd.isna(yf_val) else (yf_val - ar) / ar
        material = diff is None or abs(diff) > materiality
        if material and mask.any():
            spreads.loc[mask, s["spread_item"]] = ar
            flags.append((s["ticker"], int(s["fiscal_year"]), s["spread_item"],
                          f"Replaced yfinance value with annual report value {ar:,.1f} (diff {diff if diff is None else f'{diff:.1%}'})."))
        records.append({"ticker": s["ticker"], "figure": s["figure"], "fiscal_year": int(s["fiscal_year"]),
                        "yfinance_value": yf_val, "annual_report_value": ar,
                        "difference_pct": diff, "used": "annual report" if material else "yfinance (within tolerance)",
                        "source": s["source"]})
    return pd.DataFrame(records)


# ---------------------------------------------------------------- main entry
def load_all(refresh=False):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    companies = read_config("companies.csv")
    a = assumptions()
    flags, rows = [], []
    for t in companies["ticker"]:
        stmts = fetch_statements(t, refresh)
        rows += spread_company(t, stmts, flags)
    spreads = pd.DataFrame(rows)
    spot = apply_spot_checks(spreads, read_config("spot_checks.csv"), a["spot_check_materiality"], flags)

    for t, g in spreads.groupby("ticker"):
        if len(g) < 3:
            warn(f"{t}: only {len(g)} years of statements available (wanted 3-4).")
    for f in flags:
        if "Missing" in f[3]:
            warn(f"{f[0]} FY{f[1]} {f[2]}: {f[3]}")

    spreads.to_sql("spreads", conn, index=False)
    pd.DataFrame(flags, columns=["ticker", "fiscal_year", "item", "note"]).to_sql("flags", conn, index=False)
    spot.to_sql("spot_checks", conn, index=False)
    companies.to_sql("companies", conn, index=False)
    read_config("scorecard.csv").to_sql("scorecard", conn, index=False)
    read_config("assumptions.csv").to_sql("assumptions", conn, index=False)
    read_config("cre_deal.csv").to_sql("cre_deal", conn, index=False)
    with open(SQL_PATH) as fh:
        conn.executescript(fh.read())
    conn.commit()
    print(f"  {len(spreads)} company-years spread for {spreads['ticker'].nunique()} companies; "
          f"{len(flags)} data notes; database at data/credit.db")
    return conn
