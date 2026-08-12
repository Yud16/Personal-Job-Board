let postings = [];
let selectedKey = null;

const STATUS_OPTIONS = ["Not applied yet", "Applied", "Interview", "Rejection", "Landed"];
let selectedStatuses = new Set(STATUS_OPTIONS);

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
}

function filteredPostings() {
  const market = marketFilter.value;
  const variant = variantFilter.value;
  return postings.filter((p) => {
    if (market !== "all" && p.market !== market) return false;
    if (variant !== "all" && p.resume_variant !== variant) return false;
    if (!selectedStatuses.has(p.status)) return false;
    return true;
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
    grouped[tier].sort((a, b) => b.score - a.score);
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
  card.className = "card" + (p.key === selectedKey ? " selected" : "");
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
  variant.textContent = p.resume_variant || "—";

  const badge = document.createElement("span");
  badge.className = "badge " + badgeClass(p.tier);
  badge.textContent = p.score;

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

  card.addEventListener("click", () => selectPosting(p.key));
  return card;
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
  scoreBadge.textContent = p.score;

  const metaParts = [p.market, p.date_found ? `Found ${p.date_found}` : null, p.title_query || null, p.tailored ? "Tailored" : "Not tailored"].filter(Boolean);
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
  const parts = [`Scored ${p.score}/100 as ${p.resume_variant || "an unspecified variant"}.`];
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
