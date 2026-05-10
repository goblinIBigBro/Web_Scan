#!/bin/bash

#
# 远程环境验证脚本 - 通用版本
# 支持新旧版本算法环境检查
#
# 用法：
#   bash remote_verify_setup.sh              # 自动检测
#   bash remote_verify_setup.sh new          # 新版（HAC-plus/FCGS）
#   bash remote_verify_setup.sh contextgs    # ContextGS Python 3.10 + CUDA 12.1
#   bash remote_verify_setup.sh compgs       # CompGS Python 3.10 + CUDA 12.1
#   bash remote_verify_setup.sh reduced-3dgs # Reduced-3DGS Python 3.10 + CUDA 12.1
#   bash remote_verify_setup.sh megs2        # MEGS2 Python 3.10 + CUDA 12.1
#   bash remote_verify_setup.sh gaussian-splatting-lightning # GSL Python 3.10 + CUDA 12.1
#   bash remote_verify_setup.sh old          # 旧版（Scaffold-GS 等）
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 计数器
pass_count=0
fail_count=0
skip_count=0

# 检查函数
check_item() {
  local name=$1
  local cmd=$2
  local optional=${3:-false}
  
  echo -n "检查 $name ... "
  
  if eval "$cmd" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    ((pass_count+=1))
  else
    if [ "$optional" = "true" ]; then
      echo -e "${YELLOW}⚠ SKIP (可选)${NC}"
      ((skip_count+=1))
    else
      echo -e "${RED}✗ FAIL${NC}"
      ((fail_count+=1))
    fi
  fi
}

# 获取 Python 版本
get_python_version() {
  python3 --version 2>&1 | awk '{print $2}'
}

# 获取 PyTorch 版本
get_pytorch_version() {
  python3 -c "import torch; print(torch.__version__)" 2>/dev/null || echo "N/A"
}

# 检测环境版本
detect_version() {
  local python_ver=$(get_python_version)
  local pytorch_ver=$(get_pytorch_version)
  
  if [[ "$python_ver" == 3.10* ]] && python3 -c 'import compressai, torchac' >/dev/null 2>&1; then
    echo "contextgs"
  elif [[ "$python_ver" == 3.10* ]] && python3 -c 'import compressai, torch_scatter, knn_dist, diff_gaussian_rasterization' >/dev/null 2>&1; then
    echo "compgs"
  elif [[ "$python_ver" == 3.10* ]] && python3 -c 'import lightning, diff_gaussian_rasterization, simple_knn, gsplat' >/dev/null 2>&1; then
    echo "gaussian-splatting-lightning"
  elif [[ "$python_ver" == 3.10* ]] && python3 -c 'import diff_gaussian_rasterization, diff_gaussian_rasterization_ms, diff_gaussian_rasterization_ms_light, simple_knn' >/dev/null 2>&1; then
    echo "megs2"
  elif [[ "$python_ver" == 3.10* ]] && python3 -c 'import pandas, diff_gaussian_rasterization, simple_knn' >/dev/null 2>&1; then
    echo "reduced-3dgs"
  elif [[ "$python_ver" == 3.10* ]]; then
    echo "new"
  elif [[ "$python_ver" == 3.7* ]]; then
    echo "old"
  else
    echo "unknown"
  fi
}

