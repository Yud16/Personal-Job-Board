import csv
import datetime
import json
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from jd_scorer import export, jd_parser, scoring, storage
from jd_scorer.export import ExportError

JOB_ROOT = Path(r"C:\Users\yuddu\Desktop\cs\job")
UK_CSV = JOB_ROOT / "uk_pipeline_log.csv"
US_CSV = JOB_ROOT / "us_pipeline_log.csv"
INTL_CSV = JOB_ROOT / "intl_pipeline_log.csv"

DASHBOARD_DIR = Path(__file__).resolve().parent
STATUS_FILE = DASHBOARD_DIR / "data" / "application_status.json"
DISMISSED_FILE = DASHBOARD_DIR / "data" / "dismissed.json"
REPLIES_FILE = DASHBOARD_DIR / "data" / "possible_replies.json"
DISMISSED_REPLIES_FILE = DASHBOARD_DIR / "data" / "dismissed_replies.json"

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

STATUS_OPTIONS = ["Not applied yet", "Applied", "Interview", "Rejection", "Landed"]

app = Flask(__name__)


def load_status_overrides():
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    overrides = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            overrides[key] = {"status": value.get("status"), "changed_at": value.get("changed_at")}
        else:
            # Legacy plain-string entries predate status-change-date tracking.
            overrides[key] = {"status": value, "changed_at": None}
    return overrides


def save_status_overrides(overrides):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, sort_keys=True)


def load_dismissed():
    if not DISMISSED_FILE.exists():
        return set()
    try:
        with open(DISMISSED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dismissed(dismissed):
    DISMISSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DISMISSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(dismissed), f, indent=2)


