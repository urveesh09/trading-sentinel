"""Grid expansion, specs, rules and per-session builders for EN96-EN110 (IMPL9.md sections 3-4).

A Spec describes one configuration completely; build() turns it into t.sig9/t.meta9 arrays for one session using only
prepare9's causal features. Every cell, control and reference has a stable ID; nothing is created after scoring.
"""
from dataclasses import dataclass, replace, asdict, field
from pathlib import Path
import itertools, json, math
import numpy as np
import round8  # noqa: F401
import lab8, signals8
from data8 import L7
import signals9 as S9
import lab9

HERE = Path(__file__).resolve().parent
L4 = L7.L4
REF = S9.REF_REP
STD = lambda L: (L, 2, "CURRENT_ATM", "POOLED")
HS, PS = (20, 40), (60, 70, 80, 90)


def skey(rep):
    return "R|" + "|".join(map(str, rep))


def qkey(series, H, p):
    return f"{series}|H{H}|p{p}"


# ------------------------------------------------------------------ causal preparation
def prepare9(book):
    """Per session: E03 directions, information series and thresholds from strictly earlier covered sessions."""
    series_keys = [skey(STD(L)) for L in S9.LOOKBACKS] + [skey((15, w, a, g)) for w in S9.WIDTHS for a in S9.ANCHORS for g in S9.AGGS]
    series_keys = list(dict.fromkeys(series_keys)) + ["LAG1", "SYN", "BASIS"]
    hist = {k: S9.Threshold(40, 80) for k in series_keys}; receipts = []
    for t in book:
        t.sig9, t.meta9, t.logs9 = {}, {}, {}
        t.e03 = S9.e03_dirs(t, L7.E03_ENV)
        t.e032 = S9.e03_dirs(t, L7.E032)
        t.e03x = {e: S9.e03_dirs(t, replace(L7.E03_ENV, efficiency=e)) for e in (.5, .6)}
        t.e03x[.7] = t.e03
        oi_ok = bool(t.oi_source8["available"])
        S = {}
        for k in series_keys:
            if k.startswith("R|"):
                L, w, a, g = k.split("|")[1:]
                rep = (int(L), int(w), a, g)
                S[k] = S9.rep_series(t, rep) if oi_ok else np.full(t.n, np.nan)
        S["LAG1"] = np.r_[np.nan, S[skey(REF)][:-1]]
        S["SYN"] = S9.syn_score(t); S["BASIS"] = S9.basis_innovation(t)
        t.S9 = S
        t.q9 = {}
        for k in series_keys:
            h = hist[k]
            for H in HS:
                for p in PS:
                    if len(h.hist) < H:
                        t.q9[qkey(k, H, p)] = math.nan; continue
                    x = np.concatenate(h.hist[-H:]); x = x[np.isfinite(x)]
                    t.q9[qkey(k, H, p)] = float(np.percentile(np.abs(x), p)) if len(x) >= 200 else math.nan
        t.q9["REF"] = t.q9[qkey(skey(REF), 20, 80)]
        covered = {k: hist[k].update(t, S[k]) for k in series_keys}
        receipts.append(dict(day=t.day, covered={k: bool(v) for k, v in covered.items() if k in (skey(REF), "SYN", "BASIS")},
                             q_ref=None if not np.isfinite(t.q9["REF"]) else t.q9["REF"]))
    return receipts


