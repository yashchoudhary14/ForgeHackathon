"""Conservative source-based checks around model eligibility decisions."""
import json
import re
from decimal import Decimal
from html import unescape

from ..schemas import ProfileData, SchemeDetail


def profile_text(profile: ProfileData) -> str:
    facts = profile.model_dump(exclude_none=True)
    if profile.annual_income is not None:
        digits = str(abs(profile.annual_income))
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        amount = ",".join([*groups, tail])
        sign = "-" if profile.annual_income < 0 else ""
        lakh = Decimal(profile.annual_income) / 100000
        facts["annual_income_display"] = f"₹{sign}{amount} ({lakh.normalize():f} lakh)"
    return json.dumps(facts, ensure_ascii=False)


NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(crores?|lakhs?|lacs?|thousand|million|k\b)?", re.I)
SCALES = {"crore": 10000000, "lakh": 100000, "lac": 100000,
          "thousand": 1000, "million": 1000000, "k": 1000}
FIELDS = {"annual_income": r"\bincome\b", "age": r"\bage[ds]?\b|\byears? old\b"}


def _condition(value: Decimal, text: str) -> bool | None:
    text = re.sub(r"[*_#`]", "", unescape(text).lower())
    numbers = list(NUMBER.finditer(text))
    if not numbers:
        return None

    def amount(match):
        unit = (match[2] or "").lower().rstrip("s")
        return Decimal(match[1].replace(",", "")) * SCALES.get(unit, 1)

    if len(numbers) == 2:
        a, b = numbers
        between = text[a.end():b.start()].strip()
        if between in {"to", "-", "–", "and"} and (between != "and" or "between" in text[:a.start()]):
            # Don't guess whether a trailing unit also applies to the first bound.
            if bool(a[2]) != bool(b[2]):
                return None
            return amount(a) <= value <= amount(b)
        return None
    if len(numbers) != 1:
        return None
    number = numbers[0]
    limit = amount(number)
    before, after = text[:number.start()], text[number.end():]
    # Inclusive phrases must be checked before their strict counterparts.
    upper = (r"not (?:be )?(?:exceed|more than|greater than|above|over)|"
             r"no more than|less than or equal to|maximum|at most|up to|upto|<=|≤")
    lower = (r"at least|minimum|not (?:be )?(?:less than|below|under)|"
             r"no less than|greater than or equal to|>=|≥")
    if re.search(upper, before) or re.search(r"^(?:\s*years?)?\s*(?:or|and) (?:below|less|under)", after):
        return value <= limit
    if re.search(lower, before) or re.search(r"^(?:\s*years?)?\s*(?:or|and) (?:above|more|over)", after):
        return value >= limit
    if re.search(r"less than|below|under|<", before):
        return value < limit
    if re.search(r"more than|greater than|above|over|exceed|>", before):
        return value > limit
    return None


def numeric_checks(profile: ProfileData, claim: str, quote: str) -> dict[str, bool | None]:
    """Evaluate only quoted limits, never the model's restatement of the numbers.

    Unparseable or ambiguous numeric drops fail open to detailed review. Ordinary
    nonnumeric target restrictions are unaffected.
    """
    checks = {}
    for field, pattern in FIELDS.items():
        if not re.search(pattern, claim + " " + quote, re.I):
            continue
        value = getattr(profile, field)
        checks[field] = None
        if value is None:
            continue
        clauses = [clause.lower() for clause in re.split(r"[;\n]|(?<=[.!?])\s+(?=[A-Z])", quote)]
        relevant = [clause for clause in clauses if re.search(pattern, clause)]
        if len(relevant) != 1:
            continue
        text = relevant[0]
        # Two different fields or alternate routes need the detailed judge.
        other = "age" if field == "annual_income" else "annual_income"
        if re.search(FIELDS[other], text) or re.search(r"\bor\b(?!\s+(?:less|below|under|above|more|over)\b)", text):
            continue
        actual = Decimal(value)
        if field == "annual_income" and re.search(r"monthly|per month|a month", text):
            actual /= 12
        checks[field] = _condition(actual, text)
    return checks


def institutional_target(scheme: SchemeDetail) -> tuple[str, str] | None:
    """Return an exact source span establishing an organisational applicant.

    Construction grants have citizen end users, but organisations apply. A
    student's hostel admission or scholarship through a college is different.
    """
    organisation = (r"(?:state governments?|ut administrations?|union territory administrations?|ngos?|"
                    r"non governmental organi[sz]ations?|voluntary organi[sz]ations?|universities|"
                    r"institutions|organi[sz]ations)")
    lines = scheme.eligibility_md.splitlines()
    for index, line in enumerate(lines):
        if not re.search(r"agencies eligible for financial assistance|eligible (?:implementing )?agencies", line, re.I):
            continue
        agencies = []
        for following in lines[index + 1:]:
            if agencies and not following.strip():
                break
            if following.strip():
                agencies.append(following.strip())
        block = " ".join(agencies)
        if re.search(organisation, block, re.I) and not re.search(r"\b(?:students?|individuals?|citizens?)\b", block, re.I):
            return "eligibility", next(line for line in agencies if re.search(organisation, line, re.I))
    for section, text in (("eligibility", scheme.eligibility_md), ("details", scheme.details_md)):
        for line in text.splitlines():
            if re.search(rf"\b(?:applicants?|eligible (?:entities|agencies)|grants? (?:are )?(?:provided|given|available) to)\b.{{0,80}}\b{organisation}\b", line, re.I):
                if not re.search(r"\b(?:students?|individuals?|citizens?)\b", line, re.I):
                    return section, line.strip()
    if re.search(r"\bconstruction of\b.*\bhostels?\b|\bgrants? (?:in aid )?to (?:voluntary )?organi[sz]ations?\b",
                 re.sub(r"[-–]", " ", scheme.name), re.I):
        return "details", scheme.name
    return None
