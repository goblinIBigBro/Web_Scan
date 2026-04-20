# Change Log

## 2026-04-20

### 远程数据集管理与自动 COLMAP（Step4/Step5）

- 后端远程执行增强（`web/server/remote_executor.py`）：
  - `remote_preflight_check()` 新增：
    - 远端 `colmap` 可用性检查（可按需强制）。
    - 扫描并返回远端历史数据集列表（按算法族目录）。
  - `run_remote_algorithm()` 新增执行模式：
    - 新上传数据：支持自动远端 COLMAP 预处理。
    - 历史数据复用：支持直接选择既有远端数据集，跳过上传与 COLMAP。
    - 命名保存：训练前可将当前输入固化到命名数据集目录。
  - 新增阶段回调：`resolving_dataset_workspace`、`using_existing_dataset`、`executing_remote_colmap`、`saving_named_dataset`。

- 后端 API 对接（`web/server/api_server.py`）：
  - `POST /api/remote-check` 支持传入 `algorithm_family`，并返回远端 `datasets` 列表。
  - `POST /api/run-remote-algorithm` 支持新字段：
    - `capture_id`、`dataset_name`
    - `auto_colmap`
    - `use_existing_remote_dataset`
    - `remote_dataset_id` / `remote_dataset_path`
  - `stream/materialize/prepare-colmap` 链路接入 `capture_id` 与 `dataset_name`，支持分批采集与命名物化。

- 前端工作流升级（`web/index.html` + `web/src/core/app.js` + `web/styles.css`）：
  - Step3 新增 `Capture Batch ID`（支持一键生成新批次）。
  - Step4 新增远端历史数据选择区（下拉 + 自定义路径 + 状态摘要）。
  - Step5 新增 `Dataset Name` 与 `Auto-run COLMAP` 选项。
  - 一键训练分支化：
    - 新上传模式：上传帧 -> 远端自动 COLMAP -> 训练。
    - 历史复用模式：直接使用远端数据集 -> 训练。
  - Step 门禁逻辑更新：启用“复用历史数据”时，允许跳过新帧采集。

### 数据隔离与默认路径

- 采集帧保存路径由会话级改为批次级：
  - `web/generated/streams/<session>/captures/<capture_id>/input`
- 物化数据集改为命名实例目录：
  - `web/generated/datasets/<session>/datasets/<dataset_id>`
- 远程提交默认输出目录追加批次/数据集后缀，减少不同采集批次之间的结果覆盖。

## 2026-04-18

### Step1-5 流程重构（防卡住 + 错误码可追溯）

- 后端接口增强（`web/server/api_server.py`）：
  - 新增统一结构化错误返回字段：`code / step / reason / details / manual_url / manual_anchor / next_action`。
  - 新增 `POST /api/remote-check`，用于 Step4 远程 SSH 预检。
  - `POST /api/environment-check` 语义改为 Web Runtime Check：
    - 检查 API 运行态、`web/index.html`、viewer 资源、`web/generated` 可写、`paramiko` 可用性。
    - 不再把本地模型训练环境（repo/cuda/colmap/python module）作为 Web 流程阻断条件。
  - `POST /api/run-remote-algorithm` 移除 `hac-plus-plus` 硬编码限制，改为“适配器 operation 模板能力驱动”。
  - Step3/Step5 关键接口补充错误码（stream/materialize/workspace/pipeline 等）。

- 远程执行模块增强（`web/server/remote_executor.py`）：
  - 新增 `remote_preflight_check()`：
    - SSH 连通性检查
    - 账号认证检查
    - 远程 `repo_path` 存在性检查
    - `workspace_root/output_root` 可写检查
    - 远程 python 可执行检查
  - `RemoteExecutionError` 支持 `code_hint/stage`，便于前端展示步骤级失败原因。

- 适配器验证逻辑调整（`web/server/adapter_registry.py`）：
  - `validate_adapter().is_ready` 从“本地路径存在性”调整为“能力存在性（有 enabled operation）”。
  - 保留 `repo_exists/cwd_exists` 作为告警信息，不再作为主流程硬阻断。

- 前端主流程重构（`web/src/core/app.js`）：
  - 删除 `REMOTE_ONE_CLICK_FAMILY=hac-plus-plus` 硬门槛。
  - 新增 Step4 `Check SSH` 动作并接入 `/api/remote-check`。
  - Step1-5 状态机升级：新增 `sshChecked` 门槛，避免“验证通过但下一步卡住”。
  - 新增步骤结果卡（idle/running/success/failed），每一步都能看到明确成功/失败反馈。
  - API 错误对象透传错误码，前端直接显示 `WGSC-STEP-xxx`。

- 前端布局升级（`web/index.html` + `web/styles.css`）：
  - Workflow 标签调整为：Runtime Check / Adapter Capability / Capture / SSH Remote Check / Start Remote Job。
  - Step4 增加 `Check SSH` 按钮。
  - 每步新增结果区，显示步骤结果与失败原因。

- 文档更新：
  - `web/WEB_TRAINING_MANUAL_ZH.md`：新增 Step1-5 完成判定与错误码索引。
  - `web/WEB_TRAINING_MANUAL_EN.md`：同步英文错误码索引。

### 兼容性补充（2026-04-18）

- 保留现有本地调试接口（`/api/run-algorithm`、`/api/run-capture-pipeline` 等）。
- 旧版前端若只读取 `error` 字段仍可工作；新版前端会优先使用结构化错误字段。

### 执行监控与日志面板可视化补充（2026-04-18）

- 前端信息架构修复（`web/index.html`）：
  - 修正 `job-logs-panel` 锚点误绑定问题，确保 `View Logs` 自动展开命中 `Job Logs and Metrics` 面板。
  - `Job Logs and Metrics` 重构为分区布局：工具栏、下载动作、指标表区、原始日志区。
  - 新增 `Copy Raw Log` 按钮与 `Tail Lines (80/120/200/400)` 选择器。

- 前端交互增强（`web/src/core/app.js`）：
  - `loadJobLogs` 支持动态 tail 行数（由 `jobLogState.tailLines` 控制）。
  - 新增日志复制动作（优先 Clipboard API，失败回退 `execCommand('copy')`）。
  - 日志面板元信息增加 tail 行数反馈，便于定位当前视图范围。

- 前端视觉优化（`web/styles.css`）：
  - `Job Logs and Metrics` 双栏布局（左指标表、右日志尾部）并支持小屏自动单列。
  - 指标表头 sticky + 容器限高滚动，避免长表遮挡页面。
  - 原始日志区固定高度并可滚动，提升长日志可读性。

- 文档同步（`web/WEB_TRAINING_MANUAL_ZH.md`、`web/WEB_TRAINING_MANUAL_EN.md`）：
  - 补充 `System Board` 执行监控使用方式。
  - 明确 `View Logs` 自动跳转与日志面板新布局。
  - 更新一键流程中日志查看步骤说明，避免旧文案造成误导。

### 提交前路径强制确认（2026-04-18）

- 前端新增强制确认（`web/src/core/app.js`）：
  - 本地提交 `Submit Job` 与远程一键 `One-click Upload and Remote Train` 前，都会弹出确认框。
  - 强制用户确认 `checkpoint_path` 与 `output_dir` 当前值，取消则中止提交。
  - 若 `output_dir` 为空，前端直接阻断并提示填写。
  - 请求体新增 `path_confirmation`：
    - `confirmed`
    - `confirmed_at`
    - `family`
    - `operation`
    - `checkpoint_path`
    - `output_dir`