# ------------------------------------------------------------------ specs
@dataclass(frozen=True)
class Spec:
    base: str = "E03_ENV"                  # E03_ENV | E032 | EN55
    kw: tuple = ()                         # rule field replacements
    signal: str = "GATE"                   # GATE VETO TILT SIGN LAG1 NONE SOURCES GRADED DELAYED EN104
    rep: tuple = REF
    H: int = 20
    p: int = 80
    eff: float = .7
    sources: str = ""
    grade: tuple = ()
    context: tuple = ()                    # (maxX or None, minER)
    rev_context: float = 0.
    entry: tuple = ()                      # (style, ttl, amount, ceil)
    delay_ctl: int = 0
    delayed: tuple = ()                    # EN104 (ttl, validity, p_delay, unconditional)
    chooser: tuple = ()                    # (name, fric, admit)
    one_lot: bool = False
    mgmt: tuple = ()                       # ('EXT',cap,perm,act) ('DMG',k,n,mode) ('RND',cap,p) ('HOLD',h)
    size: tuple = ()                       # (frac, gain, oiadd) or ('CONS',)
    lab8_arm: str = ""                     # archived round-8 arm used as-is (references/controls)

    def needs_oi(self):
        if self.lab8_arm:
            return self.lab8_arm not in ("E03_env", "E032_native", "EN55_native")
        if self.signal == "NONE":
            return False
        if self.signal == "SOURCES":
            return "OI" in self.sources
        return True


@dataclass
class Config:
    id: str
    family: str
    block: str
    kind: str                             # CELL CONTROL REFERENCE DIAGNOSTIC
    settings: dict
    spec: Spec
    note: str = ""
    genes: int = 0

    def rule(self):
        return rule_of(self.spec, self.id)


def base_rule(s):
    if s.lab8_arm:
        return lab9.R9(lab8.ARMS[s.lab8_arm])
    r = {"E03_ENV": L7.E03_ENV, "E032": L7.E032, "EN55": L7.EN55}[s.base]
    return lab9.R9(r)


def rule_of(s, key):
    r = base_rule(s)
    if s.lab8_arm:
        return replace(r, max_lots=1) if s.one_lot else r
    kw = dict(s.kw)
    if kw.pop("money", None) == "NATIVE":
        kw.update(slots=2, day_budget=0., max_intents=0, max_parents=0, room_mode="")
    r = replace(r, sig9=key, rep9=s.rep, qkey9=qkey(skey(s.rep), s.H, s.p) if s.rep != REF or (s.H, s.p) != (20, 80) else "REF", **kw)
    if s.chooser:
        name, fric, admit = s.chooser
        r = replace(r, chooser9=name, fric9=float(fric or 0.), admit9=bool(admit))
    if s.one_lot:
        r = replace(r, max_lots=1)
    if s.mgmt:
        m = s.mgmt
        if m[0] == "EXT":
            r = replace(r, ext9=m[2], extcap9=int(m[1]), extact9=float(m[3]))
        elif m[0] == "DMG":
            r = replace(r, dmg9=m[3], dmgk9=float(m[1]), dmgn9=int(m[2]))
        elif m[0] == "RND":
            r = replace(r, rndext9=float(m[2]), extcap9=int(m[1]), seed9=20261118)
        elif m[0] == "HOLD":
            r = replace(r, hold=int(m[1]))
    if s.size:
        if s.size[0] == "CONS":
            r = replace(r, stage9=-1.)
        else:
            r = replace(r, stage9=float(s.size[0]), gain9=float(s.size[1]), oiadd9=s.size[2])
    return r


# ------------------------------------------------------------------ per-session builder
def _q(t, s, series=None):
    return t.q9[qkey(series or skey(s.rep), s.H, s.p)] if (series or s.rep != REF or (s.H, s.p) != (20, 80)) else t.q9["REF"]


