import { RendererInterface } from "./renderer-interface.js";

export class LegacyIframeRenderer extends RendererInterface {
  constructor({ name, viewerPath }) {
    super(name);
    this.viewerPath = viewerPath;
  }

  async mount({ frame, scene }) {
    const viewerUrl = new URL(this.viewerPath, window.location.href);
    viewerUrl.searchParams.set("url", scene.source.url);
    viewerUrl.searchParams.set("sceneId", scene.sceneId ?? scene.title ?? "scene");
    frame.src = viewerUrl.toString();
  }

  dispose({ frame }) {
    frame.src = "about:blank";
  }
}
