"""SN463: a duplicate screen before simulation (PLAN.md section 1, frozen at 83e1b444; details fixed here before any number).

Registry: every table row of docs/SN_STRATEGY_HISTORY.md whose first cell starts with SN numbers ("| 443 / 453 / 454 | ..."),
plus every bullet line that names "SN<number>"; a row's SNs = the numbers it names; its section = the nearest "## " heading.
PLAIN: TF-IDF (log tf, smoothed idf, unit vectors) cosine between a query and each row; the top 5 rows' SNs.
STRUCTURED: a deterministic mechanism lexicon (below) tags each query and row with mechanism classes; rows sharing the query's
classes ranked by PLAIN's cosine; the top 5.
LLM arm: NOT RUN. The session's model wrote this check set, so its own reading would score itself; no independent model or API
is available inside the scorer. Reported as such (the brief's arm stays open for an independent reader).
Check set (frozen here): 14 queries with the expected duplicate SNs (empty = a new mechanism; any confident hit is a wrong
duplicate). Reported: recall@5 per arm on the 12 queries with expected SNs, wrong duplicates on the 2 new queries (top-1 cosine
>= the median top-1 cosine of the expected queries), missed duplicates, and invalid citations (an expected or returned SN
with no registry row).
"""
from __future__ import annotations

import collections
import json
import math
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
HIST = ROOT / "docs" / "SN_STRATEGY_HISTORY.md"
OUT = HERE / "results-sn463.json"

CHECK = [
    ("discount", "wait for a discount below the delta-implied option price before buying while the premise holds", {443, 453}),
    ("confirm5", "confirm the ask stays for five seconds before the entry fill", {432, 444}),
    ("passive", "resting passive buy order at the bid instead of crossing the spread conservative fill", {454}),
    ("bank", "bank results filings morning reaction net interest income", {447}),
    ("london", "London open as an outside clock for NIFTY direction", {448}),
    ("pin", "expiry day pinning toward the largest open interest strike max pain", {451}),
    ("lstm", "LSTM neural network forecast of direction", {193}),
    ("lgbm", "LightGBM learned decision engine on minute features walk-forward", {131}),
    ("wkh", "futures-hedged weekly straddle seller no weekend", {221}),
    ("opener", "cheap opener inside Gold's one ledger shared wallet", {419}),
    ("bound", "full-loss bound for Gold cheaper strike ladder", {434, 446}),
    ("hindsight", "hindsight value of the perfect entry minute timing headroom", {428, 442}),
    ("participants", "participant-wise open interest FII index futures long short positioning change", set()),
    ("kronos", "pretrained time-series foundation model zero-shot forecast of OHLCV bars", set()),
]

LEX = {
    "entry_timing": ["wait", "discount", "delay", "limit", "patient", "dip", "timing", "entry minute", "passive", "resting", "confirm"],
    "fill_execution": ["fill", "bid", "ask", "spread", "depth", "queue", "packet", "slippage", "walked"],
    "information_clock": ["results", "filing", "london", "rbi", "event", "budget", "clock", "announcement", "positioning", "participant"],
    "expiry_flow": ["expiry", "pin", "max pain", "open interest", "oi", "gamma"],
    "learner": ["lstm", "lightgbm", "learner", "neural", "model", "ml", "classifier", "pretrained", "forecast"],
    "volatility_seller": ["straddle", "strangle", "seller", "variance", "hedged", "condor", "fly"],
    "gold_wallet": ["gold", "wallet", "ledger", "companion", "bound", "loss room", "reserve"],
    "hindsight": ["hindsight", "perfect", "ceiling", "headroom"],
}


