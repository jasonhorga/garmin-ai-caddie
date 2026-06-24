"""Local/private AI Caddie Web MVP.

Run:
  uv run python ai_caddie_web.py --port 8765
"""

from __future__ import annotations

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
import traceback

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

from ai_caddie.geometry.inspect_courseview_release import inspect_release, load_release_pb

from ai_caddie.analysis import build_hole_analysis, build_round_analysis, overlay_geojson, render_svg, strategy_distances
from ai_caddie.data import (
    EARTH_RADIUS_M,
    ROOT,
    SHOT_DIR,
    append_manual_shot,
    available_holes,
    create_manual_round,
    delete_manual_shot,
    latest_round_with_shots,
    load_shot_file,
    load_manual_round,
    load_scorecard,
    list_manual_rounds,
    list_rounds,
    scorecard_snapshot_id,
    snapshot_file,
    update_manual_shot,
    write_json,
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
from ai_caddie.garmin.garmin_auth import auth_headers, ensure_web_auth


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
    .decision-card { border:1px solid #cbd5e1; border-radius:8px; background:#fbfdff; padding:12px; margin:6px 0 12px; }
    .decision-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:10px; }
    .decision-title { font-size:16px; font-weight:760; line-height:1.35; }
    .decision-sub { color:var(--muted); font-size:12px; margin-top:3px; }
    .decision-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:9px; }
    .decision-block { border:1px solid #e2e8f0; border-radius:7px; background:#fff; padding:9px; min-width:0; }
    .decision-block .label { color:var(--muted); font-size:11px; margin-bottom:4px; }
    .decision-block .value { font-size:13px; line-height:1.45; }
    .decision-pill { display:inline-flex; align-items:center; border-radius:999px; padding:3px 8px; background:#eef6ff; color:#174ea6; font-size:12px; font-weight:700; white-space:nowrap; }
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
    .overlay-view-panel { background:#fff; }
    .overlay-body { background:#f8fafc; min-height:360px; }
    .overlay-body svg { width:100%; height:auto; display:block; }
    .satellite-wrap, .raster-wrap { display:flex; justify-content:center; align-items:flex-start; padding:12px; background:#edf2f7; }
    .overlay-map { width:min(730px,100%); background:#dbe4ef; }
    .static-course-viewport { position:relative; width:min(730px,100%); aspect-ratio:1 / 1; overflow:hidden; border:1px solid #cbd5e1; background:#dbe4ef; touch-action:none; cursor:grab; }
    .static-course-viewport.dragging { cursor:grabbing; }
    .static-course-layer { position:absolute; inset:0; transform-origin:center center; z-index:1; }
    .static-course-overlay-host { position:absolute; inset:0; z-index:2; pointer-events:none; }
    .static-course-img, .static-course-overlay { position:absolute; inset:0; width:100%; height:100%; display:block; }
    .static-course-img { object-fit:cover; user-select:none; -webkit-user-drag:none; }
    .static-geometry-svg { width:100%; height:100%; display:block; background:#90c2f9; }
    .raster-wrap .static-course-img { object-fit:contain; background:#90c2f9; }
    .static-course-overlay { pointer-events:none; overflow:visible; }
    .zoom-toolbar { display:inline-flex; gap:6px; align-items:center; }
    .zoom-toolbar button { width:30px; min-height:28px; padding:0; border-radius:6px; font-weight:750; }
    .overlay-empty { padding:16px; color:var(--muted); font-size:12px; }
    .map-point { background:transparent; border:0; }
    .map-point span { display:grid; place-items:center; width:26px; height:26px; border:2px solid #fff; border-radius:999px; box-shadow:0 1px 5px rgba(0,0,0,.4); color:#fff; font-size:12px; font-weight:750; line-height:1; }
    .shot-point span { background:#1f6feb; }
    .target-point span { background:#064e3b; }
    .overlay-tools { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:9px 11px; border-bottom:1px solid var(--line); background:#fff; }
    .overlay-tools .tool-spacer { width:1px; height:22px; background:var(--line); margin:0 2px; flex:0 0 auto; }
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
        <div id="decisionCard"></div>
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
const state = { rounds: [], holes: [], courses: [], clubs: [], manualId: null, manualHole: null, editShotId: null, lastAnalysis: null, lastRoundAnalysis: null, preprocessedRoundId: null, historyView: "overview", courseMap: null, overlayView: "geometry", overlayMode: "replay", distanceUnit: "yd", currentOverlayVisuals: null };
const OVERLAY_MAX_ZOOM = 3.5;
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
  const sid = $("roundSelect").value;
  const hole = $("holeSelect").value;
  showStatus("importStatus", "Analyzing all holes for this round...");
  const roundAnalysis = await api(`/api/round-analysis?scorecard_id=${encodeURIComponent(sid)}`);
  renderRoundAnalysisSummary(roundAnalysis, false);
  state.lastRoundAnalysis = roundAnalysis;
  state.preprocessedRoundId = sid;
  showStatus("importStatus", `Round processed: ${roundAnalysis.summary.analyzedHoles} holes. Loading hole ${hole}...`);
  const analysis = await api(`/api/analysis?scorecard_id=${encodeURIComponent(sid)}&hole=${encodeURIComponent(hole)}`);
  renderAnalysis(analysis);
  showStatus("importStatus", `Round processed: ${roundAnalysis.summary.analyzedHoles} holes. Showing hole ${hole}.`);
}

async function loadSelectedHoleAfterPreprocess() {
  const sid = $("roundSelect").value;
  if (!sid || state.preprocessedRoundId !== sid) return;
  const hole = $("holeSelect").value;
  showStatus("importStatus", `Loading preprocessed hole ${hole}...`);
  const analysis = await api(`/api/analysis?scorecard_id=${encodeURIComponent(sid)}&hole=${encodeURIComponent(hole)}`);
  renderAnalysis(analysis);
  showStatus("importStatus", `Round already processed. Showing hole ${hole}.`);
}

async function analyzeRound() {
  showStatus("importStatus", "Analyzing round...");
  const sid = $("roundSelect").value;
  const analysis = await api(`/api/round-analysis?scorecard_id=${encodeURIComponent(sid)}`);
  renderRoundAnalysisSummary(analysis, true);
  state.lastRoundAnalysis = analysis;
  state.preprocessedRoundId = sid;
  showStatus("importStatus", "Round analysis ready.");
}

function renderRoundAnalysisSummary(analysis, clearOverlay=true) {
  $("reviewText").textContent = analysis.review;
  $("decisionCard").innerHTML = "";
  $("metrics").innerHTML = [
    ["Round", analysis.scorecardId],
    ["Analyzed", analysis.summary.analyzedHoles],
    ["High confidence", analysis.summary.confidenceCounts.high || 0],
    ["Missing geometry", analysis.summary.missingGeometry.length],
  ].map(([k,v]) => `<span class="metric">${k}<b>${v ?? "-"}</b></span>`).join("");
  if (clearOverlay) {
    $("overlayBox").innerHTML = '<div class="muted" style="padding:16px">Select a hole to load its map. This round has already been processed.</div>';
    $("shotsTable").innerHTML = "";
    $("routesTable").innerHTML = "";
  }
  $("roundTable").innerHTML = table(["Hole", "Confidence", "Shots", "Tee shot", "Risks", "Decision", "Best route"], analysis.holes.map(h => {
    const risk = (h.risks || []).slice(0,2).map(r => `${r.kind} ${r.distance_m}m`).join(", ");
    const best = h.bestRoute || {};
    const decision = h.decision || {};
    const tee = h.teeShotRecorded
      ? `${h.teeShotClub || ""} ${fmt(h.teeShotMeters)}`
      : `missing · first ${h.firstRecordedClub || ""} ${fmt(h.firstRecordedMeters)}`;
    return [h.hole, h.confidence, h.shotCount, tee, risk, `${decision.selectedOptionId || "-"} · ${decision.failureType || "-"}`, `${best.label || ""} ${fmt(best.carry_m)}`];
  }));
}

function listText(rows, fallback="-") {
  if (!rows || !rows.length) return fallback;
  return rows.map(x => esc(typeof x === "string" ? x : (x.text || x.reason || x.kind || ""))).filter(Boolean).join("<br>");
}

function clubsText(option) {
  const clubs = option?.clubRecommendation?.clubs || [];
  if (!clubs.length) return "-";
  return clubs.map(c => `${esc(c.clubName)}${c.sampleSize ? ` n=${esc(c.sampleSize)}` : ""}`).join(", ");
}

function decisionCard(a) {
  const plan = a.decisionPlan || {};
  const outcome = a.decisionOutcome || {};
  const selected = plan.selectedOption || {};
  if (!selected.id) {
    return '<div class="decision-card"><div class="decision-title">No tee decision available</div><div class="decision-sub">Candidate route or geometry data is missing.</div></div>';
  }
  const forbidden = (plan.forbiddenZones || []).map(z => `${z.kind}${z.distance_m != null ? ` ${fmt(z.distance_m)}m` : ""}`);
  const confidence = plan.confidence || {};
  const failure = outcome.failureType || "pending";
  return `
    <div class="decision-card">
      <div class="decision-head">
        <div>
          <div class="decision-title">${esc(selected.label)} · ${fmt(selected.carry_m)}m</div>
          <div class="decision-sub">${esc(selected.routeLabel || "tee-shot plan")} · clubs: ${clubsText(selected)}</div>
        </div>
        <span class="decision-pill">${esc(confidence.level || "unknown")} · ${esc(failure)}</span>
      </div>
      <div class="decision-grid">
        <div class="decision-block"><div class="label">Do this</div><div class="value">${esc(selected.routeLabel || selected.label)} to ${fmt(selected.carry_m)}m</div></div>
        <div class="decision-block"><div class="label">Avoid</div><div class="value">${forbidden.length ? forbidden.map(esc).join("<br>") : "No selected-route risk"}</div></div>
        <div class="decision-block"><div class="label">Evidence</div><div class="value">${listText(plan.evidence || [])}</div></div>
        <div class="decision-block"><div class="label">Outcome</div><div class="value">${esc(failure)}<br>${esc(outcome.modelUpdateSuggestion || "")}</div></div>
      </div>
    </div>`;
}

function renderAnalysis(a) {
  state.lastAnalysis = a;
  $("reviewText").textContent = a.review;
  const geometrySync = a.geometrySync
    ? (a.geometrySync.ok ? a.geometrySync.status : `failed: ${a.geometrySync.error || "unknown"}`)
    : "off";
  $("metrics").innerHTML = [
    ["Source", a.source],
    ["GlobalId", a.globalId],
    ["Local hole", a.localHole],
    ["Geometry", a.geometry.hasMeshes ? "mesh" : (a.geometry.hasHazards ? "hazards" : "missing")],
    ["Geo sync", geometrySync],
    ["Confidence", a.dataQuality.confidence],
  ].map(([k,v]) => `<span class="metric">${k}<b>${v ?? "-"}</b></span>`).join("");
  $("decisionCard").innerHTML = decisionCard(a);
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

function renderGeometryOverlay(id, svg) {
  const el = $(id);
  if (!el) return;
  const viewBox = String(svg || "").match(/viewBox="([^"]+)"/);
  let aspectStyle = "aspect-ratio:1 / 1";
  if (viewBox) {
    const parts = viewBox[1].trim().split(/\s+/).map(Number);
    if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3]) && parts[2] > 0 && parts[3] > 0) {
      aspectStyle = `aspect-ratio:${parts[2]} / ${parts[3]}`;
    }
  }
  let cleaned = String(svg || "");
  if (/style="[^"]*"/.test(cleaned)) {
    cleaned = cleaned.replace(/style="[^"]*"/, 'class="static-geometry-svg" preserveAspectRatio="xMidYMid meet"');
  } else {
    cleaned = cleaned.replace("<svg ", '<svg class="static-geometry-svg" preserveAspectRatio="xMidYMid meet" ');
  }
  el.innerHTML = `
    <div class="static-course-viewport" style="${aspectStyle}">
      <div class="static-course-layer">${cleaned}</div>
    </div>`;
  installOverlayZoom(id, null);
}

function setOverlayToolState() {
  document.querySelectorAll("[data-overlay-view]").forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.overlayView === state.overlayView)));
  document.querySelectorAll("[data-overlay-view-panel]").forEach(panel => panel.classList.toggle("hidden", panel.dataset.overlayViewPanel !== state.overlayView));
  document.querySelectorAll("[data-overlay-mode]").forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.overlayMode === state.overlayMode)));
  document.querySelectorAll("[data-distance-unit]").forEach(btn => btn.setAttribute("aria-selected", String(btn.dataset.distanceUnit === state.distanceUnit)));
  const panel = $("strategyPanel");
  if (panel) panel.classList.toggle("hidden", state.overlayMode !== "strategy");
}

async function renderOverlayComparison(a) {
  const geometryId = `geometryMap_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const mapId = `satMap_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const rasterId = `rasterMap_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const params = `source=${encodeURIComponent(a.source)}&id=${encodeURIComponent(a.roundId)}&hole=${encodeURIComponent(a.hole)}`;
  $("overlayBox").innerHTML = `
    <div class="overlay-stack">
      <div class="overlay-panel">
        <div class="overlay-tools">
          <span class="muted">视图</span>
          <button data-overlay-view="geometry">球道图</button>
          <button data-overlay-view="satellite">卫星图</button>
          <button data-overlay-view="raster">Garmin 730</button>
          <span class="tool-spacer"></span>
          <span class="muted">模式</span>
          <button data-overlay-mode="replay">回放</button>
          <button data-overlay-mode="strategy">策略距离</button>
          <span class="tool-spacer"></span>
          <span class="muted">单位</span>
          <button data-distance-unit="yd">码</button>
          <button data-distance-unit="m">米</button>
        </div>
        <div class="strategy-panel" id="strategyPanel"><div class="overlay-empty">Loading strategy distances...</div></div>
        <div class="overlay-view-panel" data-overlay-view-panel="geometry">
          <div class="overlay-title">
            <b>Prodgeometry overlay</b>
            <span class="zoom-toolbar" data-zoom-controls="${geometryId}">
              <span class="muted">local meters · feature polygons + shot route</span>
              <button type="button" data-zoom-action="out">−</button>
              <button type="button" data-zoom-action="reset">1×</button>
              <button type="button" data-zoom-action="in">+</button>
            </span>
          </div>
          <div class="satellite-wrap"><div class="overlay-map" id="${geometryId}"><div class="overlay-empty">Loading geometry...</div></div></div>
        </div>
        <div class="overlay-view-panel" data-overlay-view-panel="satellite">
          <div class="overlay-title">
            <b>Satellite comparison</b>
            <span class="zoom-toolbar" data-zoom-controls="${mapId}">
              <span class="muted">730-clipped Esri crop</span>
              <button type="button" data-zoom-action="out">−</button>
              <button type="button" data-zoom-action="reset">1×</button>
              <button type="button" data-zoom-action="in">+</button>
            </span>
          </div>
          <div class="satellite-wrap"><div class="overlay-map" id="${mapId}"></div></div>
        </div>
        <div class="overlay-view-panel" data-overlay-view-panel="raster">
          <div class="overlay-title">
            <b>Garmin hand-drawn raster</b>
            <span class="zoom-toolbar" data-zoom-controls="${rasterId}">
              <span class="muted">CourseView raster + same route</span>
              <button type="button" data-zoom-action="out">−</button>
              <button type="button" data-zoom-action="reset">1×</button>
              <button type="button" data-zoom-action="in">+</button>
            </span>
          </div>
          <div class="raster-wrap" id="rasterPanel"><div class="overlay-map" id="${rasterId}"><div class="overlay-empty">Loading Garmin raster...</div></div></div>
        </div>
      </div>
    </div>`;
  const [svg, geo] = await Promise.all([
    fetch(`/api/overlay?${params}`).then(r => r.text()),
    api(`/api/overlay-geojson?${params}`),
  ]);
  $("strategyPanel").innerHTML = strategyPanel(geo.strategy);
  setOverlayToolState();
  state.currentOverlayVisuals = {
    geometryId,
    satelliteId: mapId,
    rasterId,
    geometrySvg: svg,
    geojson: geo.geojson || geo,
    raster: geo.raster || {},
    satellite: geo.satellite || {},
    strategy: geo.strategy || {},
  };
  renderCurrentOverlayVisuals();
  bindOverlayToolHandlers();
}

const overlayZoom = new Map();

function bindOverlayToolHandlers() {
  document.querySelectorAll("[data-overlay-view]").forEach(btn => {
    btn.onclick = () => {
      state.overlayView = btn.dataset.overlayView;
      setOverlayToolState();
    };
  });
  document.querySelectorAll("[data-overlay-mode]").forEach(btn => {
    btn.onclick = () => {
      state.overlayMode = btn.dataset.overlayMode;
      renderCurrentOverlayVisuals();
    };
  });
  document.querySelectorAll("[data-distance-unit]").forEach(btn => {
    btn.onclick = () => {
      state.distanceUnit = btn.dataset.distanceUnit;
      renderCurrentOverlayVisuals();
    };
  });
}

function renderCurrentOverlayVisuals() {
  const payload = state.currentOverlayVisuals;
  if (!payload) return;
  if ($("strategyPanel")) $("strategyPanel").innerHTML = strategyPanel(payload.strategy);
  setOverlayToolState();
  renderGeometryOverlay(payload.geometryId, payload.geometrySvg || "");
  renderStaticSatellite(payload.satelliteId, payload.geojson, payload.strategy, payload.satellite || {}, payload.raster || {});
  renderRasterOverlay(payload.rasterId, payload.geojson, payload.raster, payload.strategy);
}

function expandedSquareBounds(bounds, padRatio=0.08) {
  if (!bounds || bounds.south == null || bounds.north == null || bounds.west == null || bounds.east == null) return null;
  const centerLat = (Number(bounds.south) + Number(bounds.north)) / 2;
  const centerLon = (Number(bounds.west) + Number(bounds.east)) / 2;
  const metersPerDegLat = 111320;
  const metersPerDegLon = Math.max(1, 111320 * Math.cos(centerLat * Math.PI / 180));
  const widthM = Math.max(30, (Number(bounds.east) - Number(bounds.west)) * metersPerDegLon);
  const heightM = Math.max(30, (Number(bounds.north) - Number(bounds.south)) * metersPerDegLat);
  const sideM = Math.max(widthM, heightM) * (1 + padRatio * 2);
  const halfLat = sideM / metersPerDegLat / 2;
  const halfLon = sideM / metersPerDegLon / 2;
  return {
    south: centerLat - halfLat,
    west: centerLon - halfLon,
    north: centerLat + halfLat,
    east: centerLon + halfLon,
  };
}

function esriExportUrl(bounds) {
  const bbox = [bounds.west, bounds.south, bounds.east, bounds.north].map(v => Number(v).toFixed(8)).join(",");
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&imageSR=4326&size=1000,1000&format=jpg&f=image`;
}

function geoProjector(bounds) {
  const west = Number(bounds.west), east = Number(bounds.east), south = Number(bounds.south), north = Number(bounds.north);
  const lonSpan = Math.max(1e-9, east - west);
  const latSpan = Math.max(1e-9, north - south);
  const xy = coord => {
    if (!coord || coord.length < 2) return null;
    return [
      ((Number(coord[0]) - west) / lonSpan) * 1000,
      ((north - Number(coord[1])) / latSpan) * 1000,
    ];
  };
  return {
    pointFromCoord: xy,
    pointFromFeature: feature => xy(feature?.geometry?.coordinates),
    pointFromShotStart: feature => xy(feature?.geometry?.coordinates?.[0]),
    pointFromShotEnd: feature => xy(feature?.geometry?.coordinates?.[1]),
    pointFromStrategy: row => row?.lon == null || row?.lat == null ? null : xy([row.lon, row.lat]),
    pointFromStrategyPoint: row => row?.lon == null || row?.lat == null ? null : xy([row.lon, row.lat]),
    polygonFromFeature: feature => {
      const ring = feature?.geometry?.coordinates?.[0];
      if (!Array.isArray(ring)) return null;
      const pts = ring.map(xy).filter(Boolean);
      return pts.length >= 3 ? pts : null;
    },
  };
}

function localProjector(frame) {
  if (!frame || !frame.tee || !frame.target) return null;
  const tee = frame.tee.map(Number);
  const target = frame.target.map(Number);
  const dx = target[0] - tee[0], dy = target[1] - tee[1];
  const len = Math.hypot(dx, dy);
  let ux = 1, uy = 0, vx = 0, vy = 1;
  if (len >= 1) {
    vx = -dx / len;
    vy = -dy / len;
    ux = dy / len;
    uy = -dx / len;
  }
  const minX = Number(frame.minX), maxX = Number(frame.maxX), minY = Number(frame.minY), maxY = Number(frame.maxY);
  const rawW = Math.max(1, maxX - minX);
  const rawH = Math.max(1, maxY - minY);
  const pad = 58;
  const scale = Math.min((1000 - pad * 2) / rawW, (1000 - pad * 2) / rawH);
  const offX = (1000 - rawW * scale) / 2;
  const offY = (1000 - rawH * scale) / 2;
  const xyLocal = local => {
    if (!local || local.length < 2) return null;
    const nx = Number(local[0]) - tee[0];
    const ny = Number(local[1]) - tee[1];
    const rx = nx * ux + ny * uy;
    const ry = nx * vx + ny * vy;
    return [offX + (rx - minX) * scale, offY + (ry - minY) * scale];
  };
  return {
    pointFromFeature: feature => xyLocal(feature?.properties?.local),
    pointFromShotStart: feature => xyLocal(feature?.properties?.startLocal),
    pointFromShotEnd: feature => xyLocal(feature?.properties?.endLocal),
    pointFromStrategy: row => xyLocal(row?.local),
    pointFromStrategyPoint: row => xyLocal(row?.local),
    polygonFromFeature: feature => {
      const ring = feature?.properties?.localRing;
      if (!Array.isArray(ring)) return null;
      const pts = ring.map(xyLocal).filter(Boolean);
      return pts.length >= 3 ? pts : null;
    },
    trianglesFromFeature: feature => {
      const tris = feature?.properties?.localTriangles;
      if (!Array.isArray(tris)) return null;
      return tris.map(tri => tri.map(xyLocal).filter(Boolean)).filter(tri => tri.length === 3);
    },
  };
}

function rasterPixelProjector(raster, fallbackFrame) {
  const w = Number(raster?.width || raster?.pixelFit?.rasterSize?.[0] || 730);
  const h = Number(raster?.height || raster?.pixelFit?.rasterSize?.[1] || 730);
  const fit = raster?.pixelFit;
  const matrix = fit && fit.valid !== false ? fit.matrix : null;
  const fallback = localProjector(fallbackFrame);

  const scalePoint = point => {
    if (!point) return null;
    return [Number(point.x) / Math.max(1, w - 1) * 1000, Number(point.y) / Math.max(1, h - 1) * 1000];
  };
  const projectLocal = local => {
    if (!local || local.length < 2 || !matrix) return fallback ? fallback.pointFromStrategy({ local }) : null;
    const x = Number(local[0]);
    const y = Number(local[1]);
    return [
      (Number(matrix[0][0]) * x + Number(matrix[0][1]) * y + Number(matrix[0][2])) / Math.max(1, w - 1) * 1000,
      (Number(matrix[1][0]) * x + Number(matrix[1][1]) * y + Number(matrix[1][2])) / Math.max(1, h - 1) * 1000,
    ];
  };
  const localRing = feature => {
    const ring = feature?.properties?.localRing;
    if (!Array.isArray(ring)) return null;
    const pts = ring.map(projectLocal).filter(Boolean);
    return pts.length >= 3 ? pts : null;
  };
  return {
    pointFromFeature: feature => scalePoint(feature?.properties?.pixel) || projectLocal(feature?.properties?.local),
    pointFromShotStart: feature => scalePoint(feature?.properties?.startPixel) || projectLocal(feature?.properties?.startLocal),
    pointFromShotEnd: feature => scalePoint(feature?.properties?.endPixel) || projectLocal(feature?.properties?.endLocal),
    pointFromStrategy: row => projectLocal(row?.local),
    pointFromStrategyPoint: row => projectLocal(row?.local),
    polygonFromFeature: feature => localRing(feature),
    trianglesFromFeature: feature => {
      const tris = feature?.properties?.localTriangles;
      if (!Array.isArray(tris)) return null;
      return tris.map(tri => tri.map(projectLocal).filter(Boolean)).filter(tri => tri.length === 3);
    },
    source: matrix ? "pixel-fit" : "local-fallback",
  };
}

function rasterShotPixelProjector(raster) {
  const w = Number(raster?.width || 730);
  const h = Number(raster?.height || 730);
  const scalePoint = point => {
    if (!point) return null;
    const x = Number(point.x);
    const y = Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x / Math.max(1, w - 1) * 1000, y / Math.max(1, h - 1) * 1000];
  };
  return {
    pointFromFeature: feature => scalePoint(feature?.properties?.pixel),
    pointFromShotStart: feature => scalePoint(feature?.properties?.startPixel),
    pointFromShotEnd: feature => scalePoint(feature?.properties?.endPixel),
    pointFromStrategy: () => null,
    pointFromStrategyPoint: () => null,
    polygonFromFeature: () => null,
    trianglesFromFeature: () => null,
    source: "shot-pixel",
  };
}

function zoomPoint(point, viewport, zoom) {
  if (!point) return null;
  const width = Math.max(1, viewport?.clientWidth || 730);
  const height = Math.max(1, viewport?.clientHeight || width);
  const scale = Number(zoom?.scale || 1);
  const tx = Number(zoom?.x || 0) / width * 1000;
  const ty = Number(zoom?.y || 0) / height * 1000;
  return [
    500 + (Number(point[0]) - 500) * scale + tx,
    500 + (Number(point[1]) - 500) * scale + ty,
  ];
}

function zoomProjector(projector, viewport, zoom) {
  const mapPoint = point => zoomPoint(point, viewport, zoom);
  const mapList = points => Array.isArray(points) ? points.map(mapPoint).filter(Boolean) : null;
  return {
    pointFromFeature: feature => mapPoint(projector.pointFromFeature?.(feature)),
    pointFromShotStart: feature => mapPoint(projector.pointFromShotStart?.(feature)),
    pointFromShotEnd: feature => mapPoint(projector.pointFromShotEnd?.(feature)),
    pointFromStrategy: row => mapPoint(projector.pointFromStrategy?.(row)),
    pointFromStrategyPoint: row => mapPoint(projector.pointFromStrategyPoint?.(row)),
    polygonFromFeature: feature => {
      const pts = mapList(projector.polygonFromFeature?.(feature));
      return pts && pts.length >= 3 ? pts : null;
    },
    trianglesFromFeature: feature => {
      const tris = projector.trianglesFromFeature?.(feature);
      if (!Array.isArray(tris)) return null;
      return tris.map(tri => mapList(tri)).filter(tri => tri && tri.length === 3);
    },
    source: `${projector.source || "projector"}-zoomed`,
  };
}

function hasShotPixels(geojson) {
  return (geojson?.features || []).some(feature => {
    const props = feature.properties || {};
    return props.layer === "shot" && props.startPixel && props.endPixel;
  });
}

function shotDotColor(order, isPutt=false) {
  if (isPutt) return "#7c3aed";
  if (Number(order) === 1) return "#facc15";
  if (Number(order) === 2) return "#cbd5e1";
  if (Number(order) === 3) return "#fb923c";
  return "#7c3aed";
}

function shotLabelText(props) {
  const distance = distanceText(props?.meters);
  const club = String(props?.club || "").trim();
  if (!distance) return club && club !== "Unknown" ? club : "";
  if (!club || club === "Unknown") return distance;
  return `${club} ${distance}`;
}

function shotLabelPoint(a, b, index) {
  const t = 0.54;
  const mid = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const side = index % 2 === 0 ? 1 : -1;
  const offset = 24;
  return [mid[0] + (-dy / len) * offset * side, mid[1] + (dx / len) * offset * side];
}

function pointDot(x, y, color="#f8fafc", radius=9) {
  return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${radius}" fill="${color}" stroke="rgba(17,24,39,.76)" stroke-width="4"/>`;
}

function svgLabel(x, y, label, color="#facc15", preferLeft=false) {
  const w = Math.max(76, Math.min(170, String(label).length * 15 + 36));
  const left = preferLeft || x > 650;
  const rectX = left ? -w : 0;
  const textX = left ? -w / 2 : w / 2;
  return `
    <g transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" filter="url(#overlayShadow)">
      <rect x="${rectX.toFixed(1)}" y="-19" width="${w.toFixed(1)}" height="38" rx="19" fill="rgba(17,24,39,.86)" stroke="rgba(255,255,255,.82)" stroke-width="3"/>
      <circle cx="0" cy="0" r="13" fill="rgba(17,24,39,.86)" stroke="rgba(255,255,255,.82)" stroke-width="3"/>
      <circle cx="0" cy="0" r="6" fill="${color}"/>
      <text x="${textX.toFixed(1)}" y="6" font-size="18" font-weight="700" fill="#ffffff" text-anchor="middle">${esc(label)}</text>
    </g>`;
}

function teeMarker(x, y) {
  return `
    <g transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" filter="url(#overlayShadow)">
      <circle cx="0" cy="0" r="17" fill="rgba(17,24,39,.82)" stroke="rgba(255,255,255,.9)" stroke-width="3"/>
      <circle cx="0" cy="0" r="11" fill="#2563eb"/>
      <text x="0" y="6" font-size="16" font-weight="800" fill="#ffffff" text-anchor="middle">T</text>
    </g>`;
}

function targetMarker(x, y) {
  return `
    <g transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" filter="url(#overlayShadow)">
      <path d="M 0 -8 L 24 -18 L 0 -28 Z M 0 9 L 0 -28" stroke="#ef4444" fill="#ef4444" stroke-width="4"/>
      <circle cx="0" cy="0" r="13" fill="rgba(17,24,39,.84)" stroke="rgba(255,255,255,.86)" stroke-width="3"/>
      <circle cx="0" cy="0" r="6" fill="#ef4444"/>
    </g>`;
}

function geometryStyle(kind, surface="default") {
  const satellite = surface === "satellite";
  const styles = {
    fairway: { fill: "#34d399", stroke: "#047857", opacity: satellite ? 0.03 : 0.16, strokeOpacity: satellite ? 0.42 : 0.46, width: satellite ? 2.0 : 1.8 },
    green: { fill: "#22c55e", stroke: "#166534", opacity: satellite ? 0.06 : 0.22, strokeOpacity: satellite ? 0.58 : 0.58, width: 2.1 },
    bunker: { fill: "#facc15", stroke: "#92400e", opacity: satellite ? 0.07 : 0.18, strokeOpacity: satellite ? 0.60 : 0.54, width: 1.7 },
    water: { fill: "#38bdf8", stroke: "#0369a1", opacity: satellite ? 0.08 : 0.14, strokeOpacity: satellite ? 0.58 : 0.48, width: 1.9 },
    water_edge: { fill: "#0ea5e9", stroke: "#075985", opacity: satellite ? 0.03 : 0.06, strokeOpacity: satellite ? 0.25 : 0.28, width: 1.2 },
    tree_area: { fill: "#166534", stroke: "#14532d", opacity: 0, strokeOpacity: 0, width: 0 },
    teebox: { fill: "#60a5fa", stroke: "#1d4ed8", opacity: satellite ? 0.14 : 0.12, strokeOpacity: satellite ? 0.54 : 0.40, width: 1.6 },
    rough: { fill: "#84cc16", stroke: "#4d7c0f", opacity: 0, strokeOpacity: 0, width: 0 },
    playable_bounds: { fill: "none", stroke: "#ffffff", opacity: 0, strokeOpacity: 0, width: 0 },
  };
  return styles[kind] || { fill: "#94a3b8", stroke: "#475569", opacity: 0.12, strokeOpacity: 0.35, width: 1.2 };
}

function polygonPath(points) {
  return points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ") + " Z";
}

function trianglePath(triangles) {
  return (triangles || [])
    .map(tri => `M${tri[0][0].toFixed(1)} ${tri[0][1].toFixed(1)} L${tri[1][0].toFixed(1)} ${tri[1][1].toFixed(1)} L${tri[2][0].toFixed(1)} ${tri[2][1].toFixed(1)} Z`)
    .join(" ");
}

function solve3x3(matrix, vector) {
  const a = matrix.map((row, i) => [...row.map(Number), Number(vector[i])]);
  for (let col = 0; col < 3; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < 3; row += 1) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    }
    if (Math.abs(a[pivot][col]) < 1e-9) return null;
    [a[col], a[pivot]] = [a[pivot], a[col]];
    const scale = a[col][col];
    for (let j = col; j < 4; j += 1) a[col][j] /= scale;
    for (let row = 0; row < 3; row += 1) {
      if (row === col) continue;
      const factor = a[row][col];
      for (let j = col; j < 4; j += 1) a[row][j] -= factor * a[col][j];
    }
  }
  return [a[0][3], a[1][3], a[2][3]];
}

