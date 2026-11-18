"""Round-10 registry, specs, rules and per-session builders (IMPL10.md sections 4-5).

Every cell, control and reference has a stable ID and an explicit dependency set before any money exists. Fixed families
replace fields of an archived round-8 arm; builder families write t.sig9[key] / t.meta9[key] from causal inputs only.
"""
from dataclasses import dataclass, field, replace
from pathlib import Path
import hashlib, json, math
import numpy as np
import round10  # noqa: F401
import lab8
from data8 import L7
import signals9 as S9
import families9 as F9
import lab10, features10 as FX, hmm10

HERE = Path(__file__).resolve().parent
L3, L4 = L7.L3, L7.L4
REF = S9.REF_REP
NEAR1 = (("chooser9", "NEAREST"), ("max_lots", 1), ("admit9", True))
JOINT = NEAR1 + (("target", 1.5), ("hold", 12))
RANGE_KW = (("chooser9", "NEAREST"), ("max_lots", 1), ("admit9", False), ("underlying_stop", 0.), ("mg10", "EN117"), ("hold", 8))
NATIVE_MONEY = (("slots", 2), ("day_budget", 0.), ("max_intents", 0), ("max_parents", 0), ("room_mode", ""))
ORDER = 23.6
SEED = 20261118


@dataclass(frozen=True)
class Spec10:
    arm: str = ""                 # archived round-8 arm (fixed families)
    kw: tuple = ()                # Rule10 field replacements
    build: str = ""               # per-session builder
    bp: tuple = ()                # builder parameters
    needs: tuple = ()             # typed dependencies ("OI", "OI_OPTIONAL")
    learned: str = ""             # EN118 / EN120: walk-forward policy (learn10)


@dataclass
class Config:
    id: str
    family: str
    block: str
    kind: str                     # CELL CONTROL REFERENCE DYNAMIC
    settings: dict
    spec: Spec10 = None           # None: source-gated
    comparator: tuple = ()        # primary first
    note: str = ""

    def rule(self):
        return rule_of(self.spec, self.id)


def rule_of(s, key):
    if s.arm:
        r = lab10.R10(lab8.ARMS[s.arm])
    else:
        r = lab10.R10(L7.E03_ENV, sig9=key)
    return replace(r, **dict(s.kw)) if s.kw else r


def sensex_ok(spec):
    return spec is not None and "OI" not in spec.needs


# ------------------------------------------------------------------ builders
def en87_dirs(t, end=870):
    return S9.gate(t.e03, t.S9[F9.skey(REF)], t.q9["REF"], S9.window(t, end), "GATE")


def e03w(t, end):
    win = S9.window(t, end); e = t.e032 if end == 900 else t.e03
    return np.where(win, e, 0).astype(np.int8)


def coin(*parts):
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def fresh_state(ev, context, rank_key):
    r = ev.get(rank_key); a = ev.get("accel")
    if context == "EXTENSION_RANK":
        return None if r is None else r <= .5
    if context == "ACCELERATION":
        return a
    return None if r is None or a is None else (r <= .5 and a)


PROFILE112 = {"TARGET_ONLY": (("target", 1.5),), "HOLD_ONLY": (("hold", 12),), "BOTH": (("target", 1.5), ("hold", 12))}


def room112(t, i, context, assignment, rank_key):
    ev = t.ext10.get(int(i))
    f = None if ev is None else fresh_state(ev, context, rank_key)
    if f is None:
        return None
    return f if assignment == "FRESH_GETS_ROOM" else (not f)


