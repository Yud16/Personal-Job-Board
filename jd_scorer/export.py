import csv
import multiprocessing
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


def _rename_heading_prefix(paragraph, new_name):
    """Replaces just the entry-name portion of a heading paragraph (every
    run before the tab that separates name from date) with new_name, leaving
    the tab run and any date run(s) after it completely untouched. Every
    entry heading in the real template keeps the tab as its own isolated
    run, so this preserves a real date through a rename. Falls back to a
    full collapse if there's no tab run to anchor on.
    """
    runs = paragraph.runs
    tab_idx = next((i for i, r in enumerate(runs) if "\t" in r.text), None)
    if tab_idx is None:
        _collapse_to_single_run(paragraph, new_name)
        return
    runs[0].text = new_name
    for r in runs[1:tab_idx]:
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


SECTIONS = ("Education", "Projects", "Work Experience")


def render_resume_docx(bullets, layout, output_path):
    """Copies the master template and rebuilds it to reflect the current
    bullets plus the entry hide/reorder state and section order from
    layout.json. An entry that's simply kept or reordered reuses its exact
    original heading paragraph in place (preserving real formatting and any
    date text) -- only its bullet-list body is regenerated. Only a genuinely
    new or renamed entry (whose name no longer matches anything in the
    template) falls back to cloning the section's last known heading/list
    formatting, which means it renders with no date, same as before: dates
    live only in the one real template, per get_template_entry_dates().
    Hidden entries are removed entirely. Sections are physically relocated
    to match layout["section_order"], carrying their real formatting with
    them.
    """
    if not TEMPLATE_PATH.exists():
        raise ExportError(f"Resume template not found at {TEMPLATE_PATH}")

    entry_included = {(e["section"], e["entry"]): e["included"] for e in layout["entries"]}
    section_order = layout.get("section_order") or list(SECTIONS)

    shutil.copyfile(TEMPLATE_PATH, output_path)
    document = docx.Document(str(output_path))
    body = document.element.body
    doc_parent = document.paragraphs[0]._parent
    original_paragraphs = list(document.paragraphs)
    n = len(original_paragraphs)

    groups = {}
    for b in bullets:
        if not b.get("included", True):
            continue
        key = (b["section"], b["entry"])
        if not entry_included.get(key, True):
            continue
        groups.setdefault(key, []).append(b)
    for key in groups:
        groups[key].sort(key=lambda b: b["order"])

    # Keyed by each entry's stable template_key (its name at the time its
    # layout record was created), not its current display name, so a rename
    # doesn't lose track of that entry's real heading in the template.
    entry_lookup = {}
    for e in layout["entries"]:
        template_text = (e.get("template_key") or e["entry"]).strip()
        entry_lookup[template_text] = (e["section"], e["entry"])

    # --- Pass 1: walk the original template, recording each section header
    # element, each recognized entry's original element block, and a
    # heading/list template per section for cloning new/renamed entries.
    section_header_el = {}
    recognized = {}  # (section, entry) -> {"heading": el, "list_items": [el, ...]}
    last_heading_template = {}
    last_list_template = {}

    i = 0
    while i < n:
        p = original_paragraphs[i]
        if p.style.name == "List Paragraph":
            i += 1
            continue

        heading_text = p.text.split("\t")[0].strip()
        matched_key = entry_lookup.get(heading_text)

        for section in SECTIONS:
            if p.text.strip() == section:
                section_header_el[section] = p._p

        if matched_key is None:
            i += 1
            continue

        section, entry = matched_key
        last_heading_template[section] = deepcopy(p._p)

        if section == "Education":
            recognized[matched_key] = {"heading": p._p, "list_items": []}
            i += 1
            continue

        j = i + 1
        list_els = []
        while j < n and original_paragraphs[j].style.name == "List Paragraph":
            list_els.append(original_paragraphs[j]._p)
            j += 1
        if list_els:
            last_list_template[section] = deepcopy(list_els[0])
        recognized[(section, entry)] = {"heading": p._p, "list_items": list_els}
        i = j

    # --- Pass 2: detach every recognized entry's original elements. Hidden
    # or dropped ones simply never get reinserted below; kept ones get
    # rebuilt fresh (their heading is reused, their bullet list regenerated).
    for block in recognized.values():
        for el in [block["heading"]] + block["list_items"]:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    # --- Pass 3: rebuild each section's entries in the desired order,
    # immediately after that section's header.
    for section in SECTIONS:
        header_el = section_header_el.get(section)
        if header_el is None:
            continue
        section_entries = [e for e in layout["entries"] if e["section"] == section and e["included"]]
        section_entries.sort(key=lambda e: e["order"])

        if not section_entries:
            # Every entry in this section is hidden -- drop the section
            # header too, so an empty section doesn't show up with nothing
            # under it (matches the live preview, which does the same).
            parent = header_el.getparent()
            if parent is not None:
                parent.remove(header_el)
            del section_header_el[section]
            continue

        anchor = header_el
        for e in section_entries:
            key = (e["section"], e["entry"])
            bullet_list = groups.get(key, [])
            block = recognized.get(key)

            if block is not None:
                heading_el = block["heading"]
                anchor.addnext(heading_el)
                anchor = heading_el
                heading_paragraph = Paragraph(heading_el, doc_parent)
                if e["entry"] != e.get("template_key", e["entry"]):
                    _rename_heading_prefix(heading_paragraph, e["entry"])
                if section == "Education" and bullet_list:
                    if len(heading_paragraph.runs) >= 2:
                        heading_paragraph.runs[-1].text = bullet_list[0]["text"]
            else:
                template_el = last_heading_template.get(section)
                if template_el is None:
                    continue  # no formatting to clone from; skip rather than guess
                heading_el = deepcopy(template_el)
                anchor.addnext(heading_el)
                anchor = heading_el
                _collapse_to_single_run(Paragraph(heading_el, doc_parent), e["entry"])

            if section == "Education":
                continue

            list_template = last_list_template.get(section)
            if list_template is None:
                continue
            for bullet in bullet_list:
                new_p = deepcopy(list_template)
                anchor.addnext(new_p)
                anchor = new_p
                _collapse_to_single_run(Paragraph(new_p, doc_parent), bullet["text"])

    # --- Pass 4: reorder whole sections to match section_order, physically
    # relocating each section's header and everything now living under it.
    present_sections = [s for s in SECTIONS if s in section_header_el]
    if len(present_sections) > 1:
        header_els = {s: section_header_el[s] for s in present_sections}

        def collect_range(s):
            head = header_els[s]
            stop_set = {el for s2, el in header_els.items() if s2 != s}
            elements = [head]
            for sib in head.itersiblings():
                if sib in stop_set:
                    break
                elements.append(sib)
            return elements

        ranges = {s: collect_range(s) for s in present_sections}
        first_section = min(present_sections, key=lambda s: body.index(header_els[s]))
        insertion_anchor = header_els[first_section].getprevious()

        for s in present_sections:
            for el in ranges[s]:
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)

        for s in [s for s in section_order if s in present_sections]:
            for el in ranges[s]:
                if insertion_anchor is None:
                    body.insert(0, el)
                else:
                    insertion_anchor.addnext(el)
                insertion_anchor = el

    document.save(str(output_path))
    return output_path


