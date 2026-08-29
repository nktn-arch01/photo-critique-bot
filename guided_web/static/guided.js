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
  root.innerHTML = "";
  reflectGroups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "reflect-group";

    const title = document.createElement("h3");
    title.className = "reflect-group-title";
    title.textContent = group.label;
    section.appendChild(title);

    const grid = document.createElement("div");
    grid.className = "reflect-group-items";
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
      grid.appendChild(label);
    });
    section.appendChild(grid);
    root.appendChild(section);
  });
}

let sessionId = null;
let userStars = 0;
let currentFileName = null;
let localPreviewUrl = null;
let serverPreviewUrl = null;
let cardPreviewLoaded = false;
let critiqueInProgress = false;

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.hidden = key !== name;
    el.classList.toggle("active", key === name);
  });
  document.querySelectorAll(".screen-nav [data-screen]").forEach((el) => {
    el.classList.toggle("active", el.dataset.screen === name);
  });
}

function navigateToScreen(name) {
  if (name === "read") {
    if (activePreviewUrl()) {
      setPhotoPreview(activePreviewUrl());
    }
    updateReadEmptyState();
  }
  if (name === "reflect") {
    ensureReflectPreview();
  }
  showScreen(name);
}

function activePreviewUrl() {
  return serverPreviewUrl || localPreviewUrl;
}

function setPhotoPreview(url) {
  const chooseImg = document.getElementById("photo-preview");
  const readImg = document.getElementById("read-photo-preview");
  [chooseImg, readImg].forEach((img) => {
    if (!img) return;
    if (url) {
      img.src = url;
      img.hidden = false;
    } else {
      img.removeAttribute("src");
      img.hidden = true;
    }
  });
  const dropZone = document.getElementById("drop-zone");
  if (dropZone) {
    dropZone.classList.toggle("has-photo", Boolean(url));
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
  if (!res.ok) throw new Error("upload failed");
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
  document.getElementById("btn-speak").disabled = false;
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
  if (serverPreviewUrl) {
    setPhotoPreview(serverPreviewUrl);
  } else if (previewFile) {
    revokeLocalPreview();
    localPreviewUrl = URL.createObjectURL(previewFile);
    setPhotoPreview(localPreviewUrl);
  }
  renderParams(data);
  showScreen("choose");
}

async function handleSelectedFile(file) {
  revokeLocalPreview();
  localPreviewUrl = URL.createObjectURL(file);
  setPhotoPreview(localPreviewUrl);

  const data = await uploadPhoto(file);
  await applyPhotoSession(data, file);
}

async function handleNativePhotoPick() {
  const data = await pickPhotoNative();
  if (!data) return;
  revokeLocalPreview();
  localPreviewUrl = null;
  await applyPhotoSession(data, null);
}

function resetReflectionFields() {
  document.querySelectorAll("#reflect-checklist input[type=checkbox]").forEach((el) => {
    el.checked = false;
  });
  document.getElementById("reflect-user-note").value = "";
  document.getElementById("card-theme").value = "dark";
}

function clearReadData() {
  critiqueInProgress = false;
  setReadLoading(false);
  document.getElementById("read-compact-wrap").hidden = true;
  document.getElementById("read-actions").hidden = true;
  document.getElementById("read-detail").hidden = true;
  document.getElementById("read-title").textContent = "";
  document.getElementById("read-summary").textContent = "";
  document.getElementById("read-point").textContent = "";
  document.getElementById("read-phase2-hint").hidden = true;
  document.getElementById("read-scores").innerHTML = "";
  document.getElementById("read-sections").innerHTML = "";
  document.getElementById("read-skeleton").textContent = "いま写真を読んでいます…";
  document.getElementById("read-skeleton").hidden = true;
  document.getElementById("read-empty-hint").hidden = true;
}

function clearReflectData() {
  userStars = 0;
  resetReflectionFields();
  clearCardPreview();
  cardPreviewLoaded = false;
  updateStarButtons();
  updateExportButton();
}

function clearReadAndReflectData() {
  clearReadData();
  clearReflectData();
}

function updateReadEmptyState() {
  const hint = document.getElementById("read-empty-hint");
  const skeleton = document.getElementById("read-skeleton");
  const hasCritique = Boolean(document.getElementById("read-title").textContent.trim());
  if (!sessionId) {
    hint.hidden = false;
    hint.textContent = "選ぶで写真を選んでください。";
    skeleton.hidden = true;
    return;
  }
  if (!hasCritique && !critiqueInProgress) {
    hint.hidden = false;
    hint.textContent = "選ぶで「言葉にする」を押してください。";
    skeleton.hidden = true;
    return;
  }
  hint.hidden = true;
}

function setReadLoading(loading) {
  document.getElementById("read-skeleton").hidden = !loading;
  if (loading) {
    document.getElementById("read-empty-hint").hidden = true;
    document.getElementById("read-compact-wrap").hidden = true;
    document.getElementById("read-actions").hidden = true;
    document.getElementById("read-detail").hidden = true;
  }
}

function showReadPanels() {
  document.getElementById("read-skeleton").hidden = true;
  document.getElementById("read-empty-hint").hidden = true;
  document.getElementById("read-compact-wrap").hidden = false;
  document.getElementById("read-actions").hidden = false;
  document.getElementById("read-detail").hidden = false;
}

function clearAllSession() {
  sessionId = null;
  currentFileName = null;
  serverPreviewUrl = null;
  revokeLocalPreview();
  setPhotoPreview(null);
  document.getElementById("params-preview").hidden = true;
  document.getElementById("params-preview-body").innerHTML = "";
  document.getElementById("btn-speak").disabled = true;
  document.getElementById("file-input").value = "";
  document.getElementById("user-note").value = "";
  document.getElementById("lens-select").value = "self";
  clearReadAndReflectData();
  navigateToScreen("choose");
}

document.getElementById("pick-file").addEventListener("click", async () => {
  try {
    await handleNativePhotoPick();
  } catch (err) {
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
    alert("写真の読み込みに失敗しました。もう一度お試しください。");
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
    alert("写真の読み込みに失敗しました。もう一度お試しください。");
  }
});

document.getElementById("btn-speak").addEventListener("click", () => {
  if (!sessionId) return;
  if (activePreviewUrl()) {
    setPhotoPreview(activePreviewUrl());
  }
  navigateToScreen("read");
  startCritique();
});

async function startCritique() {
  const hint = document.getElementById("read-phase2-hint");
  const emptyHint = document.getElementById("read-empty-hint");
  critiqueInProgress = true;
  emptyHint.hidden = true;
  setReadLoading(true);
  hint.hidden = true;

  const lens = document.getElementById("lens-select").value || "self";
  const userNote = document.getElementById("user-note").value || "";

  try {
    const res = await fetch(`/api/session/${sessionId}/critique`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lens, user_note: userNote }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || data.detail || "講評の開始に失敗しました");
    }
    renderCritique(data);
    showReadPanels();
    critiqueInProgress = false;

    if (data.status === "phase2_running") {
      hint.hidden = false;
      await pollCritiqueComplete();
    }
  } catch (err) {
    console.error(err);
    critiqueInProgress = false;
    const skeleton = document.getElementById("read-skeleton");
    skeleton.textContent = "言葉を読み取れませんでした。APIキーとネットワークを確認してください。";
    setReadLoading(true);
  }
}