def load_possible_replies():
    if not REPLIES_FILE.exists():
        return []
    try:
        with open(REPLIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def load_dismissed_replies():
    if not DISMISSED_REPLIES_FILE.exists():
        return set()
    try:
        with open(DISMISSED_REPLIES_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dismissed_replies(dismissed):
    DISMISSED_REPLIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DISMISSED_REPLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(dismissed), f, indent=2)


def _find_vocab_term(term, vocabulary):
    needle = term.strip().lower()
    for entry in vocabulary:
        if entry["term"].lower() == needle:
            return entry
        if any(a.lower() == needle for a in entry.get("aliases", [])):
            return entry
    return None


def _canonicalize_keywords(keywords, vocabulary):
    """Map each keyword to its canonical vocabulary term, adding any unknown
    term to the vocabulary list in place. Returns (canonical_keywords, vocab_changed).
    """
    canonical_keywords = []
    vocab_changed = False
    for kw in keywords:
        existing = _find_vocab_term(kw, vocabulary)
        if existing:
            canonical_keywords.append(existing["term"])
        else:
            vocabulary.append({"term": kw, "aliases": []})
            canonical_keywords.append(kw)
            vocab_changed = True
    return canonical_keywords, vocab_changed


def posting_key(market, posting_url, date_found, company, role_title):
    if posting_url:
        return f"{market}::{posting_url}"
    return f"{market}::{date_found}::{company}::{role_title}"


def extract_variant(raw):
    raw = (raw or "").strip()
    if " (" in raw:
        return raw.split(" (", 1)[0].strip()
    return raw


def tier_for(score):
    if score is None:
        return "below"
    if score >= 80:
        return "strong"
    if score >= 70:
        return "good"
    return "below"


def parse_csv(path, market, min_score=None):
    postings = []
    if not path.exists():
        return postings

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            score_raw = (row.get("score") or "").strip()
            score = None
            if score_raw:
                try:
                    score = int(float(score_raw))
                except ValueError:
                    continue
                if not (0 <= score <= 100):
                    continue
                if min_score is not None and score < min_score:
                    continue

            date_found = (row.get("date_found") or "").strip()
            if not DATE_RE.match(date_found):
                continue

            notes = row.get("hard_blocker") or row.get("sponsorship_signal") or ""
            review_summary = (row.get("review_summary") or "").strip()
            tailored = (row.get("tailored") or "").strip().lower() == "yes"
            company = (row.get("company") or "").strip()
            role_title = (row.get("role_title") or "").strip()
            posting_url = (row.get("posting_url") or "").strip()
            applied_status_raw = (row.get("applied_status") or "").strip()

            postings.append(
                {
                    "key": posting_key(market, posting_url, date_found, company, role_title),
                    "market": market,
                    "country_code": (row.get("country_code") or "").strip(),
                    "date_found": date_found,
                    "title_query": (row.get("title_query") or row.get("category") or "").strip(),
                    "company": company,
                    "role_title": role_title,
                    "posting_url": posting_url,
                    "score": score,
                    "tier": tier_for(score),
                    "resume_variant": extract_variant(row.get("resume_variant")),
                    "notes": notes.strip(),
                    "review_summary": review_summary,
                    "window": (row.get("window") or "").strip(),
                    "tailored": tailored,
                    "resume_pdf": (row.get("resume_pdf") or "").strip(),
                    "cl_pdf": (row.get("cl_pdf") or "").strip(),
                    "applied_status_raw": applied_status_raw,
                }
            )
    return postings


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/replies")
def replies_page():
    return render_template("replies.html")


@app.route("/api/postings")
def api_postings():
    postings = (
        parse_csv(UK_CSV, "UK", min_score=50)
        + parse_csv(US_CSV, "US", min_score=50)
        + parse_csv(INTL_CSV, "INTL", min_score=50)
    )
    overrides = load_status_overrides()
    dismissed = load_dismissed()
    for p in postings:
        p["dismissed"] = p["key"] in dismissed
        if p["key"] in overrides:
            p["status"] = overrides[p["key"]]["status"]
            p["status_changed_at"] = overrides[p["key"]]["changed_at"]
        else:
            p["status"] = "Applied" if p["applied_status_raw"] else "Not applied yet"
            p["status_changed_at"] = None
    return jsonify(postings)


@app.route("/api/status", methods=["POST"])
def api_set_status():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")
    status = data.get("status")

    if not key or status not in STATUS_OPTIONS:
        return jsonify({"error": "invalid key or status"}), 400

    changed_at = datetime.date.today().isoformat()
    overrides = load_status_overrides()
    overrides[key] = {"status": status, "changed_at": changed_at}
    save_status_overrides(overrides)
    return jsonify({"ok": True, "key": key, "status": status, "status_changed_at": changed_at})


@app.route("/api/dismiss", methods=["POST"])
def api_dismiss():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")

    if not key:
        return jsonify({"error": "invalid key"}), 400

    dismissed = load_dismissed()
    dismissed.add(key)
    save_dismissed(dismissed)
    return jsonify({"ok": True, "key": key})


@app.route("/api/restore", methods=["POST"])
def api_restore():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")

    if not key:
        return jsonify({"error": "invalid key"}), 400

    dismissed = load_dismissed()
    dismissed.discard(key)
    save_dismissed(dismissed)
    return jsonify({"ok": True, "key": key})


@app.route("/api/possible-replies")
def api_possible_replies():
    replies = load_possible_replies()
    dismissed = load_dismissed_replies()
    replies = [r for r in replies if r.get("thread_id") not in dismissed]
    replies.sort(key=lambda r: r.get("date", ""), reverse=True)
    return jsonify(replies)


@app.route("/api/dismiss-reply", methods=["POST"])
def api_dismiss_reply():
    data = request.get_json(force=True, silent=True) or {}
    thread_id = data.get("thread_id")

    if not thread_id:
        return jsonify({"error": "invalid thread_id"}), 400

    dismissed = load_dismissed_replies()
    dismissed.add(thread_id)
    save_dismissed_replies(dismissed)
    return jsonify({"ok": True, "thread_id": thread_id})


@app.route("/tailor")
def tailor_page():
    return render_template("tailor.html")


@app.route("/api/state")
def api_state():
    return jsonify({
        "bullets": storage.get_bullets(),
        "vocabulary": storage.get_vocabulary(),
        "profile": storage.get_profile(),
        "entry_dates": export.get_template_entry_dates(),
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    body = request.get_json(force=True) or {}
    jd_text = (body.get("jd_text") or "").strip()
    posting_url = (body.get("posting_url") or "").strip()
    market_override = body.get("market_override")
    years_override = body.get("years_override")

    if not jd_text:
        return jsonify({"error": "jd_text is required"}), 400

    vocabulary = storage.get_vocabulary()
    profile = storage.get_profile()
    bullets = storage.get_bullets()
    included_bullets = [b for b in bullets if b.get("included", True)]

    if market_override:
        market = market_override
        market_matched_text = "manually overridden"
    else:
        market, market_matched_text = jd_parser.detect_market(jd_text, posting_url)

    country_code = jd_parser.guess_country_code(jd_text) if market == "INTL" else None
    location = jd_parser.extract_location(jd_text)

    if years_override is not None:
        years_required = float(years_override) if years_override != "" else None
        years_matched_text = "manually overridden"
    else:
        years_required, years_matched_text = jd_parser.extract_years_required(jd_text)

    eligibility = jd_parser.evaluate_eligibility(jd_text, market, profile)

    required_keywords = jd_parser.extract_keywords(jd_text, vocabulary)
    included_keyword_set = set()
    for b in included_bullets:
        included_keyword_set.update(b.get("keywords", []))
    matched_keywords = [kw for kw in required_keywords if kw in included_keyword_set]
    missing_keywords = [kw for kw in required_keywords if kw not in included_keyword_set]

    review = scoring.build_review(
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        years_required=years_required,
        years_have=profile["years_of_experience"],
        market=market,
        eligibility=eligibility,
        bullets=bullets,
    )

    return jsonify({
        "market": market,
        "market_matched_text": market_matched_text,
        "country_code": country_code,
        "location": location,
        "years_required": years_required,
        "years_matched_text": years_matched_text,
        "eligibility": eligibility,
        "review": review,
    })


@app.route("/api/bullets", methods=["POST"])
def api_add_bullet():
    body = request.get_json(force=True) or {}
    section = (body.get("section") or "").strip()
    entry = (body.get("entry") or "").strip()
    text = (body.get("text") or "").strip()
    keywords = [k.strip() for k in (body.get("keywords") or []) if k.strip()]

    if section not in ("Education", "Projects", "Work Experience"):
        return jsonify({"error": "section must be Education, Projects, or Work Experience"}), 400
    if not entry or not text:
        return jsonify({"error": "entry and text are required"}), 400

    vocabulary = storage.get_vocabulary()
    canonical_keywords, vocab_changed = _canonicalize_keywords(keywords, vocabulary)
    if vocab_changed:
        storage.save_vocabulary(vocabulary)

    bullets = storage.get_bullets()
    new_bullet = {
        "id": storage.next_bullet_id(bullets, section, entry),
        "section": section,
        "entry": entry,
        "text": text,
        "keywords": canonical_keywords,
        "included": False,
        "order": storage.next_order(bullets, section, entry),
    }
    bullets.append(new_bullet)
    storage.save_bullets(bullets)
    return jsonify({"bullet": new_bullet, "vocabulary": vocabulary}), 201


@app.route("/api/bullets/<bullet_id>", methods=["PATCH"])
def api_update_bullet(bullet_id):
    body = request.get_json(force=True) or {}
    bullets = storage.get_bullets()
    target = next((b for b in bullets if b["id"] == bullet_id), None)
    if target is None:
        return jsonify({"error": "bullet not found"}), 404

    vocabulary = None
    if "included" in body:
        target["included"] = bool(body["included"])
        if target["included"]:
            target["order"] = storage.next_order(
                [b for b in bullets if b["id"] != bullet_id], target["section"], target["entry"]
            )
    if "text" in body:
        target["text"] = body["text"]
    if "keywords" in body:
        keywords = [k.strip() for k in (body["keywords"] or []) if k.strip()]
        vocabulary = storage.get_vocabulary()
        canonical_keywords, vocab_changed = _canonicalize_keywords(keywords, vocabulary)
        if vocab_changed:
            storage.save_vocabulary(vocabulary)
        target["keywords"] = canonical_keywords
    if "order" in body:
        target["order"] = body["order"]

    storage.save_bullets(bullets)
    response = {"bullet": target}
    if vocabulary is not None:
        response["vocabulary"] = vocabulary
    return jsonify(response)


@app.route("/api/bullets/<bullet_id>", methods=["DELETE"])
def api_delete_bullet(bullet_id):
    bullets = storage.get_bullets()
    remaining = [b for b in bullets if b["id"] != bullet_id]
    if len(remaining) == len(bullets):
        return jsonify({"error": "bullet not found"}), 404
    storage.save_bullets(remaining)
    return jsonify({"ok": True})


@app.route("/api/vocabulary", methods=["POST"])
def api_add_vocabulary():
    body = request.get_json(force=True) or {}
    term = (body.get("term") or "").strip()
    aliases = [a.strip() for a in (body.get("aliases") or []) if a.strip()]
    if not term:
        return jsonify({"error": "term is required"}), 400

    vocabulary = storage.get_vocabulary()
    if _find_vocab_term(term, vocabulary):
        return jsonify({"error": "term already exists"}), 409

    entry = {"term": term, "aliases": aliases}
    vocabulary.append(entry)
    storage.save_vocabulary(vocabulary)
    return jsonify({"vocabulary": vocabulary}), 201


@app.route("/api/export", methods=["POST"])
def api_export():
    body = request.get_json(force=True) or {}
    market = body.get("market")
    country_code = body.get("country_code")
    company = (body.get("company") or "").strip()
    role_title = (body.get("role_title") or "").strip()
    posting_url = (body.get("posting_url") or "").strip()
    score = body.get("score")
    review_summary = body.get("review_summary") or ""
    eligibility_short = body.get("eligibility_short") or ""

    if market not in ("UK", "US", "INTL"):
        return jsonify({"error": "market must be UK, US, or INTL"}), 400
    if not company or not role_title:
        return jsonify({"error": "company and role_title are required"}), 400
    if score is None:
        return jsonify({"error": "score is required"}), 400

    bullets = storage.get_bullets()
    try:
        result = export.export_application(
            bullets=bullets, market=market, country_code=country_code,
            company=company, role_title=role_title, posting_url=posting_url,
            score=score, review_summary=review_summary, eligibility_short=eligibility_short,
        )
    except ExportError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
