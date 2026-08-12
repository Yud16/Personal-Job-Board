# Job search dashboard

A local Flask app that reads the job-search pipeline's CSV logs and presents them as a kanban board, grouped by match score, with a per-posting detail view and application-status tracking. It is read-only with respect to the pipeline's data — it never modifies the CSVs, triggers searches, or generates documents.

## Technology

- **Backend**: Python 3, [Flask](https://flask.palletsprojects.com/) (single-process dev server, no database)
- **Frontend**: vanilla HTML/CSS/JS — no build step, no framework, no dependencies beyond what ships in the browser
- **Data**: read directly from the pipeline's CSV files via Python's `csv` module on every request (no caching layer)
- **Persistence**: a single JSON file for the one piece of state this app owns (application status)

No package.json, no bundler, no ORM. The entire app is four files.

## Architecture

```
Browser (kanban UI)
     │  fetch() calls
     ▼
Flask app (app.py)
     │  reads                          │  reads/writes
     ▼                                  ▼
uk_pipeline_log.csv              data/application_status.json
us_pipeline_log.csv              (status overrides, keyed by posting)
(owned by the scheduled            (owned by this dashboard)
 pipeline tasks — never
 written to by this app)
```

The dashboard sits strictly downstream of the pipeline. The two CSVs are the source of truth for postings, scores, and tailoring state; this app only ever reads them. The one piece of data this app *does* own — application status (Not applied yet / Applied / Interview / Rejection / Landed) — lives in its own JSON file specifically so a card status update can never collide with the scheduled tasks appending new rows.

### Request flow

1. Browser loads `/` → Flask renders `templates/index.html` (static shell, no server-side data embedded).
2. Page JS (`static/app.js`) calls `GET /api/postings` on load and on every "Refresh" click.
3. `app.py` re-reads both CSVs from disk on every call to `/api/postings` — there is no in-memory cache, so the board always reflects the current file contents.
4. Each parsed row is merged with its status: `data/application_status.json` if an override exists, otherwise a default derived from the CSV's own `applied_status` column (see "Status tracking" below).
5. The full posting list comes back as JSON; all filtering (market, resume variant, status) and grouping (score tier) happens client-side in `app.js` — no query params, no server-side filtering.
6. Changing a status (from a card's inline dropdown or the detail modal) does `POST /api/status`, which writes straight to the JSON file. There is no queue or debounce; each change is one write.

### Files

| File | Role |
|---|---|
| `app.py` | Flask app: CSV parsing, status-file read/write, the two API routes, and the `/` route that serves the page shell |
| `templates/index.html` | Static page structure — column layout, filter controls, and the detail modal markup (all empty containers that JS fills in) |
| `static/app.js` | All UI logic: fetching, filtering, rendering cards, the detail modal, and status updates. No framework — direct DOM APIs (`createElement`, `addEventListener`) |
| `static/style.css` | All styling. CSS custom properties (`:root` variables) define the score/status color palette used by both badge and status-pill classes |
| `data/application_status.json` | The only mutable state this app writes. A flat `{posting_key: status}` map |

### CSV parsing (`parse_csv` in `app.py`)

Parsing is defensive by design, per known data-quality issues in the pipeline's output:

- A row is **skipped entirely** if `score` is missing or non-numeric, or if `date_found` doesn't match `YYYY-MM-DD`. This is how rows with shifted/corrupted columns (e.g. a scam listing that threw off the CSV structure) get silently dropped rather than crashing or rendering garbage.
- `resume_variant` values like `"SWE (historical, pre-migration)"` are cleaned by taking everything before `" ("`, so the UI only ever shows the plain variant name (`SWE`, `DevOps`, etc.).
- `tailored` (yes/no) and `score` are read and used independently — the UI never assumes a `tailored: yes` row has `score >= 70`, since stale pre-migration rows can violate that.
- The UK and US CSVs differ only in one column name (`hard_blocker` vs `sponsorship_signal`, same position/purpose). `app.py` reads whichever is present into a single `notes` field.

### Posting identity (`posting_key`)

Postings don't have a natural primary key in the CSV, but the status feature needs one that's stable across re-reads (the CSVs are re-parsed from scratch on every request, so array-index-based IDs would silently reassign if rows were ever reordered). The key is `{market}::{posting_url}`, falling back to `{market}::{date_found}::{company}::{role_title}` on the rare row with no URL. This key is what both `/api/postings` and `/api/status` use to join a posting to its saved status.

### Status tracking

Application status is a dashboard-only concept layered on top of the CSV data, not a CSV column the pipeline writes:

- **Default status** for a posting with no saved override: `"Applied"` if the CSV's own `applied_status` column has any text in it, otherwise `"Not applied yet"`. This was a one-time backfill rule for rows that already had freeform notes in that column before this feature existed.
- **Saved overrides** in `data/application_status.json` always take precedence over the default.
- Status can be changed from either the dropdown embedded in each card (styled as a colored pill) or the matching dropdown in the detail modal — both call the same `setStatus()` function in `app.js`, which posts to `/api/status` and re-renders on success.

### Kanban grouping and filtering

- **Columns** are fixed score tiers, computed server-side (`tier_for()` in `app.py`): Strong (≥80), Good (70–79), Below threshold (<70).
- **Filters** — market, resume variant, and status (multi-select checkboxes) — are all client-side in `app.js`'s `filteredPostings()`. Nothing is sent back to the server for filtering; the full posting set is fetched once and sliced in the browser.

### Detail modal

Clicking a card opens a centered modal (`#detailBackdrop` / `#detailPanel`) showing the full role title, score, a summary (the CSV's freeform notes if present, otherwise a plain sentence built from score/variant/tailored status), the status dropdown, and a link to the original posting. It closes on the × button, a click on the backdrop, or Escape.

There is deliberately no "open folder" action anymore — that required local filesystem access via a `/api/open-folder` endpoint (`os.startfile` / `explorer /select,`), which has been removed along with its button.

## Running it

```bash
cd "C:\Users\yuddu\Desktop\cs\projects\ClaudeIndeedJobBoard"
py app.py
```

Then open `http://127.0.0.1:5000`. `app.run(debug=True, ...)` is on, so editing any file auto-reloads the server — fine for local personal use, not something to expose beyond localhost.

## Out of scope (by design)

This app never writes to `uk_pipeline_log.csv` or `us_pipeline_log.csv`, never triggers a job search, and never generates or touches tailored resume/cover-letter documents. All of that remains the responsibility of the two scheduled pipeline tasks and the `tailor-job-application` skill.
