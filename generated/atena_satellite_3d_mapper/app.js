const canvas = document.getElementById("terrainCanvas");
const ctx = canvas.getContext("2d");
const latInput = document.getElementById("latInput");
const lonInput = document.getElementById("lonInput");
const zoomInput = document.getElementById("zoomInput");
const resolutionInput = document.getElementById("resolutionInput");
const generateFrame = document.getElementById("generateFrame");
const toggleStream = document.getElementById("toggleStream");
const streamStatus = document.getElementById("streamStatus");
const frameId = document.getElementById("frameId");
const coordinates = document.getElementById("coordinates");
const sampleCount = document.getElementById("sampleCount");
const avgElevation = document.getElementById("avgElevation");
const confidence = document.getElementById("confidence");
const latency = document.getElementById("latency");

let streaming = true;
let frameCounter = 0;
let currentFrame = null;
let animationId = null;

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.floor(rect.width * ratio);
  canvas.height = Math.floor(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function bboxFor(lat, lon, zoom) {
  const span = 22 / (2 ** (zoom / 2.2));
  const lonSpan = span / Math.max(0.25, Math.cos((lat * Math.PI) / 180));
  return [lon - lonSpan / 2, lat - span / 2, lon + lonSpan / 2, lat + span / 2];
}

function elevation(lat, lon, t) {
  const ridge = Math.sin(((lat * 4.7 + t * 0.03) * Math.PI) / 180) * 460;
  const valley = Math.cos(((lon * 5.1 - t * 0.02) * Math.PI) / 180) * 320;
  const micro = Math.sin((((lat + lon) * 19) * Math.PI) / 180) * 70;
  return 900 + ridge + valley + micro;
}

function generateTerrainFrame() {
  const started = performance.now();
  const centerLat = Number.parseFloat(latInput.value);
  const centerLon = Number.parseFloat(lonInput.value);
  const zoom = Number.parseInt(zoomInput.value, 10);
  const resolution = Number.parseInt(resolutionInput.value, 10);
  const bbox = bboxFor(centerLat, centerLon, zoom);
  const [west, south, east, north] = bbox;
  const t = Date.now() / 1000 + frameCounter;
  const samples = [];

  for (let row = 0; row < resolution; row += 1) {
    const lat = south + ((north - south) * row) / (resolution - 1);
    for (let col = 0; col < resolution; col += 1) {
      const lon = west + ((east - west) * col) / (resolution - 1);
      samples.push({
        lat,
        lon,
        elevation_m: elevation(lat, lon, t),
        confidence: Math.max(0.72, Math.min(0.99, 0.88 + 0.1 * Math.sin((row + col + zoom) / 9))),
      });
    }
  }

  frameCounter += 1;
  return {
    frame_id: `atena-live-${Date.now()}-${resolution}x${resolution}`,
    timestamp_ms: Date.now(),
    center_lat: centerLat,
    center_lon: centerLon,
    zoom,
    bbox,
    resolution,
    samples,
    latency_ms: Math.round(performance.now() - started),
  };
}

function colorForHeight(value, min, max) {
  const ratio = (value - min) / Math.max(1, max - min);
  const r = Math.round(20 + ratio * 235);
  const g = Math.round(90 + (1 - Math.abs(ratio - 0.55)) * 130);
  const b = Math.round(120 + (1 - ratio) * 100);
  return `rgb(${r}, ${g}, ${b})`;
}

function project(row, col, elevationValue, resolution, width, height) {
  const cell = Math.min(width / (resolution * 1.18), height / (resolution * 0.78));
  const originX = width / 2;
  const originY = height * 0.16;
  const x = originX + (col - row) * cell * 0.92;
  const y = originY + (col + row) * cell * 0.48 - elevationValue * 0.055;
  return [x, y];
}

function drawFrame(frame) {
  const rect = canvas.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  ctx.clearRect(0, 0, width, height);

  const elevations = frame.samples.map((sample) => sample.elevation_m);
  const min = Math.min(...elevations);
  const max = Math.max(...elevations);
  const res = frame.resolution;

  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "#06121f");
  gradient.addColorStop(1, "#020617");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  for (let row = 0; row < res - 1; row += 1) {
    for (let col = 0; col < res - 1; col += 1) {
      const a = frame.samples[row * res + col];
      const b = frame.samples[row * res + col + 1];
      const c = frame.samples[(row + 1) * res + col + 1];
      const d = frame.samples[(row + 1) * res + col];
      const pa = project(row, col, a.elevation_m - min, res, width, height);
      const pb = project(row, col + 1, b.elevation_m - min, res, width, height);
      const pc = project(row + 1, col + 1, c.elevation_m - min, res, width, height);
      const pd = project(row + 1, col, d.elevation_m - min, res, width, height);
      const avg = (a.elevation_m + b.elevation_m + c.elevation_m + d.elevation_m) / 4;
      ctx.beginPath();
      ctx.moveTo(pa[0], pa[1]);
      ctx.lineTo(pb[0], pb[1]);
      ctx.lineTo(pc[0], pc[1]);
      ctx.lineTo(pd[0], pd[1]);
      ctx.closePath();
      ctx.fillStyle = colorForHeight(avg, min, max);
      ctx.globalAlpha = 0.86;
      ctx.fill();
      ctx.globalAlpha = 0.28;
      ctx.strokeStyle = "#dffaff";
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  const sweepX = ((Date.now() / 22) % (width + 260)) - 130;
  ctx.fillStyle = "rgba(34, 211, 238, 0.12)";
  ctx.beginPath();
  ctx.moveTo(sweepX, 0);
  ctx.lineTo(sweepX + 130, 0);
  ctx.lineTo(sweepX + 280, height);
  ctx.lineTo(sweepX + 120, height);
  ctx.closePath();
  ctx.fill();
}

function updateMetrics(frame) {
  const elevations = frame.samples.map((sample) => sample.elevation_m);
  const avg = elevations.reduce((sum, value) => sum + value, 0) / elevations.length;
  const avgConfidence = frame.samples.reduce((sum, sample) => sum + sample.confidence, 0) / frame.samples.length;
  frameId.textContent = frame.frame_id;
  coordinates.textContent = `${frame.center_lat.toFixed(4)}, ${frame.center_lon.toFixed(4)} · z${frame.zoom}`;
  sampleCount.textContent = String(frame.samples.length);
  avgElevation.textContent = `${Math.round(avg)} m`;
  confidence.textContent = `${Math.round(avgConfidence * 100)}%`;
  latency.textContent = `${frame.latency_ms} ms`;
}

function refreshFrame() {
  currentFrame = generateTerrainFrame();
  updateMetrics(currentFrame);
}

function loop() {
  if (streaming && (!currentFrame || frameCounter % 28 === 0)) refreshFrame();
  if (currentFrame) drawFrame(currentFrame);
  animationId = requestAnimationFrame(loop);
}

generateFrame.addEventListener("click", refreshFrame);
toggleStream.addEventListener("click", () => {
  streaming = !streaming;
  streamStatus.textContent = streaming ? "STREAM ONLINE" : "STREAM PAUSADO";
  toggleStream.textContent = streaming ? "Pausar" : "Retomar";
});

window.addEventListener("resize", () => {
  resizeCanvas();
  if (currentFrame) drawFrame(currentFrame);
});

resizeCanvas();
refreshFrame();
loop();
