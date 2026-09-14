import json
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BULLETS_PATH = DATA_DIR / "bullets.json"
VOCABULARY_PATH = DATA_DIR / "vocabulary.json"
PROFILE_PATH = DATA_DIR / "profile.json"
LAYOUT_PATH = DATA_DIR / "layout.json"

SECTIONS = ("Education", "Projects", "Work Experience")

_lock = threading.Lock()


def _load(path):
    with _lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def _save(path, data):
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")


def get_bullets():
    return _load(BULLETS_PATH)


def save_bullets(bullets):
    _save(BULLETS_PATH, bullets)


def get_vocabulary():
    return _load(VOCABULARY_PATH)


def save_vocabulary(vocabulary):
    _save(VOCABULARY_PATH, vocabulary)


def get_profile():
    return _load(PROFILE_PATH)


def save_profile(profile):
    _save(PROFILE_PATH, profile)


def next_bullet_id(bullets, section, entry):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in entry)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")[:24] or section.lower()
    existing_ids = {b["id"] for b in bullets}
    n = 1
    candidate = f"{slug}-custom-{n}"
    while candidate in existing_ids:
        n += 1
        candidate = f"{slug}-custom-{n}"
    return candidate


def next_order(bullets, section, entry):
    matching = [b["order"] for b in bullets if b["section"] == section and b["entry"] == entry]
    return (max(matching) + 1) if matching else 1


def _slugify(text, max_len=40):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in text)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:max_len]


def _entry_id(section, entry, existing_ids):
    base = f"{_slugify(section)}--{_slugify(entry)}" or "entry"
    if base not in existing_ids:
        return base
    n = 2
    candidate = f"{base}-{n}"
    while candidate in existing_ids:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _synthesize_layout(bullets):
    """Builds a default layout from bullets.json for the first time this app
    runs with the layout concept: entries are registered in the order they're
    first encountered (preserving current visual order), all included.

    "template_key" records the entry's name at the moment its layout record
    is created, and is never touched by a later rename -- it's what export
    uses to find this entry's original heading in the master template, so a
    rename doesn't lose track of that entry's real formatting/date.
    """
    entries = []
    ids = set()
    for b in bullets:
        key = (b["section"], b["entry"])
        if any(e["section"] == key[0] and e["entry"] == key[1] for e in entries):
            continue
        eid = _entry_id(b["section"], b["entry"], ids)
        ids.add(eid)
        section_count = sum(1 for e in entries if e["section"] == b["section"])
        entries.append({
            "id": eid,
            "section": b["section"],
            "entry": b["entry"],
            "template_key": b["entry"],
            "included": True,
            "order": section_count + 1,
        })
    return {"section_order": list(SECTIONS), "entries": entries}


def get_layout():
    """Loads layout.json, synthesizing it from bullets.json on first run,
    reconciling any (section, entry) pairs bullets.json knows about that the
    stored layout doesn't yet (e.g. a bullet added before this file existed),
    and backfilling "template_key" on any entry saved before that field
    existed (safe to default to its current name, since it can only have
    drifted from the template if it had already been renamed under the old
    schema -- a case that didn't previously work correctly anyway).
    """
    bullets = get_bullets()
    if not LAYOUT_PATH.exists():
        layout = _synthesize_layout(bullets)
        save_layout(layout)
        return layout

    layout = _load(LAYOUT_PATH)
    known = {(e["section"], e["entry"]) for e in layout["entries"]}
    ids = {e["id"] for e in layout["entries"]}
    changed = False
    for e in layout["entries"]:
        if "template_key" not in e:
            e["template_key"] = e["entry"]
            changed = True
    for b in bullets:
        key = (b["section"], b["entry"])
        if key in known:
            continue
        known.add(key)
        eid = _entry_id(b["section"], b["entry"], ids)
        ids.add(eid)
        section_count = sum(1 for e in layout["entries"] if e["section"] == b["section"])
        layout["entries"].append({
            "id": eid,
            "section": b["section"],
            "entry": b["entry"],
            "template_key": b["entry"],
            "included": True,
            "order": section_count + 1,
        })
        changed = True
    if changed:
        save_layout(layout)
    return layout


def save_layout(layout):
    _save(LAYOUT_PATH, layout)
