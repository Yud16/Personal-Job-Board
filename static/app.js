let postings = [];
let selectedKey = null;

const STATUS_OPTIONS = ["Not applied yet", "Applied", "Interview", "Rejection", "Landed"];
let selectedStatuses = new Set(STATUS_OPTIONS);
let showDismissed = false;

const TRASH_ICON_SVG = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2.5 4h11M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M3.5 4l.6 9a1 1 0 0 0 1 .9h5.8a1 1 0 0 0 1-.9l.6-9"/>
  <path d="M6.5 7v4M9.5 7v4"/>
</svg>`;

const RESTORE_ICON_SVG = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2.5 8a5.5 5.5 0 1 0 1.8-4.1"/>
  <path d="M2.5 2.5v3.2h3.2"/>
</svg>`;

const cardsByTier = {
  strong: document.getElementById("cards-strong"),
  good: document.getElementById("cards-good"),
  below: document.getElementById("cards-below"),
};
const countByTier = {
  strong: document.getElementById("count-strong"),
  good: document.getElementById("count-good"),
  below: document.getElementById("count-below"),
};
const marketFilter = document.getElementById("marketFilter");
const variantFilter = document.getElementById("variantFilter");
const statusFilter = document.getElementById("statusFilter");
const refreshBtn = document.getElementById("refreshBtn");
const board = document.getElementById("board");
const emptyState = document.getElementById("emptyState");
const detailBackdrop = document.getElementById("detailBackdrop");
const detailPanel = document.getElementById("detailPanel");
const closeDetail = document.getElementById("closeDetail");
const detailStatusSelect = document.getElementById("detailStatus");

async function loadPostings() {
  const res = await fetch("/api/postings");
  postings = await res.json();
  populateVariantOptions();
  render();
}

function populateVariantOptions() {
  const current = variantFilter.value;
  const variants = [...new Set(postings.map((p) => p.resume_variant).filter(Boolean))].sort();
  variantFilter.innerHTML = '<option value="all">All variants</option>';
  for (const v of variants) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    variantFilter.appendChild(opt);
  }
  if (variants.includes(current)) variantFilter.value = current;
}

function buildStatusFilter() {
  statusFilter.innerHTML = "";
  for (const status of STATUS_OPTIONS) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedStatuses.has(status);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedStatuses.add(status);
      else selectedStatuses.delete(status);
      render();
    });
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(status));
    statusFilter.appendChild(label);
  }

  const dismissedLabel = document.createElement("label");
  dismissedLabel.className = "status-filter-dismissed";
  const dismissedCheckbox = document.createElement("input");
  dismissedCheckbox.type = "checkbox";
  dismissedCheckbox.checked = showDismissed;
  dismissedCheckbox.addEventListener("change", () => {
    showDismissed = dismissedCheckbox.checked;
    render();
  });
  dismissedLabel.appendChild(dismissedCheckbox);
  dismissedLabel.appendChild(document.createTextNode("Dismissed"));
  statusFilter.appendChild(dismissedLabel);
}

function filteredPostings() {
  const market = marketFilter.value;
  const variant = variantFilter.value;
  return postings.filter((p) => {
    if (market !== "all" && p.market !== market) return false;
    if (variant !== "all" && p.resume_variant !== variant) return false;
    if (p.dismissed) return showDismissed;
    return selectedStatuses.has(p.status);
  });
}

function render() {
  const filtered = filteredPostings();

  for (const tier of ["strong", "good", "below"]) {
    cardsByTier[tier].innerHTML = "";
  }

  const grouped = { strong: [], good: [], below: [] };
  for (const p of filtered) grouped[p.tier].push(p);
  for (const tier of ["strong", "good", "below"]) {
    grouped[tier].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  }

  for (const tier of ["strong", "good", "below"]) {
    countByTier[tier].textContent = grouped[tier].length;
    for (const p of grouped[tier]) {
      cardsByTier[tier].appendChild(renderCard(p));
    }
  }

  board.hidden = filtered.length === 0;
  emptyState.hidden = filtered.length !== 0;

  if (selectedKey && !filtered.some((p) => p.key === selectedKey)) {
    closePanel();
  }
}

function renderCard(p) {
  const card = document.createElement("div");
  card.className = "card" + (p.key === selectedKey ? " selected" : "") + (p.dismissed ? " card-dismissed" : "");
  card.dataset.key = p.key;

  const company = document.createElement("div");
  company.className = "card-company";
  company.textContent = p.company || "(unknown company)";

  const role = document.createElement("div");
  role.className = "card-role";
  role.textContent = p.role_title || "(unknown role)";

  const footer = document.createElement("div");
  footer.className = "card-footer";

  const variant = document.createElement("span");
  variant.className = "card-variant";
  variant.textContent = p.resume_variant || p.country_code || "—";

  const badge = document.createElement("span");
  badge.className = "badge " + badgeClass(p.tier);
  badge.textContent = p.score === null ? "—" : p.score;

  footer.appendChild(variant);
  footer.appendChild(badge);
  card.appendChild(company);
  card.appendChild(role);
  card.appendChild(footer);

  const statusSelect = document.createElement("select");
  statusSelect.className = "status-tag-select " + statusClass(p.status);
  for (const status of STATUS_OPTIONS) {
    const opt = document.createElement("option");
    opt.value = status;
    opt.textContent = status;
    statusSelect.appendChild(opt);
  }
  statusSelect.value = p.status;
  statusSelect.addEventListener("click", (e) => e.stopPropagation());
  statusSelect.addEventListener("change", () => setStatus(p, statusSelect.value, statusSelect));
  card.appendChild(statusSelect);

  const actionBtn = document.createElement("button");
  actionBtn.type = "button";
  if (p.dismissed) {
    actionBtn.className = "card-delete-btn card-restore-btn";
    actionBtn.title = "Restore to board";
    actionBtn.setAttribute("aria-label", "Restore to board");
    actionBtn.innerHTML = RESTORE_ICON_SVG;
    actionBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      restorePosting(p);
    });
  } else {
    actionBtn.className = "card-delete-btn";
    actionBtn.title = "Remove from board";
    actionBtn.setAttribute("aria-label", "Remove from board");
    actionBtn.innerHTML = TRASH_ICON_SVG;
    actionBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      dismissPosting(p);
    });
  }
  card.appendChild(actionBtn);

  card.addEventListener("click", () => selectPosting(p.key));
  return card;
}

