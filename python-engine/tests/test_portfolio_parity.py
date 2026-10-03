from portfolio_parity import reconcile_shared_cash


def _trade(ticker, entry_at, price, shares, *, exit_at=None, pnl=None, status="CLOSED"):
    row = {"ticker": ticker, "entry_time_utc": entry_at, "entry_fill_price": price,
           "shares": shares, "status": status}
    if exit_at:
        row["exit_fill_ts"] = exit_at
    if pnl is not None:
        row["net_pnl"] = pnl
    return row


def test_shared_cash_rejects_simultaneous_overcommitment_deterministically():
    result = reconcile_shared_cash([
        ("penny", [_trade("AAA", "2026-01-01T09:30:00+05:30", 700, 1, exit_at="2026-01-01T15:00:00+05:30", pnl=10)]),
        ("momentum", [_trade("BBB", "2026-01-01T09:30:00+05:30", 700, 1, exit_at="2026-01-01T15:00:00+05:30", pnl=10)]),
    ], initial_cash=1_000)
    assert (result.admitted, result.cash_rejected, result.final_cash, result.locked_cash) == (1, 1, 1_010, 0)


def test_cash_is_not_reused_until_the_recorded_exit_event():
    result = reconcile_shared_cash([
        ("cnc", [_trade("AAA", "2026-01-01T09:30:00+05:30", 800, 1, exit_at="2026-01-03T15:45:00+05:30", pnl=20)]),
        ("mis", [_trade("BBB", "2026-01-02T09:30:00+05:30", 500, 1, exit_at="2026-01-02T15:00:00+05:30", pnl=10)]),
    ], initial_cash=1_000)
    assert result.cash_rejected == 1
    assert result.final_cash == 1_020


def test_unresolved_exposure_stays_locked_not_marked_as_a_loss_or_free_cash():
    result = reconcile_shared_cash([
        ("penny", [_trade("AAA", "2026-01-01T09:30:00+05:30", 600, 1, status="UNRESOLVED")]),
    ], initial_cash=1_000)
    assert (result.unresolved, result.locked_cash, result.final_cash, result.realized_pnl) == (1, 600, 400, 0)