def build(t, s, key, rule):
    if s.arm or s.learned:
        return
    b = s.build; meta = {}
    if b == "EN112":
        context, assignment, profile, rank_key = s.bp
        out = en87_dirs(t)
        for i in np.flatnonzero(out):
            g = room112(t, i, context, assignment, rank_key)
            meta[int(i)] = dict(prof10=PROFILE112[profile], tag10="ROOM") if g else dict(tag10="BASE" if g is False else "MISSING")
    elif b == "RND112":
        context, assignment, profile, rank_key, rate = s.bp
        out = en87_dirs(t)
        for i in np.flatnonzero(out):
            g = coin(SEED, "RND112", context, assignment, t.day, int(i), int(out[i])) < rate
            meta[int(i)] = dict(prof10=PROFILE112[profile], tag10="ROOM") if g else dict(tag10="BASE")
    elif b == "EN116":
        K, refit, pers, variant = s.bp
        out = en87_dirs(t); act = state116(t, K, refit, pers, variant)
        t.state10[key] = act
        for i in np.flatnonzero(out):
            if act is None:
                meta[int(i)] = dict(tag10="FALLBACK")
            elif act[i]:
                meta[int(i)] = dict(prof10=JOINT + (("mg10", "EN116"), ("mgp10", (key,))), tag10="ACTIVE")
            else:
                meta[int(i)] = dict(tag10="INACTIVE")
        if act is None:
            t.state10[key] = np.zeros(t.n, bool)
    elif b == "EN117":
        buffer, target, stop_buffer, dirmode = s.bp
        out = np.zeros(t.n, np.int8)
        for ev in t.range10[buffer]:
            i = ev["i"]; d = ev["d"]
            if dirmode == "OPPOSITE":
                d = -d
            elif dirmode == "RANDOM":
                d = 1 if coin(SEED, "DIR117", buffer, t.day, i) < .5 else -1
            out[i] = d
            meta[i] = dict(tag10=dirmode)
            if dirmode == "SAME":
                meta[i]["range10"] = FX.range_levels(ev, target, stop_buffer)
    elif b == "E03W":
        out = e03w(t, s.bp[0])
    elif b == "CALLGATE":
        end = s.bp[0]; e = e03w(t, end); S = t.S9[F9.skey(REF)]; q = t.q9["REF"]; out = e.copy()
        for i in np.flatnonzero(e > 0):
            if not (np.isfinite(q) and np.isfinite(S[i]) and S[i] > q):
                out[i] = 0
    else:
        raise ValueError(b)
    t.sig9[key] = out; t.meta9[key] = meta


def state116(t, K, refit, pers, variant):
    rec = t.hmm10[(K, refit)]
    if rec["fallback"]:
        return None
    win = np.flatnonzero(FX.window(t)); act = np.zeros(t.n, bool)
    if variant == "HMM":
        a = hmm10.activate(rec["pT"], rec["ok"], pers)
    elif variant == "RND":
        a = hmm10.activate(rec["pR"], rec["ok"], pers)
    else:                                                             # ER10 state matched to the training activation rate
        acts, ers = [], []
        for p, ok, er in rec["train"]:
            aa = hmm10.activate(p, ok, pers); acts.append(aa[ok]); ers.append(er[ok & np.isfinite(er)])
        rate = float(np.mean(np.concatenate(acts))) if acts else 0.
        ref = np.concatenate(ers)
        er = rec_er(t)
        if rate <= 0:
            a = np.zeros(len(win), bool)
        else:
            thr = float(np.quantile(ref, 1 - rate)) if rate < 1 else -np.inf
            a = np.isfinite(er) & (er >= thr)
    act[win] = a
    return act


def rec_er(t):
    return t.obs10[FX.window(t)][:, 0]


def prepare10(B, verbose=True):
    """Causal inputs for every builder (no P&L): features10, the four HMM fit sequences, EN117 event lists."""
    out = {}
    for u, book in B.items():
        out[u] = FX.prepare10(book)
        for t in book:
            t.range10 = {}
            fresh = None
            if getattr(t, "und", "NIFTY") == "SENSEX":
                fv = L3.futvol(t); fresh = np.isfinite(fv) & (fv > 0)
            for buf in (0., .25):
                evs = FX.range_events(t, buf)
                if fresh is not None:
                    evs = [e for e in evs if fresh[e["i"]] and fresh[e["i"] - 1]]
                t.range10[buf] = evs
        for t in book:
            t.hmm10 = {}                                          # fresh per preparation (never shared with a copied tape)
        for K in (2, 3):
            for refit in (1, 5):
                recs = hmm10.states116(book, K, refit)
                for t, r in zip(book, recs):
                    t.hmm10[(K, refit)] = r
        if verbose:
            print("prepare10", u, flush=True)
    return out


