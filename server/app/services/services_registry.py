"""Verified portal directory, not a static catalogue of procedural claims.

URLs checked against the linked government sources on 2026-11-01. Requirements,
fees and processing times are deliberately retrieved live through grounding.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


def https_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        return (p.scheme == "https" and bool(p.hostname) and not p.username
                and not p.password and p.port in (None, 443))
    except ValueError:
        return False


def official_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower() if https_url(url) else ""
    return any(host == d or host.endswith("." + d) for d in ("gov.in", "nic.in"))


@dataclass(frozen=True)
class Service:
    key: str
    name: str
    portal: str
    aliases: tuple[str, ...]
    verification_url: str
    requires_state: bool = False


REGISTRY = (
    Service("driving_licence", "Driving licence", "https://sarathi.parivahan.gov.in",
            ("driving licence", "driving license", "driver licence", "driver license", "driver's license", "driver's licence", "drivers licence", "drivers license", "sarathi", "ड्राइविंग लाइसेंस", "ड्राइविंग लाइसेन्स", "ड्राइविंग लाइसन्स", "ড্রাইভিং লাইসেন্স", "ড্ৰাইভিং লাইচেন্স", "ড্ৰাইভিং লাইচেঞ্চ", "ড্ৰাইভিং লাইচেন্সৰ", "ড্ৰাইভিং লাইচেঞ্চৰ"),
            "https://sarathi.parivahan.gov.in", requires_state=True),
    Service("learner_licence", "Learner licence", "https://sarathi.parivahan.gov.in",
            ("learner licence", "learner license", "learner's licence", "learners licence", "learning licence", "लर्निंग लाइसेंस", "লার্নার লাইসেন্স", "শিক্ষানবিশ অনুজ্ঞাপত্ৰ"),
            "https://sarathi.parivahan.gov.in", requires_state=True),
    Service("vehicle_rc", "Vehicle registration certificate", "https://vahan.parivahan.gov.in",
            ("vehicle rc", "vehicle registration", "registration certificate", "vahan", "rc transfer", "वाहन पंजीकरण", "গাড়ির রেজিস্ট্রেশন", "বাহন পঞ্জীয়ন"),
            "https://parivahan.gov.in", requires_state=True),
    Service("epan", "Instant e-PAN", "https://www.incometax.gov.in",
            ("e-pan", "epan", "e pan", "instant pan"),
            "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/instant-e-pan"),
    Service("pan", "PAN", "https://www.onlineservices.nsdl.com",
            ("pan", "pan card", "पैन कार्ड", "প্যান কার্ড"),
            "https://www.incometax.gov.in/iec/foportal/help/e-filing-link-aadhaar-faq"),
    Service("pan_uti", "PAN via UTIITSL", "https://www.pan.utiitsl.com",
            ("utiitsl", "uti pan"),
            "https://www.incometax.gov.in/iec/foportal/help/e-filing-link-aadhaar-faq"),
    Service("passport", "Passport", "https://www.passportindia.gov.in",
            ("passport", "passport seva", "पासपोर्ट", "পাসপোর্ট", "পাছপোৰ্ট"), "https://www.passportindia.gov.in"),
    Service("aadhaar", "Aadhaar update", "https://myaadhaar.uidai.gov.in",
            ("aadhaar", "aadhar", "uidai", "आधार", "আধার"), "https://uidai.gov.in/en/my-aadhaar"),
    Service("voter", "Voter ID", "https://voters.eci.gov.in",
            ("voter", "electoral", "eci", "मतदाता", "ভোটার", "ভোটাৰ"), "https://voters.eci.gov.in"),
    Service("birth_death", "Birth / death certificate", "https://crsorgi.gov.in",
            ("birth certificate", "death certificate", "crs", "जन्म प्रमाण", "मृत्यु प्रमाण", "জন্ম সনদ", "জন্ম শংসাপত্ৰ", "মৃত্যু শংসাপত্ৰ", "জন্মের শংসাপত্র", "মৃত্যু সনদ"),
            "https://services.india.gov.in/service/detail/civil-registration-system-birth-and-death-certificate", requires_state=True),
    Service("ayushman", "Ayushman card", "https://beneficiary.nha.gov.in",
            ("ayushman", "nha", "आयुष्मान", "আয়ুষ্মান"), "https://health.delhi.gov.in/health/ab-pm-jay-scheme"),
    Service("pmkisan", "PM-KISAN", "https://pmkisan.gov.in",
            ("pm-kisan", "pm kisan", "pmkisan", "पीएम किसान", "পিএম কিষাণ", "পিএম কিষান", "পিএম কৃষক"), "https://pmkisan.gov.in"),
    Service("epfo", "EPFO member services", "https://unifiedportal-mem.epfindia.gov.in",
            ("epfo", "provident fund", "uan", "pf withdrawal", "ईपीएफओ", "ইপিএফও"),
            "https://www.epfindia.gov.in/site_docs/PDFs/EPFO_PRESS_RELEASES/PressRelease_18092025_AllKeyServicTthroughASingleLogin.pdf"),
    Service("scholarships", "National Scholarship Portal", "https://scholarships.gov.in",
            ("scholarship", "scholarships", "nsp", "छात्रवृत्ति", "বৃত্তি", "জলপানি"), "https://scholarships.gov.in"),
    Service("grievance", "CPGRAMS grievance", "https://pgportal.gov.in",
            ("grievance", "cpgrams", "pgportal", "शिकायत", "অভিযোগ"), "https://pgportal.gov.in"),
)


def match_service(query: str) -> Service | None:
    # Longest alias wins (e-PAN before PAN, UTI PAN before PAN).
    query = query.replace("’", "'").replace("‑", "-").replace("–", "-")
    matches = [(len(alias), entry) for entry in REGISTRY for alias in (*entry.aliases, entry.key)
               if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", query, re.I)]
    return max(matches, key=lambda item: item[0])[1] if matches else None
