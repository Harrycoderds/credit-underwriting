"""
report.py - writes reports/credit_report.xlsx.

Red fill = a breach: a ratio failing its proposed covenant, or DSCR below 1.00x.
"""
import os

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.load_data import ROOT, read_config

REPORT_PATH = os.path.join(ROOT, "reports", "credit_report.xlsx")
RED = PatternFill("solid", fgColor="FFC7CE")
RED_FONT = Font(color="9C0006", bold=True)
HEAD = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(color="FFFFFF", bold=True)
BOLD = Font(bold=True)

FMT = {"x": '0.00"x"', "pct": "0.0%", "m": "#,##0.0", "cad": "#,##0", "int": "0", "rate": "0.00%"}


def _fmt_for(col):
    c = col.lower()
    if c in ("rating", "standalone_rating", "pro_forma_rating", "combined_stress_rating", "fiscal_year", "points"):
        return FMT["int"]
    if any(k in c for k in ("headroom", "fcf_debt", "debt_capital", "ltv", "debt_yield", "difference_pct", "floating_share",
                            "cap_rate", "loan_rate", "spread", "weight", "shock")):
        return FMT["pct"]
    if any(k in c for k in ("debt_ebitda", "interest", "fccr", "dscr", "current_ratio", "max_debt", "min_interest")):
        return FMT["x"] if "expense" not in c else FMT["m"]
    if c == "ratio_value":
        return "0.00"
    if c in ("noi", "value", "loan", "debt_service"):
        return FMT["cad"]
    return FMT["m"]


def write_table(ws, df, row=1, col=1, title=None, fmts=None):
    """Write a DataFrame with a styled header; returns the next free row."""
    if title:
        ws.cell(row=row, column=col, value=title).font = Font(bold=True, size=12)
        row += 1
    for j, name in enumerate(df.columns):
        c = ws.cell(row=row, column=col + j, value=str(name))
        c.fill, c.font = HEAD, HEAD_FONT
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(rec):
            if isinstance(v, float) and pd.isna(v):
                v = None
            if hasattr(v, "item"):
                v = v.item()
            cell = ws.cell(row=row + i, column=col + j, value=v)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.number_format = (fmts or {}).get(df.columns[j], _fmt_for(df.columns[j]))
    return row + len(df) + 2


def autosize(ws, max_width=60):
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, width + 2), max_width)


def red_where(ws, header_row, n_rows, col_name, test):
    """Fill red any cell in column `col_name` whose value passes `test`."""
    headers = {ws.cell(row=header_row, column=j).value: j for j in range(1, ws.max_column + 1)}
    j = headers[col_name]
    hits = 0
    for i in range(header_row + 1, header_row + 1 + n_rows):
        v = ws.cell(row=i, column=j).value
        if v is not None and test(v):
            ws.cell(row=i, column=j).fill = RED
            ws.cell(row=i, column=j).font = RED_FONT
            hits += 1
    return hits


