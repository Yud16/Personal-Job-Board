import re

# --- Keyword extraction -----------------------------------------------------

def _term_pattern(term):
    """Word-boundary, case-insensitive pattern for a vocabulary term or alias.
    Escapes regex special characters but keeps internal spaces/slashes literal
    so multi-word terms like "REST API" or "CI/CD" still match as phrases.
    """
    escaped = re.escape(term)
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.IGNORECASE)


def extract_keywords(jd_text, vocabulary):
    """Scan jd_text against the vocabulary list. Returns the list of matched
    canonical terms (term or any alias found), case-insensitive, word-boundary
    aware, in vocabulary order.
    """
    found = []
    for entry in vocabulary:
        term = entry["term"]
        candidates = [term] + entry.get("aliases", [])
        if any(_term_pattern(c).search(jd_text) for c in candidates):
            found.append(term)
    return found


# --- Years of experience -----------------------------------------------------

_YEARS_PATTERNS = [
    re.compile(r"(\d+)\+?\s*(?:to|-)\s*(\d+)\+?\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\+?\s*years?\s*(?:of)?\s*(?:experience|exp)", re.IGNORECASE),
    re.compile(r"(?:minimum|at least)\s*(?:of\s*)?(\d+)\+?\s*years?", re.IGNORECASE),
]


def extract_years_required(jd_text):
    """Returns (years_required: float|None, matched_text: str|None).
    For a range, the effective requirement is the lowest number in the range.
    """
    for pattern in _YEARS_PATTERNS:
        m = pattern.search(jd_text)
        if m:
            groups = [g for g in m.groups() if g is not None]
            numbers = [float(g) for g in groups]
            return min(numbers), m.group(0)
    return None, None


# --- Market detection ---------------------------------------------------------

_UK_TERMS = [
    "united kingdom", "u.k.", " uk ", "uk-based", "england", "scotland",
    "wales", "northern ireland", "london", "manchester", "birmingham",
    "edinburgh", "glasgow", "bristol", "leeds", "britain", "british",
]
_US_TERMS = [
    "united states", "usa", "u.s.a", "u.s.", " us ", "us-based", "america",
    "california", "new york", "texas", "washington", "remote (us)",
]


def detect_market(jd_text, posting_url=""):
    text = f" {jd_text.lower()} "
    url = (posting_url or "").lower()

    if url.endswith(".co.uk") or ".co.uk/" in url:
        return "UK", "posting URL ends in .co.uk"
    if any(term in text for term in _UK_TERMS):
        for term in _UK_TERMS:
            if term in text:
                return "UK", term.strip()
    if any(term in text for term in _US_TERMS):
        for term in _US_TERMS:
            if term in text:
                return "US", term.strip()
    return "INTL", None


_LOCATION_LABEL_PATTERNS = [
    re.compile(r"\blocation\s*[:\-]\s*([^\n.;|]{2,80})", re.IGNORECASE),
    re.compile(r"\bbased in\s+([^\n.;|,]{2,60}(?:,\s*[^\n.;|,]{2,40})?)", re.IGNORECASE),
    re.compile(r"\bremote\s*[\(\-]\s*([A-Za-z .,]{2,40})\)?", re.IGNORECASE),
]


def extract_location(jd_text):
    """Best-effort extraction of the posting's stated location, for display
    only (market/eligibility logic does not depend on this). Returns the
    matched text or None if nothing that looks like a location was found --
    callers should say so plainly rather than guessing.
    """
    for pattern in _LOCATION_LABEL_PATTERNS:
        m = pattern.search(jd_text)
        if m:
            loc = m.group(1).strip().rstrip(").,;")
            if loc:
                return loc
    return None


_COUNTRY_GUESSES = [
    "canada", "germany", "france", "netherlands", "ireland", "australia",
    "india", "singapore", "spain", "italy", "sweden", "switzerland",
    "japan", "hong kong", "new zealand", "mexico", "brazil",
]


def guess_country_code(jd_text):
    text = jd_text.lower()
    for name in _COUNTRY_GUESSES:
        if name in text:
            return name.upper()[:3]
    return "OTHER"


# --- Eligibility ---------------------------------------------------------------

_UK_CLEARANCE_PATTERNS = [
    re.compile(r"\bSC[\s-]?cleared\b", re.IGNORECASE),
    re.compile(r"\bDV[\s-]?cleared\b", re.IGNORECASE),
    re.compile(r"\bsecurity clearance\b", re.IGNORECASE),
    re.compile(r"\bmust have resided in the UK for\b", re.IGNORECASE),
]

_US_SPONSORSHIP_PATTERNS = [
    re.compile(r"\bvisa sponsorship\b", re.IGNORECASE),
    re.compile(r"\bsponsorship\b", re.IGNORECASE),
    re.compile(r"\bwork authorization\b", re.IGNORECASE),
    re.compile(r"\bno sponsorship\b", re.IGNORECASE),
]

_INTL_SIGNAL_PATTERNS = [
    re.compile(r"\bvisa sponsorship\b", re.IGNORECASE),
    re.compile(r"\brelocation assistance\b", re.IGNORECASE),
    re.compile(r"\brelocation package\b", re.IGNORECASE),
    re.compile(r"\binternational candidates welcome\b", re.IGNORECASE),
]

_INTL_BLOCK_PATTERNS = [
    re.compile(r"\bmust have (?:an? )?existing right to work in\b", re.IGNORECASE),
    re.compile(r"\bno sponsorship\b", re.IGNORECASE),
    re.compile(r"\bwe (?:do not|don't) (?:offer|provide) sponsorship\b", re.IGNORECASE),
]


def evaluate_eligibility(jd_text, market, profile):
    if market == "UK":
        for pattern in _UK_CLEARANCE_PATTERNS:
            m = pattern.search(jd_text)
            if m:
                return {
                    "status": "hard_blocked",
                    "note": f"UK posting requires clearance (“{m.group(0)}”) — hard blocker.",
                    "short": f"Hard blocked: clearance language (“{m.group(0)}”)",
                }
        return {
            "status": "eligible",
            "note": "UK posting, no clearance language detected — British passport covers right to work.",
            "short": "No clearance language detected",
        }

    if market == "US":
        signal = None
        for pattern in _US_SPONSORSHIP_PATTERNS:
            m = pattern.search(jd_text)
            if m:
                signal = m.group(0)
                break
        note = "OPT EAD covers work authorization regardless of sponsorship language."
        return {
            "status": "eligible",
            "note": note,
            "short": (f"Sponsorship language present (“{signal}”), OPT EAD covers it" if signal
                      else "No sponsorship language, OPT EAD covers it"),
        }

    # INTL
    for pattern in _INTL_BLOCK_PATTERNS:
        m = pattern.search(jd_text)
        if m:
            return {
                "status": "hard_blocked",
                "note": f"Posting explicitly requires existing right to work / no sponsorship (“{m.group(0)}”).",
                "short": f"Hard blocked: “{m.group(0)}”",
            }
    for pattern in _INTL_SIGNAL_PATTERNS:
        m = pattern.search(jd_text)
        if m:
            return {
                "status": "eligible",
                "note": f"Explicit sponsorship/relocation signal found (“{m.group(0)}”).",
                "short": f"Sponsorship/relocation signal found (“{m.group(0)}”)",
            }
    return {
        "status": "unconfirmed",
        "note": "International posting, silent on sponsorship — treated as a real penalty, not neutral.",
        "short": "Silent on sponsorship (real penalty for international postings)",
    }
