from __future__ import annotations

from routers.filters import clear_filter_options_cache


def test_clear_filter_options_cache_is_safe() -> None:
    clear_filter_options_cache()
    clear_filter_options_cache()