# 新版检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1/11.8）
check_new_version() {
  echo -e "\n${BLUE}=== 新版算法组检查 (Python 3.10 + PyTorch 2.2) ===${NC}"
  echo ""
  
  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  
  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert \"2.2\" in torch.__version__'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  
  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "CUDA 12.1 或 11.8" "python3 -c 'import torch; v=torch.version.cuda; assert v and (\"12.1\" in v or \"11.8\" in v)'"
  
  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "lpips" "python3 -c 'import lpips'"
  check_item "einops" "python3 -c 'import einops'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "scipy" "python3 -c 'import scipy'"
  check_item "tqdm" "python3 -c 'import tqdm'"
  check_item "torch-scatter" "python3 -c 'import torch_scatter'" true
  
  # 子模块检查
  echo ""
  echo "--- 项目子模块 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "simple-knn" "python3 -c 'import simple_knn'"
  
  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "HAC_env 或 FCGS_env 存在" "conda env list | grep -E 'HAC_env|FCGS_env'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# ContextGS 检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
check_contextgs_version() {
  echo -e "\n${BLUE}=== ContextGS 检查 (Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090) ===${NC}"
  echo ""

  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  check_item "CUDA Toolkit / nvcc" "command -v nvcc >/dev/null 2>&1"

  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  check_item "RTX 4090" "python3 -c 'import torch; assert torch.cuda.is_available() and \"4090\" in torch.cuda.get_device_name(0)'"

  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "PyTorch CUDA 12.1" "python3 -c 'import torch; v=torch.version.cuda; assert v and v.startswith(\"12.1\")'"
  check_item "CUDA 架构 sm_89" "python3 -c 'import torch; assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)'"

  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "torchvision" "python3 -c 'import torchvision'"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "lpips" "python3 -c 'import lpips'"
  check_item "einops" "python3 -c 'import einops'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "scipy" "python3 -c 'import scipy'"
  check_item "tqdm" "python3 -c 'import tqdm'"
  check_item "compressai" "python3 -c 'import compressai'"
  check_item "torchac" "python3 -c 'import torchac'"
  check_item "opencv-python" "python3 -c 'import cv2'"
  check_item "torch-scatter" "python3 -c 'import torch_scatter'"

  # 子模块检查
  echo ""
  echo "--- ContextGS CUDA 子模块 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "simple-knn" "python3 -c 'import simple_knn'"

  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "contextgs 环境存在" "conda env list | grep -E '^contextgs[[:space:]]|[[:space:]]contextgs$|/contextgs$'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# CompGS 检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
check_compgs_version() {
  echo -e "\n${BLUE}=== CompGS 检查 (Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090) ===${NC}"
  echo ""

  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  check_item "CUDA Toolkit / nvcc" "command -v nvcc >/dev/null 2>&1"

  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  check_item "RTX 4090" "python3 -c 'import torch; assert torch.cuda.is_available() and \"4090\" in torch.cuda.get_device_name(0)'"

  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "PyTorch CUDA 12.1" "python3 -c 'import torch; v=torch.version.cuda; assert v and v.startswith(\"12.1\")'"
  check_item "CUDA 架构 sm_89" "python3 -c 'import torch; assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)'"

  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "torchvision" "python3 -c 'import torchvision'"
  check_item "compressai" "python3 -c 'import compressai'"
  check_item "torch-scatter" "python3 -c 'import torch_scatter'"
  check_item "lpips" "python3 -c 'import lpips'"
  check_item "pytorch-msssim" "python3 -c 'import pytorch_msssim'"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "einops" "python3 -c 'import einops'"
  check_item "PyYAML" "python3 -c 'import yaml'"
  check_item "Pillow" "python3 -c 'import PIL'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "tqdm" "python3 -c 'import tqdm'"

  # CUDA 扩展检查
  echo ""
  echo "--- CompGS CUDA 扩展 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "knn_dist" "python3 -c 'import knn_dist'"

  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "CompGS_env 环境存在" "conda env list | grep -E '^CompGS_env[[:space:]]|[[:space:]]CompGS_env$|/CompGS_env$'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# Reduced-3DGS 检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
check_reduced_3dgs_version() {
  echo -e "\n${BLUE}=== Reduced-3DGS 检查 (Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090) ===${NC}"
  echo ""

  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  check_item "CUDA Toolkit / nvcc" "command -v nvcc >/dev/null 2>&1"

  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  check_item "RTX 4090" "python3 -c 'import torch; assert torch.cuda.is_available() and \"4090\" in torch.cuda.get_device_name(0)'"

  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "PyTorch CUDA 12.1" "python3 -c 'import torch; v=torch.version.cuda; assert v and v.startswith(\"12.1\")'"
  check_item "CUDA 架构 sm_89" "python3 -c 'import torch; assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)'"

  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "torchvision" "python3 -c 'import torchvision'"
  check_item "pandas" "python3 -c 'import pandas'"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "Pillow" "python3 -c 'import PIL'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "tqdm" "python3 -c 'import tqdm'"
  check_item "nvtx" "python3 -c 'import nvtx'" true

  # 子模块检查
  echo ""
  echo "--- Reduced-3DGS CUDA 子模块 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "simple-knn" "python3 -c 'import simple_knn'"

  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "gaussian_splatting 环境存在" "conda env list | grep -E '^gaussian_splatting[[:space:]]|[[:space:]]gaussian_splatting$|/gaussian_splatting$'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# MEGS2 检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
check_megs2_version() {
  echo -e "\n${BLUE}=== MEGS2 检查 (Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090) ===${NC}"
  echo ""

  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  check_item "CUDA Toolkit / nvcc" "command -v nvcc >/dev/null 2>&1"

  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  check_item "RTX 4090" "python3 -c 'import torch; assert torch.cuda.is_available() and \"4090\" in torch.cuda.get_device_name(0)'"

  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "PyTorch CUDA 12.1" "python3 -c 'import torch; v=torch.version.cuda; assert v and v.startswith(\"12.1\")'"
  check_item "CUDA 架构 sm_89" "python3 -c 'import torch; assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)'"

  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "torchvision" "python3 -c 'import torchvision'"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "Pillow" "python3 -c 'import PIL'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "tqdm" "python3 -c 'import tqdm'"

  # 子模块检查
  echo ""
  echo "--- MEGS2 CUDA 子模块 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "diff-gaussian-rasterization-ms" "python3 -c 'import diff_gaussian_rasterization_ms'"
  check_item "diff-gaussian-rasterization-ms-light" "python3 -c 'import diff_gaussian_rasterization_ms_light'"
  check_item "simple-knn" "python3 -c 'import simple_knn'"

  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "MEGS2 环境存在" "conda env list | grep -E '^MEGS2[[:space:]]|[[:space:]]MEGS2$|/MEGS2$'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# Gaussian Splatting Lightning 检查（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
check_gaussian_splatting_lightning_version() {
  echo -e "\n${BLUE}=== Gaussian Splatting Lightning 检查 (Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090) ===${NC}"
  echo ""

  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  check_item "CUDA Toolkit / nvcc" "command -v nvcc >/dev/null 2>&1"

  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.10" "python3 --version | grep '3.10'"
  check_item "PyTorch 2.2" "python3 -c 'import torch; assert torch.__version__.startswith(\"2.2\")'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  check_item "RTX 4090" "python3 -c 'import torch; assert torch.cuda.is_available() and \"4090\" in torch.cuda.get_device_name(0)'"

  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "PyTorch CUDA 12.1" "python3 -c 'import torch; v=torch.version.cuda; assert v and v.startswith(\"12.1\")'"
  check_item "CUDA 架构 sm_89" "python3 -c 'import torch; assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)'"

  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "torchvision" "python3 -c 'import torchvision'"
  check_item "lightning" "python3 -c 'import lightning'"
  check_item "jsonargparse" "python3 -c 'import jsonargparse'"
  check_item "wandb" "python3 -c 'import wandb'"
  check_item "viser" "python3 -c 'import viser'"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "Pillow" "python3 -c 'import PIL'"
  check_item "opencv-python-headless" "python3 -c 'import cv2'"
  check_item "mediapy" "python3 -c 'import mediapy'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "tqdm" "python3 -c 'import tqdm'"

  # CUDA 扩展检查
  echo ""
  echo "--- Gaussian Splatting Lightning CUDA 扩展 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'"
  check_item "simple-knn" "python3 -c 'import simple_knn'"
  check_item "gsplat" "python3 -c 'import gsplat'"

  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "gspl 环境存在" "conda env list | grep -E '^gspl[[:space:]]|[[:space:]]gspl$|/gspl$'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# 旧版检查（Python 3.7.13 + PyTorch 1.12.1 + CUDA 11.6）
check_old_version() {
  echo -e "\n${BLUE}=== 旧版算法组检查 (Python 3.7.13 + PyTorch 1.12.1) ===${NC}"
  echo ""
  
  # 系统检查
  echo "--- 系统信息 ---"
  check_item "Linux 系统" "uname -a | grep -i linux"
  check_item "磁盘空间 (≥100GB)" "[ \$(df / 2>/dev/null | awk 'NR==2 {print \$4}') -gt 100000000 ]"
  check_item "GPU 驱动" "nvidia-smi > /dev/null"
  
  # Python 检查
  echo ""
  echo "--- Python 环境 ---"
  check_item "Python 3.7" "python3 --version | grep '3.7'"
  check_item "PyTorch 1.12" "python3 -c 'import torch; assert \"1.12\" in torch.__version__'"
  check_item "CUDA 可用" "python3 -c 'import torch; assert torch.cuda.is_available()'"
  check_item "GPU 可见" "python3 -c 'import torch; assert torch.cuda.device_count() > 0'"
  
  # CUDA 版本检查
  echo ""
  echo "--- CUDA 版本 ---"
  check_item "CUDA 11.6" "python3 -c 'import torch; v=torch.version.cuda; assert v and \"11.6\" in v'"
  
  # 依赖包检查
  echo ""
  echo "--- 依赖包 ---"
  check_item "plyfile" "python3 -c 'import plyfile'"
  check_item "lpips" "python3 -c 'import lpips'"
  check_item "einops" "python3 -c 'import einops'"
  check_item "numpy" "python3 -c 'import numpy'"
  check_item "scipy" "python3 -c 'import scipy'"
  check_item "tqdm" "python3 -c 'import tqdm'"
  check_item "torch-scatter" "python3 -c 'import torch_scatter'" true
  
  # 子模块检查
  echo ""
  echo "--- 项目子模块 ---"
  check_item "diff-gaussian-rasterization" "python3 -c 'import diff_gaussian_rasterization'" true
  check_item "simple-knn" "python3 -c 'import simple_knn'" true
  
  # 环境激活检查
  echo ""
  echo "--- 环境激活 ---"
  if command -v conda &> /dev/null; then
    check_item "Conda 命令" "conda --version"
    check_item "scaffold_gs 环境存在" "conda env list | grep -E 'scaffold_gs'" true
  else
    echo -e "${YELLOW}⚠ Conda 不在 PATH 中（可能使用绝对路径激活）${NC}"
  fi
}

# 显示汇总
show_summary() {
  echo ""
  echo "=========================================="
  echo "检查完成汇总"
  echo "=========================================="
  echo -e "  ${GREEN}✓ 通过：$pass_count 项${NC}"
  echo -e "  ${RED}✗ 失败：$fail_count 项${NC}"
  if [ $skip_count -gt 0 ]; then
    echo -e "  ${YELLOW}⚠ 跳过：$skip_count 项 (可选)${NC}"
  fi
  echo "=========================================="
  
  if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ 环境配置正确，可以开始训练${NC}"
    return 0
  else
    echo -e "${RED}✗ 环境存在问题，请查看上面的失败项并修复${NC}"
    return 1
  fi
}

# 主流程
main() {
  version=$1
  
  echo -e "${BLUE}=========================================="
  echo "Web_Scan 远程环境验证脚本"
  echo "=========================================${NC}"
  echo ""
  
  # 如果未指定版本，自动检测
  if [ -z "$version" ]; then
    version=$(detect_version)
    echo "自动检测环境版本: $version"
    
    if [ "$version" = "unknown" ]; then
      echo -e "${YELLOW}无法自动检测环境版本${NC}"
      echo "请手动指定:"
      echo "  bash remote_verify_setup.sh new   (新版: Python 3.10 + PyTorch 2.2)"
      echo "  bash remote_verify_setup.sh contextgs   (ContextGS: Python 3.10 + PyTorch 2.2 + CUDA 12.1)"
      echo "  bash remote_verify_setup.sh compgs   (CompGS: Python 3.10 + PyTorch 2.2 + CUDA 12.1)"
      echo "  bash remote_verify_setup.sh reduced-3dgs   (Reduced-3DGS: Python 3.10 + PyTorch 2.2 + CUDA 12.1)"
      echo "  bash remote_verify_setup.sh megs2   (MEGS2: Python 3.10 + PyTorch 2.2 + CUDA 12.1)"
      echo "  bash remote_verify_setup.sh gaussian-splatting-lightning   (GSL: Python 3.10 + PyTorch 2.2 + CUDA 12.1)"
      echo "  bash remote_verify_setup.sh old   (旧版: Python 3.7 + PyTorch 1.12)"
      return 1
    fi
  fi
  
  echo ""
  
  # 执行对应检查
  case $version in
    new)
      check_new_version
      ;;
    contextgs)
      check_contextgs_version
      ;;
    compgs)
      check_compgs_version
      ;;
    reduced-3dgs)
      check_reduced_3dgs_version
      ;;
    megs2)
      check_megs2_version
      ;;
    gaussian-splatting-lightning|gs-lightning)
      check_gaussian_splatting_lightning_version
      ;;
    old)
      check_old_version
      ;;
    *)
      echo -e "${RED}未知的版本: $version${NC}"
      echo "请使用 'new'、'contextgs'、'compgs'、'reduced-3dgs'、'megs2'、'gaussian-splatting-lightning'、'gs-lightning' 或 'old'"
      return 1
      ;;
  esac
  
  # 显示汇总
  show_summary
}

# 运行主程序
main "$@"
exit $?
