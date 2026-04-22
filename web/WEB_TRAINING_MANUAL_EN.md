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
- For auto COLMAP on a headless Linux host, install `xvfb`/`xvfb-run` and `virtualgl`/`vglrun`; the backend will run COLMAP inside Xvfb and use VirtualGL when available.
- The remote repo path must be able to run the HAC++ training command directly, for example:

```bash
python train.py -s <workspace> --eval -m <output_dir>
```

### 2.2.1 Headless COLMAP runtime

#### Basic principle

- Auto COLMAP is launched inside Xvfb (virtual X server) so it can run without a real desktop display.
- `xvfb-run` is required on the remote host for the headless COLMAP stage.
- `vglrun` is optional but recommended when you want VirtualGL to forward OpenGL to GPU-backed rendering.
- If only `colmap` is installed and Xvfb is missing, the COLMAP stage can still abort with `qt.qpa.xcb` / display-related errors.

#### VirtualGL / Xvfb Auto-Fallback Strategy

The backend automatically selects the optimal runtime environment:

1. **Priority 1: VirtualGL Mode** (best, requires GPU OpenGL forwarding)
   - Condition: `vglrun` available + `xvfb-run` available + GPU visible
   - Effect: COLMAP's OpenGL calls are forwarded to GPU via VirtualGL; best performance
   - Command: `xvfb-run -a ... vglrun colmap feature_extractor ...`

2. **Priority 2: Xvfb-only Mode** (fallback, CPU rendering)
   - Condition: `vglrun` unavailable, but `xvfb-run` available
   - Effect: COLMAP runs OpenGL on CPU inside virtual display; slower but functional
   - Command: `xvfb-run -a ... colmap feature_extractor ...`

3. **Failure State** (unsupported)
   - Condition: `xvfb-run` unavailable
   - Result: Error `WGSC-STEP5-COLMAP-TOOL-001` returned; Xvfb installation required

#### Environment variables at runtime

The backend sets the following before running COLMAP:

```bash
# Set OMP thread count (prevents over-concurrency; default 1)
export OMP_NUM_THREADS="1"

# Set Qt platform to xcb (X11 compatible mode)
export QT_QPA_PLATFORM=xcb
```

These settings ensure COLMAP initializes Qt graphics library correctly in a headless environment.

#### Installation guide

**Required on remote host**:

```bash
# Ubuntu 20.04 / 22.04
sudo apt-get update
sudo apt-get install -y xvfb

# Optional: GPU OpenGL forwarding (recommended for large scenes)
sudo apt-get install -y virtualgl
```

**Verify installation**:

```bash
# Check xvfb-run
command -v xvfb-run
xvfb-run -a colmap feature_extractor -h

# Check VirtualGL (if installed)
command -v vglrun
vglrun colmap feature_extractor -h
```

### 2.2.2 FCGS remote compression

- FCGS compression entrypoints directly consume existing 3DGS point clouds, but if your upstream data still has to be prepared from images or you want to run validation / scene-related flows, the remote host still needs COLMAP.
- The remote checkout must include `submodules/diff-gaussian-rasterization`. Use `git clone --recursive` or run `git submodule update --init --recursive` on the remote host.
- Use the updated Python 3.10 environment from [the FCGS remote guide](../FCGS-main/fcgs/README.md): Python 3.10, PyTorch 2.2.*, torchvision 0.17.*, pytorch-cuda 11.8, numpy 1.26.*, pillow 10.*, plyfile 1.1.*, tqdm 4.66.*, and lpips.
- FCGS runs directly from the repository root with the following entrypoints:

```bash
python encode_single_scene.py --lmd 1e-4 --ply_path_from <path/to/point_cloud.ply> --bit_path_to <path/to/bitstreams> --determ 1
python decode_single_scene.py --lmd 1e-4 --bit_path_from <path/to/bitstreams> --ply_path_to <path/to/point_cloud.ply>
python decode_single_scene_validate.py --lmd 1e-4 --bit_path_from <path/to/bitstreams> --ply_path_to <path/to/point_cloud.ply> --source_path <path/to/scene>
```

