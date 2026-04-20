# Web Remote Training Manual (EN)

## 1. Goal and Implemented Scope

This manual matches the current code behavior:

1. Upload photos from the web page to the local server.
2. Auto-materialize a local capture session into a dataset.
3. Start remote training through built-in SSH/SFTP.
4. Auto-download remote outputs back to local output_dir.
5. Auto-poll job status and auto-render results in the web UI.

Current remote-mode limits:

- Family support is capability-driven (enabled operation + command template), not hardcoded.
- Operation is selected dynamically and validated against adapter templates.
- Authentication: SSH username + password.

---

## 2. Remote Configuration Guide (HAC++)

### 2.1 Local controller

- The local machine only hosts the web UI, uploads data, submits jobs, and displays results.
- It does not need the HAC++ training environment.
- It still needs to run `web/server/api_server.py`.
- Install the required remote dependency:

```bash
python -m pip install paramiko
```

### 2.2 Remote trainer

- Reachable from the local machine via SSH.
- The account has write access to the remote workspace and output directories.
- HAC-plus-main, training scripts, and the runtime environment are ready.
- The remote repo path must be able to run the HAC++ training command directly, for example:

```bash
python train.py -s <workspace> --eval -m <output_dir>
```

### 2.3 Recommended machine and environment

| Item | Recommended value | Notes |
| --- | --- | --- |
| GPU | RTX 4090 24GB | Best default choice; enough for many scenes on a single card |
| Safer GPU | RTX A6000 48GB / RTX 6000 Ada 48GB / A100 40GB+ | Better for large scenes, long sequences, or heavier jobs |
| CPU | 8 cores or more | 16+ cores is more comfortable |
| RAM | 32GB or more | 64GB is better for large scenes |
| Disk | 200GB+ free space | Reserve space for data, workspace, output, and bitstreams |
| OS | Ubuntu 20.04/22.04 | HAC++ README reports Ubuntu 20.04.1 in testing |
| CUDA | 11.8 or the version matched by the environment file | Keep driver and runtime consistent |

- For the current repository, prefer `HAC-plus-main/environment.yml`:
  - Python 3.10
  - PyTorch 2.2.*
  - torchvision 0.17.*
  - torchaudio 2.2.*
  - pytorch-cuda 12.1
- The HAC++ README also reports a tested setup of Ubuntu 20.04.1 / CUDA 11.8 / gcc 9.4.0.
- Do not use legacy Python 3.8 / PyTorch 1.2 style environments for this branch.
- The compression and return path uses GPCC / `tmc3`, so the remote machine must be able to execute `tmc3` directly.

### 2.4 SSH notes

- Current remote mode only supports SSH username + password; private-key fields are not used.
- `Remote Host` can be an IP or hostname; `Remote Port` defaults to 22.
- `Remote Repo Path` must point to a real HAC-plus-main checkout on the remote machine, and the account must be able to read/write it.
- `Remote Workspace Root` and `Remote Output Root` must be writable directories, preferably under `/tmp/web_scan/...` or `~/web_scan/...`.
- `Remote Activate Command` runs in a non-interactive shell, so keep it to a single line.
  - Example: `source ~/.bashrc && conda activate HAC_env`
  - If conda is not initialized in `~/.bashrc`, use: `source ~/miniconda3/etc/profile.d/conda.sh && conda activate HAC_env`
- If the interpreter path is already fixed, you can set `Remote Python` to a full path such as `/home/ubuntu/miniconda3/envs/HAC_env/bin/python`.
- Avoid paths with spaces, non-ASCII characters, or special shell characters unless you have already verified them manually on the remote host.
- The training account does not need sudo/root access; write access to workspace and output is enough.
- If the remote host is behind a firewall or security group, the SSH port must be reachable from the local machine.
- Jump-host / bastion workflows are not modeled yet, so do not treat them as supported.

### 2.5 Preflight checklist

If all items below pass, it is safe to use `One-click Upload and Remote Train`.

1. Local dependency is available: `python -m pip install paramiko`.
1. SSH login works from the local machine: `ssh <user>@<host> -p <port>`.
1. Remote GPU is visible: `nvidia-smi`.
1. Remote Python and PyTorch work: `python -V` and `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`.
1. Remote conda or virtualenv activation works: `source ~/.bashrc && conda activate HAC_env` (or your own activation command).
1. Remote repo path is executable: `cd <repo_path> && python train.py -h`.
1. Remote write permissions are valid: `touch <workspace_root>/.write_test && rm <workspace_root>/.write_test` and `touch <output_root>/.write_test && rm <output_root>/.write_test`.
1. `tmc3` is callable: `which tmc3` and `tmc3 --help`.
1. Disk space is sufficient: `df -h`.
1. Only after all checks pass should you run the full upload -> train -> return flow.

### 2.6 Current support policy

- Remote entry is visible for all families.
- Actual execution support depends on whether the selected operation has an enabled command template.
- Unsupported combinations return `WGSC-STEP5-OP-UNSUPPORTED-001` with a clear fix hint.

---

## 3. Start Service

