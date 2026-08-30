const screens = {
  choose: document.getElementById("screen-choose"),
  read: document.getElementById("screen-read"),
  reflect: document.getElementById("screen-reflect"),
};

let reflectGroups = [];

async function loadReflectItems() {
  try {
    const res = await fetch("/api/reflect-items");
    if (!res.ok) return;
    const data = await res.json();
    reflectGroups = data.groups || [];
    renderReflectChecklist();
  } catch (err) {
    console.error(err);
  }
}

function renderReflectChecklist() {
  const root = document.getElementById("reflect-checklist");
  if (!root) return;
  const left = document.createElement("div");
  left.className = "reflect-checklist-column reflect-checklist-column-left";
  const right = document.createElement("div");
  right.className = "reflect-checklist-column reflect-checklist-column-right";
  reflectGroups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "reflect-group";
    section.dataset.groupId = group.id || "";

    const title = document.createElement("h3");
    title.className = "reflect-group-title";
    title.textContent = group.label;
    section.appendChild(title);

    const list = document.createElement("div");
    list.className = "reflect-group-items";
    (group.items || []).forEach((item) => {
      const key = `${group.id}_${item.id}`;
      const label = document.createElement("label");
      label.className = "reflect-check";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.reflectKey = key;
      input.dataset.reflectLabel = item.label;
      input.id = `reflect-${key}`;
      const text = document.createElement("span");
      text.textContent = item.label;
      label.appendChild(input);
      label.appendChild(text);
      list.appendChild(label);
    });
    section.appendChild(list);
    const column = group.column === "right" ? right : left;
    column.appendChild(section);
  });
  root.replaceChildren(left, right);
}

let sessionId = null;

async function releaseServerSession() {
  if (!sessionId) return;
  const id = sessionId;
  try {
    await fetch(`/api/session/${id}/release`, { method: "POST" });
  } catch (err) {
    console.warn("session cleanup failed", err);
  }
}

function releaseSessionOnUnload(event) {
  if (event && event.type === "pagehide" && event.persisted) return;
  if (!sessionId) return;
  const id = sessionId;
  const url = `/api/session/${id}/release`;
  const sent = typeof navigator.sendBeacon === "function" && navigator.sendBeacon(url);
  if (!sent) {
    fetch(url, { method: "POST", keepalive: true }).catch(() => {});
  }
}

function announceScreenLeaving(event) {
  if (event && event.type === "pagehide" && event.persisted) return;
  const url = "/api/presence/unload";
  const sent = typeof navigator.sendBeacon === "function" && navigator.sendBeacon(url);
  if (!sent) {
    fetch(url, { method: "POST", keepalive: true }).catch(() => {});
  }
}

const HEARTBEAT_MS = 8000;
let heartbeatTimer = null;

function pingHeartbeat() {
  fetch("/api/heartbeat", { method: "POST", keepalive: true }).catch(() => {});
}

