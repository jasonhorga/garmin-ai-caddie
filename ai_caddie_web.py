"""Local/private AI Caddie Web MVP.

Run:
  uv run python ai_caddie_web.py --port 8765
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import argparse
import json
import math
import subprocess
import sys
import traceback

from PIL import Image

from inspect_courseview_release import inspect_release, load_release_pb

from ai_caddie.analysis import build_hole_analysis, build_round_analysis, overlay_geojson, render_svg, strategy_distances
from ai_caddie.data import (
    ROOT,
    append_manual_shot,
    available_holes,
    create_manual_round,
    delete_manual_shot,
    latest_round_with_shots,
    load_manual_round,
    list_manual_rounds,
    list_rounds,
    update_manual_shot,
)
from ai_caddie.history import (
    history_clubs,
    history_course_detail,
    history_courses,
    history_data_quality,
    history_distribution,
    history_hole,
    history_overview,
    history_reports,
    history_rounds,
    history_shots,
    history_status,
    history_trends,
)


INDEX_HTML = r"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Caddie</title>
  <style>
    :root { color-scheme: light; --ink:#172033; --muted:#667085; --line:#d9dee8; --panel:#ffffff; --bg:#f3f6fa; --blue:#1f6feb; --green:#147a4a; --red:#b42318; }
    * { box-sizing: border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }
    header { height:56px; display:flex; align-items:center; gap:16px; padding:0 18px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:2; }
    h1 { font-size:17px; margin:0; font-weight:650; }
    button, select, input { font:inherit; }
    button { min-height:34px; border:1px solid #bdc7d8; background:#fff; color:var(--ink); border-radius:7px; padding:6px 10px; cursor:pointer; }
    button.primary { background:var(--blue); color:#fff; border-color:var(--blue); }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .tabs { display:flex; gap:8px; }
    .tabs button[aria-selected="true"] { background:#e8f0fe; border-color:#8ab4f8; color:#174ea6; }
    main { max-width:1240px; margin:0 auto; padding:18px; }
    .grid { display:grid; grid-template-columns:360px minmax(0,1fr); gap:16px; align-items:start; }
    section, .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
    h2 { font-size:15px; margin:0 0 12px; }
    label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; }
    select, input { width:100%; min-height:34px; border:1px solid #bdc7d8; border-radius:7px; padding:6px 8px; background:#fff; color:var(--ink); }
    .row { display:flex; gap:8px; align-items:center; }
    .row > * { flex:1; }
    .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
    .muted { color:var(--muted); font-size:12px; }
    .status { margin-top:10px; font-size:12px; color:var(--muted); white-space:pre-wrap; }
    .status.error { color:var(--red); }
    .review { font-size:15px; line-height:1.55; margin-bottom:12px; }
    .metric { display:inline-flex; gap:5px; align-items:baseline; margin:0 12px 8px 0; color:var(--muted); font-size:12px; }
    .metric b { color:var(--ink); font-size:14px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th, td { padding:7px 6px; border-bottom:1px solid #edf0f5; text-align:left; vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .table-scroll { width:100%; overflow:auto; }
    .table-scroll table { min-width:820px; }
    .course-cell { min-width:260px; }
    .course-name { font-weight:650; margin-bottom:7px; }
    .mini-stats { display:flex; flex-wrap:wrap; gap:4px; max-width:520px; }
    .mini-stat { display:inline-flex; align-items:center; gap:3px; padding:2px 6px; border:1px solid #d9dee8; border-radius:999px; background:#f8fafc; color:#344054; font-size:11px; line-height:1.35; white-space:nowrap; }
    .mini-stat b { color:var(--ink); font-weight:700; }
    .overlay { width:100%; min-height:360px; background:#f8fafc; border:1px solid var(--line); border-radius:8px; overflow:auto; }
    .overlay svg { width:100%; height:auto; display:block; }
    .overlay-stack { display:grid; grid-template-columns:1fr; gap:12px; }
    .overlay-panel { border:1px solid var(--line); border-radius:8px; overflow:hidden; background:#fff; }
    .overlay-title { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:9px 11px; border-bottom:1px solid var(--line); font-size:12px; color:var(--muted); }
    .overlay-title b { color:var(--ink); font-size:13px; }
    .overlay-body { background:#f8fafc; min-height:360px; }
    .overlay-body svg { width:100%; height:auto; display:block; }
    .satellite-wrap { display:flex; justify-content:center; align-items:flex-start; padding:12px; background:#edf2f7; }
    .overlay-map { width:min(730px,100%); height:520px; background:#dbe4ef; border:1px solid #cbd5e1; }
    .raster-wrap { display:flex; justify-content:center; align-items:flex-start; padding:12px; background:#edf2f7; }
    .raster-wrap img { width:min(730px,100%); height:auto; display:block; border:1px solid #cbd5e1; }
    .overlay-empty { padding:16px; color:var(--muted); font-size:12px; }
    .map-point { background:transparent; border:0; }
    .map-point span { display:grid; place-items:center; width:26px; height:26px; border:2px solid #fff; border-radius:999px; box-shadow:0 1px 5px rgba(0,0,0,.4); color:#fff; font-size:12px; font-weight:750; line-height:1; }
    .shot-point span { background:#1f6feb; }
    .target-point span { background:#064e3b; }
    .overlay-tools { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:9px 11px; border-bottom:1px solid var(--line); background:#fff; }
    .overlay-tools button[aria-selected="true"] { background:#e8f0fe; border-color:#8ab4f8; color:#174ea6; }
    .strategy-panel { display:grid; grid-template-columns:minmax(190px,.85fr) minmax(0,1.15fr); gap:10px; padding:10px 11px; border-bottom:1px solid var(--line); background:#f8fafc; }
    .strategy-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(105px,1fr)); gap:7px; align-content:start; }
    .strategy-kpi { border:1px solid #d9dee8; background:#fff; border-radius:7px; padding:8px; }
    .strategy-kpi .label { color:var(--muted); font-size:11px; margin-bottom:3px; }
    .strategy-kpi .value { font-size:16px; font-weight:750; }
    .distance-label { background:transparent; border:0; pointer-events:none; }
    .distance-label span { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; border-radius:999px; padding:5px 10px; background:rgba(17,24,39,.84); color:#fff; border:1px solid rgba(255,255,255,.82); box-shadow:0 2px 7px rgba(0,0,0,.34); font-size:12px; font-weight:720; }
    .distance-label b { font-weight:760; }
    .distance-label.target-distance span { background:rgba(6,78,59,.90); }
    .distance-label.water-distance span { background:rgba(30,64,175,.88); }
    .distance-label.bunker-distance span { background:rgba(120,72,22,.88); }
    .distance-label.green-distance span { background:rgba(22,101,52,.88); }
    .distance-label.tree_area-distance span { background:rgba(20,83,45,.88); }
    .hidden { display:none; }
    .badge { display:inline-block; padding:2px 7px; border-radius:999px; background:#eef2f7; color:#344054; font-size:12px; }
    .wide { grid-column:1 / -1; }
    .subtabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
    .subtabs button[aria-selected="true"] { background:#eef6ff; border-color:#8ab4f8; color:#174ea6; }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin-bottom:14px; }
    .card { border:1px solid var(--line); border-radius:8px; padding:12px; background:#fff; }
    .card .label { color:var(--muted); font-size:12px; margin-bottom:5px; }
    .card .value { font-size:21px; font-weight:700; }
    .chart { min-height:260px; border:1px solid var(--line); border-radius:8px; background:#fff; padding:10px; margin-bottom:14px; overflow:auto; }
    .bar { height:10px; border-radius:999px; background:#e8edf5; overflow:hidden; min-width:90px; }
    .bar > span { display:block; height:100%; background:#1f6feb; }
    #courseMap { height:460px; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:#e8edf5; margin-bottom:14px; }
    .split { display:grid; grid-template-columns:1fr 1fr; gap:14px; align-items:start; }
    @media (max-width: 820px) {
      header { height:auto; padding:10px 12px; align-items:flex-start; flex-direction:column; }
      .grid { grid-template-columns:1fr; }
      .split { grid-template-columns:1fr; }
      .strategy-panel { grid-template-columns:1fr; }
      main { padding:12px; }
      .row { flex-direction:column; align-items:stretch; }
    }
  </style>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
  <header>
    <h1>AI Caddie</h1>
    <nav class="tabs" aria-label="views">
      <button data-tab="import" aria-selected="true">Garmin 导入</button>
      <button data-tab="review">洞级复盘</button>
      <button data-tab="history">历史记录</button>
      <button data-tab="manual">手动记杆</button>
    </nav>
  </header>
  <main>
    <div class="grid">
      <section id="tab-import">
        <h2>Garmin rounds</h2>
        <label for="roundSelect">Round</label>
        <select id="roundSelect"></select>
        <label for="holeSelect">Hole</label>
        <select id="holeSelect"></select>
        <div class="actions">
          <button class="primary" id="analyzeBtn">Analyze</button>
          <button id="roundAnalyzeBtn">Round report</button>
          <button id="latestBtn">Latest</button>
          <button id="syncBtn">Sync Garmin</button>
        </div>
        <div id="importStatus" class="status"></div>
      </section>

      <section id="tab-review">
        <h2>Hole review</h2>
        <div id="reviewText" class="review muted">Select a Garmin round or manual round, then analyze.</div>
        <div id="metrics"></div>
        <div class="overlay" id="overlayBox"></div>
        <h2 style="margin-top:14px">Shots</h2>
        <div id="shotsTable"></div>
        <h2 style="margin-top:14px">Candidate routes</h2>
        <div id="routesTable"></div>
        <h2 style="margin-top:14px">Round holes</h2>
        <div id="roundTable"></div>
      </section>

      <section id="tab-history" class="wide hidden">
        <h2>History</h2>
        <div class="subtabs" aria-label="history views">
          <button data-history="overview" aria-selected="true">总览</button>
          <button data-history="rounds">时间线</button>
          <button data-history="scorecards">成绩卡</button>
          <button data-history="trends">趋势</button>
          <button data-history="distribution">分布</button>
          <button data-history="courses">球场</button>
          <button data-history="clubs">球杆</button>
          <button data-history="shots">击球</button>
          <button data-history="hole">单洞</button>
          <button data-history="reports">AI 报告</button>
          <button data-history="quality">数据质量</button>
        </div>
        <div class="row">
          <div><label>Course</label><select id="historyCourseSelect"></select></div>
          <div><label>Club</label><select id="historyClubSelect"></select></div>
          <div><label>Geometry hole</label><select id="historyHoleSelect"></select></div>
        </div>
        <div class="actions">
          <button class="primary" id="refreshHistoryBtn">Refresh history</button>
          <button id="historyCourseBtn">Open course detail</button>
          <button id="historyHoleBtn">Open hole history</button>
        </div>
        <div id="historyStatus" class="status"></div>
        <div id="historyContent" style="margin-top:14px"></div>
      </section>

      <section id="tab-manual" class="hidden">
        <h2>Manual round</h2>
        <label for="holeGeometrySelect">Course / hole geometry</label>
        <select id="holeGeometrySelect"></select>
        <label for="manualCourseName">Course name</label>
        <input id="manualCourseName" placeholder="Optional">
        <div class="actions">
          <button class="primary" id="createManualBtn">Create</button>
          <button id="manualAnalyzeBtn">Analyze manual</button>
        </div>
        <div class="status" id="manualStatus"></div>

        <h2 style="margin-top:18px">Add shot</h2>
        <div class="row">
          <div><label>Club</label><input id="clubName" placeholder="1W / 7I / 54"></div>
          <div><label>Shot type</label><input id="shotType" placeholder="TEE / APPROACH"></div>
        </div>
        <div class="row">
          <div><label>Start lat</label><input id="startLat"></div>
          <div><label>Start lon</label><input id="startLon"></div>
        </div>
        <div class="row">
          <div><label>End lat</label><input id="endLat"></div>
          <div><label>End lon</label><input id="endLon"></div>
        </div>
        <div class="actions">
          <button id="gpsStartBtn">GPS start</button>
          <button id="gpsEndBtn">GPS end</button>
          <button id="addShotBtn">Add shot</button>
          <button id="saveShotBtn">Save edit</button>
        </div>
        <h2 style="margin-top:18px">Manual shots</h2>
        <div id="manualShots"></div>
      </section>
    </div>
  </main>
<script>
const state = { rounds: [], holes: [], courses: [], clubs: [], manualId: null, manualHole: null, editShotId: null, lastAnalysis: null, historyView: "overview", courseMap: null, overlayMode: "strategy", distanceUnit: "yd" };
const $ = id => document.getElementById(id);

function showStatus(id, text, isError=false) {
  const el = $(id); el.textContent = text || ""; el.classList.toggle("error", isError);
}

async function api(path, opts={}) {
  const res = await fetch(path, { headers: { "content-type": "application/json" }, ...opts });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new Error((data && data.error) || text || res.statusText);
  return data;
}

function initTabs() {
  document.querySelectorAll(".tabs button").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b === btn)));
      ["import","review","history","manual"].forEach(name => $("tab-" + name).classList.toggle("hidden", name !== btn.dataset.tab && !(name === "review" && btn.dataset.tab === "import")));
      if (btn.dataset.tab === "import") $("tab-review").classList.remove("hidden");
      if (btn.dataset.tab === "history") renderHistory().catch(e => showStatus("historyStatus", e.message, true));
    });
  });
  document.querySelectorAll("[data-history]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.historyView = btn.dataset.history;
      document.querySelectorAll("[data-history]").forEach(b => b.setAttribute("aria-selected", String(b === btn)));
      renderHistory().catch(e => showStatus("historyStatus", e.message, true));
    });
  });
}

async function loadInitial() {
  const data = await api("/api/status");
  state.rounds = data.rounds;
  state.holes = data.availableHoles;
  $("roundSelect").innerHTML = state.rounds.map(r => `<option value="${r.id}">${r.date || ""} · ${r.courseName} · ${r.strokes || "-"} strokes${r.hasShots ? "" : " · no shots"}</option>`).join("");
  $("holeSelect").innerHTML = Array.from({length:18}, (_,i) => `<option value="${i+1}">${i+1}</option>`).join("");
  $("holeGeometrySelect").innerHTML = state.holes.map(h => `<option value="${h.globalId}:${h.holeNumber}">gid ${h.globalId} · hole ${h.holeNumber} · ${h.hazards ?? 0} features</option>`).join("");
  if (data.latest) {
    $("roundSelect").value = data.latest.id;
  }
  await loadHistoryOptions();
}

async function analyzeGarmin() {
  showStatus("importStatus", "Analyzing...");
  const sid = $("roundSelect").value;
  const hole = $("holeSelect").value;
  const analysis = await api(`/api/analysis?scorecard_id=${encodeURIComponent(sid)}&hole=${encodeURIComponent(hole)}`);
  renderAnalysis(analysis);
  showStatus("importStatus", "Analysis ready.");
}

async function analyzeRound() {
  showStatus("importStatus", "Analyzing round...");
  const sid = $("roundSelect").value;
  const analysis = await api(`/api/round-analysis?scorecard_id=${encodeURIComponent(sid)}`);
  $("reviewText").textContent = analysis.review;
  $("metrics").innerHTML = [
    ["Round", analysis.scorecardId],
    ["Analyzed", analysis.summary.analyzedHoles],
    ["High confidence", analysis.summary.confidenceCounts.high || 0],
    ["Missing geometry", analysis.summary.missingGeometry.length],
  ].map(([k,v]) => `<span class="metric">${k}<b>${v ?? "-"}</b></span>`).join("");
  $("overlayBox").innerHTML = '<div class="muted" style="padding:16px">Select a hole and click Analyze to see geometry overlay.</div>';
  $("shotsTable").innerHTML = "";
  $("routesTable").innerHTML = "";
  $("roundTable").innerHTML = table(["Hole", "Confidence", "Shots", "Tee shot", "Risks", "Best route"], analysis.holes.map(h => {
    const risk = (h.risks || []).slice(0,2).map(r => `${r.kind} ${r.distance_m}m`).join(", ");
    const best = h.bestRoute || {};
    return [h.hole, h.confidence, h.shotCount, `${h.teeShotClub || ""} ${fmt(h.teeShotMeters)}`, risk, `${best.label || ""} ${fmt(best.carry_m)}`];
  }));
  showStatus("importStatus", "Round analysis ready.");
}

function renderAnalysis(a) {
  state.lastAnalysis = a;
  $("reviewText").textContent = a.review;
  $("metrics").innerHTML = [
    ["Source", a.source],
    ["GlobalId", a.globalId],
    ["Local hole", a.localHole],
    ["Geometry", a.geometry.hasMeshes ? "mesh" : (a.geometry.hasHazards ? "hazards" : "missing")],
    ["Confidence", a.dataQuality.confidence],
  ].map(([k,v]) => `<span class="metric">${k}<b>${v ?? "-"}</b></span>`).join("");
  renderOverlayComparison(a).catch(e => {
    $("overlayBox").innerHTML = `<div class="overlay-empty">${esc(e.message)}</div>`;
  });
  $("shotsTable").innerHTML = table(["#", "Club", "Type", "Meters", "End lie", "Feature", "Risk", "Remain"], a.shots.map(s => {
    const feature = s.end?.feature?.surface?.kind || "";
    const risk = (s.end?.feature?.nearRisks || []).slice(0,2).map(r => `${r.kind} ${r.distance_m}m`).join(", ");
    return [s.shotOrder, s.clubName, s.shotType, fmt(s.meters), s.end?.lie || "", feature, risk, fmt(s.remainingToTarget_m)];
  }));
  $("routesTable").innerHTML = table(["Route", "Carry", "Surface", "Risk", "Status"], a.candidateRoutes.map(r => [
    r.label, fmt(r.carry_m), r.expectedSurface?.kind || "", r.riskScore, r.recommendation
  ]));
}

function distanceText(m) {
  if (m == null || Number.isNaN(Number(m))) return "";
  const meters = Number(m);
  if (state.distanceUnit === "yd") return `${Math.round(meters * 1.0936133)}码`;
  return `${Math.round(meters)}米`;
}

function strategyKpi(label, value, sub="") {
  return `<div class="strategy-kpi"><div class="label">${esc(label)}</div><div class="value">${esc(value || "-")}</div><div class="muted">${esc(sub)}</div></div>`;
}

function offsetText(v) {
  if (v == null || !Number.isFinite(Number(v))) return "";
  const n = Number(v);
  if (Math.abs(n) < 1) return "线上";
  return `${Math.abs(n).toFixed(0)}米${n > 0 ? "左" : "右"}`;
}

function strategyPanel(strategy) {
  if (!strategy || strategy.status !== "ok") {
    return `<div class="overlay-empty">${esc((strategy && strategy.status) || "No strategy distances available.")}</div>`;
  }
  const labels = strategy.labels || [];
  const hazards = labels.filter(x => x.kind !== "target");
  const target = strategy.target || {};
  const rows = labels.map(row => [
    esc(row.label),
    distanceText(row.carry_m),
    row.clear_m != null && Math.abs(Number(row.clear_m) - Number(row.carry_m)) >= 4 ? distanceText(row.clear_m) : "",
    offsetText(row.offset_m),
    row.crossesLine ? "目标线穿过" : (row.kind === "target" ? "目标距离" : "侧向参考"),
  ]);
  return `
    <div class="strategy-summary">
      ${strategyKpi("参考点", strategy.reference?.label || "Tee", "所有距离从这里算")}
      ${strategyKpi("目标", distanceText(target.distance_m), "到 target")}
      ${strategyKpi("关键距离", hazards.length, "障碍 / 果岭")}
      ${strategyKpi("单位", state.distanceUnit === "yd" ? "码" : "米", "可切换")}
    </div>
    <div>${table(["Feature","Carry","Clear","Offset","Note"], rows)}</div>`;
}

function strategyLabelHtml(row) {
  const clear = row.clear_m != null && Math.abs(Number(row.clear_m) - Number(row.carry_m)) >= 4 && row.crossesLine
    ? `-${distanceText(row.clear_m)}`
    : "";
  return `<span><b>${esc(row.label)}</b>${esc(distanceText(row.carry_m) + clear)}</span>`;
}

function setOverlayToolState() {
  document.querySelectorAll("[data-overlay-mode]").forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.overlayMode === state.overlayMode)));
  document.querySelectorAll("[data-distance-unit]").forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.distanceUnit === state.distanceUnit)));
  const panel = $("strategyPanel");
  if (panel) panel.classList.toggle("hidden", state.overlayMode !== "strategy");
}

async function renderOverlayComparison(a) {
  const mapId = `satMap_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const params = `source=${encodeURIComponent(a.source)}&id=${encodeURIComponent(a.roundId)}&hole=${encodeURIComponent(a.hole)}`;
  $("overlayBox").innerHTML = `
    <div class="overlay-stack">
      <div class="overlay-panel">
        <div class="overlay-tools">
          <span class="muted">Map mode</span>
          <button data-overlay-mode="replay">回放</button>
          <button data-overlay-mode="strategy">策略距离</button>
          <span class="muted" style="margin-left:8px">Unit</span>
          <button data-distance-unit="yd">码</button>
          <button data-distance-unit="m">米</button>
        </div>
        <div class="strategy-panel" id="strategyPanel"><div class="overlay-empty">Loading strategy distances...</div></div>
      </div>
      <div class="overlay-panel">
        <div class="overlay-title"><b>Prodgeometry overlay</b><span>local meters · feature polygons + shot route</span></div>
        <div class="overlay-body" id="geometryPanel"><div class="overlay-empty">Loading geometry...</div></div>
      </div>
      <div class="overlay-panel">
        <div class="overlay-title"><b>Satellite comparison</b><span>same crop · same overlay · Esri WGS84</span></div>
        <div class="satellite-wrap"><div class="overlay-map" id="${mapId}"></div></div>
      </div>
      <div class="overlay-panel">
        <div class="overlay-title"><b>Garmin hand-drawn raster</b><span>CourseView raster base, when available</span></div>
        <div class="raster-wrap" id="rasterPanel"><div class="overlay-empty">Loading Garmin raster...</div></div>
      </div>
    </div>`;
  const [svg, geo] = await Promise.all([
    fetch(`/api/overlay?${params}`).then(r => r.text()),
    api(`/api/overlay-geojson?${params}`),
  ]);
  $("geometryPanel").innerHTML = svg;
  $("strategyPanel").innerHTML = strategyPanel(geo.strategy);
  setOverlayToolState();
  renderSatelliteOverlay(mapId, geo.geojson || geo, geo.raster || {}, geo.strategy || {});
  if (geo.raster && geo.raster.available) {
    $("rasterPanel").innerHTML = `<img src="${esc(geo.raster.endpoint)}" alt="Garmin 730 raster for gid ${esc(a.globalId)} hole ${esc(a.localHole)}">`;
  } else {
    $("rasterPanel").innerHTML = `<div class="overlay-empty">${esc((geo.raster && geo.raster.reason) || "No Garmin raster URL found for this hole.")}</div>`;
  }
}

function renderSatelliteOverlay(mapId, geojson, raster={}, strategy={}) {
  const el = $(mapId);
  if (!el) return;
  if (!window.L) {
    el.innerHTML = '<div class="overlay-empty">Leaflet failed to load.</div>';
    return;
  }
  const rasterW = Number(raster.width || 730);
  const rasterH = Number(raster.height || 730);
  const displayW = el.clientWidth || Math.min(730, window.innerWidth - 48);
  if (rasterW > 0 && rasterH > 0 && displayW > 0) {
    const h = Math.round(Math.min(1180, Math.max(520, displayW * rasterH / rasterW)));
    el.style.height = `${h}px`;
  }
  const map = L.map(mapId, { zoomControl:true, attributionControl:true });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution:"Esri", maxZoom:20 }).addTo(map);
  const colors = { fairway:"#2f9e44", green:"#16a34a", rough:"#7a8f51", bunker:"#e6c567", water:"#2563eb", water_edge:"#1e40af", tree_area:"#166534", teebox:"#4ade80", playable_bounds:"#64748b" };
  const layer = L.geoJSON(geojson, {
    pointToLayer: (feature, latlng) => {
      const p = feature.properties || {};
      if (p.layer === "shot_end" || p.layer === "target") {
        const text = p.layer === "target" ? "T" : String(p.order || "");
        const cls = p.layer === "target" ? "target-point" : "shot-point";
        return L.marker(latlng, {
          icon: L.divIcon({ className:`map-point ${cls}`, html:`<span>${esc(text)}</span>`, iconSize:[26,26], iconAnchor:[13,13] })
        });
      }
      return L.circleMarker(latlng, { radius:7, color:"#fff", fillColor:"#ef4444", fillOpacity:0.98, weight:2.5 });
    },
    style: feature => {
      const p = feature.properties || {};
      if (p.layer === "shot") return { color:"#ff2d55", weight:4, opacity:0.95 };
      const color = colors[p.kind] || "#94a3b8";
      const faint = p.kind === "playable_bounds" || p.kind === "rough";
      return { color, fillColor:color, weight:faint ? 1 : 1.8, opacity:faint ? 0.38 : 0.92, fillOpacity:faint ? 0.04 : 0.38 };
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {};
      const label = p.layer === "shot" ? `shot ${p.order || ""} · ${p.club || ""} · ${fmt(p.meters)}m` : `${p.kind || p.layer || ""} ${p.id || ""}`;
      layer.bindTooltip(label);
    }
  }).addTo(map);
  const strategyGroup = L.layerGroup().addTo(map);
  function redrawStrategyLayer() {
    strategyGroup.clearLayers();
    if ($("strategyPanel")) $("strategyPanel").innerHTML = strategyPanel(strategy);
    setOverlayToolState();
    if (state.overlayMode !== "strategy" || !strategy || strategy.status !== "ok") return;
    const ref = strategy.reference;
    const target = strategy.target;
    if (ref && target) {
      const route = [[ref.lat, ref.lon], [target.lat, target.lon]];
      L.polyline(route, { color:"#111827", weight:7, opacity:0.35 }).addTo(strategyGroup);
      L.polyline(route, { color:"#ffffff", weight:3.5, opacity:0.92, dashArray:"10 7" }).addTo(strategyGroup);
    }
    (strategy.labels || []).forEach(row => {
      if (row.lat == null || row.lon == null) return;
      const cls = row.kind === "target" ? "target-distance" : `${row.kind}-distance`;
      L.marker([row.lat, row.lon], {
        icon: L.divIcon({
          className:`distance-label ${cls}`,
          html: strategyLabelHtml(row),
          iconSize:[150,28],
          iconAnchor:[0,14],
        })
      }).addTo(strategyGroup);
    });
  }
  document.querySelectorAll("[data-overlay-mode]").forEach(btn => {
    btn.onclick = () => {
      state.overlayMode = btn.dataset.overlayMode;
      redrawStrategyLayer();
    };
  });
  document.querySelectorAll("[data-distance-unit]").forEach(btn => {
    btn.onclick = () => {
      state.distanceUnit = btn.dataset.distanceUnit;
      redrawStrategyLayer();
    };
  });
  redrawStrategyLayer();
  const bounds = geojson.focusBounds || geojson.bounds;
  if (bounds) {
    map.fitBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]], { padding:[8,8], maxZoom:20, animate:false });
  } else if (layer.getBounds && layer.getBounds().isValid()) {
    map.fitBounds(layer.getBounds(), { padding:[8,8], maxZoom:20, animate:false });
  } else {
    map.setView([35, 110], 4);
  }
  setTimeout(() => map.invalidateSize(), 0);
}

function table(headers, rows) {
  if (!rows.length) return '<div class="muted">No data.</div>';
  return `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(c=>`<td>${c ?? ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function fmt(v) { return v == null ? "" : Number(v).toFixed(1); }
function pct(v) { return v == null ? "" : `${Number(v).toFixed(1)}%`; }
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
}
function card(label, value, sub="") {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${esc(value ?? "-")}</div><div class="muted">${esc(sub)}</div></div>`;
}
function bar(value, max, color="#1f6feb") {
  const w = max > 0 ? Math.max(2, Math.min(100, value / max * 100)) : 0;
  return `<div class="bar"><span style="width:${w}%;background:${color}"></span></div>`;
}
function lineChart(points, yKey="score", labelKey="date") {
  const rows = (points || []).filter(p => p[yKey] != null);
  if (rows.length < 2) return '<div class="muted">No chart data.</div>';
  const w = 860, h = 240, pad = 28;
  const ys = rows.map(p => Number(p[yKey]));
  const minY = Math.min(...ys) - 2, maxY = Math.max(...ys) + 2;
  const x = i => pad + (i / Math.max(1, rows.length - 1)) * (w - pad * 2);
  const y = v => h - pad - ((Number(v) - minY) / Math.max(1, maxY - minY)) * (h - pad * 2);
  const d = rows.map((p,i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[yKey]).toFixed(1)}`).join(" ");
  const circles = rows.map((p,i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p[yKey]).toFixed(1)}" r="2.4" fill="#1f6feb"><title>${esc(p[labelKey])} ${esc(p[yKey])}</title></circle>`).join("");
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" role="img">
    <rect x="0" y="0" width="${w}" height="${h}" fill="#fff"/>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h-pad}" stroke="#d9dee8"/>
    <line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="#d9dee8"/>
    <text x="${pad}" y="18" font-size="11" fill="#667085">${maxY.toFixed(0)}</text>
    <text x="${pad}" y="${h-6}" font-size="11" fill="#667085">${minY.toFixed(0)}</text>
    <path d="${d}" fill="none" stroke="#1f6feb" stroke-width="2.2"/>
    ${circles}
  </svg>`;
}

async function loadHistoryOptions() {
  const [courses, clubs] = await Promise.all([
    api("/api/history/courses"),
    api("/api/history/clubs"),
  ]);
  state.courses = courses.courses || [];
  state.clubs = clubs.clubs || [];
  $("historyCourseSelect").innerHTML = '<option value="">All courses</option>' + state.courses.map(c => `<option value="${esc(c.key)}">${esc(c.name)} · ${c.count} 场</option>`).join("");
  $("historyClubSelect").innerHTML = '<option value="">All clubs</option>' + state.clubs.map(c => `<option value="${esc(c.clubName)}">${esc(c.clubName)} · n=${c.sampleSize}</option>`).join("");
  $("historyHoleSelect").innerHTML = state.holes.map(h => `<option value="${h.globalId}:${h.holeNumber}">gid ${h.globalId} · hole ${h.holeNumber} · ${h.hazards ?? 0} features</option>`).join("");
}

async function renderHistory() {
  showStatus("historyStatus", "Loading history...");
  const view = state.historyView;
  if (view === "overview") await renderHistoryOverview();
  else if (view === "rounds") await renderHistoryRounds(false);
  else if (view === "scorecards") await renderHistoryRounds(true);
  else if (view === "trends") await renderHistoryTrends();
  else if (view === "distribution") await renderHistoryDistribution();
  else if (view === "courses") await renderHistoryCourses();
  else if (view === "clubs") await renderHistoryClubs();
  else if (view === "shots") await renderHistoryShots();
  else if (view === "hole") await renderHistoryHole();
  else if (view === "reports") await renderHistoryReports();
  else if (view === "quality") await renderHistoryQuality();
  showStatus("historyStatus", "");
}

async function renderHistoryOverview() {
  const [overview, trends, rounds] = await Promise.all([
    api("/api/history/overview"),
    api("/api/history/trends"),
    api("/api/history/rounds?limit=10"),
  ]);
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("Rounds", overview.totalRounds, `${overview.mergedRounds} merged`)}
      ${card("18-hole rounds", overview.eighteenHoleRounds, `avg ${overview.average18 ?? "-"}`)}
      ${card("Courses", overview.courseCount, `${overview.geometryHoleCount} geometry holes`)}
      ${card("Shots", overview.shotCount, `${overview.scorecardsWithShots} scorecards with shots`)}
      ${card("Reports", overview.reportCount, "AI report archive")}
      ${card("Recent trend", overview.recentTrend.delta ?? "-", "last 5 vs previous 5")}
    </div>
    <div class="split">
      <div><h2>Score trend</h2><div class="chart">${lineChart(trends.points || [])}</div></div>
      <div><h2>Recent rounds</h2>${roundsTable(rounds.rounds || [])}</div>
    </div>`;
  wireRoundButtons();
}

async function renderHistoryRounds(scorecards) {
  const qs = new URLSearchParams({ limit: scorecards ? "30" : "160", include_holes: scorecards ? "1" : "0" });
  const courseKey = $("historyCourseSelect").value;
  if (courseKey) qs.set("course", courseKey);
  const data = await api(`/api/history/rounds?${qs.toString()}`);
  if (!scorecards) {
    $("historyContent").innerHTML = `<h2>打球时间线</h2>${roundsTable(data.rounds || [])}`;
    wireRoundButtons();
    return;
  }
  $("historyContent").innerHTML = `<h2>成绩卡历史</h2>${(data.rounds || []).map(scorecardBlock).join("") || '<div class="muted">No scorecards.</div>'}`;
  wireRoundButtons();
}

function roundsTable(rows) {
  return table(["Date", "Course", "Holes", "Score", "To par", "Shots", ""], rows.map(r => [
    esc((r.date || "").slice(0,10)),
    esc(r.course),
    r.holesCompleted,
    r.strokes ?? "",
    r.toPar == null ? "" : (r.toPar > 0 ? `+${r.toPar}` : r.toPar),
    r.hasShots ? '<span class="badge">shots</span>' : '<span class="badge">no shots</span>',
    String(r.id).startsWith("merged_") ? '<span class="muted">merged</span>' : `<button data-round="${esc(r.id)}">Analyze</button>`,
  ]));
}

function scorecardBlock(r) {
  const holes = r.holes || [];
  const pars = r.holePars || "";
  const cells = holes.map((h, idx) => {
    const par = Number(pars[idx] || 0);
    const diff = h.strokes != null && par ? Number(h.strokes) - par : null;
    const color = diff == null ? "#667085" : diff <= 0 ? "#147a4a" : diff === 1 ? "#8a6d1d" : "#b42318";
    const label = diff == null || diff === 0 ? "" : diff > 0 ? `+${diff}` : diff;
    return `<div class="card" style="padding:7px;text-align:center;min-width:54px">
      <div class="muted">${h.number || idx + 1}</div><div style="font-size:11px;color:#98a2b3">par ${par || "-"}</div>
      <div style="font-weight:700">${h.strokes ?? "-"}</div><div style="color:${color};font-size:12px">${label}</div>
    </div>`;
  }).join("");
  return `<div class="card" style="margin-bottom:12px">
    <div class="row"><div><b>${esc(r.course)}</b><div class="muted">${esc((r.date || "").slice(0,10))} · ${r.holesCompleted} holes</div></div>
    <div style="text-align:right"><div class="value">${r.strokes ?? "-"}</div><button data-round="${esc(r.id)}">Analyze</button></div></div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">${cells}</div>
  </div>`;
}

async function renderHistoryTrends() {
  const data = await api("/api/history/trends");
  $("historyContent").innerHTML = `
    <h2>总杆趋势</h2><div class="chart">${lineChart(data.points || [])}</div>
    <div class="split">
      <div><h2>Quarterly</h2>${periodTable(data.quarterly || [])}</div>
      <div><h2>Monthly</h2>${periodTable((data.monthly || []).slice(0,24))}</div>
    </div>`;
}

function periodTable(rows) {
  return table(["Period", "Rounds", "Avg", "Best", "Worst"], rows.map(r => [r.period, r.count, fmt(r.average), r.best, r.worst]));
}

async function renderHistoryDistribution() {
  const data = await api("/api/history/distribution");
  const maxFam = Math.max(...(data.families || []).map(x => x.count), 1);
  const maxHist = Math.max(...(data.histogram || []).map(x => x.count), 1);
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("18-hole rounds", data.total)}
      ${card("Average", data.average)}
      ${card("Best", data.best)}
      ${card("Worst", data.worst)}
    </div>
    <div class="split">
      <div><h2>杆数家族</h2>${table(["Bucket","Count","Pct",""], (data.families || []).map(r => [r.bucket, r.count, pct(r.pct), bar(r.count, maxFam)]))}</div>
      <div><h2>5 杆一档</h2>${table(["Bucket","Count",""], (data.histogram || []).map(r => [r.bucket, r.count, bar(r.count, maxHist)]))}</div>
    </div>`;
}

async function renderHistoryCourses() {
  const data = await api("/api/history/courses");
  state.courses = data.courses || [];
  const totalRounds = state.courses.reduce((sum, c) => sum + (c.count || 0), 0);
  const totalRaw = state.courses.reduce((sum, c) => sum + (c.rawScorecards || 0), 0);
  const total18 = state.courses.reduce((sum, c) => sum + (c.count18 || 0), 0);
  const totalShots = state.courses.reduce((sum, c) => sum + (c.shotCount || 0), 0);
  const fullGeo = state.courses.filter(c => c.geometryCoveragePct >= 100).length;
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("Courses", data.total)}
      ${card("Rounds", totalRounds, `${totalRaw} raw · ${total18} 18H`)}
      ${card("Shots", totalShots)}
      ${card("Full geometry", fullGeo, "courses")}
    </div>
    <h2>球场地图</h2><div id="courseMap"></div>
    <h2>球场列表</h2>${coursesTable(state.courses)}`;
  renderCourseMap(state.courses);
  wireRoundButtons();
}

function coursesTable(rows) {
  return table(["Course", "Rounds", "Raw", "Merged", "18H", "9H", "Holes", "Shots", "Avg", "Recent10", "Best", "Worst", "+/-", "Last", "Geometry", ""], rows.map(c => [
    courseCell(c),
    c.count,
    c.rawScorecards,
    c.mergedPairs,
    c.count18,
    c.count9,
    c.totalHoles,
    c.shotCount,
    fmt(c.average18),
    fmt(c.recent10Average18),
    c.best18 ?? "",
    c.worst18 ?? "",
    c.averageToPar18 == null ? "" : (c.averageToPar18 > 0 ? `+${fmt(c.averageToPar18)}` : fmt(c.averageToPar18)),
    esc((c.lastPlayed || "").slice(0,10)),
    `${c.geometryHoles}/${c.geometryPossibleHoles || "-"} (${fmt(c.geometryCoveragePct)}%)`,
    `<button data-course="${esc(c.key)}">Detail</button>`,
  ]));
}

function statChip(label, value) {
  return `<span class="mini-stat">${esc(label)} <b>${esc(value ?? "-")}</b></span>`;
}

function signed(v) {
  if (v == null || v === "") return "";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1);
}

function courseCell(c) {
  return `<div class="course-cell">
    <div class="course-name">${esc(c.name)}</div>
    <div class="mini-stats">
      ${statChip("场", c.count)}
      ${statChip("raw", c.rawScorecards)}
      ${statChip("merge", c.mergedPairs)}
      ${statChip("18H", c.count18)}
      ${statChip("9H", c.count9)}
      ${statChip("洞", c.totalHoles)}
      ${statChip("shots", c.shotCount)}
      ${statChip("均", fmt(c.average18))}
      ${statChip("近10", fmt(c.recent10Average18))}
      ${statChip("best", c.best18)}
      ${statChip("worst", c.worst18)}
      ${statChip("+/-", signed(c.averageToPar18))}
      ${statChip("geo", `${c.geometryHoles}/${c.geometryPossibleHoles || "-"} ${fmt(c.geometryCoveragePct)}%`)}
    </div>
  </div>`;
}

function renderCourseMap(courses) {
  if (!window.L) {
    $("courseMap").innerHTML = '<div class="muted" style="padding:14px">Leaflet failed to load.</div>';
    return;
  }
  if (state.courseMap) {
    state.courseMap.remove();
    state.courseMap = null;
  }
  const withLoc = courses.filter(c => c.lat != null && c.lon != null);
  const map = L.map("courseMap").setView([35, 110], 4);
  state.courseMap = map;
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution:"Esri", maxZoom:18 }).addTo(map);
  const bounds = [];
  withLoc.forEach(c => {
    const marker = L.circleMarker([c.lat, c.lon], { radius: Math.min(18, 6 + Math.log(c.count + 1) * 3), color:"#1f6feb", fillColor:"#1f6feb", fillOpacity:0.45, weight:2 });
    marker.bindPopup(`<b>${esc(c.name)}</b><br>${c.count} rounds · avg ${c.average18 ?? "-"}<br><button data-course-popup="${esc(c.key)}">Open detail</button>`);
    marker.addTo(map);
    bounds.push([c.lat, c.lon]);
  });
  if (bounds.length) map.fitBounds(bounds, { padding:[28,28] });
  map.on("popupopen", () => {
    document.querySelectorAll("[data-course-popup]").forEach(btn => {
      btn.onclick = () => renderCourseDetail(btn.dataset.coursePopup).catch(e => showStatus("historyStatus", e.message, true));
    });
  });
  setTimeout(() => map.invalidateSize(), 0);
}

async function renderCourseDetail(key) {
  const data = await api(`/api/history/course?key=${encodeURIComponent(key)}`);
  const c = data.course;
  $("historyContent").innerHTML = `
    <h2>${esc(c.name)}</h2>
    <div class="cards">
      ${card("Rounds", c.rounds)}
      ${card("Raw scorecards", c.rawScorecards, `${c.mergedPairs} merged pairs`)}
      ${card("18-hole rounds", c.rounds18, `${c.rounds9} 9H · ${c.incompleteRounds} incomplete`)}
      ${card("Total holes", c.totalHoles)}
      ${card("Shots", c.shotCount)}
      ${card("18-hole avg", c.average18, `recent10 ${c.recent10Average18 ?? "-"}`)}
      ${card("Best", c.best18)}
      ${card("Worst", c.worst18)}
      ${card("Avg +/-", c.averageToPar18 == null ? "-" : (c.averageToPar18 > 0 ? `+${c.averageToPar18}` : c.averageToPar18))}
      ${card("Geometry", `${c.geometryHoles}/${c.geometryPossibleHoles || "-"}`, `${c.geometryCoveragePct}%`)}
    </div>
    <div class="split">
      <div><h2>Course trend</h2><div class="chart">${lineChart(data.trend || [])}</div></div>
      <div><h2>Hole averages</h2>${table(["Hole","Samples","Avg vs par/score"], (data.holeAverages || []).map(h => [h.hole, h.sampleSize, fmt(h.averageVsParOrScore)]))}</div>
    </div>
    <h2>Variants / raw scorecards</h2>
    ${table(["Variant", "Raw scorecards"], (c.variants || []).map(v => [esc(v.name), v.rawScorecards]))}
    <h2>Rounds</h2>${roundsTable(data.rounds || [])}`;
  wireRoundButtons();
}

async function renderHistoryClubs() {
  const data = await api("/api/history/clubs");
  const maxMedian = Math.max(...(data.clubs || []).map(c => c.median || 0), 1);
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("Shots used", data.totalShotsUsed)}
      ${card("Outliers dropped", data.droppedOutliers)}
      ${card("Clubs", (data.clubs || []).length)}
    </div>
    ${table(["Club","N","P10","Median","P90","Confidence",""], (data.clubs || []).map(c => [
      esc(c.clubName) + (c.retired ? ' <span class="badge">retired</span>' : ""),
      c.sampleSize, fmt(c.p10), fmt(c.median), fmt(c.p90), c.confidence, bar(c.median || 0, maxMedian)
    ]))}`;
}

async function renderHistoryShots() {
  const qs = new URLSearchParams({ limit: "400" });
  if ($("historyClubSelect").value) qs.set("club", $("historyClubSelect").value);
  if ($("historyCourseSelect").value) qs.set("course", $("historyCourseSelect").value);
  const data = await api(`/api/history/shots?${qs.toString()}`);
  $("historyContent").innerHTML = `<h2>击球记录</h2>${table(["Date","Course","Hole","Club","Type","Meters","End lie",""], (data.shots || []).map(s => [
    esc(s.date), esc(s.course), s.hole, esc(s.clubName), esc(s.type), fmt(s.meters), esc(s.endLie),
    s.globalId ? `<button data-hole-open="${s.globalId}:${s.localHole}">Hole history</button>` : ""
  ]))}`;
  wireRoundButtons();
}

async function renderHistoryHole() {
  const selected = $("historyHoleSelect").value || (state.holes[0] ? `${state.holes[0].globalId}:${state.holes[0].holeNumber}` : "");
  if (!selected) {
    $("historyContent").innerHTML = '<div class="muted">No geometry holes available.</div>';
    return;
  }
  const [globalId, localHole] = selected.split(":");
  const data = await api(`/api/history/hole?global_id=${encodeURIComponent(globalId)}&local_hole=${encodeURIComponent(localHole)}&overlay=1`);
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("Rounds", data.roundCount)}
      ${card("Shots", data.shotCount)}
      ${card("Average score", data.averageScore)}
      ${card("Geometry", data.hasMeshes ? "mesh" : data.hasHazards ? "hazards" : "missing")}
    </div>
    <div class="overlay">${data.overlaySvg || ""}</div>
    <h2 style="margin-top:14px">Rounds on this hole</h2>
    ${table(["Date","Course","Score","To par","Shots",""], (data.rounds || []).map(r => [
      esc((r.date || "").slice(0,10)), esc(r.course), r.strokes ?? "", r.toPar == null ? "" : r.toPar, (r.shots || []).length,
      `<button data-round-hole="${r.scorecardId}:${r.hole}">Analyze</button>`
    ]))}`;
}

async function renderHistoryReports() {
  const data = await api("/api/history/reports");
  $("historyContent").innerHTML = `<h2>AI report archive</h2>${table(["Scorecard","Kind","Title","Path","Preview"], (data.reports || []).map(r => [
    r.scorecardId, r.kind, esc(r.title), esc(r.path), `<span class="muted">${esc((r.preview || "").slice(0,220))}</span>`
  ]))}`;
}

async function renderHistoryQuality() {
  const data = await api("/api/history/data-quality");
  const s = data.summary || {};
  $("historyContent").innerHTML = `
    <div class="cards">
      ${card("Scorecards", s.scorecards)}
      ${card("Shots ready", s.shotsReady)}
      ${card("Missing shots", s.missingShots)}
      ${card("Missing geometry holes", s.missingGeometryHoles)}
      ${card("Reports", s.reports)}
      ${card("Low club samples", s.lowClubSamples)}
    </div>
    <div class="split">
      <div><h2>Missing shots</h2>${roundsTable(data.missingShots || [])}</div>
      <div><h2>Low club samples</h2>${table(["Club","N","Median","Confidence"], (data.lowClubSamples || []).map(c => [esc(c.clubName), c.sampleSize, fmt(c.median), c.confidence]))}</div>
    </div>
    <h2>Missing geometry</h2>
    ${table(["Date","Course","Hole","GlobalId","Local","Hazards","Meshes"], (data.missingGeometry || []).map(g => [
      esc((g.date || "").slice(0,10)), esc(g.course), g.hole, g.globalId, g.localHole, g.hasHazards ? "yes" : "no", g.hasMeshes ? "yes" : "no"
    ]))}`;
  wireRoundButtons();
}

function wireRoundButtons() {
  document.querySelectorAll("[data-round]").forEach(btn => {
    btn.onclick = () => {
      $("roundSelect").value = btn.dataset.round;
      document.querySelector('[data-tab="import"]').click();
      analyzeRound().catch(e => showStatus("importStatus", e.message, true));
    };
  });
  document.querySelectorAll("[data-round-hole]").forEach(btn => {
    btn.onclick = () => {
      const [sid, hole] = btn.dataset.roundHole.split(":");
      $("roundSelect").value = sid;
      $("holeSelect").value = hole;
      document.querySelector('[data-tab="import"]').click();
      analyzeGarmin().catch(e => showStatus("importStatus", e.message, true));
    };
  });
  document.querySelectorAll("[data-course]").forEach(btn => {
    btn.onclick = () => renderCourseDetail(btn.dataset.course).catch(e => showStatus("historyStatus", e.message, true));
  });
  document.querySelectorAll("[data-hole-open]").forEach(btn => {
    btn.onclick = () => {
      $("historyHoleSelect").value = btn.dataset.holeOpen;
      state.historyView = "hole";
      document.querySelectorAll("[data-history]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.history === "hole")));
      renderHistoryHole().catch(e => showStatus("historyStatus", e.message, true));
    };
  });
}

async function createManual() {
  const [globalId, holeNumber] = $("holeGeometrySelect").value.split(":").map(Number);
  const row = await api("/api/manual-rounds", { method:"POST", body: JSON.stringify({ globalId, localHole: holeNumber, courseName: $("manualCourseName").value }) });
  state.manualId = row.id;
  state.manualHole = row.localHole || row.hole;
  showStatus("manualStatus", `Created ${row.id}`);
  await refreshManualShots();
}

function gpsInto(latId, lonId) {
  showStatus("manualStatus", "Reading GPS...");
  navigator.geolocation.getCurrentPosition(pos => {
    $(latId).value = pos.coords.latitude.toFixed(7);
    $(lonId).value = pos.coords.longitude.toFixed(7);
    showStatus("manualStatus", `GPS accuracy ${Math.round(pos.coords.accuracy)}m`);
  }, err => showStatus("manualStatus", err.message, true), { enableHighAccuracy:true, timeout:10000 });
}

async function addManualShot() {
  if (!state.manualId) await createManual();
  const payload = {
    clubName: $("clubName").value,
    shotType: $("shotType").value,
    start: { lat: Number($("startLat").value), lon: Number($("startLon").value), lie: "Unknown" },
    end: { lat: Number($("endLat").value), lon: Number($("endLon").value), lie: "Unknown" },
  };
  await api(`/api/manual-rounds/${encodeURIComponent(state.manualId)}/shots`, { method:"POST", body: JSON.stringify(payload) });
  $("startLat").value = $("endLat").value; $("startLon").value = $("endLon").value;
  $("endLat").value = ""; $("endLon").value = "";
  showStatus("manualStatus", "Shot added.");
  await refreshManualShots();
}

async function refreshManualShots() {
  if (!state.manualId) {
    $("manualShots").innerHTML = '<div class="muted">No manual round yet.</div>';
    return;
  }
  const row = await api(`/api/manual-rounds/${encodeURIComponent(state.manualId)}`);
  $("manualShots").innerHTML = table(["#", "Club", "Type", "Start", "End", ""], (row.shots || []).map(s => [
    s.shotOrder,
    s.clubName,
    s.shotType,
    pointText(s.start),
    pointText(s.end),
    `<button data-edit-shot="${s.id}">Edit</button> <button data-delete-shot="${s.id}">Delete</button>`,
  ]));
  document.querySelectorAll("[data-edit-shot]").forEach(btn => {
    btn.onclick = () => {
      const shot = (row.shots || []).find(s => String(s.id) === String(btn.dataset.editShot));
      if (!shot) return;
      state.editShotId = shot.id;
      $("clubName").value = shot.clubName || "";
      $("shotType").value = shot.shotType || "";
      $("startLat").value = shot.start?.lat ?? "";
      $("startLon").value = shot.start?.lon ?? "";
      $("endLat").value = shot.end?.lat ?? "";
      $("endLon").value = shot.end?.lon ?? "";
      showStatus("manualStatus", `Editing shot ${shot.shotOrder}`);
    };
  });
  document.querySelectorAll("[data-delete-shot]").forEach(btn => {
    btn.onclick = async () => {
      await api(`/api/manual-rounds/${encodeURIComponent(state.manualId)}/shots/${encodeURIComponent(btn.dataset.deleteShot)}`, { method:"DELETE" });
      await refreshManualShots();
    };
  });
}

function pointText(p) {
  if (!p) return "";
  return `${Number(p.lat).toFixed(5)}, ${Number(p.lon).toFixed(5)}`;
}

async function analyzeManual() {
  if (!state.manualId) throw new Error("Create a manual round first.");
  const analysis = await api(`/api/analysis?manual_id=${encodeURIComponent(state.manualId)}&hole=${encodeURIComponent(state.manualHole || 1)}`);
  renderAnalysis(analysis);
  document.querySelector('[data-tab="review"]').click();
}

async function saveManualShot() {
  if (!state.manualId || !state.editShotId) throw new Error("Choose a manual shot to edit first.");
  const payload = {
    clubName: $("clubName").value,
    shotType: $("shotType").value,
    start: { lat: Number($("startLat").value), lon: Number($("startLon").value), lie: "Unknown" },
    end: { lat: Number($("endLat").value), lon: Number($("endLon").value), lie: "Unknown" },
  };
  await api(`/api/manual-rounds/${encodeURIComponent(state.manualId)}/shots/${encodeURIComponent(state.editShotId)}`, { method:"PUT", body: JSON.stringify(payload) });
  state.editShotId = null;
  showStatus("manualStatus", "Shot updated.");
  await refreshManualShots();
}

async function syncGarmin() {
  showStatus("importStatus", "Running fetch.py --shots. This can take a few minutes...");
  $("syncBtn").disabled = true;
  try {
    const result = await api("/api/sync", { method:"POST", body: JSON.stringify({ shots:true }) });
    showStatus("importStatus", result.tail || "Sync complete.");
    await loadInitial();
  } finally {
    $("syncBtn").disabled = false;
  }
}

initTabs();
loadInitial().catch(e => showStatus("importStatus", e.message, true));
$("analyzeBtn").onclick = () => analyzeGarmin().catch(e => showStatus("importStatus", e.message, true));
$("roundAnalyzeBtn").onclick = () => analyzeRound().catch(e => showStatus("importStatus", e.message, true));
$("latestBtn").onclick = async () => { const s = await api("/api/status"); if (s.latest) $("roundSelect").value = s.latest.id; };
$("syncBtn").onclick = () => syncGarmin().catch(e => showStatus("importStatus", e.message, true));
$("refreshHistoryBtn").onclick = () => { loadHistoryOptions().then(renderHistory).catch(e => showStatus("historyStatus", e.message, true)); };
$("historyCourseBtn").onclick = () => {
  const key = $("historyCourseSelect").value;
  if (key) renderCourseDetail(key).catch(e => showStatus("historyStatus", e.message, true));
};
$("historyHoleBtn").onclick = () => {
  state.historyView = "hole";
  document.querySelectorAll("[data-history]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.history === "hole")));
  renderHistoryHole().catch(e => showStatus("historyStatus", e.message, true));
};
$("historyCourseSelect").onchange = () => {
  if (["rounds","scorecards","shots"].includes(state.historyView)) renderHistory().catch(e => showStatus("historyStatus", e.message, true));
};
$("historyClubSelect").onchange = () => {
  if (state.historyView === "shots") renderHistory().catch(e => showStatus("historyStatus", e.message, true));
};
$("historyHoleSelect").onchange = () => {
  if (state.historyView === "hole") renderHistoryHole().catch(e => showStatus("historyStatus", e.message, true));
};
$("createManualBtn").onclick = () => createManual().catch(e => showStatus("manualStatus", e.message, true));
$("gpsStartBtn").onclick = () => gpsInto("startLat", "startLon");
$("gpsEndBtn").onclick = () => gpsInto("endLat", "endLon");
$("addShotBtn").onclick = () => addManualShot().catch(e => showStatus("manualStatus", e.message, true));
$("saveShotBtn").onclick = () => saveManualShot().catch(e => showStatus("manualStatus", e.message, true));
$("manualAnalyzeBtn").onclick = () => analyzeManual().catch(e => showStatus("manualStatus", e.message, true));
</script>
</body>
</html>
"""


