"""Domain errors for durable export admission and lifecycle."""
from __future__ import annotations


class ExportOperationCapacityError(RuntimeError):
    """Raised when bounded export admission refuses a new operation."""
