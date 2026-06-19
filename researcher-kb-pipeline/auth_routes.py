"""
FastAPI router for auth, AI settings, saved researchers, and AI chat.

All session-bearing routes expect the session token in the
X-Session-Token request header (set as a cookie on the BFF frontend;
forwarded here as a header to keep cookies on the frontend domain).
"""

import logging
import os
import re
import secrets
import time
import urllib.parse

import requests as http_requests
import resend as _resend
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

import auth_db
import link_verifier

logger = logging.getLogger(__name__)

router = APIRouter()

# Demo user ID allowed to use ADC when no key stored
DEMO_USER_ID = "d5a3b5dd-8c14-4765-8e04-40834555f086"

SHOW_DEV_CODE = os.environ.get("RESEARCH_AI_SHOW_DEV_CODE", "").lower() in (
    "1",
    "true",
    "yes",
)

# ── Email delivery (Resend) ────────────────────────────────────────────────
_RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
_RESEND_FROM = os.environ.get("RESEND_FROM_ADDRESS", "")

# ── OTP rate limiting (in-memory, per-identifier) ─────────────────────────
_OTP_COOLDOWN_SECONDS = 60  # minimum seconds between code requests per address
_otp_cooldown: dict[str, int] = {}  # identifier → last_request unix timestamp


# ── Pydantic models ────────────────────────────────────────────────────────


class RequestCodeBody(BaseModel):
    identifier: str


class RegisterBody(BaseModel):
    identifier: str
    password: str
    phone: str | None = None


class SupportTicketBody(BaseModel):
    name: str = ""
    email: str = ""
    message: str


class LoginBody(BaseModel):
    identifier: str
    password: str


class GoogleUpsertBody(BaseModel):
    sub: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None


class ResetPasswordBody(BaseModel):
    identifier: str
    code: str
    new_password: str


class SaveAiSettingsBody(BaseModel):
    provider: str = "gpt"
    apiBaseUrl: str = ""
    model: str = ""
    apiKey: str = ""


class SetSavedBody(BaseModel):
    savedIds: list[str]


class AiChatMessage(BaseModel):
    role: str
    content: str


class AiChatBody(BaseModel):
    provider: str = "gpt"
    apiBaseUrl: str | None = None
    apiKey: str | None = None
    model: str | None = None
    messages: list[AiChatMessage]
    context: str | None = None


class VerifyLinksBody(BaseModel):
    links: list[str]
    name: str | None = None
    institution: str | None = None


# ── Auth helpers ───────────────────────────────────────────────────────────


def _normalize(value: str) -> str:
    return value.strip().lower()


def _require_session(x_session_token: str | None) -> dict:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Login required.")
    user = auth_db.get_user_by_session(x_session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    return user


def _get_adc_access_token() -> str:
    # Prefer google.auth to obtain an OAuth access token with the
    # cloud-platform scope (works for Cloud Run, GKE, and local ADC).
    try:
        import google.auth
        import google.auth.transport.requests

        logger.info("ADC: google.auth available, attempting default credentials")
        creds, _ = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/generative-language",
            ],
        )
        request = google.auth.transport.requests.Request()
        try:
            creds.refresh(request)
            token = getattr(creds, "token", "") or ""
            if token:
                logger.info("ADC: google.auth refresh succeeded; token present")
                return token
            else:
                logger.info("ADC: google.auth refresh succeeded; token empty")
        except Exception as e:
            logger.info("ADC: google.auth refresh failed: %s", str(e))
    except Exception as e:
        logger.info("ADC: google.auth import/default failed: %s", str(e))

    # Fallback: try metadata server (Cloud Run / GCE)
    try:
        resp = http_requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
            timeout=2,
        )
        if resp.status_code == 200:
            logger.info("ADC: metadata server token fetched (status 200)")
            return resp.json().get("access_token", "")
        else:
            logger.info("ADC: metadata server returned status %s", resp.status_code)
    except Exception as e:
        logger.info("ADC: metadata server token fetch failed: %s", str(e))

    return ""


# E.164: + followed by 7–15 digits (first digit non-zero = no country code starting with 0)
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_phone(raw: str | None) -> str | None:
    """Strip spaces/dashes and validate E.164 format.

    Returns the cleaned phone number, or None if raw is empty/None.
    Raises HTTP 400 if the value is present but malformed.
    """
    if not raw:
        return None
    cleaned = raw.replace(" ", "").replace("-", "")
    if not _E164_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=(
                "Mobile number must be in international format, e.g. "
                "+1 650 555 0100 (US), +44 7700 900000 (UK), "
                "+49 151 12345678 (DE), +91 98765 43210 (IN)."
            ),
        )
    return cleaned


