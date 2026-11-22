"""
run_all.py - runs the whole credit underwriting pipeline end to end.

    python run_all.py            # uses cached statements in data/raw/ where available
    python run_all.py --refresh  # re-downloads statements from yfinance
"""
import os
import sys

import pandas as pd

from src import load_data
from src.credit import SCENARIOS, run_credit
from src.memos import write_memos
from src.report import write_report


def sanity_checks(res):
    """Hard checks that must hold for the results to make sense."""
    errors = []
    st = res["stress"]
    for t, g in st.groupby("ticker"):
        g = g.set_index("scenario")
        base = g.loc[SCENARIOS[0]]
        for name in SCENARIOS[1:]:
            if g.loc[name, "ebitda_interest"] > base["ebitda_interest"] + 1e-9:
                errors.append(f"{t}: interest coverage improved under '{name}'")
            if g.loc[name, "dscr"] > base["dscr"] + 1e-9:
                errors.append(f"{t}: DSCR improved under '{name}'")
            if g.loc[name, "rating"] < base["rating"]:
                errors.append(f"{t}: rating improved under '{name}'")
    ratings = [d["standalone_rating"] for d in res["summary"]]
    if len(set(ratings)) < len(ratings):
        errors.append(f"Companies do not land in different ratings: {ratings}")
    cre = res["cre"]
    tb = cre["table"].set_index(["scenario", "loan_case"])
    mx = tb.loc[("Base", "Max supportable")]
    c = cre["params"]
    if mx["ltv"] > c["max_ltv"] + 1e-9 or mx["dscr"] < c["min_dscr"] - 1e-9 or mx["debt_yield"] < c["min_debt_yield"] - 1e-9:
        errors.append("CRE max loan breaks a sizing constraint")
    return errors


def main():
    refresh = "--refresh" in sys.argv

    print("\n[1/5] Loading statements, spreading, spot checks -> SQLite")
    conn = load_data.load_all(refresh=refresh)
    spot = pd.read_sql("SELECT * FROM spot_checks", conn)
    flags = pd.read_sql("SELECT * FROM flags", conn)
    for _, s in spot.iterrows():
        print(f"  spot check {s['ticker']:7s} {s['figure'][:40]:40s} yfinance {s['yfinance_value']:>9,.1f}  "
              f"annual report {s['annual_report_value']:>9,.1f}  diff {s['difference_pct']:+.2%}  -> {s['used']}")

    print("\n[2/5] Ratios (SQL views), scorecard ratings, stress tests, covenants, CRE deal")
    res = run_credit(conn)
    for d in res["summary"]:
        print(f"  {d['ticker']:7s} rating {d['standalone_rating']:>2} standalone / {d['pro_forma_rating']:>2} pro forma / "
              f"{d['combined_stress_rating']:>2} combined stress | Debt/EBITDA {d['debt_ebitda']:.2f}x | "
              f"DSCR {d['dscr']:.2f}x -> {d['combined_dscr']:.2f}x stressed | {d['recommendation']}")
    cre = res["cre"]
    print(f"  CRE     NOI ${cre['noi']:,.0f} | value ${cre['value']:,.0f} | max loan ${cre['max_loan']:,.0f} "
          f"({cre['binding']} binds) vs ${cre['params']['loan_requested']:,.0f} requested -> {cre['decision']}")

    print("\n[3/5] Sanity checks")
    errors = sanity_checks(res)
    for e in errors:
        print(f"  ERROR: {e}")
    if not errors:
        print("  all passed")

    print("\n[4/5] Writing credit memos")
    for p in write_memos(res):
        print(f"  {os.path.relpath(p, load_data.ROOT)}")

    print("\n[5/5] Writing Excel workbook")
    path, reds = write_report(res, spot, flags)
    print(f"  {os.path.relpath(path, load_data.ROOT)} ({reds} cells highlighted red)")

    if load_data.warnings():
        print(f"\n{len(load_data.warnings())} warning(s) - see above.")
    conn.close()
    if errors:
        sys.exit(1)
    print("\nDone.")


if __name__ == "__main__":
    main()
