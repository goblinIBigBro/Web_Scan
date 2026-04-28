# Web 端远程训练操作手册（中文）

## 🆕 重要更新：文件上传问题已修复

**问题**：上传图片后总是提示"选中一张或多张照片"  
**根因**：页面重新渲染时，文件选择状态丢失  
**解决**：已升级为在内存中保存文件选择状态，刷新页面不再丢失文件  
**操作**：清除浏览器缓存（Ctrl+Shift+Delete）后重新访问，或在浏览器地址栏按 Ctrl+R 强制刷新

---

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

#### 基本原理

- 自动 COLMAP 会放到 Xvfb（虚拟 X 服务器）里执行，这样即使远端没有真实桌面也能运行。
- 远端无头主机必须安装 `xvfb` / `xvfb-run`，否则 COLMAP 的图形初始化仍可能失败。
- 如果希望把 OpenGL 调用转给 GPU，建议同时安装 `virtualgl` / `vglrun`；后端会在可用时自动优先使用它。
- 如果远端只装了 `colmap`，但没有 Xvfb，仍可能出现 `qt.qpa.xcb` / display 相关错误并中断。

#### VirtualGL / Xvfb 自动降级策略

后端运行时自动选择最优的执行环境：

1. **优先级1：VirtualGL 模式**（最优，需要 GPU OpenGL 透传）
   - 条件：`vglrun` 可用 + `xvfb-run` 可用 + GPU 可见
   - 效果：COLMAP 的 OpenGL 调用通过 VirtualGL 转给 GPU 处理，性能最佳
   - 命令：`xvfb-run -a ... vglrun colmap feature_extractor ...`

2. **优先级2：Xvfb-only 模式**（降级，CPU 渲染）
   - 条件：`vglrun` 不可用，但 `xvfb-run` 可用
   - 效果：COLMAP 在虚拟显示中使用 CPU 进行 OpenGL 渲染，速度较慢但可工作
   - 命令：`xvfb-run -a ... colmap feature_extractor ...`

3. **失败状态**（不支持）
   - 条件：`xvfb-run` 不可用
   - 结果：返回错误 `WGSC-STEP5-COLMAP-TOOL-001`，需要安装 Xvfb

#### 执行时的环境变量

后端在运行 COLMAP 前会设置以下环境变量：

```bash
# 设置 OMP 线程数（防止过度并发，默认1）
export OMP_NUM_THREADS="1"

# 设置 Qt 平台为 xcb（X11 兼容模式）
export QT_QPA_PLATFORM=xcb
```

这些设置确保 COLMAP 能在无显示环境下正确初始化 Qt 图形库。

#### 安装指南

**远端主机上的必需安装**：

```bash
# Ubuntu 20.04 / 22.04
sudo apt-get update
sudo apt-get install -y xvfb

# 可选：GPU OpenGL 透传（推荐大场景使用）
sudo apt-get install -y virtualgl
```

**验证安装**：

```bash
# 检查 xvfb-run
command -v xvfb-run
xvfb-run -a colmap feature_extractor -h

# 检查 VirtualGL（如果已安装）
command -v vglrun
vglrun colmap feature_extractor -h
```

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
  - numpy 1.26.*/ pillow 10.* / plyfile 1.1.*/ tqdm 4.66.* / lpips
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

1. **本地依赖**：`python -m pip install paramiko`。

2. **SSH 连接**：`ssh <user>@<host> -p <port>`。
   - 验证能否直接登录远端
   - 如失败：检查 host/port/用户名/密码

3. **远端 GPU**：`nvidia-smi`。
   - 确认 GPU 可见且驱动正常
   - 如失败：检查驱动安装、cuda-toolkit 版本

4. **远端 Python 和 PyTorch**：

   ```bash
   python -V
   python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
   ```

   - 验证 Python 版本 ≥ 3.10
   - 验证 PyTorch 已正确安装且 CUDA 可用

5. **远端环境激活**：`source ~/.bashrc && conda activate HAC_env`。
   - 根据实际配置替换激活命令
   - 如失败：检查 `.bashrc` 或 `~/.profile`

