"""
Unit tests on small hand-built examples. Run with:  python -m unittest discover tests -v
"""
import sqlite3
import unittest

import pandas as pd

from src import credit
from src.load_data import SQL_PATH, read_config

# A hand-checkable borrower (CAD millions)
CO = {"revenue": 1000.0, "ebitda": 100.0, "ebit": 70.0, "interest_expense": 10.0, "taxes": 15.0, "capex": 25.0,
      "ocf": 80.0, "cash": 20.0, "current_assets": 300.0, "current_liabilities": 200.0, "total_debt": 250.0,
      "lease_liabilities": 50.0, "equity": 500.0, "ebitda_normalized": 100.0, "one_off_year": 0}


class TestRatios(unittest.TestCase):
    def test_each_ratio_by_hand(self):
        r = credit.ratios(CO)
        self.assertAlmostEqual(r["debt_ebitda"], 2.5)                    # 250 / 100
        self.assertAlmostEqual(r["net_debt_ebitda"], 2.3)                # (250 - 20) / 100
        self.assertAlmostEqual(r["ebitda_interest"], 10.0)               # 100 / 10
        self.assertAlmostEqual(r["fccr"], 6.0)                           # (100 - 25 - 15) / 10
        self.assertAlmostEqual(r["current_ratio"], 1.5)                  # 300 / 200
        self.assertAlmostEqual(r["debt_capital"], 250 / 750)             # 250 / (250 + 500)
        self.assertAlmostEqual(r["fcf_debt"], 0.22)                      # (80 - 25) / 250

    def test_sql_view_matches_python(self):
        conn = sqlite3.connect(":memory:")
        row = dict(CO, ticker="TEST", fiscal_year=2025, period_end="2025-12-31")
        pd.DataFrame([row]).to_sql("spreads", conn, index=False)
        with open(SQL_PATH) as fh:
            conn.executescript(fh.read())
        sql = pd.read_sql("SELECT * FROM v_ratios", conn).iloc[0]
        for k, v in credit.ratios(CO).items():
            self.assertAlmostEqual(sql[k], v, msg=k)

    def test_negative_ebitda_and_equity_not_meaningful(self):
        r = credit.ratios(dict(CO, ebitda=-10.0, equity=-400.0))
        self.assertEqual(r["debt_ebitda"], credit.NOT_MEANINGFUL)
        self.assertEqual(r["debt_capital"], credit.NOT_MEANINGFUL)

    def test_negative_tax_recovery_ignored(self):
        self.assertAlmostEqual(credit.ratios(dict(CO, taxes=-30.0))["fccr"], 7.5)   # (100 - 25 - 0) / 10

    def test_missing_input_gives_none(self):
        self.assertIsNone(credit.ratios(dict(CO, interest_expense=None))["ebitda_interest"])


class TestScorecard(unittest.TestCase):
    TH = [1.0, 2.0, 3.0, 4.0, 5.5]

    def test_lower_is_better_boundaries(self):
        self.assertEqual(credit.score_ratio(1.0, "lower", self.TH), 1)     # on the threshold -> better band
        self.assertEqual(credit.score_ratio(1.01, "lower", self.TH), 3)
        self.assertEqual(credit.score_ratio(5.5, "lower", self.TH), 9)
        self.assertEqual(credit.score_ratio(5.51, "lower", self.TH), 10)

    def test_higher_is_better_boundaries(self):
        th = [12, 8, 5, 3, 1.5]
        self.assertEqual(credit.score_ratio(12, "higher", th), 1)
        self.assertEqual(credit.score_ratio(11.99, "higher", th), 3)
        self.assertEqual(credit.score_ratio(1.5, "higher", th), 9)
        self.assertEqual(credit.score_ratio(1.49, "higher", th), 10)

    def test_rating_range_and_order(self):
        sc = read_config("scorecard.csv")
        self.assertAlmostEqual(sc["weight"].sum(), 1.0)
        strong, _, _ = credit.rating(credit.ratios(CO), sc)
        weak, _, _ = credit.rating(credit.ratios(dict(CO, ebitda=30.0, cash=0.0, ocf=20.0, current_assets=150.0,
                                                      equity=50.0)), sc)
        self.assertTrue(1 <= strong < weak <= 10)

    def test_missing_ratio_reweights(self):
        sc = read_config("scorecard.csv")
        g, score, detail = credit.rating(credit.ratios(dict(CO, current_assets=None)), sc)
        self.assertIsNotNone(g)
        self.assertTrue(detail.loc[detail.ratio == "current_ratio", "points"].isna().all())


