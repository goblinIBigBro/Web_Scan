# 远程 SSH 环境配置指南 — 旧版算法组

> **适用项目**：Scaffold-GS  
> **环境**：Python 3.7.13 + PyTorch 1.12.1 + CUDA 11.6  
> **说明**：CompGS、ContextGS、reduced-3dgs 和 MEGS-2 已升级到 Python 3.10 + PyTorch 2.2 + CUDA 12.1，请使用 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)。
> **更新日期**：2026 年 4 月  
> **作者**：Web_Scan 文档

---

## 📌 快速检测清单

在配置前，请确认你的远程主机满足以下条件：

```bash
# 1️⃣ 系统检查
uname -a                          # 应为 Linux (Ubuntu 20.04/22.04)
df -h | grep -E "/$|/tmp"         # 磁盘剩余 ≥ 200GB
nvidia-smi                        # GPU 驱动正常

# 2️⃣ Python 和 PyTorch 快速验证（复制整行运行）
python3 --version && python3 -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.version.cuda}, Available: {torch.cuda.is_available()}')"

# 3️⃣ 关键依赖检查
python3 -c "import plyfile, lpips, einops, numpy, tqdm; print('✓ All deps found')" 2>&1 || echo "Some packages missing"

# 如果上面出现错误，请继续阅读下面的"分步部署"
```

---

## 🏗️ 分步部署指南

### 第一步：准备 Conda 环境

#### 方案 A：使用官方 environment.yml（推荐）

选择对应的算法进行初始化：

```bash
# Scaffold-GS
cd ~/Web_Scan/Scaffold-GS-main
conda env create --file environment.yml
conda activate scaffold_gs
```

**预计时间**：15-20 分钟（首次下载）

---

#### 方案 B：手动创建统一环境

如果想为所有算法创建一个统一的 Python 3.7.13 环境（不推荐，但可行）：

```bash
# 创建环境
conda create -n GS_legacy python=3.7.13 -y
conda activate GS_legacy

# 添加频道
conda config --env --add channels pytorch
conda config --env --add channels nvidia

# 安装 PyTorch 1.12.1 和 CUDA 11.6
conda install pytorch=1.12.1 torchvision=0.13.1 torchaudio=0.12.1 pytorch-cuda=11.6 -c pytorch -c nvidia -y

# 安装基础科学计算
conda install numpy scipy tqdm plyfile pip -y

# 通用依赖
pip install einops wandb lpips laspy opencv-python imageio matplotlib tensorboard prettytable

# 特殊依赖（某些算法需要）
pip install compressai pytorch_msssim torchac
```

---

### 第二步：准备项目代码

```bash
# 以 Scaffold-GS 为例
cd ~/Web_Scan/Scaffold-GS-main

# 初始化子模块（非常重要）
git submodule update --init --recursive

# 或者（如果子模块是 ZIP 文件）
cd submodules
for d in */; do
  if [ -f "$d/setup.py" ]; then
    cd "$d"
    python setup.py install > /dev/null 2>&1
    cd ..
  fi
done
cd ..
```

**常见问题**：子模块编译可能在 Python 3.7 环境中出现兼容性问题，参考 [故障排除](#️-故障排除) 章节。

---

### 第三步：检查环境完整性

运行以下检查（对所有旧版算法通用）：

```bash
# 检查 Python 版本
python --version  # 应输出 Python 3.7.13

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
packages = ['plyfile', 'lpips', 'einops', 'numpy', 'scipy', 'tqdm', 'wandb', 'PIL', 'cv2', 'torch_scatter']
failed = []
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
        failed.append(pkg_name)
        print(f'✗ {pkg_name} MISSING')

if failed:
    print(f'\n缺失包: {failed}')
    print('运行: pip install ' + ' '.join(failed))
"
```

**验证成功标志**：
- ✅ Python 版本为 3.7.13
- ✅ CUDA Available: True
- ✅ GPU Count ≥ 1
- ✅ 所有包都显示 ✓

---

### 第四步：配置 SSH 激活命令

在本地 Web_Scan 应用中，配置远程服务器时需要填写 **Remote Activate Command**。

根据算法选择对应的激活命令：

```bash
# Scaffold-GS
source ~/.bashrc && conda activate scaffold_gs

# 或统一环境（如果使用方案 B）
source ~/.bashrc && conda activate GS_legacy
```

#### ⚠️ 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|--------|
| `conda: command not found` | conda 路径未找到 | 检查 `~/.bashrc` 中的 conda 初始化 |
| 环境前缀消失 | 非交互 shell 中 conda 激活失败 | 使用 `source ~/.bashrc && conda activate <env>` 的完整形式 |
| `environment not found` | 环境名称拼写错误 | 运行 `conda env list` 确认环境名称 |

---

## 🚀 训练启动指南

### CompGS（已迁移到新版环境）

CompGS 当前使用 Python 3.10 + PyTorch 2.2 + CUDA 12.1，并针对 RTX 4090 检查 CUDA capability 8.9。请参考 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)，并使用：

