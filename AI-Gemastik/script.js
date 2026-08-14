"use strict";

/* ===========================================================
   CONFIG
   =========================================================== */

// Prototype only.
// Do not expose production API keys in frontend code — this
// request is structured so it can be swapped for a call to a
// backend proxy without touching any UI code below.
const ROBOFLOW_ENDPOINT =
  "https://serverless.roboflow.com/detection-fish-6asg4/14?api_key=hqILBoYsSgXJo7OxGRSv";

const DISPLAY_LABEL = "Ikan Sebelah";
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
const REQUEST_TIMEOUT_MS = 12000;

/* ===========================================================
   DOM REFERENCES
   =========================================================== */

const el = {
  statusChip: document.getElementById("statusChip"),
  statusDot: document.getElementById("statusDot"),
  statusLabel: document.getElementById("statusLabel"),

  emptyState: document.getElementById("emptyState"),
  emptyUseCamera: document.getElementById("emptyUseCamera"),
  emptyUploadImage: document.getElementById("emptyUploadImage"),
  emptyConnectIp: document.getElementById("emptyConnectIp"),

  viewer: document.getElementById("viewer"),
  viewerMedia: document.getElementById("viewerMedia"),
  imagePreview: document.getElementById("imagePreview"),
  deviceVideo: document.getElementById("deviceVideo"),
  ipCameraStream: document.getElementById("ipCameraStream"),
  overlayCanvas: document.getElementById("overlayCanvas"),
  detectionLayer: document.getElementById("detectionLayer"),

  detectingChip: document.getElementById("detectingChip"),
  countChip: document.getElementById("countChip"),
  countLabel: document.getElementById("countLabel"),

  analyzingPill: document.getElementById("analyzingPill"),
  errorBanner: document.getElementById("errorBanner"),
  errorTitle: document.getElementById("errorTitle"),
  errorDesc: document.getElementById("errorDesc"),
  retryBtn: document.getElementById("retryBtn"),

  fileInput: document.getElementById("fileInput"),

  ipBar: document.getElementById("ipBar"),
  ipUrlInput: document.getElementById("ipUrlInput"),
  connectIpBtn: document.getElementById("connectIpBtn"),
  closeIpBar: document.getElementById("closeIpBar"),

  detectionPanel: document.getElementById("detectionPanel"),
  detectionSummary: document.getElementById("detectionSummary"),
  detectionList: document.getElementById("detectionList"),
  detectionAvg: document.getElementById("detectionAvg"),
  detectionAvgValue: document.getElementById("detectionAvgValue"),
  closeDetectionPanel: document.getElementById("closeDetectionPanel"),

  settingsPanel: document.getElementById("settingsPanel"),
  closeSettings: document.getElementById("closeSettings"),
  intervalRange: document.getElementById("intervalRange"),
  intervalValue: document.getElementById("intervalValue"),
  confidenceRange: document.getElementById("confidenceRange"),
  confidenceValue: document.getElementById("confidenceValue"),

  controls: document.getElementById("controls"),
  srcCamera: document.getElementById("srcCamera"),
  srcUpload: document.getElementById("srcUpload"),
  srcIp: document.getElementById("srcIp"),
  ctrlDetections: document.getElementById("ctrlDetections"),
  ctrlFullscreen: document.getElementById("ctrlFullscreen"),
  ctrlSettings: document.getElementById("ctrlSettings"),

  captureCanvas: document.getElementById("captureCanvas"),
  app: document.getElementById("app"),
  stage: document.getElementById("stage"),
};

/* ===========================================================
   STATE
   =========================================================== */

const state = {
  source: null,             // "image" | "camera" | "ip"
  naturalW: 0,
  naturalH: 0,
  predictions: [],           // last rendered predictions (raw, natural-space)
  loopTimer: null,
  loopBusy: false,
  detectionIntervalMs: 700,
  minConfidencePct: 40,
  mediaStream: null,
  ipRetryUrl: "",
};

/* ===========================================================
   UTILITIES
   =========================================================== */

function show(elem) { elem.hidden = false; }
function hide(elem) { elem.hidden = true; }

function setStatus(label, tone) {
  el.statusLabel.textContent = label;
  el.statusChip.dataset.tone = tone || "idle";
}

function revealStage() {
  hide(el.emptyState);
  show(el.viewer);
  show(el.controls);
}

