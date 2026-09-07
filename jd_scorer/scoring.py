KEYWORD_WEIGHT = 60
YEARS_WEIGHT = 25
ELIGIBILITY_WEIGHT = 15
PER_MISSING_YEAR_PENALTY = 8
HARD_BLOCK_SCORE_CAP = 40
MIN_LOGGABLE_SCORE = 50


def compute_keyword_score(matched_count, required_count):
    if required_count == 0:
        return KEYWORD_WEIGHT
    return (matched_count / required_count) * KEYWORD_WEIGHT


def compute_years_score(years_required, years_have):
    if years_required is None or years_required <= years_have:
        return YEARS_WEIGHT
    gap = years_required - years_have
    return max(0, YEARS_WEIGHT - (gap * PER_MISSING_YEAR_PENALTY))


def compute_eligibility_score(eligibility_status):
    if eligibility_status == "hard_blocked":
        return 0
    if eligibility_status == "unconfirmed":
        return ELIGIBILITY_WEIGHT * 0.3
    return ELIGIBILITY_WEIGHT


def compute_match_score(matched_count, required_count, years_required, years_have, eligibility_status):
    keyword_score = compute_keyword_score(matched_count, required_count)
    years_score = compute_years_score(years_required, years_have)
    eligibility_score = compute_eligibility_score(eligibility_status)
    score = round(keyword_score + years_score + eligibility_score)
    if eligibility_status == "hard_blocked":
        score = min(score, HARD_BLOCK_SCORE_CAP)
    return max(0, min(100, score))


def build_bullets_available_for_gaps(missing_keywords, bullets):
    result = {}
    for kw in missing_keywords:
        matches = [b["id"] for b in bullets if kw in b.get("keywords", [])]
        result[kw] = matches
    return result


def build_review_summary(match_score, matched, missing, years_required, years_have, market, eligibility_short):
    total = len(matched) + len(missing)
    missing_text = f" (missing {', '.join(missing)})" if missing else ""
    years_text = (f"requires {years_required}, have {years_have}" if years_required is not None
                  else f"no requirement detected, have {years_have}")
    return (
        f"Score {match_score}/100. "
        f"Keywords: {len(matched)}/{total} matched{missing_text}. "
        f"Years: {years_text}. "
        f"Eligibility: {market}, {eligibility_short}."
    )


def build_review(*, matched_keywords, missing_keywords, years_required, years_have,
                  market, eligibility, bullets):
    required_count = len(matched_keywords) + len(missing_keywords)
    match_score = compute_match_score(
        matched_count=len(matched_keywords),
        required_count=required_count,
        years_required=years_required,
        years_have=years_have,
        eligibility_status=eligibility["status"],
    )
    review_summary = build_review_summary(
        match_score, matched_keywords, missing_keywords, years_required, years_have,
        market, eligibility["short"],
    )
    return {
        "match_score": match_score,
        "keyword_coverage": {"matched": matched_keywords, "missing": missing_keywords},
        "years": {
            "required": years_required,
            "have": years_have,
            "meets_requirement": (years_required is None) or (years_have >= years_required),
        },
        "eligibility": {
            "market": market,
            "status": eligibility["status"],
            "note": eligibility["note"],
        },
        "bullets_available_for_gaps": build_bullets_available_for_gaps(missing_keywords, bullets),
        "review_summary": review_summary,
    }
