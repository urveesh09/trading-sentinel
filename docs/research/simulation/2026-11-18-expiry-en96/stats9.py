"""Round-9 uncertainty: round-8 long-group t (descriptive) plus a family-wide max-t over the whole grid.

The max-t flips the signs of eight long chronological calendar groups jointly for every configuration of a family (all
2^8 = 256 patterns, exact) and compares the observed best studentised group mean with the flipped maxima. It assumes
roughly independent, sign-symmetric group means under the null; calibrate() measures its size on skewed, heavy-tailed
and dependent nulls before any score. It adjusts for picking the best cell of the full fixed grid only; the stage-B
selection is evaluated on its own later blocks instead.
"""
from itertools import product
import numpy as np
import round8  # noqa: F401
import stats8

G = 8
SIGNS = np.array(list(product((1., -1.), repeat=G)))


_WEEKS = {}


def _layout(days, groups):
    key = (tuple(days), groups)
    if key not in _WEEKS:
        x, n = stats8.weeks(list(days), [0.] * len(days))
        from datetime import date, timedelta
        ds = [date.fromisoformat(d) for d in days]; start = min(ds) - timedelta(days=min(ds).weekday())
        week = np.array([(d - start).days // 7 for d in ds])
        gid_of_week = np.empty(len(x), int)
        for g, k in enumerate(np.array_split(np.arange(len(x)), groups)):
            gid_of_week[k] = g
        gid = gid_of_week[week]
        _WEEKS[key] = (gid, np.bincount(gid, minlength=groups).astype(float))
    return _WEEKS[key]


def group_means(days, values, groups=G):
    """Equal-period means of eight chronological calendar-week groups (identical grouping to stats8.group_t)."""
    gid, cnt = _layout(days, groups)
    tot = np.bincount(gid, weights=np.asarray(values, float), minlength=groups)
    return np.where(cnt > 0, tot / np.where(cnt > 0, cnt, 1), 0.)


def _t(A):
    mu = A.mean(-1); sd = A.std(-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(sd > 1e-12, mu / (sd / np.sqrt(A.shape[-1])), np.where(mu > 1e-12, np.inf, np.where(mu < -1e-12, -np.inf, 0.)))
    return t


def maxt_matrix(M):
    obs = _t(M); flipped = _t(SIGNS[:, None, :] * M[None, :, :]); top = flipped.max(1)
    return obs, top


def maxt(days, diffs):
    """diffs: {config_id: per-session paired differences}. Returns family p for the best cell and single-step adjusted p."""
    ids = list(diffs)
    if not ids:
        return dict(best=None, p_family=None)
    M = np.array([group_means(days, diffs[k]) for k in ids])
    obs, top = maxt_matrix(M)
    b = int(np.argmax(obs))
    adj = {k: float(np.mean(top >= obs[c] - 1e-12)) for c, k in enumerate(ids)}
    return dict(best=ids[b], t_best=float(obs[b]) if np.isfinite(obs[b]) else None, p_family=adj[ids[b]], adjusted=adj, groups=G,
                patterns=len(SIGNS), configs=len(ids))


def calibrate(days, paths=1000, configs=30, seed=9601):
    """Size and power of the family max-t on synthetic families over the real session calendar."""
    rng = np.random.default_rng(seed); n = len(days); out = {}
    for kind in ("gaussian", "skewed", "heavy_tail", "dependent"):
        rej = det = 0
        for k in range(paths):
            def noise(size):
                if kind == "gaussian":
                    return rng.normal(size=size)
                if kind == "skewed":
                    return 1 - rng.exponential(size=size)
                if kind == "heavy_tail":
                    return rng.standard_t(3, size=size) / np.sqrt(3)
                z = rng.normal(size=(size[0], size[1] + 100)); a = np.zeros_like(z)
                for j in range(1, z.shape[1]):
                    a[:, j] = .6 * a[:, j - 1] + np.sqrt(1 - .36) * z[:, j]
                return a[:, -size[1]:]
            common = noise((1, n))[0]; idio = noise((configs, n))
            active = rng.random((configs, n)) < .35
            X = 400. * (.6 * common[None, :] + .8 * idio) * active
            M = np.array([group_means(days, x) for x in X])
            obs, top = maxt_matrix(M); rej += np.mean(top >= obs.max() - 1e-12) <= .05
            X2 = X.copy(); X2[0] += 100. * active[0]
            M2 = np.array([group_means(days, x) for x in X2]); o2, t2 = maxt_matrix(M2)
            det += np.mean(t2 >= o2[0] - 1e-12) <= .05
        from scipy.stats import beta
        lo = float(beta.ppf(.025, rej, paths - rej + 1)) if rej else 0.
        hi = float(beta.ppf(.975, rej + 1, paths - rej)) if rej < paths else 1.
        out[kind] = dict(paths=paths, rejections=int(rej), rate=rej / paths, binomial_95=[lo, hi],
                         planted_100_per_active_session_detected=det / paths)
    return dict(cases=out, configs=configs, sessions=n, method="exact 2^8 sign flips of eight chronological group means, max studentised",
                size_ok=all(v["binomial_95"][0] <= .05 and v["rate"] <= .075 for v in out.values()),
                note="finite Monte Carlo diagnostic; group independence and sign symmetry are assumptions")


def infer(days, values):
    return stats8.infer(days, values)