- 后端新增强制校验（`web/server/api_server.py`）：
  - 新增 `validate_path_confirmation_payload()`。
  - `POST /api/run-algorithm` 与 `POST /api/run-remote-algorithm` 现在要求 `path_confirmation` 必须存在且 `confirmed=true`。
  - 若命令模板依赖 `{checkpoint_path}`/`{output_dir}`，后端会校验确认值与本次实际提交值一致（含 `output_dir` 解析后比对）。
  - 不满足时返回：`WGSC-STEP5-CONFIRM-001`，并附带差异详情与下一步操作建议。

- 稳健性补充（`web/server/remote_executor.py` + `web/server/api_server.py`）：
  - 已接入 `sanitize_formatted_command()`，在占位符为空时自动移除悬空 flag（如无值 `--model-dir`），避免 argparse 直接失败。

## 2026-04-17

### 内置远程训练闭环（首版）

- 后端新增远程执行模块：`web/server/remote_executor.py`
  - 内置 SSH/SFTP 执行与文件同步（上传 workspace、远程执行、下载 output）。
  - 远程配置校验：`host/port/username/password/repo_path/workspace_root/output_root/python/activate_cmd`。
  - 作业返回脱敏：不在 job 中回传明文密码。

- 后端新增接口：`POST /api/run-remote-algorithm`
  - 当前限定：`algorithm_family=hac-plus-plus`、`operation=train`。
  - 支持 `auto_materialize=true` 自动将会话转为训练 workspace。
  - 远程作业状态阶段：`connecting / uploading_workspace / executing_remote_command / downloading_output / completed / failed`。

- 前端新增一键流程：
  - 新按钮：`One-click Upload and Remote Train`。
  - 流程：上传帧 -> 自动物化 session -> 提交远程训练 -> 轮询 -> 自动渲染。
  - 新增 Remote Training 配置区（主机、端口、账号密码、远程路径、激活命令等）。

- 前端状态文案新增：
  - `remote-connecting`
  - `remote-uploading`
  - `remote-training`
  - `remote-downloading`
  - `remote-completed`
  - `remote-error`

- 文档更新：
  - 重写 `web/WEB_TRAINING_MANUAL_ZH.md`（中文）
  - 重写 `web/WEB_TRAINING_MANUAL_EN.md`（英文）
  - 更新 `web/README.md`，补充远程模式依赖与入口

### 远程优先流程收纳与日志回传增强

- 前端流程区重构（`web/index.html` + `web/styles.css` + `web/src/core/app.js`）：
  - 左侧 Guided Workflow 改为可折叠分组（`details`）。
  - 默认行为：自动收起已完成/锁定分组，自动展开激活分组。
  - 手动优先：用户手动展开/收起状态会被记住并优先于自动折叠。
  - 流程主线调整为远程优先：
    - Step 4 从 `Materialize Session` 调整为 `Configure Remote`
    - Step 5 从 `Start Job` 调整为 `Start Remote Job`
  - 本地链路保留但收纳到 `Local Debug (Optional)`。

- 远程主流程一致性增强：
  - 新增远程配置就绪判定（host/user/password/repo/workspace/output 必填）。
  - `One-click Upload and Remote Train` 按钮仅在远程配置可用时启用。
  - 当算法族非 `hac-plus-plus` 时，提示远程一键模式受限，并引导到本地调试分组。

- 后端日志持久化与下载（`web/server/api_server.py`）：
  - 每个 job 持久化到 `web/generated/job_logs/<job_id>/`：
    - `runtime.log`（原始运行日志）
    - `metrics.csv`（指标历史）
  - 新增接口：
    - `GET /api/jobs/{jobId}/logs?page=1&page_size=20&tail_lines=120`
    - `GET /api/jobs/{jobId}/logs/download`
    - `GET /api/jobs/{jobId}/metrics.csv`
  - 任务响应中新增日志相关 URL 字段，便于前端直接使用。

- 前端日志面板增强：
  - `System Board -> Job Logs and Metrics` 新增：
    - Job 选择器
    - 指标分页表格
    - 原始日志尾部
    - `.log` / `metrics.csv` 下载按钮
  - Job Monitor 卡片新增快速入口：
    - `View Logs`
    - 下载 `.log`
    - 下载 `metrics.csv`

- 文档同步：
  - 更新 `web/README.md`
  - 更新 `web/WEB_TRAINING_MANUAL_ZH.md`
  - 更新 `web/WEB_TRAINING_MANUAL_EN.md`
  - 补充 HAC++ 远程配置指南：推荐机器、推荐环境、SSH 注意事项、预检清单与其他模型占位说明。

### 兼容性说明

- 现有本地模式接口仍保留：`/api/run-algorithm`、`/api/stream-frame`、`/api/materialize-session`、`/api/run-capture-pipeline`。
- 一键远程模式为增量能力，不替换原有分步调试链路。

## 2026-04-12

### Web 调试修复与测试资产补充

- 前端跨平台默认路径修复（Windows 调试可用）：
  - 修改 `web/src/core/app.js`，移除写死的 Linux 路径（`/home/fansonglin/...`）。
  - `applyMaterializedSession()` 默认输出目录改为 `/web/generated/runs/<session>/<family>`。
  - `applyColmapWorkspace()` 默认输出目录改为 `/web/generated/runs/<session>/<family>`。
  - `handleRunCapturePipeline()` 默认输出目录改为 `/web/generated/runs/<session>/<family>`。
  - `bootstrapDefaults()` 中 `server-extra-args` 默认值改为：`workspace=""`、`cwd=""`，避免 Windows 下提交任务即失败。

- SH viewer 稳定性修复（修复 `Float32Array` 对齐报错）：
  - 修改 `web/viewers/megs-sh-viewer.js`。
  - 在 `generateTexture()` 和 `runSort()` 中，构造 `Float32Array` 前先按 4 字节对齐，避免 `RangeError: byte length of Float32Array should be a multiple of 4`。
  - 在 worker 接收 `e.data.buffer` 时，将 buffer 截断到完整记录（32 字节对齐）并使用安全 `vertexCount`。
  - 在文件加载与流式读取路径里，`postMessage` 仅发送完整记录切片（`slice(0, completeBytes)`），避免半包数据进入排序/贴图流程。

- 新增最小可复现调试场景（用于快速验证页面链路）：
  - 新增 `web/generated/scene_debug/minimal_input.ply`（3 顶点最小样例）。
  - 使用 `web/tools/export_scene_package.py` 导出生成：
    - `web/generated/scene_debug/package/scene_manifest.json`
    - `web/generated/scene_debug/package/primitives/base.bin`
    - `web/generated/scene_debug/package/primitives/appearance_sh.bin`
    - `web/generated/scene_debug/package/source/minimal_input.ply`
  - 用于调试入口：`/web/?manifest=/web/generated/scene_debug/package/scene_manifest.json`。

### Merged design baseline

- 将根目录 `gaussian_encoding_web_renderer_design.md` 的核心设计原则合并进本变更记录：
  - 分层结构：`算法适配层 / 数据桥接层 / Web 渲染层`
  - 统一目标：训练侧与 Web 侧解耦，优先兼容多算法表示
  - 场景协议方向：`Scene Manifest + base.bin + appearance_*.bin + auxiliary`
  - 过渡策略：当前继续兼容 `.ply`，长期转向正式 scene package
  - 渲染策略：首版固定 `WebGL2 + SH/SG`，后续再推进压缩解码和 WebGPU
