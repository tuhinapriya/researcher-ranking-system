"""
Database layer for app-level auth, sessions, AI settings, and saved researchers.

Tables (all created via init_auth_tables()):
  app_users           — registered users (bcrypt password hash)
  app_sessions        — session tokens (14-day TTL by default)
  verification_codes  — short-lived OTP codes for registration
  user_ai_settings    — per-user AI provider / encrypted API key
  saved_researchers   — per-user list of saved researcher IDs
"""

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

import bcrypt

from db import get_connection

logger = logging.getLogger(__name__)

SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "14"))
CODE_TTL_SECONDS = 10 * 60  # 10 minutes


# ── Schema ─────────────────────────────────────────────────────────────────


def init_auth_tables() -> None:
    """CREATE TABLE IF NOT EXISTS for every auth table."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id            VARCHAR(36)  PRIMARY KEY,
                identifier    VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL DEFAULT '',
                created_at    DATETIME     NOT NULL,
                provider      VARCHAR(32)  NOT NULL DEFAULT 'password',
                provider_id   VARCHAR(255),
                display_name  VARCHAR(255),
                avatar_url    TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_sessions (
                token      VARCHAR(64) PRIMARY KEY,
                user_id    VARCHAR(36) NOT NULL,
                expires_at BIGINT      NOT NULL,
                INDEX idx_app_sessions_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                identifier VARCHAR(255) PRIMARY KEY,
                code       VARCHAR(10)  NOT NULL,
                expires_at BIGINT       NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_ai_settings (
                user_id           VARCHAR(36)   PRIMARY KEY,
                provider          VARCHAR(64)   NOT NULL DEFAULT 'gpt',
                base_url          VARCHAR(1024) NOT NULL DEFAULT '',
                model_id          VARCHAR(255)  NOT NULL DEFAULT '',
                api_key_encrypted TEXT,
                api_key_iv        VARCHAR(64),
                api_key_auth_tag  VARCHAR(64)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS saved_researchers (
                user_id       VARCHAR(36)  NOT NULL,
                researcher_id VARCHAR(255) NOT NULL,
                PRIMARY KEY (user_id, researcher_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        logger.info("Auth tables initialised.")
    finally:
        cur.close()
        conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _row_to_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "identifier": row["identifier"],
        "createdAt": (
            row["created_at"].isoformat()
            if isinstance(row["created_at"], datetime)
            else str(row["created_at"])
        ),
        "provider": row.get("provider") or "password",
        "displayName": row.get("display_name"),
        "avatarUrl": row.get("avatar_url"),
    }


# ── Session management ─────────────────────────────────────────────────────


def create_session(user_id: str) -> str:
    token = secrets.token_hex(32)
    expires_at = _now_ms() + SESSION_DAYS * 24 * 60 * 60 * 1000
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO app_sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return token


def get_user_by_session(token: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT user_id FROM app_sessions WHERE token = %s AND expires_at > %s",
            (token, _now_ms()),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("SELECT * FROM app_users WHERE id = %s", (row["user_id"],))
        user_row = cur.fetchone()
        return _row_to_user(user_row) if user_row else None
    finally:
        cur.close()
        conn.close()


def delete_session(token: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM app_sessions WHERE token = %s", (token,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


# ── Verification codes ─────────────────────────────────────────────────────


def upsert_verification_code(identifier: str, code: str) -> None:
    expires_at = _now_ms() + CODE_TTL_SECONDS * 1000
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "REPLACE INTO verification_codes (identifier, code, expires_at) VALUES (%s, %s, %s)",
            (identifier, code, expires_at),
        )
        cur.execute(
            "DELETE FROM verification_codes WHERE expires_at <= %s", (_now_ms(),)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def consume_verification_code(identifier: str, code: str) -> bool:
    """Return True and delete the code if it matches and is not expired."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT code, expires_at FROM verification_codes WHERE identifier = %s",
            (identifier,),
        )
        row = cur.fetchone()
        if not row or row["code"] != code or row["expires_at"] <= _now_ms():
            return False
        cur.execute(
            "DELETE FROM verification_codes WHERE identifier = %s", (identifier,)
        )
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()


# ── User management ────────────────────────────────────────────────────────