def build(t, s, key, rule):
    """Fill t.sig9[key], t.meta9[key], t.logs9[key] for one session."""
    if s.lab8_arm:
        return
    end = rule.end; win = S9.window(t, end)
    edirs = t.e032 if s.base in ("E032", "EN55") or (end == 900) else t.e03x[s.eff]
    if end == 900 and s.base == "E03_ENV":
        edirs = t.e032                                         # E03 signal with the 15:00 window (identical evaluator)
    S = t.S9[skey(s.rep)]; q = _q(t, s); meta = {}; logs = []
    if s.signal == "NONE":
        out = np.where(win, edirs, 0).astype(np.int8)
    elif s.signal in ("GATE", "VETO"):
        out = S9.gate(edirs, S, q, win, s.signal)
    elif s.signal == "SIGN":
        out = S9.gate(edirs, S, 0., win)
    elif s.signal == "LAG1":
        out = S9.gate(edirs, t.S9["LAG1"], t.q9[qkey("LAG1", 20, 80)], win)
    elif s.signal == "TILT":
        out, meta = S9.tilt_caps(edirs, S, q, win)
    elif s.signal == "GRADED":
        out, meta = S9.graded_caps(edirs, S, q, win, *s.grade)
    elif s.signal == "SOURCES":
        out = sources(t, edirs, win, s)
    elif s.signal == "EN104":
        ttl, validity, pd, unc = s.delayed
        out, picks, logs = S9.arms104(t, edirs, S, q, t.q9[qkey(skey(REF), 20, pd)], ttl, validity, L7.E03_ENV, unc)
        meta = {i: dict(pick=v) for i, v in picks.items()}
    else:
        raise ValueError(s.signal)
    if s.context:
        maxX, minER = s.context
        out, clog = S9.context(t, out, maxX, minER); logs.extend(clog)
    if s.rev_context:
        out = S9.reversed_context(t, out, s.rev_context)
    if s.entry:
        style, ttl, amount, ceil = s.entry
        chooser = None
        if s.chooser:
            cr = replace(rule, max_lots=1)
            chooser = lambda sp, tt, i, d, r_, b, c: lab9.contract_pick(sp, tt, i, d, cr, b, c)
        out, picks, alog = S9.arms99(t, out, S, q, style, ttl, amount, ceil, L7.E03_ENV, chooser)
        meta = {i: dict(pick=v) for i, v in picks.items()}; logs.extend(alog)
    if s.delay_ctl:
        out, picks = S9.delayed_control(t, out, s.delay_ctl, L7.E03_ENV)
        meta = {i: dict(pick=v) for i, v in picks.items()}
    t.sig9[key] = out; t.meta9[key] = meta; t.logs9[key] = logs


def sources(t, edirs, win, s):
    out = np.zeros(t.n, np.int8)
    flags = {}
    for name, series in (("OI", skey(REF)), ("SYN", "SYN"), ("BASIS", "BASIS")):
        x = t.S9[series]; q = t.q9[qkey(series, 20, s.p)]
        flags[name] = (x, q)
    for i in np.flatnonzero((edirs != 0) & win):
        d = int(edirs[i]); f = {}
        for name, (x, q) in flags.items():
            f[name] = bool(np.isfinite(x[i]) and np.isfinite(q) and d * x[i] > q)
        c = s.sources
        ok = {"SYN": f["SYN"], "BASIS": f["BASIS"], "OI_OR_SYN": f["OI"] or f["SYN"], "OI_AND_SYN": f["OI"] and f["SYN"],
              "OI_OR_BASIS": f["OI"] or f["BASIS"], "OI_AND_BASIS": f["OI"] and f["BASIS"], "SYN_OR_BASIS": f["SYN"] or f["BASIS"],
              "VOTE2": f["OI"] + f["SYN"] + f["BASIS"] >= 2}[c]
        if ok:
            out[i] = d
    return out


# ------------------------------------------------------------------ registry
def expand(manifest):
    out = []
    for fam in manifest["families"]:
        for b in fam["blocks"]:
            axes = list(b["axes"].items())
            for n, values in enumerate(itertools.product(*[v for _, v in axes]), 1):
                out.append((fam["slot"], b["id"], f"{fam['slot']}:{b['id']}:{n:04d}", dict(zip([k for k, _ in axes], values)), b.get("fidelity", "BAR_LIFECYCLE")))
    return out


