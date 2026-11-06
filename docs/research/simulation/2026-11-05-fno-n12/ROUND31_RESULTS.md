# Round 31 results. RBI impulse continuation was concentrated

The 27 decision dates and both fixed-clock arms were frozen at `2678b41`. Six dates failed the regular calendar gate. The remaining 21 had exact positive-volume futures marks and an earlier same-weekday placebo. November 5 had no scheduled RBI decision in the frozen list. [Dated evidence](RBI_CALENDAR_EVIDENCE.md), [session receipts](round31-results.json).

| Rule | Event points after hurdle | Event points without best five | Increment versus paired placebo | Increment without best five | Positive years |
|---|---:|---:|---:|---:|---:|
| Follow | +263.75 | −306.20 | +853.40 | +90.90 | 3 of 5 |
| Fade | −893.75 | −1,106.40 | −853.40 | −1,191.75 | 0 of 5 |

The follow rule beat matched dates, and its own points turned negative without the strongest five events. Fade failed on both absolute and paired points. Neither met the gate for option pricing. The figures are signed futures points with a 15-point hurdle per date. They supply no F&O wallet or fill result. The event rule used fixed clocks around the scheduled window, with no assumption about the exact release minute.

`pytest -q test_round31.py` passed two checks. The frozen `python round31.py` completed after verifying the five dated archive manifests. The combined Round 27–31 focused suite passed ten checks. All scored windows are development data. No orders or runtime changes came from this study.
