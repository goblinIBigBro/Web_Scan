from __future__ import annotations

import json
import shlex
import stat
import threading
import os
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict


class RemoteExecutionError(RuntimeError):
  def __init__(self, message: str, *, code_hint: str = "", stage: str = ""):
    super().__init__(message)
    self.code_hint = code_hint
    self.stage = stage


def _load_paramiko():
  try:
    import paramiko
  except Exception as exc:  # pragma: no cover - depends on runtime environment
    raise RemoteExecutionError(
      "Missing dependency: paramiko. Install it with `python -m pip install paramiko`.",
      code_hint="WGSC-STEP4-DEPENDENCY-001",
      stage="dependency",
    ) from exc
  return paramiko


def _normalize_remote_path(path_value: str) -> str:
  raw = str(path_value or "").strip().replace("\\", "/")
  if not raw:
    raise RemoteExecutionError(
      "Remote path cannot be empty.",
      code_hint="WGSC-STEP4-CONFIG-001",
      stage="config",
    )
  return str(PurePosixPath(raw))


def validate_remote_config(config: Dict[str, Any]) -> Dict[str, Any]:
  host = str(config.get("host", "")).strip()
  username = str(config.get("username", "")).strip()
  password = str(config.get("password", ""))

  if not host:
    raise RemoteExecutionError("remote.host is required", code_hint="WGSC-STEP4-CONFIG-001", stage="config")
  if not username:
    raise RemoteExecutionError("remote.username is required", code_hint="WGSC-STEP4-CONFIG-001", stage="config")
  if not password:
    raise RemoteExecutionError("remote.password is required", code_hint="WGSC-STEP4-CONFIG-001", stage="config")

  try:
    port = int(config.get("port", 22))
  except Exception as exc:
    raise RemoteExecutionError("remote.port must be a valid integer", code_hint="WGSC-STEP4-CONFIG-001", stage="config") from exc
  if port <= 0 or port > 65535:
    raise RemoteExecutionError("remote.port must be in range 1..65535", code_hint="WGSC-STEP4-CONFIG-001", stage="config")

  remote_repo_path = _normalize_remote_path(config.get("repo_path", ""))
  remote_workspace_root = _normalize_remote_path(config.get("workspace_root", ""))
  remote_output_root = _normalize_remote_path(config.get("output_root", ""))

  remote_python = str(config.get("python", "python3")).strip() or "python3"
  remote_activate_cmd = str(config.get("activate_cmd", "")).strip()

  return {
    "host": host,
    "port": port,
    "username": username,
    "password": password,
    "repo_path": remote_repo_path,
    "workspace_root": remote_workspace_root,
    "output_root": remote_output_root,
    "python": remote_python,
    "activate_cmd": remote_activate_cmd,
  }


def _assert_remote_repo_exists(sftp, remote_repo_path: str) -> None:
  try:
    entry = sftp.stat(remote_repo_path)
  except Exception as exc:
    raise RemoteExecutionError(
      f"remote.repo_path not found: {remote_repo_path}",
      code_hint="WGSC-STEP4-PATH-REPO-001",
      stage="path",
    ) from exc
  if stat.S_ISDIR(entry.st_mode) is False:
    raise RemoteExecutionError(
      f"remote.repo_path is not a directory: {remote_repo_path}",
      code_hint="WGSC-STEP4-PATH-REPO-001",
      stage="path",
    )


def _assert_remote_path_writable(client, remote_path: str, label: str) -> None:
  marker = f".wgsc_preflight_{int(time.time() * 1000)}_{threading.get_ident()}"
  marker_path = str(PurePosixPath(remote_path) / marker)
  test_script = (
    f"mkdir -p {_quote(remote_path)}"
    f" && test -w {_quote(remote_path)}"
    f" && touch {_quote(marker_path)}"
    f" && rm -f {_quote(marker_path)}"
  )
  return_code = _run_remote_command(client, f"bash -lc {_quote(test_script)}", None)
  if return_code != 0:
    raise RemoteExecutionError(
      f"remote.{label} is not writable: {remote_path}",
      code_hint="WGSC-STEP4-PATH-WRITE-001",
      stage="path",
    )