function fitAffine(pairs) {
  if (!pairs || pairs.length < 3) return null;
  const normal = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const bx = [0, 0, 0];
  const by = [0, 0, 0];
  pairs.forEach(pair => {
    const row = [pair.src[0], pair.src[1], 1];
    for (let r = 0; r < 3; r += 1) {
      for (let c = 0; c < 3; c += 1) normal[r][c] += row[r] * row[c];
      bx[r] += row[r] * pair.dst[0];
      by[r] += row[r] * pair.dst[1];
    }
  });
  const x = solve3x3(normal, bx);
  const y = solve3x3(normal, by);
  if (!x || !y) return null;
  return [x[0], y[0], x[1], y[1], x[2], y[2]];
}

function satelliteAffine(projector, geojson, bounds) {
  const geo = geoProjector(bounds);
  const pairs = [];
  const addPair = (coord, local) => {
    const src = geo.pointFromCoord(coord);
    const dst = projector.pointFromStrategyPoint({ local });
    if (src && dst && src.every(Number.isFinite) && dst.every(Number.isFinite)) pairs.push({ src, dst });
  };
  (geojson?.features || []).forEach(feature => {
    const props = feature.properties || {};
    if (props.layer === "geometry") {
      const coords = feature.geometry?.coordinates?.[0] || [];
      const locals = props.localRing || [];
      const count = Math.min(coords.length, locals.length);
      for (let i = 0; i < count; i += Math.max(1, Math.floor(count / 24))) addPair(coords[i], locals[i]);
    } else if (props.layer === "shot" && feature.geometry?.coordinates?.length >= 2) {
      addPair(feature.geometry.coordinates[0], props.startLocal);
      addPair(feature.geometry.coordinates[1], props.endLocal);
    } else if (props.local && feature.geometry?.coordinates) {
      addPair(feature.geometry.coordinates, props.local);
    }
  });
  return fitAffine(pairs);
}

