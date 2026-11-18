"""TR01 packet loader for round 5b (PLAN5B.md): read-only export of Production's tick recorder.

The export (C:/Users/Urveesh/sentinel-operations/tr01-export-20261118/<day>/) was copied out of the Production
container with `docker cp` (read-only on the source; nothing in Production changed). verify() re-hashes every chunk
against the recorder's own manifest.json. extract() decodes only the wanted tokens with tick_recorder's packet layout
(Kite "full" mode) and caches arrays per token in _local/. Times: receipt unix ns (recv_ns) and the packet's exchange
timestamp (unix seconds, offset 60 for F&O, 28 for indices)."""
from __future__ import annotations
import hashlib, json, lzma, struct
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
EXPORT = Path.home() / "sentinel-operations/tr01-export-20261118"
LOCAL = HERE / "_local"
DAYS = ("2026-11-16", "2026-11-17")
REC = struct.Struct(">qH")
IST_NS = 19800 * 10 ** 9


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify():
    out = {}
    for d in DAYS:
        p = EXPORT / d; m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
        items = m["chunks"].items() if isinstance(m["chunks"], dict) else [(c.get("name") or c.get("file"), c) for c in m["chunks"]]
        bad = [n for n, c in items if sha(p / n) != c["sha256"]]
        assert not bad and m.get("complete"), (d, bad[:3])
        out[d] = dict(chunks=len(items), records=sum(c.get("records", 0) for _, c in items), manifest_sha256=sha(p / "manifest.json"),
                      instruments_sha256=sha(p / "instruments.jsonl"), events_sha256=sha(p / "events.jsonl"))
    return out


def instruments(day):
    return [json.loads(l) for l in (EXPORT / day / "instruments.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _div(token):
    seg = token & 0xFF
    return 1e7 if seg == 3 else 1e4 if seg == 6 else 100.0


def extract(day, tokens):
    """{token: dict of arrays} for the wanted tokens, in arrival order (chunks are chronological; within a chunk
    each instrument's records are in arrival order)."""
    tokens = sorted(set(int(t) for t in tokens)); key = hashlib.sha256(json.dumps(tokens).encode()).hexdigest()[:10]
    cache = LOCAL / f"tr01-{day}-{key}-{sha(Path(__file__))[:8]}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=False); out = {}
        for t in tokens:
            if f"{t}_recv" in z:
                out[t] = {f: z[f"{t}_{f}"] for f in ("recv", "exch", "ltp", "vol", "bp", "bq", "ap", "aq")}
        return out
    want = set(tokens); acc = {t: {f: [] for f in ("recv", "exch", "ltp", "vol", "bp", "bq", "ap", "aq")} for t in tokens}
    p = EXPORT / day; m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    names = sorted(m["chunks"]) if isinstance(m["chunks"], dict) else sorted(c.get("name") or c.get("file") for c in m["chunks"])
    for name in names:
        raw = lzma.decompress((p / name).read_bytes()); pos = 0; n = len(raw)
        while pos < n:
            recv, length = REC.unpack_from(raw, pos); pos += REC.size
            tok = int.from_bytes(raw[pos:pos + 4], "big")
            if tok in want:
                pk = raw[pos:pos + length]; dv = _div(tok); a = acc[tok]
                a["recv"].append(recv); a["ltp"].append(struct.unpack_from(">I", pk, 4)[0] / dv)
                if tok & 0xFF == 9:
                    a["exch"].append(struct.unpack_from(">I", pk, 28)[0] if length >= 32 else 0); a["vol"].append(0)
                    a["bp"].append([np.nan] * 5); a["bq"].append([0] * 5); a["ap"].append([np.nan] * 5); a["aq"].append([0] * 5)
                elif length >= 184:
                    a["vol"].append(struct.unpack_from(">I", pk, 16)[0]); a["exch"].append(struct.unpack_from(">I", pk, 60)[0])
                    lv = [struct.unpack_from(">IIH", pk, at) for at in range(64, 184, 12)]
                    a["bq"].append([q for q, _, _ in lv[:5]]); a["bp"].append([pr / dv if q else np.nan for q, pr, _ in lv[:5]])
                    a["aq"].append([q for q, _, _ in lv[5:]]); a["ap"].append([pr / dv if q else np.nan for q, pr, _ in lv[5:]])
                else:
                    a["recv"].pop(); a["ltp"].pop()
            pos += length
    out = {}
    for t, a in acc.items():
        if a["recv"]:
            out[t] = dict(recv=np.array(a["recv"], np.int64), exch=np.array(a["exch"], np.int64), ltp=np.array(a["ltp"], float),
                          vol=np.array(a["vol"], np.int64), bp=np.array(a["bp"], float), bq=np.array(a["bq"], np.int64),
                          ap=np.array(a["ap"], float), aq=np.array(a["aq"], np.int64))
    LOCAL.mkdir(exist_ok=True)
    np.savez(cache, **{f"{t}_{f}": v for t, d in out.items() for f, v in d.items()})
    return out


def ist_seconds(recv_ns):
    """Seconds since local midnight IST."""
    return ((np.asarray(recv_ns, np.int64) + IST_NS) % (86400 * 10 ** 9)) / 1e9
