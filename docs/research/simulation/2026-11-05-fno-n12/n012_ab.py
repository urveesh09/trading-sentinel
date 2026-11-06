"""Freeze the trend exit and a size-only prior-volatility candidate."""

from bisect import bisect_left
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import subprocess

from anatomy import trades
import round30 as trend


HERE = Path(__file__).resolve().parent
r, Y = trend.r, trend.Y
OFFICIAL = HERE / "_local/india-vix/india-vol-closes.json"
FORECAST = HERE / "round18-forecasts.json"
A, B = "N012-A", "N012-B"


@lru_cache(maxsize=1)
def input_series():
    closes = json.loads(OFFICIAL.read_bytes())["closes"]
    forecasts = json.loads(FORECAST.read_bytes())
    return closes, sorted(closes), forecasts, sorted(forecasts)


def volatility_flag(day, closes, close_dates, forecasts, forecast_dates):
    cutoff = bisect_left(forecast_dates, day)
    prior = forecast_dates[max(0, cutoff - 250):cutoff]
    if day in forecasts and len(prior) >= 120:
        current = math.exp(forecasts[day][1] / 2.)
        normal = median(math.exp(forecasts[d][1] / 2.) for d in prior)
        return current >= normal, "implied_model"
    at = bisect_left(close_dates, day)
    if at and closes[close_dates[at - 1]]["vix"] is not None:
        current = closes[close_dates[at - 1]]["vix"]
        earlier = [closes[d]["vix"] for d in close_dates[:at - 1] if closes[d]["vix"] is not None]
        if len(earlier) >= 60:
            return current >= median(earlier[-60:]), "prior_vix"
    return None, "native_fallback"


@contextmanager
def entry_volatility(flag):
    if flag is None:
        yield
        return
    native = r.f.L.vol_up
    r.f.L.vol_up = lambda _now: flag
    try:
        yield
    finally:
        r.f.L.vol_up = native


class VolSizedTrendReplay(trend.TrendReplay):
    def _entry(self, book, obs, frame, day, now):
        if getattr(self, "_vol_date", None) != day:
            self._vol_date = day
            self._vol_flag, source = volatility_flag(day, *input_series())
            self.notes[f"n012_b_{source}_sessions"] += 1
        with entry_volatility(self._vol_flag):
            return super()._entry(book, obs, frame, day, now)


def frozen_models():
    base = r.books()["N11T"]
    return {"N11": r.books()["N11"], "N11T": base,
            A: {**deepcopy(base), "label": A}, B: {**deepcopy(base), "label": B}}


def candidate_result(name, model, dataset, table, window):
    engine_class = VolSizedTrendReplay if name == B else trend.TrendReplay if name == A else Y.BookReplay
    with Y.ROUTER.dispatch():
        engine = engine_class(dataset, model, table, "year")
        result = engine.run(*window)
    for row in result["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    return result


def validate_freeze():
    path = HERE / "exam-2022-h1-freeze.json"
    spec = json.loads(path.read_bytes())
    assert spec == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, expected in spec["sources"].items():
        assert hashlib.sha256((r.ROOT / name).read_text(encoding="utf-8").encode()).hexdigest() == expected, name
    for path, expected in ((OFFICIAL, spec["official_closes_sha256"]), (FORECAST, spec["implied_forecasts_sha256"])):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
    assert spec["books"] == json.loads(json.dumps(frozen_models()))
    return spec


def seen():
    spec = validate_freeze()
    r.verify_freeze()
    data = r.DATASETS[r.YEAR]
    manifest = json.loads((data / "manifest.json").read_bytes())
    with (data / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]
    a_file = HERE / f"round30-{r.YEAR}.json"
    assert hashlib.sha256(a_file.read_bytes()).hexdigest() == spec["a_control_sha256"][r.YEAR]
    a = json.loads(a_file.read_bytes())[trend.TREND]
    for name in ("N11", "N11T"):
        assert r.money(r.raw_for(r.books()[name])) == r.money(trades(r.YEAR, name)[1])
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    result = candidate_result(B, frozen_models()[B], Y.dataset("year"), Y.table("year"), r.WINDOW)
    out = {"year": r.YEAR, A: a, B: r.metrics(result)}
    path = HERE / f"n012-b-screen-{r.YEAR}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(r.YEAR, A, out[A]["net"], B, out[B]["net"], out[B]["unresolved"], flush=True)


if __name__ == "__main__":
    seen()