```bash
cd ~/Web_Scan/CompGS-main
conda activate CompGS_env
bash ../web/tools/remote_verify_setup.sh compgs
```

CompGS 仍使用 YAML 配置文件，而不是大多数新版算法使用的命令行参数。

### CompGS YAML 配置方式

#### 参数配置方式

**CompGS 使用 YAML 配置文件而非命令行参数**。参数需要修改 `Configs/` 目录中的 YAML 文件。

#### 配置流程

##### 步骤 1: 复制或创建配置文件

```bash
cd ~/Web_Scan/CompGS-main

# 使用内置模板
cp Configs/MipNeRF360.yaml Configs/my_training.yaml

# 或创建新配置
cat > Configs/my_training.yaml << 'EOF'
dataset:
  root: /workspace/data/chair
  image_folder: images

training:
  max_iterations: 30000
  save_directory: /output/chair
  save_interval: 10000
  lambda_weight: 0.001

model:
  # 其他模型参数
EOF
```

##### 步骤 2: 修改关键参数

编辑 `Configs/my_training.yaml`，修改以下字段：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `dataset.root` | str | 数据集根目录 | `/workspace/data/chair` |
| `dataset.image_folder` | str | 图像子目录名 | `images`, `images_4`, `input` |
| `training.max_iterations` | int | 最大训练迭代数 | 30000 |
| `training.save_directory` | str | 模型保存目录 | `/output/chair` |
| `training.save_interval` | int | 保存间隔（迭代） | 10000 |
| `training.lambda_weight` | float | 压缩强度 | 0.001, 0.0005, 0.003 |

##### 步骤 3: 启动训练

```bash
python Train.py --config Configs/my_training.yaml

# 或使用命令行覆盖参数
python Train.py --config Configs/my_training.yaml --key=value  # 如果支持
```

#### 快速启动示例

```bash
# 最小化测试（验证环境）
cat > Configs/test.yaml << 'EOF'
dataset:
  root: /workspace/data/nerf_synthetic/chair
  image_folder: images

training:
  max_iterations: 100
  save_directory: /output/test
  save_interval: 50
  lambda_weight: 0.001
EOF

python Train.py --config Configs/test.yaml

# 标准训练
cat > Configs/standard.yaml << 'EOF'
dataset:
  root: /workspace/data/scene
  image_folder: images

training:
  max_iterations: 30000
  save_directory: /output/scene_full
  save_interval: 10000
  lambda_weight: 0.001
EOF

python Train.py --config Configs/standard.yaml
```

---

### ContextGS（已迁移到新版环境）

ContextGS 当前使用 Python 3.10 + PyTorch 2.2 + CUDA 12.1，并针对 RTX 4090 检查 CUDA capability 8.9。请参考 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)，并使用：

```bash
cd ~/Web_Scan/ContextGS-main
conda env create --file environment.yml
conda activate contextgs
bash ../web/tools/remote_verify_setup.sh contextgs
```

### 旧版命令行算法（Scaffold-GS）

#### 参数配置方式

这些旧版算法使用命令行参数。完整参数通过各项目的 `train.py -h` 查看。

#### 必需参数

```bash
python train.py -s <SOURCE_PATH> -m <OUTPUT_PATH> [OPTIONS]
```

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `-s` / `--source_path` | str | 数据集路径 | `/workspace/data/chair` |
| `-m` / `--model_path` | str | 模型输出目录 | `/output/chair_result` |

#### 常用可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--iterations` | 30000 | 训练迭代数 |
| `--eval` | False | 启用评估模式 |
| `--test_iterations` | 7000 | 测试间隔 |
| `--save_iterations` | 10000 | 保存间隔 |

