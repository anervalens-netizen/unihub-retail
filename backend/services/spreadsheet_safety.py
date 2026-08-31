"""Single writer boundary for untrusted spreadsheet text."""
from __future__ import annotations

import math
import io
import os
import resource
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from defusedxml import ElementTree
from prometheus_client import Gauge, Histogram


_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
_OLE_COMPOUND_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


class SpreadsheetUploadError(ValueError):
    """The uploaded spreadsheet exceeded a structural safety boundary."""


@dataclass(frozen=True)
class SpreadsheetUploadLimits:
    max_source_bytes: int = 32 * 1024 * 1024
    max_members: int = 2_048
    max_member_bytes: int = 64 * 1024 * 1024
    max_uncompressed_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: int = 100
    max_cells: int = 2_000_000


@dataclass(frozen=True)
class SpreadsheetUploadStats:
    """Measured archive expansion, not an estimate from parsed Python objects."""

    source_bytes: int
    compressed_bytes: int | None
    uncompressed_bytes: int | None
    cells: int | None
    format: str


# These are deliberately separate contracts.  A compact targets workbook and
# a wide historical workbook must not inherit the same decompression/cell cap.
SALES_SPREADSHEET_LIMITS = SpreadsheetUploadLimits(
    max_source_bytes=32 * 1024 * 1024,
    max_members=2_048,
    max_member_bytes=128 * 1024 * 1024,
    max_uncompressed_bytes=256 * 1024 * 1024,
    max_compression_ratio=100,
    max_cells=2_000_000,
)
PROMO_ACTUALS_SPREADSHEET_LIMITS = SpreadsheetUploadLimits(
    max_source_bytes=32 * 1024 * 1024,
    max_members=1_024,
    max_member_bytes=32 * 1024 * 1024,
    max_uncompressed_bytes=128 * 1024 * 1024,
    max_compression_ratio=80,
    max_cells=750_000,
)
ERP_RECONCILIATION_SPREADSHEET_LIMITS = SpreadsheetUploadLimits(
    max_source_bytes=16 * 1024 * 1024,
    max_members=1_024,
    max_member_bytes=32 * 1024 * 1024,
    max_uncompressed_bytes=128 * 1024 * 1024,
    max_compression_ratio=80,
    max_cells=1_000_000,
)
TARGETS_SPREADSHEET_LIMITS = SpreadsheetUploadLimits(
    max_source_bytes=16 * 1024 * 1024,
    max_members=512,
    max_member_bytes=16 * 1024 * 1024,
    max_uncompressed_bytes=64 * 1024 * 1024,
    max_compression_ratio=50,
    max_cells=250_000,
)
HISTORY_SPREADSHEET_LIMITS = SpreadsheetUploadLimits(
    max_source_bytes=64 * 1024 * 1024,
    max_members=4_096,
    max_member_bytes=128 * 1024 * 1024,
    max_uncompressed_bytes=512 * 1024 * 1024,
    max_compression_ratio=100,
    max_cells=4_000_000,
)


