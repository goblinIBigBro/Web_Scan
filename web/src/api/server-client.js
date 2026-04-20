function withApiBase(baseUrl, path) {
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString();
}

export class ApiRequestError extends Error {
  constructor(message, payload = {}, status = 0, statusText = "") {
    super(message);
    this.name = "ApiRequestError";
    this.payload = payload || {};
    this.status = status;
    this.statusText = statusText;
    this.code = this.payload.code ?? "";
    this.step = this.payload.step ?? "";
    this.reason = this.payload.reason ?? "";
    this.details = this.payload.details ?? {};
    this.manualUrl = this.payload.manual_url ?? "";
    this.manualAnchor = this.payload.manual_anchor ?? "";
    this.nextAction = this.payload.next_action ?? "";
  }
}

async function parseJson(response) {
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {
      error: `Failed to parse server response (${response.status} ${response.statusText}).`,
    };
  }
  if (!response.ok) {
    throw new ApiRequestError(
      data.error ?? data.message ?? `${response.status} ${response.statusText}`,
      data,
      response.status,
      response.statusText,
    );
  }
  return data;
}

export async function fetchHealth(apiBaseUrl) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/health"));
  return parseJson(response);
}

export async function fetchAlgorithms(apiBaseUrl) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/algorithms"));
  return parseJson(response);
}

export async function fetchEnvironmentCheck(apiBaseUrl, family = "") {
  const response = await fetch(withApiBase(apiBaseUrl, "api/environment-check"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ family }),
  });
  return parseJson(response);
}

export async function updateAdapter(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/adapters/update"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function validateAdapter(apiBaseUrl, family) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/adapters/validate"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ family }),
  });
  return parseJson(response);
}

export async function exportScenePackage(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/export-scene"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function submitAlgorithmJob(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/run-algorithm"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function runRemoteAlgorithm(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/run-remote-algorithm"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function remoteCheck(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/remote-check"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function fetchJobs(apiBaseUrl) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/jobs"));
  return parseJson(response);
}

export async function fetchJob(apiBaseUrl, jobId) {
  const response = await fetch(withApiBase(apiBaseUrl, `api/jobs/${jobId}`));
  return parseJson(response);
}

export async function fetchJobLogs(apiBaseUrl, jobId, options = {}) {
  const page = Number(options.page || 1);
  const pageSize = Number(options.pageSize || 20);
  const tailLines = Number(options.tailLines || 120);
  const params = new URLSearchParams({
    page: String(Number.isFinite(page) && page > 0 ? page : 1),
    page_size: String(Number.isFinite(pageSize) && pageSize > 0 ? pageSize : 20),
    tail_lines: String(Number.isFinite(tailLines) && tailLines > 0 ? tailLines : 120),
  });
  const response = await fetch(withApiBase(apiBaseUrl, `api/jobs/${jobId}/logs?${params.toString()}`));
  return parseJson(response);
}

export function buildJobLogDownloadUrl(apiBaseUrl, jobId) {
  return withApiBase(apiBaseUrl, `api/jobs/${jobId}/logs/download`);
}

export function buildJobMetricsCsvUrl(apiBaseUrl, jobId) {
  return withApiBase(apiBaseUrl, `api/jobs/${jobId}/metrics.csv`);
}

export async function streamFrame(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/stream-frame"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function materializeSession(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/materialize-session"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function prepareColmapWorkspace(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/prepare-colmap-workspace"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}

export async function runCapturePipeline(apiBaseUrl, payload) {
  const response = await fetch(withApiBase(apiBaseUrl, "api/run-capture-pipeline"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response);
}
