import pytest
from partner_thesis import public_thesis_event


@pytest.mark.parametrize("direction,price,stop,target,event", [
    ("LONG", 90, 90, 110, "INVALIDATION"), ("LONG", 110, 90, 110, "TARGET_ZONE"),
    ("SHORT", 110, 110, 90, "INVALIDATION"), ("SHORT", 90, 110, 90, "TARGET_ZONE"),
    ("LONG", 100, 90, 110, None), ("LONG", float("nan"), 90, 110, None),
])
def test_public_price_thesis(direction, price, stop, target, event):
    assert public_thesis_event(direction, price, stop, target)[0] == event
