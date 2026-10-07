# -*- coding: utf-8 -*-
"""
viewer_3d.py
============

Maquette 3D d'un projet, reconstruite à partir de ses éléments de
construction (murs percés de leurs ouvertures, dalles et trémies, poteaux,
poutres, fondations). La scène est calculée côté serveur
(project.project._construction_scene_3d) et dessinée avec three.js, embarqué
dans le module (static/lib/three) : aucune dépendance réseau.

Route : GET /construction/3d/<int:project_id>
"""

import html as html_lib

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

LIB = "/miro_construction_project/static/lib/three"


class Construction3DViewerController(http.Controller):

    @http.route("/construction/3d/<int:project_id>", type="http", auth="user")
    def viewer_3d(self, project_id, **kwargs):
        project = request.env["project.project"].browse(project_id)
        try:
            if not project.exists():
                return request.not_found()
            project.check_access_rights("read")
            project.check_access_rule("read")
        except AccessError:
            return request.not_found()

        scene = project._construction_scene_3d()
        page = PAGE.replace("__TITLE__", html_lib.escape(project.name or "")) \
                   .replace("__LIB__", LIB) \
                   .replace("__SCENE__", project._scene_json(scene))
        return request.make_response(
            page, headers=[("Content-Type", "text/html; charset=utf-8")])


PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Maquette 3D — __TITLE__</title>
<style>
  :root { --ink:#1f2933; --muted:#616e7c; --line:#d9e2ec; --bg:#f5f7fa; --panel:#ffffff; --accent:#1565c0; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); }
  #app { display:grid; grid-template-columns: 280px 1fr; height:100%; }
  aside { background:var(--panel); border-right:1px solid var(--line); overflow:auto; padding:16px; }
  h1 { font-size:16px; margin:0 0 2px; }
  .sub { color:var(--muted); font-size:12px; margin-bottom:14px; }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:16px 0 8px; }
  label.row { display:flex; align-items:center; gap:8px; font-size:13px; padding:3px 0; cursor:pointer; }
  .sw { width:14px; height:14px; border-radius:3px; flex:none; border:1px solid rgba(0,0,0,.15); }
  .count { margin-left:auto; color:var(--muted); font-size:12px; }
  .seg { display:flex; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
  .seg button { flex:1; border:0; background:#fff; padding:6px; font-size:12px; cursor:pointer; color:var(--ink); }
  .seg button.on { background:var(--accent); color:#fff; }
  button.plain { width:100%; border:1px solid var(--line); background:#fff; border-radius:6px; padding:7px; font-size:12px; cursor:pointer; margin-top:6px; }
  #stage { position:relative; }
  canvas { display:block; }
  #info { position:absolute; right:14px; top:14px; width:290px; background:var(--panel); border:1px solid var(--line);
          border-radius:8px; box-shadow:0 4px 16px rgba(0,0,0,.08); padding:12px 14px; font-size:13px; display:none; }
  #info h3 { margin:0 0 6px; font-size:15px; }
  #info table { width:100%; border-collapse:collapse; }
  #info td { padding:3px 0; vertical-align:top; }
  #info td:first-child { color:var(--muted); width:42%; }
  #info a { display:inline-block; margin-top:8px; color:var(--accent); font-weight:600; text-decoration:none; }
  .bar { height:6px; background:var(--line); border-radius:3px; overflow:hidden; margin:6px 0 2px; }
  .bar span { display:block; height:100%; background:#2e7d32; }
  .tag { display:inline-block; font-size:11px; padding:1px 6px; border-radius:10px; background:#fff3e0; color:#e65100; margin-left:6px; }
  #empty { position:absolute; inset:0; display:none; align-items:center; justify-content:center; color:var(--muted); font-size:14px; text-align:center; padding:24px; }
  .hint { color:var(--muted); font-size:11px; margin-top:14px; line-height:1.5; }
  @media (max-width: 720px) { #app { grid-template-columns: 1fr; grid-template-rows: auto 1fr; } aside { max-height:40vh; } }
</style>
<script type="importmap">{"imports": {"three": "__LIB__/three.module.min.js"}}</script>
</head>
<body>
<div id="app">
  <aside>
    <h1>Maquette 3D</h1>
    <div class="sub">__TITLE__ — <span id="total"></span></div>

    <h2>Ouvrages</h2>
    <div id="types"></div>

    <h2>Niveaux</h2>
    <div id="levels"></div>

    <h2>Couleur</h2>
    <div class="seg"><button data-color="type" class="on">Par type</button><button data-color="progress">Avancement</button></div>
    <div id="progressLegend" style="display:none;font-size:11px;color:var(--muted);margin-top:6px">
      <span class="sw" style="display:inline-block;vertical-align:middle;background:#c62828"></span> 0 %
      &nbsp;<span class="sw" style="display:inline-block;vertical-align:middle;background:#f9a825"></span> 50 %
      &nbsp;<span class="sw" style="display:inline-block;vertical-align:middle;background:#2e7d32"></span> 100 %
    </div>

    <h2>Affichage</h2>
    <label class="row"><input type="checkbox" id="xray"/> Murs transparents</label>
    <label class="row"><input type="checkbox" id="explode"/> Écarter les niveaux</label>
    <button class="plain" id="reset">Recentrer la vue</button>

    <div class="hint">
      Glisser : tourner · Clic droit : déplacer · Molette : zoom<br/>
      Clic sur un ouvrage : sa fiche.<br/>
      <span class="tag" style="margin:0">supposé</span> cote non relevée sur les plans, dessinée à une valeur courante.
    </div>
  </aside>
  <div id="stage">
    <div id="info"></div>
    <div id="empty">Aucun élément de construction représentable dans ce projet.<br/>
      Analysez puis validez les plans d'exécution (coffrage, fondation, détail) et générez les éléments.</div>
  </div>
</div>

<script type="module">
import * as THREE from "three";
import { OrbitControls } from "__LIB__/OrbitControls.js";

const SCENE = __SCENE__;
const COLORS = { poteau:"#6a1b9a", poutre:"#00838f", dalle:"#8d6e63", mur:"#b0bec5",
                 semelle:"#1565c0", semelle_filante:"#2e7d32", longrine:"#e65100" };
const OPENING_COLORS = { window:"#64b5f6", french_window:"#64b5f6", door:"#8d6e63",
                         garage_door:"#795548", bay:"#ffffff", unknown:"#ffb74d" };
const stage = document.getElementById("stage");
const items = SCENE.items;
document.getElementById("total").textContent = items.length + " élément(s)";
if (!items.length) document.getElementById("empty").style.display = "flex";

// ---------- Rendu ----------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.shadowMap.enabled = true;
stage.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color("#eef2f6");
const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 2000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0005;
sun.shadow.normalBias = 0.03;
scene.add(sun);

// Repère : x plan -> x, y plan -> -z, altitude -> y
const P = (x, y, z) => new THREE.Vector3(x, z, -y);

function material(color, opts = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: .85, metalness: 0,
    transparent: !!opts.transparent, opacity: opts.opacity ?? 1, side: THREE.DoubleSide,
    // Murs et dalles enrobent poteaux et poutres (faces confondues) : on les
    // repousse d'un cheveu au rendu pour que l'ossature reste nette.
    polygonOffset: !!opts.behind, polygonOffsetFactor: 1, polygonOffsetUnits: 2 });
}

function addEdges(mesh) {
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x37474f, transparent: true, opacity: .55 }));
  mesh.add(edges);
}

function boxMesh(s, mat) {
  const h = s.z1 - s.z0;
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(s.lx, h, s.ly), mat);
  mesh.position.copy(P(s.cx, s.cy, s.z0 + h / 2));
  return mesh;
}

function slabMesh(s, mat) {
  const shape = new THREE.Shape(s.outline.map(([x, y]) => new THREE.Vector2(x, y)));
  for (const hole of s.holes) shape.holes.push(new THREE.Path(hole.map(([x, y]) => new THREE.Vector2(x, y))));
  const geo = new THREE.ExtrudeGeometry(shape, { depth: s.z1 - s.z0, bevelEnabled: false });
  geo.rotateX(-Math.PI / 2);          // (x, y, z) -> (x, z, -y) : extrusion vers le haut
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.y = s.z0;
  return mesh;
}

