"""The genes added after the first table, one at a time from E01, then the sound ones together. Seen sessions only."""
from __future__ import annotations

import genome as G
import e011_lab as L

KEYS = L.recorded_keys()
SO = [L.Recorded(d, u) for d, u in KEYS]
SA = [L.Recorded(d, u, True) for d, u in KEYS]
E = G.e01_genome()


def score(g):
    t = G.to_ticket(g)
    a = [L.net(L.run_c(S, t, "X")) for S in SO]
    b = [L.net(L.run_c(S, t, "X")) for S in SA]
    return a, b


BASE = score(E)
print("days", [d[5:] for d, _ in KEYS])
print("E01", BASE[0], round(sum(BASE[0]), 2), "adverse", round(sum(BASE[1]), 2))


def show(name, **change):
    a, b = score({**E, **change})
    d = [x - y for x, y in zip(a, BASE[0])]
    print(f"{name:40s} net {sum(a):8.0f} ({sum(a)-sum(BASE[0]):+6.0f}) adv {sum(b):8.0f} exbest {sum(a)-max(a):7.0f} worst {min(a):6.0f} up/dn {sum(x>.01 for x in d)}/{sum(x<-.01 for x in d)} | " + " ".join(f"{x:+6.0f}" for x in d), flush=True)


for bp in (20., 25., 30., 35., 45.):
    show(f"box <= {bp:.0f} bp", box_max_bp=bp)
for p in G.SPACE["pilot"]:
    if p:
        show(f"pilot {p}", pilot=p)
for h in (.75, .65, .6, .55, .5, .45, .4):
    show(f"band_hi {h}", band_hi=h)
print("--- together")
show("stop .25 + band .5", stop=.25, band_hi=.5)
show("stop .20 + band .5", stop=.20, band_hi=.5)
show("stop .25 + box 35", stop=.25, box_max_bp=35.)
show("stop .25 + pilot .5/.2/20", stop=.25, pilot=(.5, .2, 20))
show("stop .25 + pilot + box 35", stop=.25, pilot=(.5, .2, 20), box_max_bp=35.)
show("stop .25 + pilot + recover", stop=.25, pilot=(.5, .2, 20), bank="recover")
show("stop .25 + band .5 + recover", stop=.25, band_hi=.5, bank="recover")
show("stop .25 + band .5 + recover + box 35", stop=.25, band_hi=.5, bank="recover", box_max_bp=35.)
show("stop .30 + recover", bank="recover")
show("stop .30 + recover + box 35", bank="recover", box_max_bp=35.)
show("stop .20 + recover + box 35", stop=.20, bank="recover", box_max_bp=35.)
show("stop .25 + recover + box 35", stop=.25, bank="recover", box_max_bp=35.)