6. **远端仓库可运行**：`cd <repo_path> && python train.py -h`。
   - 验证仓库路径正确且包含 `train.py`
   - 验证 Python 能导入项目模块

7. **远端写权限**：

   ```bash
   touch <workspace_root>/.write_test && rm <workspace_root>/.write_test
   touch <output_root>/.write_test && rm <output_root>/.write_test
   ```

   - 确认两个目录都可写
   - 如失败：改用 `/tmp/web_scan/...` 等可写路径

8. **无头 COLMAP 工具**：

   ```bash
   command -v xvfb-run
   xvfb-run -a colmap feature_extractor -h
   ```

   - 验证 `xvfb-run` 可执行
   - 验证 COLMAP 能在虚拟显示中启动
   - **如失败**：执行 `sudo apt-get install -y xvfb`

9. **GPU OpenGL 转发（可选但推荐）**：

   ```bash
   command -v vglrun
   vglrun colmap feature_extractor -h
   ```

   - 检查 VirtualGL 是否可用
   - 如不可用，系统会自动降级到 Xvfb-only
   - **如希望启用**：执行 `sudo apt-get install -y virtualgl`

10. **tmc3 压缩工具**：`which tmc3 && tmc3 --help`。
    - 确认 tmc3 在 PATH 中（用于后端压缩阶段）
    - 如失败：安装或配置 GPCC 工具链

11. **磁盘空间**：`df -h`。
    - 确认 `/tmp` 和数据目录有足够空间（建议 200GB+）
    - 计算方式：图像数据 + workspace 临时文件 + output 结果

12. **通过以上检查后**：在页面执行 `Check SSH` 按钮再次验证远端状态，然后点击 `One-click Upload and Remote Train`。

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

## 9. 远程 COLMAP 工作流详解

### 9.1 何时触发 COLMAP

**在以下场景自动触发 COLMAP 预处理**：

1. 上传多张图像但缺少 `sparse/0/cameras.bin` 等稀疏重建文件
2. 远端 workspace 为空或不完整
3. 数据需要从原始图像进行 3D 重建

**不触发 COLMAP 的场景**：

1. 已上传完整的稀疏重建（camera、images、points 文件都存在）
2. 使用 FCGS 等不需要 COLMAP 的纯压缩流程（直接输入点云 PLY）

### 9.2 Step 4 验证阶段（远端预检查）

**点击 `Check SSH` 按钮时执行**：

```
本地 server
    ↓ （SSH 登录）
远端主机
    ├─ 检查 SSH 连接和身份认证
    ├─ 检查 workspace_root / output_root 写权限
    ├─ 检查 repo_path 存在性
    ├─ 检查 remote_python 可执行
    │
    ├─ 如果 family 需要 COLMAP：
    │  ├─ 检查 `xvfb-run` 可用
    │  ├─ 检查 `vglrun` 可用（可选）
    │  └─ 测试运行：xvfb-run -a colmap feature_extractor -h
    │
    └─ 返回检查结果
        
本地 UI（显示通过/失败）
```

**检查项详情**：

| 检查项 | 命令 | 是否必需 | 失败处理 |
|--------|------|---------|---------|
| xvfb-run | `command -v xvfb-run` | 需要 COLMAP 时必需 | `WGSC-STEP5-COLMAP-TOOL-001` → 安装 Xvfb |
| vglrun | `command -v vglrun` | 可选 | 警告，自动降级到 Xvfb-only |
| COLMAP 可执行 | `xvfb-run -a colmap feature_extractor -h` | 需要 COLMAP 时必需 | `WGSC-STEP5-COLMAP-TOOL-001` → 检查 COLMAP 安装 |

### 9.3 Step 5 执行阶段（远端运行）

**点击 `One-click Upload and Remote Train` 后的流程**：

