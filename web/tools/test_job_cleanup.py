#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import api_server


CREATED: list[str] = []


def make_job(status: str) -> dict:
  job_id = f"cleanup-{status}-{uuid.uuid4().hex[:8]}"
  job = {
    "id": job_id,
    "status": status,
    "operation": "remote_train",
    "created_at": 1,
    "metrics": {},
  }
  api_server.ensure_job_logging(job)
  api_server.persist_job_state(job)
  api_server.JOBS[job_id] = job
  CREATED.append(job_id)
  return job


def cleanup() -> None:
  for job_id in CREATED:
    api_server.JOBS.pop(job_id, None)
    api_server.JOB_LOG_LOCKS.pop(job_id, None)
    path = api_server.JOB_LOG_DIR / job_id
    if path.exists():
      shutil.rmtree(path)


def test_remove_terminal_record_keeps_logs() -> None:
  job = make_job("canceled")
  job_id = job["id"]
  log_dir = Path(job["log_dir"])
  assert (log_dir / api_server.JOB_STATE_FILE).exists()

  result = api_server.remove_job_record(job_id)
  assert result["id"] == job_id
  assert job_id not in api_server.JOBS
  assert not (log_dir / api_server.JOB_STATE_FILE).exists()
  assert (log_dir / "runtime.log").exists()
  assert (log_dir / "metrics.csv").exists()


def test_running_record_cannot_be_removed() -> None:
  job = make_job("running")
  try:
    api_server.remove_job_record(job["id"])
    raise AssertionError("running job record should not be removable")
  except ValueError as exc:
    assert "Cancel running jobs first" in str(exc)
  assert job["id"] in api_server.JOBS


def test_clear_canceled_only() -> None:
  canceled = make_job("canceled")
  completed = make_job("completed")
  running = make_job("running")
  result = api_server.clear_job_records(["canceled"])
  removed_ids = {item["id"] for item in result["removed"]}
  assert canceled["id"] in removed_ids
  assert completed["id"] in api_server.JOBS
  assert running["id"] in api_server.JOBS


def main() -> None:
  try:
    test_remove_terminal_record_keeps_logs()
    test_running_record_cannot_be_removed()
    test_clear_canceled_only()
    print("job cleanup tests passed")
  finally:
    cleanup()


if __name__ == "__main__":
  main()
