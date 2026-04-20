import { LegacyIframeRenderer } from "./legacy-iframe-renderer.js";

const SH_RENDERER = new LegacyIframeRenderer({
  name: "SH Renderer",
  viewerPath: "./viewers/sh.html",
});

const SG_RENDERER = new LegacyIframeRenderer({
  name: "SG Renderer",
  viewerPath: "./viewers/sg.html",
});

export function resolveRenderer(representation) {
  if (representation === "sg" || representation === "compressed-sg") {
    return SG_RENDERER;
  }
  return SH_RENDERER;
}
