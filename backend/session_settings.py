"""Pure session-authentication settings parsing."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from valkey_url import apply_valkey_endpoint_overrides


@dataclass(frozen=True, slots=True)
class SessionSettings:
    valkey_url: str
    encryption_key: str
    client_id: str
    client_secret: str
    public_origin: str
    issuer: str
    session_ttl_seconds: int
    secure_cookie: bool

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_origin}/auth/callback"

    @property
    def authorize_url(self) -> str:
        parsed = urlsplit(self.issuer)
        return f"{parsed.scheme}://{parsed.netloc}/application/o/authorize/"

    @property
    def token_url(self) -> str:
        parsed = urlsplit(self.issuer)
        return f"{parsed.scheme}://{parsed.netloc}/application/o/token/"

    @property
    def logout_url(self) -> str:
        return f"{self.issuer}/end-session/"


def _session_secrets(production: bool) -> tuple[str, str, str] | None:
    names = ("SESSION_ENCRYPTION_KEY", "OIDC_CLIENT_SECRET", "OIDC_ISSUER")
    configured = any(os.getenv(name) not in (None, "") for name in names)
    if not configured and not production:
        return None
    try:
        encryption_key = os.environ["SESSION_ENCRYPTION_KEY"]
        Fernet(encryption_key.encode("ascii"))
        client_secret = os.environ["OIDC_CLIENT_SECRET"]
        issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ValueError("Session authentication configuration is invalid") from exc
    return encryption_key, client_secret, issuer


def _valid_client_credentials(client_id: str, client_secret: str) -> bool:
    return (
        16 <= len(client_secret) <= 512
        and all(not char.isspace() and char.isprintable() for char in client_secret)
        and bool(client_id)
        and len(client_id) <= 256
        and all(not char.isspace() and char.isprintable() for char in client_id)
    )
def _valid_valkey_endpoint(valkey_url: str, valkey: Any, port: int | None) -> bool:
    return (
        bool(valkey_url)
        and valkey.scheme in {"redis", "rediss"}
        and bool(valkey.hostname)
        and (valkey.username is None or valkey.password is not None)
        and not valkey.query
        and not valkey.fragment
        and (port is None or 0 < port <= 65535)
    )


def _valid_public_origin(origin: Any, port: int | None, production: bool) -> bool:
    return (
        origin.scheme in ({"https"} if production else {"http", "https"})
        and bool(origin.hostname)
        and origin.username is None
        and origin.password is None
        and (port is None or 0 < port <= 65535)
        and origin.path in {"", "/"}
        and not origin.query
        and not origin.fragment
    )


def load_session_settings() -> SessionSettings | None:
    production = os.getenv("UNIHUB_ENV", "development").strip().lower() == "production"
    secrets_config = _session_secrets(production)
    if secrets_config is None:
        return None
    encryption_key, client_secret, issuer = secrets_config
    client_id = os.getenv("OIDC_CLIENT_ID", "")
    public_origin = os.getenv("SESSION_PUBLIC_ORIGIN", "http://localhost:3000").rstrip("/")
    try:
        valkey_url = apply_valkey_endpoint_overrides(
            os.getenv("SESSION_VALKEY_URL") or os.getenv("VALKEY_URL") or "",
            "SESSION_VALKEY",
        )
        ttl = int(os.getenv("SESSION_TTL_SECONDS", "2592000"))
        origin = urlsplit(public_origin)
        valkey = urlsplit(valkey_url)
        origin_port = origin.port
        valkey_port = valkey.port
    except ValueError as exc:
        raise ValueError("Session authentication configuration is invalid") from exc
    if not (
        _valid_client_credentials(client_id, client_secret)
        and _valid_valkey_endpoint(valkey_url, valkey, valkey_port)
        and _valid_public_origin(origin, origin_port, production)
        and 900 <= ttl <= 60 * 60 * 24 * 90
    ):
        raise ValueError("Session authentication configuration is invalid")
    return SessionSettings(
        valkey_url, encryption_key, client_id, client_secret, public_origin,
        issuer, ttl, production,
    )