- Supported `--lmd` values are `1e-4`, `2e-4`, `4e-4`, `8e-4`, and `16e-4`.
- If `tmc3` is not on `PATH`, update the two fallback locations in [model/gpcc_utils.py](../FCGS-main/model/gpcc_utils.py) manually.
- Keep the `checkpoints/checkpoint_*.pkl` files in place; the selected `--lmd` chooses the corresponding checkpoint.

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
- For FCGS, prefer `FCGS-main/environment.yml`:
  - Python 3.10
  - PyTorch 2.2.*
  - torchvision 0.17.*
  - pytorch-cuda 11.8
  - numpy 1.26.* / pillow 10.* / plyfile 1.1.* / tqdm 4.66.* / lpips
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

1. **Local dependency**: `python -m pip install paramiko`.

2. **SSH connectivity**: `ssh <user>@<host> -p <port>`.
   - Verify direct login to remote host
   - If fails: Check host/port/username/password

3. **Remote GPU**: `nvidia-smi`.
   - Confirm GPU is visible and driver is functional
   - If fails: Check driver installation and cuda-toolkit version

4. **Remote Python and PyTorch**:
   ```bash
   python -V
   python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
   ```
   - Verify Python version ≥ 3.10
   - Verify PyTorch installed correctly and CUDA available

5. **Remote environment activation**: `source ~/.bashrc && conda activate HAC_env`.
   - Substitute your own activation command as needed
   - If fails: Check `.bashrc` or `~/.profile` initialization

6. **Remote repo executable**: `cd <repo_path> && python train.py -h`.
   - Verify repo path is correct and contains `train.py`
   - Verify Python can import project modules

7. **Remote write permissions**:
   ```bash
   touch <workspace_root>/.write_test && rm <workspace_root>/.write_test
   touch <output_root>/.write_test && rm <output_root>/.write_test
   ```
   - Confirm both directories are writable
   - If fails: Use writable paths like `/tmp/web_scan/...`

8. **Headless COLMAP tools**:
   ```bash
   command -v xvfb-run
   xvfb-run -a colmap feature_extractor -h
   ```
   - Verify `xvfb-run` is executable
   - Verify COLMAP can launch in virtual display
   - **If fails**: Run `sudo apt-get install -y xvfb`

9. **GPU OpenGL forwarding (optional but recommended)**:
   ```bash
   command -v vglrun
   vglrun colmap feature_extractor -h
   ```
   - Check if VirtualGL is available
   - If unavailable, system auto-falls back to Xvfb-only mode
   - **To enable**: Run `sudo apt-get install -y virtualgl`

10. **tmc3 compression tool**: `which tmc3 && tmc3 --help`.
    - Confirm tmc3 is on PATH (used by backend compression stage)
    - If fails: Install or configure GPCC toolchain

11. **Disk space**: `df -h`.
    - Confirm `/tmp` and data directories have sufficient space (200GB+ recommended)
    - Estimate: image data + workspace temp files + output results

12. **After all checks pass**: Click `Check SSH` button for remote verification, then `One-click Upload and Remote Train`.

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
- Failure: invalid config, missing paramiko, SSH connectivity/auth failure, invalid remote paths, non-executable remote python, or missing headless COLMAP runtime when COLMAP validation is required.
- Typical codes: `WGSC-STEP4-CONFIG-001`, `WGSC-STEP4-DEPENDENCY-001`, `WGSC-STEP4-SSH-NET-001`, `WGSC-STEP4-SSH-AUTH-001`, `WGSC-STEP4-PATH-REPO-001`, `WGSC-STEP4-PATH-WRITE-001`, `WGSC-STEP4-REMOTE-PY-001`, `WGSC-STEP5-COLMAP-TOOL-001`.

### Step 5 Start Remote Job

