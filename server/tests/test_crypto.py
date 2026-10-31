import pytest
from cryptography.fernet import InvalidToken

from app.services.crypto import decrypt_json, encrypt_json
from test_myscheme import recorded


def test_encryption_round_trip_with_recorded_unicode():
    data = recorded("myscheme-pm-kisan.json")["en"]["schemeContent"]
    encrypted = encrypt_json(data)
    assert decrypt_json(encrypted) == data
    assert data["briefDescription"] not in encrypted
    assert encrypt_json(data) != encrypted
    assert decrypt_json(None) == {}
    with pytest.raises(InvalidToken):
        decrypt_json(encrypted[:-4] + "xxxx")