function resetToIdle() {
  show(el.emptyState);
  hide(el.viewer);
  hide(el.controls);
  hide(el.detectionPanel);
  hide(el.settingsPanel);
  hide(el.ipBar);
  setStatus("Idle", "idle");
  setSourceSelection(null);
}

/* ===========================================================
   BASE64 / IMAGE HELPERS
   =========================================================== */

function imageToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function canvasToBase64Jpeg(canvas, quality) {
  return canvas.toDataURL("image/jpeg", quality || 0.75).split(",")[1];
}

/* ===========================================================
   ROBOFLOW API
   =========================================================== */

async function detectFish(base64Image) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(ROBOFLOW_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: base64Image,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error("Detection request failed: " + response.status);
    }

    return await response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Detection request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

function processRoboflowResponse(json) {
  const raw = (json && Array.isArray(json.predictions)) ? json.predictions : [];
  const minConf = state.minConfidencePct / 100;

  return raw
    .filter((p) => typeof p.confidence === "number" && p.confidence >= minConf)
    .map((p) => ({
      x: p.x,
      y: p.y,
      width: p.width,
      height: p.height,
      confidence: p.confidence,
      label: DISPLAY_LABEL, // every detection is labeled Ikan Bandeng regardless of source class
    }));
}

/* ===========================================================
   BOUNDING BOX GEOMETRY (object-fit: contain aware)
   =========================================================== */

function getContentRect(naturalW, naturalH) {
  const containerW = el.viewerMedia.clientWidth;
  const containerH = el.viewerMedia.clientHeight;
  if (!naturalW || !naturalH || !containerW || !containerH) return null;

  const scale = Math.min(containerW / naturalW, containerH / naturalH);
  const renderedW = naturalW * scale;
  const renderedH = naturalH * scale;
  const offsetX = (containerW - renderedW) / 2;
  const offsetY = (containerH - renderedH) / 2;

  return { offsetX, offsetY, scale, containerW, containerH };
}

function clearDetections() {
  state.predictions = [];
  const ctx = el.overlayCanvas.getContext("2d");
  ctx.clearRect(0, 0, el.overlayCanvas.width, el.overlayCanvas.height);
  el.detectionLayer.innerHTML = "";
  hide(el.countChip);
  updateDetectionPanel([]);
}

function drawBoundingBoxes() {
  const canvas = el.overlayCanvas;
  const containerW = el.viewerMedia.clientWidth;
  const containerH = el.viewerMedia.clientHeight;
  canvas.width = containerW;
  canvas.height = containerH;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  el.detectionLayer.innerHTML = "";

  const rect = getContentRect(state.naturalW, state.naturalH);
  if (!rect || state.predictions.length === 0) return;

  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent-strong").trim() || "#6fcdf3";

  state.predictions.forEach((p, idx) => {
    const boxW = p.width * rect.scale;
    const boxH = p.height * rect.scale;
    const boxLeft = rect.offsetX + (p.x - p.width / 2) * rect.scale;
    const boxTop = rect.offsetY + (p.y - p.height / 2) * rect.scale;

    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(boxLeft, boxTop, boxW, boxH);

    const label = document.createElement("div");
    label.className = "bbox-label";
    label.style.left = boxLeft + "px";
    label.style.top = boxTop + "px";
    label.innerHTML = `${p.label} <span class="conf">${(p.confidence * 100).toFixed(1)}%</span>`;
    label.addEventListener("click", () => highlightDetection(idx));
    el.detectionLayer.appendChild(label);
  });
}

function updateDetectionCount(count) {
  el.countLabel.textContent =
    count === 0 ? "No fish detected" :
    count === 1 ? "1 fish detected" :
    `${count} fish detected`;
  show(el.countChip);
}

function renderDetections(predictions) {
  state.predictions = predictions;
  drawBoundingBoxes();
  updateDetectionCount(predictions.length);
  updateDetectionPanel(predictions);
}

/* ===========================================================
   DETECTION PANEL
   =========================================================== */

function updateDetectionPanel(predictions) {
  el.detectionSummary.textContent = predictions.length === 1
    ? "1 Fish Detected"
    : `${predictions.length} Fish Detected`;

  if (predictions.length === 0) {
    el.detectionList.innerHTML = '<p class="detection-empty">No detections yet.</p>';
    hide(el.detectionAvg);
    return;
  }

  el.detectionList.innerHTML = "";
  let sum = 0;
  predictions.forEach((p, idx) => {
    sum += p.confidence;
    const item = document.createElement("div");
    item.className = "detection-item";
    item.dataset.index = String(idx);
    item.innerHTML = `<span class="di-name">${p.label}</span><span class="di-conf">${(p.confidence * 100).toFixed(1)}%</span>`;
    el.detectionList.appendChild(item);
  });

  const avg = (sum / predictions.length) * 100;
  el.detectionAvgValue.textContent = avg.toFixed(1) + "%";
  show(el.detectionAvg);
}

