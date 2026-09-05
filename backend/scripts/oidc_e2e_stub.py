"""Local-only OIDC provider used by the isolated full-stack CI gate."""
from __future__ import annotations

import base64
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_kid = "retail-real-e2e"
_codes: dict[str, tuple[str, str]] = {}

PERSONA_COOKIE = "real_e2e_persona"
DEFAULT_PERSONA = "admin"


@dataclass(frozen=True)
class Persona:
    """Deterministic local-only test identity (K10, issue #236).

    Fake credentials/claims only, using the existing application role
    vocabulary. No production identity or secret is represented here.
    """

    sub: str
    email: str
    groups: tuple[str, ...]


PERSONAS: dict[str, Persona] = {
    "admin": Persona("real-e2e-owner", "owner@example.invalid", ("unihub-admin",)),
    "manager": Persona("real-e2e-manager", "manager@example.invalid", ("unihub-manager",)),
    "hr": Persona("real-e2e-hr", "hr@example.invalid", ("unihub-hr",)),
    "agent": Persona("real-e2e-agent", "agent@example.invalid", ("unihub-agent",)),
    "team-leader": Persona(
        "real-e2e-team-leader",
        "team-leader@example.invalid",
        ("unihub-team-lead",),
    ),
    "pnl-owner": Persona(
        "real-e2e-pnl-owner",
        "pnl-owner@example.invalid",
        ("unihub-manager", "pnl-owner"),
    ),
    "pnl-owner-only": Persona(
        "real-e2e-pnl-owner-only",
        "pnl-owner-only@example.invalid",
        ("pnl-owner",),
    ),
}


def _persona(name: str) -> Persona:
    persona = PERSONAS.get(name)
    if persona is None:
        raise HTTPException(400, "unknown persona")
    return persona


def _origin() -> str:
    return os.environ["OIDC_STUB_ORIGIN"].rstrip("/")


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _token(audience: str, persona: str = DEFAULT_PERSONA, *, nonce: str | None = None) -> str:
    identity = _persona(persona)
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": f"{_origin()}/application/o/retail/",
        "aud": audience,
        "sub": identity.sub,
        "email": identity.email,
        "preferred_username": identity.sub,
        "groups": list(identity.groups),
        "iat": now,
        "exp": now + 600,
    }
    if nonce is not None:
        claims["nonce"] = nonce
    return jwt.encode(claims, _key, algorithm="RS256", headers={"kid": _kid})


@app.get("/test-persona/{persona}")
async def select_persona(persona: str) -> JSONResponse:
    """Bind the browser authorization flow to one deterministic persona."""
    _persona(persona)
    response = JSONResponse({"persona": persona})
    response.set_cookie(PERSONA_COOKIE, persona, max_age=3600, path="/")
    return response


@app.get("/application/o/authorize/")
async def authorize(
    request: Request,
    redirect_uri: str = Query(...), state: str = Query(...), nonce: str = Query(...)
) -> RedirectResponse:
    if redirect_uri != os.environ["OIDC_STUB_REDIRECT_URI"]:
        raise HTTPException(400, "invalid redirect")
    persona = request.cookies.get(PERSONA_COOKIE, DEFAULT_PERSONA)
    _persona(persona)
    code = secrets.token_urlsafe(32)
    _codes[code] = (nonce, persona)
    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}", 302)


@app.post("/application/o/token/")
async def exchange(
    grant_type: str = Form(...), code: str = Form(""), client_id: str = Form(...)
) -> JSONResponse:
    if grant_type != "authorization_code" or client_id != "retail-client":
        raise HTTPException(400, "invalid grant")
    entry = _codes.pop(code, None)
    if entry is None:
        raise HTTPException(400, "invalid code")
    nonce, persona = entry
    return JSONResponse({
        "access_token": _token("retail-api", persona),
        "id_token": _token("retail-client", persona, nonce=nonce),
        "refresh_token": secrets.token_urlsafe(48),
        "token_type": "Bearer",
        "expires_in": 600,
    })


@app.get("/jwks")
async def jwks() -> dict[str, object]:
    numbers = _key.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": _kid, "n": _b64(numbers.n), "e": _b64(numbers.e)}]}


@app.get("/test-token/{persona}")
async def test_token(persona: str) -> dict[str, str]:
    return {"access_token": _token("retail-api", persona)}


@app.get("/application/o/retail/end-session/")
async def logout(post_logout_redirect_uri: str = Query(...)) -> RedirectResponse:
    return RedirectResponse(post_logout_redirect_uri, 302)
