import json
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BULLETS_PATH = DATA_DIR / "bullets.json"
VOCABULARY_PATH = DATA_DIR / "vocabulary.json"
PROFILE_PATH = DATA_DIR / "profile.json"

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
