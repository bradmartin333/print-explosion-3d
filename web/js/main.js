// Boot and wiring: the Python bridge, the chat, the viewer and the Adjust panel.

import { createViewer } from "./viewer.js";
import { createChat } from "./chat.js";
import { renderParams } from "./params.js";
import { prepareImage, imageFiles } from "./images.js";

const DEFAULT_THEME = { model_color: "#f2a65a", bg_color: "#f7f3ee", shadow_opacity: 0.18, spin_speed: 0.35 };
const MAX_PHOTOS = 4;
const $ = (id) => document.getElementById(id);

// pywebview creates `window.pywebview.api` before attaching its methods, then fires
// `pywebviewready` — so check for a real method, not just the object.
function bridgeReady() {
  if (typeof window.pywebview?.api?.ping === "function") return Promise.resolve(window.pywebview.api);
  return new Promise((resolve) =>
    window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true }));
}

const state = { api: null, project: null, busy: false, stale: false, attachments: [], pending: null, edits: {} };
let viewer, chat, editTimer;
const handlers = {};
window.peEvent = (name, data) => handlers[name]?.(data); // Python → page

// ---- small UI helpers ----------------------------------------------------------------------

function refreshButtons() {
  const hasModel = !!viewer?.hasModel;
  $("generate").disabled = state.busy || !state.stale;
  $("export").disabled = state.busy || !hasModel;
  $("bambu").disabled = state.busy || !hasModel;
  $("stale").hidden = !state.stale;
  $("viewer-empty").hidden = hasModel;
  $("delete-project").disabled = state.busy || !state.project;
}

// The backend sends short stage names. The chat bubble and the preview's pill say different
// things about the same stage, so she never reads the same words twice.
const STAGES = {
  "Thinking…": { chat: "Thinking about your idea…", pill: "Designing…" },
  "Fixing a small problem…": { chat: "Fixing a small problem…", pill: "Adjusting…" },
  "Building…": { chat: "Putting the pieces together…", pill: "Shaping the model…" },
};
const stage = (msg) => STAGES[msg] ?? { chat: msg, pill: msg };

function setBusy(on, text = "Working…") {
  state.busy = on;
  $("busy").hidden = !on;
  $("busy-text").textContent = text;
  for (const id of ["send", "new-project", "project-switch"]) $(id).disabled = on;
  refreshButtons();
}

function setCost(text) { $("cost").textContent = text || ""; }

function setStale(on) { state.stale = on; refreshButtons(); }
function setSaveStatus(text) { $("save-status").textContent = text; }

async function refreshModel() {
  const stl = await state.api.get_stl();
  if (stl) viewer.loadStl(stl); else viewer.clear();
  refreshButtons();
}

async function flushEdits() {
  clearTimeout(editTimer);
  const edits = state.edits;
  if (!Object.keys(edits).length) return;
  state.edits = {};
  const res = await state.api.set_params(edits);
  if (res.saved) { setSaveStatus(res.status); setStale(true); }
  else if (res.error) chat.addInfo(res.error);
}

function onParamEdit(name, value) {
  state.edits[name] = value;
  clearTimeout(editTimer);
  editTimer = setTimeout(flushEdits, 250);
}

const showParams = (sections) => renderParams($("param-list"), sections, onParamEdit);

async function renderSwitcher() {
  const projects = await state.api.list_projects();
  const thumbs = await state.api.project_thumbs();
  const menu = $("project-menu");
  menu.replaceChildren();
  for (const p of projects) {
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", String(p.folder === state.project?.folder));
    const img = document.createElement("img");
    img.className = "thumb-img";
    img.alt = "";
    if (thumbs[p.folder]) img.src = thumbs[p.folder]; else img.style.visibility = "hidden";
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = p.name;
    li.append(img, nm);
    li.addEventListener("click", async () => {
      menu.hidden = true;
      if (p.folder === state.project?.folder) return;
      const opened = await state.api.open_project(p.folder);
      if (opened) await showProject(opened); else await renderSwitcher();
    });
    menu.append(li);
  }
  $("project-name").textContent = state.project ? state.project.name : "New project";
  const mine = state.project && thumbs[state.project.folder];
  $("project-thumb").hidden = !mine;
  if (mine) $("project-thumb").src = mine;
}

