"use strict";

const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");
const modeInfo = {
  count: "Review the complete grain outlines inside the marked tray area. Partial objects are shown separately.",
  grade: "Compare the narrow projected width of each complete grain with a single screen opening.",
  slot: "Slotted screen with the hole length along the photo width. Grains pass as they lie, pass after a hand turn to the listed bearing, or never fit. The hand-turning choice sets the adopted grading.",
  coat: "Compare the share of blue pixels on each complete grain. Glare and shadows can change this estimate.",
  debris: "Find light, low-color fragments and unusually long pieces before hand sorting.",
  surface: "Flag bright patches inside the grain. The marks are indications for hand review.",
  zones: "Compare grain density across a 3 × 3 grid of equal image regions."
};
const names = {
  grain: "Grain", partial: "Partial", speck: "Small fleck", foreign: "Foreign",
  retained: "Retained", through: "Through", turn: "Turn to pass"
};
Object.assign(names, {coated: "Coated", verify: "Verify coating", clear: "Clear", mark: "Pale mark"});
const ink = {
  grain: "#a3ed83", retained: "#a3ed83", coated: "#a3ed83", clear: "#a3ed83",
  through: "#62d3ed", verify: "#ffc875", mark: "#ffc875", turn: "#ffc875",
  foreign: "#ff9176", partial: "#e1c9f2", speck: "#bcb6a1",
};
const state = {
  tray: null, modes: {}, mode: "count", image: null, settings: null, defaults: {},
  report: null, ticket: 0, saved: null, chosen: null, draw: null, drag: null, original: false
};

async function call(path, method = "GET", data) {
  const options = {method};
  if (data instanceof FormData) options.body = data;
  else if (data !== undefined) {
    options.headers = {"Content-Type": "application/json"};
    options.body = JSON.stringify(data);
  }
  const response = await fetch("/seed" + path, options);
  if (response.status === 204) return null;
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "The check could not be completed.");
  return body;
}

function message(text = "", bad = false) {
  $("notice").textContent = text;
  $("notice").classList.toggle("bad", bad);
}

function task(action) {
  return async (event) => {
    event?.preventDefault();
    try { await action(event); }
    catch (error) { message(error.message, true); }
  };
}

