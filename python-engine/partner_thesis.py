"""Pure public-price thesis rules shared by advisory and research."""
import math


def public_thesis_event(direction, observed_underlying, invalidation, target):
    """Return the published level crossed, with invalidation first."""
    def positive(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    if not positive(observed_underlying):
        return None, None
    if direction == "LONG":
        if positive(invalidation) and observed_underlying <= invalidation:
            return "INVALIDATION", float(invalidation)
        if positive(target) and observed_underlying >= target:
            return "TARGET_ZONE", float(target)
    elif direction == "SHORT":
        if positive(invalidation) and observed_underlying >= invalidation:
            return "INVALIDATION", float(invalidation)
        if positive(target) and observed_underlying <= target:
            return "TARGET_ZONE", float(target)
    return None, None
