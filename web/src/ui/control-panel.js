import { DEFAULT_SCENES } from "../scene/default-scenes.js";
import { REPRESENTATIONS, SURVEY_METHODS, getOperationsForMethod } from "../scene/survey-method-registry.js";

const METHOD_LABELS = {
  "gaussian-splatting-lightning": "Gaussian Splatting Lightning",
  "gaussian-splatting-web": "Gaussian Splatting Web",
  "vanilla-3dgs": "Vanilla 3DGS",
  megs2: "MEGS2",
  gaussianspa: "GaussianSpa",
  "scaffold-gs": "Scaffold-GS",
  "reduced-3dgs": "Reduced 3DGS",
  hac: "HAC",
  hemgs: "HEMGS",
  "hac-plus-plus": "HAC++",
  contextgs: "ContextGS",
  codecgs: "CodecGS",
  fcgs: "FCGS",
  mesongs: "MesonGS",
  compgs: "CompGS",
  "rdo-gaussian": "RDO-Gaussian",
  "compressed-3dgs": "Compressed 3DGS",
  "octree-gs": "Octree-GS",
  gaussianpro: "GaussianPro",
  atomgs: "AtomGS",
  taming3dgs: "Taming3DGS",
};

const CATEGORY_LABELS = {
  framework: "Framework",
  viewer: "Viewer",
  baseline: "Baseline",
  compression: "Compression",
  compaction: "Compaction",
  anchor: "Anchor",
  lod: "Level of Detail",
};

const REPRESENTATION_LABELS = {
  sh: "SH",
  sg: "SG",
  "compressed-sh": "Compressed SH",
  "compressed-sg": "Compressed SG",
  "compressed-anchor": "Compressed Anchor",
  "compressed-feature": "Compressed Feature",
};

const OPERATION_LABELS = {
  train: "Train",
  render: "Render",
  export_scene: "Export Scene",
  compress: "Compress",
  encode: "Encode",
  decode: "Decode",
  decompress: "Decompress",
};

function localizedMethodLabel(item) {
  if (!item) return "-";
  return METHOD_LABELS[item.family] ?? item.label ?? item.family ?? "-";
}

function categoryText(value) {
  return CATEGORY_LABELS[value] ?? (value || "-");
}

function representationText(value) {
  return REPRESENTATION_LABELS[value] ?? (value || "-");
}

function operationText(value) {
  return OPERATION_LABELS[value] ?? value;
}

function boolText(value) {
  return value ? "Yes" : "No";
}

function compatibilityText(value) {
  const mapping = {
    "viewer-ready": "Viewer Ready",
    "manifest-ready": "Manifest Ready",
    blocked: "Blocked",
  };
  return mapping[value] ?? (value || "-");
}

function jobStatusText(value) {
  const mapping = {
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
  };
  return mapping[value] ?? (value || "-");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function summarizeText(value, maxLength = 140) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "-";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
}

function formatCreatedAt(unixSeconds) {
  if (!Number.isFinite(Number(unixSeconds))) return "-";
  try {
    return new Date(Number(unixSeconds) * 1000).toLocaleString();
  } catch {
    return "-";
  }
}