#### 快速启动示例

```bash
# 测试
python train.py \
  -s /workspace/data/nerf_synthetic/chair \
  -m /output/test_chair \
  --iterations 100

# 完整训练
python train.py \
  -s /workspace/data/scene \
  -m /output/scene_full \
  --iterations 30000 \
  --eval
```

---

### MEGS-2（已迁移到新版环境）

MEGS-2 当前使用 Python 3.10 + PyTorch 2.2 + CUDA 12.1，并针对 RTX 4090 检查 CUDA capability 8.9。请参考 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)，并使用：

```bash
cd ~/Web_Scan/MEGS-2-main
conda env create --file environment.yml
conda activate MEGS2
bash ../web/tools/remote_verify_setup.sh megs2
```

---

### reduced-3dgs（已迁移到新版环境）

reduced-3dgs 当前使用 Python 3.10 + PyTorch 2.2 + CUDA 12.1，并针对 RTX 4090 检查 CUDA capability 8.9。请参考 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)，并使用：

```bash
cd ~/Web_Scan/reduced-3dgs-main
conda env create --file environment.yml
conda activate gaussian_splatting
bash ../web/tools/remote_verify_setup.sh reduced-3dgs
```

---

### Scaffold-GS（命令行参数方式）

#### 参数配置方式

**Scaffold-GS 使用命令行参数**。

#### 快速启动示例

```bash
# 基础训练
python train.py \
  -s /workspace/data/scene \
  -m /output/scaffold_result

# 完整训练
python train.py \
  -s /workspace/data/scene \
  -m /output/scaffold_full \
  --eval \
  --iterations 30000
```

---

## 🔍 环境验证完成检测

### 一键验证脚本

将以下内容保存为 `verify_env_legacy.sh`，在远程主机上运行：

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "远程环境验证脚本（旧版算法组）"
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
check_item "磁盘空间 (≥100GB)" "[ \$(df / | awk 'NR==2 {print \$4}') -gt 100000000 ]"
check_item "GPU 驱动" "nvidia-smi"

# Python 检查
echo ""
echo "--- Python 环境 ---"
check_item "Python 3.7" "python3 --version | grep '3.7'"
check_item "PyTorch 1.12" "python3 -c 'import torch; assert torch.__version__.startswith(\"1.12\")'"
check_item "CUDA 11.6 兼容" "python3 -c 'import torch; v=torch.version.cuda; assert v and (\"11.6\" in v or \"11\" in v)'"
check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"

# 依赖包检查
echo ""
echo "--- 依赖包 ---"
check_item "plyfile" "python3 -c 'import plyfile'"
check_item "lpips" "python3 -c 'import lpips'"
check_item "einops" "python3 -c 'import einops'"
check_item "numpy" "python3 -c 'import numpy'"
check_item "torch-scatter" "python3 -c 'import torch_scatter'" || echo "(可选)"

# 子模块检查（示例）
echo ""
echo "--- 项目子模块 ---"
check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'" || echo "(某些算法可选)"
check_item "simple-knn" "python3 -c 'import simple_knn'" || echo "(某些算法可选)"

# 环境激活检查
echo ""
echo "--- 环境激活 ---"
if command -v conda &> /dev/null; then
  check_item "Conda 命令" "conda --version"
else
  echo -e "${YELLOW}⚠ Conda 未在 PATH 中${NC}"