- Success: `/api/run-remote-algorithm` returns `WGSC-STEP5-QUEUED` with `job.id`.
- Failure: unknown family, unsupported operation template, missing/non-existing workspace, missing template args.
- Typical codes: `WGSC-STEP5-ADAPTER-404`, `WGSC-STEP5-OP-UNSUPPORTED-001`, `WGSC-STEP5-WORKSPACE-001`, `WGSC-STEP5-WORKSPACE-002`, `WGSC-STEP5-TEMPLATE-001`.

---

## 10. Remote COLMAP Workflow in Detail

### 10.1 When COLMAP is triggered

**Auto-triggered in these scenarios**:

1. Uploading multiple images but missing sparse reconstruction files like `sparse/0/cameras.bin`
2. Remote workspace is empty or incomplete
3. Data requires 3D reconstruction from raw images

**Not triggered in these scenarios**:

1. Complete sparse reconstruction already uploaded (camera, images, points files all present)
2. Using compression-only workflows like FCGS (direct point cloud PLY input)

### 10.2 Step 4 Verification Phase (remote preflight)

**Executed when you click `Check SSH` button**:

```
Local server
    ↓ (SSH login)
Remote host
    ├─ Check SSH connection and authentication
    ├─ Check workspace_root / output_root write permissions
    ├─ Check repo_path existence
    ├─ Check remote_python executable
    │
    ├─ If family requires COLMAP:
    │  ├─ Check `xvfb-run` available
    │  ├─ Check `vglrun` available (optional)
    │  └─ Test run: xvfb-run -a colmap feature_extractor -h
    │
    └─ Return check results
        ↓
Local UI (show pass/fail)
```

**Check details**:

| Check Item | Command | Required | Failure handling |
|------------|---------|----------|------------------|
| xvfb-run | `command -v xvfb-run` | Required for COLMAP | `WGSC-STEP5-COLMAP-TOOL-001` → Install Xvfb |
| vglrun | `command -v vglrun` | Optional | Warning, auto-fallback to Xvfb-only |
| COLMAP executable | `xvfb-run -a colmap feature_extractor -h` | Required for COLMAP | `WGSC-STEP5-COLMAP-TOOL-001` → Check COLMAP installation |

### 10.3 Step 5 Execution Phase (remote run)

**Flow after clicking `One-click Upload and Remote Train`**:

```
Local
├─ Upload image data to <workspace_root>/<session_id>/<family>/<job_id>/input/
└─ Return workspace path to backend

Remote host (run_remote_algorithm)
├─ Step 1: Check if COLMAP is needed
│  └─ If yes → Execute COLMAP preprocessing
│
├─ Step 2: Set runtime environment variables
│  ├─ OMP_NUM_THREADS=1 (or external value)
│  ├─ QT_QPA_PLATFORM=xcb
│  └─ Define colmap_headless() function
│
├─ Step 3: Auto-select execution mode
│  ├─ If vglrun available → Use VirtualGL mode
│  └─ Otherwise → Use Xvfb-only mode
│
├─ Step 4: Execute COLMAP command
│  └─ xvfb-run -a -s "-screen 0 1280x1024x24" bash -lc '
│       OMP_NUM_THREADS=1 QT_QPA_PLATFORM=xcb
│       colmap_headless colmap feature_extractor \
│         --database_path <workspace>/distorted/database.db \
│         --image_path <workspace>/input \
│         --ImageReader.single_camera 1 \
│         --ImageReader.camera_model OPENCV
│     '
│
└─ Continue with training pipeline (HAC++ train.py)

Return results to local
├─ Sparse reconstruction files (cameras.bin, images.bin, points3D.bin)
├─ Training results (point_cloud.ply)
└─ Metrics log (metrics.csv)
```

### 10.4 Environment variable explanation

**OMP_NUM_THREADS**

- **Default**: 1 (conservative to prevent OOM from over-concurrency)
- **Tuning range**: 1 ~ CPU core count
- **Optimization guidance**:
  - Small scenes (<200 images): Keep default 1
  - Medium scenes (200-500 images): Set to 2-4
  - Large scenes (>500 images): Set to 50-75% of CPU core count