function schemaValueType(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function renderSchemaNode(key, value, depth = 0) {
  const keyText = depth === 0 ? "root" : String(key);
  const type = schemaValueType(value);

  if (type !== "object" && type !== "array") {
    const primitive = value === undefined ? "undefined" : JSON.stringify(value);
    return `
      <div class="schema-row">
        <span class="schema-key">${escapeHtml(keyText)}</span>
        <span class="schema-type">${escapeHtml(type)}</span>
        <span class="schema-value">${escapeHtml(primitive)}</span>
      </div>
    `;
  }

  const entries = type === "array"
    ? value.map((item, index) => [index, item])
    : Object.entries(value);
  const meta = type === "array" ? `${entries.length} items` : `${entries.length} keys`;
  const children = entries
    .map(([childKey, childValue]) => renderSchemaNode(childKey, childValue, depth + 1))
    .join("");

  return `
    <details class="schema-node" ${depth <= 1 ? "open" : ""}>
      <summary class="schema-summary">
        <span class="schema-key">${escapeHtml(keyText)}</span>
        <span class="schema-type">${escapeHtml(type)}</span>
        <span class="schema-meta">${escapeHtml(meta)}</span>
      </summary>
      <div class="schema-children">
        ${children || '<p class="schema-empty">(empty)</p>'}
      </div>
    </details>
  `;
}

function viewerStateText(value) {
  const mapping = {
    idle: "Idle",
    loading: "Loading",
    running: "Running",
    queued: "Queued",
    completed: "Completed",
    failed: "Failed",
    exported: "Exported",
    error: "Error",
    "api-ready": "API Ready",
    "api-error": "API Error",
    "export-error": "Export Error",
    "job-error": "Job Error",
    "pipeline-error": "Pipeline Error",
    "camera-ready": "Camera Ready",
    "camera-error": "Camera Error",
    "camera-stopped": "Camera Stopped",
    "stream-running": "Stream Running",
    "stream-stopped": "Stream Stopped",
    "stream-error": "Stream Error",
    "stream-processing": "Stream Processing",
    "frame-uploaded": "Frame Uploaded",
    "session-materialized": "Session Materialized",
    "session-ready": "Session Ready",
    "session-error": "Session Error",
    "colmap-workspace-ready": "COLMAP Workspace Ready",
    "colmap-workspace-applied": "COLMAP Workspace Applied",
    "colmap-error": "COLMAP Error",
    "capture-pipeline-running": "Capture Pipeline Running",
    "adapter-validated": "Adapter Validated",
    "adapter-saved": "Adapter Saved",
    "adapter-error": "Adapter Error",
    "remote-connecting": "Remote Connecting",
    "remote-uploading": "Remote Uploading",
    "remote-training": "Remote Training",
    "remote-downloading": "Remote Downloading",
    "remote-completed": "Remote Completed",
    "remote-error": "Remote Error",
    "recent-scene-error": "Recent Scene Load Failed",
    "query-error": "Query Error",
  };
  return mapping[value] ?? (value || "-");
}

export function bindStaticOptions() {
  const presetScene = document.getElementById("preset-scene");
  const representation = document.getElementById("representation");
  const algorithmFamily = document.getElementById("algorithm-family");
  const operation = document.getElementById("algorithm-operation");

  presetScene.innerHTML = [
    '<option value="">Select Preset</option>',
    ...DEFAULT_SCENES.map(
      (item) => `<option value="${item.manifestUrl}">${item.label}</option>`,
    ),
  ].join("");

  representation.innerHTML = REPRESENTATIONS.map(
    (item) => `<option value="${item.value}">${item.label}</option>`,
  ).join("");

  algorithmFamily.innerHTML = SURVEY_METHODS.map(
    (item) => `<option value="${item.family}">${localizedMethodLabel(item)}</option>`,
  ).join("");

  const defaultMethod = SURVEY_METHODS[0];
  operation.innerHTML = getOperationsForMethod(defaultMethod).map(
    (item) => `<option value="${item}">${operationText(item)}</option>`,
  ).join("");
}

export function renderMethodRegistry() {
  const container = document.getElementById("method-registry");
  if (!container) return;
  container.innerHTML = SURVEY_METHODS.map((item) => {
    const readinessClass =
      item.compatibility === "viewer-ready"
        ? "ready"
        : item.compatibility === "manifest-ready"
          ? "partial"
          : "blocked";
    return `
      <article class="method-card">
        <h3>${localizedMethodLabel(item)}</h3>
        <p>${item.notes}</p>
        <div class="badge-row">
          <span class="badge">Category: ${categoryText(item.category)}</span>
          <span class="badge">Representation: ${representationText(item.representation)}</span>
          <span class="badge ${readinessClass}">${compatibilityText(item.compatibility)}</span>
        </div>
      </article>
    `;
  }).join("");
}

export function setOperationOptions(method) {
  const operation = document.getElementById("algorithm-operation");
  const operations = method?.operations
    ? Object.entries(method.operations)
      .filter(([, config]) => config.enabled)
      .map(([name]) => name)
    : getOperationsForMethod(method);
  operation.innerHTML = operations.map(
    (item) => `<option value="${item}">${operationText(item)}</option>`,
  ).join("");
}

export function applyAlgorithmOptions(algorithms) {
  if (!algorithms?.length) return;
  const algorithmFamily = document.getElementById("algorithm-family");
  algorithmFamily.innerHTML = algorithms.map(
    (item) => `<option value="${item.family}">${localizedMethodLabel(item)}</option>`,
  ).join("");
}

export function renderAdapterDetail(adapter, validation) {
  const container = document.getElementById("adapter-detail");
  if (!container) return;
  if (!adapter) {
    container.innerHTML = "<p>No adapter selected.</p>";
    return;
  }
  const operations = Object.entries(adapter.operations ?? {})
    .filter(([, config]) => config.enabled)
    .map(([name]) => name)
    .join(", ");
  const runnableOps = Array.isArray(validation?.runnable_operations)
    ? validation.runnable_operations.join(", ")
    : "-";
  const warnings = Array.isArray(validation?.warnings) ? validation.warnings : [];
  container.innerHTML = `
    <h3>${localizedMethodLabel(adapter)}</h3>
    <p>Family: ${adapter.family}</p>
    <p>Representation: ${adapter.representation}</p>
    <p>Compatibility: ${compatibilityText(adapter.compatibility)}</p>
    <p>Repo: ${adapter.repo_path || "-"}</p>
    <p>CWD: ${adapter.default_cwd || "-"}</p>
    <p>Operations: ${operations || "-"}</p>
    <p>Runnable Ops: ${runnableOps || "-"}</p>
    <p>Ready: ${boolText(validation?.is_ready)}</p>
    <p>Repo Exists: ${boolText(validation?.repo_exists)}</p>
    <p>CWD Exists: ${boolText(validation?.cwd_exists)}</p>
    ${warnings.length ? `<p>Warnings: ${warnings.join(" | ")}</p>` : ""}
  `;
}

export function renderEnvironmentCheck(report) {
  const container = document.getElementById("environment-check");
  if (!container) return;
  if (!report) {
    container.innerHTML = "<p>No environment report yet.</p>";
    return;
  }

  const checks = Array.isArray(report.checks) ? report.checks : [];
  const checkRows = checks
    .map((item) => {
      const state = item.ok ? "OK" : (item.required ? "Required Fail" : "Optional Fail");
      const hint = item.hint ? `<p>Hint: ${item.hint}</p>` : "";
      return `<div class="method-card"><p>${item.name}: ${state}</p><p>${item.message ?? "-"}</p>${hint}</div>`;
    })
    .join("");

  const warnings = Array.isArray(report.warnings) ? report.warnings : [];
  const warningRows = warnings.map((item) => `<p>${item}</p>`).join("");

  container.innerHTML = `
    <h3>Runtime Check</h3>
    <p>Family: ${report.family || "-"}</p>
    <p>Runtime Ready: ${boolText(report.runtime_ready ?? report.web_runnable)}</p>
    <p>Remote Ready: ${boolText(report.remote_ready)}</p>
    <p>GPU Visible (optional): ${boolText(report.gpu_visible)}</p>
    ${checkRows || "<p>No check details.</p>"}
    ${warningRows ? `<div class="method-card"><p>Warnings</p>${warningRows}</div>` : ""}
    <p>Summary: ${report.summary ?? "-"}</p>
  `;
}

export function updateStatus(status) {
  const entries = {
    renderer: status.renderer ?? "-",
    algorithm: status.algorithm ?? "-",
    scene: status.scene ?? "-",
    source: status.source ?? "-",
    fps: status.fps ?? "-",
    vertices: status.vertices ?? "-",
    progress: status.progress ?? "-",
    viewer: viewerStateText(status.viewer ?? "-"),
    job: status.job ?? "-",
    "web-url": status.webUrl ?? "-",
    "algo-fps": status.algoFps ?? "-",
    loss: status.loss ?? "-",
    psnr: status.psnr ?? "-",
    iter: status.iter ?? "-",
  };

  Object.entries(entries).forEach(([key, value]) => {
    const node = document.getElementById(`status-${key}`);
    if (node) node.textContent = value;
  });
}

export function updateViewerHeader({ title, subtitle }) {
  document.getElementById("viewer-title").textContent = title;
  document.getElementById("viewer-subtitle").textContent = subtitle;
}

export function setOverlayVisible(visible, message = "No scene loaded") {
  const overlay = document.getElementById("viewer-overlay");
  overlay.classList.toggle("hidden", !visible);
  overlay.querySelector("p").textContent = message;
}

export function setShareUrl(url) {
  const input = document.getElementById("share-url");
  if (input) input.value = url ?? "";
}

export function renderJobs(jobs) {
  const container = document.getElementById("job-list");
  if (!container) return;
  if (!jobs.length) {
    container.innerHTML = '<div class="job-item"><p>No jobs yet.</p></div>';
    return;
  }
  container.innerHTML = jobs
    .slice()
    .reverse()
    .map((job) => {
      const status = jobStatusText(job.status);
      const summaryMetrics = `fps=${job.metrics?.fps ?? "-"} · iter=${job.metrics?.iter ?? "-"} · loss=${job.metrics?.loss ?? "-"}`;
      const commandPreview = summarizeText(job.command, 120);
      const stderrPreview = summarizeText(job.stderr, 180);
      const createdAtText = formatCreatedAt(job.created_at);
      return `
        <article class="job-item" data-status="${escapeHtml(job.status ?? "-")}">
          <details class="job-card" ${job.status === "running" || job.status === "failed" ? "open" : ""}>
            <summary class="job-summary">
              <div class="job-summary-main">
                <h3>${escapeHtml(job.algorithm_family)} · ${escapeHtml(status)}</h3>
                <p>ID: ${escapeHtml(job.id)}</p>
              </div>
              <div class="job-summary-side">
                <p>${escapeHtml(summaryMetrics)}</p>
                <p>Operation: ${escapeHtml(job.operation ?? "-")}</p>
              </div>
            </summary>
            <div class="job-detail-grid">
              <p><strong>Created:</strong> ${escapeHtml(createdAtText)}</p>
              <p><strong>Remote Stage:</strong> ${escapeHtml(job.remote_stage ?? "-")}</p>
              <p><strong>Return code:</strong> ${escapeHtml(job.return_code ?? "-")}</p>
              <p><strong>Command:</strong> ${escapeHtml(commandPreview)}</p>
              <p><strong>STDERR:</strong> ${escapeHtml(stderrPreview)}</p>
            </div>
            <div class="job-action-row">
              <button type="button" class="job-inline-button" data-log-job-id="${escapeHtml(job.id)}">View Logs</button>
              ${job.logs_download_url
                ? `<a class="button-link" href="${job.logs_download_url}" download>Download .log</a>`
                : "<span></span>"}
            </div>
            <div class="job-action-row">
              ${job.metrics_csv_url
                ? `<a class="button-link" href="${job.metrics_csv_url}" download>Download metrics.csv</a>`
                : "<span></span>"}
              <span></span>
            </div>
          </details>
        </article>
      `;
    })
    .join("");
}

export function renderManifestSchema(schema) {
  const container = document.getElementById("schema-preview");
  if (!container) return;
  if (!schema || typeof schema !== "object") {
    container.innerHTML = '<p class="schema-empty">No schema preview.</p>';
    return;
  }
  container.innerHTML = `
    <div class="schema-tree">
      ${renderSchemaNode("root", schema, 0)}
    </div>
  `;
}

export function renderRecentScenes(scenes) {
  const container = document.getElementById("recent-scenes");
  if (!container) return;
  if (!scenes.length) {
    container.innerHTML = '<div class="job-item"><p>No recent scenes.</p></div>';
    return;
  }
  container.innerHTML = scenes
    .slice()
    .reverse()
    .map(
      (scene, index) => `
        <article class="job-item" data-scene-index="${index}">
          <h3>${scene.title ?? scene.sceneId ?? "Untitled"}</h3>
          <p>${scene.algorithm?.family ?? "-"}</p>
          <p>${scene.source?.url ?? scene.manifestUrl ?? "-"}</p>
        </article>
      `,
    )
    .join("");
}