function highlightDetection(idx) {
  openPanel(el.detectionPanel);
  const item = el.detectionList.querySelector(`.detection-item[data-index="${idx}"]`);
  if (!item) return;
  item.scrollIntoView({ block: "nearest", behavior: "smooth" });
  item.classList.add("is-highlighted");
  setTimeout(() => item.classList.remove("is-highlighted"), 1400);
}

/* ===========================================================
   LOADING / ERROR STATES
   =========================================================== */

function setAnalyzing(isAnalyzing) {
  el.analyzingPill.hidden = !isAnalyzing;
}

function setDetectingChip(isOn) {
  el.detectingChip.hidden = !isOn;
}

function showError(title, desc) {
  el.errorTitle.textContent = title;
  el.errorDesc.textContent = desc;
  show(el.errorBanner);
}

function hideErrorBanner() {
  hide(el.errorBanner);
}

/* ===========================================================
   SOURCE SWITCHING
   =========================================================== */

function setSourceSelection(source) {
  [el.srcCamera, el.srcUpload, el.srcIp].forEach((btn) => {
    if (!btn) return;
    btn.setAttribute("aria-selected", String(btn.dataset.source === source));
  });
}

function stopAllSources() {
  stopDeviceCamera();
  stopContinuousLoop();
  hide(el.imagePreview);
  hide(el.deviceVideo);
  hide(el.ipCameraStream);
  el.ipCameraStream.onload = null;
  el.ipCameraStream.onerror = null;
  el.ipCameraStream.src = "";
  clearDetections();
  hideErrorBanner();
  setAnalyzing(false);
  setDetectingChip(false);
  hide(el.ipBar);
}

function stopContinuousLoop() {
  if (state.loopTimer) {
    clearInterval(state.loopTimer);
    state.loopTimer = null;
  }
  setDetectingChip(false);
}

/* ===========================================================
   MODE 1 — IMAGE UPLOAD
   =========================================================== */

async function handleImageFile(file) {
  if (!file) return;
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    revealStage();
    showError("Unsupported file", "Please upload a JPG, PNG, or WEBP image.");
    return;
  }

  stopAllSources();
  state.source = "image";
  revealStage();
  setSourceSelection("upload");
  setStatus("Image loaded", "live");

  const base64 = await imageToBase64(file);

  el.imagePreview.src = "data:" + file.type + ";base64," + base64;
  show(el.imagePreview);
  hide(el.deviceVideo);
  hide(el.ipCameraStream);

  el.imagePreview.onload = async () => {
    state.naturalW = el.imagePreview.naturalWidth;
    state.naturalH = el.imagePreview.naturalHeight;
    await runDetectionOnBase64(base64);
  };
}

async function runDetectionOnBase64(base64) {
  setAnalyzing(true);
  hideErrorBanner();
  try {
    const json = await detectFish(base64);
    const predictions = processRoboflowResponse(json);
    renderDetections(predictions);
  } catch (err) {
    showError("Detection failed.", "There was a problem analyzing this image. Check your connection and try again.");
  } finally {
    setAnalyzing(false);
  }
}

el.fileInput.addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) handleImageFile(file);
  el.fileInput.value = "";
});

el.retryBtn.addEventListener("click", async () => {
  hideErrorBanner();
  if (state.source === "image" && el.imagePreview.src) {
    const base64 = el.imagePreview.src.split(",")[1];
    await runDetectionOnBase64(base64);
  } else if (state.source === "camera") {
    if (!state.mediaStream) {
      // Camera never connected (e.g. permission denied) — reattempt the connection.
      await startDeviceCamera();
    } else {
      await runCameraDetectionCycle();
    }
  } else if (state.source === "ip") {
    if (!el.ipCameraStream.naturalWidth) {
      // Stream never connected — reattempt with the last URL entered.
      connectIPCamera(state.ipRetryUrl);
    } else {
      await runIpDetectionCycle();
    }
  } else {
    resetToIdle();
  }
});

/* ===========================================================
   MODE 2 — DEVICE CAMERA
   =========================================================== */