# ── OTP helpers ───────────────────────────────────────────────────────────


def _check_otp_rate_limit(identifier: str) -> None:
    """Raise HTTP 429 if a code was requested within the cooldown window.

    Also evicts stale entries (older than 5 min) to keep the dict bounded.
    """
    now = int(time.time())
    last = _otp_cooldown.get(identifier, 0)
    if now - last < _OTP_COOLDOWN_SECONDS:
        wait = _OTP_COOLDOWN_SECONDS - (now - last)
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait} seconds before requesting another code.",
        )
    # Evict entries idle for >5 minutes to prevent unbounded growth.
    cutoff = now - 300
    for k in [k for k, v in _otp_cooldown.items() if v < cutoff]:
        del _otp_cooldown[k]
    _otp_cooldown[identifier] = now


def _send_recovery_email(to_email: str, code: str) -> None:
    """Deliver the 6-digit OTP to the user via Resend.

    Raises HTTP 503 if RESEND_API_KEY / RESEND_FROM_ADDRESS are missing
    or if delivery fails, so the caller never silently swallows a failure.
    """
    if not _RESEND_API_KEY or not _RESEND_FROM:
        logger.error(
            "RESEND_API_KEY or RESEND_FROM_ADDRESS env var is missing. "
            "Set both on the Cloud Run service to enable email OTP delivery."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Email delivery is not configured on this server. "
                "Please contact support."
            ),
        )
    _resend.api_key = _RESEND_API_KEY
    try:
        _resend.Emails.send(
            {
                "from": _RESEND_FROM,
                "to": [to_email],
                "subject": "Your password recovery code",
                "html": (
                    "<div style='font-family:sans-serif;max-width:480px;margin:0 auto'>"
                    "<p style='color:#1a1a2e;font-size:15px'>Your Research AI recovery code is:</p>"
                    f"<p style='font-family:monospace;font-size:36px;letter-spacing:10px;"
                    f"color:#1a1a2e;margin:16px 0'><strong>{code}</strong></p>"
                    "<p style='color:#555;font-size:13px'>This code expires in <strong>10 minutes</strong>.</p>"
                    "<p style='color:#888;font-size:12px'>If you did not request a password reset, "
                    "you can safely ignore this email.</p>"
                    "</div>"
                ),
            }
        )
    except Exception as exc:
        logger.error("Resend delivery failed to %s: %s", to_email, exc)
        raise HTTPException(
            status_code=503,
            detail="Could not send the recovery email. Please try again.",
        )


# ── Auth routes ────────────────────────────────────────────────────────────


@router.post("/auth/request-code")
def request_code(body: RequestCodeBody):
    identifier = _normalize(body.identifier)
    if not identifier:
        raise HTTPException(status_code=400, detail="Email address is required.")
    if identifier.startswith("+"):
        # Phone OTP not yet implemented — guide the user clearly.
        raise HTTPException(
            status_code=400,
            detail="Phone recovery is not yet available. Please use your email address.",
        )
    _check_otp_rate_limit(identifier)
    code = str(secrets.randbelow(900000) + 100000)  # 6-digit code
    auth_db.upsert_verification_code(identifier, code)
    _send_recovery_email(identifier, code)  # raises 503 on misconfiguration / failure
    response: dict = {"ok": True}
    if SHOW_DEV_CODE:
        response["devCode"] = code
    return response


@router.post("/auth/register")
def register(body: RegisterBody):
    identifier = _normalize(body.identifier)
    password = body.password
    if not identifier or len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Email and password (≥6 chars) are required.",
        )
    phone = _validate_phone(body.phone)  # raises 400 if present but malformed
    if auth_db.get_user_by_identifier(identifier):
        raise HTTPException(status_code=409, detail="This account already exists.")
    user = auth_db.create_password_user(identifier, password, phone)
    token = auth_db.create_session(user["id"])
    return {"token": token, "user": user}


