"""The frozen N13 arms (shared by the runner and the scorer; no lab imports).

In N11T only two strategies carry a native profit lock (fno_book.EXIT_OVERRIDES): OR20 arms at 0.80 R and the
shipped break at the global 0.40 R; EFF, TPB and the earned lot have none. N012-A's trend rule
(regular_rules.trend_params) also switches a lock on during an adverse trail for any strategy. Each arm turns locks off
for a set of strategies, the trend-made lock included; the others keep N012-A exactly. A pick's neighbours differ from
it by one strategy.
"""

STRATEGIES = ("OR20", "SHIPPED")
ARMS = {"CENTRE": (), "OR20_OFF": ("OR20",), "SHIPPED_OFF": ("SHIPPED",), "LOCK_OFF": ("ALL",)}
LINE = tuple(ARMS)
CENTER = "CENTRE"            # N012-A exactly (Round 30 TREND_ONLY)


def _set(name):
    off = ARMS[name]
    return set(STRATEGIES) if "ALL" in off else set(off)


def neighbours(name):
    return [n for n in ARMS if len(_set(n) ^ _set(name)) == 1]


def distance(name):
    return len(_set(name))
