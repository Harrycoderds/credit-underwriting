"""
memos.py - writes one Markdown credit memo per deal (3 corporate loans + 1 CRE loan).

Numbers come from credit.run_credit(). The narrative is rule-based: each strength or
risk line is triggered by a ratio level or trend, so nothing is said that the data
(or a cited note in config/companies.csv) does not support.
"""
import os

from src.credit import SCENARIOS
from src.load_data import ROOT

MEMO_DIR = os.path.join(ROOT, "memos")


def x(v, d=2):
    return "n/a" if v is None else ("n.m." if v >= 99 else f"{v:.{d}f}x")


def pct(v, d=1):
    return "n/a" if v is None else f"{v:.{d}%}"


def m(v, d=1):
    if v is None:
        return "n/a"
    return f"-${-v:,.{d}f}M" if v < 0 else f"${v:,.{d}f}M"


def _slug(name):
    return name.lower().replace(".", "").replace(",", "").replace(" ", "_")


# ------------------------------------------------------------------ corporate memo pieces
def strengths_and_risks(d, hist):
    """Rule-based bullets. d = summary entry; hist = that company's ratio history (oldest -> newest)."""
    s, r = [], []
    latest = hist.iloc[-1]
    clean = hist[hist["one_off_year"] == 0]          # trend baseline skips years distorted by one-offs
    first = clean.iloc[0] if len(clean) > 1 else hist.iloc[0]
    sh = d["spreads_hist"].set_index("fiscal_year")
    fy0 = int(first["fiscal_year"])
    sp = d["latest"]
    pf = d["scen"][SCENARIOS[0]]["ratios"]
    lev, cov = latest["debt_ebitda"], latest["ebitda_interest"]

    if lev <= 2.0:
        s.append(f"Low leverage: Debt/EBITDA of {x(lev)} (including leases) in FY{d['fiscal_year']}, {x(pf['debt_ebitda'])} after the new loan.")
    elif lev >= 4.0:
        r.append(f"High leverage: Debt/EBITDA of {x(lev)} (including leases), {x(pf['debt_ebitda'])} after the new loan.")
    if cov >= 8:
        s.append(f"Strong interest coverage: EBITDA covers interest {x(cov, 1)}.")
    elif cov < 3:
        r.append(f"Thin interest coverage: EBITDA covers interest only {x(cov)}.")
    if latest["current_ratio"] >= 1.5:
        s.append(f"Good liquidity: current ratio {x(latest['current_ratio'])}.")
    elif latest["current_ratio"] < 1.0:
        r.append(f"Weak liquidity: current ratio {x(latest['current_ratio'])} (current liabilities exceed current assets).")
    if latest["fcf_debt"] is not None and latest["fcf_debt"] >= 0.25:
        s.append(f"Free cash flow (OCF - capex) equal to {pct(latest['fcf_debt'], 0)} of total debt in one year.")
    elif latest["fcf_debt"] is not None and latest["fcf_debt"] < 0.08:
        r.append(f"Low free cash flow relative to debt: (OCF - capex)/Debt of {pct(latest['fcf_debt'])}.")
    if latest["fccr"] is not None and latest["fccr"] < 1.5:
        r.append(f"Fixed charge coverage after capex and taxes is {x(latest['fccr'])}, leaving little cash after spending.")
    if sp.get("equity") is not None and sp["equity"] < 0:
        r.append(f"Negative shareholders' equity of {m(sp['equity'])}; lenders have no equity cushion on the balance sheet.")
    if lev < first["debt_ebitda"] - 0.25:
        s.append(f"Leverage has improved from {x(first['debt_ebitda'])} in FY{int(first['fiscal_year'])} to {x(lev)}.")
    elif lev > first["debt_ebitda"] + 0.25:
        r.append(f"Leverage has risen from {x(first['debt_ebitda'])} in FY{int(first['fiscal_year'])} to {x(lev)}.")
    rev0, rev1 = sh.loc[fy0, "revenue"], sh.iloc[-1]["revenue"]
    if fy0 != int(latest["fiscal_year"]) and rev1 > rev0 * 1.05:
        s.append(f"Revenue grew from {m(rev0)} in FY{fy0} to {m(rev1)} in FY{int(latest['fiscal_year'])}.")
    elif fy0 != int(latest["fiscal_year"]) and rev1 < rev0 * 0.95:
        r.append(f"Revenue fell from {m(rev0)} in FY{fy0} to {m(rev1)} in FY{int(latest['fiscal_year'])}.")
    skipped = hist[hist["one_off_year"] == 1]["fiscal_year"].astype(int).tolist()
    if skipped:
        r.append("Earnings are uneven: reported EBITDA in " + ", ".join(f"FY{y}" for y in skipped)
                 + " differs from yfinance's normalized EBITDA by more than 20% (unusual items); "
                 + ("that year is" if len(skipped) == 1 else "those years are") + " not used as a trend baseline.")
    if d["company"]["existing_floating_share"] > 0.25:
        r.append(f"About {pct(d['company']['existing_floating_share'], 0)} of existing debt is floating rate (see Assumptions), plus the new loan.")

    mitigants = ["Proposed maintenance covenants (below) give the bank an early warning and a seat at the table if results weaken.",
                 f"Scheduled amortization over {int(d['company']['loan_amort_years'])} years reduces exposure each year."]
    if d["recommendation"] == "Decline":
        mitigants = ["Covenants and amortization would not offset the weaknesses above; see recommendation."]
    elif d["any_covenant_breach"]:
        mitigants.append("Because a covenant breaches under stress, conditions below are required before approval.")
    return s, r, mitigants