def _assert_remote_python_available(client, remote_python: str) -> None:
  test_script = f"{_quote(remote_python)} --version >/dev/null 2>&1"
  return_code = _run_remote_command(client, f"bash -lc {_quote(test_script)}", None)
  if return_code != 0:
    raise RemoteExecutionError(
      f"remote.python is not executable: {remote_python}",
      code_hint="WGSC-STEP4-REMOTE-PY-001",
      stage="path",
    )


def _check_remote_command_available(client, command_name: str) -> bool:
  test_script = f"command -v {_quote(command_name)} >/dev/null 2>&1"
  return _run_remote_command(client, f"bash -lc {_quote(test_script)}", None) == 0


def _remote_colmap_runtime_setup_script() -> str:
  return (
    "OMP_NUM_THREADS_VALUE=\"${OMP_NUM_THREADS:-1}\""
    " && case \"$OMP_NUM_THREADS_VALUE\" in \"\"|*[!0-9]*|0) OMP_NUM_THREADS_VALUE=1 ;; esac"
    " && export OMP_NUM_THREADS=\"$OMP_NUM_THREADS_VALUE\""
    " && export QT_QPA_PLATFORM=xcb"
    " && if command -v vglrun >/dev/null 2>&1; then colmap_headless() { vglrun \"$@\"; }; else colmap_headless() { \"$@\"; }; fi"
  )


def _wrap_remote_colmap_headless_script(command_script: str) -> str:
  runtime_script = _remote_colmap_runtime_setup_script()
  return (
    "command -v xvfb-run >/dev/null 2>&1"
    f" && xvfb-run -a -s \"-screen 0 1280x1024x24\" bash -lc {_quote(runtime_script + ' && ' + command_script)}"
  )


def _check_remote_colmap_available(client) -> bool:
  test_script = _wrap_remote_colmap_headless_script(
    "command -v colmap >/dev/null 2>&1"
    " && colmap_headless colmap feature_extractor -h >/dev/null 2>&1"
  )
  return _run_remote_command(client, f"bash -lc {_quote(test_script)}", None) == 0


def _safe_int(value: Any, default: int = 0) -> int:
  try:
    return int(value)
  except Exception:
    return default


def _read_remote_json_file(sftp, remote_path: str) -> Dict[str, Any]:
  try:
    with sftp.open(remote_path, "r") as handle:
      raw = handle.read()
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}
  except Exception:
    return {}


def _remote_path_exists_sftp(sftp, remote_path: str) -> bool:
  try:
    sftp.stat(remote_path)
    return True
  except Exception:
    return False


def _remote_count_files_sftp(sftp, remote_dir: str) -> int:
  try:
    entries = sftp.listdir_attr(remote_dir)
  except Exception:
    return 0
  return sum(1 for item in entries if not stat.S_ISDIR(item.st_mode))


