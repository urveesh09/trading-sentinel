"""Builds lab.py for SN52-SN75 from the frozen sn-gold/gold_v4.py (which is never edited)."""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
shutil.copyfile(HERE.parent / "sn-gold" / "gold_v4.py", HERE / "lab.py")
p = HERE / "lab.py"
t = p.read_text(encoding="utf-8")


def rep(old, new):
    global t
    assert t.count(old) == 1, (old[:80], t.count(old))
    t = t.replace(old, new)


rep('"""SN31-SN50 LAB', '"""SN51-SN75 LAB (a copy of the frozen sn-gold/gold_v4.py; v4 itself is never edited).\nSN31-SN50 LAB')
# SN58 day profit lock; SN66 partial fills; SN60 deepest affordable strike
rep('''        if ntr >= v.get("max_trades", 99):
            break''', '''        if ntr >= v.get("max_trades", 99):
            break
        if v.get("day_lock") and realized >= v["day_lock"] * wallet:      # SN58: protect a big day (no new trades)
            break''')
rep('''        lots = size(S, sg, v, full_lots, ctx, vol_day)''', '''        lots = size(S, sg, v, full_lots, ctx, vol_day)
        if v.get("partial") and lots >= 2 and _rng(S.day, i) < v["partial"]:   # SN66: only one lot gets filled
            lots = 1''')
rep('''            depths = range(casc, 0, -1) if casc else [v.get("itm_depth", 1)]''', '''            if v.get("itm_max"):    # SN60: the deepest in-the-money strike (up to itm_max) whose lots fit a budget share
                casc = v["itm_max"]
            depths = range(casc, 0, -1) if casc else [v.get("itm_depth", 1)]''')
rep('''                if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet:''',
    '''                if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet * v.get("itm_share", 1.0):''')
# walk(): SN61 scale-in by index ATR, SN62 pyramid to full, SN63 hybrid trail, SN64 extension end
rep('''    in_px = ask * (1 + v["in_x"]) if v.get("in_x") else None''', '''    in_px = ask * (1 + v["in_x"]) if v.get("in_x") else None
    in_u = (c[i] + d * v["in_atr"] * atr[i]) if v.get("in_atr") else None
    if in_u is not None:
        in_px = None
    ext_end = v.get("ext_end", 355)
    peak_b = ask''')
rep('''        if in_px is not None and tr[j] and bc[j] >= in_px:''', '''        trig = (in_px is not None and tr[j] and bc[j] >= in_px) or (in_u is not None and tr[j] and (c[j] - in_u) * d >= 0)
        if trig and in_u is not None:
            in_u = None
        if trig:''')
rep('''            add_ask = M.ask_of(float(a[3][j]))
            if (open_lots + 1) * add_ask * M.LOT <= wallet:''', '''            add_ask = M.ask_of(float(a[3][j]))
            n_new = max(1, int(wallet // (add_ask * M.LOT)) - open_lots) if v.get("in_full") else 1
            if (open_lots + n_new) * add_ask * M.LOT <= wallet:''')
rep('''                pieces = held + [[add_ask, 1]]''', '''                pieces = held + [[add_ask, n_new]]''')
rep('''                if new_stop < bc[j]:
                    held.append([add_ask, 1])''', '''                if new_stop < bc[j]:
                    held.append([add_ask, n_new])''')
rep('''        if ext:
            if (c[j] - (best_u - d * v["ext_k"] * atr[j])) * d <= 0 or j >= 355:''', '''        if ext:
            peak_b = max(peak_b, bid)
            if v.get("ext_give") and bid <= peak_b - v["ext_give"] * (peak_b - ask):
                px = bid
                break
            if (c[j] - (best_u - d * v["ext_k"] * atr[j])) * d <= 0 or j >= ext_end:''')
rep('''            if v.get("extend") and bid >= ask * (1 + v["ext_x"]) and j < 355:''',
    '''            if v.get("extend") and bid >= ask * (1 + v["ext_x"]) and j < ext_end:''')
rep('''    for j in range(i + 1, M.EXIT_MIN + 1):
        open_lots = sum(p[1] for p in held)''', '''    for j in range(i + 1, max(M.EXIT_MIN, v.get("ext_end", 355)) + 1):
        open_lots = sum(p[1] for p in held)''')
# SN65 slippage as a share of premium
rep('''def cost(entry, exit_, qty, lots):
    return M.charges(entry, exit_, qty) + STRESS * lots''', '''STRESS_PCT = 0.0      # SN65: slippage as a share of premium per side (on top of STRESS per lot)


def cost(entry, exit_, qty, lots):
    return M.charges(entry, exit_, qty) + STRESS * lots + STRESS_PCT * (entry + exit_) * qty


def _rng(day, i):
    import hashlib
    return int(hashlib.sha256(f"{day}|{i}".encode()).hexdigest()[:8], 16) / 2 ** 32''')
