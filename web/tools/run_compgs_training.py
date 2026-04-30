#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_path(value: str | None, *, base: Path | None = None) -> Path | None:
  text = str(value or "").strip()
  if not text:
    return None
  path = Path(text).expanduser()
  if not path.is_absolute() and base is not None:
    path = base / path
  return path.resolve()


def yaml_scalar(value: object) -> str:
  if isinstance(value, bool):
    return "true" if value else "false"
  if isinstance(value, (int, float)):
    return str(value)
  return json.dumps(str(value), ensure_ascii=False)


def rewrite_compgs_config(template_path: Path, output_path: Path, updates: dict[str, dict[str, object]]) -> None:
  current_section = ""
  rewritten: list[str] = []
  for raw_line in template_path.read_text(encoding="utf-8").splitlines():
    stripped = raw_line.strip()
    if stripped and not raw_line.startswith((" ", "\t")) and stripped.endswith(":"):
      current_section = stripped[:-1]

    next_line = raw_line
    if current_section in updates and raw_line.startswith("  ") and ":" in stripped:
      key = stripped.split(":", 1)[0].strip()
      if key in updates[current_section]:
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        comment = ""
        if "#" in raw_line:
          comment = "  #" + raw_line.split("#", 1)[1]
        next_line = f"{indent}{key}: {yaml_scalar(updates[current_section][key])}{comment}"
    rewritten.append(next_line)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def infer_image_folder(dataset_root: Path, requested: str) -> str:
  if requested:
    return requested
  for name in ("images", "images_4", "images_2", "input"):
    if (dataset_root / name).is_dir():
      return name
  return "images"


def latest_compgs_ply(output_dir: Path) -> Path | None:
  candidates: list[tuple[int, float, Path]] = []
  for path in output_dir.rglob("point_cloud.ply"):
    parts = path.parts
    iteration = -1
    for part in parts:
      if part.startswith("iteration_"):
        try:
          iteration = int(part.split("_")[-1])
        except ValueError:
          iteration = -1
    candidates.append((iteration, path.stat().st_mtime, path))
  if not candidates:
    return None
  candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
  return candidates[0][2]


def main() -> int:
  parser = argparse.ArgumentParser(description="Prepare a CompGS YAML config, then run CompGS training.")
  parser.add_argument("--dataset-root", required=True)
  parser.add_argument("--output-dir", required=True)
  parser.add_argument("--repo-path", default="")
  parser.add_argument("--config-template", default="")
  parser.add_argument("--image-folder", default="")
  parser.add_argument("--gpcc-codec-path", default="")
  parser.add_argument("--max-iterations", type=int, default=30000)
  parser.add_argument("--lambda-weight", type=float, default=0.001)
  parser.add_argument("--save-interval", type=int, default=10000)
  parser.add_argument("--generated-config-name", default="webscan_compgs.yaml")
  args = parser.parse_args()

  script_root = Path(__file__).resolve().parents[2]
  repo_path = resolve_path(args.repo_path) or (script_root / "CompGS-main").resolve()
  dataset_root = resolve_path(args.dataset_root)
  output_dir = resolve_path(args.output_dir)
  if dataset_root is None or not dataset_root.is_dir():
    raise SystemExit(f"Dataset root not found: {args.dataset_root}")
  if output_dir is None:
    raise SystemExit("--output-dir is required")
  if not repo_path.is_dir():
    raise SystemExit(f"CompGS repo not found: {repo_path}")

  template_path = resolve_path(args.config_template, base=repo_path) if args.config_template else None
  if template_path is None:
    template_path = repo_path / "Configs" / "MipNeRF360.yaml"
  if not template_path.is_file():
    raise SystemExit(f"CompGS config template not found: {template_path}")

  image_folder = infer_image_folder(dataset_root, args.image_folder)
  gpcc_codec_path = args.gpcc_codec_path.strip() or os.environ.get("GSC_GPCC_CODEC_PATH", "").strip() or "tmc3"
  generated_config = output_dir / "config" / args.generated_config_name
  updates = {
    "dataset": {
      "root": str(dataset_root),
      "image_folder": image_folder,
    },
    "training": {
      "max_iterations": args.max_iterations,
      "save_directory": str(output_dir),
      "save_interval": args.save_interval,
      "gpcc_codec_path": gpcc_codec_path,
      "lambda_weight": args.lambda_weight,
    },
  }
  rewrite_compgs_config(template_path, generated_config, updates)
  print(f"[CompGS] Wrote config: {generated_config}", flush=True)
  print(f"[CompGS] Dataset root: {dataset_root}", flush=True)
  print(f"[CompGS] Image folder: {image_folder}", flush=True)
  print(f"[CompGS] Save directory: {output_dir}", flush=True)

  command = [sys.executable, str(repo_path / "Train.py"), "--config", str(generated_config)]
  completed = subprocess.run(command, cwd=str(repo_path))
  if completed.returncode != 0:
    return completed.returncode

  latest_ply = latest_compgs_ply(output_dir)
  if latest_ply:
    stable_ply = output_dir / "compgs_point_cloud.ply"
    if latest_ply.resolve() != stable_ply.resolve():
      shutil.copy2(latest_ply, stable_ply)
    print(f"[CompGS] Latest PLY: {latest_ply}", flush=True)
    print(f"[CompGS] Stable PLY: {stable_ply}", flush=True)
  else:
    print("[CompGS] Training finished, but no point_cloud.ply checkpoint was found.", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
