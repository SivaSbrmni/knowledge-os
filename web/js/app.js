/**
 * Knowledge OS — Mentor UI
 */

const state = {
  sessionId: null,
  connected: false,
  loading: false,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function api(path) {
  const base = $("#apiBase").value.replace(/\/$/, "");
  return `${base}${path}`;
}

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const token = $("#token").value.trim();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

function toast(message, type = "info") {
  const container = $("#toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

function setConnected(connected, sessionId = null) {
  state.connected = connected;
  state.sessionId = sessionId;
  const dot = $("#sessionDot");
  const label = $("#sessionLabel");
  const askBtn = $("#askBtn");
  const question = $("#question");
  const welcome = $("#welcomeState");
  const messages = $("#messages");

  question.disabled = !connected;

  if (connected && sessionId) {
    dot.classList.add("live");
    label.textContent = `Session ${sessionId.slice(0, 8)}…`;
    askBtn.disabled = false;
    welcome.classList.add("hidden");
  } else {
    dot.classList.remove("live");
    label.textContent = "Not connected";
    askBtn.disabled = true;
    if (!messages.querySelector(".message-row")) {
      welcome.classList.remove("hidden");
    }
  }
}

function showTyping() {
  const row = document.createElement("div");
  row.className = "typing-indicator";
  row.id = "typingIndicator";
  row.innerHTML = `
    <div class="avatar assistant">K</div>
    <div class="typing-dots"><span></span><span></span><span></span></div>
  `;
  $("#messages").appendChild(row);
  scrollMessages();
}

function hideTyping() {
  const el = $("#typingIndicator");
  if (el) el.remove();
}

function scrollMessages() {
  const el = $("#messages");
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function addMessage(role, content, meta = {}) {
  $("#welcomeState").classList.add("hidden");

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role}`;
  avatar.textContent = role === "user" ? "You" : "K";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (meta.withheld) bubble.classList.add("withheld");
  bubble.innerHTML = content;

  if (meta.trust) {
    const block = document.createElement("div");
    block.className = "trust-block";
    const pct = Math.round(meta.trust.overall * 100);
    const low = !meta.trust.threshold_met;
    block.innerHTML = `
      <div class="trust-header">
        <span class="trust-label">Trust vector</span>
        <span class="trust-score">${pct}%</span>
      </div>
      <div class="trust-bar">
        <div class="trust-bar-fill ${low ? "low" : ""}" style="width: ${pct}%"></div>
      </div>
      <p class="trust-explanation">${escapeHtml(meta.trust.explanation || "")}</p>
    `;
    bubble.appendChild(block);
  }

  if (meta.citations?.length) {
    const citBlock = document.createElement("div");
    citBlock.className = "citations-block";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "citations-toggle";
    toggle.innerHTML = `▸ ${meta.citations.length} source${meta.citations.length > 1 ? "s" : ""}`;
    const list = document.createElement("div");
    list.className = "citation-list";

    meta.citations.forEach((c) => {
      const card = document.createElement("div");
      card.className = "citation-card";
      card.innerHTML = `
        <header>
          <span>chunk ${c.chunk_id.slice(0, 8)}… · p.${c.page ?? "?"}</span>
          <span class="confidence-tag">${Math.round(c.confidence * 100)}%</span>
        </header>
        <p class="citation-excerpt">${escapeHtml(c.text_excerpt)}</p>
      `;
      list.appendChild(card);
    });

    toggle.onclick = () => {
      const open = list.classList.toggle("open");
      toggle.innerHTML = `${open ? "▾" : "▸"} ${meta.citations.length} source${meta.citations.length > 1 ? "s" : ""}`;
    };

    citBlock.appendChild(toggle);
    citBlock.appendChild(list);
    bubble.appendChild(citBlock);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  $("#messages").appendChild(row);
  scrollMessages();
}

async function loadAssets() {
  const ws = $("#workspaceId").value.trim();
  if (!ws) return;
  const list = $("#docList");
  list.innerHTML = `<div class="empty-docs">Loading documents…</div>`;

  try {
    const res = await fetch(api(`/workspaces/${ws}/knowledge/assets`), { headers: headers(false) });
    if (!res.ok) throw new Error(await res.text());
    const assets = await res.json();

    if (!assets.length) {
      list.innerHTML = `<div class="empty-docs">No documents yet. Upload PDF or text to build your knowledge base.</div>`;
      return;
    }

    list.innerHTML = assets
      .map(
        (a) => `
      <div class="doc-card">
        <div class="doc-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div class="doc-info">
          <div class="doc-name">${escapeHtml(a.filename)}</div>
          <div class="doc-meta">
            <span class="status-pill status-${a.status}">${a.status}</span>
          </div>
        </div>
      </div>`
      )
      .join("");
  } catch (err) {
    list.innerHTML = `<div class="empty-docs">Could not load documents.</div>`;
    toast(err.message, "error");
  }
}

async function connect() {
  const ws = $("#workspaceId").value.trim();
  const agent = $("#agentId").value.trim();
  if (!ws || !agent) {
    toast("Workspace ID and Agent ID are required.", "error");
    return;
  }

  const btn = $("#connectBtn");
  btn.disabled = true;
  btn.textContent = "Connecting…";

  try {
    const res = await fetch(api(`/workspaces/${ws}/sessions`), {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ agent_id: agent }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setConnected(true, data.session_id);
    localStorage.setItem("kos_workspace", ws);
    localStorage.setItem("kos_agent", agent);
    toast("Connected to your mentor session.", "success");
    await loadAssets();
  } catch (err) {
    toast(`Connection failed: ${err.message}`, "error");
    setConnected(false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Connect";
  }
}

async function uploadFile(file) {
  const ws = $("#workspaceId").value.trim();
  if (!file) return;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("agent_id", $("#agentId").value.trim());

  $("#uploadBtn").disabled = true;
  try {
    const res = await fetch(api(`/workspaces/${ws}/knowledge/upload`), {
      method: "POST",
      headers: headers(false),
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    await loadAssets();
    addMessage("assistant", `Indexed <strong>${escapeHtml(file.name)}</strong> into your knowledge base.`);
    toast(`${file.name} uploaded successfully.`, "success");
  } catch (err) {
    toast(`Upload failed: ${err.message}`, "error");
  } finally {
    $("#uploadBtn").disabled = false;
    $("#fileInput").value = "";
  }
}

async function ask(question) {
  const q = question?.trim() || $("#question").value.trim();
  if (!q || !state.sessionId) return;

  const ws = $("#workspaceId").value.trim();
  addMessage("user", escapeHtml(q));
  $("#question").value = "";
  autoResizeTextarea();

  const askBtn = $("#askBtn");
  askBtn.disabled = true;
  showTyping();

  try {
    const res = await fetch(api(`/workspaces/${ws}/sessions/${state.sessionId}/query`), {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ question: q }),
    });
    hideTyping();
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    addMessage("assistant", escapeHtml(data.answer).replace(/\n/g, "<br>"), {
      trust: data.trust,
      citations: data.citations,
      withheld: data.withheld,
    });
  } catch (err) {
    hideTyping();
    addMessage("assistant", `Something went wrong. ${escapeHtml(err.message)}`);
    toast("Query failed.", "error");
  } finally {
    askBtn.disabled = false;
  }
}

function autoResizeTextarea() {
  const ta = $("#question");
  ta.style.height = "auto";
  ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
}

function initUploadZone() {
  const zone = $("#uploadZone");
  const input = $("#fileInput");

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
  input.addEventListener("change", () => {
    if (input.files[0]) uploadFile(input.files[0]);
  });
}

function initAccordion() {
  $("#advancedToggle").addEventListener("click", () => {
    const body = $("#advancedBody");
    const open = body.classList.toggle("open");
    $("#advancedToggle").setAttribute("aria-expanded", open);
  });
}

function initSuggestions() {
  $$(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      if (!state.connected) {
        toast("Connect your session first.", "error");
        return;
      }
      ask(chip.dataset.q);
    });
  });
}

function initComposer() {
  const ta = $("#question");
  ta.addEventListener("input", autoResizeTextarea);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  });
  $("#askBtn").addEventListener("click", () => ask());
}

function initMobileNav() {
  $("#mobileToggle").addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
  });
}

function restoreSettings() {
  const ws = localStorage.getItem("kos_workspace");
  const agent = localStorage.getItem("kos_agent");
  const token = localStorage.getItem("kos_token");
  if (ws) $("#workspaceId").value = ws;
  if (agent) $("#agentId").value = agent;
  if (token) $("#token").value = token;
}

function persistToken() {
  $("#token").addEventListener("change", () => {
    localStorage.setItem("kos_token", $("#token").value.trim());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  restoreSettings();
  persistToken();
  initUploadZone();
  initAccordion();
  initSuggestions();
  initComposer();
  initMobileNav();

  $("#connectBtn").addEventListener("click", connect);
  $("#uploadBtn").addEventListener("click", () => {
    const file = $("#fileInput").files[0];
    if (file) uploadFile(file);
    else toast("Choose a file to upload.", "error");
  });
});