@router.post("/auth/login")
def login(body: LoginBody):
    identifier = _normalize(body.identifier)
    raw = auth_db.get_user_by_identifier(identifier)
    if not raw or not auth_db.check_password(
        body.password, raw.get("password_hash", "")
    ):
        raise HTTPException(status_code=401, detail="Invalid account or password.")
    token = auth_db.create_session(raw["id"])
    user = auth_db._row_to_user(raw)
    return {"token": token, "user": user}


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordBody):
    identifier = _normalize(body.identifier)
    if not identifier or len(body.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Identifier and password (≥6 chars) are required.",
        )
    if not auth_db.consume_verification_code(identifier, body.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid or expired recovery code.")
    auth_db.update_password_hash(identifier, body.new_password)
    return {"ok": True}


@router.post("/auth/logout")
def logout(x_session_token: str | None = Header(None)):
    if x_session_token:
        auth_db.delete_session(x_session_token)
    return {"ok": True}


@router.get("/auth/me")
def me(x_session_token: str | None = Header(None)):
    if not x_session_token:
        return {"user": None}
    user = auth_db.get_user_by_session(x_session_token)
    return {"user": user}


@router.post("/auth/google-upsert")
def google_upsert(body: GoogleUpsertBody):
    """
    Called by the frontend BFF after it completes the Google OAuth token exchange.
    The frontend verifies the Google profile server-side; we just upsert the user.
    """
    if not body.sub:
        raise HTTPException(status_code=400, detail="Google sub is required.")
    user = auth_db.upsert_google_user(body.sub, body.email, body.name, body.picture)
    token = auth_db.create_session(user["id"])
    return {"token": token, "user": user}


# ── Support tickets ────────────────────────────────────────────────────────


@router.post("/support")
def create_support_ticket(
    body: SupportTicketBody,
    x_session_token: str | None = Header(None),
):
    """Save a support ticket to the database.

    Optionally associates the ticket with a logged-in user.
    Never returns any user message content in the response.
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")
    user_id: str | None = None
    if x_session_token:
        user = auth_db.get_user_by_session(x_session_token)
        if user:
            user_id = user["id"]
    ticket_id = auth_db.create_support_ticket(
        message=body.message.strip(),
        name=body.name.strip(),
        email=body.email.strip(),
        user_id=user_id,
    )
    return {"ok": True, "ticketId": ticket_id}


# ── AI Settings ────────────────────────────────────────────────────────────


@router.get("/settings/ai")
def get_ai_settings(x_session_token: str | None = Header(None)):
    user = _require_session(x_session_token)
    settings = auth_db.get_ai_settings(user["id"])
    if not settings:
        return {"provider": None, "apiBaseUrl": None, "model": None, "hasApiKey": False}
    return {
        "provider": settings["provider"],
        "apiBaseUrl": settings["apiBaseUrl"] or None,
        "model": settings["model"] or None,
        "hasApiKey": settings["hasApiKey"],
    }


@router.put("/settings/ai")
def save_ai_settings(
    body: SaveAiSettingsBody, x_session_token: str | None = Header(None)
):
    user = _require_session(x_session_token)
    try:
        auth_db.save_ai_settings(
            user_id=user["id"],
            provider=body.provider.strip() or "gpt",
            base_url=body.apiBaseUrl.strip(),
            model_id=body.model.strip(),
            api_key=body.apiKey.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    settings = auth_db.get_ai_settings(user["id"])
    return {"ok": True, "hasApiKey": bool(settings and settings["hasApiKey"])}


# ── Saved researchers ──────────────────────────────────────────────────────


@router.get("/saved-researchers")
def get_saved(x_session_token: str | None = Header(None)):
    user = _require_session(x_session_token)
    return {"savedIds": auth_db.get_saved_researchers(user["id"])}


@router.put("/saved-researchers")
def set_saved(body: SetSavedBody, x_session_token: str | None = Header(None)):
    user = _require_session(x_session_token)
    ids = [str(i) for i in body.savedIds]
    saved = auth_db.set_saved_researchers(user["id"], ids)
    return {"savedIds": saved}


# ── AI Chat ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are ResearchAI, an academic search assistant. "
    "Be concise, practical, and grounded in the supplied researcher context. "
    "Do not mention any company, sponsor, business use case, or private organizational context."
)


def _openai_chat(
    api_key: str,
    model: str,
    base_url: str,
    messages: list[AiChatMessage],
    context: str | None,
) -> str:
    base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
    model = model or "gpt-4o"
    full_messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context:
        full_messages.append({"role": "system", "content": context})
    full_messages.extend({"role": m.role, "content": m.content} for m in messages)
    body: dict = {"model": model, "messages": full_messages}
    if not re.match(r"^gpt-5", model):
        body["temperature"] = 0.3
    resp = http_requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise ValueError("AI response did not include a message.")
    return content


def _gemini_chat(
    api_key: str,
    model: str,
    base_url: str,
    messages: list[AiChatMessage],
    context: str | None,
    access_token: str | None = None,
) -> str:
    model = model or "gemini-2.5-flash"
    base_url = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip(
        "/"
    )
    # Preserve the incoming model string for matching and avoid altering
    # the canonical model identifier returned by ListModels. Do NOT strip
    # suffixes like '-flash' because ListModels names are authoritative.
    requested_model = model or ""
    prompt_parts = [_SYSTEM_PROMPT, context or ""] + [
        f"{m.role}: {m.content}" for m in messages
    ]
    prompt = "\n\n".join(p for p in prompt_parts if p)

    if access_token:
        # When using ADC (service account access token) for the demo user,
        # query the Generative Language ModelService to find a model that
        # actually supports `generateContent` in this project/region. Use
        # the model `name` returned by the API (often `models/...`) which
        # is safe to call directly.
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        try:
            list_url = f"{base_url}/models"
            logger.info("Generativelanguage ListModels request: url=%s", list_url)
            list_resp = http_requests.get(list_url, headers=headers, timeout=10)
            models_json = list_resp.json() if list_resp.status_code == 200 else {}
            candidates = models_json.get("models", []) if isinstance(models_json, dict) else []
        except Exception as e:
            logger.info("Generativelanguage ListModels failed: %s", str(e))
            candidates = []

        # Prefer an explicit model that contains the original requested
        # model string (exact match), then prefer any model that contains
        # 'gemini' and advertises a generate-like method. If none found,
        # fall back to the incoming `model` value (normalized later).
        found_model_name = None
        for m in candidates:
            name = m.get("name", "") or ""
            disp = (m.get("displayName") or "").lower()
            # Accept several possible field names returned by different
            # API versions: 'supportedMethods', 'supported_methods',
            # and 'supportedGenerationMethods'. Lowercase for comparison.
            methods = (
                m.get("supportedMethods")
                or m.get("supported_methods")
                or m.get("supportedGenerationMethods")
                or m.get("supported_generation_methods")
                or []
            )
            methods = [str(x).lower() for x in methods]
            # Consider any method mentioning 'generate' as a candidate.
            if any("generate" in mm for mm in methods):
                # Prefer exact matches to the original requested model string
                if requested_model and requested_model.lower() in name.lower():
                    found_model_name = name
                    break
                # Prefer gemini models when available
                if "gemini" in name.lower() or "gemini" in disp:
                    found_model_name = name
                    break
                if not found_model_name:
                    found_model_name = name

        # If we found a model name from the ListModels response, use it.
        # Otherwise, fall back to the incoming `model` parameter.
        if found_model_name:
            model_name_to_call = found_model_name
        else:
            # ensure model is in the form 'models/...' for the generateContent path
            if model and model.startswith("models/"):
                model_name_to_call = model
            elif model:
                model_name_to_call = f"models/{model.lstrip('/') }"
            else:
                # No model found via ListModels and no model was supplied.
                # Do NOT fall back to hard-coded models (eg. text-bison).
                raise ValueError(
                    "No Gemini model found via ListModels and no model supplied. "
                    "Call /debug/list-models to inspect available models for ADC."
                )

        try:
            logger.info("Generativelanguage ADC request: chosen_model=%r base_url=%r", model_name_to_call, base_url)
        except Exception:
            logger.info("Generativelanguage ADC request unreadable")
        # Use the same request shape as the Generativelanguage generateContent
        # call so the Vertex `:generateContent` endpoint receives the prompt
        # and generation config. Keep temperature low for deterministic output.
        resp = http_requests.post(
            f"{base_url}/{model_name_to_call}:generateContent" if not model_name_to_call.startswith(base_url) else f"{model_name_to_call}:generateContent",
            headers=headers,
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3},
            },
            timeout=60,
        )
        # If the model isn't available for this API version (404), log a
        # clear diagnostic and allow the error to be raised so callers can
        # see the precise provider response. Do NOT fall back to other
        # models here — fallbacks risk calling unsupported APIs.
        if resp.status_code == 404:
            try:
                logger.info("Generativelanguage model %s not found for generateContent; status=404", model_name_to_call)
            except Exception:
                pass
        # Log Vertex response for diagnostics (helps surface detailed error bodies)
        try:
            logger.info("Vertex generateContent response: %s %s", resp.status_code, resp.text)
        except Exception:
            logger.info("Vertex generateContent response unreadable")
    else:
        if not api_key:
            raise ValueError("No API key provided for Gemini call.")
        url = f"{base_url}/models/{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
        resp = http_requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3},
            },
            timeout=60,
        )

        # Log the request URL (safe) for diagnostics when provider returns errors.
        try:
            logger.info("Gemini generateContent request url: %s", url)
        except Exception:
            pass

    try:
        resp.raise_for_status()
    except Exception as exc:
        # Surface provider error bodies for easier debugging.
        try:
            body_text = resp.text
        except Exception:
            body_text = "(unreadable response body)"
        raise ValueError(f"Gemini provider error: {body_text}") from exc
    resp_json = resp.json()
    # Try several response shapes: generativelanguage (`candidates`),
    # Vertex predict (`predictions`), or a simple string
    content = ""
    if isinstance(resp_json, dict):
        if "candidates" in resp_json:
            parts = (
                resp_json.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            )
            content = "".join(p.get("text", "") for p in parts)
        elif "predictions" in resp_json and isinstance(
            resp_json.get("predictions"), list
        ):
            p0 = resp_json.get("predictions", [None])[0]
            if isinstance(p0, dict):
                content = p0.get("content") or p0.get("output") or p0.get("text") or ""
            elif isinstance(p0, str):
                content = p0
        else:
            # Fallback: stringify the response body (useful for debugging)
            content = str(resp_json)
    elif isinstance(resp_json, list) and resp_json:
        first = resp_json[0]
        if isinstance(first, dict):
            content = first.get("content") or first.get("text") or ""
        elif isinstance(first, str):
            content = first
    if not content:
        raise ValueError("Gemini response did not include text.")
    return content


def _claude_chat(
    api_key: str,
    model: str,
    base_url: str,
    messages: list[AiChatMessage],
    context: str | None,
) -> str:
    model = model or "claude-sonnet-4-20250514"
    base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")
    system_parts = [_SYSTEM_PROMPT, context or ""] + [
        m.content for m in messages if m.role == "system"
    ]
    system = "\n\n".join(p for p in system_parts if p)
    non_system = [
        {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
        for m in messages
        if m.role != "system"
    ]
    resp = http_requests.post(
        f"{base_url}/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": non_system,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = "".join(
        p.get("text", "")
        for p in resp.json().get("content", [])
        if p.get("type") == "text"
    )
    if not content:
        raise ValueError("Claude response did not include text.")
    return content


@router.post("/ai/chat")
def ai_chat(body: AiChatBody, x_session_token: str | None = Header(None)):
    if not body.messages:
        raise HTTPException(
            status_code=400, detail="At least one chat message is required."
        )

    provider = body.provider or "gpt"
    base_url = body.apiBaseUrl or ""
    model = (body.model or "").strip()

    # Strict policy: require authenticated user with a stored API key. No
    # fallbacks, ADC, or client-supplied keys are allowed.
    if not x_session_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in and add your API key in Settings.",
        )

    user = auth_db.get_user_by_session(x_session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session. Please log in.")

    stored = auth_db.get_ai_settings(user["id"])

    api_key = ""
    access_token = None

    if stored and stored.get("apiKey"):
        api_key = stored["apiKey"]
        provider = body.provider or stored.get("provider", "gpt")
        base_url = body.apiBaseUrl or stored.get("apiBaseUrl", "") or ""
        model = model or stored.get("model", "")
    else:
        # No stored API key. Allow ADC only for the official demo user id.
        if user.get("id") == DEMO_USER_ID:
            access_token = _get_adc_access_token()
            if not access_token:
                raise HTTPException(
                    status_code=401,
                    detail="No AI API key configured. Please add your API key in Settings.",
                )
            provider = body.provider or "gemini"
            base_url = body.apiBaseUrl or ""
            model = model or "gemini-2.5-flash"
        else:
            # Non-demo users must have a stored key
            raise HTTPException(
                status_code=401,
                detail="No AI API key configured. Please add your API key in Settings.",
            )

    try:
        if provider == "gemini":
            answer = _gemini_chat(
                api_key,
                model,
                base_url,
                body.messages,
                body.context,
                access_token=access_token,
            )
        elif provider == "claude":
            answer = _claude_chat(api_key, model, base_url, body.messages, body.context)
        else:
            answer = _openai_chat(api_key, model, base_url, body.messages, body.context)
        return {"answer": answer}
    except http_requests.HTTPError as exc:
        # Try to parse provider error body for clearer mapping.
        try:
            err_json = exc.response.json()
            detail_msg = err_json.get("error", {}).get("message") or str(exc)
            err_status = err_json.get("error", {}).get("status") or ""
            err_code = err_json.get("error", {}).get("code")
        except Exception:
            detail_msg = str(exc)
            err_status = ""
            err_code = None

        detail_lower = detail_msg.lower() if isinstance(detail_msg, str) else ""
        billing_depleted = (
            "prepay" in detail_lower
            or "credit" in detail_lower
            or "billing" in detail_lower
            or "payment" in detail_lower
        )
        rate_or_quota_limited = (
            err_code == 429
            or err_status == "RESOURCE_EXHAUSTED"
            or "rate limit" in detail_lower
            or "too many requests" in detail_lower
            or "quota" in detail_lower
            or "resource_exhausted" in detail_lower
        )

        # Distinguish exhausted billing from generic rate/quota throttling.
        if billing_depleted:
            raise HTTPException(
                status_code=402,
                detail=(
                    "AI provider billing exhausted: project prepay credits are depleted. "
                    "Manage billing and add credits at https://ai.studio/projects to resume demo."
                ),
            ) from exc

        if rate_or_quota_limited:
            raise HTTPException(
                status_code=429,
                detail=(
                    "AI provider rate limit or quota reached. "
                    "Please retry shortly, switch model/provider, or verify quota in your provider console."
                ),
            ) from exc

        raise HTTPException(status_code=502, detail=detail_msg) from exc
    except Exception as exc:
        msg = str(exc)
        msg_lower = msg.lower()
        if "prepay" in msg_lower or "credit" in msg_lower or "billing" in msg_lower or "payment" in msg_lower:
            raise HTTPException(
                status_code=402,
                detail=(
                    "AI provider billing exhausted: project prepay credits are depleted. "
                    "Manage billing and add credits at https://ai.studio/projects to resume demo."
                ),
            )
        if "resource_exhausted" in msg_lower or "rate limit" in msg_lower or "too many requests" in msg_lower or "quota" in msg_lower:
            raise HTTPException(
                status_code=429,
                detail=(
                    "AI provider rate limit or quota reached. "
                    "Please retry shortly, switch model/provider, or verify quota in your provider console."
                ),
            )
        raise HTTPException(status_code=400, detail=msg)


@router.post("/ai/verify-links")
def verify_links(body: VerifyLinksBody):
    """
    Verify that candidate links are live and plausibly about the requested
    researcher/institution. Returns a list of verified links with optional
    simple label (hostname or provided snippet).
    This endpoint is intentionally permissive (no auth) because link
    verification requires no privileged access.
    """
    # Use the robust verifier implemented in link_verifier.py. This applies
    # multiple signals (provider patterns, title/meta, JSON-LD, URL patterns,
    # affiliation tokens) and returns only high-confidence matches.
    if not body.links:
        return {"verified": []}

    # The verifier expects raw links and will normalize scheme where needed.
    try:
        results = link_verifier.verify_and_rank(body.links, body.name, body.institution, threshold=0.75)
    except Exception as exc:
        logger.exception("link_verifier failed: %s", exc)
        return {"verified": []}

    # Convert to the previous response shape but include a confidence score.
    verified = []
    for r in results:
        verified.append({"url": r.get("url"), "label": r.get("label"), "score": r.get("score")})
    return {"verified": verified}


@router.get("/debug/list-models")
def debug_list_models(x_session_token: str | None = Header(None)):
    """Return the raw Generative Language ModelService ListModels output.

    Restricted to the demo user so it can be called from the frontend for
    diagnostics when ADC is in use.
    """
    user = _require_session(x_session_token)
    if user.get("id") != DEMO_USER_ID:
        raise HTTPException(status_code=403, detail="Forbidden")

    access_token = _get_adc_access_token()
    if not access_token:
        raise HTTPException(status_code=401, detail="No ADC access token available.")

    base_url = "https://generativelanguage.googleapis.com/v1beta"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        resp = http_requests.get(f"{base_url}/models", headers=headers, timeout=10)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"status_code": resp.status_code, "body": body}
    except Exception as exc:
        logger.exception("debug_list_models failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
