import pytest

from round25 import LOT, amount, costs, selection


def test_turnover_tax_goes_on_sale_for_long_and_short():
    assert amount(20000., 20020., 1, 2.) == pytest.approx(16 * LOT - costs(20002., 20018.))
    assert amount(20000., 19980., -1, 2.) == pytest.approx(16 * LOT - costs(19982., 19998.))
    assert costs(20000., 20100.) > costs(20100., 20000.)


def test_selection_bounds_stop_loss_and_modeled_margin():
    assert selection(20000., 19995., 1, 65, 0)[1] == (.10, .13, .16)
    assert selection(25000., 24995., 1, 65, 0)[1] == (.10, .13)
    assert selection(25000., 24955., 1, 65, 0)[1] == ()
    assert selection(20000., 20005., -1, 65, 1) == (None, ())
    assert selection(20000., 20005., -1, 130, 0) == (None, ())
