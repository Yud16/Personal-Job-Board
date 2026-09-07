const state = {
  bullets: [],
  vocabulary: [],
  profile: null,
  entryDates: {},
  lastAnalysis: null,
  lastJdText: "",
  lastPostingUrl: "",
  marketOverride: null,
  yearsOverride: null,
  extraRequiredKeywords: [],
  addBulletSection: "Education",
  addBulletKeywords: [],
  editingBulletId: null,
};

let dragState = null;

const RING_CIRCUMFERENCE = 238.8;

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// --- data loading -------------------------------------------------------------

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  state.bullets = data.bullets;
  state.vocabulary = data.vocabulary;
  state.profile = data.profile;
  state.entryDates = data.entry_dates || {};
  renderBulletLibrary();
  renderPreview();
  populateEntryOptions();
}

function findVocabTerm(term) {
  const needle = term.trim().toLowerCase();
  return state.vocabulary.find((v) => v.term.toLowerCase() === needle
    || (v.aliases || []).some((a) => a.toLowerCase() === needle));
}

// --- bullet library -------------------------------------------------------------

const SECTION_ORDER = ["Education", "Projects", "Work Experience"];

function groupBullets() {
  const groups = {};
  for (const section of SECTION_ORDER) groups[section] = {};
  for (const b of state.bullets) {
    if (!groups[b.section]) groups[b.section] = {};
    if (!groups[b.section][b.entry]) groups[b.section][b.entry] = [];
    groups[b.section][b.entry].push(b);
  }
  for (const section of Object.keys(groups)) {
    for (const entry of Object.keys(groups[section])) {
      groups[section][entry].sort((a, b) => a.order - b.order);
    }
  }
  return groups;
}

function renderBulletLibrary() {
  const container = el("bullet-sections");
  container.innerHTML = "";
  const groups = groupBullets();
  let total = 0, pending = 0;

  for (const section of SECTION_ORDER) {
    const entries = groups[section];
    if (!entries || Object.keys(entries).length === 0) continue;
    const sectionDiv = document.createElement("div");
    const label = document.createElement("div");
    label.className = "entry-label";
    label.textContent = section;
    sectionDiv.appendChild(label);

    for (const entry of Object.keys(entries)) {
      const entryDiv = document.createElement("div");
      entryDiv.className = "entry-group";
      if (Object.keys(entries).length > 1 || section !== "Education") {
        const entryTitle = document.createElement("div");
        entryTitle.style.cssText = "font-size:12px;font-weight:700;color:var(--ink-soft);margin:6px 0 2px 0;";
        entryTitle.textContent = entry;
        if (section !== "Education") entryDiv.appendChild(entryTitle);
      }
      for (const b of entries[entry]) {
        total++;
        if (!b.included) pending++;
        entryDiv.appendChild(renderBulletRow(b));
      }
      sectionDiv.appendChild(entryDiv);
    }
    container.appendChild(sectionDiv);
  }

  el("library-count").textContent = pending > 0
    ? `${total} lines, ${pending} pending`
    : `${total} lines`;
}

