# 远程 SSH 环境配置指南 — 新版算法组

> **适用项目**：HAC-plus、FCGS、ContextGS  
> **环境**：Python 3.10 + PyTorch 2.2.* + CUDA 11.8/12.1  
> **更新日期**：2026 年 4 月  
> **作者**：Web_Scan 文档

---

## 📌 快速检测清单

在配置前，请确认你的远程主机满足以下条件：

```bash
# 1️⃣ 系统检查
uname -a                          # 应为 Linux (Ubuntu 20.04/22.04 推荐)
df -h | grep -E "/$|/tmp"         # 磁盘剩余 ≥ 200GB
nvidia-smi                        # GPU 驱动正常，显示可用 GPU

# 2️⃣ Python 和 PyTorch 快速验证（复制整行运行）
python3 --version && python3 -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.version.cuda}, Available: {torch.cuda.is_available()}')"

# 3️⃣ 关键依赖检查
python3 -c "import plyfile, lpips, einops, numpy, tqdm; print('✓ All deps found')"

# 如果上面出现错误，请继续阅读下面的"分步部署"
```

---

## 🏗️ 分步部署指南

### 第一步：准备 Conda 环境

#### 方案 A：使用官方 environment.yml（推荐）

```bash
# HAC-plus
cd ~/Web_Scan/HAC-plus-main
conda env create --file environment.yml
conda activate HAC_env

# 或者 FCGS
cd ~/Web_Scan/FCGS-main
conda env create --file environment.yml
conda activate FCGS_env

# 或者 ContextGS（RTX 4090 推荐 CUDA 12.1）
cd ~/Web_Scan/ContextGS-main
conda env create --file environment.yml
conda activate contextgs
```

**预计时间**：10-15 分钟（首次下载）

---

#### 方案 B：手动创建环境（如已有 Python 3.10）

```bash
# 创建环境
conda create -n HAC_env python=3.10 -y

# 激活环境
conda activate HAC_env

# 添加必要的频道
conda config --env --add channels pytorch
conda config --env --add channels nvidia

# 安装 PyTorch 和 CUDA
# 对于 CUDA 12.1（推荐 HAC-plus）
conda install -y pytorch=2.2 torchvision=0.17 torchaudio=2.2 pytorch-cuda=12.1 -c pytorch -c nvidia

# 对于 CUDA 11.8（推荐 FCGS）
conda install -y pytorch=2.2 torchvision=0.17 pytorch-cuda=11.8 -c pytorch -c nvidia

# 安装其他依赖
conda install -y numpy scipy tqdm plyfile pip
pip install einops wandb lpips colorama opencv-python imageio matplotlib

# ContextGS 额外依赖
pip install compressai==1.2.8 torchac==0.8.15
pip install torch-scatter -f https://data.pyg.org/whl/torch-2.2.0+cu121.html
```

---

### 第二步：准备项目代码

```bash
# 进入项目目录
cd ~/Web_Scan/HAC-plus-main  # 或 FCGS-main / ContextGS-main

# 初始化子模块（非常重要）
git submodule update --init --recursive

# 或者（如果子模块是 ZIP 文件）
cd submodules
unzip *.zip 2>/dev/null
for d in */; do
  cd "$d"
  python setup.py install > /dev/null 2>&1
  cd ..
done
cd ..
```

**ContextGS 注意**：当前仓库不提交 `ContextGS-main/submodules`，需要先恢复 `diff-gaussian-rasterization` 和 `simple-knn`，再用 `CUDA_HOME=/usr/local/cuda-12.1 TORCH_CUDA_ARCH_LIST=8.9` 编译。