async function pollCritiqueComplete() {
  const hint = document.getElementById("read-phase2-hint");
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const res = await fetch(`/api/session/${sessionId}/critique`);
    const data = await res.json();
    if (data.status === "complete") {
      renderCritique(data);
      hint.hidden = true;
      return;
    }
    if (data.status === "error") {
      hint.textContent = data.error || "詳細の取得に失敗しました";
      return;
    }
  }
  hint.textContent = "詳細の取得がタイムアウトしました。もう一度お試しください。";
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

  const sectionsEl = document.getElementById("read-sections");
  sectionsEl.innerHTML = "";
  (data.sections || []).forEach((sec) => {
    if (!["1", "2", "3", "4", "5", "6", "7"].includes(sec.id)) return;
    const details = document.createElement("details");
    details.className = "read-details read-section";
    if (sec.id === "2") {
      details.open = false;
    }
    const summary = document.createElement("summary");
    summary.textContent = sec.heading || `【${sec.id}】`;
    const body = document.createElement("div");
    body.textContent = sec.text;
    details.appendChild(summary);
    details.appendChild(body);
    sectionsEl.appendChild(details);
  });
}

document.getElementById("btn-reset").addEventListener("click", () => {
  clearAllSession();
});

document.querySelectorAll(".screen-nav [data-screen]").forEach((btn) => {
  btn.addEventListener("click", () => {
    navigateToScreen(btn.dataset.screen);
  });
});

document.getElementById("btn-again").addEventListener("click", () => {
  if (activePreviewUrl()) {
    setPhotoPreview(activePreviewUrl());
  }
  navigateToScreen("choose");
});

document.getElementById("btn-keep").addEventListener("click", () => {
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
  loading.hidden = false;
  loading.textContent = "カードを準備しています…";
  cardPreviewLoaded = false;
}

function reflectUserNote() {
  return document.getElementById("reflect-user-note").value || "";
}

async function refreshCardPreview() {
  if (!sessionId) return;
  clearCardPreview();
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
    const img = document.getElementById("card-preview-img");
    const loading = document.getElementById("card-preview-loading");
    img.src = `${data.card_url}?t=${Date.now()}`;
    img.hidden = false;
    loading.hidden = true;
    cardPreviewLoaded = true;
  } catch (err) {
    console.error(err);
    document.getElementById("card-preview-loading").textContent =
      "カードを表示できませんでした。講評が完了してからお試しください。";
    cardPreviewLoaded = false;
  }
}

function ensureReflectPreview() {
  if (!sessionId || cardPreviewLoaded) return;
  refreshCardPreview();
}

function prepareReflectScreen() {
  const reflectNote = document.getElementById("reflect-user-note");
  if (!reflectNote.value.trim()) {
    reflectNote.value = document.getElementById("user-note").value || "";
  }
  ensureReflectPreview();
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
    if (!res.ok) {
      throw new Error(data.detail || "書き出しに失敗しました");
    }
    await refreshCardPreview();
    alert(`書き出しました:\n${data.files.card}\n${data.files.note}`);
  } catch (err) {
    console.error(err);
    alert(err.message || "書き出しに失敗しました。");
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
loadReflectItems();
