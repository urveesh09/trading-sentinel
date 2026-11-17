"""SN458: one fair zero-shot test of a pretrained market model, Kronos-small (PLAN.md section 1, frozen at 83e1b444; details
fixed here before any number). Run with the research venv (C:\\Users\\Urveesh\\sentinel-ml-venv), python -I.

  sn458.py draw    resumable: the Kronos draws for every test date into _local/sn458_draws.json (no scoring)
  sn458.py score   once: every arm and metric into results-sn458.json

Pins: Kronos code 67b630e6 (C:\\Users\\Urveesh\\sentinel-ml-models\\Kronos), checkpoints NeoQuasar/Kronos-small rev 901c26c1 and
NeoQuasar/Kronos-Tokenizer-base rev 0e011738 (model.safetensors sha256 asserted from hf_pins.json); torch 2.5.1+cpu, 4 threads.
Bars: five-minute bars of the test day's near future (feat456's rule), bar k = 1-minute indexes 5k..5k+4 (09:15-15:30, 75 a
session); a bar needs all five 1-minute bars (else the date is excluded). Context: the 480 bars ending with today's bar 8
(09:55-10:00), on the same contract. Columns open/high/low/close/volume/amount (amount = volume x mean OHLC, Kronos's proxy);
timestamps = bar starts.
Kronos: Kronos's predict() normalisation (per-column mean/std over the context, clip 5), then auto_regressive_inference copied
with the final average removed (draws kept); sample_count 8, T 1.0, top_p 0.9, top_k 0, pred_len 6; torch.manual_seed(458000 +
the date's ordinal). r_K = mean over draws of ln(pred close at step 6 / the last context close); P_K = share of draws with
|ln ret| >= theta.
Target r = ln(F74 / F44) (1-minute closes, exact bars); theta = 13 / F44. Test dates 2024-07-01 .. 2026-10-28.
RIDGE: alpha 10 on training-standardised [last 1 / 3 / 6 / 12 bar log returns, today's open -> 10:00, gap (today's open vs the
contract's previous last close), the context's 5-minute return SD]; trained on eligible dates 2019-07-01 .. 2024-06-28, refit
every 60 test dates on all earlier eligible dates. VOL: sigma = SD of the previous 60 eligible dates' r; P = P(|N(0, s^2)| >=
theta); RIDGE's event probability P(|N(r_R, s^2)| >= theta).
Metrics (paired by date; 2,000 circular block-bootstrap resamples, block 20, seed 458; 90% CIs of the differences):
MAE (primary), MSE, Brier, sign hit, correlation. Value iff MAE(K) < MAE(ZERO) and < MAE(RIDGE) and Brier(K) < Brier(VOL), each
difference's 90% CI wholly favourable; else STOP.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOC = HERE / "_local"
DRAWS = LOC / "sn458_draws.json"
OUT = HERE / "results-sn458.json"
MODELS = Path(r"C:\Users\Urveesh\sentinel-ml-models")
FUT_SHA = "d61db7570c1ce4337411c8269c9afd57749faca1cc19159907c874d3d0d24845"
T0, T1, TR0 = "2024-07-01", "2026-10-28", "2019-07-01"
CTX, NS = 480, 8


def load():
    p = LOC / "fut.npz"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == FUT_SHA
    z = np.load(p)
    days, exps, a = [str(x) for x in z["days"]], z["expiries"], z["ohlcv"]
    slot = {(d, str(exps[t, b])): (t, b) for t, d in enumerate(days) for b in range(exps.shape[1]) if exps[t, b]}
    return days, exps, a, slot


def near(t, d, exps, a):
    best = None
    for b in range(exps.shape[1]):
        e = str(exps[t, b])
        if e and e >= d and np.sum(~np.isnan(a[t, b, :, 3])) >= 300:
            if best is None or e < best[0]:
                best = (e, b)
    return best


def bars5(m, upto):
    """five-minute bars from a (390, 5) minute array, bars 0..upto-1; None if any minute is missing."""
    out = []
    for k in range(upto):
        w = m[5 * k:5 * k + 5]
        if np.isnan(w[:, :4]).any():
            return None
        out.append([w[0, 0], w[:, 1].max(), w[:, 2].min(), w[-1, 3], np.nansum(w[:, 4])])
    return out


def window(t, days, exps, a, slot):
    """(context bars (480, 5), bar start datetimes, r, theta, extras) or (None, reason)."""
    d = days[t]
    nb = near(t, d, exps, a)
    if nb is None:
        return None, "no_near"
    e, b = nb
    today = a[t, b]
    f44, f74 = today[44, 3], today[74, 3]
    if np.isnan(f44) or np.isnan(f74):
        return None, "no_target"
    cur = bars5(today, 9)
    if cur is None:
        return None, "today_gap"
    seq, stamps = list(cur), [dt.datetime.fromisoformat(d) + dt.timedelta(hours=9, minutes=15 + 5 * k) for k in range(9)]
    tt = t - 1
    prev_close = None
    while len(seq) < CTX and tt >= 0:
        s = slot.get((days[tt], e))
        if s is None:
            return None, "contract_history"
        bb = bars5(a[s[0], s[1]], 75)
        if bb is None:
            return None, "history_gap"
        if prev_close is None:
            prev_close = bb[-1][3]
        seq = bb + seq
        stamps = [dt.datetime.fromisoformat(days[tt]) + dt.timedelta(hours=9, minutes=15 + 5 * k) for k in range(75)] + stamps
        tt -= 1
    if len(seq) < CTX:
        return None, "short"
    x = np.array(seq[-CTX:], float)
    st = stamps[-CTX:]
    cl = x[:, 3]
    lr = np.diff(np.log(cl))
    feats = [np.log(cl[-1] / cl[-2]), np.log(cl[-1] / cl[-4]), np.log(cl[-1] / cl[-7]), np.log(cl[-1] / cl[-13]),
             np.log(cl[-1] / cur[0][0]), np.log(cur[0][0] / prev_close), float(lr.std())]
    return {"day": d, "x": x, "stamps": st, "r": float(np.log(f74 / f44)), "theta": 13.0 / float(f44), "feats": feats,
            "last": float(cl[-1])}, None


def eligible():
    days, exps, a, slot = load()
    out, why = [], {}
    for t, d in enumerate(days):
        if d < TR0 or d > T1:
            continue
        w, reason = window(t, days, exps, a, slot)
        if w is None:
            why[reason] = why.get(reason, 0) + 1
            continue
        out.append(w)
    return out, why


def kronos():
    import torch
    sys.path.insert(0, str(MODELS / "Kronos"))
    from model import Kronos, KronosTokenizer  # noqa: E402
    from model.kronos import sample_from_logits, calc_time_stamps  # noqa: E402
    pins = json.loads((MODELS / "hf_pins.json").read_text(encoding="utf-8"))
    for rid, sub in (("NeoQuasar/Kronos-small", "Kronos-small"), ("NeoQuasar/Kronos-Tokenizer-base", "Kronos-Tokenizer-base")):
        f = MODELS / "hf" / sub / "model.safetensors"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == pins[rid]["files"]["model.safetensors"], rid
    torch.set_num_threads(4)
    tok = KronosTokenizer.from_pretrained(str(MODELS / "hf" / "Kronos-Tokenizer-base"))
    mod = Kronos.from_pretrained(str(MODELS / "hf" / "Kronos-small"))
    tok.eval()
    mod.eval()
    return torch, tok, mod, sample_from_logits, calc_time_stamps


def draws_for(w, K):
    """Kronos's predict() path with the draws kept (auto_regressive_inference copied; the final mean removed)."""
    import pandas as pd
    torch, tok, mod, sample_from_logits, calc_time_stamps = K
    x = np.column_stack([w["x"], w["x"][:, 4] * w["x"][:, :4].mean(1)]).astype(np.float32)
    ys = [w["stamps"][-1] + dt.timedelta(minutes=5 * (k + 1)) for k in range(6)]
    xst = calc_time_stamps(pd.Series(pd.to_datetime(w["stamps"]))).values.astype(np.float32)
    yst = calc_time_stamps(pd.Series(pd.to_datetime(ys))).values.astype(np.float32)
    mu, sd = x.mean(0), x.std(0)
    xn = np.clip((x - mu) / (sd + 1e-5), -5, 5)
    torch.manual_seed(458000 + dt.date.fromisoformat(w["day"]).toordinal())
    with torch.no_grad():
        X = torch.from_numpy(xn[None]).repeat(NS, 1, 1)
        XS = torch.from_numpy(xst[None]).repeat(NS, 1, 1)
        YS = torch.from_numpy(yst[None]).repeat(NS, 1, 1)
        X = torch.clip(X, -5, 5)
        xt = tok.encode(X, half=True)
        L, P, ctx = X.size(1), 6, 512
        full_stamp = torch.cat([XS, YS], dim=1)
        pre, post = xt[0], xt[1]
        for i in range(P):
            cur = L + i
            s0 = max(0, cur - ctx)
            s1_logits, context = mod.decode_s1(pre[:, s0:cur], post[:, s0:cur], full_stamp[:, s0:cur, :].contiguous())
            sp = sample_from_logits(s1_logits[:, -1, :], temperature=1.0, top_k=0, top_p=0.9, sample_logits=True)
            s2_logits = mod.decode_s2(context, sp)
            so = sample_from_logits(s2_logits[:, -1, :], temperature=1.0, top_k=0, top_p=0.9, sample_logits=True)
            pre = torch.cat([pre, sp], dim=1)
            post = torch.cat([post, so], dim=1)
        s0 = max(0, L + P - ctx)
        z = tok.decode([pre[:, s0:L + P].contiguous(), post[:, s0:L + P].contiguous()], half=True)
    z = z.cpu().numpy()[:, -P:, :] * (sd + 1e-5) + mu
    return [float(np.log(c / w["last"])) for c in z[:, -1, 3]]