# ------------------------------------------------------------------ registry
def load_grids():
    auditor = json.loads((HERE / "families10-proposed.json").read_text(encoding="utf-8"))
    own = json.loads((HERE / "families10-own.json").read_text(encoding="utf-8"))
    return auditor["families"] + own["families"]


def cell_spec(slot, st):
    if slot == "EN111":
        kw = (NEAR1 if st["contract"] == "NEARER_ONE_LOT" else ()) + (("target", float(st["target"])), ("hold", int(st["hold"])))
        return Spec10(arm="EN87", kw=kw, needs=("OI",)), ("REF:EN87",)
    if slot == "EN112":
        return Spec10(build="EN112", bp=(st["context"], st["assignment"], st["profile"], "rank40"), needs=("OI",)), ("REF:EN87",)
    if slot == "EN113":
        mode = "DENY" if st["response"] == "DENY_EXTENSION" else "GIVEBACK"
        return Spec10(arm="EN87", kw=(("hold", 12), ("mg10", "EN113"), ("mgp10", (st["lag"], f"L{st['lag']}|p{st['percentile']}", mode, 0))),
                      needs=("OI",)), ("REF:EN87", "EN113:ctl:fixed12")
    if slot == "EN114":
        return Spec10(arm="EN87", kw=(("hold", 999), ("mg10", "EN114"), ("mgp10", (float(st["activity"]), int(st["wall"]), st["scope"]))),
                      needs=("OI",)), ("REF:EN87",)
    if slot == "EN115":
        return Spec10(arm="EN87", kw=(("chooser9", "RESP"), ("max_lots", 1), ("admit9", True),
                                      ("resp10", (int(st["window"]), float(st["ridge"]), float(st["residual_penalty"]), "MODEL"))),
                      needs=("OI",)), ("REF:EN87_ONE_LOT", "REF:EN87", "EN111:0010")
    if slot == "EN116":
        return Spec10(build="EN116", bp=(st["states"], st["refit"], st["persistence"], "HMM"), needs=("OI",)), ("REF:EN87", "EN111:0018")
    if slot == "EN117":
        return Spec10(build="EN117", bp=(float(st["excursion"]), st["target"], float(st["stop_buffer"]), "SAME"),
                      kw=RANGE_KW + (("cov10", float(st["cost_coverage"])),)), ("CASH", "REF:E03_env")
    if slot == "EN118":
        return Spec10(learned="EN118", bp=(st["learner"], st["regularization"], int(st["k"]), "WITH_OI"), needs=("OI",)), ("REF:EN87", "REF:E03_env")
    if slot == "EN119":
        return None, ()
    if slot == "EN120":
        return Spec10(learned="EN120", bp=(int(st["depth"]), int(st["refit"]), float(st["switch_margin"])), needs=("OI",)), ("REF:EN87",)
    if slot == "EN121":
        c = {"LEGACY": (), "NEAREST_ONE_LOT": NEAR1, "NEAREST_SAME_ROOM": (("chooser9", "NEAREST"), ("admit9", True))}[st["contract"]]
        return Spec10(arm=st["book"], kw=c + (("target", float(st["target"])), ("hold", int(st["hold"])))), ("REF:" + st["book"],)
    if slot == "EN122":
        kw = (("end", int(st["window_end"])), ("put_mult", float(st["put_mult"])))
        if st["money"] == "NATIVE":
            kw += NATIVE_MONEY
        if st["geometry"] == "JOINT":
            kw += JOINT
        gate = st["gate"] == "CALLS_ONLY"
        return Spec10(build="CALLGATE" if gate else "E03W", bp=(int(st["window_end"]),), kw=kw, needs=("OI",) if gate else ()), \
            ("REF:E032_native", "REF:E03_env")
    if slot == "EN123":
        kw = NEAR1 + (("target", float(st["target"])), ("stop", float(st["stop"])))
        if st["at_target"] != "SELL_ALL":
            kw += (("solo_runner", True), ("runner_keep", float(st["at_target"].rsplit("_", 1)[1])))
        return Spec10(arm=st["base"], kw=kw, needs=("OI",) if st["base"] == "EN87" else ()), \
            ("REF:EN87" if st["base"] == "EN87" else "REF:E03_env",)
    if slot == "EN124":
        arm, kw = {"EN87": ("EN87", ()), "EN87_JOINT": ("EN87", JOINT), "E03_env_JOINT": ("E03_env", JOINT), "E032_JOINT": ("E032_native", JOINT)}[st["base"]]
        x = st["stress"]
        if x in ("ENTRY_PLUS1", "ALL"):
            kw += (("entry_delay", 1),)
        stress = ()
        if x in ("SELL_PLUS1", "ALL"):
            stress += (("sell_delay", 1),)
        if x in ("FEE_PLUS1ORDER", "ALL"):
            stress += (("extra_fee", ORDER),)
        if stress:
            kw += (("stress10", stress),)
        return Spec10(arm=arm, kw=kw, needs=("OI",) if arm == "EN87" else ()), ()        # comparators filled in registry()
    if slot == "EN125":
        kw = (NEAR1 if st["contract"] == "NEAREST_ONE_LOT" else ()) + (("mg10", "EN125"), ("mgp10", (st["wall"], st["trigger"], st["action"].replace("_0.8", ""))))
        return Spec10(arm="EN87", kw=kw, needs=("OI",)), ("REF:EN87" if st["contract"] == "LEGACY_UP_TO_3" else "EN111:0010", "REF:EN87")
    raise ValueError(slot)


