#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from shutil import which
from typing import Any, Callable, Dict
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT_DIR / "web"
STREAM_DIR = WEB_DIR / "generated" / "streams"
DATASET_DIR = WEB_DIR / "generated" / "datasets"
WORKSPACE_DIR = WEB_DIR / "generated" / "workspaces"
JOB_LOG_DIR = WEB_DIR / "generated" / "job_logs"
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

from web.server.adapter_registry import (
  get_adapter,
  list_adapters,
  supported_operations,
  update_adapter_override,
  validate_adapter,
)
from web.server.remote_executor import (
  RemoteExecutionError,
  build_remote_paths,
  build_remote_tmux_attach_command,
  build_remote_tmux_session_name,
  cancel_remote_detached_job,
  check_remote_output_download,
  download_remote_output_directory,
  poll_remote_detached_job,
  remote_preflight_check,
  sanitize_remote_config,
  sanitize_formatted_command,
  start_remote_algorithm_detached,
  validate_remote_config,
)
from web.tools.export_scene_package import build_scene_package

JOBS: Dict[str, Dict[str, Any]] = {}
JOB_LOG_LOCKS: Dict[str, threading.Lock] = {}
RESULT_DOWNLOAD_LOCK = threading.Lock()
MAX_JOB_HISTORY = 300
MAX_PROCESS_FRAME_COMPLETED_HISTORY = 80
MAX_METRICS_HISTORY = 5000
JOB_STATE_FILE = "job.json"
TERMINAL_STATUSES = {"completed", "failed", "canceled"}
ARTIFACT_RESULT_FIELDS = (
  "manifest_url",
  "viewer_url",
  "point_cloud_url",
  "result_url",
  "result_urls",
  "render_images",
  "render_image_count",
)

MANUAL_ZH_URL = "/web/WEB_TRAINING_MANUAL_ZH.md"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
PLY_EXTENSIONS = {".ply"}
RESULT_SCAN_EXCLUDED_DIRS = {
  ".git",
  "__pycache__",
  "assets",
  "docs",
  "node_modules",
  "submodules",
  "SIBR_viewers",
}
LOCAL_RESULT_PROJECTS = [
  {
    "family": "compgs",
    "label": "CompGS",
    "root": ROOT_DIR / "CompGS-main",
    "representation": "sh",
  },
  {
    "family": "contextgs",
    "label": "ContextGS",
    "root": ROOT_DIR / "ContextGS-main",
    "representation": "sh",
  },
  {
    "family": "fcgs",
    "label": "FCGS",
    "root": ROOT_DIR / "FCGS-main",
    "representation": "sh",
  },
  {
    "family": "hac-plus-plus",
    "label": "HAC++",
    "root": ROOT_DIR / "HAC-plus-main",
    "representation": "sh",
  },
  {
    "family": "megs2",
    "label": "MEGS2",
    "root": ROOT_DIR / "MEGS-2-main",
    "representation": "sg",
  },
  {
    "family": "scaffold-gs",
    "label": "Scaffold-GS",
    "root": ROOT_DIR / "Scaffold-GS-main",
    "representation": "sh",
  },
  {
    "family": "reduced-3dgs",
    "label": "Reduced 3DGS",
    "root": ROOT_DIR / "reduced-3dgs-main",
    "representation": "sh",
  },
]


def extract_job_metrics(text: str) -> Dict[str, Any]:
  import re

  metrics: Dict[str, Any] = {}
  patterns = {
    "fps": [
      r"(?i)\b([0-9]+(?:\.[0-9]+)?)[ \t]*fps\b",
      r"(?i)\bfps[:=]\s*([0-9]+(?:\.[0-9]+)?)\b",
      r"(?i)\bfps\s+([0-9]+(?:\.[0-9]+)?)\b",
    ],
    "iter": [
      r"(?i)\biter(?:ation)?[:=\s]+([0-9]+)\b",
      r"(?i)\b([0-9]+)\s*/\s*[0-9]+\b",
    ],
    "loss": [
      r"(?i)\bloss[:=\s]+([0-9]+(?:\.[0-9]+)?)\b",
    ],
    "psnr": [
      r"(?i)\bpsnr[:=\s]+([0-9]+(?:\.[0-9]+)?)\b",
    ],
    "ssim": [
      r"(?i)\bssim[:=\s]+([0-9]+(?:\.[0-9]+)?)\b",
    ],
    "lpips": [
      r"(?i)\blpips[:=\s]+([0-9]+(?:\.[0-9]+)?)\b",
    ],
  }

  for key, regexes in patterns.items():
    for regex in regexes:
      matches = re.findall(regex, text)
      if matches:
        metrics[key] = matches[-1]
        break
  return metrics


METRICS_CSV_COLUMNS = ["timestamp", "channel", "iter", "loss", "psnr", "ssim", "lpips", "fps"]


def utc_timestamp_text(now: float | None = None) -> str:
  moment = datetime.fromtimestamp(now or time.time(), tz=timezone.utc)
  return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_job_logging(job: Dict[str, Any]) -> None:
  job_id = str(job.get("id", "")).strip()
  if not job_id:
    return

  JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
  job_dir = (JOB_LOG_DIR / job_id).resolve()
  job_dir.mkdir(parents=True, exist_ok=True)

  log_file = job_dir / "runtime.log"
  metrics_csv = job_dir / "metrics.csv"

  if not log_file.exists():
    log_file.write_text("", encoding="utf-8")

  if not metrics_csv.exists():
    with metrics_csv.open("w", newline="", encoding="utf-8") as handle:
      writer = csv.DictWriter(handle, fieldnames=METRICS_CSV_COLUMNS)
      writer.writeheader()

  history = job.get("metrics_history")
  if not isinstance(history, list):
    history = []
  job["metrics_history"] = history[-MAX_METRICS_HISTORY:]

  job["log_dir"] = str(job_dir)
  job["log_file"] = str(log_file)
  job["metrics_csv_file"] = str(metrics_csv)
  job["logs_api_url"] = f"/api/jobs/{job_id}/logs"
  job["logs_download_url"] = f"/api/jobs/{job_id}/logs/download"
  job["metrics_csv_url"] = f"/api/jobs/{job_id}/metrics.csv"

  if job_id not in JOB_LOG_LOCKS:
    JOB_LOG_LOCKS[job_id] = threading.Lock()


def sanitize_job_for_persistence(job: Dict[str, Any]) -> Dict[str, Any]:
  persisted: Dict[str, Any] = {}
  for key, value in job.items():
    if key.startswith("_"):
      continue
    if key in {"log_dir", "log_file", "metrics_csv_file"}:
      continue
    if key == "remote":
      if isinstance(value, dict):
        remote_value = dict(value)
        if "password" in remote_value:
          remote_value = sanitize_remote_config(remote_value)
        else:
          remote_value.pop("password", None)
        persisted[key] = remote_value
      else:
        persisted[key] = value
      continue
    try:
      json.dumps(value)
    except TypeError:
      continue
    persisted[key] = value
  if isinstance(persisted.get("remote"), dict):
    persisted["remote"].pop("password", None)
  return persisted


def persist_job_state(job: Dict[str, Any]) -> None:
  job_id = str(job.get("id", "")).strip()
  if not job_id:
    return
  ensure_job_logging(job)
  job_dir = Path(str(job.get("log_dir", "")))
  if not job_dir:
    return
  payload = sanitize_job_for_persistence(job)
  target = job_dir / JOB_STATE_FILE
  tmp = job_dir / f".{JOB_STATE_FILE}.tmp"
  tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
  tmp.replace(target)


def load_persisted_jobs() -> None:
  if not JOB_LOG_DIR.exists():
    return
  for state_path in sorted(JOB_LOG_DIR.glob(f"*/{JOB_STATE_FILE}")):
    try:
      payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
      continue
    if not isinstance(payload, dict):
      continue
    job_id = str(payload.get("id", "")).strip()
    if not job_id or job_id in JOBS:
      continue
    status = str(payload.get("status", "")).strip().lower()
    if payload.get("remote_detached") and status not in TERMINAL_STATUSES:
      payload["status"] = "detached"
      payload["remote_stage"] = "needs_monitor"
      payload["monitor_state"] = "needs_remote_config"
      payload["safe_to_close_web"] = True
    ensure_job_logging(payload)
    JOBS[job_id] = payload


def append_job_log_line(job: Dict[str, Any], channel: str, line: str) -> None:
  if not line:
    return

  ensure_job_logging(job)
  job_id = str(job.get("id", "")).strip()
  if not job_id:
    return

  target_key = "stdout" if channel == "stdout" else "stderr"
  normalized = line if line.endswith("\n") else f"{line}\n"
  job[target_key] = (job.get(target_key, "") + normalized)[-12000:]

  timestamp = utc_timestamp_text()
  lock = JOB_LOG_LOCKS.setdefault(job_id, threading.Lock())
  log_file_value = str(job.get("log_file", "")).strip()
  if log_file_value:
    log_path = Path(log_file_value)
    with lock:
      with log_path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"[{timestamp}] [{channel.upper()}] {normalized}")

  metrics_update = extract_job_metrics(normalized)
  if not metrics_update:
    return

  job["metrics"] = {
    **job.get("metrics", {}),
    **metrics_update,
  }

  entry = {
    "timestamp": timestamp,
    "channel": channel.upper(),
    "iter": metrics_update.get("iter", ""),
    "loss": metrics_update.get("loss", ""),
    "psnr": metrics_update.get("psnr", ""),
    "ssim": metrics_update.get("ssim", ""),
    "lpips": metrics_update.get("lpips", ""),
    "fps": metrics_update.get("fps", ""),
  }
  history = job.setdefault("metrics_history", [])
  history.append(entry)
  if len(history) > MAX_METRICS_HISTORY:
    del history[: len(history) - MAX_METRICS_HISTORY]

  csv_file_value = str(job.get("metrics_csv_file", "")).strip()
  if csv_file_value:
    csv_path = Path(csv_file_value)
    with lock:
      with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRICS_CSV_COLUMNS)
        writer.writerow(entry)


def read_job_log_tail_lines(job: Dict[str, Any], limit: int) -> list[str]:
  ensure_job_logging(job)
  log_file_value = str(job.get("log_file", "")).strip()
  if not log_file_value:
    return []
  log_file = Path(log_file_value)
  if not log_file.exists():
    return []

  safe_limit = max(1, min(limit, 3000))
  with log_file.open("r", encoding="utf-8", errors="replace") as handle:
    return list(deque(handle, maxlen=safe_limit))


def read_job_log_since_cursor(job: Dict[str, Any], cursor: int, max_bytes: int = 200_000) -> Dict[str, Any]:
  ensure_job_logging(job)
  log_file_value = str(job.get("log_file", "")).strip()
  if not log_file_value:
    return {"cursor": 0, "from_cursor": 0, "lines": [], "truncated": False}

  log_file = Path(log_file_value)
  if not log_file.exists():
    return {"cursor": 0, "from_cursor": 0, "lines": [], "truncated": False}

  file_size = log_file.stat().st_size
  safe_cursor = max(0, int(cursor or 0))
  if safe_cursor > file_size:
    safe_cursor = 0

  read_from = safe_cursor
  truncated = False
  if file_size - read_from > max_bytes:
    read_from = max(0, file_size - max_bytes)
    truncated = True

  with log_file.open("rb") as handle:
    handle.seek(read_from)
    raw = handle.read(max_bytes)

  text = raw.decode("utf-8", errors="replace")
  return {
    "cursor": file_size,
    "from_cursor": read_from,
    "lines": text.splitlines(keepends=True),
    "truncated": truncated,
  }


def build_metrics_page(job: Dict[str, Any], page: int, page_size: int) -> Dict[str, Any]:
  history = list(job.get("metrics_history", []))
  history.reverse()

  safe_page_size = max(1, min(page_size, 200))
  total = len(history)
  total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
  safe_page = max(1, min(page, total_pages))
  start = (safe_page - 1) * safe_page_size
  end = start + safe_page_size

  return {
    "page": safe_page,
    "page_size": safe_page_size,
    "total": total,
    "total_pages": total_pages,
    "rows": history[start:end],
  }


def _normalize_slug(value: str, *, fallback: str) -> str:
  text = str(value or "").strip().lower()
  if not text:
    return fallback
  normalized = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in text)
  while "--" in normalized:
    normalized = normalized.replace("--", "-")
  normalized = normalized.strip("-_")
  return normalized[:48] or fallback


def _generate_capture_id() -> str:
  return f"capture-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


def _resolve_capture_input_dir(session_dir: Path, capture_id: str = "") -> tuple[str, Path]:
  captures_root = session_dir / "captures"
  desired_capture = str(capture_id or "").strip()

  if desired_capture:
    desired_input_dir = (captures_root / desired_capture / "input").resolve()
    if desired_input_dir.exists() and desired_input_dir.is_dir():
      return desired_capture, desired_input_dir
    raise FileNotFoundError(f"Capture input directory does not exist: {desired_input_dir}")

  if captures_root.exists() and captures_root.is_dir():
    candidates = []
    for child in captures_root.iterdir():
      if not child.is_dir():
        continue
      input_dir = child / "input"
      if not input_dir.exists() or not input_dir.is_dir():
        continue
      try:
        score = input_dir.stat().st_mtime
      except OSError:
        score = 0
      candidates.append((score, child.name, input_dir))
    if candidates:
      candidates.sort(key=lambda item: item[0], reverse=True)
      _, selected_capture_id, selected_input_dir = candidates[0]
      return selected_capture_id, selected_input_dir.resolve()

  legacy_input_dir = (session_dir / "input").resolve()
  if legacy_input_dir.exists() and legacy_input_dir.is_dir():
    return "legacy", legacy_input_dir

  raise FileNotFoundError(f"No capture input directory found under session: {session_dir}")


def save_stream_frame(session_id: str, image_data: str, filename: str, capture_id: str = "") -> Dict[str, str]:
  session_dir = STREAM_DIR / session_id
  resolved_capture_id = str(capture_id or "").strip() or _generate_capture_id()
  input_dir = session_dir / "captures" / resolved_capture_id / "input"
  output_dir = session_dir / "output"
  input_dir.mkdir(parents=True, exist_ok=True)
  output_dir.mkdir(parents=True, exist_ok=True)

  if "," in image_data:
    _, encoded = image_data.split(",", 1)
  else:
    encoded = image_data
  binary = base64.b64decode(encoded)

  input_path = input_dir / filename
  input_path.write_bytes(binary)

  # Default fallback preview: mirror the latest input frame until an algorithm writes output.
  mirrored_output = output_dir / "latest.png"
  mirrored_output.write_bytes(binary)

  return {
    "capture_id": resolved_capture_id,
    "capture_input_dir": str(input_dir.resolve()),
    "input_path": str(input_path.resolve()),
    "output_path": str(mirrored_output.resolve()),
    "input_url": "/" + str(input_path.relative_to(ROOT_DIR)).replace("\\", "/"),
    "output_url": "/" + str(mirrored_output.relative_to(ROOT_DIR)).replace("\\", "/"),
  }