function satelliteClip(projector, geojson, clipId) {
  const features = geojson?.features || [];
  const clipKinds = new Set(["rough", "fairway", "green", "bunker", "water", "water_edge", "teebox", "tree_area"]);
  let clipFeatures = features.filter(f => (f.properties || {}).layer === "geometry" && (f.properties || {}).kind === "rough");
  if (!clipFeatures.length) {
    clipFeatures = features.filter(f => (f.properties || {}).layer === "geometry" && clipKinds.has((f.properties || {}).kind));
  }
  const paths = [];
  clipFeatures.forEach(feature => {
    const pts = projector.polygonFromFeature ? projector.polygonFromFeature(feature) : null;
    if (pts) paths.push(`<path d="${polygonPath(pts)}"/>`);
  });
  if (!paths.length) return { defs: "", outline: "" };
  const outlineFeatures = features.filter(f => (f.properties || {}).layer === "geometry" && (f.properties || {}).kind === "rough");
  const outlines = outlineFeatures
    .map(feature => projector.polygonFromFeature ? projector.polygonFromFeature(feature) : null)
    .filter(Boolean)
    .map(pts => `<path d="${polygonPath(pts)}" fill="none" stroke="rgba(255,255,255,.72)" stroke-width="3.5" stroke-linejoin="round"/>`)
    .join("");
  return {
    defs: `<clipPath id="${clipId}" clipPathUnits="userSpaceOnUse">${paths.join("")}</clipPath>`,
    outline: outlines,
  };
}