def _list_remote_datasets(
  sftp,
  *,
  workspace_root: str,
  family: str,
  max_items: int = 50,
) -> list[Dict[str, Any]]:
  dataset_base = PurePosixPath(workspace_root) / "datasets"
  if family:
    dataset_base = dataset_base / family
  dataset_base_str = str(dataset_base)

  try:
    entries = sftp.listdir_attr(dataset_base_str)
  except Exception:
    return []

  items: list[Dict[str, Any]] = []
  for entry in entries:
    if not stat.S_ISDIR(entry.st_mode):
      continue

    dataset_id = entry.filename
    dataset_dir = str(dataset_base / dataset_id)
    workspace_dir = str(PurePosixPath(dataset_dir) / "workspace")
    input_dir = str(PurePosixPath(workspace_dir) / "input")
    images_dir = str(PurePosixPath(workspace_dir) / "images")
    sparse_dir = str(PurePosixPath(workspace_dir) / "sparse" / "0")
    undistorted_marker = str(PurePosixPath(workspace_dir) / ".wgsc_colmap_undistorted.ok")

    manifest = {}
    for candidate in (
      str(PurePosixPath(dataset_dir) / "dataset_manifest.json"),
      str(PurePosixPath(dataset_dir) / "capture_session.json"),
      str(PurePosixPath(dataset_dir) / "workspace_manifest.json"),
    ):
      manifest = _read_remote_json_file(sftp, candidate)
      if manifest:
        break

    frame_count = _safe_int(manifest.get("frame_count"), 0)
    dataset_name = str(manifest.get("dataset_name") or manifest.get("title") or dataset_id)

    input_file_count = _remote_count_files_sftp(sftp, input_dir)
    images_file_count = _remote_count_files_sftp(sftp, images_dir)
    sparse_file_count = _remote_count_files_sftp(sftp, sparse_dir)
    has_raw_images = input_file_count > 0 or images_file_count > 0 or frame_count > 0
    has_sparse_model = sparse_file_count > 0
    has_undistorted = _remote_path_exists_sftp(sftp, undistorted_marker)

    stage_label = "raw_only"
    if has_sparse_model:
      stage_label = "sparse_ready"
    if has_sparse_model and has_undistorted:
      stage_label = "undistorted_ready"

    resolved_frame_count = frame_count or input_file_count or images_file_count

    items.append({
      "id": dataset_id,
      "name": dataset_name,
      "path": workspace_dir,
      "dataset_dir": dataset_dir,
      "session_id": str(manifest.get("session_id", "")),
      "capture_id": str(manifest.get("capture_id", "")),
      "frame_count": resolved_frame_count,
      "input_file_count": input_file_count,
      "images_file_count": images_file_count,
      "sparse_file_count": sparse_file_count,
      "has_input_images": has_raw_images,
      "has_sparse_model": has_sparse_model,
      "has_undistorted_marker": has_undistorted,
      "latest_marker": ".wgsc_colmap_undistorted.ok" if has_undistorted else "",
      "stage": {
        "raw": has_raw_images,
        "sparse": has_sparse_model,
        "undistorted": has_undistorted,
        "label": stage_label,
      },
      "stage_label": stage_label,
      "updated_at": _safe_int(getattr(entry, "st_mtime", 0), 0),
    })

  items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
  return items[: max(1, min(max_items, 200))]


def remote_preflight_check(
  *,
  remote_config: Dict[str, Any],
  timeout_seconds: int = 20,
  family: str = "",
  include_datasets: bool = True,
  check_colmap_required: bool = False,
) -> Dict[str, Any]:
  validated = validate_remote_config(remote_config)
  paramiko = _load_paramiko()

  client = paramiko.SSHClient()
  client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  sftp = None
  checks: list[Dict[str, Any]] = []

  try:
    try:
      client.connect(
        hostname=validated["host"],
        port=validated["port"],
        username=validated["username"],
        password=validated["password"],
        timeout=timeout_seconds,
        look_for_keys=False,
        allow_agent=False,
      )
      checks.append({
        "name": "ssh_connect",
        "ok": True,
        "message": "SSH connection established",
      })
    except paramiko.AuthenticationException as exc:
      raise RemoteExecutionError(
        "SSH authentication failed. Check remote username/password.",
        code_hint="WGSC-STEP4-SSH-AUTH-001",
        stage="auth",
      ) from exc
    except Exception as exc:
      raise RemoteExecutionError(
        f"SSH connection failed: {exc}",
        code_hint="WGSC-STEP4-SSH-NET-001",
        stage="connect",
      ) from exc

    sftp = client.open_sftp()
    _assert_remote_repo_exists(sftp, validated["repo_path"])
    checks.append({
      "name": "repo_path",
      "ok": True,
      "message": "Remote repo path exists",
      "path": validated["repo_path"],
    })

    _assert_remote_path_writable(client, validated["workspace_root"], "workspace_root")
    checks.append({
      "name": "workspace_root",
      "ok": True,
      "message": "Remote workspace root is writable",
      "path": validated["workspace_root"],
    })

    _assert_remote_path_writable(client, validated["output_root"], "output_root")
    checks.append({
      "name": "output_root",
      "ok": True,
      "message": "Remote output root is writable",
      "path": validated["output_root"],
    })

    _assert_remote_python_available(client, validated["python"])
    checks.append({
      "name": "remote_python",
      "ok": True,
      "message": "Remote python executable is available",
      "python": validated["python"],
    })

    xvfb_run_available = _check_remote_command_available(client, "xvfb-run")
    checks.append({
      "name": "remote_xvfb_run",
      "ok": xvfb_run_available,
      "message": "Remote xvfb-run executable is available" if xvfb_run_available else "Remote xvfb-run executable not found in PATH",
      "required": bool(check_colmap_required),
    })
    if check_colmap_required and not xvfb_run_available:
      raise RemoteExecutionError(
        "Remote xvfb-run is not available. Install Xvfb/xvfb-run before auto COLMAP workflow.",
        code_hint="WGSC-STEP5-COLMAP-TOOL-001",
        stage="colmap",
      )

    vglrun_available = _check_remote_command_available(client, "vglrun")
    checks.append({
      "name": "remote_vglrun",
      "ok": vglrun_available,
      "message": "Remote VirtualGL vglrun executable is available" if vglrun_available else "Remote VirtualGL vglrun not found in PATH; Xvfb fallback will be used",
      "required": False,
    })

    colmap_available = _check_remote_colmap_available(client)
    checks.append({
      "name": "remote_colmap",
      "ok": colmap_available,
      "message": "Remote colmap can run under Xvfb" if colmap_available else "Remote colmap failed headless preflight",
      "required": bool(check_colmap_required),
    })
    if check_colmap_required and not colmap_available:
      raise RemoteExecutionError(
        "Remote colmap cannot start under Xvfb. Install Xvfb/xvfb-run and ensure colmap is in PATH before auto COLMAP workflow.",
        code_hint="WGSC-STEP5-COLMAP-TOOL-001",
        stage="colmap",
      )

    datasets: list[Dict[str, Any]] = []
    if include_datasets:
      datasets = _list_remote_datasets(
        sftp,
        workspace_root=validated["workspace_root"],
        family=str(family or "").strip(),
      )

    return {
      "remote": sanitize_remote_config(validated),
      "checks": checks,
      "datasets": datasets,
      "summary": (
        f"SSH and remote path preflight checks passed. "
        f"Found {len(datasets)} reusable remote dataset(s)."
      ),
    }
  finally:
    try:
      if sftp is not None:
        sftp.close()
    except Exception:
      pass
    try:
      client.close()
    except Exception:
      pass