- 本仓库后续所有与 Web 平台相关的结构调整，以本节和后续 change log 为准持续演进。

### Initial web platform scaffold

- 新建 `web/` 独立目录，作为统一的高斯编码 Web 平台。
- 增加统一入口页、控制面板、状态面板和 viewer shell。
- 接入 `SH` 与 `SG` 两条 legacy viewer 路径。
- 增加 survey 方法注册表，映射 `3dgs-compression-survey` 中的算法家族。
- 定义 scene manifest 基本结构与示例模板。

### Server/export/task integration

- 新增 `web/tools/export_scene_package.py`，支持 `PLY -> unified scene package` 导出。
- 新增 `web/server/api_server.py`，提供：
  - `GET /api/health`
  - `GET /api/algorithms`
  - `GET /api/jobs`
  - `POST /api/export-scene`
  - `POST /api/run-algorithm`
- 新增前端 API client，支持：
  - API 健康检查
  - 导出场景包
  - 提交算法任务
  - 刷新任务列表
- 新增当前场景分享 URL 展示，用于生成可直接访问的 Web 地址。
- 新增 query 参数驱动加载：
  - `?manifest=...`
  - `?source=...&representation=...&family=...`
- 新增算法切换时自动同步推荐 representation。

### Multi-repo adapter registry

- 新增 `web/config/algorithm_adapters.json`，将算法兼容从硬编码升级为配置驱动。
- 新增 `web/server/adapter_registry.py`，服务端统一读取 adapter 配置。
- 当前已纳入十多个算法/仓库适配入口：
  - `vanilla-3dgs`
  - `megs2`
  - `gaussianspa`
  - `hac`
  - `hemgs`
  - `hac-plus-plus`
  - `contextgs`
  - `codecgs`
  - `fcgs`
  - `compgs`
  - `rdo-gaussian`
  - `compressed-3dgs`
  - `mesongs`
  - `octree-gs`
  - `gaussianpro`
  - `atomgs`
  - `taming3dgs`
- 每个 adapter 支持声明：
  - `repo_path`
  - `repo_url`
  - `representation`
  - `compatibility`
  - `operations`
  - `default_cwd`
- 前端新增 operation 选择器，服务端根据 `operation + adapter template` 调度实际命令。

### Reference-driven workflow upgrades

- 参考 `gaussian-splatting-lightning` 的工程化方向，将下列能力纳入当前平台：
  - 算法切换不再依赖单一 viewer 页面，而是进入统一 pipeline 配置
  - 加载前预处理参数显式化：
    - parser
    - downsample
    - mask path
    - reorient
    - uint8 image cache
    - async caching
  - 多模型工作流通过 `Recent Scenes` 保留最近加载/导出的场景
- 参考 `gaussian-splatting-web` 的浏览器 viewer 思路，将下列能力纳入当前平台：
  - 增加 viewer backend 选择入口，当前 `WebGL2` 可用，`WebGPU` 标为 planned
  - 场景编辑参数进入 manifest metadata：
    - translation
    - rotation
    - scale
    - background
- scene package 导出时会把 `preprocess/editor/backend` 一并写入 manifest metadata。
- 算法任务提交时会把 `preprocess/editor/backend` 一并写入 job payload，便于服务器调度底层仓库。

### Design file consolidation

- 已将独立设计稿内容合并到 `web/change.md`。
- 删除单独文件 `web/gaussian_encoding_web_renderer_design.md`。
- 后续所有设计与实现变化统一记录在 `web/change.md`。

### Adapter management and validation

- 新增 `web/config/algorithm_adapters.override.json`，用于保存本地仓库路径覆盖配置，避免直接修改基础 registry。
- 服务端新增 adapter 管理能力：
  - `POST /api/adapters/update`
  - `POST /api/adapters/validate`
- 服务端 `GET /api/algorithms` 现在返回：
  - 算法列表
  - 每个 adapter 的校验状态
- 新增 adapter 校验信息：
  - `repo_exists`
  - `cwd_exists`
  - `is_ready`
  - `suggested_cwd`
- 前端新增：
  - `Adapter Detail` 面板
  - repo path / default cwd 可保存
  - 仓库校验按钮
  - 保存配置按钮
- 现在可以直接在网页中逐个维护十多份仓库的本地路径，而不是手改配置文件。

### Realtime algorithm metrics on web

- 服务端新增任务日志指标提取：
  - `fps`
  - `iter`
  - `loss`
  - `psnr`
  - `ssim`
  - `lpips`
- 任务完成后会从 stdout/stderr 中解析上述指标并写入 `job.metrics`。
- 前端新增任务轮询逻辑，会在任务运行期间周期性请求 job 状态。
- Web 状态面板新增：
  - `Algo FPS`
  - `Loss`
  - `PSNR`
  - `Iter`
- Job Monitor 面板新增每个任务的 metrics 摘要。
- `web/README.md` 已补充当前系统的完整链路说明和完整性检查说明。

### Camera/image realtime pipeline

- Web 页面新增 `Realtime Input` 面板：
  - 启动/停止摄像头
  - 单张图片上传
  - 手动发送当前帧
  - 自动周期流式上传
- Web 页面新增 `Realtime Preview`：
  - 本地摄像头视频预览
  - 服务器处理结果图像回显
- 服务端新增 `POST /api/stream-frame`
  - 保存输入帧到 `web/generated/streams/<session_id>/input/`
  - 默认镜像输入帧到 `output/latest.png` 作为回显占位
  - 若 adapter 支持 `process_frame`，则立即启动底层算法任务
- 前端发送帧后会：
  - 更新处理结果图像
  - 若创建了任务，则自动轮询 job 状态
  - 实时刷新算法指标

### Streaming job execution

- 服务端算法执行由一次性 `subprocess.run` 改为流式 `subprocess.Popen`。
- stdout/stderr 在任务运行中持续读取并增量写入 job 状态。
- metrics 提取从“任务结束后解析”升级为“任务运行中持续解析”。
- 前端现可在任务执行过程中实时看到指标刷新，而不是只在结束后看到结果。

### First-batch repo entries

- adapter registry 新增：
  - `gaussian-splatting-lightning`
  - `gaussian-splatting-web`
- 这两项当前分别承担：
  - 多算法训练/验证框架入口
  - WebGPU viewer backend 参考入口

### Realtime bridge contract

- 新增 `web/tools/realtime_adapter_bridge.py`，作为实时输入链路的统一桥接脚本。
- 第一批 adapter 已启用桥接式 `process_frame`：
  - `gaussian-splatting-lightning`
  - `MEGS2`
  - `GaussianSpa`
- 统一约定底层实时处理输出：
  - `output/latest.png`
  - `output/metrics.json`
- 服务端 job 在运行期间会持续读取这些产物，并把：
  - `result_url`
  - `metrics`
  回传给前端。
- 前端轮询 job 时，若发现 `result_url` 更新，会自动刷新 `Processed Result` 图像。

# Gaussian Encoding Web Renderer Design

## 1. 目标

构建一个面向“高斯编码重建”算法的网页版渲染工具，覆盖从算法底层参数导出到浏览器端显示的完整链路，并能兼容多种高斯表示方法，而不只绑定单一论文实现。

首阶段不直接追求完整产品，而是先搭建可扩展的基础结构，满足以下目标：