async function startDeviceCamera() {
  stopAllSources();
  state.source = "camera";
  revealStage();
  setSourceSelection("camera");
  setStatus("Connecting…", "connecting");

  try {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
    } catch (preferredErr) {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }

    state.mediaStream = stream;
    el.deviceVideo.srcObject = stream;
    show(el.deviceVideo);
    hide(el.imagePreview);
    hide(el.ipCameraStream);

    await el.deviceVideo.play();

    state.naturalW = el.deviceVideo.videoWidth;
    state.naturalH = el.deviceVideo.videoHeight;

    setStatus("Live", "live");
    setDetectingChip(true);

    state.loopTimer = setInterval(runCameraDetectionCycle, state.detectionIntervalMs);
  } catch (err) {
    setStatus("Offline", "error");
    showError("Camera access unavailable.", "Please allow camera access in your browser settings.");
  }
}

function stopDeviceCamera() {
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((t) => t.stop());
    state.mediaStream = null;
  }
  el.deviceVideo.srcObject = null;
  if (state.source === "camera") setStatus("Offline", "idle");
}

async function captureVideoFrame(sourceEl, naturalW, naturalH) {
  const canvas = el.captureCanvas;
  canvas.width = naturalW;
  canvas.height = naturalH;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(sourceEl, 0, 0, naturalW, naturalH);
  return canvas;
}

async function runCameraDetectionCycle() {
  if (state.loopBusy || state.source !== "camera") return;
  if (!el.deviceVideo.videoWidth) return;
  state.loopBusy = true;
  try {
    const naturalW = el.deviceVideo.videoWidth;
    const naturalH = el.deviceVideo.videoHeight;
    state.naturalW = naturalW;
    state.naturalH = naturalH;

    const canvas = await captureVideoFrame(el.deviceVideo, naturalW, naturalH);
    const base64 = canvasToBase64Jpeg(canvas, 0.75);
    const json = await detectFish(base64);
    const predictions = processRoboflowResponse(json);
    renderDetections(predictions);
    hideErrorBanner();
  } catch (err) {
    showError("Detection failed.", "There was a problem analyzing this frame. Check your connection and try again.");
  } finally {
    state.loopBusy = false;
  }
}

/* ===========================================================
   MODE 3 — IP CAMERA
   =========================================================== */

function connectIPCamera(url) {
  if (!url) return;
  stopAllSources();
  state.source = "ip";
  state.ipRetryUrl = url;
  revealStage();
  setSourceSelection("ip");
  setStatus("Connecting…", "connecting");
  hideErrorBanner();

  const img = el.ipCameraStream;

  const onLoad = () => {
    state.naturalW = img.naturalWidth;
    state.naturalH = img.naturalHeight;
    setStatus("Live", "live");
    setDetectingChip(true);
    show(img);
    hide(el.imagePreview);
    hide(el.deviceVideo);
    hide(el.ipBar);

    if (!state.loopTimer) {
      state.loopTimer = setInterval(runIpDetectionCycle, state.detectionIntervalMs);
    }
  };

  const onError = () => {
    setStatus("Offline", "error");
    stopContinuousLoop();
    showError(
      "Can't reach this IP camera.",
      "Check the URL, camera availability, stream format, CORS settings, and network connection."
    );
  };

  img.onload = onLoad;
  img.onerror = onError;
  img.crossOrigin = "anonymous";
  img.src = url;
}

async function runIpDetectionCycle() {
  if (state.loopBusy || state.source !== "ip") return;
  const img = el.ipCameraStream;
  if (!img.naturalWidth) return;

  state.loopBusy = true;
  try {
    const naturalW = img.naturalWidth;
    const naturalH = img.naturalHeight;
    state.naturalW = naturalW;
    state.naturalH = naturalH;

    const canvas = await captureVideoFrame(img, naturalW, naturalH);
    let base64;
    try {
      base64 = canvasToBase64Jpeg(canvas, 0.75);
    } catch (secErr) {
      // Tainted canvas: cross-origin stream without CORS headers.
      stopContinuousLoop();
      showError(
        "Stream loaded, but frames are blocked by CORS.",
        "The camera server needs to send an Access-Control-Allow-Origin header so frames can be read for detection."
      );
      return;
    }

    const json = await detectFish(base64);
    const predictions = processRoboflowResponse(json);
    renderDetections(predictions);
    hideErrorBanner();
  } catch (err) {
    showError("Detection failed.", "There was a problem analyzing this frame. Check your connection and try again.");
  } finally {
    state.loopBusy = false;
  }
}

