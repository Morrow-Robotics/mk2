"use strict";

const $ = (s, r = document) => r.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const CASES = ["development", "holdout", "negative"];

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function chip(t, k) { return `<span class="chip ${k}">${esc(t)}</span>`; }
async function getJSON(u) { const r = await fetch(u); if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); }

const caseCache = {};
async function fetchCase(name) { if (!caseCache[name]) caseCache[name] = await getJSON(`/api/cases/${name}`); return caseCache[name]; }

// ============ view switching ============

function switchView(v) {
  $("#view-demo").classList.toggle("hidden", v !== "demo");
  $("#view-research").classList.toggle("hidden", v !== "research");
  document.querySelectorAll(".viewnav button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "research") loadStatus();
}

// ============ DEMO: replay graph ============

const rv = () => $("#rv");
let graph = null;  // { nodes, edges, duration }

function minVideoStart(evList) {
  const ts = (evList || []).filter((e) => e.source === "video" && e.start_s != null).map((e) => e.start_s);
  return ts.length ? Math.min(...ts) : null;
}

function computeGraph(spec, duration) {
  const nodes = [];
  const endT = duration * 0.98;

  spec.entities.forEach((e, i, a) => nodes.push({
    id: "e:" + e.id, cls: "entity", type: "entity", label: e.name, sub: e.role,
    x: 10 + 80 * ((i + 0.5) / a.length), y: 15,
    revealAt: minVideoStart(e.evidence) ?? 0, seekAt: minVideoStart(e.evidence), evidence: e.evidence,
  }));

  spec.steps.forEach((s, i, a) => {
    const t = s.start_s != null ? s.start_s : (minVideoStart(s.evidence) ?? (duration * (i + 0.5) / a.length));
    nodes.push({
      id: "s:" + s.id, sid: s.id, cls: "step", type: "action",
      label: `${s.action}`, sub: (s.entity_ids || []).join(", "),
      x: Math.max(8, Math.min(92, 8 + 84 * (t / (duration || 1)))), y: 46,
      revealAt: t, endAt: s.end_s ?? t, seekAt: minVideoStart(s.evidence) ?? t,
      evidence: s.evidence, detail: s.description,
    });
  });

  spec.final_goals.forEach((g, i, a) => {
    const vs = minVideoStart(g.evidence);
    const fromDesc = vs == null;
    nodes.push({
      id: "g:" + i, cls: fromDesc ? "goaldesc" : "goal", type: fromDesc ? "goal · from description" : "goal",
      label: g.description, sub: "",
      x: 12 + 76 * ((i + 0.5) / a.length), y: 74,
      revealAt: fromDesc ? endT : vs, seekAt: vs, evidence: g.evidence,
    });
  });

  spec.unknowns.forEach((u, i, a) => nodes.push({
    id: "u:" + i, cls: "unknown", type: "blocking unknown", label: "? " + u.question, sub: u.why_it_matters,
    x: 15 + 70 * ((i + 0.5) / a.length), y: 90, revealAt: endT, seekAt: null, evidence: [],
  }));

  const stepIds = new Set(spec.steps.map((s) => "s:" + s.id));
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = spec.ordering.filter((o) => stepIds.has("s:" + o.before) && stepIds.has("s:" + o.after)).map((o) => {
    const after = nodeById["s:" + o.after];
    return {
      before: "s:" + o.before, after: "s:" + o.after, necessity: o.necessity, rationale: o.rationale,
      observedAt: after.revealAt, necessityAt: after.endAt ?? after.revealAt,
    };
  });

  return { nodes, edges, duration, nodeById, statusReveal: duration * 0.99, status: spec.status };
}

function renderGraph(g) {
  const holder = $("#graph .nodes");
  const svg = $("#graph .edges");
  holder.innerHTML = "";
  svg.querySelectorAll("line").forEach((l) => l.remove());

  g.nodes.forEach((n) => {
    const el = document.createElement("div");
    el.className = "node " + n.cls;
    el.style.left = n.x + "%";
    el.style.top = n.y + "%";
    el.innerHTML = `<span class="ntype">${esc(n.type)}</span><span class="nlabel">${esc(n.label)}</span>` +
      (n.sub ? `<span class="nsub">${esc(n.sub)}</span>` : "");
    el.addEventListener("click", () => onNodeClick(n));
    holder.appendChild(el);
    n.el = el;
  });

  g.edges.forEach((e) => {
    const line = document.createElementNS(NS, "line");
    svg.appendChild(line);
    e.el = line;
  });

  const status = $("#graph-status");
  status.className = "graph-status " + g.status;
  status.textContent = g.status.replace(/_/g, " ");

  layoutEdges(g);
  renderLegend();
}

function layoutEdges(g) {
  const box = $("#graph");
  const w = box.clientWidth, h = box.clientHeight;
  const svg = $("#graph .edges");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  g.edges.forEach((e) => {
    const a = g.nodeById[e.before].el, b = g.nodeById[e.after].el;
    if (!a || !b) return;
    let x1 = a.offsetLeft, y1 = a.offsetTop, x2 = b.offsetLeft, y2 = b.offsetTop;
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
    const off = 34;
    e.el.setAttribute("x1", x1 + ux * off); e.el.setAttribute("y1", y1 + uy * off);
    e.el.setAttribute("x2", x2 - ux * off); e.el.setAttribute("y2", y2 - uy * off);
  });
}

function applyReveal(t) {
  if (!graph) return;
  graph.nodes.forEach((n) => n.el.classList.toggle("shown", t >= n.revealAt - 0.05));
  graph.edges.forEach((e) => {
    e.el.classList.toggle("shown", t >= e.observedAt - 0.05);
    e.el.classList.toggle("req", e.necessity === "required" && t >= e.necessityAt - 0.05);
  });
  $("#graph-status").classList.toggle("shown", t >= graph.statusReveal - 0.05);
  const ph = $("#timeline .playhead");
  if (ph) ph.style.left = (100 * t / (graph.duration || 1)) + "%";
  $("#rv-clock").textContent = `${t.toFixed(1)}s / ${(graph.duration || 0).toFixed(1)}s`;
}

function renderTimeline(spec, duration) {
  const tl = $("#timeline");
  tl.innerHTML = '<div class="playhead"></div>';
  spec.steps.forEach((s) => {
    if (s.start_s == null || s.end_s == null) return;
    const seg = document.createElement("div");
    seg.className = "seg";
    seg.style.left = (100 * s.start_s / duration) + "%";
    seg.style.width = Math.max(2, 100 * (s.end_s - s.start_s) / duration) + "%";
    seg.innerHTML = `<span class="lbl">${esc(s.action)}</span>`;
    tl.appendChild(seg);
  });
  tl.onclick = (ev) => {
    const r = tl.getBoundingClientRect();
    rv().currentTime = ((ev.clientX - r.left) / r.width) * duration;
  };
}

function renderLegend() {
  $("#legend").innerHTML = [
    ['<span class="sw entity"></span>', "grounded entity / action"],
    ['<span class="sw goaldesc"></span>', "goal from description"],
    ['<span class="sw unknown"></span>', "blocking unknown"],
    ['<span class="sw edge-req"></span>', "required order"],
    ['<span class="sw edge-obs"></span>', "observed, necessity unknown"],
  ].map(([sw, t]) => `<span class="li">${sw}${esc(t)}</span>`).join("");
}

function onNodeClick(n) {
  document.querySelectorAll("#graph .node").forEach((el) => el.classList.remove("sel"));
  n.el.classList.add("sel");
  if (n.seekAt != null && graph) { rv().currentTime = n.seekAt; }
  $("#inspector-body").innerHTML =
    `<div class="card"><div class="title">${esc(n.type)} — ${esc(n.label)}</div>` +
    (n.sub ? `<div class="evid">${esc(n.sub)}</div>` : "") +
    (n.detail ? `<div class="evid">${esc(n.detail)}</div>` : "") +
    evidenceBlock(n.evidence) +
    (n.seekAt != null ? `<div class="evid">▶ jumped video to ${n.seekAt.toFixed(1)}s</div>` : `<div class="evid">no video frame — cited from the description</div>`) +
    `</div>`;
}

function evidenceLine(ev) {
  const bits = [];
  if (ev.source === "video") bits.push(`<span class="mono">t=${ev.start_s}${ev.end_s != null ? "–" + ev.end_s : ""}s</span>`);
  else { bits.push(esc(ev.source)); if (ev.quote) bits.push(`“${esc(ev.quote)}”`); }
  if (ev.note) bits.push(esc(ev.note));
  return `<div class="evid">${bits.join(" · ")}</div>`;
}
function evidenceBlock(list) { return (list || []).map(evidenceLine).join(""); }

async function selectDemoCase(name) {
  document.querySelectorAll("#case-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.case === name));
  $("#inspector-body").innerHTML = '<span class="muted">Click any node to see its cited evidence and jump the video there.</span>';
  const payload = await fetchCase(name);
  const spec = payload.gold;
  const video = rv();

  if (payload.video.present) {
    $("#video-wrap").innerHTML = '<video id="rv" preload="metadata" playsinline></video>';
    const v = $("#rv");
    v.src = payload.video.url;
    v.addEventListener("loadedmetadata", () => setupReplay(spec, v.duration || fallbackDuration(spec)), { once: true });
    v.addEventListener("timeupdate", () => applyReveal(v.currentTime));
    v.load();
  } else {
    $("#video-wrap").innerHTML = `<div class="missing-video">Video missing: <span class="mono">data/videos/${esc(payload.video.filename)}</span></div>`;
    const d = fallbackDuration(spec);
    setupReplay(spec, d);
    applyReveal(d + 1);  // no video: reveal the whole graph
  }
}

function fallbackDuration(spec) {
  let m = 1;
  spec.steps.forEach((s) => { if (s.end_s) m = Math.max(m, s.end_s); });
  [...spec.entities, ...spec.steps, ...spec.final_goals].forEach((x) =>
    (x.evidence || []).forEach((e) => { if (e.end_s) m = Math.max(m, e.end_s); if (e.start_s) m = Math.max(m, e.start_s); }));
  return m + 1;
}

function setupReplay(spec, duration) {
  graph = computeGraph(spec, duration);
  renderGraph(graph);
  renderTimeline(spec, duration);
  applyReveal(0);
}

function wireReplayControls() {
  $("#rv-play").addEventListener("click", () => { const v = rv(); if (v && v.src) { if (v.paused) v.play(); else v.pause(); } });
  $("#rv-restart").addEventListener("click", () => { const v = rv(); if (v && v.src) { v.currentTime = 0; applyReveal(0); } });
  window.addEventListener("resize", () => { if (graph) layoutEdges(graph); });
}

// ============ RESEARCH CONSOLE ============

async function loadStatus() {
  let s;
  try { s = await getJSON("/api/status"); }
  catch (e) { $("#runtime .body").innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  renderRuntime(s.runtime, s.model);
  renderPipeline(s.pipeline);
  renderBaseline(s.baseline0);
}

function renderRuntime(rt, model) {
  const yn = (b) => b ? chip("yes", "ok") : chip("no", "muted");
  const rows = [
    ["chip", esc(rt.chip)], ["os", `${esc(rt.os)} ${esc(rt.os_release)}`], ["arch", esc(rt.arch)],
    ["python", esc(rt.python)],
    ["torch", rt.torch_installed ? chip(esc(rt.torch_version || "installed"), "ok") : chip("missing", "warn")],
    ["MPS", yn(rt.mps_available)], ["CUDA", yn(rt.cuda_available)],
    ["CUDA devices", rt.cuda_devices.length ? esc(rt.cuda_devices.join(", ")) : "—"],
    ["Qwen checkpoint", `<span class="mono">${esc(model.checkpoint)}</span>`],
    ["checkpoint local", model.available_locally ? chip("present", "ok") : chip("not found", "warn")],
  ];
  $("#runtime .body").innerHTML =
    `<div class="grid">${rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`).join("")}</div>
     <p class="sub">Detected live from this server's hardware. Status inspection loads no model weights.</p>`;
}

function renderPipeline(stages) {
  const kind = (st) => st === "complete" ? "ok" : st === "ready" ? "muted" : "warn";
  $("#pipeline .body").innerHTML =
    `<div class="stages">${stages.map((s) => `<div class="stage"><div class="name">${esc(s.stage)} ${chip(s.state, kind(s.state))}</div><div class="detail">${esc(s.detail)}</div></div>`).join("")}</div>`;
}

function renderBaseline(b) {
  const items = b.checklist.map((c) => `<li>${c.done ? chip("done", "ok") : chip("pending", "warn")} ${esc(c.item)}</li>`).join("");
  const gold = Object.entries(b.gold).map(([n, g]) => `<div class="kv"><span class="k">${esc(n)}</span><span class="v">${g.valid ? chip("valid", "ok") : chip("invalid", "bad")} ${esc(g.status || "—")}</span></div>`).join("");
  $("#baseline .body").innerHTML =
    `<ul class="checklist">${items}</ul><h3>Frozen gold</h3><div class="grid">${gold}</div>
     <h3>Runs</h3><div>${b.runs_present ? chip("runs present", "ok") : chip("no Qwen runs yet — Baseline-0 pending", "warn")}</div>
     <p class="sub mono">prompt ${esc(b.prompt_version)} · observe ${esc(b.prompt_fingerprint.observe_system_sha256.slice(0, 12))}…</p>`;
}

async function selectResearchCase(name) {
  document.querySelectorAll("#rcase-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.case === name));
  $("#rcase-detail").innerHTML = "loading…";
  const c = await fetchCase(name);
  $("#rcase-detail").innerHTML = renderCaseCards(c);
}

function renderCaseCards(c) {
  const g = c.gold; if (!g) return "gold missing";
  const val = c.validation;
  const valChip = val.pass ? chip(val.bounds_checked ? "valid" : "valid (bounds unchecked)", "ok") : chip("INVALID", "bad");
  const section = (title, items, empty) => `<h3>${title}</h3>${items.length ? items.join("") : `<p class='sub'>${empty}</p>`}`;
  const ent = g.entities.map((e) => `<div class="card"><div class="title">${esc(e.name)} ${chip(e.role, "muted")}</div>${evidenceBlock(e.evidence)}</div>`);
  const steps = g.steps.map((s) => `<div class="card"><div class="title">${esc(s.action)}: ${esc(s.description)} ${s.start_s != null ? `<span class="mono">${s.start_s}–${s.end_s}s</span>` : ""} ${chip("conf " + s.confidence, "muted")}</div>${evidenceBlock(s.evidence)}</div>`);
  const goals = g.final_goals.map((x) => `<div class="card"><div class="title">${esc(x.description)}</div>${evidenceBlock(x.evidence)}</div>`);
  const ords = g.ordering.map((o) => `<div class="card"><div class="title"><span class="mono">${esc(o.before)} → ${esc(o.after)}</span> · observed ${o.observed ? "yes" : "no"} · necessity <span class="necessity-${esc(o.necessity)}">${esc(o.necessity)}</span></div><div class="evid">${esc(o.rationale)}</div></div>`);
  const unk = g.unknowns.map((u) => `<div class="card"><div class="title">? ${esc(u.question)}</div><div class="evid">${esc(u.why_it_matters)}</div></div>`);
  return `<div class="banner gold">Frozen human gold</div>
    <div class="grid" style="margin:10px 0">
      <div class="kv"><span class="k">description</span><span class="v">${esc(c.description)}</span></div>
      <div class="kv"><span class="k">expected status</span><span class="v">${esc(c.expected.status)}</span></div>
      <div class="kv"><span class="k">confidence</span><span class="v">${esc(c.expected.confidence)}</span></div>
      <div class="kv"><span class="k">validation</span><span class="v">${valChip}</span></div>
    </div>
    <p>${esc(g.task_summary)}</p>
    ${section("Entities", ent, "none")}${section("Steps", steps, "none")}${section("Goals", goals, "none")}
    ${section("Ordering", ords, "none")}${section("Unknowns", unk, "none")}`;
}

async function runLive() {
  const btn = $("#live-run"), out = $("#live-output");
  const payload = { case: $("#live-case").value, model: $("#live-model").value.trim() || null, frames: parseInt($("#live-frames").value, 10) || 8 };
  btn.disabled = true;
  out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="sub">Loading Qwen and analysing…</p>`;
  try {
    const r = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok || d.error) out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="err">${esc(d.error || "failed")}</p>`;
    else out.innerHTML = `<div class="banner live">Live Qwen output — preview, not a Baseline-0 artifact</div>
      <p class="sub mono">${esc(d.backend.model)} · ${esc(d.backend.device || "")} · observe ${esc(d.telemetry.observe_latency_s)}s · synth ${esc(d.telemetry.synthesize_latency_s)}s</p>
      <h3>WorkflowSpec (live)</h3><pre>${esc(JSON.stringify(d.spec, null, 2))}</pre>
      <h3>Observations (live)</h3><pre>${esc(JSON.stringify(d.observations, null, 2))}</pre>`;
  } catch (e) { out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="err">${esc(e.message)}</p>`; }
  finally { btn.disabled = false; }
}

// ============ init ============

function tabs(sel, onClick) {
  $(sel).innerHTML = CASES.map((n) => `<button data-case="${n}">${n}</button>`).join("");
  $(sel).querySelectorAll("button").forEach((b) => b.addEventListener("click", () => onClick(b.dataset.case)));
}

function init() {
  document.querySelectorAll(".viewnav button").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  tabs("#case-tabs", selectDemoCase);
  tabs("#rcase-tabs", selectResearchCase);
  wireReplayControls();
  $("#live-run").addEventListener("click", runLive);
  selectDemoCase("development");
  selectResearchCase("development");
}

document.addEventListener("DOMContentLoaded", init);
