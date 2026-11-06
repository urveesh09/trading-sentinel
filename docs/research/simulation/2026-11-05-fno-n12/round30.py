"""Compose the frozen trend-aware exit and earlier entry mix in one wallet."""

from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from anatomy import trades
import round24 as mix
from regular_rules import Trend, trend_params


HERE = Path(__file__).resolve().parent
r, Y = mix.r, mix.Y
TREND, COMBINED = "TREND_ONLY", "TREND_ENTRY_MIX"


@contextmanager
def trend_dispatch():
    previous = r.exits.evaluate_single_leg_exit

    def evaluate(position, *, params, **kwargs):
        chosen = trend_params(params, position, getattr(position, "round30_status", "UNKNOWN"))
        return previous(position, params=chosen, **kwargs)

    r.exits.evaluate_single_leg_exit = evaluate
    try:
        yield
    finally:
        r.exits.evaluate_single_leg_exit = previous


class TrendReplay(Y.BookReplay):
    def _manage(self, book, obs, now):
        for leg in book.open.values():
            if not hasattr(leg, "round30_trend"):
                leg.round30_trend = Trend()
            leg.round30_status = leg.round30_trend.update(now, obs.future.ltp, leg.direction)
        with trend_dispatch():
            return super()._manage(book, obs, now)


class TrendEntryReplay(TrendReplay, mix.MixReplay):
    pass


def books():
    trend = copy.deepcopy(r.books()["N11T"])
    combo = mix.books()[mix.ENTRY]
    trend["label"] = f"N12|{TREND}"
    combo["label"] = f"N12|{COMBINED}"
    return {TREND: trend, COMBINED: combo}


def verify_prior_trend(result):
    if r.YEAR == "2022":
        return
    saved = json.loads((r.PREV / f"regular-annual-{r.YEAR}.json").read_bytes())["TREND"]
    for key in ("net", "closed", "unresolved", "closed_drawdown", "worst_day", "daily"):
        assert result[key] == saved[key], (r.YEAR, key, result[key], saved[key])


def main():
    freeze = HERE / "round30-freeze.json"
    cfg = json.loads(freeze.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{freeze.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, expected in cfg["source"].items():
        assert hashlib.sha256((r.ROOT / name).read_text(encoding="utf-8").encode()).hexdigest() == expected
    assert cfg["books"] == json.loads(json.dumps(books()))
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    out = {name: r.metrics(raw) for name, raw in controls.items()}
    with mix.mix_dispatch():
        for name, model in books().items():
            engine_type = TrendReplay if name == TREND else TrendEntryReplay
            with Y.ROUTER.dispatch():
                engine = engine_type(Y.dataset("year"), model, Y.table("year"), "year")
                raw = engine.run(*r.WINDOW)
            for row in raw["trades"]:
                row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
            out[name] = r.metrics(raw)
            if name == TREND:
                verify_prior_trend(out[name])
            print(r.YEAR, name, out[name]["net"], out[name]["closed"], out[name]["unresolved"], flush=True)
    with (HERE / f"round30-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