def cell_spec(slot, block, st):
    U = lambda x: None if x == "UNBOUNDED" else x
    if slot == "EN96":
        return Spec(rep=STD(st["lookback_minutes"]), p=st["percentile"], H=st["prior_covered_expiries"])
    if slot == "EN97":
        return Spec(rep=(15, st["half_width"], st["anchor"], "POOLED" if st["aggregation"] == "POOLED" else "MEDIAN_LEAVE_ONE_PAIR_OUT"))
    if slot == "EN98":
        return Spec(context=(U(st["max_signed_atr_extension"]), float(st["min_er10"])))
    if slot == "EN99":
        if block == "immediate":
            return Spec()
        if block == "confirm":
            return Spec(entry=("CONFIRM", st["ttl_minutes"], st["progress_atr"], st["ask_multiple"]))
        if block == "reclaim":
            return Spec(entry=("RECLAIM", st["ttl_minutes"], st["pullback_atr"], st["ask_multiple"]))
        return None                                             # packet block: source-gated
    if slot == "EN100":
        name = {"LEGACY": "LEGACY", "NEAREST_ATM_AFFORDABLE": "NEAREST", "MIN_FRICTION_OVER_RESERVE": "MINFRIC"}[st["chooser"]]
        return Spec(chooser=(name, U(st["max_friction_ratio"]) or 0., True), one_lot=True)
    if slot == "EN101":
        return Spec(mgmt=("EXT", st["absolute_hold_minutes"], st["permission"], st["activation_net_over_reserve"]))
    if slot == "EN102":
        return Spec(mgmt=("DMG", st["opposing_oi_threshold_k"], st["consecutive_observations"],
                          {"NONE": "NONE", "ENTRY_DAMAGE": "ENTRY", "STRUCTURE_DAMAGE": "STRUCTURE"}[st["price_damage"]]))
    if slot == "EN103":
        if block == "full":
            return Spec()
        frac = {"ONE_THIRD": 1 / 3, "ONE_HALF": .5}[st["initial_fraction"]]
        return Spec(size=(frac, st["bid_gain"], st["oi_permission"]))
    if slot == "EN104":
        return Spec(signal="EN104", delayed=(st["ttl_minutes"], st["direction_validity"], st["delayed_oi_percentile"], False))
    if slot == "EN105":
        g = tuple(int(st[k]) for k in ("signal_gene", "context_gene", "entry_gene", "contract_gene", "management_gene", "size_gene"))
        return Spec(signal="GENOTYPE", kw=(("genes", g),))
    if slot == "EN106":
        if block == "native":
            return Spec(base="E032", signal=st["mode"], p=st["percentile"])
        if block == "bridge":
            return Spec(kw=(("end", st["window_end"]), ("put_mult", float(st["put_mult"])), ("money", st["money"])))
        return Spec(base="EN55", signal=st["mode"])
    if slot == "EN107":
        return Spec(signal="SOURCES", sources=st["combination"], p=st["percentile"])
    if slot == "EN108":
        return Spec(eff=st["efficiency"], p=st["percentile"], kw=(("premium_high", float(st["premium_high"])), ("efficiency", st["efficiency"])))
    if slot == "EN109":
        return Spec(signal="GRADED", grade=(st["weak_lots"], st["agree_lots"], st["strong_z"]))
    if slot == "EN110":
        return Spec(kw=(("stop", st["stop"]), ("target", st["target"]), ("runner_keep", st["runner_keep"])))
    raise ValueError(slot)


REFERENCES = {
    "REF:E03_env": Spec(lab8_arm="E03_env"), "REF:EN87": Spec(lab8_arm="EN87"), "REF:EN87_ONE_LOT": Spec(lab8_arm="EN87", one_lot=True),
    "REF:E032_native": Spec(lab8_arm="E032_native"), "REF:EN55_native": Spec(lab8_arm="EN55_native"), "REF:EN83": Spec(lab8_arm="EN83"),
    "REF:EN94": Spec(lab8_arm="EN94"), "REF:EN87_unrelated": Spec(lab8_arm="EN87_unrelated_ctl"),
}
FAMILY_REFERENCE = {f: "REF:EN87" for f in ("EN96", "EN97", "EN98", "EN99", "EN101", "EN102", "EN103", "EN104", "EN105", "EN107", "EN108", "EN109", "EN110")}
FAMILY_REFERENCE.update(EN100="REF:EN87_ONE_LOT", EN106="REF:E032_native")