def sanitize_remote_config(config: Dict[str, Any]) -> Dict[str, Any]:
  return {
    "host": str(config.get("host", "")),
    "port": int(config.get("port", 22) or 22),
    "username": str(config.get("username", "")),
    "repo_path": str(config.get("repo_path", "")),
    "workspace_root": str(config.get("workspace_root", "")),
    "output_root": str(config.get("output_root", "")),
    "python": str(config.get("python", "python3") or "python3"),
    "activate_cmd": str(config.get("activate_cmd", "")),
    "has_password": bool(config.get("password")),
  }


def build_remote_paths(
  *,
  workspace_root: str,
  output_root: str,
  session_id: str,
  family: str,
  job_id: str,
) -> Dict[str, str]:
  workspace_dir = str(PurePosixPath(workspace_root) / session_id / family / job_id / "workspace")
  output_dir = str(PurePosixPath(output_root) / session_id / family / job_id / "output")
  return {
    "workspace_dir": workspace_dir,
    "output_dir": output_dir,
  }


def _quote(value: str) -> str:
  return shlex.quote(str(value))


def _sftp_mkdir_p(sftp, remote_dir: str) -> None:
  path = PurePosixPath(remote_dir)
  current = PurePosixPath("/") if path.is_absolute() else PurePosixPath(path.parts[0])
  start_index = 1 if path.is_absolute() else 1

  if not path.parts:
    return

  if path.is_absolute():
    try:
      sftp.stat("/")
    except Exception:
      pass

  for part in path.parts[start_index:]:
    current = current / part
    current_str = str(current)
    try:
      sftp.stat(current_str)
    except Exception:
      sftp.mkdir(current_str)


def _upload_directory(sftp, local_dir: Path, remote_dir: str) -> Dict[str, Any]:
  uploaded_files = 0
  uploaded_bytes = 0
  _sftp_mkdir_p(sftp, remote_dir)

  for root_raw, _, files in os.walk(local_dir):
    root = Path(root_raw)
    relative = root.relative_to(local_dir)
    remote_root = PurePosixPath(remote_dir)
    if str(relative) != ".":
      remote_root = remote_root / relative.as_posix()
      _sftp_mkdir_p(sftp, str(remote_root))
    for file_name in files:
      local_file = root / file_name
      remote_file = str(remote_root / file_name)
      sftp.put(str(local_file), remote_file)
      uploaded_files += 1
      try:
        uploaded_bytes += local_file.stat().st_size
      except OSError:
        pass

  return {
    "files": uploaded_files,
    "bytes": uploaded_bytes,
  }


