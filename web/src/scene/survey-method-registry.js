export const SURVEY_METHODS = [
  {
    family: "gaussian-splatting-lightning",
    label: "Gaussian Splatting Lightning",
    category: "framework",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Multi-algorithm training/validation framework; serves as a unified backend entrypoint.",
  },
  {
    family: "gaussian-splatting-web",
    label: "Gaussian Splatting Web",
    category: "viewer",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Reference WebGPU viewer implementation.",
  },
  {
    family: "vanilla-3dgs",
    label: "Vanilla 3DGS",
    category: "baseline",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Direct mapping to SH/RGB Gaussian paths.",
  },
  {
    family: "megs2",
    label: "MEGS2",
    category: "compression",
    representation: "sg",
    compatibility: "viewer-ready",
    notes: "Preserves variable SG axes and maps to the SG renderer.",
  },
  {
    family: "gaussianspa",
    label: "GaussianSpa",
    category: "compaction",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Reuses the SH renderer and retains pruning metadata.",
  },
  {
    family: "scaffold-gs",
    label: "Scaffold-GS",
    category: "anchor",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "Local anchor-based Gaussian repo with training/rendering/realtime bridge.",
  },
  {
    family: "reduced-3dgs",
    label: "Reduced 3DGS",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Local reduced-3dgs repo with training/compression/rendering entrypoints.",
  },
  {
    family: "hac",
    label: "HAC",
    category: "compression",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "Hash-grid assisted context compression.",
  },
  {
    family: "hemgs",
    label: "HEMGS",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Hybrid entropy model.",
  },
  {
    family: "hac-plus-plus",
    label: "HAC++",
    category: "compression",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "Local HAC++ repo connected to training entrypoint; web displays results via bridged scenes.",
  },
  {
    family: "contextgs",
    label: "ContextGS",
    category: "compression",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "Local ContextGS repo connected to train/decompress entrypoints.",
  },
  {
    family: "codecgs",
    label: "CodecGS",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Compression pipeline requires unified scene packaging and decoders.",
  },
  {
    family: "fcgs",
    label: "FCGS",
    category: "compression",
    representation: "compressed-feature",
    compatibility: "manifest-ready",
    notes: "Local FCGS repo connected to encode/decode entrypoints.",
  },
  {
    family: "mesongs",
    label: "MesonGS",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Integrated via unified exporter.",
  },
  {
    family: "compgs",
    label: "CompGS",
    category: "compaction",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "Local CompGS repo connected to Train/Test entrypoints.",
  },
  {
    family: "rdo-gaussian",
    label: "RDO-Gaussian",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Rate-distortion optimized representation.",
  },
  {
    family: "compressed-3dgs",
    label: "Compressed 3DGS",
    category: "compression",
    representation: "compressed-sh",
    compatibility: "manifest-ready",
    notes: "Compressed Gaussian representation.",
  },
  {
    family: "octree-gs",
    label: "Octree-GS",
    category: "lod",
    representation: "compressed-anchor",
    compatibility: "manifest-ready",
    notes: "LOD-structured octree representation.",
  },
  {
    family: "gaussianpro",
    label: "GaussianPro",
    category: "compaction",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Progressive propagation densification.",
  },
  {
    family: "atomgs",
    label: "AtomGS",
    category: "compaction",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Atomized Gaussian route.",
  },
  {
    family: "taming3dgs",
    label: "Taming3DGS",
    category: "compaction",
    representation: "sh",
    compatibility: "viewer-ready",
    notes: "Placeholder adapter compatible with pruning/compression.",
  },
];

export const REPRESENTATIONS = [
  { value: "sh", label: "SH Gaussian" },
  { value: "sg", label: "Spherical Gaussian" },
  { value: "compressed-sh", label: "Compressed SH" },
  { value: "compressed-sg", label: "Compressed SG" },
  { value: "compressed-anchor", label: "Compressed Anchor" },
  { value: "compressed-feature", label: "Compressed Feature" },
];

export function getMethodDefinition(family) {
  return SURVEY_METHODS.find((item) => item.family === family) ?? null;
}

export function getOperationsForMethod(method) {
  if (!method) return ["train"];
  if (method.compatibility === "viewer-ready") {
    return ["train", "export_scene", "render"];
  }
  return ["train", "compress", "encode", "decode", "decompress", "export_scene"];
}
