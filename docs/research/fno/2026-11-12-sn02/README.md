# SN02: what SN01 taught, applied to the ₹15,000 wallet (Nov 12, 2026)

**This is an exploratory, in-sample description.** No freeze was committed before these runs, and every year used here was already seen. The one honest test is the frozen forward check in `FORWARD.md` (sessions from Nov 13). Research only, in Dev: no runtime change, no Production write, no order.

## The owner's follow-up

- "Get it profitable", with any data granularity and full freedom.
- Learn from N08–N012, which the owner calls the profitable "gold".
- Quick trades or longer holds are both fine.
- "If at a certain point we stop increasing the wallet … and just continuously farm" the minimum, does that help? The owner expected the start to have been easier.

## SN01's lessons that shaped SN02

- **Costs:** each trade pays about ₹85–120 per lot in charges and spread. No entry of SN01's own covered it, so fewer and bigger trades.
- **Where the profit is:** the system's proven profit (N11) comes from a few large winners. A cap at ₹1,500 cuts exactly those.

## A. N11's entries inside the SN01 wallet (`sn02_ext.py`, `sn02_grid.py`)

**Parity first.** N11's stored one-year replays (`2026-11-02-fno-n11/_local/evals`, book `N11`) replayed in the SN01 simulator:
- entry and exit prices match exactly (median difference 0.00);
- per trade about −₹3 (charges on one lot, against N11's per-lot share of two).

One position at a time; `skip` means an unaffordable lot is skipped.

**One lot, ₹15,000 wallet, ₹3,000 day loss limit, four-year totals:**

| Exit | +₹0 | +₹100 | +₹205 |
|---|---:|---:|---:|
| **N11's own exits**, skip | 1,11,612 | 96,449 | 84,579 |
| **N11's own exits**, out-of-the-money substitute (`otm`) | **1,36,688** | **1,20,226** | **1,06,990** |
| Sell at the ₹1,500 day target | 32,586 | 19,544 | 11,240 |
| Lock at ₹1,500, trail 0.5 × target | 70,800 | 53,699 | 45,715 |
| Lock, trail 1.0 × target | 81,174 | 67,302 | 59,287 |

- **The 10% cap cuts 70–90% of N11's money.** The lock is the least bad overlay, and still below N11's own exits.
- **By year, `otm` at +₹205:** 2023 −7,059; 2024 +35,618; 2025 +34,109; 2026 +44,322.
- **2023 is negative in every variant.** N11 was built after 2023 had been seen, and it still loses there.
- **Leave-one-year-out over the overlay alone** (21 variants): "N11's own exits" is chosen with every year held out. The entries stay in-sample.

## B. Buying both sides on move days (`sn02_strangle.py`)

- **What it is:** a call and a put, at the money or 1–2 strikes out, at 09:20–10:45. Exits at a target of ₹750–3,000 or a stop of ₹1,500–3,000, after 30–360 minutes. Days: all, after a narrow day, or after a wide day.
- **Result:** 648 combinations at +₹0. **None is positive in every year.** The best is −₹7,580 over four years; the median is −₹62,053.
- **Dead:** time decay and double charges beat the move.
- Opening-drive and prior-range ideas were already tested by the N012 rounds (Nov 6, `2026-11-05-fno-n12`), and none qualified.

## C. The wallet: grow, cap or farm (`sn02_ledger.py`; N11 entries, `otm`, N11's exits)

Jan 2023 → Oct 2026, 742 sessions:

| Wallet rule | +₹0 | +₹100 | +₹205 | Worst day at +₹205 | Largest fall at +₹205 |
|---|---:|---:|---:|---:|---:|
| **Farm: ₹15,000 forever, 1 lot** | 1,42,103 | 1,25,441 | **1,11,995** | −2,998 | 11,225 |
| Grow at most 1 step (₹22,500), then farm | 2,45,534 | 2,03,348 | 1,42,315 | −4,532 | 16,696 |
| Grow at most 2 steps (₹33,750), then farm | 3,52,317 | 3,12,674 | 2,39,621 | −6,751 | 23,218 |
| Grow without limit (lots follow the wallet) | 31,16,443 | 19,60,602 | 8,88,177 | −51,093 | 93,447 |
| Owner's target rule: lock 1.0, every 2 | 1,22,432 | 34,975 | 25,170 | −4,532 | 22,039 |
| Owner's target rule: sell at target, every 2 | 28,658 | 15,022 | −78 | −2,998 | 24,988 |

- **Unlimited growth is not believable.** It reaches 59 lots by Oct 2026, with no extra slippage and days of −₹51k. The house rule applies: as-replayed results at high size are never reported as achievable.
- **Farm, by half-year at +₹205:**

  | Half | Result |
  |---|---:|
  | 2023-H1 | −4,472 |
  | 2023-H2 | −2,587 |
  | 2024-H1 | +18,054 |
  | 2024-H2 | +17,563 |
  | 2025-H1 | +26,490 |
  | 2025-H2 | +12,623 |
  | 2026-H1 | +17,918 |
  | 2026-H2 | +26,404 |

- **The start was the hardest stretch, not the easiest.** In SN01 at realistic costs the wallet never grew at all, so growth was not why SN01 lost.
- **Farming the minimum does work as a risk choice.** Capping growth gives up profit but keeps the worst day near the 20% limit.
- **Activity:** about 55 green and 63 red days, with no trade on 624 of 742 days. This is not a 10%-every-day strategy. On ₹15,000 it averages about ₹150 a session (~1%), mostly from a few big days.

## Forward evidence already in hand (looked at Nov 12, so not part of the frozen check)

- **The main paper book's NIFTY N11 trades, Nov 2–11** (forward-panel export `20261112T103005Z`, read-only): 7 trades, about +₹141 per lot in total. Roughly flat.
- **The one-lot record** `fno_n11_paper`, Nov 3–11 (N13 note): +₹12,883 over 5 trades.

## Data granularity

- History exists only as 1-minute candles. The live quote archive samples about once a minute. Breeze can serve 1-second history, but only with the owner's daily login and many days of download.
- Finer data makes a simulation more honest, usually worse for quick trades; it does not create an edge.
- SN02 holds trades for 30 minutes to hours, so 1-minute data is adequate.

## Verdict and next step

- **SN02:**
  - N11's entries and exits at one lot in a fixed ₹15,000 wallet;
  - the out-of-the-money substitute when a lot is unaffordable;
  - a ₹3,000 day limit, no 10% cap.
- It is the best version found. It is **unproven**: in-sample, a loss in 2023, and flat in the few forward trades so far.
- **The frozen forward check** (`FORWARD.md`) scores it from Nov 13 at ≥ 20 trades, from Production's existing one-lot record. That record already runs, so no runtime change is needed to collect it.
- Real money only after a PASS, and only on the owner's word.

## Files

| File | Holds |
|---|---|
| `sn02_ext.py` | N11 entries in the SN01 simulator |
| `sn02_grid.py` → `results-grid.json` | overlay grid |
| `sn02_strangle.py` → `results-strangle.json` | buying both sides |
| `sn02_ledger.py` → `results-ledger.json` | wallet rules |
| `FORWARD.md` | the frozen forward check |

- It reuses `../2026-11-12-sn01` (`sn01_sim`, `sn01_data` caches).
