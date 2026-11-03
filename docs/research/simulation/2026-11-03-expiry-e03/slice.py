"""Read the ticket surface: Rs per ~Rs 1,000 ticket, fees in, by one reading at a time, per year."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e02"))
import e02_lab as E  # noqa: E402

df = pd.read_csv(HERE / "_local/surface.csv")
lots = np.clip(np.floor(1000 / (df.entry * 65)), 1, 10)
qty = lots * 65
EXITS = ["hold", "t3", "t5", "t10", "hold_s50", "t3_s50", "t5_s50", "t10_s50"]
for x in EXITS:
    sale = df[x] * df.entry
    fees = [E.fee(p, q, True) + (E.fee(s, q, False) if s > 0 else 0) for p, s, q in zip(df.entry, sale, qty)]
    df["rs_" + x] = (sale - df.entry) * qty - np.array(fees)
df["cost"] = df.entry * qty


def show(name, key, exits=("hold", "t5", "t10", "t5_s50", "t10_s50")):
    print(f"\n== {name}")
    g = df.groupby(["year", key], observed=True)
    tab = g.agg(n=("entry", "size"), days=("day", "nunique"), **{x: ("rs_" + x, "mean") for x in exits},
                hit5=("best", lambda b: (b >= 5).mean()))
    print(tab.round(1).to_string())


df["rv60_b"] = pd.cut(df.rv60, [0, .10, .14, .20, 9])
df["ivrv_b"] = pd.cut(df.ivrv, [0, 1.0, 1.5, 2.0, 3.0, 99])
df["eff30_b"] = pd.cut(df.eff30, [-1.01, -.3, 0, .3, .6, 1.01])
df["move13_b"] = pd.cut(df.move13, [-999, -40, 0, 40, 80, 999])
df["min_b"] = pd.cut(df.minute, [779, 810, 840, 870, 900])
df["price_b"] = pd.cut(df.entry, [0, 2, 4, 8, 20])
df["reach_b"] = pd.cut(df.reach, [0, .5, 1, 1.5, 2, 99])
df["atm_iv_b"] = pd.cut(df.atm_iv, [0, .10, .14, .20, 9])
print("all tickets", df.groupby("year").agg(n=("entry", "size"), **{x: ("rs_" + x, "mean") for x in EXITS}).round(1).to_string())
for name, key in (("realized vol 60m", "rv60_b"), ("option IV / RV60", "ivrv_b"), ("ATM IV", "atm_iv_b"),
                  ("trend efficiency 30m, signed to the ticket", "eff30_b"), ("move since 13:00, signed", "move13_b"),
                  ("decision minute", "min_b"), ("entry price", "price_b"), ("reach (dist / ATR sqrt(t))", "reach_b")):
    show(name, key)
