import json
from pathlib import Path

import pytest

from app.services import myscheme
from app.services.markdown import field_markdown, to_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def recorded(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))["data"]


def test_real_scheme_markdown():
    raw = recorded("myscheme-pm-kisan.json")
    detail = myscheme.parse_detail("pm-kisan", "en", raw,
        recorded("myscheme-documents.json"), recorded("myscheme-faqs.json"))
    assert detail.name == raw["en"]["basicDetails"]["schemeName"]
    assert "**Rs. 6000 per annum per family**" in detail.benefits_md
    assert "1. Aadhaar Card" in detail.documents_md
    assert "farmer" in detail.eligibility_md
    assert detail.application[0].url.startswith("https://pmkisan.gov.in/")
    assert detail.faqs[0]["answer"]
    content = raw["en"]["schemeContent"]
    assert "**" in to_markdown(content["benefits"])
    assert field_markdown(content, "benefits") == content["benefits_md"].strip()


def test_filter_mapping_includes_universal_schemes():
    filters = myscheme.translate_filters(dict(state="Uttar Pradesh", gender="female", caste="sc",
        residence="rural", age=23, is_student=True, is_bpl=False, disability=True, is_minority=False,
        unsupported="ignored"))
    assert {"identifier": "beneficiaryState", "value": "All"} in filters
    assert {"identifier": "caste", "value": "Scheduled Caste (SC)"} in filters
    assert {"identifier": "residence", "value": "Both"} in filters
    assert {"identifier": "age-sc", "min": 23, "max": 23} in filters
    assert {"identifier": "isBpl", "value": "No"} in filters
    assert len(filters) == 13


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_myscheme_search():
    try:
        result = await myscheme.search("scholarship", {"state": "Uttar Pradesh"}, 0, 2)
        assert result.total > 0
        assert result.items and result.items[0].slug
    finally:
        await myscheme.client().aclose()
