import {
  buildDirectSceneConfig,
  loadSceneManifest,
  manifestSchemaExample,
  parseVec3Input,
} from "../loaders/scene-manifest-loader.js";
import {
  buildJobLogDownloadUrl,
  buildJobMetricsCsvUrl,
  exportScenePackage,
  fetchEnvironmentCheck,
  fetchAlgorithms,
  fetchHealth,
  fetchJob,
  fetchJobLogs,
  fetchJobs,
  materializeSession,
  prepareColmapWorkspace,
  remoteCheck,
  runRemoteAlgorithm,
  runCapturePipeline,
  streamFrame,
  submitAlgorithmJob,
  updateAdapter,
  validateAdapter,
} from "../api/server-client.js";
import { resolveRenderer } from "../renderers/renderer-registry.js";
import { getMethodDefinition } from "../scene/survey-method-registry.js";
import {
  applyAlgorithmOptions,
  bindStaticOptions,
  renderAdapterDetail,
  renderEnvironmentCheck,
  renderManifestSchema,
  renderJobs,
  renderRecentScenes,
  renderMethodRegistry,
  setOperationOptions,
  setShareUrl,
  setOverlayVisible,
  updateStatus,
  updateViewerHeader,
} from "../ui/control-panel.js";

const frame = document.getElementById("viewer-frame");
let activeRenderer = null;
let currentScene = null;
const RECENT_SCENES_KEY = "gaussian-web-recent-scenes";
let serverAlgorithms = [];
let serverValidation = new Map();
let jobPollTimer = null;
let cameraStream = null;
let streamTimer = null;
let lastJobSceneToken = "";
let lastMaterializedSession = null;
let lastColmapWorkspace = null;
let environmentReport = null;
let lastRemoteCheckReport = null;
let suppressFlowToggleSync = false;
let flowManualState = {};
let lastJobsSnapshot = [];
let uploadPreviewObjectUrls = [];

const FLOW_BLOCK_IDS = [
  "flow-runtime",
  "flow-capture",
  "flow-remote-config",
  "flow-remote-run",
  "flow-local-debug",
];
const FLOW_MANUAL_STATE_KEY = "gaussian-web-flow-manual-state-v1";
const DEFAULT_LOG_PAGE_SIZE = 20;

const jobLogState = {
  jobId: "",
  page: 1,
  pageSize: DEFAULT_LOG_PAGE_SIZE,
  totalPages: 1,
  tailLines: 120,
};

const workflowState = {
  apiChecked: false,
  adapterReady: false,
  frameReady: false,
  sessionReady: false,
  remoteConfigReady: false,
  sshChecked: false,
  jobStarted: false,
};

function isAdapterValidationReady(validation) {
  if (!validation) return false;
  const ready = validation.is_ready ?? false;
  return Boolean(ready);
}

function computeRemoteConfigReady() {
  const remote = collectRemoteConfig();
  const required = [
    remote.host,
    remote.username,
    remote.password,
    remote.repo_path,
    remote.workspace_root,
    remote.output_root,
  ];
  return required.every((item) => Boolean(String(item || "").trim()));
}

