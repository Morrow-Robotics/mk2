"use strict";

const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function chip(text, kind) { return `<span class="chip ${kind}">${esc(text)}</span>`; }

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// --- status ---------------------------------------------------------------

async function loadStatus() {
  let s;
  try { s = await getJSON("/api/status"); }
  catch (e) { $("#runtime .body").innerHTML = `<span class="err">status failed: ${esc(e.message)}</span>`; return; }
  renderRuntime(s.runtime, s.model);
  renderPipeline(s.pipeline);
  renderBaseline(s.baseline0);
}

function renderRuntime(rt, model) {
  const yn = (b) => b ? chip("yes", "ok") : chip("no", "muted");
  const rows = [
    ["chip", esc(rt.chip)],
    ["os", `${esc(rt.os)} ${esc(rt.os_release)}`],
    ["arch", esc(rt.arch)],
    ["python", esc(rt.python)],
    ["torch", rt.torch_installed ? chip(esc(rt.torch_version || "installed"), "ok") : chip("missing", "warn")],
    ["MPS available", yn(rt.mps_available)],
    ["CUDA available", yn(rt.cuda_available)],
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
    `<div class="stages">${stages.map((s) => `
      <div class="stage"><div class="name">${esc(s.stage)} ${chip(s.state, kind(s.state))}</div>
        <div class="detail">${esc(s.detail)}</div></div>`).join("")}</div>`;
}

function renderBaseline(b) {
  const items = b.checklist.map((c) =>
    `<li>${c.done ? chip("done", "ok") : chip("pending", "warn")} ${esc(c.item)}</li>`).join("");
  const gold = Object.entries(b.gold).map(([name, g]) =>
    `<div class="kv"><span class="k">${esc(name)}</span><span class="v">${g.valid ? chip("valid", "ok") : chip("invalid", "bad")} ${esc(g.status || "—")}</span></div>`).join("");
  const runsNote = b.runs_present
    ? chip("runs present", "ok")
    : chip("no Qwen runs yet — Baseline-0 pending", "warn");
  $("#baseline .body").innerHTML =
    `<ul class="checklist">${items}</ul>
     <h3>Frozen gold</h3><div class="grid">${gold}</div>
     <h3>Runs</h3><div>${runsNote}</div>
     <p class="sub mono">prompt ${esc(b.prompt_version)} · observe ${esc(b.prompt_fingerprint.observe_system_sha256.slice(0, 12))}… · synthesize ${esc(b.prompt_fingerprint.synthesize_system_sha256.slice(0, 12))}…</p>`;
}

// --- cases ----------------------------------------------------------------

const CASES = ["development", "holdout", "negative"];

function buildTabs() {
  $("#case-tabs").innerHTML = CASES.map((n) => `<button data-case="${n}">${n}</button>`).join("");
  $("#case-tabs").querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => loadCase(btn.dataset.case)));
}

async function loadCase(name) {
  $("#case-tabs").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.case === name));
  $("#case-detail").innerHTML = "loading…";
  let c;
  try { c = await getJSON(`/api/cases/${name}`); }
  catch (e) { $("#case-detail").innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  $("#case-detail").innerHTML = renderCase(c);
}

function evidenceLine(ev) {
  const bits = [];
  if (ev.source === "video") {
    const span = ev.end_s != null ? `t=${ev.start_s}–${ev.end_s}s` : `t=${ev.start_s}s`;
    bits.push(`<span class="mono">${esc(span)}</span>`);
  } else {
    bits.push(esc(ev.source));
    if (ev.quote) bits.push(`“${esc(ev.quote)}”`);
  }
  if (ev.note) bits.push(esc(ev.note));
  return `<div class="evid">${bits.join(" · ")}</div>`;
}

function evidenceBlock(evList) { return (evList || []).map(evidenceLine).join(""); }

