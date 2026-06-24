from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from msal import ConfidentialClientApplication

from src.db.repositories.users import get_user_by_id, upsert_user
from src.utils.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "menas_session"
AUTH_STATE_COOKIE_NAME = "menas_auth_state"
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24)))
MSAL_REDIRECT_URI = os.getenv("MSAL_REDIRECT_URI", "").strip()

# MSAL adds openid/profile/offline_access automatically for sign-in;
# User.Read keeps the request valid and compatible with Entra ID consent.
AUTH_SCOPES = ["User.Read"]


def _get_session_secret() -> str:
    secret = (
        os.getenv("SESSION_SECRET")
        or os.getenv("SHAREPOINT_CLIENT_SECRET")
        or os.getenv("GEMINI_API_KEY")
    )
    if not secret:
        raise RuntimeError("SESSION_SECRET is not configured")
    return secret


def _sign_bytes(payload: bytes) -> str:
    digest = hmac.new(
        _get_session_secret().encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=") + "." + base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _verify_signed_value(value: str) -> bytes:
    try:
        payload_b64, digest_b64 = value.split(".", 1)
        payload = base64.urlsafe_b64decode(_pad_base64(payload_b64))
        digest = base64.urlsafe_b64decode(_pad_base64(digest_b64))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    expected = hmac.new(
        _get_session_secret().encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, digest):
        raise HTTPException(status_code=401, detail="Invalid session")
    return payload


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


def _encode_payload(payload: dict[str, Any]) -> str:
    return _sign_bytes(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _decode_payload(value: str) -> dict[str, Any]:
    payload = json.loads(_verify_signed_value(value).decode("utf-8"))
    exp = payload.get("exp")
    if exp and time.time() > float(exp):
        raise HTTPException(status_code=401, detail="Session expired")
    return payload


def _get_public_base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _get_public_prefix(request: Request) -> str:
    prefix = request.headers.get("x-forwarded-prefix", "").strip()
    if not prefix or prefix == "/":
        return ""
    return prefix.rstrip("/")


def _is_https_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _get_redirect_uri(request: Request) -> str:
    if MSAL_REDIRECT_URI:
        return MSAL_REDIRECT_URI
    prefix = _get_public_prefix(request)
    if prefix:
        return f"{_get_public_base_url(request)}{prefix}/auth/callback"
    return f"{_get_public_base_url(request)}/api/auth/callback"


def _get_return_to(request: Request, provided: str | None = None) -> str:
    if provided:
        if provided.startswith("http://") or provided.startswith("https://"):
            provided_url = urlparse(provided)
            request_url = urlparse(_get_public_base_url(request))
            if (
                provided_url.scheme == request_url.scheme
                and provided_url.hostname
                and provided_url.hostname == request_url.hostname
            ):
                return provided
        if provided.startswith("/"):
            return f"{_get_public_base_url(request)}{provided}"
    return f"{_get_public_base_url(request)}/"


def _get_msal_client() -> ConfidentialClientApplication:
    tenant_id = os.environ["SHAREPOINT_TENANT_ID"]
    client_id = os.environ["SHAREPOINT_CLIENT_ID"]
    client_secret = os.environ["SHAREPOINT_CLIENT_SECRET"]
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )


def build_login_redirect(request: Request, return_to: str | None = None) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    redirect_uri = _get_redirect_uri(request)
    state_payload = {
        "state": state,
        "return_to": _get_return_to(request, return_to),
        "exp": time.time() + 600,
    }
    signed_state = _encode_payload(state_payload)
    auth_url = _get_msal_client().get_authorization_request_url(
        AUTH_SCOPES,
        state=signed_state,
        redirect_uri=redirect_uri,
        prompt="select_account",
    )
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        AUTH_STATE_COOKIE_NAME,
        signed_state,
        httponly=True,
        secure=_is_https_request(request),
        samesite="lax",
        path="/",
        max_age=600,
    )
    return response


def complete_login(request: Request, code: str, state: str) -> RedirectResponse:
    raw_state = request.cookies.get(AUTH_STATE_COOKIE_NAME)
    if raw_state:
        state_payload = _decode_payload(raw_state)
        if state_payload.get("state") != _decode_payload(state).get("state"):
            raise HTTPException(status_code=400, detail="Invalid login state")
    else:
        state_payload = _decode_payload(state)

    redirect_uri = _get_redirect_uri(request)
    result = _get_msal_client().acquire_token_by_authorization_code(
        code,
        scopes=AUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    if "id_token_claims" not in result:
        raise HTTPException(status_code=401, detail="Microsoft sign-in failed")

    claims = result["id_token_claims"]
    user_id = str(claims.get("oid") or claims.get("sub") or claims.get("preferred_username"))
    name = str(claims.get("name") or claims.get("preferred_username") or "User")
    email = str(claims.get("preferred_username") or claims.get("email") or "")

    user_row = upsert_user(user_id, name=name, role="admin")
    logger.info("Microsoft user upserted: id=%s name=%s", user_row.get("id"), user_row.get("name"))
    session_payload = {
        "user_id": user_id,
        "name": user_row.get("name") or name,
        "email": email,
        "role": user_row.get("role") or "admin",
        "exp": time.time() + SESSION_TTL_SECONDS,
    }

    response = RedirectResponse(url=state_payload.get("return_to") or _get_return_to(request), status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _encode_payload(session_payload),
        httponly=True,
        secure=_is_https_request(request),
        samesite="lax",
        path="/",
        max_age=SESSION_TTL_SECONDS,
    )
    response.delete_cookie(AUTH_STATE_COOKIE_NAME, path="/")
    return response


def get_current_session(request: Request) -> dict[str, Any]:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _decode_payload(raw)


def get_current_user(request: Request) -> dict[str, Any]:
    session = get_current_session(request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user_by_id(user_id)
    if not user:
        logger.warning("User %s missing from users table; restoring from session", user_id)
        user = upsert_user(
            user_id,
            name=session.get("name") or "",
            role=session.get("role") or "admin",
        )
    return {
        "id": user["id"],
        "name": user.get("name") or session.get("name") or "",
        "email": session.get("email") or "",
        "role": user.get("role") or session.get("role") or "admin",
    }


def logout_response() -> JSONResponse:
    response = JSONResponse({"status": "success"})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(AUTH_STATE_COOKIE_NAME, path="/")
    return response
