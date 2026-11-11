"""The frozen N13 arms (shared by the runner and the scorer; no lab imports).

One number moves: where the native profit lock arms, in premium-R (N11T: 0.40). Every arm keeps N012-A's trend rule
(regular_rules.trend_params: SUPPORT keep 0.35; ADVERSE arm min(0.60, arm) and keep 0.65; ADVERSE during a trail with
the lock off switches it on at 1.0 R keeping 0.60). LOCK_OFF has no profit lock at all, native or trend-made.
The line is ordered: a pick's neighbours are the arms next to it.
"""

LINE = ("ARM0.40", "ARM0.70", "ARM1.00", "LOCK_OFF")
ARMS = {"ARM0.40": 0.40, "ARM0.70": 0.70, "ARM1.00": 1.00, "LOCK_OFF": None}
CENTER = "ARM0.40"           # N012-A exactly (Round 30 TREND_ONLY)


def neighbours(name):
    i = LINE.index(name)
    return [LINE[j] for j in (i - 1, i + 1) if 0 <= j < len(LINE)]


def distance(name):
    return abs(LINE.index(name) - LINE.index(CENTER))
