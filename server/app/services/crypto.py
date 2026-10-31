"""Encrypt sensitive profile fields using the deployment's Fernet key."""
import json

from cryptography.fernet import Fernet

from ..config import get_settings


def _cipher() -> Fernet:
    secret = get_settings().profile_secret
    if not secret:
        raise RuntimeError("PROFILE_SECRET must be configured before saving sensitive profile fields")
    return Fernet(secret.encode("ascii"))


def encrypt_json(data: dict) -> str:
    return _cipher().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decrypt_json(value: str | None) -> dict:
    if not value:
        return {}
    data = json.loads(_cipher().decrypt(value.encode("ascii")))
    if not isinstance(data, dict):
        raise ValueError("Encrypted profile must contain a JSON object")
    return data