def tok(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def registry():
    rows, sec = [], None
    for line in HIST.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sec = line[3:].strip()
            continue
        m = re.match(r"^\|\s*\**\s*(\d{1,3}[a-z]?(?:\s*(?:/|,|–|-)\s*\d{1,3}[a-z]?)*)\s*\**\s*(?:\((?:own|auditor)\))?\s*\|(.*)$", line)
        if m:
            sns = {int(x) for x in re.findall(r"\d{1,3}", m.group(1))}
            rows.append({"sns": sorted(sns), "text": m.group(2), "section": sec})
            continue
        if line.lstrip().startswith("-") and re.search(r"SN\d{2,3}", line):
            sns = {int(x) for x in re.findall(r"SN(\d{2,3})(?!\d)", line)}
            rows.append({"sns": sorted(sns), "text": line, "section": sec})
    return rows


def tfidf(docs):
    df = collections.Counter()
    toks = [tok(d) for d in docs]
    for t in toks:
        df.update(set(t))
    n = len(docs)
    vocab = {w: i for i, w in enumerate(sorted(df))}
    idf = {w: math.log((1 + n) / (1 + df[w])) + 1 for w in df}

    def vec(t):
        v = np.zeros(len(vocab))
        for w, c in collections.Counter(t).items():
            if w in vocab:
                v[vocab[w]] = (1 + math.log(c)) * idf[w]
        nv = np.linalg.norm(v)
        return v / nv if nv else v
    return np.array([vec(t) for t in toks]), vec


def classes(text):
    s = " " + text.lower() + " "
    return {c for c, words in LEX.items() if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", s) for w in words)}


def main():
    if OUT.exists():
        raise SystemExit("SN463 is scored once")
    reg = registry()
    known = {s for r in reg for s in r["sns"]}
    M, vec = tfidf([r["text"] for r in reg])
    rcls = [classes(r["text"]) for r in reg]
    res = {"registry_rows": len(reg), "registry_sns": len(known), "queries": {}}
    tops = {}
    for qid, q, exp in CHECK:
        v = vec(tok(q))
        cos = M @ v
        order = np.argsort(-cos)
        plain = [reg[i]["sns"] for i in order[:5]]
        qc = classes(q)
        cand = [i for i in order if rcls[i] & qc]
        struct = [reg[i]["sns"] for i in cand[:5]]
        tops[qid] = float(cos[order[0]])
        hitp = sorted(exp & {s for r in plain for s in r})
        hits = sorted(exp & {s for r in struct for s in r})
        res["queries"][qid] = {"expected": sorted(exp), "invalid_expected": sorted(s for s in exp if s not in known),
                               "plain_top5": plain, "structured_top5": struct, "query_classes": sorted(qc),
                               "plain_found": hitp, "structured_found": hits, "top1_cosine": round(tops[qid], 3)}
    withexp = [c for c in CHECK if c[2]]
    thr = float(np.median([tops[c[0]] for c in withexp]))
    for arm in ("plain", "structured"):
        rec = [len(res["queries"][c[0]][f"{arm}_found"]) / len(c[2]) for c in withexp]
        res[f"{arm}_recall_at_5"] = round(float(np.mean(rec)), 3)
        res[f"{arm}_queries_fully_found"] = sum(r == 1.0 for r in rec)
        res[f"{arm}_missed"] = {c[0]: sorted(c[2] - set(res["queries"][c[0]][f"{arm}_found"])) for c in withexp if set(res["queries"][c[0]][f"{arm}_found"]) != c[2]}
    res["wrong_duplicate_threshold_cosine"] = round(thr, 3)
    res["wrong_duplicates_on_new_queries"] = {c[0]: tops[c[0]] >= thr for c in CHECK if not c[2]}
    res["invalid_citations"] = {c[0]: res["queries"][c[0]]["invalid_expected"] for c in CHECK if res["queries"][c[0]]["invalid_expected"]}
    res["llm_arm"] = "NOT RUN: the session model wrote the check set; no independent reader is available inside the scorer"
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "queries"}, indent=1))
    for qid, r in res["queries"].items():
        print(qid, r["expected"], "plain", r["plain_found"], "struct", r["structured_found"], "top1", r["top1_cosine"], r["plain_top5"][:3])


if __name__ == "__main__":
    main()
