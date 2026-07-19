"""
[PARTNER-ENRICH 2026-07-19] Macro event calendar (T3c): event-day and
day-before warnings, silence otherwise, and the static map's shape.
"""
from datetime import date

import macro_events as me


def test_event_day_warns_about_crush():
    day = date(2026, 7, 29)   # FOMC decision in the map
    note = me.event_note_for(day)
    assert "TODAY" in note and "crush" in note


def test_day_before_warns_against_holding():
    note = me.event_note_for(date(2026, 7, 28))
    assert "tomorrow" in note and "avoid holding" in note


def test_quiet_day_is_silent():
    assert me.event_note_for(date(2026, 7, 20)) == ""


def test_map_shape_is_iso_dates_to_labels():
    for k, v in me.MACRO_EVENTS.items():
        assert date.fromisoformat(k)   # raises on a malformed key
        assert isinstance(v, str) and v
