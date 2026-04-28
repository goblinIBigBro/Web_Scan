import {
  buildJobLogDownloadUrl,
  buildJobMetricsCsvUrl,
  cancelJob,
  fetchAlgorithms,
  fetchDiscoveredResults,
  fetchEnvironmentCheck,
  fetchHealth,
  fetchJob,
  fetchJobLogDelta,
  fetchJobLogs,
  fetchJobs,
  loadResultPath,
  materializeSession,
  prepareColmapWorkspace,
  previewRemoteAlgorithm,
  reattachRemoteJob,
  remoteCheck,
  runRemoteAlgorithm,
  streamFrame,
  validateAdapter,
} from "../api/server-client.js?v=20260428-detached";

const root = document.getElementById("app-root");

const STATE_KEY = "gaussvision-workbench-state-v1";
const REMOTE_KEY = "gaussvision-remote-config-v1";
const MAX_LOG_CHARS = 180_000;
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"]);
const MODEL_EXTENSIONS = new Set([".ply"]);

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "data", label: "Off Line" },
  { id: "realtime", label: "On Line" },
  { id: "algorithm", label: "Algorithms" },
  { id: "browser", label: "Browser" },
  { id: "analysis", label: "Analysis" },
];

const PAGE_ALIASES = {
  train: "algorithm",
  monitor: "algorithm",
  debug: "data",
  viewer: "browser",
  "Remote Data": "data",
  "Local Upload": "realtime",
};

const DEFAULT_REMOTE = {
  host: "",
  port: 22,
  username: "",
  password: "",
  repo_path: "",
  workspace_root: "/tmp/web_scan/workspaces",
  output_root: "/tmp/web_scan/outputs",
  python: "python3",
  activate_cmd: "",
};

const DEFAULT_TRAINING = {
  iterations: 30000,
  voxel_size: 0.001,
  update_init_factor: 16,
  lmbda: 0.001,
  mask_lr_final: 0.0001,
  position_lr_init: 0,
  position_lr_final: 0,
  position_lr_delay_mult: 0.01,
  position_lr_max_steps: 30000,
  offset_lr_init: 0.01,
  offset_lr_final: 0.0001,
  offset_lr_delay_mult: 0.01,
  offset_lr_max_steps: 30000,
  mask_lr_init: 0.01,
  mask_lr_delay_mult: 0.01,
  mask_lr_max_steps: 30000,
  feature_lr: 0.0075,
  opacity_lr: 0.02,
  scaling_lr: 0.007,
  rotation_lr: 0.002,
};

let algorithms = [];
let validation = new Map();
let jobs = [];
let discoveredResults = [];
let environmentReport = null;
let cameraStream = null;
let streamTimer = null;
let busy = false;
let toastTimer = null;
let pendingActionKey = "";
let pressedActionKey = "";
let pressTimer = null;
const reattachInFlight = new Set();
const reattachAttempted = new Set();

const state = loadState();

function defaultState() {
  return {
    activePage: initialPage(),
    apiBaseUrl: window.location.origin,
    apiOnline: null,
    sessionId: "session-demo",
    captureId: "",
    datasetName: "",
    uploadedCount: 0,
    useExistingRemoteDataset: false,
    selectedRemoteDatasetId: "",
    remoteDatasetPath: "",
    autoColmap: true,
    algorithmFamily: "",
    operation: "train",
    outputDir: "",
    checkpointPath: "",
    renderMode: "ply",
    selectedJobId: "",
    quickPlyPath: "",
    loadedPly: null,
    remoteConfig: { ...DEFAULT_REMOTE },
    training: { ...DEFAULT_TRAINING },
    sshChecked: false,
    remoteReport: null,
    lastPreview: null,
    lastError: null,
    logCursor: 0,
    logText: "",
    metricsRows: [],
  };
}

function initialPage() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("page") || "overview";
  return PAGE_ALIASES[raw] || raw;
}

function loadState() {
  const base = defaultState();
  try {
    const stored = JSON.parse(localStorage.getItem(STATE_KEY) || "{}");
    const remoteStored = JSON.parse(localStorage.getItem(REMOTE_KEY) || "{}");
    return {
      ...base,
      ...stored,
      activePage: initialPage(),
      remoteConfig: {
        ...DEFAULT_REMOTE,
        ...stored.remoteConfig,
        ...remoteStored,
      },
      training: {
        ...DEFAULT_TRAINING,
        ...stored.training,
      },
      logText: "",
      logCursor: 0,
      lastError: null,
    };
  } catch {
    return base;
  }
}

function persistState() {
  const payload = {
    ...state,
    logText: "",
    logCursor: 0,
    lastError: null,
    remoteReport: state.remoteReport,
    lastPreview: state.lastPreview,
  };
  localStorage.setItem(STATE_KEY, JSON.stringify(payload));
}

function setPage(page, options = {}) {
  state.activePage = page;
  persistState();
  if (!options.silent) {
    const url = new URL(window.location.href);
    url.searchParams.set("page", page);
    if (page !== "result") {
      url.searchParams.delete("job");
    }
    window.history.pushState({}, "", url);
  }
  render();
  afterRender();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function summarize(value, length = 64) {
  const text = String(value ?? "").trim();
  if (text.length <= length) return text || "-";
  return `${text.slice(0, length - 1)}…`;
}

function fileExtension(value) {
  const text = String(value ?? "").split("?")[0].split("#")[0].trim().toLowerCase();
  const name = text.slice(text.lastIndexOf("/") + 1);
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot) : "";
}

function classifyAssetUrl(url) {
  const ext = fileExtension(url);
  if (MODEL_EXTENSIONS.has(ext)) return "ply";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  return "";
}

function getRenderablePlyAsset(asset = {}) {
  const sourceUrl = asset.point_cloud_url || asset.ply_url || asset.ply_path || asset.manifest_url || "";
  const isModelAsset = classifyAssetUrl(sourceUrl) === "ply"
    || (asset.manifest_url && asset.viewer_url)
    || asset.type === "ply"
    || asset.type === "manifest";
  if (!isModelAsset) return null;
  return {
    type: asset.type === "manifest" ? "manifest" : "ply",
    sourceUrl,
    viewerUrl: asset.viewer_url || "",
  };
}

function getRenderableImageAsset(asset = {}) {
  const imageUrl = asset.result_url || asset.output_url || asset.image_url || "";
  if (classifyAssetUrl(imageUrl) !== "image") return null;
  return {
    type: "image",
    imageUrl,
    sourceUrl: imageUrl,
  };
}

function classifyResultAsset(asset = {}) {
  return getRenderablePlyAsset(asset) || getRenderableImageAsset(asset) || {
    type: "",
    sourceUrl: asset.point_cloud_url || asset.result_url || asset.viewer_url || asset.output_url || "",
  };
}

function resultTypeLabel(asset = {}) {
  const plyAsset = getRenderablePlyAsset(asset);
  if (plyAsset?.type === "manifest") return "Scene Manifest";
  if (plyAsset) return "PLY 3D Model";
  if (getRenderableImageAsset(asset)) return "Image";
  return "Unknown";
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (["completed", "ok", "ready", "canceled"].includes(normalized)) return "ok";
  if (["running", "queued", "detached"].includes(normalized)) return "warn";
  if (["failed", "error"].includes(normalized)) return "bad";
  return "";
}

function isTerminal(status) {
  return ["completed", "failed", "canceled"].includes(String(status || "").toLowerCase());
}

function selectedAlgorithm() {
  return algorithms.find((item) => item.family === state.algorithmFamily) || algorithms[0] || null;
}

function supportedOperations(adapter = selectedAlgorithm()) {
  if (!adapter?.operations) return [];
  return Object.entries(adapter.operations)
    .filter(([, config]) => config?.enabled)
    .map(([name]) => name);
}

function selectedOperationConfig() {
  const adapter = selectedAlgorithm();
  return adapter?.operations?.[state.operation] || {};
}

function operationSupportsRemote() {
  return Boolean(selectedOperationConfig()?.template);
}

function selectedDataset() {
  const datasets = Array.isArray(state.remoteReport?.datasets) ? state.remoteReport.datasets : [];
  return datasets.find((item) => String(item.id || "") === String(state.selectedRemoteDatasetId || "")) || null;
}

function datasetHasColmap(dataset) {
  if (!dataset) return false;
  const stage = dataset.stage || {};
  return Boolean(
    stage.sparse
    || stage.undistorted
    || dataset.has_sparse_model
    || dataset.has_undistorted_marker
    || dataset.sparse_file_count > 0,
  );
}

function datasetNameForPayload() {
  if (state.useExistingRemoteDataset) {
    const dataset = selectedDataset();
    return String(dataset?.name || dataset?.id || state.remoteDatasetPath || state.datasetName || "remote-dataset").trim();
  }
  return String(state.datasetName || `${state.sessionId}-${state.captureId || "capture"}`).trim();
}

