# N012 regular F&O checkpoint

## Where the 2022 loss came from

N11 and N11T each closed the same 28 trades, with eight winners. Gross P&L was −₹2,704, then modeled costs of ₹1,943.29 and a separate ₹5,955 execution allowance took net to −₹10,602.29. The historical panel supplied 145 futures sessions. Regular-trading coverage and option availability are partial. The registered 200-session comparison did not pass, and neither N11T condition produced a size change.

Fourteen underlying-stop exits lost ₹23,281.72. Eight never reached +0.5 initial R on observed minute closes. Four high-ADX EFF trades all failed to reach +0.5R and lost ₹4,785.12. Twenty low-ADX TPB puts, the biggest cohort, lost ₹7,901.53 despite entering on the favorable side of VWAP and the session open. Five July losses in the low-ADX put sleeve cost ₹8,434.98. NSE recorded Nifty rising 8.7% in July, with a material shift in foreign flows. The July result explains why a daily market label can coexist with poor short continuation. [NSE August 2022 Market Pulse](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Market_Pulse_August_2022.pdf).

The one-lot no-brake diagnostic admitted 12 additional trades that netted +₹10,689.63. The subset of 11 screened out by stand-aside netted +₹11,691.15. This is a fixed-admission attribution. Removing stand-aside changes the cash and risk path. Prior research found the same brake materially helpful in 2023, and the frozen recovery override in this study recovered none of the 2022 opportunities. August and September had different market conditions, with dated rate announcements and reversals. Headlines and reports published after an entry were used to interpret events. [NSE September 2022 Market Pulse](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Market_Pulse_Sep_2022_0.pdf), [Federal Reserve September 21 decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20220921a.htm).

The first anatomy run used a timestamp separator inconsistent with the candle index. It produced no valid path matches and is preserved under local evidence. The corrected run joined minute prices and reconciled all 28 trades. A separate data sensitivity found the archived Nifty daily closes differed by more than ten points on 104 of 248 dates against the public daily series. A 244.65-point difference on April 29 was the largest. Replacing those 2022 daily inputs while retaining the original minute execution tape reproduced the controls' counts and P&L exactly. That discrepancy does not account for the 2022 losses under the tested daily-gate inputs. [Daily sensitivity results](daily-sensitivity-results.json), [NSE-hosted issuer annual report](https://nsearchives.nseindia.com/corporate/KAMDHENU_31072023192659_RevisedARIntimation.pdf).

## Full account results

These are five independent ₹250,000 NIFTY single-leg development runs, with original lot normalization, fresh annual wallets and modeled adverse quotes plus fees and stress. Every trade in both controls matched the frozen prior receipts. Drawdown uses closed P&L. The 2022 and 2026 windows are partial. No result qualifies SENSEX, the defined-risk lifecycle or a combined account.

| Window | N11 net | N11T net | N11T trades | N11T worst day | N11T closed drawdown |
|---|---:|---:|---:|---:|---:|
| 2022 partial | −₹10,602 | −₹10,602 | 28 | −₹4,410 | 7.09% |
| 2023 | −₹11,537 | −₹11,537 | 28 | −₹3,526 | 6.89% |
| 2024 | +₹93,256 | +₹95,040 | 29 | −₹3,148 | 2.13% |
| 2025 | +₹53,095 | +₹63,479 | 73 | −₹5,641 | 5.29% |
| 2026 available window | +₹120,551 | +₹127,763 | 51 | −₹4,495 | 2.91% |
| Sum of independent runs | +₹244,763 | +₹264,142 | 209 | −₹5,641 | 7.09% max |

Through round six no challenger meets the frozen goal of at least 20% above N11T with comparable downside, acceptable annual performance and gains beyond the five largest incremental days. No challenger reached the point of doubled-stress qualification. Freeze and finish round seven independently before changing the hypotheses again.

| Round | Study | Development result vs N11T |
|---|---|---|
| 1 | Better entry price / protecting earned progress | Better price reduced the 2022 worst day to ₹2,005, then sacrificed ₹135,417 across the five windows. Protection improved 2022 by ₹1,311 and cost ₹8,637 overall. |
| 2 | Recovery override / prevent overlapping bets | Recovery added ₹1,445 overall and lost ₹3,494 when the five best incremental days were removed. The overlap rule helped four windows, hurt 2025 by ₹8,950 and lost ₹351 overall. The 2025 cost included three legitimate winning second entries. |
| 3 | Alternate nearby strike | One liquidity or sizing fallback changed the book and added ₹338 in 2026. The strike-dominance test activated zero times. |
| 4 | Opening gap failure / midday compression | Opening rejection opened one new trade. Both arms lost aggregate net. Midday compression reduced net in each of its four years with activations. |
| 5 | Early structural failure / trend runner | The first saved about ₹1,051 in 2023 and ₹2,501 in 2025, then cost ₹11,420 in 2026. A single premature exit on April 6 gave up about ₹10,536. Giving winners more room lost ₹7,642 overall. |
| 6 | More premium capacity / only above an older locked position | Raising the cap to 20% cost ₹9,923 overall. Several extra earned lots turned profitable parents into small net wins or losses. The funded cap exception left all five windows identical. |
| 7 | Low-ADX opening acceptance | Frozen after round six. Test selective calls and filtering conflicting puts independently. |

