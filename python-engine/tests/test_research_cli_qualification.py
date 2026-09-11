import json

from research_cli import main


def test_full_policy_cli_writes_nonqualifying_causal_decision(tmp_path, capsys):
    bars = tmp_path / "bars.csv"
    bars.write_text("bar_start,open,high,low,close,volume\n2026-09-11 09:15:00,100,102,99,101,100\n", encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"state": "RETROSPECTIVE", "source": "historical-kite",
                                      "event_at": "2026-09-11T03:45:00+00:00",
                                      "received_at": None, "retrieved_at": "2026-09-12T03:45:00+00:00"}), encoding="utf-8")
    output = tmp_path / "decision.json"
    result = main(["full-policy-diagnostic", "--underlying", "NIFTY", "--bars", str(bars),
                   "--regime", "REGIME_1_NORMAL", "--decision-at", "2026-09-11T04:00:00+00:00",
                   "--bar-provenance", str(provenance), "--output", str(output)])
    assert result == 0 and output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["state"] == "NO_SETUP" and saved["can_qualify"] is False
    assert "NO_SETUP" in capsys.readouterr().out
