"use strict";

const API_BASE_URL = (
    window.PROMPT2EDIT_API_URL || "https://prompt2video.onrender.com"
).replace(/\/+$/, "");
const $ = (id) => document.getElementById(id);

let sessionId = null;
let selectedVideoFile = null;
let localVideoUrl = null;
let originalUploaded = false;
let currentTimelineHash = null;
let currentTimelineVersion = 0;

async function apiRequest(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body !== undefined && options.body !== null && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  let data;
  try {
    const type = response.headers.get("content-type") || "";
    data = type.includes("application/json") ? await response.json() : {};
  } catch {
    data = {};
  }
  if (!response.ok && !data.status) data.status = "Rejected";
  return { response, data };
}

function statusClass(status) {
  return String(status || "Rejected").toLowerCase().replace(/\s+/g, "-");
}

function showResponse(status, message, target = "response") {
  const box = $(target === "render" ? "renderMessage" : "responseBox");
  const title = $(target === "render" ? "renderMessageTitle" : "responseStatus");
  const body = $(target === "render" ? "renderMessageText" : "responseMessage");
  if (!box) return;
  box.hidden = false;
  box.className = `response-box status-${statusClass(status)}`;
  if (title) title.textContent = status || "Rejected";
  if (body) body.textContent = message || "No message was provided.";
}

function setRenderStatus(text, good = false) {
  const element = $("renderStatus");
  if (!element) return;
  element.textContent = text;
  element.className = `pill${good ? " pill-success" : ""}`;
}

function setBusy(button, busy, busyText, normalText) {
  if (!button) return;
  button.disabled = busy;
  button.textContent = busy ? busyText : normalText;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "Unknown duration";
  const rounded = Math.floor(seconds);
  const h = Math.floor(rounded / 3600);
  const m = Math.floor((rounded % 3600) / 60);
  const s = rounded % 60;
  return h ? [h, m, s].map((v) => String(v).padStart(2, "0")).join(":") : [m, s].map((v) => String(v).padStart(2, "0")).join(":");
}

async function checkBackend() {
  const label = $("connectionStatus");
  const dot = $("connectionDot");
  const button = $("checkBackendBtn");
  if (label) label.textContent = "Checking backend…";
  if (dot) dot.className = "dot";
  if (button) button.disabled = true;
  try {
    const { response, data } = await apiRequest("/api/health");
    if (!response.ok) throw new Error(data.message || "Health check failed.");
    if (label) label.textContent = "Backend connected";
    if (dot) dot.className = "dot dot-connected";
  } catch (error) {
    if (label) label.textContent = "Backend unavailable";
    if (dot) dot.className = "dot dot-disconnected";
    console.error("Backend connection error:", error);
  } finally {
    if (button) button.disabled = false;
  }
}

function updateSessionUI() {
  if ($("sessionStatus")) {
    $("sessionStatus").textContent = sessionId ? "Active session" : "No active session";
    $("sessionStatus").className = `pill${sessionId ? " pill-success" : ""}`;
  }
  if ($("sessionIdDisplay")) $("sessionIdDisplay").textContent = sessionId || "Not created";
  updateButtonStates();
}

function updateButtonStates(timeline = null) {
  if ($("uploadBtn")) $("uploadBtn").disabled = !sessionId || !selectedVideoFile || originalUploaded;
  if ($("applyPromptBtn")) $("applyPromptBtn").disabled = !sessionId || !originalUploaded;
  if ($("renderBtn")) $("renderBtn").disabled = !sessionId || !originalUploaded;
  if ($("verifyOriginalBtn")) $("verifyOriginalBtn").disabled = !sessionId || !originalUploaded;
  if ($("restoreBtn")) $("restoreBtn").disabled = !sessionId;
  if (timeline) {
    if ($("undoBtn")) $("undoBtn").disabled = !timeline.can_undo;
    if ($("redoBtn")) $("redoBtn").disabled = !timeline.can_redo;
  }
}