**常见问题**：如果子模块中的 `simple-knn` 或 `diff-gaussian-rasterization` 编译失败，参考 [故障排除](#️-故障排除) 章节。

---

### 第三步：检查环境完整性

运行诊断脚本（如果存在）：

```bash
# HAC-plus
python diagnose.py

# 或 FCGS
python FCGS-main/diagnose.py

# 或 ContextGS
bash ../web/tools/remote_verify_setup.sh contextgs
```

如果没有诊断脚本，手动运行以下检查：

```bash
# 检查 Python 版本
python --version  # 应输出 Python 3.10.x

# 检查 PyTorch
python -c "
import torch
print(f'PyTorch Version: {torch.__version__}')
print(f'CUDA Available: {torch.cuda.is_available()}')
print(f'CUDA Version: {torch.version.cuda}')
print(f'GPU Count: {torch.cuda.device_count()}')
if torch.cuda.is_available():
    print(f'GPU Name: {torch.cuda.get_device_name(0)}')
"

# 检查关键包
python -c "
packages = ['plyfile', 'lpips', 'einops', 'numpy', 'scipy', 'tqdm', 'wandb', 'PIL', 'cv2']
for pkg_name in packages:
    try:
        if pkg_name == 'PIL':
            from PIL import Image
        elif pkg_name == 'cv2':
            import cv2
        else:
            __import__(pkg_name)
        print(f'✓ {pkg_name}')
    except ImportError:
        print(f'✗ {pkg_name} MISSING')
"
```

**验证成功标志**：
- ✅ Python 版本为 3.10.x
- ✅ CUDA Available: True
- ✅ GPU Count ≥ 1
- ✅ 所有包都显示 ✓

---

### 第四步：配置 SSH 激活命令

在本地 Web_Scan 应用中，配置远程服务器时需要填写 **Remote Activate Command**。

#### 标准激活命令

**如果 conda 已在 `~/.bashrc` 中初始化：**
```bash
source ~/.bashrc && conda activate HAC_env
```

**如果 conda 未初始化或使用 miniconda：**
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate HAC_env
```

**如果使用 anaconda：**
```bash
source ~/anaconda3/etc/profile.d/conda.sh && conda activate HAC_env
```

**如果使用绝对路径到 Python（最稳定）：**
```bash
/home/YOUR_USERNAME/miniconda3/envs/HAC_env/bin/python --version
```

#### ⚠️ 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|--------|
| `conda: command not found` | conda 路径未找到 | 检查 `~/.bashrc` 中的 conda 初始化，或使用完整路径 |
| `(HAC_env)` 前缀消失 | 非交互 shell 中 conda 激活失败 | 改用 `source ~/.bashrc && conda activate` 的完整形式 |
| `environment not found` | 环境名称错误 | 运行 `conda env list` 确认环境名称 |

---

## 🚀 训练启动指南

### HAC-plus 训练

#### 参数配置方式

**参数直接通过命令行传入**（不需要修改配置文件）。完整参数列表：

```bash
python train.py -s <SOURCE_PATH> -m <OUTPUT_PATH> [OPTIONS]
```

#### 必需参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `-s` / `--source_path` | str | 数据集路径（包含 images/ 和 sparse/ 目录） | `/workspace/data/chair` |
| `-m` / `--model_path` | str | 模型输出目录 | `/output/chair_result` |

#### 常用可选参数

| 参数 | 默认值 | 说明 | 调整建议 |
|------|--------|------|---------|
| `--iterations` | 30000 | 训练迭代数 | 测试: 1000，完整: 30000 |
| `--eval` | False | 启用评估模式 | 训练时启用 `--eval` |
| `--voxel_size` | 0.001 | 体素大小（3D 精度） | 质量↑ 速度↓: 0.0005; 质量↓ 速度↑: 0.002 |
| `--lmbda` | 0.001 | 压缩强度（LoD 压缩权重） | 压缩多: 0.003; 保质量: 0.0005 |
| `--lod` | 0 | LoD 细节层级 | 0(最高质量) 到 2 |
| `--mask_lr_final` | 0.00008 | 最终掩码学习率 | 通常不调整 |
| `--mask_lr` | 0.001 | 掩码学习率 | 通常不调整 |

#### 快速启动示例

```bash
# 最小化测试（验证环境，1 分钟）
python train.py \
  -s /workspace/data/nerf_synthetic/chair \
  -m /output/test_chair \
  --iterations 100

# 标准训练
python train.py \
  -s /workspace/data/nerf_synthetic/chair \
  -m /output/chair_full \
  --iterations 30_000 \
  --eval \
  --lod 0 \
  --voxel_size 0.001

# 高质量训练（更高压缩，更长时间）
python train.py \
  -s /workspace/data/complex_scene \
  -m /output/complex_hq \
  --iterations 40_000 \
  --eval \
  --voxel_size 0.0005 \
  --lmbda 0.0003 \
  --lod 0
```

---

### FCGS 压缩流程

#### 参数配置方式

**参数直接通过命令行传入**（不需要修改配置文件）。

#### 完整压缩流程（3 步）

##### 步骤 1: 编码压缩

```bash
python encode_single_scene.py \
  --lmd <LAMBDA> \
  --ply_path_from <INPUT_PLY> \
  --bit_path_to <OUTPUT_DIR> \
  --determ 1 \
  [--nr NORM_RADIUS]
```

| 参数 | 类型 | 说明 | 推荐值 |
|------|------|------|--------|
| `--lmd` | float | 压缩强度（权衡文件大小与质量） | `1e-4`(高质量), `4e-4`(平衡), `16e-4`(高压缩) |
| `--ply_path_from` | path | 输入 PLY 文件路径 | 指向原始点云文件 |
| `--bit_path_to` | path | 输出比特流目录（存储压缩后的 .bin 文件） | 确保目录存在或可创建 |
| `--determ` | int | 确定性模式（0/1） | 1 (推荐，结果可重现) |
| `--nr` | float | 归一化半径 | 默认自动计算；通常 0.1～1.0 |

**示例**：
```bash
# 平衡模式（推荐）
python encode_single_scene.py \
  --lmd 4e-4 \
  --ply_path_from /workspace/point_cloud.ply \
  --bit_path_to /output/compressed \
  --determ 1

# 高质量模式
python encode_single_scene.py \
  --lmd 1e-4 \
  --ply_path_from /workspace/point_cloud.ply \
  --bit_path_to /output/compressed_hq \
  --determ 1
```

---

##### 步骤 2: 解码还原

```bash
python decode_single_scene.py \
  --lmd <LAMBDA> \
  --bit_path_from <INPUT_DIR> \
  --ply_path_to <OUTPUT_PLY>
```

**示例**：
```bash
python decode_single_scene.py \
  --lmd 4e-4 \
  --bit_path_from /output/compressed \
  --ply_path_to /output/restored.ply
```

---

##### 步骤 3: 验证质量（可选）

```bash
python decode_single_scene_validate.py \
  --lmd <LAMBDA> \
  --bit_path_from <INPUT_DIR> \
  --ply_path_to <OUTPUT_PLY> \
  --source_path <REFERENCE_IMAGES_DIR>
```

---

#### 批量压缩

使用提供的批量脚本：

```bash
bash batch_compress.sh \
  <INPUT_DIR> \
  <LAMBDA> \
  <OUTPUT_DIR>
```

**示例**：
```bash
# 为目录中的所有 PLY 文件压缩
bash batch_compress.sh \
  /workspace/ply_files \
  4e-4 \
  /output/batch_compressed
```

---

## 🔍 环境验证完成检测

### 一键验证脚本

将以下内容保存为 `verify_env.sh`，在远程主机上运行：

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "远程环境验证脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass_count=0
fail_count=0

check_item() {
  local name=$1
  local cmd=$2
  echo -n "检查 $name ... "
  if eval "$cmd" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    ((pass_count++))
  else
    echo -e "${RED}✗ FAIL${NC}"
    ((fail_count++))
  fi
}

# 系统检查
echo ""
echo "--- 系统信息 ---"
check_item "Linux 系统" "uname -a | grep -i linux"
check_item "磁盘空间 (≥100GB)" "[ $(df / | awk 'NR==2 {print $4}') -gt 100000000 ]"
check_item "GPU 驱动" "nvidia-smi"

# Python 检查
echo ""
echo "--- Python 环境 ---"
check_item "Python 3.10" "python3 --version | grep '3.10'"
check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"

# 依赖包检查
echo ""
echo "--- 依赖包 ---"
check_item "plyfile" "python3 -c 'import plyfile'"
check_item "lpips" "python3 -c 'import lpips'"
check_item "einops" "python3 -c 'import einops'"
check_item "numpy" "python3 -c 'import numpy'"
check_item "torch-scatter" "python3 -c 'import torch_scatter'"

# 环境激活检查
echo ""
echo "--- 环境激活 ---"
if command -v conda &> /dev/null; then
  check_item "Conda 命令" "conda --version"
  check_item "conda activate 脚本" "[ -f ~/.bashrc ] || [ -f ~/miniconda3/etc/profile.d/conda.sh ]"
else
  echo -e "${YELLOW}⚠ Conda 未在 PATH 中${NC}"
fi

# 子模块检查
echo ""
echo "--- 项目子模块 ---"
check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
check_item "simple-knn" "python3 -c 'import simple_knn'"

# 总结
echo ""
echo "=========================================="
echo -e "检查完成: ${GREEN}✓ $pass_count 项通过${NC}, ${RED}✗ $fail_count 项失败${NC}"
echo "=========================================="

if [ $fail_count -eq 0 ]; then
  echo -e "${GREEN}✓ 环境配置正确，可以开始训练${NC}"
  exit 0
else
  echo -e "${RED}✗ 环境存在问题，请查看上面的失败项并修复${NC}"
  exit 1
fi
```

**运行方式**：
```bash
bash verify_env.sh
```

**输出示例**：
```
==========================================
远程环境验证脚本
==========================================

--- 系统信息 ---
检查 Linux 系统 ... ✓ PASS
检查 磁盘空间 (≥100GB) ... ✓ PASS
检查 GPU 驱动 ... ✓ PASS

--- Python 环境 ---
检查 Python 3.10 ... ✓ PASS
检查 PyTorch 2.2 ... ✓ PASS
检查 CUDA 可用 ... ✓ PASS
...

==========================================
检查完成: ✓ 11 项通过, ✗ 0 项失败
==========================================
✓ 环境配置正确，可以开始训练
```

---

## 🆘 故障排除

### Q1: conda: command not found

**症状**：运行 conda 命令时显示命令未找到

**解决方案**：
```bash
# 方案 A: 检查 ~/.bashrc 初始化
grep "conda" ~/.bashrc

# 方案 B: 手动初始化 conda
eval "$(/home/YOUR_USERNAME/miniconda3/bin/conda shell.bash hook)"
conda activate HAC_env

# 方案 C: 使用完整路径激活
source ~/miniconda3/etc/profile.d/conda.sh
conda activate HAC_env
```

---

### Q2: ImportError: cannot import name 'simple_knn'

**症状**：运行训练时报错 `ModuleNotFoundError: No module named 'simple_knn'`

**原因**：子模块未正确编译或安装

**解决方案**：
```bash
# 清理旧编译
rm -rf submodules/simple-knn/build
rm -rf submodules/simple-knn/*.so

# 重新初始化子模块
git submodule update --init --recursive

# 进入子模块目录并编译
cd submodules/simple-knn
python setup.py install
cd ../..

# 验证
python -c "import simple_knn; print('✓ simple_knn OK')"
```

---

### Q3: CUDA out of memory

**症状**：训练中途显示 `RuntimeError: CUDA out of memory`

**原因**：显存不足或批次过大

**解决方案**：
```bash
# 减小迭代次数或调小参数
python train.py \
  -s <SOURCE> \
  -m <OUTPUT> \
  --iterations 15_000  # 减半
```

---

### Q4: RuntimeError: CUDA driver version is insufficient

**症状**：CUDA 版本与驱动不匹配

**解决方案**：
```bash
# 检查驱动版本
nvidia-smi

# 检查 PyTorch CUDA 版本
python -c "import torch; print(torch.version.cuda)"

# 如果不匹配，重新安装对应 CUDA 版本的 PyTorch
# 示例：安装 CUDA 11.8 版本
conda install pytorch=2.2 pytorch-cuda=11.8 -c pytorch -c nvidia
```

---

### Q5: ImportError: cannot import name 'lpips'

**症状**：导入 lpips 失败

**解决方案**：
```bash
# 卸载旧版本
pip uninstall lpips -y

# 重新安装
pip install lpips

# 如果上面失败，尝试从 GitHub 安装
pip install git+https://github.com/richzhang/PerceptualSimilarity.git
```

---

## 📋 SSH 前置检查清单

在使用 Web_Scan 的远程训练功能前，请完成以下检查：

### ✅ 连接检查
- [ ] SSH 连接可用：`ssh <user>@<host> -p <port> echo "OK"`
- [ ] 用户名和密码正确
- [ ] 无防火墙阻挡 SSH 端口（通常 22）

### ✅ 系统检查
- [ ] GPU 驱动正常：`nvidia-smi` 输出显示 GPU
- [ ] 磁盘空间充足：`df -h | grep -E "/$|/tmp"` 显示 ≥ 200GB 可用空间
- [ ] Python 版本 3.10：`python3 --version`

### ✅ 环境检查
- [ ] Conda 环境已创建：`conda env list | grep -E "HAC_env|FCGS_env|contextgs"`
- [ ] 环境激活命令可用：`source ~/.bashrc && conda activate HAC_env` 或 `source ~/.bashrc && conda activate contextgs`

### ✅ 项目检查
- [ ] 项目代码已克隆/复制到远程主机
- [ ] 子模块已初始化：`ls -la submodules/ | wc -l` 输出多于 2（不是空目录）
- [ ] 关键脚本存在：`ls -l train.py encode_single_scene.py` 等

### ✅ 验证脚本
- [ ] 运行 `bash verify_env.sh`，所有项 ✓ 通过

---

## 📞 联系与支持

- **文档位置**：[web/project_md/REMOTE_SETUP_GUIDE_NEW.md](../REMOTE_SETUP_GUIDE_NEW.md)
- **诊断工具**：`python diagnose.py` (HAC-plus / FCGS) 或 `bash web/tools/remote_verify_setup.sh contextgs` (ContextGS)
- **问题报告**：记录 `diagnose.py` 的输出，提交至项目 Issue

---

**祝你训练顺利！** 🚀
