from prior_range_reclaim import Bar, START, decision, geometry


def test_long_and_short_symmetric_and_target_is_midpoint():
    inside = Bar(1020, 1030, 1010, 1020)
    sweep = Bar(1020, 1020, 990, 995)
    reclaim = Bar(995, 1010, 993, 1009)
    long = geometry(1000, 1100, inside, sweep, reclaim, 600)
    assert (long.direction, long.minute, long.stop, long.target) == ("LONG", 600, 989.95, 1050)
    mirror = lambda row: Bar(2100 - row.open, 2100 - row.low, 2100 - row.high, 2100 - row.close)
    short = geometry(1000, 1100, mirror(inside), mirror(sweep), mirror(reclaim), 600)
    assert (short.direction, short.stop, short.target) == ("SHORT", 1110.05, 1050)


def test_two_sided_and_poor_reward_are_rejected():
    inside = Bar(1020, 1030, 1010, 1020)
    assert geometry(1000, 1100, inside, Bar(1020, 1101, 990, 995), Bar(995, 1010, 993, 1009), 600) is None
    assert geometry(1000, 1100, inside, Bar(1020, 1021, 990, 995), Bar(995, 1040, 993, 1039), 600) is None


def test_incomplete_prior_and_current_and_no_lookahead_past_first_decision():
    prior = {minute: Bar(1050, 1100, 1000, 1050) for minute in range(START, 930)}
    current = {minute: Bar(1020, 1021, 1019, 1020) for minute in range(START, 600)}
    current.update({minute: Bar(995, 1020, 990, 995) for minute in range(590, 595)})
    current.update({minute: Bar(1009, 1010, 993, 1009) for minute in range(595, 600)})
    assert decision(prior, current)[1].minute == 600
    assert decision(prior, {**current, 600: Bar(0, 0, 0, 0)})[1].minute == 600
    assert decision({k: v for k, v in prior.items() if k != 929}, current)[0] == "missing_prior_same_contract"
    assert decision(prior, {k: v for k, v in current.items() if k != 599})[0] == "missing_current_before_decision"