function renderBulletRow(bullet) {
  const row = document.createElement("div");
  row.className = "bullet-row" + (bullet.included ? "" : " excluded pending");
  row.draggable = true;

  row.addEventListener("dragstart", (e) => {
    dragState = { id: bullet.id, section: bullet.section, entry: bullet.entry };
    row.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", bullet.id);
  });
  row.addEventListener("dragend", () => {
    row.classList.remove("dragging");
    document.querySelectorAll(".bullet-row.drag-over").forEach((r) => r.classList.remove("drag-over"));
    dragState = null;
  });
  row.addEventListener("dragover", (e) => {
    if (!dragState || dragState.id === bullet.id
      || dragState.section !== bullet.section || dragState.entry !== bullet.entry) return;
    e.preventDefault();
    row.classList.add("drag-over");
  });
  row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
  row.addEventListener("drop", async (e) => {
    e.preventDefault();
    row.classList.remove("drag-over");
    if (!dragState || dragState.id === bullet.id) return;
    if (dragState.section !== bullet.section || dragState.entry !== bullet.entry) return;
    const draggedId = dragState.id;
    dragState = null;
    await reorderBullets(bullet.section, bullet.entry, draggedId, bullet.id);
  });

  const handle = document.createElement("span");
  handle.className = "drag-handle";
  handle.textContent = "⠿";
  handle.title = "Drag to reorder";
  row.appendChild(handle);

  const text = document.createElement("div");
  text.className = "text";
  text.textContent = bullet.text;
  if (!bullet.included) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "NOT ON RESUME";
    text.appendChild(badge);
  }
  row.appendChild(text);

  const actions = document.createElement("div");
  actions.className = "row-actions";

  const editBtn = document.createElement("button");
  editBtn.className = "icon-btn";
  editBtn.title = "Edit bullet";
  editBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
  editBtn.addEventListener("click", () => openEditBulletPanel(bullet));
  actions.appendChild(editBtn);

  const btn = document.createElement("button");
  btn.className = "icon-btn";
  btn.title = bullet.included ? "Remove from resume" : "Insert into resume";
  btn.innerHTML = bullet.included
    ? '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
    : '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>';
  btn.addEventListener("click", () => toggleBulletIncluded(bullet.id, !bullet.included));
  actions.appendChild(btn);

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "icon-btn";
  deleteBtn.title = "Delete from library";
  deleteBtn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
  deleteBtn.addEventListener("click", () => deleteBullet(bullet.id));
  actions.appendChild(deleteBtn);

  row.appendChild(actions);

  return row;
}

async function deleteBullet(id) {
  const bullet = state.bullets.find((b) => b.id === id);
  if (!bullet) return;
  const confirmed = confirm(`Delete this bullet from the library for good?\n\n"${bullet.text}"`);
  if (!confirmed) return;

  const res = await fetch(`/api/bullets/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "Could not delete this bullet.");
    return;
  }
  state.bullets = state.bullets.filter((b) => b.id !== id);
  renderBulletLibrary();
  renderPreview();
  populateEntryOptions();
  if (state.lastJdText) await runAnalyze();
}

async function reorderBullets(section, entry, draggedId, targetId) {
  const group = state.bullets
    .filter((b) => b.section === section && b.entry === entry)
    .sort((a, b) => a.order - b.order);
  const fromIdx = group.findIndex((b) => b.id === draggedId);
  if (fromIdx === -1) return;
  const [moved] = group.splice(fromIdx, 1);
  const toIdx = group.findIndex((b) => b.id === targetId);
  if (toIdx === -1) return;
  group.splice(toIdx, 0, moved);

  const updates = [];
  group.forEach((b, i) => {
    const newOrder = i + 1;
    if (b.order !== newOrder) {
      b.order = newOrder;
      updates.push(fetch(`/api/bullets/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order: newOrder }),
      }));
    }
  });
  await Promise.all(updates);
  renderBulletLibrary();
  renderPreview();
}

