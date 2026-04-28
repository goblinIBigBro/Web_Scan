#!/usr/bin/env python3
from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import api_server
from web.server.remote_executor import RemoteExecutionError


class DummyProcess:
  def __init__(self) -> None:
    self.terminated = False

  def poll(self):
    return None

  def terminate(self) -> None:
    self.terminated = True


def test_flow_temp_paths_are_scoped() -> None:
  session_id = f"flow-reset-{uuid.uuid4().hex[:8]}"
  removed: list[str] = []
  cleaned = api_server.cleanup_flow_temporary_dirs(
    session_id,
    remover=lambda path: removed.append(str(path)),
    exists=lambda path: True,
  )
  assert len(cleaned) == 3
  assert cleaned == removed
  for item in cleaned:
    assert "/web/generated/" in item
    assert session_id in item


def test_reset_cancels_matching_local_job() -> None:
  session_id = f"flow-reset-{uuid.uuid4().hex[:8]}"
  job_id = f"job-{uuid.uuid4().hex[:8]}"
  process = DummyProcess()
  job = {
    "id": job_id,
    "status": "running",
    "operation": "remote_train",
    "session_id": session_id,
    "capture_id": "capture-a",
    "created_at": 1,
    "metrics": {},
    "_process": process,
  }
  api_server.JOBS[job_id] = job
  try:
    result = api_server.reset_flow({
      "session_id": session_id,
      "capture_id": "capture-a",
      "selected_job_id": job_id,
      "reset_scope": "all",
      "cancel_unfinished": True,
    })
    assert result["ok"] is True
    assert result["canceled_jobs"][0]["id"] == job_id
    assert job["status"] == "canceled"
    assert job["remote_stage"] == "flow_reset"
    assert process.terminated is True
  finally:
    api_server.JOBS.pop(job_id, None)


def test_reset_requires_remote_credentials_for_detached_job() -> None:
  session_id = f"flow-reset-{uuid.uuid4().hex[:8]}"
  job_id = f"job-{uuid.uuid4().hex[:8]}"
  api_server.JOBS[job_id] = {
    "id": job_id,
    "status": "running",
    "operation": "remote_train",
    "session_id": session_id,
    "remote_detached": True,
    "created_at": 1,
    "metrics": {},
  }
  try:
    try:
      api_server.reset_flow({
        "session_id": session_id,
        "selected_job_id": job_id,
        "reset_scope": "all",
        "cancel_unfinished": True,
        "remote": {},
      })
      raise AssertionError("reset_flow should require remote credentials for detached jobs")
    except RemoteExecutionError as exc:
      assert exc.code_hint == "WGSC-FLOW-RESET-REMOTE-CONFIG"
      assert api_server.JOBS[job_id]["status"] == "running"
  finally:
    api_server.JOBS.pop(job_id, None)


def main() -> None:
  test_flow_temp_paths_are_scoped()
  test_reset_cancels_matching_local_job()
  test_reset_requires_remote_credentials_for_detached_job()
  print("flow reset tests passed")


if __name__ == "__main__":
  main()
