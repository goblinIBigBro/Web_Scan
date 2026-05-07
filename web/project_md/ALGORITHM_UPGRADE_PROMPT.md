# 3DGS 算法升级复用 Prompt

本文档用于复用 ContextGS、reduced-3dgs、MEGS-2 的升级经验。目标是把一个旧版 3D Gaussian Splatting 算法从 Python 3.7/3.8、PyTorch 1.x、CUDA 11.x 升级到 Python 3.10、PyTorch 2.2.2、CUDA 12.1，并适配 RTX 4090。

使用方式：复制下面的 Prompt，把占位符替换为目标算法信息后交给 Codex 或其他工程代理执行。

```text
请把仓库中的 <ALGORITHM_NAME> 进行与 ContextGS / reduced-3dgs / MEGS-2 相同的升级。

目标目录：
- 算法目录：<ALGORITHM_DIR>
- Web 配置：web/config/algorithm_adapters.json
- Web API：web/server/api_server.py
- 远程检查脚本：web/tools/remote_verify_setup.sh
- 文档目录：web/project_md/

目标环境：
- Python 3.10
- PyTorch 2.2.2
- torchvision 0.17.2
- torchaudio 2.2.2
- pytorch-cuda=12.1
- RTX 4090 / 4090D，CUDA capability 8.9
- 保留现有 conda 环境名：<ENV_NAME>

请先检查，不要直接覆盖：
- 读取 <ALGORITHM_DIR>/environment.yml、requirements.txt、setup_env.sh 是否存在。
- 找出入口脚本，例如 train.py、render.py、metrics.py、compress.py、decompress.py、test.py。
- 找出 CUDA 扩展目录，例如 submodules/diff-gaussian-rasterization、submodules/simple-knn，以及算法自己的扩展。
- 用 Python 3.10 AST parse 检查所有 <ALGORITHM_DIR>/**/*.py。
- 搜索 PyTorch 2.x / Python 3.10 风险点：
  - torch.cuda.amp.custom_fwd/custom_bwd
  - pandas DataFrame.append
  - import 失败的可选依赖
  - 入口脚本在 argparse 前调用 torch.cuda.set_device 或 .cuda()
  - CUDA 扩展 setup.py 中 BuildExtension、nvcc flags、compiler check

需要实施的改动：

1. 更新 environment.yml
- 保留 name: <ENV_NAME>。
- channels 使用 pytorch、nvidia、conda-forge、defaults。
- dependencies 至少包含：
  - python=3.10
  - pip
  - pytorch=2.2.2
  - torchvision=0.17.2
  - torchaudio=2.2.2
  - pytorch-cuda=12.1
  - numpy=1.26.*
  - pillow=10.*
  - plyfile=1.1.*
  - tqdm
- 按算法实际需要保留/加入 scipy、pandas=2.2.*、einops、lpips、wandb、opencv-python、compressai、torchac、torch_scatter 等。
- pip 本地安装项只保留实际存在或需要恢复的 submodules。

2. 新增或更新 setup_env.sh
- 使用 bash，set -euo pipefail。
- 优先使用 mamba，缺失时回退 conda。
- 创建或复用 <ENV_NAME>。
- 分批安装依赖，避免完整 environment.yml solver 卡住。
- 设置：
  - CUDA_HOME=${CUDA_HOME:-/usr/local/cuda-12.1}
  - TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST:-8.9}
  - FORCE_CUDA=1
  - MAX_JOBS=${MAX_JOBS:-4}
  - OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
  - PATH=$CUDA_HOME/bin:$PATH
  - LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}
- 检查每个 CUDA 扩展源码目录是否存在，缺失时给出明确错误。
- 使用 python -m pip install --no-build-isolation -v <submodule_dir> 编译本地 CUDA 扩展。
- 末尾打印 torch version、torch.version.cuda、cuda available、GPU 名称和 capability。

3. 修复 CUDA 扩展 setup.py
- 对每个本地 CUDA 扩展检查 setup.py。
- 若使用 torch.utils.cpp_extension，补充 PyTorch 2.x 兼容处理：
  import torch.utils.cpp_extension as torch_cpp_ext
  torch_cpp_ext.get_compiler_abi_compatibility_and_version = lambda compiler: (True, torch_cpp_ext.TorchVersion('0.0.0'))
  torch_cpp_ext._check_cuda_version = lambda compiler_name, compiler_version: None
- nvcc extra_compile_args 加入：
  - -allow-unsupported-compiler
  - -D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH
- 若原本有 GLM include，例如 third_party/glm，需要保留。
- BuildExtension 建议使用 BuildExtension.with_options(use_ninja=False)，降低远程容器编译问题。

4. 新增运行时 CUDA 检查
- 新建 <ALGORITHM_DIR>/utils/runtime_utils.py，提供 assert_cuda_runtime。
- 检查：
  - Python 3.10
  - PyTorch 2.2.x
  - torch.version.cuda startswith "12.1"
  - torch.cuda.is_available()
  - device 0 可见
  - 如果环境变量 <ALGORITHM_ENV_PREFIX>_REQUIRE_RTX4090=true/1，则要求 GPU 名称包含 4090
  - 如果 GPU 名称包含 4090，则 capability 必须为 (8, 9)
- 错误信息要明确指出当前 Python、torch、CUDA、GPU 状态。

5. 在入口脚本接入运行时检查
- 在 train.py、render.py、metrics.py、compress.py、decompress.py、test.py 等实际需要 CUDA 的入口中导入 assert_cuda_runtime。
- 必须允许 -h/--help 不要求 CUDA。
- 因此 assert_cuda_runtime 应放在 argparse parse_args 或 get_combined_args 之后、真正调用 CUDA 逻辑之前。
- 若脚本当前在 parse_args 前 torch.cuda.set_device，需要后移。

6. 修复 Python 3.10 / 新依赖兼容
- pandas 2.x：DataFrame.append(...) 改为 pd.concat(...) 或 DataFrame([row])。
- PyTorch AMP：torch.cuda.amp.custom_fwd/custom_bwd 改为兼容 fallback，优先使用 torch.amp.custom_fwd/custom_bwd，必要时退回旧路径。
- 可选依赖 import：只对实际使用的 API 做 fallback，避免因为未使用符号变动导致整体崩溃。
- 不要改动无关算法逻辑。

7. 更新 Web 适配器
- 在 web/config/algorithm_adapters.json 对 <FAMILY_KEY> 添加 requirements：
  - python_modules 包含 torch、torchvision、所有 CUDA 扩展 import 名、plyfile、PIL、tqdm，以及算法实际依赖。
  - install_commands.cuda121 给出 conda create、conda activate、conda install pytorch-cuda=12.1、基础依赖安装、本地 CUDA 扩展 pip 编译命令。
- 检查 operations 模板是否缺少算法必需参数。例如 MEGS-2 的 train.py 必须传 --imp_metric。

8. 更新 Web 环境检查
- 在 web/server/api_server.py 的 ALGORITHM_CUDA_CHECK_SPECS 中加入 <FAMILY_KEY>：
  - label
  - root
  - env_name
  - required_modules
- 复用已有通用 CUDA 检查逻辑，要求 Python 3.10、Torch 2.2、CUDA 12.1、RTX 4090、capability 8.9、nvcc、必需模块。

9. 更新远程验证脚本
- 在 web/tools/remote_verify_setup.sh 增加 <FAMILY_KEY> 模式。
- detect_version 中根据 Python 3.10 和算法特有模块 import 自动识别。
- 新增 check_<FAMILY_KEY>_version：
  - Linux
  - disk
  - nvidia-smi
  - nvcc
  - Python 3.10
  - PyTorch 2.2
  - torch.version.cuda 12.1
  - CUDA available
  - RTX 4090
  - capability (8, 9)
  - required Python modules
  - CUDA extension imports
  - conda env 存在
- 若算法原来在 old 组，把它从 old 检查和说明中移除。

10. 更新文档
- web/README.md：把算法移动到 New Algorithms。
- REMOTE_SETUP_INDEX.md：
  - 快速选择中加入该算法。
  - 算法速查表改为 NEW / Python 3.10 / Torch 2.2 / CUDA 12.1。
  - 环境验证加入 bash remote_verify_setup.sh <FAMILY_KEY>。
  - 快速命令加入该算法训练示例。
- REMOTE_SETUP_GUIDE_NEW.md：
  - 适用项目加入该算法。
  - environment.yml 创建步骤加入该算法。
  - 子模块说明加入该算法实际 CUDA 扩展。
  - 验证脚本加入 remote_verify_setup.sh <FAMILY_KEY>。
  - checklist 加入 <ENV_NAME>。
- REMOTE_SETUP_GUIDE_OLD.md：
  - 从旧版适用项目移除该算法。
  - 添加“已迁移到新版环境”的说明和跳转命令。

验证计划：

本地静态验证：
- python3 -m json.tool web/config/algorithm_adapters.json >/dev/null
- bash -n <ALGORITHM_DIR>/setup_env.sh
- bash -n web/tools/remote_verify_setup.sh
- 用 Python 3.10 AST parse <ALGORITHM_DIR>/**/*.py
- PYTHONPYCACHEPREFIX=/private/tmp/web_scan_pycache python3 -m py_compile 触及的 Web Python 文件和入口脚本
- 调用 environment_check("<FAMILY_KEY>")，本地无 GPU 时应返回结构化 checks，pipeline_ready=false
- 验证 adapter 仍暴露 train/render/compress/process_frame/export_scene 等已有操作

远程 RTX 4090 验证：
- conda env create --file environment.yml 或 bash setup_env.sh
- conda activate <ENV_NAME>
- python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
- 导入所有必需模块和 CUDA 扩展。
- python train.py -h、python render.py -h、python metrics.py -h 等帮助命令不应要求 CUDA 运行任务。
- 运行一次短训练 smoke test。
- 运行 render / metrics / compress / decompress 等算法实际链路。
- bash ../web/tools/remote_verify_setup.sh <FAMILY_KEY> 全部关键项 PASS。
- Web /api/environment-check?family=<FAMILY_KEY> 返回 pipeline_ready=true。

约束：
- 不要回滚用户已有改动。
- 不要改无关算法。
- 如果算法目录被 .gitignore 忽略，也要实际修改本地文件，并在最终说明中提醒这些文件不会出现在普通 git status。
- 本机没有 RTX 4090/CUDA 时，不要假装已完成 GPU 编译验证；只做静态和结构化检查，并明确说明远程验证项。

最终输出：
- 简述改了哪些文件和目的。
- 列出已运行的验证命令。
- 列出未能本地验证、需要远程 4090 验证的项目。
- 给出远程 Activate Command，例如：
  source ~/.bashrc && conda activate <ENV_NAME> && unset OMP_NUM_THREADS && export OMP_NUM_THREADS=1 && export CUDA_HOME=/usr/local/cuda-12.1 && export PATH=$CUDA_HOME/bin:$PATH && export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}
```