async function dismissPosting(p) {
  try {
    const res = await fetch("/api/dismiss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: p.key }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Could not remove posting: " + (err.error || res.statusText));
      return;
    }
    p.dismissed = true;
    if (selectedKey === p.key) {
      closePanel();
    } else {
      render();
    }
  } catch (e) {
    alert("Could not remove posting: " + e.message);
  }
}

async function restorePosting(p) {
  try {
    const res = await fetch("/api/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: p.key }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Could not restore posting: " + (err.error || res.statusText));
      return;
    }
    p.dismissed = false;
    render();
  } catch (e) {
    alert("Could not restore posting: " + e.message);
  }
}

function badgeClass(tier) {
  if (tier === "strong") return "badge-strong";
  if (tier === "good") return "badge-good";
  return "badge-below";
}

function statusClass(status) {
  switch (status) {
    case "Applied":
      return "status-applied";
    case "Interview":
      return "status-interview";
    case "Rejection":
      return "status-rejection";
    case "Landed":
      return "status-landed";
    default:
      return "status-not-applied";
  }
}

function selectPosting(key) {
  selectedKey = key;
  render();
  const p = postings.find((x) => x.key === key);
  if (!p) return;

  document.getElementById("detailCompany").textContent = p.company || "(unknown company)";
  document.getElementById("detailRole").textContent = p.role_title || "(unknown role)";

  const scoreBadge = document.getElementById("detailScoreBadge");
  scoreBadge.className = "badge " + badgeClass(p.tier);
  scoreBadge.textContent = p.score === null ? "—" : p.score;

  const metaParts = [p.market, p.country_code || null, p.date_found ? `Found ${p.date_found}` : null, p.title_query || null, p.tailored ? "Tailored" : "Not tailored"].filter(Boolean);
  document.getElementById("detailMeta").textContent = metaParts.join(" · ");

  document.getElementById("detailSummaryLabel").hidden = !p.review_summary;
  document.getElementById("detailSummary").textContent = summaryFor(p);

  detailStatusSelect.innerHTML = "";
  for (const status of STATUS_OPTIONS) {
    const opt = document.createElement("option");
    opt.value = status;
    opt.textContent = status;
    detailStatusSelect.appendChild(opt);
  }
  detailStatusSelect.value = p.status;
  detailStatusSelect.onchange = () => setStatus(p, detailStatusSelect.value, detailStatusSelect);

  const appliedRow = document.getElementById("detailAppliedRow");
  if (p.applied_status_raw) {
    appliedRow.hidden = false;
    document.getElementById("detailApplied").textContent = p.applied_status_raw;
  } else {
    appliedRow.hidden = true;
  }

  const urlLink = document.getElementById("detailUrl");
  if (p.posting_url) {
    urlLink.href = p.posting_url;
    urlLink.style.display = "";
  } else {
    urlLink.style.display = "none";
  }

  detailBackdrop.hidden = false;
}

function summaryFor(p) {
  if (p.review_summary) return p.review_summary;
  if (p.notes) return p.notes;
  const scorePart = p.score === null ? "Not scored (manually tracked)" : `Scored ${p.score}/100`;
  const parts = [`${scorePart} as ${p.resume_variant || "an unspecified variant"}.`];
  parts.push(p.tailored ? "Resume and cover letter were tailored." : "Not tailored.");
  return parts.join(" ");
}

async function setStatus(p, newStatus, sourceSelect) {
  const targetSelect = sourceSelect || detailStatusSelect;
  const previous = p.status;
  targetSelect.disabled = true;
  try {
    const res = await fetch("/api/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: p.key, status: newStatus }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("Could not save status: " + (err.error || res.statusText));
      targetSelect.value = previous;
      return;
    }
    p.status = newStatus;
    if (!detailBackdrop.hidden && selectedKey === p.key) {
      detailStatusSelect.value = newStatus;
    }
    render();
  } catch (e) {
    alert("Could not save status: " + e.message);
    targetSelect.value = previous;
  } finally {
    targetSelect.disabled = false;
  }
}

function closePanel() {
  selectedKey = null;
  detailBackdrop.hidden = true;
  render();
}

closeDetail.addEventListener("click", closePanel);
detailBackdrop.addEventListener("click", (e) => {
  if (e.target === detailBackdrop) closePanel();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !detailBackdrop.hidden) closePanel();
});
marketFilter.addEventListener("change", render);
variantFilter.addEventListener("change", render);
refreshBtn.addEventListener("click", loadPostings);

buildStatusFilter();
loadPostings();
