#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import stat
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import api_server
from web.server.remote_executor import (
  _build_remote_cancel_script,
  _build_remote_detached_run_script,
  _build_remote_tmux_start_command,
  _download_directory,
  _remote_job_paths,
  _tmux_install_candidates,
  build_remote_tmux_attach_command,
  build_remote_tmux_session_name,
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
  tmux_session = build_remote_tmux_session_name(family="hac", job_id="job 1:unsafe/name")
  start_command = _build_remote_tmux_start_command(job_paths, tmux_session)
  attach_command = build_remote_tmux_attach_command(
    {
      "host": "10.0.0.5",
      "port": 2222,
      "username": "ubuntu",
      "password": "secret-password",
      "repo_path": "/remote/repo",
      "workspace_root": "/tmp/web_scan/workspaces",
      "output_root": "/tmp/web_scan/outputs",
      "python": "python3",
      "activate_cmd": "",
    },
    tmux_session,
  )

  assert "status.json" in script
  assert "runtime.log" in script
  assert "echo \"$$\" > \"$PID_FILE\"" in script
  assert "EXIT_CODE_FILE" in script
  assert "sequential_matcher" in script
  assert "tmux new-session" in start_command
  assert "tee -a" in start_command
  assert "setsid" not in start_command
  assert "nohup" not in start_command
  assert tmux_session == "wgsc-hac-job-1-unsafe-name"
  assert "tmux attach -t" in attach_command
  assert "secret-password" not in attach_command


def test_existing_dataset_disables_auto_colmap_contract() -> None:
  validated = {
    "python": "python3",
    "repo_path": "/remote/repo",
    "activate_cmd": "",
  }
  remote_paths = {
    "workspace_dir": "/tmp/web_scan/workspaces/session/hac/job/workspace",
    "output_dir": "/tmp/web_scan/outputs/session/hac/job/output",
  }
  job_paths = _remote_job_paths(remote_paths["output_dir"])
  script = _build_remote_detached_run_script(
    validated=validated,
    job_id="job-existing",
    family="hac",
    remote_paths=remote_paths,
    remote_job_paths=job_paths,
    remote_workspace_for_command="/tmp/web_scan/workspaces/datasets/hac/reuse/workspace",
    remote_command="python train.py -s /tmp/reuse -m /tmp/out",
    auto_colmap=True,
    resolved_dataset_id="reuse",
    resolved_dataset_name="Reuse",
    use_existing_remote_dataset=True,
  )

  assert "AUTO_COLMAP=0" in script
  assert "USE_EXISTING_REMOTE_DATASET=1" in script
  assert "[Dataset] Reusing existing remote dataset" in script
  assert "sequential_matcher" not in script
  assert "feature_extractor" not in script
  assert "executing_remote_colmap" not in script


def test_existing_dataset_colmap_preflight_is_optional() -> None:
  assert api_server.effective_auto_colmap(True, True) is False
  assert api_server.effective_auto_colmap(True, False) is True
  assert api_server.effective_colmap_preflight_required({
    "check_colmap_required": True,
    "use_existing_remote_dataset": True,
  }) is False
  assert api_server.effective_colmap_preflight_required({
    "check_colmap_required": True,
    "use_existing_remote_dataset": False,
  }) is True


def test_tmux_install_candidates_use_mamba_or_noninteractive_sudo_only() -> None:
  candidates = _tmux_install_candidates()
  assert candidates
  assert candidates[0]["manager"] == "mamba"
  assert candidates[0]["command"] == "mamba install -y -c conda-forge tmux"
  for candidate in candidates:
    command = candidate["command"]
    assert "sudo -S" not in command
    assert "secret" not in command.lower()
    assert "password" not in command.lower()
    if candidate["manager"] != "mamba":
      assert "sudo -n" in command


def test_tmux_cancel_script_kills_session_and_preserves_logs() -> None:
  job_paths = _remote_job_paths("/tmp/web_scan/outputs/session/hac/job/output")
  cancel_script = _build_remote_cancel_script(job_paths, "12345", "wgsc-hac-job")

  assert "tmux kill-session -t" in cancel_script
  assert "echo 130" in cancel_script
  assert "runtime.log" in cancel_script
  assert "rm -rf" not in cancel_script


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


class FakeSftpAttr:
  def __init__(self, filename: str, *, is_dir: bool = False, size: int = 0):
    self.filename = filename
    self.st_size = size
    self.st_mode = stat.S_IFDIR if is_dir else stat.S_IFREG


class FakeSftp:
  def __init__(self) -> None:
    self.files = {
      "/remote/point_cloud.ply": b"new-point-cloud",
      "/remote/nested/meta.json": b"{\"ok\": true}",
    }
    self.get_calls: list[str] = []

  def listdir_attr(self, remote_path: str):
    if remote_path == "/remote":
      return [
        FakeSftpAttr("point_cloud.ply", size=len(self.files["/remote/point_cloud.ply"])),
        FakeSftpAttr("nested", is_dir=True),
      ]
    if remote_path == "/remote/nested":
      return [FakeSftpAttr("meta.json", size=len(self.files["/remote/nested/meta.json"]))]
    return []

  def get(self, remote_item: str, local_item: str, callback=None):
    self.get_calls.append(remote_item)
    payload = self.files[remote_item]
    target = Path(local_item)
    target.write_bytes(payload)
    if callback:
      callback(len(payload), len(payload))


def test_remote_download_uses_temp_file_and_reports_progress() -> None:
  target_dir = Path(api_server.WEB_DIR) / "generated" / "download_tests" / f"download-{uuid.uuid4().hex[:8]}"
  try:
    target_dir.mkdir(parents=True, exist_ok=True)
    stale_file = target_dir / "point_cloud.ply"
    stale_file.write_bytes(b"old")
    progress = []

    result = _download_directory(FakeSftp(), "/remote", target_dir, progress_callback=progress.append)

    assert result["pending"] is False
    assert result["files"] == 2
    assert result["total_files"] == 2
    assert result["skipped_files"] == 0
    assert stale_file.read_bytes() == b"new-point-cloud"
    assert (target_dir / "nested" / "meta.json").read_bytes() == b"{\"ok\": true}"
    assert not list(target_dir.glob("*.wgsc-download"))
    assert progress
    assert progress[0]["pending"] is True
  finally:
    if target_dir.exists():
      shutil.rmtree(target_dir)


def test_remote_download_skips_complete_local_files() -> None:
  target_dir = Path(api_server.WEB_DIR) / "generated" / "download_tests" / f"skip-{uuid.uuid4().hex[:8]}"
  fake = FakeSftp()
  try:
    (target_dir / "nested").mkdir(parents=True, exist_ok=True)
    (target_dir / "point_cloud.ply").write_bytes(fake.files["/remote/point_cloud.ply"])
    (target_dir / "nested" / "meta.json").write_bytes(fake.files["/remote/nested/meta.json"])

    result = _download_directory(fake, "/remote", target_dir, progress_callback=lambda _: None)

    assert result["pending"] is False
    assert result["complete"] is True
    assert result["files"] == 0
    assert result["bytes"] == 0
    assert result["skipped_files"] == 2
    assert fake.get_calls == []
  finally:
    if target_dir.exists():
      shutil.rmtree(target_dir)


def test_result_download_validation_allows_completed_only() -> None:
  base = {
    "remote_detached": True,
    "remote_output_dir": "/remote/output",
    "output_dir": "/local/output",
  }
  assert api_server.validate_completed_result_download_job({**base, "status": "completed"}) == ("/remote/output", "/local/output")

  for status in ("failed", "canceled", "running", "detached"):
    try:
      api_server.validate_completed_result_download_job({**base, "status": status})
    except ValueError as exc:
      assert "Only completed jobs can download results" in str(exc)
    else:
      raise AssertionError(f"status should be rejected: {status}")

  try:
    api_server.validate_completed_result_download_job({
      **base,
      "status": "completed",
      "remote_detached": False,
    })
  except ValueError as exc:
    assert "Only completed remote jobs" in str(exc)
  else:
    raise AssertionError("local completed job should be rejected")


class AliveDownloadThread:
  def is_alive(self) -> bool:
    return True


def test_result_download_repeated_request_returns_already_running() -> None:
  base = {
    "id": f"result-download-{uuid.uuid4().hex[:8]}",
    "status": "completed",
    "remote_detached": True,
    "remote_output_dir": "/remote/output",
    "output_dir": str(Path(api_server.WEB_DIR) / "generated" / "download_tests" / "already-running"),
  }

  active = api_server.start_completed_result_download({**base, "_result_download_thread": AliveDownloadThread()}, {})
  starting = api_server.start_completed_result_download({**base, "_result_download_starting": True}, {})

  assert active["started"] is False
  assert active["already_running"] is True
  assert starting["started"] is False
  assert starting["already_running"] is True


def test_pending_remote_download_hides_partial_artifacts() -> None:
  target_dir = Path(api_server.WEB_DIR) / "generated" / "download_tests" / f"pending-{uuid.uuid4().hex[:8]}"
  try:
    (target_dir / "point_cloud" / "iteration_1").mkdir(parents=True, exist_ok=True)
    (target_dir / "point_cloud" / "iteration_1" / "point_cloud.ply").write_bytes(b"partial")
    job = {
      "id": f"pending-{uuid.uuid4().hex[:8]}",
      "status": "completed",
      "remote_detached": True,
      "remote_result": {"download": {"pending": True, "files": 0, "bytes": 0}},
      "output_dir": str(target_dir),
      "representation": "sh",
    }

    enriched = api_server.enrich_job(job)

    assert "point_cloud_url" not in enriched
    assert api_server.is_remote_download_pending(enriched)
  finally:
    if target_dir.exists():
      shutil.rmtree(target_dir)


def main() -> None:
  test_detached_script_contract()
  test_existing_dataset_disables_auto_colmap_contract()
  test_existing_dataset_colmap_preflight_is_optional()
  test_tmux_install_candidates_use_mamba_or_noninteractive_sudo_only()
  test_tmux_cancel_script_kills_session_and_preserves_logs()
  test_job_persistence_sanitizes_password()
  test_apply_remote_poll_statuses()
  test_remote_download_uses_temp_file_and_reports_progress()
  test_remote_download_skips_complete_local_files()
  test_result_download_validation_allows_completed_only()
  test_result_download_repeated_request_returns_already_running()
  test_pending_remote_download_hides_partial_artifacts()
  print("detached remote tests passed")


if __name__ == "__main__":
  main()
