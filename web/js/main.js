// Boot: wait for the Python bridge, apply the theme, start the viewer.
// M0 spike: shows a placeholder box until the real chat → OpenSCAD → STL pipeline lands.

import * as THREE from "three";
import { createViewer } from "./viewer.js";

const DEFAULT_THEME = { model_color: "#f2a65a", bg_color: "#f7f3ee", shadow_opacity: 0.18, spin_speed: 0.35 };

// pywebview creates `window.pywebview.api` before attaching its methods, then fires
// `pywebviewready` — so check for a real method, not just the object.
function bridgeReady() {
  if (typeof window.pywebview?.api?.ping === "function") return Promise.resolve(window.pywebview.api);
  return new Promise((resolve) =>
    window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true }));
}

async function boot() {
  const status = document.getElementById("statusbar");
  let theme = DEFAULT_THEME;
  let bootError = null;
  try {
    const api = await bridgeReady();
    const [pong, serverTheme] = await Promise.all([api.ping(), api.get_theme()]);
    theme = { ...DEFAULT_THEME, ...serverTheme };
    status.textContent = `Connected · v${pong.version}`;
  } catch (err) {
    status.textContent = "Couldn't reach the app backend";
    bootError = String(err?.message ?? err);
    console.error(err);
  }

  document.documentElement.style.setProperty("--bg", theme.bg_color);
  document.documentElement.style.setProperty("--accent", theme.model_color);

  const viewer = createViewer(document.getElementById("stage"), theme);
  // Placeholder part: 40 × 30 × 20 mm block, sitting on the bed.
  viewer.setGeometry(new THREE.BoxGeometry(40, 30, 20));

  document.getElementById("zoom").addEventListener("input", (e) => viewer.setZoom(+e.target.value));
  document.getElementById("angle").addEventListener("input", (e) => viewer.setElevation(+e.target.value));

  const hint = document.getElementById("viewer-hint");
  setTimeout(() => { hint.style.opacity = "0"; }, 6000);

  // Hook for scripts/smoke_ui.py (and later, project thumbnails).
  window.__pe = {
    viewer,
    state: () => ({ status: status.textContent, bootError, ...viewer.stats() }),
  };
}

boot();
