# Credit Underwriting Toolkit

A small Python + SQLite + Excel tool that underwrites loans the way a bank credit analyst does: spread the financial statements, calculate credit ratios, assign an internal risk rating, stress test, set covenants, and write a credit memo with a recommendation.

It covers three hypothetical corporate term loans to real TSX-listed companies and one hypothetical commercial real estate (CRE) mortgage on a Greater Toronto Area industrial building.

```
python run_all.py
```

Output: `reports/credit_report.xlsx` and four memos in `memos/`.

## The problem: how a bank decides to lend

A commercial lender mainly asks two questions: **can the borrower repay from cash flow**, and **what happens if things go wrong**. The usual process:

1. **Request**: amount, purpose, term, pricing.
2. **Spread**: put the borrower's statements into one standard template so companies can be compared.
3. **Ratios**: leverage (how much debt for each dollar of EBITDA), coverage (how many times cash earnings cover interest and principal), and liquidity.
4. **Rating**: turn the ratios into an internal risk grade.
5. **Stress and covenants**: test a downturn and higher rates, then set covenants that warn the bank early.
6. **Memo and decision**: approve, approve with conditions, or decline.

For CRE the property itself repays the loan, so the focus is on net operating income (NOI), value, loan-to-value (LTV), debt service coverage (DSCR), and debt yield.

## Companies chosen

All three are **mid-size TSX-listed non-financial companies that report in CAD**. Companies this size usually borrow from bank syndicates (revolvers and term loans) instead of public bond markets, which makes them realistic commercial banking borrowers. Banks and insurers are excluded because their balance sheets work differently.

| Profile | Company | Ticker | FY2025 revenue | Why |
|---|---|---|---|---|
| Strong | Richelieu Hardware | RCH.TO | $1,964M | Little funded debt ($9.9M term debt plus a $22.9M overdraft); most of its debt is leases. Low leverage, high coverage. |
| Middle | Rogers Sugar | RSI.TO | $1,313M | Moderate leverage, a bank revolver plus convertible debentures, and heavy current capex (the LEAP capacity project). |
| Weak | Cineplex | CGX.TO | $1,285M | High leverage including leases, thin coverage, negative shareholders' equity. |

Each was checked before use: still trading (prices through Nov 20, 2026), four years of annual statements in yfinance, and every spread line item present. Other candidates were tested and dropped: Savaria and Pollard Banknote had leverage too close to Richelieu to show a "middle" profile, and Andrew Peller returned no recent price data.

## Data

- **Source**: yfinance annual income statement, balance sheet and cash flow, cached to `data/raw/`. Four fiscal years per company (FY2022-FY2025). Richelieu's year ends Nov 30, Rogers Sugar's in late September, Cineplex's Dec 31.
- **Units**: CAD millions for the companies, CAD for the CRE deal.
- **Total debt includes lease liabilities.** Under IFRS 16, EBITDA already excludes rent, so leaving leases out of debt would make leverage look better than it is. For the same reason, the DSCR includes lease principal repayments from each company's cash flow statement.
- **Reported EBITDA, not "adjusted"**, for consistency across companies. Years where reported EBITDA differs from yfinance's normalized EBITDA by more than 20% are flagged (Rogers Sugar FY2022; Cineplex FY2022 and FY2024). Their ratios are still shown, but the memos don't use them as the starting point for trend statements.
- **Missing items** would be left blank and flagged, and any ratio that needs them would be blank too. In this run nothing in the spread template is missing.

### Spot checks: yfinance vs annual report (latest fiscal year, CAD millions)

If a difference is above 2%, the annual report value replaces the yfinance value automatically. None did.

