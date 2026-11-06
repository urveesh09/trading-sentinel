# Deployed two-index control

Use the November 3 paper reset at ₹250,000. Reconcile NIFTY and SENSEX in chronological order, using the native exchange fee schedules and each position's actual initial lots and underlying. Include recorded defined-risk settlements in the account equity at their real clocks. Keep them separate from single-leg strategy attribution. Compare the five recorded admissions with their independently stored accepted signal events and recomputed decision-time pool. Replay management from the held path at its exact clocks. In particular, recompute the native N11 EFF soft time stop on every observation and verify the recorded parameter hash. Require matching contract, lots, exit clock, exit price, reason and net within ₹1.

This step can reconcile entries as recorded evidence and independently replay the exits. A signal-from-market admission replay also needs the original evaluation phase, current option packets, dated contract master and pre-tick cash state. Keep those fidelity levels distinct. A future historical run will require two-venue management by position owner, NIFTY-first priority on matching clocks, instrument-specific deduplication and stop re-entry levels, exchange fees, and one actual risk and cash ledger. The expanded ordinary SENSEX inventory supplies partial data only. The historical control must report the dates with missing SENSEX evidence. No SENSEX sleeve or new candidate is tested here.

Read immutable export hashes and only November 3–5 records. Report unavailable clocks and identity discrepancies rather than inferring them. No runtime, settings, migration, orders, expiry or rollout changes. Rollback is to retire this audit.

## November 3–5 observed reconciliation

| Position | Venue | Strike | Contracts | Exit | Net |
|---|---|---:|---:|---|---:|
| 55 | SENSEX | 76,600 CE | 2 × 20 | Time stop | −₹481.29 |
| 56 | SENSEX | 77,000 CE | 2 × 20 | Time stop | −₹84.97 |
| 57 | NIFTY | 24,400 CE | 2 × 65 | Time stop | −₹765.59 |
| 58 | NIFTY | 24,350 CE | 1 × 65 | Profit lock | ₹1,028.70 |
| 59 | NIFTY | 24,400 CE | 1 × 65 | Trail stop | ₹4,558.07 |

Across 2,263 held observations, all five recorded exits matched on clock, reason and price with independently recomputed costs. The recomputed single-leg sum was ₹4,254.93, of which ₹4,821.18 came from November 5. Defined-risk positions settled separately for ₹690.28 and ₹2,545.91. The first settlement entered the cash pool before the November 4 admission. The second settled after the last November 5 admission. The November 5 export is unsealed. The November 3 and 4 sessions may predate the current Production revision.

The [machine-readable audit](deployed-control-nov5.json) retains the exact clocks, symbol identities and equity at entry. `python deployed_control_nov5.py <local-export>` validated the file hashes and completed with five matches. Entry economics come from the recorded accepted signals and position ledger. The conditional entry-signal replay below is separate from the complete entry planner and historical two-venue one-wallet comparison. The SENSEX time stops in the earlier fixed-clock replay disagreed because the live EFF stop was recomputed as each position stalled.

## Historical data feasibility

| Year | NIFTY archive sessions | Dated SENSEX overlap | Overlap with recorded positive intraday option OI |
|---|---:|---:|---:|
| 2025 | 248 | 80 | 1 |
| 2026 through October 28 | 203 | 131 | 0 |
| **Total** | **451** | **211** | **1** |

The two dated SENSEX snapshots have disjoint calendars. Round 9 has 896,633 option rows, with 12,884 positive OI rows all on September 23, 2025. Of those, 12,845 meet the configured 5,000-unit floor. Round 36 has 1,945,903 option rows and no positive OI. The [earlier calendar run](ROUND10.md) already showed that missing OI can force simulated entry refusals despite traded option volume. Treat those dates as unavailable for the native entry replay. Prior-session closing OI is a separate proxy and changes what the benchmark tests. One date with nonzero values also falls short of entry parity because it still needs verified observations at decision clocks and the rest of the chain inputs.

