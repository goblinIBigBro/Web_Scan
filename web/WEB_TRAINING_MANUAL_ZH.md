# Web 端远程训练操作手册（中文）

## 1. 目标与当前能力

本手册对应当前代码实现的流程：

1. Web 页面上传照片到本地服务端。
2. 服务端自动物化会话数据集。
3. 服务端通过内置 SSH/SFTP 发起远程训练任务。
4. 远程输出自动回传到本地 output_dir。
5. 前端自动轮询任务并自动渲染结果（viewer 或图片回退）。

当前版本的远程模式限制：

- 算法家族不再硬编码，按 adapter 是否存在可用 operation/template 决定是否支持。
- operation 不再固定 train，按当前选择 operation 与模板能力执行。
- 认证方式为 SSH 账号密码。

---

## 2. 远程配置指南（能力驱动）

### 2.1 本地控制机

- 本机只负责网页、上传、任务下发和结果展示，不需要装 HAC++ 训练环境。
- 仍然需要可以启动 `web/server/api_server.py`。
- 安装远程依赖（必须）：

```bash
python -m pip install paramiko
```

### 2.2 远程训练机

- 可以被本地通过 SSH 访问。
- 拥有独立账号，且该账号可以写入远程工作目录和输出目录。
- 已准备 HAC-plus-main 代码、训练脚本和依赖环境。
- 远端必须能直接运行 HAC++ 的训练命令，例如：

```bash
python train.py -s <workspace> --eval -m <output_dir>
```

### 2.2.1 无头 COLMAP 运行环境

- 自动 COLMAP 会放到 Xvfb 里执行，这样即使远端没有真实桌面也能运行。
- 远端无头主机必须安装 `xvfb` / `xvfb-run`，否则 COLMAP 的图形初始化仍可能失败。
- 如果希望把 OpenGL 调用转给 GPU，建议同时安装 `virtualgl` / `vglrun`；后端会在可用时自动优先使用它。
- 如果远端只装了 `colmap`，但没有 Xvfb，仍可能出现 `qt.qpa.xcb` / display 相关错误并中断。
- 后端会优先使用 VirtualGL；如果没有 `vglrun`，则自动退回到纯 Xvfb 方式。

### 2.2.2 FCGS 远程压缩

- FCGS 的压缩入口本身直接处理已有的 3DGS 点云，但如果你的上游数据需要从图像准备 3DGS，或者要跑验证/场景相关流程，远端仍需要 COLMAP。
- 远端仓库必须包含 `submodules/diff-gaussian-rasterization`。请用 `git clone --recursive`，或者在远端执行 `git submodule update --init --recursive`。
- 按 [FCGS 远程配置指南](../FCGS-main/fcgs/README.md) 使用更新后的 Python 3.10 环境：Python 3.10、PyTorch 2.2.*、torchvision 0.17.*、pytorch-cuda 11.8、numpy 1.26.*、pillow 10.*、plyfile 1.1.*、tqdm 4.66.*、lpips。
- FCGS 直接在仓库根目录运行下面这些入口：

```bash
python encode_single_scene.py --lmd 1e-4 --ply_path_from <path/to/point_cloud.ply> --bit_path_to <path/to/bitstreams> --determ 1
python decode_single_scene.py --lmd 1e-4 --bit_path_from <path/to/bitstreams> --ply_path_to <path/to/point_cloud.ply>
python decode_single_scene_validate.py --lmd 1e-4 --bit_path_from <path/to/bitstreams> --ply_path_to <path/to/point_cloud.ply> --source_path <path/to/scene>
```

- 支持的 `--lmd` 取值是 `1e-4`、`2e-4`、`4e-4`、`8e-4`、`16e-4`。
- 如果 `tmc3` 不在 `PATH` 里，就手动修改 [model/gpcc_utils.py](../FCGS-main/model/gpcc_utils.py) 中两个 `change tmc3 path` 位置。
- `checkpoints/checkpoint_*.pkl` 需要保留；选择的 `--lmd` 会对应到相应的 checkpoint。

### 2.3 推荐机器与环境