function renderCase(c) {
  const g = c.gold;
  const video = c.video.present
    ? `<video controls preload="metadata" src="${esc(c.video.url)}"></video>`
    : `<div class="missing-video">Video missing: <span class="mono">data/videos/${esc(c.video.filename)}</span><br>Copy the source clip there to enable playback.</div>`;

  const val = c.validation;
  const valChip = !val.parsed ? chip("gold missing", "bad")
    : val.pass ? chip(val.bounds_checked ? "valid" : "valid (bounds unchecked)", "ok")
    : chip("INVALID", "bad");

  if (!g) {
    return `${video}<p>${valChip}</p>`;
  }

  const meta = [
    ["requested description", esc(c.description)],
    ["source", `<span class="mono">${esc(c.source)}</span>`],
    ["expected status", esc(c.expected.status)],
    ["expected confidence", esc(c.expected.confidence)],
    ["deterministic validation", valChip],
  ].map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`).join("");

  const entities = g.entities.map((e) =>
    `<div class="card"><div class="title">${esc(e.name)} <span class="chip muted">${esc(e.role)}</span></div>${evidenceBlock(e.evidence)}</div>`).join("") || "<p class='sub'>none</p>";

  const steps = g.steps.map((s) => {
    const span = (s.start_s != null && s.end_s != null) ? ` <span class="mono">${s.start_s}–${s.end_s}s</span>` : "";
    return `<div class="card"><div class="title">${esc(s.action)}: ${esc(s.description)}${span} <span class="chip muted">conf ${esc(s.confidence)}</span></div>${evidenceBlock(s.evidence)}</div>`;
  }).join("") || "<p class='sub'>none demonstrated</p>";

  const goals = g.final_goals.map((gl) =>
    `<div class="card"><div class="title">${esc(gl.description)}</div>${evidenceBlock(gl.evidence)}</div>`).join("") || "<p class='sub'>none</p>";

  const orders = g.ordering.map((o) =>
    `<div class="card"><div class="title"><span class="mono">${esc(o.before)} → ${esc(o.after)}</span>
      · observed ${o.observed ? "yes" : "no"} · necessity <span class="necessity-${esc(o.necessity)}">${esc(o.necessity)}</span></div>
      <div class="evid">${esc(o.rationale)}</div></div>`).join("") || "<p class='sub'>none</p>";

  const unknowns = g.unknowns.map((u) =>
    `<div class="card"><div class="title">? ${esc(u.question)}</div><div class="evid">${esc(u.why_it_matters)}</div></div>`).join("") || "<p class='sub'>none</p>";

  const runs = c.runs.length
    ? c.runs.map((r) => `<div class="card"><div class="title mono">${esc(r.run_id)}</div><div class="evid">${esc(r.dir)} · ${r.scores.length} score(s)</div></div>`).join("")
    : `<p>${chip("no runs yet — Qwen Baseline-0 pending", "warn")}</p>`;

  return `
    <div class="banner gold">Frozen human gold — not model output</div>
    ${video}
    <div class="grid" style="margin-top:12px">${meta}</div>
    <h3>Task summary</h3><p>${esc(g.task_summary)}</p>
    <h3>Entities</h3>${entities}
    <h3>Demonstrated steps</h3>${steps}
    <h3>Final goals</h3>${goals}
    <h3>Ordering</h3>${orders}
    <h3>Unknowns</h3>${unknowns}
    <h3>Run artifacts</h3>${runs}`;
}

// --- live analysis --------------------------------------------------------

async function runLive() {
  const btn = $("#live-run");
  const out = $("#live-output");
  const payload = {
    case: $("#live-case").value,
    model: $("#live-model").value.trim() || null,
    frames: parseInt($("#live-frames").value, 10) || 8,
  };
  btn.disabled = true;
  out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="sub">Loading Qwen and analysing… this can take a while and needs local weights + compute.</p>`;
  try {
    const r = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    out.innerHTML = renderLive(data, r.ok);
  } catch (e) {
    out.innerHTML = `<div class="banner live">Live Qwen output</div><p class="err">request failed: ${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
}

function renderLive(data, ok) {
  const banner = `<div class="banner live">Live Qwen output — preview, not a Baseline-0 artifact</div>`;
  if (!ok || data.error) {
    return `${banner}<p class="err">${esc(data.error || "analysis failed")}</p>`;
  }
  const b = data.backend || {};
  const meta = `<p class="sub mono">backend ${esc(b.backend)} · ${esc(b.model)} · observe ${esc(data.telemetry.observe_latency_s)}s · synth ${esc(data.telemetry.synthesize_latency_s)}s</p>`;
  return `${banner}${meta}
    <h3>WorkflowSpec (live)</h3><pre>${esc(JSON.stringify(data.spec, null, 2))}</pre>
    <h3>Observations (live)</h3><pre>${esc(JSON.stringify(data.observations, null, 2))}</pre>`;
}

// --- init -----------------------------------------------------------------

function init() {
  loadStatus();
  buildTabs();
  loadCase("development");
  $("#live-run").addEventListener("click", runLive);
}

document.addEventListener("DOMContentLoaded", init);
