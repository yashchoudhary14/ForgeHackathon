"""plain-language, regional-language explainer for schemes / notifications / any govt document"""
import logging

from pydantic import BaseModel

from ..schemas import Citation, ExplainIn, ExplainOut, ProfileData
from ..services import llm
from .matcher import quote_found

log = logging.getLogger(__name__)

MAX_CHARS = 120_000

LANG_NAMES = {
    "en": "English", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
    "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "od": "Odia",
}

SYSTEM = """You explain Indian government schemes, notifications, circulars and laws to ordinary citizens.
Write for someone who studied till class 8: short sentences, everyday words, no legal jargon, explain any
unavoidable term in brackets. Use the requested output language in its native script (keep scheme names,
amounts in ₹, dates and numbers exact).
Be strictly faithful to the source. If the source doesn't say something, don't say it. Never guess amounts or dates.
For every key point / right / deadline there must be supporting evidence: put it in `evidence` as an exact
verbatim quote copied from the SOURCE text (in the source's original language), max 30 words.
If a citizen profile is given, `what_it_means_for_you` says concretely how this affects that person
(including if it probably doesn't apply to them). Otherwise leave it empty."""


class _Evidence(BaseModel):
    quote: str
    supports: str  # which point this backs


class _Explained(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    your_rights: list[str]
    what_it_means_for_you: str
    deadlines: list[str]
    documents_needed: list[str]
    evidence: list[_Evidence]


async def _load_source(body: ExplainIn) -> tuple[str, str, str]:
    """returns (title, text, source_url)"""
    from ..services import ingest, myscheme, rag

    src = body.source
    if src.type == "scheme":
        s = await myscheme.get_scheme(src.slug, lang="en")
        parts = [
            ("Details", s.details_md), ("Benefits", s.benefits_md), ("Eligibility", s.eligibility_md),
            ("Exclusions", s.exclusions_md), ("Documents required", s.documents_md),
        ]
        parts += [(f"How to apply ({a.mode})", a.steps_md) for a in s.application]
        text = "\n\n".join(f"## {h}\n{t}" for h, t in parts if t)
        return s.name, text, s.source_url
    if src.type == "url":
        doc = await ingest.ingest_url(src.url)
        return doc.title, await rag.document_text(doc.id, MAX_CHARS), src.url
    doc = await ingest.get_document(src.document_id)
    return doc.title, await rag.document_text(doc.id, MAX_CHARS), doc.source_url or f"document:{doc.id}"


async def explain(body: ExplainIn, profile: ProfileData | None) -> ExplainOut:
    title, text, source_url = await _load_source(body)
    if not text.strip():
        raise ValueError("couldn't read any text from that source")

    lang = LANG_NAMES.get(body.language, "English")
    prompt = (
        f"Output language: {lang}\n"
        f"Citizen profile: {profile.model_dump_json(exclude_none=True) if profile else 'not given'}\n\n"
        f"SOURCE ({title}):\n\"\"\"\n{text[:MAX_CHARS]}\n\"\"\""
    )
    out = await llm.generate_json(prompt, _Explained, system=SYSTEM, temperature=0.2)

    citations = [
        Citation(source_url=source_url, title=title, quote=e.quote, section=e.supports)
        for e in out.evidence
        if quote_found(e.quote, text)
    ]
    if len(citations) < len(out.evidence):
        log.info("explainer: %d/%d quotes failed verification", len(out.evidence) - len(citations), len(out.evidence))

    audio_url = None
    if body.with_audio:
        spoken = "\n".join([out.summary, *out.key_points[:4], out.what_it_means_for_you or ""])
        try:
            from ..services import sarvam

            audio_url = await sarvam.tts_to_file(spoken, body.language)
        except Exception as e:  # audio is a nice-to-have, never fail the explanation for it
            log.warning("tts failed: %s", e)

    return ExplainOut(
        title=out.title or title,
        summary=out.summary,
        key_points=out.key_points,
        your_rights=out.your_rights,
        what_it_means_for_you=out.what_it_means_for_you or None,
        deadlines=out.deadlines,
        documents_needed=out.documents_needed,
        citations=citations,
        language=body.language,
        audio_url=audio_url,
    )
