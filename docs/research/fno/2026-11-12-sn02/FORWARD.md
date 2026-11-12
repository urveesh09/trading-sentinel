# SN02 forward check (frozen Nov 12, 2026, before the Nov 13 session)

**The candidate is SN02**, N11's own entries and exits inside the owner's ₹15,000 wallet:
- one NIFTY option lot per N11 signal, one position at a time;
- if one lot of N11's contract costs more than ₹15,000, the strike one step further out of the money (same side, same minute) instead;
- N11's own exits; **no 10% day cap**;
- a ₹3,000 day loss limit (20% of the wallet);
- the wallet stays at ₹15,000: no growth while this check runs.

**Why it is only a candidate:** every SN02 number in `README.md` is in-sample. N11's entries were shaped on 2023–2026, and SN02's overlay was picked after looking.

**The forward data is unseen:** sessions from **Nov 13, 2026** on. Oct 29 – Nov 12 was looked at on Nov 12 through the main paper book, so it does not count.

**Source:**
- Production's one-lot paper record `fno_n11_paper` (NIFTY, every N11 signal at one lot, live quotes), closed rows with an entry date from 2026-11-13, exported read-only.
- The out-of-the-money substitute is priced from the research quote archive (`/data/research/quotes`, ATM±5), read-only:
  - entered at the ask of the first archived quote at or after the record's entry time;
  - sold at the bid of the first quote at or after its exit time;
  - if it can't be priced, the trade is skipped and counted.
- **Charges:** the shipped model, with no extra stress, because these are live quotes.

**Day loss limit:** once a day's realised result reaches −₹3,000, that day's later trades are skipped. A stop inside a trade cannot be replayed from closed records; that limitation is stated, not repaired.

**Rule, scored once at ≥ 20 counted trades:**
- **PASS** when the net after charges is > 0 AND the net without the single best trade is > 0.
- Otherwise **FAIL**.
- Report also: the trades skipped (busy, unaffordable, unpriceable), the days won, lost and empty, and the worst day.

**What a PASS means:** SN02 may be offered to the owner for real money at ₹15,000, by its own runbook and only on the owner's word. A FAIL ends SN02.

**At about 0.3 N11 signals a session,** 20 trades takes roughly 3–4 months. The rule is not shortened.
