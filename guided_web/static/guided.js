const screens = {
  choose: document.getElementById("screen-choose"),
  read: document.getElementById("screen-read"),
  reflect: document.getElementById("screen-reflect"),
};

let sessionId = null;
let userStars = 0;
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
  document.getElementById("btn-export").disabled = true;
  updateStarButtons();
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
  if (activePreviewUrl()) {
    setPhotoPreview(activePreviewUrl());
  }
  showScreen("read");
  document.getElementById("read-skeleton").hidden = false;
  document.getElementById("read-content").hidden = true;
});

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
  showScreen("reflect");
});

document.querySelectorAll("#user-stars button").forEach((btn) => {
  btn.addEventListener("click", () => {
    userStars = Number(btn.dataset.value);
    updateStarButtons();
    document.getElementById("btn-export").disabled = userStars < 1;
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
