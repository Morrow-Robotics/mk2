"use strict";

const $ = (s, r = document) => r.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const CASES = ["development", "holdout", "negative"];

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function chip(t, k) { return `<span class="chip ${k}">${esc(t)}</span>`; }
function yn(b) { return b ? chip("yes", "ok") : chip("no", "muted"); }
async function getJSON(u) { const r = await fetch(u); if (!r.ok) throw new Error(`${r.status}`); return r.json(); }

const caseCache = {}, evalCache = {};
async function fetchCase(n) { if (!caseCache[n]) caseCache[n] = await getJSON(`/api/cases/${n}`); return caseCache[n]; }
async function fetchEval(n) { return getJSON(`/api/eval/${n}`); }  // not cached — runs change

// ===================== nav =====================
let statusLoaded = false;
function switchView(v) {
  ["demo", "eval", "system"].forEach((x) => $("#view-" + x).classList.toggle("hidden", x !== v));
  document.querySelectorAll(".viewnav button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "system" && !statusLoaded) { statusLoaded = true; loadSystem(); }
}

// ===================== DEMO =====================
const rv = () => $("#rv");
let graph = null, currentSpec = null;

function minVideoStart(ev) { const t = (ev || []).filter((e) => e.source === "video" && e.start_s != null).map((e) => e.start_s); return t.length ? Math.min(...t) : null; }

function computeGraph(spec, duration) {
  const nodes = [], endT = duration * 0.98;
  spec.entities.forEach((e, i, a) => nodes.push({ id: "e:" + e.id, cls: "entity", type: "entity", label: e.name, sub: e.role, x: 10 + 80 * ((i + 0.5) / a.length), y: 15, revealAt: minVideoStart(e.evidence) ?? 0, seekAt: minVideoStart(e.evidence), evidence: e.evidence }));
  spec.steps.forEach((s, i, a) => { const t = s.start_s != null ? s.start_s : (minVideoStart(s.evidence) ?? (duration * (i + 0.5) / a.length)); nodes.push({ id: "s:" + s.id, cls: "step", type: "action", label: s.action, sub: (s.entity_ids || []).join(", "), x: Math.max(8, Math.min(92, 8 + 84 * (t / (duration || 1)))), y: 46, revealAt: t, endAt: s.end_s ?? t, seekAt: minVideoStart(s.evidence) ?? t, evidence: s.evidence, detail: s.description }); });
  spec.final_goals.forEach((g, i, a) => { const vs = minVideoStart(g.evidence), fromDesc = vs == null; nodes.push({ id: "g:" + i, cls: fromDesc ? "goaldesc" : "goal", type: fromDesc ? "goal · from description" : "goal", label: g.description, sub: "", x: 12 + 76 * ((i + 0.5) / a.length), y: 74, revealAt: fromDesc ? endT : vs, seekAt: vs, evidence: g.evidence }); });
  spec.unknowns.forEach((u, i, a) => nodes.push({ id: "u:" + i, cls: "unknown", type: "blocking unknown", label: "? " + u.question, sub: u.why_it_matters, x: 15 + 70 * ((i + 0.5) / a.length), y: 90, revealAt: endT, seekAt: null, evidence: [] }));
  const stepIds = new Set(spec.steps.map((s) => "s:" + s.id)), nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = spec.ordering.filter((o) => stepIds.has("s:" + o.before) && stepIds.has("s:" + o.after)).map((o) => { const a = nodeById["s:" + o.after]; return { before: "s:" + o.before, after: "s:" + o.after, necessity: o.necessity, observedAt: a.revealAt, necessityAt: a.endAt ?? a.revealAt }; });
  return { nodes, edges, duration, nodeById, statusReveal: duration * 0.99, status: spec.status };
}

function renderGraph(g) {
  const holder = $("#graph .nodes"), svg = $("#graph .edges");
  holder.innerHTML = ""; svg.querySelectorAll("line").forEach((l) => l.remove());
  g.nodes.forEach((n) => { const el = document.createElement("div"); el.className = "node " + n.cls; el.style.left = n.x + "%"; el.style.top = n.y + "%"; el.innerHTML = `<span class="ntype">${esc(n.type)}</span><span class="nlabel">${esc(n.label)}</span>` + (n.sub ? `<span class="nsub">${esc(n.sub)}</span>` : ""); el.addEventListener("click", () => onNodeClick(n)); holder.appendChild(el); n.el = el; });
  g.edges.forEach((e) => { const line = document.createElementNS(NS, "line"); svg.appendChild(line); e.el = line; });
  const st = $("#graph-status"); st.className = "graph-status " + g.status; st.textContent = g.status.replace(/_/g, " ");
  layoutEdges(g); renderLegend();
}

function layoutEdges(g) {
  const box = $("#graph"), w = box.clientWidth, h = box.clientHeight, svg = $("#graph .edges");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  g.edges.forEach((e) => { const a = g.nodeById[e.before].el, b = g.nodeById[e.after].el; if (!a || !b) return; const x1 = a.offsetLeft, y1 = a.offsetTop, x2 = b.offsetLeft, y2 = b.offsetTop; const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len, off = 34; e.el.setAttribute("x1", x1 + ux * off); e.el.setAttribute("y1", y1 + uy * off); e.el.setAttribute("x2", x2 - ux * off); e.el.setAttribute("y2", y2 - uy * off); });
}

function applyReveal(t) {
  if (!graph) return;
  graph.nodes.forEach((n) => n.el.classList.toggle("shown", t >= n.revealAt - 0.05));
  graph.edges.forEach((e) => { e.el.classList.toggle("shown", t >= e.observedAt - 0.05); e.el.classList.toggle("req", e.necessity === "required" && t >= e.necessityAt - 0.05); });
  const done = t >= graph.statusReveal - 0.05;
  $("#graph-status").classList.toggle("shown", done);
  $("#demo-outcome").innerHTML = done ? outcomeHTML(currentSpec) : "";
  const ph = $("#timeline .playhead"); if (ph) ph.style.left = (100 * t / (graph.duration || 1)) + "%";
  $("#rv-clock").textContent = `${t.toFixed(1)}s / ${(graph.duration || 0).toFixed(1)}s`;
}

function outcomeHTML(spec) {
  if (!spec) return "";
  if (spec.status === "accepted") return `<span class="badge ok">Workflow accepted</span>`;
  if (spec.status === "needs_new_video") return `<span class="badge bad">Insufficient view — a new recording is needed</span>`;
  const q = spec.unknowns[0] ? spec.unknowns[0].question : "a detail needs confirmation";
  return `<span class="badge warn">Needs confirmation</span> <span class="muted">${esc(q)}</span>`;
}

function renderTimeline(spec, duration) {
  const tl = $("#timeline"); tl.innerHTML = '<div class="playhead"></div>';
  spec.steps.forEach((s) => { if (s.start_s == null || s.end_s == null) return; const seg = document.createElement("div"); seg.className = "seg"; seg.style.left = (100 * s.start_s / duration) + "%"; seg.style.width = Math.max(2, 100 * (s.end_s - s.start_s) / duration) + "%"; seg.innerHTML = `<span class="lbl">${esc(s.action)}</span>`; tl.appendChild(seg); });
  tl.onclick = (ev) => { const r = tl.getBoundingClientRect(); rv().currentTime = ((ev.clientX - r.left) / r.width) * duration; };
}

function renderLegend() {
  $("#legend").innerHTML = [['<span class="sw entity"></span>', "grounded entity / action"], ['<span class="sw goaldesc"></span>', "goal from instruction"], ['<span class="sw unknown"></span>', "blocking question"], ['<span class="sw edge-req"></span>', "required order"], ['<span class="sw edge-obs"></span>', "observed, necessity unknown"]].map(([sw, t]) => `<span class="li">${sw}${esc(t)}</span>`).join("");
}

function evidenceLine(ev) { const b = []; if (ev.source === "video") b.push(`<span class="mono">t=${ev.start_s}${ev.end_s != null ? "–" + ev.end_s : ""}s</span>`); else { b.push(esc(ev.source)); if (ev.quote) b.push(`“${esc(ev.quote)}”`); } if (ev.note) b.push(esc(ev.note)); return `<div class="evid">${b.join(" · ")}</div>`; }
function evidenceBlock(l) { return (l || []).map(evidenceLine).join(""); }

function onNodeClick(n) {
  document.querySelectorAll("#graph .node").forEach((el) => el.classList.remove("sel"));
  n.el.classList.add("sel");
  if (n.seekAt != null) rv().currentTime = n.seekAt;
  $("#inspector-body").innerHTML = `<b>${esc(n.type)}</b> — ${esc(n.label)} ` + (n.detail ? `· ${esc(n.detail)} ` : "") + (n.seekAt != null ? `<span class="mono">▶ ${n.seekAt.toFixed(1)}s</span>` : `<span class="muted">cited from the instruction</span>`);
}

async function selectDemoCase(name) {
  document.querySelectorAll("#demo-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.case === name));
  const c = await fetchCase(name);
  $("#demo-desc").textContent = c.description;
  $("#rv-source").textContent = "· source: human reference workflow";
  $("#inspector-body").innerHTML = "Click any node to jump the video to its cited evidence.";
  const spec = c.gold; currentSpec = spec;
  if (c.video.present) {
    $("#video-wrap").innerHTML = '<video id="rv" preload="metadata" playsinline></video>';
    const v = $("#rv"); v.src = c.video.url;
    v.addEventListener("loadedmetadata", () => setupReplay(spec, v.duration || fallbackDuration(spec)), { once: true });
    v.addEventListener("timeupdate", () => applyReveal(v.currentTime));
    v.load();
  } else {
    $("#video-wrap").innerHTML = `<div class="missing-video">Video missing: <span class="mono">data/videos/${esc(c.video.filename)}</span></div>`;
    const d = fallbackDuration(spec); setupReplay(spec, d); applyReveal(d + 1);
  }
}
function fallbackDuration(spec) { let m = 1; spec.steps.forEach((s) => { if (s.end_s) m = Math.max(m, s.end_s); }); [...spec.entities, ...spec.steps, ...spec.final_goals].forEach((x) => (x.evidence || []).forEach((e) => { if (e.end_s) m = Math.max(m, e.end_s); if (e.start_s) m = Math.max(m, e.start_s); })); return m + 1; }
function setupReplay(spec, duration) { graph = computeGraph(spec, duration); renderGraph(graph); renderTimeline(spec, duration); applyReveal(0); }

// ===================== EVALUATION =====================
async function selectEvalCase(name) {
  document.querySelectorAll("#eval-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.case === name));
  $("#eval-body").innerHTML = "loading…";
  const payload = await fetchEval(name);
  const runs = payload.runs || [];
  const sel = $("#eval-run");
  sel.innerHTML = runs.map((r, i) => `<option value="${i}">${esc(r.kind)} · ${esc(r.run_id)} · ${esc((r.backend && r.backend.model) || "")}</option>`).join("");
  sel.onchange = () => renderEvalRun(payload, runs[+sel.value]);
  $("#spec-inspector-body").innerHTML = payload.gold ? renderSpecCards(payload.gold, payload.description) : "gold missing";
  if (!runs.length) {
    $("#eval-body").innerHTML = `<div class="empty"><b>No model result exists for this case yet.</b><div class="muted">Run <span class="mono">eval/explore.py ${esc(name)}</span> to generate one. The frozen human gold is available in the collapsible Spec inspector below.</div></div>`;
    return;
  }
  renderEvalRun(payload, runs[0]);
}

function renderEvalRun(payload, run) {
  const gold = payload.gold;
  const b = run.backend || {}, tel = run.telemetry || {}, ss = run.stage_status || {};
  const failed = !run.spec;
  const head = `<div class="run-head">
    <div>${chip(run.kind, run.kind === "baseline0" ? "ok" : "muted")} <span class="mono">${esc(run.run_id)}</span>
      · <b>${esc(b.model || "")}</b> · ${esc(b.device || "")}/${esc(b.dtype || "")} · ${esc(run.frames)} frames</div>
    <div class="muted">observe: ${statusChip(ss.observe)} · synthesize: ${statusChip(ss.synthesize)}
      · observe ${esc(tel.observe_latency_s)}s · synth ${esc(tel.synthesize_latency_s)}s
      · peak RSS ${run.peak_rss_bytes ? (run.peak_rss_bytes / 1e9).toFixed(2) + " GB" : "—"}</div>
    <div class="muted mono">frames at ${esc(JSON.stringify(run.frame_timestamps))}</div>
  </div>`;

  if (failed) {
    const raw = run.synthesis_raw || run.observation_raw || "";
    $("#eval-body").innerHTML = head + `<div class="bucket schema"><h3>Schema elicitation — FAILED</h3>
      <p>The model did not produce a parseable spec. The immediate bottleneck is schema elicitation; observations/synthesis quality can't be judged until the output parses. Raw output preserved:</p>
      <pre>${esc(raw.slice(0, 4000))}</pre></div>`;
    return;
  }

  const sb = run.scoreboard || {}, gm = sb.gold || {}, cc = sb.critical_checks || {};
  const goldReq = gold.ordering.filter((o) => o.necessity === "required").length;
  const predReq = run.spec.ordering.filter((o) => o.necessity === "required").length;
  const buckets = `<div class="buckets">
    ${bucket("Perception", "did it see the right objects & actions?", [
      ["entity F1", fmt(gm.entity && gm.entity.f1)], ["entity recall", fmt(gm.entity && gm.entity.recall)],
      ["action F1", fmt(gm.action_f1 && gm.action_f1.f1)], ["invented entities", (gm.invented_entities || []).join(", ") || "none"]])}
    ${bucket("Schema", "valid, well-formed spec?", [
      ["parsed", "yes"], ["validation errors", String((run.validation || []).filter((i) => i.severity === "error").length)]])}
    ${bucket("Synthesis", "observations → correct spec?", [
      ["goal recall", fmt(gm.final_goal_recall)], ["goal set exact", String(gm.final_goal_exact_set_match)],
      ["order necessity agreement", fmt(gm.order_necessity && gm.order_necessity.agreement)], ["required orders (model/gold)", `${predReq} / ${goldReq}`]])}
    ${bucket("Scope", "in/out-of-scope reasoning?", [
      ["surplus hard constraints", String(gm.hard_constraints && gm.hard_constraints.surplus)],
      ["raised a blocking question", (run.spec.unknowns.length > 0) ? "yes (" + run.spec.unknowns.length + ")" : "no"],
      ["status (model/gold)", `${run.spec.status} / ${gold.status}`]])}
  </div>`;

  const critical = `<div class="panel"><h3>Critical checks</h3><div class="grid">` +
    Object.entries(cc).map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v == null ? chip("n/a", "muted") : yn(v)}</span></div>`).join("") + `</div></div>`;

  const compare = `<div class="compare"><div class="col"><h3>Generated (model)</h3>${specSummary(run.spec)}</div><div class="col"><h3>Frozen human gold</h3>${specSummary(gold)}</div></div>`;
  const val = (run.validation || []).length ? `<div class="panel"><h3>Validation issues</h3>${run.validation.map((i) => `<div class="evid">[${esc(i.severity)}] ${esc(i.message)}</div>`).join("")}</div>` : "";
  const sbs = run.side_by_side ? `<details class="panel"><summary>Full side-by-side report</summary><pre>${esc(run.side_by_side)}</pre></details>` : "";
  $("#eval-body").innerHTML = head + buckets + critical + compare + val + sbs;
}

function statusChip(s) { return s === "parsed" ? chip("parsed", "ok") : s === "schema_failure" ? chip("schema failure", "bad") : chip(s || "—", "muted"); }
function fmt(x) { return x == null ? "—" : (typeof x === "number" ? x.toFixed(2) : String(x)); }
function bucket(title, q, rows) { return `<div class="bucket"><h3>${esc(title)}</h3><div class="muted bq">${esc(q)}</div>` + rows.map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("") + `</div>`; }

function specSummary(s) {
  const li = (t, items, f) => `<div class="ss"><span class="ss-k">${t}</span> ${items.length ? items.map(f).join(", ") : "<span class='muted'>none</span>"}</div>`;
  return `<div class="kv"><span class="k">status</span><span class="v">${esc(s.status)} · conf ${esc(s.confidence)}</span></div>` +
    li("entities", s.entities, (e) => esc(e.name)) +
    li("steps", s.steps, (x) => esc(x.action)) +
    li("goals", s.final_goals, (g) => esc(g.description)) +
    li("ordering", s.ordering, (o) => `${esc(o.before)}→${esc(o.after)} <span class="necessity-${esc(o.necessity)}">${esc(o.necessity)}</span>`) +
    li("unknowns", s.unknowns, (u) => esc(u.question));
}

function renderSpecCards(g, desc) {
  const sec = (t, items) => `<h3>${t}</h3>${items.length ? items.join("") : "<p class='sub'>none</p>"}`;
  return sec("Entities", g.entities.map((e) => `<div class="card"><div class="title">${esc(e.name)} ${chip(e.role, "muted")}</div>${evidenceBlock(e.evidence)}</div>`)) +
    sec("Steps", g.steps.map((s) => `<div class="card"><div class="title">${esc(s.action)}: ${esc(s.description)} ${s.start_s != null ? `<span class="mono">${s.start_s}–${s.end_s}s</span>` : ""}</div>${evidenceBlock(s.evidence)}</div>`)) +
    sec("Goals", g.final_goals.map((x) => `<div class="card"><div class="title">${esc(x.description)}</div>${evidenceBlock(x.evidence)}</div>`)) +
    sec("Ordering", g.ordering.map((o) => `<div class="card"><div class="title"><span class="mono">${esc(o.before)} → ${esc(o.after)}</span> · necessity <span class="necessity-${esc(o.necessity)}">${esc(o.necessity)}</span></div><div class="evid">${esc(o.rationale)}</div></div>`)) +
    sec("Unknowns", g.unknowns.map((u) => `<div class="card"><div class="title">? ${esc(u.question)}</div><div class="evid">${esc(u.why_it_matters)}</div></div>`));
}

// ===================== SYSTEM =====================
async function loadSystem() {
  let s; try { s = await getJSON("/api/status"); } catch (e) { $("#sys-hw").innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  const rt = s.runtime, b = s.baseline0;
  const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
  $("#sys-hw").innerHTML = `<div class="grid">` +
    kv("chip", esc(rt.chip)) + kv("os", `${esc(rt.os)} ${esc(rt.os_release)}`) + kv("arch", esc(rt.arch)) +
    kv("python", esc(rt.python)) + kv("torch", rt.torch_installed ? chip(esc(rt.torch_version), "ok") : chip("missing", "warn")) +
    kv("MPS", yn(rt.mps_available)) + kv("CUDA", yn(rt.cuda_available)) + kv("CUDA devices", rt.cuda_devices.join(", ") || "—") + `</div>`;
  $("#sys-model").innerHTML = `<div class="grid">` +
    kv("checkpoint", `<span class="mono">${esc(s.model.checkpoint)}</span>`) + kv("checkpoint local", s.model.available_locally ? chip("present", "ok") : chip("not found", "warn")) +
    kv("prompt version", esc(b.prompt_version)) +
    kv("observe prompt sha256", `<span class="mono">${esc(b.prompt_fingerprint.observe_system_sha256.slice(0, 16))}…</span>`) +
    kv("synthesize prompt sha256", `<span class="mono">${esc(b.prompt_fingerprint.synthesize_system_sha256.slice(0, 16))}…</span>`) +
    kv("WorkflowSpec schema sha256", `<span class="mono">${esc((b.schema_sha256 || "").slice(0, 16))}…</span>`) + `</div>`;
  $("#sys-deps").innerHTML = `<div class="grid">` + Object.entries(rt.libraries || {}).map(([k, v]) => kv(k, v ? esc(v) : chip("missing", "muted"))).join("") + `</div>`;
  $("#sys-pipe").innerHTML = `<div class="stages">${s.pipeline.map((st) => `<div class="stage"><div class="name">${esc(st.stage)} ${chip(st.state, st.state === "complete" ? "ok" : st.state === "ready" ? "muted" : "warn")}</div><div class="detail">${esc(st.detail)}</div></div>`).join("")}</div>` +
    `<ul class="checklist">${b.checklist.map((c) => `<li>${c.done ? chip("done", "ok") : chip("pending", "warn")} ${esc(c.item)}</li>`).join("")}</ul>`;
}

async function runLive() {
  const btn = $("#live-run"), out = $("#live-output");
  const payload = { case: $("#live-case").value, model: $("#live-model").value.trim() || null, frames: parseInt($("#live-frames").value, 10) || 8 };
  btn.disabled = true; out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="sub">Loading Qwen and analysing…</p>`;
  try {
    const r = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok || d.error) out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="err">${esc(d.error || "failed")}</p>`;
    else out.innerHTML = `<div class="banner live">Live Qwen output — preview, not a Baseline-0 artifact</div><p class="sub mono">${esc(d.backend.model)} · ${esc(d.backend.device || "")}</p><pre>${esc(JSON.stringify(d.spec, null, 2))}</pre>`;
  } catch (e) { out.innerHTML = `<p class="err">${esc(e.message)}</p>`; } finally { btn.disabled = false; }
}

// ===================== init =====================
function tabs(sel, onClick) { $(sel).innerHTML = CASES.map((n) => `<button data-case="${n}">${n}</button>`).join(""); $(sel).querySelectorAll("button").forEach((b) => b.addEventListener("click", () => onClick(b.dataset.case))); }
function init() {
  document.querySelectorAll(".viewnav button").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  tabs("#demo-tabs", selectDemoCase); tabs("#eval-tabs", selectEvalCase);
  $("#rv-play").addEventListener("click", () => { const v = rv(); if (v && v.src) v.paused ? v.play() : v.pause(); });
  $("#rv-restart").addEventListener("click", () => { const v = rv(); if (v && v.src) { v.currentTime = 0; applyReveal(0); } });
  window.addEventListener("resize", () => { if (graph) layoutEdges(graph); });
  $("#live-run").addEventListener("click", runLive);
  selectDemoCase("development"); selectEvalCase("development");
}
document.addEventListener("DOMContentLoaded", init);
