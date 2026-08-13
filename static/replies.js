const listEl = document.getElementById("replyList");
const emptyStateEl = document.getElementById("emptyState");
const refreshBtn = document.getElementById("refreshBtn");

function typeClass(typeGuess) {
  const key = (typeGuess || "").toLowerCase().replace(/[^a-z]+/g, "-");
  return `reply-type reply-type-${key || "other"}`;
}

function renderReplies(replies) {
  listEl.innerHTML = "";

  if (!replies.length) {
    emptyStateEl.hidden = false;
    return;
  }
  emptyStateEl.hidden = true;

  for (const r of replies) {
    const card = document.createElement("div");
    card.className = "reply-card";

    const header = document.createElement("div");
    header.className = "reply-card-header";

    const company = document.createElement("span");
    company.className = "reply-company";
    company.textContent = r.company_guess || r.sender || "Unknown sender";
    header.appendChild(company);

    if (r.type_guess) {
      const tag = document.createElement("span");
      tag.className = typeClass(r.type_guess);
      tag.textContent = r.type_guess;
      header.appendChild(tag);
    }

    card.appendChild(header);

    if (r.role_guess) {
      const role = document.createElement("div");
      role.className = "reply-role";
      role.textContent = r.role_guess;
      card.appendChild(role);
    }

    const subject = document.createElement("div");
    subject.className = "reply-subject";
    subject.textContent = r.subject || "";
    card.appendChild(subject);

    if (r.snippet) {
      const snippet = document.createElement("div");
      snippet.className = "reply-snippet";
      snippet.textContent = r.snippet;
      card.appendChild(snippet);
    }

    const meta = document.createElement("div");
    meta.className = "reply-meta";
    meta.textContent = `${r.date || ""} · ${r.sender || ""}`;
    card.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "reply-actions";

    const openLink = document.createElement("a");
    openLink.href = r.gmail_url || "#";
    openLink.target = "_blank";
    openLink.rel = "noopener";
    openLink.textContent = "Open in Gmail";
    actions.appendChild(openLink);

    const dismissBtn = document.createElement("button");
    dismissBtn.textContent = "Dismiss";
    dismissBtn.addEventListener("click", () => dismissReply(r.thread_id, card));
    actions.appendChild(dismissBtn);

    card.appendChild(actions);
    listEl.appendChild(card);
  }
}

async function loadReplies() {
  const res = await fetch("/api/possible-replies");
  const replies = await res.json();
  renderReplies(replies);
}

async function dismissReply(threadId, cardEl) {
  if (!threadId) return;
  const res = await fetch("/api/dismiss-reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId }),
  });
  if (res.ok) {
    cardEl.remove();
    if (!listEl.children.length) {
      emptyStateEl.hidden = false;
    }
  }
}

refreshBtn.addEventListener("click", loadReplies);

loadReplies();
