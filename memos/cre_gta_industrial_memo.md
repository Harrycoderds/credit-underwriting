# Credit Memo - GTA Industrial Mortgage (HYPOTHETICAL)
*Hypothetical commercial real estate loan for practice. Market inputs are sourced (see config/cre_deal.csv); everything else is labelled as an assumption. Amounts in CAD.*

## 1. Borrower / property overview
Hypothetical single-tenant-capable industrial/logistics building, Greater Toronto Area: 150,000 sq ft of rentable industrial space, underwritten at the Q3 2026 GTA average net asking rent of $18.75 psf and a 4.79% cap rate (Lee & Associates Toronto Industrial Q3 2026, p.1). The borrower is a hypothetical single-purpose entity.

## 2. Loan request
- First mortgage of $35,000,000, 5-year term, 25-year amortization
- Rate: 5-yr GoC (3.53%, Bank of Canada) + 1.85% spread (assumption) = 5.38% fixed

## 3. Key financials (underwriting)
| Line | Amount |
|---|---|
| Potential gross rent (150,000 sf x $18.75) | $2,812,500 |
| Less vacancy (5.0%, assumption; market 3.83%) | -$140,625 |
| Less non-recoverable costs (3.0% of EGI, assumption) | -$80,156 |
| Less structural reserve ($0.15 psf, assumption) | -$22,500 |
| **Net operating income (NOI)** | **$2,569,219** |
| Value = NOI / cap rate 4.79% | $53,637,135 ($358 psf vs market $356.28 psf) |
| Annual debt service on requested loan | $2,549,156 |

| Metric | Requested loan | Max supportable loan | Policy |
|---|---|---|---|
| Loan | $35,000,000 | $28,200,000 | |
| LTV | 65.3% | 52.6% | <= 65% |
| DSCR | 1.01x | 1.25x | >= 1.25x |
| Debt yield | 7.3% | 9.1% | >= 8.0% |

Loan limits from each constraint: LTV $34,864,138; DSCR $28,220,372; Debt yield $32,115,234. The binding constraint is **DSCR**.

## 4. Strengths
- Conservative value check: underwritten value of $358 psf is in line with the $356.28 psf average GTA industrial sale price in the same source.
- Tight market: GTA industrial vacancy of 3.83% (Lee Q3 2026), below the 5% used here.
- At the max supportable loan, LTV is only 52.6%, leaving a large equity cushion.

## 5. Risks and mitigants
- Risk: negative leverage - the 4.79% cap rate is below the 5.38% loan rate, so cash flow, not value, limits the loan. Mitigant: size the loan to DSCR, not LTV.
- Risk: the requested loan only covers debt service 1.01x at base case. Mitigant: reduce the loan.
- Risk: industrial rents have softened (Lee Q3 2026 asking rent down from Q2). Mitigant: vacancy and reserve assumptions above market.
- Risk: refinancing at maturity if rates or cap rates rise. Mitigant: 25-year amortization pays down principal during the term.

## 6. Stress results
| Scenario | NOI | Value | LTV (req.) | DSCR (req.) | LTV (max) | DSCR (max) |
|---|---|---|---|---|---|---|
| Base | $2,569,219 | $53,637,135 | 65.3% | 1.01x | 52.6% | 1.25x |
| NOI -10% | $2,312,297 | $48,273,421 | 72.5% | **0.91x** | 58.4% | 1.13x |
| Cap rate +100 bps | $2,569,219 | $44,373,381 | 78.9% | 1.01x | 63.6% | 1.25x |
| Combined | $2,312,297 | $39,936,043 | 87.6% | **0.91x** | 70.6% | 1.13x |

*Bold DSCR = below 1.00x (NOI does not cover the mortgage payment).*

## 7. Proposed covenants
- Minimum DSCR 1.25x, tested annually on the rent roll
- Maximum LTV 65% on any new appraisal
- Assignment of leases and rents; first-ranking mortgage; no secondary financing

## 8. Recommendation
**Approve with conditions** - approve a reduced loan of $28,200,000 (vs $35,000,000 requested). At the requested size DSCR is 1.01x at base and 0.91x under combined stress. At $28,200,000 DSCR is 1.25x at base and stays at 1.13x under combined stress, with LTV of 70.6%.
- Under combined stress the reduced loan still covers its payments, but DSCR 1.13x is below the 1.25x covenant and LTV 70.6% is above the 65% limit. Conditions: a cash-flow sweep if DSCR falls below the covenant, and a partial paydown (or extra security) if a new appraisal shows LTV above the limit.
