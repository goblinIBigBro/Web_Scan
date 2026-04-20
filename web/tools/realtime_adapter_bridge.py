#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path


def sh_vertex_line(x: float, y: float, z: float, scale: float, color: tuple[float, float, float]) -> str:
  return (
    f"{x:.5f} {y:.5f} {z:.5f} "
    f"{scale:.5f} {scale:.5f} {scale:.5f} "
    "1.00000 0.00000 0.00000 0.00000 "
    "2.00000 "
    f"{color[0]:.5f} {color[1]:.5f} {color[2]:.5f}"
  )


def sg_vertex_line(x: float, y: float, z: float, scale: float, color: tuple[float, float, float]) -> str:
  return (
    f"{x:.5f} {y:.5f} {z:.5f} "
    f"{scale:.5f} {scale:.5f} {scale:.5f} "
    "1.00000 0.00000 0.00000 0.00000 "
    "2.00000 "
    f"{color[0]:.5f} {color[1]:.5f} {color[2]:.5f} "
    "0"
  )


def build_demo_points() -> list[tuple[float, float, float, float, tuple[float, float, float]]]:
  colors = [
    (0.8, -0.2, -0.2),
    (-0.3, 0.9, -0.2),
    (-0.3, -0.2, 0.9),
    (0.6, 0.5, -0.1),
    (0.5, -0.1, 0.7),
    (-0.1, 0.7, 0.6),
    (0.2, 0.2, 0.2),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
  ]
  points: list[tuple[float, float, float, float, tuple[float, float, float]]] = []
  cursor = 0
  for z in (-0.18, 0.0, 0.18):
    for y in (-0.18, 0.0, 0.18):
      for x in (-0.18, 0.0, 0.18):
        points.append((x, y, z, -3.2, colors[cursor % len(colors)]))
        cursor += 1
  return points


def write_demo_ply(output_dir: Path, representation: str) -> Path:
  points = build_demo_points()
  point_cloud_path = output_dir / "point_cloud.ply"
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
    rows = [sg_vertex_line(x, y, z, scale, color) for x, y, z, scale, color in points]
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
    rows = [sh_vertex_line(x, y, z, scale, color) for x, y, z, scale, color in points]
  point_cloud_path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
  return point_cloud_path


def write_scene_manifest(output_dir: Path, adapter: str, representation: str) -> Path:
  manifest_path = output_dir / "scene_manifest.json"
  manifest = {
    "version": "0.1.0",
    "sceneId": f"realtime-{adapter}",
    "title": f"Realtime {adapter}",
    "renderer": representation,
    "representation": representation,
    "source": {
      "url": "./point_cloud.ply",
      "format": "ply",
    },
    "algorithm": {
      "family": adapter,
      "name": adapter,
      "mode": "realtime-bridge",
    },
    "metadata": {
      "appearanceModel": representation,
      "generatedBy": "realtime_adapter_bridge.py",
      "notes": "Bridge placeholder scene for end-to-end realtime viewer validation.",
    },
  }
  manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
  return manifest_path


def main() -> None:
  parser = argparse.ArgumentParser(description="Bridge realtime frame processing results back to the web platform.")
  parser.add_argument("--adapter", required=True)
  parser.add_argument("--input", required=True)
  parser.add_argument("--output-dir", required=True)
  parser.add_argument("--repo-path", default="")
  parser.add_argument("--representation", default="sh", choices=["sh", "sg"])
  parser.add_argument("--mode", default="copy", choices=["copy", "copy-and-scene"])
  args = parser.parse_args()

  input_path = Path(args.input)
  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)

  latest_output = output_dir / "latest.png"
  shutil.copyfile(input_path, latest_output)
  point_cloud_path = write_demo_ply(output_dir, args.representation)
  manifest_path = write_scene_manifest(output_dir, args.adapter, args.representation)

  metrics = {
    "adapter": args.adapter,
    "fps": 24.0,
    "iter": 1,
    "loss": 0.0,
    "psnr": 30.0,
    "status": "bridge-copy",
    "repo_path": args.repo_path,
    "representation": args.representation,
    "point_cloud": str(point_cloud_path),
    "scene_manifest": str(manifest_path),
    "timestamp": time.time(),
  }
  (output_dir / "metrics.json").write_text(
    json.dumps(metrics, indent=2, ensure_ascii=False),
    encoding="utf-8",
  )
  print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
  main()