function startHeartbeat() {
  if (heartbeatTimer != null) return;
  pingHeartbeat();
  heartbeatTimer = window.setInterval(pingHeartbeat, HEARTBEAT_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer == null) return;
  window.clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

const TOAST_MS = 4200;

function showToast(message, tone = "info") {
  const region = document.getElementById("toast-region");
  if (!region || !message) return;
  const el = document.createElement("div");
  el.className = `toast toast-${tone}`;
  el.setAttribute("role", tone === "error" ? "alert" : "status");
  el.textContent = message;
  region.appendChild(el);
  requestAnimationFrame(() => el.classList.add("visible"));
  window.setTimeout(() => {
    el.classList.remove("visible");
    window.setTimeout(() => el.remove(), 280);
  }, TOAST_MS);
}

function setPhase2RetryVisible(visible) {
  const btn = document.getElementById("btn-phase2-retry");
  if (btn) btn.hidden = !visible;
}

function resetPhase2Hint() {
  const hint = document.getElementById("read-phase2-hint");
  hint.textContent = "詳しい言葉を読み込んでいます…";
  hint.hidden = true;
  setPhase2RetryVisible(false);
}
let userStars = 0;
let currentFileName = null;
let localPreviewUrl = null;
let serverPreviewUrl = null;
let cardPreviewLoaded = false;
let critiqueInProgress = false;
let critiqueGeneration = 0;
let critiqueAbort = null;
let activeCritiqueEpoch = null;
let readPhotoShown = false;
let reflectPrepared = false;

function stopCritiqueWatch() {
  critiqueGeneration += 1;
  if (critiqueAbort) {
    critiqueAbort.abort();
    critiqueAbort = null;
  }
  critiqueInProgress = false;
  setReadLoading(false);
}

function endCritiqueWatch() {
  critiqueAbort = null;
  critiqueInProgress = false;
}

function critiqueWatchIsLive() {
  return Boolean(critiqueAbort && !critiqueAbort.signal.aborted);
}

function applyInterruptedCritiqueHint() {
  critiqueInProgress = false;
  const hint = document.getElementById("read-phase2-hint");
  const pending = readDropdownElements().some(
    (el) => el && el.classList.contains("read-group-pending"),
  );
  if (hint && pending) {
    hint.hidden = false;
    hint.textContent = "詳しい言葉が途切れました。「選ぶ」で「言葉にする」を押してください。";
    setPhase2RetryVisible(false);
  }
  updateKeepButton();
}

async function ensureCritiqueWatch() {
  if (!sessionId || critiqueWatchIsLive()) return;
  try {
    const res = await fetch(`/api/session/${sessionId}/critique`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.epoch != null) activeCritiqueEpoch = data.epoch;
    if (data.status === "complete") {
      await applyCritiqueProgress(data, critiqueGeneration);
      endCritiqueWatch();
      resetPhase2Hint();
      updateKeepButton();
      return;
    }
    if (data.status === "phase1_running" || data.status === "phase2_running") {
      const requestId = critiqueGeneration;
      critiqueAbort = new AbortController();
      critiqueInProgress = true;
      updateKeepButton();
      await applyCritiqueProgress(data, requestId);
      if (requestId !== critiqueGeneration) return;
      const hint = document.getElementById("read-phase2-hint");
      if (data.status === "phase2_running") hint.hidden = false;
      await pollCritique(requestId, Boolean(data.phase1));
      if (requestId !== critiqueGeneration) return;
      endCritiqueWatch();
      updateKeepButton();
      return;
    }
    if (data.status === "idle") {
      endCritiqueWatch();
      return;
    }
  } catch (err) {
    if (err && err.name === "AbortError") return;
    console.error(err);
  }
}

function syncSpeakButton() {
  const btn = document.getElementById("btn-speak");
  if (btn) btn.disabled = !sessionId;
}

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    if (!el) return;
    const on = key === name;
    el.hidden = !on;
    el.inert = !on;
    el.classList.toggle("active", on);
  });
  document.querySelectorAll(".screen-nav [data-screen]").forEach((el) => {
    el.classList.toggle("active", el.dataset.screen === name);
  });
  syncSpeakButton();
}

function hasReadContent() {
  const title = document.getElementById("read-title");
  return (
    readPhotoShown ||
    critiqueInProgress ||
    Boolean(title && title.textContent.trim())
  );
}

function syncScreenGuides() {
  const readEmpty = document.getElementById("read-empty");
  const readBody = document.getElementById("read-body");
  const reflectEmpty = document.getElementById("reflect-empty");
  const reflectBody = document.getElementById("reflect-body");
  const readyRead = hasReadContent();
  if (readEmpty) readEmpty.hidden = readyRead;
  if (readBody) readBody.hidden = !readyRead;
  if (reflectEmpty) reflectEmpty.hidden = reflectPrepared;
  if (reflectBody) reflectBody.hidden = !reflectPrepared;
}

