import pytest

from crypto_predictor.features.mcap_weight import mcap_rank_weight


def test_top_100_returns_full_weight():
    assert mcap_rank_weight(rank=1) == 1.0
    assert mcap_rank_weight(rank=50) == 1.0
    assert mcap_rank_weight(rank=100) == 1.0


def test_mid_tier_returns_seven_tenths():
    assert mcap_rank_weight(rank=101) == 0.7
    assert mcap_rank_weight(rank=200) == 0.7


def test_long_tail_returns_four_tenths():
    assert mcap_rank_weight(rank=201) == 0.4
    assert mcap_rank_weight(rank=340) == 0.4


def test_unknown_rank_returns_four_tenths():
    assert mcap_rank_weight(rank=None) == 0.4