SPREADSHEET_SOURCE_BYTES = Gauge(
    "spreadsheet_parser_source_bytes",
    "Source file bytes observed by the latest spreadsheet parser run.",
    ("parser", "format"),
)
SPREADSHEET_COMPRESSED_BYTES = Gauge(
    "spreadsheet_parser_compressed_bytes",
    "Compressed ZIP bytes observed by the latest spreadsheet parser run; zero when unavailable.",
    ("parser", "format"),
)
SPREADSHEET_EXPANDED_BYTES = Gauge(
    "spreadsheet_parser_expanded_bytes",
    "Expanded ZIP bytes observed by the latest spreadsheet parser run; zero when unavailable.",
    ("parser", "format"),
)
SPREADSHEET_CELLS = Gauge(
    "spreadsheet_parser_cells",
    "Structural worksheet cells observed by the latest spreadsheet parser run; zero when unavailable.",
    ("parser", "format"),
)
SPREADSHEET_ROWS = Gauge(
    "spreadsheet_parser_rows",
    "Business rows emitted by the latest spreadsheet parser run.",
    ("parser", "format"),
)
SPREADSHEET_PARSE_SECONDS = Histogram(
    "spreadsheet_parser_parse_seconds",
    "Spreadsheet preflight, parse and business-validation duration.",
    ("parser", "format"),
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
SPREADSHEET_PEAK_RSS_BYTES = Gauge(
    "spreadsheet_parser_peak_rss_bytes",
    "Maximum resident set size sampled while the latest parser run was active.",
    ("parser", "format"),
)
SPREADSHEET_MEASUREMENT_AVAILABLE = Gauge(
    "spreadsheet_parser_measurement_available",
    "Whether a structural metric is measurable for the source format.",
    ("parser", "format", "metric"),
)


def _current_rss_bytes() -> int:
    """Return current RSS, using a finite process-lifetime fallback off Linux."""

    try:
        statm = Path("/proc/self/statm").read_text(encoding="ascii").split()
        return max(0, int(statm[1]) * os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, IndexError):
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return max(0, value * (1024 if os.name == "posix" else 1))


class SpreadsheetParserMeasurement:
    """Measure one parser run without treating process-lifetime max RSS as its peak."""

    def __init__(self, parser: str) -> None:
        self.parser = parser
        self.stats: SpreadsheetUploadStats | None = None
        self.rows = 0
        self.peak_rss_bytes = 0
        self._started_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "SpreadsheetParserMeasurement":
        self._started_at = time.perf_counter()
        self.peak_rss_bytes = _current_rss_bytes()

        def sample() -> None:
            while not self._stop.wait(0.01):
                self.peak_rss_bytes = max(self.peak_rss_bytes, _current_rss_bytes())

        self._thread = threading.Thread(target=sample, name=f"rss-{self.parser}", daemon=True)
        self._thread.start()
        return self

    def set_preflight(self, stats: SpreadsheetUploadStats) -> None:
        self.stats = stats

    def set_rows(self, rows: int) -> None:
        self.rows = max(0, int(rows))

    def as_dict(self) -> dict[str, int | float | str | None]:
        stats = self.stats
        return {
            "parser": self.parser,
            "format": stats.format if stats is not None else "unknown",
            "source_bytes": stats.source_bytes if stats is not None else 0,
            "compressed_bytes": stats.compressed_bytes if stats is not None else None,
            "expanded_bytes": stats.uncompressed_bytes if stats is not None else None,
            "cells": stats.cells if stats is not None else None,
            "rows": self.rows,
            "parse_seconds": max(0.0, time.perf_counter() - self._started_at),
            "peak_rss_bytes": max(0, self.peak_rss_bytes),
        }

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.1)
        self.peak_rss_bytes = max(self.peak_rss_bytes, _current_rss_bytes())
        stats = self.stats
        source_format = stats.format if stats is not None else "unknown"
        labels = {"parser": self.parser, "format": source_format}
        source_bytes = stats.source_bytes if stats is not None else 0
        compressed = stats.compressed_bytes if stats is not None else None
        expanded = stats.uncompressed_bytes if stats is not None else None
        cells = stats.cells if stats is not None else None
        SPREADSHEET_SOURCE_BYTES.labels(**labels).set(max(0, source_bytes))
        SPREADSHEET_COMPRESSED_BYTES.labels(**labels).set(max(0, compressed or 0))
        SPREADSHEET_EXPANDED_BYTES.labels(**labels).set(max(0, expanded or 0))
        SPREADSHEET_CELLS.labels(**labels).set(max(0, cells or 0))
        SPREADSHEET_ROWS.labels(**labels).set(self.rows)
        SPREADSHEET_PEAK_RSS_BYTES.labels(**labels).set(self.peak_rss_bytes)
        SPREADSHEET_PARSE_SECONDS.labels(**labels).observe(
            max(0.0, time.perf_counter() - self._started_at)
        )
        for metric, value in (
            ("compressed_bytes", compressed),
            ("expanded_bytes", expanded),
            ("cells", cells),
        ):
            SPREADSHEET_MEASUREMENT_AVAILABLE.labels(
                **labels,
                metric=metric,
            ).set(1 if value is not None else 0)