def controls():
    c = [("EN96", "sign_only", Spec(signal="SIGN"), "d*S15 > 0"),
         ("EN96", "no_gate", Spec(lab8_arm="E03_env"), "= matched E03"), ("EN96", "raw_crossings", Spec(lab8_arm="EN83"), "round-8 raw OI crossings"),
         ("EN96", "unrelated_day", Spec(lab8_arm="EN87_unrelated_ctl"), "OI from the 20th prior covered session, same minute"),
         ("EN97", "lag1_oi", Spec(signal="LAG1"), "S15 one minute stale, own threshold")]
    c += [("EN98", f"reversed_ext_{x}", Spec(rev_context=x), "diagnostic: keep only X > x") for x in (.5, 1., 2.)]
    c += [("EN99", f"delay_{k}", Spec(delay_ctl=k), "deterministic delay, no information re-check") for k in (1, 3, 5)]
    c += [("EN100", f"{n.lower()}_unrestricted", Spec(chooser=(n, 0., False), one_lot=True), "EN92-style: no legacy admission") for n in ("NEAREST", "MINFRIC")]
    c += [("EN101", f"fixed_hold_{h}", Spec(mgmt=("HOLD", h)), "fixed time exit") for h in (12, 16, 24)]
    c += [("EN101", f"random_extension_{h}", Spec(mgmt=("RND", h, None)), "equal-activity control: extension probability = mean"
           f" extension rate of the six {h}-minute cells on the first 100 dates (training), no evidence") for h in (12, 16, 24)]
    c += [("EN102", f"damage_only_{m.lower()}_{n}", Spec(mgmt=("DMG", -1., n, m)), "price damage without OI") for m in ("ENTRY", "STRUCTURE") for n in (1, 2, 3)]
    c += [("EN102", "en94_archived", Spec(lab8_arm="EN94"), "round-8 EN94 (raw entries + OI exit)")]
    c += [("EN103", "conservative_full", Spec(size=("CONS",)), "full entry at the staged plan's lot count")]
    c += [("EN104", f"unconditional_{k}", Spec(signal="EN104", delayed=(k, "NONE", 80, True)), "failed-gate E03 events entered at +ttl") for k in (1, 3, 5)]
    c += [("EN106", "en55_native", Spec(lab8_arm="EN55_native"), "EN55 native")]
    c += [("EN108", f"ungated_e{e}_p{ph}", Spec(signal="NONE", eff=e, kw=(("premium_high", float(ph)), ("efficiency", e))), "looser E03 without OI")
          for e in (.5, .6, .7) for ph in (20, 30) if (e, ph) != (.7, 20)]
    return c


def registry():
    auditor = json.loads((HERE / "families9.json").read_text(encoding="utf-8"))
    own = json.loads((HERE / "families9-own.json").read_text(encoding="utf-8"))
    out = []
    for slot, block, cid, st, fid in expand(auditor) + expand(own):
        sp = cell_spec(slot, block, st)
        cfg = Config(cid, slot, block, "CELL", st, sp, "" if sp else "SOURCE_GATED: packet execution needs >=20 synchronized covered expiries")
        if slot == "EN105":
            cfg.genes = sum(dict(sp.kw)["genes"]); cfg.note = "composed per outer fold from training-selected components (search9)"
        out.append(cfg)
    for cid, sp in REFERENCES.items():
        out.append(Config(cid, "REF", "reference", "REFERENCE", {}, sp))
    for fam, name, sp, note in controls():
        out.append(Config(f"{fam}:ctl:{name}", fam, "control", "CONTROL", {}, sp, note))
    ids = [c.id for c in out]
    assert len(ids) == len(set(ids))
    return out


def counts(reg):
    cells = [c for c in reg if c.kind == "CELL"]
    by = {}
    for c in cells:
        by[c.family] = by.get(c.family, 0) + 1
    return dict(cells=len(cells), bar=sum(1 for c in cells if c.spec), packet=sum(1 for c in cells if not c.spec), by_family=by,
                controls=sum(c.kind == "CONTROL" for c in reg), references=sum(c.kind == "REFERENCE" for c in reg))
