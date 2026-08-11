"""Bounded artifact contract for chunked XLSX responses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import IO, Iterator

XLSX_STREAM_CHUNK_BYTES = 256 * 1024


@dataclass
class XlsxArtifact:
    stream: IO[bytes]
    filename: str
    size: int
    sha256: str | None = None
    peak_rss_bytes: int | None = None
    build_seconds: float | None = None
    cell_count: int | None = None
    row_count: int | None = None

    def iter_chunks(self, chunk_size: int = XLSX_STREAM_CHUNK_BYTES) -> Iterator[bytes]:
        self.stream.seek(0)
        while chunk := self.stream.read(chunk_size):
            yield chunk

    def close(self) -> None:
        self.stream.close()