- 支持多种算法接入：Vanilla 3DGS、SH-based Gaussian、SG-based Gaussian、后续压缩/剪枝/量化变体。
- 解耦训练侧与 Web 侧：训练框架负责产出统一描述，Web 端只关心加载、解码、排序、渲染。
- 保留“算法特征”的表达能力：不能因为统一格式而丢掉 SG lobes、SH 系数、pruning mask、编码块等信息。
- 支持未来逐步演进为“研究展示工具 + 算法调试工具 + 轻量部署工具”。

## 2. 参考现状

### 2.1 本地现有基础

当前目录中的 `MEGS-2-main` 已经具备两个关键能力：

- 训练/推理端已经支持 `SphericalGaussianModel`，并能将参数写入 `.ply`。
- `WebGL_viewer` 已经能在浏览器中解析 `.ply` 并渲染：
  - `main_sg.js`：支持 SG attributes。
  - `main_sh.js`：支持 3rd-order SH。

这说明我们不是从零开始，而是已经有：

- 一个“算法参数导出格式”的原型。
- 一个“浏览器端解析 + 排序 + splat 渲染”的原型。

### 2.2 外部参考项目

参考 `yzslab/gaussian-splatting-lightning` 的价值不在于直接复刻其 viewer，而在于借鉴它的工程组织方式：

- 多算法共存。
- 多模型加载。
- 训练输出与 viewer 解耦。
- 第三方模型适配入口明确。

对我们更有价值的是“可扩展框架设计”，而不是直接照搬它的渲染实现。

## 3. 产品定位

这个工具建议定位为三层结构：

1. 算法层
负责不同高斯编码/重建算法的训练结果组织、导出和适配。

2. 数据桥接层
负责把不同算法内部表示转换为统一的 Web 可消费格式。

3. Web 渲染层
负责资源加载、参数上传、视锥裁剪、深度排序、着色与交互。

最终交付形态建议是：

- 一个本地/服务端导出工具链。
- 一个标准化场景包格式。
- 一个基于 WebGL2，后续可升级到 WebGPU 的前端 viewer。

## 4. 核心设计原则

### 4.1 算法兼容优先于单算法最优

底层接口必须允许不同表示共存：

- 各向异性 Gaussian + RGB/opacity
- Gaussian + SH
- Gaussian + SG lobes
- Gaussian + 压缩编码参数
- Gaussian + 剪枝/稀疏索引

不能把首版格式写死成单一 `point_cloud.ply`。

### 4.2 统一“描述层”，不统一“训练内部实现”

不同算法训练时的数据结构可以完全不同，但导出到 Web 时应统一成一套“Scene Description + Primitive Payload”。

### 4.3 Viewer 先稳定，再做编码优化

首版先保证：

- 数据能正确显示。
- 算法差异可被表达。
- 前端渲染路径可插拔。

压缩、流式加载、块级调度、增量解码可以作为第二阶段增强。

### 4.4 数据格式要面向传输

研究代码常用 `.ply` 便于调试，但 Web 部署更适合：

- 二进制 header + payload
- chunk 化
- 支持 typed array 直接上传 GPU
- 支持 progressive loading

因此 `.ply` 只适合作为中间调试格式，不建议作为长期正式发布格式。

## 5. 总体架构

建议新系统采用以下逻辑结构：

```text
Gaussian Encoding Web Renderer
├── algorithms/          # 各算法适配器
├── exporters/           # 训练输出 -> 统一场景格式
├── scene_format/        # 场景描述协议
├── viewer_core/         # Web 端加载/调度/渲染核心
├── shaders/             # SH/SG/vanilla 等着色路径
├── ui/                  # 控制面板、调试面板、场景管理
└── docs/                # 设计与格式说明
```

若后续在本仓库内继续实现，建议采用如下目录方案：

```text
Web_Scan/
├── MEGS-2-main/                     # 当前参考训练代码
├── docs/
│   ├── architecture/
│   ├── format/
│   └── roadmap/
├── tools/
│   ├── exporters/
│   ├── converters/
│   └── validators/
├── web/
│   ├── app/
│   ├── public/
│   ├── src/
│   │   ├── core/
│   │   ├── loaders/
│   │   ├── renderers/
│   │   ├── shaders/
│   │   ├── scene/
│   │   ├── ui/
│   │   └── workers/
│   └── package.json
└── gaussian_encoding_web_renderer_design.md
```

## 6. 分层设计

### 6.1 算法适配层

职责：

- 接入不同训练框架输出。
- 将算法内部参数映射到统一场景协议。
- 管理算法特有字段。

建议定义统一适配器接口：

```text
AlgorithmAdapter
├── load_checkpoint()
├── load_point_representation()
├── export_scene_manifest()
├── export_primitive_payload()
└── export_algorithm_metadata()
```

建议首批适配器：

- `Vanilla3DGSAdapter`
- `SHGaussianAdapter`
- `SphericalGaussianAdapter`
- `CompressedGaussianAdapter`

其中：

- `SphericalGaussianAdapter` 可直接参考 `MEGS-2-main/scene/spherical_gaussian_model.py` 的字段组织。
- `SHGaussianAdapter` 可兼容传统 `f_dc + f_rest` 的 PLY 结构。

### 6.2 统一场景描述层

建议定义一个统一场景包 `Scene Manifest`，至少包含：

```json
{
  "scene_id": "garden_megs2",
  "version": "0.1.0",
  "coordinate_system": "colmap",
  "representation": "gaussian",
  "appearance_model": "sg",
  "primitive_count": 1250000,
  "payloads": {
    "base": "primitives/base.bin",
    "appearance": "primitives/appearance_sg.bin",
    "index": "primitives/index.bin"
  },
  "camera": {
    "default_fov": 60.0,
    "initial_pose": {}
  },
  "algorithm": {
    "name": "MEGS2",
    "checkpoint_step": 30000,
    "sg_degree": 3,
    "variable_sg_bands": true
  }
}
```

建议把通用字段和算法特有字段分开：

- 通用字段：位置、缩放、旋转、不透明度、包围信息。
- 表观字段：RGB / SH / SG / learned feature。
- 算法元信息：pruning ratio、编码策略、量化信息、版本号。

### 6.3 数据载荷层

建议将 primitive 数据拆成 3 类：

1. `base.bin`
包含所有算法共享字段：

- `position`
- `scale`
- `rotation`
- `opacity`
- `primitive_id`
- 可选 `importance`

1. `appearance_*.bin`
按表观模型拆分：

- `appearance_rgb.bin`
- `appearance_sh.bin`
- `appearance_sg.bin`
- `appearance_feature.bin`

1. `auxiliary.bin`
放调试或高级功能数据：

- pruning mask
- cluster id
- semantic label
- LOD level
- compression block index

这种拆法优点：

- Web 端按需加载。
- 算法差异集中在 appearance payload，不污染核心渲染主干。
- 后续便于做 progressive streaming。

## 7. Web 端基础结构

### 7.1 前端模块划分

建议前端采用如下模块：

