from pathlib import Path

import pytest

from app.services.feeds import parse_feed


@pytest.mark.parametrize("language", [1, 2])
def test_recorded_pib_feed(language):
    items = parse_feed((Path(__file__).parent / "fixtures" / f"pib-{language}.xml").read_bytes())
    assert items and all(item.source == "PIB" and item.url.startswith("https://pib.gov.in/") for item in items)
    assert len({item.url for item in items}) == len(items)
    if language == 2:
        assert any("\u0900" <= c <= "\u097f" for c in items[0].title)
