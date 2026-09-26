(() => {
  "use strict";

  const DEFAULTS = {
    apiBase: "",
    maxFiles: 3,
    historyLimit: 50,
    mode: "auto",
    semantic: true
  };

  const state = {
    settings: loadSettings(),
    workspaces: [],
    workspace: null,
    indexState: null,
    patches: [],
    currentPatch: null,
    patchFilter: "all",
    requestCount: 0,
    patchCount: 0,
    patchMode: false,
    busy: false
  };

  const $ = (id) => document.getElementById(id);
  const qsa = (selector) => Array.from(document.querySelectorAll(selector));

  const els = {
    workspaceButton: $("workspaceButton"),
    workspaceName: $("workspaceName"),
    workspaceMeta: $("workspaceMeta"),
    workspaceAvatar: $("workspaceAvatar"),
    workspaceMenu: $("workspaceMenu"),
    modelStatus: $("modelStatus"),
    structuralMini: $("structuralMini"),
    semanticMini: $("semanticMini"),
    connectionPill: $("connectionPill"),
    viewEyebrow: $("viewEyebrow"),
    viewTitle: $("viewTitle"),
    emptyChat: $("emptyChat"),
    messages: $("messages"),
    promptInput: $("promptInput"),
    modeSelect: $("modeSelect"),
    semanticToggle: $("semanticToggle"),
    patchModeButton: $("patchModeButton"),
    sendButton: $("sendButton"),
    structuralStatus: $("structuralStatus"),
    semanticStatus: $("semanticStatus"),
    structuralDot: $("structuralDot"),
    semanticDot: $("semanticDot"),
    dirtyNotice: $("dirtyNotice"),
    dirtyFiles: $("dirtyFiles"),
    recentPatches: $("recentPatches"),
    readyBadge: $("readyBadge"),
    patchList: $("patchList"),
    reconcileAll: $("reconcileAll"),
    repoCardName: $("repoCardName"),
    repoDirtyBadge: $("repoDirtyBadge"),
    repoHead: $("repoHead"),
    repoHash: $("repoHash"),
    repoChangedCount: $("repoChangedCount"),
    repoStructuralBadge: $("repoStructuralBadge"),
    repoSemanticBadge: $("repoSemanticBadge"),
    structuralIndexedAt: $("structuralIndexedAt"),
    semanticIndexedAt: $("semanticIndexedAt"),
    changedFilesList: $("changedFilesList"),
    rebuildStructural: $("rebuildStructural"),
    rebuildSemantic: $("rebuildSemantic"),
    patchDrawer: $("patchDrawer"),
    patchDrawerBackdrop: $("patchDrawerBackdrop"),
    closeDrawer: $("closeDrawer"),
    drawerStatus: $("drawerStatus"),
    drawerTitle: $("drawerTitle"),
    drawerMeta: $("drawerMeta"),
    drawerSummary: $("drawerSummary"),
    drawerValidation: $("drawerValidation"),
    drawerDiff: $("drawerDiff"),
    drawerActions: $("drawerActions"),
    approvePatch: $("approvePatch"),
    rejectPatch: $("rejectPatch"),
    reconcilePatch: $("reconcilePatch"),
    settingsButton: $("settingsButton"),
    settingsModal: $("settingsModal"),
    closeSettings: $("closeSettings"),
    apiBaseInput: $("apiBaseInput"),
    maxFilesInput: $("maxFilesInput"),
    historyLimitInput: $("historyLimitInput"),
    saveSettings: $("saveSettings"),
    resetSettings: $("resetSettings"),
    refreshAll: $("refreshAll"),
    refreshIndexState: $("refreshIndexState"),
    sessionRequests: $("sessionRequests"),
    sessionPatches: $("sessionPatches"),
    toastRegion: $("toastRegion"),
    addWorkspaceButton: $("addWorkspaceButton"),
    addWorkspaceModal: $("addWorkspaceModal"),
    closeAddWorkspace: $("closeAddWorkspace"),
    cancelAddWorkspace: $("cancelAddWorkspace"),
    addWorkspaceForm: $("addWorkspaceForm"),
    newWorkspaceName: $("newWorkspaceName"),
    newWorkspacePath: $("newWorkspacePath"),
    newWorkspaceAutoScan: $("newWorkspaceAutoScan"),
    addWorkspaceError: $("addWorkspaceError"),
    submitAddWorkspace: $("submitAddWorkspace"),
    submitAddWorkspaceText: $("submitAddWorkspaceText")
  };

  function loadSettings() {
    try {
      return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem("outrightbot.settings") || "{}")) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function persistSettings() {
    localStorage.setItem("outrightbot.settings", JSON.stringify(state.settings));
  }

  function apiUrl(path) {
    const base = (state.settings.apiBase || "").replace(/\/+$/, "");
    if (!base) return path;
    return `${base}${path}`;
  }

  async function api(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      ...options
    });

    let payload = null;
    const text = await response.text();
    if (text) {
      try { payload = JSON.parse(text); }
      catch { payload = { detail: text }; }
    }

    if (!response.ok) {
      const detail = payload?.detail || payload?.message || `${response.status} ${response.statusText}`;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }

    return payload;
  }

  async function apiTry(paths, options = {}) {
    let lastError;
    for (const path of paths) {
      try { return await api(path, options); }
      catch (error) {
        lastError = error;
        if (![404, 405].includes(error.status)) throw error;
      }
    }
    throw lastError || new Error("API endpoint unavailable.");
  }

  function escapeHtml(value = "") {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function markdownLite(text = "") {
    let safe = escapeHtml(text);
    safe = safe.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    const blocks = safe.split(/\n{2,}/).map(block => `<p>${block.replace(/\n/g, "<br>")}</p>`);
    return blocks.join("");
  }

  function initials(name = "OutrightBot") {
    const parts = name.split(/\s+/).filter(Boolean);
    return (parts.slice(0, 2).map(x => x[0]).join("") || "OR").toUpperCase();
  }

  function shortHash(value) {
    if (!value) return "—";
    return value.length > 13 ? `${value.slice(0, 12)}…` : value;
  }

  function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
  }

  function statusClass(status = "") {
    return String(status).toLowerCase().replaceAll(" ", "_");
  }

  function toast(title, text = "", type = "neutral") {
    const item = document.createElement("div");
    item.className = `toast ${type}`;
    item.innerHTML = `
      <span class="toast-dot"></span>
      <div><div class="toast-title">${escapeHtml(title)}</div>${text ? `<div class="toast-text">${escapeHtml(text)}</div>` : ""}</div>
    `;
    els.toastRegion.appendChild(item);
    setTimeout(() => item.remove(), 4300);
  }

  function setConnection(ok) {
    els.connectionPill.classList.toggle("good", ok);
    els.connectionPill.classList.toggle("bad", !ok);
    els.connectionPill.querySelector("span:last-child").textContent = ok ? "API online" : "API offline";
  }

  async function loadHealth() {
    try {
      const health = await apiTry(["/api/llm/health", "/health"]);
      setConnection(true);
      const raw = health || {};
      const model = raw.model || raw.model_name || raw.llm_model || "Qwen";
      const online = raw.ok !== false && raw.healthy !== false && raw.status !== "error";
      els.modelStatus.className = `status-pill ${online ? "good" : "bad"}`;
      els.modelStatus.innerHTML = `<span class="status-dot"></span>${escapeHtml(model)}`;
    } catch (error) {
      setConnection(false);
      els.modelStatus.className = "status-pill bad";
      els.modelStatus.innerHTML = `<span class="status-dot"></span>Offline`;
    }
  }

  function normalizeWorkspaces(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.workspaces)) return payload.workspaces;
    if (Array.isArray(payload?.items)) return payload.items;
    if (payload?.workspace_id || payload?.id) return [payload];
    return [];
  }

  function workspaceId(ws) {
    return ws?.workspace_id || ws?.id || ws?.slug || "";
  }

  function workspaceName(ws) {
    return ws?.name || ws?.workspace_name || ws?.title || workspaceId(ws) || "Workspace";
  }

  function workspacePath(ws) {
    return ws?.path || ws?.root_path || ws?.repository_path || "";
  }

  async function loadWorkspaces() {
    try {
      const payload = await apiTry(["/api/workspaces", "/api/workspaces/"]);
      const items = normalizeWorkspaces(payload);
      state.workspaces = items;

      const remembered = localStorage.getItem("outrightbot.workspace");
      const next = items.find(x => workspaceId(x) === remembered) || items[0];

      if (!next) {
        els.workspaceName.textContent = "No workspace";
        els.workspaceMeta.textContent = "Add a repository to begin";
        renderWorkspaceMenu();
        return;
      }

      await selectWorkspace(next, { refresh: false });
      renderWorkspaceMenu();
      await refreshWorkspaceData();
    } catch (error) {
      setConnection(false);
      els.workspaceName.textContent = "Workspace unavailable";
      els.workspaceMeta.textContent = error.message;
      toast("Could not load workspaces", error.message, "error");
    }
  }

  function renderWorkspaceMenu() {
    const listHtml = state.workspaces.map(ws => `
      <button class="workspace-option" data-workspace-id="${escapeHtml(workspaceId(ws))}">
        <strong>${escapeHtml(workspaceName(ws))}</strong>
        <span>${escapeHtml(workspacePath(ws) || workspaceId(ws))}</span>
      </button>
    `).join("");

    const addActionHtml = `
      ${state.workspaces.length ? '<div class="workspace-menu-divider"></div>' : ''}
      <button id="menuAddWorkspaceBtn" class="workspace-option add-workspace-option" type="button">
        <svg viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <span><strong>Add new workspace…</strong></span>
      </button>
    `;

    els.workspaceMenu.innerHTML = listHtml + addActionHtml;

    qsa(".workspace-option[data-workspace-id]").forEach(button => {
      button.addEventListener("click", async () => {
        const ws = state.workspaces.find(x => workspaceId(x) === button.dataset.workspaceId);
        if (!ws) return;
        els.workspaceMenu.classList.add("hidden");
        await selectWorkspace(ws);
      });
    });

    const menuAddBtn = $("menuAddWorkspaceBtn");
    if (menuAddBtn) {
      menuAddBtn.addEventListener("click", () => {
        els.workspaceMenu.classList.add("hidden");
        openAddWorkspaceModal();
      });
    }
  }

  function openAddWorkspaceModal() {
    if (els.newWorkspaceName) els.newWorkspaceName.value = "";
    if (els.newWorkspacePath) els.newWorkspacePath.value = "";
    hideAddWorkspaceError();
    if (els.submitAddWorkspace) els.submitAddWorkspace.disabled = false;
    if (els.submitAddWorkspaceText) els.submitAddWorkspaceText.textContent = "Add & Switch Workspace";
    if (els.addWorkspaceModal) els.addWorkspaceModal.classList.remove("hidden");
    setTimeout(() => {
      if (els.newWorkspaceName) els.newWorkspaceName.focus();
    }, 50);
  }

  function closeAddWorkspaceModal() {
    if (els.addWorkspaceModal) els.addWorkspaceModal.classList.add("hidden");
    hideAddWorkspaceError();
  }

  function showAddWorkspaceError(message) {
    if (!els.addWorkspaceError) return;
    els.addWorkspaceError.textContent = message;
    els.addWorkspaceError.classList.remove("hidden");
  }

  function hideAddWorkspaceError() {
    if (!els.addWorkspaceError) return;
    els.addWorkspaceError.textContent = "";
    els.addWorkspaceError.classList.add("hidden");
  }

  async function handleAddWorkspace(event) {
    if (event) event.preventDefault();
    const name = (els.newWorkspaceName?.value || "").trim();
    const path = (els.newWorkspacePath?.value || "").trim();
    const autoScan = els.newWorkspaceAutoScan ? els.newWorkspaceAutoScan.checked : true;

    if (!name || !path) {
      showAddWorkspaceError("Please enter both a workspace name and codebase path.");
      return;
    }

    try {
      if (els.submitAddWorkspace) els.submitAddWorkspace.disabled = true;
      if (els.submitAddWorkspaceText) els.submitAddWorkspaceText.textContent = "Registering repository…";
      hideAddWorkspaceError();

      const created = await apiTry(["/api/workspaces", "/api/workspaces/"], {
        method: "POST",
        body: JSON.stringify({ name, path })
      });

      const newId = workspaceId(created);

      if (autoScan && newId) {
        if (els.submitAddWorkspaceText) els.submitAddWorkspaceText.textContent = "Scanning codebase…";
        try {
          await api(`/api/workspaces/${encodeURIComponent(newId)}/scan`, { method: "POST" });
        } catch (scanErr) {
          console.warn("Auto-scan error on new workspace:", scanErr);
        }
      }

      const payload = await apiTry(["/api/workspaces", "/api/workspaces/"]);
      state.workspaces = normalizeWorkspaces(payload);
      renderWorkspaceMenu();

      const target = state.workspaces.find(x => workspaceId(x) === newId) || created;
      await selectWorkspace(target);

      closeAddWorkspaceModal();
      toast("Workspace added", `Switched to ${workspaceName(target)}`, "success");
    } catch (error) {
      showAddWorkspaceError(error.message || "Failed to add workspace.");
      toast("Could not add workspace", error.message, "error");
    } finally {
      if (els.submitAddWorkspace) els.submitAddWorkspace.disabled = false;
      if (els.submitAddWorkspaceText) els.submitAddWorkspaceText.textContent = "Add & Switch Workspace";
    }
  }

  async function selectWorkspace(ws, { refresh = true } = {}) {
    state.workspace = ws;
    localStorage.setItem("outrightbot.workspace", workspaceId(ws));
    els.workspaceName.textContent = workspaceName(ws);
    els.workspaceMeta.textContent = workspacePath(ws) || workspaceId(ws);
    els.workspaceAvatar.textContent = initials(workspaceName(ws));
    els.repoCardName.textContent = workspaceName(ws);
    if (refresh) await refreshWorkspaceData();
  }

  async function refreshWorkspaceData() {
    if (!state.workspace) return;
    await Promise.allSettled([loadIndexState(), loadPatches(), loadHealth()]);
  }

  async function loadIndexState() {
    if (!state.workspace) return;
    try {
      const id = encodeURIComponent(workspaceId(state.workspace));
      const data = await api(`/api/workspaces/${id}/index-state`);
      state.indexState = data;
      renderIndexState();
    } catch (error) {
      state.indexState = null;
      els.structuralStatus.textContent = "Unavailable";
      els.semanticStatus.textContent = "Unavailable";
      els.structuralMini.textContent = "—";
      els.semanticMini.textContent = "—";
    }
  }

  function renderIndexState() {
    const data = state.indexState || {};
    const current = data.current || {};
    const structural = data.structural || {};
    const semantic = data.semantic || {};

    const setFresh = (fresh, statusEl, dotEl, miniEl) => {
      statusEl.textContent = fresh ? "Fresh" : "Needs refresh";
      dotEl.className = `quality-dot ${fresh ? "good" : "bad"}`;
      miniEl.textContent = fresh ? "Fresh" : "Stale";
      miniEl.className = `tiny-state ${fresh ? "good" : "bad"}`;
    };

    setFresh(Boolean(structural.fresh), els.structuralStatus, els.structuralDot, els.structuralMini);
    setFresh(Boolean(semantic.fresh), els.semanticStatus, els.semanticDot, els.semanticMini);

    const dirty = Boolean(current.dirty);
    els.dirtyNotice.classList.toggle("hidden", !dirty);
    els.dirtyFiles.textContent = (current.changed_files || []).join(", ");

    els.repoDirtyBadge.textContent = dirty ? "Dirty" : "Clean";
    els.repoDirtyBadge.className = `soft-badge ${dirty ? "warn" : "good"}`;
    els.repoHead.textContent = shortHash(current.head_commit);
    els.repoHash.textContent = shortHash(current.state_hash);
    els.repoChangedCount.textContent = String((current.changed_files || []).length);

    els.repoStructuralBadge.textContent = structural.fresh ? "Fresh" : "Stale";
    els.repoStructuralBadge.className = `soft-badge ${structural.fresh ? "good" : "warn"}`;
    els.repoSemanticBadge.textContent = semantic.fresh ? "Fresh" : "Stale";
    els.repoSemanticBadge.className = `soft-badge ${semantic.fresh ? "good" : "warn"}`;

    els.structuralIndexedAt.textContent = structural.indexed_at ? `Updated ${formatTime(structural.indexed_at)}` : "Not indexed";
    els.semanticIndexedAt.textContent = semantic.indexed_at ? `Updated ${formatTime(semantic.indexed_at)}` : "Not indexed";

    const changed = current.changed_files || [];
    els.changedFilesList.innerHTML = changed.length
      ? changed.map(file => `<div class="changed-file">${escapeHtml(file)}</div>`).join("")
      : `<div class="empty-list">No changed files. Working tree is clean.</div>`;
  }

  function normalizePatches(payload) {
    const items = Array.isArray(payload) ? payload : (payload?.patches || payload?.items || []);
    return Array.isArray(items) ? items : [];
  }

  async function loadPatches() {
    if (!state.workspace) return;
    try {
      const id = encodeURIComponent(workspaceId(state.workspace));
      const payload = await api(`/api/workspaces/${id}/patches?limit=${Number(state.settings.historyLimit) || 50}`);
      state.patches = normalizePatches(payload);
      renderPatchViews();
    } catch (error) {
      els.patchList.innerHTML = `<div class="table-empty">Patch history unavailable: ${escapeHtml(error.message)}</div>`;
      els.recentPatches.innerHTML = `<div class="table-empty">Unavailable</div>`;
    }
  }

  function renderPatchViews() {
    const patches = state.patches;
    const ready = patches.filter(p => p.status === "ready").length;
    els.readyBadge.textContent = String(ready);
    els.readyBadge.classList.toggle("hidden", ready === 0);

    const recent = patches.slice(0, 4);
    els.recentPatches.innerHTML = recent.length ? recent.map(patch => `
      <div class="recent-patch" data-patch-id="${escapeHtml(patch.patch_id)}">
        <div class="recent-patch-top">
          <div class="recent-patch-title">${escapeHtml(patch.summary || patch.task || patch.patch_id)}</div>
          <span class="status-badge ${statusClass(patch.status)}">${escapeHtml(patch.status)}</span>
        </div>
        <div class="recent-patch-meta">${escapeHtml((patch.files_changed || []).length)} file(s) · ${escapeHtml(formatTime(patch.created_at))}</div>
      </div>
    `).join("") : `<div class="table-empty">No patches yet.</div>`;

    qsa(".recent-patch").forEach(item => item.addEventListener("click", () => openPatch(item.dataset.patchId)));
    renderPatchTable();
  }

  function renderPatchTable() {
    const filtered = state.patchFilter === "all"
      ? state.patches
      : state.patches.filter(p => {
          if (state.patchFilter === "failed") return ["failed", "validation_failed"].includes(p.status);
          return p.status === state.patchFilter;
        });

    if (!filtered.length) {
      els.patchList.innerHTML = `<div class="table-empty">No ${escapeHtml(state.patchFilter === "all" ? "" : state.patchFilter)} patches found.</div>`;
      return;
    }

    els.patchList.innerHTML = filtered.map(patch => `
      <div class="patch-row" data-patch-id="${escapeHtml(patch.patch_id)}">
        <div class="patch-task">
          <div class="patch-task-title">${escapeHtml(patch.summary || patch.task || patch.patch_id)}</div>
          <div class="patch-task-meta">${escapeHtml(patch.patch_id)}</div>
        </div>
        <div><span class="status-badge ${statusClass(patch.status)}">${escapeHtml(patch.status)}</span></div>
        <div class="patch-cell">${escapeHtml(String((patch.files_changed || []).length))} file(s)</div>
        <div class="patch-cell">${escapeHtml(formatTime(patch.created_at))}</div>
        <svg class="patch-chevron" viewBox="0 0 20 20" fill="none"><path d="m8 6 4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
    `).join("");

    qsa(".patch-row").forEach(row => row.addEventListener("click", () => openPatch(row.dataset.patchId)));
  }

  function normalizePatchDetail(payload, existing = {}) {
    return {
      ...existing,
      ...(payload || {}),
      patch_id: payload?.patch_id || existing.patch_id,
      files_changed: payload?.files_changed || existing.files_changed || [],
      validation: payload?.validation || payload?.validation_results || existing.validation || [],
      diff: payload?.diff || payload?.diff_text || existing.diff || "",
      summary: payload?.summary || existing.summary || "",
      status: payload?.status || existing.status || "unknown"
    };
  }

  async function openPatch(patchId) {
    let patch = state.patches.find(p => p.patch_id === patchId) || { patch_id: patchId };
    try {
      const detail = await api(`/api/patches/${encodeURIComponent(patchId)}`);
      patch = normalizePatchDetail(detail, patch);
    } catch {
      patch = normalizePatchDetail(null, patch);
    }

    state.currentPatch = patch;
    renderPatchDrawer();
    els.patchDrawerBackdrop.classList.remove("hidden");
    requestAnimationFrame(() => els.patchDrawer.classList.add("open"));
  }

  function closePatchDrawer() {
    els.patchDrawer.classList.remove("open");
    setTimeout(() => els.patchDrawerBackdrop.classList.add("hidden"), 220);
  }

  function renderPatchDrawer() {
    const patch = state.currentPatch;
    if (!patch) return;

    els.drawerStatus.textContent = patch.status || "patch";
    els.drawerStatus.className = `status-badge ${statusClass(patch.status)}`;
    els.drawerTitle.textContent = patch.task || patch.summary || "Patch details";
    els.drawerMeta.textContent = `${patch.patch_id || ""} · ${(patch.files_changed || []).length} file(s)`;
    els.drawerSummary.textContent = patch.summary || "No summary available.";

    const validation = patch.validation || [];
    els.drawerValidation.innerHTML = validation.length ? validation.map(check => `
      <div class="validation-item">
        <div class="validation-icon ${check.passed === false ? "fail" : ""}">${check.passed === false ? "!" : "?"}</div>
        <div>
          <div class="validation-name">${escapeHtml(check.name || "Validation")}</div>
          <div class="validation-output">${escapeHtml(check.output || (check.passed === false ? "Failed" : "Passed"))}</div>
        </div>
      </div>
    `).join("") : `<div class="empty-list">No validation results stored.</div>`;

    els.drawerDiff.innerHTML = renderDiff(patch.diff || "");

    const ready = patch.status === "ready";
    els.approvePatch.classList.toggle("hidden", !ready);
    els.reconcilePatch.classList.toggle("hidden", ["applied", "rejected"].includes(patch.status));
    els.rejectPatch.classList.toggle("hidden", !["ready", "stale", "failed", "validation_failed"].includes(patch.status));
  }

  function renderDiff(diff) {
    if (!diff) return `<div class="table-empty">Diff unavailable.</div>`;
    return diff.split("\n").map(line => {
      let cls = "";
      if (line.startsWith("+++ ") || line.startsWith("--- ") || line.startsWith("diff --git")) cls = "file";
      else if (line.startsWith("@@")) cls = "hunk";
      else if (line.startsWith("+")) cls = "add";
      else if (line.startsWith("-")) cls = "del";
      return `<div class="diff-line ${cls}">${escapeHtml(line || " ")}</div>`;
    }).join("");
  }

  async function patchAction(action) {
    const patch = state.currentPatch;
    if (!patch?.patch_id) return;
    const buttonMap = { approve: els.approvePatch, reject: els.rejectPatch, reconcile: els.reconcilePatch };
    const button = buttonMap[action];
    const original = button?.textContent;

    try {
      if (button) { button.disabled = true; button.textContent = "Working…"; }
      const result = await api(`/api/patches/${encodeURIComponent(patch.patch_id)}/${action}`, { method: "POST" });
      toast(`Patch ${action}${action.endsWith("e") ? "d" : "ed"}`, result?.message || patch.patch_id, "success");
      closePatchDrawer();
      await Promise.allSettled([loadPatches(), loadIndexState()]);
    } catch (error) {
      toast(`Could not ${action} patch`, error.message, "error");
    } finally {
      if (button) { button.disabled = false; button.textContent = original; }
    }
  }

  function addMessage(role, content, extraHtml = "") {
    els.emptyChat.classList.add("hidden");
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;
    wrapper.innerHTML = `
      <div class="message-label">${role === "user" ? "You" : "OutrightBot"}</div>
      <div class="message-bubble">${role === "assistant" ? markdownLite(content) : escapeHtml(content)}${extraHtml}</div>
    `;
    els.messages.appendChild(wrapper);
    wrapper.scrollIntoView({ behavior: "smooth", block: "end" });
    return wrapper;
  }

  function addLoadingMessage(label = "Investigating repository") {
    els.emptyChat.classList.add("hidden");
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";
    wrapper.innerHTML = `
      <div class="message-label">OutrightBot</div>
      <div class="message-bubble">
        <div class="activity-card">
          <div class="activity-title">${escapeHtml(label)}</div>
          <div class="activity-meta"><span class="loading-dots"><i></i><i></i><i></i></span></div>
        </div>
      </div>
    `;
    els.messages.appendChild(wrapper);
    wrapper.scrollIntoView({ behavior: "smooth", block: "end" });
    return wrapper;
  }

  function extractAssistantText(result) {
    if (!result) return "No response returned.";
    return (
      result.answer ||
      result.reply ||
      result.response ||
      result.summary ||
      result.message ||
      result.result ||
      (typeof result === "string" ? result : JSON.stringify(result, null, 2))
    );
  }

  function assistantExtra(result) {
    const route = result?.route || result?.routing?.route || result?.mode_used;
    const inspected = result?.files_inspected || result?.context?.files_inspected || [];
    const steps = result?.steps || result?.tool_steps || [];

    const bits = [];
    if (route) bits.push(`Mode: ${route}`);
    if (Array.isArray(inspected) && inspected.length) bits.push(`${inspected.length} file(s) inspected`);
    if (Array.isArray(steps) && steps.length) bits.push(`${steps.length} tool step(s)`);

    return bits.length ? `
      <div class="activity-card" style="margin-top:12px">
        <div class="activity-title">Investigation</div>
        <div class="activity-meta">${escapeHtml(bits.join(" · "))}</div>
      </div>
    ` : "";
  }

  async function askAssistant(prompt) {
    if (!state.workspace) throw new Error("Select a workspace first.");
    const id = encodeURIComponent(workspaceId(state.workspace));
    const basePayload = {
      mode: els.modeSelect.value,
      max_files: Number(state.settings.maxFiles) || 3,
      use_semantic: els.semanticToggle.checked
    };

    const candidates = [
      { ...basePayload, question: prompt },
      { ...basePayload, query: prompt },
      { ...basePayload, prompt }
    ];

    let lastError;
    for (const body of candidates) {
      try {
        return await api(`/api/workspaces/${id}/assistant/ask`, {
          method: "POST",
          body: JSON.stringify(body)
        });
      } catch (error) {
        lastError = error;
        if (error.status !== 422) throw error;
      }
    }
    throw lastError;
  }

  async function createPatch(prompt) {
    if (!state.workspace) throw new Error("Select a workspace first.");
    const id = encodeURIComponent(workspaceId(state.workspace));
    return api(`/api/workspaces/${id}/patches`, {
      method: "POST",
      body: JSON.stringify({
        task: prompt,
        max_files: Number(state.settings.maxFiles) || 3,
        use_semantic: els.semanticToggle.checked
      })
    });
  }

  async function submitPrompt() {
    const prompt = els.promptInput.value.trim();
    if (!prompt || state.busy) return;

    state.busy = true;
    els.promptInput.value = "";
    resizeTextarea();
    addMessage("user", prompt);
    const loading = addLoadingMessage(state.patchMode ? "Preparing safe patch" : "Investigating repository");
    els.sendButton.disabled = true;

    try {
      state.requestCount += 1;
      els.sessionRequests.textContent = String(state.requestCount);

      if (state.patchMode) {
        const patch = await createPatch(prompt);
        state.patchCount += 1;
        els.sessionPatches.textContent = String(state.patchCount);
        loading.remove();

        const patchId = patch.patch_id;
        addMessage(
          "assistant",
          patch.summary || "I prepared a reviewable patch.",
          `
            <div class="patch-inline">
              <div class="patch-inline-head">
                <div>
                  <div class="patch-inline-title">${escapeHtml(patchId || "Generated patch")}</div>
                  <div class="patch-inline-meta">${escapeHtml((patch.files_changed || []).join(", ") || "Review required")}</div>
                </div>
                <button class="secondary-button inline-review" data-patch-id="${escapeHtml(patchId || "")}">Review patch</button>
              </div>
            </div>
          `
        );

        document.querySelectorAll(".inline-review").forEach(btn => {
          btn.addEventListener("click", () => openPatch(btn.dataset.patchId));
        });

        await Promise.allSettled([loadPatches(), loadIndexState()]);
        if (patchId) await openPatch(patchId);
      } else {
        const result = await askAssistant(prompt);
        loading.remove();
        addMessage("assistant", extractAssistantText(result), assistantExtra(result));
      }
    } catch (error) {
      loading.remove();
      addMessage("assistant", `Request failed: ${error.message}`);
      toast("Request failed", error.message, "error");
    } finally {
      state.busy = false;
      els.sendButton.disabled = false;
      els.promptInput.focus();
    }
  }

  function resizeTextarea() {
    els.promptInput.style.height = "auto";
    els.promptInput.style.height = `${Math.min(180, Math.max(30, els.promptInput.scrollHeight))}px`;
  }

  async function rebuildIndex(kind) {
    if (!state.workspace) return;
    const id = encodeURIComponent(workspaceId(state.workspace));
    const button = kind === "structural" ? els.rebuildStructural : els.rebuildSemantic;
    const original = button.textContent;
    let timerInterval = null;
    let elapsed = 0;

    try {
      button.disabled = true;
      button.textContent = kind === "structural" ? "Parsing code…" : "Embedding (0s)…";

      if (kind === "semantic") {
        toast("Building semantic index", "Generating vector embeddings for code chunks. This can take 30–90s on CPU.", "neutral");
        timerInterval = setInterval(() => {
          elapsed += 1;
          button.textContent = `Embedding (${elapsed}s)…`;
        }, 1000);
      } else {
        timerInterval = setInterval(() => {
          elapsed += 1;
          button.textContent = `Parsing (${elapsed}s)…`;
        }, 1000);
      }

      const path = kind === "structural"
        ? `/api/workspaces/${id}/index`
        : `/api/workspaces/${id}/semantic/build`;
      await api(path, { method: "POST" });
      toast(`${kind === "structural" ? "Structural" : "Semantic"} index refreshed`, `Completed in ${elapsed || 1}s`, "success");
      await loadIndexState();
    } catch (error) {
      toast("Index refresh failed", error.message, "error");
    } finally {
      if (timerInterval) clearInterval(timerInterval);
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function reconcileAll() {
    if (!state.workspace) return;
    const id = encodeURIComponent(workspaceId(state.workspace));
    const original = els.reconcileAll.textContent;
    try {
      els.reconcileAll.disabled = true;
      els.reconcileAll.textContent = "Reconciling…";
      await api(`/api/workspaces/${id}/patches/reconcile`, { method: "POST" });
      toast("Patch states reconciled", "", "success");
      await loadPatches();
    } catch (error) {
      toast("Could not reconcile patches", error.message, "error");
    } finally {
      els.reconcileAll.disabled = false;
      els.reconcileAll.textContent = original;
    }
  }

  function switchView(view) {
    qsa(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
    qsa(".view").forEach(panel => panel.classList.toggle("active", panel.id === `${view}View`));

    const titles = {
      chat: ["Workspace assistant", "Ask your codebase"],
      patches: ["Patch lifecycle", "Review & history"],
      repository: ["Repository intelligence", "Index state"]
    };
    els.viewEyebrow.textContent = titles[view][0];
    els.viewTitle.textContent = titles[view][1];

    if (view === "patches") loadPatches();
    if (view === "repository") loadIndexState();
  }

  function openSettings() {
    els.apiBaseInput.value = state.settings.apiBase || "";
    els.maxFilesInput.value = state.settings.maxFiles;
    els.historyLimitInput.value = state.settings.historyLimit;
    els.settingsModal.classList.remove("hidden");
  }

  function saveSettings() {
    state.settings.apiBase = els.apiBaseInput.value.trim();
    state.settings.maxFiles = Math.max(1, Math.min(10, Number(els.maxFilesInput.value) || 3));
    state.settings.historyLimit = Math.max(10, Math.min(200, Number(els.historyLimitInput.value) || 50));
    persistSettings();
    els.settingsModal.classList.add("hidden");
    toast("Settings saved", "Refreshing API connection.", "success");
    refreshWorkspaceData();
  }

  function bindEvents() {
    qsa(".nav-item").forEach(item => item.addEventListener("click", () => switchView(item.dataset.view)));
    qsa("[data-view-jump]").forEach(item => item.addEventListener("click", () => switchView(item.dataset.viewJump)));

    els.workspaceButton.addEventListener("click", () => els.workspaceMenu.classList.toggle("hidden"));
    document.addEventListener("click", event => {
      if (!els.workspaceButton.contains(event.target) && !els.workspaceMenu.contains(event.target)) {
        els.workspaceMenu.classList.add("hidden");
      }
    });

    els.promptInput.addEventListener("input", resizeTextarea);
    els.promptInput.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitPrompt();
      }
    });

    els.sendButton.addEventListener("click", submitPrompt);

    els.patchModeButton.addEventListener("click", () => {
      state.patchMode = !state.patchMode;
      els.patchModeButton.classList.toggle("active", state.patchMode);
      els.patchModeButton.textContent = state.patchMode ? "Change mode on" : "Make change";
      els.promptInput.placeholder = state.patchMode
        ? "Describe the code change you want OutrightBot to prepare…"
        : "Ask OutrightBot about this repository…";
    });

    qsa(".suggestion").forEach(item => item.addEventListener("click", () => {
      els.promptInput.value = item.dataset.prompt || "";
      resizeTextarea();
      els.promptInput.focus();
    }));

    qsa(".filter-tab").forEach(item => item.addEventListener("click", () => {
      state.patchFilter = item.dataset.filter;
      qsa(".filter-tab").forEach(x => x.classList.toggle("active", x === item));
      renderPatchTable();
    }));

    els.closeDrawer.addEventListener("click", closePatchDrawer);
    els.patchDrawerBackdrop.addEventListener("click", closePatchDrawer);
    els.approvePatch.addEventListener("click", () => patchAction("approve"));
    els.rejectPatch.addEventListener("click", () => patchAction("reject"));
    els.reconcilePatch.addEventListener("click", () => patchAction("reconcile"));
    els.reconcileAll.addEventListener("click", reconcileAll);

    els.rebuildStructural.addEventListener("click", () => rebuildIndex("structural"));
    els.rebuildSemantic.addEventListener("click", () => rebuildIndex("semantic"));
    els.refreshIndexState.addEventListener("click", loadIndexState);
    els.refreshAll.addEventListener("click", refreshWorkspaceData);

    els.settingsButton.addEventListener("click", openSettings);
    els.closeSettings.addEventListener("click", () => els.settingsModal.classList.add("hidden"));
    els.settingsModal.addEventListener("click", event => {
      if (event.target === els.settingsModal) els.settingsModal.classList.add("hidden");
    });
    els.saveSettings.addEventListener("click", saveSettings);
    els.resetSettings.addEventListener("click", () => {
      state.settings = { ...DEFAULTS };
      persistSettings();
      openSettings();
    });

    if (els.addWorkspaceButton) els.addWorkspaceButton.addEventListener("click", openAddWorkspaceModal);
    if (els.closeAddWorkspace) els.closeAddWorkspace.addEventListener("click", closeAddWorkspaceModal);
    if (els.cancelAddWorkspace) els.cancelAddWorkspace.addEventListener("click", closeAddWorkspaceModal);
    if (els.addWorkspaceModal) {
      els.addWorkspaceModal.addEventListener("click", event => {
        if (event.target === els.addWorkspaceModal) closeAddWorkspaceModal();
      });
    }
    if (els.addWorkspaceForm) els.addWorkspaceForm.addEventListener("submit", handleAddWorkspace);

    els.modeSelect.value = state.settings.mode || "auto";
    els.semanticToggle.checked = state.settings.semantic !== false;
    els.modeSelect.addEventListener("change", () => {
      state.settings.mode = els.modeSelect.value;
      persistSettings();
    });
    els.semanticToggle.addEventListener("change", () => {
      state.settings.semantic = els.semanticToggle.checked;
      persistSettings();
    });
  }

  async function bootstrap() {
    bindEvents();
    resizeTextarea();
    await loadHealth();
    await loadWorkspaces();
  }

  bootstrap();
})();