```text
web/src/
├── core/
│   ├── app.ts
│   ├── runtime.ts
│   └── event-bus.ts
├── scene/
│   ├── scene-loader.ts
│   ├── manifest-parser.ts
│   ├── camera-controller.ts
│   └── scene-state.ts
├── loaders/
│   ├── base-loader.ts
│   ├── ply-loader.ts
│   ├── scene-package-loader.ts
│   └── chunk-stream-loader.ts
├── renderers/
│   ├── renderer-interface.ts
│   ├── gaussian-base-renderer.ts
│   ├── sh-gaussian-renderer.ts
│   ├── sg-gaussian-renderer.ts
│   └── debug-renderer.ts
├── shaders/
│   ├── common.glsl
│   ├── gaussian.vert.glsl
│   ├── gaussian.frag.glsl
│   ├── sh_eval.glsl
│   └── sg_eval.glsl
├── workers/
│   ├── depth-sort.worker.ts
│   ├── decode.worker.ts
│   └── stream.worker.ts
└── ui/
    ├── control-panel.ts
    ├── stats-panel.ts
    └── debug-panel.ts
```

### 7.2 渲染主流程

首版推荐固定成以下流程：

1. 加载 `scene_manifest.json`
2. 识别 `appearance_model`
3. 加载对应二进制 payload
4. 在 CPU 或 Worker 中完成：
   - 格式解码
   - 重要度排序初始化
   - 深度排序或 tile/bin 索引构建
5. 上传 GPU 纹理/缓冲
6. 执行对应 renderer
7. UI 层显示性能、算法信息、开关项

### 7.3 渲染接口抽象

建议定义统一 Renderer 接口：

```text
IGaussianRenderer
├── initialize(gl, scene)
├── upload(scenePayload)
├── render(cameraState)
├── resize(width, height)
├── dispose()
```

这样可以在不改 UI 和加载层的前提下切换：

- Vanilla Gaussian Renderer
- SH Renderer
- SG Renderer
- Future WebGPU Renderer

## 8. 基础功能清单

首阶段建议只做最关键功能，避免一开始把工程做散。

### 8.1 必做功能

- 加载单场景。
- 支持至少两类表示：
  - SH Gaussian
  - SG Gaussian
- 鼠标/触控相机控制。
- 基础性能信息：
  - FPS
  - primitive count
  - loaded memory
- 视图参数显示：
  - 相机位置
  - FOV
  - 当前 representation
- 可切换背景色。
- 可切换 splat 尺度倍率。
- 可显示加载进度。

### 8.2 调试功能

- 显示原始 primitive 数量。
- 显示 pruning 后数量。
- 显示 SG axis count 分布。
- 显示 SH degree / SG degree。
- 显示包围盒。
- 显示排序耗时与上传耗时。

### 8.3 第二阶段功能

- 多模型同屏对比。
- 模型平移/缩放/旋转。
- 切换不同 checkpoint。
- progressive loading。
- chunk streaming。
- 录制相机轨迹。
- 热力图模式：
  - alpha
  - size
  - sharpness
  - contribution

## 9. 多算法兼容策略

### 9.1 兼容的关键不是“同一种 shader”，而是“同一种场景协议”

不同算法差异主要在这几个维度：

- 几何 primitive 是否仍是 3D Gaussian。
- 表观模型是 RGB、SH 还是 SG。
- 是否存在 variable-band / variable-axis。
- 是否做了剪枝、聚类、蒸馏、量化。
- 是否需要额外解码步骤。

因此兼容策略应是：

- 几何层共用。
- 表观层分插件。
- 解码层分算法适配器。

### 9.2 建议的兼容矩阵

| 算法类型 | 几何基元 | 表观模型 | Web 侧实现 |
|---|---|---|---|
| Vanilla 3DGS | Gaussian | RGB / SH | `sh-gaussian-renderer` |
| MEGS2 | Gaussian | SG + base RGB | `sg-gaussian-renderer` |
| LightGaussian 类 | Gaussian | SH/RGB + pruning | 复用 base renderer，补充 pruning metadata |
| 压缩编码类 | Gaussian | 取决于算法 | 增加 decode worker |

### 9.3 对 MEGS2 的特殊支持

结合本地代码，MEGS2 需要重点保留以下字段：

- `rgb_base`
- `sg_axis_count`
- `sg_dir_i`
- `sg_sharp_i`
- `sg_rgb_i`
- `scale`
- `rotation`
- `opacity`

这里 `sg_axis_count` 很关键，因为它直接决定每个 primitive 有多少个激活 lobes，首版协议必须原生支持 variable-axis。

## 10. 数据格式建议

### 10.1 过渡阶段

首阶段可以继续支持：

- `.ply` 直接加载

因为本地已有 `main_sg.js` 与 `main_sh.js` 作为验证基础。

但建议把 `.ply` 支持定义为：

- 调试输入格式
- 兼容输入格式

而不是长期标准格式。

### 10.2 正式格式

建议定义一个轻量二进制场景包：

```text
scene_package/
├── scene_manifest.json
├── cameras.json
├── primitives/
│   ├── base.bin
│   ├── appearance_sg.bin
│   ├── appearance_sh.bin
│   └── aux.bin
└── preview/
    └── cover.png
```

`base.bin` 建议使用结构化二进制布局：

```text
float32 x, y, z
float32 sx, sy, sz
float32 qx, qy, qz, qw
float32 opacity
uint32  appearance_offset
uint16  appearance_count
uint16  flags
```

SG appearance 可采用：

```text
float32 rgb_base[3]
uint16 axis_count
uint16 reserved
repeat axis_count:
  float32 dir[3]
  float32 sharpness
  float32 rgb[3]
```

后续如果需要减小体积，再引入：

- `float16`
- 量化法线方向
- block compression
- delta coding

## 11. 首版技术路线建议

### 11.1 图形 API

首版建议：

- `WebGL2`

原因：

- 当前 `MEGS-2-main/WebGL_viewer` 已是 WebGL 路线，复用价值高。
- 浏览器兼容性更稳。
- 适合先把协议、模块、功能跑通。

第二阶段可评估：

- `WebGPU`

适用于：

- 更大规模 primitive
- 更复杂的 sorting / compute
- 更灵活的 buffer 组织

### 11.2 框架选择

如果以“研究工具”和“快速迭代”为优先，建议：

- 前端 UI：`React + Vite`
- 渲染核心：原生 `WebGL2`
- Worker：原生 Worker

不要一开始把渲染主逻辑绑定到 Three.js，因为 Gaussian splatting 的数据流、排序和 shader 组织更适合直接掌控。

### 11.3 性能策略

首版即应纳入以下性能点：

- 深度排序放到 Worker。
- CPU 解码与主线程渲染分离。
- Buffer/Texture 复用，避免频繁重建。
- 按 appearance model 切分 shader program。
- 控制上传频率，只在数据变动时更新 GPU。

## 12. 开发阶段规划

### Phase 0：整理与抽象

- 复盘 `MEGS-2-main` 的 `.ply` 输出字段。
- 复盘 `main_sg.js` / `main_sh.js` 的输入依赖。
- 提炼统一 manifest 与 payload 结构。

交付物：

- 场景协议草案
- adapter 接口草案
- renderer 接口草案

### Phase 1：最小可运行版本

- 搭建 `web/` 基础工程。
- 接入单场景加载。
- 支持 `.ply` 输入。
- 抽象 `SHRenderer` 与 `SGRenderer`。
- 完成基础交互与性能面板。

交付物：

- 浏览器加载单模型。
- SH / SG 两条渲染路径可切换。

### Phase 2：统一导出格式

- 增加 exporter。
- 从训练结果导出 `scene_manifest + *.bin`。
- Web 端支持正式场景包。

交付物：

- 不再依赖手工拷贝 `.ply`。
- 算法侧导出流程可自动化。

### Phase 3：多算法扩展

- 接入 vanilla 3DGS。
- 接入 pruning / compression 变体。
- 增加算法 metadata 面板。

交付物：