async function toggleBulletIncluded(id, included) {
  const res = await fetch(`/api/bullets/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ included }),
  });
  const data = await res.json();
  const idx = state.bullets.findIndex((b) => b.id === id);
  if (idx >= 0) state.bullets[idx] = data.bullet;
  renderBulletLibrary();
  renderPreview();
  if (state.lastJdText) await runAnalyze();
}

function populateEntryOptions() {
  const list = el("entry-options");
  list.innerHTML = "";
  const seen = new Set();
  for (const b of state.bullets) {
    if (b.section !== state.addBulletSection) continue;
    if (seen.has(b.entry)) continue;
    seen.add(b.entry);
    const opt = document.createElement("option");
    opt.value = b.entry;
    list.appendChild(opt);
  }
}

// --- live preview -------------------------------------------------------------

function renderEntryRow(entry) {
  const date = state.entryDates[entry];
  const dateHtml = date ? `<span class="date">${escapeHtml(date)}</span>` : "";
  return `<div class="preview-entry-row"><span>${escapeHtml(entry)}</span>${dateHtml}</div>`;
}

function renderPreview() {
  const groups = groupBullets();
  const preview = el("preview");
  let html = `
    <div class="preview-header">
      <div class="preview-name">Yud Wong</div>
      <div class="preview-contact">323.794.6504 &nbsp;|&nbsp; <span class="link-blue">yudduy11@gmail.com</span> &nbsp;|&nbsp; <span class="link-blue">GitHub</span> &nbsp;|&nbsp; <span class="link-blue">LinkedIn</span> &nbsp;|&nbsp; <span class="link-blue">Portfolio</span></div>
    </div>`;

  // Education
  const eduEntries = groups["Education"] || {};
  const eduEntry = Object.keys(eduEntries)[0];
  if (eduEntry) {
    const bullets = eduEntries[eduEntry].filter((b) => b.included);
    html += `<div class="preview-section-title">Education</div>`;
    html += `<div class="preview-entry-row"><span>${escapeHtml(eduEntry)}</span>`
      + `<span class="date">${escapeHtml(bullets[0] ? bullets[0].text : "")}</span></div>`;
  }

  // Projects
  const projEntries = groups["Projects"] || {};
  if (Object.keys(projEntries).length) {
    html += `<div class="preview-section-title">Projects</div>`;
    for (const entry of Object.keys(projEntries)) {
      const bullets = projEntries[entry].filter((b) => b.included);
      html += renderEntryRow(entry);
      html += `<ul class="preview-list">${bullets.map((b) => `<li>${escapeHtml(b.text)}</li>`).join("")}</ul>`;
    }
  }

  // Work Experience
  const workEntries = groups["Work Experience"] || {};
  if (Object.keys(workEntries).length) {
    html += `<div class="preview-section-title">Work Experience</div>`;
    for (const entry of Object.keys(workEntries)) {
      const bullets = workEntries[entry].filter((b) => b.included);
      html += renderEntryRow(entry);
      html += `<ul class="preview-list">${bullets.map((b) => `<li>${escapeHtml(b.text)}</li>`).join("")}</ul>`;
    }
  }

  preview.innerHTML = html;
}

// --- add bullet form -------------------------------------------------------------

function setupAddBulletForm() {
  el("toggle-add-bullet").addEventListener("click", () => {
    const panel = el("add-bullet-panel");
    if (panel.classList.contains("open") && !state.editingBulletId) {
      panel.classList.remove("open");
    } else {
      resetAddBulletForm();
      panel.classList.add("open");
    }
  });
  el("cancel-add-bullet").addEventListener("click", resetAddBulletForm);

  document.querySelectorAll(".section-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".section-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.addBulletSection = pill.dataset.section;
      populateEntryOptions();
    });
  });

  const input = el("keyword-input");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const val = input.value.trim().replace(/,$/, "");
      if (val) addKeywordTag(val);
      input.value = "";
      renderKeywordSuggestions("");
      input.focus();
    } else if (e.key === "Backspace" && input.value === "" && state.addBulletKeywords.length > 0) {
      e.preventDefault();
      state.addBulletKeywords.pop();
      renderKeywordTags();
      renderKeywordSuggestions("");
    }
  });
  input.addEventListener("input", () => renderKeywordSuggestions(input.value.trim()));

  el("save-bullet").addEventListener("click", saveBullet);
}

function openEditBulletPanel(bullet) {
  state.editingBulletId = bullet.id;
  state.addBulletSection = bullet.section;
  state.addBulletKeywords = [...(bullet.keywords || [])];

  document.querySelectorAll(".section-pill").forEach((p) => {
    p.classList.toggle("active", p.dataset.section === bullet.section);
  });
  populateEntryOptions();

  el("bullet-entry").value = bullet.entry;
  el("bullet-entry").disabled = true;
  el("bullet-text").value = bullet.text;
  el("keyword-input").value = "";
  renderKeywordTags();
  renderKeywordSuggestions("");

  el("section-pills").classList.add("disabled-group");
  el("add-bullet-panel-title").textContent = "Edit bullet";
  el("save-bullet").textContent = "Save changes";
  el("add-bullet-panel").classList.add("open");
  el("add-bullet-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function addKeywordTag(term) {
  if (state.addBulletKeywords.some((k) => k.toLowerCase() === term.toLowerCase())) return;
  state.addBulletKeywords.push(term);
  renderKeywordTags();
}

function removeKeywordTag(term) {
  state.addBulletKeywords = state.addBulletKeywords.filter((k) => k !== term);
  renderKeywordTags();
}

function renderKeywordTags() {
  const row = el("keyword-tags");
  const input = el("keyword-input");
  row.querySelectorAll(".keyword-tag").forEach((n) => n.remove());
  for (const term of state.addBulletKeywords) {
    const known = findVocabTerm(term);
    const tag = document.createElement("span");
    tag.className = "keyword-tag" + (known ? "" : " new-term");
    tag.innerHTML = `${escapeHtml(term)}${known ? "" : ' <span style="font-style:italic;font-weight:400;">(new term)</span>'}`;
    const removeBtn = document.createElement("button");
    removeBtn.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    removeBtn.addEventListener("click", () => removeKeywordTag(term));
    tag.appendChild(removeBtn);
    row.insertBefore(tag, input);
  }
}

function renderKeywordSuggestions(query) {
  const box = el("keyword-suggestions");
  box.innerHTML = "";
  if (!query) return;
  const q = query.toLowerCase();
  const matches = state.vocabulary
    .filter((v) => v.term.toLowerCase().includes(q))
    .filter((v) => !state.addBulletKeywords.some((k) => k.toLowerCase() === v.term.toLowerCase()))
    .slice(0, 6);
  for (const v of matches) {
    const chip = document.createElement("span");
    chip.className = "keyword-suggestion";
    chip.textContent = v.term;
    chip.addEventListener("click", () => {
      addKeywordTag(v.term);
      el("keyword-input").value = "";
      renderKeywordSuggestions("");
      el("keyword-input").focus();
    });
    box.appendChild(chip);
  }
  if (!state.vocabulary.some((v) => v.term.toLowerCase() === q)) {
    const create = document.createElement("span");
    create.className = "keyword-suggestion";
    create.textContent = `+ create "${query}"`;
    create.addEventListener("click", () => {
      addKeywordTag(query);
      el("keyword-input").value = "";
      renderKeywordSuggestions("");
      el("keyword-input").focus();
    });
    box.appendChild(create);
  }
}

function resetAddBulletForm() {
  el("add-bullet-panel").classList.remove("open");
  el("bullet-entry").value = "";
  el("bullet-entry").disabled = false;
  el("bullet-text").value = "";
  el("keyword-input").value = "";
  state.addBulletKeywords = [];
  state.editingBulletId = null;
  el("section-pills").classList.remove("disabled-group");
  el("add-bullet-panel-title").textContent = "Add bullet";
  el("save-bullet").textContent = "Add to library";
  renderKeywordTags();
  renderKeywordSuggestions("");
}

async function saveBullet() {
  const text = el("bullet-text").value.trim();
  if (!text) {
    alert("Bullet text is required.");
    return;
  }

  if (state.editingBulletId) {
    const res = await fetch(`/api/bullets/${state.editingBulletId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, keywords: state.addBulletKeywords }),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.error || "Could not save changes.");
      return;
    }
    const data = await res.json();
    const idx = state.bullets.findIndex((b) => b.id === data.bullet.id);
    if (idx >= 0) state.bullets[idx] = data.bullet;
    if (data.vocabulary) state.vocabulary = data.vocabulary;
    resetAddBulletForm();
    renderBulletLibrary();
    renderPreview();
    if (state.lastJdText) await runAnalyze();
    return;
  }

  const entry = el("bullet-entry").value.trim();
  if (!entry) {
    alert("Entry and bullet text are both required.");
    return;
  }
  const res = await fetch("/api/bullets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      section: state.addBulletSection,
      entry, text,
      keywords: state.addBulletKeywords,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "Could not add bullet.");
    return;
  }
  const data = await res.json();
  state.bullets.push(data.bullet);
  state.vocabulary = data.vocabulary;
  resetAddBulletForm();
  renderBulletLibrary();
  populateEntryOptions();
  if (state.lastJdText) await runAnalyze();
}

