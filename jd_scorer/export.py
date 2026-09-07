import csv
import shutil
import subprocess
from copy import deepcopy
from datetime import date
from pathlib import Path

import docx
from docx.text.paragraph import Paragraph

from .scoring import MIN_LOGGABLE_SCORE

JOB_ROOT = Path(r"C:\Users\yuddu\Desktop\cs\job")
TEMPLATE_PATH = JOB_ROOT / "_templates" / "YudWong_Resume_Master.docx"

CSV_PATHS = {
    "UK": JOB_ROOT / "uk_pipeline_log.csv",
    "US": JOB_ROOT / "us_pipeline_log.csv",
    "INTL": JOB_ROOT / "intl_pipeline_log.csv",
}

CSV_COLUMNS = {
    "UK": ["date_found", "title_query", "company", "role_title", "posting_url", "score",
           "resume_variant", "hard_blocker", "window", "tailored", "resume_pdf", "cl_pdf",
           "applied_status", "legacy_source", "review_summary"],
    "US": ["date_found", "title_query", "company", "role_title", "posting_url", "score",
           "resume_variant", "sponsorship_signal", "window", "tailored", "resume_pdf", "cl_pdf",
           "applied_status", "legacy_source", "review_summary"],
    "INTL": ["date_found", "country_code", "category", "company", "role_title", "posting_url",
             "score", "sponsorship_signal", "window", "tailored", "resume_pdf", "cl_pdf",
             "applied_status", "review_summary"],
}


class ExportError(Exception):
    pass


# --- docx rendering -----------------------------------------------------------

def _collapse_to_single_run(paragraph, text):
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


def get_template_entry_dates():
    """Reads the master template's entry heading lines and returns a dict of
    {entry text before the tab: date text after the tab}, so the live preview
    can show dates (e.g. "Summer 2025") without those dates living in
    bullets.json -- they stay sourced from the one real docx.
    """
    if not TEMPLATE_PATH.exists():
        return {}
    document = docx.Document(str(TEMPLATE_PATH))
    dates = {}
    for p in document.paragraphs:
        if p.style.name == "List Paragraph" or "\t" not in p.text:
            continue
        before, _, after = p.text.partition("\t")
        before, after = before.strip(), after.strip()
        if before and after:
            dates[before] = after
    return dates


def render_resume_docx(bullets, output_path):
    """Copies the master template and replaces bullet-paragraph text in place,
    preserving formatting. Never touches the name/contact block or entry
    heading lines (title, company, dates) -- only the bullet body paragraphs.
    """
    if not TEMPLATE_PATH.exists():
        raise ExportError(f"Resume template not found at {TEMPLATE_PATH}")

    shutil.copyfile(TEMPLATE_PATH, output_path)
    document = docx.Document(str(output_path))
    original_paragraphs = list(document.paragraphs)
    n = len(original_paragraphs)

    groups = {}
    for b in bullets:
        if not b.get("included", True):
            continue
        key = (b["section"], b["entry"])
        groups.setdefault(key, []).append(b)
    for key in groups:
        groups[key].sort(key=lambda b: b["order"])

    entry_lookup = {entry.strip(): (section, entry) for (section, entry) in groups}
    handled_keys = set()
    last_heading_p = {}   # section -> lxml element, for appending brand-new entries
    last_list_template = {}  # section -> lxml element

    i = 0
    while i < n:
        p = original_paragraphs[i]
        if p.style.name == "List Paragraph":
            i += 1
            continue

        heading_text = p.text.split("\t")[0].strip()
        matched_key = entry_lookup.get(heading_text)

        # track section headers as we pass them, to know which section we're in
        for section in ("Education", "Projects", "Work Experience"):
            if p.text.strip() == section:
                current_section = section

        if matched_key is None:
            i += 1
            continue

        section, entry = matched_key
        handled_keys.add(matched_key)
        bullet_list = groups[matched_key]
        last_heading_p[section] = p._p

        if section == "Education":
            if bullet_list and len(p.runs) >= 2:
                p.runs[-1].text = bullet_list[0]["text"]
            i += 1
            continue

        j = i + 1
        list_paragraphs = []
        while j < n and original_paragraphs[j].style.name == "List Paragraph":
            list_paragraphs.append(original_paragraphs[j])
            j += 1

        template_element = deepcopy(list_paragraphs[0]._p) if list_paragraphs else last_list_template.get(section)
        if template_element is not None:
            last_list_template[section] = template_element

        for lp in list_paragraphs:
            lp._p.getparent().remove(lp._p)

        if bullet_list and template_element is not None:
            anchor_p = p._p
            for bullet in bullet_list:
                new_p = deepcopy(template_element)
                anchor_p.addnext(new_p)
                anchor_p = new_p
                _collapse_to_single_run(Paragraph(new_p, p._parent), bullet["text"])

        i = j

    # Any bullet groups whose entry wasn't found anywhere in the template are
    # brand-new entries added through the app -- append them at the end of
    # their section using the last known heading/bullet formatting in it.
    leftover = [key for key in groups if key not in handled_keys and key[0] != "Education"]
    for section, entry in leftover:
        heading_anchor = last_heading_p.get(section)
        list_template = last_list_template.get(section)
        if heading_anchor is None or list_template is None:
            continue  # no formatting to clone from; skip rather than guess
        new_heading = deepcopy(heading_anchor)
        heading_anchor.addnext(new_heading)
        heading_paragraph = Paragraph(new_heading, document.paragraphs[0]._parent)
        _collapse_to_single_run(heading_paragraph, entry)

        anchor_p = new_heading
        for bullet in groups[(section, entry)]:
            new_p = deepcopy(list_template)
            anchor_p.addnext(new_p)
            anchor_p = new_p
            _collapse_to_single_run(Paragraph(new_p, document.paragraphs[0]._parent), bullet["text"])

    document.save(str(output_path))
    return output_path