function ensureCaptureId(force = false) {
  if (!state.captureId || force) {
    state.captureId = `capture-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
    persistState();
  }
  return state.captureId;
}

function outputDirForPayload() {
  if (state.outputDir) return state.outputDir;
  const suffix = state.useExistingRemoteDataset
    ? (state.selectedRemoteDatasetId || "existing-dataset")
    : (state.captureId || "capture");
  return `/web/generated/runs/${state.sessionId}/${state.algorithmFamily || "algorithm"}/${suffix}`;
}

function getJob(jobId = state.selectedJobId) {
  return jobs.find((item) => item.id === jobId) || null;
}

function setBusy(next) {
  busy = Boolean(next);
}

function buttonActionKey(node) {
  if (!node) return "";
  if (node.dataset.page) return `page:${node.dataset.page}`;
  if (!node.dataset.action) return "";
  const parts = [node.dataset.action];
  for (const key of ["jobId", "datasetId", "outputDir", "mode"]) {
    if (node.dataset[key]) parts.push(node.dataset[key]);
  }
  return parts.join(":");
}

function setPressedAction(key) {
  if (!key) return;
  pressedActionKey = key;
  window.clearTimeout(pressTimer);
  pressTimer = window.setTimeout(() => {
    pressedActionKey = "";
    decorateButtonFeedback();
  }, 1800);
  decorateButtonFeedback();
}

function setPendingAction(key) {
  pendingActionKey = key || "";
  render();
  afterRender();
}

function decorateButtonFeedback() {
  root.querySelectorAll("button[data-action], button[data-page]").forEach((button) => {
    const key = buttonActionKey(button);
    const isPending = key && key === pendingActionKey;
    const isPressed = key && key === pressedActionKey;
    button.classList.toggle("is-loading", Boolean(isPending));
    button.classList.toggle("is-pressed", Boolean(isPressed));
    if (isPending) {
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
    } else {
      button.removeAttribute("aria-busy");
    }
  });
}

function showToast(message) {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    node.hidden = true;
  }, 3600);
}

function setError(error, fallback = "Action failed") {
  const payload = error?.payload || {};
  state.lastError = {
    code: payload.code || error?.code || "",
    message: payload.message || payload.error || error?.message || fallback,
    details: payload.details || {},
    nextAction: payload.next_action || "",
    status: error?.status || "",
  };
  persistState();
  render();
  afterRender();
}

async function guarded(action, fallback, actionKey = "") {
  try {
    setBusy(true);
    setPendingAction(actionKey);
    state.lastError = null;
    const result = await action();
    persistState();
    render();
    afterRender();
    return result;
  } catch (error) {
    setError(error, fallback);
    return null;
  } finally {
    setBusy(false);
    pendingActionKey = "";
    render();
    afterRender();
  }
}

function buildRunPayload(extra = {}) {
  const dataset = selectedDataset();
  const customPath = String(state.remoteDatasetPath || "").trim();
  const selectedPath = String(dataset?.path || "").trim();
  const remoteDatasetPath = customPath || selectedPath;
  return {
    algorithm_family: state.algorithmFamily,
    operation: state.operation || "train",
    session_id: state.sessionId || "default-session",
    capture_id: state.captureId,
    dataset_name: datasetNameForPayload(),
    auto_materialize: !state.useExistingRemoteDataset,
    auto_colmap: Boolean(state.autoColmap),
    use_existing_remote_dataset: Boolean(state.useExistingRemoteDataset),
    remote_dataset_id: customPath ? "" : (state.selectedRemoteDatasetId || ""),
    remote_dataset_path: remoteDatasetPath,
    workspace: "",
    output_dir: outputDirForPayload(),
    checkpoint_path: state.checkpointPath || "",
    input_path: "",
    preview_job_id: state.lastPreview?.preview_job_id || "",
    remote: { ...state.remoteConfig },
    require_remote_check: true,
    ...state.training,
    ...extra,
  };
}

function render() {
  root.innerHTML = `
    <div class="workbench">
      ${renderTopbar()}
      <div class="layout">
        <aside class="rail">${renderLeftRail()}</aside>
        <main class="main-column">${renderMain()}</main>
      </div>
    </div>
    <div id="modal-layer" class="modal-layer" hidden></div>
    <div id="toast" class="toast" hidden></div>
  `;
}

function renderTopbar() {
  return `
    <header class="topbar">
      <div class="brand-mark">
        <div class="brand-cube">GSC</div>
        <div>
          <h1 class="brand-title">Web-GSC</h1>
          <p class="brand-subtitle">Remote training and 3D results workbench</p>
        </div>
      </div>
      <nav class="nav-tabs">
        ${NAV_ITEMS.map((item) => `
          <button class="nav-tab ${state.activePage === item.id ? "active" : ""}" data-page="${item.id}" type="button">${item.label}</button>
        `).join("")}
      </nav>
      <div class="api-chip">
        <span class="status-dot ${state.apiOnline ? "ok" : state.apiOnline === false ? "bad" : "warn"}">${state.apiOnline ? "Online" : state.apiOnline === false ? "Offline" : "Checking"}</span>
        <button data-action="refresh-all" type="button" ${busy ? "disabled" : ""}>Refresh</button>
      </div>
    </header>
  `;
}

function renderLeftRail() {
  const activeJobs = jobs.filter((job) => ["queued", "running"].includes(String(job.status || "").toLowerCase()));
  return `
    <section class="panel">
      <div class="panel-head">
        <h3>Current Data</h3>
        <span class="badge ${state.useExistingRemoteDataset ? "ok" : "warn"}">${state.useExistingRemoteDataset ? "Remote reuse" : "New upload"}</span>
      </div>
      <div class="card rail-facts">
        <p class="panel-copy">Session: ${escapeHtml(state.sessionId || "-")}</p>
        <p class="panel-copy">Capture: ${escapeHtml(state.captureId || "-")}</p>
        <p class="panel-copy">Dataset: ${escapeHtml(datasetNameForPayload())}</p>
        <p class="panel-copy">Uploaded: ${state.uploadedCount || 0} image(s)</p>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h3>Active Jobs</h3>
        <span class="badge warn">${activeJobs.length}</span>
      </div>
      <div class="job-list card">
        ${activeJobs.length ? activeJobs.slice(0, 4).map((job) => renderMiniJob(job)).join("") : `<p class="panel-copy">No jobs are running.</p>`}
      </div>
    </section>
    ${renderStatusRail()}
  `;
}

function renderMiniJob(job) {
  return `
    <article class="selectable-card">
      <strong>${escapeHtml(job.algorithm_family || "-")}</strong>
      <p class="panel-copy">${escapeHtml(job.status || "-")} · ${escapeHtml(job.remote_stage || job.operation || "-")}</p>
      <button data-action="select-job" data-job-id="${escapeHtml(job.id)}" type="button">View</button>
    </article>
  `;
}

function renderStatusRail() {
  return `
    <section class="panel">
      <div class="panel-head">
        <h3>Platform Status</h3>
        <span class="status-dot ${state.apiOnline ? "ok" : state.apiOnline === false ? "bad" : "warn"}">${state.apiOnline ? "Online" : state.apiOnline === false ? "Offline" : "Checking"}</span>
      </div>
      <div class="card grid">
        <p class="panel-copy">API: ${escapeHtml(state.apiBaseUrl)}</p>
        <p class="panel-copy">SSH: ${state.sshChecked ? "Precheck passed" : "Not checked or expired"}</p>
        <p class="panel-copy">COLMAP: ${state.autoColmap ? "Automatic" : "Manual confirmation"}</p>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h3>Environment Check</h3>
        <button data-action="check-runtime" type="button">Check</button>
      </div>
      <div class="card grid">
        ${renderEnvironmentChecks()}
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h3>Current Job</h3>
        <button data-action="refresh-jobs" type="button">Refresh</button>
      </div>
      <div class="card">
        ${renderCurrentJobSummary()}
      </div>
    </section>
    ${state.lastError ? `
      <section class="panel">
        <div class="panel-head"><h3>Error Details</h3><span class="badge bad">${escapeHtml(state.lastError.code || "ERROR")}</span></div>
        <div class="error-box">
          <p>${escapeHtml(state.lastError.message)}</p>
          ${state.lastError.nextAction ? `<p class="panel-copy">Next action: ${escapeHtml(state.lastError.nextAction)}</p>` : ""}
          ${Object.keys(state.lastError.details || {}).length ? `<pre>${escapeHtml(JSON.stringify(state.lastError.details, null, 2))}</pre>` : ""}
        </div>
      </section>
    ` : ""}
  `;
}

function renderEnvironmentChecks() {
  const checks = environmentReport?.checks || [];
  if (!checks.length) return `<p class="panel-copy">Click Check to read the local web runtime and algorithm environment.</p>`;
  return checks.map((item) => `
    <div class="status-dot ${item.ok ? "ok" : item.required ? "bad" : "warn"}">
      ${escapeHtml(item.name || "-")} · ${escapeHtml(item.message || (item.ok ? "OK" : "Failed"))}
    </div>
  `).join("");
}

function renderCurrentJobSummary() {
  const job = getJob();
  if (!job) return `<p class="panel-copy">No job selected. The latest submitted job will be selected automatically.</p>`;
  return `
    <div class="grid">
      <span class="badge ${statusClass(job.status)}">${escapeHtml(job.status || "-")}</span>
      <strong>${escapeHtml(job.algorithm_family || "-")}</strong>
      <p class="panel-copy">ID: ${escapeHtml(job.id)}</p>
      <p class="panel-copy">Stage: ${escapeHtml(job.remote_stage || "-")}</p>
      <p class="panel-copy">FPS ${escapeHtml(job.metrics?.fps || "-")} · PSNR ${escapeHtml(job.metrics?.psnr || "-")} · Loss ${escapeHtml(job.metrics?.loss || "-")}</p>
      <div class="button-row">
        <button data-action="select-job" data-job-id="${escapeHtml(job.id)}" type="button">Logs</button>
        <button data-action="open-result" data-job-id="${escapeHtml(job.id)}" type="button">Results</button>
      </div>
    </div>
  `;
}

function renderMain() {
  if (state.activePage === "overview") return renderOverviewPage();
  if (state.activePage === "data") return renderDataPage();
  if (state.activePage === "realtime") return renderRealtimePage();
  if (state.activePage === "algorithm") return renderAlgorithmPage();
  if (state.activePage === "browser") return renderBrowserPage();
  if (state.activePage === "analysis") return renderAnalysisPage();
  if (state.activePage === "result") return renderResultPage();
  return renderOverviewPage();
}

function renderOverviewPage() {
  const running = jobs.filter((job) => ["queued", "running"].includes(String(job.status || "").toLowerCase())).length;
  const completed = jobs.filter((job) => job.status === "completed").length;
  return `
    <section class="panel hero">
      <p class="eyebrow">Remote-first Gaussian Workflow</p>
      <h1>The web training page is now a progressive 3D training workbench</h1>
      <div class="action-row">
        <button class="primary" data-page="data" type="button">Prepare Data</button>
        <button data-page="algorithm" type="button">Open Training</button>
        <button data-page="browser" type="button">Open PLY Browser</button>
      </div>
    </section>
    <section class="metric-grid">
      <div class="metric"><span class="muted">Platform</span><strong>${state.apiOnline ? "OK" : state.apiOnline === false ? "Offline" : "..."}</strong></div>
      <div class="metric"><span class="muted">Total Jobs</span><strong>${jobs.length}</strong></div>
      <div class="metric"><span class="muted">Running</span><strong>${running}</strong></div>
      <div class="metric"><span class="muted">Completed</span><strong>${completed}</strong></div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Training Pipeline</h2>
        <span class="badge">Capture -> Upload -> Session Prep -> COLMAP -> Train -> Render -> View</span>
      </div>
      <div class="card step-flow">
        ${["Capture", "Upload", "Session Prep", "COLMAP", "Train", "Render", "View"].map((label, index) => `
          <div class="step ${index < pipelineProgressIndex() ? "done" : index === pipelineProgressIndex() ? "active" : ""}">
            <span class="badge">${index + 1}</span>
            <h3>${label}</h3>
            <p class="panel-copy">${pipelineHint(label)}</p>
          </div>
        `).join("")}
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Recent Jobs</h2>
        <button data-page="algorithm" type="button">Open Job Monitor</button>
      </div>
      <div class="card">${renderJobsTable(jobs.slice(0, 6))}</div>
    </section>
  `;
}

function pipelineProgressIndex() {
  const job = getJob();
  if (job?.status === "completed") return 6;
  if (job?.status === "running") return 4;
  if (state.sshChecked) return 3;
  if (state.uploadedCount > 0 || state.useExistingRemoteDataset) return 2;
  return 0;
}

function pipelineHint(label) {
  const hints = {
    "Capture": "Camera or image input",
    "Upload": "Write into session/capture",
    "Session Prep": "Auto-materialize dataset",
    "COLMAP": "Remote sparse recovery",
    "Train": "Remote queue execution",
    "Render": "Return results and metrics",
    "View": "PLY first, images as fallback",
    "Data Input": "Capture or select input data",
    "Data Prep": "Materialize and prepare workspace",
    "SSH Precheck": "Verify remote access and dependencies",
    "Command Review": "Preview paths and shell command",
    "Remote Submit": "Create remote training job",
    "Logs and Metrics": "Follow logs and metrics",
    "Result Page": "Open PLY or image result",
  };
  return hints[label] || "";
}

function renderDataPage() {
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Data Input and Dataset Management</h2>
          <p class="panel-copy">Phase one keeps only the data selection, upload, remote reuse, and COLMAP state needed for training.</p>
        </div>
        <button data-action="open-dataset-modal" type="button">Name Dataset</button>
      </div>
      <div class="card split">
        <div class="grid">
          ${renderSessionFields()}
          ${renderUploadBox()}
          <div class="button-row">
            <button class="primary" data-action="upload-images" type="button">Upload to Session</button>
            <button data-action="new-capture" type="button">New Capture</button>
          </div>
        </div>
        <div class="grid">
          ${renderRemoteDatasetControls()}
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Advanced Data Prep</h2>
        <span class="badge warn">Debug fallback</span>
      </div>
      <div class="card grid two">
        <button data-action="materialize-session" type="button" ${state.uploadedCount ? "" : "disabled"}>Manual Session Materialize</button>
        <button data-action="prepare-colmap" type="button" ${state.uploadedCount ? "" : "disabled"}>Manual COLMAP Workspace</button>
      </div>
    </section>
  `;
}

function renderSessionFields() {
  return `
    <div class="form-grid">
      <label>Session ID
        <input data-bind="sessionId" value="${escapeHtml(state.sessionId)}" />
      </label>
      <label>Capture ID
        <input data-bind="captureId" value="${escapeHtml(state.captureId)}" placeholder="Auto-generated" />
      </label>
      <label class="wide">Dataset Name
        <input data-bind="datasetName" value="${escapeHtml(state.datasetName)}" placeholder="Click Name Dataset, or confirm before submit" />
      </label>
    </div>
  `;
}

function renderUploadBox() {
  return `
    <div class="dropzone">
      <strong>Select images or capture from camera</strong>
      <p class="panel-copy">Multiple images are sent one by one through /api/stream-frame for backend compatibility.</p>
      <input id="image-upload-input" type="file" accept="image/*" multiple />
      <div id="upload-preview-grid" class="preview-grid"></div>
    </div>
  `;
}

function renderRemoteDatasetControls() {
  const datasets = Array.isArray(state.remoteReport?.datasets) ? state.remoteReport.datasets : [];
  return `
    <label class="wide">
      <span><input data-bind="useExistingRemoteDataset" type="checkbox" ${state.useExistingRemoteDataset ? "checked" : ""} /> Use an existing remote dataset and skip local upload/materialize</span>
    </label>
    <label>Remote Dataset
      <select data-bind="selectedRemoteDatasetId">
        <option value="">Not selected</option>
        ${datasets.map((item) => `
          <option value="${escapeHtml(item.id || "")}" ${state.selectedRemoteDatasetId === item.id ? "selected" : ""}>
            ${escapeHtml(item.name || item.id || "unnamed")} · ${datasetHasColmap(item) ? "COLMAP OK" : "Needs COLMAP"}
          </option>
        `).join("")}
      </select>
    </label>
    <label>Custom Remote Data Path
      <input data-bind="remoteDatasetPath" value="${escapeHtml(state.remoteDatasetPath)}" placeholder="/tmp/web_scan/workspaces/datasets/.../workspace" />
    </label>
    <label class="wide">
      <span><input data-bind="autoColmap" type="checkbox" ${state.autoColmap ? "checked" : ""} /> Run remote COLMAP automatically when sparse/undistorted data is missing</span>
    </label>
    <div class="dataset-list">
      ${datasets.length ? datasets.slice(0, 6).map((item) => renderDatasetCard(item)).join("") : `<p class="panel-copy">Remote datasets appear here after the SSH precheck on the Algorithms page.</p>`}
    </div>
  `;
}

function renderDatasetCard(dataset) {
  const active = dataset.id && dataset.id === state.selectedRemoteDatasetId;
  const colmapOk = datasetHasColmap(dataset);
  return `
    <article class="selectable-card ${active ? "active" : ""}">
      <strong>${escapeHtml(dataset.name || dataset.id || "Unnamed dataset")}</strong>
      <p class="panel-copy">${escapeHtml(summarize(dataset.path, 76))}</p>
      <div class="button-row">
        <span class="badge ${colmapOk ? "ok" : "warn"}">${colmapOk ? "COLMAP Ready" : "Will need COLMAP"}</span>
        <span class="badge">${Number(dataset.frame_count || 0) || "?"} frames</span>
      </div>
      <button data-action="use-dataset" data-dataset-id="${escapeHtml(dataset.id || "")}" type="button">Use This Dataset</button>
    </article>
  `;
}

function renderRealtimePage() {
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Realtime Capture and Result Echo</h2>
          <p class="panel-copy">Keep camera capture, image upload, automatic streaming, and the processing flow.</p>
        </div>
        <span class="badge ok">LIVE READY</span>
      </div>
      <div class="card">
        ${renderUploadBox()}
        <div class="button-row">
          <button data-action="start-camera" type="button">Start Camera</button>
          <button data-action="stop-camera" type="button">Stop</button>
          <button class="primary" data-action="upload-images" type="button">Send Current Input</button>
          <button data-action="toggle-stream" type="button">${streamTimer ? "Stop Auto Upload" : "Auto Stream Upload"}</button>
        </div>
        <div class="split" style="margin-top: 14px;">
          <div>
            <p class="eyebrow">Live Preview</p>
            <video id="local-stream" class="video-frame" autoplay playsinline muted></video>
          </div>
          <div>
            <p class="eyebrow">Result Echo</p>
            ${renderProcessedResult()}
          </div>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>Processing Flow</h2><span class="badge">${state.sessionId}</span></div>
      <div class="card step-flow">
        ${["Capture", "Upload", "Session Prep", "COLMAP", "Train", "Render", "View"].map((label, index) => `
          <div class="step ${index < pipelineProgressIndex() ? "done" : index === pipelineProgressIndex() ? "active" : ""}">
            <h3>${label}</h3>
            <p class="panel-copy">${pipelineHint(label)}</p>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderProcessedResult() {
  const job = getJob();
  if (job) return renderResultSurface(job, { tall: false });
  return renderResultSurface(null, { tall: false, emptyText: "Waiting for upload or training results." });
}

function renderAlgorithmPage() {
  const adapter = selectedAlgorithm();
  const ops = supportedOperations(adapter);
  const canSubmit = canSubmitRemoteJob();
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Algorithm Management and Remote Job Scheduling</h2>
          <p class="panel-copy">Remote training is the only training entry. Local APIs stay available for debug compatibility only.</p>
        </div>
        <span class="badge ${operationSupportsRemote() ? "ok" : "bad"}">${operationSupportsRemote() ? "Remote Template OK" : "No Remote Template"}</span>
      </div>
      <div class="card grid">
        <div class="step-flow">
          ${["Data Input", "Data Prep", "SSH Precheck", "Command Review", "Remote Submit", "Logs and Metrics", "Result Page"].map((label, index) => `
            <div class="step ${index < pipelineProgressIndex() ? "done" : index === pipelineProgressIndex() ? "active" : ""}">
              <h3>${label}</h3>
              <p class="panel-copy">${pipelineHint(label) || "Move by dependency"}</p>
            </div>
          `).join("")}
        </div>
        <div class="split">
          <div class="grid">
            <div class="form-grid">
              <label>Algorithm
                <select data-bind="algorithmFamily">
                  ${algorithms.map((item) => `<option value="${escapeHtml(item.family)}" ${state.algorithmFamily === item.family ? "selected" : ""}>${escapeHtml(item.label || item.family)}</option>`).join("")}
                </select>
              </label>
              <label>Operation
                <select data-bind="operation">
                  ${ops.map((op) => `<option value="${escapeHtml(op)}" ${state.operation === op ? "selected" : ""}>${escapeHtml(op)}</option>`).join("")}
                </select>
              </label>
              <label>Local Result Output Directory
                <input data-bind="outputDir" value="${escapeHtml(state.outputDir)}" placeholder="${escapeHtml(outputDirForPayload())}" />
              </label>
              <label>Checkpoint Path
                <input data-bind="checkpointPath" value="${escapeHtml(state.checkpointPath)}" placeholder="Only required by some templates" />
              </label>
            </div>
            ${renderTrainingFields()}
            ${renderCommandPreview()}
          </div>
          <div class="grid">
            ${renderRemoteConfigForm()}
            <div class="button-row">
              <button data-action="save-remote-config" type="button">Save Remote Config</button>
              <button data-action="restore-remote-config" type="button">Restore Last Config</button>
            </div>
            <p class="panel-copy">Note: the password is saved only in this browser localStorage, visible on this machine, and never written to the codebase.</p>
            <div class="button-row">
              <button data-action="check-remote" type="button" ${busy ? "disabled" : ""}>SSH / COLMAP Precheck</button>
              <button data-action="preview-command" type="button" ${state.sshChecked ? "" : "disabled"}>Generate Command Preview</button>
              <button class="primary" data-action="submit-remote" type="button" ${canSubmit ? "" : "disabled"}>Submit Remote Job</button>
            </div>
            ${renderRemoteChecks()}
          </div>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Job Monitor</h2>
        <div class="button-row">
          <button data-action="refresh-jobs" type="button">Refresh Jobs</button>
          ${state.selectedJobId ? `<button data-action="load-log-reset" type="button">Reload Logs</button>` : ""}
        </div>
      </div>
      <div class="card grid">
        ${renderJobsTable(jobs)}
        ${renderLogPanel()}
      </div>
    </section>
  `;
}

function renderTrainingFields() {
  return `
    <details class="panel pad">
      <summary>Training Parameters and Advanced Fields</summary>
      <div class="form-grid" style="margin-top: 14px;">
        ${Object.entries(DEFAULT_TRAINING).map(([key]) => `
          <label>${escapeHtml(key)}
            <input data-training="${escapeHtml(key)}" type="number" step="any" value="${escapeHtml(state.training[key])}" />
          </label>
        `).join("")}
      </div>
    </details>
  `;
}

function renderRemoteConfigForm() {
  const remote = state.remoteConfig;
  return `
    <section class="panel pad">
      <h3>Remote Environment Config</h3>
      <div class="form-grid" style="margin-top: 14px;">
        <label>Host<input data-remote="host" value="${escapeHtml(remote.host)}" placeholder="192.168.1.20" /></label>
        <label>Port<input data-remote="port" type="number" value="${escapeHtml(remote.port)}" /></label>
        <label>Username<input data-remote="username" value="${escapeHtml(remote.username)}" placeholder="ubuntu" /></label>
        <label>Password<input data-remote="password" type="password" value="${escapeHtml(remote.password)}" /></label>
        <label class="wide">Repo Path<input data-remote="repo_path" value="${escapeHtml(remote.repo_path)}" placeholder="/home/ubuntu/HAC-plus-main" /></label>
        <label>Workspace Root<input data-remote="workspace_root" value="${escapeHtml(remote.workspace_root)}" /></label>
        <label>Output Root<input data-remote="output_root" value="${escapeHtml(remote.output_root)}" /></label>
        <label>Python<input data-remote="python" value="${escapeHtml(remote.python)}" /></label>
        <label class="wide">Activate Command<input data-remote="activate_cmd" value="${escapeHtml(remote.activate_cmd)}" placeholder="source ~/.bashrc && conda activate env" /></label>
      </div>
    </section>
  `;
}

function renderCommandPreview() {
  const preview = state.lastPreview;
  if (!preview) {
    return `
      <section class="panel pad">
        <h3>Command Review</h3>
        <p class="panel-copy">Generate a command preview after SSH precheck. Submission opens a custom confirmation dialog instead of the native browser confirm.</p>
      </section>
    `;
  }
  return `
    <section class="panel pad">
      <div class="button-row" style="justify-content: space-between;">
        <h3>Command Review</h3>
        <span class="badge ok">Preview Ready</span>
      </div>
      <div class="command-box grid" style="margin-top: 12px;">
        <p class="panel-copy">Remote Workspace: ${escapeHtml(preview.remote_workspace)}</p>
        <p class="panel-copy">Remote Output: ${escapeHtml(preview.remote_output_dir)}</p>
        <p class="panel-copy">Local Output: ${escapeHtml(preview.local_output_dir)}</p>
        ${preview.missing_inputs?.length ? `<p class="badge bad">Missing template inputs: ${escapeHtml(preview.missing_inputs.join(", "))}</p>` : `<p class="badge ok">Template inputs complete</p>`}
        <pre>${escapeHtml(preview.shell_command || preview.remote_command || "")}</pre>
      </div>
    </section>
  `;
}

function renderRemoteChecks() {
  const checks = state.remoteReport?.checks || [];
  if (!checks.length) {
    return `<section class="panel pad"><p class="panel-copy">No remote precheck result yet.</p></section>`;
  }
  return `
    <section class="panel pad">
      <h3>Remote Precheck Result</h3>
      <div class="grid" style="margin-top: 12px;">
        ${checks.map((item) => `
          <div class="status-dot ${item.ok ? "ok" : item.required ? "bad" : "warn"}">${escapeHtml(item.name)} · ${escapeHtml(item.message)}</div>
        `).join("")}
      </div>
    </section>
  `;
}

function canSubmitRemoteJob() {
  if (!state.sshChecked || !operationSupportsRemote()) return false;
  if (state.useExistingRemoteDataset) {
    const dataset = selectedDataset();
    const hasDataset = Boolean(state.remoteDatasetPath || state.selectedRemoteDatasetId);
    if (!hasDataset) return false;
    if (dataset && !datasetHasColmap(dataset) && !state.autoColmap) return false;
    return Boolean(state.lastPreview);
  }
  return state.uploadedCount > 0 && Boolean(state.lastPreview);
}

function renderJobsTable(items) {
  if (!items.length) return `<p class="panel-copy">No jobs yet.</p>`;
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Job</th><th>Status</th><th>Metrics</th><th>Dataset</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((job) => `
            <tr>
              <td>
                <strong>${escapeHtml(job.algorithm_family || "-")}</strong>
                <p class="panel-copy">${escapeHtml(summarize(job.id, 18))}</p>
              </td>
              <td>
                <span class="badge ${statusClass(job.status)}">${escapeHtml(job.status || "-")}</span>
                ${job.safe_to_close_web && !isTerminal(job.status) ? `<span class="badge ok">Safe to close page</span>` : ""}
                <p class="panel-copy">${escapeHtml(job.remote_stage || job.operation || "-")}</p>
                ${job.monitor_state === "needs_remote_config" ? `<p class="panel-copy">Waiting for remote reattach.</p>` : ""}
              </td>
              <td>FPS ${escapeHtml(job.metrics?.fps || "-")}<br />PSNR ${escapeHtml(job.metrics?.psnr || "-")}<br />Loss ${escapeHtml(job.metrics?.loss || "-")}</td>
              <td>${escapeHtml(summarize(job.remote_result?.remote_dataset_id || job.remote_dataset_id || job.dataset_name || "-", 32))}</td>
              <td>
                <div class="button-row">
                  <button data-action="select-job" data-job-id="${escapeHtml(job.id)}" type="button">Logs</button>
                  <button data-action="open-result" data-job-id="${escapeHtml(job.id)}" type="button">Results</button>
                  <button data-action="rerun-job" data-job-id="${escapeHtml(job.id)}" type="button">Rerun</button>
                  <button class="danger" data-action="cancel-job" data-job-id="${escapeHtml(job.id)}" type="button" ${isTerminal(job.status) ? "disabled" : ""}>Cancel</button>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderLogPanel() {
  const job = getJob();
  if (!job) return `<p class="panel-copy">Select a job to stream incremental logs here.</p>`;
  const logUrl = buildJobLogDownloadUrl(state.apiBaseUrl, job.id);
  const csvUrl = buildJobMetricsCsvUrl(state.apiBaseUrl, job.id);
  const downloadsEnabled = isTerminal(job.status);
  return `
    <section class="panel pad">
      <div class="button-row" style="justify-content: space-between;">
        <div>
          <h3>Logs and Metrics</h3>
          <p class="panel-copy">${escapeHtml(job.id)} · ${escapeHtml(job.status || "-")}</p>
          ${job.safe_to_close_web && !isTerminal(job.status) ? `<p class="status-dot ok">Safe to close page · remote training keeps running.</p>` : ""}
          ${job.monitor_state === "needs_remote_config" ? `<p class="status-dot warn">Detached remote job needs reattach with the saved remote config.</p>` : ""}
        </div>
        <div class="button-row">
          <a class="button-link ${downloadsEnabled ? "" : "disabled"}" href="${downloadsEnabled ? escapeHtml(logUrl) : "#"}" download>Download Logs</a>
          <a class="button-link ${downloadsEnabled ? "" : "disabled"}" href="${downloadsEnabled ? escapeHtml(csvUrl) : "#"}" download>Download metrics.csv</a>
        </div>
      </div>
      <pre id="log-tail" class="logs">${escapeHtml(state.logText || "Waiting for log output...")}</pre>
    </section>
  `;
}

function renderBrowserPage() {
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>PLY / Image Result Browser</h2>
          <p class="panel-copy">Open a project result folder or a single PLY/image file. PLY is used first, then image fallback.</p>
        </div>
        <button data-action="discover-results" type="button">Discover Results</button>
      </div>
      <div class="card grid">
        <div class="form-grid">
          <label class="wide">Result Folder / File Path
            <input data-bind="quickPlyPath" value="${escapeHtml(state.quickPlyPath)}" placeholder="/abs/path/to/project-output-or-model.ply" />
          </label>
        </div>
        <div class="button-row">
          <button class="primary" data-action="load-result" type="button">Open Result</button>
          <button data-action="open-selected-result" type="button" ${state.selectedJobId ? "" : "disabled"}>Open Current Job Result</button>
        </div>
        ${renderResultSurface(state.loadedPly, { tall: true })}
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2>Discovered Results</h2><span class="badge">${discoveredResults.length}</span></div>
      <div class="card dataset-list">
        ${discoveredResults.length ? discoveredResults.map((item) => {
          const asset = classifyResultAsset(item);
          return `
            <article class="selectable-card">
              <div class="button-row">
                <strong>${escapeHtml(summarize(item.output_dir, 84))}</strong>
                <span class="badge ${asset.type ? "ok" : "warn"}">${escapeHtml(resultTypeLabel(item))}</span>
              </div>
              <p class="panel-copy">${escapeHtml(item.family ? `${item.family} · ${asset.sourceUrl || item.resolved_path || "-"}` : asset.sourceUrl || item.resolved_path || "-")}</p>
              <button data-action="open-discovered-result" data-output-dir="${escapeHtml(item.output_dir)}" type="button">Open</button>
            </article>
          `;
        }).join("") : `<p class="panel-copy">Click Discover Results to scan generated outputs and local project result folders.</p>`}
      </div>
    </section>
  `;
}

function renderResultSurface(asset, options = {}) {
  const classified = classifyResultAsset(asset || {});
  const frameClass = `viewer-frame${options.tall === false ? "" : " tall"}`;
  if (classified.type === "ply" || classified.type === "manifest") {
    if (!classified.viewerUrl) {
      return `
        <div class="${frameClass} result-placeholder">
          <div>
            <h3>PLY 3D Model Detected</h3>
            <p class="panel-copy">${escapeHtml(classified.sourceUrl)}</p>
            <p class="panel-copy">A PLY file must be opened through the 3D viewer. No viewer URL was returned for this model.</p>
          </div>
        </div>
      `;
    }
    return `
      <section class="result-surface">
        <div class="result-toolbar">
          <span class="badge ok">${classified.type === "manifest" ? "Scene Manifest" : "PLY 3D Model"}</span>
          <span class="panel-copy">Use the 3D viewer controls to rotate and zoom.</span>
        </div>
        <iframe class="${frameClass}" src="${escapeHtml(classified.viewerUrl)}" title="PLY 3D model viewer"></iframe>
      </section>
    `;
  }
  if (classified.type === "image") {
    return `
      <section class="result-surface result-surface-image">
        <div class="result-toolbar">
          <span class="badge ok">Image Result</span>
          <span class="panel-copy">Displayed as an image. 3D rendering is skipped.</span>
        </div>
        <img class="result-image" src="${escapeHtml(classified.imageUrl)}" alt="model result" />
      </section>
    `;
  }
  return `
    <div class="${frameClass} result-placeholder">
      <div>
        <h3>Waiting for supported result assets</h3>
        <p class="panel-copy">${classified.sourceUrl ? escapeHtml(classified.sourceUrl) : escapeHtml(options.emptyText || "PLY and image files are handled by separate viewers.")}</p>
      </div>
    </div>
  `;
}

function renderAnalysisPage() {
  const job = getJob();
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Training Metrics Analysis</h2>
          <p class="panel-copy">Parse metrics.csv and job metrics to show FPS, Loss, PSNR, SSIM, LPIPS, and Iter.</p>
        </div>
        <button data-action="load-analysis" type="button" ${job ? "" : "disabled"}>Load Metrics</button>
      </div>
      <div class="card grid">
        <label>Select Job
          <select data-bind="selectedJobId">
            <option value="">Not selected</option>
            ${jobs.map((item) => `<option value="${escapeHtml(item.id)}" ${state.selectedJobId === item.id ? "selected" : ""}>${escapeHtml(item.algorithm_family || "-")} · ${escapeHtml(item.status || "-")} · ${escapeHtml(item.id.slice(0, 8))}</option>`).join("")}
          </select>
        </label>
        <div class="metric-grid">
          ${jobs.slice(0, 4).map((item) => `
            <div class="metric">
              <span class="muted">${escapeHtml(item.algorithm_family || "-")} · ${escapeHtml(item.status || "-")}</span>
              <strong>${escapeHtml(item.metrics?.psnr || item.metrics?.fps || "-")}</strong>
              <p class="panel-copy">PSNR/FPS · ${escapeHtml(item.id.slice(0, 8))}</p>
            </div>
          `).join("") || `<p class="panel-copy">No jobs to compare yet.</p>`}
        </div>
        <canvas id="metrics-chart" class="chart"></canvas>
        ${renderMetricsTable(state.metricsRows)}
      </div>
    </section>
  `;
}

function renderMetricsTable(rows) {
  if (!rows.length) return `<p class="panel-copy">No metrics yet. While running, use the log panel for live tail output; after completion, download metrics.csv.</p>`;
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Time</th><th>Iter</th><th>Loss</th><th>PSNR</th><th>SSIM</th><th>LPIPS</th><th>FPS</th></tr></thead>
        <tbody>
          ${rows.slice(-80).reverse().map((row) => `
            <tr>
              <td>${escapeHtml(row.timestamp || "-")}</td>
              <td>${escapeHtml(row.iter || "-")}</td>
              <td>${escapeHtml(row.loss || "-")}</td>
              <td>${escapeHtml(row.psnr || "-")}</td>
              <td>${escapeHtml(row.ssim || "-")}</td>
              <td>${escapeHtml(row.lpips || "-")}</td>
              <td>${escapeHtml(row.fps || "-")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderResultPage() {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get("job") || state.selectedJobId;
  const job = getJob(jobId);
  const plyAsset = job ? getRenderablePlyAsset(job) : null;
  const imageAsset = job ? getRenderableImageAsset(job) : null;
  const preferredMode = state.renderMode || "ply";
  const mode = preferredMode === "image" && imageAsset ? "image" : plyAsset ? "ply" : imageAsset ? "image" : preferredMode;
  const surfaceAsset = mode === "image"
    ? { result_url: imageAsset?.imageUrl || "" }
    : { viewer_url: plyAsset?.viewerUrl || "", point_cloud_url: plyAsset?.sourceUrl || "" };
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Result Page</h2>
          <p class="panel-copy">${job ? `${job.algorithm_family} · ${job.id}` : "Job not found. Try opening it from discovered results."}</p>
        </div>
        <div class="button-row">
          <button data-bind-render="ply" class="${mode === "ply" ? "primary" : ""}" data-action="set-render-mode" data-mode="ply" type="button" ${plyAsset ? "" : "disabled"}>PLY</button>
          <button data-bind-render="image" class="${mode === "image" ? "primary" : ""}" data-action="set-render-mode" data-mode="image" type="button" ${imageAsset ? "" : "disabled"}>Image</button>
          <button data-page="algorithm" type="button">Back to Jobs</button>
        </div>
      </div>
      <div class="card grid">
        ${job ? renderResultSurface(surfaceAsset, { tall: true }) : `<p class="panel-copy">No renderable job yet. Finish training first or open a result from the Browser page.</p>`}
        ${job && !plyAsset && !imageAsset ? `<div class="error-box"><p>No supported result file was found. Supported model files use .ply, while image results use .png, .jpg, .jpeg, .bmp, .gif, .webp, .tif, or .tiff.</p></div>` : ""}
      </div>
    </section>
  `;
}

function bindStaticEvents() {
  root.addEventListener("click", handleClick);
  root.addEventListener("change", handleChange);
  root.addEventListener("input", handleInput);
  window.addEventListener("popstate", () => {
    state.activePage = initialPage();
    const params = new URLSearchParams(window.location.search);
    if (params.get("job")) state.selectedJobId = params.get("job");
    render();
    afterRender();
  });
}

async function handleClick(event) {
  const pageButton = event.target.closest("[data-page]");
  if (pageButton) {
    setPressedAction(buttonActionKey(pageButton));
    setPage(pageButton.dataset.page);
    return;
  }

  const actionNode = event.target.closest("[data-action]");
  if (!actionNode) return;
  const action = actionNode.dataset.action;
  const jobId = actionNode.dataset.jobId || "";
  if (busy) return;
  const actionKey = buttonActionKey(actionNode);
  setPressedAction(actionKey);

  if (action === "refresh-all") await refreshAll(actionKey);
  if (action === "refresh-jobs") await guarded(refreshJobs, "Failed to refresh jobs", actionKey);
  if (action === "check-runtime") await guarded(checkRuntime, "Environment check failed", actionKey);
  if (action === "select-algorithm") selectAlgorithm(actionNode.dataset.family);
  if (action === "open-dataset-modal") await askDatasetName();
  if (action === "new-capture") newCapture();
  if (action === "upload-images") await guarded(uploadImages, "Image upload failed", actionKey);
  if (action === "materialize-session") await guarded(materializeCurrentSession, "Session materialize failed", actionKey);
  if (action === "prepare-colmap") await guarded(prepareCurrentColmap, "COLMAP workspace prep failed", actionKey);
  if (action === "use-dataset") useDataset(actionNode.dataset.datasetId);
  if (action === "start-camera") await guarded(startCamera, "Failed to start camera", actionKey);
  if (action === "stop-camera") stopCamera();
  if (action === "toggle-stream") await guarded(toggleStream, "Auto upload failed", actionKey);
  if (action === "save-remote-config") saveRemoteConfig();
  if (action === "restore-remote-config") restoreRemoteConfig();
  if (action === "check-remote") await guarded(checkRemote, "Remote precheck failed", actionKey);
  if (action === "preview-command") await guarded(previewCommand, "Command preview failed", actionKey);
  if (action === "submit-remote") await guarded(submitRemote, "Remote job submission failed", actionKey);
  if (action === "select-job") selectJob(jobId);
  if (action === "load-log-reset") await guarded(() => loadLog(true), "Failed to load logs", actionKey);
  if (action === "cancel-job") await guarded(() => cancelSelectedJob(jobId), "Failed to cancel job", actionKey);
  if (action === "open-result") openResult(jobId);
  if (action === "open-selected-result") openResult(state.selectedJobId);
  if (action === "rerun-job") rerunJob(jobId);
  if (action === "load-result") await guarded(loadQuickResult, "Failed to open result", actionKey);
  if (action === "load-ply") await guarded(loadQuickResult, "Failed to open result", actionKey);
  if (action === "discover-results") await guarded(discoverResults, "Failed to discover results", actionKey);
  if (action === "open-discovered-result") openDiscovered(actionNode.dataset.outputDir);
  if (action === "load-analysis") await guarded(loadAnalysisRows, "Failed to load metrics", actionKey);
  if (action === "set-render-mode") {
    state.renderMode = actionNode.dataset.mode || "ply";
    persistState();
    render();
    afterRender();
  }
}

function handleInput(event) {
  const node = event.target;
  if (node.matches("[data-bind]")) {
    updateBoundValue(node);
  }
  if (node.matches("[data-remote]")) {
    const key = node.dataset.remote;
    state.remoteConfig[key] = key === "port" ? Number(node.value || 22) : node.value;
    invalidateRemoteState();
    persistState();
  }
  if (node.matches("[data-training]")) {
    state.training[node.dataset.training] = Number(node.value);
    state.lastPreview = null;
    persistState();
  }
}

function handleChange(event) {
  const node = event.target;
  if (node.matches("[data-bind]")) {
    updateBoundValue(node);
    if (node.dataset.bind === "algorithmFamily") {
      normalizeOperation();
      invalidateRemoteState();
      render();
      afterRender();
    }
    if (node.dataset.bind === "operation" || node.dataset.bind === "useExistingRemoteDataset" || node.dataset.bind === "autoColmap") {
      invalidateRemoteState();
      render();
      afterRender();
    }
    if (node.dataset.bind === "selectedJobId") {
      state.logText = "";
      state.logCursor = 0;
      loadLog(true).catch(() => {});
      if (state.activePage === "analysis") {
        loadAnalysisRows()
          .then(() => {
            render();
            afterRender();
          })
          .catch(() => {});
      }
    }
  }
  if (node.id === "image-upload-input") {
    renderSelectedFiles(node.files || []);
  }
}

function updateBoundValue(node) {
  const key = node.dataset.bind;
  if (node.type === "checkbox") {
    state[key] = node.checked;
  } else {
    state[key] = node.value;
  }
  if (["sessionId", "captureId", "datasetName", "remoteDatasetPath", "outputDir", "checkpointPath"].includes(key)) {
    state.lastPreview = null;
  }
  persistState();
}

function afterRender() {
  decorateButtonFeedback();
  const video = document.getElementById("local-stream");
  if (video && cameraStream) {
    video.srcObject = cameraStream;
  }
  const logNode = document.getElementById("log-tail");
  if (logNode) {
    logNode.scrollTop = logNode.scrollHeight;
  }
  if (state.activePage === "analysis") {
    drawMetricsChart();
  }
}

function selectAlgorithm(family) {
  state.algorithmFamily = family || state.algorithmFamily;
  normalizeOperation();
  invalidateRemoteState();
  persistState();
  render();
  afterRender();
}

function normalizeOperation() {
  const ops = supportedOperations();
  if (!ops.includes(state.operation)) {
    state.operation = ops[0] || "train";
  }
}

function invalidateRemoteState() {
  state.sshChecked = false;
  state.lastPreview = null;
  state.lastError = null;
  reattachAttempted.clear();
}

async function refreshAll(actionKey = "") {
  await guarded(async () => {
    await Promise.allSettled([refreshHealth(), refreshAlgorithms(), refreshJobs(), discoverResults(false)]);
    if (state.algorithmFamily) {
      await checkRuntime(false);
    }
  }, "Failed to refresh workbench", actionKey);
}

async function refreshHealth() {
  try {
    await fetchHealth(state.apiBaseUrl);
    state.apiOnline = true;
  } catch (error) {
    state.apiOnline = false;
    throw error;
  }
}

async function refreshAlgorithms() {
  const data = await fetchAlgorithms(state.apiBaseUrl);
  algorithms = data.algorithms || [];
  validation = new Map((data.validation || []).map((item) => [item.family, item]));
  if (!state.algorithmFamily && algorithms[0]) {
    state.algorithmFamily = algorithms[0].family;
  }
  normalizeOperation();
}

async function checkRuntime(shouldRender = true) {
  const data = await fetchEnvironmentCheck(state.apiBaseUrl, state.algorithmFamily);
  environmentReport = data.report;
  if (state.algorithmFamily) {
    try {
      const adapterResult = await validateAdapter(state.apiBaseUrl, state.algorithmFamily);
      validation.set(state.algorithmFamily, adapterResult.validation);
    } catch {
      // Runtime checks should remain visible even if adapter validation fails.
    }
  }
  if (shouldRender) {
    render();
    afterRender();
  }
}

async function refreshJobs() {
  const data = await fetchJobs(state.apiBaseUrl);
  jobs = data.jobs || [];
  if (!state.selectedJobId && jobs[0]) {
    state.selectedJobId = jobs[0].id;
  }
  await autoReattachDetachedJobs();
  persistState();
}

function remoteConfigReadyForReattach() {
  const remote = state.remoteConfig || {};
  return Boolean(
    String(remote.host || "").trim()
    && String(remote.username || "").trim()
    && String(remote.password || "").trim()
    && String(remote.repo_path || "").trim()
    && String(remote.workspace_root || "").trim()
    && String(remote.output_root || "").trim(),
  );
}

function needsRemoteReattach(job) {
  if (!job?.remote_detached || isTerminal(job.status)) return false;
  const monitorState = String(job.monitor_state || "").toLowerCase();
  const status = String(job.status || "").toLowerCase();
  return ["needs_remote_config", "disconnected"].includes(monitorState) || ["detached"].includes(status);
}

async function autoReattachDetachedJobs() {
  if (!remoteConfigReadyForReattach()) return;
  const candidates = jobs.filter(needsRemoteReattach);
  await Promise.all(candidates.map(async (job) => {
    const key = `${job.id}:${state.remoteConfig.host}:${state.remoteConfig.username}`;
    if (reattachInFlight.has(key) || reattachAttempted.has(key)) return;
    reattachInFlight.add(key);
    try {
      const data = await reattachRemoteJob(state.apiBaseUrl, job.id, state.remoteConfig);
      const updated = data.job;
      if (updated?.id) {
        jobs = jobs.map((item) => item.id === updated.id ? updated : item);
        showToast(`Reattached remote monitor: ${updated.id}`);
      }
    } catch {
      reattachAttempted.add(key);
    } finally {
      reattachInFlight.delete(key);
    }
  }));
}

async function discoverResults(shouldRender = true) {
  const data = await fetchDiscoveredResults(state.apiBaseUrl, { limit: 40, maxScanDirs: 2500 });
  discoveredResults = data.results || [];
  if (shouldRender) {
    render();
    afterRender();
  }
}

async function askDatasetName() {
  const value = await openInputModal({
    title: "Name Dataset",
    description: "Give this dataset a clear name. Remote datasets will keep the same name when possible for reuse and reruns.",
    defaultValue: datasetNameForPayload(),
    placeholder: "office-apr24-batch01",
  });
  if (value) {
    state.datasetName = value;
    state.lastPreview = null;
    persistState();
    render();
    afterRender();
  }
}

function newCapture() {
  ensureCaptureId(true);
  state.uploadedCount = 0;
  state.lastPreview = null;
  persistState();
  render();
  afterRender();
}

async function startCamera() {
  if (cameraStream) return;
  cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  afterRender();
}

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  if (streamTimer) {
    window.clearInterval(streamTimer);
    streamTimer = null;
  }
  render();
  afterRender();
}

async function toggleStream() {
  if (streamTimer) {
    window.clearInterval(streamTimer);
    streamTimer = null;
    render();
    afterRender();
    return;
  }
  await startCamera();
  await uploadImages();
  streamTimer = window.setInterval(() => {
    uploadImages().catch((error) => setError(error, "Auto upload failed"));
  }, 5000);
}

async function imageFileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function captureCameraFrame() {
  await startCamera();
  const video = document.getElementById("local-stream");
  if (video && (!video.videoWidth || !video.videoHeight)) {
    await new Promise((resolve) => {
      const timer = window.setTimeout(resolve, 900);
      video.addEventListener("loadedmetadata", () => {
        window.clearTimeout(timer);
        resolve();
      }, { once: true });
    });
  }
  const canvas = document.createElement("canvas");
  canvas.width = video?.videoWidth || 1280;
  canvas.height = video?.videoHeight || 720;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return {
    imageData: canvas.toDataURL("image/png"),
    filename: `frame_${Date.now()}.png`,
  };
}

async function uploadImages() {
  ensureCaptureId();
  const input = document.getElementById("image-upload-input");
  const files = Array.from(input?.files || []);
  if (!state.datasetName) {
    await askDatasetName();
  }
  const frames = files.length
    ? await Promise.all(files.map(async (file) => ({
      imageData: await imageFileToDataUrl(file),
      filename: file.name || `upload_${Date.now()}.png`,
    })))
    : [await captureCameraFrame()];

  let lastResult = null;
  for (let index = 0; index < frames.length; index += 1) {
    const frame = frames[index];
    lastResult = await streamFrame(state.apiBaseUrl, {
      session_id: state.sessionId,
      capture_id: state.captureId,
      algorithm_family: "",
      image_data: frame.imageData,
      filename: frame.filename,
    });
    if (lastResult.capture_id) state.captureId = lastResult.capture_id;
  }
  state.uploadedCount += frames.length;
  state.useExistingRemoteDataset = false;
  state.lastPreview = null;
  showToast(`Uploaded ${frames.length} image(s) to ${state.sessionId}/${state.captureId}`);
}

function renderSelectedFiles(files) {
  const grid = document.getElementById("upload-preview-grid");
  if (!grid) return;
  const safeFiles = Array.from(files || []);
  if (!safeFiles.length) {
    grid.innerHTML = `<p class="panel-copy">No images selected. Upload will use the current camera frame.</p>`;
    return;
  }
  grid.innerHTML = safeFiles.slice(0, 12).map((file) => {
    const url = URL.createObjectURL(file);
    window.setTimeout(() => URL.revokeObjectURL(url), 20_000);
    return `<img src="${url}" alt="${escapeHtml(file.name)}" title="${escapeHtml(file.name)}" />`;
  }).join("");
}

async function materializeCurrentSession() {
  if (!state.datasetName) await askDatasetName();
  const data = await materializeSession(state.apiBaseUrl, {
    session_id: state.sessionId,
    capture_id: state.captureId,
    dataset_name: datasetNameForPayload(),
    title: datasetNameForPayload(),
  });
  showToast(`Materialize completed: ${data.result?.dataset_root || "-"}`);
}

async function prepareCurrentColmap() {
  if (!state.datasetName) await askDatasetName();
  const data = await prepareColmapWorkspace(state.apiBaseUrl, {
    session_id: state.sessionId,
    capture_id: state.captureId,
    dataset_name: datasetNameForPayload(),
    algorithm_family: state.algorithmFamily,
  });
  showToast(`COLMAP workspace ready: ${data.result?.workspace_root || "-"}`);
}

function useDataset(datasetId) {
  state.selectedRemoteDatasetId = datasetId || "";
  state.useExistingRemoteDataset = Boolean(datasetId);
  state.lastPreview = null;
  persistState();
  render();
  afterRender();
}

function saveRemoteConfig() {
  localStorage.setItem(REMOTE_KEY, JSON.stringify(state.remoteConfig));
  showToast("Remote config saved in this browser.");
}

function restoreRemoteConfig() {
  const saved = JSON.parse(localStorage.getItem(REMOTE_KEY) || "{}");
  state.remoteConfig = { ...DEFAULT_REMOTE, ...saved };
  invalidateRemoteState();
  persistState();
  render();
  afterRender();
  showToast("Restored the last remote config.");
}

async function checkRemote() {
  if (!state.algorithmFamily) throw new Error("Select an algorithm first.");
  const data = await remoteCheck(state.apiBaseUrl, {
    remote: state.remoteConfig,
    timeout_seconds: 20,
    algorithm_family: state.algorithmFamily,
    check_colmap_required: Boolean(state.autoColmap),
  });
  state.remoteReport = data.result;
  state.sshChecked = true;
  state.lastPreview = null;
  showToast("SSH / remote paths / COLMAP precheck passed.");
}

async function previewCommand() {
  validateDatasetReadiness();
  if (!state.datasetName && !state.useExistingRemoteDataset) {
    await askDatasetName();
  }
  const payload = buildRunPayload();
  const data = await previewRemoteAlgorithm(state.apiBaseUrl, payload);
  state.lastPreview = data.preview;
  state.outputDir = data.preview?.local_output_dir || state.outputDir;
  showToast("Command preview generated.");
}

function validateDatasetReadiness() {
  if (!state.useExistingRemoteDataset && state.uploadedCount <= 0) {
    throw new Error("Upload images from the Data or Realtime page before submitting remote training.");
  }
  if (state.useExistingRemoteDataset) {
    const dataset = selectedDataset();
    if (!state.selectedRemoteDatasetId && !state.remoteDatasetPath) {
      throw new Error("Select an existing remote dataset or enter a custom remote data path first.");
    }
    if (dataset && !datasetHasColmap(dataset) && !state.autoColmap) {
      throw new Error("This remote dataset lacks COLMAP sparse/undistorted data. Enable auto COLMAP or use a processed dataset.");
    }
  }
}

async function submitRemote() {
  validateDatasetReadiness();
  if (!state.sshChecked) throw new Error("Complete the SSH / remote environment precheck first.");
  if (!state.lastPreview) await previewCommand();
  const confirmed = await openConfirmModal(state.lastPreview);
  if (!confirmed) return;

  const pathConfirmation = {
    ...state.lastPreview.path_confirmation,
    confirmed: true,
    confirmed_at: new Date().toISOString(),
  };
  const data = await runRemoteAlgorithm(state.apiBaseUrl, buildRunPayload({
    output_dir: state.lastPreview.local_output_dir || outputDirForPayload(),
    path_confirmation: pathConfirmation,
  }));
  if (data.job?.id) {
    state.selectedJobId = data.job.id;
    state.logCursor = 0;
    state.logText = "";
    await refreshJobs();
    await loadLog(true);
  }
  showToast(`Remote job submitted: ${data.job?.id || "-"}`);
}

function selectJob(jobId) {
  state.selectedJobId = jobId;
  state.logCursor = 0;
  state.logText = "";
  persistState();
  render();
  afterRender();
  loadLog(true).catch(() => {});
}

async function loadLog(reset = false) {
  if (!state.selectedJobId) return;
  if (reset) {
    state.logCursor = 0;
    state.logText = "";
  }
  const data = await fetchJobLogDelta(state.apiBaseUrl, state.selectedJobId, state.logCursor);
  state.logCursor = Number(data.cursor || state.logCursor || 0);
  if (data.log_text) {
    state.logText = `${state.logText}${data.log_text}`.slice(-MAX_LOG_CHARS);
  }
  persistState();
  const logNode = document.getElementById("log-tail");
  if (logNode) {
    logNode.textContent = state.logText || "Waiting for log output...";
    logNode.scrollTop = logNode.scrollHeight;
  }
}

async function cancelSelectedJob(jobId) {
  const id = jobId || state.selectedJobId;
  if (!id) return;
  await cancelJob(state.apiBaseUrl, id, state.remoteConfig);
  await refreshJobs();
  await loadLog(false);
  showToast("Cancel requested. Logs and generated outputs will be retained.");
}

function openResult(jobId) {
  if (!jobId) return;
  state.selectedJobId = jobId;
  state.activePage = "result";
  persistState();
  const url = new URL(window.location.href);
  url.searchParams.set("page", "result");
  url.searchParams.set("job", jobId);
  window.history.pushState({}, "", url);
  render();
  afterRender();
}

function rerunJob(jobId) {
  const job = getJob(jobId);
  if (!job) return;
  state.algorithmFamily = job.algorithm_family || state.algorithmFamily;
  state.operation = job.requested_operation || "train";
  state.sessionId = job.session_id || state.sessionId;
  state.captureId = job.capture_id || state.captureId;
  state.datasetName = job.dataset_name || state.datasetName;
  state.useExistingRemoteDataset = Boolean(job.use_existing_remote_dataset);
  state.selectedRemoteDatasetId = job.remote_dataset_id || "";
  state.remoteDatasetPath = job.remote_dataset_path || "";
  state.outputDir = "";
  state.lastPreview = null;
  setPage("algorithm");
}

async function loadQuickResult() {
  if (!state.quickPlyPath) throw new Error("Enter a result folder or file path.");
  const data = await loadResultPath(state.apiBaseUrl, {
    path: state.quickPlyPath,
  });
  state.loadedPly = data;
  if (!data.ok) throw new Error(data.reason || data.error || "Result open failed");
  showToast("Result opened.");
}

function openDiscovered(outputDir) {
  const item = discoveredResults.find((result) => result.output_dir === outputDir);
  if (!item) return;
  state.loadedPly = { ok: true, ...item };
  state.activePage = "browser";
  persistState();
  render();
  afterRender();
}

async function loadAnalysisRows() {
  const job = getJob();
  if (!job) throw new Error("Select a job.");
  try {
    const url = buildJobMetricsCsvUrl(state.apiBaseUrl, job.id);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.metricsRows = parseCsv(await response.text());
  } catch {
    const data = await fetchJobLogs(state.apiBaseUrl, job.id, { page: 1, pageSize: 200, tailLines: 80 });
    state.metricsRows = data.metrics_page?.rows || [];
  }
  persistState();
}

function parseCsv(text) {
  const lines = String(text || "").trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((item) => item.trim());
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] || ""]));
  });
}

function drawMetricsChart() {
  const canvas = document.getElementById("metrics-chart");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(640, Math.floor(rect.width * dpr));
  canvas.height = Math.floor(260 * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, 260);
  ctx.fillStyle = "#030913";
  ctx.fillRect(0, 0, rect.width, 260);
  const rows = state.metricsRows.filter((row) => Number(row.psnr || row.loss || row.fps));
  if (!rows.length) {
    ctx.fillStyle = "#8ea4c5";
    ctx.fillText("No drawable metrics yet", 24, 38);
    return;
  }
  const series = [
    { key: "psnr", color: "#2f7dff" },
    { key: "loss", color: "#ff5570" },
    { key: "fps", color: "#2be48f" },
  ];
  ctx.strokeStyle = "rgba(142,164,197,0.2)";
  for (let y = 40; y < 230; y += 38) {
    ctx.beginPath();
    ctx.moveTo(42, y);
    ctx.lineTo(rect.width - 20, y);
    ctx.stroke();
  }
  series.forEach((serie, serieIndex) => {
    const values = rows.map((row) => Number(row[serie.key])).filter((value) => Number.isFinite(value));
    if (!values.length) return;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    ctx.strokeStyle = serie.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    rows.forEach((row, index) => {
      const value = Number(row[serie.key]);
      if (!Number.isFinite(value)) return;
      const x = 42 + (index / Math.max(1, rows.length - 1)) * (rect.width - 70);
      const y = 220 - ((value - min) / span) * 170;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = serie.color;
    ctx.fillText(serie.key.toUpperCase(), 48 + serieIndex * 82, 24);
  });
}

function saveRemoteField(key, value) {
  state.remoteConfig[key] = key === "port" ? Number(value || 22) : value;
  invalidateRemoteState();
  persistState();
}

function openInputModal({ title, description, defaultValue, placeholder }) {
  const layer = document.getElementById("modal-layer");
  layer.hidden = false;
  layer.innerHTML = `
    <div class="modal">
      <div class="panel-head"><h2>${escapeHtml(title)}</h2></div>
      <div class="modal-body grid">
        <p class="panel-copy">${escapeHtml(description)}</p>
        <label>Name
          <input id="modal-input" value="${escapeHtml(defaultValue)}" placeholder="${escapeHtml(placeholder)}" />
        </label>
      </div>
      <div class="modal-footer">
        <button data-modal-cancel type="button">Cancel</button>
        <button class="primary" data-modal-ok type="button">Confirm</button>
      </div>
    </div>
  `;
  return new Promise((resolve) => {
    const input = document.getElementById("modal-input");
    input.focus();
    layer.querySelector("[data-modal-cancel]").addEventListener("click", () => {
      layer.hidden = true;
      resolve("");
    });
    layer.querySelector("[data-modal-ok]").addEventListener("click", () => {
      const value = input.value.trim();
      layer.hidden = true;
      resolve(value);
    });
  });
}

function openConfirmModal(preview) {
  const layer = document.getElementById("modal-layer");
  layer.hidden = false;
  layer.innerHTML = `
    <div class="modal">
      <div class="panel-head"><h2>Pre-submit Review</h2><span class="badge warn">Path and command review</span></div>
      <div class="modal-body grid">
        <p>Review the paths and remote command below. Confirming will submit the remote training job.</p>
        <div class="command-box grid">
          <p class="panel-copy">Dataset: ${escapeHtml(preview.dataset_name || datasetNameForPayload())}</p>
          <p class="panel-copy">Operation: ${escapeHtml(preview.algorithm_family)} / ${escapeHtml(preview.operation)}</p>
          <p class="panel-copy">Local Output: ${escapeHtml(preview.local_output_dir)}</p>
          <p class="panel-copy">Remote Workspace: ${escapeHtml(preview.remote_workspace)}</p>
          <p class="panel-copy">Remote Output: ${escapeHtml(preview.remote_output_dir)}</p>
          <pre>${escapeHtml(preview.shell_command || preview.remote_command || "")}</pre>
        </div>
      </div>
      <div class="modal-footer">
        <button data-modal-cancel type="button">Cancel</button>
        <button class="primary" data-modal-ok type="button">Confirm and Submit</button>
      </div>
    </div>
  `;
  return new Promise((resolve) => {
    layer.querySelector("[data-modal-cancel]").addEventListener("click", () => {
      layer.hidden = true;
      resolve(false);
    });
    layer.querySelector("[data-modal-ok]").addEventListener("click", () => {
      layer.hidden = true;
      resolve(true);
    });
  });
}

async function poll() {
  try {
    await refreshJobs();
    if (state.selectedJobId) {
      await loadLog(false);
    }
    const editing = document.activeElement?.matches?.("input, textarea, select");
    if (!editing && ["overview", "algorithm", "result", "analysis"].includes(state.activePage)) {
      render();
      afterRender();
    }
  } catch {
    // Keep the UI usable when the backend is temporarily offline.
  }
}

async function bootstrap() {
  bindStaticEvents();
  render();
  afterRender();
  await refreshAll();
  render();
  afterRender();
  window.setInterval(poll, 5000);
}

bootstrap().catch((error) => setError(error, "Workbench startup failed"));