## 占位符说明

| 占位符 | 示例 | 说明 |
|---|---|---|
| `<ALGORITHM_NAME>` | MEGS-2 | 显示名称 |
| `<ALGORITHM_DIR>` | MEGS-2-main | 算法目录 |
| `<ENV_NAME>` | MEGS2 | conda 环境名，优先保留原项目已有名字 |
| `<FAMILY_KEY>` | megs2 | Web adapter 的 family key |
| `<ALGORITHM_ENV_PREFIX>` | MEGS2 | 运行时环境变量前缀，例如 `MEGS2_REQUIRE_RTX4090` |

## 升级经验要点

- 不要盲目运行完整 legacy environment.yml，老版本 PyTorch/CUDA 组合容易让 mamba/conda solver 卡住。
- 4090/4090D 不建议继续强行使用 PyTorch 1.12 + CUDA 11.6，现代栈应使用 CUDA 12.1 并编译 `sm_89`。
- 本地 CUDA 扩展是最大风险点，必须明确检查源码是否存在，并在目标环境中重新编译。
- `-h/--help` 必须可用，运行时 CUDA 检查不能放在 argparse 之前。
- Web 适配器模板要检查算法自己的必需参数，否则环境升级完成后 Web 训练仍会失败。
- 本地无 GPU 时，正确结果不是 PASS，而是环境检查能结构化返回失败原因。