async function createSession() {
  const button = $("createSessionBtn");
  setBusy(button, true, "Creating session…", "＋ Create editing session");
  try {
    const { response, data } = await apiRequest("/api/session", { method: "POST", body: JSON.stringify({}) });
    if (!response.ok || !data.session_id) throw new Error(data.message || "Could not create an editing session.");
    sessionId = String(data.session_id);
    originalUploaded = false;
    currentTimelineHash = null;
    currentTimelineVersion = 0;
    clearRenderedOutput();
    updateSessionUI();
    if ($("originalHashDisplay")) $("originalHashDisplay").textContent = "Not uploaded";
    if ($("sourceMessage")) $("sourceMessage").textContent = "Choose a video and upload it to this session.";
    await refreshTimeline(false);
    showResponse("Applied", "Session created. Select a video and upload it before applying edits.");
  } catch (error) {
    showResponse("Rejected", error.message);
  } finally {
    if (button) { button.disabled = false; button.textContent = "＋ Create editing session"; }
  }
}

function handleVideoSelection(file) {
  if (!file) return;
  const allowed = [".mp4", ".mov", ".avi", ".mkv", ".webm"];
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!allowed.includes(ext)) {
    showResponse("Rejected", "Choose MP4, MOV, AVI, MKV or WebM video.");
    return;
  }
  if (localVideoUrl) URL.revokeObjectURL(localVideoUrl);
  selectedVideoFile = file;
  localVideoUrl = URL.createObjectURL(file);
  const video = $("videoPreview");
  if (video) {
    video.src = localVideoUrl;
    video.hidden = false;
    video.onloadedmetadata = () => {
      if ($("videoDuration")) $("videoDuration").textContent = formatDuration(video.duration);
    };
    video.onerror = () => {
      if ($("videoDuration")) $("videoDuration").textContent = "Preview unavailable";
    };
    video.load();
  }
  if ($("selectedFileInfo")) $("selectedFileInfo").hidden = false;
  if ($("videoName")) $("videoName").textContent = file.name;
  if ($("videoDuration")) $("videoDuration").textContent = "Reading duration…";
  if ($("uploadArea")) $("uploadArea").classList.add("has-file");
  updateButtonStates();
  if (!sessionId) showResponse("Needs clarification", "Create an editing session before uploading the video.");
}

$("videoInput")?.addEventListener("change", (event) => {
  handleVideoSelection(event.target.files?.[0]);
  event.target.value = "";
});

$("uploadBtn")?.addEventListener("click", async () => {
  if (!sessionId || !selectedVideoFile) return;
  const button = $("uploadBtn");
  setBusy(button, true, "Uploading and validating…", "Upload original to backend");
  const formData = new FormData();
  formData.append("file", selectedVideoFile, selectedVideoFile.name);
  try {
    const { response, data } = await apiRequest(`/api/upload/${encodeURIComponent(sessionId)}`, { method: "POST", body: formData });
    if (!response.ok || data.status !== "Applied") throw new Error(data.message || "Upload failed.");
    originalUploaded = true;
    if ($("originalHashDisplay")) {
      const hash = data.original?.sha256 || data.original_sha256 || "Registered";
      $("originalHashDisplay").textContent = hash;
      $("originalHashDisplay").title = hash;
    }
    const meta = data.original || {};
    if ($("sourceMessage")) $("sourceMessage").textContent = `Uploaded and validated · ${meta.width || "?"} × ${meta.height || "?"} · ${formatDuration(meta.duration || 0)} · Original stored separately.`;
    showResponse("Applied", "Original uploaded, validated and registered. Its SHA-256 hash has been recorded.");
    updateButtonStates();
    await refreshTimeline(false);
  } catch (error) {
    originalUploaded = false;
    showResponse("Rejected", error.message);
    updateButtonStates();
  } finally {
    if (button) { button.disabled = !sessionId || !selectedVideoFile || originalUploaded; button.textContent = "Upload original to backend"; }
  }
});