function navigateToScreen(name, opts) {
  const hydrate = !opts || opts.hydrate !== false;
  if (name === "read" && readPhotoShown && activePreviewUrl()) {
    setReadPhotoPreview(activePreviewUrl());
  }
  syncScreenGuides();
  showScreen(name);
  if (name === "read" && hydrate) {
    void ensureCritiqueWatch();
  }
}

function activePreviewUrl() {
  return serverPreviewUrl || localPreviewUrl;
}

function setChoosePhotoPreview(url) {
  const img = document.getElementById("photo-preview");
  const dropZone = document.getElementById("drop-zone");
  if (!img) return;
  if (url) {
    img.src = url;
    img.hidden = false;
  } else {
    img.removeAttribute("src");
    img.hidden = true;
  }
  if (dropZone) {
    dropZone.classList.toggle("has-photo", Boolean(url));
  }
}

function setReadPhotoPreview(url) {
  const img = document.getElementById("read-photo-preview");
  if (!img) return;
  if (url) {
    img.src = url;
    img.hidden = false;
  } else {
    img.removeAttribute("src");
    img.hidden = true;
  }
}

function hideReadPhoto() {
  readPhotoShown = false;
  setReadPhotoPreview(null);
}

function setPhotoPreview(url) {
  setChoosePhotoPreview(url);
  if (readPhotoShown) {
    setReadPhotoPreview(url);
  }
}

function revokeLocalPreview() {
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = null;
  }
}

async function uploadPhoto(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/session/photo", { method: "POST", body: fd });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "upload failed");
  }
  return res.json();
}

function renderParams(data) {
  const wrap = document.getElementById("params-preview");
  const body = document.getElementById("params-preview-body");
  const groups =
    data.parameter_display ||
    buildParameterDisplayFallback(data.api_parameters, data.file_name);
  body.innerHTML = "";

  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "params-group";

    const title = document.createElement("h3");
    title.className = "params-group-title";
    title.textContent = group.title;
    section.appendChild(title);

    const table = document.createElement("table");
    table.className = "params-table";
    const tbody = document.createElement("tbody");

    (group.rows || []).forEach((row) => {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.scope = "row";
      th.textContent = row.label;
      const td = document.createElement("td");
      td.textContent = row.value;
      tr.appendChild(th);
      tr.appendChild(td);
      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    section.appendChild(table);
    body.appendChild(section);
  });

  wrap.hidden = false;
  syncSpeakButton();
}

function buildParameterDisplayFallback(apiParameters, fileName) {
  const image = apiParameters?.image || {};
  const camera = apiParameters?.camera || {};
  const imageRows = [
    ["file_name", "ファイル名", fileName || image.file_name],
    ["size", "サイズ", image.size],
    ["shot_at", "撮影日時", image.shot_at],
    ["timezone", "タイムゾーン", image.timezone],
    ["region", "地域", image.region],
    ["time_band", "時間帯", image.time_band],
  ].map(([key, label, value]) => ({
    key,
    label,
    value: value ?? "不明",
  }));
  const cameraRows = [
    ["focal_length", "焦点距離"],
    ["aperture", "絞り"],
    ["shutter_speed", "シャッター速度"],
    ["iso", "ISO"],
    ["mode", "露出モード"],
    ["exposure_compensation", "露出補正"],
  ].map(([key, label]) => ({
    key,
    label,
    value: camera[key] ?? "不明",
  }));
  return [
    { title: "画像情報", rows: imageRows },
    { title: "カメラ設定", rows: cameraRows },
  ];
}

async function pickPhotoNative() {
  const res = await fetch("/api/session/photo-pick", { method: "POST" });
  if (res.status === 400) {
    const data = await res.json().catch(() => ({}));
    if ((data.detail || "").includes("not selected")) {
      return null;
    }
    throw new Error(data.detail || "photo pick failed");
  }
  if (!res.ok) throw new Error("photo pick failed");
  return res.json();
}

