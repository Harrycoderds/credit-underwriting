"""
credit.py - ratios, scorecard rating, pro forma loan, stress tests, covenants,
and the commercial real estate (CRE) loan metrics.

Plain functions only. Amounts are CAD millions for companies, CAD for the CRE deal.
"""
import math

import pandas as pd

from src.load_data import assumptions, read_config

RATIO_NAMES = ["debt_ebitda", "net_debt_ebitda", "ebitda_interest", "fccr",
               "current_ratio", "debt_capital", "fcf_debt"]
POINTS = [1, 3, 5, 7, 9, 10]          # band 1 (best) ... band 6 (worst)
NOT_MEANINGFUL = 99.0                 # same convention as sql/ratios.sql
SCENARIOS = ["Base (pro forma)", "EBITDA -20%", "Rates +200 bps", "Combined"]


def _div(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return a / b


# ------------------------------------------------------------------ ratios
def ratios(s):
    """Python mirror of sql/ratios.sql, used for pro forma and stressed figures."""
    ebitda, debt, eq = s.get("ebitda"), s.get("total_debt"), s.get("equity")
    taxes = max(s.get("taxes") or 0.0, 0.0)
    capex = s.get("capex")
    bad_ebitda = ebitda is not None and not pd.isna(ebitda) and ebitda <= 0
    cap = None if debt is None or eq is None or pd.isna(debt) or pd.isna(eq) else debt + eq
    return {
        "debt_ebitda": NOT_MEANINGFUL if bad_ebitda else _div(debt, ebitda),
        "net_debt_ebitda": NOT_MEANINGFUL if bad_ebitda else _div(
            None if debt is None or s.get("cash") is None else debt - s["cash"], ebitda),
        "ebitda_interest": _div(ebitda, s.get("interest_expense")),
        "fccr": _div(None if ebitda is None or capex is None else ebitda - capex - taxes,
                     s.get("interest_expense")),
        "current_ratio": _div(s.get("current_assets"), s.get("current_liabilities")),
        "debt_capital": NOT_MEANINGFUL if cap is not None and cap <= 0 else _div(debt, cap),
        "fcf_debt": _div(None if s.get("ocf") is None or capex is None else s["ocf"] - capex, debt),
    }


# ------------------------------------------------------------------ scorecard
def score_ratio(value, direction, thresholds):
    """Map a ratio to points (1 = best, 10 = worst) using 5 thresholds -> 6 bands.
    'lower' = lower is better (leverage); 'higher' = higher is better (coverage)."""
    if value is None or pd.isna(value):
        return None
    for i, t in enumerate(thresholds):
        if (direction == "lower" and value <= t) or (direction == "higher" and value >= t):
            return POINTS[i]
    return POINTS[-1]


def rating(ratio_values, scorecard):
    """Weighted average of points -> internal rating 1-10 (1 = strongest).
    Missing ratios are dropped and the remaining weights re-scaled (and reported)."""
    rows, wsum, total = [], 0.0, 0.0
    for _, r in scorecard.iterrows():
        th = [r[f"t{i}"] for i in range(1, 6)]
        v = ratio_values.get(r["ratio"])
        pts = score_ratio(v, r["direction"], th)
        rows.append({"ratio": r["ratio"], "label": r["label"], "ratio_value": v, "points": pts, "weight": r["weight"]})
        if pts is not None:
            wsum += r["weight"]
            total += r["weight"] * pts
    score = total / wsum if wsum else None
    grade = None if score is None else int(min(10, max(1, math.floor(score + 0.5))))
    return grade, score, pd.DataFrame(rows)


# ------------------------------------------------------------------ loan, pro forma, stress
def loan_terms(company, a):
    rate = a["corra"] + float(company["loan_spread"])
    amount = float(company["loan_amount"])
    return {"amount": amount, "rate": rate, "principal": amount / float(company["loan_amort_years"])}


def pro_forma(s, loan):
    """Add the new term loan: more debt, more interest, interest paid out of operating cash flow."""
    p = dict(s)
    new_int = loan["amount"] * loan["rate"]
    p["total_debt"] = s["total_debt"] + loan["amount"]
    p["interest_expense"] = s["interest_expense"] + new_int
    p["ocf"] = None if s.get("ocf") is None else s["ocf"] - new_int
    return p


def stress(p, existing_debt, floating_share, loan_amount, ebitda_shock=0.0, rate_shock=0.0):
    """Apply shocks to a pro forma spread. Lost EBITDA and extra interest come straight out of cash flow
    (no tax shield - conservative). Rate shock hits the floating share of existing debt plus the new loan,
    which is fully floating."""
    s = dict(p)
    d_ebitda = p["ebitda"] * ebitda_shock                      # negative number
    d_int = rate_shock * (existing_debt * floating_share + loan_amount)
    s["ebitda"] = p["ebitda"] + d_ebitda
    s["ebit"] = None if p.get("ebit") is None else p["ebit"] + d_ebitda
    s["interest_expense"] = p["interest_expense"] + d_int
    s["ocf"] = None if p.get("ocf") is None else p["ocf"] + d_ebitda - d_int
    return s


def corporate_dscr(s, new_principal, lease_principal=0.0):
    """(EBITDA - cash taxes) / (all interest + lease principal + scheduled principal on the new loan).
    Lease principal is included because IFRS 16 EBITDA adds back all rent. Capex is excluded because the
    proposed loans fund capex/acquisitions; FCCR shows the after-capex view."""
    taxes = max(s.get("taxes") or 0.0, 0.0)
    return _div(s["ebitda"] - taxes, s["interest_expense"] + lease_principal + new_principal)


def covenant_headroom(debt_ebitda, interest_cover, max_lev, min_cov):
    """How far EBITDA could fall before each covenant breaches (negative = already in breach)."""
    lev = None if debt_ebitda is None else 1 - debt_ebitda / max_lev
    cov = None if interest_cover is None else 1 - min_cov / interest_cover
    return lev, cov


def recommend(pro_forma_rating, base_dscr, combined_dscr, any_breach, a):
    reasons = []
    if pro_forma_rating >= a["decline_rating"]:
        reasons.append(f"pro forma rating {pro_forma_rating} is at or above the decline line ({int(a['decline_rating'])})")
    if combined_dscr is not None and combined_dscr < 1.0:
        reasons.append(f"DSCR falls to {combined_dscr:.2f}x under combined stress (below 1.00x)")
    if reasons:
        return "Decline", reasons
    if pro_forma_rating >= a["conditions_rating"]:
        reasons.append(f"pro forma rating {pro_forma_rating} is in the watch range ({int(a['conditions_rating'])}-{int(a['decline_rating']) - 1})")
    if any_breach:
        reasons.append("at least one proposed covenant breaches under stress")
    if base_dscr is not None and base_dscr < a["min_dscr_corporate"]:
        reasons.append(f"base DSCR {base_dscr:.2f}x is below the {a['min_dscr_corporate']:.2f}x minimum")
    if reasons:
        return "Approve with conditions", reasons
    return "Approve", ["rating, coverage and covenant headroom all pass, including under combined stress"]


# ------------------------------------------------------------------ CRE
def cre_noi(rentable_sf, rent_psf, vacancy, opex_pct, reserve_psf):
    """Net operating income on a net (NNN) lease: rent after vacancy, less non-recoverable costs and reserves."""
    egi = rentable_sf * rent_psf * (1 - vacancy)
    return egi - egi * opex_pct - rentable_sf * reserve_psf


def cre_value(noi, cap_rate):
    return noi / cap_rate


def mortgage_constant(rate, amort_years):
    """Annual debt service per $1 of loan (monthly payments, monthly compounding)."""
    r, n = rate / 12, amort_years * 12
    return 12 * r / (1 - (1 + r) ** -n)


def annual_debt_service(loan, rate, amort_years):
    return loan * mortgage_constant(rate, amort_years)


def ltv(loan, value):
    return loan / value


def dscr(noi, debt_service):
    return noi / debt_service


def debt_yield(noi, loan):
    return noi / loan


def max_loan(noi, value, rate, amort_years, max_ltv, min_dscr, min_debt_yield):
    """Largest loan that satisfies every constraint at once = the smallest of the three limits."""
    limits = {
        "LTV": value * max_ltv,
        "DSCR": noi / min_dscr / mortgage_constant(rate, amort_years),
        "Debt yield": noi / min_debt_yield,
    }
    binding = min(limits, key=limits.get)
    return limits[binding], binding, limits


def cre_params():
    df = read_config("cre_deal.csv")
    out = {}
    for _, r in df.iterrows():
        try:
            out[r["parameter"]] = float(r["value"])
        except ValueError:
            out[r["parameter"]] = r["value"]
    return out


def run_cre(a):
    c = cre_params()
    rate = a["goc_5y"] + c["loan_spread"]
    base_noi = cre_noi(c["rentable_sf"], c["market_rent_psf"], c["underwritten_vacancy"],
                       c["non_recoverable_opex_pct"], c["structural_reserve_psf"])
    base_value = cre_value(base_noi, c["cap_rate"])
    mx, binding, limits = max_loan(base_noi, base_value, rate, c["amort_years"],
                                   c["max_ltv"], c["min_dscr"], c["min_debt_yield"])
    mx = math.floor(mx / 100_000) * 100_000      # round down to the nearest $100k
    scen = {"Base": (0, 0), "NOI -10%": (c["noi_shock"], 0), "Cap rate +100 bps": (0, c["cap_rate_shock"]),
            "Combined": (c["noi_shock"], c["cap_rate_shock"])}
    rows = []
    for name, (dn, dc) in scen.items():
        noi = base_noi * (1 + dn)
        cap = c["cap_rate"] + dc
        val = cre_value(noi, cap)
        for label, loan in (("Requested", c["loan_requested"]), ("Max supportable", mx)):
            ds = annual_debt_service(loan, rate, c["amort_years"])
            rows.append({"scenario": name, "loan_case": label, "noi": noi, "cap_rate": cap, "value": val,
                         "loan": loan, "debt_service": ds, "ltv": ltv(loan, val), "dscr": dscr(noi, ds),
                         "debt_yield": debt_yield(noi, loan)})
    table = pd.DataFrame(rows)
    comb_max = table[(table.scenario == "Combined") & (table.loan_case == "Max supportable")].iloc[0]
    if c["loan_requested"] <= mx and comb_max["dscr"] >= 1.0:
        decision = "Approve"
    elif comb_max["dscr"] >= 1.0:
        decision = "Approve with conditions"
    else:
        decision = "Decline"
    return {"params": c, "rate": rate, "noi": base_noi, "value": base_value, "max_loan": mx,
            "binding": binding, "limits": limits, "table": table, "decision": decision}


# ------------------------------------------------------------------ orchestration
def run_credit(conn):
    a = assumptions()
    sc = read_config("scorecard.csv")
    companies = read_config("companies.csv")
    spreads = pd.read_sql("SELECT * FROM spreads ORDER BY ticker, fiscal_year", conn)
    ratio_tbl = pd.read_sql("SELECT * FROM v_ratio_trends ORDER BY ticker, fiscal_year", conn)

    # standalone rating for every year (trend)
    ratio_tbl["rating"] = [rating(r, sc)[0] for r in ratio_tbl[RATIO_NAMES].to_dict("records")]

    score_rows, stress_rows, cov_rows, summary = [], [], [], []
    for _, co in companies.iterrows():
        t = co["ticker"]
        s = spreads[spreads.ticker == t].iloc[-1].to_dict()          # latest fiscal year
        s = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in s.items()}
        loan = loan_terms(co, a)
        stand_grade, stand_score, stand_detail = rating(ratios(s), sc)
        pf = pro_forma(s, loan)

        scen_inputs = {
            SCENARIOS[0]: (0.0, 0.0),
            SCENARIOS[1]: (a["ebitda_shock"], 0.0),
            SCENARIOS[2]: (0.0, a["rate_shock"]),
            SCENARIOS[3]: (a["ebitda_shock"], a["rate_shock"]),
        }
        res = {}
        for name, (es, rs) in scen_inputs.items():
            st = stress(pf, s["total_debt"], float(co["existing_floating_share"]), loan["amount"], es, rs)
            r = ratios(st)
            g, score, detail = rating(r, sc)
            d = corporate_dscr(st, loan["principal"], float(co["lease_principal"]))
            lev_h, cov_h = covenant_headroom(r["debt_ebitda"], r["ebitda_interest"],
                                             co["cov_max_debt_ebitda"], co["cov_min_interest_cover"])
            res[name] = dict(ratios=r, rating=g, score=score, dscr=d, lev_h=lev_h, cov_h=cov_h, detail=detail, spread=st)
            stress_rows.append({"ticker": t, "scenario": name, "ebitda": st["ebitda"],
                                "interest_expense": st["interest_expense"], "debt_ebitda": r["debt_ebitda"],
                                "ebitda_interest": r["ebitda_interest"], "fccr": r["fccr"], "dscr": d,
                                "rating": g, "score": score})
            cov_rows.append({"ticker": t, "scenario": name,
                             "max_debt_ebitda": co["cov_max_debt_ebitda"], "debt_ebitda": r["debt_ebitda"],
                             "leverage_headroom": lev_h, "leverage_breach": lev_h is not None and lev_h < 0,
                             "min_interest_cover": co["cov_min_interest_cover"], "ebitda_interest": r["ebitda_interest"],
                             "coverage_headroom": cov_h, "coverage_breach": cov_h is not None and cov_h < 0})

        for label, det, score, grade in (("Standalone (latest FY)", stand_detail, stand_score, stand_grade),
                                         ("Pro forma with new loan", res[SCENARIOS[0]]["detail"],
                                          res[SCENARIOS[0]]["score"], res[SCENARIOS[0]]["rating"])):
            d = det.copy()
            d.insert(0, "basis", label)
            d.insert(0, "ticker", t)
            d["weighted_points"] = d["points"] * d["weight"]
            score_rows.append(d)
            score_rows.append(pd.DataFrame([{"ticker": t, "basis": label, "label": "Weighted score -> rating",
                                             "ratio_value": score, "points": grade}]))

        any_breach = any(r["lev_h"] < 0 or r["cov_h"] < 0 for r in res.values())
        pf_rating = res[SCENARIOS[0]]["rating"]
        decision, reasons = recommend(pf_rating, res[SCENARIOS[0]]["dscr"], res[SCENARIOS[3]]["dscr"], any_breach, a)
        summary.append({"ticker": t, "name": co["name"], "profile": co["profile"], "fiscal_year": int(s["fiscal_year"]),
                        "loan_amount": loan["amount"], "loan_rate": loan["rate"],
                        "standalone_rating": stand_grade, "pro_forma_rating": pf_rating,
                        "combined_stress_rating": res[SCENARIOS[3]]["rating"],
                        "debt_ebitda": res[SCENARIOS[0]]["ratios"]["debt_ebitda"],
                        "ebitda_interest": res[SCENARIOS[0]]["ratios"]["ebitda_interest"],
                        "dscr": res[SCENARIOS[0]]["dscr"], "combined_dscr": res[SCENARIOS[3]]["dscr"],
                        "any_covenant_breach": any_breach, "recommendation": decision,
                        "reasons": "; ".join(reasons), "latest": s, "loan": loan, "scen": res, "company": co})

    cre = run_cre(a)
    return {"assumptions": a, "ratios": ratio_tbl, "scorecard": pd.concat(score_rows, ignore_index=True),
            "stress": pd.DataFrame(stress_rows), "covenants": pd.DataFrame(cov_rows),
            "summary": summary, "cre": cre, "spreads": spreads}
