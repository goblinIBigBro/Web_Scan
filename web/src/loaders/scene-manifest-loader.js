function normalizeUrl(input, baseHref = window.location.href) {
  if (!input) return "";
  return new URL(input, baseHref).toString();
}

export async function loadSceneManifest(manifestUrl) {
  const resolvedUrl = normalizeUrl(manifestUrl);
  const response = await fetch(resolvedUrl);
  if (!response.ok) {
    throw new Error(`Failed to load manifest: ${response.status} ${response.statusText}`);
  }

  const manifest = await response.json();
  return normalizeManifest(manifest, resolvedUrl);
}

export function normalizeManifest(manifest, baseHref = window.location.href) {
  const resolved = structuredClone(manifest);
  resolved.source = resolved.source ?? {};
  resolved.algorithm = resolved.algorithm ?? {};
  resolved.metadata = resolved.metadata ?? {};
  resolved.renderer = resolved.renderer ?? resolved.representation ?? resolved.metadata.appearanceModel;
  resolved.source.url = normalizeUrl(resolved.source.url ?? "", baseHref);
  return resolved;
}

export function buildDirectSceneConfig({ sourceUrl, representation, algorithmFamily }) {
  return normalizeManifest({
    version: "0.1.0",
    sceneId: "direct-input",
    title: "Direct Input",
    renderer: representation,
    representation,
    source: {
      url: sourceUrl,
      format: sourceUrl.toLowerCase().endsWith(".ply") ? "ply" : "binary",
    },
    algorithm: {
      family: algorithmFamily,
      name: algorithmFamily,
    },
    metadata: {
      compatibilityMode: "direct",
    },
  });
}

export function parseVec3Input(rawValue, fallback) {
  const raw = (rawValue ?? "").trim();
  if (!raw) return fallback;
  const parts = raw.split(",").map((item) => Number(item.trim()));
  if (parts.length !== 3 || parts.some((value) => Number.isNaN(value))) {
    return fallback;
  }
  return parts;
}

export function manifestSchemaExample() {
  return {
    version: "0.1.0",
    sceneId: "megs2-garden",
    title: "MEGS2 Garden",
    renderer: "sg",
    representation: "sg",
    source: {
      url: "./assets/garden_point_cloud.ply",
      format: "ply",
    },
    algorithm: {
      family: "megs2",
      name: "MEGS²",
      surveyCategory: "compression",
    },
    metadata: {
      appearanceModel: "sg",
      variableSgBands: true,
      notes: "SG lobes will be parsed by the SG renderer.",
    },
  };
}