async function applyPhotoSession(data, previewFile) {
  clearReadAndReflectData();
  document.getElementById("user-note").value = "";
  document.getElementById("lens-select").value = "self";
  sessionId = data.session_id;
  currentFileName = data.file_name || previewFile?.name;
  serverPreviewUrl = data.preview_url || null;
  const previousLocal = localPreviewUrl;
  if (serverPreviewUrl) {
    localPreviewUrl = null;
    setChoosePhotoPreview(serverPreviewUrl);
  } else if (previewFile) {
    localPreviewUrl = URL.createObjectURL(previewFile);
    setChoosePhotoPreview(localPreviewUrl);
  } else {
    localPreviewUrl = null;
    setChoosePhotoPreview(null);
  }
  if (previousLocal && previousLocal !== localPreviewUrl) {
    URL.revokeObjectURL(previousLocal);
  }
  hideReadPhoto();
  renderParams(data);
  showScreen("choose");
}

async function adoptPhotoSession(data, previewFile) {
  const previousId = sessionId;
  stopCritiqueWatch();
  await applyPhotoSession(data, previewFile);
  if (previousId && previousId !== sessionId) {
    try {
      await fetch(`/api/session/${previousId}/release`, { method: "POST" });
    } catch (err) {
      console.warn("session cleanup failed", err);
    }
  }
}

async function handleSelectedFile(file) {
  const data = await uploadPhoto(file);
  await adoptPhotoSession(data, file);
}

let nativePickInFlight = false;

async function handleNativePhotoPick() {
  if (nativePickInFlight) return;
  nativePickInFlight = true;
  const pickBtn = document.getElementById("pick-file");
  if (pickBtn) pickBtn.disabled = true;
  try {
    const data = await pickPhotoNative();
    if (!data) return;
    await adoptPhotoSession(data, null);
  } finally {
    nativePickInFlight = false;
    if (pickBtn) pickBtn.disabled = false;
  }
}

function resetReflectionFields() {
  document.querySelectorAll("#reflect-checklist input[type=checkbox]").forEach((el) => {
    el.checked = false;
  });
  document.getElementById("reflect-user-note").value = "";
  document.getElementById("card-theme").value = "dark";
}

function readDropdownElements() {
  return [
    document.getElementById("detail-scores"),
    document.getElementById("detail-sections-123"),
    document.getElementById("detail-sections-4567"),
  ];
}

function setReadDropdownPending(el, pending) {
  if (!el) return;
  if (pending) {
    el.open = false;
    el.classList.add("read-group-pending");
  } else {
    el.classList.remove("read-group-pending");
  }
}

function resetReadDropdowns() {
  readDropdownElements().forEach((el) => setReadDropdownPending(el, true));
  updateKeepButton();
}

function hasScoresContent(data) {
  const scores = data.phase1?.scores || {};
  return Object.keys(scores).length > 0;
}

function hasSectionsContent(data, ids) {
  return (data.sections || []).some(
    (sec) => ids.includes(sec.id) && String(sec.text || "").trim(),
  );
}

function nextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

async function activateDropdownsSequentially(data) {
  const groups = [
    {
      el: document.getElementById("detail-scores"),
      ready: () => hasScoresContent(data),
    },
    {
      el: document.getElementById("detail-sections-123"),
      ready: () => hasSectionsContent(data, ["1", "2", "3"]),
    },
    {
      el: document.getElementById("detail-sections-4567"),
      ready: () => hasSectionsContent(data, ["4", "5", "6", "7"]),
    },
  ];

  for (const group of groups) {
    if (!group.el || !group.el.classList.contains("read-group-pending")) continue;
    if (!group.ready()) continue;
    setReadDropdownPending(group.el, false);
    updateKeepButton();
    await nextPaint();
  }
}

function updateKeepButton() {
  const btn = document.getElementById("btn-keep");
  if (!btn) return;
  const pending = readDropdownElements().some(
    (el) => el && el.classList.contains("read-group-pending"),
  );
  btn.disabled = pending || critiqueInProgress;
}