function overlaySvg(projector, geojson, strategy, options={}) {
  const surface = options.surface || "default";
  const features = geojson?.features || [];
  const geometryFeatures = features.filter(f => (f.properties || {}).layer === "geometry");
  const shots = features
    .filter(f => (f.properties || {}).layer === "shot")
    .sort((a, b) => Number((a.properties || {}).order || 0) - Number((b.properties || {}).order || 0));
  const tee = features.find(f => (f.properties || {}).layer === "tee");
  const target = features.find(f => (f.properties || {}).layer === "target");
  const pin = features.find(f => (f.properties || {}).layer === "pin") || target;
  const parts = [
    '<svg class="static-course-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">',
    `<defs><filter id="overlayShadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000" flood-opacity=".35"/></filter>${options.extraDefs || ""}</defs>`,
  ];
  if (options.background) parts.push(options.background);

  const geometryOrder = { rough: 1, tree_area: 2, fairway: 3, water: 4, water_edge: 5, teebox: 6, bunker: 7, green: 8, playable_bounds: 9 };
  geometryFeatures
    .slice()
    .sort((a, b) => (geometryOrder[(a.properties || {}).kind] || 50) - (geometryOrder[(b.properties || {}).kind] || 50))
    .forEach(feature => {
      const kind = (feature.properties || {}).kind;
      if (surface === "satellite" && ["rough", "tree_area", "playable_bounds"].includes(kind)) return;
      if (surface === "raster" && ["rough", "tree_area", "playable_bounds"].includes(kind)) return;
      const pts = projector.polygonFromFeature ? projector.polygonFromFeature(feature) : null;
      const triangles = projector.trianglesFromFeature ? projector.trianglesFromFeature(feature) : null;
      if (!pts && (!triangles || !triangles.length)) return;
      const style = geometryStyle(kind, surface);
      if (style.opacity <= 0 && style.strokeOpacity <= 0) return;
      if (triangles && triangles.length) {
        parts.push(`<path d="${trianglePath(triangles)}" fill="${style.fill}" fill-opacity="${style.opacity}" stroke="none"/>`);
      }
      if (pts) {
        const triangleFillDrawn = triangles && triangles.length;
        if (surface === "satellite" && triangleFillDrawn) return;
        parts.push(`<path d="${polygonPath(pts)}" fill="${triangleFillDrawn ? "none" : style.fill}" fill-opacity="${triangleFillDrawn ? 0 : style.opacity}" stroke="${style.stroke}" stroke-opacity="${style.strokeOpacity}" stroke-width="${style.width}"/>`);
      }
    });

  if (state.overlayMode === "strategy" && strategy && strategy.status === "ok") {
    const ref = projector.pointFromStrategyPoint(strategy.reference);
    const tgt = projector.pointFromStrategyPoint(strategy.target);
    if (ref && tgt) {
      parts.push(`<line x1="${ref[0].toFixed(1)}" y1="${ref[1].toFixed(1)}" x2="${tgt[0].toFixed(1)}" y2="${tgt[1].toFixed(1)}" stroke="rgba(17,24,39,.46)" stroke-width="12" stroke-linecap="round"/>`);
      parts.push(`<line x1="${ref[0].toFixed(1)}" y1="${ref[1].toFixed(1)}" x2="${tgt[0].toFixed(1)}" y2="${tgt[1].toFixed(1)}" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-dasharray="18 12"/>`);
    }
    (strategy.labels || []).forEach((row, index) => {
      const p = projector.pointFromStrategy(row);
      if (!p) return;
      const color = row.kind === "target" ? "#10b981" : (row.kind === "water" ? "#2563eb" : row.kind === "bunker" ? "#d97706" : "#22c55e");
      parts.push(svgLabel(p[0], p[1], `${row.label} ${distanceText(row.carry_m)}`, color, index % 2 === 1));
    });
  } else {
    shots.forEach(feature => {
      const a = projector.pointFromShotStart(feature);
      const b = projector.pointFromShotEnd(feature);
      if (!a || !b) return;
      parts.push(`<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke="rgba(17,24,39,.48)" stroke-width="13" stroke-linecap="round"/>`);
      parts.push(`<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke="#ffffff" stroke-width="7" stroke-linecap="round"/>`);
    });
    shots.forEach((feature, index) => {
      const p = feature.properties || {};
      const a = projector.pointFromShotStart(feature);
      const b = projector.pointFromShotEnd(feature);
      if (!a || !b) return;
      const isPutt = String(p.type || "").includes("PUTT") || String(p.club || "").toLowerCase() === "putter";
      if (index === 0) parts.push(pointDot(a[0], a[1], "#f8fafc", 8));
      parts.push(pointDot(b[0], b[1], "#f8fafc", 9));
      const label = shotLabelText(p);
      if (label) {
        const lp = shotLabelPoint(a, b, index);
        parts.push(svgLabel(lp[0], lp[1], label, shotDotColor(p.order, isPutt), index % 2 === 1));
      }
    });
    if (pin && (pin.properties || {}).putts != null) {
      let p = projector.pointFromFeature(pin);
      if (!p && shots.length) p = projector.pointFromShotEnd(shots[shots.length - 1]);
      if (p) parts.push(svgLabel(p[0], p[1], `${(pin.properties || {}).putts} 次推杆`, "#7c3aed", true));
    }
  }

  const teePoint = tee ? projector.pointFromFeature(tee) : null;
  if (teePoint) parts.push(teeMarker(teePoint[0], teePoint[1]));
  const targetPoint = target ? projector.pointFromFeature(target) : null;
  if (targetPoint) parts.push(targetMarker(targetPoint[0], targetPoint[1]));
  parts.push("</svg>");
  return parts.join("");
}

function renderStaticSatellite(id, geojson, strategy, satellite={}, raster={}) {
  const el = $(id);
  if (!el) return;
  const projector = satellite.projector === "raster-pixel-fit"
    ? rasterPixelProjector(raster, geojson?.localFrame)
    : localProjector(geojson?.localFrame);
  if (projector && satellite.endpoint) {
    el.innerHTML = `
      <div class="static-course-viewport">
        <div class="static-course-layer">
          <img class="static-course-img satellite-local-img" src="${esc(satellite.endpoint)}" alt="Rotated satellite crop">
        </div>
        <div class="static-course-overlay-host"></div>
      </div>`;
    installOverlayZoom(id, (viewport, zoom) => (
      overlaySvg(zoomProjector(projector, viewport, zoom), geojson, strategy, { surface: "satellite" })
    ));
    return;
  }

  const bounds = expandedSquareBounds(geojson?.bounds || geojson?.focusBounds, 0.14);
  if (!bounds) {
    el.innerHTML = '<div class="overlay-empty">No WGS84 bounds available for satellite crop.</div>';
    return;
  }
  if (!projector) {
    const fallback = geoProjector(bounds);
    const img = esriExportUrl(bounds);
    el.innerHTML = `
      <div class="static-course-viewport">
        <div class="static-course-layer">
          <img class="static-course-img" src="${esc(img)}" alt="Satellite crop">
        </div>
        <div class="static-course-overlay-host"></div>
      </div>`;
    installOverlayZoom(id, (viewport, zoom) => (
      overlaySvg(zoomProjector(fallback, viewport, zoom), geojson, strategy, { surface: "satellite" })
    ));
    return;
  }
  el.innerHTML = '<div class="overlay-empty">Satellite local render endpoint is unavailable.</div>';
}