def _download_directory(sftp, remote_dir: str, local_dir: Path) -> Dict[str, Any]:
  downloaded_files = 0
  downloaded_bytes = 0
  local_dir.mkdir(parents=True, exist_ok=True)

  def walk(remote_path: str, local_path: Path) -> None:
    nonlocal downloaded_files, downloaded_bytes
    try:
      entries = sftp.listdir_attr(remote_path)
    except Exception:
      return

    for entry in entries:
      remote_item = str(PurePosixPath(remote_path) / entry.filename)
      local_item = local_path / entry.filename
      if stat.S_ISDIR(entry.st_mode):
        local_item.mkdir(parents=True, exist_ok=True)
        walk(remote_item, local_item)
      else:
        local_item.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(remote_item, str(local_item))
        downloaded_files += 1
        downloaded_bytes += int(getattr(entry, "st_size", 0) or 0)

  walk(remote_dir, local_dir)
  return {
    "files": downloaded_files,
    "bytes": downloaded_bytes,
  }


def _read_stream(stream, channel: str, log_callback: Callable[[str, str], None] | None) -> None:
  for raw_line in iter(stream.readline, ""):
    if raw_line is None:
      break
    line = raw_line
    if isinstance(line, bytes):
      line = line.decode("utf-8", errors="replace")
    if not line:
      break
    if log_callback:
      log_callback(channel, line)
  stream.close()


def _run_remote_command(client, command: str, log_callback: Callable[[str, str], None] | None) -> int:
  stdin, stdout, stderr = client.exec_command(command, get_pty=True)
  stdin.close()

  stdout_thread = threading.Thread(target=_read_stream, args=(stdout, "stdout", log_callback), daemon=True)
  stderr_thread = threading.Thread(target=_read_stream, args=(stderr, "stderr", log_callback), daemon=True)
  stdout_thread.start()
  stderr_thread.start()
  return_code = stdout.channel.recv_exit_status()
  stdout_thread.join(timeout=1)
  stderr_thread.join(timeout=1)
  return return_code


def _run_remote_command_cancellable(
  client,
  command: str,
  log_callback: Callable[[str, str], None] | None,
  cancel_checker: Callable[[], bool] | None = None,
) -> int:
  stdin, stdout, stderr = client.exec_command(command, get_pty=True)
  stdin.close()

  stdout_thread = threading.Thread(target=_read_stream, args=(stdout, "stdout", log_callback), daemon=True)
  stderr_thread = threading.Thread(target=_read_stream, args=(stderr, "stderr", log_callback), daemon=True)
  stdout_thread.start()
  stderr_thread.start()

  channel = stdout.channel
  while not channel.exit_status_ready():
    if cancel_checker and cancel_checker():
      if log_callback:
        log_callback("stderr", "[Cancel] Cancellation requested. Closing remote command channel.\n")
      try:
        channel.close()
      except Exception:
        pass
      stdout_thread.join(timeout=1)
      stderr_thread.join(timeout=1)
      return 130
    time.sleep(0.25)

  return_code = channel.recv_exit_status()
  stdout_thread.join(timeout=1)
  stderr_thread.join(timeout=1)
  return return_code


def sanitize_formatted_command(command_template: str, formatted_command: str, format_args: Dict[str, Any]) -> str:
  """Remove flags from a formatted command when their template placeholders were empty.

  This scans `command_template` for occurrences like "--flag {key}" and if
  `format_args[key]` is empty, removes the corresponding flag token (and
  variants like "--flag=") from `formatted_command`.
  """
  import re
  # map flags -> placeholder keys (e.g. '--model-dir' -> 'checkpoint_path')
  flag_key_map: Dict[str, str] = {}
  for m in re.finditer(r"\{([^}]+)\}", command_template):
    key = m.group(1).strip()
    left = command_template[: m.start()].rstrip()
    last = re.search(r"([^\s]+)\s*$", left)
    if not last:
      continue
    last_token = last.group(1)
    if last_token.endswith("="):
      flag = last_token[:-1]
    else:
      flag = last_token
    if flag.startswith("-"):
      flag_key_map[flag] = key

  if not flag_key_map:
    return formatted_command

  # Tokenize and remove tokens that match flags whose placeholder value is empty.
  tokens = shlex.split(formatted_command)
  cleaned: list[str] = []
  i = 0
  n = len(tokens)
  while i < n:
    tok = tokens[i]
    removed = False
    for flag, key in flag_key_map.items():
      if not str(format_args.get(key, "")).strip():
        # match forms: "--flag", "--flag=", "--flag=VALUE"
        if tok == flag or tok.startswith(flag + "=") or tok == flag + "=":
          removed = True
          break
        # also handle when flag is a token followed immediately by another flag
        if tok == flag and (i + 1 >= n or tokens[i + 1].startswith("-")):
          removed = True
          break
    if removed:
      i += 1
      continue
    cleaned.append(tok)
    i += 1

  try:
    return shlex.join(cleaned)
  except AttributeError:
    return " ".join(shlex.quote(t) for t in cleaned)