# IMPL10 section 8 / PHASE0-10.md: rank40 was defined for 0 of 38 EN87 minutes (median 7 prior same-direction events), so the
# pre-registered geometry revision adds EN112:r1 cells using rank_all; the literal cells stay registered (NOT IDENTIFIED).
REVISED112 = ("EXTENSION_RANK", "BOTH")

REFERENCES = {"REF:E03_env": Spec10(arm="E03_env"), "REF:EN87": Spec10(arm="EN87", needs=("OI",)),
              "REF:EN87_ONE_LOT": Spec10(arm="EN87", kw=(("max_lots", 1),), needs=("OI",)),
              "REF:E032_native": Spec10(arm="E032_native"), "REF:EN55_native": Spec10(arm="EN55_native")}


def controls():
    c = []
    for tg in (1.0, 1.25, 1.5):
        for h in (8, 10, 12):
            c.append(("EN111", f"equal_one_lot_t{tg}_h{h}", Spec10(arm="EN87", kw=(("max_lots", 1), ("target", tg), ("hold", h)), needs=("OI",)),
                      "legacy contract at one lot: the contract-mechanism companion", ()))
    for tg in (1.0, 1.5):
        for h in (8, 12):
            c.append(("EN111", f"no_partial_t{tg}_h{h}", Spec10(arm="EN87", kw=(("split", False), ("target", tg), ("hold", h)), needs=("OI",)),
                      "target sells every lot (no half-sale, no runner)", ("REF:EN87",)))
    for prof, kw in PROFILE112.items():
        c.append(("EN112", f"fixed_{prof.lower()}", Spec10(arm="EN87", kw=kw, needs=("OI",)), "profile given to every entry", ("REF:EN87",)))
    c.append(("EN113", "fixed12", Spec10(arm="EN87", kw=(("hold", 12),), needs=("OI",)), "fixed 12-minute hold (the family base)", ("REF:EN87",)))
    c.append(("EN113", "price_giveback", Spec10(arm="EN87", kw=(("hold", 12), ("mg10", "EN113"), ("mgp10", (0, "", "PRICE_ONLY", 0))), needs=("OI",)),
              "giveback exit without OI", ("REF:EN87", "EN113:ctl:fixed12")))
    for L in (1, 3, 5):
        for p in (80, 90):
            c.append(("EN113", f"fast_oi_only_L{L}_p{p}", Spec10(arm="EN87", kw=(("hold", 12), ("mg10", "EN113"), ("mgp10", (L, f"L{L}|p{p}", "OI_ONLY", 0))), needs=("OI",)),
                      "exit on confirmed fast deterioration alone", ("REF:EN87", "EN113:ctl:fixed12")))
            for mode in ("DENY", "GIVEBACK"):
                c.append(("EN113", f"stale_{mode.lower()}_L{L}_p{p}", Spec10(arm="EN87", kw=(("hold", 12), ("mg10", "EN113"), ("mgp10", (L, f"L{L}|p{p}", mode, 1))), needs=("OI",)),
                          "source-lag companion: S_L one bar stale", ("REF:EN87", "EN113:ctl:fixed12")))
    for h in (4, 8, 12, 16):
        c.append(("EN114", f"fixed_{h}_base_only", Spec10(arm="EN87", kw=(("hold", h),), needs=("OI",)), "fixed clock, runners native", ("REF:EN87",)))
        c.append(("EN114", f"fixed_{h}_base_and_runner", Spec10(arm="EN87", kw=(("hold", h), ("mg10", "HOLDALL"), ("mgp10", (h,))), needs=("OI",)),
                  "fixed clock also ends runners", ("REF:EN87",)))
    c.append(("EN114", "volratio", Spec10(arm="EN87", kw=(("hold", 999), ("mg10", "VOLRATIO")), needs=("OI",)), "hold = clip(8*sqrt(vref/v0), 4, 16)", ("REF:EN87",)))
    c.append(("EN115", "min_friction_one_lot", Spec10(arm="EN87", kw=(("chooser9", "MINFRIC"), ("max_lots", 1), ("admit9", True)), needs=("OI",)),
              "EN100 min-friction one lot", ("REF:EN87_ONE_LOT",)))
    c.append(("EN115", "equal_reserve_w40_r10", Spec10(arm="EN87", kw=(("chooser9", "RESP"), ("max_lots", 1), ("admit9", True), ("resp10", (40, 10., 0., "EQRES"))),
                                                   needs=("OI",)), "legacy chooser given the response pick's reserve (<= 3 lots)", ("REF:EN87",)))
    for W in (20, 40, 60):
        for lam in (1., 10.):
            for rp in (0., 1.):
                c.append(("EN115", f"constbeta_w{W}_r{int(lam)}_p{int(rp)}", Spec10(arm="EN87", kw=(("chooser9", "RESP"), ("max_lots", 1), ("admit9", True), ("resp10", (W, lam, rp, "CONSTBETA"))),
                                                                                  needs=("OI",)), "beta = candidates' median", ("REF:EN87_ONE_LOT",)))
    for K in (2, 3):
        for refit in (1, 5):
            for pers in ("IMMEDIATE", "TWO_BAR_HYSTERESIS"):
                for v in ("ER", "RND"):
                    c.append(("EN116", f"{v.lower()}_K{K}_R{refit}_{pers.lower()}", Spec10(build="EN116", bp=(K, refit, pers, v), needs=("OI",)),
                              "ER10 state matched to the training activation rate" if v == "ER" else "seeded random state mapping", ("REF:EN87", "EN111:0018")))
    for buf in (0., .25):
        for tg in ("MIDPOINT", "OPPOSITE_QUARTILE"):
            for sb in (.25, .5):
                c.append(("EN117", f"gate_off_b{buf}_{tg.lower()}_s{sb}", Spec10(build="EN117", bp=(buf, tg, sb, "SAME"), kw=RANGE_KW), "cost gate off", ("CASH", "REF:E03_env")))
                if (tg, sb) == ("MIDPOINT", .5):
                    for dm in ("OPPOSITE", "RANDOM"):
                        kw = (("chooser9", "NEAREST"), ("max_lots", 1), ("admit9", False), ("hold", 8))
                        c.append(("EN117", f"{dm.lower()}_dir_b{buf}", Spec10(build="EN117", bp=(buf, tg, sb, dm), kw=kw),
                                  f"same clocks, {dm.lower()} direction, native exits, gate off", ("CASH", "REF:E03_env")))
    c.append(("EN118", "mean_actions", Spec10(learned="EN118", bp=("MEAN", "LIGHT", 0, "NO_OI"), needs=("OI_OPTIONAL",)), "unconditional action means", ("REF:EN87",)))
    c.append(("EN118", "direction_only", Spec10(learned="EN118", bp=("DIRECTION", "HEAVY", 0, "WITH_OI"), needs=("OI",)), "ridge direction forecast acting LEGACY_100_8", ("REF:EN87",)))
    for prof in ("NEARER_100_8_AT_E03", "NEARER_150_12_AT_E03"):
        kw = NEAR1 if prof.startswith("NEARER_100") else JOINT
        c.append(("EN118", f"fixed_{prof.lower()}", Spec10(arm="E03_env", kw=kw), "fixed action at every E03 event", ("REF:EN87", "REF:E03_env")))
    c.append(("EN120", "fixed_priority_union", Spec10(learned="EN120", bp=("UNION",), needs=("OI",)), "EN87 minute -> EN111 profile; else range -> EN117", ("REF:EN87",)))
    c.append(("EN120", "past_pnl_chooser", Spec10(learned="EN120", bp=("PASTPNL",), needs=("OI",)), "EN79-style: profile with the best prior cumulative adverse P&L", ("REF:EN87",)))
    return c


