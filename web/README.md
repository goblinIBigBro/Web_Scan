# Gaussian Encoding Web Platform

## Overview

This folder provides a standalone web platform that serves as a unified visualization entrypoint for various Gaussian encoding and reconstruction algorithms.

## User Manual

If you are using this for the first time, please refer to the training manual:

- Chinese: `web/WEB_TRAINING_MANUAL_ZH.md`
- English: `web/WEB_TRAINING_MANUAL_EN.md`

## Basic Functions

The platform currently provides the following core features:

- Scene loading and rendering
  - Single entry page: `index.html`
  - Scene manifest loading
  - Renderer registry
  - Two viewer paths: SH / SG
  - Legacy viewer connected via `iframe + postMessage` to the control panel

- Algorithm management and job scheduling
  - Survey method registry
  - Config-driven multi-repo adapter registry
  - Server export interfaces and algorithm job APIs
  - Capture pipeline script generation and execution
  - Environment self-checks and runtime readiness verification
  - Guided workflow with state-driven fold/unfold
  - Remote-first flow blocks and optional Local Debug group
  - Scene sharing URLs and a job monitor

- Real-time input and result display
  - Camera capture
  - Image upload
  - Streamed uploads
  - Collection sessions assembled into multi-frame datasets
  - Automatic COLMAP workspace preparation
  - Two-column realtime workspace (capture / results)
  - Dual-mode result display: result image or interactive structural viewer
  - Built-in remote training mode (SSH/SFTP) with automatic output download

- Metrics and status monitoring
  - Algorithm task metrics extraction and real-time frontend display
  - Viewer-side metrics: `FPS`, `Vertices`, `Progress`
  - Algorithm-side metrics: `Algo FPS`, `Loss`, `PSNR`, `Iter`
  - Persistent job runtime logs (`.log`) and metrics history (`.csv`)
  - Frontend log tail + paged metrics table + one-click downloads

## Run

We recommend running the built-in API and static server:

Install dependency for remote mode:

```bash
python -m pip install paramiko
```

For the full HAC++ remote setup checklist, see:

- Chinese: `web/WEB_TRAINING_MANUAL_ZH.md`
- English: `web/WEB_TRAINING_MANUAL_EN.md`

```bash
python3 web/server/api_server.py --host 127.0.0.1 --port 8080
```

Then open:

```
http://127.0.0.1:8080/web/
```

You can also open a specific manifest via a share URL:

```
http://127.0.0.1:8080/web/?manifest=/web/generated/scene_a/scene_manifest.json
```

## End-to-end Flow

The web UI covers the following flow:

1. Check API and validate adapter in `Runtime Config`.
2. Capture at least one frame in `Capture`.
3. Fill remote credentials and paths in `Remote Training Config`. Current remote mode is HAC++ only; other algorithm families are reserved as placeholders. Run the preflight checklist in the training manual before clicking submit.
4. Click `One-click Upload and Remote Train` in `Remote Run`.
5. The backend executes: upload frame -> materialize session -> remote train -> download outputs.
6. The frontend polls task status, updates metrics, and auto-switches viewer to latest result.
7. Open `System Board -> Job Logs and Metrics` to inspect log tail, paged metrics rows, and download `.log/.csv`.
8. Optional: use `Local Debug (Optional)` for local fallback operations.

### Additional capture flow

- Browser collects camera frames or uploaded images.
- The server stores frames at `web/generated/streams/<session_id>/input/`.
- `POST /api/materialize-session` assembles the capture session into a dataset under `web/generated/datasets/<session_id>/`.
- The frontend can autofill task forms with these paths for COLMAP / training workflows.
- `POST /api/prepare-colmap-workspace` can prepare a COLMAP workspace and related files.

### Real-time processing

- Browser sends frames to `POST /api/stream-frame`.
- The server persists frames and provides a `process_frame` scheduling entry.
- If the adapter defines a `process_frame` template, the server will trigger the backend algorithm to process the frame and return results.
- The frontend polls and displays the processed result image or interactive scene when available.

### One-click remote training

- Fill remote credentials and paths in `Remote Training Config`.
- Click `One-click Upload and Remote Train` in `Remote Run`.
- The flow is: frame upload -> auto materialize session -> remote train -> auto download outputs -> auto render.

### Job logs and metrics download

- `GET /api/jobs/<job_id>/logs?page=1&page_size=20&tail_lines=120`
  - Returns paged metrics rows and raw log tail.
- `GET /api/jobs/<job_id>/logs/download`
  - Downloads persisted runtime log (`.log`).
- `GET /api/jobs/<job_id>/metrics.csv`
  - Downloads metrics history (`.csv`).

The frontend `Job Logs and Metrics` panel binds these endpoints directly and supports pagination.

## Runtime Checks

The page performs environment checks for tools such as:

- `python3`
- `colmap`
- `nvidia-smi`
- `magick`

The system distinguishes two readiness states:

- `web_runnable`: whether the web service itself can start
- `pipeline_ready`: whether the algorithm pipeline has the required environment to run

For remote mode, network/auth/path checks are validated at job submission time.

## Adapter Registry

Adapters are configured in:

```
web/config/algorithm_adapters.json
```

Each adapter entry should provide `family`, `repo_path`, `repo_url`, `representation`, `operations`, and `default_cwd`. The frontend reads this configuration to display and switch algorithms.

## Realtime Bridge Contract

Realtime input / output conventions used by the platform:

- Input frames uploaded to: `web/generated/streams/<session_id>/input/`
- Processing outputs should be written to: `web/generated/streams/<session_id>/output/latest.png`
- If an interactive Gaussian structure is produced, place one of:
  - `web/generated/streams/<session_id>/output/point_cloud.ply`
  - `web/generated/streams/<session_id>/output/latest.ply`
  - `web/generated/streams/<session_id>/output/scene.ply`
  - `web/generated/streams/<session_id>/output/scene_manifest.json`
- Structured metrics may be written to `metrics.json` in the same output folder.

The server watches stdout/stderr, `metrics.json`, `latest.png`, and `.ply` / `scene_manifest.json` and relays updates to the frontend.

## Scene Manifest Example

See `src/loaders/scene-manifest-loader.js` for `manifestSchemaExample()`.