def write_report(res, spot, flags):
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    wb = Workbook()
    reds = 0

    # ---------------- Summary
    ws = wb.active
    ws.title = "Summary"
    rows = []
    for d in res["summary"]:
        rows.append({"deal": f"{d['name']} ({d['ticker']})", "fiscal_year": d["fiscal_year"],
                     "loan_cad_m": d["loan_amount"], "loan_rate": d["loan_rate"],
                     "standalone_rating": d["standalone_rating"], "pro_forma_rating": d["pro_forma_rating"],
                     "combined_stress_rating": d["combined_stress_rating"], "debt_ebitda": d["debt_ebitda"],
                     "ebitda_interest": d["ebitda_interest"], "dscr": d["dscr"], "combined_dscr": d["combined_dscr"],
                     "recommendation": d["recommendation"], "why": d["reasons"]})
    cre = res["cre"]
    tb = cre["table"].set_index(["scenario", "loan_case"])
    rows.append({"deal": "GTA industrial mortgage (hypothetical CRE)", "fiscal_year": None,
                 "loan_cad_m": cre["params"]["loan_requested"] / 1e6, "loan_rate": cre["rate"],
                 "standalone_rating": None, "pro_forma_rating": None, "combined_stress_rating": None,
                 "debt_ebitda": None, "ebitda_interest": None,
                 "dscr": tb.loc[("Base", "Requested"), "dscr"], "combined_dscr": tb.loc[("Combined", "Requested"), "dscr"],
                 "recommendation": cre["decision"],
                 "why": f"Requested loan fails DSCR; approve max supportable ${cre['max_loan']:,.0f} "
                        f"(binding constraint: {cre['binding']})"})
    summ = pd.DataFrame(rows)
    ws.cell(row=1, column=1, value="Credit Underwriting Toolkit - deal summary (CAD; ratings 1 = strongest, 10 = weakest; "
                                   "DSCR/ratios are pro forma with the new loan)").font = Font(bold=True, size=12)
    write_table(ws, summ, row=3)
    reds += red_where(ws, 3, len(summ), "combined_dscr", lambda v: v < 1.0)
    reds += red_where(ws, 3, len(summ), "dscr", lambda v: v < 1.0)
    autosize(ws)

    # ---------------- Spreads (one block per company)
    ws = wb.create_sheet("Spreads")
    row = 1
    items = ["revenue", "ebitda", "ebit", "interest_expense", "taxes", "capex", "ocf", "cash", "current_assets",
             "current_liabilities", "total_debt", "lease_liabilities", "equity"]
    companies = read_config("companies.csv").set_index("ticker")
    for t, g in res["spreads"].groupby("ticker", sort=False):
        block = g.set_index("fiscal_year")[items].T
        block.columns = [f"FY{c}" for c in block.columns]
        block.insert(0, "line_item (CAD millions)", block.index)
        row = write_table(ws, block, row=row,
                          title=f"{companies.loc[t, 'name']} ({t}) - {companies.loc[t, 'units']}, FYE {companies.loc[t, 'fiscal_year_end']}. "
                                "Total debt includes lease liabilities.")
    autosize(ws)

    # ---------------- Ratios
    ws = wb.create_sheet("Ratios")
    rt = res["ratios"].drop(columns=["period_end"])
    ws.cell(row=1, column=1, value="Ratios by year (from SQL view v_ratio_trends). 99 = not meaningful (negative EBITDA or capital). "
                                   "Red = Debt/EBITDA above, or EBITDA/Interest below, the proposed covenant.").font = BOLD
    write_table(ws, rt, row=3)
    hdr = {ws.cell(row=3, column=j).value: j for j in range(1, ws.max_column + 1)}
    for i in range(4, 4 + len(rt)):
        t = ws.cell(row=i, column=hdr["ticker"]).value
        co = companies.loc[t]
        for name, bad in (("debt_ebitda", lambda v: v > co["cov_max_debt_ebitda"]),
                          ("ebitda_interest", lambda v: v < co["cov_min_interest_cover"])):
            c = ws.cell(row=i, column=hdr[name])
            if c.value is not None and bad(c.value):
                c.fill, c.font = RED, RED_FONT
                reds += 1
    autosize(ws, 22)

    # ---------------- Scorecard
    ws = wb.create_sheet("Scorecard")
    sc_cfg = read_config("scorecard.csv")
    r = write_table(ws, sc_cfg, fmts={f"t{i}": "General" for i in range(1, 6)}, title="Scorecard design (config/scorecard.csv). Points: band 1-6 = 1, 3, 5, 7, 9, 10. "
                                     "Thresholds are my own design, loosely informed by typical rating-agency ranges.")
    write_table(ws, res["scorecard"], row=r, title="Scores for the latest fiscal year: standalone and pro forma with the new loan")
    autosize(ws, 40)

    # ---------------- Stress
    ws = wb.create_sheet("Stress")
    st = res["stress"]
    ws.cell(row=1, column=1, value="Pro forma stress tests. Red = DSCR below 1.00x.").font = BOLD
    write_table(ws, st, row=3)
    reds += red_where(ws, 3, len(st), "dscr", lambda v: v < 1.0)
    autosize(ws)

    # ---------------- Covenants
    ws = wb.create_sheet("Covenants")
    cv = res["covenants"]
    ws.cell(row=1, column=1, value="Proposed covenants and headroom (share EBITDA can fall before breach). Red = breach.").font = BOLD
    write_table(ws, cv, row=3)
    reds += red_where(ws, 3, len(cv), "leverage_headroom", lambda v: v < 0)
    reds += red_where(ws, 3, len(cv), "coverage_headroom", lambda v: v < 0)
    reds += red_where(ws, 3, len(cv), "leverage_breach", lambda v: v is True)
    reds += red_where(ws, 3, len(cv), "coverage_breach", lambda v: v is True)
    autosize(ws)

    # ---------------- CRE_Deal
    ws = wb.create_sheet("CRE_Deal")
    c = cre["params"]
    key = pd.DataFrame([
        {"metric": "NOI", "value": cre["noi"]}, {"metric": "Value (NOI / cap rate)", "value": cre["value"]},
        {"metric": "Loan rate (5y GoC + spread)", "value": cre["rate"]},
        {"metric": "Max loan - LTV limit", "value": cre["limits"]["LTV"]},
        {"metric": "Max loan - DSCR limit", "value": cre["limits"]["DSCR"]},
        {"metric": "Max loan - debt yield limit", "value": cre["limits"]["Debt yield"]},
        {"metric": f"Max supportable loan (binding: {cre['binding']})", "value": cre["max_loan"]},
        {"metric": "Requested loan", "value": c["loan_requested"]}])
    r = write_table(ws, key, title="HYPOTHETICAL GTA industrial mortgage - key results (CAD)")
    for i in range(3, 3 + len(key)):
        ws.cell(row=i, column=2).number_format = FMT["rate"] if "rate" in ws.cell(row=i, column=1).value else FMT["cad"]
    write_table(ws, cre["table"], row=r, title=f"Scenarios (red = fails policy/covenant: DSCR below {c['min_dscr']:.2f}x "
                                               f"or LTV above {c['max_ltv']:.0%}; DSCR below 1.00x means NOI does not cover payments)")
    reds += red_where(ws, r + 1, len(cre["table"]), "dscr", lambda v: v < c["min_dscr"] - 1e-9)
    reds += red_where(ws, r + 1, len(cre["table"]), "ltv", lambda v: v > c["max_ltv"] + 1e-9)
    autosize(ws, 50)

    # ---------------- Spot_Checks
    ws = wb.create_sheet("Spot_Checks")
    write_table(ws, spot, title="yfinance vs annual report, latest fiscal year (CAD millions). "
                                "Differences above the materiality threshold are replaced with the annual report value.")
    autosize(ws, 80)

    # ---------------- Assumptions
    ws = wb.create_sheet("Assumptions")
    r = write_table(ws, read_config("assumptions.csv"), title="General assumptions and sources",
                    fmts={"value": "General"})
    cols = ["ticker", "loan_purpose", "loan_amount", "loan_spread", "spread_source", "loan_tenor_years", "loan_amort_years",
            "existing_floating_share", "floating_share_source", "lease_principal", "lease_principal_source",
            "cov_max_debt_ebitda", "cov_min_interest_cover"]
    r = write_table(ws, read_config("companies.csv")[cols], row=r, title="Hypothetical loan requests (CAD millions) - all hypothetical")
    r = write_table(ws, read_config("cre_deal.csv"), row=r, title="CRE deal inputs (each sourced or labelled 'Assumption')",
                    fmts={"value": "General"})
    write_table(ws, flags, row=r, title="Data notes (missing items, substitutions, spot-check replacements)")
    autosize(ws, 70)

    wb.save(REPORT_PATH)
    return REPORT_PATH, reds
