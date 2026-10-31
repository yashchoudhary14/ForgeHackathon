"""Encrypt profile JSON; a missing secret is explicitly process-local."""
import json
import logging

from cryptography.fernet import Fernet

from ..config import get_settings

log = logging.getLogger(__name__)
_secret = get_settings().profile_secret
if not _secret:
    _secret = Fernet.generate_key()
    log.warning("PROFILE_SECRET is empty; generated an ephemeral profile encryption key. "
                "Set PROFILE_SECRET to retain access to profiles after a restart.")
_fernet = Fernet(_secret.encode("ascii") if isinstance(_secret, str) else _secret)
del _secret


def encrypt_json(d: dict) -> str:
    return _fernet.encrypt(json.dumps(d, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decrypt_json(s: str | None) -> dict:
    if not s:
        return {}
    value = json.loads(_fernet.decrypt(s.encode("ascii")).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Encrypted profile payload must be an object")
    return value
