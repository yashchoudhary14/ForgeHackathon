"""turns free text (any language) into a structured citizen profile + asks for what's missing"""
from pydantic import BaseModel

from ..schemas import ProfileData, SensitiveData
from ..services import llm

# fields that actually move the needle when matching schemes, in the order we ask for them
KEY_FIELDS = ["state", "age", "gender", "occupation", "annual_income", "caste", "residence", "is_student"]

SYSTEM = """You extract a citizen's profile for matching them to Indian government welfare schemes.
Rules:
- Only fill a field if the user actually said it or it is directly implied (e.g. "I farm 2 acres" -> occupation farmer, land_acres 2). Never guess.
- annual_income is yearly household income in INR (convert "15k a month" -> 180000, "2 lakh" -> 200000).
- state must be a full Indian state/UT name in English (e.g. "Uttar Pradesh").
- caste: general | obc | sc | st | pvtg | dnt. gender: male | female | transgender. residence: urban | rural.
- Put name, phone, email, dob, address, father_name, bank_ifsc only in `sensitive`.
- The user may write in Hindi, Hinglish or any Indian language. Output field values in English.
- Preserve stated religion, course, study_year (first year = 1), institution_type
  (e.g. government college), and parent_occupation separately from the citizen's occupation.
- Preserve an explicitly stated is_single_child, is_hosteller and institution_name.
  Explicitly not disabled means disability_percent=0; absence of disability information means null.
"""

ASK_SYSTEM = """You are a friendly government-services helper talking to an ordinary citizen.
Ask ONE short, simple question to get the missing information listed. Max 25 words.
Write it in the language given by code: en English, hi Hindi, bn Bengali, ta Tamil, te Telugu, mr Marathi,
gu Gujarati, kn Kannada, ml Malayalam, pa Punjabi, od Odia. Use the native script. No jargon."""


class Extracted(BaseModel):
    data: ProfileData
    sensitive: SensitiveData


def merge(old: BaseModel, new: BaseModel) -> dict:
    out = old.model_dump()
    for k, v in new.model_dump().items():
        if v is not None:
            out[k] = v
    return out


def missing(data: ProfileData) -> list[str]:
    gaps = [f for f in KEY_FIELDS if getattr(data, f) is None]
    if data.is_student and "occupation" in gaps:
        gaps.remove("occupation")  # "student" is the occupation, asking again sounds dumb
    return gaps


async def extract(text: str, current: ProfileData, current_sensitive: SensitiveData) -> tuple[ProfileData, SensitiveData]:
    prompt = (
        f"Profile so far (JSON): {current.model_dump_json(exclude_none=True)}\n\n"
        f"New message from the user:\n\"\"\"{text}\"\"\"\n\n"
        "Return only what the new message adds or corrects."
    )
    got = await llm.generate_json(prompt, Extracted, system=SYSTEM)
    data = ProfileData(**merge(current, got.data))
    sensitive = SensitiveData(**merge(current_sensitive, got.sensitive))
    return data, sensitive


async def follow_up(data: ProfileData, language: str) -> str | None:
    gaps = missing(data)
    if not gaps:
        return None
    ask = gaps[:2]  # two at a time feels natural, more is an interrogation
    prompt = f"Language: {language}\nAlready known: {data.model_dump_json(exclude_none=True)}\nMissing: {', '.join(ask)}"
    return (await llm.generate(prompt, system=ASK_SYSTEM, temperature=0.4)).strip()
