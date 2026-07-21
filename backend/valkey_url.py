"""Safe endpoint overrides for Valkey URLs that retain existing credentials."""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


def apply_valkey_endpoint_overrides(base_url: str, prefix: str) -> str:
    port_raw = os.getenv(f"{prefix}_PORT")
    database_raw = os.getenv(f"{prefix}_DATABASE")
    if port_raw is None and database_raw is None:
        return base_url
    try:
        parsed = urlsplit(base_url)
        port = parsed.port if port_raw is None else int(port_raw)
        database = (
            parsed.path.removeprefix("/") or "0"
            if database_raw is None
            else database_raw
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Valkey endpoint override is invalid") from exc
    if (
        parsed.scheme not in {"redis", "rediss"}
        or not parsed.hostname
        or port is None
        or not 1 <= port <= 65535
        or not database.isascii()
        or not database.isdecimal()
        or not 0 <= int(database) <= 15
    ):
        raise ValueError("Valkey endpoint override is invalid")

    credentials = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else ""
    hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{hostname}:{port}"
    if credentials:
        netloc = f"{credentials}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, f"/{int(database)}", "", ""))