def validate_spreadsheet_upload(
    content: bytes,
    suffix: str,
    *,
    limits: SpreadsheetUploadLimits | None = None,
) -> SpreadsheetUploadStats:
    """Validate file signature and bounded XLSX expansion before parsing."""

    normalized_suffix = suffix.casefold()
    policy = limits or SALES_SPREADSHEET_LIMITS
    if len(content) > policy.max_source_bytes:
        raise SpreadsheetUploadError("Workbook-ul depășește limita sursei")
    if normalized_suffix == ".xls":
        if not content.startswith(_OLE_COMPOUND_MAGIC):
            raise SpreadsheetUploadError("Fișierul .xls are o semnătură invalidă")
        # OLE2 does not expose ZIP member expansion or worksheet cell counts.
        # Report those dimensions as unavailable instead of inventing equality
        # between source and expanded bytes.
        return SpreadsheetUploadStats(
            source_bytes=len(content),
            compressed_bytes=None,
            uncompressed_bytes=None,
            cells=None,
            format="xls",
        )
    if normalized_suffix != ".xlsx":
        raise SpreadsheetUploadError("Format spreadsheet neacceptat")
    if not content.startswith(b"PK"):
        raise SpreadsheetUploadError("Fișierul .xlsx are o semnătură invalidă")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > policy.max_members:
                raise SpreadsheetUploadError("Workbook-ul conține prea mulți membri ZIP")
            names = {member.filename for member in members}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise SpreadsheetUploadError("Structura XLSX obligatorie lipsește")

            expanded = 0
            compressed = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise SpreadsheetUploadError("Workbook-urile ZIP criptate nu sunt acceptate")
                if member.file_size > policy.max_member_bytes:
                    raise SpreadsheetUploadError("Un membru XLSX depășește limita permisă")
                expanded += member.file_size
                compressed += member.compress_size
                if expanded > policy.max_uncompressed_bytes:
                    raise SpreadsheetUploadError("Workbook-ul depășește bugetul decomprimat")
            if expanded > max(compressed, 1) * policy.max_compression_ratio:
                raise SpreadsheetUploadError("Raportul de compresie XLSX este excesiv")

            cell_count = 0
            worksheets = [
                member
                for member in members
                if member.filename.startswith("xl/worksheets/")
                and member.filename.endswith(".xml")
            ]
            for worksheet in worksheets:
                with archive.open(worksheet) as stream:
                    for _event, element in ElementTree.iterparse(stream, events=("end",)):
                        if element.tag.rsplit("}", 1)[-1] == "c":
                            cell_count += 1
                            if cell_count > policy.max_cells:
                                raise SpreadsheetUploadError(
                                    "Workbook-ul depășește limita de celule"
                                )
                        element.clear()
            return SpreadsheetUploadStats(
                source_bytes=len(content),
                compressed_bytes=len(content),
                uncompressed_bytes=expanded,
                cells=cell_count,
                format="xlsx",
            )
    except SpreadsheetUploadError:
        raise
    except (zipfile.BadZipFile, OSError, ElementTree.ParseError) as exc:
        raise SpreadsheetUploadError("Workbook-ul XLSX este corupt") from exc


@dataclass(frozen=True)
class TrustedFormula:
    expression: str

    def __post_init__(self) -> None:
        if not self.expression.startswith("="):
            raise ValueError("TrustedFormula must start with '='")


def sanitize_spreadsheet_text(value: str) -> str:
    return "'" + value if value.startswith(_DANGEROUS_PREFIXES) else value


def spreadsheet_cell_value(value: object) -> object:
    if isinstance(value, TrustedFormula):
        return value
    if isinstance(value, str):
        return sanitize_spreadsheet_text(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, Decimal) and not value.is_finite():
        return str(value)
    if value is None or isinstance(value, (int, float, Decimal, bool, date, datetime)):
        return value
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    return sanitize_spreadsheet_text(text)


def csv_cell_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


def google_sheets_value(value: object) -> object:
    safe = spreadsheet_cell_value(value)
    return safe.expression if isinstance(safe, TrustedFormula) else safe


def sanitize_dataframe_text(frame: Any) -> Any:
    """Copy a pandas-like table and neutralize textual cells only.

    Missing values remain blank instead of becoming the literal strings ``nan``
    or ``<NA>``.  Object, pandas string, categorical and compatible extension
    text columns are covered while numeric columns retain their native dtype.
    """
    import pandas as pd

    safe_frame = frame.copy()
    for column in safe_frame.columns:
        series = safe_frame[column]
        dtype = series.dtype
        kind = getattr(dtype, "kind", None)
        is_textual = (
            kind in {"O", "U", "S"}
            or isinstance(dtype, pd.StringDtype)
            or isinstance(dtype, pd.CategoricalDtype)
        )
        if not is_textual:
            continue

        def sanitize_value(value: object) -> object:
            try:
                missing = pd.isna(value)
                try:
                    if bool(missing):
                        return None
                except (TypeError, ValueError):
                    pass
            except Exception:
                pass
            return spreadsheet_cell_value(value)

        # Convert extension/categorical columns to object so neutralized values
        # that are not part of the original category set can be assigned safely.
        safe_frame[column] = series.astype("object").map(sanitize_value)
    return safe_frame


def set_openpyxl_cell(cell: Any, value: object) -> None:
    safe = spreadsheet_cell_value(value)
    if isinstance(safe, TrustedFormula):
        cell.value = safe.expression
        cell.data_type = "f"
    elif isinstance(safe, str):
        cell.value = safe
        cell.data_type = "s"
    else:
        cell.value = safe


def append_openpyxl_row(ws: Any, values: Iterable[object]) -> None:
    if ws.__class__.__name__ == "WriteOnlyWorksheet":
        raise TypeError("append_openpyxl_row does not support write-only worksheets")

    # ``max_row`` cannot distinguish an untouched worksheet from a logical row
    # beginning in column B.  Preserve writer state so such rows are never reused.
    last_row = getattr(ws, "_unihub_safe_last_row", None)
    if last_row is None:
        first_row_is_empty = ws.max_row == 1 and all(cell.value is None for cell in ws[1])
        last_row = 0 if first_row_is_empty else ws.max_row
    row_index = last_row + 1
    for column_index, value in enumerate(values, start=1):
        set_openpyxl_cell(ws.cell(row=row_index, column=column_index), value)
    setattr(ws, "_unihub_safe_last_row", row_index)