def get_user_by_identifier(identifier: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM app_users WHERE identifier = %s", (identifier,))
        row = cur.fetchone()
        return row  # raw row (includes password_hash) — for internal use
    finally:
        cur.close()
        conn.close()


def create_password_user(identifier: str, password: str) -> dict:
    """Hash password with bcrypt, insert user row, return public user dict."""
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # store as UTC naive
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO app_users (id, identifier, password_hash, created_at, provider) VALUES (%s, %s, %s, %s, %s)",
            (user_id, identifier, password_hash, now, "password"),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return {
        "id": user_id,
        "identifier": identifier,
        "createdAt": now.isoformat(),
        "provider": "password",
        "displayName": None,
        "avatarUrl": None,
    }


def check_password(raw_password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw_password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def update_password_hash(identifier: str, new_password: str) -> bool:
    """Hash new_password with bcrypt and update the stored hash.

    Only updates accounts with provider='password' (not OAuth accounts).
    Returns True if a row was updated, False if the account was not found.
    """
    new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE app_users SET password_hash = %s WHERE identifier = %s AND provider = 'password'",
            (new_hash, identifier),
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        cur.close()
        conn.close()


def upsert_google_user(
    sub: str, email: str | None, name: str | None, picture: str | None
) -> dict:
    """Find or create a Google user; update display_name/avatar_url. Returns public user dict."""
    identifier = (email or f"google:{sub}").strip().lower()
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        # Look up by provider_id first, then by identifier
        cur.execute(
            "SELECT * FROM app_users WHERE provider = 'google' AND provider_id = %s",
            (sub,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT * FROM app_users WHERE identifier = %s", (identifier,))
            row = cur.fetchone()

        if not row:
            user_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cur.execute(
                "INSERT INTO app_users (id, identifier, password_hash, created_at, provider, provider_id, display_name, avatar_url) VALUES (%s, %s, '', %s, 'google', %s, %s, %s)",
                (user_id, identifier, now, sub, name, picture),
            )
            conn.commit()
            return {
                "id": user_id,
                "identifier": identifier,
                "createdAt": now.isoformat(),
                "provider": "google",
                "displayName": name,
                "avatarUrl": picture,
            }
        else:
            cur.execute(
                "UPDATE app_users SET provider_id = COALESCE(provider_id, %s), display_name = COALESCE(%s, display_name), avatar_url = COALESCE(%s, avatar_url) WHERE id = %s",
                (sub, name, picture, row["id"]),
            )
            conn.commit()
            return _row_to_user(
                {
                    **row,
                    "display_name": name or row.get("display_name"),
                    "avatar_url": picture or row.get("avatar_url"),
                }
            )
    finally:
        cur.close()
        conn.close()


# ── AI Settings ────────────────────────────────────────────────────────────


def _get_enc_key() -> bytes | None:
    hex_key = (os.environ.get("AI_SETTINGS_ENCRYPTION_KEY") or "").strip()
    if not hex_key:
        return None
    buf = bytes.fromhex(hex_key)
    return buf if len(buf) == 32 else None


def encrypt_api_key(api_key: str) -> tuple[str, str, str] | None:
    """Returns (ciphertext_hex, iv_hex, tag_hex) or None if no key configured."""
    key = _get_enc_key()
    if not key:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, api_key.encode("utf-8"), None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]
    return ciphertext.hex(), nonce.hex(), tag.hex()


def decrypt_api_key(encrypted_hex: str, iv_hex: str, tag_hex: str) -> str:
    key = _get_enc_key()
    if not key:
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(key)
        nonce = bytes.fromhex(iv_hex)
        ct_with_tag = bytes.fromhex(encrypted_hex) + bytes.fromhex(tag_hex)
        return aesgcm.decrypt(nonce, ct_with_tag, None).decode("utf-8")
    except Exception:
        return ""


def get_ai_settings(user_id: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM user_ai_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        api_key = ""
        if (
            row.get("api_key_encrypted")
            and row.get("api_key_iv")
            and row.get("api_key_auth_tag")
        ):
            api_key = decrypt_api_key(
                row["api_key_encrypted"], row["api_key_iv"], row["api_key_auth_tag"]
            )
        return {
            "provider": row.get("provider") or "gpt",
            "apiBaseUrl": row.get("base_url") or "",
            "model": row.get("model_id") or "",
            "apiKey": api_key,
            "hasApiKey": bool(row.get("api_key_encrypted")),
        }
    finally:
        cur.close()
        conn.close()


def save_ai_settings(
    user_id: str, provider: str, base_url: str, model_id: str, api_key: str
) -> bool:
    """Returns True if saved OK. Raises ValueError if api_key provided but no enc key."""
    enc_hex = iv_hex = tag_hex = None
    if api_key:
        result = encrypt_api_key(api_key)
        if result is None:
            raise ValueError(
                "AI_SETTINGS_ENCRYPTION_KEY is not configured. API key cannot be stored securely."
            )
        enc_hex, iv_hex, tag_hex = result

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO user_ai_settings (user_id, provider, base_url, model_id, api_key_encrypted, api_key_iv, api_key_auth_tag)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                provider = VALUES(provider),
                base_url = VALUES(base_url),
                model_id = VALUES(model_id),
                api_key_encrypted = COALESCE(VALUES(api_key_encrypted), api_key_encrypted),
                api_key_iv        = COALESCE(VALUES(api_key_iv),        api_key_iv),
                api_key_auth_tag  = COALESCE(VALUES(api_key_auth_tag),  api_key_auth_tag)
        """,
            (user_id, provider, base_url, model_id, enc_hex, iv_hex, tag_hex),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return True


# ── Saved researchers ──────────────────────────────────────────────────────


def get_saved_researchers(user_id: str) -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT researcher_id FROM saved_researchers WHERE user_id = %s", (user_id,)
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def set_saved_researchers(user_id: str, ids: list[str]) -> list[str]:
    unique_ids = list(dict.fromkeys(ids))[:1000]
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("START TRANSACTION")
        cur.execute("DELETE FROM saved_researchers WHERE user_id = %s", (user_id,))
        if unique_ids:
            cur.executemany(
                "INSERT INTO saved_researchers (user_id, researcher_id) VALUES (%s, %s)",
                [(user_id, rid) for rid in unique_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return unique_ids
