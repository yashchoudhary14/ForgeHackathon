"""Real Hindi round trip. Start uvicorn, then set TALK_BASE_URL to its local URL."""
import io
import json
import os
import re
import wave
from urllib.parse import urlsplit

import httpx
import pytest


def decode(response):
    response.raise_for_status()
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.mark.live
async def test_first_hindi_text_student_profile_cards_and_playable_audio():
    base_url = os.environ.get("TALK_BASE_URL", "http://127.0.0.1:8873")
    assert urlsplit(base_url).hostname in {"localhost", "127.0.0.1"}
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
        created = await client.post("/api/profile", json={"mode": "talk"})
        created.raise_for_status()
        profile_id = created.json()["id"]
        events = decode(await client.post("/api/talk", json={"profile_id": profile_id,
            "text": "मैं बिहार की 19 साल की SC छात्रा हूँ, B.Sc पहले साल"}))
        assert not [event for event in events if event["type"] == "error"], events
        done = next(event for event in events if event["type"] == "done")
        assert done["lang"] == "hi" and re.search(r"[\u0900-\u097f]", done["text"])
        assert {key: done["profile"].get(key) for key in (
            "state", "age", "gender", "caste", "is_student", "study_year")} == {
                "state": "Bihar", "age": 19, "gender": "female", "caste": "sc",
                "is_student": True, "study_year": 1}
        assert done["profile"].get("course", "").lower().replace(".", "").replace(" ", "") == "bsc"
        cards = [event["card"] for event in events if event["type"] == "card"
                 and event["card"]["kind"] == "scheme"]
        assert cards, events
        audio = await client.get(done["audio_url"])
        audio.raise_for_status()
        assert audio.headers["content-type"].startswith("audio/")
        with wave.open(io.BytesIO(audio.content)) as wav:
            assert wav.getnframes() > 0 and wav.getframerate() > 0
        saved = await client.get(f"/api/profile/{profile_id}")
        saved.raise_for_status()
        assert saved.json()["language"] == "hi"


@pytest.mark.live
async def test_hindi_audio_profile_matching_and_followup():
    base_url = os.environ.get("TALK_BASE_URL", "http://127.0.0.1:8873")
    assert urlsplit(base_url).hostname in {"localhost", "127.0.0.1"}, "Use a local stack for this check"
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
        health = await client.get("/api/health")
        health.raise_for_status()
        created = await client.post("/api/profile", json={"mode": "talk"})
        created.raise_for_status()
        profile_id = created.json()["id"]
        speech = await client.post("/api/voice/tts", json={
            "text": "main Uttar Pradesh ka kisan hoon, do acre zameen hai", "language": "hi"})
        speech.raise_for_status()
        assert speech.content.startswith(b"RIFF")
        first = decode(await client.post("/api/talk", data={"profile_id": profile_id},
                                        files={"audio": ("farmer.wav", speech.content, "audio/wav")}))
        assert not [e for e in first if e["type"] == "error"], first
        transcript = next(e for e in first if e["type"] == "transcript")
        assert transcript["lang"] == "hi", transcript
        saved = await client.get(f"/api/profile/{profile_id}")
        saved.raise_for_status()
        profile = saved.json()
        assert profile["language"] == "hi" and profile["mode"] == "talk"
        assert profile["data"]["state"] == "Uttar Pradesh"
        assert "farm" in profile["data"]["occupation"].lower()
        assert profile["data"]["land_acres"] == 2
        schemes = [e["card"] for e in first if e["type"] == "card" and e["card"]["kind"] == "scheme"]
        assert schemes, first
        first_done = next(e for e in first if e["type"] == "done")
        assert first_done["audio_url"] and re.search(r"[\u0900-\u097f]", first_done["text"])
        # The follow-up is intentionally English: it must NOT switch the session.
        second = decode(await client.post("/api/talk", json={"profile_id": profile_id,
                                                            "text": "Please explain the first scheme briefly"}))
        done = next(e for e in second if e["type"] == "done")
        assert done["lang"] == "hi" and re.search(r"[\u0900-\u097f]", done["text"])
        assert done["audio_url"]
        for url in (first_done["audio_url"], done["audio_url"]):
            audio = await client.get(url)
            assert audio.status_code == 200 and audio.content.startswith(b"RIFF")
            assert audio.headers["content-type"].startswith("audio/")
        print(json.dumps({"profile_id": profile_id, "transcript": transcript, "profile": first_done["profile"],
                          "scheme_slugs": [s["slug"] for s in schemes], "first_reply": first_done["text"],
                          "followup_reply": done["text"], "followup_audio_url": done["audio_url"]}, ensure_ascii=False))