Research rationale included market intraday momentum, return dynamics and stopping rules, and volatility scaling. Each paper motivates a test. Its findings concern a different market, instrument or horizon. [Gao et al.](https://www.sciencedirect.com/science/article/pii/S0304405X18301351), [Baltussen et al.](https://academicweb.nd.edu/~zda/intramom.pdf), [Kaminski and Lo](https://dspace.mit.edu/entities/publication/bb69ca4b-0cdc-487f-831d-63b2e84fafee), [Moreira and Muir](https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.12513).

## Two wallets

**₹250,000 paper.** N11T had open premium during 2.71–7.54% of the regular session clock in the five panels. Its active-day median peak ranged from ₹8,861 to ₹22,181. 2026 peak open premium was ₹43,869. The 15% paper cap is a percentage of current equity, so it can exceed ₹37,500 after gains. With the 20% cap 2026 peak grew to ₹56,427, while time exposed and active days were unchanged. Most additional idle times had no native signal. Usage is the NIFTY singles' premium commitment and omits other books and unobserved opportunities on incomplete dates. Capital efficiency improves through repeatable incremental opportunities or better return at comparable exposure. [Capital audit](capital-results.json), [capacity test](ROUND6.md).

**₹15,000 trial.** Same-clock one-lot conditional mirror of N11T admissions, with independent cash, one position, full premium and fee reserve, recomputed fees and the previous configured ₹7,000 floor. This is a diagnostic with today's normalized 65-unit lots, not an account history. Adverse uses the frozen entry and exit friction plus ₹205 per trade. In 2025, six stressed tickets exhausted admission to −₹8,771 and a 58.47% drawdown. Adding a full-premium budget of ₹9,750 turned that year to +₹3,637 while the 2023 adverse drawdown reached 66.11%. The ₹1,500 estimated-stop screen left only 2–6 trades per year and lost in four of five adverse years. Neither screen qualifies. [Trial mechanics](TRIAL.md), [results](trial-results.json), [NSE lot circular](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf).

| Window | ₹15k modeled quotes | ₹15k adverse | Adverse with cash buffer |
|---|---:|---:|---:|
| 2022 partial | −₹7,708 | −₹7,524 | −₹6,802 |
| 2023 | −₹234 | −₹9,137 | −₹8,878 |
| 2024 | +₹34,774 | +₹25,555 | +₹13,066 |
| 2025 | +₹14,533 | −₹8,771 | +₹3,637 |
| 2026 available window | +₹49,321 | +₹36,474 | +₹15,748 |

**November 5.** Production NIFTY singles +₹4,821.18, three exact held-path exits. The separate defined-risk paper close added ₹2,545.91 to the recorded regular total of ₹7,367.09. NIFTY one-lot mirror +₹4,151.68 at recorded prices and +₹3,299.48 under adverse assumptions. It took the first and third entries and skipped the overlapping second. Both starting wallets gave the same result. The report covers conditional admissions and exits, no counterfactual market queue or fully independent new policy. For ordinary SENSEX, two unique signal bars reached the dated same-day exclusion. No SENSEX or expiry performance has been imputed. [November 5 model output](nov5-capital-results.json).

## Resume

Run each immutable round from Dev with `N12_YEAR` set for the selected window and `python-engine/winvenv/Scripts/python.exe`. Existing result files are protected from overwrites. The results for rounds 1–6 have full controls. Finish the remaining round-seven jobs using cached evals if present. Run verification before the result commit.

The November 5 helper passed `report` and `verify` at `97477f8` in `_local/nov5-wallet-receipt-v2`. The first attempt preserved its partial result because helper init pre-created NOT_RUN module placeholders. The fixed writer replaces only those placeholders. Verifying an older receipt against a later Git head reports the expected SHA change. Prior policy source, receipts and raw inputs were separately checked unchanged.

Change perspective again if round seven does not transfer. Probe the already sealed SENSEX and NIFTY intersection and same-side overlap for a genuinely distinct opportunity with shared-account attribution. A historical 2022 SENSEX test remains unavailable. For the small wallet, the next useful test is an affordable near-ATM alternative with a complete, independently managed quote lifecycle. Use actual captured quotes for strike, freshness, depth and exit feasibility before using a 65-unit full-cash calculation as evidence for an order. Keep future dates untouched until any eventual candidate is frozen. Re-test baseline parity, carry losses and stress before considering forward qualification. This checkpoint is local Dev research with no settings, schema, rollout or broker changes.