def haversine_m(a: dict, b: dict) -> float | None:
    try:
        lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lon"]))
        lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lon"]))
    except Exception:
        return None
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(h))


RASTER_CACHE = ROOT / "output" / "hole_overlays"


def garmin_raster_url(global_id: int, local_hole: int, *, live: bool = False) -> str | None:
    try:
        info = inspect_release(load_release_pb(int(global_id), live))
    except Exception:
        return None
    for hole in info.get("holes", []) or []:
        if int(hole.get("hole") or -1) == int(local_hole):
            return hole.get("raster_url")
    return None


def garmin_raster_cache_path(url: str) -> Path:
    name = url.split("/", 1)[-1].split("?")[0].split("/")[-1]
    return RASTER_CACHE / f"img_{name}"


def ensure_garmin_raster(global_id: int, local_hole: int) -> tuple[Path | None, str | None]:
    cached = sorted(RASTER_CACHE.glob(f"img_gid{int(global_id):06d}_hole{int(local_hole):02d}_*.jpg"))
    if cached:
        return cached[0], None
    url = garmin_raster_url(global_id, local_hole)
    if not url:
        return None, "No Garmin raster URL in CourseView release."
    RASTER_CACHE.mkdir(parents=True, exist_ok=True)
    errors = []
    for candidate in [url, garmin_raster_url(global_id, local_hole, live=True)]:
        if not candidate:
            continue
        path = garmin_raster_cache_path(candidate)
        if path.exists():
            return path, None
        req = Request(candidate, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(req, timeout=30) as response:
                path.write_bytes(response.read())
            return path, None
        except Exception as exc:
            errors.append(str(exc))
    return None, "Garmin raster URL exists but could not be fetched or cached locally: " + "; ".join(errors)


def raster_dimensions(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "AICaddieHTTP/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[web] {self.address_string()} {fmt % args}")

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: str, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_error(self, exc: Exception) -> None:
        traceback.print_exc()
        self._json({"error": str(exc)}, status=500)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path == "/":
                self._text(INDEX_HTML)
            elif parsed.path == "/api/status":
                self._json({
                    "rounds": list_rounds(),
                    "latest": latest_round_with_shots(),
                    "availableHoles": available_holes(),
                    "manualRounds": list_manual_rounds(),
                    "historyStatus": history_status(),
                })
            elif parsed.path == "/api/history/overview":
                self._json(history_overview())
            elif parsed.path == "/api/history/rounds":
                self._json(history_rounds(
                    limit=int(qs.get("limit", ["120"])[0]),
                    year=qs.get("year", [None])[0],
                    course_key_filter=qs.get("course", [None])[0],
                    include_holes=qs.get("include_holes", ["0"])[0] in {"1", "true", "yes"},
                ))
            elif parsed.path == "/api/history/trends":
                self._json(history_trends())
            elif parsed.path == "/api/history/distribution":
                self._json(history_distribution())
            elif parsed.path == "/api/history/courses":
                self._json(history_courses())
            elif parsed.path == "/api/history/course":
                key = qs.get("key", [None])[0]
                if not key:
                    raise ValueError("key is required")
                self._json(history_course_detail(key))
            elif parsed.path == "/api/history/clubs":
                self._json(history_clubs())
            elif parsed.path == "/api/history/shots":
                self._json(history_shots(
                    limit=int(qs.get("limit", ["300"])[0]),
                    club=qs.get("club", [None])[0],
                    course_key_filter=qs.get("course", [None])[0],
                ))
            elif parsed.path == "/api/history/hole":
                global_id = int(qs.get("global_id", ["0"])[0])
                local_hole = int(qs.get("local_hole", ["0"])[0])
                if not global_id or not local_hole:
                    raise ValueError("global_id and local_hole are required")
                self._json(history_hole(global_id, local_hole, include_overlay=qs.get("overlay", ["1"])[0] != "0"))
            elif parsed.path == "/api/history/reports":
                self._json(history_reports(limit=int(qs.get("limit", ["80"])[0])))
            elif parsed.path == "/api/history/data-quality":
                self._json(history_data_quality())
            elif parsed.path == "/api/analysis":
                hole = int(qs.get("hole", ["1"])[0])
                analysis = build_hole_analysis(
                    scorecard_id=qs.get("scorecard_id", [None])[0],
                    manual_round_id=qs.get("manual_id", [None])[0],
                    hole_number=hole,
                )
                self._json(analysis)
            elif parsed.path == "/api/round-analysis":
                scorecard_id = qs.get("scorecard_id", [None])[0]
                if not scorecard_id:
                    raise ValueError("scorecard_id is required")
                self._json(build_round_analysis(scorecard_id=scorecard_id))
            elif parsed.path == "/api/overlay-geojson":
                hole = int(qs.get("hole", ["1"])[0])
                source = qs.get("source", ["garmin"])[0]
                rid = qs.get("id", [None])[0]
                analysis = build_hole_analysis(
                    scorecard_id=rid if source == "garmin" else None,
                    manual_round_id=rid if source == "manual" else None,
                    hole_number=hole,
                )
                raster_path, raster_error = ensure_garmin_raster(int(analysis["globalId"]), int(analysis["localHole"]))
                endpoint = f"/api/raster?global_id={analysis['globalId']}&local_hole={analysis['localHole']}" if raster_path else None
                self._json({
                    "schema": "ai-caddie-overlay-geojson-v1",
                    "roundId": analysis["roundId"],
                    "hole": analysis["hole"],
                    "globalId": analysis["globalId"],
                    "localHole": analysis["localHole"],
                    "geojson": overlay_geojson(analysis),
                    "strategy": strategy_distances(analysis),
                    "raster": {
                        "available": bool(raster_path),
                        "endpoint": endpoint,
                        "reason": raster_error,
                        **(raster_dimensions(raster_path) or {}),
                    },
                })
            elif parsed.path == "/api/overlay":
                hole = int(qs.get("hole", ["1"])[0])
                source = qs.get("source", ["garmin"])[0]
                rid = qs.get("id", [None])[0]
                analysis = build_hole_analysis(
                    scorecard_id=rid if source == "garmin" else None,
                    manual_round_id=rid if source == "manual" else None,
                    hole_number=hole,
                )
                self._text(render_svg(analysis), content_type="image/svg+xml; charset=utf-8")
            elif parsed.path == "/api/raster":
                global_id = int(qs.get("global_id", ["0"])[0])
                local_hole = int(qs.get("local_hole", ["0"])[0])
                if not global_id or not local_hole:
                    raise ValueError("global_id and local_hole are required")
                path, error = ensure_garmin_raster(global_id, local_hole)
                if error or path is None:
                    self._json({"error": error or "raster unavailable"}, status=404)
                else:
                    self._bytes(path.read_bytes(), "image/jpeg")
            elif parsed.path.startswith("/api/manual-rounds/"):
                manual_id = parsed.path.split("/")[3]
                self._json(load_manual_round(manual_id))
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/sync":
                body = self._read_json()
                cmd = [sys.executable, "fetch.py"]
                if body.get("shots", True):
                    cmd.append("--shots")
                proc = subprocess.run(cmd, cwd=".", text=True, capture_output=True, timeout=900)
                tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-12:])
                self._json({"ok": proc.returncode == 0, "returncode": proc.returncode, "tail": tail}, status=200 if proc.returncode == 0 else 500)
            elif parsed.path == "/api/manual-rounds":
                body = self._read_json()
                row = create_manual_round(int(body["globalId"]), int(body["localHole"]), body.get("courseName"), body.get("teeBox"))
                self._json(row)
            elif parsed.path.startswith("/api/manual-rounds/") and parsed.path.endswith("/shots"):
                manual_id = parsed.path.split("/")[3]
                body = self._read_json()
                if body.get("meters") is None and body.get("start") and body.get("end"):
                    meters = haversine_m(body["start"], body["end"])
                    if meters is not None:
                        body["meters"] = round(meters, 1)
                row = append_manual_shot(manual_id, body)
                self._json(row)
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)

    def do_PUT(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/manual-rounds/") and "/shots/" in parsed.path:
                parts = parsed.path.split("/")
                manual_id = parts[3]
                shot_id = parts[5]
                body = self._read_json()
                if body.get("meters") is None and body.get("start") and body.get("end"):
                    meters = haversine_m(body["start"], body["end"])
                    if meters is not None:
                        body["meters"] = round(meters, 1)
                self._json(update_manual_shot(manual_id, shot_id, body))
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/manual-rounds/") and "/shots/" in parsed.path:
                parts = parsed.path.split("/")
                manual_id = parts[3]
                shot_id = parts[5]
                delete_manual_shot(manual_id, shot_id)
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[ok] AI Caddie web running at http://{args.host}:{args.port}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