```

本地
├─ 上传图像数据到 <workspace_root>/<session_id>/<family>/<job_id>/input/
└─ 返回 workspace 路径给后端

远端主机（run_remote_algorithm）
├─ Step 1: 验证 COLMAP 必需
│  └─ 若需要 → 执行 COLMAP 预处理
│
├─ Step 2: 设置运行时环境变量
│  ├─ OMP_NUM_THREADS=1（或外部指定值）
│  ├─ QT_QPA_PLATFORM=xcb
│  └─ 定义 colmap_headless() 函数
│
├─ Step 3: 自动选择执行模式
│  ├─ 若 vglrun 可用 → 使用 VirtualGL 模式
│  └─ 否则 → 使用 Xvfb-only 模式
│
├─ Step 4: 执行 COLMAP 命令
│  └─ xvfb-run -a -s "-screen 0 1280x1024x24" bash -lc '
│       OMP_NUM_THREADS=1 QT_QPA_PLATFORM=xcb
│       colmap_headless colmap feature_extractor \
│         --database_path <workspace>/distorted/database.db \
│         --image_path <workspace>/input \
│         --ImageReader.single_camera 1 \
│         --ImageReader.camera_model OPENCV
│     '
│
└─ 继续执行后续训练流程（HAC++ train.py）

结果回传本地
├─ 稀疏重建文件（cameras.bin、images.bin、points3D.bin）
├─ 训练结果（point_cloud.ply）
└─ 指标日志（metrics.csv）
```

### 10.4 环境变量说明

**OMP_NUM_THREADS**

- **默认值**：1（保守值，防止过度并发造成内存溢出）
- **可调范围**：1 ~ CPU 核数
- **优化建议**：
  - 小场景（<200 张图）：保留默认 1
  - 中等场景（200-500 张）：设置为 2-4
  - 大场景（>500 张）：设置为 CPU 核数的 50-75%
- **设置方法**（在远端执行前）：`export OMP_NUM_THREADS=4`

**QT_QPA_PLATFORM**

- **值**：`xcb`（X11 兼容模式）
- **作用**：强制 Qt 使用 X11 backend，避免 Wayland 或其他显示服务器冲突

### 10.5 VirtualGL vs Xvfb 对比

| 对比项 | VirtualGL 模式 | Xvfb-only 模式 |
|--------|---------------|----------------|
| 依赖 | vglrun + Xvfb | Xvfb 只 |
| 性能 | 快（GPU 加速） | 慢（CPU 渲染） |
| OpenGL | GPU 处理 | CPU 软件实现 |
| 适用场景 | 大场景、GPU 充足 | 小场景、无 GPU 或演示 |
| 故障率 | 低（成熟方案） | 极低（无需 GPU 驱动） |

### 10.6 常见问题与诊断

#### 问题：`qt.qpa.xcb: Could not connect to display`

**原因**：Xvfb 未成功启动或虚拟显示初始化失败

**诊断**：

```bash
# 手动测试 Xvfb
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99
colmap feature_extractor -h
```

**修复**：

```bash
# 重新安装 Xvfb
sudo apt-get remove -y xvfb
sudo apt-get install -y xvfb
# 验证
xvfb-run -a glxgears
```

#### 问题：COLMAP 进程被 killed（OOM）

**原因**：内存不足或 OMP_NUM_THREADS 设置过高

**诊断**：

```bash
free -h
grep OMP_NUM_THREADS ~/.bashrc  # 查看当前设置
dmesg | tail -20  # 查看内存 OOM 日志
```

**修复**：

```bash
# 降低线程数
export OMP_NUM_THREADS=1
# 清理临时文件
rm -rf /tmp/web_scan/workspaces/*/workspace/distorted/*
# 检查磁盘空间
du -sh <workspace_root>
```

#### 问题：`vglrun: command not found`（但不影响运行）

**原因**：VirtualGL 未安装

**诊断**：

```bash
command -v vglrun  # 返回空
dpkg -l | grep virtualgl
```

**恢复方案**：

- 若不装 VirtualGL：系统自动降级到 Xvfb-only，功能不变，仅速度略慢
- 若想启用 GPU 透传：`sudo apt-get install -y virtualgl`

