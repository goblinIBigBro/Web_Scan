#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import api_server


def write_file(path: Path, data: bytes = b"png") -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(data)
  return path


def cleanup_session(session_id: str) -> None:
  for root in (api_server.STREAM_DIR, api_server.DATASET_DIR, api_server.WORKSPACE_DIR):
    target = root / session_id
    if target.exists():
      shutil.rmtree(target)


def make_session() -> str:
  session_id = f"flow-data-{uuid.uuid4().hex[:8]}"
  capture_id = "capture-a"
  write_file(api_server.STREAM_DIR / session_id / "captures" / capture_id / "input" / "0001.png")
  write_file(api_server.STREAM_DIR / session_id / "captures" / capture_id / "input" / "0002.png")
  write_file(api_server.STREAM_DIR / session_id / "output" / "latest.png")
  dataset_root = api_server.DATASET_DIR / session_id / "datasets" / "dataset-a"
  write_file(dataset_root / "images" / "0001.png")
  (dataset_root / "capture_session.json").write_text(
    '{"dataset_id":"dataset-a","dataset_name":"Dataset A","capture_id":"capture-a","frame_count":1}',
    encoding="utf-8",
  )
  workspace_root = api_server.WORKSPACE_DIR / session_id / "hac-plus-plus" / "dataset-a"
  write_file(workspace_root / "input" / "0001.png")
  (workspace_root / "workspace_manifest.json").write_text(
    '{"dataset_id":"dataset-a","dataset_name":"Dataset A","family":"hac-plus-plus","capture_id":"capture-a","frame_count":1}',
    encoding="utf-8",
  )
  return session_id


def test_inspect_flow_data() -> None:
  session_id = make_session()
  try:
    data = api_server.inspect_flow_data(session_id, "capture-a", "hac-plus-plus")
    assert data["ok"] is True
    assert data["capture"]["frame_count"] == 2, data
    assert data["upload"]["uploaded_frame_count"] == 2, data
    assert data["session_prep"]["dataset_count"] == 1, data
    assert data["session_prep"]["workspace_count"] == 1, data
  finally:
    cleanup_session(session_id)


def test_delete_session_prep_keeps_upload() -> None:
  session_id = make_session()
  try:
    result = api_server.delete_flow_data_stage({
      "session_id": session_id,
      "capture_id": "capture-a",
      "family": "hac-plus-plus",
      "stage": "session_prep",
    })
    assert result["ok"] is True
    assert len(result["deleted_paths"]) == 2, result
    data = result["data"]
    assert data["capture"]["frame_count"] == 2, data
    assert data["session_prep"]["dataset_count"] == 0, data
    assert data["session_prep"]["workspace_count"] == 0, data
  finally:
    cleanup_session(session_id)


def test_delete_capture_clears_stream_capture() -> None:
  session_id = make_session()
  try:
    result = api_server.delete_flow_data_stage({
      "session_id": session_id,
      "capture_id": "capture-a",
      "stage": "capture",
    })
    assert result["ok"] is True
    data = result["data"]
    assert data["capture"]["frame_count"] == 0, data
    assert data["upload"]["latest_output"] is None, data
    assert data["session_prep"]["dataset_count"] == 1, data
  finally:
    cleanup_session(session_id)


def test_rejects_unsafe_session_root() -> None:
  try:
    api_server.inspect_flow_data("", "", "")
    raise AssertionError("inspect_flow_data should require session_id")
  except ValueError as exc:
    assert "session_id" in str(exc)


def main() -> None:
  test_inspect_flow_data()
  test_delete_session_prep_keeps_upload()
  test_delete_capture_clears_stream_capture()
  test_rejects_unsafe_session_root()
  print("flow data tests passed")


if __name__ == "__main__":
  main()