| 项目 | 推荐值 | 备注 |
| --- | --- | --- |
| GPU | RTX 4090 24GB | 首选，单卡就能覆盖大多数示例场景 |
| 更稳妥的 GPU | RTX A6000 48GB / RTX 6000 Ada 48GB / A100 40GB+ | 大场景、长序列或并发训练更稳 |
| CPU | 8 核及以上 | 16 核以上更舒服 |
| 内存 | 32GB 及以上 | 大场景建议 64GB |
| 磁盘 | 200GB 及以上可用空间 | 数据、workspace、output、bitstream 都要预留 |
| 系统 | Ubuntu 20.04/22.04 | 官方 README 提到的实测环境是 Ubuntu 20.04.1 |
| CUDA | 11.8 或与环境文件匹配的 12.1 | 以驱动和环境一致为准 |

- 以当前仓库 `HAC-plus-main/environment.yml` 为准，推荐：
  - Python 3.10
  - PyTorch 2.2.*
  - torchvision 0.17.*
  - torchaudio 2.2.*
  - pytorch-cuda 12.1
- FCGS 则建议使用 `FCGS-main/environment.yml`：
  - Python 3.10
  - PyTorch 2.2.*
  - torchvision 0.17.*
  - pytorch-cuda 11.8
  - numpy 1.26.* / pillow 10.* / plyfile 1.1.* / tqdm 4.66.* / lpips
- HAC++ 官方 README 还给出了 Ubuntu 20.04.1 / CUDA 11.8 / gcc 9.4.0 的实测组合。
- 不建议再按 Python 3.8 / PyTorch 1.2 这类旧组合来配当前分支。
- 压缩和回传链路会调用 GPCC / tmc3，远端还需要能直接执行 `tmc3`。

### 2.4 SSH 远程注意事项

- 当前版本只支持 SSH 用户名 + 密码，不接收私钥字段。
- `Remote Host` 可以是 IP 或域名；`Remote Port` 默认 22。
- `Remote Repo Path` 必须是远端真实存在的 HAC-plus-main 路径，且该账号可读写。
- `Remote Workspace Root` 和 `Remote Output Root` 必须是该账号可写目录，建议放在 `/tmp/web_scan/...` 或 `~/web_scan/...`。
- `Remote Activate Command` 会在非交互 shell 中执行，推荐写成一行。
  - 示例：`source ~/.bashrc && conda activate HAC_env`
  - 如果 conda 没有写入 `~/.bashrc`，可以改成：`source ~/miniconda3/etc/profile.d/conda.sh && conda activate HAC_env`
- 如果你已经在远端把解释器路径固定好，也可以把 `Remote Python` 写成完整路径，例如 `/home/ubuntu/miniconda3/envs/HAC_env/bin/python`。
- 不要把有空格、中文或特殊字符的路径当作默认值，除非你已经在远端手动验证过。
- 训练账号不需要 sudo/root 权限，只需要能写 workspace 和 output。
- 如果远端有防火墙或安全组，SSH 端口必须对本机可达。
- 如果需要通过跳板机再登录，当前页面还没有单独的 jump host 字段，先不要把它当成“已支持”。

### 2.5 提交前检查清单

只要下面这些检查都通过，就可以放心点页面里的 `One-click Upload and Remote Train`。

1. 本地依赖可用：`python -m pip install paramiko`。
1. 本地到远端 SSH 可登录：`ssh <user>@<host> -p <port>`。
1. 远端 GPU 可见：`nvidia-smi`。
1. 远端 Python 和 PyTorch 可用：`python -V` 与 `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`。
1. 远端 conda / 虚拟环境能正常激活：`source ~/.bashrc && conda activate HAC_env`（或使用你自己的激活命令）。
1. 远端仓库路径可运行：`cd <repo_path> && python train.py -h`。
1. 远端写权限正常：`touch <workspace_root>/.write_test && rm <workspace_root>/.write_test` 以及 `touch <output_root>/.write_test && rm <output_root>/.write_test`。
1. 无头 COLMAP 运行环境可用：`command -v xvfb-run`，并且 `xvfb-run -a colmap feature_extractor -h` 可以启动。
1. 如需 GPU OpenGL 转发，`command -v vglrun` 可用（可选，Xvfb-only 模式也能工作）。
1. `tmc3` 可直接调用：`which tmc3` 与 `tmc3 --help`。
1. 磁盘空间足够：`df -h`。
1. 通过上述检查后，再执行页面的一键上传、训练、回传流程。

