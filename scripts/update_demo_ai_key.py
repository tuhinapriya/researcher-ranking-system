"""
One-shot script: update the Lam Research demo account's Gemini API key
in user_ai_settings using the same AES-GCM encryption the app uses.

Usage:
    python scripts/update_demo_ai_key.py

The script prompts for the key with no terminal echo (like a password prompt).
The key is never written to disk or displayed.
"""

import getpass
import os
import sys

import mysql.connector
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ── Config ────────────────────────────────────────────────────────────────────
DEMO_USER_ID = "d5a3b5dd-8c14-4765-8e04-40834555f086"
ENC_KEY_HEX = "b197cc066bca1a0bbde54f563835bc73bc1da08b52f00a268750fbd815290d5e"
DB_HOST = "127.0.0.1"
DB_PORT = 3308  # Cloud SQL proxy port
DB_USER = "researcher_user"
DB_PASS = "practicum"
DB_NAME = "researcher_db"

# ── Prompt for key (no echo) ──────────────────────────────────────────────────
print("Enter the new Lam Research Gemini API key (input hidden):")
api_key = getpass.getpass(prompt="Gemini API key: ").strip()

if not api_key:
    print("ERROR: No key entered. Aborting.")
    sys.exit(1)

# ── Encrypt ───────────────────────────────────────────────────────────────────
key_bytes = bytes.fromhex(ENC_KEY_HEX)
nonce = os.urandom(12)
aesgcm = AESGCM(key_bytes)
ct_with_tag = aesgcm.encrypt(nonce, api_key.encode("utf-8"), None)
enc_hex = ct_with_tag[:-16].hex()
iv_hex = nonce.hex()
tag_hex = ct_with_tag[-16:].hex()

# ── Write to DB ───────────────────────────────────────────────────────────────
conn = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASS,
    database=DB_NAME,
)
cur = conn.cursor()
cur.execute(
    """
    UPDATE user_ai_settings
    SET provider          = 'gemini',
        model_id          = 'gemini-2.5-flash',
        base_url          = '',
        api_key_encrypted = %s,
        api_key_iv        = %s,
        api_key_auth_tag  = %s
    WHERE user_id = %s
    """,
    (enc_hex, iv_hex, tag_hex, DEMO_USER_ID),
)
conn.commit()
rows = cur.rowcount
cur.close()
conn.close()

if rows == 1:
    print("Success: Gemini API key updated for demo.lamresearch@gmail.com.")
else:
    print(f"WARNING: {rows} rows affected — expected 1. Check the user_id.")