function renderRasterOverlay(id, geojson, raster, strategy) {
  const el = $(id);
  if (!el) return;
  if (!raster || !raster.available || !raster.endpoint) {
    el.innerHTML = `<div class="overlay-empty">${esc((raster && raster.reason) || "No Garmin raster URL found for this hole.")}</div>`;
    return;
  }
  const fit = raster.pixelFit;
  const validFit = fit && fit.valid !== false && fit.matrix;
  const shotPixels = hasShotPixels(geojson);
  const rasterWidth = Number(raster.width || raster.pixelFit?.rasterSize?.[0] || 730);
  const rasterHeight = Number(raster.height || raster.pixelFit?.rasterSize?.[1] || 730);
  const aspectStyle = `aspect-ratio:${Math.max(1, rasterWidth)} / ${Math.max(1, rasterHeight)}`;
  const dimensionText = `${Math.round(rasterWidth)}×${Math.round(rasterHeight)}`;
  if (!validFit) {
    const reason = fit?.reason || "missing pixel fit";
    const shotProjector = shotPixels ? rasterShotPixelProjector({ width: rasterWidth, height: rasterHeight }) : null;
    const note = shotPixels
      ? `${dimensionText} · Garmin shot x/y · route only`
      : `${dimensionText} · ${reason} · overlay hidden`;
    el.innerHTML = `
      <div class="static-course-viewport" style="${aspectStyle}">
        <div class="muted" style="position:absolute;left:8px;bottom:7px;z-index:3;background:rgba(255,255,255,.82);border-radius:6px;padding:3px 6px">${esc(note)}</div>
        <div class="static-course-layer">
          <img class="static-course-img" style="object-fit:fill" src="${esc(raster.endpoint)}" alt="Garmin CourseView raster">
        </div>
        <div class="static-course-overlay-host"></div>
      </div>`;
    installOverlayZoom(id, shotProjector ? ((viewport, zoom) => (
      overlaySvg(zoomProjector(shotProjector, viewport, zoom), geojson, strategy, { surface: "raster-shots" })
    )) : null);
    return;
  }
  const projector = rasterPixelProjector(raster, geojson?.localFrame);
  if (!projector) {
    el.innerHTML = '<div class="overlay-empty">Garmin raster is available, but pixel/local projection data is missing.</div>';
    return;
  }
  const fitNote = validFit
    ? `<div class="muted" style="position:absolute;left:8px;bottom:7px;z-index:3;background:rgba(255,255,255,.78);border-radius:6px;padding:3px 6px">${dimensionText} pixel fit · max residual ${Number(fit.maxResidualPx || 0).toFixed(1)}px</div>`
    : `<div class="muted" style="position:absolute;left:8px;bottom:7px;z-index:3;background:rgba(255,255,255,.78);border-radius:6px;padding:3px 6px">${dimensionText} · ${fit?.reason ? "invalid pixel fit" : "fallback projection"}</div>`;
  el.innerHTML = `
    <div class="static-course-viewport" style="${aspectStyle}">
      ${fitNote}
      <div class="static-course-layer">
        <img class="static-course-img" style="object-fit:fill" src="${esc(raster.endpoint)}" alt="Garmin CourseView raster">
      </div>
      <div class="static-course-overlay-host"></div>
    </div>`;
  installOverlayZoom(id, (viewport, zoom) => (
    overlaySvg(zoomProjector(projector, viewport, zoom), geojson, strategy, { surface: "raster" })
  ));
}

function installOverlayZoom(id, overlayRenderer=null) {
  const root = $(id);
  const viewport = root ? root.querySelector(".static-course-viewport") : null;
  const layer = root ? root.querySelector(".static-course-layer") : null;
  const overlayHost = root ? root.querySelector(".static-course-overlay-host") : null;
  if (!viewport || !layer) return;
  const current = overlayZoom.get(id) || { scale: 1, x: 0, y: 0 };
  overlayZoom.set(id, current);
  const apply = () => {
    layer.style.transform = `translate(${current.x}px, ${current.y}px) scale(${current.scale})`;
    if (overlayHost) {
      overlayHost.innerHTML = overlayRenderer ? overlayRenderer(viewport, current) : "";
    }
  };
  const zoomAt = (nextScale, clientX=null, clientY=null) => {
    const rect = viewport.getBoundingClientRect();
    const oldScale = Number(current.scale || 1);
    nextScale = Math.max(1, Math.min(OVERLAY_MAX_ZOOM, Number(nextScale)));
    if (!Number.isFinite(nextScale) || Math.abs(nextScale - oldScale) < 0.001) return;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const mx = (clientX == null ? centerX : clientX) - centerX;
    const my = (clientY == null ? centerY : clientY) - centerY;
    const imageX = (mx - current.x) / oldScale;
    const imageY = (my - current.y) / oldScale;
    current.x = mx - imageX * nextScale;
    current.y = my - imageY * nextScale;
    current.scale = nextScale;
    apply();
  };
  apply();
  document.querySelectorAll(`[data-zoom-controls="${id}"] [data-zoom-action]`).forEach(btn => {
    btn.onclick = () => {
      const action = btn.dataset.zoomAction;
      if (action === "in") zoomAt(current.scale * 1.22);
      if (action === "out") zoomAt(current.scale / 1.22);
      if (action === "reset") {
        current.scale = 1;
        current.x = 0;
        current.y = 0;
        apply();
      }
    };
  });
  let dragging = false;
  let startX = 0, startY = 0, baseX = 0, baseY = 0;
  viewport.onpointerdown = event => {
    if (event.button != null && event.button !== 0) return;
    event.preventDefault();
    dragging = true;
    viewport.classList.add("dragging");
    viewport.setPointerCapture(event.pointerId);
    startX = event.clientX;
    startY = event.clientY;
    baseX = current.x;
    baseY = current.y;
  };
  viewport.onpointermove = event => {
    if (!dragging) return;
    event.preventDefault();
    current.x = baseX + event.clientX - startX;
    current.y = baseY + event.clientY - startY;
    apply();
  };
  viewport.onpointerup = event => {
    dragging = false;
    viewport.classList.remove("dragging");
    try { viewport.releasePointerCapture(event.pointerId); } catch {}
  };
  viewport.onpointercancel = () => {
    dragging = false;
    viewport.classList.remove("dragging");
  };
  viewport.onwheel = event => {
    event.preventDefault();
    zoomAt(current.scale * (event.deltaY > 0 ? 0.90 : 1.10), event.clientX, event.clientY);
  };
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
$("holeSelect").onchange = () => loadSelectedHoleAfterPreprocess().catch(e => showStatus("importStatus", e.message, true));
$("roundSelect").onchange = () => {
  state.preprocessedRoundId = null;
  state.lastRoundAnalysis = null;
};
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
SATELLITE_CACHE = ROOT / "output" / "satellite_cache"
SATELLITE_RENDER_VERSION = "local-frame-v8"
SATELLITE_RENDER_SIZE = 2600
OVERLAY_MAX_ZOOM = 3.5
WEB_MERCATOR_RADIUS_M = 6_378_137.0
WEB_MERCATOR_MAX_LAT = 85.05112878
GOLF_API_BASE = "https://connect.garmin.cn/golf-api/gcs-golfcommunity/api/v2"


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


def ensure_raster_url_cached(url: str | None) -> tuple[Path | None, str | None]:
    if not url:
        return None, "No Garmin raster URL in shot data."
    RASTER_CACHE.mkdir(parents=True, exist_ok=True)
    path = garmin_raster_cache_path(url)
    if path.exists():
        return path, None
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=30) as response:
            path.write_bytes(response.read())
        return path, None
    except Exception as exc:
        return None, f"Garmin shot raster URL could not be cached locally: {exc}"


def _shot_data_has_pixels(data: dict[str, object] | None) -> bool:
    if not data:
        return False
    for hole in data.get("holeShots", []) or []:
        if hole.get("holeImageUrl"):
            return True
        for shot in hole.get("shots", []) or []:
            for loc in (shot.get("startLoc") or {}, shot.get("endLoc") or {}):
                if loc.get("x") is not None and loc.get("y") is not None:
                    return True
    return False


def _fetch_scorecard_shots_with_pixels(session: requests.Session, scorecard_id: int | str) -> requests.Response:
    return session.get(
        f"{GOLF_API_BASE}/shot/scorecard/{scorecard_id}/hole",
        params={"user-locale": "zh_CN", "per-page": "10000", "image-size": "IMG_730X730"},
        timeout=30,
    )


def ensure_scorecard_shots_with_pixels(scorecard_id: int | str | None) -> dict[str, object] | None:
    if scorecard_id is None:
        return None
    cached = load_shot_file(scorecard_id)
    if _shot_data_has_pixels(cached):
        return {"ok": True, "status": "cached", "scorecardId": scorecard_id}
    try:
        auth = ensure_web_auth(validate=True)
    except Exception:
        auth = ensure_web_auth(force=True, validate=True)
    session = requests.Session()
    session.headers.update(auth_headers(auth))
    response = _fetch_scorecard_shots_with_pixels(session, scorecard_id)
    if response.status_code in (401, 403):
        auth = ensure_web_auth(force=True, validate=True)
        session.headers.update(auth_headers(auth))
        response = _fetch_scorecard_shots_with_pixels(session, scorecard_id)
    response.raise_for_status()
    data = response.json()
    write_json(SHOT_DIR / f"{scorecard_id}.json", data)
    holes = len(data.get("holeShots", []) or [])
    shots = sum(len(h.get("shots", []) or []) for h in data.get("holeShots", []) or [])
    xy_locs = 0
    for hole in data.get("holeShots", []) or []:
        for shot in hole.get("shots", []) or []:
            for loc in (shot.get("startLoc") or {}, shot.get("endLoc") or {}):
                if loc.get("x") is not None and loc.get("y") is not None:
                    xy_locs += 1
    return {
        "ok": True,
        "status": "downloaded",
        "scorecardId": scorecard_id,
        "holes": holes,
        "shots": shots,
        "xyLocs": xy_locs,
    }


def scorecard_hole_raster_url(scorecard_id: int | str | None, hole: int | str | None) -> str | None:
    if scorecard_id is None or hole is None:
        return None
    data = load_shot_file(scorecard_id)
    if not data:
        return None
    for row in data.get("holeShots", []) or []:
        if int(row.get("holeNumber") or -1) == int(hole):
            return row.get("holeImageUrl")
    return None