el.connectIpBtn.addEventListener("click", () => {
  const url = el.ipUrlInput.value.trim();
  if (url) connectIPCamera(url);
});
el.ipUrlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") el.connectIpBtn.click();
});
el.closeIpBar.addEventListener("click", () => {
  hide(el.ipBar);
  if (state.source !== "ip" || !el.ipCameraStream.naturalWidth) {
    resetToIdle();
  }
});

/* ===========================================================
   SOURCE SEGMENTED CONTROL
   =========================================================== */

el.srcCamera.addEventListener("click", () => {
  if (state.source === "camera") { stopAllSources(); resetToIdle(); return; }
  startDeviceCamera();
});
el.srcUpload.addEventListener("click", () => {
  el.fileInput.click();
});
el.srcIp.addEventListener("click", () => {
  const alreadyLiveIp = state.source === "ip" && el.ipCameraStream.naturalWidth;
  if (alreadyLiveIp) { stopAllSources(); resetToIdle(); return; }
  if (state.source && state.source !== "ip") stopAllSources();
  revealStage();
  setSourceSelection("ip");
  show(el.ipBar);
  el.ipUrlInput.focus();
});

/* ===========================================================
   PANELS — detection drawer / settings drawer
   =========================================================== */

function openPanel(panelEl) {
  [el.detectionPanel, el.settingsPanel].forEach((p) => { if (p !== panelEl) hide(p); });
  show(panelEl);
  updateControlActiveStates();
}

function togglePanel(panelEl) {
  if (panelEl.hidden) openPanel(panelEl); else { hide(panelEl); updateControlActiveStates(); }
}

function updateControlActiveStates() {
  el.ctrlDetections.classList.toggle("active", !el.detectionPanel.hidden);
  el.ctrlSettings.classList.toggle("active", !el.settingsPanel.hidden);
}

el.ctrlDetections.addEventListener("click", () => togglePanel(el.detectionPanel));
el.ctrlSettings.addEventListener("click", () => togglePanel(el.settingsPanel));
el.closeDetectionPanel.addEventListener("click", () => { hide(el.detectionPanel); updateControlActiveStates(); });
el.closeSettings.addEventListener("click", () => { hide(el.settingsPanel); updateControlActiveStates(); });

/* Empty-state shortcuts */
el.emptyUseCamera.addEventListener("click", () => startDeviceCamera());
el.emptyUploadImage.addEventListener("click", () => {
  el.fileInput.click();
});
el.emptyConnectIp.addEventListener("click", () => {
  revealStage();
  setSourceSelection("ip");
  show(el.ipBar);
  el.ipUrlInput.focus();
});

/* ===========================================================
   SETTINGS — interval & confidence
   =========================================================== */

el.intervalRange.addEventListener("input", () => {
  state.detectionIntervalMs = Number(el.intervalRange.value);
  el.intervalValue.textContent = (state.detectionIntervalMs / 1000).toFixed(1) + "s";
  if (state.loopTimer && (state.source === "camera" || state.source === "ip")) {
    clearInterval(state.loopTimer);
    const cycle = state.source === "camera" ? runCameraDetectionCycle : runIpDetectionCycle;
    state.loopTimer = setInterval(cycle, state.detectionIntervalMs);
  }
});

el.confidenceRange.addEventListener("input", () => {
  state.minConfidencePct = Number(el.confidenceRange.value);
  el.confidenceValue.textContent = state.minConfidencePct + "%";
});

/* ===========================================================
   FULLSCREEN
   =========================================================== */

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    el.app.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

el.ctrlFullscreen.addEventListener("click", toggleFullscreen);
document.addEventListener("fullscreenchange", () => {
  el.ctrlFullscreen.classList.toggle("active", !!document.fullscreenElement);
  requestAnimationFrame(drawBoundingBoxes);
});

/* ===========================================================
   RESPONSIVE — recompute bounding boxes on layout changes
   =========================================================== */

const resizeObserver = new ResizeObserver(() => {
  if (state.predictions.length > 0) drawBoundingBoxes();
});
resizeObserver.observe(el.viewerMedia);

window.addEventListener("resize", () => {
  if (state.predictions.length > 0) drawBoundingBoxes();
});

/* ===========================================================
   INIT
   =========================================================== */

resetToIdle();
