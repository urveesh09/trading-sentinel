"""The frozen N012-A2 grid (shared by the runner and the scorer; no lab imports)."""
import itertools

S_GRID, A_GRID, T_GRID = (0.25, 0.35, 0.45), (0.55, 0.65, 0.75), (None, 0.60, 0.75)
CENTER = (0.35, 0.65, 0.60)


def arm_name(s, a, t):
    return f"S{s:.2f}_A{a:.2f}_T{'OFF' if t is None else f'{t:.2f}'}"


ARMS = {arm_name(*k): k for k in itertools.product(S_GRID, A_GRID, T_GRID)}
