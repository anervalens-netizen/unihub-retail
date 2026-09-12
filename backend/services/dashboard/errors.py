"""Typed Dashboard availability failures."""


class DashboardGenerationUnstable(RuntimeError):
    """Sales/reporting generation changed during both bounded load attempts."""
