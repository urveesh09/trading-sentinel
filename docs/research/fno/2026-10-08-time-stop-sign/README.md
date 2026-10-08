# F&O time stop after the bought-put sign fix (Oct 8 audit O8-F2)

Development evidence on the same 18 archived sessions as
`2026-10-07-exit-and-reentry` (Sep 10 to Oct 7, `_local/with-oct7`, which is
not committed). It is in-sample, not forward proof.

## The bug

`fno_exit_rules` negated premium P&L for `direction == "SHORT"`. Single-leg
positions always **buy** the option (a PE for a bearish view) and settle as
`(exit - entry) x qty`. So the "defer the time stop while in profit" rule
(`FNO_TIME_STOP_RESPECTS_PREMIUM`) actually deferred **losing** puts and cut
profitable ones. Calls were handled correctly.

## Replay (profit lock 0.4 R / keep half + re-entry confirmation, as shipped)

Live halts on (15% drawdown halt from the Rs 2.5 L pool):

| Time-stop rule | Trades | Net | Max DD | PF |
| --- | --- | --- | --- | --- |
| Corrected sign, deferral ON | 8 | −₹5,267 | ₹5,267 | 0.07 |
| **Corrected sign, deferral OFF (shipped)** | **11** | **+₹6,968** | **₹1,991** | **2.26** |
| Defer only while the profit lock is armed | 11 | +₹6,748 | ₹1,991 | 2.22 |

The drawdown halt dominates the first row: the replay starts near the
halt line (~₹212.5k), so a few small losses stop all later entries,
including the Sep 28, Sep 30 and Oct 1 trail winners.

With the halt removed, so every arm takes the same trades:

| Rule | Net | Max DD | PF |
| --- | --- | --- | --- |
| Old inverted sign, deferral ON (what Oct 7 shipped) | ₹8,411 | ₹1,991 | 2.97 |
| Corrected sign, deferral ON | ₹3,487 | ₹4,170 | 1.58 |
| Deferral OFF (sign irrelevant) | ₹6,604 | ₹1,991 | 2.12 |

The old rule's extra ₹1,807 over "deferral OFF" comes from three puts
(Sep 10, Sep 24, Sep 28 11:55) that it held while losing and that then
recovered. That is a hold-the-loser effect on three trades, so it was not
kept. With the sign correct, deferral loses money on both sides: Sep 28 10:25
gives +₹356 banked against −₹144 deferred, and Sep 23's call gives +₹638
against +₹417.

Scripts: `replay_time_stop.py <root> <start> <end> <out> <drawdown_pct>` and
`replay_old_vs_new_sign.py`. Results: `results.json`.
