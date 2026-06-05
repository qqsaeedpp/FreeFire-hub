"""Lightweight symmetric encryption for sensitive account credentials.

Account email/password/backup-code are stored encrypted at rest. The key is
derived from the bot token so no extra secret management is required, but you
can override it with an explicit ENCRYPTION_KEY in production.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _build_key() -> bytes:
    raw = os.getenv("ENCRYPTION_KEY") or settings.bot_token
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_build_key())


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