- 一个 viewer 支持多个算法结果加载。

### Phase 4：高级功能

- 多模型对比。
- progressive loading。
- 相机轨迹编辑。
- 调试热力图。

## 13. 风险与关键问题

### 13.1 `.ply` 不适合长期承载复杂编码

当算法开始引入：

- variable-length coding
- chunk-level compression
- learned codebook
- feature distillation

`.ply` 会变得越来越难维护，必须尽早转向自定义场景包。

### 13.2 SG / SH 路径不应互相污染

当前本地 viewer 是分 `main_sg.js` 和 `main_sh.js` 的，这个方向是对的。后续应该抽象为：

- 共享几何上传逻辑
- 独立 appearance evaluation shader

而不是把所有分支硬塞进一个超大 shader。

### 13.3 多算法兼容最容易失控的地方在“字段膨胀”

解决方法：

- 通用字段固定。
- 特有字段模块化。
- manifest 显式声明 `appearance_model` 与 `extensions`。

## 14. 建议的第一批落地任务

建议下一步按以下顺序实施：

1. 从 `MEGS-2-main/WebGL_viewer` 中抽离通用能力：
   - 相机控制
   - PLY 解析
   - worker 排序
   - WebGL 上传

2. 定义统一接口：
   - `SceneManifest`
   - `AlgorithmAdapter`
   - `IGaussianRenderer`

3. 先只打通两条算法链路：
   - Vanilla/SH
   - MEGS2/SG

4. 再增加 exporter：
   - `checkpoint -> scene package`

5. 最后再做 UI 面板和多模型管理。

## 15. 本设计结论

这个项目的正确起点不是“再写一个 viewer 页面”，而是构建一套面向多算法的高斯场景描述和渲染框架。

对当前目录而言，最合理的演进路径是：

- 以 `MEGS-2-main` 作为 SG/SH 数据来源参考；
- 借鉴 `gaussian-splatting-lightning` 的多算法组织方式；
- 新建独立的统一导出协议与 Web 渲染核心；
- 首版先支持 SH 和 SG 两条主链路；
- 后续再扩展到压缩编码、剪枝和流式加载。

这能保证后面无论你接 MEGS、LightGaussian，还是新的“高斯编码”方法，都不需要重做 Web 基础设施。

## 2026-04-12 Realtime Workspace Upgrade

- 将底部 `Realtime Preview` 重构为 `Realtime Workspace`，保持左侧采集输入、右侧服务器结果的双栏工作区。
- 右侧结果区新增双模式回显：
  - 优先加载 `processed-viewer-frame`
  - 若服务端没有返回结构化场景，则回退到 `processed-frame`
- 前端新增结果显示策略：
  - `viewer_url` 存在时，右侧直接加载可交互 viewer
  - 否则显示 `latest.png`
  - 若尚无结果，则显示 placeholder
- 服务端 `read_runtime_artifacts()` 增强为识别以下运行产物：
  - `metrics.json`
  - `latest.png`
  - `point_cloud.ply`
  - `latest.ply`
  - `scene.ply`
  - `scene_manifest.json`
- 当服务端输出 `.ply` 时，自动生成 `/web/viewers/sh.html?url=...` 或 `/web/viewers/sg.html?url=...`
- 当服务端输出 `scene_manifest.json` 时，自动生成 `/web/?manifest=...`
- `stream-frame` 接口现在会直接返回 `viewer_url`，因此实时帧处理链路已经具备“图片回显”和“结构 viewer 回显”的统一入口

当前边界：

- 这一轮优化解决的是“结果区表现形态”和“服务端产物识别”，不是“真实高斯算法已全部接通”
- 右侧结果区已能支持鼠标拖动旋转，但前提是底层算法真实写出了 `.ply` 或 manifest
- 若底层算法只产 `latest.png`，右侧仍然只能显示 2D 结果图
- 当前首批 `process_frame` adapter 仍然主要依赖桥接脚本，尚未替换成原生高斯编码/渲染流程

## 2026-04-12 Bridge Scene Output Upgrade

本轮修改过程：

1. 先把上一轮“Realtime Workspace + viewer_url 回显”的修改继续补充到文档主线。
2. 将 `README.md` 的“当前实现内容”改写为按模块划分的基础功能清单，便于后续持续维护。
3. 继续按建议优化实时链路，不再只停留在 `latest.png` 镜像，而是让桥接层直接产出结构化场景结果。

具体改动：

- 升级 [web/tools/realtime_adapter_bridge.py](/home/fansonglin/xieliang/Web_Scan/web/tools/realtime_adapter_bridge.py)
  - 新增 `--representation` 与 `--mode` 参数
  - 在输出目录中同时写出：
    - `latest.png`
    - `point_cloud.ply`
    - `scene_manifest.json`
    - `metrics.json`
  - 生成一个可被 SH/SG viewer 直接加载的占位高斯点云，保证实时链路可以完整演示“结构化结果回传”
- 更新 [web/config/algorithm_adapters.json](/home/fansonglin/xieliang/Web_Scan/web/config/algorithm_adapters.json)
  - `gaussian-splatting-lightning`
  - `megs2`
  - `gaussianspa`
  这三条 `process_frame` 模板都改为显式传入 `representation`，并启用 `copy-and-scene` 模式
- 更新 [web/README.md](/home/fansonglin/xieliang/Web_Scan/web/README.md)
  - 将当前基础功能按“场景渲染 / 算法调度 / 实时输入 / 指标监控”分点汇总
  - 明确桥接层现在已经能输出 `latest.png + point_cloud.ply + scene_manifest.json + metrics.json`

当前意义：

- 即使还没接入真实底层仓库，Web 页面也已经可以稳定演示：
  - 摄像头/图片上传
  - 服务器处理任务启动
  - 指标回传
  - 右侧结构化 viewer 回显
  - 鼠标拖拽旋转结果结构
- 这让前后端工作流先闭环，后面替换成真实算法时只需要替换 `process_frame` 命令，不需要重写 Web 端结果区

## 2026-04-12 Local Repository Integration

本轮继续按“先接入当前目录已有仓库，再逐步替换桥接层”为原则推进。

已完成的本地仓库接入：

- `MEGS-2-main`
- `ContextGS-main`
- `HAC-plus-main`
- `FCGS-main`
- `CompGS-main`
- `Scaffold-GS-main`
- `reduced-3dgs-main`

具体改动：

- 更新 [web/config/algorithm_adapters.json](/home/fansonglin/xieliang/Web_Scan/web/config/algorithm_adapters.json)
  - 将 `ContextGS`、`HAC++`、`FCGS`、`CompGS` 从“外部占位”改为“本地仓库已接入”
  - 新增 `Scaffold-GS` 与 `Reduced 3DGS` 两个本地 adapter
  - 为上述仓库补充真实 `repo_path` 与 `default_cwd`
  - 按仓库中实际存在的脚本，修正 `train / render / encode / decode / compress` 命令模板
  - 对尚未有 Web 原生解码链路的方法，统一追加 `process_frame -> realtime_adapter_bridge.py`
- 更新 [web/src/scene/survey-method-registry.js](/home/fansonglin/xieliang/Web_Scan/web/src/scene/survey-method-registry.js)
  - 同步增加 `scaffold-gs`、`reduced-3dgs`
  - 调整 `ContextGS / HAC++ / FCGS / CompGS` 的兼容说明
- 更新 [web/README.md](/home/fansonglin/xieliang/Web_Scan/web/README.md)
  - 新增“当前已接入本目录本地仓库”列表