def _normalize_dataset_id(dataset_name: str, job_id: str) -> str:
  raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(dataset_name or "").strip()).strip("-_")
  base = raw[:48] if raw else "dataset"
  return f"{base}-{job_id[:8]}"


def _remote_directory_exists(client, remote_dir: str) -> bool:
  script = f"test -d {_quote(remote_dir)}"
  return _run_remote_command(client, f"bash -lc {_quote(script)}", None) == 0


def _remote_has_sparse_workspace(client, workspace_dir: str) -> bool:
  sparse_dir = str(PurePosixPath(workspace_dir) / "sparse" / "0")
  marker_path = str(PurePosixPath(workspace_dir) / ".wgsc_colmap_undistorted.ok")
  script = (
    f"test -f {_quote(marker_path)}"
    f" && test -d {_quote(sparse_dir)}"
    f" && [ \"$(find {_quote(sparse_dir)} -maxdepth 1 -type f | wc -l)\" -gt 0 ]"
  )
  return _run_remote_command(client, f"bash -lc {_quote(script)}", None) == 0


def _build_remote_colmap_script(workspace_dir: str) -> str:
  input_dir = str(PurePosixPath(workspace_dir) / "input")
  images_dir = str(PurePosixPath(workspace_dir) / "images")
  distorted_dir = str(PurePosixPath(workspace_dir) / "distorted")
  database_path = str(PurePosixPath(distorted_dir) / "database.db")
  distorted_sparse = str(PurePosixPath(distorted_dir) / "sparse")
  sparse_root = str(PurePosixPath(workspace_dir) / "sparse")
  distorted_sparse_0 = str(PurePosixPath(distorted_sparse) / "0")
  sparse_0 = str(PurePosixPath(sparse_root) / "0")
  marker_path = str(PurePosixPath(workspace_dir) / ".wgsc_colmap_undistorted.ok")

  steps = [
    "command -v colmap >/dev/null 2>&1",
    f"rm -f {_quote(marker_path)} {_quote(database_path)}",
    f"mkdir -p {_quote(distorted_sparse)} {_quote(sparse_root)}",
    (
      f"colmap_headless colmap feature_extractor "
      f"--database_path {_quote(database_path)} "
      f"--image_path {_quote(input_dir)} "
      "--ImageReader.single_camera 1 --ImageReader.camera_model SIMPLE_PINHOLE"
    ),
    f"colmap_headless colmap sequential_matcher --database_path {_quote(database_path)}",
    (
      f"colmap_headless colmap mapper "
      f"--database_path {_quote(database_path)} "
      f"--image_path {_quote(input_dir)} "
      f"--output_path {_quote(distorted_sparse)}"
    ),
    f"rm -rf {_quote(images_dir)} {_quote(sparse_root)}",
    f"mkdir -p {_quote(images_dir)} {_quote(sparse_root)} {_quote(sparse_0)}",
    (
      f"colmap_headless colmap image_undistorter "
      f"--image_path {_quote(input_dir)} "
      f"--input_path {_quote(distorted_sparse_0)} "
      f"--output_path {_quote(workspace_dir)} "
      "--output_type COLMAP"
    ),
    f"if [ -d {_quote(sparse_root)} ]; then find {_quote(sparse_root)} -maxdepth 1 -type f -exec mv -f {{}} {_quote(sparse_0)} \\; ; fi",
    f"touch {_quote(marker_path)}",
  ]
  return _wrap_remote_colmap_headless_script(" && ".join(steps))