function bindReadDropdownGuards() {
  readDropdownElements().forEach((el) => {
    if (!el || el.dataset.guardBound) return;
    el.dataset.guardBound = "1";
    el.addEventListener("toggle", () => {
      if (el.classList.contains("read-group-pending")) {
        el.open = false;
      }
    });
  });
}

function clearReadData() {
  critiqueInProgress = false;
  hideReadPhoto();
  setReadLoading(false);
  document.getElementById("read-compact-wrap").hidden = true;
  document.getElementById("read-actions").hidden = true;
  document.getElementById("read-detail").hidden = true;
  document.getElementById("read-title").textContent = "";
  document.getElementById("read-summary").textContent = "";
  document.getElementById("read-point").textContent = "";
  resetPhase2Hint();
  document.getElementById("read-scores").innerHTML = "";
  document.getElementById("read-sections-123").innerHTML = "";
  document.getElementById("read-sections-4567").innerHTML = "";
  document.getElementById("read-skeleton").textContent = "いま写真を読んでいます…";
  document.getElementById("read-skeleton").hidden = true;
  resetReadDropdowns();
  updateKeepButton();
  syncScreenGuides();
}

function clearReflectData() {
  reflectPrepared = false;
  userStars = 0;
  resetReflectionFields();
  clearCardPreview();
  cardPreviewLoaded = false;
  updateStarButtons();
  updateExportButton();
  syncScreenGuides();
}

function clearReadAndReflectData() {
  clearReadData();
  clearReflectData();
}

function setReadLoading(loading) {
  document.getElementById("read-skeleton").hidden = !loading;
  document.getElementById("read-detail").hidden = false;
  if (loading) {
    document.getElementById("read-compact-wrap").hidden = true;
    document.getElementById("read-actions").hidden = false;
    resetReadDropdowns();
  }
  updateKeepButton();
}

function showReadPanelsPhase1() {
  document.getElementById("read-skeleton").hidden = true;
  document.getElementById("read-compact-wrap").hidden = false;
  document.getElementById("read-actions").hidden = false;
  document.getElementById("read-detail").hidden = false;
  updateKeepButton();
}

async function clearAllSession() {
  stopCritiqueWatch();
  await releaseServerSession();
  sessionId = null;
  currentFileName = null;
  serverPreviewUrl = null;
  revokeLocalPreview();
  setChoosePhotoPreview(null);
  hideReadPhoto();
  document.getElementById("params-preview").hidden = true;
  document.getElementById("params-preview-body").innerHTML = "";
  document.getElementById("file-input").value = "";
  document.getElementById("user-note").value = "";
  document.getElementById("lens-select").value = "self";
  clearReadAndReflectData();
  syncSpeakButton();
  navigateToScreen("choose");
}

document.getElementById("pick-file").addEventListener("click", async () => {
  try {
    await handleNativePhotoPick();
  } catch (err) {
    const msg = String(err && err.message ? err.message : "");
    if (msg.includes("unreadable image") || msg.includes("not found")) {
      showToast("写真の読み込みに失敗しました。もう一度お試しください。", "error");
      return;
    }
    console.warn("native photo pick unavailable, falling back to file input", err);
    document.getElementById("file-input").click();
  }
});

document.getElementById("file-input").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    await handleSelectedFile(file);
  } catch (err) {
    console.error(err);
    showToast("写真の読み込みに失敗しました。もう一度お試しください。", "error");
  } finally {
    e.target.value = "";
  }
});

const dropZone = document.getElementById("drop-zone");
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});
dropZone.addEventListener("drop", async (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer?.files?.[0];
  if (!file || !file.type.startsWith("image/")) return;
  try {
    await handleSelectedFile(file);
  } catch (err) {
    console.error(err);
    showToast("写真の読み込みに失敗しました。もう一度お試しください。", "error");
  }
});

document.getElementById("btn-speak").addEventListener("click", () => {
  if (!sessionId) {
    showToast("写真がありません。もう一度写真を選んでください。", "error");
    syncSpeakButton();
    return;
  }
  stopCritiqueWatch();
  clearReadAndReflectData();
  if (activePreviewUrl()) {
    setReadPhotoPreview(activePreviewUrl());
    readPhotoShown = true;
  }
  critiqueInProgress = true;
  setReadLoading(true);
  navigateToScreen("read", { hydrate: false });
  startCritique();
});

