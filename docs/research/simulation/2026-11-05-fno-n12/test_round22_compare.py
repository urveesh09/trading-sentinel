import round22_compare as gates


def year(year, candidate, unresolved=0):
    def row(daily):
        return {"daily": daily, "net": sum(daily.values()), "worst_day": min(0., *daily.values()),
                "drawdown_pct": 2.0, "unresolved": 0}

    outcome = row({f"{year}-01-02": candidate, f"{year}-01-03": 150.})
    outcome["unresolved"] = unresolved
    return {"N11": row({f"{year}-01-02": 100.}), "N11T": row({f"{year}-01-02": 150.}),
            "ACCEPT_15": outcome}


def test_development_uses_stronger_control_and_keeps_qualification_separate():
    panels = {str(y): year(y, 250.) for y in range(2022, 2027)}
    result = gates.compare(panels, "ACCEPT_15")
    assert result["control"] == "N11T" and result["control_net"] == 750.
    assert result["increment_after_best_five"] == 500.
    assert result["provisional_development_pass"]
    assert result["qualified"] is False


def test_concentration_and_unresolved_exposure_fail_even_if_net_passes():
    result = gates.compare({"2022": year(2022, 400., unresolved=1)}, "ACCEPT_15")
    assert result["gates"]["20_percent_net_improvement"]
    assert not result["gates"]["after_best_five_incremental_days"]
    assert not result["gates"]["no_unresolved_exposure"]
