"""Write ANATOMY10-tables.md from results10.json (every cell, control and reference; descriptive)."""
import json
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent


def f(x, nd=0):
    if x is None:
        return "—"
    return f"{x:,.{nd}f}"


def row(cid, r):
    o, a = r["ordinary"], r["adverse"]; w = r["wallet"]
    v = r["vs"][0] if r.get("vs") else None
    vs = "—" if not v else f"{v['reference'].replace('REF:', '')}: {f(v.get('adverse_sum', v['adverse']['mean'] * a['sessions']))} / x2 {f(v.get('adverse_without_top2'))} ({v['changed_parents']} ch)"
    st = r.get("settings") or {}
    s = ", ".join(f"{k}={x}" for k, x in st.items() if k not in ("matches",)) or r.get("note", "")[:60]
    return (f"| `{cid}` | {s} | {f(o['net'])} | {f(a['net'])} | {o['trades']} | {f(o['without_top2'])} | {f(w['ordinary']['P'])} / {f(w['adverse']['P'])}"
            f"{' H' if w['ordinary']['halted'] or w['adverse']['halted'] else ''} | {vs} | {r.get('support', '—')}{' DUP' if r.get('duplicate_of_primary') else ''} |"
            f" {f(r.get('entry_plus1_adverse'))} |")


def main():
    res = json.loads((HERE / "results10.json").read_text())
    by = defaultdict(list)
    for key, r in res["configs"].items():
        cid, u = key.rsplit("|", 1)
        by[(r["family"], u)].append((cid, r))
    out = ["# Round 10 tables (development screen on studied sessions; descriptive only)", "",
           "Columns:",
           "- independent-session net (ordinary, adverse) and parents;",
           "- ordinary net without the best two days;",
           "- continuous ₹30,000 wallet P (ordinary / adverse; H = halted);",
           "- versus the primary comparator: adverse paired sum, the same without the best two days, and changed parents;",
           "- support label;",
           "- adverse net with entry one bar later.",
           "",
           "Learned EN118/EN120 rows cover the walk-forward dates 100–196 only.", ""]
    fams = sorted({f for f, _ in by}, key=lambda x: (x != "REF", int(x[2:]) if x[2:].isdigit() else 0))
    for fam in fams:
        for u in ("NIFTY", "SENSEX"):
            rows = by.get((fam, u))
            if not rows:
                continue
            out += [f"## {fam} — {u}", "", "| id | settings | ord | adv | parents | ord ex-top2 | wallet P ord/adv | vs primary (adv) | support | entry+1 adv |",
                    "|---|---|---:|---:|---:|---:|---|---|---|---:|"]
            rows.sort(key=lambda x: (x[1]["kind"] != "CELL", x[0]))
            out += [row(c, r) for c, r in rows]
            out.append("")
    out += ["## Unavailable", ""] + [f"- `{k}`: {v}" for k, v in sorted(res["unavailable"].items()) if not k.startswith("EN119")]
    out += ["", f"- EN119: {sum(k.startswith('EN119') for k in res['unavailable'])} cells × index SOURCE-GATED", ""]
    (HERE / "ANATOMY10-tables.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("rows", sum(len(v) for v in by.values()))


if __name__ == "__main__":
    main()
