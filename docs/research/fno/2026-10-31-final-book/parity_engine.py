"""O31d - the engine's entry_stretch against the research's stretch_at, on the sealed data. Research only.

Two proofs: every bar from 09:45 of every session, in both directions, reads the same; and the candidate book's stored
replay reproduces trade for trade when the replay reads the engine's function instead of the research's.

    python ../run_slice.py --env O30C_YEAR=2026 -- <folder>/parity_engine.py      # the same with O30C_YEAR=2025, O30F_YEAR=2024
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_o2 as X  # noqa: E402

import fno_book  # noqa: E402
from fno_models import FnoDirection  # noqa: E402

S, Y, C, L, O27F = X.S, X.Y, X.C, X.L, X.O27F
research = S.stretch_at


def engine(frame, now, direction: str):
    return fno_book.entry_stretch(frame, now, FnoDirection(direction))


def bars_compared() -> dict:
    data = Y.dataset("year")
    compared = different = none_both = 0
    worst = []
    for day in [d for d in data.days if C.WINDOW[0] <= d <= C.WINDOW[1]]:
        session = date.fromisoformat(day)
        observations = data.observations(day)[0]
        if not observations:
            continue
        frame = data.futures_frame(observations[0].future.contract.token, session)
        for minutes in range(9 * 60 + 45, 15 * 60 + 15, 5):
            now = Y.replay.IST.localize(datetime.combine(session, datetime.min.time()) + timedelta(minutes=minutes, seconds=59))
            for direction in ("LONG", "SHORT"):
                a, b = research(frame, now, direction), engine(frame, now, direction)
                compared += 1
                none_both += a is None and b is None
                if a != b:
                    different += 1
                    worst.append((day, minutes, direction, a, b))
    return {"compared": compared, "different": different, "both_none": none_both, "first_differences": worst[:5]}


def main() -> None:
    O27F.deny_network()
    Y.speedups()
    C.table("year")
    Y._worker_init()
    bars = bars_compared()
    print("bars", bars, flush=True)
    S.stretch_at = engine
    Y.EVALS = X.LOCAL / "parity"
    book = X.X.books()["ADX|30"]
    _key, again = Y.evaluate((book, "year", C.WINDOW))
    keys = json.loads((X.LOCAL / f"keys-{X.YEAR}.json").read_text(encoding="utf-8"))
    first = json.loads((X.LOCAL / "evals" / f"{keys['ADX|30']}.json").read_text(encoding="utf-8"))["trades"]
    same = json.loads(json.dumps(again)) == first
    print("REPLAY", X.YEAR, "trades", len(first), "identical", same, flush=True)
    L._atomic(X.LOCAL / f"parity-{X.YEAR}.json", {"bars": bars, "trades": len(first), "replay_identical": same})
    print("DONE parity", X.YEAR, flush=True)


if __name__ == "__main__":
    main()