def raster_dimensions(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return None


def ensure_course_snapshot_shots(scorecard_id: int | str | None) -> dict[str, object] | None:
    if scorecard_id is None:
        return None
    scorecard = load_scorecard(scorecard_id)
    snapshot_id = scorecard_snapshot_id(scorecard)
    if snapshot_id is None:
        return {"ok": False, "status": "missing-snapshot-id"}
    path = snapshot_file(snapshot_id)
    if path.exists():
        return {"ok": True, "status": "cached", "snapshotId": snapshot_id, "path": str(path)}
    try:
        auth = ensure_web_auth(validate=True)
    except Exception:
        auth = ensure_web_auth(force=True, validate=True)
    session = requests.Session()
    session.headers.update(auth_headers(auth))
    url = f"{GOLF_API_BASE}/shot/course-snapshot/{snapshot_id}/hole"
    params = {
        "user-locale": "zh_CN",
        "per-page": "10000",
        "image-size": "IMG_730X730",
        "skip-club-detail-info": "true",
    }
    response = session.get(url, params=params, timeout=30)
    if response.status_code in (401, 403):
        auth = ensure_web_auth(force=True, validate=True)
        session.headers.update(auth_headers(auth))
        response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    write_json(path, data)
    shots = sum(len(h.get("shots", []) or []) for h in data.get("holeShots", []) or [])
    return {
        "ok": True,
        "status": "downloaded",
        "snapshotId": snapshot_id,
        "path": str(path),
        "holes": len(data.get("holeShots", []) or []),
        "shots": shots,
    }
    try:
        with Image.open(path) as image:
            return {"width": int(image.width), "height": int(image.height)}
    except Exception:
        return None


def raster_pixel_fit(global_id: int, local_hole: int) -> dict | None:
    expected_global_id = int(global_id)
    expected_hole = int(local_hole)
    path = (
        ROOT
        / "output"
        / "prodgeometry_overlay"
        / f"gid{expected_global_id}_rasterh{expected_hole:02d}_prodgeometry_h{expected_hole:02d}_diagnostics.json"
    )
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    mesh_path_raw = data.get("mesh_json")
    mesh_global_id = None
    mesh_hole = None
    if mesh_path_raw:
        mesh_path = Path(mesh_path_raw)
        if not mesh_path.is_absolute():
            mesh_path = ROOT / mesh_path
        try:
            mesh_data = json.loads(mesh_path.read_text())
            mesh_meta = mesh_data.get("hole") or {}
            mesh_global_id = int(mesh_meta.get("GlobalId"))
            mesh_hole = int(mesh_meta.get("HoleNumber"))
        except Exception as exc:
            return {
                "valid": False,
                "source": "invalid_prodgeometry_raster_fit",
                "diagnostics": str(path),
                "reason": f"cannot validate diagnostics mesh: {exc}",
            }
        if mesh_global_id != expected_global_id or mesh_hole != expected_hole:
            return {
                "valid": False,
                "source": "invalid_prodgeometry_raster_fit",
                "diagnostics": str(path),
                "reason": (
                    f"diagnostics mesh mismatch: expected gid {expected_global_id} hole {expected_hole}, "
                    f"got gid {mesh_global_id} hole {mesh_hole}"
                ),
            }
    if int(data.get("course_id") or expected_global_id) != expected_global_id:
        return {
            "valid": False,
            "source": "invalid_prodgeometry_raster_fit",
            "diagnostics": str(path),
            "reason": f"diagnostics course mismatch: expected gid {expected_global_id}, got {data.get('course_id')}",
        }
    if int(data.get("raster_hole_number") or expected_hole) != expected_hole:
        return {
            "valid": False,
            "source": "invalid_prodgeometry_raster_fit",
            "diagnostics": str(path),
            "reason": (
                f"diagnostics raster hole mismatch: expected hole {expected_hole}, "
                f"got {data.get('raster_hole_number')}"
            ),
        }
    fit = data.get("fit") or {}
    matrix = fit.get("matrix")
    if not matrix:
        return None
    return {
        "valid": True,
        "source": "validated_prodgeometry_raster_fit",
        "diagnostics": str(path),
        "meshGlobalId": mesh_global_id,
        "meshHole": mesh_hole,
        "matrix": matrix,
        "rasterSize": data.get("raster_size") or [730, 730],
        "controlPoints": fit.get("control_points"),
        "maxResidualPx": max(
            float(fit.get("residual_x_max_px") or 0.0),
            float(fit.get("residual_y_max_px") or 0.0),
        ),
    }


def _valid_pixel_fit(fit: dict | None) -> bool:
    return bool(fit and fit.get("valid") is not False and fit.get("matrix"))


def shot_pixel_affine_fit(
    geojson: dict,
    raster_width: int = 730,
    raster_height: int = 730,
) -> dict | None:
    pairs: list[tuple[list[float], list[float]]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for feature in geojson.get("features", []) or []:
        props = feature.get("properties") or {}
        if props.get("layer") != "shot":
            continue
        for local_key, pixel_key in (("startLocal", "startPixel"), ("endLocal", "endPixel")):
            local = props.get(local_key)
            pixel = props.get(pixel_key)
            if not isinstance(local, list) or len(local) < 2 or not isinstance(pixel, dict):
                continue
            try:
                lx = float(local[0])
                ly = float(local[1])
                px = float(pixel["x"])
                py = float(pixel["y"])
            except Exception:
                continue
            if not all(math.isfinite(value) for value in (lx, ly, px, py)):
                continue
            key = (round(lx, 3), round(ly, 3), round(px, 3), round(py, 3))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(([lx, ly, 1.0], [px, py]))

    if len(pairs) < 3:
        return {
            "valid": False,
            "source": "shot_pixel_affine",
            "reason": f"need at least 3 local/pixel shot pairs, got {len(pairs)}",
            "pairs": len(pairs),
            "rasterSize": [int(raster_width), int(raster_height)],
        }

    a = np.asarray([row for row, _pixel in pairs], dtype=np.float64)
    px = np.asarray([pixel[0] for _row, pixel in pairs], dtype=np.float64)
    py = np.asarray([pixel[1] for _row, pixel in pairs], dtype=np.float64)
    rank = int(np.linalg.matrix_rank(a))
    if rank < 3:
        return {
            "valid": False,
            "source": "shot_pixel_affine",
            "reason": f"shot local/pixel pairs are collinear, rank={rank}",
            "pairs": len(pairs),
            "rasterSize": [int(raster_width), int(raster_height)],
        }

    mx = np.linalg.lstsq(a, px, rcond=None)[0]
    my = np.linalg.lstsq(a, py, rcond=None)[0]
    pred_x = a @ mx
    pred_y = a @ my
    residuals = np.sqrt((pred_x - px) ** 2 + (pred_y - py) ** 2)
    return {
        "valid": True,
        "source": "shot_pixel_affine",
        "matrix": [
            [float(mx[0]), float(mx[1]), float(mx[2])],
            [float(my[0]), float(my[1]), float(my[2])],
        ],
        "rasterSize": [int(raster_width), int(raster_height)],
        "pairs": len(pairs),
        "maxResidualPx": round(float(np.max(residuals)), 3),
        "meanResidualPx": round(float(np.mean(residuals)), 3),
    }


def _expanded_square_bounds(bounds: dict | None, pad_ratio: float = 0.14) -> dict[str, float] | None:
    if not bounds:
        return None
    try:
        south = float(bounds["south"])
        west = float(bounds["west"])
        north = float(bounds["north"])
        east = float(bounds["east"])
    except Exception:
        return None
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = max(1.0, 111_320.0 * math.cos(math.radians(center_lat)))
    width_m = max(30.0, (east - west) * meters_per_deg_lon)
    height_m = max(30.0, (north - south) * meters_per_deg_lat)
    side_m = max(width_m, height_m) * (1.0 + pad_ratio * 2.0)
    half_lat = side_m / meters_per_deg_lat / 2.0
    half_lon = side_m / meters_per_deg_lon / 2.0
    return {
        "south": center_lat - half_lat,
        "west": center_lon - half_lon,
        "north": center_lat + half_lat,
        "east": center_lon + half_lon,
    }


def _esri_export_url(bounds: dict[str, float], size: int = 1000) -> str:
    bbox = ",".join(f"{float(bounds[key]):.8f}" for key in ("west", "south", "east", "north"))
    return (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
        f"?bbox={bbox}&bboxSR=4326&imageSR=4326&size={size},{size}&format=jpg&f=image"
    )


def _satellite_base_image(bounds: dict[str, float], size: int = 1000) -> Image.Image:
    SATELLITE_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps({"bounds": bounds, "size": size}, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    path = SATELLITE_CACHE / f"esri_{key}.jpg"
    if not path.exists():
        req = Request(_esri_export_url(bounds, size), headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=45) as response:
            path.write_bytes(response.read())
    return Image.open(path).convert("RGB")


def _lonlat_to_web_mercator(lon: float, lat: float) -> tuple[float, float]:
    clipped_lat = max(-WEB_MERCATOR_MAX_LAT, min(WEB_MERCATOR_MAX_LAT, float(lat)))
    lat_rad = math.radians(clipped_lat)
    return (
        WEB_MERCATOR_RADIUS_M * math.radians(float(lon)),
        WEB_MERCATOR_RADIUS_M * math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0)),
    )


def _expanded_square_mercator_bounds(bounds: dict | None, pad_ratio: float = 0.14) -> dict[str, float] | None:
    if not bounds:
        return None
    try:
        south = float(bounds["south"])
        west = float(bounds["west"])
        north = float(bounds["north"])
        east = float(bounds["east"])
    except Exception:
        return None
    west_x, south_y = _lonlat_to_web_mercator(west, south)
    east_x, north_y = _lonlat_to_web_mercator(east, north)
    min_x, max_x = min(west_x, east_x), max(west_x, east_x)
    min_y, max_y = min(south_y, north_y), max(south_y, north_y)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    side_m = max(30.0, max(max_x - min_x, max_y - min_y)) * (1.0 + pad_ratio * 2.0)
    return {
        "west": center_x - side_m / 2.0,
        "south": center_y - side_m / 2.0,
        "east": center_x + side_m / 2.0,
        "north": center_y + side_m / 2.0,
    }


def _esri_export_url_mercator(bounds: dict[str, float], size: int = 1000) -> str:
    bbox = ",".join(f"{float(bounds[key]):.3f}" for key in ("west", "south", "east", "north"))
    return (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
        f"?bbox={bbox}&bboxSR=102100&imageSR=102100&size={size},{size}&format=jpg&f=image"
    )


def _satellite_base_image_mercator(bounds: dict[str, float], size: int = 1000) -> Image.Image:
    SATELLITE_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(
        json.dumps({"mercatorBounds": bounds, "size": size}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    path = SATELLITE_CACHE / f"esri_mercator_{key}.jpg"
    if not path.exists():
        req = Request(_esri_export_url_mercator(bounds, size), headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=45) as response:
            path.write_bytes(response.read())
    return Image.open(path).convert("RGB")


def _local_projector_params(frame: dict | None, size: int = 1000) -> dict[str, float] | None:
    if not frame or not frame.get("tee") or not frame.get("target"):
        return None
    tee = [float(frame["tee"][0]), float(frame["tee"][1])]
    target = [float(frame["target"][0]), float(frame["target"][1])]
    dx = target[0] - tee[0]
    dy = target[1] - tee[1]
    length = math.hypot(dx, dy)
    if length >= 1.0:
        vx = -dx / length
        vy = -dy / length
        ux = dy / length
        uy = -dx / length
    else:
        ux, uy, vx, vy = 1.0, 0.0, 0.0, 1.0
    min_x = float(frame["minX"])
    max_x = float(frame["maxX"])
    min_y = float(frame["minY"])
    max_y = float(frame["maxY"])
    raw_w = max(1.0, max_x - min_x)
    raw_h = max(1.0, max_y - min_y)
    pad = 58.0
    scale = min((size - pad * 2.0) / raw_w, (size - pad * 2.0) / raw_h)
    return {
        "tee_x": tee[0],
        "tee_y": tee[1],
        "ux": ux,
        "uy": uy,
        "vx": vx,
        "vy": vy,
        "min_x": min_x,
        "min_y": min_y,
        "off_x": (size - raw_w * scale) / 2.0,
        "off_y": (size - raw_h * scale) / 2.0,
        "scale": scale,
        "size": float(size),
    }


def _project_local_point(point: list[float] | tuple[float, float] | None, params: dict[str, float]) -> tuple[float, float] | None:
    if not point or len(point) < 2:
        return None
    nx = float(point[0]) - params["tee_x"]
    ny = float(point[1]) - params["tee_y"]
    rx = nx * params["ux"] + ny * params["uy"]
    ry = nx * params["vx"] + ny * params["vy"]
    return (
        params["off_x"] + (rx - params["min_x"]) * params["scale"],
        params["off_y"] + (ry - params["min_y"]) * params["scale"],
    )


def _screen_to_local_arrays(size: int, params: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(size, dtype=np.float32), np.arange(size, dtype=np.float32))
    rx = (xs - params["off_x"]) / params["scale"] + params["min_x"]
    ry = (ys - params["off_y"]) / params["scale"] + params["min_y"]
    local_x = params["tee_x"] + rx * params["ux"] + ry * params["vx"]
    local_y = params["tee_y"] + rx * params["uy"] + ry * params["vy"]
    return local_x, local_y


def _sample_satellite_image(
    base: Image.Image,
    local_x: np.ndarray,
    local_y: np.ndarray,
    bounds: dict[str, float],
    ref_lat: float,
    ref_lon: float,
) -> np.ndarray:
    arr = np.asarray(base, dtype=np.float32)
    h, w = arr.shape[:2]
    lat = ref_lat + (local_y / EARTH_RADIUS_M) * 180.0 / math.pi
    lon = ref_lon + (local_x / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))) * 180.0 / math.pi
    sx = (lon - float(bounds["west"])) / max(1e-12, float(bounds["east"]) - float(bounds["west"])) * (w - 1)
    sy = (float(bounds["north"]) - lat) / max(1e-12, float(bounds["north"]) - float(bounds["south"])) * (h - 1)

    valid = (sx >= 0) & (sx <= w - 1) & (sy >= 0) & (sy <= h - 1)
    sx = np.clip(sx, 0, w - 1)
    sy = np.clip(sy, 0, h - 1)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    wx = sx - x0
    wy = sy - y0

    top = arr[y0, x0] * (1.0 - wx[..., None]) + arr[y0, x1] * wx[..., None]
    bottom = arr[y1, x0] * (1.0 - wx[..., None]) + arr[y1, x1] * wx[..., None]
    sampled = top * (1.0 - wy[..., None]) + bottom * wy[..., None]
    sampled[~valid] = 0
    return np.clip(sampled, 0, 255).astype(np.uint8)


def _sample_satellite_image_mercator(
    base: Image.Image,
    local_x: np.ndarray,
    local_y: np.ndarray,
    bounds: dict[str, float],
    ref_lat: float,
    ref_lon: float,
) -> np.ndarray:
    arr = np.asarray(base, dtype=np.float32)
    h, w = arr.shape[:2]
    lat = ref_lat + (local_y / EARTH_RADIUS_M) * 180.0 / math.pi
    lon = ref_lon + (local_x / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))) * 180.0 / math.pi
    lat = np.clip(lat, -WEB_MERCATOR_MAX_LAT, WEB_MERCATOR_MAX_LAT)
    lat_rad = np.deg2rad(lat)
    merc_x = WEB_MERCATOR_RADIUS_M * np.deg2rad(lon)
    merc_y = WEB_MERCATOR_RADIUS_M * np.log(np.tan(math.pi / 4.0 + lat_rad / 2.0))
    sx = (merc_x - float(bounds["west"])) / max(1e-9, float(bounds["east"]) - float(bounds["west"])) * (w - 1)
    sy = (float(bounds["north"]) - merc_y) / max(1e-9, float(bounds["north"]) - float(bounds["south"])) * (h - 1)

    valid = (sx >= 0) & (sx <= w - 1) & (sy >= 0) & (sy <= h - 1)
    sx = np.clip(sx, 0, w - 1)
    sy = np.clip(sy, 0, h - 1)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    wx = sx - x0
    wy = sy - y0

    top = arr[y0, x0] * (1.0 - wx[..., None]) + arr[y0, x1] * wx[..., None]
    bottom = arr[y1, x0] * (1.0 - wx[..., None]) + arr[y1, x1] * wx[..., None]
    sampled = top * (1.0 - wy[..., None]) + bottom * wy[..., None]
    sampled[~valid] = 0
    return np.clip(sampled, 0, 255).astype(np.uint8)