// A small picture of the model for the project list (taken after every build).
function saveThumbnail() {
  if (!viewer?.hasModel || !state.project) return;
  try {
    const src = new Image();
    src.onload = async () => {
      const size = 160, scale = Math.min(1, size / Math.max(src.width, src.height));
      const c = document.createElement("canvas");
      c.width = Math.round(src.width * scale); c.height = Math.round(src.height * scale);
      c.getContext("2d").drawImage(src, 0, 0, c.width, c.height);
      if (await state.api.save_thumbnail(c.toDataURL("image/png"))) renderSwitcher();
    };
    src.src = viewer.snapshot({ standard: true });
  } catch (err) { console.error(err); }
}

async function showProject(p) {
  state.project = p;
  state.edits = {};
  state.stale = false;
  chat.show(p?.chat?.display);
  showParams(p?.params);
  setSaveStatus(p ? "All changes saved" : "Not saved yet");
  await renderSwitcher();
  await refreshModel();
  $("prompt").focus();
}

// ---- photos --------------------------------------------------------------------------------

function renderAttachments() {
  const box = $("attachments");
  box.hidden = !state.attachments.length;
  box.replaceChildren();
  state.attachments.forEach((a, i) => {
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    const img = document.createElement("img");
    img.src = a.preview;
    img.alt = "A photo ready to send";
    const x = document.createElement("button");
    x.type = "button";
    x.textContent = "×";
    x.title = "Remove this photo";
    x.addEventListener("click", () => { state.attachments.splice(i, 1); renderAttachments(); });
    thumb.append(img, x);
    box.append(thumb);
  });
}

async function addFiles(files) {
  for (const f of imageFiles(files).slice(0, MAX_PHOTOS - state.attachments.length)) {
    try { state.attachments.push(await prepareImage(f)); }
    catch { chat.addInfo("I couldn't read that photo. Could you try a different one?"); }
  }
  renderAttachments();
}

// ---- sending -------------------------------------------------------------------------------

async function send(text) {
  text = text.trim();
  if (state.busy || (!text && !state.attachments.length)) return;
  await flushEdits(); // her latest tweaks must be in the file before the AI looks at it
  const photos = state.attachments;
  const res = await state.api.send_message(text, photos.map(({ name, data }) => ({ name, data })));
  if (res.command) {               // handled locally: "start a new project", "open my bird feeder"
    $("prompt").value = "";
    await showProject(res.project);
    return;
  }
  if (!res.started) {
    if (res.error) chat.addInfo(res.error);
    return;
  }
  state.attachments = [];
  renderAttachments();
  $("prompt").value = "";
  if (!state.project) state.project = res.project; // the first message creates the project
  chat.addUser(text, photos.map((p) => p.preview));
  state.pending = chat.pending(stage("Thinking…").chat);
  setBusy(true, stage("Thinking…").pill);
}

handlers.status = (msg) => {
  const s = stage(msg);
  state.pending?.status(s.chat);
  $("busy-text").textContent = s.pill;
};
handlers.text = (t) => state.pending?.text(t);

handlers.turn_done = async (r) => {
  state.pending?.remove();
  state.pending = null;
  if (r.error) chat.addInfo(r.error);
  else chat.addAssistant(r.text || (r.changed ? "Here's your design." : ""), { chip: r.changed, choices: r.choices });
  state.project = { ...(state.project || {}), ...r.project };
  if (r.changed) {
    showParams(r.params);
    state.edits = {};
    state.stale = false;
    setSaveStatus("All changes saved");
    await refreshModel();
    saveThumbnail();
  }
  setCost(r.cost);
  await renderSwitcher();
  setBusy(false);
  $("prompt").focus();
};

handlers.built = async (r) => {
  if (r.error) chat.addInfo(r.error);
  showParams(r.params);
  setSaveStatus(r.status);
  state.stale = false; // on a failed build the file went back to match the model on screen
  await refreshModel();
  if (!r.error) saveThumbnail();
  setBusy(false);
};

// ---- boot ----------------------------------------------------------------------------------

function wireComposer() {
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send($("prompt").value); });
  $("prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("prompt").value); }
  });
  $("attach").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
  document.addEventListener("paste", (e) => {
    const files = imageFiles(e.clipboardData?.files);
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  let depth = 0;
  const panel = $("chat-panel");
  panel.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; $("drop-hint").hidden = false; });
  panel.addEventListener("dragover", (e) => e.preventDefault());
  panel.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("drop-hint").hidden = true; } });
  panel.addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0; $("drop-hint").hidden = true;
    addFiles(e.dataTransfer?.files);
  });
}

