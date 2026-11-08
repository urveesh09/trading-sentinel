"""Pre-filter parity: the full shipped evaluator on every prefix of random ticker-days accepts exactly what lab finds."""
import random, sys
import pandas as pd
import lab, lab_data
from engine import evaluate_momentum_signal
from models import Regime

if __name__ == "__main__":
    data = lab_data.load_dev()
    shipped = pd.read_pickle(lab_data.LOCAL / "dev_shipped.pkl")
    keys = sorted(k for k in data["bars"] if k[0] != lab.INDEX)
    rng = random.Random(20261108)
    sample = rng.sample(keys, 600) + sorted({(r.ticker, r.day) for r in shipped.itertuples()})[:60]
    mismatch = 0
    for ticker, day in sample:
        bars, prior = data["bars"][(ticker, day)], lab.prior_daily(data, ticker, day)
        full = set()
        if prior is not None:
            for i in range(4, len(bars) + 1):
                lunch = "11:30" <= bars.index[i - 1].strftime("%H:%M") <= "13:15"
                fired, _ = evaluate_momentum_signal(ticker, bars.iloc[:i], float(prior["high"].iloc[-1]), lab.POOL,
                                                    lab.POOL, 4, prior, 1.75 if lunch else 1.5, "BULL",
                                                    Regime.REGIME_2_ELEVATED)
                if fired:
                    full.add(i - 1)
        fast = set(shipped[(shipped.ticker == ticker) & (shipped.day == day)]["bar"])
        mismatch += full != fast
    print("ticker-days", len(sample), "mismatches", mismatch)