async function startCritique() {
  const requestId = ++critiqueGeneration;
  if (critiqueAbort) critiqueAbort.abort();
  critiqueAbort = new AbortController();
  const signal = critiqueAbort.signal;

  const hint = document.getElementById("read-phase2-hint");
  critiqueInProgress = true;
  setReadLoading(true);
  resetPhase2Hint();

  const lens = document.getElementById("lens-select").value || "self";
  const userNote = document.getElementById("user-note").value || "";

  try {
    const res = await fetch(`/api/session/${sessionId}/critique`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lens, user_note: userNote, force_restart: true }),
      signal,
    });
    if (requestId !== critiqueGeneration) return;
    const data = await res.json().catch(() => ({}));
    if (requestId !== critiqueGeneration) return;
    if (data.epoch != null) activeCritiqueEpoch = data.epoch;
    if (res.status === 404) {
      sessionId = null;
      activeCritiqueEpoch = null;
      endCritiqueWatch();
      syncSpeakButton();
      showToast("写真がありません。もう一度写真を選んでください。", "error");
      navigateToScreen("choose");
      return;
    }
    if (res.status === 409) {
      throw new Error("いま読み込みの途中です。少し待ってから、もう一度「言葉にする」を押してください。");
    }
    if (!res.ok) {
      throw new Error(data.error || data.detail || "講評の開始に失敗しました");
    }
    await applyCritiqueProgress(data, requestId);
    if (requestId !== critiqueGeneration) return;
    if (data.status === "phase1_running" || data.status === "phase2_running") {
      if (data.status === "phase2_running") hint.hidden = false;
      await pollCritique(requestId, Boolean(data.phase1));
    }
    if (requestId !== critiqueGeneration) return;
    endCritiqueWatch();
    updateKeepButton();
  } catch (err) {
    if (err.name === "AbortError" || requestId !== critiqueGeneration) return;
    console.error(err);
    endCritiqueWatch();
    updateKeepButton();
    const skeleton = document.getElementById("read-skeleton");
    skeleton.textContent = err.message || "言葉を読み取れませんでした。「もう一度」を押してください。";
    setReadLoading(true);
  }
}

async function applyCritiqueProgress(data, requestId) {
  if (!data.phase1) return;
  if (requestId !== critiqueGeneration) return;
  renderCritique(data);
  showReadPanelsPhase1();
  await activateDropdownsSequentially(data);
}

async function pollCritique(requestId, shownPhase1) {
  const hint = document.getElementById("read-phase2-hint");
  for (let i = 0; i < 200; i++) {
    if (requestId !== critiqueGeneration) return;
    await new Promise((r) => setTimeout(r, 400));
    if (requestId !== critiqueGeneration) return;
    const res = await fetch(`/api/session/${sessionId}/critique`, { signal: critiqueAbort?.signal });
    if (requestId !== critiqueGeneration) return;
    const data = await res.json();
    if (data.epoch != null) activeCritiqueEpoch = data.epoch;
    if (data.status === "idle") {
      applyInterruptedCritiqueHint();
      endCritiqueWatch();
      return;
    }
    if (data.phase1 && !shownPhase1) {
      shownPhase1 = true;
      await applyCritiqueProgress(data, requestId);
      if (data.status === "phase2_running") hint.hidden = false;
    }
    if (data.status === "complete") {
      renderCritique(data);
      resetPhase2Hint();
      await activateDropdownsSequentially(data);
      return;
    }
    if (data.status === "error") {
      if (shownPhase1) {
        hint.hidden = false;
        hint.textContent = data.error || "詳細の取得に失敗しました";
        setPhase2RetryVisible(true);
        return;
      }
      throw new Error(data.error || "言葉を読み取れませんでした。「もう一度」を押してください。");
    }
    if (data.status === "phase2_running" && shownPhase1) {
      hint.hidden = false;
    }
  }
  if (requestId !== critiqueGeneration) return;
  hint.hidden = false;
  hint.textContent = "詳細の取得がタイムアウトしました。";
  setPhase2RetryVisible(true);
}

