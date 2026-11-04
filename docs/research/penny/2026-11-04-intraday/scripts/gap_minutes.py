"""How quickly the gap-down recovery happens, on development minutes (seen data).

For stock-days opening <= -2% (official open vs previous close), the mean return from each
entry clock to each exit clock, using the last traded price at/before the clock. If most of the
recovery is between the auction print and the first minutes, only an auction buyer earns it.
"""
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import idata  # noqa: E402

ENTRY = [("open", None), ("09:15c", 555), ("09:16", 556), ("09:17", 557), ("09:20", 560), ("09:30", 570), ("09:45", 585), ("10:00", 600)]
EXIT = [("09:30", 570), ("10:00", 600), ("10:30", 630), ("12:00", 720), ("14:00", 840), ("15:00", 900), ("15:15", 915), ("close", None)]


def px(d, m):
    if m is None:
        return None
    return idata.price_at(d.bars, m)


def main():
    days = [d for d in idata.dev_days() if idata.in_band(d) and d.day_open and d.day_close]
    for lo, hi, name in ((-1.0, -0.02, "gap <= -2%"), (-0.05, -0.02, "-5% < gap <= -2%"), (-1.0, -0.05, "gap <= -5%"), (0.02, 1.0, "gap >= +2%"), (-0.01, 0.01, "flat")):
        sel = [d for d in days if lo < d.day_open / d.prev_close - 1 <= hi]
        print(f"\n{name}: n={len(sel)}  (first bar open == official open in {sum(abs(d.bars[0][1]/d.day_open-1)<0.002 for d in sel)} days, first bar at 09:15 in {sum(d.bars[0][0]==555 for d in sel)})")
        print(f"{'entry':8s}" + "".join(f"{e[0]:>8s}" for e in EXIT))
        for en, em in ENTRY:
            line = f"{en:8s}"
            for xn, xm in EXIT:
                if em is not None and xm is not None and xm <= em:
                    line += f"{'':8s}"
                    continue
                rs = []
                for d in sel:
                    a = d.day_open if en == "open" else px(d, em)
                    b = d.day_close if xn == "close" else px(d, xm)
                    if a and b:
                        rs.append(b / a - 1)
                line += f"{100*statistics.fmean(rs):8.2f}" if rs else f"{'':8s}"
            print(line)


if __name__ == "__main__":
    main()