### 10.7 性能优化建议

1. **预先测试 COLMAP**：在远端单独运行一次小规模数据集的 COLMAP，验证环境
2. **调整 OMP_NUM_THREADS**：根据 CPU 核数和内存调参
3. **使用 GPU 加速**：安装 VirtualGL + 高端 GPU（RTX 4090 等）
4. **网络优化**：上传图像前压缩，减少传输时间
5. **监控资源**：在远端终端执行 `watch -n 1 'nvidia-smi && free -h'` 实时观察

---

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
| WGSC-STEP5-COLMAP-TOOL-001 | Step4/5 | 无头 COLMAP 运行环境缺失，或 `xvfb-run` 无法拉起 COLMAP | **安装 Xvfb**：`sudo apt-get install -y xvfb`；**验证**：`xvfb-run -a colmap feature_extractor -h`；如需 GPU 透传再装 `vglrun`：`sudo apt-get install -y virtualgl` |
| WGSC-STEP5-COLMAP-REMOTE-001 | Step5 | 远端 COLMAP 预处理失败，可能原因：OpenGL 驱动缺失、图像数据权限、虚拟显示配置错误、OMP_NUM_THREADS 设置不当 | **查看日志**：`tail -f /tmp/web_scan/outputs/.../runtime.log`；**检查项**：1) OpenGL：`glxinfo \| grep vendor`；2) 图像权限：`ls -l <input_dir>`；3) OMP 线程：`echo $OMP_NUM_THREADS`；4) Xvfb：`ps aux \| grep Xvfb`；**常见修复**：调高 OMP_NUM_THREADS 至 CPU 核数、检查磁盘空间、重新安装驱动 |
| WGSC-STEP5-OP-UNSUPPORTED-001 | Step5 | operation 无远程模板 | 切换 operation 或补齐 adapter 模板 |
| WGSC-STEP5-WORKSPACE-001 | Step5 | workspace 缺失 | 开启 `auto_materialize` 或显式传 workspace |
| WGSC-STEP5-WORKSPACE-002 | Step5 | workspace 目录不存在 | 检查本地路径是否存在 |
| WGSC-STEP5-TEMPLATE-001 | Step5 | 命令模板参数缺失 | 根据缺失字段补齐输入参数 |
| WGSC-STEP5-PIPELINE-001 | Step5 | 本地 pipeline 运行失败 | 查看 job log 与 stderr 进一步定位 |

---

## 10. 错误代码参考

见上表。

---

## 11. 结果回传与渲染规则

服务端会在本地 output_dir 中识别并返回：

- scene_manifest.json -> manifest_url + viewer_url
- point_cloud.ply 或 point_cloud/iteration_x/point_cloud.ply -> point_cloud_url + viewer_url
- latest.png -> result_url（图片回退）
- metrics.json -> job.metrics

同时，服务端会在 `web/generated/job_logs/<job_id>/` 持久化：

- `runtime.log`
- `metrics.csv`

---

## 12. 安全建议

- 当前版本使用账号密码，仅用于受控内网环境。
- 不要将密码写入版本库。
- 后端已对 job 返回做脱敏，不返回明文密码；仍建议使用低权限训练账号。

---

## 13. 版本说明

本文档对应功能：

- 后端新增 `/api/remote-check` 与结构化错误码响应。
- `/api/run-remote-algorithm` 从固定 hac-plus-plus 放开为适配器能力驱动。
- 前端 Step1-5 增加可视化结果卡（成功/失败/错误码）。

---

## 14. 文件上传常见问题与解决方案

### 问题1：上传图片后总是显示"选中一张或多张照片"

**症状**：
- 选择了图片文件，看到了预览
- 点击"Upload Selected Photos"后报错"上传前请选中一张或多张照片"

**原因**：
- 旧版本代码中，页面重新渲染时会重置 input 元素，导致文件选择丢失

**解决方案**（✅ 已在最新版本修复）：
1. **清除浏览器缓存**：
   - Windows/Linux：Ctrl + Shift + Delete
   - Mac：Cmd + Shift + Delete
   - 选择"全部"并清除
   