### 2.6 当前支持与未来占位

- 远程入口对所有 family 可见。
- 实际是否可运行取决于当前 family 的 operation 是否定义并启用了命令模板。
- 若不支持会返回 `WGSC-STEP5-OP-UNSUPPORTED-001`，并可在错误码索引章节查修复方案。

---

## 3. 启动服务

在仓库根目录启动：

```bash
python3 web/server/api_server.py --host 127.0.0.1 --port 8080
```

打开页面：

- <http://127.0.0.1:8080/web/>

---

## 4. 页面配置说明

在左侧面板配置以下关键项：

页面采用流程折叠机制：

- 已完成/锁定区块会自动收起。
- 当前激活区块会自动展开。
- 若用户手动展开/收起，系统会优先尊重手动状态。
- 本地流程已收纳到 `Local Debug (Optional)`，默认不打断远程主流程。

### 4.1 Runtime Config

- API Base URL: 例如 `http://127.0.0.1:8080`
- Algorithm Family: 选择目标 family（不再限制为 hac-plus-plus）
- Repo Path / Default CWD: 本地调试链路用，可保留或填写

### 4.2 Capture

- Stream Session ID: 会话名，建议按场景命名（如 session-demo）
- Upload Image: 可上传图片文件
- 或使用 Start Camera + Send Frame

### 4.3 Remote Training Config

- Remote Host: 远程主机 IP/域名
- Remote Port: SSH 端口（默认 22）
- Remote Username / Remote Password: SSH 账号密码
- Remote Repo Path: 远程 HAC-plus-main 路径
- Remote Workspace Root: 远程数据上传根目录（如 /tmp/web_scan/workspaces）
- Remote Output Root: 远程输出根目录（如 /tmp/web_scan/outputs）
- Remote Python: 远程 Python 命令（默认 python3）
- Remote Activate Command: 可选环境激活命令
  - 示例：source ~/.bashrc && conda activate HAC_env

### 4.4 Remote Run

- One-click Upload and Remote Train: 一键执行完整链路
- Refresh Jobs: 刷新任务状态
- Export Package: 导出可分享场景

### 4.5 System Board（执行监控）

- `Execution Monitor -> Job Monitor`：
  - Job 卡片已改为可折叠摘要视图，默认展示关键信息（状态、ID、operation、核心指标）。
  - 列表区域为限高滚动，不会再把整个页面顶出可视区。
  - 点击 `View Logs` 会自动展开 `Job Logs and Metrics`，并切换到对应 job。
- `Execution Monitor -> Job Logs and Metrics`：
  - 顶部工具栏：`Select Job`、`Refresh Log`。
  - 下载动作：`Download .log`、`Download metrics.csv`。
  - 新增 `Copy Raw Log`，可一键复制当前日志尾部。
  - 指标表与原始日志分栏显示：左侧指标分页表格，右侧 Raw Log Tail。
  - `Tail Lines` 可选 80/120/200/400，用于调节日志尾部长度。

### 4.6 Local Debug（可选）

- Session Tools / Local Job Tools 仅用于本地调试兜底。
- 远程用户可忽略该分组。

---

## 5. 一键流程（推荐）

1. 点击 Check Runtime。
2. 确认目标 family 的 Adapter Capability 可用。
3. 上传图片（或启动相机）。
4. 填写 Remote Training 全部必填项并执行 Check SSH。
5. 点击 One-click Upload and Remote Train（当前 operation 必须有远程模板）。
6. 观察状态：
Remote Connecting -> Remote Uploading -> Remote Training -> Remote Downloading -> Remote Completed
7. 任务完成后，右侧 Processed Result 自动显示 viewer 或结果图。
8. 在 `System Board -> Job Monitor` 点击 `View Logs`，自动跳转到 `Job Logs and Metrics` 查看：
指标分页表格、Raw Log Tail、`.log`/`metrics.csv` 下载，以及 `Copy Raw Log` 快捷复制。

