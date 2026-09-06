import math

import pytest

from rsa.fees import (KalshiFees, NoFees, RobinhoodFees, RobinhoodFlatFees, breakeven_probability, ceil_to_cent,
                      expected_profit, get_fee_model)


def test_ceil_to_cent_handles_float_noise():
    assert ceil_to_cent(0.30000000000000004) == 0.30
    assert ceil_to_cent(0.451) == 0.46
    assert ceil_to_cent(0.0) == 0.0
    assert ceil_to_cent(0.01) == 0.01


def test_robinhood_worked_example_from_fee_schedule():
    # 100 YES at $0.90: Gold $0.45, standard $0.90 commission (June 2026 schedule), before exchange fees
    assert RobinhoodFees(gold=True).commission(0.90, 100) == pytest.approx(0.45)
    assert RobinhoodFees().commission(0.90, 100) == pytest.approx(0.90)
    # exchange fee adds $0.01 per contract
    assert RobinhoodFees().fee(0.90, 100) == pytest.approx(1.90)


def test_robinhood_commission_is_symmetric_and_peaks_at_half():
    rh = RobinhoodFees()
    assert rh.commission(0.3, 100) == rh.commission(0.7, 100)
    assert rh.commission(0.5, 100) > rh.commission(0.1, 100)
    assert rh.commission(0.5, 1) == 0.03  # 0.025 rounded up


def test_flat_and_kalshi_models():
    assert RobinhoodFlatFees().fee(0.5, 10) == pytest.approx(0.20)
    assert KalshiFees().fee(0.5, 100) == pytest.approx(1.75)
    assert KalshiFees().fee(0.5, 1) == 0.02
    assert NoFees().fee(0.5, 100) == 0.0


def test_breakeven_and_expected_profit():
    rh = RobinhoodFees()
    be = breakeven_probability(0.40, rh)
    assert be == pytest.approx(0.40 + rh.fee(0.40, 1))
    assert expected_profit(be, 0.40, rh) == pytest.approx(0.0, abs=1e-9)
    assert expected_profit(0.5, 0.40, rh) > 0


def test_price_validation_and_registry():
    with pytest.raises(ValueError):
        RobinhoodFees().fee(1.5)
    assert get_fee_model("robinhood_gold").gold is True
    with pytest.raises(KeyError):
        get_fee_model("nope")
