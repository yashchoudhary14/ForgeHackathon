"""Boundary checks for the real-source adapters; HTTP is mocked only in tests."""
import json
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.services import crypto, feeds, myscheme


def http_client(monkeypatch, module, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))


def test_profile_filters_include_schemes_open_to_all():
    filters = myscheme._filters({
        "state": "Andaman and Nicobar Islands", "caste": "sc", "gender": "female",
        "residence": "rural", "age": 20, "is_student": True, "is_bpl": False,
    })
    assert {"identifier": "beneficiaryState", "value": "Andaman and Nicobar Islands"} in filters
    assert {"identifier": "beneficiaryState", "value": "All"} in filters
    assert {"identifier": "caste", "value": "Scheduled Caste (SC)"} in filters
    assert {"identifier": "caste", "value": "All"} in filters
    assert {"identifier": "gender", "value": "All"} in filters
    assert {"identifier": "residence", "value": "Both"} in filters
    assert {"identifier": "isStudent", "value": "Yes"} in filters
    assert {"identifier": "isBpl", "value": "No"} in filters
    assert {"identifier": "age-sc", "min": 20, "max": 20} in filters


async def test_search_sends_official_query_and_deduplicates_slugs(monkeypatch):
    def handler(request):
        assert str(request.url).startswith("https://www.myscheme.gov.in/api/apisetu/search/schemes?")
        assert request.url.params["keyword"] == "scholarship"
        assert json.loads(request.url.params["q"])[0] == {"identifier": "beneficiaryState", "value": "Bihar"}
        item = {"fields": {"slug": "test", "schemeName": "Source title", "briefDescription": "Source words", "beneficiaryState": ["Bihar"]}}
        return httpx.Response(200, json={"data": {"summary": {"total": 2}, "hits": {"items": [item, item]}}})

    http_client(monkeypatch, myscheme, handler)
    result = await myscheme.search("scholarship", {"state": "Bihar"}, 0, 8)
    assert result.total == 2 and len(result.items) == 1
    assert result.items[0].brief == "Source words"


async def test_upstream_failure_never_returns_fabricated_schemes(monkeypatch):
    http_client(monkeypatch, myscheme, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await myscheme.search("scholarship", {}, 0, 8)


def test_details_preserve_source_markdown_and_rich_text():
    data = {"_id": "id", "slug": "test", "en": {
        "basicDetails": {"schemeName": "Official title"},
        "schemeContent": {"benefits_md": "- Exact source benefit."},
        "eligibilityCriteria": {"eligibilityDescription_md": "Exact source criterion."},
        "applicationProcess": [{"mode": "Online", "process": [{"type": "paragraph", "children": [
            {"text": "Visit the "}, {"type": "link", "children": [{"text": "portal"}]}, {"text": "."},
        ]}]}],
    }}
    documents = {"en": {"documentsRequired_md": "Exact source documents."}}
    detail = myscheme._detail(data, documents, None, "en")
    assert detail.benefits_md == "- Exact source benefit."
    assert detail.eligibility_md == "Exact source criterion."
    assert detail.application[0].steps_md == "Visit the portal."
    assert detail.documents_md == "Exact source documents."
    assert detail.source_url == "https://www.myscheme.gov.in/schemes/test"
    with pytest.raises(LookupError):
        myscheme._detail(data, documents, None, "hi")


def test_sensitive_profile_encryption_round_trip_and_tamper_rejection(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(crypto, "get_settings", lambda: SimpleNamespace(profile_secret=key))
    data = {"full_name": "निजी नाम", "phone": "private-test-value"}
    token = crypto.encrypt_json(data)
    assert data["phone"] not in token
    assert crypto.decrypt_json(token) == data
    assert crypto.decrypt_json(None) == {}
    with pytest.raises(InvalidToken):
        crypto.decrypt_json(token[:-10] + "modified")


def test_missing_encryption_key_does_not_fall_back_to_plaintext(monkeypatch):
    monkeypatch.setattr(crypto, "get_settings", lambda: SimpleNamespace(profile_secret=""))
    with pytest.raises(RuntimeError, match="PROFILE_SECRET"):
        crypto.encrypt_json({"phone": "private"})


async def test_pib_feed_accepts_only_official_links(monkeypatch):
    xml = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>PIB</title>
    <item><title>Official &amp; update</title><link>https://pib.gov.in/PressReleasePage.aspx?PRID=1</link><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate></item>
    <item><title>Unexpected host</title><link>https://example.com/item</link></item>
    </channel></rss>'''
    http_client(monkeypatch, feeds, lambda request: httpx.Response(200, content=xml))
    items = await feeds.latest_pib()
    assert len(items) == 1
    assert items[0].source == "PIB" and items[0].title == "Official & update"
    assert items[0].published == "Fri, 30 Oct 2026 12:00:00 GMT"


async def test_malformed_pib_feed_is_an_error(monkeypatch):
    http_client(monkeypatch, feeds, lambda request: httpx.Response(200, text="upstream error page"))
    with pytest.raises(ValueError, match="RSS"):
        await feeds.latest_pib()