def run_remote_algorithm(
  *,
  remote_config: Dict[str, Any],
  local_workspace_dir: str,
  local_output_dir: str,
  session_id: str,
  family: str,
  job_id: str,
  command_template: str,
  checkpoint_path: str,
  input_path: str,
  source_path: str,
  auto_colmap: bool = True,
  dataset_name: str = "",
  remote_dataset_id: str = "",
  remote_dataset_path: str = "",
  use_existing_remote_dataset: bool = False,
  training_args: Dict[str, Any] | None = None,
  log_callback: Callable[[str, str], None] | None = None,
  stage_callback: Callable[[str], None] | None = None,
  cancel_checker: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
  validated = validate_remote_config(remote_config)

  workspace_dir: Path | None = None
  if not use_existing_remote_dataset:
    workspace_dir = Path(local_workspace_dir).expanduser().resolve()
    if not workspace_dir.exists() or not workspace_dir.is_dir():
      raise RemoteExecutionError(f"Local workspace directory not found: {workspace_dir}")

  output_dir = Path(local_output_dir).expanduser().resolve()
  output_dir.mkdir(parents=True, exist_ok=True)

  remote_paths = build_remote_paths(
    workspace_root=validated["workspace_root"],
    output_root=validated["output_root"],
    session_id=session_id,
    family=family,
    job_id=job_id,
  )

  resolved_dataset_id = str(remote_dataset_id or "").strip()
  resolved_dataset_name = str(dataset_name or "").strip() or resolved_dataset_id

  if use_existing_remote_dataset:
    selected_path = str(remote_dataset_path or "").strip()
    if selected_path:
      remote_workspace_for_command = str(PurePosixPath(selected_path))
      if not resolved_dataset_id:
        resolved_dataset_id = PurePosixPath(remote_workspace_for_command).parent.name
    elif resolved_dataset_id:
      remote_workspace_for_command = str(
        PurePosixPath(validated["workspace_root"]) / "datasets" / family / resolved_dataset_id / "workspace"
      )
    else:
      raise RemoteExecutionError(
        "No remote dataset was selected. Choose an existing dataset before running this operation.",
        code_hint="WGSC-STEP5-DATASET-SELECT-001",
        stage="dataset",
      )
  else:
    resolved_dataset_id = resolved_dataset_id or _normalize_dataset_id(resolved_dataset_name, job_id)
    resolved_dataset_name = resolved_dataset_name or resolved_dataset_id
    remote_workspace_for_command = str(
      PurePosixPath(validated["workspace_root"]) / "datasets" / family / resolved_dataset_id / "workspace"
    )

  remote_command = command_template.format(
    input_path=input_path,
    output_dir=remote_paths["output_dir"],
    workspace=remote_workspace_for_command,
    checkpoint_path=checkpoint_path,
    repo_path=validated["repo_path"],
    source=source_path or remote_workspace_for_command,
    **(training_args or {}),
  )

  format_args = {
    "input_path": input_path,
    "output_dir": remote_paths["output_dir"],
    "workspace": remote_workspace_for_command,
    "checkpoint_path": checkpoint_path,
    "repo_path": validated["repo_path"],
    "source": source_path or remote_workspace_for_command,
    **(training_args or {}),
  }
  try:
    remote_command = sanitize_formatted_command(command_template, remote_command, format_args)
  except Exception:
    pass

  if remote_command.lstrip().startswith("python "):
    remote_command = f"{validated['python']}{remote_command.lstrip()[len('python') :]}"

  paramiko = _load_paramiko()
  client = paramiko.SSHClient()
  client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  sftp = None

  try:
    def assert_not_cancelled() -> None:
      if cancel_checker and cancel_checker():
        raise RemoteExecutionError(
          "Remote job was canceled by user.",
          code_hint="WGSC-JOB-CANCELED",
          stage="canceled",
        )

    if stage_callback:
      stage_callback("connecting")
    client.connect(
      hostname=validated["host"],
      port=validated["port"],
      username=validated["username"],
      password=validated["password"],
      timeout=20,
      look_for_keys=False,
      allow_agent=False,
    )

    sftp = client.open_sftp()
    assert_not_cancelled()

    if use_existing_remote_dataset:
      if stage_callback:
        stage_callback("using_existing_dataset")
      if not _remote_directory_exists(client, remote_workspace_for_command):
        raise RemoteExecutionError(
          f"Selected remote dataset workspace not found: {remote_workspace_for_command}",
          code_hint="WGSC-STEP5-DATASET-SELECT-001",
          stage="dataset",
        )
      upload_info = {
        "files": 0,
        "bytes": 0,
        "skipped": True,
      }
    else:
      if stage_callback:
        stage_callback("uploading_workspace")
      upload_info = _upload_directory(sftp, workspace_dir, remote_paths["workspace_dir"])
      assert_not_cancelled()

      if stage_callback:
        stage_callback("saving_named_dataset")
      remote_dataset_dir = str(PurePosixPath(remote_workspace_for_command).parent)
      persist_script = (
        f"mkdir -p {_quote(remote_dataset_dir)}"
        f" && rm -rf {_quote(remote_workspace_for_command)}"
        f" && cp -a {_quote(remote_paths['workspace_dir'])} {_quote(remote_workspace_for_command)}"
      )
      persist_rc = _run_remote_command_cancellable(
        client,
        f"bash -lc {_quote(persist_script)}",
        log_callback,
        cancel_checker,
      )
      if persist_rc != 0:
        raise RemoteExecutionError(
          "Failed to persist named remote dataset workspace.",
          code_hint="WGSC-STEP5-DATASET-NAME-001",
          stage="dataset",
        )

    if auto_colmap:
      has_sparse = _remote_has_sparse_workspace(client, remote_workspace_for_command)
      if has_sparse:
        if log_callback:
          log_callback("stdout", f"[AutoCOLMAP] Skip: sparse workspace already exists at {remote_workspace_for_command}\n")
      else:
        if stage_callback:
          stage_callback("executing_remote_colmap")
        if not _check_remote_colmap_available(client):
          raise RemoteExecutionError(
            "Remote colmap is not available. Install colmap or configure PATH on remote host.",
            code_hint="WGSC-STEP5-COLMAP-TOOL-001",
            stage="colmap",
          )
        colmap_script = _build_remote_colmap_script(remote_workspace_for_command)
        colmap_rc = _run_remote_command_cancellable(
          client,
          f"bash -lc {_quote(colmap_script)}",
          log_callback,
          cancel_checker,
        )
        if colmap_rc != 0:
          raise RemoteExecutionError(
            "Remote COLMAP preprocessing failed.",
            code_hint="WGSC-STEP5-COLMAP-REMOTE-001",
            stage="colmap",
          )
        if stage_callback:
          stage_callback("remote_colmap_completed")
    elif use_existing_remote_dataset and log_callback:
      log_callback("stdout", f"[Dataset] Reusing existing remote dataset: {resolved_dataset_id or remote_workspace_for_command}\n")

    assert_not_cancelled()
    steps = [
      f"mkdir -p {_quote(remote_paths['output_dir'])}",
      f"cd {_quote(validated['repo_path'])}",
    ]
    if validated["activate_cmd"]:
      steps.append(validated["activate_cmd"])
    steps.append(remote_command)
    remote_script = " && ".join(steps)
    shell_command = f"bash -lc {_quote(remote_script)}"

    if stage_callback:
      stage_callback("executing_remote_command")
    return_code = _run_remote_command_cancellable(client, shell_command, log_callback, cancel_checker)
    if cancel_checker and cancel_checker():
      raise RemoteExecutionError(
        "Remote job was canceled by user.",
        code_hint="WGSC-JOB-CANCELED",
        stage="canceled",
      )

    if stage_callback:
      stage_callback("downloading_output")
    download_info = _download_directory(sftp, remote_paths["output_dir"], output_dir)

    if stage_callback:
      stage_callback("completed" if return_code == 0 else "failed")

    return {
      "return_code": return_code,
      "remote_workspace_dir": remote_workspace_for_command,
      "remote_output_dir": remote_paths["output_dir"],
      "remote_dataset_id": resolved_dataset_id,
      "remote_dataset_name": resolved_dataset_name,
      "remote_dataset_workspace": remote_workspace_for_command,
      "remote_command": remote_command,
      "upload": upload_info,
      "download": download_info,
    }
  finally:
    try:
      if sftp is not None:
        sftp.close()
    except Exception:
      pass
    try:
      client.close()
    except Exception:
      pass