Counts come from intersecting each frozen NIFTY manifest's `sessions` with the union of the two SENSEX session lists, and querying both snapshot databases read-only. For each snapshot use `SELECT count(*), sum(oi>0), count(DISTINCT CASE WHEN oi>0 THEN substr(datetime,1,10) END) FROM candles WHERE kind='option'`. The Round 9 manifest SHA-256 is `935bfdb971d443479417020fa6d46f72b9e3b3f94f3db834b973c37c19d6ba8a`. See [Round 36](ROUND36_DATA.md) for that manifest hash. No replay or P&L was computed from these gaps.

Historical trade or order book data would need a sample with dated SENSEX series, bid and ask, last-trade time, volume and intraday OI to qualify as a source. BSE advertises historical and derivative data. Its public daily market summary describes session-level OI, and the published materials inspected here do not establish that the available historical package includes the needed intraday field. [BSE data catalogue](https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf), [BSE derivative file formats](https://www.bseindia.com/downloads1/File_Format_Equity_Derivatives.pdf).

## Entry evidence slice

Use only the existing frozen export and IDs 55–59. Compare the Dev pure signal sources with Production `398d44ad`, and keep prior-session deployment uncertainty visible. Re-evaluate the native ordered N11 route from 21 calendar days of archived front-future bars. For SENSEX use archived NIFTY participation. Condition the replay on the recorded regime and HIGH trend branch. Rebuild intraday retest memory on observable closed bars, then evaluate at the recorded scan clock. Match direction, strategy, bar, range, ATR, participation, stop and target.

Independently locate the last archived option and futures packets before each entry. Check them against recorded prices and explain the effect of any disagreement on full admission parity. Keep payoff arithmetic on the recorded selected contract separate from strike selection and sizing. Hash inputs and retain the five exact rows. No runtime, configuration, trading or rollout change. Rollback is to retire the evidence script and retain the result.

### November 3–5 entry evidence

The native ordered N11 route reproduced **5 of 5** recorded direction, strategy and signal bars, with identical range, ATR, relative volume, stop and target to eight decimal places. Each case was conditioned on the recorded regime and the HIGH ADX branch implied by the recorded strategy. The earlier intraday state was rebuilt one second after each archived five-minute bar closed. The final evaluation used the scan-ID clock. This reproduces signal geometry while leaving the original ADX reading and intervening runtime state unverified.

| ID | Replayed route | Recorded ask | Previous recorder ask | Recorder seconds before entry | Reward / risk on logged terms |
|---|---|---:|---:|---:|---:|
| 55 | SENSEX EFF | ₹335.40 | ₹339.80 | 36.894 | 2.38316 |
| 56 | SENSEX EFF | ₹345.55 | ₹323.95 | 41.679 | 2.31556 |
| 57 | NIFTY OR20 | ₹141.75 | ₹138.70 | 57.935 | 1.77600 |
| 58 | NIFTY OR20 | ₹154.00 | ₹157.10 | 40.449 | 3.08189 |
| 59 | NIFTY TPB | ₹152.95 | ₹142.25 | 42.002 | 2.04149 |

The independently scheduled quote recorder supplied each listed packet. All five option asks and all five futures marks differ from the recorded decision snapshot. Strike selection, age checks, lot sizing and reservation timing still require the actual decision chain and complete decision-time risk state. The logged selected ask times initial quantity matched structural maximum loss for each position. SENSEX's two two-lot entries were ordinary N11 sizing. The deployed N11T tolerance applies only to NIFTY paper entries. [Production entry orchestration](../../../../python-engine/fno_orchestrator.py), [recorder schedule](../../../../python-engine/scheduler_setup.py).

`python deployed_entry_audit.py <local-export>` validated the export database and three quote segment hashes, checked the pure source against Production `398d44ad`, and reproduced the [saved five-row audit](deployed-entry-audit.json) on a second run. Production and Dev differ in the excluded opening-drive storage functions and two unrelated config declarations. Earlier runtime revisions are still uncertain. The first audit run exposed text tokens in the quote archive and integer tokens in the ledger. The completed audit normalizes the representation and independently checks symbol, expiry and lot size. The unchanged exit auditor reproduced five exits and ₹4,254.93. The four focused engine suites passed 89 tests and emitted an asynchronous shadow cleanup warning after completion. The full historical two-venue benchmark remains unavailable with the current SENSEX open-interest coverage.

## Production risk and secondary OI evidence slice

Read the existing Production database in a single read-only transaction, scoped to the five known decisions and their strictly earlier N11 reference closes. Capture the three daily ADX and volatility rows and only matching paper reserve and dispatch records. Recompute selected-contract affordability, shared single-leg premium usage, native lot ceilings, NIFTY-only tolerance and exchange-specific cash reserves using the deployed rules. Require all five lot counts and full reservation amounts to agree. Check settings only through an explicit numeric and Boolean allowlist. The selected contract remains an observed input because the original competing chain is absent.

Separately inspect immutable operational SENSEX analytics exports through October 28. Verify file hashes and count dates with positive intraday OI. This secondary source establishes sampled OI availability only. Do not use it as the decision chain or infer fills from its LTP. No runtime, configuration, trading or rollout change. Rollback is to retire the research audit and retain the scoped evidence.

### Observed gate and cash reconciliation

Production's stored prior-day ADX confirmed HIGH on all three days, with values 31.13, 30.69 and 30.66 against the threshold of 30. The volatility ratios were 1.23, 1.22 and 1.18, so the volatility gate allowed two lots. The strictly prior 20-trade reference total was ₹19,159.13 for IDs 55–58 and ₹19,665.05 for ID 59. Those samples contained 17 and 16 research seed trades respectively. The paper reference's positive reading therefore still leaned heavily on earlier research.

| ID | Native ceiling | Native and recorded lots | Held single-leg premium | Reserved cash | N11T second-lot explanation |
|---|---:|---:|---:|---:|---|
| 55 | 2 | 2 | ₹0.00 | ₹13,468.76 | SENSEX native sizing |
| 56 | 2 | 2 | ₹0.00 | ₹13,874.93 | SENSEX native sizing |
| 57 | 2 | 2 | ₹0.00 | ₹18,483.00 | Native plan already had two lots |
| 58 | 2 | 1 | ₹18,427.50 | ₹10,061.71 | Open-premium cap refused the second lot |
| 59 | 1 | 1 | ₹10,010.00 | ₹9,993.43 | Prior ₹765.59 loss cut the lot ceiling |

For ID 58, two lots would have raised total open premium to ₹38,447.50 against a ₹37,518.60 limit. For ID 59, the earlier loss independently set the one-lot ceiling. The deployed tolerance was enabled and produced zero raised entries in these five decisions. All recorded cash reservations and dispatch states matched. The reserved amounts equal full premium plus the exchange-specific zero-premium exit fee. This replays sizing conditional on the chosen contract. The competing option ladder and original quote freshness remain unavailable for an independent strike and entry replay.

The [scoped Production inputs](deployed-risk-inputs.json) were captured using `docker exec -i --user quantuser python-engine python -B -` with [the capture script](deployed_risk_capture.py) as stdin. The capture used a single SQLite read-only transaction and an allowlist of risk settings. It reproduced exactly on a second read. `python deployed_risk_audit.py <local-export>` reproduced the [five sizing results](deployed-risk-audit.json). The focused N11, entry-plan and adaptive-risk suites passed 53 tests. The atlas regenerated without changes. No Production files, runtime settings or orders were changed.

### Secondary SENSEX OI coverage

The 31 verified operational archives contain 2,605 SENSEX analytics snapshots across 37 dates from September 2 through October 28, 2026. Of 161,510 distinct rows, 161,329 have positive OI. Every date has positive OI. All 37 overlap the 2026 NIFTY archive, 22 overlap the dated SENSEX minute snapshots and 31 overlap the separate quote-recorder calendar. These are date-level joins. A candidate tape still needs verification of contract, clock, depth and quote freshness on each decision. The analytics archive retains time, LTP, OI and volume, and lacks bid, ask and quantities. It contributes no additional 2025 dates.

BSE's direct feed documents timestamped intraday derivative OI broadcasts. Its historical-data catalogue does not establish that the historical product includes those broadcasts alongside replayable quotes. A qualifying sample would need both the intraday OI messages and the quote/depth data, plus contract identity. [BSE intraday feed specification](https://www.bseindia.com/downloads1/BSE_DIRECT_NFCAST_Manual.pdf), [BSE data catalogue](https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf).

## Synchronized market evidence slice

On the frozen recorder dates through October 28, qualify market inputs for the unchanged two-index control. Bind the exact dated Kite masters for NIFTY and SENSEX. Derive each venue's nearest listed option expiry and front future independently. Separate dates when both are eligible from dates when one venue's own expiry blocks regular entry. Reuse the archived provider-packet verifier and native target-delta strike selector.

For each five-minute entry clock from 09:45 through 14:40, check a same-venue futures and option batch received before the next minute. Require raw provider packets, a provider timestamp no more than ten seconds before receipt, the native OI, volume, spread and last-trade-age gates, and displayed depth for two lots on the selected call and put. A two-venue clock also requires a receipt skew within ten seconds. Report each venue's clock gaps, quote availability at hard flat and contract coverage separately. These rules measure data readiness only. They do not infer actual decisions, fills, P&L or a full management path. Freeze the observed source hashes and preserve unusable clocks. Verify with synthetic clock and depth examples. No configuration, migration or rollout change. Rollback is to retire the research audit and retain its counts.

### Observed clock coverage

Verified the raw and normalized hashes of 62 archived dated masters and the 62 finalized recorder files covering 31 sessions from September 10 through October 28. Both venues were eligible on 17 dates. The other 14 had exactly one venue eligible because of its counterpart's own expiry. The prior daily export had rotated. The November 6 Panel D copy supplied the same six previously bound pre-cutoff files that overlap the Round 10 audit. The new report binds only the pre-cutoff files so later daily exports can reproduce it if they retain those segments.

| Coverage check | Usable | Possible |
|---|---:|---:|
| Both venues, observed subsets and synchronized clocks | 284 | 1,020 |
| Both venues, full verified ladders and synchronized clocks | 241 | 1,020 |
| NIFTY, full verified ladder with usable calls and puts | 694 | 1,440 |
| SENSEX, full verified ladder with usable calls and puts | 543 | 1,440 |
| NIFTY selected contract-dates with a two-lot bid in the hard-flat minute | 179 | 219 |
| SENSEX selected contract-dates with a two-lot bid in the hard-flat minute | 179 | 270 |

The 241 full-ladder pairs are 23.6% of the eligible two-venue checkpoints. Fifteen of the 17 dates have at least one pair. The best day had 26 of 60 and no date was complete. Allowing a wider receipt skew would only recover four sampled pairs and no full-ladder pairs. The most common rejection was insufficient displayed depth on the native selector's chosen strike. The optional subset count allows a selected strike from a partial ladder. It does not imply that the same strike would be selected with all quotes present. The hard-flat counts identify possible marks for the same selected tokens and do not establish the intervening held path.

This preflight verified intraday OI directly from the raw recorder packets when available. It did not transplant the earlier analytics snapshot or manufacture bid and ask from minute closes. The next data check is whether missing clocks coincide with fired native signals and whether their exact selected contracts remain observable until close. A full 2025–2026 shared-wallet result still needs broader usable quote evidence and chronological management.

To reproduce, send [the master reader](capture_control_masters.py) to `docker exec -i --user quantuser python-engine python -B -`, gzip its stdout with `mtime=0` into `_local/deployed-control-masters.json.gz` in Dev, and run `python control_quote_coverage.py <local-export>`. A second full run reproduced the [saved report](control-quote-coverage.json), which lists source hashes and every covered clock. The first run stopped on a zero-sized depth field normalized to null. The corrected reader represents both as zero and refuses insufficient depth. The focused research suite passed 26 checks, including the clock skew, last-trade age and zero-depth cases. No new strategy score was calculated.

## Native signal and held-contract coverage slice

Keep the same 31 finalized dates and dated masters. Reconstruct the ordered native N11 signals on a fixed clock one second after each five-minute bar closes. Use the archived front-future bars, NIFTY participation for SENSEX and the prior-day NIFTY ADX rule at its native threshold. Use the latest same-day logged market regime already available at each clock. Report absent regime, missing five-minute bars and truncated prior front-contract history separately. The historical signal study uses neither wallet acceptance nor observed trade outcomes.

At a fired signal, take the first archived same-venue batch before the next minute. Require the exact verified ladder for the native selected strike and apply the evidence gates in the signal's direction. Report one- and two-lot depth separately. For a selected contract with eligible depth, track the same option token and dated front future through the 15:10 hard-flat minute. Count usable bids and maximum receipt gaps, including an explicit 90-second diagnostic and the native ten-second comparison. A missing path is unavailable. Preserve all fired clocks, refusals and source identities. No entry or exit prices are used for a P&L result. No rollout or runtime change. Rollback is to retire this audit and retain its evidence.

### Results at fired signal clocks

The ordered N11 evaluator produced 39 signal checkpoints on 15 archived dates. These are representative market-signal evaluations on the declared clock. The historical strategy had a different scan phase and the audit does not apply wallet acceptance or trade deduplication. Of the 39, 31 had a complete archived front-future lookback and retest context under the audit's rules. Seven eligible venue-dates had truncated futures inputs. Forty-eight early venue checkpoints lacked any causal same-day regime observation, and four fired checkpoints had incomplete earlier retest context. The [saved audit](control-signal-coverage.json) retains the affected dates and flags.

| Evidence | NIFTY | SENSEX | Total |
|---|---:|---:|---:|
| Fired checkpoints | 18 | 21 | 39 |
| Usable exact-ladder entry with one-lot depth | 12 | 15 | 27 |
| Usable entry with two-lot depth | 12 | 12 | 24 |
| One-lot bid on the selected token in the hard-flat minute | 11 | 12 | 23 |
| Two-lot bid on the selected token in the hard-flat minute | 11 | 8 | 19 |
| One-lot path to hard flat with no gap over 90 seconds | 4 | 4 | 8 |
| Two-lot path to hard flat with no gap over 90 seconds | 0 | 0 | 0 |
| Native ten-second path to hard flat at either size | 0 | 0 | 0 |

Seven fired checkpoints lacked a complete verified ladder and five lacked a recorder batch after the signal within the minute. Among the 31 checkpoints with complete signal context, 19 had usable one-lot entry evidence and 16 had two-lot evidence. Of 26 fired checkpoints on dual-eligible dates, nine coincided with the strict paired-clock result. Both venues fired on four representative clocks. The best observed one-lot path still had a 61.34-second gap. Requiring a path through hard flat gives a common coverage horizon. An actual trade can exit earlier, so the result does not determine its exit or profitability.

`python control_signal_coverage.py <local-export>` verified the pre-cutoff quote hashes, dated masters and native source, with a separate hash for the scoped futures and regime rows so the export can rotate. A second run reproduced the saved results. The prior synchronized-clock report also reproduced after reusing its quote helpers. Twenty-nine focused checks passed, including synthetic tests for regime lookahead, first-batch selection and exact same-batch exit marks. This research contributes entry feasibility and explains why the archive cannot presently establish the deployed two-venue lifecycle. Keep the November 3–5 observed Production reconciliation separate. No new strategy or P&L was scored.

## Forward exit observability

The frozen A rule can loosen a native profit lock when the futures trend supports the trade. A synthetic long with entry premium ₹100 and peak ₹140 has a ₹120 native lock floor, which keeps 50% of the gain. A's ₹114 floor keeps 35%. Two ₹116 bids ten seconds apart confirm the native exit and leave A open. Only later quotes can determine A's close. In the synthetic check, two later ₹112 bids confirm its exit. The same test uses the unchanged `Trend` and shared exit evaluator.

The fast exit loop only loads native open positions and stops provider work when the books are flat. Its native held journal therefore cannot supply this hypothetical continuation. The separate recorder can retain an exact token, but its nominal interval is 60 seconds and the earlier audit found no complete ten-second path. A forward comparison must preserve the exact option bid and dated futures observations while either arm remains open, keep each arm's own lock confirmation clock, and record missing continuation as unresolved. The native close price cannot fill A. The paper journal stores price and time, and the separate ₹15,000 execution question would also need observed depth. Replaying held entries alone remains a fixed-entry experiment. Changes in occupancy or cash require a separate shared-wallet comparison.

The recorded November 5 improvement of ₹1,050.98 used three candidate exits inside the existing native held paths. That result does not establish the coverage of future delayed exits. The new check is synthetic and does not rescore November 5, alter the frozen A code or start forward collection. [Synthetic proof](test_exam_evidence_limits.py), [native fast exit](../../../../python-engine/fno_orchestrator.py), [held journal](../../../../python-engine/fno_exit_paths.py).

## Chronological shared-wallet mechanics slice

The November reconciliation establishes conditional sizing and settlement for observed trades. Build a research-only replay of the shared directional wallet so a NIFTY entry can change the SENSEX decision on the same tick and either venue's settlements affect both. The input contract is one chronological IST tick, prequalified same-venue option and futures observations, and fired native signal and chain inputs. Carry the contemporaneous N11 gate result and an explicit spread reserve or cash settlement as external inputs. Invoke native entry and exit functions with the shared risk state. Keep the stricter historical quote evidence separate from paper execution semantics.

Verify synthetic simultaneous signals, venue-specific lot sizes and fees, expiry eligibility, reserve usage, loss and re-entry gates and missing or late quote handling. The slice does not build the earned-lot or spread strategy, reconstruct the N11 shadow gate, or score a historical period. Complete those inputs and qualify the archived quote path before attempting the combined historical result. No configuration, migration or rollout. Rollback is to remove this isolated Dev research adapter.

### Verification and evidence boundary

The directional control now takes one time-ordered stream. Each tick manages existing positions with the corresponding venue's exact token and futures mark, applies confirmed spread cash and exposure supplied by the caller, then runs native NIFTY and SENSEX entry planning in that order. The shared ledger applies fees from the option's own segment, uses the dated contract's lot size and updates realised equity before entry. It includes native portfolio brakes, adaptive sizing, per-venue expiry and stopped re-entry checks, and the NIFTY-only tolerance fallback when the shared reserve refuses two lots.

The replay requires displayed depth at the admitted ask and at the held bid. Production paper can mark against thinner bids or fall back to the last traded price. This stricter historical comparison keeps an unavailable entry or a held quote gap explicit. It clears pending lock confirmation after a missing bid and refuses to carry an unresolved position into another session. A passed synthetic test does not fill a gap in historical evidence.

Thirteen synthetic cases passed in `test_shared_control.py`. The first lock fixture used EFF, whose native profit lock is disabled. The corrected fixture uses OR20 and verifies peak persistence with no futures quote, two distinct bid observations for confirmation, and how a missing quote interrupts confirmation. The wider focused suite passed 146 checks covering the new control, archive coverage, exam runner, native gates, adaptive risk, fees, N11 and N11T and shared cash. Run the local Dev venv's pytest against those research and engine files. The regenerated atlas still indexes 304 modules. No existing market data was scored and the sealed exam inputs stayed unopened. This commit adds research code and tests only. Production was read-only at `398d44ad`. There is no change to configuration, migration, broker or rollout.

The combined historical control still needs qualified bid paths at native management clocks, dated chains, N11 gate and earned-lot evidence, and synchronized spread reserve and settlements. Integrate those inputs as a separate slice before reporting a shared-wallet result.

## Earned-lot mechanics slice

A two-lot N11 parent can consume extra cash before the scheduled spread and regular entry passes. Add this management stage to the Dev replay with its own exact contract bid and ask and the spread reserve still in force before spread management. Reuse the native progress and risk charges. Keep one child per parent, the parent-linked exit, segment fees and the distinction between cash and an adaptive single-leg strike. Tests must prove venue isolation, chronological quote refusal, reserve ordering, parent and child exit order, and the effect of earned occupancy on later entries. Existing N11 gate and spread observations remain external. An absent input stays explicit. No candidate scoring, rollout or migration. Rollback is to remove the research stage.

### Verification and Production sample

The Dev replay applies the add after single-leg exits and before the spread cash update. A child reserves premium and segment fees. It contributes realised cash without using a regular entry slot or adding an adaptive strike. Child exits consume the same displayed bid size as the parent, so a missing third lot of bid depth leaves that child unresolved at that tick. The add uses a separately supplied same-venue quote. This is stricter than the Production paper top-of-book treatment.

The 18 shared-wallet cases and 151 focused checks passed. Earlier test runs exposed a missing local entry key after a refactor and a synthetic SENSEX fixture whose sizing cap could admit only one lot. The corrected checks exercise the parent and child rules with explicit fixture limits. The generated atlas remains at 304 modules.

The read-only [November 3–5 audit](deployed-earned-nov5.json) reproduced from Panel D export 20261106T103349Z using `python audit_earned_nov5.py <export>`. The three two-lot parents had 805 pre-exit futures marks. The maxima were 0.347206R for position 55, 0.338859R for 56 and 0.590618R for 57. The ledger contained no child for any of the three. The comparison checks the observed no-add case. The add fills and the parent-linked exit are verified on synthetic data. Actual historical add fills require the dedicated option quote, the matching future and both books' shared cash at that point. The scoped Production checkout remained at `398d44ad`. No runtime, configuration, migration or deployment change.

## Point-in-time N11 gate slice

Connect a read-only gate source to the shared replay. Use the N11 volatility reading only from its recorded time and the completed N11 one-lot shadow results strictly before the decision time. Keep the research seeds in the native ordered history and apply the native stand-aside and positive-paper formulas. An out-of-coverage clock must refuse a new entry while held management remains available. Freeze the observed scope to November 2–6. Compare the saved flags against the native volatility records, the shadow entry flags and the five previously audited directional entries. Count historical coverage separately from this observed parity. The 2025–2026 market replay must still generate its own counterfactual shadow history before it can claim a causal portfolio result. No candidate scoring, configuration, migration or rollout. Rollback removes the Dev research input adapter.

### Gate verification and coverage

The Dev control accepts a time-scoped gate tape for both venues. The tape uses the recorded same-day volatility only once available and only includes shadow exits strictly earlier than the decision. Equal-time earlier closes use the native ID ordering. A clock outside the declared scope or on a date with no known volatility record leaves new entry evidence unavailable. An earlier clock on a recorded day uses the native unknown-volatility handling. Existing exit management still runs. The input source must supply all settled shadow history before its scope, including any native opening seeds.

The [observed gate audit](control-gate-audit.json) matched all five volatility rows and the stored flags on all six N11 shadow entries. It also matched the prior-20 net and the expected open gate on directional positions 55–59. The prior-20 net was ₹19,159.13 on four entries and ₹19,665.05 on the fifth. The live store had 22 research seed closes and six native one-lot closes. At each directional entry only three or four native closes were available before the decision. Removing the research seeds would turn the positive-paper flag off at all five clocks. That flag can allow NIFTY tolerance sizing, subject to the other gates. The original audit found no tolerance upgrade on these five trades, so this check supplies no incremental P&L.

The 31 September–October dates in the pre-cutoff native signal audit have zero matching logged volatility dates. November records establish observed gate parity for November 2–6 only. The older replay still needs causal volatility inputs and its own one-lot shadow history with exact management quotes. A tape of the observed November outcomes cannot stand in for that historical state.

To reproduce, pipe `audit_control_gate.py --runtime` via stdin to the Production engine under the read-only query and save its stdout in Dev. Run `python audit_control_gate.py --evidence <capture>` with that capture. The local input hash and observed Production release are recorded in the report. A repeat run reproduced the output exactly. Four new synthetic checks cover the same-time shadow cutoff, duplicate-time order, both venues and held management after coverage ends. The 22 shared-wallet checks and 155 focused checks passed. The regenerated atlas remains at 304 modules. Production stayed at `398d44ad`. No runtime, settings, migration or rollout change. No candidate was scored and the 2022 exam stayed sealed.

## Historical one-lot shadow path slice

Test whether a representative native N11 one-lot shadow can reach its own exit before the recorder loses the contract. Use the same 31 frozen dates, NIFTY signal clocks, dated chains and first eligible raw packet as the previous market audit. Run the native entry planner with a fixed 250,000 rupee allocation, one lot and fresh independent entry state at each fired clock. This checks individual candidate paths without assuming a historical shadow portfolio. Use the exact option bid and matching futures packet. Require displayed depth for one lot, a minimum 55 seconds between management checks before hard flat, and a maximum 90 seconds from the previous check or entry. Keep the first eligible check and refuse a path at its first unverified gap. Use the native shadow ladder and EFF clock. Record only evidence status, clocks and exit reasons. An early resolved path may need fewer observations than a path through hard flat. No P&L or candidate selection is in scope. No configuration, migration or rollout. Rollback retires the isolated research audit.

### Coverage result

The 31-session archive yielded 18 representative NIFTY signal clocks. The native one-lot planner accepted all 12 candidates with verified entry evidence in the fresh-state check. Two of the 12 resolved at the sampled management clocks. October 7 reached the native underlying stop after 12 looks and October 8 reached hard flat after 275. Both had complete signal context under the earlier audit. Four fired clocks had no recorder sample after the signal within its minute, and two lacked the complete strike ladder. The other ten candidate paths hit a held gap before an exit. Their first gaps ranged from 92.54 to 272.65 seconds.

Four NIFTY paths had met the earlier 90-second check across all available marks through hard flat. Two of those four fail the new check after applying the representative 55-second minimum between management decisions. A supply of raw observations every 90 seconds does not guarantee equivalent management once the native cadence is applied. These outcomes are sampled path checks on independent entries. They do not establish the shadow book's realised cash, occupancy, stopped re-entry levels or exact production management clocks.

The 16 unqualified signal clocks prevent a reliable chronological historical shadow or recent-20 gate in this archive. The two resolved paths may be used as path fixtures. The full 2025–2026 shared control still needs continuous exact chain and held quotes, plus the native spread and volatility inputs. No market P&L was calculated.

### Verification

Run `python shadow_path_coverage.py <Panel D export>` from Dev. The report uses export `20261106T103349Z` with the pre-October 29 scope and the existing dated-master and daily-input hashes. The first run mixed native diagnostic logs into the JSON stream. Redirecting those logs to stderr produced a clean [machine-readable report](shadow-path-coverage.json) with the same result for all 18 paths. The first fixture run exposed the test module's import order and passed after correction. Four synthetic path cases cover an early underlying stop, insufficient bid depth, EFF's soft time stop and hard-flat clock. All 159 focused research and native checks passed. The regenerated atlas remains at 304 modules. Production was read-only at `398d44ad`. No configuration, migration or rollout effect.

The original 31-session two-index signal coverage audit reproduced exactly after adding optional signal geometry for this path check.