- **How to set** (before remote execution): `export OMP_NUM_THREADS=4`

**QT_QPA_PLATFORM**

- **Value**: `xcb` (X11 compatible mode)
- **Purpose**: Force Qt to use X11 backend, avoiding conflicts with Wayland or other display servers

### 10.5 VirtualGL vs Xvfb comparison

| Criterion | VirtualGL mode | Xvfb-only mode |
|-----------|----------------|----------------|
| Dependencies | vglrun + Xvfb | Xvfb only |
| Performance | Fast (GPU-accelerated) | Slow (CPU rendering) |
| OpenGL | GPU-processed | CPU software implementation |
| Use case | Large scenes, GPU-rich | Small scenes, no GPU, demos |
| Failure rate | Low (mature solution) | Minimal (no GPU drivers) |

### 10.6 Common issues and diagnostics

#### Issue: `qt.qpa.xcb: Could not connect to display`

**Cause**: Xvfb failed to start or virtual display init failed

**Diagnosis**:
```bash
# Test Xvfb manually
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99
colmap feature_extractor -h
```

**Fix**:
```bash
# Reinstall Xvfb
sudo apt-get remove -y xvfb
sudo apt-get install -y xvfb
# Verify
xvfb-run -a glxgears
```

#### Issue: COLMAP process killed (OOM)

**Cause**: Insufficient memory or OMP_NUM_THREADS too high

**Diagnosis**:
```bash
free -h
grep OMP_NUM_THREADS ~/.bashrc  # Check current setting
dmesg | tail -20  # Check OOM logs
```

**Fix**:
```bash
# Reduce thread count
export OMP_NUM_THREADS=1
# Clean temp files
rm -rf /tmp/web_scan/workspaces/*/workspace/distorted/*
# Check disk space
du -sh <workspace_root>
```

#### Issue: `vglrun: command not found` (but doesn't block execution)

**Cause**: VirtualGL not installed

**Diagnosis**:
```bash
command -v vglrun  # Returns empty
dpkg -l | grep virtualgl
```

**Recovery**:
- If VirtualGL not installed: System auto-falls back to Xvfb-only, functionality unchanged, just slower
- To enable GPU forwarding: `sudo apt-get install -y virtualgl`

### 10.7 Performance optimization tips

1. **Pre-test COLMAP**: Run small dataset COLMAP on remote once to verify environment
2. **Tune OMP_NUM_THREADS**: Adjust based on CPU cores and available memory
3. **Enable GPU acceleration**: Install VirtualGL + high-end GPU (e.g., RTX 4090)
4. **Optimize network**: Compress images before upload to reduce transfer time
5. **Monitor resources**: Run `watch -n 1 'nvidia-smi && free -h'` on remote for real-time stats

---

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
| WGSC-STEP5-COLMAP-TOOL-001 | Step4/5 | Headless COLMAP runtime missing or `xvfb-run` cannot launch COLMAP | **Install Xvfb**: `sudo apt-get install -y xvfb`; **Verify**: `xvfb-run -a colmap feature_extractor -h`; Optionally install `vglrun` for GPU forwarding: `sudo apt-get install -y virtualgl` |
| WGSC-STEP5-COLMAP-REMOTE-001 | Step5 | COLMAP preprocessing failed on remote, possible causes: missing OpenGL drivers, image data permissions, virtual display misconfiguration, improper OMP_NUM_THREADS | **Check logs**: `tail -f /tmp/web_scan/outputs/.../runtime.log`; **Verify**: 1) OpenGL: `glxinfo \| grep vendor`; 2) Image permissions: `ls -l <input_dir>`; 3) OMP threads: `echo $OMP_NUM_THREADS`; 4) Xvfb: `ps aux \| grep Xvfb`; **Common fixes**: Increase OMP_NUM_THREADS to CPU core count, check disk space, reinstall drivers |
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
