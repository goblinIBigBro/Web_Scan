export class RendererInterface {
  constructor(name) {
    this.name = name;
  }

  async mount() {
    throw new Error("mount() must be implemented by subclasses.");
  }

  dispose() {}
}