async function retryPhase2() {
  if (!sessionId) return;
  const hint = document.getElementById("read-phase2-hint");
  setPhase2RetryVisible(false);
  hint.hidden = false;
  hint.textContent = "詳しい言葉を読み込んでいます…";
  try {
    const res = await fetch(`/api/session/${sessionId}/critique/phase2/retry`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || data.error || "再取得に失敗しました");
    }
    await pollCritique(critiqueGeneration, true);
  } catch (err) {
    console.error(err);
    hint.hidden = false;
    hint.textContent = err.message || "詳細の取得に失敗しました";
    setPhase2RetryVisible(true);
  }
}

function appendSectionBlock(container, sec) {
  const block = document.createElement("div");
  block.className = "read-section-block";
  const heading = document.createElement("h3");
  heading.className = "read-section-heading";
  heading.textContent = sec.heading || `【${sec.id}】`;
  const body = document.createElement("div");
  body.className = "read-section-text";
  body.textContent = sec.text;
  block.appendChild(heading);
  block.appendChild(body);
  container.appendChild(block);
}

function renderCritique(data) {
  const p1 = data.phase1 || {};
  document.getElementById("read-title").textContent = p1.title || "";
  document.getElementById("read-summary").textContent = p1.summary || "";
  document.getElementById("read-point").textContent = p1.critique_summary || "";

  const scoresEl = document.getElementById("read-scores");
  scoresEl.innerHTML = "";
  const scores = p1.scores || {};
  Object.entries(scores).forEach(([label, info]) => {
    const line = document.createElement("p");
    line.textContent = `${label}: ${info.stars || ""} (${info.val || ""}/5)`;
    scoresEl.appendChild(line);
  });

  const sections123 = document.getElementById("read-sections-123");
  const sections4567 = document.getElementById("read-sections-4567");
  sections123.innerHTML = "";
  sections4567.innerHTML = "";
  (data.sections || []).forEach((sec) => {
    if (["1", "2", "3"].includes(sec.id)) {
      appendSectionBlock(sections123, sec);
    }
    if (["4", "5", "6", "7"].includes(sec.id)) {
      appendSectionBlock(sections4567, sec);
    }
  });
}

document.getElementById("btn-reset").addEventListener("click", () => {
  clearAllSession();
});

document.getElementById("btn-phase2-retry").addEventListener("click", () => {
  retryPhase2();
});

document.querySelectorAll(".screen-nav [data-screen]").forEach((btn) => {
  btn.addEventListener("click", () => {
    navigateToScreen(btn.dataset.screen);
  });
});

document.getElementById("btn-again").addEventListener("click", () => {
  navigateToScreen("choose");
});

document.getElementById("btn-keep").addEventListener("click", () => {
  if (document.getElementById("btn-keep").disabled) return;
  prepareReflectScreen();
  navigateToScreen("reflect");
});

function updateExportButton() {
  const btn = document.getElementById("btn-export");
  btn.disabled = !(userStars >= 1 && sessionId);
}

function clearCardPreview() {
  const img = document.getElementById("card-preview-img");
  const loading = document.getElementById("card-preview-loading");
  img.hidden = true;
  img.removeAttribute("src");
  loading.hidden = true;
  cardPreviewLoaded = false;
}

function reflectUserNote() {
  return document.getElementById("reflect-user-note").value || "";
}