function generateCaptureBatchId() {
  return `capture-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
}

function getUploadInputNode() {
  return document.getElementById("stream-image-file");
}

function getSelectedUploadFiles() {
  return Array.from(getUploadInputNode()?.files ?? []);
}

function revokeUploadPreviewObjectUrls() {
  uploadPreviewObjectUrls.forEach((url) => {
    try {
      URL.revokeObjectURL(url);
    } catch {
      // ignore URL revoke errors
    }
  });
  uploadPreviewObjectUrls = [];
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function renderUploadSelectionSummary() {
  const summaryNode = document.getElementById("upload-file-summary");
  const previewGrid = document.getElementById("upload-preview-grid");
  if (!summaryNode || !previewGrid) return;

  revokeUploadPreviewObjectUrls();
  const files = getSelectedUploadFiles();
  if (!files.length) {
    summaryNode.textContent = "No file selected. Camera capture mode is ready.";
    const empty = document.createElement("p");
    empty.className = "upload-preview-empty";
    empty.textContent = "No photos selected yet.";
    previewGrid.replaceChildren(empty);
    return;
  }

  const totalBytes = files.reduce((sum, file) => sum + (Number(file.size) || 0), 0);
  summaryNode.textContent = `${files.length} image(s) selected · ${formatFileSize(totalBytes)}`;

  const previewLimit = 12;
  const fragment = document.createDocumentFragment();
  files.slice(0, previewLimit).forEach((file, index) => {
    const card = document.createElement("article");
    card.className = "upload-preview-card";

    const image = document.createElement("img");
    const objectUrl = URL.createObjectURL(file);
    uploadPreviewObjectUrls.push(objectUrl);
    image.src = objectUrl;
    image.alt = file.name || `selected image ${index + 1}`;

    const name = document.createElement("span");
    name.className = "upload-preview-name";
    name.textContent = `${index + 1}. ${file.name || `image_${index + 1}`}`;

    card.appendChild(image);
    card.appendChild(name);
    fragment.appendChild(card);
  });

  if (files.length > previewLimit) {
    const more = document.createElement("div");
    more.className = "upload-preview-more";
    more.textContent = `+${files.length - previewLimit} more`;
    fragment.appendChild(more);
  }

  previewGrid.replaceChildren(fragment);
}

function applyDroppedUploadFiles(files) {
  const input = getUploadInputNode();
  if (!input) return;

  const imageFiles = Array.from(files).filter((file) => String(file.type || "").startsWith("image/"));
  if (!imageFiles.length) return;

  try {
    const dataTransfer = new DataTransfer();
    imageFiles.forEach((file) => dataTransfer.items.add(file));
    input.files = dataTransfer.files;
    renderUploadSelectionSummary();
  } catch {
    // Some browsers disallow programmatic assignment of FileList.
  }
}

function clearUploadFileSelection() {
  const input = getUploadInputNode();
  if (!input) return;
  input.value = "";
  renderUploadSelectionSummary();
}

function ensureCaptureBatchId(forceNew = false) {
  const input = document.getElementById("capture-batch-id");
  if (!input) return "";
  const current = input.value.trim();
  if (!current || forceNew) {
    const next = generateCaptureBatchId();
    input.value = next;
    return next;
  }
  return current;
}

function isUseExistingRemoteDataset() {
  const node = document.getElementById("use-existing-remote-dataset");
  return Boolean(node?.checked);
}

function getSelectedRemoteDataset() {
  const select = document.getElementById("remote-dataset-select");
  if (!select) {
    return { id: "", path: "", label: "" };
  }
  const selectedOption = select.selectedOptions?.[0] ?? null;
  return {
    id: String(select.value || "").trim(),
    path: String(selectedOption?.dataset?.path || "").trim(),
    label: String(selectedOption?.textContent || "").trim(),
  };
}

function populateRemoteDatasetSelector(datasets) {
  const select = document.getElementById("remote-dataset-select");
  if (!select) return;

  const previous = String(select.value || "").trim();
  const safeDatasets = Array.isArray(datasets) ? datasets : [];

  const options = [
    '<option value="">Upload a new capture and run COLMAP</option>',
  ];

  safeDatasets.forEach((dataset) => {
    const id = String(dataset?.id || "").trim();
    if (!id) return;
    const path = String(dataset?.path || "").trim();
    const frameCount = Number(dataset?.frame_count || 0);
    const marker = String(dataset?.latest_marker || "").trim();
    const summary = [
      id,
      frameCount > 0 ? `${frameCount} frames` : "frames unknown",
      marker || "no marker",
    ].join(" · ");
    options.push(`<option value="${escapeHtml(id)}" data-path="${escapeHtml(path)}">${escapeHtml(summary)}</option>`);
  });

  select.innerHTML = options.join("");
  if (previous && safeDatasets.some((dataset) => String(dataset?.id || "").trim() === previous)) {
    select.value = previous;
  }
}

function refreshRemoteDatasetSummary(report = null) {
  const summary = document.getElementById("remote-dataset-summary");
  if (!summary) return;

  const customPath = document.getElementById("remote-dataset-path")?.value.trim() || "";
  const selected = getSelectedRemoteDataset();
  const useExisting = isUseExistingRemoteDataset();
  const availableDatasets = Array.isArray(report?.datasets)
    ? report.datasets.length
    : Math.max(0, (document.getElementById("remote-dataset-select")?.options?.length || 1) - 1);

  if (useExisting) {
    if (customPath) {
      summary.textContent = `Using custom remote dataset path: ${customPath}`;
      return;
    }
    if (selected.id) {
      summary.textContent = `Using existing remote dataset: ${selected.id}`;
      return;
    }
    summary.textContent = "Existing dataset mode is enabled. Please select a dataset or fill custom path.";
    return;
  }

  const autoColmap = document.getElementById("auto-colmap")?.checked !== false;
  summary.textContent = autoColmap
    ? `New-upload mode: uploaded frames will run remote COLMAP automatically. SSH found ${availableDatasets} existing datasets.`
    : `New-upload mode: remote COLMAP is disabled. SSH found ${availableDatasets} existing datasets.`;
}

function loadFlowManualState() {
  try {
    const raw = localStorage.getItem(FLOW_MANUAL_STATE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return parsed;
  } catch {
    return {};
  }
}

function saveFlowManualState() {
  localStorage.setItem(FLOW_MANUAL_STATE_KEY, JSON.stringify(flowManualState));
}

function registerFlowBlockToggleHandlers() {
  FLOW_BLOCK_IDS.forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.addEventListener("toggle", () => {
      if (suppressFlowToggleSync) return;
      flowManualState[id] = node.open;
      saveFlowManualState();
    });
  });
}

function flowStateForBlock(blockId) {
  const useExisting = isUseExistingRemoteDataset();
  if (blockId === "flow-runtime") {
    if (!workflowState.apiChecked || !workflowState.adapterReady) {
      return "active";
    }
    return "done";
  }
  if (blockId === "flow-capture") {
    if (!workflowState.adapterReady) return "locked";
    return workflowState.frameReady ? "done" : "active";
  }
  if (blockId === "flow-remote-config") {
    if (!workflowState.adapterReady) return "locked";
    if (!workflowState.frameReady && !useExisting) return "locked";
    return workflowState.remoteConfigReady && workflowState.sshChecked ? "done" : "active";
  }
  if (blockId === "flow-remote-run") {
    if ((!workflowState.frameReady && !useExisting) || !workflowState.remoteConfigReady || !workflowState.sshChecked) {
      return "locked";
    }
    return workflowState.jobStarted ? "done" : "active";
  }
  if (blockId === "flow-local-debug") {
    if (!workflowState.frameReady) return "locked";
    if (workflowState.jobStarted || workflowState.sessionReady) return "done";
    return "locked";
  }
  return "locked";
}

function syncFlowBlocks() {
  suppressFlowToggleSync = true;
  FLOW_BLOCK_IDS.forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    const state = flowStateForBlock(id);
    node.dataset.flowState = state;
    if (typeof flowManualState[id] === "boolean") {
      node.open = flowManualState[id];
      return;
    }
    node.open = state === "active";
  });
  suppressFlowToggleSync = false;
}

function setButtonDisabled(id, disabled) {
  const node = document.getElementById(id);
  if (node) {
    node.disabled = disabled;
  }
}

function setStepPill(id, state, text) {
  const node = document.getElementById(id);
  if (!node) return;
  node.classList.remove("locked", "active", "done");
  node.classList.add(state);
  node.textContent = text;
}

function formatApiError(error, fallbackCode = "WGSC-UNKNOWN") {
  if (!error) {
    return {
      code: fallbackCode,
      message: "Unknown error",
      reason: "",
      manualUrl: "",
      manualAnchor: "",
      nextAction: "",
    };
  }
  return {
    code: error.code || fallbackCode,
    message: error.message || "Unknown error",
    reason: error.reason || "",
    manualUrl: error.manualUrl || error.payload?.manual_url || "",
    manualAnchor: error.manualAnchor || error.payload?.manual_anchor || "",
    nextAction: error.nextAction || error.payload?.next_action || "",
  };
}

function setStepResult(stepId, state, title, detail = "") {
  const node = document.getElementById(`step-result-${stepId}`);
  if (!node) return;
  node.classList.remove("idle", "running", "success", "failed");
  node.classList.add(state);
  const detailHtml = detail ? `<p>${escapeHtml(detail)}</p>` : "";
  node.innerHTML = `<strong>${escapeHtml(title)}</strong>${detailHtml}`;
}

function selectedOperationSupportsRemote() {
  const adapter = getSelectedAdapter();
  const operation = document.getElementById("algorithm-operation").value;
  const operationConfig = adapter?.operations?.[operation];
  return Boolean(operationConfig?.enabled && operationConfig?.template);
}

function refreshWorkflowHint() {
  const node = document.getElementById("workflow-hint");
  if (!node) return;
  const useExisting = isUseExistingRemoteDataset();
  if (!workflowState.apiChecked) {
    node.textContent = "Step 1: Click 'Check Runtime'.";
    return;
  }
  if (!workflowState.adapterReady) {
    node.textContent = "Step 2: Validate adapter capability.";
    return;
  }
  if (!workflowState.frameReady && !useExisting) {
    node.textContent = "Step 3: Please send at least one frame (Send Frame).";
    return;
  }
  if (!workflowState.remoteConfigReady) {
    node.textContent = "Step 4: Fill remote host/user/password and remote paths, then run Check SSH.";
    return;
  }
  if (!workflowState.sshChecked) {
    node.textContent = "Step 4: Run Check SSH before starting remote job.";
    return;
  }
  if (!selectedOperationSupportsRemote()) {
    node.textContent = "Step 5: Current operation has no remote template. Switch operation or update adapter config.";
    return;
  }
  const remoteDatasetPath = document.getElementById("remote-dataset-path")?.value.trim() || "";
  const selectedRemoteDataset = getSelectedRemoteDataset();
  if (useExisting && !remoteDatasetPath && !selectedRemoteDataset.id) {
    node.textContent = "Step 5: Existing dataset mode is on. Select a remote dataset or enter remote dataset path.";
    return;
  }
  if (!workflowState.jobStarted) {
    node.textContent = "Step 5: Click One-click Upload and Remote Train.";
    return;
  }
  node.textContent = "Remote workflow is running or completed. You can inspect logs, refresh jobs, and export scene packages.";
}

function refreshWorkflowUI() {
  workflowState.remoteConfigReady = computeRemoteConfigReady();

  const useExisting = isUseExistingRemoteDataset();
  const remoteDatasetPath = document.getElementById("remote-dataset-path")?.value.trim() || "";
  const selectedRemoteDataset = getSelectedRemoteDataset();
  const existingDatasetReady = Boolean(remoteDatasetPath || selectedRemoteDataset.id);

  const canAdapter = workflowState.apiChecked;
  const canCapture = workflowState.adapterReady;
  const canSession = workflowState.frameReady;
  const canRunJob = workflowState.sessionReady;
  const canRefreshJobs = workflowState.apiChecked;
  const canRemoteCheck = canCapture && (canSession || useExisting) && workflowState.remoteConfigReady;
  const canRemoteTrain =
    canCapture
    && workflowState.remoteConfigReady
    && workflowState.sshChecked
    && selectedOperationSupportsRemote()
    && (!useExisting || existingDatasetReady);
  const canExport = workflowState.jobStarted;

  setButtonDisabled("check-api", false);

  setButtonDisabled("validate-adapter", !canAdapter);
  setButtonDisabled("save-adapter", !canAdapter);

  setButtonDisabled("start-camera", !canCapture);
  setButtonDisabled("send-frame", !canCapture);
  setButtonDisabled("toggle-stream", !canCapture);
  setButtonDisabled("stop-camera", !(canCapture && Boolean(cameraStream)));

  setButtonDisabled("materialize-session", !canSession);
  setButtonDisabled("use-session-workspace", !canSession);
  setButtonDisabled("prepare-colmap-workspace", !canSession);
  setButtonDisabled("use-colmap-workspace", !canSession);

  setButtonDisabled("submit-algorithm-job", !canRunJob);
  setButtonDisabled("run-capture-pipeline", !canRunJob);
  setButtonDisabled("refresh-jobs", !canRefreshJobs);
  setButtonDisabled("check-remote-ssh", !canRemoteCheck);
  setButtonDisabled("one-click-remote-train", !canRemoteTrain);

  setButtonDisabled("export-package", !canExport);

  setStepPill("step-pill-api", workflowState.apiChecked ? "done" : "active", workflowState.apiChecked ? "Done" : "Active");

  if (!workflowState.apiChecked) {
    setStepPill("step-pill-adapter", "locked", "Locked");
  } else {
    setStepPill("step-pill-adapter", workflowState.adapterReady ? "done" : "active", workflowState.adapterReady ? "Done" : "Active");
  }

  if (!workflowState.adapterReady) {
    setStepPill("step-pill-capture", "locked", "Locked");
  } else {
    setStepPill("step-pill-capture", workflowState.frameReady ? "done" : "active", workflowState.frameReady ? "Done" : "Active");
  }

  if (!workflowState.frameReady && !useExisting) {
    setStepPill("step-pill-session", "locked", "Locked");
  } else {
    setStepPill(
      "step-pill-session",
      workflowState.remoteConfigReady && workflowState.sshChecked ? "done" : "active",
      workflowState.remoteConfigReady && workflowState.sshChecked ? "Done" : "Active",
    );
  }

  if ((!workflowState.frameReady && !useExisting) || !workflowState.remoteConfigReady || !workflowState.sshChecked) {
    setStepPill("step-pill-job", "locked", "Locked");
  } else {
    setStepPill("step-pill-job", workflowState.jobStarted ? "done" : "active", workflowState.jobStarted ? "Done" : "Active");
  }

  refreshWorkflowHint();
  syncFlowBlocks();
}

function showProcessedPlaceholder(message = "Waiting for server response") {
  const placeholder = document.getElementById("processed-placeholder");
  const image = document.getElementById("processed-frame");
  const viewer = document.getElementById("processed-viewer-frame");
  placeholder.querySelector("p").textContent = message;
  placeholder.classList.remove("hidden");
  image.classList.add("hidden");
  viewer.classList.add("hidden");
}

function showProcessedImage(url) {
  const placeholder = document.getElementById("processed-placeholder");
  const image = document.getElementById("processed-frame");
  const viewer = document.getElementById("processed-viewer-frame");
  image.src = url + `?t=${Date.now()}`;
  image.classList.remove("hidden");
  viewer.classList.add("hidden");
  viewer.removeAttribute("src");
  placeholder.classList.add("hidden");
}

function showProcessedViewer(url) {
  const placeholder = document.getElementById("processed-placeholder");
  const image = document.getElementById("processed-frame");
  const viewer = document.getElementById("processed-viewer-frame");
  viewer.src = url + (url.includes("?") ? "&" : "?") + `t=${Date.now()}`;
  viewer.classList.remove("hidden");
  image.classList.add("hidden");
  image.removeAttribute("src");
  placeholder.classList.add("hidden");
}

async function mountJobResult(job) {
  if (!job) return;
  const token = job.manifest_url ?? job.point_cloud_url ?? "";
  if (!token || token === lastJobSceneToken) return;

  if (job.manifest_url) {
    await handleManifestLoad(job.manifest_url);
    lastJobSceneToken = job.manifest_url;
    return;
  }

  if (job.point_cloud_url) {
    const scene = buildDirectSceneConfig({
      sourceUrl: job.point_cloud_url,
      representation: job.representation ?? "sh",
      algorithmFamily: job.algorithm_family ?? "unknown",
    });
    scene.title = `${job.algorithm_family ?? "Algorithm"} Output`;
    scene.sceneId = job.id ?? "job-output";
    await mountScene(scene);
    lastJobSceneToken = job.point_cloud_url;
  }
}

function getApiBaseUrl() {
  return document.getElementById("api-base-url").value.trim();
}

function parseExtraArgs() {
  const raw = document.getElementById("server-extra-args").value.trim();
  if (!raw) return {};
  return JSON.parse(raw);
}

function collectPreprocessOptions() {
  return {
    parser: document.getElementById("preprocess-parser").value,
    downsample: Number(document.getElementById("preprocess-downsample").value || 1),
    mask_path: document.getElementById("preprocess-mask-path").value.trim(),
    reorient: document.getElementById("preprocess-reorient").checked,
    image_uint8: document.getElementById("preprocess-image-uint8").checked,
    async_caching: document.getElementById("preprocess-async-caching").checked,
  };
}

function collectEditorOptions() {
  return {
    translation: parseVec3Input(document.getElementById("edit-translation").value, [0, 0, 0]),
    rotation: parseVec3Input(document.getElementById("edit-rotation").value, [0, 0, 0]),
    scale: parseVec3Input(document.getElementById("edit-scale").value, [1, 1, 1]),
    background: document.getElementById("edit-background").value,
  };
}

function loadRecentScenes() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_SCENES_KEY) || "[]");
  } catch {
    return [];
  }
}

function getSelectedAdapter() {
  const family = document.getElementById("algorithm-family").value;
  return serverAlgorithms.find((item) => item.family === family) ?? getMethodDefinition(family);
}

function syncAdapterDetail() {
  const adapter = getSelectedAdapter();
  const validation = adapter ? serverValidation.get(adapter.family) : null;
  renderAdapterDetail(adapter, validation);
  const familyReport = environmentReport?.family === adapter?.family ? environmentReport : null;
  renderEnvironmentCheck(familyReport);
  if (adapter?.repo_path !== undefined) {
    document.getElementById("server-repo-path").value = adapter.repo_path ?? "";
  }
  if (adapter?.default_cwd !== undefined) {
    document.getElementById("server-default-cwd").value = adapter.default_cwd ?? "";
  }
}

function currentRuntimeContext() {
  const extraArgs = parseExtraArgs();
  return {
    family: document.getElementById("algorithm-family").value,
    repoPath: document.getElementById("server-repo-path").value.trim(),
    cwd: document.getElementById("server-default-cwd").value.trim() || extraArgs.cwd || "",
    workspace: extraArgs.workspace ?? "",
    checkpointPath: extraArgs.checkpoint_path ?? "",
  };
}

function buildPathConfirmationPayload({ family, operation, checkpointPath, outputDir }) {
  return {
    confirmed: true,
    confirmed_at: new Date().toISOString(),
    family: family ?? "",
    operation: operation ?? "",
    checkpoint_path: (checkpointPath ?? "").trim(),
    output_dir: (outputDir ?? "").trim(),
  };
}

function confirmPathSettingsOrThrow({ family, operation, checkpointPath, outputDir }) {
  const checkpointValue = (checkpointPath ?? "").trim();
  const outputValue = (outputDir ?? "").trim();

  if (!outputValue) {
    throw new Error("output_dir is required. Please fill Output Dir before submitting the job.");
  }

  const warning = checkpointValue
    ? ""
    : "\nWarning: checkpoint_path is empty. Continue only if this operation does not require checkpoint input.";

  const message = [
    "Please confirm path settings before submitting:",
    `Family: ${family ?? "-"}`,
    `Operation: ${operation ?? "-"}`,
    `checkpoint_path: ${checkpointValue || "(empty)"}`,
    `output_dir: ${outputValue}`,
    warning,
    "",
    "Click OK to continue, or Cancel to edit paths.",
  ].join("\n");

  const confirmed = window.confirm(message);
  if (!confirmed) {
    throw new Error("Job submission canceled. Please confirm checkpoint_path/output_dir first.");
  }

  return buildPathConfirmationPayload({
    family,
    operation,
    checkpointPath: checkpointValue,
    outputDir: outputValue,
  });
}

function collectRemoteConfig() {
  const port = Number(document.getElementById("remote-port").value || 22);
  return {
    host: document.getElementById("remote-host").value.trim(),
    port: Number.isFinite(port) && port > 0 ? port : 22,
    username: document.getElementById("remote-username").value.trim(),
    password: document.getElementById("remote-password").value,
    repo_path: document.getElementById("remote-repo-path").value.trim(),
    workspace_root: document.getElementById("remote-workspace-root").value.trim(),
    output_root: document.getElementById("remote-output-root").value.trim(),
    python: document.getElementById("remote-python").value.trim() || "python3",
    activate_cmd: document.getElementById("remote-activate-cmd").value.trim(),
  };
}

async function handleRemoteSshCheck() {
  const runtime = currentRuntimeContext();
  const autoColmap = document.getElementById("auto-colmap")?.checked !== false;
  const payload = {
    remote: collectRemoteConfig(),
    timeout_seconds: 20,
    algorithm_family: runtime.family,
    check_colmap_required: !isUseExistingRemoteDataset() && autoColmap,
  };
  updateStatus({ viewer: "remote-connecting" });
  const result = await remoteCheck(getApiBaseUrl(), payload);
  lastRemoteCheckReport = result.result;
  populateRemoteDatasetSelector(result.result?.datasets || []);
  refreshRemoteDatasetSummary(result.result);
  workflowState.sshChecked = true;
  updateStatus({ viewer: "remote-completed" });
  const datasetCount = Array.isArray(result.result?.datasets) ? result.result.datasets.length : 0;
  setStepResult(
    "step4",
    "success",
    "Step 4 passed",
    `${result.result?.summary || "SSH preflight checks passed."} Found ${datasetCount} remote datasets.`,
  );
  refreshWorkflowUI();
  return result;
}

function invalidateRemoteSshCheck() {
  workflowState.sshChecked = false;
  lastRemoteCheckReport = null;
  populateRemoteDatasetSelector([]);
  refreshRemoteDatasetSummary();
}

function setExtraArgs(nextArgs) {
  document.getElementById("server-extra-args").value = JSON.stringify(nextArgs, null, 2);
}

function applyJobMetrics(job) {
  if (!job) return;
  let viewerState = job.status;
  if (job.operation === "remote_train") {
    const remoteStateMap = {
      connecting: "remote-connecting",
      resolving_dataset_workspace: "remote-connecting",
      using_existing_dataset: "remote-connecting",
      uploading_workspace: "remote-uploading",
      executing_remote_colmap: "remote-training",
      saving_named_dataset: "remote-uploading",
      executing_remote_command: "remote-training",
      downloading_output: "remote-downloading",
      completed: "remote-completed",
      failed: "remote-error",
    };
    viewerState = remoteStateMap[job.remote_stage] ?? (job.status === "failed" ? "remote-error" : job.status);
  }
  updateStatus({
    job: job.id,
    viewer: viewerState,
    algoFps: job.metrics?.fps ?? "-",
    loss: job.metrics?.loss ?? "-",
    psnr: job.metrics?.psnr ?? "-",
    iter: job.metrics?.iter ?? "-",
  });
  if (job.viewer_url) {
    showProcessedViewer(job.viewer_url);
  } else if (job.result_url) {
    showProcessedImage(job.result_url);
  }
  void mountJobResult(job);
}

function startJobPolling(jobId) {
  if (jobPollTimer) {
    window.clearInterval(jobPollTimer);
  }
  jobPollTimer = window.setInterval(async () => {
    try {
      const job = await fetchJob(getApiBaseUrl(), jobId);
      applyJobMetrics(job);
      if (job.status === "completed" || job.status === "failed") {
        window.clearInterval(jobPollTimer);
        jobPollTimer = null;
        await refreshJobs();
      }
    } catch {
      window.clearInterval(jobPollTimer);
      jobPollTimer = null;
    }
  }, 2000);
}

async function startCamera() {
  if (cameraStream) return cameraStream;
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: true,
    audio: false,
  });
  const video = document.getElementById("local-stream");
  video.srcObject = cameraStream;
  refreshWorkflowUI();
  return cameraStream;
}

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  const video = document.getElementById("local-stream");
  video.srcObject = null;
  if (streamTimer) {
    window.clearInterval(streamTimer);
    streamTimer = null;
  }
  document.getElementById("toggle-stream").textContent = "Start Stream";
  refreshWorkflowUI();
}

async function imageFileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function captureCurrentFrame() {
  await startCamera();
  const video = document.getElementById("local-stream");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  const context = canvas.getContext("2d");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return {
    imageData: canvas.toDataURL("image/png"),
    filename: `frame_${Date.now()}.png`,
  };
}

async function collectFramesForUpload() {
  const files = getSelectedUploadFiles();
  if (!files.length) {
    return [await captureCurrentFrame()];
  }

  const frames = [];
  for (const file of files) {
    frames.push({
      imageData: await imageFileToDataUrl(file),
      filename: file.name || `upload_${Date.now()}.png`,
    });
  }
  return frames;
}

async function sendCurrentFrame(options = {}) {
  const triggerProcessing = options.triggerProcessing !== false;
  const placeholderMessage = options.placeholderMessage ?? "Frame uploaded, waiting for server processing";
  showProcessedPlaceholder(placeholderMessage);
  const frames = await collectFramesForUpload();
  const runtime = currentRuntimeContext();
  const sessionId = document.getElementById("stream-session-id").value.trim() || "default-session";
  const captureId = ensureCaptureBatchId();

  let lastResult = null;
  for (let index = 0; index < frames.length; index += 1) {
    const frame = frames[index];
    const payload = {
      session_id: sessionId,
      capture_id: captureId,
      algorithm_family: triggerProcessing ? runtime.family : "",
      repo_path: runtime.repoPath,
      cwd: runtime.cwd,
      workspace: runtime.workspace,
      checkpoint_path: runtime.checkpointPath,
      image_data: frame.imageData,
      filename: frame.filename,
    };
    const result = await streamFrame(getApiBaseUrl(), payload);
    lastResult = result;

    if (result.capture_id) {
      const captureNode = document.getElementById("capture-batch-id");
      if (captureNode) {
        captureNode.value = result.capture_id;
      }
    }

    if (frames.length > 1) {
      setStepResult("step3", "running", "Step 3 running", `Uploading images ${index + 1}/${frames.length} ...`);
    }
  }

  const result = lastResult;
  if (!result) {
    throw new Error("No frame was uploaded.");
  }

  if (result.viewer_url) {
    showProcessedViewer(result.viewer_url);
  } else if (result.output_url) {
    showProcessedImage(result.output_url);
  }
  if (result.job?.id) {
    applyJobMetrics(result.job);
    startJobPolling(result.job.id);
  }
  updateStatus({
    viewer: result.job ? "stream-processing" : "frame-uploaded",
    source: result.input_url ?? "-",
  });
  const uploadedText = frames.length > 1 ? `${frames.length} images` : "1 frame";
  setStepResult(
    "step3",
    "success",
    "Step 3 passed",
    `Uploaded ${uploadedText} to session ${sessionId}, capture ${result.capture_id || captureId}.`,
  );
  if (!workflowState.frameReady) {
    workflowState.frameReady = true;
    workflowState.sessionReady = false;
    workflowState.jobStarted = false;
    refreshWorkflowUI();
  }
  return {
    ...result,
    uploaded_count: frames.length,
  };
}

async function handleMaterializeSession() {
  const sessionId = document.getElementById("stream-session-id").value.trim() || "default-session";
  const captureId = ensureCaptureBatchId();
  const datasetName = document.getElementById("dataset-name")?.value.trim() || sessionId;
  const result = await materializeSession(getApiBaseUrl(), {
    session_id: sessionId,
    title: sessionId,
    capture_id: captureId,
    dataset_name: datasetName,
  });
  lastMaterializedSession = result.result;
  updateStatus({
    viewer: "session-materialized",
    source: result.result.dataset_root,
  });
  return result.result;
}

function applyMaterializedSession(result) {
  if (!result) return;
  document.getElementById("server-input-path").value = result.input_dir;
  const family = document.getElementById("algorithm-family").value;
  const outputDir = `/web/generated/runs/${result.session_id}/${family}/${result.dataset_id || "dataset"}`;
  document.getElementById("server-output-dir").value = outputDir;
  const nextArgs = {
    ...parseExtraArgs(),
    workspace: result.dataset_root,
  };
  setExtraArgs(nextArgs);
  updateStatus({
    viewer: "session-ready",
    source: result.dataset_root,
  });
  workflowState.sessionReady = true;
  workflowState.jobStarted = false;
  refreshWorkflowUI();
}

async function handlePrepareColmapWorkspace() {
  const sessionId = document.getElementById("stream-session-id").value.trim() || "default-session";
  const captureId = ensureCaptureBatchId();
  const datasetName = document.getElementById("dataset-name")?.value.trim() || sessionId;
  const runtime = currentRuntimeContext();
  const result = await prepareColmapWorkspace(getApiBaseUrl(), {
    session_id: sessionId,
    capture_id: captureId,
    dataset_name: datasetName,
    algorithm_family: runtime.family,
    repo_path: runtime.repoPath,
  });
  lastColmapWorkspace = result.result;
  updateStatus({
    viewer: "colmap-workspace-ready",
    source: result.result.workspace_root,
  });
  return result.result;
}

function applyColmapWorkspace(result) {
  if (!result) return;
  document.getElementById("server-input-path").value = result.input_dir;
  const outputDir = `/web/generated/runs/${result.session_id}/${result.family}/${result.dataset_id || "dataset"}`;
  document.getElementById("server-output-dir").value = outputDir;
  const nextArgs = {
    ...parseExtraArgs(),
    workspace: result.workspace_root,
    colmap_command: result.suggested_command,
  };
  setExtraArgs(nextArgs);
  updateStatus({
    viewer: "colmap-workspace-applied",
    source: result.workspace_root,
  });
  workflowState.sessionReady = true;
  workflowState.jobStarted = false;
  refreshWorkflowUI();
}

function saveRecentScene(scene) {
  const scenes = loadRecentScenes();
  const next = scenes.filter((item) => item.manifestUrl !== scene.manifestUrl && item.source?.url !== scene.source?.url);
  next.push({
    title: scene.title,
    sceneId: scene.sceneId,
    algorithm: scene.algorithm,
    source: scene.source,
    manifestUrl: scene.manifestUrl ?? "",
    representation: scene.representation,
  });
  localStorage.setItem(RECENT_SCENES_KEY, JSON.stringify(next.slice(-12)));
  renderRecentScenes(loadRecentScenes());
}

function sceneShareUrl(scene) {
  const url = new URL(window.location.href);
  url.searchParams.delete("manifest");
  url.searchParams.delete("source");
  url.searchParams.delete("representation");
  url.searchParams.delete("family");
  if (scene?.manifestUrl) {
    url.searchParams.set("manifest", scene.manifestUrl);
    return url.toString();
  }
  if (scene?.source?.url) {
    url.searchParams.set("source", scene.source.url);
    url.searchParams.set("representation", scene.representation ?? scene.renderer ?? "sh");
    url.searchParams.set("family", scene.algorithm?.family ?? "unknown");
    return url.toString();
  }
  return url.toString();
}

function setSchemaPreview() {
  renderManifestSchema(manifestSchemaExample());
}

function updateFromScene(scene) {
  const method = getMethodDefinition(scene.algorithm?.family);
  updateStatus({
    renderer: scene.renderer,
    algorithm: method?.label ?? scene.algorithm?.name ?? scene.algorithm?.family,
    scene: scene.title ?? scene.sceneId,
    source: scene.source?.url ?? "-",
    viewer: "loading",
    webUrl: sceneShareUrl(scene) || "-",
  });
  updateViewerHeader({
    title: scene.title ?? "Untitled Scene",
    subtitle:
      method?.notes ??
      `representation=${scene.representation ?? scene.renderer}, source=${scene.source?.format ?? "unknown"}`,
  });
  setShareUrl(sceneShareUrl(scene));
}

async function mountScene(scene) {
  if (!scene.source?.url) {
    throw new Error("Scene source URL is required.");
  }

  if (activeRenderer) {
    activeRenderer.dispose({ frame });
  }

  const renderer = resolveRenderer(scene.renderer);
  activeRenderer = renderer;
  currentScene = scene;
  updateFromScene(scene);
  saveRecentScene(scene);
  setOverlayVisible(false);
  await renderer.mount({ frame, scene });
}

async function handleManifestLoad(manifestUrl) {
  const scene = await loadSceneManifest(manifestUrl);
  scene.manifestUrl = manifestUrl;
  await mountScene(scene);
}

async function handleDirectLoad() {
  const sourceUrl = document.getElementById("source-url").value.trim();
  const representation = document.getElementById("representation").value;
  const algorithmFamily = document.getElementById("algorithm-family").value;

  if (!sourceUrl) {
    throw new Error("Model URL is required.");
  }

  const scene = buildDirectSceneConfig({
    sourceUrl,
    representation,
    algorithmFamily,
  });
  scene.metadata = {
    ...scene.metadata,
    viewerBackend: document.getElementById("viewer-backend").value,
    preprocess: collectPreprocessOptions(),
    editor: collectEditorOptions(),
  };
  await mountScene(scene);
}

async function handleApiHealthCheck() {
  const health = await fetchHealth(getApiBaseUrl());
  updateStatus({
    viewer: "api-ready",
    source: health.root_dir,
  });
  const algorithms = await fetchAlgorithms(getApiBaseUrl());
  if (Array.isArray(algorithms.algorithms)) {
    serverAlgorithms = algorithms.algorithms;
    serverValidation = new Map((algorithms.validation ?? []).map((item) => [item.family, item]));
    applyAlgorithmOptions(algorithms.algorithms);
    const currentMethod = algorithms.algorithms.find(
      (item) => item.family === document.getElementById("algorithm-family").value,
    ) ?? algorithms.algorithms[0];
    if (currentMethod) {
      document.getElementById("algorithm-family").value = currentMethod.family;
      document.getElementById("representation").value = currentMethod.representation;
      setOperationOptions(currentMethod);
      syncAdapterDetail();
    }
  }
  const family = document.getElementById("algorithm-family").value;
  const env = await fetchEnvironmentCheck(getApiBaseUrl(), family);
  environmentReport = env.report;
  renderEnvironmentCheck(environmentReport);

  const runtimeReady = Boolean(environmentReport?.runtime_ready ?? environmentReport?.web_runnable);

  workflowState.apiChecked = runtimeReady;
  workflowState.adapterReady = runtimeReady && isAdapterValidationReady(serverValidation.get(family));
  invalidateRemoteSshCheck();

  if (runtimeReady) {
    setStepResult("step1", "success", "Step 1 passed", environmentReport?.summary || "Runtime check passed.");
    updateStatus({ viewer: "api-ready" });
  } else {
    const firstRequiredFail = (environmentReport?.checks || []).find((item) => item.required && !item.ok);
    const reason = firstRequiredFail?.message || environmentReport?.summary || "Runtime check failed.";
    setStepResult("step1", "failed", "Step 1 failed", reason);
    updateStatus({ viewer: "api-error" });
  }

  if (workflowState.adapterReady) {
    setStepResult("step2", "success", "Step 2 passed", "Adapter capability is ready.");
  } else {
    setStepResult("step2", "idle", "Step 2 pending", "Validate adapter capability.");
  }

  if (!workflowState.adapterReady) {
    workflowState.frameReady = false;
    workflowState.sessionReady = false;
    workflowState.jobStarted = false;
  }
  refreshWorkflowUI();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function findJobById(jobId) {
  return (lastJobsSnapshot ?? []).find((item) => item.id === jobId) ?? null;
}

function setJobLogMeta(text) {
  const node = document.getElementById("job-log-meta");
  if (node) {
    node.textContent = text;
  }
}

async function copyCurrentJobLogTail() {
  const textarea = document.getElementById("job-log-tail");
  if (!textarea) return;
  const raw = textarea.value || "";
  if (!raw.trim()) {
    setJobLogMeta("No log content to copy.");
    return;
  }
  try {
    await navigator.clipboard.writeText(raw);
    setJobLogMeta(`Copied ${raw.length} chars from raw log tail.`);
  } catch {
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    setJobLogMeta(`Copied ${raw.length} chars from raw log tail.`);
  }
}

function renderJobMetricsRows(rows) {
  const body = document.getElementById("job-metrics-rows");
  if (!body) return;
  if (!rows?.length) {
    body.innerHTML = `
      <tr>
        <td colspan="8">No metrics yet.</td>
      </tr>
    `;
    return;
  }

  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.timestamp || "-")}</td>
          <td>${escapeHtml(row.channel || "-")}</td>
          <td>${escapeHtml(row.iter || "-")}</td>
          <td>${escapeHtml(row.loss || "-")}</td>
          <td>${escapeHtml(row.psnr || "-")}</td>
          <td>${escapeHtml(row.ssim || "-")}</td>
          <td>${escapeHtml(row.lpips || "-")}</td>
          <td>${escapeHtml(row.fps || "-")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderJobLogTail(lines) {
  const textarea = document.getElementById("job-log-tail");
  if (!textarea) return;
  textarea.value = (lines ?? []).join("");
  textarea.scrollTop = textarea.scrollHeight;
}

function updateJobMetricsPager(page, totalPages, totalRows) {
  const prev = document.getElementById("job-metrics-prev");
  const next = document.getElementById("job-metrics-next");
  const label = document.getElementById("job-metrics-page");
  if (prev) prev.disabled = page <= 1;
  if (next) next.disabled = page >= totalPages;
  if (label) {
    label.textContent = `Page ${page} / ${totalPages} · ${totalRows} rows`;
  }
}

function setJobLogDownloadLinks(jobId, job = null, payload = null) {
  const logLink = document.getElementById("download-job-log");
  const csvLink = document.getElementById("download-job-csv");
  if (!logLink || !csvLink) return;

  if (!jobId) {
    logLink.href = "#";
    csvLink.href = "#";
    logLink.classList.add("disabled-link");
    csvLink.classList.add("disabled-link");
    return;
  }

  const apiBase = getApiBaseUrl();
  const resolvedLogUrl = payload?.logs_download_url || job?.logs_download_url || buildJobLogDownloadUrl(apiBase, jobId);
  const resolvedCsvUrl = payload?.metrics_csv_url || job?.metrics_csv_url || buildJobMetricsCsvUrl(apiBase, jobId);
  logLink.href = resolvedLogUrl;
  csvLink.href = resolvedCsvUrl;
  logLink.classList.remove("disabled-link");
  csvLink.classList.remove("disabled-link");
}

function ensureJobLogsPanelVisible() {
  const systemBoard = document.getElementById("system-board");
  if (systemBoard) {
    systemBoard.open = true;
  }
  const logsPanel = document.getElementById("job-logs-panel");
  if (logsPanel) {
    logsPanel.open = true;
    logsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function populateJobLogSelector(jobs) {
  const select = document.getElementById("log-job-id");
  if (!select) return;

  const previousJobId = jobLogState.jobId;
  const orderedJobs = jobs.slice().reverse();
  select.innerHTML = [
    '<option value="">Select Job</option>',
    ...orderedJobs.map((job) => `<option value="${job.id}">${job.algorithm_family} · ${job.id.slice(0, 8)} · ${job.status}</option>`),
  ].join("");

  let nextJobId = previousJobId;
  if (nextJobId && !orderedJobs.some((job) => job.id === nextJobId)) {
    nextJobId = "";
  }
  if (!nextJobId && orderedJobs.length) {
    nextJobId = orderedJobs[0].id;
    jobLogState.page = 1;
  }

  jobLogState.jobId = nextJobId;
  select.value = nextJobId;
  setJobLogDownloadLinks(nextJobId, findJobById(nextJobId));
}

async function loadJobLogs(page = 1) {
  const selectedJobId = jobLogState.jobId;
  if (!selectedJobId) {
    setJobLogMeta("No job selected.");
    renderJobMetricsRows([]);
    renderJobLogTail([]);
    updateJobMetricsPager(1, 1, 0);
    setJobLogDownloadLinks("");
    return;
  }

  const requestedPage = Number.isFinite(page) && page > 0 ? page : 1;
  const payload = await fetchJobLogs(getApiBaseUrl(), selectedJobId, {
    page: requestedPage,
    pageSize: jobLogState.pageSize,
    tailLines: jobLogState.tailLines,
  });

  const metricsPage = payload.metrics_page ?? {};
  const resolvedPage = Number(metricsPage.page || requestedPage);
  const totalPages = Number(metricsPage.total_pages || 1);
  const totalRows = Number(metricsPage.total || 0);
  const rows = Array.isArray(metricsPage.rows) ? metricsPage.rows : [];

  jobLogState.page = resolvedPage;
  jobLogState.totalPages = totalPages;

  renderJobMetricsRows(rows);
  renderJobLogTail(payload.log_tail_lines ?? []);
  setJobLogMeta(
    `Job ${selectedJobId} · Status ${payload.status ?? "-"} · Metrics rows ${totalRows} · Tail ${jobLogState.tailLines} lines`,
  );
  updateJobMetricsPager(resolvedPage, totalPages, totalRows);
  setJobLogDownloadLinks(selectedJobId, findJobById(selectedJobId), payload);
}

async function refreshJobs() {
  const data = await fetchJobs(getApiBaseUrl());
  const jobs = data.jobs ?? [];
  lastJobsSnapshot = jobs;
  renderJobs(jobs);
  populateJobLogSelector(jobs);
  if (jobLogState.jobId) {
    await loadJobLogs(jobLogState.page);
  }
  const runningJob = jobs.slice().reverse().find((item) => item.status === "running" || item.status === "queued");
  if (runningJob) {
    applyJobMetrics(runningJob);
  }
  return jobs;
}

async function handleExportPackage() {
  const payload = {
    input_path: document.getElementById("server-input-path").value.trim(),
    output_dir: document.getElementById("server-output-dir").value.trim(),
    scene_id: document.getElementById("server-scene-id").value.trim() || "exported-scene",
    title: document.getElementById("server-scene-id").value.trim() || "Exported Scene",
    representation: document.getElementById("representation").value,
    algorithm_family: document.getElementById("algorithm-family").value,
    web_base_url: window.location.origin,
    preprocess: collectPreprocessOptions(),
    editor: collectEditorOptions(),
    viewer_backend: document.getElementById("viewer-backend").value,
  };
  const result = await exportScenePackage(getApiBaseUrl(), payload);
  updateStatus({
    viewer: "exported",
    source: result.result.scene_dir,
    webUrl: result.share_url,
  });
  setShareUrl(result.share_url);
  document.getElementById("manifest-url").value = result.manifest_url;
  if (typeof result.manifest_url === "string") {
    await handleManifestLoad(result.manifest_url);
  }
}

async function handleSubmitAlgorithmJob() {
  const extraArgs = parseExtraArgs();
  const algorithmFamily = document.getElementById("algorithm-family").value;
  const operation = document.getElementById("algorithm-operation").value;
  const outputDir = document.getElementById("server-output-dir").value.trim();
  const checkpointPath = extraArgs.checkpoint_path ?? "";
  const pathConfirmation = confirmPathSettingsOrThrow({
    family: algorithmFamily,
    operation,
    checkpointPath,
    outputDir,
  });

  const payload = {
    algorithm_family: algorithmFamily,
    operation,
    input_path: document.getElementById("server-input-path").value.trim(),
    output_dir: outputDir,
    cwd: extraArgs.cwd ?? "",
    workspace: extraArgs.workspace ?? "",
    checkpoint_path: checkpointPath,
    repo_path: document.getElementById("server-repo-path").value.trim(),
    source: document.getElementById("server-input-path").value.trim(),
    preprocess: collectPreprocessOptions(),
    editor: collectEditorOptions(),
    viewer_backend: document.getElementById("viewer-backend").value,
    path_confirmation: pathConfirmation,
  };
  const result = await submitAlgorithmJob(getApiBaseUrl(), payload);
  applyJobMetrics(result.job);
  jobLogState.jobId = result.job?.id ?? jobLogState.jobId;
  jobLogState.page = 1;
  await refreshJobs();
  startJobPolling(result.job.id);
  workflowState.jobStarted = true;
  refreshWorkflowUI();
}

async function handleRunCapturePipeline() {
  const runtime = currentRuntimeContext();
  const sessionId = document.getElementById("stream-session-id").value.trim() || "default-session";
  const outputDir =
    document.getElementById("server-output-dir").value.trim() ||
    `/web/generated/runs/${sessionId}/${runtime.family}`;
  const result = await runCapturePipeline(getApiBaseUrl(), {
    session_id: sessionId,
    algorithm_family: runtime.family,
    output_dir: outputDir,
    repo_path: runtime.repoPath,
    checkpoint_path: runtime.checkpointPath,
    execute_immediately: true,
  });
  document.getElementById("server-output-dir").value = result.pipeline.output_dir;
  const nextArgs = {
    ...parseExtraArgs(),
    workspace: result.pipeline.workspace.workspace_root,
    capture_pipeline_script: result.pipeline.script_path,
    colmap_command: result.pipeline.workspace.suggested_command,
  };
  setExtraArgs(nextArgs);
  if (result.job?.id) {
    applyJobMetrics(result.job);
    jobLogState.jobId = result.job.id;
    jobLogState.page = 1;
    await refreshJobs();
    startJobPolling(result.job.id);
  }
  updateStatus({
    viewer: "capture-pipeline-running",
    source: result.pipeline.workspace.workspace_root,
  });
  workflowState.jobStarted = true;
  refreshWorkflowUI();
}

async function handleOneClickRemoteTrain() {
  const runtime = currentRuntimeContext();
  const sessionId = document.getElementById("stream-session-id").value.trim() || "default-session";
  const operation = document.getElementById("algorithm-operation").value;
  const useExisting = isUseExistingRemoteDataset();
  const selectedRemoteDataset = getSelectedRemoteDataset();
  const remoteDatasetPath = document.getElementById("remote-dataset-path")?.value.trim() || "";
  const effectiveRemoteDatasetPath = remoteDatasetPath || selectedRemoteDataset.path;
  const autoColmap = document.getElementById("auto-colmap")?.checked !== false;
  const captureId = ensureCaptureBatchId();
  const datasetName = document.getElementById("dataset-name")?.value.trim() || `${sessionId}-${captureId}`;

  if (!workflowState.sshChecked) {
    throw new Error("Step 4 is not completed. Please run 'Check SSH' first.");
  }
  if (!selectedOperationSupportsRemote()) {
    throw new Error(`Operation ${operation} is not available for remote execution in ${runtime.family}.`);
  }
  if (useExisting && !selectedRemoteDataset.id && !effectiveRemoteDatasetPath) {
    throw new Error("Existing dataset mode is enabled. Please select a remote dataset or provide remote dataset path.");
  }

  setStepResult("step5", "running", "Step 5 running", `Submitting remote ${runtime.family}/${operation} job...`);
  if (!useExisting) {
    updateStatus({ viewer: "remote-uploading" });
    await sendCurrentFrame({
      triggerProcessing: false,
      placeholderMessage: "Frame uploaded, preparing remote training",
    });
  }

  const outputNode = document.getElementById("server-output-dir");
  const outputSuffix = useExisting ? (selectedRemoteDataset.id || "existing-dataset") : captureId;
  const outputDir = outputNode.value.trim() || `/web/generated/runs/${sessionId}/${runtime.family}/${outputSuffix}`;
  outputNode.value = outputDir;

  const pathConfirmation = confirmPathSettingsOrThrow({
    family: runtime.family,
    operation,
    checkpointPath: runtime.checkpointPath,
    outputDir,
  });

  updateStatus({ viewer: "remote-connecting" });
  const result = await runRemoteAlgorithm(getApiBaseUrl(), {
    algorithm_family: runtime.family,
    operation,
    session_id: sessionId,
    capture_id: captureId,
    dataset_name: datasetName,
    auto_materialize: !useExisting,
    auto_colmap: autoColmap,
    use_existing_remote_dataset: useExisting,
    remote_dataset_id: selectedRemoteDataset.id,
    remote_dataset_path: effectiveRemoteDatasetPath,
    workspace: useExisting ? runtime.workspace : "",
    checkpoint_path: runtime.checkpointPath,
    output_dir: outputDir,
    path_confirmation: pathConfirmation,
    remote: collectRemoteConfig(),
    require_remote_check: true,
  });

  if (result.materialized?.dataset_root) {
    const nextArgs = {
      ...parseExtraArgs(),
      workspace: result.materialized.dataset_root,
    };
    setExtraArgs(nextArgs);
    workflowState.sessionReady = true;
  }

  if (result.job?.id) {
    applyJobMetrics(result.job);
    jobLogState.jobId = result.job.id;
    jobLogState.page = 1;
    await refreshJobs();
    startJobPolling(result.job.id);
  }

  workflowState.frameReady = true;
  workflowState.sessionReady = true;
  workflowState.jobStarted = true;
  const modeText = useExisting
    ? `remote dataset ${selectedRemoteDataset.id || effectiveRemoteDatasetPath}`
    : `capture ${captureId}`;
  setStepResult("step5", "success", "Step 5 queued", `Job ${result.job?.id || "-"} queued successfully using ${modeText}.`);
  refreshWorkflowUI();
  updateStatus({
    viewer: "remote-training",
    job: result.job?.id ?? "-",
  });
}

async function bootstrapFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const manifest = params.get("manifest");
  if (manifest) {
    await handleManifestLoad(manifest);
    return;
  }
  const source = params.get("source");
  if (source) {
    document.getElementById("source-url").value = source;
    document.getElementById("representation").value = params.get("representation") ?? "sh";
    document.getElementById("algorithm-family").value = params.get("family") ?? "vanilla-3dgs";
    await handleDirectLoad();
  }
}

function bindEvents() {
  showProcessedPlaceholder();
  registerFlowBlockToggleHandlers();

  const uploadInput = getUploadInputNode();
  const uploadDropzone = document.getElementById("upload-dropzone");
  const clearUploadButton = document.getElementById("clear-upload-files");

  if (uploadInput) {
    uploadInput.addEventListener("change", () => {
      renderUploadSelectionSummary();
      const fileCount = getSelectedUploadFiles().length;
      if (fileCount > 0) {
        setStepResult("step3", "idle", "Step 3 pending", `Selected ${fileCount} image(s). Click Send Frame to upload.`);
      }
    });
  }

  if (clearUploadButton) {
    clearUploadButton.addEventListener("click", () => {
      clearUploadFileSelection();
      setStepResult("step3", "idle", "Step 3 pending", "Upload a frame or select photos.");
    });
  }

  if (uploadDropzone) {
    const preventDefault = (event) => {
      event.preventDefault();
      event.stopPropagation();
    };

    ["dragenter", "dragover"].forEach((eventName) => {
      uploadDropzone.addEventListener(eventName, (event) => {
        preventDefault(event);
        uploadDropzone.classList.add("dragover");
      });
    });

    ["dragleave", "dragend", "drop"].forEach((eventName) => {
      uploadDropzone.addEventListener(eventName, (event) => {
        preventDefault(event);
        uploadDropzone.classList.remove("dragover");
      });
    });

    uploadDropzone.addEventListener("drop", (event) => {
      const droppedFiles = Array.from(event.dataTransfer?.files ?? []);
      if (!droppedFiles.length) return;
      applyDroppedUploadFiles(droppedFiles);
      const fileCount = getSelectedUploadFiles().length;
      if (fileCount > 0) {
        setStepResult("step3", "idle", "Step 3 pending", `Selected ${fileCount} image(s) by drag-and-drop.`);
      }
    });
  }

  window.addEventListener("beforeunload", () => {
    revokeUploadPreviewObjectUrls();
  });

  document.getElementById("api-base-url").addEventListener("change", () => {
    workflowState.apiChecked = false;
    workflowState.adapterReady = false;
    workflowState.frameReady = false;
    workflowState.sessionReady = false;
    workflowState.remoteConfigReady = false;
    invalidateRemoteSshCheck();
    workflowState.jobStarted = false;
    setStepResult("step1", "idle", "Step 1 pending", "Click Check Runtime.");
    setStepResult("step2", "idle", "Step 2 pending", "Validate adapter capability.");
    setStepResult("step3", "idle", "Step 3 pending", "Upload a frame.");
    setStepResult("step4", "idle", "Step 4 pending", "Fill remote config and check SSH.");
    setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
    refreshWorkflowUI();
  });

  const resetAdapterStage = () => {
    workflowState.adapterReady = false;
    workflowState.frameReady = false;
    workflowState.sessionReady = false;
    workflowState.remoteConfigReady = false;
    invalidateRemoteSshCheck();
    workflowState.jobStarted = false;
    setStepResult("step2", "idle", "Step 2 pending", "Adapter config changed. Re-validate adapter.");
    setStepResult("step3", "idle", "Step 3 pending", "Upload a frame.");
    setStepResult("step4", "idle", "Step 4 pending", "Fill remote config and check SSH.");
    setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
    refreshWorkflowUI();
  };

  document.getElementById("server-repo-path").addEventListener("change", resetAdapterStage);
  document.getElementById("server-default-cwd").addEventListener("change", resetAdapterStage);

  document.getElementById("stream-session-id").addEventListener("change", () => {
    ensureCaptureBatchId(true);
    workflowState.frameReady = false;
    workflowState.sessionReady = false;
    workflowState.remoteConfigReady = false;
    invalidateRemoteSshCheck();
    workflowState.jobStarted = false;
    setStepResult("step3", "idle", "Step 3 pending", "Session changed. Upload a new frame.");
    setStepResult("step4", "idle", "Step 4 pending", "Run SSH check again for this session.");
    setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
    refreshWorkflowUI();
  });

  document.getElementById("new-capture-batch").addEventListener("click", () => {
    ensureCaptureBatchId(true);
    setStepResult("step3", "idle", "Step 3 pending", "Capture batch switched. Upload a new frame batch.");
    workflowState.frameReady = false;
    workflowState.sessionReady = false;
    workflowState.jobStarted = false;
    refreshWorkflowUI();
  });

  document.getElementById("preset-scene").addEventListener("change", (event) => {
    document.getElementById("manifest-url").value = event.target.value;
  });

  document.getElementById("algorithm-family").addEventListener("change", (event) => {
    const method = getSelectedAdapter();
    if (method) {
      document.getElementById("representation").value = method.representation;
      setOperationOptions(method);
      syncAdapterDetail();
      fetchEnvironmentCheck(getApiBaseUrl(), method.family)
        .then((env) => {
          environmentReport = env.report;
          renderEnvironmentCheck(environmentReport);
        })
        .catch(() => { });

      if (workflowState.apiChecked) {
        workflowState.adapterReady = isAdapterValidationReady(serverValidation.get(method.family));
      } else {
        workflowState.adapterReady = false;
      }
      workflowState.frameReady = false;
      workflowState.sessionReady = false;
      workflowState.remoteConfigReady = false;
      invalidateRemoteSshCheck();
      workflowState.jobStarted = false;
      if (workflowState.adapterReady) {
        setStepResult("step2", "success", "Step 2 passed", "Adapter capability is ready for this family.");
      } else {
        setStepResult("step2", "idle", "Step 2 pending", "Algorithm changed. Re-validate adapter.");
      }
      setStepResult("step3", "idle", "Step 3 pending", "Upload a frame.");
      setStepResult("step4", "idle", "Step 4 pending", "Fill remote config and check SSH.");
      setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
      refreshWorkflowUI();
    }
  });

  document.getElementById("algorithm-operation").addEventListener("change", () => {
    invalidateRemoteSshCheck();
    setStepResult("step4", "idle", "Step 4 pending", "Operation changed. Re-run Check SSH.");
    setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
    refreshWorkflowUI();
  });

  [
    "remote-host",
    "remote-port",
    "remote-username",
    "remote-password",
    "remote-repo-path",
    "remote-workspace-root",
    "remote-output-root",
    "remote-python",
    "remote-activate-cmd",
  ].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      invalidateRemoteSshCheck();
      setStepResult("step4", "idle", "Step 4 pending", "Remote config changed. Run Check SSH.");
      setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
      refreshWorkflowUI();
    });
  });

  document.getElementById("use-existing-remote-dataset").addEventListener("change", () => {
    refreshRemoteDatasetSummary(lastRemoteCheckReport);
    refreshWorkflowUI();
  });

  document.getElementById("remote-dataset-select").addEventListener("change", () => {
    refreshRemoteDatasetSummary(lastRemoteCheckReport);
    refreshWorkflowUI();
  });

  document.getElementById("remote-dataset-path").addEventListener("input", () => {
    refreshRemoteDatasetSummary(lastRemoteCheckReport);
    refreshWorkflowUI();
  });

  document.getElementById("auto-colmap").addEventListener("change", () => {
    if (!isUseExistingRemoteDataset()) {
      invalidateRemoteSshCheck();
      setStepResult("step4", "idle", "Step 4 pending", "COLMAP option changed. Run Check SSH.");
    }
    refreshRemoteDatasetSummary(lastRemoteCheckReport);
    refreshWorkflowUI();
  });

  document.getElementById("load-manifest").addEventListener("click", async () => {
    try {
      const manifestUrl = document.getElementById("manifest-url").value.trim();
      if (!manifestUrl) {
        throw new Error("Manifest URL is required.");
      }
      await handleManifestLoad(manifestUrl);
    } catch (error) {
      updateStatus({ viewer: "error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("load-direct").addEventListener("click", async () => {
    try {
      await handleDirectLoad();
    } catch (error) {
      updateStatus({ viewer: "error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("check-api").addEventListener("click", async () => {
    try {
      setStepResult("step1", "running", "Step 1 running", "Checking runtime and environment...");
      await handleApiHealthCheck();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP1-RUNTIME-FAIL");
      setStepResult("step1", "failed", `Step 1 failed (${info.code})`, info.message);
      updateStatus({ viewer: "api-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("check-remote-ssh").addEventListener("click", async () => {
    try {
      setStepResult("step4", "running", "Step 4 running", "Checking SSH connectivity and remote paths...");
      await handleRemoteSshCheck();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP4-SSH-UNKNOWN-001");
      invalidateRemoteSshCheck();
      setStepResult("step4", "failed", `Step 4 failed (${info.code})`, info.message);
      updateStatus({ viewer: "remote-error" });
      setOverlayVisible(true, `${info.message}${info.nextAction ? `\nNext: ${info.nextAction}` : ""}`);
      refreshWorkflowUI();
    }
  });

  document.getElementById("export-package").addEventListener("click", async () => {
    try {
      await handleExportPackage();
    } catch (error) {
      updateStatus({ viewer: "export-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("submit-algorithm-job").addEventListener("click", async () => {
    try {
      await handleSubmitAlgorithmJob();
    } catch (error) {
      updateStatus({ viewer: "job-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("run-capture-pipeline").addEventListener("click", async () => {
    try {
      await handleRunCapturePipeline();
    } catch (error) {
      updateStatus({ viewer: "pipeline-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("one-click-remote-train").addEventListener("click", async () => {
    try {
      await handleOneClickRemoteTrain();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP5-RUN-001");
      setStepResult("step5", "failed", `Step 5 failed (${info.code})`, info.message);
      updateStatus({ viewer: "remote-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("start-camera").addEventListener("click", async () => {
    try {
      await startCamera();
      updateStatus({ viewer: "camera-ready" });
    } catch (error) {
      updateStatus({ viewer: "camera-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("stop-camera").addEventListener("click", () => {
    stopCamera();
    updateStatus({ viewer: "camera-stopped" });
  });

  document.getElementById("send-frame").addEventListener("click", async () => {
    try {
      setStepResult("step3", "running", "Step 3 running", "Uploading selected image(s)...");
      await sendCurrentFrame();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP3-FRAME-001");
      setStepResult("step3", "failed", `Step 3 failed (${info.code})`, info.message);
      updateStatus({ viewer: "stream-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("toggle-stream").addEventListener("click", async (event) => {
    try {
      if (streamTimer) {
        window.clearInterval(streamTimer);
        streamTimer = null;
        event.target.textContent = "Start Stream";
        updateStatus({ viewer: "stream-stopped" });
        return;
      }
      if (getSelectedUploadFiles().length) {
        throw new Error("Start Stream uses camera frames only. Clear selected photos first, or click Send Frame for batch upload.");
      }
      await startCamera();
      const intervalMs = Number(document.getElementById("stream-interval-ms").value || 1000);
      await sendCurrentFrame();
      streamTimer = window.setInterval(() => {
        sendCurrentFrame().catch(() => { });
      }, intervalMs);
      event.target.textContent = "Stop Stream";
      updateStatus({ viewer: "stream-running" });
    } catch (error) {
      updateStatus({ viewer: "stream-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("materialize-session").addEventListener("click", async () => {
    try {
      const result = await handleMaterializeSession();
      applyMaterializedSession(result);
    } catch (error) {
      updateStatus({ viewer: "session-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("use-session-workspace").addEventListener("click", async () => {
    try {
      if (!lastMaterializedSession) {
        lastMaterializedSession = await handleMaterializeSession();
      }
      applyMaterializedSession(lastMaterializedSession);
    } catch (error) {
      updateStatus({ viewer: "session-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("prepare-colmap-workspace").addEventListener("click", async () => {
    try {
      const result = await handlePrepareColmapWorkspace();
      applyColmapWorkspace(result);
    } catch (error) {
      updateStatus({ viewer: "colmap-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("use-colmap-workspace").addEventListener("click", async () => {
    try {
      if (!lastColmapWorkspace) {
        lastColmapWorkspace = await handlePrepareColmapWorkspace();
      }
      applyColmapWorkspace(lastColmapWorkspace);
    } catch (error) {
      updateStatus({ viewer: "colmap-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("refresh-jobs").addEventListener("click", async () => {
    try {
      await refreshJobs();
    } catch (error) {
      updateStatus({ viewer: "job-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("log-job-id").addEventListener("change", async (event) => {
    jobLogState.jobId = event.target.value;
    jobLogState.page = 1;
    try {
      await loadJobLogs(1);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  document.getElementById("refresh-job-log").addEventListener("click", async () => {
    try {
      await loadJobLogs(jobLogState.page);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  document.getElementById("job-log-tail-lines").addEventListener("change", async (event) => {
    const value = Number(event.target.value || 120);
    jobLogState.tailLines = Number.isFinite(value) ? Math.max(20, Math.min(1200, value)) : 120;
    try {
      await loadJobLogs(jobLogState.page);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  document.getElementById("copy-job-log").addEventListener("click", async () => {
    await copyCurrentJobLogTail();
  });

  document.getElementById("job-metrics-prev").addEventListener("click", async () => {
    if (jobLogState.page <= 1) return;
    try {
      await loadJobLogs(jobLogState.page - 1);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  document.getElementById("job-metrics-next").addEventListener("click", async () => {
    if (jobLogState.page >= jobLogState.totalPages) return;
    try {
      await loadJobLogs(jobLogState.page + 1);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  ["download-job-log", "download-job-csv"].forEach((id) => {
    document.getElementById(id).addEventListener("click", (event) => {
      if (!jobLogState.jobId) {
        event.preventDefault();
      }
    });
  });

  document.getElementById("job-list").addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-log-job-id]");
    if (!trigger) return;
    const jobId = trigger.dataset.logJobId;
    if (!jobId) return;
    ensureJobLogsPanelVisible();
    jobLogState.jobId = jobId;
    jobLogState.page = 1;
    const select = document.getElementById("log-job-id");
    if (select) {
      if (!Array.from(select.options).some((option) => option.value === jobId)) {
        const linkedJob = findJobById(jobId);
        const label = linkedJob
          ? `${linkedJob.algorithm_family} · ${jobId.slice(0, 8)} · ${linkedJob.status}`
          : `Job · ${jobId.slice(0, 8)}`;
        const option = document.createElement("option");
        option.value = jobId;
        option.textContent = label;
        select.appendChild(option);
      }
      select.value = jobId;
    }
    try {
      await loadJobLogs(1);
    } catch (error) {
      setJobLogMeta(`Failed to load logs: ${error.message}`);
    }
  });

  document.getElementById("validate-adapter").addEventListener("click", async () => {
    try {
      const family = document.getElementById("algorithm-family").value;
      setStepResult("step2", "running", "Step 2 running", `Validating adapter ${family}...`);
      const result = await validateAdapter(getApiBaseUrl(), family);
      serverValidation.set(family, result.validation);
      syncAdapterDetail();
      updateStatus({ viewer: "adapter-validated" });

      const ready = isAdapterValidationReady(result.validation);
      workflowState.adapterReady = ready;
      invalidateRemoteSshCheck();
      if (!ready) {
        setStepResult("step2", "failed", "Step 2 failed", "Adapter has no enabled operations.");
        workflowState.frameReady = false;
        workflowState.sessionReady = false;
        workflowState.jobStarted = false;
      } else {
        setStepResult("step2", "success", "Step 2 passed", "Adapter capability is valid.");
      }
      refreshWorkflowUI();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP2-ADAPTER-001");
      setStepResult("step2", "failed", `Step 2 failed (${info.code})`, info.message);
      updateStatus({ viewer: "adapter-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("save-adapter").addEventListener("click", async () => {
    try {
      const family = document.getElementById("algorithm-family").value;
      setStepResult("step2", "running", "Step 2 running", `Saving adapter ${family}...`);
      const result = await updateAdapter(getApiBaseUrl(), {
        family,
        repo_path: document.getElementById("server-repo-path").value.trim(),
        default_cwd: document.getElementById("server-default-cwd").value.trim(),
      });
      await handleApiHealthCheck();
      serverValidation.set(family, result.validation);
      syncAdapterDetail();
      updateStatus({ viewer: "adapter-saved" });

      const ready = isAdapterValidationReady(result.validation);
      workflowState.adapterReady = ready;
      invalidateRemoteSshCheck();
      if (!ready) {
        setStepResult("step2", "failed", "Step 2 failed", "Adapter save succeeded but capability is not ready.");
        workflowState.frameReady = false;
        workflowState.sessionReady = false;
        workflowState.jobStarted = false;
      } else {
        setStepResult("step2", "success", "Step 2 passed", "Adapter saved and validated.");
      }
      refreshWorkflowUI();
    } catch (error) {
      const info = formatApiError(error, "WGSC-STEP2-ADAPTER-SAVE-001");
      setStepResult("step2", "failed", `Step 2 failed (${info.code})`, info.message);
      updateStatus({ viewer: "adapter-error" });
      setOverlayVisible(true, error.message);
    }
  });

  document.getElementById("recent-scenes").addEventListener("click", async (event) => {
    const item = event.target.closest("[data-scene-index]");
    if (!item) return;
    const scenes = loadRecentScenes().slice().reverse();
    const scene = scenes[Number(item.dataset.sceneIndex)];
    if (!scene) return;
    try {
      if (scene.manifestUrl) {
        await handleManifestLoad(scene.manifestUrl);
      } else if (scene.source?.url) {
        document.getElementById("source-url").value = scene.source.url;
        document.getElementById("representation").value = scene.representation ?? "sh";
        document.getElementById("algorithm-family").value = scene.algorithm?.family ?? "vanilla-3dgs";
        await handleDirectLoad();
      }
    } catch (error) {
      updateStatus({ viewer: "recent-scene-error" });
      setOverlayVisible(true, error.message);
    }
  });

  window.addEventListener("message", (event) => {
    if (!event.data || event.data.type !== "gaussian-viewer-stats") return;
    updateStatus({
      fps: event.data.fps ?? "-",
      vertices: event.data.vertices ?? "-",
      progress: event.data.progress ?? "-",
      viewer: event.data.status ?? "running",
    });
  });
}

function bootstrapDefaults() {
  flowManualState = loadFlowManualState();

  document.getElementById("manifest-url").value = "./scenes/megs2-sg.scene.json";
  document.getElementById("source-url").value = "";
  document.getElementById("viewer-backend").value = "webgl2";
  document.getElementById("preprocess-parser").value = "colmap";
  document.getElementById("preprocess-downsample").value = "1";
  document.getElementById("preprocess-mask-path").value = "";
  document.getElementById("preprocess-reorient").checked = true;
  document.getElementById("preprocess-image-uint8").checked = false;
  document.getElementById("preprocess-async-caching").checked = false;
  document.getElementById("edit-translation").value = "0,0,0";
  document.getElementById("edit-rotation").value = "0,0,0";
  document.getElementById("edit-scale").value = "1,1,1";
  document.getElementById("edit-background").value = "black";
  document.getElementById("api-base-url").value = window.location.origin;
  document.getElementById("server-input-path").value = "";
  document.getElementById("server-output-dir").value = "";
  document.getElementById("server-scene-id").value = "";
  document.getElementById("server-repo-path").value = "";
  document.getElementById("server-default-cwd").value = "";
  document.getElementById("remote-host").value = "";
  document.getElementById("remote-port").value = "22";
  document.getElementById("remote-username").value = "";
  document.getElementById("remote-password").value = "";
  document.getElementById("remote-repo-path").value = "";
  document.getElementById("remote-workspace-root").value = "/tmp/web_scan/workspaces";
  document.getElementById("remote-output-root").value = "/tmp/web_scan/outputs";
  document.getElementById("remote-python").value = "python3";
  document.getElementById("remote-activate-cmd").value = "";
  document.getElementById("stream-session-id").value = "session-demo";
  const uploadInput = getUploadInputNode();
  if (uploadInput) {
    uploadInput.value = "";
  }
  document.getElementById("capture-batch-id").value = "";
  document.getElementById("dataset-name").value = "";
  document.getElementById("use-existing-remote-dataset").checked = false;
  document.getElementById("auto-colmap").checked = true;
  document.getElementById("remote-dataset-path").value = "";
  document.getElementById("stream-interval-ms").value = "1000";
  document.getElementById("server-extra-args").value = JSON.stringify(
    {
      checkpoint_path: "",
      workspace: "",
      cwd: "",
    },
    null,
    2,
  );
  renderJobs([]);
  renderRecentScenes(loadRecentScenes());
  renderAdapterDetail(null, null);
  renderJobMetricsRows([]);
  renderJobLogTail([]);
  setJobLogMeta("No job selected.");
  updateJobMetricsPager(1, 1, 0);
  setJobLogDownloadLinks("");
  populateRemoteDatasetSelector([]);
  ensureCaptureBatchId(true);
  refreshRemoteDatasetSummary();
  renderUploadSelectionSummary();
  lastJobsSnapshot = [];
  jobLogState.jobId = "";
  jobLogState.page = 1;
  jobLogState.totalPages = 1;
  jobLogState.tailLines = 120;
  document.getElementById("job-log-tail-lines").value = "120";

  workflowState.apiChecked = false;
  workflowState.adapterReady = false;
  workflowState.frameReady = false;
  workflowState.sessionReady = false;
  workflowState.remoteConfigReady = false;
  workflowState.sshChecked = false;
  workflowState.jobStarted = false;
  setStepResult("step1", "idle", "Step 1 pending", "Check runtime.");
  setStepResult("step2", "idle", "Step 2 pending", "Validate adapter capability.");
  setStepResult("step3", "idle", "Step 3 pending", "Upload first frame.");
  setStepResult("step4", "idle", "Step 4 pending", "Fill remote config and run Check SSH.");
  setStepResult("step5", "idle", "Step 5 pending", "Start remote job.");
  refreshWorkflowUI();
}

bindStaticOptions();
renderMethodRegistry();
setSchemaPreview();
bindEvents();
bootstrapDefaults();
setOverlayVisible(true, "Waiting for scene to load");
bootstrapFromQuery().catch((error) => {
  updateStatus({ viewer: "query-error" });
  setOverlayVisible(true, error.message);
});
setOverlayVisible(true, "Waiting for scene");
;