# --- PDF conversion + verification --------------------------------------------

def _convert_worker(docx_path, pdf_path, queue):
    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        queue.put(None)
    except Exception as e:
        queue.put(str(e))


def convert_to_pdf(docx_path, pdf_path, timeout=90):
    """Runs docx2pdf (drives real Microsoft Word via COM automation) in a
    subprocess with a timeout. Without this, a Word dialog stuck waiting for
    input (a compatibility prompt, an autosave-recovery notice) hangs this
    call -- and the whole export request -- forever with no feedback, which
    is exactly what a stuck export looks like from the UI.
    """
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=_convert_worker, args=(str(docx_path), str(pdf_path), queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise ExportError(
            f"PDF conversion timed out after {timeout}s -- Microsoft Word is likely stuck "
            "on a dialog box. Check for a hidden Word window, close it, and try exporting again."
        )
    error = queue.get() if not queue.empty() else None
    if error:
        raise ExportError(f"PDF conversion failed: {error}")
    if not Path(pdf_path).exists():
        raise ExportError("docx2pdf did not produce a PDF file.")
    return pdf_path


def verify_pdf(pdf_path, expected_sections=SECTIONS):
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
    required = ["Yud Wong", *expected_sections]
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

def export_application(*, bullets, layout, market, country_code, company, role_title, posting_url,
                        score, review_summary, eligibility_short):
    folder = dated_folder(market, country_code)
    pdf_name = resume_filename(role_title, company, market, country_code)
    pdf_path = folder / pdf_name
    docx_path = folder / (pdf_name[:-4] + ".docx")

    render_resume_docx(bullets, layout, docx_path)
    convert_to_pdf(docx_path, pdf_path)
    expected_sections = [
        s for s in SECTIONS
        if any(e["section"] == s and e["included"] for e in layout["entries"])
    ]
    verification = verify_pdf(pdf_path, expected_sections)
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