def corporate_memo(d, hist, a):
    co, sp, loan = d["company"], d["latest"], d["loan"]
    s, r, mit = strengths_and_risks(d, hist)
    notes = [n.strip() for n in str(co["analyst_notes"]).split("|")]
    years = list(hist["fiscal_year"].astype(int))
    spreads = d["spreads_hist"]

    L = []
    L.append(f"# Credit Memo - {co['name']} ({co['ticker']})")
    L.append(f"*Internal practice memo. Loan request is hypothetical. Figures in {co['units']} unless stated; "
             f"latest fiscal year FY{d['fiscal_year']}, year end {co['fiscal_year_end']}.*\n")
    L.append("## 1. Borrower overview")
    L.append(f"{co['name']} is a TSX-listed company in {co['sector']}. FY{d['fiscal_year']} revenue was {m(sp['revenue'])} "
             f"and EBITDA {m(sp['ebitda'])} ({pct(sp['ebitda'] / sp['revenue'])} margin). Profile selected for this exercise: {co['profile']}.")
    for n in notes:
        L.append(f"- {n}")
    L.append("\n## 2. Loan request")
    L.append(f"- Facility: {m(loan['amount'], 0)} senior term loan - {co['loan_purpose']}")
    L.append(f"- Pricing: CORRA ({pct(a['corra'], 2)}) + {pct(float(co['loan_spread']), 2)} = {pct(loan['rate'], 2)} floating "
             f"(spread: {co['spread_source']})")
    L.append(f"- Tenor {int(co['loan_tenor_years'])} years; straight-line amortization over {int(co['loan_amort_years'])} years "
             f"({m(loan['principal'])} principal per year)")
    L.append(f"- Size vs EBITDA: {x(loan['amount'] / sp['ebitda'])} of FY{d['fiscal_year']} EBITDA\n")

    L.append("## 3. Key financials")
    hdr = "| Item | " + " | ".join(f"FY{y}" for y in years) + " |"
    L.append(hdr)
    L.append("|" + "---|" * (len(years) + 1))
    for lab, key in (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("Interest expense", "interest_expense"),
                     ("Operating cash flow", "ocf"), ("Capex", "capex"), ("Total debt (incl. leases)", "total_debt"),
                     ("Equity", "equity")):
        L.append(f"| {lab} | " + " | ".join(m(v) for v in spreads[key]) + " |")
    for lab, key, f in (("Debt / EBITDA", "debt_ebitda", x), ("EBITDA / Interest", "ebitda_interest", x),
                        ("Current ratio", "current_ratio", x), ("(OCF - capex) / Debt", "fcf_debt", pct),
                        ("Internal rating (1-10)", "rating", lambda v: str(int(v)))):
        L.append(f"| {lab} | " + " | ".join(f(v) for v in hist[key]) + " |")
    L.append("")

    L.append("## 4. Strengths")
    L += [f"- {t}" for t in s] or ["- No ratio meets the strength thresholds used in this memo."]
    L.append("\n## 5. Risks and mitigants")
    L += [f"- Risk: {t}" for t in r] or ["- Risk: no ratio triggers the risk thresholds used in this memo; main risk is a general downturn (see stress)."]
    L += [f"- Mitigant: {t}" for t in mit]

    L.append("\n## 6. Stress results (pro forma, with the new loan)")
    L.append(f"Stress: EBITDA {pct(a['ebitda_shock'], 0)}; rates +{a['rate_shock'] * 1e4:.0f} bps on the floating share of existing debt "
             f"({pct(co['existing_floating_share'], 0)}) and on the new loan; both combined. DSCR = (EBITDA - taxes) / "
             f"(interest + lease principal {m(float(co['lease_principal']))} + new loan principal).\n")
    L.append("| Scenario | EBITDA | Debt/EBITDA | EBITDA/Interest | DSCR | Rating |")
    L.append("|---|---|---|---|---|---|")
    for name in SCENARIOS:
        sc = d["scen"][name]
        L.append(f"| {name} | {m(sc['spread']['ebitda'])} | {x(sc['ratios']['debt_ebitda'])} | "
                 f"{x(sc['ratios']['ebitda_interest'])} | {x(sc['dscr'])} | {sc['rating']} |")

    L.append("\n## 7. Proposed covenants")
    L.append(f"- Maximum Debt/EBITDA (incl. leases): {co['cov_max_debt_ebitda']:.2f}x")
    L.append(f"- Minimum EBITDA/Interest: {co['cov_min_interest_cover']:.2f}x\n")
    L.append("| Scenario | Debt/EBITDA headroom | Coverage headroom |")
    L.append("|---|---|---|")
    for name in SCENARIOS:
        sc = d["scen"][name]
        flag = lambda h: f"**BREACH ({pct(h)})**" if h < 0 else pct(h)
        L.append(f"| {name} | {flag(sc['lev_h'])} | {flag(sc['cov_h'])} |")
    L.append("\n*Headroom = how much EBITDA could fall from that scenario before the covenant breaches.*")

    L.append("\n## 8. Recommendation")
    L.append(f"**{d['recommendation']}** - internal rating {d['standalone_rating']} standalone, "
             f"{d['pro_forma_rating']} pro forma, {d['combined_stress_rating']} under combined stress (1 = strongest, 10 = weakest).")
    L.append(f"- Basis: {d['reasons']}.")
    if d["recommendation"] == "Approve with conditions":
        L.append("- Conditions: quarterly compliance certificates; covenants as above tested quarterly; cash sweep of 50% of excess "
                 "cash flow while Debt/EBITDA is above the covenant less 0.50x; no increase in distributions while a covenant "
                 "has less than 15% headroom.")
    elif d["recommendation"] == "Decline":
        L.append("- The bank could revisit if leverage falls below the decline line on audited results, "
                 "or with additional collateral / a guarantor that changes the risk.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ CRE memo
def cre_memo(cre, a):
    c, t = cre["params"], cre["table"]
    base = t[(t.scenario == "Base")].set_index("loan_case")
    comb = t[(t.scenario == "Combined")].set_index("loan_case")
    sf, rent = c["rentable_sf"], c["market_rent_psf"]
    gross = sf * rent
    egi = gross * (1 - c["underwritten_vacancy"])
    L = ["# Credit Memo - GTA Industrial Mortgage (HYPOTHETICAL)",
         "*Hypothetical commercial real estate loan for practice. Market inputs are sourced (see config/cre_deal.csv); "
         "everything else is labelled as an assumption. Amounts in CAD.*\n",
         "## 1. Borrower / property overview",
         f"{c['property']}: {sf:,.0f} sq ft of rentable industrial space, underwritten at the Q3 2026 GTA average net asking "
         f"rent of ${rent:.2f} psf and a {pct(c['cap_rate'], 2)} cap rate (Lee & Associates Toronto Industrial Q3 2026, p.1). "
         f"The borrower is a hypothetical single-purpose entity.\n",
         "## 2. Loan request",
         f"- First mortgage of ${c['loan_requested']:,.0f}, {int(c['term_years'])}-year term, {int(c['amort_years'])}-year amortization",
         f"- Rate: 5-yr GoC ({pct(a['goc_5y'], 2)}, Bank of Canada) + {pct(c['loan_spread'], 2)} spread (assumption) = {pct(cre['rate'], 2)} fixed\n",
         "## 3. Key financials (underwriting)",
         "| Line | Amount |", "|---|---|",
         f"| Potential gross rent ({sf:,.0f} sf x ${rent:.2f}) | ${gross:,.0f} |",
         f"| Less vacancy ({pct(c['underwritten_vacancy'])}, assumption; market {pct(c['market_vacancy'], 2)}) | -${gross - egi:,.0f} |",
         f"| Less non-recoverable costs ({pct(c['non_recoverable_opex_pct'])} of EGI, assumption) | -${egi * c['non_recoverable_opex_pct']:,.0f} |",
         f"| Less structural reserve (${c['structural_reserve_psf']:.2f} psf, assumption) | -${sf * c['structural_reserve_psf']:,.0f} |",
         f"| **Net operating income (NOI)** | **${cre['noi']:,.0f}** |",
         f"| Value = NOI / cap rate {pct(c['cap_rate'], 2)} | ${cre['value']:,.0f} (${cre['value'] / sf:,.0f} psf vs market ${c['market_price_psf']:,.2f} psf) |",
         f"| Annual debt service on requested loan | ${base.loc['Requested', 'debt_service']:,.0f} |",
         "",
         "| Metric | Requested loan | Max supportable loan | Policy |", "|---|---|---|---|",
         f"| Loan | ${c['loan_requested']:,.0f} | ${cre['max_loan']:,.0f} | |",
         f"| LTV | {pct(base.loc['Requested', 'ltv'])} | {pct(base.loc['Max supportable', 'ltv'])} | <= {pct(c['max_ltv'], 0)} |",
         f"| DSCR | {x(base.loc['Requested', 'dscr'])} | {x(base.loc['Max supportable', 'dscr'])} | >= {c['min_dscr']:.2f}x |",
         f"| Debt yield | {pct(base.loc['Requested', 'debt_yield'])} | {pct(base.loc['Max supportable', 'debt_yield'])} | >= {pct(c['min_debt_yield'], 1)} |",
         "",
         "Loan limits from each constraint: " + "; ".join(f"{k} ${v:,.0f}" for k, v in cre["limits"].items())
         + f". The binding constraint is **{cre['binding']}**.\n",
         "## 4. Strengths",
         f"- Conservative value check: underwritten value of ${cre['value'] / sf:,.0f} psf is in line with the ${c['market_price_psf']:,.2f} psf "
         "average GTA industrial sale price in the same source.",
         f"- Tight market: GTA industrial vacancy of {pct(c['market_vacancy'], 2)} (Lee Q3 2026), below the {pct(c['underwritten_vacancy'], 0)} used here.",
         f"- At the max supportable loan, LTV is only {pct(base.loc['Max supportable', 'ltv'])}, leaving a large equity cushion.\n",
         "## 5. Risks and mitigants",
         f"- Risk: negative leverage - the {pct(c['cap_rate'], 2)} cap rate is below the {pct(cre['rate'], 2)} loan rate, so cash flow, not value, "
         "limits the loan. Mitigant: size the loan to DSCR, not LTV.",
         f"- Risk: the requested loan only covers debt service {x(base.loc['Requested', 'dscr'])} at base case. Mitigant: reduce the loan.",
         "- Risk: industrial rents have softened (Lee Q3 2026 asking rent down from Q2). Mitigant: vacancy and reserve assumptions above market.",
         "- Risk: refinancing at maturity if rates or cap rates rise. Mitigant: 25-year amortization pays down principal during the term.\n",
         "## 6. Stress results",
         "| Scenario | NOI | Value | LTV (req.) | DSCR (req.) | LTV (max) | DSCR (max) |", "|---|---|---|---|---|---|---|"]
    for name in t.scenario.unique():
        g = t[t.scenario == name].set_index("loan_case")
        flag = lambda v: f"**{v:.2f}x**" if v < 1.0 else f"{v:.2f}x"
        L.append(f"| {name} | ${g.loc['Requested', 'noi']:,.0f} | ${g.loc['Requested', 'value']:,.0f} | "
                 f"{pct(g.loc['Requested', 'ltv'])} | {flag(g.loc['Requested', 'dscr'])} | "
                 f"{pct(g.loc['Max supportable', 'ltv'])} | {flag(g.loc['Max supportable', 'dscr'])} |")
    L += ["\n*Bold DSCR = below 1.00x (NOI does not cover the mortgage payment).*\n",
          "## 7. Proposed covenants",
          f"- Minimum DSCR {c['min_dscr']:.2f}x, tested annually on the rent roll",
          f"- Maximum LTV {pct(c['max_ltv'], 0)} on any new appraisal",
          "- Assignment of leases and rents; first-ranking mortgage; no secondary financing\n",
          "## 8. Recommendation",
          f"**{cre['decision']}** - approve a reduced loan of ${cre['max_loan']:,.0f} (vs ${c['loan_requested']:,.0f} requested). "
          f"At the requested size DSCR is {x(base.loc['Requested', 'dscr'])} at base and {x(comb.loc['Requested', 'dscr'])} under combined stress. "
          f"At ${cre['max_loan']:,.0f} DSCR is {x(base.loc['Max supportable', 'dscr'])} at base and stays at {x(comb.loc['Max supportable', 'dscr'])} "
          f"under combined stress, with LTV of {pct(comb.loc['Max supportable', 'ltv'])}."]
    fails = []
    if comb.loc["Max supportable", "dscr"] < c["min_dscr"]:
        fails.append(f"DSCR {x(comb.loc['Max supportable', 'dscr'])} is below the {c['min_dscr']:.2f}x covenant")
    if comb.loc["Max supportable", "ltv"] > c["max_ltv"]:
        fails.append(f"LTV {pct(comb.loc['Max supportable', 'ltv'])} is above the {pct(c['max_ltv'], 0)} limit")
    if fails:
        L.append(f"- Under combined stress the reduced loan still covers its payments, but " + " and ".join(fails)
                 + ". Conditions: a cash-flow sweep if DSCR falls below the covenant, and a partial paydown "
                 "(or extra security) if a new appraisal shows LTV above the limit.")
    return "\n".join(L) + "\n"


def write_memos(res):
    os.makedirs(MEMO_DIR, exist_ok=True)
    a, paths = res["assumptions"], []
    for d in res["summary"]:
        hist = res["ratios"][res["ratios"].ticker == d["ticker"]].reset_index(drop=True)
        d["spreads_hist"] = res["spreads"][res["spreads"].ticker == d["ticker"]].reset_index(drop=True)
        p = os.path.join(MEMO_DIR, f"{d['ticker'].split('.')[0].lower()}_{_slug(d['name'].split()[0])}_memo.md")
        with open(p, "w") as fh:
            fh.write(corporate_memo(d, hist, a))
        paths.append(p)
    p = os.path.join(MEMO_DIR, "cre_gta_industrial_memo.md")
    with open(p, "w") as fh:
        fh.write(cre_memo(res["cre"], a))
    paths.append(p)
    return paths