| Company | Figure | yfinance | Annual report | Diff | Source |
|---|---|---|---|---|---|
| Richelieu | Revenue | 1,964.0 | 1,964.0 | 0.0% | [Annual Report 2025](https://www.richelieu.com/html/An/statique/infoFinanciere/fichier/SEDAR%20RCH_RA2025_COMPLETE%20EN.pdf), PDF p.68 |
| Richelieu | EBITDA | 213.9 | 213.9 | 0.0% | same, PDF p.68 |
| Richelieu | Total debt (overdraft + LTD + leases) | 276.9 | 276.9 | 0.0% | same, PDF p.67 |
| Rogers Sugar | Revenue | 1,312.6 | 1,312.6 | 0.0% | [Q4/FY2025 report](https://lanticrogers.com/media/earning-releases/2025/11/rsi_q4_2025_report_en.pdf), PDF p.1 |
| Rogers Sugar | EBITDA (reported) | 137.8 | 139.9 | -1.5% | same, PDF p.1 |
| Rogers Sugar | Total debt (revolver + debentures + term loans + notes + leases) | 387.7 | 387.7 | 0.0% | [2025 Annual Report](https://lanticrogers.com/media/financial-reports/2026/03/2025_combined_annual_report_web_en.pdf), PDF p.122 |
| Cineplex | Revenue | 1,284.8 | 1,284.8 | 0.0% | [2025 Financial Statements](https://mediafiles.cineplex.com/investor-relations/reports/CineplexFS%20(Q4%202025).pdf), PDF p.10 |
| Cineplex | EBITDA (reported) | 251.8 | 251.0 | +0.3% | [2025 MD&A](https://mediafiles.cineplex.com/investor-relations/reports/CineplexMD_A%20(Q4%202025).pdf), PDF p.69 |
| Cineplex | Total debt (LTD + leases) | 1,793.7 | 1,793.7 | 0.0% | 2025 Financial Statements, PDF p.9 |

The same table, generated from the data, is in the `Spot_Checks` sheet.

### CRE market inputs

| Input | Value | Source |
|---|---|---|
| GTA industrial cap rate | 4.79% | Lee & Associates, [Toronto Industrial Q3 2026](https://www.lee-associates.com/wp-content/uploads/2026/10/2026-Q3-Toronto-ON-Industrial.pdf), p.1 |
| Average net (NNN) asking rent | $18.75 psf | same |
| Vacancy | 3.83% | same |
| Average sale price | $356.28 psf | same (used only to sanity-check value) |
| 5-year Government of Canada yield | 3.53% (Nov 19, 2026) | [Bank of Canada](https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/) |
| CORRA | 2.55% (Nov 19, 2026) | [Bank of Canada](https://www.bankofcanada.ca/rates/interest-rates/corra/) |

Everything else (building size, vacancy allowance, loan spread, lender limits) is labelled "Assumption" in `config/cre_deal.csv`.

## Methods

**Ratios** (SQL views in `sql/ratios.sql`, mirrored in Python for pro forma and stress):

| Ratio | Formula |
|---|---|
| Debt / EBITDA | Total debt incl. leases / EBITDA |
| Net Debt / EBITDA | (Total debt - cash) / EBITDA |
| EBITDA / Interest | EBITDA / interest expense |
| Fixed charge coverage | (EBITDA - capex - taxes) / interest |
| Current ratio | Current assets / current liabilities |
| Debt / Capital | Debt / (debt + equity); negative equity scores worst |
| (OCF - capex) / Debt | Free cash flow / total debt |
| DSCR (loan) | (EBITDA - taxes) / (interest + lease principal + new loan principal) |

**Scorecard** (`config/scorecard.csv`): each ratio falls into one of six bands worth 1, 3, 5, 7, 9 or 10 points. The weighted average becomes a 1-10 rating (1 = strongest). Weights: Debt/EBITDA 25%, EBITDA/Interest 20%, fixed charge coverage 15%, and 10% each for the rest. **I designed the thresholds myself**, loosely based on typical rating-agency leverage and coverage ranges. They are not a bank's actual model.

**Loan requests** (`config/companies.csv`, all hypothetical): floating-rate senior term loans at CORRA plus a spread, sized at 0.24-0.54x EBITDA:

| Borrower | Loan | Rate | Amortization | Proposed covenants |
|---|---|---|---|---|
| Richelieu | $100M acquisition term loan | CORRA + 1.50% = 4.05% | 10 yrs | Debt/EBITDA <= 3.00x; EBITDA/Interest >= 4.00x |
| Rogers Sugar | $75M capex term loan | CORRA + 2.00% = 4.55% | 7 yrs | <= 4.00x; >= 3.00x |
| Cineplex | $60M capex term loan | CORRA + 4.25% = 6.80% (its actual revolver margin) | 5 yrs | <= 7.50x; >= 1.50x |

**Stress tests**: EBITDA -20%; rates +200 bps on the floating share of existing debt plus the whole new loan; and both combined. The floating shares come from each company's debt notes: Richelieu 8% (bank overdraft), Rogers Sugar 38% (revolver before swaps; one $100M swap ends Dec 2026), Cineplex 0% (all existing debt is fixed). Lost EBITDA and extra interest come straight out of cash flow, with no tax shield.

**Decision rule** (`config/assumptions.csv`): decline if the pro forma rating is 8 or worse, or if DSCR falls below 1.00x under combined stress. Approve with conditions if the rating is 5-7, any covenant breaches under stress, or base DSCR is below 1.25x. Otherwise approve.

**CRE**: NOI = rent after vacancy, less non-recoverable costs and a reserve. Value = NOI / cap rate. Debt service assumes monthly payments over a 25-year amortization. The maximum loan is the smallest of the LTV limit (65%), the DSCR limit (1.25x) and the debt yield limit (8%). Stresses: NOI -10%, cap rate +100 bps, and both combined.

## Results

| Deal | Rating (standalone / pro forma / combined stress) | Pro forma Debt/EBITDA | Pro forma EBITDA/Interest | DSCR (base -> combined stress) | Recommendation |
|---|---|---|---|---|---|
| Richelieu, $100M | 2 / 3 / 4 | 1.76x | 11.6x | 2.35x -> 1.74x | **Approve** |
| Rogers Sugar, $75M | 6 / 7 / 8 | 3.36x | 5.5x | 2.71x -> 1.87x | **Approve with conditions** (leverage covenant breaches under a 20% EBITDA drop) |
| Cineplex, $60M | 10 / 10 / 10 | 7.36x | 1.7x | 1.02x -> 0.81x | **Decline** |
| GTA industrial, $35.0M requested | n/a | n/a | n/a | 1.01x -> 0.91x as requested | **Approve with conditions** at $28.2M |

CRE detail: NOI $2.57M; value $53.6M ($358 psf, close to the $356 psf market average); limits are LTV $34.9M, DSCR $28.2M and debt yield $32.1M. **DSCR binds** because the 4.79% cap rate is below the 5.38% mortgage rate (negative leverage). At $28.2M, LTV is 52.6% and DSCR is 1.25x at base, falling to 1.13x DSCR and 70.6% LTV under combined stress. The loan still covers its payments in that case but would trip both covenants.

## Limitations

- **Public data only.** A real lender would get monthly financials, projections, an aged receivables list, and management meetings. Ratios here use the latest fiscal year and are not forward-looking.
- **My own scorecard.** The thresholds and weights are my design, not a bank's or rating agency's model, and the ratings are not comparable to agency ratings.
- **The loans and the CRE property are hypothetical.** The loan amounts, spreads, covenants and the building are made up for practice. Market inputs and company facts are sourced.
- **Simplified DSCR.** Scheduled principal on existing debt isn't available in a consistent form, so DSCR counts interest, lease principal and the new loan's principal only. Growth capex is left out of DSCR but is included in fixed charge coverage.
- **yfinance labels.** EBITDA definitions differ slightly from company-reported figures (for example, Rogers Sugar is 1.5% lower). Only three figures per company were spot-checked, and only for the latest year.
- **Stress tests are simple** one-period shocks with no working-capital or management response.

## How to run

Requires Python 3.10+ on Mac or Linux.

```bash
cd credit-underwriting
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python run_all.py              # uses cached statements in data/raw/ if present
python run_all.py --refresh    # re-downloads from yfinance
python -m unittest discover tests -v
```

## Project structure

```
config/companies.csv     tickers, hypothetical loan requests, covenants, sourced notes
config/scorecard.csv     ratio thresholds and weights for the 1-10 rating
config/assumptions.csv   base rates (sourced), stress sizes, decision rule
config/cre_deal.csv      CRE inputs, each sourced or labelled "Assumption"
config/spot_checks.csv   annual report values with page references
sql/ratios.sql           ratio calculations as SQL views
src/load_data.py         download -> standard spread -> spot checks -> SQLite
src/credit.py            ratios, scorecard, pro forma, stress, covenants, CRE metrics
src/memos.py             credit memos (Markdown)
src/report.py            Excel workbook
tests/test_credit.py     unit tests on hand-built examples
run_all.py               runs everything end to end
```