Run from repo root:

```bash
python3 web/server/api_server.py --host 127.0.0.1 --port 8080
```

Open:

- <http://127.0.0.1:8080/web/>

---

## 4. UI Field Guide

The left workflow is collapsible and state-driven:

- Completed/locked sections auto-collapse.
- The active section auto-expands.
- Manual open/close by users has priority and is remembered.
- Local path is grouped under `Local Debug (Optional)` and does not interrupt remote-first flow.

### 4.1 Runtime Config

- API Base URL: e.g. `http://127.0.0.1:8080`
- Algorithm Family: select target family (not limited to hac-plus-plus)
- Repo Path / Default CWD: optional for local-debug flow

### 4.2 Capture

- Stream Session ID: recommended per scene (e.g. session-demo)
- Upload Image: upload file
- Or use Start Camera + Send Frame

### 4.3 Remote Training Config

- Remote Host
- Remote Port (default 22)
- Remote Username / Remote Password
- Remote Repo Path (remote HAC-plus-main path)
- Remote Workspace Root (e.g. /tmp/web_scan/workspaces)
- Remote Output Root (e.g. /tmp/web_scan/outputs)
- Remote Python (default python3)
- Remote Activate Command (optional)
  - Example: source ~/.bashrc && conda activate HAC_env

### 4.4 Remote Run

- One-click Upload and Remote Train
- Refresh Jobs
- Export Package

### 4.5 System Board (execution monitor)

- `Execution Monitor -> Job Monitor`:
  - Job cards are now collapsible summary cards (status, ID, operation, key metrics first).
  - The list is height-limited with internal scrolling to avoid page overflow.
  - Clicking `View Logs` auto-expands `Job Logs and Metrics` and selects the matching job.
- `Execution Monitor -> Job Logs and Metrics`:
  - Top toolbar: `Select Job` and `Refresh Log`.
  - Download actions: `Download .log` and `Download metrics.csv`.
  - `Copy Raw Log` to copy current tail content quickly.
  - Split layout: left metrics table (paged), right raw log tail.
  - `Tail Lines` selector supports 80/120/200/400.

### 4.6 Local Debug (optional)

- Session tools and local-job tools are kept only for fallback debugging.
- Remote-only users can skip this group.

---

## 5. One-click Flow (recommended)

1. Click Check Runtime.
2. Ensure the selected family passes Adapter Capability validation.
3. Upload an image (or start camera).
4. Fill Remote Training fields and run Check SSH.
5. Click One-click Upload and Remote Train (selected operation must have remote template).
6. Track states:
Remote Connecting -> Remote Uploading -> Remote Training -> Remote Downloading -> Remote Completed
7. After completion, Processed Result auto-switches to viewer or fallback image.
8. In `System Board -> Job Monitor`, click `View Logs` to jump to `Job Logs and Metrics` and inspect paged metrics, raw log tail, downloads, and quick copy.

Notes:

- One-click first uploads the current frame, then auto-materializes session.
- If output_dir is empty, default local path is `/web/generated/runs/{session}/{family}`.

---

## 6. Step-by-step Fallback (debug)

Use manual flow when troubleshooting:

1. Send Frame (upload only)
2. Materialize Session
3. Submit Job (local mode) or call remote API
4. Refresh Jobs and inspect stderr/metrics

---

## 7. Backend API (remote mode)

### 7.1 Submit remote job

- POST /api/run-remote-algorithm

Request example:

```json
{
  "algorithm_family": "hac-plus-plus",
  "operation": "train",
  "session_id": "session-demo",
  "auto_materialize": true,
  "output_dir": "/web/generated/runs/session-demo/hac-plus-plus",
  "checkpoint_path": "",
  "remote": {
    "host": "192.168.1.20",
    "port": 22,
    "username": "ubuntu",
    "password": "***",
    "repo_path": "/home/ubuntu/HAC-plus-main",
    "workspace_root": "/tmp/web_scan/workspaces",
    "output_root": "/tmp/web_scan/outputs",
    "python": "python3",
    "activate_cmd": "source ~/.bashrc && conda activate HAC_env"
  }
}
```

Response:

- Unified job object (queued/running/completed/failed)
- materialized info if auto-materialization was used

### 7.2 Query jobs

- GET /api/jobs
- GET /api/jobs/{jobId}

### 7.3 Logs and metrics download (new)

- GET /api/jobs/{jobId}/logs?page=1&page_size=20&tail_lines=120
  - Returns paged metrics rows and raw log tail.
- GET /api/jobs/{jobId}/logs/download
  - Downloads persisted runtime `.log`.
- GET /api/jobs/{jobId}/metrics.csv
  - Downloads persisted metrics history `.csv`.

---

## 8. Step1-5 Completion Criteria

### Step 1 Runtime Check

- Success: `/api/environment-check` returns `runtime_ready=true`.
- Failure: any required runtime check fails.
- Typical codes: `WGSC-STEP1-RUNTIME-FAIL`, `WGSC-REQUEST-JSON-001`.

### Step 2 Adapter Capability