function wallGroup(s, mat, it) {
  // Mur dans son plan local : x le long de l'axe, y vers le haut, percé de ses ouvertures
  const L = Math.hypot(s.x2 - s.x1, s.y2 - s.y1), H = s.z1 - s.z0;
  const shape = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(L, 0),
                                 new THREE.Vector2(L, H), new THREE.Vector2(0, H)]);
  const panes = [];
  for (const o of s.openings) {
    const x0 = Math.max(o.offset, 0.02), x1 = Math.min(o.offset + o.width, L - 0.02);
    const y0 = Math.max(o.sill, 0), y1 = Math.min(o.sill + o.height, H - 0.02);
    if (x1 - x0 < 0.05 || y1 - y0 < 0.05) continue;
    // Une ouverture posée au sol coupe le bas du mur : on garde 1 mm pour
    // que le contour reste un trou valide.
    const yb = Math.max(y0, 0.001);
    shape.holes.push(new THREE.Path([new THREE.Vector2(x0, yb), new THREE.Vector2(x1, yb),
                                     new THREE.Vector2(x1, y1), new THREE.Vector2(x0, y1)]));
    panes.push({ x0, x1, y0: yb, y1, o });
  }
  const geo = new THREE.ExtrudeGeometry(shape, { depth: s.thickness, bevelEnabled: false });
  geo.translate(0, 0, -s.thickness / 2);
  const group = new THREE.Group();
  const wall = new THREE.Mesh(geo, mat);
  wall.userData.item = it;
  group.add(wall);
  for (const p of panes) {
    const kind = p.o.known ? p.o.kind : "unknown";
    const glass = ["window", "french_window"].includes(kind);
    const pane = new THREE.Mesh(
      new THREE.BoxGeometry(p.x1 - p.x0, p.y1 - p.y0, glass ? 0.02 : 0.04),
      material(OPENING_COLORS[kind] || OPENING_COLORS.unknown,
               { transparent: true, opacity: kind === "bay" ? 0.15 : glass ? 0.45 : 0.85 }));
    pane.position.set((p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2, 0);
    pane.userData.opening = p.o;
    pane.userData.item = it;
    group.add(pane);
  }
  group.position.copy(P(s.x1, s.y1, s.z0));
  group.rotation.y = Math.atan2(s.y2 - s.y1, s.x2 - s.x1);
  return group;
}

// ---------- Construction de la scène ----------
const objects = [];      // { it, obj, mats }
const bounds = new THREE.Box3();
for (const it of items) {
  const color = COLORS[it.type] || "#78909c";
  const mat = material(color, { behind: ["mur", "dalle"].includes(it.type) });
  let obj;
  if (it.shape.kind === "box") obj = boxMesh(it.shape, mat);
  else if (it.shape.kind === "slab") obj = slabMesh(it.shape, mat);
  else if (it.shape.kind === "wall") obj = wallGroup(it.shape, mat, it);
  if (!obj) continue;
  obj.traverse((o) => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; o.userData.item = it; } });
  if (obj.isMesh) addEdges(obj); else obj.children.filter((c) => c.material === mat).forEach(addEdges);
  obj.userData.baseY = obj.position.y;
  scene.add(obj);
  objects.push({ it, obj, mat });
  bounds.expandByObject(obj);
}