// --- analyze / score -------------------------------------------------------------

function renderScore(data) {
  const review = data.review;
  el("score-card").classList.remove("hidden");
  el("keyword-card").classList.remove("hidden");
  el("years-card").classList.remove("hidden");

  const score = review.match_score;
  el("score-value").textContent = score;
  const offset = RING_CIRCUMFERENCE * (1 - score / 100);
  el("score-arc").style.strokeDashoffset = offset;
  const arcColor = score >= 70 ? "#7A8F5C" : (score >= 50 ? "#B5502A" : "#A13B1C");
  el("score-arc").setAttribute("stroke", arcColor);

  let verdict = "Worth a look";
  if (review.eligibility.status === "hard_blocked") verdict = "Hard blocked";
  else if (score < 50) verdict = "Weak fit";
  else if (score < 70) verdict = "Possible fit";
  el("score-verdict").textContent = `“${verdict}”`;

  el("market-pill").textContent = data.market + (data.country_code ? ` · ${data.country_code}` : "");
  const eligPill = el("eligibility-pill");
  eligPill.textContent = review.eligibility.status === "eligible" ? "Eligible"
    : review.eligibility.status === "hard_blocked" ? "Hard blocked" : "Unconfirmed";
  eligPill.className = "pill " + (review.eligibility.status === "eligible" ? "pill-good"
    : review.eligibility.status === "hard_blocked" ? "pill-bad" : "pill-neutral");
  el("location-line").textContent = data.location ? `Location: ${data.location}` : "Location: not listed";

  renderKeywordCoverage(review);
  renderYears(review, data);

  el("export-btn").disabled = false;
}

