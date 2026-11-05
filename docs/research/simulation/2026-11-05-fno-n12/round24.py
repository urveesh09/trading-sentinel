"""Replay two prespecified combinations through the regular NIFTY account."""

from contextlib import contextmanager
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess

from anatomy import trades
import round1 as r


HERE = Path(__file__).resolve().parent
Y = r.Y
T = r.f.T
ENTRY = "ENTRY_MIX"
CONDITIONED = "CONDITIONED_MIX"
FORECASTS = HERE / "round18-forecasts.json"

# Frozen rounds install their own replay wrappers at import. Retain the rule
# functions and restore the base dispatch before installing this study's scope.
BASE_ENTRY, BASE_ROUTE, BASE_MANAGE = Y.BookReplay._entry, Y.BookReplay.route, Y.BookReplay._manage
BASE_PLANNER = T._planner
try:
    import round2 as recovery
    import round3 as fallback
    import round5 as invalidation
finally:
    Y.BookReplay._entry, Y.BookReplay.route, Y.BookReplay._manage = BASE_ENTRY, BASE_ROUTE, BASE_MANAGE
    T._planner = BASE_PLANNER


@contextmanager
def component(model, mode):
    assert "n12" not in model, "overlapping research dispatch scopes"
    model["n12"] = mode
    try:
        yield
    finally:
        del model["n12"]


@lru_cache(maxsize=1)
def forecasts():
    return json.loads(FORECASTS.read_bytes())


def forecast_supports_invalidation(row):
    if row is None:
        return False
    realized, implied = row
    return math.isfinite(realized) and math.isfinite(implied) and implied - realized <= 2 * math.log(.90)


def planner(sig, snap, regime, now, state):
    engine = T.ENGINE["now"]
    if engine is None or not engine.book.get("n12_mix"):
        return BASE_PLANNER(sig, snap, regime, now, state)
    with component(engine.book, "CHAIN_FALLBACK"):
        return fallback.planner(sig, snap, regime, now, state)


@contextmanager
def mix_dispatch():
    assert T._planner is BASE_PLANNER
    T._planner = planner
    try:
        yield
    finally:
        T._planner = BASE_PLANNER


class MixReplay(Y.BookReplay):
    def route(self, frame, regime, now):
        with component(self.book, "RECOVERY"):
            return recovery.route(self, frame, regime, now)

    def _manage(self, book, obs, now):
        if (self.book["n12_mix"] == CONDITIONED and book.open
                and forecast_supports_invalidation(forecasts().get(now.date().isoformat()))):
            with component(self.book, "INVALIDATED"):
                return invalidation.manage(self, book, obs, now)
        return super()._manage(book, obs, now)


def books():
    base = r.books()["N11T"]
    del base["n11"]["stand"]
    return {name: {**copy.deepcopy(base), "label": f"N12|{name}", "n12_mix": name}
            for name in (ENTRY, CONDITIONED)}


def text_hash(name):
    return hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest()


def main():
    spec = HERE / "round24-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["source"].items():
        assert text_hash(name) == sha, name
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
    results = {}
    with mix_dispatch():
        for name, model in books().items():
            with Y.ROUTER.dispatch():
                engine = MixReplay(Y.dataset("year"), model, Y.table("year"), "year")
                results[name] = engine.run(*r.WINDOW)
            for row in results[name]["trades"]:
                row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(raw) for name, raw in {**controls, **results}.items()}
    out["candidate_trades"] = {name: raw["trades"] for name, raw in results.items()}
    with (HERE / f"round24-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    for name in results:
        row = out[name]
        print(r.YEAR, name, row["net"], row["unresolved"],
              {k: v for k, v in row["notes"].items() if k.startswith("n12_")}, flush=True)


if __name__ == "__main__":
    main()
