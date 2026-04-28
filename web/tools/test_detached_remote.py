#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import api_server
from web.server.remote_executor import (
  _build_remote_detached_run_script,
  _build_remote_detached_start_command,
  _remote_job_paths,
)


def test_detached_script_contract() -> None:
  validated = {
    "python": "python3",
    "repo_path": "/remote/repo",
    "activate_cmd": "source /opt/env/bin/activate",
  }
  remote_paths = {
    "workspace_dir": "/tmp/web_scan/workspaces/session/hac/job/workspace",
    "output_dir": "/tmp/web_scan/outputs/session/hac/job/output",
  }
  job_paths = _remote_job_paths(remote_paths["output_dir"])
  script = _build_remote_detached_run_script(
    validated=validated,
    job_id="job-1",
    family="hac",
    remote_paths=remote_paths,
    remote_job_paths=job_paths,
    remote_workspace_for_command="/tmp/web_scan/workspaces/datasets/hac/demo/workspace",
    remote_command="python train.py -s /tmp/source -m /tmp/out",
    auto_colmap=True,
    resolved_dataset_id="demo",
    resolved_dataset_name="Demo",
    use_existing_remote_dataset=False,
  )
  start_command = _build_remote_detached_start_command(job_paths)

  assert "status.json" in script
  assert "runtime.log" in script
  assert "echo \"$$\" > \"$PID_FILE\"" in script
  assert "EXIT_CODE_FILE" in script
  assert "sequential_matcher" in script
  assert "setsid" in start_command
  assert "nohup" in start_command


def test_job_persistence_sanitizes_password() -> None:
  job = {
    "id": "persist-test",
    "status": "running",
    "remote_detached": True,
    "remote": {
      "host": "127.0.0.1",
      "port": 22,
      "username": "chen",
      "password": "secret-password",
      "repo_path": "/remote/repo",
      "workspace_root": "/tmp/workspaces",
      "output_root": "/tmp/outputs",
      "python": "python3",
      "activate_cmd": "",
    },
    "_remote_config": {"password": "secret-password"},
  }
  payload = api_server.sanitize_job_for_persistence(job)
  serialized = json.dumps(payload, ensure_ascii=False)

  assert "secret-password" not in serialized
  assert payload["remote"]["has_password"] is True
  assert "_remote_config" not in payload


def test_apply_remote_poll_statuses() -> None:
  job_id = f"detached-test-{uuid.uuid4().hex[:8]}"
  job = {
    "id": job_id,
    "status": "detached",
    "operation": "remote_train",
    "representation": "sh",
    "output_dir": str(Path(api_server.WEB_DIR) / "generated" / "runs" / job_id),
    "remote_result": {},
  }
  api_server.apply_remote_poll_result(job, {
    "status": "running",
    "stage": "executing_remote_command",
    "return_code": "",
    "remote_pid": "12345",
    "log_text": "iter 1 loss 0.1\n",
    "log_cursor": 18,
    "remote_output_dir": "/tmp/outputs/session/hac/job/output",
    "download": {"files": 0, "bytes": 0, "pending": True},
  })
  assert job["status"] == "running"
  assert job["remote_stage"] == "executing_remote_command"
  assert job["remote_pid"] == "12345"
  assert job["monitor_state"] == "monitoring"

  api_server.apply_remote_poll_result(job, {
    "status": "completed",
    "stage": "completed",
    "return_code": 0,
    "log_text": "done\n",
    "log_cursor": 23,
    "download": {"files": 2, "bytes": 128},
  })
  assert job["status"] == "completed"
  assert job["return_code"] == 0
  assert job["finished_at"]
  assert job["remote_result"]["download"]["files"] == 2


def main() -> None:
  test_detached_script_contract()
  test_job_persistence_sanitizes_password()
  test_apply_remote_poll_statuses()
  print("detached remote tests passed")


if __name__ == "__main__":
  main()