$("verifyOriginalBtn")?.addEventListener("click", async () => {
  if (!sessionId || !originalUploaded) return;
  try {
    const { response, data } = await apiRequest(`/api/verify-original/${encodeURIComponent(sessionId)}`);
    showResponse(data.status || (response.ok ? "Applied" : "Rejected"), `${data.message || "Verification finished."}${data.actual_sha256 ? ` SHA-256: ${data.actual_sha256}` : ""}`);
  } catch (error) { showResponse("Rejected", error.message); }
});

function clearRenderedOutput() {
  const video = $("renderedVideo");
  if (video) { video.pause(); video.removeAttribute("src"); video.load(); video.hidden = true; }
  if ($("renderResultActions")) $("renderResultActions").hidden = true;
  if ($("verificationOutput")) $("verificationOutput").textContent = "Render verification is not available yet.";
  setRenderStatus("Not rendered");
}

function renderDescription(op) {
  const p = op.parameters || {};
  const type = op.operation_type || "edit";
  if (type === "reorder") return `Output order: ${(p.segments || []).map((s) => `${s.start}–${s.end}s`).join(" → ")}`;
  if (type === "speed") return `${p.factor}× speed · ${p.whole_source ? "whole source" : `${p.start}–${p.end}s`}`;
  if (type === "caption") return `“${p.text}” · ${p.start}–${p.end}s (source time)`;
  if (type === "effect") return `${p.name}${p.value !== undefined ? ` (${p.value})` : ""} · ${p.whole_source ? "whole source" : `${p.start}–${p.end}s`}`;
  if (type === "cut" || type === "mute" || type === "bleep") return `${p.start}–${p.end}s (source time)`;
  return JSON.stringify(p);
}

function renderTimeline(data) {
  const operations = Array.isArray(data.operations) ? data.operations : [];
  currentTimelineHash = data.timeline_hash || null;
  currentTimelineVersion = data.version ?? 0;
  if ($("operationCount")) $("operationCount").textContent = `${operations.length} operation${operations.length === 1 ? "" : "s"}`;
  if ($("timelineVersion")) $("timelineVersion").textContent = `Version ${currentTimelineVersion}`;
  if ($("timelineHash")) { $("timelineHash").textContent = currentTimelineHash || "No timeline hash"; $("timelineHash").title = currentTimelineHash || ""; }
  if ($("emptyTimeline")) $("emptyTimeline").hidden = operations.length > 0;
  const list = $("operationList");
  if (list) {
    list.replaceChildren();
    operations.forEach((op, index) => {
      const row = document.createElement("div"); row.className = "operation-row";
      const count = document.createElement("span"); count.className = "operation-number"; count.textContent = String(index + 1).padStart(2, "0");
      const body = document.createElement("div"); body.className = "operation-body";
      const title = document.createElement("b"); title.textContent = String(op.operation_type || "Edit").toUpperCase();
      const desc = document.createElement("p"); desc.textContent = renderDescription(op);
      body.append(title, desc); row.append(count, body); list.appendChild(row);
    });
  }
  updateButtonStates(data);
}

async function refreshTimeline(showMessage = true) {
  if (!sessionId) return;
  try {
    const { response, data } = await apiRequest(`/api/timeline/${encodeURIComponent(sessionId)}`);
    if (!response.ok) throw new Error(data.message || "Could not load timeline.");
    renderTimeline(data);
    originalUploaded = Boolean(data.source_uploaded || originalUploaded);
    if (showMessage) showResponse("Applied", "Timeline refreshed.");
  } catch (error) { if (showMessage) showResponse("Rejected", error.message); }
}

async function applyPrompt() {
  const prompt = $("promptInput")?.value.trim();
  if (!prompt) { showResponse("Needs clarification", "Enter an editing instruction first."); return; }
  if (!sessionId || !originalUploaded) { showResponse("Needs clarification", "Create a session and upload the original video first."); return; }
  const button = $("applyPromptBtn");
  setBusy(button, true, "Processing…", "Apply instruction →");
  try {
    const { response, data } = await apiRequest("/api/prompt", { method: "POST", body: JSON.stringify({ prompt, session_id: sessionId }) });
    showResponse(data.status || (response.ok ? "Applied" : "Rejected"), data.message || "No response message was returned.");
    if (response.ok && data.status === "Applied") {
      clearRenderedOutput();
      await refreshTimeline(false);
    }
  } catch (error) { showResponse("Rejected", `Could not contact the backend: ${error.message}`); }
  finally { if (button) { button.disabled = !sessionId || !originalUploaded; button.textContent = "Apply instruction →"; } }
}