def _draw_satellite_mask(geojson: dict, params: dict[str, float], size: int = 1000) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    clip_kinds = {"rough", "fairway", "green", "bunker", "water", "water_edge", "teebox", "tree_area"}
    drawn = 0
    for feature in geojson.get("features", []) or []:
        props = feature.get("properties") or {}
        if props.get("layer") != "geometry" or props.get("kind") not in clip_kinds:
            continue
        triangles = props.get("localTriangles")
        if isinstance(triangles, list) and triangles:
            for tri in triangles:
                pts = [_project_local_point(point, params) for point in tri]
                pts = [point for point in pts if point]
                if len(pts) == 3:
                    draw.polygon(pts, fill=255)
                    drawn += 1
        else:
            ring = props.get("localRing")
            if isinstance(ring, list) and len(ring) >= 3:
                pts = [_project_local_point(point, params) for point in ring]
                pts = [point for point in pts if point]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=255)
                    drawn += 1
    if drawn == 0:
        draw.rectangle((0, 0, size, size), fill=255)
    return mask


def _invert_pixel_fit(matrix: list[list[float]]) -> tuple[float, float, float, float, float, float] | None:
    try:
        a = float(matrix[0][0])
        b = float(matrix[0][1])
        c = float(matrix[0][2])
        d = float(matrix[1][0])
        e = float(matrix[1][1])
        f = float(matrix[1][2])
    except Exception:
        return None
    det = a * e - b * d
    if abs(det) < 1e-9:
        return None
    return (
        e / det,
        -b / det,
        (b * f - e * c) / det,
        -d / det,
        a / det,
        (d * c - a * f) / det,
    )


def _raster_pixel_to_local_arrays(
    matrix: list[list[float]],
    raster_width: int,
    raster_height: int,
    size: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    inverse = _invert_pixel_fit(matrix)
    if inverse is None:
        return None
    ia, ib, ic, id_, ie, iff = inverse
    xs, ys = np.meshgrid(np.arange(size, dtype=np.float32), np.arange(size, dtype=np.float32))
    px = xs / max(1.0, float(size - 1)) * max(1.0, float(raster_width - 1))
    py = ys / max(1.0, float(size - 1)) * max(1.0, float(raster_height - 1))
    local_x = ia * px + ib * py + ic
    local_y = id_ * px + ie * py + iff
    return local_x, local_y


def _odd_kernel(size: int, fraction: float, minimum: int) -> int:
    value = max(minimum, int(size * fraction))
    return value if value % 2 else value + 1


def _feather_mask(mask: Image.Image, size: int) -> Image.Image:
    close_kernel = _odd_kernel(size, 0.014, 9)
    erode_kernel = _odd_kernel(size, 0.008, 5)
    return (
        mask.filter(ImageFilter.MaxFilter(close_kernel))
        .filter(ImageFilter.MinFilter(erode_kernel))
        .filter(ImageFilter.GaussianBlur(max(1.2, size * 0.0022)))
    )


def _raster_hole_mask(path: Path, size: int) -> Image.Image | None:
    try:
        raster = Image.open(path).convert("RGB").resize((size, size), Image.Resampling.BILINEAR)
    except Exception:
        return None
    arr = np.asarray(raster, dtype=np.int16)
    border = np.concatenate((arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]), axis=0)
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(arr - bg, axis=2)
    border_dist = np.linalg.norm(border - bg, axis=1)
    threshold = float(np.clip(np.percentile(border_dist, 99) + 20.0, 34.0, 72.0))
    candidate = dist <= threshold
    visited = np.zeros(candidate.shape, dtype=bool)
    q: deque[tuple[int, int]] = deque()
    h, w = candidate.shape

    def add(y: int, x: int) -> None:
        if 0 <= y < h and 0 <= x < w and candidate[y, x] and not visited[y, x]:
            visited[y, x] = True
            q.append((y, x))

    for x in range(w):
        add(0, x)
        add(h - 1, x)
    for y in range(h):
        add(y, 0)
        add(y, w - 1)
    while q:
        y, x = q.popleft()
        add(y - 1, x)
        add(y + 1, x)
        add(y, x - 1)
        add(y, x + 1)

    mask = (~visited).astype(np.uint8) * 255
    if int(np.count_nonzero(mask)) < max(32, int(size * size * 0.002)):
        return None
    return _feather_mask(Image.fromarray(mask, "L"), size)


def _local_to_output_pixel(
    local: list[float] | tuple[float, float] | None,
    matrix: list[list[float]],
    raster_width: int,
    raster_height: int,
    size: int,
) -> tuple[float, float] | None:
    if not local or len(local) < 2:
        return None
    x = float(local[0])
    y = float(local[1])
    px = float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2])
    py = float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2])
    return (
        px / max(1.0, float(raster_width - 1)) * float(size),
        py / max(1.0, float(raster_height - 1)) * float(size),
    )


def _geometry_feature_mask(
    geojson: dict,
    matrix: list[list[float]],
    raster_width: int,
    raster_height: int,
    size: int,
) -> Image.Image | None:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    feature_kinds = {"rough", "fairway", "green", "bunker", "teebox", "tree_area"}
    drawn = 0

    for feature in geojson.get("features", []) or []:
        props = feature.get("properties") or {}
        if props.get("layer") != "geometry" or props.get("kind") not in feature_kinds:
            continue
        triangles = props.get("localTriangles")
        if isinstance(triangles, list) and triangles:
            for tri in triangles:
                pts = [
                    _local_to_output_pixel(point, matrix, raster_width, raster_height, size)
                    for point in tri
                ]
                pts = [point for point in pts if point]
                if len(pts) == 3:
                    draw.polygon(pts, fill=255)
                    drawn += 1
        else:
            ring = props.get("localRing")
            if isinstance(ring, list) and len(ring) >= 3:
                pts = [
                    _local_to_output_pixel(point, matrix, raster_width, raster_height, size)
                    for point in ring
                ]
                pts = [point for point in pts if point]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=255)
                    drawn += 1

    if drawn == 0:
        return None
    return _feather_mask(mask, size)