class TestStress(unittest.TestCase):
    LOAN = {"amount": 50.0, "rate": 0.05, "principal": 10.0}

    def test_pro_forma_adds_debt_and_interest(self):
        p = credit.pro_forma(CO, self.LOAN)
        self.assertAlmostEqual(p["total_debt"], 300.0)
        self.assertAlmostEqual(p["interest_expense"], 12.5)

    def test_stress_never_improves_coverage(self):
        p = credit.pro_forma(CO, self.LOAN)
        base = credit.ratios(p)
        base_dscr = credit.corporate_dscr(p, 10.0, 5.0)
        for es, rs in ((-0.2, 0), (0, 0.02), (-0.2, 0.02)):
            s = credit.stress(p, CO["total_debt"], 0.5, self.LOAN["amount"], es, rs)
            r = credit.ratios(s)
            self.assertLessEqual(r["ebitda_interest"], base["ebitda_interest"])
            self.assertLessEqual(r["fccr"], base["fccr"])
            self.assertGreaterEqual(r["debt_ebitda"], base["debt_ebitda"])
            self.assertLessEqual(credit.corporate_dscr(s, 10.0, 5.0), base_dscr)

    def test_rate_shock_hits_only_floating_debt(self):
        p = credit.pro_forma(CO, self.LOAN)
        s = credit.stress(p, 250.0, 0.4, 50.0, 0, 0.02)
        self.assertAlmostEqual(s["interest_expense"] - p["interest_expense"], 0.02 * (250 * 0.4 + 50))

    def test_dscr_by_hand(self):
        # (100 - 15) / (10 + 5 + 10) = 3.4
        self.assertAlmostEqual(credit.corporate_dscr(CO, 10.0, 5.0), 3.4)

    def test_covenant_headroom(self):
        lev, cov = credit.covenant_headroom(2.5, 10.0, 3.0, 4.0)
        self.assertAlmostEqual(lev, 1 - 2.5 / 3.0)
        self.assertAlmostEqual(cov, 0.6)
        lev, _ = credit.covenant_headroom(3.5, 10.0, 3.0, 4.0)
        self.assertLess(lev, 0)


class TestCRE(unittest.TestCase):
    def test_noi_value_ltv_dscr_debt_yield_by_hand(self):
        # 10,000 sf x $20 = 200,000; 5% vacancy -> 190,000; 3% costs -> 184,300; reserve $0.30 psf -> 181,300
        noi = credit.cre_noi(10_000, 20.0, 0.05, 0.03, 0.30)
        self.assertAlmostEqual(noi, 181_300)
        self.assertAlmostEqual(credit.cre_value(100_000, 0.05), 2_000_000)
        self.assertAlmostEqual(credit.ltv(1_300_000, 2_000_000), 0.65)
        self.assertAlmostEqual(credit.dscr(100_000, 80_000), 1.25)
        self.assertAlmostEqual(credit.debt_yield(100_000, 1_250_000), 0.08)

    def test_mortgage_payment_by_hand(self):
        # $1,000,000 at 6% over 25 years, monthly payments: 12 x 6,443.01 = 77,316
        ds = credit.annual_debt_service(1_000_000, 0.06, 25)
        r, n = 0.005, 300
        self.assertAlmostEqual(ds, 12 * 1_000_000 * r / (1 - (1 + r) ** -n))
        self.assertAlmostEqual(ds, 77_316, delta=5)

    def test_max_loan_respects_all_constraints(self):
        noi, value, rate, amort = 1_000_000, 20_000_000, 0.055, 25
        for max_ltv, min_dscr, min_dy in ((0.65, 1.25, 0.08), (0.50, 1.10, 0.05), (0.75, 1.50, 0.07)):
            loan, binding, limits = credit.max_loan(noi, value, rate, amort, max_ltv, min_dscr, min_dy)
            ds = credit.annual_debt_service(loan, rate, amort)
            self.assertLessEqual(credit.ltv(loan, value), max_ltv + 1e-9)
            self.assertGreaterEqual(credit.dscr(noi, ds), min_dscr - 1e-9)
            self.assertGreaterEqual(credit.debt_yield(noi, loan), min_dy - 1e-9)
            self.assertAlmostEqual(loan, min(limits.values()))   # the binding limit, no larger

    def test_ltv_binds_when_cap_rate_high(self):
        # high cap rate -> low value -> LTV binds before DSCR
        loan, binding, _ = credit.max_loan(1_000_000, 1_000_000 / 0.09, 0.05, 25, 0.65, 1.25, 0.08)
        self.assertEqual(binding, "LTV")


if __name__ == "__main__":
    unittest.main()