# sizing: SN53 OI agreement, SN54 puts, SN55 ADX, SN59 equity curve
rep('''    if rule == "vol_puts":''', '''    if rule == "oi":        # SN53: option writers' flow at entry agrees with the trade (SN09 OI cache)
        return full if (vol_day and oi_agree(S, sg, v)) else small
    if rule == "oi_or_vol":
        return full if (vol_day or oi_agree(S, sg, v)) else small
    if rule == "puts_full":
        return full if (sg["opt"] == "PE" or vol_day) else small
    if rule in ("adx_hi", "adx_lo"):
        rd = ADX.get(S.day)
        hi = rd is not None and rd["adx"] >= v.get("adx", 30)
        return full if (vol_day and (hi if rule == "adx_hi" else not hi)) else small
    if rule == "equity":    # SN59: the book's own last N trading days net positive
        recent = ctx.day_nets[-v.get("eq_n", 20):]
        return full if (vol_day and sum(recent) > 0) else small
    if rule == "vol_puts":''')
rep('''class Ctx:
    """Causal per-run state shared across days (for adaptive sizing)."""

    def __init__(self):''', '''OI = {}
ADX = {}


def oi_agree(S, sg, v):
    oi = OI.get(S.day)
    if not oi:
        return False
    k, w, thr = v.get("oi_k", 15), v.get("oi_w", 150), v.get("oi_thr", 0.0)
    i = sg["i"]
    if i < k:
        return False
    p = S.F["c"][i]
    near = sorted({s for s, _ in oi if abs(s - p) <= w})

    def tot(opt, at):
        return sum(float(oi[(s, opt)][at]) for s in near if (s, opt) in oi)
    d_pe, d_ce = tot("PE", i) - tot("PE", i - k), tot("CE", i) - tot("CE", i - k)
    base = tot("PE", i - k) + tot("CE", i - k)
    flow = (d_pe - d_ce) / base if base > 0 else 0.0
    return flow * (1 if sg["opt"] == "CE" else -1) >= thr


class Ctx:
    """Causal per-run state shared across days (for adaptive sizing)."""

    def __init__(self):
        self.day_nets = []''')
# run(): streams, day nets, floating account (SN52), start date (SN68)
rep('''                x = play_day(S, n11.get(S.day, []), v, W, full, ctx, vday)''', '''                if v.get("from_day") and S.day < v["from_day"]:
                    continue
                if kind == "float":
                    full = int(W // 15000)
                    if full == 0:
                        ctx.day_nets.append(0.0)
                        per[y]["none"] += 1
                        continue
                x = play_day(S, sig_of(Y, S.day, v), v, W, full, ctx, vday)
                ctx.day_nets.append(x)''')
rep('''                if kind == "grow":''', '''                if kind == "float":
                    W += x
                    W_end[0] = W
                if kind == "grow":''')
rep('''        ctx = Ctx()
        W, steps, prog = W0, 0, 0.0''', '''        ctx = Ctx()
        W, steps, prog = W0, 0, 0.0
        W_end = [W0]''')
rep('''        out[name] = {y: {k: round(val) for k, val in per[y].items()} for y in YEARS}''', '''        out[name] = {y: {k: round(val) for k, val in per[y].items()} for y in YEARS}
        if kind == "float":
            out[name]["final_equity"] = {"net": round(W_end[0])}''')
rep('''                if kind == "one":
                    full, vday = 1, False''', '''                if kind == "one":
                    full, vday = 1, False
                elif kind == "float":
                    full, vday = 1, vday_of(S.day, v)''')
rep('''def run(years, vol, v) -> dict:''', '''def sig_of(Y, day, v):
    books = v.get("books", ("N11",))
    if tuple(books) == ("N11",):
        return Y.sigs("N11").get(day, [])
    seen, out = set(), []
    for b in books:
        for s in Y.sigs(b).get(day, []):
            if s["sig_key"] not in seen:
                seen.add(s["sig_key"])
                out.append(s)
    return out


def run(years, vol, v) -> dict:''')
rep('''            n11 = Y.sigs("N11")
            for S in Y.ordered():
                if kind == "one":''', '''            for S in Y.ordered():
                if kind == "one":''')
# the summary line shows won / refilled / net at the end
rep('''def line(name, r) -> str:''', '''def line(name, r) -> str:
    def net(w):
        return sum(r[w][y]["net"] for y in YEARS)
    return f"{name:46s} " + " ".join(f"{w.split()[0]} {net(w):>8}" for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5"))


def _old_line(name, r) -> str:''')
p.write_text(t, encoding="utf-8")
print("lab built")
