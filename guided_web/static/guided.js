const screens = {
  choose: document.getElementById("screen-choose"),
  read: document.getElementById("screen-read"),
  reflect: document.getElementById("screen-reflect"),
};

let sessionId = null;
let userStars = 0;
let saveFolder = null;
let localPreviewUrl = null;
let serverPreviewUrl = null;

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.hidden = key !== name;
    el.classList.toggle("active", key === name);
  });
  document.querySelectorAll(".screen-nav span").forEach((el) => {
    el.classList.toggle("active", el.dataset.screen === name);
  });
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
  const el = document.getElementById("params-preview");
  el.hidden = false;
  el.textContent = JSON.stringify(data.api_parameters, null, 2);
  document.getElementById("btn-speak").disabled = false;
}

async function handleSelectedFile(file) {
  revokeLocalPreview();
  localPreviewUrl = URL.createObjectURL(file);
  setPhotoPreview(localPreviewUrl);

  const data = await uploadPhoto(file);
  sessionId = data.session_id;
  serverPreviewUrl = data.preview_url || null;
  if (serverPreviewUrl) {
    setPhotoPreview(serverPreviewUrl);
  }
  renderParams(data);
}

function resetSession() {
  sessionId = null;
  userStars = 0;
  serverPreviewUrl = null;
  revokeLocalPreview();
  setPhotoPreview(null);
  document.getElementById("params-preview").hidden = true;
  document.getElementById("params-preview").textContent = "";
  document.getElementById("btn-speak").disabled = true;
  document.getElementById("file-input").value = "";
  document.getElementById("user-note").value = "";
  document.getElementById("reflect-note-edit").value = "";
  document.getElementById("reflect-user-note").hidden = true;
  document.getElementById("reflect-user-note").textContent = "";
  clearCardPreview();
  updateStarButtons();
  updateExportButton();
  showScreen("choose");
}

document.getElementById("pick-file").addEventListener("click", () => {
  document.getElementById("file-input").click();
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
  showScreen("read");
  startCritique();
});

async function startCritique() {
  const skeleton = document.getElementById("read-skeleton");
  const content = document.getElementById("read-content");
  const hint = document.getElementById("read-phase2-hint");
  skeleton.hidden = false;
  content.hidden = true;
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
    skeleton.hidden = true;
    content.hidden = false;

    if (data.status === "phase2_running") {
      hint.hidden = false;
      await pollCritiqueComplete();
    }
  } catch (err) {
    console.error(err);
    skeleton.textContent = "言葉を読み取れませんでした。APIキーとネットワークを確認してください。";
    skeleton.hidden = false;
    content.hidden = true;
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
    if (sec.id === "2") {
      const details = document.createElement("details");
      details.className = "read-details read-section";
      details.open = false;
      const summary = document.createElement("summary");
      summary.textContent = "情景描写";
      const body = document.createElement("div");
      body.textContent = sec.text;
      details.appendChild(summary);
      details.appendChild(body);
      sectionsEl.appendChild(details);
      return;
    }
    if (["1", "3", "4", "5", "6", "7"].includes(sec.id)) {
      const details = document.createElement("details");
      details.className = "read-details read-section";
      const summary = document.createElement("summary");
      summary.textContent = sec.heading || `【${sec.id}】`;
      const body = document.createElement("div");
      body.textContent = sec.text;
      details.appendChild(summary);
      details.appendChild(body);
      sectionsEl.appendChild(details);
    }
  });
}

document.getElementById("btn-reset").addEventListener("click", () => {
  resetSession();
});

document.getElementById("btn-again").addEventListener("click", () => {
  // リセットではなく選ぶへ戻るだけ（写真・パラメータは保持）
  if (activePreviewUrl()) {
    setPhotoPreview(activePreviewUrl());
  }
  showScreen("choose");
});

document.getElementById("btn-keep").addEventListener("click", () => {
  prepareReflectScreen();
  showScreen("reflect");
});

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    if (!res.ok) return;
    const data = await res.json();
    saveFolder = data.save_folder || null;
    updateSaveFolderDisplay();
  } catch (err) {
    console.error(err);
  }
}

function updateSaveFolderDisplay() {
  const el = document.getElementById("save-folder-path");
  el.textContent = saveFolder || "未選択（フォルダを選んでください）";
  updateExportButton();
}

function updateExportButton() {
  const btn = document.getElementById("btn-export");
  btn.disabled = !(userStars >= 1 && saveFolder && sessionId);
}

function clearCardPreview() {
  const img = document.getElementById("card-preview-img");
  const loading = document.getElementById("card-preview-loading");
  img.hidden = true;
  img.removeAttribute("src");
  loading.hidden = false;
  loading.textContent = "カードを準備しています…";
}

async function refreshCardPreview() {
  if (!sessionId) return;
  clearCardPreview();
  const theme = document.getElementById("card-theme").value || "dark";
  try {
    const res = await fetch(`/api/session/${sessionId}/card`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_theme: theme }),
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
  } catch (err) {
    console.error(err);
    document.getElementById("card-preview-loading").textContent =
      "カードを表示できませんでした。講評が完了してからお試しください。";
  }
}

function prepareReflectScreen() {
  const note = document.getElementById("user-note").value.trim();
  const reflectNote = document.getElementById("reflect-note-edit");
  const reflectDisplay = document.getElementById("reflect-user-note");
  reflectNote.value = note;
  if (note) {
    reflectDisplay.textContent = `選ぶで添えた一言: ${note}`;
    reflectDisplay.hidden = false;
  } else {
    reflectDisplay.hidden = true;
    reflectDisplay.textContent = "";
  }
  refreshCardPreview();
}

document.getElementById("card-theme").addEventListener("change", () => {
  refreshCardPreview();
});

document.getElementById("btn-pick-folder").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/settings/pick-folder", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "フォルダの選択に失敗しました");
    }
    saveFolder = data.save_folder;
    updateSaveFolderDisplay();
  } catch (err) {
    console.error(err);
    alert("フォルダを選べませんでした。もう一度お試しください。");
  }
});

document.getElementById("btn-export").addEventListener("click", async () => {
  if (!sessionId || userStars < 1 || !saveFolder) return;
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
        user_note: document.getElementById("reflect-note-edit").value || "",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "書き出しに失敗しました");
    }
    alert(`書き出しました:\n${data.export_path}`);
    resetSession();
  } catch (err) {
    console.error(err);
    alert(err.message || "書き出しに失敗しました。");
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
loadSettings();