function wireProjects() {
  $("project-switch").addEventListener("click", (e) => {
    e.stopPropagation();
    $("project-menu").hidden = !$("project-menu").hidden;
  });
  document.addEventListener("click", () => { $("project-menu").hidden = true; });
  $("new-project").addEventListener("click", async () => {
    const p = await state.api.new_project();
    if (p) await showProject(p);
  });
  $("delete-project").addEventListener("click", () => {
    if (!state.project) return;
    $("confirm-text").textContent = `Delete "${state.project.name}"? It goes to the Trash, so you can still get it back.`;
    $("confirm").hidden = false;
  });
  $("confirm-no").addEventListener("click", () => { $("confirm").hidden = true; });
  $("confirm-yes").addEventListener("click", async () => {
    $("confirm").hidden = true;
    if (!state.project) return;
    if (!(await state.api.delete_project(state.project.folder))) {
      chat.addInfo("I couldn't delete that one. Please try again.");
      return;
    }
    const next = (await state.api.list_projects())[0];
    await showProject(next ? await state.api.open_project(next.folder) : null);
  });
}

function wireActions() {
  $("generate").addEventListener("click", async () => {
    await flushEdits();
    const res = await state.api.generate();
    if (res.started) setBusy(true, "Updating the model…");
    else if (res.error) chat.addInfo(res.error);
  });
  $("export").addEventListener("click", async () => {
    const res = await state.api.export_stl();
    if (res.error) chat.addInfo(res.error);
    else if (res.saved) setSaveStatus(`Saved ${res.name}`);
  });
  $("bambu").addEventListener("click", async () => {
    const res = await state.api.open_in_bambu();
    if (res.error) chat.addInfo(res.error);
  });
}

function wireUpdate() {
  const banner = $("update-banner");
  $("update-later").addEventListener("click", () => { banner.hidden = true; });
  $("update-now").addEventListener("click", async () => {
    $("update-now").disabled = true;
    $("update-title").textContent = "Updating… the app will restart in a moment.";
    $("update-notes").textContent = "";
    const res = await state.api.apply_update();
    if (!res.ok) {
      $("update-title").textContent = res.error;
      $("update-now").disabled = false;
    }
  });
}

async function checkForUpdate() {
  try {
    const info = await state.api.check_update();
    if (!info.available) return;
    // Notes are plain text from CHANGELOG.md: bullets become lines.
    $("update-notes").textContent = info.notes.replace(/^\s*[-*]\s+/gm, "• ");
    $("update-banner").hidden = false;
  } catch (err) {
    console.error(err); // an update check must never bother her
  }
}

async function boot() {
  const status = $("statusbar");
  let theme = DEFAULT_THEME;
  let first = { project: null, has_key: true };
  let bootError = null;
  try {
    state.api = await bridgeReady();
    first = await state.api.boot();
    setCost(first.cost);
    theme = { ...DEFAULT_THEME, ...first.theme };
    status.textContent = `Connected · v${first.version}`;
  } catch (err) {
    status.textContent = "Couldn't reach the app backend";
    bootError = String(err?.message ?? err);
    console.error(err);
  }
  document.documentElement.style.setProperty("--bg", theme.bg_color);
  document.documentElement.style.setProperty("--accent", theme.model_color);

  viewer = createViewer($("stage"), theme, { onElevation: (deg) => { $("angle").value = deg; } });
  chat = createChat($("messages"), { onChoice: (c) => send(c) });
  $("zoom").addEventListener("input", (e) => viewer.setZoom(+e.target.value));
  $("angle").addEventListener("input", (e) => viewer.setElevation(+e.target.value));
  setTimeout(() => { $("viewer-hint").style.opacity = "0"; }, 6000);
  wireComposer();
  wireProjects();
  wireActions();
  wireUpdate();

  if (!bootError) {
    await showProject(first.project);
    checkForUpdate(); // in the background; the banner appears if something is ready
    if (!first.has_key) chat.addInfo("To chat with me, this app needs its AI key. Ask Brad to set it up.");
  }

  // Hook for scripts/smoke_ui.py and scripts/screenshots.py.
  window.__pe = {
    viewer,
    thumbnail: saveThumbnail,
    state: () => ({ status: status.textContent, bootError, ...viewer.stats() }),
  };
}

boot();
