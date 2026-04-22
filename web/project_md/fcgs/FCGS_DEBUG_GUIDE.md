# FCGS 完整调试文档

## 目录
1. [环境配置](#环境配置)
2. [项目初始化](#项目初始化)
3. [数据准备](#数据准备)
4. [压缩和解压](#压缩和解压)
5. [性能评估](#性能评估)
6. [常见问题排查](#常见问题排查)
7. [性能优化](#性能优化)

---

## 环境配置

### 1. 基础系统要求
```bash
# 检查系统信息
uname -a

# 验证 CUDA 安装
nvidia-smi

# 验证 GCC 版本（需要 >= 9.4.0）
gcc --version
```

### 2. 创建 Conda 环境

```bash
# 进入项目目录
cd /Users/chen/Documents/Web_Scan/FCGS-main

# 创建环境（使用 environment.yml）
conda env create --file environment.yml

# 激活环境
conda activate FCGS_env

# 验证环境
conda list | grep torch
python -c "import torch; print(torch.__version__)"
python -c "import torch; print(torch.cuda.is_available())"
```

### 3. 克隆和更新子模块

```bash
# 如果之前未使用 --recursive 克隆
git submodule update --init --recursive

# 验证子模块
ls -la submodules/
# 应该包含: diff-gaussian-rasterization, simple-knn, freqencoder, gridencoder, gridcreater, arithmetic
```

### 4. 安装 TMC3（GPCC 编解码器）

```bash
# 克隆 MPEG codec 项目
git clone https://github.com/MPEGGroup/mpeg-pcc-tmc13.git
cd mpeg-pcc-tmc13

# 创建构建目录
mkdir build
cd build

# 编译
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j8

# 添加到环境变量
echo 'export PATH=$PATH:/path/to/mpeg-pcc-tmc13/build' >> ~/.bashrc
source ~/.bashrc

# 验证安装
which tmc3
tmc3 --version

# 注意：如果 tmc3 不在 PATH，需要在代码中修改路径
# 编辑 model/gpcc_utils.py 中的 tmc3 路径（共 2 处）
```

### 5. 验证安装

```bash
# 激活环境
conda activate FCGS_env

# 测试关键导入
python << 'EOF'
import torch
import numpy as np
from plyfile import PlyFile
from model.utils import load_ply, save_ply
print("✓ 所有导入成功")
print(f"✓ CUDA 可用: {torch.cuda.is_available()}")
print(f"✓ CUDA 设备: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'}")
EOF
```

---

## 项目初始化

### 1. 验证项目结构

```bash
# 检查必要的文件结构
ls -la /Users/chen/Documents/Web_Scan/FCGS-main/

# 输出应该包含：
# ├── encode_single_scene.py
# ├── decode_single_scene.py
# ├── decode_single_scene_validate.py
# ├── fcgs/
# ├── model/
# ├── utils/
# ├── submodules/
# └── environment.yml
```

### 2. 检查 Python 脚本

```bash
# 验证主要脚本存在
ls -la encode_single_scene.py decode_single_scene.py decode_single_scene_validate.py

# 检查脚本可执行性
file encode_single_scene.py
```

### 3. 验证模型文件

```bash
# 检查预训练模型
ls -la checkpoints/

# 查看模型结构
python << 'EOF'
import torch

# 列出可用的模型
checkpoints_dir = './checkpoints'
import os
models = [f for f in os.listdir(checkpoints_dir) if f.endswith('.pth')]
print(f"✓ 找到 {len(models)} 个模型文件:")
for model in models:
    print(f"  - {model}")
EOF
```

---

## 数据准备

### 1. 获取 3DGS 点云文件

FCGS 需要现有的 3DGS 点云文件（.ply 格式）作为输入。

**获取来源**:
- 使用其他 3DGS 训练方法（3DGS, 3DGS Editions 等）生成
- 从公开数据集下载预训练模型
- 自己训练 3DGS 模型

**示例**:
```bash
# 创建数据目录
mkdir -p data/ply_files

# 从预训练模型下载（示例）
# 或从其他来源获取 .ply 文件放到 data/ply_files/
```

### 2. 验证 PLY 文件格式

```bash
# 检查 PLY 文件的有效性
python << 'EOF'
from plyfile import PlyFile
import os

ply_path = "./data/ply_files/point_cloud.ply"

if os.path.exists(ply_path):
    try:
        ply_data = PlyFile(ply_path)
        print(f"✓ PLY 文件有效")
        print(f"  元素数: {len(ply_data.elements)}")
        for elem in ply_data.elements:
            print(f"    - {elem.name}: {elem.count} 个点")
            print(f"      属性: {elem.describe()}")
    except Exception as e:
        print(f"✗ PLY 文件读取失败: {e}")
else:
    print(f"✗ PLY 文件不存在: {ply_path}")
EOF
```

### 3. 理解 3DGS 属性

```
标准 3DGS PLY 文件包含以下属性:

几何信息:
  - x, y, z: 3D 位置坐标
  - nx, ny, nz: 法向量（可选）

外观信息:
  - f_dc_{0,1,2}: 球谐基函数系数（DC 分量）
  - f_rest_{0-44}: 球谐高阶系数（如果 sh_degree > 0）
  - opacity: 不透明度

缩放和旋转:
  - scale_{0,1,2}: 缩放因子
  - rot_{0,1,2,3}: 四元数旋转

其他:
  - shs_degree: 球谐函数的度数（通常为 3）
```

---

## 压缩和解压

### 1. 快速压缩示例

```bash
# 激活环境
conda activate FCGS_env

# 最小化测试压缩（测试设置）
python encode_single_scene.py \
  --lmd 1e-4 \
  --ply_path_from data/ply_files/point_cloud.ply \
  --bit_path_to outputs/test_compressed \
  --determ 1 \
  2>&1 | tee test_compress.log
```

### 2. 完整压缩流程

```bash
# 单个场景的完整压缩
python encode_single_scene.py \
  --lmd 4e-4 \
  --ply_path_from data/ply_files/scene_1.ply \
  --bit_path_to outputs/scene_1_compressed \
  --determ 1 \
  2>&1 | tee logs/compress_scene_1.log
```

### 3. 解压缩文件

```bash
# 从比特流恢复 PLY 文件
python decode_single_scene.py \
  --lmd 4e-4 \
  --bit_path_from outputs/scene_1_compressed \
  --ply_path_to outputs/scene_1_decompressed.ply \
  2>&1 | tee test_decompress.log
```

### 4. 验证解压质量

```bash
# 解压并评估与原始文件的相似性
python decode_single_scene_validate.py \
  --lmd 4e-4 \
  --bit_path_from outputs/scene_1_compressed \
  --ply_path_to outputs/scene_1_decompressed.ply \
  --source_path data/source_images/scene_1 \
  2>&1 | tee logs/validate_scene_1.log
```

### 5. 参数说明

```
关键参数解析:

--lmd (Lambda 参数)
  压缩强度，控制大小与保真度的权衡
  可选值: [1e-4, 2e-4, 4e-4, 8e-4, 16e-4]
  
  1e-4:   最大保真度，较大文件
  4e-4:   平衡配置（推荐）
  16e-4:  最大压缩，文件最小

--ply_path_from
  输入 PLY 文件的路径
  格式: /path/to/point_cloud.ply

--bit_path_to
  输出比特流保存的目录
  脚本会在此目录创建多个 .bin 文件

--bit_path_from
  输入比特流所在的目录
  用于解压

--ply_path_to
  输出 PLY 文件的保存路径

--determ
  确定性模式（0 或 1）
  1: 启用确定性操作，结果可复现
  0: 允许随机操作，可能略快

--source_path
  源场景的图像目录（用于验证）
  格式: /path/to/scene_images
  用于计算 PSNR 等评估指标
```

### 6. 批量压缩脚本示例

```bash
# 创建批量压缩脚本
cat > batch_compress.sh << 'EOF'
#!/bin/bash

set -e

# 配置
PLY_DIR="./data/ply_files"
OUTPUT_DIR="./outputs"
LAMBDA="4e-4"

# 创建输出目录
mkdir -p $OUTPUT_DIR

# 遍历所有 PLY 文件
for ply_file in $PLY_DIR/*.ply; do
    if [ -f "$ply_file" ]; then
        basename=$(basename "$ply_file" .ply)
        output_path="$OUTPUT_DIR/${basename}_compressed"
        
        echo "=========================================="
        echo "压缩: $basename"
        echo "=========================================="
        
        mkdir -p "$output_path"
        
        python encode_single_scene.py \
            --lmd $LAMBDA \
            --ply_path_from "$ply_file" \
            --bit_path_to "$output_path" \
            --determ 1 \
            2>&1 | tee logs/compress_${basename}.log
        
        echo "✓ $basename 压缩完成"
    fi
done

echo "=========================================="
echo "所有文件压缩完成!"
echo "=========================================="
EOF

chmod +x batch_compress.sh
./batch_compress.sh
```

---

## 性能评估

### 1. 压缩比计算

```bash
# 计算压缩比
python << 'EOF'
import os
from pathlib import Path

def calculate_compression_ratio(original_ply, compressed_dir):
    """计算压缩比"""
    
    # 原始文件大小
    original_size = os.path.getsize(original_ply)
    
    # 压缩后的总大小
    compressed_size = 0
    for root, dirs, files in os.walk(compressed_dir):
        for file in files:
            if file.endswith('.bin'):
                compressed_size += os.path.getsize(os.path.join(root, file))
    
    # 计算比率
    ratio = original_size / compressed_size if compressed_size > 0 else 0
    
    print(f"原始文件大小: {original_size / (1024**2):.2f} MB")
    print(f"压缩后大小: {compressed_size / (1024**2):.2f} MB")
    print(f"压缩比: {ratio:.2f}x")
    
    return ratio

# 使用示例
calculate_compression_ratio(
    "data/ply_files/point_cloud.ply",
    "outputs/test_compressed"
)
EOF
```

### 2. 质量评估（PSNR）

```bash
# 使用验证脚本评估质量
python decode_single_scene_validate.py \
  --lmd 4e-4 \
  --bit_path_from outputs/scene_compressed \
  --ply_path_to outputs/scene_decompressed.ply \
  --source_path data/scene_images \
  2>&1 | tee logs/evaluation.log

# 查看评估结果
grep -E "PSNR|SSIM|LPIPS" logs/evaluation.log
```

### 3. 性能基准

```bash
# 记录压缩时间
time python encode_single_scene.py \
  --lmd 4e-4 \
  --ply_path_from data/point_cloud.ply \
  --bit_path_to outputs/perf_test \
  --determ 1

# 记录解压缩时间
time python decode_single_scene.py \
  --lmd 4e-4 \
  --bit_path_from outputs/perf_test \
  --ply_path_to outputs/perf_test.ply
```

---

## 常见问题排查

### 问题 1: CUDA 不可用

```bash
# 诊断步骤
python << 'EOF'
import torch
print("CUDA 可用:", torch.cuda.is_available())
print("CUDA 版本:", torch.version.cuda)
print("设备数:", torch.cuda.device_count())
if torch.cuda.is_available():
    print("当前设备:", torch.cuda.current_device())
    print("设备名:", torch.cuda.get_device_name(0))
EOF

# 解决方案：重新安装 PyTorch
conda remove torch torchvision torchaudio pytorch-cuda -y
conda install pytorch=2.2 torchvision=0.17 torchaudio=2.2 pytorch-cuda=11.8 -c pytorch -c nvidia
```

### 问题 2: PLY 文件加载失败

```bash
# 诊断步骤
python << 'EOF'
from plyfile import PlyFile
import traceback

try:
    ply_data = PlyFile("data/ply_files/point_cloud.ply")
    print("✓ PLY 文件可以正常加载")
except Exception as e:
    print("✗ 加载失败:")
    traceback.print_exc()
EOF

# 解决方案
# 1. 检查文件路径是否正确
# 2. 检查文件是否完整（未损坏）
# 3. 验证 PLY 格式
```

### 问题 3: TMC3 不在 PATH 中

```bash
# 检查 tmc3 位置
which tmc3

# 如果未找到，手动指定路径
# 编辑 model/gpcc_utils.py，搜索 "change tmc3 path"
# 将 tmc3_path = "tmc3" 改为 tmc3_path = "/full/path/to/tmc3"
```

### 问题 4: 内存不足

```bash
# FCGS 是前馈网络，通常内存需求较小
# 但对于非常大的点云可能仍然不足

# 解决方案：清理 GPU 缓存
python << 'EOF'
import torch
torch.cuda.empty_cache()
print("✓ GPU 缓存已清理")
EOF
```

### 问题 5: 编码失败

```bash
# 检查错误消息
tail -100 logs/compress_*.log

# 常见原因：
# 1. PLY 文件格式不兼容
# 2. 输出目录权限问题
# 3. 磁盘空间不足

# 解决：
mkdir -p outputs
chmod 755 outputs
# 检查磁盘空间: df -h
```

### 问题 6: 解压质量差

```bash
# 检查使用的 lambda 值是否一致
# 编码和解码时必须使用相同的 lambda

# 验证
echo "检查编码日志中的 lambda 值"
grep "lmd" logs/compress_*.log

echo "检查解码日志中的 lambda 值"
grep "lmd" logs/decompress_*.log
```

---

## 性能优化

### 1. GPU 优化配置

```bash
# 创建优化配置
cat > optimize_fcgs.py << 'EOF'
# FCGS GPU 优化配置

import torch

# 启用 cuDNN 自动调优
torch.backends.cudnn.benchmark = True

# 使用混合精度（如适用）
from torch.cuda.amp import autocast

print("✓ GPU 优化配置已启用")
EOF
```

### 2. 批处理优化

```bash
# 同时处理多个文件时使用并行处理
# 使用 GNU parallel 或 xargs

# 示例：使用 parallel 并行压缩
find data/ply_files -name "*.ply" | \
  parallel -j 4 'python encode_single_scene.py --lmd 4e-4 --ply_path_from {} --bit_path_to outputs/{/.}_compressed --determ 1'
```

### 3. Lambda 参数选择优化

```bash
# 测试不同的 lambda 值以找到最优平衡
for lambda in 1e-4 2e-4 4e-4 8e-4 16e-4; do
    echo "测试 lambda=$lambda"
    
    python encode_single_scene.py \
      --lmd $lambda \
      --ply_path_from data/point_cloud.ply \
      --bit_path_to outputs/test_lambda_$lambda \
      --determ 1
    
    # 获取文件大小
    size=$(du -sh outputs/test_lambda_$lambda | cut -f1)
    echo "  压缩后大小: $size"
done
```

### 4. 内存优化

```bash
# 对于大型点云，清理中间结果
python << 'EOF'
import torch
import gc

# 显式垃圾回收
gc.collect()

# 清理 CUDA 缓存
torch.cuda.empty_cache()

# 监控内存
print(f"分配内存: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
print(f"保留内存: {torch.cuda.memory_reserved() / 1024**3:.2f} GB")
EOF
```

---

## 完整工作流示例

### 从零开始的完整流程

```bash
#!/bin/bash

# ========== 1. 环境配置 ==========
echo "步骤 1: 环境配置"
cd /Users/chen/Documents/Web_Scan/FCGS-main
conda env create --file environment.yml -y
conda activate FCGS_env

# ========== 2. 更新子模块 ==========
echo "步骤 2: 更新子模块"
git submodule update --init --recursive

# ========== 3. 创建必要目录 ==========
echo "步骤 3: 创建必要目录"
mkdir -p data/ply_files outputs logs

# ========== 4. 快速测试 ==========
echo "步骤 4: 快速测试（可选）"
if [ -f "data/ply_files/test.ply" ]; then
    python encode_single_scene.py \
      --lmd 4e-4 \
      --ply_path_from data/ply_files/test.ply \
      --bit_path_to outputs/quick_test \
      --determ 1
    
    echo "✓ 快速测试完成"
else
    echo "⚠ 测试 PLY 文件不存在，跳过测试"
fi

# ========== 5. 压缩示例 ==========
echo "步骤 5: 压缩示例"
echo "使用 batch_compress.sh 进行批量压缩"

# ========== 完成 ==========
echo "✓ 工作流设置完成!"
```

---

## 参数预设

### 质量优先（最高保真度）
```bash
--lmd 1e-4
# 结果: 最高质量，最大文件
```

### 平衡配置（推荐）
```bash
--lmd 4e-4
# 结果: 质量与大小的良好平衡
```

### 速度/压缩优先（最大压缩）
```bash
--lmd 16e-4
# 结果: 最小文件，可能降低质量
```

---

## 快速参考命令

```bash
# 激活环境
conda activate FCGS_env

# 压缩单个文件
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output_dir --determ 1

# 解压缩文件
python decode_single_scene.py --lmd 4e-4 --bit_path_from output_dir --ply_path_to output.ply

# 验证质量
python decode_single_scene_validate.py --lmd 4e-4 --bit_path_from output_dir --ply_path_to output.ply --source_path images_dir

# 监控 GPU
nvidia-smi

# 清理缓存
find outputs -name "*.bin" -delete
```

---

## 资源链接

- [FCGS GitHub](https://github.com/YihangChen-ee/FCGS/)
- [论文 (ICLR'25)](https://openreview.net/pdf?id=DCandSZ2F1)
- [Arxiv](https://arxiv.org/pdf/2410.08017)
- [项目主页](https://yihangchen-ee.github.io/project_fcgs/)
- [DL3DV-GS-960P 数据集](https://huggingface.co/datasets/DL3DV/DL3DV-GS-960P)

---

**最后更新**: 2025 年 4 月  
**文档版本**: 1.0  
**FCGS 版本**: Latest (ICLR'25)
