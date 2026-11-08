"""Read-only November 5 test using production exports and exact held inputs."""
import argparse
from contextlib import closing
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import round18 as vol
import round19 as strategy
from fno_exit_paths import params_digest

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026-11-05-fno-expiry-followup"
sys.path.insert(0, str(PREVIOUS))
from regular_today import outcome, stamp

DAY = "2026-11-05"
CALENDAR_DIR = HERE / "_local/india-vix/nov5-calendar"


def read(path):
    return json.loads(path.read_bytes())


def dated_contracts(day, earlier, expected_hash):
    path = CALENDAR_DIR / f"NSE-{earlier}.raw"
    assert vol.sha(path) == expected_hash and earlier < day
    with zipfile.ZipFile(path) as archive:
        member, = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        rows = list(csv.DictReader(io.StringIO(archive.read(member).decode("utf-8-sig"))))
    options, futures = set(), set()
    for row in rows:
        if row["TckrSymb"] != "NIFTY":
            continue
        assert row["TradDt"] == earlier
        expiry = row["FininstrmActlXpryDt"] or row["XpryDt"]
        if expiry < day:
            continue
        if row["FinInstrmTp"] == "IDF":
            futures.add((expiry, row["FinInstrmNm"]))
        elif row["OptnTp"] in ("CE", "PE"):
            options.add(expiry)
    return min(options), min(futures)[1]


def forecast_from_export(db, archive, official, calendar):
    closes = official["closes"]
    days = sorted(closes)
    records = []
    for folder in vol.DATASETS.values():
        with closing(sqlite3.connect((folder / "breeze.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as con:
            previous, _ = vol.observations(read(folder / "manifest.json"), con, closes, days)
        records.extend(previous)
    cut = records[-1][0]
    excluded = {}
    actual = None
    for day in [d for d in days if cut < d < DAY] + [DAY]:
        earlier, digest = calendar[day]
        option_expiry, future_name = dated_contracts(day, earlier, digest)
        if option_expiry == day:
            excluded[day] = "own expiry"
            continue
        future_token, = [int(token) for token, name in archive["nifty_future_tokens"].items() if name == future_name]
        prices = dict(db.execute(
            "SELECT substr(datetime,12),close FROM fut_candles WHERE instrument_token=? AND interval='minute' "
            "AND datetime BETWEEN ? AND ?",
            (future_token, f"{day} {vol.MARKS[0]}", f"{day} {vol.MARKS[-1]}"),
        ).fetchall())
        values = [prices.get(mark) for mark in vol.MARKS]
        if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
            excluded[day] = "incomplete futures clocks"
            continue
        variance = 252. * sum(math.log(b / a) ** 2 for a, b in zip(values, values[1:]))
        feature = vol.official_features(closes, days, day)
        assert feature is not None and variance > 0
        records.append((day, variance, feature))
        if day == DAY:
            actual = variance
    assert actual is not None
    forecasts = vol.score(records)["2026"]
    expected = strategy.forecasts()[cut]
    reconstructed = next(row for row in forecasts if row["day"] == cut)
    assert [reconstructed["realized_only_log_forecast"], reconstructed["implied_log_forecast"]] == expected
    forecast = forecasts[-1]
    assert forecast["day"] == DAY
    return forecast, excluded, [d for d, _, _ in records if cut < d < DAY]


def compare_held(rows, path, factor):
    looks = {row["id"]: [] for row in rows}
    for line in path.open(encoding="utf-8"):
        mark = json.loads(line)
        if mark["source"] == "FNO_PAPER" and mark["position_id"] in looks:
            looks[mark["position_id"]].append(mark)
    compared = []
    for row in rows:
        held = sorted(looks[row["id"]], key=lambda mark: stamp(mark["at"]))
        params = held[0]["params"]
        assert all(mark["params_sha"] == params_digest(params) and mark["token"] == row["token"] for mark in held)
        clocks = [stamp(mark["at"]) for mark in held]
        gap = max((b - a).total_seconds() for a, b in zip(clocks, clocks[1:]))
        baseline = outcome(row, held, [], "N11T", rows, 250000.)
        assert baseline["exit_time"] == row["exit_time"] and baseline["reason"] == row["exit_reason"]
        assert baseline["exit"] == row["exit_premium"] and abs(baseline["net"] - row["pnl"]) < .01
        altered = {**params, "FNO_TRAIL_ATR_MULT": params["FNO_TRAIL_ATR_MULT"] * factor}
        changed = [{**held[0], "params": altered}, *held[1:]]
        candidate = outcome(row, changed, [], "N11T", rows, 250000.) if gap <= 90. else {
            "status": "UNAVAILABLE", "reason": "held gap exceeds 90 seconds"}
        compared.append({"id": row["id"], "baseline": baseline, "candidate": candidate,
                         "looks": len(held), "max_gap_seconds": gap})
    return compared


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    archive = read(args.export / "manifest.json")
    freeze = HERE / "round19-nov5-freeze.json"
    frozen = read(freeze)
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(vol.ROOT).as_posix()}"], cwd=vol.ROOT))
    for name, digest in frozen["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == digest
    assert vol.sha(args.export / "manifest.json") == frozen["export_manifest"]
    for name in ("fno-replay.sqlite", f"fno_exit_paths/{DAY}.jsonl"):
        assert vol.sha(args.export / name) == archive["files_sha256"][name]
    historical = read(HERE / "round18-freeze.json")
    assert vol.sha(vol.INPUT) == historical["official_closes"]
    for year, folder in vol.DATASETS.items():
        assert [vol.sha(folder / f) for f in ("manifest.json", "breeze.sqlite")] == historical["futures"][year]
    db_path = args.export / "fno-replay.sqlite"
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        forecast, exclusions, training_additions = forecast_from_export(db, archive, read(vol.INPUT), frozen["official_calendar"])
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM fno_positions WHERE entry_date=? AND source='FNO_PAPER' AND underlying='NIFTY' ORDER BY id",
            (DAY,),
        )]
    factor = strategy.trail_scale((forecast["realized_only_log_forecast"], forecast["implied_log_forecast"]))
    assert len(rows) == 3 and min(row["entry_time"][11:16] for row in rows) < "10:00"
    assert dated_contracts(DAY, *frozen["official_calendar"][DAY])[0] == "2026-11-09"
    paired = compare_held(rows, args.export / f"fno_exit_paths/{DAY}.jsonl", factor)
    fully_closed = all(r["candidate"]["status"] == "CLOSED" for r in paired)
    result = {"day": DAY, "forecast": forecast, "training_exclusions": exclusions,
              "training_additions_after_oct28": training_additions, "trail_scale": factor,
              "pair_gate": "prior native entry and four days to nearest expiry", "paired_held": paired,
              "conditional_candidate_single_net": round(sum(r["candidate"]["net"] for r in paired), 2) if fully_closed else None,
              "baseline_single_net": round(sum(row["pnl"] for row in rows), 2),
              "separate_recorded_spread_net": read(HERE / "round9-nov5.json")["separate_recorded_defined_risk_net"]}
    with (HERE / "round19-nov5-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
