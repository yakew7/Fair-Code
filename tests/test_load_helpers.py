"""tests/load_helpers.py scales timing-sensitive tests by the machine load (#1264, #1284)."""
from load_helpers import load_factor


def test_load_factor_scales_with_the_load_per_core_and_is_bounded():
    assert load_factor(lambda: (0.5, 0, 0), 8) == 1.0
    assert load_factor(lambda: (16.0, 0, 0), 8) == 2.0
    assert load_factor(lambda: (400.0, 0, 0), 8) == 4.0

    def unavailable():
        raise OSError

    assert load_factor(unavailable, 8) == 1.0