$("applyPromptBtn")?.addEventListener("click", applyPrompt);
$("promptInput")?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); applyPrompt(); }
});
document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
  if ($("promptInput")) { $("promptInput").value = chip.dataset.prompt || ""; $("promptInput").focus(); }
}));

async function historyAction(action) {
  if (!sessionId) return;
  const button = $(action === "undo" ? "undoBtn" : "redoBtn");
  if (button) button.disabled = true;
  try {
    const { response, data } = await apiRequest(`/api/${action}/${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify({}) });
    showResponse(data.status || (response.ok ? "Applied" : "Rejected"), data.message || `${action} completed.`);
    if (response.ok && data.status === "Applied") { clearRenderedOutput(); await refreshTimeline(false); }
  } catch (error) { showResponse("Rejected", error.message); }
  finally { updateButtonStates(); }
}
$("undoBtn")?.addEventListener("click", () => historyAction("undo"));
$("redoBtn")?.addEventListener("click", () => historyAction("redo"));
$("refreshTimelineBtn")?.addEventListener("click", () => refreshTimeline());

$("restoreBtn")?.addEventListener("click", async () => {
  if (!sessionId) return;
  const raw = $("restoreVersion")?.value;
  if (raw === "" || raw === undefined) { showResponse("Needs clarification", "Enter the timeline version to restore."); return; }
  try {
    const { response, data } = await apiRequest(`/api/restore/${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify({ version: Number(raw) }) });
    showResponse(data.status || (response.ok ? "Applied" : "Rejected"), data.message || "Restore request completed.");
    if (response.ok && data.status === "Applied") { clearRenderedOutput(); await refreshTimeline(false); }
  } catch (error) { showResponse("Rejected", error.message); }
});

$("renderBtn")?.addEventListener("click", async () => {
  if (!sessionId || !originalUploaded) { showResponse("Needs clarification", "Create a session and upload the original first."); return; }
  const button = $("renderBtn");
  setBusy(button, true, "Rendering and verifying…", "▶ Render video");
  setRenderStatus("Rendering…");
  clearRenderedOutput();
  setRenderStatus("Rendering…");
  try {
    const { response, data } = await apiRequest(`/api/render/${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify({}) });
    if (!response.ok || data.status !== "Applied") throw new Error(data.message || "Rendering failed.");
    const previewUrl = `${API_BASE_URL}${data.preview_url}?v=${Date.now()}`;
    const downloadUrl = `${API_BASE_URL}${data.download_url}`;
    const video = $("renderedVideo");
    if (video) { video.src = previewUrl; video.hidden = false; video.load(); }
    if ($("downloadBtn")) { $("downloadBtn").href = downloadUrl; }
    if ($("openOutputBtn")) $("openOutputBtn").href = downloadUrl;
    if ($("renderResultActions")) $("renderResultActions").hidden = false;
    if ($("verificationOutput")) $("verificationOutput").textContent = JSON.stringify(data.verification || {}, null, 2);
    setRenderStatus("Rendered · verified", true);
    showResponse("Applied", `Rendered output created: ${data.rendered_filename || "MP4"}. Duration ${formatDuration(data.duration_seconds)}. Verification report saved next to the output.`, "render");
  } catch (error) {
    setRenderStatus("Render failed");
    showResponse("Rejected", error.message, "render");
  } finally {
    if (button) { button.disabled = !sessionId || !originalUploaded; button.textContent = "▶ Render video"; }
  }
});

$("createSessionBtn")?.addEventListener("click", createSession);
$("checkBackendBtn")?.addEventListener("click", checkBackend);
window.addEventListener("beforeunload", () => { if (localVideoUrl) URL.revokeObjectURL(localVideoUrl); });

updateSessionUI();
checkBackend();