# --- PDF conversion + verification --------------------------------------------

def convert_to_pdf(docx_path, pdf_path):
    from docx2pdf import convert
    convert(str(docx_path), str(pdf_path))
    if not Path(pdf_path).exists():
        raise ExportError("docx2pdf did not produce a PDF file.")
    return pdf_path


def verify_pdf(pdf_path):
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except FileNotFoundError:
        return {"ok": None, "note": "pdftotext not found on PATH -- skipped verification."}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "note": f"pdftotext failed: {e.stderr}"}

    text = result.stdout
    required = ["Yud Wong", "Education", "Projects", "Work Experience"]
    missing = [r for r in required if r not in text]
    if missing:
        return {"ok": False, "note": f"PDF missing expected sections: {', '.join(missing)}"}
    return {"ok": True, "note": "Header and section headers present."}


# --- folder / filename conventions --------------------------------------------

def _location_code(market, country_code):
    if market in ("UK", "US"):
        return market
    return country_code or "OTHER"


def dated_folder(market, country_code):
    today = date.today()
    mmdd = today.strftime("%m%d")
    location = _location_code(market, country_code)
    folder = JOB_ROOT / f"{mmdd}_{location}_cvs&cls"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def resume_filename(role_title, company, market, country_code):
    location = _location_code(market, country_code)
    safe_role = role_title.strip() or "Role"
    safe_company = company.strip() or "Company"
    return f"Yud Wong - {safe_role} Resume - {safe_company} ({location}).pdf"


# --- CSV logging ----------------------------------------------------------------

def upsert_csv_row(market, row):
    """Appends a new row, or -- if a row already exists in this market's CSV
    with the same resume_pdf filename (i.e. this export overwrote a file from
    an earlier export of the same application) -- replaces that row in place
    instead of duplicating it. Preserves the file's existing LF-only line
    endings; csv.writer defaults to CRLF, which would otherwise mix line
    endings into an all-LF file. Returns "updated" or "appended".
    """
    path = CSV_PATHS[market]
    columns = CSV_COLUMNS[market]
    ordered_row = [row.get(col, "") for col in columns]
    pdf_col = columns.index("resume_pdf")
    target_pdf = row.get("resume_pdf", "")

    with open(path, "r", newline="", encoding="utf-8") as f:
        all_rows = list(csv.reader(f))
    header, data_rows = all_rows[0], all_rows[1:]

    action = "appended"
    if target_pdf:
        for i, existing in enumerate(data_rows):
            if len(existing) > pdf_col and existing[pdf_col] == target_pdf:
                data_rows[i] = ordered_row
                action = "updated"
                break
    if action == "appended":
        data_rows.append(ordered_row)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(data_rows)
    return action


def build_csv_row(*, market, country_code, company, role_title, posting_url, score,
                   review_summary, resume_pdf_name, eligibility_short):
    today_iso = date.today().isoformat()
    common = {
        "date_found": today_iso,
        "company": company,
        "role_title": role_title,
        "posting_url": posting_url or "",
        "score": score,
        "window": "APP",
        "tailored": "yes",
        "resume_pdf": resume_pdf_name,
        "cl_pdf": "",
        "applied_status": "",
        "review_summary": review_summary,
    }
    if market == "UK":
        common.update({"title_query": "app", "resume_variant": "Default",
                       "hard_blocker": eligibility_short, "legacy_source": ""})
    elif market == "US":
        common.update({"title_query": "app", "resume_variant": "Default",
                       "sponsorship_signal": eligibility_short, "legacy_source": ""})
    else:
        common.update({"country_code": country_code or "OTHER", "category": "Default",
                       "sponsorship_signal": eligibility_short})
    return common


# --- orchestration ---------------------------------------------------------------

def export_application(*, bullets, market, country_code, company, role_title, posting_url,
                        score, review_summary, eligibility_short):
    folder = dated_folder(market, country_code)
    pdf_name = resume_filename(role_title, company, market, country_code)
    pdf_path = folder / pdf_name
    docx_path = folder / (pdf_name[:-4] + ".docx")

    render_resume_docx(bullets, docx_path)
    convert_to_pdf(docx_path, pdf_path)
    verification = verify_pdf(pdf_path)
    docx_path.unlink(missing_ok=True)

    logged = False
    csv_action = None
    if score >= MIN_LOGGABLE_SCORE:
        row = build_csv_row(
            market=market, country_code=country_code, company=company, role_title=role_title,
            posting_url=posting_url, score=score, review_summary=review_summary,
            resume_pdf_name=pdf_name, eligibility_short=eligibility_short,
        )
        csv_action = upsert_csv_row(market, row)
        logged = True

    return {
        "resume_pdf": str(pdf_path),
        "verification": verification,
        "logged_to_csv": logged,
        "csv_action": csv_action,
        "csv_path": str(CSV_PATHS[market]) if logged else None,
    }