fi

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
bash verify_env_legacy.sh
```

---

## 🆘 故障排除

### Q1: ImportError: cannot import name 'diff_gaussian_rasterization'

**症状**：运行训练时报错 `ModuleNotFoundError: No module named 'diff_gaussian_rasterization'`

**原因**：子模块未正确编译（Python 3.7 编译器兼容性问题）

**解决方案**：
```bash
# 清理旧编译
rm -rf submodules/diff-gaussian-rasterization/build
rm -rf submodules/diff-gaussian-rasterization/*.so

# 重新编译（确保在正确的环境中）
cd submodules/diff-gaussian-rasterization
python setup.py install

# 验证
cd ../..
python -c "import diff_gaussian_rasterization; print('✓ OK')"

# 如果仍失败，检查编译器
gcc --version  # 应为 gcc 7.x 或更高
```

---

### Q2: RuntimeError: CUDA driver version is insufficient

**症状**：CUDA 版本与驱动不匹配

**解决方案**：
```bash
# 检查当前驱动版本
nvidia-smi

# 查看支持的最高 CUDA 版本
# 例如：如果显示 "CUDA Version: 11.8"，你最多可以使用 11.8 或更低版本

# 检查 PyTorch 使用的 CUDA 版本
python -c "import torch; print(torch.version.cuda)"

# 如果版本过高，降级 PyTorch CUDA 版本
# 示例：降级到 CUDA 11.6
conda install pytorch=1.12.1 pytorch-cuda=11.6 torchvision=0.13.1 -c pytorch -c nvidia
```

---

### Q3: error: Microsoft Visual C++ 14.0 is required (Windows on Linux)

**症状**：编译 C++ 子模块时报错缺少编译器

**原因**：系统中没有 C++ 编译工具链

**解决方案（Ubuntu/Debian）**：
```bash
# 安装编译工具
sudo apt-get update
sudo apt-get install -y build-essential
sudo apt-get install -y python3.7-dev  # 如果使用 Python 3.7

# 重新编译子模块
cd submodules/diff-gaussian-rasterization
python setup.py install
cd ../..
```

---

### Q4: ImportError: cannot import name 'simple_knn'

**症状**：导入 simple_knn 失败

**解决方案**：
```bash
# 清理旧编译
rm -rf submodules/simple-knn/build
rm -rf submodules/simple-knn/*.so

# 重新初始化并编译
cd submodules/simple-knn
python setup.py install
cd ../..

# 验证
python -c "import simple_knn; print('✓ simple_knn OK')"
```

---

### Q5: CUDA out of memory

**症状**：训练中途显示 `RuntimeError: CUDA out of memory`

**原因**：显存不足

**解决方案**：
```bash
# 对于 CompGS，减小配置中的参数
# 编辑 Configs/my_training.yaml
training:
  max_iterations: 15000  # 减半

# 对于其他算法，使用命令行参数
python train.py -s <SOURCE> -m <OUTPUT> --iterations 15000
```

---

### Q6: COLMAP not found (HAC-plus/FCGS 仅）

**症状**：需要 COLMAP 处理图像数据

**解决方案**（仅适用新版算法，但在旧版中如果需要）：
```bash
# 检查 COLMAP 是否可用
which colmap

# 如果未找到，安装 COLMAP
sudo apt-get install colmap

# 验证
colmap -h
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
- [ ] 磁盘空间充足：`df -h` 显示 ≥ 200GB 可用空间
- [ ] Python 版本 3.7.13：`python3 --version`

### ✅ 环境检查
- [ ] Conda 环境已创建：`conda env list` 显示 scaffold_gs
- [ ] 环境激活命令可用：`source ~/.bashrc && conda activate scaffold_gs`

### ✅ 项目检查
- [ ] 项目代码已克隆到远程主机
- [ ] 子模块已初始化：`ls -la submodules/ | wc -l` 输出多于 2
- [ ] 关键脚本存在：`ls -l train.py` 等

### ✅ 验证脚本
- [ ] 运行 `bash verify_env_legacy.sh`，所有项 ✓ 通过

---

## 📊 算法对应表

| 算法 | Conda 环境名 | 激活命令 | 训练脚本 | 参数方式 | 状态 |
|------|-------------|---------|---------|---------|------|
| CompGS | CompGS_env | `conda activate CompGS_env` | Train.py | YAML 配置 | 已迁移到新版 |
| ContextGS | contextgs | `conda activate contextgs` | train.py | 命令行参数 | 已迁移到新版 |
| MEGS-2 | MEGS2 | `conda activate MEGS2` | train.py | 命令行参数 | 已迁移到新版 |
| reduced-3dgs | gaussian_splatting | `conda activate gaussian_splatting` | train.py | 命令行参数 | 已迁移到新版 |
| Scaffold-GS | scaffold_gs | `conda activate scaffold_gs` | train.py | 命令行参数 | ✓ |

---

## 📞 联系与支持

- **文档位置**：[web/project_md/REMOTE_SETUP_GUIDE_OLD.md](../REMOTE_SETUP_GUIDE_OLD.md)
- **问题报告**：运行 `verify_env_legacy.sh`，记录失败项目

---

**祝你训练顺利！** 🚀
