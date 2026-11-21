// 3D preview: Z-up (matches OpenSCAD and the print bed), soft ground shadow, no grid.
// The model spins slowly on its own; clicking it pauses/resumes, and dragging turns and tilts it
// (left/right turns, up/down tilts). Zoom and angle also come from plain sliders. The angle goes
// below the ground so she can look at the underside; the ground is one-sided, so it disappears
// from below.

import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

export const DEFAULT_ELEVATION = 28;
const MAX_ELEVATION = 85;
const DRAG_THRESHOLD_PX = 4; // smaller moves are still a click
const DRAG_DEG_PER_PX = 0.4;

export function createViewer(container, theme, { onElevation } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(theme.bg_color);

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
  camera.up.set(0, 0, 1);

  scene.add(new THREE.HemisphereLight(0xffffff, 0xd8cfc4, 1.6));
  const under = new THREE.DirectionalLight(0xffffff, 0.5); // so the underside isn't flat
  under.position.set(0.3, 0.6, -1);
  scene.add(under);
  const sun = new THREE.DirectionalLight(0xffffff, 1.8);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.radius = 6;
  scene.add(sun, sun.target);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.ShadowMaterial({ opacity: theme.shadow_opacity }),
  );
  ground.receiveShadow = true;
  scene.add(ground);

  const spinner = new THREE.Group(); // rotates around Z; the mesh sits inside it
  scene.add(spinner);
  const material = new THREE.MeshStandardMaterial({
    color: theme.model_color, roughness: 0.55, metalness: 0.0,
  });
  let mesh = null;

  const view = {
    zoom: 1, elevationDeg: DEFAULT_ELEVATION, spinning: true, radius: 50, center: new THREE.Vector3(),
  };

  let loads = 0; // models shown so far, so scripts can tell a new model from the last one

  function setGeometry(geometry) {
    loads += 1;
    if (mesh) { spinner.remove(mesh); mesh.geometry.dispose(); }
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const center = box.getCenter(new THREE.Vector3());
    // Center on the spin axis and rest exactly on the ground, whatever the source coordinates.
    geometry.translate(-center.x, -center.y, -box.min.z);
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();

    mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    spinner.add(mesh);

    const size = box.getSize(new THREE.Vector3());
    view.radius = Math.max(geometry.boundingSphere.radius, 1);
    view.center.set(0, 0, size.z / 2);
    ground.scale.set(view.radius * 12, view.radius * 12, 1);

    const s = view.radius * 3;
    Object.assign(sun.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 0.1, far: s * 6 });
    sun.shadow.camera.updateProjectionMatrix();
    sun.position.set(view.radius * 1.5, -view.radius * 2, view.radius * 4);
    placeCamera();
  }

  const stlLoader = new STLLoader();

  // Show a model sent over the bridge as base64 binary STL (as OpenSCAD writes it).
  function loadStl(base64) {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    setGeometry(stlLoader.parse(bytes.buffer));
  }

  function clear() {
    if (!mesh) return;
    spinner.remove(mesh);
    mesh.geometry.dispose();
    mesh = null;
  }

  function placeCamera() {
    // Fit the bounding sphere (the spin sweeps it) inside the narrower of the two FOVs.
    const vFov = THREE.MathUtils.degToRad(camera.fov);
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
    const fitDistance = view.radius / Math.sin(Math.min(vFov, hFov) / 2);
    const distance = fitDistance * 1.5 / view.zoom;
    const elev = THREE.MathUtils.degToRad(view.elevationDeg);
    camera.position.set(0, -distance * Math.cos(elev), view.center.z + distance * Math.sin(elev));
    camera.lookAt(view.center);
  }

  function resize() {
    const { clientWidth: w, clientHeight: h } = container;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = `${w}px`;
    renderer.domElement.style.height = `${h}px`;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    placeCamera();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  function setElevation(deg) {
    view.elevationDeg = THREE.MathUtils.clamp(deg, -MAX_ELEVATION, MAX_ELEVATION);
    placeCamera();
  }

  // A click toggles spinning; a drag turns and tilts the model and leaves it paused there.
  const canvas = renderer.domElement;
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.ctrlKey) return; // ctrl-click is a right-click on a Mac
    drag = { x: e.clientX, y: e.clientY, moved: false };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if ((e.buttons & 1) === 0) { cancelDrag(); return; } // the button-up never reached us
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
    if (!drag.moved) { drag.moved = true; view.spinning = false; canvas.classList.add("dragging"); }
    drag.x = e.clientX;
    drag.y = e.clientY;
    spinner.rotation.z += THREE.MathUtils.degToRad(dx * DRAG_DEG_PER_PX);
    setElevation(view.elevationDeg + dy * DRAG_DEG_PER_PX);
    onElevation?.(view.elevationDeg);
  });
  const endDrag = () => {
    if (drag && !drag.moved) view.spinning = !view.spinning;
    drag = null;
    canvas.classList.remove("dragging");
  };
  // A drag that ends without a proper button-up (focus lost, a menu popped up) leaves the model
  // where it is: no spin toggle.
  const cancelDrag = () => { if (drag) drag.moved = true; endDrag(); };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", cancelDrag);
  canvas.addEventListener("lostpointercapture", cancelDrag); // after pointerup, drag is already null

  const clock = new THREE.Clock();
  let frames = 0;
  renderer.setAnimationLoop(() => {
    const dt = clock.getDelta();
    if (view.spinning) spinner.rotation.z += theme.spin_speed * dt;
    renderer.render(scene, camera);
    frames += 1;
  });

  return {
    setGeometry,
    loadStl,
    clear,
    get hasModel() { return mesh !== null; },
    setZoom(z) { view.zoom = z; placeCamera(); },
    setElevation,
    get elevation() { return view.elevationDeg; },
    setSpinning(on) { view.spinning = on; },
    setTurn(deg) { spinner.rotation.z = THREE.MathUtils.degToRad(deg); },
    get spinning() { return view.spinning; },
    // PNG data URL of the current view (render first: the drawing buffer isn't preserved).
    // `standard` uses the default zoom and angle, so a project picture never shows the underside.
    snapshot({ standard = false } = {}) {
      const saved = { zoom: view.zoom, elevationDeg: view.elevationDeg };
      if (standard) Object.assign(view, { zoom: 1, elevationDeg: DEFAULT_ELEVATION });
      placeCamera();
      renderer.render(scene, camera);
      const url = renderer.domElement.toDataURL("image/png");
      Object.assign(view, saved);
      placeCamera();
      return url;
    },
    stats() {
      return { frames, loads, triangles: renderer.info.render.triangles, width: container.clientWidth, height: container.clientHeight };
    },
  };
}
