"""SN02 wallet ledger on N11 entries: grow (owner's +50% per 100% net profit), capped growth, or farm (never grow)."""
import json, sys
import sn02_ext as X

def target_for(mode, steps, wallet):
    if mode == "every2": return 1500 * 1.5 ** (steps // 2)
    if mode == "every3": return 1500 * 1.5 ** (steps // 3)
    return 1500.0

def play(v, growth_cap, tmode, stress, years=X.YEARS):
    W, steps, prog, total, refill = 15000.0, 0, 0.0, 0.0, 0.0
    days, step_days, halves = [], [], {}
    cum = peak = dd = 0.0
    for y in years:
        Y = X.Year(y)
        for S in Y.ordered():
            T = target_for(tmode, steps, W) if v["exit"] != "n11" else 1e12
            r = X.play_day(S, Y.sigs.get(S.day, []), v, W, T, 0.20 * W, stress)
            n = r["net"]; total += n; cum += n; peak = max(peak, cum); dd = max(dd, peak - cum)
            if n < 0: refill -= n
            h = S.day[:4] + ("-H1" if S.day[5:7] <= "06" else "-H2")
            halves[h] = halves.get(h, 0.0) + n
            prog += n
            while prog >= W and steps < growth_cap:
                prog -= W; W *= 1.5; steps += 1
                step_days.append((S.day, round(W)))
            days.append(n)
    return {"total": round(total), "refilled": round(refill), "steps": steps, "final_wallet": round(W),
            "step_days": step_days, "green": sum(1 for d in days if d > 0), "red": sum(1 for d in days if d < 0),
            "no_trade": sum(1 for d in days if d == 0), "worst_day": round(min(days)), "best_day": round(max(days)),
            "max_fall": round(dd), "halves": {k: round(v) for k, v in halves.items()}}

if __name__ == "__main__":
    out = {}
    base = {"exit": "n11", "give": 0.0, "cash": 1.0, "otm_fallback": True}
    cases = {
        "farm 1 lot (never grow)": ({**base, "max_lots": 1}, 0, "flat"),
        "grow, lots follow the wallet": ({**base, "max_lots": 50}, 99, "flat"),
        "grow at most 1 step, then farm": ({**base, "max_lots": 50}, 1, "flat"),
        "grow at most 2 steps, then farm": ({**base, "max_lots": 50}, 2, "flat"),
        "owner rule: lock 1.0, every2": ({**base, "exit": "lock", "give": 1.0, "max_lots": 50}, 99, "every2"),
        "owner rule: lock 1.0, every3": ({**base, "exit": "lock", "give": 1.0, "max_lots": 50}, 99, "every3"),
        "owner rule: sell at target, every2": ({**base, "exit": "sell", "max_lots": 50}, 99, "every2"),
    }
    for name, (v, cap, tm) in cases.items():
        for s in (0.0, 100.0, 205.0):
            r = play(v, cap, tm, s)
            out[f"{name} | +{int(s)}"] = r
            print(f"{name:36s} +{int(s):<3} total {r['total']:>8} steps {r['steps']} wallet {r['final_wallet']:>7} green/red/none {r['green']}/{r['red']}/{r['no_trade']} worst {r['worst_day']} fall {r['max_fall']} refilled {r['refilled']}", flush=True)
    print("halves farm +205:", out["farm 1 lot (never grow) | +205"]["halves"])
    print("halves grow +205:", out["grow, lots follow the wallet | +205"]["halves"], out["grow, lots follow the wallet | +205"]["step_days"])
    (X.HERE / "_local" / "ledger.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