当前状态：

- adapter 总数已增加到 `21`
- 本目录已有的主流高斯/压缩仓库，已经基本都能在 Web 页面里被选中和调度
- 其中一部分是“真实训练/编码命令 + 桥接回显”，不是“真实实时推理命令”
- 这一步的价值是先把仓库治理和页面调度统一起来，后面逐仓替换成真正的 `process_frame` 即可

## 2026-04-12 Runtime Artifact Auto-discovery

继续按“先打通真实仓库输出发现，再逐步替换实时桥接”为原则推进。

本轮改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - `read_runtime_artifacts()` 现在会对 `output_dir` 做 `resolve()`，修复相对路径场景下无法生成 `viewer_url/result_url` 的问题
  - 新增对真实训练/渲染目录结构的自动发现：
    - `point_cloud/iteration_*/point_cloud.ply`
    - `test/ours_*/renders/*.png`
    - `train/ours_*/renders/*.png`
  - 这使得 `MEGS2`、`reduced-3dgs` 等本地仓库按默认输出目录运行后，Web 服务端可以自动识别结构结果和渲染结果
- 更新 [web/config/algorithm_adapters.json](/home/fansonglin/xieliang/Web_Scan/web/config/algorithm_adapters.json)
  - 修正 `MEGS2` 的 `train/render` 命令，使其围绕 `output_dir` 组织
  - 同步修正 `GaussianSpa`、`HAC++` 等部分本地/半本地 adapter 的命令模板
- 更新 [web/README.md](/home/fansonglin/xieliang/Web_Scan/web/README.md)
  - 增加“服务端自动发现真实运行产物”的说明

验证结果：

- 已确认 `read_runtime_artifacts('web/generated/streams/test-session/output', 'sg')` 会返回：
  - `manifest_url`
  - `viewer_url`
  - `point_cloud_url`
  - `result_url`
- 这说明前端轮询 job 时，已经可以在结构化产物存在时自动切换到右侧可旋转 viewer

## 2026-04-12 Main Viewer Auto-mount

本轮继续优化“算法任务结果如何回到主工作区”。

具体改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - 新增 `enrich_job()`，在 `GET /api/jobs` 和 `GET /api/jobs/{id}` 时动态补全：
    - `manifest_url`
    - `viewer_url`
    - `point_cloud_url`
    - `result_url`
    - 合并后的 `metrics`
  - 这样即使页面刷新，或者任务线程早已结束，只要运行目录还在，前端依然能重新发现结果
- 更新 [web/src/core/app.js](/home/fansonglin/xieliang/Web_Scan/web/src/core/app.js)
  - 新增 `mountJobResult(job)`
  - 当前端轮询到 job 含有 `manifest_url` 或 `point_cloud_url` 时，会自动把主 viewer 切换到该任务输出
  - 增加 `lastJobSceneToken`，避免重复重载同一结果
- 更新 [web/README.md](/home/fansonglin/xieliang/Web_Scan/web/README.md)
  - 增加“若任务输出了 manifest 或 .ply，主 viewer 会自动切换到最新算法结果”的说明

当前意义：

- 现在不仅右侧 `Realtime Workspace` 能看到算法结果，主场景 viewer 也会同步切换到最新输出
- 这让“任务调度 / 结果查看 / 结构交互”进入同一个主工作流，而不再分裂成两个区域各看各的

## 2026-04-12 Real Model Output Materialization

这一步开始把 `process_frame` 从“纯桥接假结果”往“真实模型输出回传”推进。

关键判断：

- 以 `MEGS-2-main` 为代表的当前目录高斯仓库，本质上都是
  - 多视图图像
  - 相机参数
  - COLMAP/Blender 场景
  -> 训练/渲染
- 它们并不支持“单张摄像头帧直接高斯重建”
- 因此不能把“上传一张相机帧”直接等价为“真实高斯编码重建完成”

在这个前提下，本轮做了两件事：

1. 新增 [web/tools/materialize_model_output.py](/home/fansonglin/xieliang/Web_Scan/web/tools/materialize_model_output.py)
   - 当用户提供 `checkpoint_path` 指向已训练模型目录时：
     - 自动查找真实 `point_cloud/iteration_*/point_cloud.ply`
     - 自动查找最近的 `train/test/ours_*/renders/*.png`
     - 输出到 Web 运行目录：
       - `point_cloud.ply`
       - `scene_manifest.json`
       - `latest.png`（若存在）
       - `metrics.json`
   - 当没有可用模型目录时：
     - 自动退回到带 `point_cloud.ply + scene_manifest.json` 的 fallback 结构场景
     - 不再只回显一张 2D 图片

2. 更新 [web/config/algorithm_adapters.json](/home/fansonglin/xieliang/Web_Scan/web/config/algorithm_adapters.json)
   - 将 `megs2`
   - `scaffold-gs`
   - `reduced-3dgs`
   - `hac-plus-plus`
   - `contextgs`
   - `fcgs`
   - `compgs`
   的 `process_frame` 改为优先走 `materialize_model_output.py`

验证结果：

- fallback 路径已经验证能在 `web/generated/streams/...` 下生成：
  - `point_cloud.ply`
  - `scene_manifest.json`
  - `metrics.json`
  - `latest.png`
- 服务端 `read_runtime_artifacts()` 能正确识别并返回：
  - `manifest_url`
  - `viewer_url`
  - `point_cloud_url`
  - `result_url`

这一步后的真实能力边界：

- 可以实现：
  - Web 端拍摄/上传
  - 传到服务器
  - 服务器基于已训练高斯模型回传真实结构结果
  - Web 端主 viewer + 右侧结果区同步展示
- 还不能实现：
  - 单张摄像头帧直接触发新的高斯重建训练并实时返回真实新模型

## 2026-04-12 Capture Session Materialization

继续按“让 Web 采集结果真正进入现有多视图仓库工作流”推进。

本轮改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - 新增 `DATASET_DIR`
  - 新增 `materialize_stream_session(session_id)`
  - 新增接口 `POST /api/materialize-session`
  - 该接口会将 `web/generated/streams/<session_id>/input/` 下的采集帧整理为：
    - `web/generated/datasets/<session_id>/images/`
    - `web/generated/datasets/<session_id>/input/`
    - `web/generated/datasets/<session_id>/capture_session.json`
- 更新 [web/src/api/server-client.js](/home/fansonglin/xieliang/Web_Scan/web/src/api/server-client.js)
  - 新增 `materializeSession()`
- 更新 [web/index.html](/home/fansonglin/xieliang/Web_Scan/web/index.html)
  - 在 `Realtime Input` 面板增加：
    - `整理采集会话`
    - `填入训练路径`
- 更新 [web/src/core/app.js](/home/fansonglin/xieliang/Web_Scan/web/src/core/app.js)
  - 新增 `handleMaterializeSession()`
  - 新增 `applyMaterializedSession()`
  - 物化采集会话后，自动将：
    - `workspace`
    - `server-input-path`
    - `server-output-dir`
    回填到前端表单

实测结果：

- `materialize_stream_session('test-session')` 已确认可返回：
  - `dataset_root`
  - `images_dir`
  - `input_dir`
  - `manifest_path`
  - `manifest_url`
  - `frame_count`

这一步的意义：

- 虽然当前仓库仍不能做到“单帧直接高斯重建”，但 Web 端采集到的多帧数据已经可以被整理成后续训练工作区
- 这让系统从“实时演示平台”更进一步变成“采集 -> 数据落地 -> 仓库训练/渲染 -> Web 查看”的完整工程链路

