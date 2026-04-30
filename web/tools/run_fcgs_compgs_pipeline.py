#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from run_compgs_training import latest_compgs_ply, resolve_path


def main() -> int:
  parser = argparse.ArgumentParser(description="Train a 3DGS-style PLY with CompGS, then run FCGS on it.")
  parser.add_argument("--dataset-root", required=True)
  parser.add_argument("--output-dir", required=True)
  parser.add_argument("--fcgs-repo", default="")
  parser.add_argument("--compgs-repo", default="")
  parser.add_argument("--compgs-config-template", default="")
  parser.add_argument("--image-folder", default="")
  parser.add_argument("--gpcc-codec-path", default="")
  parser.add_argument("--max-iterations", type=int, default=30000)
  parser.add_argument("--lambda-weight", type=float, default=0.001)
  parser.add_argument("--save-interval", type=int, default=10000)
  parser.add_argument("--fcgs-lmd", type=float, default=1e-4)
  parser.add_argument("--fcgs-nr", type=float, default=3)
  parser.add_argument("--fcgs-determ", type=float, default=1)
  parser.add_argument("--skip-decode", action="store_true")
  args = parser.parse_args()

  script_root = Path(__file__).resolve().parents[2]
  fcgs_repo = resolve_path(args.fcgs_repo) or (script_root / "FCGS-main").resolve()
  compgs_repo = resolve_path(args.compgs_repo) or (script_root / "CompGS-main").resolve()
  dataset_root = resolve_path(args.dataset_root)
  output_dir = resolve_path(args.output_dir)
  if dataset_root is None or not dataset_root.is_dir():
    raise SystemExit(f"Dataset root not found: {args.dataset_root}")
  if output_dir is None:
    raise SystemExit("--output-dir is required")
  if not fcgs_repo.is_dir():
    raise SystemExit(f"FCGS repo not found: {fcgs_repo}")
  if not compgs_repo.is_dir():
    raise SystemExit(f"CompGS repo not found: {compgs_repo}")

  compgs_output = output_dir / "compgs_pretrain"
  fcgs_bits = output_dir / "fcgs_bitstreams"
  output_dir.mkdir(parents=True, exist_ok=True)

  compgs_command = [
    sys.executable,
    str(script_root / "web" / "tools" / "run_compgs_training.py"),
    "--dataset-root",
    str(dataset_root),
    "--output-dir",
    str(compgs_output),
    "--repo-path",
    str(compgs_repo),
    "--max-iterations",
    str(args.max_iterations),
    "--lambda-weight",
    str(args.lambda_weight),
    "--save-interval",
    str(args.save_interval),
  ]
  if args.compgs_config_template:
    compgs_command.extend(["--config-template", args.compgs_config_template])
  if args.image_folder:
    compgs_command.extend(["--image-folder", args.image_folder])
  if args.gpcc_codec_path:
    compgs_command.extend(["--gpcc-codec-path", args.gpcc_codec_path])

  print("[FCGS] Starting CompGS pre-training for source PLY.", flush=True)
  completed = subprocess.run(compgs_command)
  if completed.returncode != 0:
    return completed.returncode

  source_ply = latest_compgs_ply(compgs_output)
  if source_ply is None:
    raise SystemExit(f"CompGS did not produce a point_cloud.ply under {compgs_output}")
  stable_source_ply = output_dir / "compgs_point_cloud.ply"
  shutil.copy2(source_ply, stable_source_ply)
  print(f"[FCGS] Using CompGS PLY: {stable_source_ply}", flush=True)

  encode_command = [
    sys.executable,
    str(fcgs_repo / "encode_single_scene.py"),
    "--lmd",
    str(args.fcgs_lmd),
    "--nr",
    str(args.fcgs_nr),
    "--determ",
    str(args.fcgs_determ),
    "--ply_path_from",
    str(stable_source_ply),
    "--bit_path_to",
    str(fcgs_bits),
  ]
  print("[FCGS] Encoding CompGS PLY.", flush=True)
  completed = subprocess.run(encode_command, cwd=str(fcgs_repo))
  if completed.returncode != 0:
    return completed.returncode

  if not args.skip_decode:
    decoded_ply = output_dir / "point_cloud.ply"
    decode_command = [
      sys.executable,
      str(fcgs_repo / "decode_single_scene.py"),
      "--lmd",
      str(args.fcgs_lmd),
      "--bit_path_from",
      str(fcgs_bits),
      "--ply_path_to",
      str(decoded_ply),
    ]
    print("[FCGS] Decoding bitstreams to point_cloud.ply for the web viewer.", flush=True)
    completed = subprocess.run(decode_command, cwd=str(fcgs_repo))
    if completed.returncode != 0:
      return completed.returncode
    print(f"[FCGS] Decoded PLY: {decoded_ply}", flush=True)

  print(f"[FCGS] Bitstreams: {fcgs_bits}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