def draw():
    ws, why = eligible()
    test = [w for w in ws if w["day"] >= T0]
    got = json.loads(DRAWS.read_text(encoding="utf-8")) if DRAWS.exists() else {}
    K = kronos()
    t0 = time.time()
    for w in test:
        if w["day"] in got:
            continue
        if time.time() - t0 > 520:
            break
        got[w["day"]] = draws_for(w, K)
        DRAWS.write_text(json.dumps(got), encoding="utf-8")
    left = sum(1 for w in test if w["day"] not in got)
    print(f"{len(got)} dates drawn, {left} left; eligible test {len(test)}; excluded {why}", "DONE" if left == 0 else "MORE")


def ridge_fit(X, y, alpha=10.0):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    A = (X - mu) / sd
    ym = y.mean()
    beta = np.linalg.solve(A.T @ A + alpha * np.eye(A.shape[1]), A.T @ (y - ym))
    return lambda Z: ym + ((Z - mu) / sd) @ beta


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def p_event(m, s, th):
    return (1 - phi((th - m) / s)) + phi((-th - m) / s)


def boot_ci(d, seed=458, n=2000, block=20):
    rng = np.random.default_rng(seed)
    m = len(d)
    k = int(np.ceil(m / block))
    idx = ((rng.integers(0, m, (n, k))[:, :, None] + np.arange(block)) % m).reshape(n, -1)[:, :m]
    bm = d[idx].mean(1)
    return [round(float(np.percentile(bm, 5)), 8), round(float(np.percentile(bm, 95)), 8)]