2. **强制刷新页面**：在浏览器地址栏按 Ctrl+R（或 Cmd+R 在 Mac 上）
   
3. **重新访问页面**：关闭所有标签页，重新打开 http://127.0.0.1:8080/web/

4. **如果问题仍然存在**：
   - 检查浏览器控制台（F12）是否有 JavaScript 错误
   - 尝试使用无痕窗口（Ctrl+Shift+N）测试
   - 确认 api_server.py 已启动且显示"Online"

### 问题2：选择文件后页面崩溃或卡住

**症状**：
- 点击"Select images"选择文件后页面无响应
- 浏览器标签页变灰或显示加载中

**原因**：
- 选择大量文件时，预览生成消耗资源过多
- 浏览器内存不足

**解决方案**：
1. **分批上传**：一次选择不超过 50 张图片
2. **优化图片**：确保每张图片不超过 5MB
3. **清理浏览器**：关闭其他标签页，释放内存
4. **检查浏览器**：升级到最新版本（Chrome、Firefox、Safari、Edge）

### 问题3：上传后收不到"Uploaded X image(s)"提示

**症状**：
- 点击上传按钮没有任何反应
- 页面无错误提示，但也没有成功提示

**原因**：
- SSH 配置未完成（需先通过 Check SSH）
- 后端 api_server.py 未启动或崩溃
- Session ID 为空或不合法

**解决方案**：
1. **检查 SSH 配置**：
   ```
   数据页 -> 在右侧"Remote Training Config"填写所有必需字段 -> 点击"Check SSH"
   ```
   
2. **确认 API 在线**：
   - 查看页面右上角"Online/Offline"状态
   - 如显示 Offline，刷新页面
   - 检查终端是否运行：`python3 web/server/api_server.py`

3. **检查 Session ID**：
   - 不能为空
   - 不能包含特殊字符（建议用小写字母+数字+下划线，如 session_demo_001）

4. **查看浏览器控制台**：
   - 按 F12 打开开发者工具
   - 切换到"Console"标签
   - 查看红色错误信息，记录完整错误文本用于排查

### 问题4：预览网格中看不到上传的图片

**症状**：
- 选择文件后，下面的网格显示"No images selected"
- 或网格中的图片显示为破损

**原因**：
- 文件格式不被支持
- 文件太大导致生成预览失败
- 浏览器权限问题

**解决方案**：
1. **检查文件格式**：仅支持 PNG、JPG、JPEG、BMP、GIF、WebP、TIF、TIFF
   - 其他格式如 RAW、HEIC 需转换为 JPG/PNG

2. **压缩文件大小**：
   ```bash
   # Mac/Linux：用 ImageMagick 批量压缩
   mogrify -resize 50% -quality 80 *.jpg
   
   # 或用在线工具：https://tinypng.com/
   ```

3. **尝试不同浏览器**：有些浏览器对 WebP 等格式的支持差异

### 问题5：上传到远端后提示"远端目录不可写"（WGSC-STEP4-PATH-WRITE-001）

**症状**：
- Check SSH 时报错"远端目录不可写"
- Step4 检查失败

**原因**：
- Remote Workspace Root 或 Remote Output Root 不存在
- 账号对目录无写权限
- 远端磁盘已满

**解决方案**：
1. **SSH 登录远端手动检查**：
   ```bash
   ssh user@host -p 22
   ls -ld /tmp/web_scan/workspaces/
   touch /tmp/web_scan/workspaces/.test && rm /tmp/web_scan/workspaces/.test
   ```

2. **如果目录不存在，创建它**：
   ```bash
   # 在远端执行
   mkdir -p /tmp/web_scan/workspaces /tmp/web_scan/outputs
   chmod 755 /tmp/web_scan/workspaces /tmp/web_scan/outputs
   ```

3. **检查磁盘空间**：
   ```bash
   df -h /tmp  # 至少需要 100GB 可用空间
   du -sh /tmp/web_scan/  # 查看当前占用
   ```