// Sol
if (!bounds.isEmpty()) {
  const size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
  const span = Math.max(size.x, size.z) * 1.6 + 4;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(span, span),
    new THREE.MeshStandardMaterial({ color: "#dfe7ec", roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(center.x, Math.min(bounds.min.y, 0) - 0.01, center.z);
  ground.receiveShadow = true;
  scene.add(ground);
  const grid = new THREE.GridHelper(span, Math.round(span), 0xb0bec5, 0xd5dde3);
  grid.position.copy(ground.position).setY(ground.position.y + 0.005);
  scene.add(grid);
  sun.position.set(center.x + span * .4, size.y + span * .6, center.z + span * .3);
  sun.target.position.copy(center);
  scene.add(sun.target);
  const d = span / 2;
  Object.assign(sun.shadow.camera, { left: -d, right: d, top: d, bottom: -d, far: span * 3 });
  sun.shadow.camera.updateProjectionMatrix();
}

function resetView() {
  if (bounds.isEmpty()) { camera.position.set(10, 10, 10); controls.target.set(0, 0, 0); return; }
  const size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
  const r = Math.max(size.x, size.y, size.z);
  camera.position.set(center.x + r * 0.9, center.y + r * 0.8, center.z + r * 1.1);
  controls.target.copy(center);
  controls.update();
}
resetView();

// ---------- Panneau latéral ----------
const state = { types: {}, levels: {}, color: "type", xray: false, explode: false };
const typeNames = SCENE.types || {};
function checkboxList(containerId, values, store, colorOf, labelOf) {
  const box = document.getElementById(containerId);
  for (const v of values) {
    store[v] = true;
    const n = items.filter((i) => (containerId === "types" ? i.type : i.level) === v).length;
    const row = document.createElement("label");
    row.className = "row";
    row.innerHTML = `<input type="checkbox" checked/>${colorOf ? `<span class="sw" style="background:${colorOf(v)}"></span>` : ""}<span></span><span class="count">${n}</span>`;
    row.querySelector("span:not(.sw):not(.count)").textContent = labelOf(v);
    row.querySelector("input").addEventListener("change", (e) => { store[v] = e.target.checked; refresh(); });
    box.appendChild(row);
  }
}
checkboxList("types", [...new Set(items.map((i) => i.type))], state.types,
             (t) => COLORS[t] || "#78909c", (t) => typeNames[t] || t);
const levelValues = [...new Set(items.map((i) => i.level || ""))];
checkboxList("levels", levelValues, state.levels, null, (l) => l || "Sans niveau");
const levelOrder = [...new Set(items.slice().sort((a, b) => objMinY(a) - objMinY(b)).map((i) => i.level || ""))];
function objMinY(it) { return it.shape.z0; }

function progressColor(p) {
  const c = new THREE.Color();
  return p < 50 ? c.set("#c62828").lerp(new THREE.Color("#f9a825"), p / 50)
                : c.set("#f9a825").lerp(new THREE.Color("#2e7d32"), (p - 50) / 50);
}

function refresh() {
  for (const { it, obj, mat } of objects) {
    obj.visible = state.types[it.type] && state.levels[it.level || ""];
    mat.color.set(state.color === "progress" ? progressColor(it.progress) : (COLORS[it.type] || "#78909c"));
    const see = state.xray && it.type === "mur";
    mat.transparent = see; mat.opacity = see ? 0.25 : 1; mat.depthWrite = !see;
    const rank = Math.max(levelOrder.indexOf(it.level || ""), 0);
    obj.position.y = obj.userData.baseY + (state.explode ? rank * 2.5 : 0);
  }
}
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
  state.color = b.dataset.color;
  document.getElementById("progressLegend").style.display = state.color === "progress" ? "block" : "none";
  refresh();
}));
document.getElementById("xray").addEventListener("change", (e) => { state.xray = e.target.checked; refresh(); });
document.getElementById("explode").addEventListener("change", (e) => { state.explode = e.target.checked; refresh(); });
document.getElementById("reset").addEventListener("click", resetView);
refresh();

// ---------- Sélection ----------
const info = document.getElementById("info");
const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
let selected = null, downAt = null;
renderer.domElement.addEventListener("pointerdown", (e) => { downAt = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return;
  const r = renderer.domElement.getBoundingClientRect();
  pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(objects.filter((o) => o.obj.visible).map((o) => o.obj), true)
                       .find((h) => h.object.userData.item);
  select(hit ? hit.object : null);
});

function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c])); }
function select(mesh) {
  if (selected) selected.material.emissive?.set(0x000000);
  selected = mesh;
  if (!mesh) { info.style.display = "none"; return; }
  mesh.material.emissive?.set(0x334455);
  const it = mesh.userData.item, o = mesh.userData.opening;
  let rows = Object.entries(it.info).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("");
  let title = esc(it.key);
  if (o) {
    title = esc(o.label || "Ouverture") + ` <span style="color:var(--muted);font-size:12px">dans ${esc(it.key)}</span>`;
    rows = `<tr><td>Largeur</td><td>${o.width.toFixed(2)} m</td></tr>
            <tr><td>Hauteur</td><td>${o.known ? o.height.toFixed(2) + " m" : "inconnue"}</td></tr>
            <tr><td>Allège</td><td>${o.known ? o.sill.toFixed(2) + " m" : "—"}</td></tr>` + rows;
  }
  info.innerHTML = `<h3>${title}${it.assumed || (o && !o.known) ? '<span class="tag">supposé</span>' : ""}</h3>
    <div class="bar"><span style="width:${Math.min(it.progress, 100)}%"></span></div>
    <div style="font-size:12px;color:var(--muted)">Avancement ${it.progress} %</div>
    <table>${rows}</table>
    <a href="/web#id=${it.id}&model=construction.element&view_type=form" target="_blank">Ouvrir l'élément →</a>`;
  info.style.display = "block";
}

// ---------- Boucle ----------
function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize();
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
</script>
</body>
</html>
"""
