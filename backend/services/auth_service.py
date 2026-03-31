from __future__ import annotations

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
import hmac
import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import MissingBackendError, UnknownHashError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
PBKDF2_ITERATIONS = 600_000


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


def get_jwt_expire_hours() -> int:
    return int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(plain_password, password_hash)
    except (MissingBackendError, UnknownHashError):
        return _verify_password_fallback(plain_password, password_hash)


def hash_password(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except MissingBackendError:
        return _hash_password_fallback(password)


def create_access_token(user_id: int, username: str, role: str) -> str:
    expires_delta = timedelta(hours=get_jwt_expire_hours())
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Token invalid") from exc


def _hash_password_fallback(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$pbkdf2-sha256$%d$%s$%s" % (
        PBKDF2_ITERATIONS,
        urlsafe_b64encode(salt).decode("ascii"),
        urlsafe_b64encode(digest).decode("ascii"),
    )


def _verify_password_fallback(plain_password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) != 5 or parts[1] != "pbkdf2-sha256":
        raise ValueError("Unsupported password hash format")
    _, _, iterations_str, salt_b64, digest_b64 = parts
    salt = urlsafe_b64decode(_pad_b64(salt_b64))
    expected_digest = urlsafe_b64decode(_pad_b64(digest_b64))
    actual_digest = pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        int(iterations_str),
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def _pad_b64(value: str) -> str:
    return value + "=" * (-len(value) % 4)
