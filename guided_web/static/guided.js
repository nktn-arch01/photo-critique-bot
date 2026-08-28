const screens = {
  choose: document.getElementById("screen-choose"),
  read: document.getElementById("screen-read"),
  reflect: document.getElementById("screen-reflect"),
};

let sessionId = null;
let userStars = 0;

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.hidden = key !== name;
    el.classList.toggle("active", key === name);
  });
  document.querySelectorAll(".screen-nav span").forEach((el) => {
    el.classList.toggle("active", el.dataset.screen === name);
  });
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
  const p = data.api_parameters;
  el.hidden = false;
  el.textContent = JSON.stringify(p, null, 2);
  document.getElementById("btn-speak").disabled = false;
}

document.getElementById("pick-file").addEventListener("click", () => {
  document.getElementById("file-input").click();
});

document.getElementById("file-input").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const data = await uploadPhoto(file);
  sessionId = data.session_id;
  renderParams(data);
});

document.getElementById("btn-speak").addEventListener("click", () => {
  showScreen("read");
  document.getElementById("read-skeleton").hidden = false;
  document.getElementById("read-content").hidden = true;
});

document.getElementById("btn-reset").addEventListener("click", () => {
  sessionId = null;
  userStars = 0;
  document.getElementById("params-preview").hidden = true;
  document.getElementById("btn-speak").disabled = true;
  document.getElementById("file-input").value = "";
  updateStarButtons();
  showScreen("choose");
});

document.getElementById("btn-again").addEventListener("click", () => {
  document.getElementById("btn-reset").click();
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
