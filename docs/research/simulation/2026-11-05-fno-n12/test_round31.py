from round31 import placebo_dates, score


def test_placebo_dates_use_only_prior_matching_weekdays_and_skip_events():
    sessions = ["2025-05-23", "2025-05-30", "2025-06-05", "2025-06-06", "2025-06-13", "2025-06-20"]
    assert placebo_dates(sessions, {"2025-06-06", "2025-06-13"}, "2025-06-13") == ["2025-05-30", "2025-05-23"]


def test_score_removes_the_five_best_events_and_paired_contributions_separately():
    panels = {str(y): {"pairs": [({"points": 30.}, {"points": 8.})] * 4} for y in range(2022, 2027)}
    follow, fade = (score(panels, side) for side in (1, -1))
    assert follow["paired_events"] == 20
    assert follow["event_ex_best_five"] == 225.
    assert follow["paired_increment_ex_best_five"] == 330.
    assert follow["advance_to_options"]
    assert not fade["advance_to_options"]