4. **在页面中修改路径**：如果 `/tmp` 权限有限，改用 `$HOME/web_scan_data`
   ```
   Remote Workspace Root: /home/username/web_scan_data/workspaces
   Remote Output Root: /home/username/web_scan_data/outputs
   ```

### 问题6：浏览器自动清理缓存导致文件选择再次丢失

**症状**：
- 浏览器设置为"关闭时清理数据"
- 每次打开页面后之前选择的文件都消失

**原因**：
- 旧版本中文件列表存储在 localStorage，被浏览器清理
- 新版本虽然改进了，但如果会话被中断仍可能丢失

**解决方案**：
1. **不要设置关闭浏览器时自动清理**：
   - Chrome：设置 -> 隐私和安全 -> 清除浏览数据 -> 取消"退出时清除Cookie及其他网站数据"
   - Firefox：首选项 -> 隐私 -> 关闭 Firefox 时删除Cookie和网站数据

2. **改用本地上传**：
   - 在数据页选择后立即点击"Upload Selected Photos"，不要关闭浏览器
   - 如果需要临时中断，点击"Materialize Session"以保存进度

3. **定期备份配置**：
   ```bash
   # 导出 localStorage
   # 在浏览器控制台执行：
   copy(JSON.stringify(localStorage))
   ```

---

## 15. 快速诊断流程图

```
页面显示"选中一张或多张照片"错误
  │
  ├─ 是否选择了文件？
  │  ├─ 否 → 请先选择图片文件
  │  └─ 是 → 继续下一步
  │
  ├─ 浏览器是否显示"Online"？
  │  ├─ 否 → 1) 检查 api_server.py 是否运行
  │  │       2) 检查网络（防火墙/VPN）
  │  └─ 是 → 继续下一步
  │
  ├─ 是否完成了"Check SSH"？
  │  ├─ 否 → 填写 Remote Training Config，点击"Check SSH"
  │  └─ 是 → 继续下一步
  │
  ├─ Check SSH 是否返回"passed"？
  │  ├─ 否 → 根据错误码查看第9章节的错误代码表
  │  └─ 是 → 继续下一步
  │
  ├─ Session ID 是否为空或包含特殊字符？
  │  ├─ 是 → 填写合法的 Session ID（如 session_demo_001）
  │  └─ 否 → 继续下一步
  │
  └─ 清除浏览器缓存 + 强制刷新
     （Ctrl+Shift+Delete 然后 Ctrl+R）
     如问题仍存在，按 F12 查看控制台错误
```

---

## 16. 高级调试技巧

### 查看后端实时日志

```bash
# 终端中启动服务时保持输出可见
python3 web/server/api_server.py --host 127.0.0.1 --port 8080

# 或在后台运行但可以查看日志
tail -f /tmp/web_scan_debug.log  # 如果有记录
```

### 检查浏览器网络请求

1. 打开开发者工具（F12）
2. 切换到"Network"标签
3. 执行上传操作
4. 查看请求列表：
   - `stream-frame` 请求是否返回 200
   - Response 中是否有 `error` 字段
   - 检查 request body 是否包含完整的 image_data

### 重置所有本地存储

```javascript
// 在浏览器控制台执行
localStorage.clear();
sessionStorage.clear();
location.reload();
```

### 验证 API 服务健康

```bash
# 在终端执行
curl -s http://127.0.0.1:8080/api/health | python -m json.tool

# 应输出类似：
# {
#   "ok": true,
#   "status": "online"
# }
```

---

## 17. 反馈与支持

如遇到本文档未覆盖的问题，请提供：

1. **错误代码**（如 WGSC-STEP4-SSH-AUTH-001）
2. **完整错误信息**（从浏览器控制台或服务器日志复制）
3. **操作步骤**（能否复现问题）
4. **系统信息**：
   - 操作系统及版本
   - 浏览器类型及版本
   - Python 版本
   - 远端系统配置（GPU、CUDA 版本等）

将此信息发送给技术支持团队，以便快速定位问题。
