#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server.api_server import discover_runtime_results, load_result_path


TEST_ROOT = ROOT_DIR / "web" / "generated" / "result_loader_tests"
DISCOVER_ROOT = ROOT_DIR / "web" / "generated" / "runs" / "result_loader_tests_discover"


def write_file(path: Path, data: bytes = b"test") -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(data)
  return path


def reset_test_root() -> None:
  if TEST_ROOT.exists():
    shutil.rmtree(TEST_ROOT)
  if DISCOVER_ROOT.exists():
    shutil.rmtree(DISCOVER_ROOT)
  TEST_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_test_root() -> None:
  if TEST_ROOT.exists():
    shutil.rmtree(TEST_ROOT)
  if DISCOVER_ROOT.exists():
    shutil.rmtree(DISCOVER_ROOT)


def test_ply_priority() -> None:
  result_dir = TEST_ROOT / "hac"
  write_file(result_dir / "point_cloud" / "iteration_10" / "point_cloud.ply", b"ply\n")
  write_file(result_dir / "test" / "ours_10" / "renders" / "00001.png", b"png")
  write_file(result_dir / "train" / "ours_10" / "renders" / "00002.png", b"png")

  result = load_result_path(str(result_dir), family="hac-plus-plus")
  assert result["ok"], result
  assert result["type"] == "ply", result
  assert result["point_cloud_url"].endswith("/point_cloud.ply"), result
  assert result["render_image_count"] == 2, result
  assert len(result["result_urls"]) == 2, result
  assert all(url.endswith(".png") for url in result["result_urls"]), result


def test_image_fallback() -> None:
  result_dir = TEST_ROOT / "image-only"
  write_file(result_dir / "test" / "ours_30" / "renders" / "00001.png", b"png")
  write_file(result_dir / "test" / "ours_30" / "renders" / "00002.png", b"png")

  result = load_result_path(str(result_dir), family="contextgs")
  assert result["ok"], result
  assert result["type"] == "image", result
  assert result["result_url"].endswith(".png"), result
  assert result["render_image_count"] == 2, result
  assert len(result["render_images"]) == 2, result


def test_reduced_prefers_quantised_half() -> None:
  result_dir = TEST_ROOT / "reduced"
  iteration_dir = result_dir / "point_cloud" / "iteration_7"
  write_file(iteration_dir / "point_cloud.ply", b"baseline")
  write_file(iteration_dir / "point_cloud_quantised.ply", b"quantised")
  write_file(iteration_dir / "point_cloud_quantised_half.ply", b"half")

  result = load_result_path(str(result_dir), family="reduced-3dgs")
  assert result["ok"], result
  assert result["type"] == "ply", result
  assert result["resolved_path"].endswith("point_cloud_quantised_half.ply"), result


def test_compgs_image_fallback() -> None:
  result_dir = TEST_ROOT / "compgs"
  write_file(result_dir / "eval" / "rendered" / "0000.png", b"png")

  result = load_result_path(str(result_dir), family="compgs")
  assert result["ok"], result
  assert result["type"] == "image", result
  assert result["result_url"].endswith("/0000.png"), result


def test_compgs_timestamp_ply_from_parent() -> None:
  result_dir = TEST_ROOT / "compgs-timestamp-ply"
  write_file(result_dir / "2026-05-02_10-00" / "point_cloud" / "iteration_10000" / "point_cloud.ply", b"old")
  write_file(result_dir / "2026-05-03_10-27" / "point_cloud" / "iteration_30000" / "point_cloud.ply", b"new")

  result = load_result_path(str(result_dir), family="compgs")
  assert result["ok"], result
  assert result["type"] == "ply", result
  assert "2026-05-03_10-27" in result["resolved_path"], result
  assert result["resolved_path"].endswith("point_cloud/iteration_30000/point_cloud.ply"), result


def test_compgs_timestamp_image_fallback_from_parent() -> None:
  result_dir = TEST_ROOT / "compgs-timestamp-image"
  write_file(result_dir / "2026-05-03_10-27" / "eval_training" / "rendered" / "0000.png", b"png")

  result = load_result_path(str(result_dir), family="compgs")
  assert result["ok"], result
  assert result["type"] == "image", result
  assert "2026-05-03_10-27" in result["resolved_path"], result
  assert result["result_url"].endswith("/eval_training/rendered/0000.png"), result


def test_fcgs_bitstream_message() -> None:
  result_dir = TEST_ROOT / "fcgs-bitstream"
  write_file(result_dir / "0.0001" / "0" / "chunk.bin", b"bits")

  result = load_result_path(str(result_dir), family="fcgs")
  assert not result["ok"], result
  assert "decoded PLY" in result["reason"], result


def test_empty_directory() -> None:
  result_dir = TEST_ROOT / "empty"
  result_dir.mkdir(parents=True, exist_ok=True)

  result = load_result_path(str(result_dir), family="megs2")
  assert not result["ok"], result
  assert "No supported" in result["reason"], result


def test_discover_generated_runs() -> None:
  result_dir = DISCOVER_ROOT / "session-a" / "hac-plus-plus"
  write_file(result_dir / "point_cloud" / "iteration_3" / "point_cloud.ply", b"ply\n")
  write_file(result_dir / "test" / "ours_3" / "renders" / "00001.png", b"png")

  results = discover_runtime_results(limit=20, max_scan_dirs=500)
  assert any(
    item.get("point_cloud_url", "").endswith("/point_cloud.ply")
    and "result_loader_tests_discover" in item.get("output_dir", "")
    and item.get("render_image_count") == 1
    for item in results
  ), results


def main() -> None:
  reset_test_root()
  try:
    test_ply_priority()
    test_image_fallback()
    test_reduced_prefers_quantised_half()
    test_compgs_image_fallback()
    test_compgs_timestamp_ply_from_parent()
    test_compgs_timestamp_image_fallback_from_parent()
    test_fcgs_bitstream_message()
    test_empty_directory()
    test_discover_generated_runs()
    print("result loader tests passed")
  finally:
    cleanup_test_root()


if __name__ == "__main__":
  main()