说明：

- 一键流程会先上传当前帧，再自动物化 session。
- 若 output_dir 未填写，默认写入 `/web/generated/runs/{session}/{family}`。

---

## 6. 分步流程（调试兜底）

如需排查问题，可按分步执行：

1. Send Frame（仅上传）
2. Materialize Session
3. Submit Job（本地模式）或调用远程 API（远程模式）
4. Refresh Jobs 观察 stderr 与 metrics

---

## 7. 后端接口（远程模式）

### 7.1 远程任务提交

- POST /api/run-remote-algorithm

请求示例：

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

响应：

- 返回统一 job 对象（status=queued/running/completed/failed）
- 返回 materialized 信息（若自动物化成功）

### 7.2 作业查询

- GET /api/jobs
- GET /api/jobs/{jobId}

### 7.3 日志与指标下载（新增）

- GET /api/jobs/{jobId}/logs?page=1&page_size=20&tail_lines=120
  - 返回日志尾部 + 指标分页数据（用于前端表格）。
- GET /api/jobs/{jobId}/logs/download
  - 下载原始运行日志 `.log`。
- GET /api/jobs/{jobId}/metrics.csv
  - 下载指标历史 `.csv`。

---

## 8. Step1-5 完成判定

### Step 1 Runtime Check

- 成功：`/api/environment-check` 返回 `runtime_ready=true`。
- 失败：必需检查项（`required=true`）任一失败。
- 常见代码：`WGSC-STEP1-RUNTIME-FAIL`、`WGSC-REQUEST-JSON-001`。

### Step 2 Adapter Capability

- 成功：适配器 `validation.is_ready=true`，并至少有一个可用 operation。
- 失败：family 不存在，或 adapter 无可用 operation。
- 常见代码：`WGSC-STEP2-ADAPTER-OK`、`WGSC-STEP2-ADAPTER-404`。

### Step 3 Capture First Frame

- 成功：`/api/stream-frame` 返回 `ok=true`，并有 `input_url`。
- 失败：缺少 `image_data`、帧落盘失败、session 物化失败。
- 常见代码：`WGSC-STEP3-PAYLOAD-001`、`WGSC-STEP3-FRAME-SAVE-001`、`WGSC-STEP3-MATERIALIZE-001`。

### Step 4 SSH Remote Check

- 成功：`/api/remote-check` 返回 `WGSC-STEP4-SSH-OK`。
- 失败：配置缺失、paramiko 缺失、网络不可达、认证失败、repo 路径不存在、远端目录不可写、远端 python 不可执行，或者在需要 COLMAP 校验时缺少无头运行环境。
- 常见代码：`WGSC-STEP4-CONFIG-001`、`WGSC-STEP4-DEPENDENCY-001`、`WGSC-STEP4-SSH-NET-001`、`WGSC-STEP4-SSH-AUTH-001`、`WGSC-STEP4-PATH-REPO-001`、`WGSC-STEP4-PATH-WRITE-001`、`WGSC-STEP4-REMOTE-PY-001`、`WGSC-STEP5-COLMAP-TOOL-001`。

### Step 5 Start Remote Job

- 成功：`/api/run-remote-algorithm` 返回 `WGSC-STEP5-QUEUED`，并带 `job.id`。
- 失败：family 不存在、operation 不支持远程模板、workspace 缺失/不存在、模板参数缺失、远程链路失败。
- 常见代码：`WGSC-STEP5-ADAPTER-404`、`WGSC-STEP5-OP-UNSUPPORTED-001`、`WGSC-STEP5-WORKSPACE-001`、`WGSC-STEP5-WORKSPACE-002`、`WGSC-STEP5-TEMPLATE-001`。

---

## 9. 常见错误码与解决方案

