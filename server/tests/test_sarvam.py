import pytest

from app.services import sarvam
from test_myscheme import recorded
from app.services.markdown import to_markdown


@pytest.mark.parametrize("lang", ["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "od"])
def test_language_codes(lang):
    assert sarvam.language_code(lang) == lang + "-IN"
    assert sarvam.app_language(lang + "-IN") == lang


def test_odia_alias_and_unknown_language():
    assert sarvam.app_language("or-IN") == "od"
    with pytest.raises(ValueError):
        sarvam.app_language("unknown")


def test_long_text_chunks_preserve_source():
    text = to_markdown(recorded("myscheme-pm-kisan.json")["en"]["schemeContent"]["exclusions"])
    for limit in (1000, 2500):
        chunks = sarvam.split_text(text, limit)
        assert "".join(chunks) == text
        assert all(0 < len(chunk) <= limit for chunk in chunks)


@pytest.mark.asyncio
async def test_tts_missing_key_is_explicit(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(sarvam, "get_settings", lambda: SimpleNamespace(sarvam_api_key=""))
    with pytest.raises(RuntimeError, match="SARVAM_API_KEY"):
        await sarvam.tts("नमस्ते", "hi")