- Success: adapter `validation.is_ready=true` and at least one enabled operation exists.
- Failure: unknown family or no usable operation.
- Typical codes: `WGSC-STEP2-ADAPTER-OK`, `WGSC-STEP2-ADAPTER-404`.

### Step 3 Capture First Frame

- Success: `/api/stream-frame` returns `ok=true` with `input_url`.
- Failure: missing `image_data`, frame save failure, or materialization failure.
- Typical codes: `WGSC-STEP3-PAYLOAD-001`, `WGSC-STEP3-FRAME-SAVE-001`, `WGSC-STEP3-MATERIALIZE-001`.

### Step 4 SSH Remote Check

- Success: `/api/remote-check` returns `WGSC-STEP4-SSH-OK`.
- Failure: invalid config, missing paramiko, SSH connectivity/auth failure, invalid remote paths, non-executable remote python.
- Typical codes: `WGSC-STEP4-CONFIG-001`, `WGSC-STEP4-DEPENDENCY-001`, `WGSC-STEP4-SSH-NET-001`, `WGSC-STEP4-SSH-AUTH-001`, `WGSC-STEP4-PATH-REPO-001`, `WGSC-STEP4-PATH-WRITE-001`, `WGSC-STEP4-REMOTE-PY-001`.

### Step 5 Start Remote Job

- Success: `/api/run-remote-algorithm` returns `WGSC-STEP5-QUEUED` with `job.id`.
- Failure: unknown family, unsupported operation template, missing/non-existing workspace, missing template args.
- Typical codes: `WGSC-STEP5-ADAPTER-404`, `WGSC-STEP5-OP-UNSUPPORTED-001`, `WGSC-STEP5-WORKSPACE-001`, `WGSC-STEP5-WORKSPACE-002`, `WGSC-STEP5-TEMPLATE-001`.

---

## 9. Error Codes and Fixes

| Code | Step | Meaning | Action |
| --- | --- | --- | --- |
| WGSC-REQUEST-JSON-001 | Request | Invalid JSON payload | Fix request body format |
| WGSC-STEP1-RUNTIME-FAIL | Step1 | Required runtime check failed | Open Runtime panel and fix failed required items |
| WGSC-STEP2-ADAPTER-404 | Step2 | Unknown algorithm family | Re-select family in dropdown |
| WGSC-STEP3-PAYLOAD-001 | Step3 | `image_data` missing | Re-upload frame or camera capture |
| WGSC-STEP3-FRAME-SAVE-001 | Step3 | Frame save failed | Check write permission of `web/generated` |
| WGSC-STEP3-MATERIALIZE-001 | Step3 | Session materialization failed | Ensure uploaded input frames exist |
| WGSC-STEP4-DEPENDENCY-001 | Step4 | `paramiko` missing | Run `python -m pip install paramiko` |
| WGSC-STEP4-CONFIG-001 | Step4 | Remote config invalid/missing fields | Fill host/user/password/port/paths |
| WGSC-STEP4-SSH-NET-001 | Step4 | SSH network unreachable | Verify host/port/firewall/security-group |
| WGSC-STEP4-SSH-AUTH-001 | Step4 | SSH authentication failed | Verify username/password/port |
| WGSC-STEP4-PATH-REPO-001 | Step4 | Remote repo path not found | Use actual repo directory on remote host |
| WGSC-STEP4-PATH-WRITE-001 | Step4 | Remote workspace/output not writable | Switch to writable path like `/tmp/web_scan/...` |
| WGSC-STEP4-REMOTE-PY-001 | Step4 | Remote python not executable | Fix `remote.python` or activate command |
| WGSC-STEP5-OP-UNSUPPORTED-001 | Step5 | No remote template for selected operation | Switch operation or update adapter template |
| WGSC-STEP5-WORKSPACE-001 | Step5 | Workspace missing | Enable `auto_materialize` or provide workspace |
| WGSC-STEP5-WORKSPACE-002 | Step5 | Workspace does not exist | Fix local workspace path |
| WGSC-STEP5-TEMPLATE-001 | Step5 | Missing required command template arguments | Fill missing fields in request |
| WGSC-STEP5-PIPELINE-001 | Step5 | Local fallback pipeline failed | Inspect job logs and stderr |

---

## 10. Return-and-Render Rules

Server scans local output_dir and emits:

- scene_manifest.json -> manifest_url + viewer_url
- point_cloud.ply or point_cloud/iteration_x/point_cloud.ply -> point_cloud_url + viewer_url
- latest.png -> result_url fallback
- metrics.json -> job.metrics

In addition, server persists job logs at `web/generated/job_logs/<job_id>/`:

- `runtime.log`
- `metrics.csv`

---

## 11. Security Notes

- Current version uses username/password auth for controlled environments.
- Do not commit passwords into repository files.
- Job payloads are sanitized and do not return plaintext password.

---

## 12. Version Mapping

This manual corresponds to:

- New backend API: `/api/remote-check`
- `/api/run-remote-algorithm` now supports capability-driven family/operation checks
- Step1-5 cards now show success/failure with error codes