function renderKeywordCoverage(review) {
  const matched = review.keyword_coverage.matched;
  const missing = review.keyword_coverage.missing;
  const total = matched.length + missing.length;
  el("keyword-count").textContent = `${matched.length} of ${total}`;

  const matchedBox = el("matched-chips");
  matchedBox.innerHTML = matched.map((kw) => `<span class="chip chip-matched">${escapeHtml(kw)}</span>`).join("");

  const missingBox = el("missing-chips");
  missingBox.innerHTML = "";
  el("gap-detail").classList.add("hidden");
  for (const kw of missing) {
    const suggestions = review.bullets_available_for_gaps[kw] || [];
    const chip = document.createElement("span");
    chip.className = "chip chip-missing" + (suggestions.length ? " has-suggestion" : "");
    chip.innerHTML = escapeHtml(kw) + (suggestions.length ? ' <span class="plus">+</span>' : "");
    if (suggestions.length) {
      chip.addEventListener("click", () => showGapDetail(kw, suggestions[0]));
    }
    missingBox.appendChild(chip);
  }
}

function setupAddKeywordForm() {
  el("toggle-add-keyword").addEventListener("click", () => {
    el("add-keyword-panel").classList.toggle("open");
  });
  el("cancel-add-keyword").addEventListener("click", resetAddKeywordForm);
  el("save-keyword").addEventListener("click", saveKeyword);
}

function resetAddKeywordForm() {
  el("add-keyword-panel").classList.remove("open");
  el("new-keyword-term").value = "";
  el("new-keyword-aliases").value = "";
}

async function saveKeyword() {
  const term = el("new-keyword-term").value.trim();
  const aliases = el("new-keyword-aliases").value
    .split(",")
    .map((a) => a.trim())
    .filter(Boolean);
  if (!term) {
    alert("Enter a keyword term first.");
    return;
  }
  const res = await fetch("/api/vocabulary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ term, aliases }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || "Could not add keyword.");
    return;
  }
  state.vocabulary = data.vocabulary;
  resetAddKeywordForm();
  if (state.lastJdText) await runAnalyze();
}

