# Web Scan 调试与修复记录（中文）

## 2026-04-20 远程训练自动化升级（批次隔离 + 历史复用）

- 后端远程能力（`web/server/remote_executor.py`）
   - SSH 预检新增远端历史数据集扫描与 `colmap` 可用性检查。
   - 远程训练支持两条路径：
      - 新上传数据自动 COLMAP 后训练；
      - 直接复用远端既有数据集（跳过上传与 COLMAP）。
   - 增加命名数据集保存能力，便于后续在 Step4 直接复用。

- API 与前端联动（`web/server/api_server.py` + `web/src/core/app.js` + `web/index.html`）
   - 新增字段：`capture_id`、`dataset_name`、`auto_colmap`、`use_existing_remote_dataset`、`remote_dataset_id/path`。
   - Step3 支持 Capture Batch ID；Step4 可查看并选择远端历史数据集；Step5 可配置 Dataset Name 与 Auto COLMAP。
   - workflow 门禁更新：启用“复用历史数据”时可跳过新帧上传，直接提交远程训练。

- 本地数据组织升级
   - 采集改为批次目录（`streams/<session>/captures/<capture_id>/input`）。
   - 物化数据集改为命名实例目录（`datasets/<session>/datasets/<dataset_id>`）。

## 2026-04-18 路径确认强制校验（UI + 后端）

- 前端 `web/src/core/app.js`：
   - 在本地提交与远程一键训练前，强制弹窗确认 `checkpoint_path` 和 `output_dir`。
   - 若 `output_dir` 为空则直接阻断提交。
   - 提交请求新增 `path_confirmation` 字段。

- 后端 `web/server/api_server.py`：
   - 新增 `validate_path_confirmation_payload()`。
   - `POST /api/run-algorithm` 与 `POST /api/run-remote-algorithm` 强制校验 `path_confirmation`。
   - 不满足时返回 `WGSC-STEP5-CONFIRM-001`，并给出差异详情。

- 稳健性增强：
   - 在命令格式化后自动清理空占位符对应参数，避免出现 `--model-dir` 无值导致的 argparse 错误。

## 1. 近期核心问题：提交任务后出现 `WinError 123`

### 现象

- 点击前端的提交/捕获流程后，后端作业（`process_frame`、`train`）多次失败。
- 报错为 `[WinError 123] 文件名、目录名或卷标语法不正确`。
- 前端显示 `return_code = -`，说明失败发生在 `subprocess.Popen` 启动阶段，子进程甚至未真正执行。

### 根因分析

1. Windows 上命令拆分与引号处理不稳定。
   - 某些模板变量为空时，会出现裸的空引号参数（例如 `""`），在 `CreateProcessW` 里可能触发路径/参数语法错误。
2. `python` 可执行文件依赖 PATH 解析。
   - 当 PATH 或 Python 别名状态异常时，`Popen` 可能直接失败。

### 已落地修复

1. 固定解释器路径。
   - 将命令首 token 为 `python` 时替换为 `sys.executable`，确保使用启动服务的同一个 Python。
2. 参数清洗。
   - 对空引号参数和悬空参数进行清理，避免无效 token 进入 `Popen`。

---

## 2. 新问题：`python main.py` 找不到文件 + Windows 无 `bash`

### 现象

- `train` 报错：`can't open file ...\main.py`。
- `capture_pipeline` 报错：`[WinError 2] 系统找不到指定的文件`。

### 根因分析

1. `gaussian-splatting-lightning` 在当时缺少有效 `repo_path/default_cwd`，导致 `python main.py` 在错误目录执行。
2. 捕获流水线使用了 `bash run_capture_pipeline.sh`，但 Windows 主机不一定具备 bash。
3. 相对路径（如 `../...`）在不同工作目录下容易失配。

### 已落地修复

1. 增加 `resolve_workspace_path()`。
   - 统一解析绝对/相对路径；优先按 `web/` 相对路径解析，再回退项目根目录。
2. Windows 流水线脚本双产出。
   - 保留 `.sh`，新增 `.cmd`。
3. 按平台选择启动命令。
   - Windows：`cmd /c ...run_capture_pipeline.cmd`
   - 非 Windows：`bash ...run_capture_pipeline.sh`
4. 对 `python main.py` 类命令增加前置校验。
   - 若缺少 `repo_path/default_cwd`，直接返回清晰 HTTP 400，而不是后台崩溃。

---

## 3. 新问题：`process_frame` 因空 `--repo-path` 参数报 argparse 用法错误

### 现象

- `process_frame` 多次返回 `return_code = 2`。
- stderr 显示 argparse usage，并提示 `--repo-path` 需要值。

### 根因分析

- 模板里固定包含 `--repo-path {repo_path}`，当 `repo_path` 为空时形成悬空参数。

### 已落地修复

1. 新增 `strip_empty_repo_path_flag(command, repo_path)`。
   - 当 repo_path 为空时，从命令字符串中移除 `--repo-path`。
2. 运行时二次防御。
   - 在 `start_job_thread` 中，若发现悬空 `--repo-path`，在执行前再次剔除。

### 验证结果

- `POST /api/stream-frame` 在空 repo_path 下可成功完成。
- 作业状态为 `completed`，`return_code = 0`，并正常生成 metrics / viewer_url。

---

## 4. 新问题：历史失败任务卡片过多，干扰当前判断

### 现象

- 前端 job 列表保留大量旧失败记录，尤其是高频 `process_frame`。

### 已落地修复

1. 增加作业历史修剪。
   - 设置全局历史上限。
   - 单独限制 `process_frame + completed` 的保留数量。
2. 新增接口：`POST /api/jobs/clear`
   - 支持清空全部任务，或按 operation 定向清空。

### 验证结果

