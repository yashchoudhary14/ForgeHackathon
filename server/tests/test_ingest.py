from types import SimpleNamespace

from app.services import ingest, rag
from test_myscheme import recorded
from app.services.markdown import to_markdown


def test_chunker_preserves_real_document_and_page_boundaries():
    raw = recorded("myscheme-pm-kisan.json")
    text = to_markdown(raw["en"]["schemeContent"]["exclusions"])
    parts = ingest.chunk_text(text)
    assert len(parts) > 1 and all(len(part) <= 1200 for part in parts)
    assert parts[0][-200:] == parts[1][:200]
    chunks = [SimpleNamespace(text=part, page=1, position=i) for i, part in enumerate(parts)]
    assert rag.join_chunks(chunks) == "[page 1]\n" + text
    windows = ingest.chunk_windows(text)
    chunks.append(SimpleNamespace(text=parts[0], page=2, position=len(chunks)))
    assert rag.join_chunks(chunks, [offset for offset, _ in windows] + [0]) == (
        "[page 1]\n" + text + "\n\n[page 2]\n" + parts[0])


def test_html_main_text_from_official_page():
    # Recorded public myScheme detail (rich text), rather than invented content.
    raw = recorded("myscheme-pm-kisan.json")
    text = to_markdown(raw["en"]["schemeContent"]["detailedDescription"])
    assert ingest.chunk_text(text) == [text]


def test_invalid_chunk_settings():
    import pytest
    with pytest.raises(ValueError):
        ingest.chunk_text("", 200, 200)


def test_unsupported_and_empty_uploads():
    import pytest
    for data in (b"", b"not a supported file"):
        with pytest.raises(ValueError):
            ingest.detect_type(data, "application/pdf")