def score():
    if OUT.exists():
        raise SystemExit("SN458 is scored once")
    ws, why = eligible()
    got = json.loads(DRAWS.read_text(encoding="utf-8"))
    train = [w for w in ws if w["day"] < T0]
    test = [w for w in ws if w["day"] >= T0]
    assert all(w["day"] in got for w in test), "draws incomplete"
    allw = train + test
    r_all = np.array([w["r"] for w in allw])
    rows = []
    for k, w in enumerate(test):
        i = len(train) + k
        if k % 60 == 0:
            f = ridge_fit(np.array([v["feats"] for v in allw[:i]]), r_all[:i])
        sig = float(np.std(r_all[i - 60:i], ddof=1))
        dk = np.array(got[w["day"]])
        rr = float(f(np.array([w["feats"]]))[0])
        rows.append({"day": w["day"], "r": w["r"], "th": w["theta"], "K": float(dk.mean()), "PK": float(np.mean(np.abs(dk) >= w["theta"])),
                     "R": rr, "PR": p_event(rr, sig, w["theta"]), "PV": p_event(0.0, sig, w["theta"])})
    r = np.array([x["r"] for x in rows])
    ev = np.array([abs(x["r"]) >= x["th"] for x in rows], float)
    arm = {"K": np.array([x["K"] for x in rows]), "R": np.array([x["R"] for x in rows]), "ZERO": np.zeros(len(rows))}
    pr = {"K": np.array([x["PK"] for x in rows]), "R": np.array([x["PR"] for x in rows]), "VOL": np.array([x["PV"] for x in rows])}
    res = {"test_dates": len(rows), "train_dates": len(train), "excluded": why, "event_rate": round(float(ev.mean()), 4),
           "draws_per_date": NS, "MAE_bp": {k: round(1e4 * float(np.mean(np.abs(r - v))), 3) for k, v in arm.items()},
           "MSE_bp2": {k: round(1e8 * float(np.mean((r - v) ** 2)), 2) for k, v in arm.items()},
           "Brier": {k: round(float(np.mean((v - ev) ** 2)), 5) for k, v in pr.items()},
           "sign_hit": {k: round(float(np.mean(np.sign(v[r != 0]) == np.sign(r[r != 0]))), 4) for k, v in arm.items() if k != "ZERO"},
           "corr": {k: round(float(np.corrcoef(v, r)[0, 1]), 4) for k, v in arm.items() if k != "ZERO"}}
    dm = {}
    for other in ("ZERO", "R"):
        d = np.abs(r - arm["K"]) - np.abs(r - arm[other])
        dm[f"MAE_K_minus_{other}_bp"] = {"mean": round(1e4 * float(d.mean()), 4), "ci90": [round(1e4 * c, 4) for c in boot_ci(d)]}
    for other in ("VOL", "R"):
        d = (pr["K"] - ev) ** 2 - (pr[other] - ev) ** 2
        dm[f"Brier_K_minus_{other}"] = {"mean": round(float(d.mean()), 5), "ci90": [round(c, 5) for c in boot_ci(d)]}
    res["paired"] = dm
    value = dm["MAE_K_minus_ZERO_bp"]["ci90"][1] < 0 and dm["MAE_K_minus_R_bp"]["ci90"][1] < 0 and dm["Brier_K_minus_VOL"]["ci90"][1] < 0
    res["verdict"] = "FORECAST_VALUE (forward comparison only)" if value else "STOP (no forecast value over simple controls)"
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"draw": draw, "score": score}[sys.argv[1]]()
