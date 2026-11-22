-- Credit ratios for every company-year in the standard spread.
-- All amounts in CAD millions. NULLIF stops division by zero; a NULL input gives a NULL ratio.
-- Total debt includes lease liabilities (IFRS 16) because EBITDA under IFRS 16 already
-- excludes rent; leaving leases out would flatter leverage.

DROP VIEW IF EXISTS v_ratios;
CREATE VIEW v_ratios AS
SELECT
    s.ticker,
    s.fiscal_year,
    s.period_end,
    s.one_off_year,
    -- 99 = not meaningful (EBITDA <= 0 or capital <= 0); scored in the worst band.
    CASE WHEN s.ebitda <= 0 THEN 99.0 ELSE s.total_debt / s.ebitda END             AS debt_ebitda,
    CASE WHEN s.ebitda <= 0 THEN 99.0 ELSE (s.total_debt - s.cash) / s.ebitda END  AS net_debt_ebitda,
    s.ebitda / NULLIF(s.interest_expense, 0)                              AS ebitda_interest,
    -- Fixed charge coverage: cash left after capex and taxes vs interest.
    -- Negative tax (a recovery) is floored at 0: a non-cash recovery should not add coverage.
    (s.ebitda - s.capex - MAX(COALESCE(s.taxes, 0), 0)) / NULLIF(s.interest_expense, 0) AS fccr,
    s.current_assets / NULLIF(s.current_liabilities, 0)                   AS current_ratio,
    CASE WHEN s.total_debt + s.equity <= 0 THEN 99.0
         ELSE s.total_debt / (s.total_debt + s.equity) END                AS debt_capital,
    (s.ocf - s.capex) / NULLIF(s.total_debt, 0)                           AS fcf_debt
FROM spreads s;

-- Year-over-year change in leverage, for the trend columns.
DROP VIEW IF EXISTS v_ratio_trends;
CREATE VIEW v_ratio_trends AS
SELECT
    r.*,
    r.debt_ebitda - LAG(r.debt_ebitda) OVER (PARTITION BY r.ticker ORDER BY r.fiscal_year)         AS debt_ebitda_change,
    r.ebitda_interest - LAG(r.ebitda_interest) OVER (PARTITION BY r.ticker ORDER BY r.fiscal_year) AS ebitda_interest_change
FROM v_ratios r;