def own_settings(slot, st):
    return st


def registry():
    out = []
    for fam in load_grids():
        slot = fam["slot"]
        for cell in fam["cells"]:
            st = cell["settings"]
            sp, comp = cell_spec(slot, st)
            out.append(Config(cell["id"], slot, fam.get("name", slot), "CELL", st, sp, comp,
                              "" if sp else "SOURCE_GATED: >=20 synchronized packet expiries required; 1-2 available"))
            if slot == "EN112" and st["context"] in REVISED112:
                sp2 = replace(sp, bp=sp.bp[:3] + ("rank_all",))
                out.append(Config(cell["id"].replace("EN112:", "EN112:r1:"), slot, "revision_rank_all", "CELL", dict(st, rank="rank_all"), sp2, comp,
                                  "phase-zero geometry revision: extension rank over all prior covered sessions (>= 20 events)"))
            if slot == "EN118":
                sp2 = replace(sp, bp=sp.bp[:3] + ("NO_OI",), needs=("OI_OPTIONAL",))
                out.append(Config(cell["id"] + ":no_oi", slot, "no_oi", "CELL", dict(st, features="NO_OI"), sp2, comp,
                                  "separately registered no-OI model"))
    for cid, sp in REFERENCES.items():
        out.append(Config(cid, "REF", "reference", "REFERENCE", {}, sp))
    for fam, name, sp, note, comp in controls():
        out.append(Config(f"{fam}:ctl:{name}", fam, "control", "CONTROL", {}, sp, comp or ("REF:EN87",), note))
    byid = {c.id: c for c in out}
    # EN124 comparators: same-stress EN87 cell (deployable), own unstressed base (cost of stress)
    unstressed = {"EN87": "REF:EN87", "EN87_JOINT": "EN111:0018"}
    for c in out:
        if c.family == "EN121" and c.settings["contract"] == "NEAREST_ONE_LOT" and c.settings["target"] == 1.5 and c.settings["hold"] == 12:
            unstressed[{"E03_env": "E03_env_JOINT", "E032_native": "E032_JOINT", "EN55_native": "EN55_JOINT"}[c.settings["book"]]] = c.id
    for c in out:
        if c.family == "EN124":
            same = next(x.id for x in out if x.family == "EN124" and x.settings == dict(c.settings, base="EN87"))
            c.comparator = ((same,) if same != c.id else ()) + (unstressed[c.settings["base"]],)
    # EN111 contract-mechanism companions
    for c in out:
        if c.family == "EN111" and c.kind == "CELL":
            c.comparator = c.comparator + (f"EN111:ctl:equal_one_lot_t{float(c.settings['target'])}_h{int(c.settings['hold'])}",)
    ids = [c.id for c in out]
    assert len(ids) == len(set(ids))
    for c in out:
        for x in c.comparator:
            assert x == "CASH" or x in byid, (c.id, x)
    return out


def neighbours(reg, cfg):
    if cfg.kind != "CELL":
        return []
    return [c.id for c in reg if c.family == cfg.family and c.kind == "CELL" and c.block == cfg.block and c.id != cfg.id
            and len(c.settings) == len(cfg.settings) and sum(c.settings[k] != cfg.settings[k] for k in cfg.settings) == 1]


def counts(reg):
    cells = [c for c in reg if c.kind == "CELL"]
    by = {}
    for c in cells:
        by[c.family] = by.get(c.family, 0) + 1
    return dict(cells=len(cells), source_gated=sum(1 for c in cells if c.spec is None), by_family=by,
                controls=sum(c.kind == "CONTROL" for c in reg), references=sum(c.kind == "REFERENCE" for c in reg))