async function refreshCardPreview() {
  if (!sessionId) return;
  const img = document.getElementById("card-preview-img");
  const loading = document.getElementById("card-preview-loading");
  img.hidden = true;
  img.removeAttribute("src");
  loading.hidden = false;
  cardPreviewLoaded = false;

  const theme = document.getElementById("card-theme").value || "dark";
  try {
    const res = await fetch(`/api/session/${sessionId}/card`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        card_theme: theme,
        user_stars: userStars,
        user_note: reflectUserNote(),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "カードの生成に失敗しました");
    }
    img.src = `${data.card_url}?t=${Date.now()}`;
    img.hidden = false;
    loading.hidden = true;
    cardPreviewLoaded = true;
  } catch (err) {
    console.error(err);
    loading.hidden = true;
    cardPreviewLoaded = false;
    showToast(err.message || "カードの生成に失敗しました。", "error");
  }
}

function prepareReflectScreen() {
  reflectPrepared = true;
  const reflectNote = document.getElementById("reflect-user-note");
  if (!reflectNote.value.trim()) {
    reflectNote.value = document.getElementById("user-note").value || "";
  }
  syncScreenGuides();
  refreshCardPreview();
}

function afterExportSuccess(files) {
  const card = files?.card || "";
  const note = files?.note || "";
  const lines = ["書き出しました", card, note].filter(Boolean);
  showToast(lines.join("\n"), "success");
}

function collectReflections() {
  const out = {};
  document.querySelectorAll("#reflect-checklist input[type=checkbox]").forEach((el) => {
    const key = el.dataset.reflectKey;
    if (!key) return;
    out[key] = {
      checked: el.checked,
      text: "",
      label: el.dataset.reflectLabel || "",
    };
  });
  return out;
}

document.getElementById("btn-export").addEventListener("click", async () => {
  if (!sessionId || userStars < 1) return;
  const btn = document.getElementById("btn-export");
  btn.disabled = true;
  btn.textContent = "書き出し中…";
  try {
    const res = await fetch(`/api/session/${sessionId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_stars: userStars,
        card_theme: document.getElementById("card-theme").value || "dark",
        user_note: reflectUserNote(),
        reflections: collectReflections(),
      }),
    });
    const data = await res.json();
    if (data.cancelled) {
      return;
    }
    if (!res.ok) {
      throw new Error(data.detail || "書き出しに失敗しました");
    }
    await refreshCardPreview();
    afterExportSuccess(data.files || {});
  } catch (err) {
    console.error(err);
    showToast(err.message || "書き出しに失敗しました。", "error");
  } finally {
    updateExportButton();
    btn.textContent = "Noteに書き出す";
  }
});

document.querySelectorAll("#user-stars button").forEach((btn) => {
  btn.addEventListener("click", () => {
    userStars = Number(btn.dataset.value);
    updateStarButtons();
    updateExportButton();
  });
});

function updateStarButtons() {
  document.querySelectorAll("#user-stars button").forEach((btn) => {
    const v = Number(btn.dataset.value);
    const filled = userStars >= v;
    btn.textContent = filled ? "★" : "☆";
    btn.classList.toggle("selected", filled && v === userStars);
  });
}

updateStarButtons();
bindReadDropdownGuards();
syncScreenGuides();
syncSpeakButton();
loadReflectItems();
startHeartbeat();
window.addEventListener("beforeunload", releaseSessionOnUnload);
window.addEventListener("pagehide", releaseSessionOnUnload);
window.addEventListener("pagehide", announceScreenLeaving);

async function quitApp() {
  const btn = document.getElementById("btn-quit");
  if (btn) btn.disabled = true;
  stopHeartbeat();
  try {
    await fetch("/api/shutdown", { method: "POST" });
  } catch (_err) {
    /* server already gone */
  }
  document.querySelectorAll("main.screen").forEach((el) => {
    el.hidden = true;
    el.inert = true;
  });
  const header = document.querySelector(".app-header");
  if (header) header.hidden = true;
  let done = document.getElementById("quit-done");
  if (!done) {
    done = document.createElement("p");
    done.id = "quit-done";
    done.className = "quit-done";
    document.body.appendChild(done);
  }
  done.textContent = "終了しました。このタブを閉じてください。";
}

document.getElementById("btn-quit")?.addEventListener("click", () => {
  void quitApp();
});