def _convex_hull_mask(mask: Image.Image, size: int) -> Image.Image | None:
    arr = np.asarray(mask, dtype=np.uint8)
    ys, xs = np.nonzero(arr > 0)
    if xs.size < 3:
        return None
    points = sorted(set(zip(xs.tolist(), ys.tolist())))

    def cross(o: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> int:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[int, int]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[int, int]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None
    out = Image.new("L", (size, size), 0)
    ImageDraw.Draw(out).polygon(hull, fill=255)
    return out.filter(ImageFilter.MaxFilter(max(3, int(size * 0.010) // 2 * 2 + 1)))


def _bounds_from_local_mask(
    local_x: np.ndarray,
    local_y: np.ndarray,
    mask: Image.Image,
    ref_lat: float,
    ref_lon: float,
) -> dict[str, float] | None:
    active = np.asarray(mask, dtype=np.uint8) > 8
    if not np.any(active):
        active = np.ones(local_x.shape, dtype=bool)
    lat = ref_lat + (local_y[active] / EARTH_RADIUS_M) * 180.0 / math.pi
    lon = ref_lon + (local_x[active] / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))) * 180.0 / math.pi
    if lat.size == 0 or lon.size == 0:
        return None
    return {
        "south": float(np.min(lat)),
        "west": float(np.min(lon)),
        "north": float(np.max(lat)),
        "east": float(np.max(lon)),
    }


def _render_satellite_png_from_raster_fit(analysis: dict[str, object], *, size: int = 1000) -> bytes | None:
    global_id = int(analysis["globalId"])
    local_hole = int(analysis["localHole"])
    raster_path, raster_error = ensure_raster_url_cached(analysis.get("holeImageUrl"))
    if raster_path is None:
        raster_path, raster_error = ensure_garmin_raster(global_id, local_hole)
    if raster_path is None or raster_error:
        return None
    dimensions = raster_dimensions(raster_path) or {}
    raster_width = int(dimensions.get("width") or 730)
    raster_height = int(dimensions.get("height") or 730)
    geojson = overlay_geojson(analysis)
    fit = raster_pixel_fit(global_id, local_hole)
    if not _valid_pixel_fit(fit):
        fit = shot_pixel_affine_fit(geojson, raster_width, raster_height)
    if not _valid_pixel_fit(fit):
        return None
    geometry = analysis.get("geometry") or {}
    ref_lat = geometry.get("refLat")
    ref_lon = geometry.get("refLon")
    if ref_lat is None or ref_lon is None:
        return None

    key_data = {
        "version": SATELLITE_RENDER_VERSION + "-raster-fit",
        "round": analysis.get("roundId"),
        "source": analysis.get("source"),
        "hole": analysis.get("hole"),
        "globalId": global_id,
        "localHole": local_hole,
        "matrix": fit.get("matrix"),
        "raster": str(raster_path),
        "rasterMtime": raster_path.stat().st_mtime,
        "size": size,
    }
    key = hashlib.sha1(json.dumps(key_data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    out_path = SATELLITE_CACHE / f"rasterfit_{key}.png"
    if out_path.exists():
        return out_path.read_bytes()

    arrays = _raster_pixel_to_local_arrays(fit["matrix"], raster_width, raster_height, size)
    if arrays is None:
        return None
    local_x, local_y = arrays
    mask = _raster_hole_mask(raster_path, size)
    if mask is None:
        mask = _geometry_feature_mask(geojson, fit["matrix"], raster_width, raster_height, size)
    if mask is None:
        return None
    wgs_bounds = _bounds_from_local_mask(local_x, local_y, mask, float(ref_lat), float(ref_lon))
    bounds = _expanded_square_mercator_bounds(wgs_bounds, 0.10)
    if bounds is None:
        return None
    base = _satellite_base_image_mercator(bounds, size)
    rgb = _sample_satellite_image_mercator(base, local_x, local_y, bounds, float(ref_lat), float(ref_lon))
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = np.asarray(mask, dtype=np.uint8)
    SATELLITE_CACHE.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    out_path.write_bytes(buf.getvalue())
    return out_path.read_bytes()


def render_satellite_png(analysis: dict[str, object], *, size: int = 1000) -> bytes:
    raster_fit_png = _render_satellite_png_from_raster_fit(analysis, size=size)
    if raster_fit_png is not None:
        return raster_fit_png

    geojson = overlay_geojson(analysis)
    frame = geojson.get("localFrame")
    params = _local_projector_params(frame, size)
    bounds = _expanded_square_bounds(geojson.get("bounds") or geojson.get("focusBounds"), 0.14)
    geometry = analysis.get("geometry") or {}
    ref_lat = geometry.get("refLat")
    ref_lon = geometry.get("refLon")
    if not params or not bounds or ref_lat is None or ref_lon is None:
        raise ValueError("satellite render requires local frame, WGS84 bounds, and geometry refLat/refLon")

    key_data = {
        "version": SATELLITE_RENDER_VERSION,
        "round": analysis.get("roundId"),
        "source": analysis.get("source"),
        "hole": analysis.get("hole"),
        "globalId": analysis.get("globalId"),
        "localHole": analysis.get("localHole"),
        "bounds": bounds,
        "frame": frame,
        "size": size,
    }
    key = hashlib.sha1(json.dumps(key_data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    out_path = SATELLITE_CACHE / f"hole_{key}.png"
    if out_path.exists():
        return out_path.read_bytes()

    base = _satellite_base_image(bounds, size)
    local_x, local_y = _screen_to_local_arrays(size, params)
    rgb = _sample_satellite_image(base, local_x, local_y, bounds, float(ref_lat), float(ref_lon))
    mask = _draw_satellite_mask(geojson, params, size)
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = np.asarray(mask, dtype=np.uint8)
    SATELLITE_CACHE.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    out_path.write_bytes(buf.getvalue())
    return out_path.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "AICaddieHTTP/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[web] {self.address_string()} {fmt % args}")

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-cache, no-store, must-revalidate")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: str, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-cache, no-store, must-revalidate")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-cache, no-store, must-revalidate")
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
                scorecard_id = qs.get("scorecard_id", [None])[0]
                if scorecard_id:
                    ensure_scorecard_shots_with_pixels(scorecard_id)
                analysis = build_hole_analysis(
                    scorecard_id=scorecard_id,
                    manual_round_id=qs.get("manual_id", [None])[0],
                    hole_number=hole,
                    ensure_geometry=True,
                )
                self._json(analysis)
            elif parsed.path == "/api/round-analysis":
                scorecard_id = qs.get("scorecard_id", [None])[0]
                if not scorecard_id:
                    raise ValueError("scorecard_id is required")
                ensure_scorecard_shots_with_pixels(scorecard_id)
                self._json(build_round_analysis(scorecard_id=scorecard_id, ensure_geometry=True))
            elif parsed.path == "/api/overlay-geojson":
                hole = int(qs.get("hole", ["1"])[0])
                source = qs.get("source", ["garmin"])[0]
                rid = qs.get("id", [None])[0]
                shot_sync = ensure_scorecard_shots_with_pixels(rid) if source == "garmin" and rid else None
                analysis = build_hole_analysis(
                    scorecard_id=rid if source == "garmin" else None,
                    manual_round_id=rid if source == "manual" else None,
                    hole_number=hole,
                    ensure_geometry=True,
                )
                raster_path, raster_error = ensure_raster_url_cached(analysis.get("holeImageUrl"))
                if raster_path is None:
                    raster_path, raster_error = ensure_garmin_raster(int(analysis["globalId"]), int(analysis["localHole"]))
                raster_query = {"global_id": analysis["globalId"], "local_hole": analysis["localHole"]}
                if source == "garmin" and rid:
                    raster_query.update({"scorecard_id": rid, "hole": hole})
                endpoint = f"/api/raster?{urlencode(raster_query)}" if raster_path else None
                geojson = overlay_geojson(analysis)
                raster_dims = raster_dimensions(raster_path) or {}
                raster_width = int(raster_dims.get("width") or 730)
                raster_height = int(raster_dims.get("height") or 730)
                pixel_fit = raster_pixel_fit(int(analysis["globalId"]), int(analysis["localHole"]))
                if not _valid_pixel_fit(pixel_fit):
                    pixel_fit = shot_pixel_affine_fit(geojson, raster_width, raster_height)
                satellite_projector = (
                    "raster-pixel-fit"
                    if raster_path and _valid_pixel_fit(pixel_fit)
                    else "local-frame"
                )
                satellite_query = urlencode({"source": source, "id": rid or "", "hole": hole, "size": SATELLITE_RENDER_SIZE})
                self._json({
                    "schema": "ai-caddie-overlay-geojson-v1",
                    "roundId": analysis["roundId"],
                    "hole": analysis["hole"],
                    "globalId": analysis["globalId"],
                    "localHole": analysis["localHole"],
                    "geojson": geojson,
                    "strategy": strategy_distances(analysis),
                    "shotSync": shot_sync,
                    "raster": {
                        "available": bool(raster_path),
                        "endpoint": endpoint,
                        "reason": raster_error,
                        "pixelFit": pixel_fit,
                        **raster_dims,
                    },
                    "satellite": {
                        "available": True,
                        "endpoint": f"/api/satellite?{satellite_query}",
                        "render": "server-png",
                        "projector": satellite_projector,
                    },
                })
            elif parsed.path == "/api/satellite":
                hole = int(qs.get("hole", ["1"])[0])
                source = qs.get("source", ["garmin"])[0]
                rid = qs.get("id", [None])[0]
                size = max(1000, min(3200, int(qs.get("size", [str(SATELLITE_RENDER_SIZE)])[0])))
                if source == "garmin" and rid:
                    ensure_scorecard_shots_with_pixels(rid)
                analysis = build_hole_analysis(
                    scorecard_id=rid if source == "garmin" else None,
                    manual_round_id=rid if source == "manual" else None,
                    hole_number=hole,
                    ensure_geometry=True,
                )
                self._bytes(render_satellite_png(analysis, size=size), "image/png")
            elif parsed.path == "/api/overlay":
                hole = int(qs.get("hole", ["1"])[0])
                source = qs.get("source", ["garmin"])[0]
                rid = qs.get("id", [None])[0]
                if source == "garmin" and rid:
                    ensure_scorecard_shots_with_pixels(rid)
                analysis = build_hole_analysis(
                    scorecard_id=rid if source == "garmin" else None,
                    manual_round_id=rid if source == "manual" else None,
                    hole_number=hole,
                    ensure_geometry=True,
                )
                self._text(render_svg(analysis), content_type="image/svg+xml; charset=utf-8")
            elif parsed.path == "/api/raster":
                global_id = int(qs.get("global_id", ["0"])[0])
                local_hole = int(qs.get("local_hole", ["0"])[0])
                if not global_id or not local_hole:
                    raise ValueError("global_id and local_hole are required")
                scorecard_id = qs.get("scorecard_id", [None])[0]
                hole = qs.get("hole", [None])[0]
                path = None
                error = None
                if scorecard_id and hole:
                    ensure_scorecard_shots_with_pixels(scorecard_id)
                    path, error = ensure_raster_url_cached(scorecard_hole_raster_url(scorecard_id, hole))
                if path is None:
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
                cmd = [sys.executable, "-m", "ai_caddie.garmin.fetch"]
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