| 错误码 | 步骤 | 含义 | 处理建议 |
| --- | --- | --- | --- |
| WGSC-REQUEST-JSON-001 | 请求 | 请求体不是合法 JSON | 检查请求格式或浏览器插件改写 |
| WGSC-STEP1-RUNTIME-FAIL | Step1 | 运行时必需检查失败 | 在环境面板查看失败项并修复 |
| WGSC-STEP2-ADAPTER-404 | Step2 | family 不存在 | 重新选择 Algorithm Family |
| WGSC-STEP3-PAYLOAD-001 | Step3 | 未提供 image_data | 重新上传图片或重新采集相机帧 |
| WGSC-STEP3-FRAME-SAVE-001 | Step3 | 保存帧失败 | 检查 `web/generated` 写权限 |
| WGSC-STEP3-MATERIALIZE-001 | Step3 | 物化 session 失败 | 确认 session 下已有 input 帧 |
| WGSC-STEP4-DEPENDENCY-001 | Step4 | 本地缺少 paramiko | `python -m pip install paramiko` |
| WGSC-STEP4-CONFIG-001 | Step4 | 远程配置字段缺失或非法 | 补全 host/user/password/port/path |
| WGSC-STEP4-SSH-NET-001 | Step4 | SSH 网络不可达 | 检查 host/port、防火墙、安全组 |
| WGSC-STEP4-SSH-AUTH-001 | Step4 | SSH 认证失败 | 校验用户名、密码、端口 |
| WGSC-STEP4-PATH-REPO-001 | Step4 | 远端 repo_path 不存在 | 修正为远端真实仓库目录 |
| WGSC-STEP4-PATH-WRITE-001 | Step4 | 远端目录不可写 | 改用可写路径如 `/tmp/web_scan/...` |
| WGSC-STEP4-REMOTE-PY-001 | Step4 | 远端 python 不可执行 | 修正 `remote.python` 或激活命令 |
| WGSC-STEP5-COLMAP-TOOL-001 | Step4/5 | 无头 COLMAP 运行环境缺失，或 `xvfb-run` 无法拉起 COLMAP | 安装 `xvfb-run`；如需 GPU 透传 OpenGL 再装 `vglrun`；确认 `xvfb-run -a colmap feature_extractor -h` 能正常启动 |
| WGSC-STEP5-COLMAP-REMOTE-001 | Step5 | 在无头运行时执行 COLMAP 预处理失败 | 查看远端 `runtime.log`，检查 OpenGL 驱动、图像数据、权限与 `OMP_NUM_THREADS`，修复后重试 |
| WGSC-STEP5-OP-UNSUPPORTED-001 | Step5 | operation 无远程模板 | 切换 operation 或补齐 adapter 模板 |
| WGSC-STEP5-WORKSPACE-001 | Step5 | workspace 缺失 | 开启 `auto_materialize` 或显式传 workspace |
| WGSC-STEP5-WORKSPACE-002 | Step5 | workspace 目录不存在 | 检查本地路径是否存在 |
| WGSC-STEP5-TEMPLATE-001 | Step5 | 命令模板参数缺失 | 根据缺失字段补齐输入参数 |
| WGSC-STEP5-PIPELINE-001 | Step5 | 本地 pipeline 运行失败 | 查看 job log 与 stderr 进一步定位 |

---

## 10. 结果回传与渲染规则

服务端会在本地 output_dir 中识别并返回：

- scene_manifest.json -> manifest_url + viewer_url
- point_cloud.ply 或 point_cloud/iteration_x/point_cloud.ply -> point_cloud_url + viewer_url
- latest.png -> result_url（图片回退）
- metrics.json -> job.metrics

同时，服务端会在 `web/generated/job_logs/<job_id>/` 持久化：

- `runtime.log`
- `metrics.csv`

---

## 11. 安全建议

- 当前版本使用账号密码，仅用于受控内网环境。
- 不要将密码写入版本库。
- 后端已对 job 返回做脱敏，不返回明文密码；仍建议使用低权限训练账号。

---

## 12. 版本说明

本文档对应功能：

- 后端新增 `/api/remote-check` 与结构化错误码响应。
- `/api/run-remote-algorithm` 从固定 hac-plus-plus 放开为适配器能力驱动。
- 前端 Step1-5 增加可视化结果卡（成功/失败/错误码）。
