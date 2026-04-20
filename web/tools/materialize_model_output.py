#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path


def demo_vertex_rows(representation: str) -> tuple[str, list[str]]:
  points = []
  for z in (-0.12, 0.12):
    for y in (-0.12, 0.12):
      for x in (-0.12, 0.12):
        points.append((x, y, z))
  if representation == "sg":
    header = "\n".join([
      "ply",
      "format ascii 1.0",
      f"element vertex {len(points)}",
      "property float x",
      "property float y",
      "property float z",
      "property float scale_0",
      "property float scale_1",
      "property float scale_2",
      "property float rot_0",
      "property float rot_1",
      "property float rot_2",
      "property float rot_3",
      "property float opacity",
      "property float rgb_base_0",
      "property float rgb_base_1",
      "property float rgb_base_2",
      "property uchar sg_axis_count",
      "end_header",
    ])
    rows = [
      f"{x:.5f} {y:.5f} {z:.5f} -3.30000 -3.30000 -3.30000 1.00000 0.00000 0.00000 0.00000 2.00000 0.70000 0.20000 0.10000 0"
      for x, y, z in points
    ]
  else:
    header = "\n".join([
      "ply",
      "format ascii 1.0",
      f"element vertex {len(points)}",
      "property float x",
      "property float y",
      "property float z",
      "property float scale_0",
      "property float scale_1",
      "property float scale_2",
      "property float rot_0",
      "property float rot_1",
      "property float rot_2",
      "property float rot_3",
      "property float opacity",
      "property float f_dc_0",
      "property float f_dc_1",
      "property float f_dc_2",
      "end_header",
    ])
    rows = [
      f"{x:.5f} {y:.5f} {z:.5f} -3.30000 -3.30000 -3.30000 1.00000 0.00000 0.00000 0.00000 2.00000 0.70000 0.20000 0.10000"
      for x, y, z in points
    ]
  return header, rows


def write_demo_point_cloud(output_dir: Path, representation: str) -> Path:
  point_cloud_path = output_dir / "point_cloud.ply"
  header, rows = demo_vertex_rows(representation)
  point_cloud_path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
  return point_cloud_path


def latest_iteration_ply(model_dir: Path) -> Path | None:
  point_cloud_dir = model_dir / "point_cloud"
  candidates: list[tuple[int, Path]] = []
  if point_cloud_dir.exists():
    for child in point_cloud_dir.iterdir():
      if not child.is_dir() or not child.name.startswith("iteration_"):
        continue
      try:
        iteration = int(child.name.split("_")[-1])
      except ValueError:
        continue
      ply_path = child / "point_cloud.ply"
      if ply_path.exists():
        candidates.append((iteration, ply_path))
  if candidates:
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

  direct_candidates = [
    model_dir / "point_cloud.ply",
    model_dir / "input.ply",
  ]
  for candidate in direct_candidates:
    if candidate.exists():
      return candidate
  return None


def latest_render_image(model_dir: Path) -> Path | None:
  candidates: list[tuple[float, Path]] = []
  for root_name in ("test", "train"):
    root = model_dir / root_name
    if not root.exists():
      continue
    for image_path in root.glob("ours_*/renders/*.png"):
      try:
        score = image_path.stat().st_mtime
      except OSError:
        continue
      candidates.append((score, image_path))
  if not candidates:
    return None
  candidates.sort(key=lambda item: item[0], reverse=True)
  return candidates[0][1]


def write_manifest(output_dir: Path, adapter: str, representation: str) -> Path:
  manifest_path = output_dir / "scene_manifest.json"
  manifest = {
    "version": "0.1.0",
    "sceneId": f"materialized-{adapter}",
    "title": f"{adapter} Materialized Output",
    "renderer": representation,
    "representation": representation,
    "source": {
      "url": "./point_cloud.ply",
      "format": "ply",
    },
    "algorithm": {
      "family": adapter,
      "name": adapter,
      "mode": "materialized-model-output",
    },
    "metadata": {
      "appearanceModel": representation,
      "generatedBy": "materialize_model_output.py",
    },
  }
  manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
  return manifest_path


def write_bridge_fallback(output_dir: Path, input_path: Path | None, adapter: str, representation: str, model_dir: str) -> None:
  if input_path is not None and input_path.exists():
    shutil.copyfile(input_path, output_dir / "latest.png")
  point_cloud_path = write_demo_point_cloud(output_dir, representation)
  manifest_path = write_manifest(output_dir, adapter, representation)
  metrics = {
    "adapter": adapter,
    "representation": representation,
    "status": "materialized-fallback-bridge",
    "model_dir": model_dir,
    "point_cloud": str(point_cloud_path.resolve()),
    "scene_manifest": str(manifest_path.resolve()),
    "timestamp": time.time(),
  }
  (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
  print(json.dumps(metrics, ensure_ascii=False))


def main() -> None:
  parser = argparse.ArgumentParser(description="Materialize a trained model output into the web runtime output layout.")
  parser.add_argument("--adapter", required=True)
  parser.add_argument("--representation", required=True)
  parser.add_argument("--model-dir", default="")
  parser.add_argument("--output-dir", required=True)
  parser.add_argument("--input", default="")
  args = parser.parse_args()

  output_dir = Path(args.output_dir).expanduser().resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  input_path = Path(args.input).expanduser().resolve() if args.input else None

  if not args.model_dir:
    write_bridge_fallback(output_dir, input_path, args.adapter, args.representation, "")
    return

  model_dir = Path(args.model_dir).expanduser().resolve()
  if not model_dir.exists():
    write_bridge_fallback(output_dir, input_path, args.adapter, args.representation, str(model_dir))
    return

  ply_path = latest_iteration_ply(model_dir)
  if ply_path is None:
    write_bridge_fallback(output_dir, input_path, args.adapter, args.representation, str(model_dir))
    return

  shutil.copyfile(ply_path, output_dir / "point_cloud.ply")

  render_path = latest_render_image(model_dir)
  if render_path is not None:
    shutil.copyfile(render_path, output_dir / "latest.png")

  manifest_path = write_manifest(output_dir, args.adapter, args.representation)
  metrics = {
    "adapter": args.adapter,
    "representation": args.representation,
    "status": "materialized-model-output",
    "model_dir": str(model_dir),
    "point_cloud": str((output_dir / "point_cloud.ply").resolve()),
    "scene_manifest": str(manifest_path.resolve()),
    "timestamp": time.time(),
  }
  (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
  print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
  main()