def materialize_stream_session(
  session_id: str,
  title: str | None = None,
  *,
  capture_id: str = "",
  dataset_name: str = "",
) -> Dict[str, Any]:
  session_dir = (STREAM_DIR / session_id).resolve()
  resolved_capture_id, input_dir = _resolve_capture_input_dir(session_dir, capture_id)

  frame_paths = sorted([path for path in input_dir.iterdir() if path.is_file()])
  if not frame_paths:
    raise FileNotFoundError(f"No captured frames found in: {input_dir}")

  resolved_dataset_name = str(dataset_name or "").strip() or title or f"capture-{session_id}"
  dataset_slug = _normalize_slug(resolved_dataset_name, fallback="dataset")
  dataset_id = f"{dataset_slug}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

  dataset_root = (DATASET_DIR / session_id / "datasets" / dataset_id).resolve()
  images_dir = dataset_root / "images"
  input_copy_dir = dataset_root / "input"
  images_dir.mkdir(parents=True, exist_ok=True)
  input_copy_dir.mkdir(parents=True, exist_ok=True)

  copied_frames: list[str] = []
  for index, frame_path in enumerate(frame_paths, start=1):
    suffix = frame_path.suffix.lower() or ".png"
    target_name = f"{index:05d}{suffix}"
    images_target = images_dir / target_name
    input_target = input_copy_dir / target_name
    shutil.copyfile(frame_path, images_target)
    shutil.copyfile(frame_path, input_target)
    copied_frames.append("/" + str(images_target.relative_to(ROOT_DIR)).replace("\\", "/"))

  dataset_manifest = {
    "version": "0.1.0",
    "session_id": session_id,
    "capture_id": resolved_capture_id,
    "dataset_id": dataset_id,
    "dataset_name": resolved_dataset_name,
    "title": title or f"capture-{session_id}",
    "frame_count": len(frame_paths),
    "dataset_root": str(dataset_root),
    "capture_input_dir": str(input_dir),
    "images_dir": str(images_dir),
    "input_dir": str(input_copy_dir),
    "source_hint": "This is a multi-frame capture workspace. Current local Gaussian repos still require COLMAP/Blender scene conversion before training.",
    "generated_at": time.time(),
    "frames": copied_frames,
  }
  manifest_path = dataset_root / "capture_session.json"
  manifest_path.write_text(json.dumps(dataset_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

  return {
    "session_id": session_id,
    "capture_id": resolved_capture_id,
    "dataset_id": dataset_id,
    "dataset_name": resolved_dataset_name,
    "frame_count": len(frame_paths),
    "dataset_root": str(dataset_root),
    "images_dir": str(images_dir),
    "input_dir": str(input_copy_dir),
    "manifest_path": str(manifest_path),
    "manifest_url": "/" + str(manifest_path.relative_to(ROOT_DIR)).replace("\\", "/"),
    "source_hint": dataset_manifest["source_hint"],
  }


def prepare_colmap_workspace(
  session_id: str,
  family: str,
  repo_path: str | None = None,
  *,
  capture_id: str = "",
  dataset_name: str = "",
) -> Dict[str, Any]:
  dataset_info = materialize_stream_session(
    session_id,
    session_id,
    capture_id=capture_id,
    dataset_name=dataset_name,
  )
  dataset_root = Path(dataset_info["dataset_root"]).resolve()
  dataset_id = str(dataset_info.get("dataset_id", "dataset")).strip() or "dataset"
  workspace_root = (WORKSPACE_DIR / session_id / family / dataset_id).resolve()
  input_dir = workspace_root / "input"
  images_dir = workspace_root / "images"
  sparse_dir = workspace_root / "sparse" / "0"
  distorted_sparse_dir = workspace_root / "distorted" / "sparse"
  input_dir.mkdir(parents=True, exist_ok=True)
  images_dir.mkdir(parents=True, exist_ok=True)
  sparse_dir.mkdir(parents=True, exist_ok=True)
  distorted_sparse_dir.mkdir(parents=True, exist_ok=True)

  copied_frames: list[str] = []
  for image_path in sorted((dataset_root / "images").iterdir()):
    if not image_path.is_file():
      continue
    input_target = input_dir / image_path.name
    images_target = images_dir / image_path.name
    shutil.copyfile(image_path, input_target)
    shutil.copyfile(image_path, images_target)
    copied_frames.append(str(input_target))

  resolved_repo = resolve_workspace_path(repo_path)
  repo_root = Path(resolved_repo) if resolved_repo else None
  convert_script = repo_root / "convert.py" if repo_root else None
  if convert_script and convert_script.exists():
    suggested_command = f"python {convert_script} -s {workspace_root}"
  else:
    database_path = workspace_root / "distorted" / "database.db"
    distorted_sparse_path = workspace_root / "distorted" / "sparse"
    distorted_sparse_0 = distorted_sparse_path / "0"
    sparse_root = workspace_root / "sparse"
    sparse_0 = sparse_root / "0"
    marker_path = workspace_root / ".wgsc_colmap_undistorted.ok"

    colmap_prepare_script = (
      "OMP_NUM_THREADS_VALUE=\"${OMP_NUM_THREADS:-1}\""
      " && case \"$OMP_NUM_THREADS_VALUE\" in \"\"|*[!0-9]*|0) OMP_NUM_THREADS_VALUE=1 ;; esac"
      " && export OMP_NUM_THREADS=\"$OMP_NUM_THREADS_VALUE\""
      " && export QT_QPA_PLATFORM=xcb"
      " && if command -v vglrun >/dev/null 2>&1; then colmap_headless() { vglrun \"$@\"; }; else colmap_headless() { \"$@\"; }; fi"
      " && command -v colmap >/dev/null 2>&1"
      f" && rm -f {shlex.quote(str(marker_path))} {shlex.quote(str(database_path))}"
      f" && mkdir -p {shlex.quote(str(distorted_sparse_path))} {shlex.quote(str(sparse_root))}"
      f" && colmap_headless colmap feature_extractor --database_path {shlex.quote(str(database_path))} --image_path {shlex.quote(str(input_dir))} "
      "--ImageReader.single_camera 1 --ImageReader.camera_model SIMPLE_PINHOLE"
      f" && colmap_headless colmap sequential_matcher --database_path {shlex.quote(str(database_path))}"
      f" && colmap_headless colmap mapper --database_path {shlex.quote(str(database_path))} --image_path {shlex.quote(str(input_dir))} --output_path {shlex.quote(str(distorted_sparse_path))}"
      f" && rm -rf {shlex.quote(str(images_dir))} {shlex.quote(str(sparse_root))}"
      f" && mkdir -p {shlex.quote(str(images_dir))} {shlex.quote(str(sparse_root))} {shlex.quote(str(sparse_0))}"
      f" && colmap_headless colmap image_undistorter --image_path {shlex.quote(str(input_dir))} --input_path {shlex.quote(str(distorted_sparse_0))} --output_path {shlex.quote(str(workspace_root))} --output_type COLMAP"
      f" && if [ -d {shlex.quote(str(sparse_root))} ]; then find {shlex.quote(str(sparse_root))} -maxdepth 1 -type f -exec mv -f {{}} {shlex.quote(str(sparse_0))} \\; ; fi"
      f" && touch {shlex.quote(str(marker_path))}"
    )
    suggested_command = f'xvfb-run -a -s "-screen 0 1280x1024x24" bash -lc {shlex.quote(colmap_prepare_script)}'

  manifest = {
    "version": "0.1.0",
    "session_id": session_id,
    "family": family,
    "workspace_root": str(workspace_root),
    "input_dir": str(input_dir),
    "images_dir": str(images_dir),
    "sparse_dir": str(sparse_dir),
    "distorted_sparse_dir": str(distorted_sparse_dir),
    "frame_count": len(copied_frames),
    "suggested_command": suggested_command,
    "generated_at": time.time(),
  }
  manifest_path = workspace_root / "workspace_manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
  run_script = workspace_root / "run_colmap_prepare.sh"
  run_script.write_text("#!/usr/bin/env bash\n" + suggested_command + "\n", encoding="utf-8")

  return {
    "session_id": session_id,
    "capture_id": dataset_info.get("capture_id", ""),
    "dataset_id": dataset_info.get("dataset_id", ""),
    "dataset_name": dataset_info.get("dataset_name", ""),
    "family": family,
    "workspace_root": str(workspace_root),
    "input_dir": str(input_dir),
    "images_dir": str(images_dir),
    "sparse_dir": str(sparse_dir),
    "manifest_path": str(manifest_path),
    "manifest_url": "/" + str(manifest_path.relative_to(ROOT_DIR)).replace("\\", "/"),
    "suggested_command": suggested_command,
    "run_script": str(run_script),
    "frame_count": len(copied_frames),
  }


def format_operation_command(
  adapter: Dict[str, Any],
  operation: str,
  *,
  input_path: str = "",
  output_dir: str = "",
  workspace: str = "",
  checkpoint_path: str = "",
  repo_path: str = "",
  training_args: Dict[str, Any] | None = None,
) -> str | None:
  operation_config = adapter.get("operations", {}).get(operation, {})
  command_template = operation_config.get("template")
  if not operation_config.get("enabled") or not command_template:
    return None
  format_args = {
    "input_path": input_path,
    "output_dir": output_dir,
    "workspace": workspace,
    "checkpoint_path": checkpoint_path,
    "repo_path": repo_path or adapter.get("repo_path", ""),
    "source": input_path or workspace,
    **(training_args or {}),
  }
  return command_template.format(**format_args)


def resolve_workspace_path(path_value: str | None) -> str:
  if not path_value:
    return ""
  raw = str(path_value).strip().strip('"').strip("'")
  if not raw:
    return ""

  candidate = Path(raw)
  if candidate.is_absolute():
    return str(candidate.resolve())

  # Prefer web-relative resolution first because existing adapter JSON uses paths like ../MEGS-2-main.
  web_relative = (WEB_DIR / raw).resolve()
  root_relative = (ROOT_DIR / raw).resolve()
  if web_relative.exists():
    return str(web_relative)
  if root_relative.exists():
    return str(root_relative)
  return str(web_relative)


def resolve_project_path(path_value: str | None) -> str:
  if not path_value:
    return ""
  raw = str(path_value).strip().strip('"').strip("'")
  if not raw:
    return ""

  if raw.startswith("/web/"):
    return str((ROOT_DIR / raw.lstrip("/")).resolve())
  if raw.startswith("web/"):
    return str((ROOT_DIR / raw).resolve())

  return resolve_workspace_path(raw)


def default_run_output_dir(session_id: str, family: str) -> str:
  return str((WEB_DIR / "generated" / "runs" / session_id / family).resolve())


def strip_empty_repo_path_flag(command: str, repo_path: str) -> str:
  if repo_path:
    return command
  cleaned = command
  for needle in (' --repo-path ""', " --repo-path ''", " --repo-path"):
    cleaned = cleaned.replace(needle, "")
  return cleaned.strip()


def adapter_requirement_spec(adapter: Dict[str, Any]) -> Dict[str, Any]:
  requirements = adapter.get("requirements", {}) or {}
  python_modules = [
    str(name).strip()
    for name in requirements.get("python_modules", [])
    if str(name).strip()
  ]
  install_commands = requirements.get("install_commands", {}) or {}

  if adapter.get("family") == "gaussian-splatting-lightning":
    if not python_modules:
      python_modules = [
        "torch",
        "lightning",
        "jsonargparse",
        "wandb",
        "viser",
        "plyfile",
        "diff_gaussian_rasterization",
        "simple_knn",
      ]
    if not install_commands:
      install_commands = {
        "cuda121": [
          "python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121",
          "python -m pip install lightning",
          "python -m pip install jsonargparse",
          "python -m pip install wandb plyfile==0.8.1 viser==0.2.3",
          "python -m pip install --no-build-isolation git+https://github.com/graphdeco-inria/diff-gaussian-rasterization.git@59f5f77e3ddbac3ed9db93ec2cfe99ed6c5d121d",
          "python -m pip install --no-build-isolation git+https://github.com/yzslab/simple-knn.git@44f764299fa305faf6ec5ebd99939e0508331503",
        ],
        "cpu": [
          "python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu",
          "python -m pip install lightning",
          "python -m pip install jsonargparse",
          "python -m pip install wandb plyfile==0.8.1 viser==0.2.3",
        ],
      }

  return {
    "python_modules": python_modules,
    "install_commands": install_commands,
  }


def find_missing_python_modules(module_names: list[str]) -> list[str]:
  missing: list[str] = []
  for module_name in module_names:
    if not module_name:
      continue
    try:
      if importlib.util.find_spec(module_name) is None:
        missing.append(module_name)
    except Exception:
      missing.append(module_name)
  return missing


def missing_template_fields(command_template: str, format_args: Dict[str, Any]) -> list[str]:
  required_keys = ("workspace", "input_path", "output_dir", "checkpoint_path", "source")
  missing: list[str] = []
  for key in required_keys:
    if f"{{{key}}}" in command_template and not str(format_args.get(key, "")).strip():
      missing.append(key)
  return missing


def extract_missing_module_from_stderr(stderr_text: str) -> str:
  import re

  match = re.search(r"ModuleNotFoundError:\\s+No module named ['\"]([^'\"]+)['\"]", stderr_text or "")
  return match.group(1) if match else ""


def build_dependency_hint(adapter: Dict[str, Any], missing_module: str) -> str:
  requirement_spec = adapter_requirement_spec(adapter)
  install_commands = requirement_spec.get("install_commands", {})

  lines = [
    f"[DependencyHint] Missing module: {missing_module}",
    f"[DependencyHint] Python executable: {sys.executable}",
  ]

  cuda121_commands = install_commands.get("cuda121", [])
  cpu_commands = install_commands.get("cpu", [])
  if cuda121_commands:
    lines.append("[DependencyHint] Install commands (CUDA 12.1):")
    lines.extend(f"  {command}" for command in cuda121_commands)
  if cpu_commands:
    lines.append("[DependencyHint] Install commands (CPU-only):")
    lines.extend(f"  {command}" for command in cpu_commands)

  if missing_module in {"diff_gaussian_rasterization", "simple_knn"}:
    cuda_toolkit = detect_cuda_toolkit()
    lines.append("[DependencyHint] This module is a CUDA extension and requires CUDA Toolkit (nvcc).")
    lines.append(f"[DependencyHint] CUDA_HOME: {cuda_toolkit.get('cuda_home') or '(not set)'}")
    lines.append(f"[DependencyHint] nvcc: {cuda_toolkit.get('nvcc_path') or '(not found)'}")

  return "\n".join(lines)


def detect_cuda_toolkit() -> Dict[str, Any]:
  cuda_home = os.environ.get("CUDA_HOME") or os.environ.get("CUDA_PATH") or ""
  nvcc_path = which("nvcc") or ""

  if cuda_home:
    try:
      cuda_home = str(Path(cuda_home).resolve())
    except Exception:
      cuda_home = str(cuda_home)

  if cuda_home and not nvcc_path:
    nvcc_candidate = Path(cuda_home) / "bin" / ("nvcc.exe" if os.name == "nt" else "nvcc")
    if nvcc_candidate.exists():
      nvcc_path = str(nvcc_candidate.resolve())

  if not cuda_home and os.name == "nt":
    for candidate in (
      Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1"),
      Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4"),
      Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8"),
    ):
      if candidate.exists():
        cuda_home = str(candidate.resolve())
        if not nvcc_path:
          nvcc_candidate = candidate / "bin" / "nvcc.exe"
          if nvcc_candidate.exists():
            nvcc_path = str(nvcc_candidate.resolve())
        break

  cuda_home_exists = bool(cuda_home and Path(cuda_home).exists())
  toolkit_ready = bool(cuda_home_exists and nvcc_path)
  return {
    "cuda_home": cuda_home,
    "cuda_home_exists": cuda_home_exists,
    "nvcc_path": nvcc_path,
    "toolkit_ready": toolkit_ready,
  }


def _write_probe(path: Path) -> tuple[bool, str]:
  probe = path / f".wgsc_write_probe_{uuid.uuid4().hex}"
  try:
    path.mkdir(parents=True, exist_ok=True)
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)
    return True, ""
  except Exception as exc:
    return False, str(exc)


def _runtime_check_item(name: str, ok: bool, *, required: bool, message: str, hint: str = "", details: Dict[str, Any] | None = None) -> Dict[str, Any]:
  return {
    "name": name,
    "ok": ok,
    "required": required,
    "message": message,
    "hint": hint,
    "details": details or {},
  }


def _python_probe(script: str, timeout: int = 15) -> Dict[str, Any]:
  try:
    result = subprocess.run(
      [sys.executable, "-c", script],
      cwd=str(ROOT_DIR),
      capture_output=True,
      text=True,
      timeout=timeout,
      check=False,
    )
  except Exception as exc:
    return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": -1}
  return {
    "ok": result.returncode == 0,
    "stdout": result.stdout.strip(),
    "stderr": result.stderr.strip(),
    "returncode": result.returncode,
  }


ALGORITHM_CUDA_CHECK_SPECS: Dict[str, Dict[str, Any]] = {
  "contextgs": {
    "label": "ContextGS",
    "root": ROOT_DIR / "ContextGS-main",
    "env_name": "contextgs",
    "required_modules": [
      ("torchvision", "torchvision"),
      ("diff_gaussian_rasterization", "diff_gaussian_rasterization"),
      ("simple_knn", "simple_knn"),
      ("torch_scatter", "torch_scatter"),
      ("compressai", "compressai"),
      ("torchac", "torchac"),
      ("lpips", "lpips"),
      ("plyfile", "plyfile"),
      ("einops", "einops"),
      ("cv2", "opencv-python"),
    ],
  },
  "reduced-3dgs": {
    "label": "Reduced-3DGS",
    "root": ROOT_DIR / "reduced-3dgs-main",
    "env_name": "gaussian_splatting",
    "required_modules": [
      ("torchvision", "torchvision"),
      ("diff_gaussian_rasterization", "diff_gaussian_rasterization"),
      ("simple_knn", "simple_knn"),
      ("pandas", "pandas"),
      ("plyfile", "plyfile"),
      ("PIL", "pillow"),
      ("tqdm", "tqdm"),
    ],
  },
}


def _algorithm_cuda_environment_checks(family_key: str) -> tuple[list[Dict[str, Any]], list[str], Dict[str, Any]]:
  checks: list[Dict[str, Any]] = []
  warnings: list[str] = []
  metadata: Dict[str, Any] = {}
  spec = ALGORITHM_CUDA_CHECK_SPECS[family_key]
  label = str(spec["label"])
  check_prefix = family_key.replace("-", "_")
  repo_root = spec["root"]
  env_name = str(spec["env_name"])
  required_modules = spec["required_modules"]

  repo_ok = repo_root.exists()
  checks.append(_runtime_check_item(
    f"{check_prefix}_repo",
    repo_ok,
    required=True,
    message=f"{label} repository exists." if repo_ok else f"Missing {repo_root.name} repository.",
    hint=f"Place {repo_root.name} next to web/ or update the adapter repo path.",
    details={"path": str(repo_root)},
  ))

  python_ok = sys.version_info[:2] == (3, 10)
  checks.append(_runtime_check_item(
    f"{check_prefix}_python310",
    python_ok,
    required=True,
    message=f"Python {sys.version_info.major}.{sys.version_info.minor} is active." if python_ok else f"Expected Python 3.10, got {sys.version.split()[0]}.",
    hint=f"Activate the {env_name} conda environment before launching the API server.",
    details={"python_executable": sys.executable, "version": sys.version.split()[0]},
  ))

  torch_probe = _python_probe(
    "import json, torch; "
    "info={'torch_version': torch.__version__, 'cuda_version': torch.version.cuda, "
    "'cuda_available': torch.cuda.is_available(), 'device_count': torch.cuda.device_count(), "
    "'device_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else '', "
    "'capability': torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None}; "
    "print(json.dumps(info))"
  )
  torch_info: Dict[str, Any] = {}
  if torch_probe["ok"]:
    try:
      torch_info = json.loads(torch_probe["stdout"] or "{}")
    except Exception:
      torch_info = {}
  metadata["torch"] = torch_info

  torch_version = str(torch_info.get("torch_version", ""))
  torch_ok = torch_probe["ok"] and torch_version.startswith("2.2")
  checks.append(_runtime_check_item(
    f"{check_prefix}_torch22",
    torch_ok,
    required=True,
    message=f"PyTorch {torch_version} is active." if torch_ok else f"Expected PyTorch 2.2.x for {label}.",
    hint=f"Install PyTorch 2.2.2 with pytorch-cuda=12.1 in the {env_name} environment.",
    details={"probe": torch_probe, "torch": torch_info},
  ))

  cuda_version = str(torch_info.get("cuda_version", "") or "")
  cuda_ok = torch_probe["ok"] and cuda_version.startswith("12.1")
  checks.append(_runtime_check_item(
    f"{check_prefix}_cuda121",
    cuda_ok,
    required=True,
    message=f"PyTorch CUDA runtime is {cuda_version}." if cuda_ok else f"Expected torch.version.cuda to be 12.1, got {cuda_version or 'unavailable'}.",
    hint="Reinstall PyTorch with `pytorch-cuda=12.1`.",
    details={"cuda_version": cuda_version},
  ))

  cuda_available = bool(torch_info.get("cuda_available"))
  checks.append(_runtime_check_item(
    f"{check_prefix}_cuda_available",
    cuda_available,
    required=True,
    message="CUDA is available to PyTorch." if cuda_available else "PyTorch cannot access CUDA.",
    hint="Check NVIDIA driver, nvidia-smi, CUDA_VISIBLE_DEVICES, and conda environment activation.",
    details={"torch": torch_info},
  ))

  device_name = str(torch_info.get("device_name", "") or "")
  rtx4090_ok = cuda_available and "4090" in device_name
  checks.append(_runtime_check_item(
    f"{check_prefix}_rtx4090",
    rtx4090_ok,
    required=True,
    message=f"First CUDA device is {device_name}." if rtx4090_ok else f"Expected RTX 4090, got {device_name or 'no CUDA device'}.",
    hint=f"Run {label} on the remote Linux RTX 4090 host, or set CUDA_VISIBLE_DEVICES to the 4090.",
    details={"device_name": device_name, "capability": torch_info.get("capability")},
  ))

  toolkit = detect_cuda_toolkit()
  checks.append(_runtime_check_item(
    f"{check_prefix}_cuda_toolkit",
    bool(toolkit.get("toolkit_ready")),
    required=True,
    message="CUDA Toolkit and nvcc are available." if toolkit.get("toolkit_ready") else "CUDA Toolkit or nvcc was not found.",
    hint=f"Install CUDA Toolkit 12.1 and set CUDA_HOME before rebuilding {label} CUDA extensions.",
    details=toolkit,
  ))

  missing_modules: list[str] = []
  if not torch_probe["ok"]:
    missing_modules.append("torch")
  for module_name, package_name in required_modules:
    probe = _python_probe(f"import {module_name}")
    if not probe["ok"]:
      missing_modules.append(module_name)
    checks.append(_runtime_check_item(
      f"{check_prefix}_module_{module_name}",
      probe["ok"],
      required=True,
      message=f"Python module {module_name} imports successfully." if probe["ok"] else f"Missing or broken Python module {module_name}.",
      hint=f"Install/rebuild {package_name} in the {env_name} environment.",
      details={"probe": probe},
    ))

  if missing_modules:
    warnings.append(f"{label} missing modules: " + ", ".join(missing_modules))

  metadata["missing_python_modules"] = missing_modules
  metadata["python_modules"] = ["torch"] + [name for name, _package in required_modules]
  return checks, warnings, metadata


def environment_check(family: str | None = None) -> Dict[str, Any]:
  checks: list[Dict[str, Any]] = []
  warnings: list[str] = []

  web_index = WEB_DIR / "index.html"
  viewer_sh = WEB_DIR / "viewers" / "sh.html"
  viewer_sg = WEB_DIR / "viewers" / "sg.html"
  generated_dir = WEB_DIR / "generated"

  checks.append(_runtime_check_item(
    "api_runtime",
    True,
    required=True,
    message="API service runtime is active.",
    details={"python_executable": sys.executable},
  ))

  web_index_ok = web_index.exists()
  checks.append(_runtime_check_item(
    "web_index",
    web_index_ok,
    required=True,
    message="Web index page exists." if web_index_ok else "Missing web/index.html.",
    hint="Ensure the web assets are present under /web.",
    details={"path": str(web_index)},
  ))

  viewer_assets_ok = viewer_sh.exists() and viewer_sg.exists()
  checks.append(_runtime_check_item(
    "viewer_assets",
    viewer_assets_ok,
    required=True,
    message="Viewer pages are available." if viewer_assets_ok else "Missing viewer pages (sh.html/sg.html).",
    hint="Check /web/viewers/sh.html and /web/viewers/sg.html.",
    details={"sh": str(viewer_sh), "sg": str(viewer_sg)},
  ))

  generated_writable, generated_error = _write_probe(generated_dir)
  checks.append(_runtime_check_item(
    "generated_dir_writable",
    generated_writable,
    required=True,
    message="web/generated is writable." if generated_writable else "web/generated is not writable.",
    hint="Grant write permission to web/generated for runtime artifacts.",
    details={"path": str(generated_dir), "error": generated_error},
  ))

  python3_path = which("python3")
  python3_ok = bool(python3_path)
  checks.append(_runtime_check_item(
    "python3_command",
    python3_ok,
    required=False,
    message="python3 command is available." if python3_ok else "python3 command was not found in PATH.",
    hint="Install python3 or adjust PATH when using shell helpers.",
    details={"path": python3_path or ""},
  ))
  if not python3_ok:
    warnings.append("python3 is not in PATH; some shell-based operations may fail.")

  paramiko_available = importlib.util.find_spec("paramiko") is not None
  checks.append(_runtime_check_item(
    "paramiko_dependency",
    paramiko_available,
    required=False,
    message="paramiko is installed." if paramiko_available else "paramiko is not installed.",
    hint="Install with `python -m pip install paramiko` before remote SSH checks.",
  ))
  if not paramiko_available:
    warnings.append("Remote SSH features are unavailable until paramiko is installed.")

  family_key = (family or "").strip().lower()
  algorithm_metadata: Dict[str, Any] = {}
  cuda_check_spec = ALGORITHM_CUDA_CHECK_SPECS.get(family_key)
  algorithm_label = str(cuda_check_spec.get("label", family_key)) if cuda_check_spec else family_key
  if cuda_check_spec:
    algorithm_checks, algorithm_warnings, algorithm_metadata = _algorithm_cuda_environment_checks(family_key)
    checks.extend(algorithm_checks)
    warnings.extend(algorithm_warnings)

  required_checks_ok = all(item["ok"] for item in checks if item["required"])
  web_required_names = {"api_runtime", "web_index", "viewer_assets", "generated_dir_writable"}
  web_required_ok = all(item["ok"] for item in checks if item["required"] and item["name"] in web_required_names)
  runtime_ready = web_required_ok
  algorithm_ready = required_checks_ok
  remote_ready = runtime_ready and paramiko_available

  summary = "Web runtime checks passed."
  if not runtime_ready:
    summary = "Web runtime checks failed. Fix required items before continuing."
  elif cuda_check_spec and not algorithm_ready:
    summary = f"Web runtime is ready, but {algorithm_label} Python/CUDA checks failed."
  elif not remote_ready:
    summary = "Web runtime is ready, but remote SSH checks require paramiko."
  elif cuda_check_spec:
    summary = f"Web runtime and {algorithm_label} Python/CUDA checks passed."

  adapter = get_adapter(family_key) if family_key else None
  requirement_spec = adapter_requirement_spec(adapter) if adapter else {"python_modules": [], "install_commands": {}}

  return {
    "family": family or "",
    "runtime_ready": runtime_ready,
    "algorithm_ready": algorithm_ready,
    "remote_ready": remote_ready,
    "checks": checks,
    "warnings": warnings,
    "summary": summary,
    # Backward-compatible fields used by previous UI versions.
    "web_runnable": runtime_ready,
    "pipeline_ready": algorithm_ready,
    "repo_exists": True,
    "gpu_visible": bool(which("nvidia-smi")),
    "python_executable": sys.executable,
    "python_modules": algorithm_metadata.get("python_modules", requirement_spec.get("python_modules", [])),
    "missing_python_modules": algorithm_metadata.get("missing_python_modules", []),
    "install_commands": requirement_spec.get("install_commands", {}),
    "cuda_toolkit": detect_cuda_toolkit(),
    "commands": {
      "python3": {"found": python3_ok, "path": python3_path},
      "paramiko": {"found": paramiko_available, "path": "python module" if paramiko_available else ""},
      "nvidia-smi": {"found": bool(which("nvidia-smi")), "path": which("nvidia-smi")},
    },
    "scripts": {
      "index.html": {"exists": web_index_ok, "path": str(web_index)},
      "viewers/sh.html": {"exists": viewer_sh.exists(), "path": str(viewer_sh)},
      "viewers/sg.html": {"exists": viewer_sg.exists(), "path": str(viewer_sg)},
    },
  }


def build_capture_pipeline(
  session_id: str,
  family: str,
  *,
  output_dir: str,
  repo_path: str = "",
  checkpoint_path: str = "",
  training_args: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
  adapter = get_adapter(family)
  if not adapter:
    raise ValueError(f"Unknown algorithm family: {family}")

  resolved_repo = resolve_workspace_path(repo_path or adapter.get("repo_path", ""))
  workspace_result = prepare_colmap_workspace(session_id, family, resolved_repo)
  workspace_root = workspace_result["workspace_root"]
  resolved_output_dir = output_dir or str((WEB_DIR / "generated" / "runs" / session_id / family).resolve())

  commands: list[dict[str, str]] = []
  convert_command = workspace_result.get("suggested_command")
  if convert_command:
    commands.append({"name": "prepare_colmap", "command": convert_command})

  for operation in ("train", "render"):
    command = format_operation_command(
      adapter,
      operation,
      input_path=workspace_result["input_dir"],
      output_dir=resolved_output_dir,
      workspace=workspace_root,
      checkpoint_path=checkpoint_path,
      repo_path=resolved_repo,
      training_args=training_args,
    )
    if command:
      commands.append({"name": operation, "command": command})

  resolved_cwd = resolve_workspace_path(adapter.get("default_cwd") or resolved_repo)
  requires_repo_main = any("python main.py" in item["command"] for item in commands)
  if requires_repo_main and not resolved_cwd:
    raise ValueError(
      f"{family} capture pipeline requires repo_path/default_cwd because train/render use 'python main.py'."
    )

  pipeline_script = Path(workspace_root) / "run_capture_pipeline.sh"
  script_lines = ["#!/usr/bin/env bash", "set -e"]
  script_lines.extend(item["command"] for item in commands)
  pipeline_script.write_text("\n".join(script_lines) + "\n", encoding="utf-8")

  pipeline_script_cmd = Path(workspace_root) / "run_capture_pipeline.cmd"
  cmd_lines = ["@echo off", "setlocal"]
  for item in commands:
    cmd_lines.append(item["command"])
    cmd_lines.append("if errorlevel 1 exit /b %errorlevel%")
  cmd_lines.append("exit /b 0")
  pipeline_script_cmd.write_text("\r\n".join(cmd_lines) + "\r\n", encoding="utf-8")

  return {
    "session_id": session_id,
    "family": family,
    "workspace": workspace_result,
    "output_dir": resolved_output_dir,
    "repo_path": resolved_repo,
    "checkpoint_path": checkpoint_path,
    "commands": commands,
    "script_path": str(pipeline_script),
    "script_path_cmd": str(pipeline_script_cmd),
  }


def build_viewer_url(relative_url: str, representation: str | None = None) -> str:
  renderer = "sg" if (representation or "").lower() == "sg" else "sh"
  return f"/web/viewers/{renderer}.html?url={relative_url}"


def path_is_inside(path: Path, parent: Path) -> bool:
  try:
    path.resolve().relative_to(parent.resolve())
    return True
  except ValueError:
    return False


def file_url_for_path(path: Path, cache_group: str = "files") -> str:
  resolved = path.resolve()
  if path_is_inside(resolved, ROOT_DIR):
    return "/" + str(resolved.relative_to(ROOT_DIR)).replace("\\", "/")

  cache_dir = WEB_DIR / "generated" / "result_cache" / cache_group
  cache_dir.mkdir(parents=True, exist_ok=True)
  stat = resolved.stat()
  suffix = resolved.suffix.lower()
  digest = uuid.uuid5(
    uuid.NAMESPACE_URL,
    f"{resolved}:{stat.st_mtime_ns}:{stat.st_size}",
  ).hex[:12]
  cache_path = cache_dir / f"{resolved.stem}_{digest}{suffix}"
  if not cache_path.exists():
    shutil.copy2(resolved, cache_path)
  return "/" + str(cache_path.relative_to(ROOT_DIR)).replace("\\", "/")


def safe_generated_child(root: Path, *parts: str) -> Path:
  root_resolved = root.resolve()
  candidate = root_resolved
  for part in parts:
    raw = str(part or "").strip()
    if not raw:
      continue
    candidate = candidate / raw
  candidate = candidate.resolve()
  if root_resolved == candidate or root_resolved not in candidate.parents:
    raise ValueError(f"Unsafe generated path: {candidate}")
  return candidate


def image_file_paths(directory: Path) -> list[Path]:
  if not directory.exists() or not directory.is_dir():
    return []
  files = [
    path
    for path in directory.iterdir()
    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
  ]
  return sorted(files, key=lambda path: (path.stat().st_mtime, path.name))


def file_brief(path: Path) -> Dict[str, Any]:
  stat = path.stat()
  return {
    "name": path.name,
    "path": str(path.resolve()),
    "url": file_url_for_path(path),
    "size": stat.st_size,
    "mtime": stat.st_mtime,
  }


def read_json_if_present(path: Path) -> Dict[str, Any]:
  if not path.exists() or not path.is_file():
    return {}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def inspect_flow_data(session_id: str, capture_id: str = "", family: str = "") -> Dict[str, Any]:
  resolved_session = str(session_id or "").strip()
  resolved_capture = str(capture_id or "").strip()
  resolved_family = str(family or "").strip()
  if not resolved_session:
    raise ValueError("session_id is required")

  stream_session_dir = safe_generated_child(STREAM_DIR, resolved_session)
  dataset_session_dir = safe_generated_child(DATASET_DIR, resolved_session)
  workspace_session_dir = safe_generated_child(WORKSPACE_DIR, resolved_session)

  captures_root = stream_session_dir / "captures"
  captures: list[Dict[str, Any]] = []
  if captures_root.exists() and captures_root.is_dir():
    for child in sorted(captures_root.iterdir(), key=lambda item: item.name):
      if not child.is_dir():
        continue
      input_dir = child / "input"
      frames = image_file_paths(input_dir)
      latest_frame = file_brief(frames[-1]) if frames else None
      captures.append({
        "capture_id": child.name,
        "input_dir": str(input_dir.resolve()),
        "frame_count": len(frames),
        "latest_frame": latest_frame,
        "frames": [file_brief(path) for path in frames[-12:]],
        "mtime": max((path.stat().st_mtime for path in frames), default=child.stat().st_mtime),
      })

  selected_capture = None
  if resolved_capture:
    selected_capture = next((item for item in captures if item["capture_id"] == resolved_capture), None)
  if selected_capture is None and captures:
    selected_capture = sorted(captures, key=lambda item: item.get("mtime", 0), reverse=True)[0]
    resolved_capture = str(selected_capture.get("capture_id", resolved_capture))

  output_dir = stream_session_dir / "output"
  output_files = image_file_paths(output_dir)
  latest_output = file_brief(output_files[-1]) if output_files else None

  dataset_root = dataset_session_dir / "datasets"
  datasets: list[Dict[str, Any]] = []
  if dataset_root.exists() and dataset_root.is_dir():
    for child in sorted(dataset_root.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
      if not child.is_dir():
        continue
      manifest_path = child / "capture_session.json"
      manifest = read_json_if_present(manifest_path)
      datasets.append({
        "dataset_id": str(manifest.get("dataset_id") or child.name),
        "dataset_name": str(manifest.get("dataset_name") or child.name),
        "capture_id": str(manifest.get("capture_id") or ""),
        "frame_count": int(manifest.get("frame_count") or 0),
        "dataset_root": str(child.resolve()),
        "images_dir": str((child / "images").resolve()),
        "manifest_url": file_url_for_path(manifest_path) if manifest_path.exists() else "",
        "generated_at": manifest.get("generated_at") or child.stat().st_mtime,
      })

  workspace_roots: list[Path] = []
  if resolved_family:
    family_root = workspace_session_dir / resolved_family
    if family_root.exists():
      workspace_roots.append(family_root)
  elif workspace_session_dir.exists():
    workspace_roots = [path for path in workspace_session_dir.iterdir() if path.is_dir()]

  workspaces: list[Dict[str, Any]] = []
  for root in workspace_roots:
    for manifest_path in sorted(root.glob("*/workspace_manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True):
      manifest = read_json_if_present(manifest_path)
      workspace_root = manifest_path.parent
      workspaces.append({
        "dataset_id": str(manifest.get("dataset_id") or workspace_root.name),
        "dataset_name": str(manifest.get("dataset_name") or workspace_root.name),
        "family": str(manifest.get("family") or root.name),
        "capture_id": str(manifest.get("capture_id") or ""),
        "frame_count": int(manifest.get("frame_count") or 0),
        "workspace_root": str(workspace_root.resolve()),
        "input_dir": str((workspace_root / "input").resolve()),
        "manifest_url": file_url_for_path(manifest_path),
        "generated_at": manifest.get("generated_at") or manifest_path.stat().st_mtime,
      })

  return {
    "ok": True,
    "session_id": resolved_session,
    "capture_id": resolved_capture,
    "family": resolved_family,
    "capture": {
      "exists": bool(selected_capture),
      "current": selected_capture,
      "captures": captures,
      "capture_count": len(captures),
      "frame_count": int(selected_capture.get("frame_count", 0)) if selected_capture else 0,
    },
    "upload": {
      "exists": stream_session_dir.exists(),
      "stream_dir": str(stream_session_dir),
      "output_dir": str(output_dir.resolve()),
      "latest_output": latest_output,
      "output_count": len(output_files),
      "uploaded_frame_count": sum(int(item.get("frame_count", 0)) for item in captures),
    },
    "session_prep": {
      "exists": bool(datasets or workspaces),
      "dataset_count": len(datasets),
      "workspace_count": len(workspaces),
      "datasets": datasets,
      "workspaces": workspaces,
    },
  }


def delete_flow_data_stage(
  payload: Dict[str, Any],
  *,
  remover: Callable[[Path], None] | None = None,
  exists: Callable[[Path], bool] | None = None,
) -> Dict[str, Any]:
  session_id = str(payload.get("session_id", "")).strip()
  capture_id = str(payload.get("capture_id", "")).strip()
  family = str(payload.get("family", "")).strip()
  stage = str(payload.get("stage", "")).strip().lower()
  if not session_id:
    raise ValueError("session_id is required")
  if stage not in {"capture", "upload", "session_prep", "all_staging"}:
    raise ValueError("stage must be one of: capture, upload, session_prep, all_staging")

  remover = remover or (lambda path: shutil.rmtree(path))
  exists = exists or (lambda path: path.exists())

  targets: list[Path] = []
  stream_session_dir = safe_generated_child(STREAM_DIR, session_id)
  if stage == "capture":
    if capture_id:
      targets.append(safe_generated_child(STREAM_DIR, session_id, "captures", capture_id))
    else:
      targets.append(safe_generated_child(STREAM_DIR, session_id, "captures"))
    targets.append(safe_generated_child(STREAM_DIR, session_id, "output"))
  elif stage == "upload":
    targets.append(stream_session_dir)
  elif stage == "session_prep":
    targets.append(safe_generated_child(DATASET_DIR, session_id))
    targets.append(safe_generated_child(WORKSPACE_DIR, session_id))
  elif stage == "all_staging":
    targets.extend(flow_temporary_dirs(session_id))

  deleted: list[str] = []
  for target in targets:
    if not exists(target):
      continue
    remover(target)
    deleted.append(str(target))

  return {
    "ok": True,
    "stage": stage,
    "session_id": session_id,
    "capture_id": capture_id,
    "deleted_paths": deleted,
    "data": inspect_flow_data(session_id, capture_id, family),
  }


def project_for_family(family: str | None) -> Dict[str, Any] | None:
  normalized = str(family or "").strip().lower()
  if not normalized:
    return None
  for project in LOCAL_RESULT_PROJECTS:
    if project["family"] == normalized:
      return project
  return None


def infer_family_for_path(path: Path, explicit_family: str | None = None) -> str:
  if explicit_family:
    return str(explicit_family).strip()
  resolved = path.resolve()
  for project in LOCAL_RESULT_PROJECTS:
    root = Path(project["root"]).resolve()
    if root.exists() and path_is_inside(resolved, root):
      return str(project["family"])
  path_parts = {part.lower() for part in resolved.parts}
  for project in LOCAL_RESULT_PROJECTS:
    if str(project["family"]).lower() in path_parts:
      return str(project["family"])
  return ""


def representation_for_family(family: str | None, fallback: str | None = None) -> str:
  if fallback:
    return fallback
  project = project_for_family(family)
  if project:
    return str(project.get("representation") or "sh")
  adapter = get_adapter(str(family or ""))
  return str((adapter or {}).get("representation") or "sh")


def is_image_file(path: Path) -> bool:
  return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def is_ply_file(path: Path) -> bool:
  return path.is_file() and path.suffix.lower() in PLY_EXTENSIONS


def newest_file(paths: list[Path]) -> Path | None:
  existing = [path for path in paths if path.exists() and path.is_file()]
  if not existing:
    return None
  return max(existing, key=lambda item: (item.stat().st_mtime, str(item)))


def newest_image_from_globs(directory: Path, patterns: list[str]) -> Path | None:
  candidates: list[Path] = []
  for pattern in patterns:
    for image_path in directory.glob(pattern):
      if is_image_file(image_path):
        candidates.append(image_path)
  return newest_file(candidates)


def path_mtime(path: Path) -> float:
  try:
    return path.stat().st_mtime
  except OSError:
    return 0.0


def compgs_result_candidate_dirs(directory: Path, family: str | None = None) -> list[Path]:
  family = str(family or "").strip()
  if family != "compgs" or not directory.is_dir():
    return [directory]

  nested: list[Path] = []
  result_markers = ("point_cloud", "eval", "eval_training", "Log")
  for child in directory.iterdir():
    if not child.is_dir() or child.name.startswith("."):
      continue
    if child.name in RESULT_SCAN_EXCLUDED_DIRS or child.name == "config":
      continue
    if any((child / marker).exists() for marker in result_markers):
      nested.append(child)

  nested.sort(key=lambda path: (path_mtime(path), path.name), reverse=True)
  return [directory, *nested]


def latest_iteration_dir(point_cloud_dir: Path) -> Path | None:
  if not point_cloud_dir.exists() or not point_cloud_dir.is_dir():
    return None
  candidates: list[tuple[int, Path]] = []
  for child in point_cloud_dir.iterdir():
    if not child.is_dir() or not child.name.startswith("iteration_"):
      continue
    try:
      iteration = int(child.name.split("_")[-1])
    except ValueError:
      continue
    candidates.append((iteration, child))
  if not candidates:
    return None
  candidates.sort(key=lambda item: item[0], reverse=True)
  return candidates[0][1]


def direct_ply_candidates(directory: Path, names: list[str] | None = None) -> list[Path]:
  target_names = names or ["point_cloud.ply", "latest.ply", "scene.ply"]
  return [directory / name for name in target_names]


def find_result_ply_in_directory(directory: Path, names: list[str]) -> Path | None:
  direct = newest_file([path for path in direct_ply_candidates(directory, names) if is_ply_file(path)])
  if direct:
    return direct

  iteration_dir = latest_iteration_dir(directory / "point_cloud")
  if iteration_dir:
    for candidate in direct_ply_candidates(iteration_dir, names):
      if is_ply_file(candidate):
        return candidate

  if directory.name.startswith("iteration_"):
    for candidate in direct_ply_candidates(directory, names):
      if is_ply_file(candidate):
        return candidate

  return None


def find_result_ply(directory: Path, family: str | None = None) -> Path | None:
  family = str(family or "").strip()
  if is_ply_file(directory):
    return directory

  names = ["point_cloud.ply", "latest.ply", "scene.ply"]
  if family == "reduced-3dgs":
    names = ["point_cloud_quantised_half.ply", "point_cloud_quantised.ply", "point_cloud.ply", "latest.ply", "scene.ply"]

  if directory.is_dir():
    for candidate_dir in compgs_result_candidate_dirs(directory, family):
      result = find_result_ply_in_directory(candidate_dir, names)
      if result:
        return result

  return None


def find_result_manifest(directory: Path) -> Path | None:
  if directory.is_file() and directory.name == "scene_manifest.json":
    return directory
  if not directory.is_dir():
    return None
  candidate = directory / "scene_manifest.json"
  return candidate if candidate.exists() and candidate.is_file() else None


def result_image_patterns_for_family(family: str | None = None) -> list[str]:
  family = str(family or "").strip()
  if family == "compgs":
    return [
      "eval/rendered/*",
      "eval_training/rendered/*",
    ]
  if family == "reduced-3dgs":
    return [
      "test/*/renders/*",
      "train/*/renders/*",
    ]
  return [
    "test/ours_*/renders/*",
    "train/ours_*/renders/*",
  ]


def dedupe_paths(paths: list[Path]) -> list[Path]:
  deduped: list[Path] = []
  seen: set[str] = set()
  for path in paths:
    try:
      resolved = path.resolve()
    except OSError:
      continue
    key = str(resolved)
    if key in seen:
      continue
    seen.add(key)
    deduped.append(resolved)
  return deduped


def find_result_images(directory: Path, family: str | None = None) -> list[Path]:
  if is_image_file(directory):
    return [directory.resolve()]
  if not directory.is_dir():
    return []

  patterns = result_image_patterns_for_family(family)
  candidates: list[Path] = []

  for candidate_dir in compgs_result_candidate_dirs(directory, family):
    candidates.extend(candidate_dir / f"latest{suffix}" for suffix in IMAGE_EXTENSIONS)
    for pattern in patterns:
      candidates.extend(path for path in candidate_dir.glob(pattern) if is_image_file(path))

  images = [path for path in dedupe_paths(candidates) if is_image_file(path)]
  images.sort(key=lambda path: (path_mtime(path), str(path)), reverse=True)
  return images


def find_result_image(directory: Path, family: str | None = None) -> Path | None:
  images = find_result_images(directory, family)
  return images[0] if images else None


def image_search_dirs_for_result_file(path: Path) -> list[Path]:
  if is_image_file(path):
    return [path]
  candidates = [path.parent]
  current = path.parent
  for ancestor in current.parents:
    if ancestor == ROOT_DIR.parent:
      break
    candidates.append(ancestor)
    if len(candidates) >= 5:
      break
  return dedupe_paths(candidates)


def find_result_images_for_file(path: Path, family: str | None = None) -> list[Path]:
  images: list[Path] = []
  for candidate_dir in image_search_dirs_for_result_file(path):
    images.extend(find_result_images(candidate_dir, family))
  images = dedupe_paths(images)
  images.sort(key=lambda item: (path_mtime(item), str(item)), reverse=True)
  return images


def render_image_payloads(paths: list[Path]) -> list[Dict[str, Any]]:
  items: list[Dict[str, Any]] = []
  for path in paths:
    if not is_image_file(path):
      continue
    resolved = path.resolve()
    stat = resolved.stat()
    items.append({
      "name": resolved.name,
      "url": file_url_for_path(resolved, "images"),
      "path": str(resolved),
      "file_size": stat.st_size,
      "mtime": stat.st_mtime,
    })
  return items


def attach_render_images(payload: Dict[str, Any], image_paths: list[Path]) -> Dict[str, Any]:
  image_items = render_image_payloads(image_paths)
  if not image_items:
    return payload
  image_urls = [item["url"] for item in image_items]
  payload["result_url"] = payload.get("result_url") or image_urls[0]
  payload["result_urls"] = image_urls
  payload["render_images"] = image_items
  payload["render_image_count"] = len(image_items)
  return payload


def result_payload_for_ply(path: Path, *, family: str | None = None, representation: str | None = None) -> Dict[str, Any]:
  resolved = path.resolve()
  resolved_family = infer_family_for_path(resolved, family)
  resolved_representation = representation_for_family(resolved_family, representation)
  point_cloud_url = file_url_for_path(resolved, "ply")
  return {
    "ok": True,
    "type": "ply",
    "family": resolved_family,
    "representation": resolved_representation,
    "point_cloud_url": point_cloud_url,
    "viewer_url": build_viewer_url(point_cloud_url, resolved_representation),
    "resolved_path": str(resolved),
    "path": str(resolved),
    "file_size": resolved.stat().st_size,
  }


def result_payload_for_image(path: Path, *, family: str | None = None) -> Dict[str, Any]:
  resolved = path.resolve()
  resolved_family = infer_family_for_path(resolved, family)
  image_url = file_url_for_path(resolved, "images")
  return {
    "ok": True,
    "type": "image",
    "family": resolved_family,
    "result_url": image_url,
    "resolved_path": str(resolved),
    "path": str(resolved),
    "file_size": resolved.stat().st_size,
  }


def result_payload_for_manifest(path: Path, *, family: str | None = None, representation: str | None = None) -> Dict[str, Any]:
  resolved = path.resolve()
  resolved_family = infer_family_for_path(resolved, family)
  resolved_representation = representation_for_family(resolved_family, representation)
  manifest_url = file_url_for_path(resolved, "manifests")
  return {
    "ok": True,
    "type": "manifest",
    "family": resolved_family,
    "representation": resolved_representation,
    "manifest_url": manifest_url,
    "viewer_url": f"/web/?manifest={manifest_url}",
    "resolved_path": str(resolved),
    "path": str(resolved),
    "file_size": resolved.stat().st_size,
  }


def looks_like_fcgs_bitstream_dir(directory: Path) -> bool:
  if not directory.is_dir():
    return False
  for child in directory.iterdir():
    if not child.is_dir():
      continue
    try:
      float(child.name)
    except ValueError:
      continue
    return True
  return False


def load_result_path(path_value: str, family: str | None = None, representation: str | None = None) -> Dict[str, Any]:
  resolved_text = resolve_project_path(path_value)
  resolved = Path(resolved_text).resolve() if resolved_text else Path(str(path_value or "")).expanduser().resolve()
  resolved_family = infer_family_for_path(resolved, family)
  resolved_representation = representation_for_family(resolved_family, representation)

  if not resolved.exists():
    reason = f"Result path does not exist: {path_value}"
    return {
      "ok": False,
      "type": "",
      "family": resolved_family,
      "reason": reason,
      "error": reason,
      "path": str(path_value or ""),
      "resolved_path": str(resolved),
    }

  if is_ply_file(resolved):
    return attach_render_images(
      result_payload_for_ply(resolved, family=resolved_family, representation=resolved_representation),
      find_result_images_for_file(resolved, resolved_family),
    )
  if is_image_file(resolved):
    return attach_render_images(result_payload_for_image(resolved, family=resolved_family), [resolved])
  if resolved.is_file() and resolved.name == "scene_manifest.json":
    return attach_render_images(
      result_payload_for_manifest(resolved, family=resolved_family, representation=resolved_representation),
      find_result_images_for_file(resolved, resolved_family),
    )
  if resolved.is_file():
    reason = f"Unsupported result file type: {resolved.suffix or resolved.name}"
    return {
      "ok": False,
      "type": "",
      "family": resolved_family,
      "reason": reason,
      "error": reason,
      "path": str(path_value or ""),
      "resolved_path": str(resolved),
    }

  render_image_paths = find_result_images(resolved, resolved_family)

  ply_path = find_result_ply(resolved, resolved_family)
  if ply_path:
    return attach_render_images(
      result_payload_for_ply(ply_path, family=resolved_family, representation=resolved_representation),
      render_image_paths,
    )

  manifest_path = find_result_manifest(resolved)
  if manifest_path:
    return attach_render_images(
      result_payload_for_manifest(manifest_path, family=resolved_family, representation=resolved_representation),
      render_image_paths,
    )

  if render_image_paths:
    return attach_render_images(
      result_payload_for_image(render_image_paths[0], family=resolved_family),
      render_image_paths,
    )

  reason = "No supported PLY, scene manifest, or rendered image was found in this result directory."
  if resolved_family == "fcgs" and looks_like_fcgs_bitstream_dir(resolved):
    reason = "FCGS bitstreams were found, but no decoded PLY exists yet. Decode to point_cloud.ply, latest.ply, or scene.ply first."
  return {
    "ok": False,
    "type": "",
    "family": resolved_family,
    "reason": reason,
    "error": reason,
    "path": str(path_value or ""),
    "resolved_path": str(resolved),
  }


def load_ply_file(ply_path: str, representation: str | None = None) -> Dict[str, Any]:
  """
  Load a PLY file independently from the training flow.
  Supports absolute paths and paths relative to ROOT_DIR.
  """
  try:
    ply_file = Path(ply_path).resolve()

    # Keep path handling explicit so load failures can be explained clearly.
    if not (ply_file.exists()):
      return {
        "ok": False,
        "error": f"PLY file does not exist: {ply_path}",
        "path": ply_path,
      }

    if not ply_file.suffix.lower() == ".ply":
      return {
        "ok": False,
        "error": f"File is not a PLY file: {ply_file.suffix}",
        "path": str(ply_file),
      }

    return result_payload_for_ply(ply_file, representation=representation)
  except Exception as e:
    return {
      "ok": False,
      "error": str(e),
      "path": ply_path,
    }


def _training_format_args(payload: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "iterations": payload.get("iterations", 30_000),
    "image_folder": payload.get("image_folder", ""),
    "save_interval": payload.get("save_interval", 10_000),
    "gpcc_codec_path": payload.get("gpcc_codec_path", os.environ.get("GSC_GPCC_CODEC_PATH", "tmc3")),
    "fcgs_lmd": payload.get("fcgs_lmd", payload.get("lmd", 1e-4)),
    "voxel_size": payload.get("voxel_size", 0.001),
    "update_init_factor": payload.get("update_init_factor", 16),
    "lmbda": payload.get("lmbda", 0.001),
    "mask_lr_final": payload.get("mask_lr_final", 0.0001),
    "position_lr_init": payload.get("position_lr_init", 0.0),
    "position_lr_final": payload.get("position_lr_final", 0.0),
    "position_lr_delay_mult": payload.get("position_lr_delay_mult", 0.01),
    "position_lr_max_steps": payload.get("position_lr_max_steps", 30_000),
    "offset_lr_init": payload.get("offset_lr_init", 0.01),
    "offset_lr_final": payload.get("offset_lr_final", 0.0001),
    "offset_lr_delay_mult": payload.get("offset_lr_delay_mult", 0.01),
    "offset_lr_max_steps": payload.get("offset_lr_max_steps", 30_000),
    "mask_lr_init": payload.get("mask_lr_init", 0.01),
    "mask_lr_delay_mult": payload.get("mask_lr_delay_mult", 0.01),
    "mask_lr_max_steps": payload.get("mask_lr_max_steps", 30_000),
    "feature_lr": payload.get("feature_lr", 0.0075),
    "opacity_lr": payload.get("opacity_lr", 0.02),
    "scaling_lr": payload.get("scaling_lr", 0.007),
    "rotation_lr": payload.get("rotation_lr", 0.002),
  }


def newest_iteration_ply(directory: Path) -> Path | None:
  point_cloud_dir = directory / "point_cloud"
  if not point_cloud_dir.exists():
    return None
  candidates: list[tuple[int, Path]] = []
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
  if not candidates:
    return None
  candidates.sort(key=lambda item: item[0], reverse=True)
  return candidates[0][1]


def newest_render_image(directory: Path) -> Path | None:
  render_roots = [
    directory / "test",
    directory / "train",
  ]
  candidates: list[tuple[float, Path]] = []
  for root in render_roots:
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


def read_runtime_artifacts(output_dir: str | None, representation: str | None = None) -> Dict[str, Any]:
  if not output_dir:
    return {}
  directory = Path(output_dir).resolve()
  metrics_path = directory / "metrics.json"
  payload: Dict[str, Any] = {}
  if metrics_path.exists():
    try:
      payload["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
      pass
  artifact = load_result_path(str(directory), representation=representation)
  if artifact.get("ok"):
    for key in ("type", "family", "representation", "resolved_path", *ARTIFACT_RESULT_FIELDS):
      if artifact.get(key):
        payload[key] = artifact[key]
  return payload


def json_response(handler: "ApiHandler", payload: Dict[str, Any], status: int = 200) -> None:
  body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  handler.send_response(status)
  handler.send_header("Content-Type", "application/json; charset=utf-8")
  handler.send_header("Content-Length", str(len(body)))
  handler.send_header("Access-Control-Allow-Origin", "*")
  handler.send_header("Access-Control-Allow-Headers", "Content-Type")
  handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
  handler.end_headers()
  handler.wfile.write(body)


def build_error_payload(
  *,
  code: str,
  step: str,
  message: str,
  reason: str = "",
  details: Dict[str, Any] | None = None,
  manual_anchor: str = "",
  next_action: str = "",
) -> Dict[str, Any]:
  return {
    "ok": False,
    "error": message,
    "code": code,
    "step": step,
    "message": message,
    "reason": reason or message,
    "details": details or {},
    "manual_url": MANUAL_ZH_URL,
    "manual_anchor": manual_anchor,
    "next_action": next_action,
  }


def error_response(
  handler: "ApiHandler",
  *,
  code: str,
  step: str,
  message: str,
  status: int = 400,
  reason: str = "",
  details: Dict[str, Any] | None = None,
  manual_anchor: str = "",
  next_action: str = "",
) -> None:
  json_response(
    handler,
    build_error_payload(
      code=code,
      step=step,
      message=message,
      reason=reason,
      details=details,
      manual_anchor=manual_anchor,
      next_action=next_action,
    ),
    status=status,
  )


def extract_remote_config_input(payload: Dict[str, Any]) -> Dict[str, Any]:
  remote_payload = payload.get("remote", {}) if isinstance(payload.get("remote"), dict) else {}
  return {
    "host": remote_payload.get("host", payload.get("remote_host", "")),
    "port": remote_payload.get("port", payload.get("remote_port", 22)),
    "username": remote_payload.get("username", payload.get("remote_username", "")),
    "password": remote_payload.get("password", payload.get("remote_password", "")),
    "repo_path": remote_payload.get("repo_path", payload.get("remote_repo_path", "")),
    "workspace_root": remote_payload.get("workspace_root", payload.get("remote_workspace_root", "")),
    "output_root": remote_payload.get("output_root", payload.get("remote_output_root", "")),
    "python": remote_payload.get("python", payload.get("remote_python", "python3")),
    "activate_cmd": remote_payload.get("activate_cmd", payload.get("remote_activate_cmd", "")),
  }


def validate_path_confirmation_payload(
  payload: Dict[str, Any],
  *,
  command_template: str,
  expected_checkpoint_path: str,
  expected_output_dir: str,
) -> tuple[bool, str, Dict[str, Any]]:
  confirmation = payload.get("path_confirmation")
  if not isinstance(confirmation, dict):
    return (
      False,
      "Missing path_confirmation. Please confirm checkpoint_path/output_dir in UI before submit.",
      {
        "required": {
          "path_confirmation.confirmed": True,
          "path_confirmation.checkpoint_path": "string",
          "path_confirmation.output_dir": "string",
        },
      },
    )

  if confirmation.get("confirmed") is not True:
    return (
      False,
      "path_confirmation.confirmed must be true.",
      {"path_confirmation": confirmation},
    )

  requires_checkpoint = "{checkpoint_path}" in command_template
  requires_output = "{output_dir}" in command_template

  confirmed_checkpoint = str(confirmation.get("checkpoint_path", "")).strip()
  confirmed_output_raw = str(confirmation.get("output_dir", "")).strip()

  expected_checkpoint = str(expected_checkpoint_path or "").strip()
  expected_output = str(expected_output_dir or "").strip()
  resolved_confirmed_output = resolve_project_path(confirmed_output_raw) if confirmed_output_raw else ""

  mismatches: Dict[str, Any] = {}
  if requires_checkpoint and confirmed_checkpoint != expected_checkpoint:
    mismatches["checkpoint_path"] = {
      "confirmed": confirmed_checkpoint,
      "expected": expected_checkpoint,
    }

  if requires_output:
    if not expected_output:
      mismatches["output_dir"] = {
        "confirmed": confirmed_output_raw,
        "expected": "<non-empty>",
      }
    elif confirmed_output_raw != expected_output and resolved_confirmed_output != expected_output:
      mismatches["output_dir"] = {
        "confirmed": confirmed_output_raw,
        "confirmed_resolved": resolved_confirmed_output,
        "expected": expected_output,
      }

  if mismatches:
    return (
      False,
      "Path confirmation mismatch. Please re-confirm checkpoint_path/output_dir in UI and retry.",
      {
        "required_fields": {
          "checkpoint_path": requires_checkpoint,
          "output_dir": requires_output,
        },
        "mismatches": mismatches,
      },
    )

  return (
    True,
    "",
    {
      "required_fields": {
        "checkpoint_path": requires_checkpoint,
        "output_dir": requires_output,
      },
      "confirmed_at": confirmation.get("confirmed_at", ""),
    },
  )


def operation_command_template(adapter: Dict[str, Any], operation: str) -> str:
  operation_config = adapter.get("operations", {}).get(operation, {})
  if not operation_config.get("enabled"):
    raise ValueError(f"Operation {operation} is not enabled for {adapter.get('family', 'unknown')}")
  command_template = operation_config.get("template")
  if not command_template:
    raise ValueError(f"Operation {operation} does not define command template")
  return command_template


def effective_auto_colmap(auto_colmap: Any, use_existing_remote_dataset: Any) -> bool:
  return bool(auto_colmap) and not bool(use_existing_remote_dataset)


def effective_colmap_preflight_required(payload: Dict[str, Any]) -> bool:
  return effective_auto_colmap(
    payload.get("check_colmap_required", False),
    payload.get("use_existing_remote_dataset", False),
  )


def build_remote_algorithm_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
  family = str(payload.get("algorithm_family", "")).strip()
  if not family:
    raise ValueError("algorithm_family is required")

  adapter = get_adapter(family)
  if not adapter:
    raise ValueError(f"Unknown algorithm family: {family}")

  operation = str(payload.get("operation", "train")).strip() or "train"
  command_template = operation_command_template(adapter, operation)
  remote_config = validate_remote_config(extract_remote_config_input(payload))

  session_id = str(payload.get("session_id", "default-session")).strip() or "default-session"
  dataset_name = str(payload.get("dataset_name", "")).strip() or session_id
  preview_job_id = str(payload.get("preview_job_id", "")).strip() or f"preview-{uuid.uuid4().hex[:8]}"
  use_existing_remote_dataset = bool(payload.get("use_existing_remote_dataset", False))
  remote_dataset_id = str(payload.get("remote_dataset_id", "")).strip()
  remote_dataset_path = str(payload.get("remote_dataset_path", "")).strip()

  if use_existing_remote_dataset:
    if remote_dataset_path:
      remote_workspace_for_command = str(PurePosixPath(remote_dataset_path))
      if not remote_dataset_id:
        remote_dataset_id = PurePosixPath(remote_workspace_for_command).parent.name
    elif remote_dataset_id:
      remote_workspace_for_command = str(
        PurePosixPath(remote_config["workspace_root"]) / "datasets" / family / remote_dataset_id / "workspace"
      )
    else:
      raise ValueError("remote_dataset_id or remote_dataset_path is required when use_existing_remote_dataset=true")
  else:
    dataset_slug = _normalize_slug(dataset_name, fallback="dataset")
    remote_dataset_id = remote_dataset_id or f"{dataset_slug}-{preview_job_id.replace('preview-', '')}"
    remote_workspace_for_command = str(
      PurePosixPath(remote_config["workspace_root"]) / "datasets" / family / remote_dataset_id / "workspace"
    )

  requested_output_dir = str(payload.get("output_dir", "")).strip()
  resolved_output_dir = resolve_project_path(requested_output_dir)
  if not resolved_output_dir:
    resolved_output_dir = default_run_output_dir(session_id, family)

  remote_paths = build_remote_paths(
    workspace_root=remote_config["workspace_root"],
    output_root=remote_config["output_root"],
    session_id=session_id,
    family=family,
    job_id=preview_job_id,
  )
  remote_tmux_session = build_remote_tmux_session_name(family=family, job_id=preview_job_id)
  remote_tmux_attach_command = build_remote_tmux_attach_command(remote_config, remote_tmux_session)

  checkpoint_path = str(payload.get("remote_checkpoint_path", payload.get("checkpoint_path", ""))).strip()
  input_path = str(payload.get("input_path", "")).strip()
  source_path = str(payload.get("source", "")).strip()
  format_args = {
    "input_path": input_path,
    "output_dir": remote_paths["output_dir"],
    "workspace": remote_workspace_for_command,
    "checkpoint_path": checkpoint_path,
    "repo_path": remote_config["repo_path"],
    "source": source_path or remote_workspace_for_command,
    **_training_format_args(payload),
  }
  remote_command = command_template.format(**format_args)
  remote_command = sanitize_formatted_command(command_template, remote_command, format_args)
  if remote_command.lstrip().startswith("python "):
    remote_command = f"{remote_config['python']}{remote_command.lstrip()[len('python') :]}"

  steps = [
    f"mkdir -p {shlex.quote(remote_paths['output_dir'])}",
    f"cd {shlex.quote(remote_config['repo_path'])}",
  ]
  if remote_config["activate_cmd"]:
    steps.append(remote_config["activate_cmd"])
  steps.append(remote_command)
  remote_script = " && ".join(steps)
  missing_inputs = missing_template_fields(command_template, format_args)

  return {
    "preview_job_id": preview_job_id,
    "algorithm_family": family,
    "operation": operation,
    "execution_backend": "tmux",
    "remote_tmux_session": remote_tmux_session,
    "remote_tmux_attach_command": remote_tmux_attach_command,
    "tmux_available": None,
    "tmux_install": {
      "policy": "submit_time_mamba_or_sudo_n",
      "uses_password_sudo": False,
    },
    "dataset_name": dataset_name,
    "remote_dataset_id": remote_dataset_id,
    "remote_workspace": remote_workspace_for_command,
    "remote_output_dir": remote_paths["output_dir"],
    "local_output_dir": resolved_output_dir,
    "checkpoint_path": checkpoint_path,
    "command_template": command_template,
    "remote_command": remote_command,
    "shell_command": f"bash -lc {shlex.quote(remote_script)}",
    "missing_inputs": missing_inputs,
    "remote": sanitize_remote_config(remote_config),
    "path_confirmation": {
      "confirmed": True,
      "family": family,
      "operation": operation,
      "checkpoint_path": checkpoint_path,
      "output_dir": resolved_output_dir,
    },
  }


def safe_int(raw_value: Any, default: int, *, minimum: int, maximum: int) -> int:
  try:
    value = int(raw_value)
  except Exception:
    value = default
  return max(minimum, min(maximum, value))


def file_download_response(
  handler: "ApiHandler",
  file_path: Path,
  *,
  content_type: str,
  download_name: str,
) -> None:
  if not file_path.exists() or not file_path.is_file():
    json_response(handler, {"error": f"File not found: {file_path}"}, status=404)
    return

  body = file_path.read_bytes()
  handler.send_response(HTTPStatus.OK)
  handler.send_header("Content-Type", content_type)
  handler.send_header("Content-Length", str(len(body)))
  handler.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
  handler.send_header("Access-Control-Allow-Origin", "*")
  handler.send_header("Access-Control-Allow-Headers", "Content-Type")
  handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
  handler.end_headers()
  handler.wfile.write(body)


def enrich_job(job: Dict[str, Any]) -> Dict[str, Any]:
  ensure_job_logging(job)
  enriched = dict(job)
  if not is_remote_download_pending(enriched):
    artifacts = read_runtime_artifacts(enriched.get("output_dir"), enriched.get("representation"))
    if artifacts.get("metrics"):
      enriched["metrics"] = {
        **enriched.get("metrics", {}),
        **artifacts["metrics"],
      }
    for key in ARTIFACT_RESULT_FIELDS:
      if artifacts.get(key):
        enriched[key] = artifacts[key]
  else:
    for key in ARTIFACT_RESULT_FIELDS:
      enriched.pop(key, None)
  job_id = str(enriched.get("id", "")).strip()
  if job_id:
    enriched["logs_api_url"] = f"/api/jobs/{job_id}/logs"
    enriched["logs_download_url"] = f"/api/jobs/{job_id}/logs/download"
    enriched["metrics_csv_url"] = f"/api/jobs/{job_id}/metrics.csv"
  if isinstance(enriched.get("metrics_history"), list):
    enriched["metrics_history_count"] = len(enriched["metrics_history"])
    enriched.pop("metrics_history", None)
  for private_field in ("log_dir", "log_file", "metrics_csv_file", "_process"):
    enriched.pop(private_field, None)
  return enriched


def _artifact_score(directory: Path) -> float:
  """Use the freshest file timestamp under a candidate output dir as ranking score."""
  targets = [
    directory / "scene_manifest.json",
    directory / "latest.png",
    directory / "point_cloud.ply",
    directory / "latest.ply",
    directory / "scene.ply",
    directory / "metrics.json",
  ]
  scores: list[float] = []
  for target in targets:
    if target.exists():
      try:
        scores.append(target.stat().st_mtime)
      except OSError:
        continue
  try:
    scores.append(directory.stat().st_mtime)
  except OSError:
    pass
  return max(scores) if scores else 0.0


def result_scan_roots() -> list[tuple[Path, str, str]]:
  roots: list[tuple[Path, str, str]] = [
    ((WEB_DIR / "generated" / "runs").resolve(), "", "generated"),
    ((STREAM_DIR).resolve(), "", "generated"),
    ((WEB_DIR / "generated" / "datasets").resolve(), "", "generated"),
  ]
  for project in LOCAL_RESULT_PROJECTS:
    project_root = Path(project["root"]).resolve()
    if not project_root.exists():
      continue
    roots.append((project_root, str(project["family"]), "project"))
  return roots


def discover_runtime_results(*, limit: int = 30, max_scan_dirs: int = 1800) -> list[Dict[str, Any]]:
  """Scan local server output roots and return mountable runtime artifacts."""
  safe_limit = max(1, min(limit, 100))
  safe_max_scan_dirs = max(200, min(max_scan_dirs, 8000))

  discovered: Dict[str, Dict[str, Any]] = {}
  scanned_dirs = 0

  for root, family, source in result_scan_roots():
    if not root.exists() or not root.is_dir():
      continue

    for current_root, dirnames, _ in os.walk(root):
      dirnames[:] = [
        dirname for dirname in dirnames
        if dirname not in RESULT_SCAN_EXCLUDED_DIRS and not dirname.startswith(".")
      ]
      scanned_dirs += 1
      if scanned_dirs > safe_max_scan_dirs:
        break
      directory = Path(current_root)
      if output_dir_has_pending_remote_download(directory):
        continue
      artifact = load_result_path(str(directory), family=family)
      if not artifact.get("ok"):
        continue

      output_dir = str(directory.resolve())
      asset_path = str(artifact.get("resolved_path") or output_dir)
      try:
        score = Path(asset_path).stat().st_mtime
      except OSError:
        score = _artifact_score(directory)
      item = {
        "id": f"discovered::{uuid.uuid5(uuid.NAMESPACE_URL, output_dir).hex[:12]}",
        "source": source,
        "output_dir": output_dir,
        "resolved_path": asset_path,
        "type": artifact.get("type", ""),
        "family": artifact.get("family", family),
        "representation": artifact.get("representation") or ("sg" if str(artifact.get("viewer_url", "")).find("/viewers/sg.html") >= 0 else "sh"),
        "score": score,
      }
      for key in (*ARTIFACT_RESULT_FIELDS, "reason"):
        if artifact.get(key):
          item[key] = artifact[key]

      metrics = read_runtime_artifacts(str(directory)).get("metrics")
      if isinstance(metrics, dict):
        item["metrics"] = metrics

      discovered.setdefault(asset_path, item)

    if scanned_dirs > safe_max_scan_dirs:
      break

  ordered = sorted(discovered.values(), key=lambda value: float(value.get("score", 0.0)), reverse=True)
  return ordered[:safe_limit]


def _normalize_remote_dataset_path(path: str) -> str:
  value = str(path or "").strip().replace("\\", "/")
  while value.endswith("/"):
    value = value[:-1]
  return value


def _append_family_coverage(coverage: Dict[str, set[str]], job_status: str, family: str) -> None:
  normalized_status = str(job_status or "").strip().lower()
  if normalized_status == "completed":
    coverage["trained"].add(family)
    return
  if normalized_status == "failed":
    coverage["failed"].add(family)
    return
  if normalized_status in {"queued", "running"}:
    coverage["running"].add(family)


def _annotate_datasets_with_training_coverage(
  datasets: list[Dict[str, Any]],
  *,
  family_scope: str,
) -> list[Dict[str, Any]]:
  if not datasets:
    return []

  available_families = sorted({
    str(item.get("family", "")).strip()
    for item in list_adapters()
    if str(item.get("family", "")).strip()
  })

  coverage_by_id: Dict[str, Dict[str, set[str]]] = {}
  coverage_by_id_family: Dict[str, Dict[str, set[str]]] = {}
  coverage_by_path: Dict[str, Dict[str, set[str]]] = {}

  for raw_job in JOBS.values():
    job = enrich_job(raw_job)
    if str(job.get("operation", "")).strip() != "remote_train":
      continue

    trained_family = str(job.get("algorithm_family", "")).strip()
    if not trained_family:
      continue

    job_status = str(job.get("status", "")).strip()
    remote_result_raw = job.get("remote_result")
    remote_result: Dict[str, Any] = remote_result_raw if isinstance(remote_result_raw, dict) else {}
    dataset_id = str(
      remote_result.get("remote_dataset_id")
      or job.get("remote_dataset_id")
      or ""
    ).strip()
    dataset_path = _normalize_remote_dataset_path(
      str(
        remote_result.get("remote_dataset_workspace")
        or job.get("remote_dataset_path")
        or ""
      )
    )

    if dataset_id:
      bucket = coverage_by_id.setdefault(dataset_id, {"trained": set(), "failed": set(), "running": set()})
      _append_family_coverage(bucket, job_status, trained_family)

      family_bucket_key = f"{trained_family}::{dataset_id}"
      family_bucket = coverage_by_id_family.setdefault(family_bucket_key, {"trained": set(), "failed": set(), "running": set()})
      _append_family_coverage(family_bucket, job_status, trained_family)

    if dataset_path:
      path_bucket = coverage_by_path.setdefault(dataset_path, {"trained": set(), "failed": set(), "running": set()})
      _append_family_coverage(path_bucket, job_status, trained_family)

  normalized_scope = str(family_scope or "").strip()
  annotated: list[Dict[str, Any]] = []
  for dataset in datasets:
    annotated_item = dict(dataset)
    dataset_id = str(dataset.get("id", "")).strip()
    dataset_path = _normalize_remote_dataset_path(str(dataset.get("path", "")))

    trained_families: set[str] = set()
    failed_families: set[str] = set()
    running_families: set[str] = set()

    if dataset_id and normalized_scope:
      scoped_key = f"{normalized_scope}::{dataset_id}"
      scoped = coverage_by_id_family.get(scoped_key)
      if scoped:
        trained_families.update(scoped["trained"])
        failed_families.update(scoped["failed"])
        running_families.update(scoped["running"])

    if dataset_id:
      generic = coverage_by_id.get(dataset_id)
      if generic:
        trained_families.update(generic["trained"])
        failed_families.update(generic["failed"])
        running_families.update(generic["running"])

    if dataset_path:
      by_path = coverage_by_path.get(dataset_path)
      if by_path:
        trained_families.update(by_path["trained"])
        failed_families.update(by_path["failed"])
        running_families.update(by_path["running"])

    missing_families = sorted(f for f in available_families if f not in trained_families)

    annotated_item["trained_families"] = sorted(trained_families)
    annotated_item["failed_families"] = sorted(failed_families)
    annotated_item["running_families"] = sorted(running_families)
    annotated_item["missing_families"] = missing_families
    annotated_item["training_coverage"] = {
      "available_families": available_families,
      "trained_families": sorted(trained_families),
      "failed_families": sorted(failed_families),
      "running_families": sorted(running_families),
      "missing_families": missing_families,
    }
    annotated.append(annotated_item)

  return annotated


def prune_job_history() -> None:
  ordered_jobs = sorted(JOBS.values(), key=lambda item: item.get("created_at", 0), reverse=True)
  keep_ids: set[str] = set()
  completed_process_frame_count = 0

  for job in ordered_jobs:
    job_id = job.get("id")
    if not job_id:
      continue
    if job.get("operation") == "process_frame" and job.get("status") == "completed":
      if completed_process_frame_count >= MAX_PROCESS_FRAME_COMPLETED_HISTORY:
        continue
      completed_process_frame_count += 1
    keep_ids.add(job_id)
    if len(keep_ids) >= MAX_JOB_HISTORY:
      break

  for job_id in list(JOBS.keys()):
    if job_id not in keep_ids:
      del JOBS[job_id]
      JOB_LOG_LOCKS.pop(job_id, None)


def is_job_terminal(job: Dict[str, Any]) -> bool:
  return str(job.get("status", "")).strip().lower() in TERMINAL_STATUSES


def remote_download_info(job: Dict[str, Any]) -> Dict[str, Any]:
  remote_result = job.get("remote_result")
  if not isinstance(remote_result, dict):
    return {}
  download = remote_result.get("download")
  return download if isinstance(download, dict) else {}


def is_remote_download_pending(job: Dict[str, Any]) -> bool:
  download = remote_download_info(job)
  return bool(job.get("remote_detached") and download.get("pending"))


def is_remote_download_active(job: Dict[str, Any]) -> bool:
  thread = job.get("_result_download_thread")
  return bool(thread is not None and getattr(thread, "is_alive", lambda: False)())


def is_remote_download_starting(job: Dict[str, Any]) -> bool:
  return bool(job.get("_result_download_starting"))


def completed_remote_result_paths(job: Dict[str, Any]) -> tuple[str, str]:
  remote_result = job.get("remote_result") if isinstance(job.get("remote_result"), dict) else {}
  remote_output_dir = str(job.get("remote_output_dir") or remote_result.get("remote_output_dir") or "").strip()
  local_output_dir = str(job.get("output_dir") or "").strip()
  return remote_output_dir, local_output_dir


def result_download_remote_config(job: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
  remote_config = payload.get("remote") if isinstance(payload.get("remote"), dict) else job.get("_remote_config")
  if not isinstance(remote_config, dict) or not str(remote_config.get("password", "")).strip():
    raise RemoteExecutionError(
      "Remote credentials are required to download completed job results.",
      code_hint="WGSC-JOB-RESULTS-REMOTE-CONFIG",
      stage="config",
    )
  validate_remote_config(remote_config)
  return remote_config


def validate_completed_result_download_job(job: Dict[str, Any]) -> tuple[str, str]:
  status = str(job.get("status", "")).strip().lower()
  if status != "completed":
    raise ValueError("Only completed jobs can download results.")
  if not job.get("remote_detached"):
    raise ValueError("Only completed remote jobs can download results.")
  remote_output_dir, local_output_dir = completed_remote_result_paths(job)
  if not remote_output_dir:
    raise ValueError("Completed remote job has no remote_output_dir to download.")
  if not local_output_dir:
    raise ValueError("Completed remote job has no local output_dir to download into.")
  return remote_output_dir, local_output_dir


def set_remote_download_progress(job: Dict[str, Any], progress: Dict[str, Any]) -> None:
  remote_result = job.setdefault("remote_result", {})
  if not isinstance(remote_result, dict):
    remote_result = {}
    job["remote_result"] = remote_result
  download = {
    **remote_download_info(job),
    **progress,
    "updated_at": time.time(),
  }
  remote_result["download"] = download
  job["safe_to_close_web"] = True
  if download.get("pending"):
    job["remote_stage"] = "remote_downloading"
    job["monitor_state"] = "downloading"


def apply_completed_result_check(job: Dict[str, Any], check: Dict[str, Any]) -> None:
  set_remote_download_progress(job, {
    **check,
    "pending": False,
    "phase": "complete" if check.get("complete") else "incomplete",
  })
  if check.get("complete"):
    update_job_artifacts(job)
  job["remote_stage"] = "completed"
  job["monitor_state"] = "completed"


def check_completed_result_download(job: Dict[str, Any], remote_config: Dict[str, Any]) -> Dict[str, Any]:
  remote_output_dir, local_output_dir = validate_completed_result_download_job(job)
  check = check_remote_output_download(
    remote_config=remote_config,
    remote_output_dir=remote_output_dir,
    local_output_dir=local_output_dir,
  )
  apply_completed_result_check(job, check)
  persist_job_state(job)
  return check


def start_completed_result_download(job: Dict[str, Any], remote_config: Dict[str, Any]) -> Dict[str, Any]:
  with RESULT_DOWNLOAD_LOCK:
    if is_remote_download_active(job) or is_remote_download_starting(job):
      return {"ok": True, "started": False, "already_running": True, "job": enrich_job(job)}
    remote_output_dir, local_output_dir = validate_completed_result_download_job(job)
    job["_result_download_starting"] = True

  try:
    check = check_remote_output_download(
      remote_config=remote_config,
      remote_output_dir=remote_output_dir,
      local_output_dir=local_output_dir,
    )
  except Exception:
    with RESULT_DOWNLOAD_LOCK:
      job.pop("_result_download_starting", None)
    raise

  if check.get("complete"):
    with RESULT_DOWNLOAD_LOCK:
      apply_completed_result_check(job, check)
      job.pop("_result_download_starting", None)
    persist_job_state(job)
    return {"ok": True, "started": False, "complete": True, "check": check, "job": enrich_job(job)}

  set_remote_download_progress(job, {
    **check,
    "pending": True,
    "phase": "queued",
    "files": 0,
    "bytes": 0,
    "current_file": "",
  })
  persist_job_state(job)

  def runner() -> None:
    try:
      def record_download_progress(progress: Dict[str, Any]) -> None:
        set_remote_download_progress(job, progress)
        persist_job_state(job)

      result = download_remote_output_directory(
        remote_config=remote_config,
        remote_output_dir=remote_output_dir,
        local_output_dir=local_output_dir,
        progress_callback=record_download_progress,
      )
      set_remote_download_progress(job, {
        **result,
        "pending": False,
        "phase": "complete",
      })
      job["remote_stage"] = "completed"
      job["monitor_state"] = "completed"
      update_job_artifacts(job)
      persist_job_state(job)
    except Exception as exc:  # pragma: no cover - network dependent
      set_remote_download_progress(job, {
        "pending": False,
        "phase": "error",
        "error": str(exc),
      })
      job["remote_stage"] = "result_download_failed"
      job["monitor_state"] = "completed"
      append_job_log_line(job, "stderr", f"[ResultDownload] Failed to download completed result: {exc}\n")
      persist_job_state(job)
    finally:
      with RESULT_DOWNLOAD_LOCK:
        job.pop("_result_download_thread", None)
        job.pop("_result_download_starting", None)

  thread = threading.Thread(target=runner, daemon=True)
  with RESULT_DOWNLOAD_LOCK:
    job["_result_download_thread"] = thread
    job.pop("_result_download_starting", None)
  thread.start()
  return {"ok": True, "started": True, "complete": False, "check": check, "job": enrich_job(job)}


def output_dir_has_pending_remote_download(directory: Path) -> bool:
  try:
    resolved = directory.resolve()
  except OSError:
    return False
  for job in JOBS.values():
    if not is_remote_download_pending(job):
      continue
    output_dir = str(job.get("output_dir") or "").strip()
    if not output_dir:
      continue
    try:
      root = Path(output_dir).resolve()
    except OSError:
      continue
    if resolved == root or root in resolved.parents:
      return True
  return False


def job_log_dir_for_id(job_id: str) -> Path:
  raw = str(job_id or "").strip()
  if not raw:
    raise ValueError("job_id is required")
  candidate = (JOB_LOG_DIR / raw).resolve()
  root = JOB_LOG_DIR.resolve()
  if root == candidate or root not in candidate.parents:
    raise ValueError(f"Unsafe job log path: {candidate}")
  return candidate


def remove_job_record(job_id: str, *, require_terminal: bool = True) -> Dict[str, Any]:
  raw = str(job_id or "").strip()
  if not raw:
    raise ValueError("job_id is required")
  job = JOBS.get(raw)
  if not job:
    raise KeyError(f"Unknown job: {raw}")
  if require_terminal and not is_job_terminal(job):
    raise ValueError("Only completed, failed, or canceled job records can be removed. Cancel running jobs first.")

  log_dir_value = str(job.get("log_dir", "")).strip()
  try:
    log_dir = Path(log_dir_value).resolve() if log_dir_value else job_log_dir_for_id(raw)
  except Exception:
    log_dir = job_log_dir_for_id(raw)
  job_log_root = JOB_LOG_DIR.resolve()
  if log_dir == job_log_root or not path_is_inside(log_dir, job_log_root):
    raise ValueError(f"Unsafe job log path: {log_dir}")

  state_file = log_dir / JOB_STATE_FILE
  removed_state_file = False
  if state_file.exists() and state_file.is_file():
    state_file.unlink()
    removed_state_file = True

  removed = JOBS.pop(raw, None)
  JOB_LOG_LOCKS.pop(raw, None)
  return {
    "id": raw,
    "status": removed.get("status", "") if isinstance(removed, dict) else "",
    "removed_state_file": removed_state_file,
    "logs_retained": str(log_dir),
  }


def normalize_clear_statuses(value: Any) -> set[str]:
  if value in (None, "", []):
    return set(TERMINAL_STATUSES)
  if isinstance(value, str):
    raw_items = [value]
  elif isinstance(value, list):
    raw_items = value
  else:
    raw_items = []

  statuses: set[str] = set()
  for item in raw_items:
    text = str(item or "").strip().lower()
    if not text:
      continue
    if text in {"finished", "terminal", "done"}:
      statuses.update(TERMINAL_STATUSES)
    else:
      statuses.add(text)
  return {status for status in statuses if status in TERMINAL_STATUSES}


def clear_job_records(statuses_value: Any = None) -> Dict[str, Any]:
  statuses = normalize_clear_statuses(statuses_value)
  removed: list[Dict[str, Any]] = []
  skipped: list[Dict[str, str]] = []
  for job_id, job in list(JOBS.items()):
    status = str(job.get("status", "")).strip().lower()
    if status not in statuses:
      continue
    if not is_job_terminal(job):
      skipped.append({"id": job_id, "status": status})
      continue
    removed.append(remove_job_record(job_id, require_terminal=True))
  return {
    "ok": True,
    "statuses": sorted(statuses),
    "removed": removed,
    "removed_count": len(removed),
    "skipped": skipped,
    "remaining": len(JOBS),
  }


def update_job_artifacts(job: Dict[str, Any]) -> None:
  if is_remote_download_pending(job):
    return
  artifacts = read_runtime_artifacts(job.get("output_dir"), job.get("representation"))
  if artifacts.get("metrics"):
    job["metrics"] = {
      **job.get("metrics", {}),
      **artifacts["metrics"],
    }
  for key in ARTIFACT_RESULT_FIELDS:
    if artifacts.get(key):
      job[key] = artifacts[key]


def apply_remote_poll_result(job: Dict[str, Any], poll_result: Dict[str, Any]) -> None:
  log_text = str(poll_result.get("log_text", ""))
  if log_text:
    append_job_log_line(job, "stdout", log_text)
  job["remote_log_cursor"] = int(poll_result.get("log_cursor", job.get("remote_log_cursor", 0)) or 0)
  job["status"] = str(poll_result.get("status") or job.get("status") or "running")
  job["remote_stage"] = str(poll_result.get("stage") or job.get("remote_stage") or "remote_detached_running")
  job["monitor_state"] = "monitoring" if not is_job_terminal(job) else "completed"
  job["safe_to_close_web"] = True
  if poll_result.get("return_code") not in (None, ""):
    job["return_code"] = poll_result.get("return_code")
  if poll_result.get("remote_pid"):
    job["remote_pid"] = poll_result.get("remote_pid")
  if poll_result.get("remote_tmux_session"):
    job["remote_tmux_session"] = poll_result.get("remote_tmux_session")
  remote_result = job.setdefault("remote_result", {})
  for target_key, source_key in (
    ("remote_output_dir", "remote_output_dir"),
    ("remote_dataset_id", "remote_dataset_id"),
    ("remote_dataset_name", "remote_dataset_name"),
    ("remote_dataset_workspace", "remote_dataset_workspace"),
  ):
    if poll_result.get(source_key):
      remote_result[target_key] = poll_result[source_key]
  if poll_result.get("download"):
    remote_result["download"] = poll_result["download"]
  update_job_artifacts(job)
  if is_job_terminal(job) and not job.get("finished_at"):
    job["finished_at"] = time.time()


def start_remote_monitor_thread(job: Dict[str, Any], remote_config: Dict[str, Any]) -> None:
  if job.get("_monitoring"):
    return
  job["_monitoring"] = True
  job["_remote_config"] = dict(remote_config)

  def monitor() -> None:
    try:
      while True:
        if job.get("cancel_requested"):
          break
        try:
          poll_result = poll_remote_detached_job(
            remote_config=remote_config,
            remote_status_path=str(job.get("remote_status_path", "")),
            remote_log_path=str(job.get("remote_log_path", "")),
            remote_output_dir=str(job.get("remote_output_dir", "")),
            local_output_dir=str(job.get("output_dir", "")),
            log_cursor=int(job.get("remote_log_cursor", 0) or 0),
            download_output=False,
          )
          apply_remote_poll_result(job, poll_result)
          persist_job_state(job)
          if is_job_terminal(job):
            set_remote_download_progress(job, {
              "files": 0,
              "bytes": 0,
              "pending": True,
              "current_file": "",
            })
            persist_job_state(job)

            def record_download_progress(progress: Dict[str, Any]) -> None:
              set_remote_download_progress(job, progress)
              persist_job_state(job)

            final_poll = poll_remote_detached_job(
              remote_config=remote_config,
              remote_status_path=str(job.get("remote_status_path", "")),
              remote_log_path=str(job.get("remote_log_path", "")),
              remote_output_dir=str(job.get("remote_output_dir", "")),
              local_output_dir=str(job.get("output_dir", "")),
              log_cursor=int(job.get("remote_log_cursor", 0) or 0),
              download_output=True,
              download_progress_callback=record_download_progress,
            )
            apply_remote_poll_result(job, final_poll)
            if str(job.get("monitor_state", "")) != "completed":
              job["monitor_state"] = "completed"
            persist_job_state(job)
            break
        except Exception as exc:  # pragma: no cover - network dependent
          job["monitor_state"] = "needs_remote_config"
          job["remote_stage"] = "detached_monitor_disconnected"
          append_job_log_line(job, "stderr", f"[Monitor] Detached remote monitor disconnected: {exc}\n")
          persist_job_state(job)
          break
        time.sleep(3)
    finally:
      job["_monitoring"] = False

  threading.Thread(target=monitor, daemon=True).start()


def job_matches_flow(job: Dict[str, Any], *, session_id: str, capture_id: str, selected_job_id: str) -> bool:
  if selected_job_id and str(job.get("id", "")).strip() == selected_job_id:
    return True
  if session_id:
    job_session = str(job.get("session_id") or job.get("stream_session_id") or "").strip()
    if job_session == session_id:
      return True
  if capture_id:
    job_capture = str(job.get("capture_id", "")).strip()
    if job_capture == capture_id:
      return True
  return False


def unfinished_flow_jobs(*, session_id: str, capture_id: str, selected_job_id: str) -> list[Dict[str, Any]]:
  if not any((session_id, capture_id, selected_job_id)):
    return []
  return [
    job
    for job in JOBS.values()
    if not is_job_terminal(job)
    and job_matches_flow(job, session_id=session_id, capture_id=capture_id, selected_job_id=selected_job_id)
  ]


def cancel_flow_job(job: Dict[str, Any], remote_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
  if is_job_terminal(job):
    return {"id": job.get("id", ""), "status": job.get("status", ""), "already_terminal": True}

  append_job_log_line(job, "stderr", "[FlowReset] Canceling unfinished job before restarting upload training.\n")
  job["cancel_requested"] = True

  if job.get("remote_detached"):
    if not isinstance(remote_config, dict) or not str(remote_config.get("password", "")).strip():
      job["monitor_state"] = "needs_remote_config"
      persist_job_state(job)
      raise RemoteExecutionError(
        "Remote credentials are required to cancel detached jobs before resetting the flow.",
        code_hint="WGSC-FLOW-RESET-REMOTE-CONFIG",
        stage="flow_reset",
      )
    cancel_remote_detached_job(
      remote_config=remote_config,
      remote_job_dir=str(job.get("remote_job_dir", "")),
      remote_pid=str(job.get("remote_pid", "")),
      remote_tmux_session=str(job.get("remote_tmux_session", "")),
    )
  else:
    process = job.get("_process")
    if process is not None:
      try:
        if process.poll() is None:
          process.terminate()
      except Exception as exc:
        append_job_log_line(job, "stderr", f"[FlowReset] Failed to terminate local process: {exc}\n")

  job["status"] = "canceled"
  job["remote_stage"] = "flow_reset"
  job["monitor_state"] = "completed"
  job["return_code"] = 130
  job["finished_at"] = time.time()
  persist_job_state(job)
  return {"id": job.get("id", ""), "status": "canceled", "remote_detached": bool(job.get("remote_detached"))}


def flow_temporary_dirs(session_id: str) -> list[Path]:
  raw = str(session_id or "").strip()
  if not raw:
    return []
  roots = [STREAM_DIR, DATASET_DIR, WORKSPACE_DIR]
  candidates: list[Path] = []
  for root in roots:
    root_resolved = root.resolve()
    candidate = (root_resolved / raw).resolve()
    if root_resolved == candidate or root_resolved not in candidate.parents:
      raise ValueError(f"Refusing to clean unsafe flow path: {candidate}")
    candidates.append(candidate)
  return candidates


def cleanup_flow_temporary_dirs(
  session_id: str,
  *,
  remover: Callable[[Path], None] | None = None,
  exists: Callable[[Path], bool] | None = None,
) -> list[str]:
  remover = remover or (lambda path: shutil.rmtree(path))
  exists = exists or (lambda path: path.exists())
  cleaned: list[str] = []
  for path in flow_temporary_dirs(session_id):
    if not exists(path):
      continue
    remover(path)
    cleaned.append(str(path))
  return cleaned


def reset_flow(payload: Dict[str, Any]) -> Dict[str, Any]:
  session_id = str(payload.get("session_id", "")).strip()
  capture_id = str(payload.get("capture_id", "")).strip()
  selected_job_id = str(payload.get("selected_job_id", "")).strip()
  cancel_unfinished = bool(payload.get("cancel_unfinished", True))
  remote_config = payload.get("remote") if isinstance(payload.get("remote"), dict) else {}

  targets = unfinished_flow_jobs(
    session_id=session_id,
    capture_id=capture_id,
    selected_job_id=selected_job_id,
  )
  if cancel_unfinished:
    needs_remote = [job for job in targets if job.get("remote_detached")]
    if needs_remote and not str(remote_config.get("password", "")).strip():
      raise RemoteExecutionError(
        "Remote credentials are required to cancel detached jobs before resetting the flow.",
        code_hint="WGSC-FLOW-RESET-REMOTE-CONFIG",
        stage="flow_reset",
      )

  canceled: list[Dict[str, Any]] = []
  if cancel_unfinished:
    for job in targets:
      canceled.append(cancel_flow_job(job, remote_config))

  cleaned_paths = cleanup_flow_temporary_dirs(session_id)
  return {
    "ok": True,
    "code": "WGSC-FLOW-RESET-OK",
    "canceled_jobs": canceled,
    "cleaned_paths": cleaned_paths,
    "session_id": session_id,
    "capture_id": capture_id,
    "reset_scope": str(payload.get("reset_scope", "all")),
  }


def start_job_thread(job: Dict[str, Any], command: str, cwd: str | None = None) -> None:
  def runner() -> None:
    ensure_job_logging(job)
    if job.get("cancel_requested"):
      job["status"] = "canceled"
      job["finished_at"] = time.time()
      return
    job["status"] = "running"
    job["started_at"] = time.time()
    job["metrics"] = {}
    job["stdout"] = ""
    job["stderr"] = ""
    combined_log: list[str] = []

    def consume_stream(stream, channel: str) -> None:
      for line in iter(stream.readline, ""):
        if not line:
          break
        append_job_log_line(job, channel, line)
        combined_log.append(line)
        job["metrics"] = extract_job_metrics("".join(combined_log[-2000:]))
        artifacts = read_runtime_artifacts(job.get("output_dir"), job.get("representation"))
        if artifacts.get("metrics"):
          job["metrics"] = {
            **job.get("metrics", {}),
            **artifacts["metrics"],
          }
        for key in ARTIFACT_RESULT_FIELDS:
          if artifacts.get(key):
            job[key] = artifacts[key]
      stream.close()

    try:
      effective_cwd = resolve_workspace_path(cwd) or None
      args = shlex.split(command, posix=not sys.platform.startswith("win"))
      if args and args[0] == "python":
        args[0] = sys.executable
      # Remove any empty trailing arguments or literal empty quotes that shlex on posix=False might leave
      args = [a.strip('"').strip("'") if a in ('""', "''") else a for a in args]
      cleaned_args: list[str] = []
      idx = 0
      while idx < len(args):
        token = args[idx]
        if token == "--repo-path" and (idx + 1 >= len(args) or args[idx + 1].startswith("--")):
          idx += 1
          continue
        cleaned_args.append(token)
        idx += 1
      args = cleaned_args
      if len(args) >= 2 and args[1].lower().endswith(".py"):
        script_arg = args[1].strip('"').strip("'")
        script_path = Path(script_arg)
        if not script_path.is_absolute():
          base_dir = Path(effective_cwd) if effective_cwd else ROOT_DIR
          candidate = (base_dir / script_path).resolve()
          if not candidate.exists() and script_arg.replace("\\", "/").startswith("../web/"):
            candidate = (ROOT_DIR / script_arg.replace("\\", "/")[3:]).resolve()
          if candidate.exists():
            args[1] = str(candidate)
      process = subprocess.Popen(
        args,
        cwd=effective_cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
      )
      job["_process"] = process
      stdout_thread = threading.Thread(target=consume_stream, args=(process.stdout, "stdout"), daemon=True)
      stderr_thread = threading.Thread(target=consume_stream, args=(process.stderr, "stderr"), daemon=True)
      stdout_thread.start()
      stderr_thread.start()
      return_code = process.wait()
      stdout_thread.join(timeout=1)
      stderr_thread.join(timeout=1)
      artifacts = read_runtime_artifacts(job.get("output_dir"), job.get("representation"))
      if artifacts.get("metrics"):
        job["metrics"] = {
          **job.get("metrics", {}),
          **artifacts["metrics"],
        }
      for key in ARTIFACT_RESULT_FIELDS:
        if artifacts.get(key):
          job[key] = artifacts[key]
      job["return_code"] = return_code
      if return_code != 0:
        missing_module = extract_missing_module_from_stderr(job.get("stderr", ""))
        if missing_module:
          adapter = get_adapter(job.get("algorithm_family", "")) or {}
          hint_text = build_dependency_hint(adapter, missing_module)
          if hint_text:
            append_job_log_line(job, "stderr", hint_text)
            merged_stderr = f"{job.get('stderr', '').rstrip()}\n\n{hint_text}".strip()
            job["stderr"] = merged_stderr[-12000:]
      if job.get("cancel_requested"):
        job["status"] = "canceled"
      else:
        job["status"] = "completed" if return_code == 0 else "failed"
    except Exception as exc:  # pragma: no cover
      job["status"] = "canceled" if job.get("cancel_requested") else "failed"
      append_job_log_line(job, "stderr", str(exc))
      job["stderr"] = str(exc)
    finally:
      job.pop("_process", None)
      job["finished_at"] = time.time()

  threading.Thread(target=runner, daemon=True).start()


def start_remote_job_thread(
  job: Dict[str, Any],
  *,
  remote_config: Dict[str, Any],
  local_workspace_dir: str | None,
  local_output_dir: str,
  command_template: str,
  checkpoint_path: str,
  input_path: str,
  source_path: str,
  session_id: str,
  auto_colmap: bool,
  dataset_name: str,
  remote_dataset_id: str,
  remote_dataset_path: str,
  use_existing_remote_dataset: bool,
  training_args: Dict[str, Any] | None = None,
  command_override: str = "",
) -> None:
  auto_colmap = effective_auto_colmap(auto_colmap, use_existing_remote_dataset)

  def runner() -> None:
    ensure_job_logging(job)
    if job.get("cancel_requested"):
      job["status"] = "canceled"
      job["remote_stage"] = "canceled"
      job["finished_at"] = time.time()
      return
    job["status"] = "running"
    job["started_at"] = time.time()
    job["metrics"] = {}
    job["stdout"] = ""
    job["stderr"] = ""
    job["remote_stage"] = "queued"
    job["monitor_state"] = "starting"
    persist_job_state(job)
    combined_log: list[str] = []

    def update_artifacts() -> None:
      artifacts = read_runtime_artifacts(job.get("output_dir"), job.get("representation"))
      if artifacts.get("metrics"):
        job["metrics"] = {
          **job.get("metrics", {}),
          **artifacts["metrics"],
        }
      for key in ARTIFACT_RESULT_FIELDS:
        if artifacts.get(key):
          job[key] = artifacts[key]

    def on_log(channel: str, line: str) -> None:
      append_job_log_line(job, channel, line)
      combined_log.append(line)
      job["metrics"] = extract_job_metrics("".join(combined_log[-2000:]))
      update_artifacts()

    def on_stage(stage: str) -> None:
      job["remote_stage"] = stage

    try:
      result = start_remote_algorithm_detached(
        remote_config=remote_config,
        local_workspace_dir=local_workspace_dir or "",
        local_output_dir=local_output_dir,
        session_id=session_id,
        family=job.get("algorithm_family", "unknown"),
        job_id=job.get("id", "remote-job"),
        command_template=command_template,
        checkpoint_path=checkpoint_path,
        input_path=input_path,
        source_path=source_path,
        auto_colmap=auto_colmap,
        dataset_name=dataset_name,
        remote_dataset_id=remote_dataset_id,
        remote_dataset_path=remote_dataset_path,
        use_existing_remote_dataset=use_existing_remote_dataset,
        training_args=training_args or {},
        command_override=command_override,
        log_callback=on_log,
        stage_callback=on_stage,
        cancel_checker=lambda: bool(job.get("cancel_requested")),
      )
      job["remote_detached"] = True
      job["execution_backend"] = result.get("execution_backend", "tmux")
      job["safe_to_close_web"] = True
      job["monitor_state"] = result.get("monitor_state", "monitoring")
      job["remote_pid"] = result.get("remote_pid", "")
      job["remote_tmux_session"] = result.get("remote_tmux_session", job.get("remote_tmux_session", ""))
      job["remote_tmux_attach_command"] = result.get("remote_tmux_attach_command", job.get("remote_tmux_attach_command", ""))
      job["tmux_available"] = result.get("tmux_available", True)
      job["tmux_install"] = result.get("tmux_install", job.get("tmux_install", {}))
      job["remote_job_dir"] = result.get("remote_job_dir", "")
      job["remote_run_script"] = result.get("remote_run_script", "")
      job["remote_log_path"] = result.get("remote_log_path", "")
      job["remote_status_path"] = result.get("remote_status_path", "")
      job["remote_exit_code_path"] = result.get("remote_exit_code_path", "")
      job["remote_output_dir"] = result.get("remote_output_dir", "")
      job["remote_log_cursor"] = 0
      job["remote_result"] = {
        "remote_workspace_dir": result.get("remote_workspace_dir", ""),
        "remote_output_dir": result.get("remote_output_dir", ""),
        "remote_dataset_id": result.get("remote_dataset_id", ""),
        "remote_dataset_name": result.get("remote_dataset_name", ""),
        "remote_dataset_workspace": result.get("remote_dataset_workspace", ""),
        "upload": result.get("upload", {}),
        "download": result.get("download", {}),
      }
      update_artifacts()
      if job.get("cancel_requested"):
        job["status"] = "canceled"
        job["remote_stage"] = "canceled"
      else:
        job["status"] = "running"
        job["remote_stage"] = "remote_detached_running"
        append_job_log_line(job, "stdout", "[Tmux] Safe to close page. Remote training will continue inside the tmux session.\n")
        persist_job_state(job)
        start_remote_monitor_thread(job, remote_config)
    except Exception as exc:  # pragma: no cover - network/runtime dependent
      if job.get("cancel_requested") or getattr(exc, "code_hint", "") == "WGSC-JOB-CANCELED":
        job["status"] = "canceled"
        job["remote_stage"] = "canceled"
      else:
        job["status"] = "failed"
      append_job_log_line(job, "stderr", str(exc))
      merged_stderr = f"{job.get('stderr', '').rstrip()}\n{exc}".strip()
      job["stderr"] = merged_stderr[-12000:]
    finally:
      if not job.get("remote_detached") or is_job_terminal(job):
        job["finished_at"] = time.time()
      persist_job_state(job)

  threading.Thread(target=runner, daemon=True).start()


class ApiHandler(SimpleHTTPRequestHandler):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

  def end_headers(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    super().end_headers()

  def do_OPTIONS(self) -> None:
    self.send_response(HTTPStatus.NO_CONTENT)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    self.end_headers()

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    query = parse_qs(parsed.query)
    if parsed.path == "/api/health":
      json_response(self, {
        "ok": True,
        "root_dir": str(ROOT_DIR),
        "web_dir": str(WEB_DIR),
      })
      return
    if parsed.path == "/api/algorithms":
      algorithms = list_adapters()
      json_response(self, {"algorithms": algorithms, "validation": [validate_adapter(item) for item in algorithms]})
      return
    if parsed.path.startswith("/api/algorithms/"):
      family = parsed.path.split("/")[-1]
      adapter = get_adapter(family)
      if not adapter:
        json_response(self, {"error": f"Unknown algorithm family: {family}"}, status=404)
        return
      json_response(self, {"algorithm": adapter, "operations": supported_operations(adapter), "validation": validate_adapter(adapter)})
      return
    if parsed.path == "/api/jobs":
      json_response(self, {"jobs": [enrich_job(job) for job in JOBS.values()]})
      return
    if parsed.path == "/api/flow/data":
      try:
        result = inspect_flow_data(
          session_id=query.get("session_id", [""])[0],
          capture_id=query.get("capture_id", [""])[0],
          family=query.get("family", [""])[0],
        )
        json_response(self, result)
      except Exception as exc:
        error_response(
          self,
          code="WGSC-FLOW-DATA-001",
          step="flow_data",
          message=str(exc),
          status=400,
        )
      return
    if parsed.path == "/api/results/discover":
      limit = safe_int(query.get("limit", ["30"])[0], 30, minimum=1, maximum=100)
      max_scan_dirs = safe_int(query.get("max_scan_dirs", ["1800"])[0], 1800, minimum=200, maximum=8000)
      results = discover_runtime_results(limit=limit, max_scan_dirs=max_scan_dirs)
      json_response(self, {
        "ok": True,
        "results": results,
        "latest": results[0] if results else None,
        "count": len(results),
      })
      return
    if parsed.path.startswith("/api/jobs/"):
      parts = parsed.path.strip("/").split("/")
      if len(parts) < 3:
        json_response(self, {"error": f"Unsupported endpoint: {parsed.path}"}, status=404)
        return
      job_id = parts[2]
      job = JOBS.get(job_id)
      if not job:
        json_response(self, {"error": f"Unknown job: {job_id}"}, status=404)
        return

      ensure_job_logging(job)

      if len(parts) == 3:
        json_response(self, enrich_job(job))
        return

      if len(parts) == 4 and parts[3] == "logs":
        if "cursor" in query:
          cursor = safe_int(query.get("cursor", ["0"])[0], 0, minimum=0, maximum=10_000_000_000)
          delta = read_job_log_since_cursor(job, cursor)
          json_response(self, {
            "ok": True,
            "job_id": job_id,
            "status": job.get("status", "-"),
            "cursor": delta["cursor"],
            "from_cursor": delta["from_cursor"],
            "log_lines": delta["lines"],
            "log_text": "".join(delta["lines"]),
            "truncated": delta["truncated"],
            "logs_download_url": f"/api/jobs/{job_id}/logs/download",
            "metrics_csv_url": f"/api/jobs/{job_id}/metrics.csv",
          })
          return

        page = safe_int(query.get("page", ["1"])[0], 1, minimum=1, maximum=100000)
        page_size = safe_int(query.get("page_size", ["20"])[0], 20, minimum=1, maximum=200)
        tail_lines = safe_int(query.get("tail_lines", ["120"])[0], 120, minimum=1, maximum=3000)
        metrics_page = build_metrics_page(job, page, page_size)
        log_tail = read_job_log_tail_lines(job, tail_lines)
        json_response(self, {
          "ok": True,
          "job_id": job_id,
          "status": job.get("status", "-"),
          "metrics_page": metrics_page,
          "log_tail_lines": log_tail,
          "logs_download_url": f"/api/jobs/{job_id}/logs/download",
          "metrics_csv_url": f"/api/jobs/{job_id}/metrics.csv",
        })
        return

      if len(parts) == 5 and parts[3] == "logs" and parts[4] == "download":
        log_file_value = str(job.get("log_file", "")).strip()
        if not log_file_value:
          json_response(self, {"error": f"No log file for job: {job_id}"}, status=404)
          return
        file_download_response(
          self,
          Path(log_file_value),
          content_type="text/plain; charset=utf-8",
          download_name=f"{job_id}.runtime.log",
        )
        return

      if len(parts) == 4 and parts[3] == "metrics.csv":
        csv_file_value = str(job.get("metrics_csv_file", "")).strip()
        if not csv_file_value:
          json_response(self, {"error": f"No metrics csv for job: {job_id}"}, status=404)
          return
        file_download_response(
          self,
          Path(csv_file_value),
          content_type="text/csv; charset=utf-8",
          download_name=f"{job_id}.metrics.csv",
        )
        return

      json_response(self, {"error": f"Unsupported endpoint: {parsed.path}"}, status=404)
      return
    super().do_GET()

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    length = int(self.headers.get("Content-Length", "0"))
    raw = self.rfile.read(length) if length else b"{}"
    try:
      payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as exc:
      error_response(
        self,
        code="WGSC-REQUEST-JSON-001",
        step="request",
        message="Invalid JSON payload.",
        reason=str(exc),
        status=400,
        manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
      )
      return

    if parsed.path.startswith("/api/jobs/") and "/results/" in parsed.path:
      parts = parsed.path.strip("/").split("/")
      job_id = parts[2] if len(parts) >= 3 else ""
      action = parts[4] if len(parts) == 5 and parts[3] == "results" else ""
      job = JOBS.get(job_id)
      if not job:
        json_response(self, {"ok": False, "error": f"Unknown job: {job_id}"}, status=404)
        return
      if action not in {"check", "download"}:
        json_response(self, {"ok": False, "error": f"Unsupported endpoint: {parsed.path}"}, status=404)
        return
      try:
        validate_completed_result_download_job(job)
        remote_config = result_download_remote_config(job, payload)
        if action == "check":
          result = check_completed_result_download(job, remote_config)
          json_response(self, {"ok": True, "check": result, "job": enrich_job(job)})
          return
        result = start_completed_result_download(job, remote_config)
        json_response(self, result)
        return
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-JOB-RESULTS-REMOTE-001",
          step="job",
          message=str(exc),
          status=400,
          details={"job_id": job_id, "stage": exc.stage},
        )
        return
      except Exception as exc:
        error_response(
          self,
          code="WGSC-JOB-RESULTS-001",
          step="job",
          message=str(exc),
          status=400,
          details={"job_id": job_id},
        )
        return

    if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/delete"):
      parts = parsed.path.strip("/").split("/")
      job_id = parts[2] if len(parts) >= 3 else ""
      job = JOBS.get(job_id)
      if not job:
        json_response(self, {"ok": False, "error": f"Unknown job: {job_id}"}, status=404)
        return
      if not is_job_terminal(job):
        error_response(
          self,
          code="WGSC-JOB-DELETE-RUNNING",
          step="job",
          message="Only completed, failed, or canceled job records can be removed. Cancel running jobs first.",
          status=400,
          details={"job_id": job_id, "status": job.get("status", "")},
        )
        return
      try:
        removed = remove_job_record(job_id, require_terminal=True)
      except Exception as exc:
        error_response(
          self,
          code="WGSC-JOB-DELETE-001",
          step="job",
          message=str(exc),
          status=400,
          details={"job_id": job_id},
        )
        return
      json_response(self, {
        "ok": True,
        "code": "WGSC-JOB-RECORD-REMOVED",
        "removed": removed,
        "remaining": len(JOBS),
      })
      return

    if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
      parts = parsed.path.strip("/").split("/")
      job_id = parts[2] if len(parts) >= 3 else ""
      job = JOBS.get(job_id)
      if not job:
        json_response(self, {"ok": False, "error": f"Unknown job: {job_id}"}, status=404)
        return

      status = str(job.get("status", "")).strip().lower()
      if status in {"completed", "failed", "canceled"}:
        json_response(self, {"ok": True, "job": enrich_job(job), "message": f"Job is already {status}."})
        return

      job["cancel_requested"] = True
      append_job_log_line(job, "stderr", "[Cancel] User requested job cancellation.\n")
      if job.get("remote_detached"):
        remote_config = payload.get("remote") if isinstance(payload.get("remote"), dict) else job.get("_remote_config")
        if not isinstance(remote_config, dict) or not str(remote_config.get("password", "")).strip():
          job["monitor_state"] = "needs_remote_config"
          persist_job_state(job)
          error_response(
            self,
            code="WGSC-JOB-CANCEL-REMOTE-CONFIG",
            step="job",
            message="Remote credentials are required to cancel this detached remote job.",
            status=400,
            details={"job_id": job_id},
          )
          return
        try:
          cancel_remote_detached_job(
            remote_config=remote_config,
            remote_job_dir=str(job.get("remote_job_dir", "")),
            remote_pid=str(job.get("remote_pid", "")),
            remote_tmux_session=str(job.get("remote_tmux_session", "")),
          )
        except Exception as exc:
          job["cancel_requested"] = False
          append_job_log_line(job, "stderr", f"[Cancel] Failed to cancel detached remote job: {exc}\n")
          persist_job_state(job)
          error_response(
            self,
            code=getattr(exc, "code_hint", "") or "WGSC-JOB-CANCEL-REMOTE-001",
            step="job",
            message=str(exc),
            status=500,
            details={"job_id": job_id},
          )
          return
        job["status"] = "canceled"
        job["remote_stage"] = "canceled"
        job["monitor_state"] = "completed"
        job["return_code"] = 130
        job["finished_at"] = time.time()
        persist_job_state(job)
        json_response(self, {
          "ok": True,
          "code": "WGSC-JOB-CANCELED",
          "job": enrich_job(job),
        })
        return

      job["status"] = "canceled"
      job["remote_stage"] = "canceled"
      process = job.get("_process")
      if process is not None:
        try:
          if process.poll() is None:
            process.terminate()
        except Exception as exc:
          append_job_log_line(job, "stderr", f"[Cancel] Failed to terminate local process: {exc}\n")
      json_response(self, {
        "ok": True,
        "code": "WGSC-JOB-CANCELED",
        "job": enrich_job(job),
      })
      persist_job_state(job)
      return

    if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/reattach"):
      parts = parsed.path.strip("/").split("/")
      job_id = parts[2] if len(parts) >= 3 else ""
      job = JOBS.get(job_id)
      if not job:
        json_response(self, {"ok": False, "error": f"Unknown job: {job_id}"}, status=404)
        return
      if not job.get("remote_detached"):
        json_response(self, {"ok": True, "job": enrich_job(job), "message": "Job is not detached."})
        return
      remote_config = payload.get("remote") if isinstance(payload.get("remote"), dict) else {}
      if not str(remote_config.get("password", "")).strip():
        error_response(
          self,
          code="WGSC-JOB-REATTACH-REMOTE-CONFIG",
          step="job",
          message="Remote credentials are required to reattach detached job monitoring.",
          status=400,
          details={"job_id": job_id},
        )
        return
      try:
        validate_remote_config(remote_config)
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-JOB-REATTACH-CONFIG",
          step="job",
          message=str(exc),
          status=400,
          details={"stage": exc.stage},
        )
        return
      job["monitor_state"] = "monitoring"
      job["remote_stage"] = "reattaching_monitor"
      job["_remote_config"] = dict(remote_config)
      persist_job_state(job)
      start_remote_monitor_thread(job, remote_config)
      json_response(self, {
        "ok": True,
        "code": "WGSC-JOB-REATTACHED",
        "job": enrich_job(job),
      })
      return

    if parsed.path == "/api/flow/reset":
      try:
        result = reset_flow(payload)
        json_response(self, result)
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-FLOW-RESET-001",
          step="flow_reset",
          message=str(exc),
          status=400,
          details={"stage": exc.stage},
        )
      except Exception as exc:
        error_response(
          self,
          code="WGSC-FLOW-RESET-001",
          step="flow_reset",
          message=str(exc),
          status=500,
        )
      return

    if parsed.path == "/api/flow/data/delete":
      try:
        result = delete_flow_data_stage(payload)
        json_response(self, result)
      except Exception as exc:
        error_response(
          self,
          code="WGSC-FLOW-DATA-DELETE-001",
          step="flow_data",
          message=str(exc),
          status=400,
        )
      return

    if parsed.path == "/api/jobs/clear":
      try:
        result = clear_job_records(payload.get("statuses"))
        json_response(self, result)
      except Exception as exc:
        error_response(
          self,
          code="WGSC-JOBS-CLEAR-001",
          step="job",
          message=str(exc),
          status=400,
        )
      return

    if parsed.path == "/api/export-scene":
      try:
        result = build_scene_package(
          input_path=payload["input_path"],
          output_dir=payload["output_dir"],
          scene_id=payload["scene_id"],
          title=payload.get("title", payload["scene_id"]),
          representation=payload["representation"],
          algorithm_family=payload.get("algorithm_family", "unknown"),
          extra_metadata={
            "preprocess": payload.get("preprocess", {}),
            "editor": payload.get("editor", {}),
            "viewerBackend": payload.get("viewer_backend", "webgl2"),
          },
        )
        manifest_path = Path(result["manifest_path"])
        if ROOT_DIR in manifest_path.parents or manifest_path == ROOT_DIR:
          web_manifest_path = "/" + str(manifest_path.relative_to(ROOT_DIR)).replace("\\", "/")
        else:
          web_manifest_path = str(manifest_path)
        share_url = f"{payload.get('web_base_url', '')}/web/?manifest={web_manifest_path}" if payload.get("web_base_url") else web_manifest_path
        json_response(self, {
          "ok": True,
          "result": result,
          "manifest_url": web_manifest_path,
          "share_url": share_url,
        })
      except Exception as exc:
        json_response(self, {"error": str(exc)}, status=400)
      return

    if parsed.path == "/api/adapters/update":
      family = payload.get("family")
      if not family:
        json_response(self, {"error": "family is required"}, status=400)
        return
      adapter = get_adapter(family)
      if not adapter:
        json_response(self, {"error": f"Unknown algorithm family: {family}"}, status=404)
        return
      updated = update_adapter_override(
        family,
        {
          "repo_path": payload.get("repo_path"),
          "default_cwd": payload.get("default_cwd"),
          "repo_url": payload.get("repo_url"),
        },
      )
      json_response(self, {"ok": True, "adapter": updated, "validation": validate_adapter(updated)})
      return

    if parsed.path == "/api/adapters/validate":
      family = payload.get("family")
      adapter = get_adapter(family) if family else None
      if not adapter:
        error_response(
          self,
          code="WGSC-STEP2-ADAPTER-404",
          step="step2",
          message=f"Unknown algorithm family: {family}",
          status=404,
          manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
          next_action="Select a valid algorithm family from the dropdown and retry.",
        )
        return
      json_response(self, {
        "ok": True,
        "code": "WGSC-STEP2-ADAPTER-OK",
        "step": "step2",
        "validation": validate_adapter(adapter),
      })
      return

    if parsed.path == "/api/environment-check":
      family = payload.get("family", "")
      report = environment_check(family or None)
      json_response(self, {
        "ok": True,
        "code": "WGSC-STEP1-RUNTIME-OK" if report.get("runtime_ready") else "WGSC-STEP1-RUNTIME-FAIL",
        "step": "step1",
        "report": report,
      })
      return

    if parsed.path == "/api/remote-check":
      try:
        remote_config_input = extract_remote_config_input(payload)
        family = str(payload.get("algorithm_family", "")).strip()
        check_colmap_required = effective_colmap_preflight_required(payload)
        result = remote_preflight_check(
          remote_config=remote_config_input,
          timeout_seconds=int(payload.get("timeout_seconds", 20) or 20),
          family=family,
          include_datasets=True,
          check_colmap_required=check_colmap_required,
        )
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-STEP4-SSH-UNKNOWN-001",
          step="step4",
          message=str(exc),
          reason=f"stage={exc.stage or 'unknown'}",
          status=400,
          details={"stage": exc.stage or "unknown"},
          manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
          next_action="Fix the remote configuration or SSH connectivity and run 'Check SSH' again.",
        )
        return
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP4-SSH-UNKNOWN-001",
          step="step4",
          message=f"Remote SSH preflight failed: {exc}",
          status=400,
          manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
        )
        return

      raw_datasets = result.get("datasets")
      datasets: list[Dict[str, Any]] = [item for item in raw_datasets if isinstance(item, dict)] if isinstance(raw_datasets, list) else []
      result["datasets"] = _annotate_datasets_with_training_coverage(datasets, family_scope=family)

      json_response(self, {
        "ok": True,
        "code": "WGSC-STEP4-SSH-OK",
        "step": "step4",
        "result": result,
      })
      return

    if parsed.path == "/api/run-remote-algorithm/preview":
      try:
        preview = build_remote_algorithm_preview(payload)
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-STEP5-PREVIEW-001",
          step="preview",
          message=str(exc),
          reason=f"stage={exc.stage or 'preview'}",
          status=400,
          details={"stage": exc.stage or "preview"},
          next_action="Fix the remote configuration or command inputs, then preview again.",
        )
        return
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP5-PREVIEW-001",
          step="preview",
          message=str(exc),
          status=400,
          next_action="Fix the algorithm, dataset, output, or remote configuration, then preview again.",
        )
        return

      json_response(self, {
        "ok": True,
        "code": "WGSC-STEP5-PREVIEW-OK",
        "step": "preview",
        "preview": preview,
      })
      return

    if parsed.path == "/api/run-remote-algorithm":
      family = payload.get("algorithm_family", "")
      if not family:
        error_response(
          self,
          code="WGSC-STEP5-PAYLOAD-001",
          step="step5",
          message="algorithm_family is required",
          status=400,
          manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
        )
        return

      definition = get_adapter(family)
      if not definition:
        error_response(
          self,
          code="WGSC-STEP5-ADAPTER-404",
          step="step5",
          message=f"Unknown algorithm family: {family}",
          status=400,
          manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
        )
        return

      operation = payload.get("operation", "train")
      try:
        command_template = operation_command_template(definition, operation)
      except ValueError as exc:
        error_response(
          self,
          code="WGSC-STEP5-OP-UNSUPPORTED-001",
          step="step5",
          message=str(exc),
          status=400,
          details={"family": family, "operation": operation},
          manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
          next_action="Switch operation/family or update adapter template and retry.",
        )
        return

      session_id = str(payload.get("session_id", "default-session"))
      capture_id = str(payload.get("capture_id", "")).strip()
      dataset_name = str(payload.get("dataset_name", "")).strip()
      auto_materialize = bool(payload.get("auto_materialize", True))
      auto_colmap = bool(payload.get("auto_colmap", True))
      use_existing_remote_dataset = bool(payload.get("use_existing_remote_dataset", False))
      auto_colmap = effective_auto_colmap(auto_colmap, use_existing_remote_dataset)
      remote_dataset_id = str(payload.get("remote_dataset_id", "")).strip()
      remote_dataset_path = str(payload.get("remote_dataset_path", "")).strip()
      workspace_input = str(payload.get("workspace", "")).strip()
      materialized_result = None
      workspace_path: Path | None = None

      if use_existing_remote_dataset:
        if not remote_dataset_id and not remote_dataset_path:
          error_response(
            self,
            code="WGSC-STEP5-DATASET-SELECT-001",
            step="step5",
            message="Choose an existing remote dataset or provide remote_dataset_path before running Step 5.",
            status=400,
            manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
          )
          return
        auto_materialize = False
        auto_colmap = False
      else:
        if auto_materialize and not workspace_input:
          try:
            materialized_result = materialize_stream_session(
              session_id,
              payload.get("title", session_id),
              capture_id=capture_id,
              dataset_name=dataset_name or str(payload.get("title", "")).strip() or session_id,
            )
            workspace_input = materialized_result["dataset_root"]
            dataset_name = dataset_name or str(materialized_result.get("dataset_name", "")).strip()
            capture_id = capture_id or str(materialized_result.get("capture_id", "")).strip()
          except Exception as exc:
            error_response(
              self,
              code="WGSC-STEP3-MATERIALIZE-001",
              step="step3",
              message=f"Failed to materialize session {session_id}: {exc}",
              status=400,
              manual_anchor="#6-%E5%88%86%E6%AD%A5%E6%B5%81%E7%A8%8B%E8%B0%83%E8%AF%95%E5%85%9C%E5%BA%95",
            )
            return

        resolved_workspace = resolve_project_path(workspace_input)
        if not resolved_workspace:
          error_response(
            self,
            code="WGSC-STEP5-WORKSPACE-001",
            step="step5",
            message="workspace is required (or enable auto_materialize, or choose existing remote dataset)",
            status=400,
            manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
          )
          return

        workspace_path = Path(resolved_workspace).resolve()
        if not workspace_path.exists() or not workspace_path.is_dir():
          error_response(
            self,
            code="WGSC-STEP5-WORKSPACE-002",
            step="step5",
            message=f"workspace directory not found: {workspace_path}",
            status=400,
            manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
          )
          return

      requested_output_dir = payload.get("output_dir", "")
      resolved_output_dir = resolve_project_path(requested_output_dir)
      if not resolved_output_dir:
        resolved_output_dir = default_run_output_dir(session_id, family)
      Path(resolved_output_dir).mkdir(parents=True, exist_ok=True)

      remote_config_input = extract_remote_config_input(payload)

      try:
        validated_remote = validate_remote_config(remote_config_input)
      except RemoteExecutionError as exc:
        error_response(
          self,
          code=exc.code_hint or "WGSC-STEP4-CONFIG-001",
          step="step4",
          message=str(exc),
          reason=f"stage={exc.stage or 'config'}",
          status=400,
          details={"stage": exc.stage or "config"},
          manual_anchor="#4.3-Remote-Training-Config",
        )
        return

      require_preflight = bool(payload.get("require_remote_check", True))
      preflight_report = None
      if require_preflight:
        try:
          preflight_report = remote_preflight_check(
            remote_config=validated_remote,
            timeout_seconds=20,
            family=family,
            include_datasets=True,
            check_colmap_required=auto_colmap,
          )
        except RemoteExecutionError as exc:
          error_response(
            self,
            code=exc.code_hint or "WGSC-STEP4-SSH-UNKNOWN-001",
            step="step4",
            message=str(exc),
            reason=f"stage={exc.stage or 'unknown'}",
            status=400,
            details={"stage": exc.stage or "unknown"},
            manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
            next_action="Run Step 4 SSH check, fix the issue, then retry Step 5.",
          )
          return

      remote_checkpoint_path = str(payload.get("remote_checkpoint_path", payload.get("checkpoint_path", "")))
      input_path = str(payload.get("input_path", ""))
      source_path = str(payload.get("source", ""))
      workspace_for_template = (
        str(workspace_path)
        if workspace_path
        else (remote_dataset_path or (f"remote-dataset/{remote_dataset_id}" if remote_dataset_id else ""))
      )

      remote_format_args = {
        "input_path": input_path,
        "output_dir": resolved_output_dir,
        "workspace": workspace_for_template,
        "checkpoint_path": remote_checkpoint_path,
        "source": source_path or workspace_for_template,
        **_training_format_args(payload),
      }

      confirmed_ok, confirmed_message, confirmed_details = validate_path_confirmation_payload(
        payload,
        command_template=command_template,
        expected_checkpoint_path=remote_checkpoint_path,
        expected_output_dir=resolved_output_dir,
      )
      if not confirmed_ok:
        error_response(
          self,
          code="WGSC-STEP5-CONFIRM-001",
          step="step5",
          message=confirmed_message,
          status=400,
          details=confirmed_details,
          manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
          next_action="Confirm checkpoint_path/output_dir in UI and retry Step 5.",
        )
        return

      missing_inputs = missing_template_fields(command_template, remote_format_args)
      if missing_inputs:
        error_response(
          self,
          code="WGSC-STEP5-TEMPLATE-001",
          step="step5",
          message=(
            f"{family} operation {operation} is missing required inputs: "
            + ", ".join(missing_inputs)
          ),
          status=400,
          details={"missing_fields": missing_inputs, "command_template": command_template},
          manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
        )
        return

      command_override = str(payload.get("command_override", "")).strip()
      requested_job_id = str(payload.get("job_id", payload.get("preview_job_id", ""))).strip()
      job_id = requested_job_id if requested_job_id and requested_job_id not in JOBS else str(uuid.uuid4())
      job_tmux_session = build_remote_tmux_session_name(family=family, job_id=job_id)
      job = {
        "id": job_id,
        "status": "queued",
        "algorithm_family": family,
        "representation": definition.get("representation", "sh"),
        "operation": "remote_train",
        "requested_operation": operation,
        "command": command_override or command_template,
        "command_override": command_override,
        "created_at": time.time(),
        "workspace": workspace_for_template,
        "output_dir": resolved_output_dir,
        "session_id": session_id,
        "capture_id": capture_id,
        "dataset_name": dataset_name,
        "use_existing_remote_dataset": use_existing_remote_dataset,
        "remote_dataset_id": remote_dataset_id,
        "remote_dataset_path": remote_dataset_path,
        "repo_path": definition.get("repo_path", ""),
        "cwd": definition.get("default_cwd", ""),
        "remote": sanitize_remote_config(validated_remote),
        "execution_backend": "tmux",
        "remote_tmux_session": job_tmux_session,
        "remote_tmux_attach_command": build_remote_tmux_attach_command(validated_remote, job_tmux_session),
        "tmux_available": None,
        "tmux_install": {
          "policy": "submit_time_mamba_or_sudo_n",
          "uses_password_sudo": False,
        },
        "remote_stage": "queued",
        "remote_detached": False,
        "safe_to_close_web": False,
        "monitor_state": "queued",
        "metrics": {},
        "step_result": {
          "step": "step5",
          "code": "WGSC-STEP5-QUEUED",
          "message": "Remote job queued.",
        },
      }
      ensure_job_logging(job)
      JOBS[job_id] = job
      persist_job_state(job)
      prune_job_history()

      start_remote_job_thread(
        job,
        remote_config=validated_remote,
        local_workspace_dir=str(workspace_path) if workspace_path else None,
        local_output_dir=resolved_output_dir,
        command_template=command_template,
        checkpoint_path=remote_checkpoint_path,
        input_path=input_path,
        source_path=source_path,
        session_id=session_id,
        auto_colmap=auto_colmap,
        dataset_name=dataset_name,
        remote_dataset_id=remote_dataset_id,
        remote_dataset_path=remote_dataset_path,
        use_existing_remote_dataset=use_existing_remote_dataset,
        training_args=_training_format_args(payload),
        command_override=command_override,
      )
      json_response(
        self,
        {
          "ok": True,
          "code": "WGSC-STEP5-QUEUED",
          "step": "step5",
          "job": enrich_job(job),
          "materialized": materialized_result,
          "remote_check": preflight_report,
          "remote_detached": bool(job.get("remote_detached")),
          "execution_backend": job.get("execution_backend", "tmux"),
          "remote_pid": job.get("remote_pid", ""),
          "remote_tmux_session": job.get("remote_tmux_session", ""),
          "remote_tmux_attach_command": job.get("remote_tmux_attach_command", ""),
          "tmux_available": job.get("tmux_available"),
          "tmux_install": job.get("tmux_install", {}),
          "remote_log_path": job.get("remote_log_path", ""),
          "remote_status_path": job.get("remote_status_path", ""),
          "safe_to_close_web": bool(job.get("safe_to_close_web")),
          "monitor_state": job.get("monitor_state", "queued"),
        },
        status=202,
      )
      return

    if parsed.path == "/api/run-algorithm":
      family = payload["algorithm_family"]
      definition = get_adapter(family)
      if not definition:
        json_response(self, {"error": f"Unknown algorithm family: {family}"}, status=400)
        return

      operation = payload.get("operation", "train")
      operation_config = definition.get("operations", {}).get(operation, {})
      command_template = operation_config.get("template")
      if not operation_config.get("enabled"):
        json_response(self, {"error": f"Operation {operation} is not enabled for {family}"}, status=400)
        return
      if not command_template:
        json_response(self, {"error": f"Algorithm {family} operation {operation} does not have a command template"}, status=400)
        return

      resolved_repo = resolve_workspace_path(payload.get("repo_path") or definition.get("repo_path", ""))
      resolved_cwd = resolve_workspace_path(payload.get("cwd") or definition.get("default_cwd") or resolved_repo)
      if "python main.py" in command_template and not resolved_cwd:
        json_response(
          self,
          {
            "error": (
              f"{family} requires repo_path/default_cwd for operation {operation}. "
              "Current command is python main.py, but no working directory was configured."
            )
          },
          status=400,
        )
        return

      format_args = {
        "input_path": payload.get("input_path", ""),
        "output_dir": payload.get("output_dir", ""),
        "workspace": payload.get("workspace", ""),
        "checkpoint_path": payload.get("checkpoint_path", ""),
        "repo_path": resolved_repo,
        "source": payload.get("source", payload.get("workspace", "")),
        **_training_format_args(payload),
      }

      confirmed_ok, confirmed_message, confirmed_details = validate_path_confirmation_payload(
        payload,
        command_template=command_template,
        expected_checkpoint_path=str(format_args.get("checkpoint_path", "")),
        expected_output_dir=str(format_args.get("output_dir", "")),
      )
      if not confirmed_ok:
        error_response(
          self,
          code="WGSC-STEP5-CONFIRM-001",
          step="step5",
          message=confirmed_message,
          status=400,
          details=confirmed_details,
          manual_anchor="#5-%E4%B8%80%E9%94%AE%E6%B5%81%E7%A8%8B%E6%8E%A8%E8%8D%90",
          next_action="Confirm checkpoint_path/output_dir in UI and retry.",
        )
        return

      missing_inputs = missing_template_fields(command_template, format_args)
      if missing_inputs:
        json_response(
          self,
          {
            "error": (
              f"{family} operation {operation} is missing required inputs: "
              + ", ".join(missing_inputs)
            ),
            "missing_fields": missing_inputs,
            "command_template": command_template,
          },
          status=400,
        )
        return

      requirement_spec = adapter_requirement_spec(definition)
      missing_modules = find_missing_python_modules(requirement_spec.get("python_modules", []))
      if missing_modules:
        cuda_toolkit = detect_cuda_toolkit()
        dependency_hint = ""
        if any(module in missing_modules for module in ("diff_gaussian_rasterization", "simple_knn")) and not cuda_toolkit.get("toolkit_ready"):
          dependency_hint = (
            "Missing CUDA Toolkit (nvcc/CUDA_HOME). "
            "Install CUDA Toolkit, set CUDA_HOME, and then reinstall extension modules."
          )
        json_response(
          self,
          {
            "error": f"Missing Python dependencies for {family}: {', '.join(missing_modules)}",
            "missing_modules": missing_modules,
            "python_executable": sys.executable,
            "install_commands": requirement_spec.get("install_commands", {}),
            "cuda_toolkit": cuda_toolkit,
            "hint": dependency_hint,
          },
          status=400,
        )
        return

      command = strip_empty_repo_path_flag(command_template.format(**format_args), resolved_repo)
      try:
        command = sanitize_formatted_command(command_template, command, format_args)
      except Exception:
        pass
      job_id = str(uuid.uuid4())
      job = {
        "id": job_id,
        "status": "queued",
        "algorithm_family": family,
        "representation": definition["representation"],
        "operation": operation,
        "command": command,
        "cwd": resolved_cwd,
        "created_at": time.time(),
        "repo_path": resolved_repo,
        "output_dir": payload.get("output_dir", ""),
        "preprocess": payload.get("preprocess", {}),
        "editor": payload.get("editor", {}),
        "viewer_backend": payload.get("viewer_backend", "webgl2"),
        "metrics": {},
      }
      ensure_job_logging(job)
      JOBS[job_id] = job
      prune_job_history()
      start_job_thread(job, command=command, cwd=job["cwd"])
      json_response(self, {"ok": True, "job": enrich_job(job)}, status=202)
      return

    if parsed.path == "/api/stream-frame":
      session_id = payload.get("session_id", "default-session")
      capture_id = str(payload.get("capture_id", "")).strip()
      family = payload.get("algorithm_family", "")
      if not payload.get("image_data"):
        error_response(
          self,
          code="WGSC-STEP3-PAYLOAD-001",
          step="step3",
          message="image_data is required",
          status=400,
          manual_anchor="#6-%E5%88%86%E6%AD%A5%E6%B5%81%E7%A8%8B%E8%B0%83%E8%AF%95%E5%85%9C%E5%BA%95",
        )
        return
      try:
        frame_info = save_stream_frame(
          session_id=session_id,
          image_data=payload["image_data"],
          filename=payload.get("filename", f"{int(time.time() * 1000)}.png"),
          capture_id=capture_id,
        )
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP3-FRAME-SAVE-001",
          step="step3",
          message=f"Failed to save frame: {exc}",
          status=400,
          manual_anchor="#9-%E5%B8%B8%E8%A7%81%E9%94%99%E8%AF%AF%E7%A0%81%E4%B8%8E%E8%A7%A3%E5%86%B3%E6%96%B9%E6%A1%88",
        )
        return

      job = None
      adapter = get_adapter(family) if family else None
      if adapter:
        resolved_repo = resolve_workspace_path(payload.get("repo_path") or adapter.get("repo_path", ""))
        resolved_cwd = resolve_workspace_path(payload.get("cwd") or adapter.get("default_cwd") or resolved_repo)
        operation = "process_frame"
        operation_config = adapter.get("operations", {}).get(operation, {})
        command_template = operation_config.get("template")
        if operation_config.get("enabled") and command_template:
          job_id = str(uuid.uuid4())
          command = command_template.format(
            input_path=frame_info["input_path"],
            output_dir=str((STREAM_DIR / session_id / "output").resolve()),
            workspace=payload.get("workspace", ""),
            checkpoint_path=payload.get("checkpoint_path", ""),
            repo_path=resolved_repo,
            source=frame_info["input_path"],
          )
          command = strip_empty_repo_path_flag(command, resolved_repo)
          try:
            command = sanitize_formatted_command(command_template, command, {
              "input_path": frame_info["input_path"],
              "output_dir": str((STREAM_DIR / session_id / "output").resolve()),
              "workspace": payload.get("workspace", ""),
              "checkpoint_path": payload.get("checkpoint_path", ""),
              "repo_path": resolved_repo,
              "source": frame_info["input_path"],
            })
          except Exception:
            pass
          job = {
            "id": job_id,
            "status": "queued",
            "algorithm_family": family,
            "representation": adapter["representation"],
            "operation": operation,
            "command": command,
            "cwd": resolved_cwd,
            "created_at": time.time(),
            "repo_path": resolved_repo,
            "metrics": {},
            "stream_session_id": session_id,
            "output_dir": str((STREAM_DIR / session_id / "output").resolve()),
            "result_url": frame_info["output_url"],
          }
          ensure_job_logging(job)
          JOBS[job_id] = job
          prune_job_history()
          start_job_thread(job, command=command, cwd=job["cwd"])

      stream_artifacts = read_runtime_artifacts(str((STREAM_DIR / session_id / "output").resolve()), adapter.get("representation") if adapter else None)

      json_response(self, {
        "ok": True,
        "session_id": session_id,
        "capture_id": frame_info.get("capture_id", capture_id),
        "input_url": frame_info["input_url"],
        "output_url": stream_artifacts.get("result_url", frame_info["output_url"]),
        "result_url": stream_artifacts.get("result_url"),
        "result_urls": stream_artifacts.get("result_urls", []),
        "render_images": stream_artifacts.get("render_images", []),
        "render_image_count": stream_artifacts.get("render_image_count", 0),
        "viewer_url": stream_artifacts.get("viewer_url"),
        "job": enrich_job(job) if job else None,
      }, status=202 if job else 200)
      return

    if parsed.path == "/api/materialize-session":
      session_id = payload.get("session_id", "default-session")
      try:
        result = materialize_stream_session(
          session_id,
          payload.get("title"),
          capture_id=str(payload.get("capture_id", "")).strip(),
          dataset_name=str(payload.get("dataset_name", "")).strip(),
        )
        json_response(self, {"ok": True, "code": "WGSC-STEP3-MATERIALIZE-OK", "step": "step3", "result": result})
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP3-MATERIALIZE-001",
          step="step3",
          message=str(exc),
          status=400,
          manual_anchor="#6-%E5%88%86%E6%AD%A5%E6%B5%81%E7%A8%8B%E8%B0%83%E8%AF%95%E5%85%9C%E5%BA%95",
        )
      return

    if parsed.path == "/api/prepare-colmap-workspace":
      session_id = payload.get("session_id", "default-session")
      family = payload.get("algorithm_family", "vanilla-3dgs")
      try:
        result = prepare_colmap_workspace(
          session_id,
          family,
          payload.get("repo_path"),
          capture_id=str(payload.get("capture_id", "")).strip(),
          dataset_name=str(payload.get("dataset_name", "")).strip(),
        )
        json_response(self, {"ok": True, "code": "WGSC-STEP3-WORKSPACE-OK", "step": "step3", "result": result})
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP3-WORKSPACE-001",
          step="step3",
          message=str(exc),
          status=400,
          manual_anchor="#6-%E5%88%86%E6%AD%A5%E6%B5%81%E7%A8%8B%E8%B0%83%E8%AF%95%E5%85%9C%E5%BA%95",
        )
      return

    if parsed.path == "/api/run-capture-pipeline":
      session_id = payload.get("session_id", "default-session")
      family = payload.get("algorithm_family", "vanilla-3dgs")
      output_dir = payload.get("output_dir", "")
      repo_path = resolve_workspace_path(payload.get("repo_path", ""))
      checkpoint_path = payload.get("checkpoint_path", "")
      execute = bool(payload.get("execute_immediately", True))
      try:
        pipeline = build_capture_pipeline(
          session_id,
          family,
          output_dir=output_dir,
          repo_path=repo_path,
          checkpoint_path=checkpoint_path,
          training_args=_training_format_args(payload),
        )
        job = None
        if execute:
          adapter = get_adapter(family)
          job_id = str(uuid.uuid4())
          pipeline_command = (
            f'cmd /c "{pipeline["script_path_cmd"]}"'
            if os.name == "nt"
            else f"bash {pipeline['script_path']}"
          )
          job = {
            "id": job_id,
            "status": "queued",
            "algorithm_family": family,
            "representation": adapter.get("representation", "sh") if adapter else "sh",
            "operation": "capture_pipeline",
            "command": pipeline_command,
            "cwd": pipeline["repo_path"] or resolve_workspace_path(adapter.get("default_cwd") if adapter else "") or pipeline["workspace"]["workspace_root"],
            "created_at": time.time(),
            "repo_path": pipeline["repo_path"],
            "output_dir": pipeline["output_dir"],
            "workspace": pipeline["workspace"]["workspace_root"],
            "metrics": {},
            "pipeline": pipeline,
          }
          ensure_job_logging(job)
          JOBS[job_id] = job
          prune_job_history()
          start_job_thread(job, command=job["command"], cwd=job["cwd"])
        json_response(self, {"ok": True, "pipeline": pipeline, "job": enrich_job(job) if job else None}, status=202 if job else 200)
      except Exception as exc:
        error_response(
          self,
          code="WGSC-STEP5-PIPELINE-001",
          step="step5",
          message=str(exc),
          status=400,
          manual_anchor="#6-%E5%88%86%E6%AD%A5%E6%B5%81%E7%A8%8B%E8%B0%83%E8%AF%95%E5%85%9C%E5%BA%95",
        )
      return

    if parsed.path == "/api/load-result":
      result_path = str(payload.get("path", "") or payload.get("result_path", "") or "").strip()
      family = str(payload.get("family", "")).strip() or None
      representation = str(payload.get("representation", "")).strip() or None

      if not result_path:
        json_response(self, {
          "ok": False,
          "type": "",
          "error": "Missing path parameter",
          "reason": "Missing path parameter",
        }, status=400)
        return

      result = load_result_path(result_path, family=family, representation=representation)
      status = 200 if result.get("ok") else 400
      json_response(self, result, status=status)
      return

    if parsed.path == "/api/load-ply":
      ply_path = str(payload.get("ply_path", "")).strip()
      representation = str(payload.get("representation", "")).strip() or None

      if not ply_path:
        json_response(self, {
          "ok": False,
          "error": "Missing ply_path parameter",
        }, status=400)
        return

      result = load_ply_file(ply_path, representation)
      status = 200 if result.get("ok") else 400
      json_response(self, result, status=status)
      return

    json_response(self, {"error": f"Unsupported endpoint: {parsed.path}"}, status=404)


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the Gaussian Encoding web server.")
  parser.add_argument("--host", default="127.0.0.1")
  parser.add_argument("--port", type=int, default=8080)
  args = parser.parse_args()

  load_persisted_jobs()
  server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
  print(f"Serving web app at http://{args.host}:{args.port}/web/")
  server.serve_forever()


if __name__ == "__main__":
  main()
