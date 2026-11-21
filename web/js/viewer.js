// 3D preview: Z-up (matches OpenSCAD and the print bed), soft ground shadow, no grid.
// The model spins slowly on its own; clicking it pauses/resumes. Zoom and angle come from
// plain sliders so nobody has to learn CAD mouse controls.

import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

export function createViewer(container, theme) {
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

  const view = { zoom: 1, elevationDeg: 28, spinning: true, radius: 50, center: new THREE.Vector3() };

  function setGeometry(geometry) {
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

  renderer.domElement.addEventListener("click", () => { view.spinning = !view.spinning; });

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
    setElevation(deg) { view.elevationDeg = deg; placeCamera(); },
    setSpinning(on) { view.spinning = on; },
    get spinning() { return view.spinning; },
    // PNG data URL of the current view (render first: the drawing buffer isn't preserved).
    snapshot() { renderer.render(scene, camera); return renderer.domElement.toDataURL("image/png"); },
    stats() {
      return { frames, triangles: renderer.info.render.triangles, width: container.clientWidth, height: container.clientHeight };
    },
  };
}