function el(tag, text = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function button(text, callback, css) {
  const node = el("button", text);
  node.type = "button";
  if (css) node.className = css;
  node.addEventListener("click", task(callback));
  return node;
}

function trayPath() {
  return "/trays/" + state.tray.id;
}

function options() {
  const value = {...state.settings};
  for (const field of $("settings").querySelectorAll("input[name], select[name]")) {
    value[field.name] = field.tagName === "SELECT" ? field.value : field.valueAsNumber;
  }
  return value;
}

function setFields() {
  for (const field of $("settings").querySelectorAll("input[name], select[name]")) {
    field.value = state.settings[field.name];
  }
}

async function loadList(requested) {
  const list = await call("/trays");
  const previous = requested || state.tray?.id || localStorage.getItem("seedbench-tray");
  $("tray-select").replaceChildren(...list.map(row => {
    const option = el("option", row.title);
    option.value = row.id;
    return option;
  }));
  const selected = list.find(row => row.id === previous) || list[0];
  $("workspace").hidden = !selected;
  $("empty").hidden = Boolean(selected);
  if (selected) {
    if (selected.id !== state.tray?.id) await openTray(selected.id);
    $("tray-select").value = selected.id;
  } else {
    state.tray = null;
    localStorage.removeItem("seedbench-tray");
  }
}

async function openTray(id) {
  ++state.ticket;
  const row = await call("/trays/" + id);
  const image = new Image();
  image.src = "/seed/trays/" + id + "/image";
  await image.decode();
  state.tray = row;
  state.image = image;
  state.settings = {...state.defaults, ...structuredClone(row.settings)};
  state.saved = null;
  state.report = null;
  state.chosen = null;
  state.original = false;
  turnOffDrawing();
  $("show-source").setAttribute("aria-pressed", "false");
  localStorage.setItem("seedbench-tray", id);
  $("source-details").textContent = [row.filename, row.width + " × " + row.height, row.synthetic ? "Synthetic" : ""].filter(Boolean).join(" · ");
  const ratio = Math.min(1, 1350 / row.width, 1000 / row.height);
  canvas.width = Math.max(1, Math.round(row.width * ratio));
  canvas.height = Math.max(1, Math.round(row.height * ratio));
  setFields();
  renderChrome();
  await inspect();
}

function renderChrome() {
  const mode = state.saved ? state.report.mode : state.mode;
  $("current-mode").textContent = state.saved ? state.report.title : state.modes[mode];
  $("mode-info").textContent = modeInfo[mode];
  $("proof-label").textContent = state.saved ? "Saved check" : "Current tray";
  $("settings").hidden = Boolean(state.saved);
  for (const node of $("settings").querySelectorAll("[data-mode]")) node.hidden = node.dataset.mode !== mode;
  for (const node of $("modes").children) node.setAttribute("aria-current", String(node.dataset.mode === mode));
  const proofs = state.tray.proofs;
  $("proof-count").textContent = String(proofs.length);
  $("proofs").replaceChildren(...proofs.slice().reverse().map((proof, i) => {
    const control = button(proof.title + " · " + (proofs.length - i), () => openProof(proof.id), "tool");
    control.setAttribute("aria-current", String(proof.id === state.saved));
    return control;
  }));
  if (!proofs.length) $("proofs").append(el("p", "Saved checks for this tray appear here."));
  if (state.saved) $("proofs").prepend(button("Return to current tray", () => changeMode(state.mode), "secondary"));
  $("downloads").hidden = !state.saved;
  if (state.saved) {
    const base = "/seed" + trayPath() + "/proofs/" + state.saved;
    $("csv").href = base + "/report.csv";
    $("png").href = base + "/overlay.png";
  }
  $("photo-caption").textContent = state.draw === "area" ? "Drag to mark the tray rectangle." :
    state.draw === "ruler" ? "Drag between two marks on the ruler." : state.original ? "Original image" : "Source-coordinate inspection overlay";
}

async function changeMode(mode) {
  state.mode = mode;
  state.saved = null;
  state.chosen = null;
  state.report = null;
  turnOffDrawing();
  renderChrome();
  renderReport();
  await inspect();
}

async function inspect() {
  const ticket = ++state.ticket;
  const report = await call(trayPath() + "/preview", "POST", {mode: state.mode, settings: options()});
  if (ticket !== state.ticket) return;
  state.report = report;
  state.chosen = null;
  renderReport();
}

async function apply() {
  const row = state.tray;
  const updated = await call(trayPath() + "/settings", "PUT", {revision: row.revision, settings: options()});
  if (row.id !== state.tray?.id) return;
  state.tray = updated;
  state.settings = structuredClone(updated.settings);
  await inspect();
  message("Tray settings applied.");
}

async function save() {
  if (!$("settings").reportValidity()) return;
  if (JSON.stringify(options()) !== JSON.stringify(state.tray.settings)) await apply();
  const result = await call(trayPath() + "/proofs", "POST", {revision: state.tray.revision, mode: state.mode});
  state.tray = result.tray;
  ++state.ticket;
  setProof(result.proof);
  message("Check saved. Download the marked photo or the readings.");
}

async function openProof(id) {
  const ticket = ++state.ticket;
  const report = await call(trayPath() + "/proofs/" + id);
  if (ticket !== state.ticket) return;
  setProof(report);
  message();
}

function setProof(report) {
  state.saved = report.id;
  state.report = report;
  state.chosen = null;
  turnOffDrawing();
  renderChrome();
  renderReport();
}

function renderReport() {
  draw();
  const report = state.report;
  $("results").hidden = !report;
  $("measure-caption").textContent = report ? report.mm_per_pixel.toFixed(4) + " mm/px · " +
    report.supported_pct.toFixed(1) + "% photo support" : "";
  if (!report) return;
  const stats = [["Visible grains", report.visible_grains]];
  if (report.mode === "grade") stats.push(["Through screen", report.counts.through || 0], ["Retained", report.counts.retained || 0]);
  if (report.mode === "slot") {
    stats.push(["Through as dropped", report.counts.through || 0], ["Turn to pass", report.counts.turn || 0],
      ["Cannot pass", report.counts.retained || 0]);
    if (report.adopted) {
      const hand = report.settings.slot_policy === "turned" ? "hand-turned" : "as dropped";
      stats.push([`Adopted through · ${hand}`, report.adopted.through], ["Adopted retained", report.adopted.retained]);
    }
  }
  if (report.mode === "coat") stats.push(["Coated", report.counts.coated || 0], ["Verify coating", report.counts.verify || 0]);
  if (report.mode === "surface") stats.push(["Pale marks", report.counts.mark || 0]);
  if (report.mode === "debris") stats.push(["Foreign material", report.counts.foreign || 0], ["Small flecks", report.counts.speck || 0]);
  stats.push(["Partial objects", report.counts.partial || 0]);
  $("stats").replaceChildren(...stats.map(([label, value]) => {
    const node = el("div");
    node.className = "stat";
    node.append(el("strong", String(value)), el("span", label));
    return node;
  }));
  const columns = report.mode === "zones" ? ["Zone", "Grains", "Support cm²", "Grains/cm²"] :
    report.mode === "slot" ? ["Object", "Status", "Turn °", "Axis °", "Length mm"] :
    ["Object", "Status", report.mode === "grade" ? "Width mm" :
      report.mode === "coat" ? "Blue %" : report.mode === "surface" ? "Mark px" : "Area mm²"];
  const list = report.mode === "zones" ? report.zones : report.rows;
  const head = el("tr");
  head.append(...columns.map(name => el("th", name)));
  $("table-head").replaceChildren(head);
  $("rows").replaceChildren(...list.map(row => {
    const tr = el("tr");
    tr.dataset.key = row.id;
    const index = el("td");
    index.append(button(String(row.id), () => {
      state.chosen = row.id;
      $("rows").querySelector(".picked")?.classList.remove("picked");
      tr.classList.add("picked");
      draw();
    }));
    const values = report.mode === "zones" ? [row.grains, row.observed_cm2, row.grains_per_cm2] :
      report.mode === "slot" ? [names[row.status], row.turn_deg, row.axis_deg, row.length_mm] :
      [names[row.status], row.value];
    tr.append(index, ...values.map(value => el("td", value === null || value === undefined ? "—" : String(value))));
    return tr;
  }));
}

function draw() {
  if (!state.image) return;
  const {width, height} = canvas;
  const sx = width / state.tray.width, sy = height / state.tray.height;
  ctx.fillStyle = "#181e1c";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(state.image, 0, 0, width, height);
  if (state.original && !state.draw) return;
  const options = state.saved ? state.report.settings : state.settings;
  const rectangle = state.drag && state.draw === "area" ? rect(state.drag.from, state.drag.to) : options.area;
  const reference = state.drag && state.draw === "ruler" ? [state.drag.from, state.drag.to] : options.reference;
  const [x0, y0, x1, y1] = rectangle;
  ctx.lineWidth = 1.3;
  ctx.strokeStyle = "#e1d8ae";
  ctx.setLineDash([6, 3]);
  ctx.strokeRect(x0 * width, y0 * height, (x1 - x0) * width, (y1 - y0) * height);
  ctx.setLineDash([]);
  ctx.strokeStyle = "#f5c474";
  ctx.fillStyle = "#f5c474";
  ctx.beginPath();
  ctx.moveTo(reference[0][0] * width, reference[0][1] * height);
  ctx.lineTo(reference[1][0] * width, reference[1][1] * height);
  ctx.stroke();
  for (const [x, y] of reference) ctx.fillRect(x * width - 2.5, y * height - 2.5, 5, 5);
  if (!state.report || state.draw) return;
  const items = state.report.mode === "zones" ? state.report.zones : state.report.rows;
  for (const item of items) {
    if (item.status === "speck" && state.report.mode !== "debris" && item.id !== state.chosen) continue;
    const [x, y, w, h] = item.box;
    const focused = item.id === state.chosen;
    const color = focused ? "#ffffff" : ink[item.status] || "#ffe095";
    ctx.lineWidth = focused ? 3 : 1.4;
    ctx.strokeStyle = color;
    ctx.strokeRect(x * sx, y * sy, w * sx, h * sy);
    const title = item.grains === undefined ? String(item.id) : item.id + "  " + item.grains;
    const labelY = item.grains === undefined ? Math.max(0, y * sy - 13) : y * sy + 2;
    ctx.font = focused ? "bold 12px system-ui" : "11px system-ui";
    ctx.fillStyle = "#161d18";
    ctx.fillRect(x * sx, labelY, ctx.measureText(title).width + 6, 13);
    ctx.fillStyle = color;
    ctx.textBaseline = "top";
    ctx.fillText(title, x * sx + 3, labelY);
  }
  if (state.report.mode === "slot") {
    for (const item of state.report.rows) {
      if (item.status !== "turn" || item.turn_deg === null || item.turn_deg === undefined) continue;
      const half = (item.length_mm || 0) / state.report.mm_per_pixel / 2;
      if (half <= 0) continue;
      const theta = item.turn_deg * Math.PI / 180;
      const dx = half * Math.cos(theta) * sx, dy = half * Math.sin(theta) * sy;
      const [cx, cy] = [item.centre[0] * sx, item.centre[1] * sy];
      for (const [color, lineWidth] of [["#161d18", 3.4], ["#f5f2e8", 1.4]]) {
        ctx.strokeStyle = color;
        ctx.lineWidth = lineWidth;
        ctx.beginPath();
        ctx.moveTo(cx - dx, cy - dy);
        ctx.lineTo(cx + dx, cy + dy);
        ctx.stroke();
      }
    }
  }
}

function turnOffDrawing() {
  state.draw = null;
  state.drag = null;
  canvas.classList.remove("marking");
  $("draw-area").setAttribute("aria-pressed", "false");
  $("draw-ruler").setAttribute("aria-pressed", "false");
}

function mark(type) {
  if (state.saved) return message("Return to the current tray before moving the marks.", true);
  if (state.draw === type) turnOffDrawing();
  else {
    turnOffDrawing();
    state.draw = type;
    state.original = false;
    $("show-source").setAttribute("aria-pressed", "false");
    canvas.classList.add("marking");
    $(type === "area" ? "draw-area" : "draw-ruler").setAttribute("aria-pressed", "true");
  }
  renderChrome();
  draw();
}

function point(event) {
  const box = canvas.getBoundingClientRect();
  return [(event.clientX - box.left) / box.width, (event.clientY - box.top) / box.height]
    .map(value => Math.max(0, Math.min(1, value)));
}

function rect(first, second) {
  return [Math.min(first[0], second[0]), Math.min(first[1], second[1]),
    Math.max(first[0], second[0]), Math.max(first[1], second[1])];
}

canvas.addEventListener("pointerdown", (event) => {
  if (!state.draw) return;
  const at = point(event);
  state.drag = {from: at, to: at};
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener("pointermove", (event) => {
  if (!state.drag) return;
  state.drag.to = point(event);
  draw();
});
canvas.addEventListener("pointercancel", () => {
  state.drag = null;
  draw();
});
canvas.addEventListener("pointerup", (event) => {
  if (!state.drag) return;
  const first = state.drag.from, end = point(event), type = state.draw;
  const bounds = rect(first, end);
  const fits = type === "area" ? bounds[2] - bounds[0] >= 0.025 && bounds[3] - bounds[1] >= 0.025 :
    Math.hypot(first[0] - end[0], first[1] - end[1]) >= 0.01;
  if (fits) {
    state.settings[type === "area" ? "area" : "reference"] = type === "area" ? bounds : [first, end];
    turnOffDrawing();
    message("Mark updated. Apply and inspect to refresh the readings.");
  } else {
    state.drag = null;
    message("Drag a larger mark on the photograph.", true);
  }
  renderChrome();
  draw();
});

$("show-source").addEventListener("click", () => {
  turnOffDrawing();
  state.original = !state.original;
  $("show-source").setAttribute("aria-pressed", String(state.original));
  renderChrome();
  draw();
});
$("draw-area").addEventListener("click", () => mark("area"));
$("draw-ruler").addEventListener("click", () => mark("ruler"));
$("settings").addEventListener("submit", task(apply));
$("save").addEventListener("click", task(save));
$("tray-select").addEventListener("change", task(async event => {
  await openTray(event.target.value);
  message();
}));
$("demo").addEventListener("click", task(async () => {
  const demo = await call("/demo", "POST");
  await loadList(demo.id);
  message("Synthetic tray opened.");
}));
$("upload-toggle").addEventListener("click", () => {
  $("upload-form").hidden = !$("upload-form").hidden;
  if (!$("upload-form").hidden) $("upload-form").elements.title.focus();
});
$("upload-form").addEventListener("submit", task(async event => {
  const form = event.currentTarget;
  const tray = await call("/trays", "POST", new FormData(form));
  form.reset();
  form.hidden = true;
  await loadList(tray.id);
  message("Photo imported. Mark the ruler and inspection area.");
}));
$("remove").addEventListener("click", task(async () => {
  if (!confirm("Remove this tray and its saved checks?")) return;
  await call(trayPath(), "DELETE", {revision: state.tray.revision});
  state.tray = null;
  await loadList();
  message("Tray removed.");
}));

task(async () => {
  const config = await call("/config");
  state.modes = config.modes;
  state.defaults = config.settings;
  for (const [key, title] of Object.entries(state.modes)) {
    const control = button(title, () => changeMode(key));
    control.dataset.mode = key;
    $("modes").append(control);
  }
  await loadList();
})();