## 2026-04-12 COLMAP Workspace Preparation

继续按“把采集数据真正送到现有仓库前处理入口”推进。

本轮改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - 新增 `WORKSPACE_DIR`
  - 新增 `prepare_colmap_workspace(session_id, family, repo_path)`
  - 新增接口 `POST /api/prepare-colmap-workspace`
  - 该接口会基于采集会话生成：
    - `web/generated/workspaces/<session_id>/<family>/input/`
    - `images/`
    - `sparse/0/`
    - `distorted/sparse/`
    - `workspace_manifest.json`
    - `run_colmap_prepare.sh`
  - 若目标仓库存在 `convert.py`，则自动生成对应建议命令
- 更新 [web/src/api/server-client.js](/home/fansonglin/xieliang/Web_Scan/web/src/api/server-client.js)
  - 新增 `prepareColmapWorkspace()`
- 更新 [web/index.html](/home/fansonglin/xieliang/Web_Scan/web/index.html)
  - 新增两个按钮：
    - `准备COLMAP工作区`
    - `填入COLMAP路径`
- 更新 [web/src/core/app.js](/home/fansonglin/xieliang/Web_Scan/web/src/core/app.js)
  - 新增 `handlePrepareColmapWorkspace()`
  - 新增 `applyColmapWorkspace()`
  - 可自动把：
    - `server-input-path`
    - `server-output-dir`
    - `workspace`
    - `colmap_command`
    回填到任务表单

验证结果：

- `prepare_colmap_workspace('test-session', 'megs2', '/home/fansonglin/xieliang/Web_Scan/MEGS-2-main')` 已确认生成：
  - `workspace_root`
  - `input_dir`
  - `images_dir`
  - `sparse_dir`
  - `workspace_manifest.json`
  - `run_colmap_prepare.sh`
  - 建议命令：
    - `python /home/fansonglin/xieliang/Web_Scan/MEGS-2-main/convert.py -s ...`

当前完整性判断进一步更新：

- 已经可以做到：
  - Web 拍摄/上传
  - 服务器保存
  - 会话整理
  - COLMAP 工作区准备
  - 训练路径自动回填
  - 已训练模型结果回传与展示
- 仍然不能做到：
  - Web 端一键自动跑完整个 COLMAP + 训练 + 重建 + 返回模型
  - 原因是当前还没有把 COLMAP 和各仓库训练命令编排成一条端到端自动 pipeline

## 2026-04-12 Capture Pipeline Orchestration

这一步把“编排”补上了，不再只是准备路径。

本轮改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - 新增 `format_operation_command()`
  - 新增 `build_capture_pipeline()`
  - 新增接口 `POST /api/run-capture-pipeline`
  - 该接口会：
    - 基于采集会话准备 COLMAP 工作区
    - 读取 adapter 的 `train/render` 模板
    - 自动生成 `run_capture_pipeline.sh`
    - 可直接创建后台 job 执行 `bash run_capture_pipeline.sh`
- 更新 [web/src/api/server-client.js](/home/fansonglin/xieliang/Web_Scan/web/src/api/server-client.js)
  - 新增 `runCapturePipeline()`
- 更新 [web/src/core/app.js](/home/fansonglin/xieliang/Web_Scan/web/src/core/app.js)
  - 新增 `handleRunCapturePipeline()`
  - 自动回填：
    - `workspace`
    - `capture_pipeline_script`
    - `colmap_command`
  - 若 job 成功创建，则直接进入 job polling
- 更新 [web/index.html](/home/fansonglin/xieliang/Web_Scan/web/index.html)
  - 新增按钮：`运行采集流程`

实测结果：

- 已确认 `build_capture_pipeline('test-session', 'megs2', ...)` 会生成：
  - `run_capture_pipeline.sh`
  - 命令链：
    - `python .../MEGS-2-main/convert.py -s ...`
    - `python train.py -s ... -m ...`
    - `python render.py -m ...`

当前完整性结论：

- 这套网页作为“Web 服务 + 控制台 + viewer”已经是可直接运行的
- 采集、会话整理、COLMAP 工作区准备、pipeline 脚本生成、任务提交、结果查看，链路现在已经完整
- 但“完整 pipeline 一键执行成功”是否成立，取决于运行环境：
  - 是否安装 `COLMAP`
  - 是否安装 CUDA / PyTorch / 各仓库依赖
  - 是否具备可训练的 GPU 环境
  - 目标仓库的参数模板是否与本地环境完全匹配
- 因此：网页本身可直接运行；重建 pipeline 是 orchestration-complete，但不是 environment-guaranteed

## 2026-04-12 Environment Check Panel

继续把“代码是否完整”和“环境是否能跑”从描述层变成可见状态。

本轮改动：

- 更新 [web/server/api_server.py](/home/fansonglin/xieliang/Web_Scan/web/server/api_server.py)
  - 新增 `environment_check()`
  - 新增接口 `POST /api/environment-check`
  - 检查内容包括：
    - `python3`
    - `colmap`
    - `nvidia-smi`
    - `magick`
    - 当前选中仓库中的 `convert.py/train.py/render.py/...`
  - 返回两个关键状态：
    - `web_runnable`
    - `pipeline_ready`
- 更新 [web/src/api/server-client.js](/home/fansonglin/xieliang/Web_Scan/web/src/api/server-client.js)
  - 新增 `fetchEnvironmentCheck()`
- 更新 [web/src/ui/control-panel.js](/home/fansonglin/xieliang/Web_Scan/web/src/ui/control-panel.js)
  - 新增 `renderEnvironmentCheck()`
- 更新 [web/src/core/app.js](/home/fansonglin/xieliang/Web_Scan/web/src/core/app.js)
  - 在 API health check 后自动拉取环境报告
  - 算法切换时自动刷新环境报告
- 更新 [web/index.html](/home/fansonglin/xieliang/Web_Scan/web/index.html)
  - 新增 `Environment Check` 面板

实际检查结果：

- 当前机器上：
  - `python3`: 可用
  - `nvidia-smi`: 可用
  - `MEGS-2-main/convert.py/train.py/render.py`: 存在
  - `colmap`: 不可用
  - `magick`: 不可用
- 因此：
  - `web_runnable = true`
  - `megs2.pipeline_ready = false`

最终判断进一步明确：

- 现有网页是完整的、可直接运行的 Web 页面
- 但完整高斯重建 pipeline 目前不是“可直接执行”的状态
- 当前阻塞点是运行环境，而不是网页代码结构
  
### Web 调试修复与测试资产补充 (续)  
- **Float32Array WebGL 字节对齐故障**... 分析发现是因为ASCII的Ply且缺少f_rest_*属性而被误作为二进制块丢弃，引发控制台不报错但是黑屏的情况。  
- 现已重写并提供标准的 alid_point_cloud.ply 二进制点云提供 _dc 与 _rest 供测试。  
- 改正了 isPly() 对于 Windows 下 \r\n 的识别匹配。 
- 修正新打包的 \scene_manifest.json\ 指向测试资源的相对层级，解决 404 Not Found。 
- 批量修正了后台模型配置文件 \web/config/algorithm_adapters.json\ 中残留的数十处指向 \/home/fansonglin/xieliang/...\ 的 Linux 绝对路径为跨平台相对路径 (\../HAC-plus\、\../web/tools\) 