- 清理接口返回 `ok: true`，并可将列表清到 0 条。

---

## 5. 新问题：`gaussian-splatting-lightning` 缺少 `repo_path/default_cwd`

### 现象

- `/api/run-algorithm` 对 `train` 返回：需要 `repo_path/default_cwd`。

### 根因分析

- 即使基础配置已改，`algorithm_adapters.override.json` 的覆盖值仍可能优先生效。

### 已落地修复

1. 本地克隆仓库：
   - `C:\Users\chen\Documents\3DGS\Web_Scan\gaussian-splatting-lightning-main`
2. 覆盖适配器配置：
   - `repo_path` 与 `default_cwd` 均指向该本地仓库。

### 验证结果

- 适配器校验显示 `repo_exists=true`、`cwd_exists=true`、`is_ready=true`。

---

## 6. 当前训练阻塞：CUDA 扩展依赖未就绪（`diff_gaussian_rasterization`）

### 现象

- `train` 作业已可启动并跨过 `lightning` / `jsonargparse` / `wandb` / `viser` / `plyfile` 阶段，
   但仍报错：
   - `ModuleNotFoundError: No module named 'diff_gaussian_rasterization'`

### 根因分析

- `diff_gaussian_rasterization` 与 `simple_knn` 属于 CUDA 扩展模块。
- 本机当前缺少 CUDA Toolkit（未检测到 `CUDA_HOME` / `nvcc`），无法本地编译扩展。

---

## 7. 本次新增实现（2026-04-13）

### 7.1 后端新增依赖前置检查（避免无效排队）

已在 `web/server/api_server.py` 增加：

1. 依赖规格读取：`adapter_requirement_spec()`
2. 模块缺失检测：`find_missing_python_modules()`
3. 模板必填参数检测：`missing_template_fields()`
4. CUDA 工具链检测：`detect_cuda_toolkit()`
5. 模块缺失解析与提示：
   - `extract_missing_module_from_stderr()`
   - `build_dependency_hint()`

在 `/api/run-algorithm` 中新增行为：

- 若模板要求的关键字段为空（例如 `train` 的 `{workspace}`），直接返回 400 并说明缺失字段。
- 若适配器声明了必需 Python 模块且当前环境缺失，直接返回 400，附带：
  - `missing_modules`
  - `python_executable`
  - `install_commands`
   - `cuda_toolkit`
   - `hint`（当缺 CUDA 扩展时返回明确提示）

### 7.2 任务失败时附加安装建议

- 当任务 stderr 含 `ModuleNotFoundError: No module named 'xxx'`：
  - 自动在 stderr 末尾追加 `[DependencyHint]`。
  - 给出当前 Python 路径和建议安装命令（CUDA 12.1 / CPU）。

### 7.3 环境检查接口增强

- `/api/environment-check` 现在返回：
  - `python_executable`
  - `python_modules`
  - `missing_python_modules`
  - `install_commands`
   - `cuda_toolkit`（含 `cuda_home`、`nvcc_path`、`toolkit_ready`）

### 7.4 适配器配置增强

已在 `web/config/algorithm_adapters.json` 的 `gaussian-splatting-lightning` 中新增：

1. `requirements.python_modules`: `torch`, `lightning`, `jsonargparse`, `wandb`, `viser`, `plyfile`, `diff_gaussian_rasterization`, `simple_knn`
2. `requirements.install_commands`:
   - `cuda121`
   - `cpu`

并保留训练模板：

- `python main.py fit --data.parser {workspace}`

该模板现在会受到后端“必填参数检查”保护，避免再次出现 `--data.parser` 后无值的无效任务。

---

## 8. 运行与验证建议

### 8.1 建议安装命令（CUDA 12.1）

```powershell
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install --upgrade pip
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install lightning
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install jsonargparse
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install wandb plyfile==0.8.1 viser==0.2.3
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install --no-build-isolation git+https://github.com/graphdeco-inria/diff-gaussian-rasterization.git@59f5f77e3ddbac3ed9db93ec2cfe99ed6c5d121d
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -m pip install --no-build-isolation git+https://github.com/yzslab/simple-knn.git@44f764299fa305faf6ec5ebd99939e0508331503
```

> 说明：后两条为 CUDA 扩展安装命令，需要本机已安装 CUDA Toolkit 并正确设置 `CUDA_HOME`（且 `nvcc` 可用）。

### 8.2 依赖检查

```powershell
C:\Users\chen\.conda\envs\GS_3DGS\python.exe -c "import torch, lightning, jsonargparse, wandb, viser, plyfile; print(torch.__version__, lightning.__version__)"
```

### 8.3 训练调用注意事项

- `train` 需要有效 `workspace`（即 `--data.parser` 的值不能空）。
- 若空值提交，后端现在会直接返回缺失字段，而不会创建失败任务。

---

## 9. 当前状态总结

1. Windows 路径/脚本/启动器相关问题已完成修复。
2. `process_frame` 已可稳定完成。
3. 历史任务噪声已可通过自动修剪与手动清理控制。
4. `gaussian-splatting-lightning` 的训练主要剩余工作是：
   - 补齐 CUDA Toolkit（`CUDA_HOME`、`nvcc`）；
   - 编译安装 `diff_gaussian_rasterization` 与 `simple_knn`；
   - 提交训练时提供有效 `workspace`。

---

## 10. 新增 Web 训练操作手册（2026-04-13）

为方便新同学快速上手，已新增独立文档：

- `web/WEB_TRAINING_MANUAL_ZH.md`

手册覆盖内容：

1. 零基础逐步操作流程（页面按钮级）
2. 训练前置检查与依赖安装路径
3. 常见报错与对应修复动作
4. 底层接口与目录流转原理附录

同时在 `web/README.md` 中增加了手册入口，减少首次使用成本。
