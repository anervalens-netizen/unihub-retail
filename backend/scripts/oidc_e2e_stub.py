"""Local-only OIDC provider used by the isolated full-stack CI gate."""
from __future__ import annotations

import base64
import os
import secrets
import time
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_kid = "retail-real-e2e"
_codes: dict[str, str] = {}


def _origin() -> str:
    return os.environ["OIDC_STUB_ORIGIN"].rstrip("/")


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _token(audience: str, *, nonce: str | None = None) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": f"{_origin()}/application/o/retail/",
        "aud": audience,
        "sub": "real-e2e-owner",
        "email": "owner@example.invalid",
        "preferred_username": "real-e2e-owner",
        "groups": ["unihub-admin"],
        "iat": now,
        "exp": now + 600,
    }
    if nonce is not None:
        claims["nonce"] = nonce
    return jwt.encode(claims, _key, algorithm="RS256", headers={"kid": _kid})


@app.get("/application/o/authorize/")
async def authorize(
    redirect_uri: str = Query(...), state: str = Query(...), nonce: str = Query(...)
) -> RedirectResponse:
    if redirect_uri != os.environ["OIDC_STUB_REDIRECT_URI"]:
        raise HTTPException(400, "invalid redirect")
    code = secrets.token_urlsafe(32)
    _codes[code] = nonce
    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}", 302)


@app.post("/application/o/token/")
async def exchange(
    grant_type: str = Form(...), code: str = Form(""), client_id: str = Form(...)
) -> JSONResponse:
    if grant_type != "authorization_code" or client_id != "retail-client":
        raise HTTPException(400, "invalid grant")
    nonce = _codes.pop(code, None)
    if nonce is None:
        raise HTTPException(400, "invalid code")
    return JSONResponse({
        "access_token": _token("retail-api"),
        "id_token": _token("retail-client", nonce=nonce),
        "refresh_token": secrets.token_urlsafe(48),
        "token_type": "Bearer",
        "expires_in": 600,
    })


@app.get("/jwks")
async def jwks() -> dict[str, object]:
    numbers = _key.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": _kid, "n": _b64(numbers.n), "e": _b64(numbers.e)}]}


@app.get("/test-token/admin")
async def test_token() -> dict[str, str]:
    return {"access_token": _token("retail-api")}


@app.get("/application/o/retail/end-session/")
async def logout(post_logout_redirect_uri: str = Query(...)) -> RedirectResponse:
    return RedirectResponse(post_logout_redirect_uri, 302)
