import csv
import json
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request

JOB_ROOT = Path(r"C:\Users\yuddu\Desktop\cs\job")
UK_CSV = JOB_ROOT / "uk_pipeline_log.csv"
US_CSV = JOB_ROOT / "us_pipeline_log.csv"

DASHBOARD_DIR = Path(__file__).resolve().parent
STATUS_FILE = DASHBOARD_DIR / "data" / "application_status.json"

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

STATUS_OPTIONS = ["Not applied yet", "Applied", "Interview", "Rejection", "Landed"]

app = Flask(__name__)


def load_status_overrides():
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_status_overrides(overrides):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, sort_keys=True)


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
    if score >= 80:
        return "strong"
    if score >= 70:
        return "good"
    return "below"


def parse_csv(path, market):
    postings = []
    if not path.exists():
        return postings

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            score_raw = (row.get("score") or "").strip()
            if not score_raw:
                continue
            try:
                score = int(float(score_raw))
            except ValueError:
                continue
            if not (0 <= score <= 100):
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
                    "date_found": date_found,
                    "title_query": (row.get("title_query") or "").strip(),
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


@app.route("/api/postings")
def api_postings():
    postings = parse_csv(UK_CSV, "UK") + parse_csv(US_CSV, "US")
    overrides = load_status_overrides()
    for p in postings:
        if p["key"] in overrides:
            p["status"] = overrides[p["key"]]
        else:
            p["status"] = "Applied" if p["applied_status_raw"] else "Not applied yet"
    return jsonify(postings)


@app.route("/api/status", methods=["POST"])
def api_set_status():
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key")
    status = data.get("status")

    if not key or status not in STATUS_OPTIONS:
        return jsonify({"error": "invalid key or status"}), 400

    overrides = load_status_overrides()
    overrides[key] = status
    save_status_overrides(overrides)
    return jsonify({"ok": True, "key": key, "status": status})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