function showGapDetail(keyword, bulletId) {
  const bullet = state.bullets.find((b) => b.id === bulletId);
  if (!bullet) return;
  const box = el("gap-detail");
  box.classList.remove("hidden");
  box.innerHTML = `<strong>${escapeHtml(keyword)}</strong> &mdash; a library bullet already covers this: &ldquo;${escapeHtml(bullet.text)}&rdquo;`;
  const btn = document.createElement("div");
  btn.className = "btn btn-dark insert-btn";
  btn.style.display = "inline-block";
  btn.textContent = bullet.included ? "Already on resume" : "Insert into resume";
  if (!bullet.included) {
    btn.addEventListener("click", () => toggleBulletIncluded(bullet.id, true));
  }
  box.appendChild(btn);
}

function renderYears(review, data) {
  const y = review.years;
  el("years-value").innerHTML = y.required !== null
    ? `${y.have} <span class="of">/ ${y.required}</span>`
    : `${y.have} <span class="of">/ not listed</span>`;
  const verdict = el("years-verdict");
  if (y.required === null) {
    verdict.textContent = "no years requirement listed";
    verdict.style.color = "var(--muted-2)";
  } else if (y.meets_requirement) {
    verdict.textContent = "meets the requirement";
    verdict.style.color = "var(--sage)";
  } else {
    verdict.textContent = "short of the mark";
    verdict.style.color = "var(--terracotta)";
  }

  const statusEl = el("eligibility-status");
  statusEl.textContent = review.eligibility.status === "eligible" ? `${data.market}, all clear`
    : review.eligibility.status === "hard_blocked" ? `${data.market}, hard blocked`
    : `${data.market}, unconfirmed`;
  statusEl.className = "eligibility-status " + review.eligibility.status;
  el("eligibility-note").textContent = review.eligibility.note;
}

async function runAnalyze() {
  const jd_text = el("jd-text").value.trim();
  const posting_url = el("posting-url").value.trim();
  if (!jd_text) {
    alert("Paste a job description first.");
    return;
  }
  state.lastJdText = jd_text;
  state.lastPostingUrl = posting_url;

  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jd_text, posting_url,
      market_override: state.marketOverride,
      years_override: state.yearsOverride,
    }),
  });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "Could not analyze this posting.");
    return;
  }
  const data = await res.json();
  state.lastAnalysis = data;
  renderScore(data);
}

// --- export -------------------------------------------------------------

async function runExport() {
  if (!state.lastAnalysis) {
    alert("Analyze a posting first.");
    return;
  }
  const company = el("export-company").value.trim();
  const role_title = el("export-role").value.trim();
  if (!company || !role_title) {
    alert("Company and role title are required to export.");
    return;
  }
  const data = state.lastAnalysis;
  const resultEl = el("export-result");
  resultEl.textContent = "Exporting…";
  resultEl.className = "export-result";

  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      market: data.market,
      country_code: data.country_code,
      company, role_title,
      posting_url: state.lastPostingUrl,
      score: data.review.match_score,
      review_summary: data.review.review_summary,
      eligibility_short: data.eligibility.short,
    }),
  });
  const result = await res.json();
  if (!res.ok) {
    resultEl.textContent = result.error || "Export failed.";
    resultEl.className = "export-result error";
    return;
  }
  const verify = result.verification && result.verification.ok === false
    ? ` — warning: ${result.verification.note}` : "";
  const csvNote = result.logged_to_csv
    ? (result.csv_action === "updated"
        ? `Updated the existing row in ${result.csv_path} (same file, re-exported).`
        : `Logged to ${result.csv_path}.`)
    : "Score below 50 — not logged to the pipeline CSV.";
  resultEl.textContent = `Saved to ${result.resume_pdf} (overwritten if it already existed). ${csvNote}${verify}`;
  resultEl.className = "export-result";
}

// --- init -------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  setupAddBulletForm();
  setupAddKeywordForm();
  el("analyze-btn").addEventListener("click", runAnalyze);
  el("export-btn").addEventListener("click", runExport);
  loadState();
});
