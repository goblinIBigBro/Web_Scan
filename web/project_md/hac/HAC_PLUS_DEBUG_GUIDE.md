# HAC++ 完整调试文档

## 目录
1. [环境配置](#环境配置)
2. [项目初始化](#项目初始化)
3. [数据准备](#数据准备)
4. [训练调试](#训练调试)
5. [评估和压缩](#评估和压缩)
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
cd /Users/chen/Documents/Web_Scan/HAC-plus-main

# 创建环境（使用 environment.yml）
conda env create --file environment.yml

# 激活环境
conda activate HAC_env

# 验证环境
conda list | grep torch
python -c "import torch; print(torch.__version__)"
python -c "import torch; print(torch.cuda.is_available())"
```

### 3. 编译 CUDA 子模块

```bash
# 解压缩子模块
cd submodules
unzip diff-gaussian-rasterization.zip
unzip gridencoder.zip
unzip simple-knn.zip
unzip arithmetic.zip
cd ..

# 编译子模块（自动编译）
python -c "from setup import *"

# 或手动编译（如果上面失败）
cd submodules/diff-gaussian-rasterization
python setup.py install
cd ../gridencoder
python setup.py install
cd ../simple-knn
python setup.py install
cd ../arithmetic
python setup.py install
cd ../..
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
```

---

## 项目初始化

### 1. 验证项目结构

```bash
# 检查必要的文件结构
ls -la /Users/chen/Documents/Web_Scan/HAC-plus-main/

# 输出应该包含：
# ├── train.py
# ├── arguments/
# ├── scene/
# ├── gaussian_renderer/
# ├── utils/
# ├── submodules/
# └── environment.yml
```

### 2. 创建数据目录

```bash
cd /Users/chen/Documents/Web_Scan/HAC-plus-main

# 创建数据目录
mkdir -p data

# 查看数据目录结构
ls -la data/
```

### 3. 验证 Python 导入

```bash
# 激活环境
conda activate HAC_env

# 测试关键导入
python << 'EOF'
import torch
import numpy as np
from scene import Scene, GaussianModel
from utils.general_utils import safe_state
from arguments import ModelParams, PipelineParams, OptimizationParams
print("✓ 所有导入成功")
print(f"✓ CUDA 可用: {torch.cuda.is_available()}")
print(f"✓ CUDA 设备: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'}")
EOF
```

---

## 数据准备

### 1. 下载数据集

**Synthetic NeRF 数据集**
```bash
# 下载链接：https://drive.google.com/drive/folders/128yBriW1IG_3NJ5Rp7APL5xYV5c2D8Z5

# 创建结构
mkdir -p data/nerf_synthetic
cd data/nerf_synthetic

# 解压后的目录结构应该是：
# data/nerf_synthetic/
# ├── chair/
# ├── drums/
# ├── ficus/
# ├── hotdog/
# ├── lego/
# ├── materials/
# ├── mic/
# └── ship/
```

**Mip-NeRF 360 数据集**
```bash
# 下载链接：https://jonbarron.info/mipnerf360/

mkdir -p data/mipnerf360
# 解压后的目录结构应该是：
# data/mipnerf360/
# ├── bicycle/
# ├── bonsai/
# ├── counter/
# ├── flowers/
# ├── garden/
# ├── kitchen/
# ├── room/
# ├── stump/
# └── treehill/
```

**Blending 数据集**
```bash
# 下载链接：https://dl.fbaipublicfiles.com/nerfstudio/datasets/evimo2_dataset/

mkdir -p data/blending
# 解压后的目录结构应该是：
# data/blending/
# ├── drjohnson/
# └── playroom/
```

### 2. 验证数据格式

```bash
# 检查数据目录完整性
python << 'EOF'
import os
from pathlib import Path

def check_scene_structure(scene_path):
    """检查场景是否有必要的结构"""
    print(f"\n检查: {scene_path}")
    
    images_dir = os.path.join(scene_path, 'images')
    sparse_dir = os.path.join(scene_path, 'sparse', '0')
    
    checks = [
        ("images 目录", os.path.isdir(images_dir)),
        ("sparse/0 目录", os.path.isdir(sparse_dir)),
        ("COLMAP 文件", os.path.exists(os.path.join(sparse_dir, 'cameras.bin')))
    ]
    
    for check_name, result in checks:
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
    
    if os.path.isdir(images_dir):
        img_count = len(os.listdir(images_dir))
        print(f"  - 图像数量: {img_count}")

# 检查示例
check_scene_structure('./data/nerf_synthetic/chair')
EOF
```

---

## 训练调试

### 1. 最小化测试训练

```bash
cd /Users/chen/Documents/Web_Scan/HAC-plus-main

# 激活环境
conda activate HAC_env

# 最小化测试（快速验证设置）
python train.py \
  -s data/nerf_synthetic/chair \
  --eval \
  --lod 0 \
  --voxel_size 0.001 \
  --update_init_factor 4 \
  --iterations 100 \
  -m outputs/test_chair \
  --lmbda 0.001 \
  --mask_lr_final 0.00008 \
  2>&1 | tee test_train.log
```

### 2. 单个场景完整训练

```bash
# Synthetic NeRF - chair 场景（完整配置）
python train.py \
  -s data/nerf_synthetic/chair \
  --eval \
  --lod 0 \
  --voxel_size 0.001 \
  --update_init_factor 4 \
  --iterations 30_000 \
  -m outputs/nerf_synthetic/chair/0.001 \
  --lmbda 0.001 \
  --mask_lr_final 0.00008 \
  2>&1 | tee chair_train.log
```

### 3. 批量训练脚本

```bash
# 创建批量训练脚本
cat > batch_train.sh << 'EOF'
#!/bin/bash

cd /Users/chen/Documents/Web_Scan/HAC-plus-main
conda activate HAC_env

# Synthetic NeRF 数据集
SCENES=('chair' 'drums' 'ficus' 'hotdog' 'lego' 'materials' 'mic' 'ship')
LAMBDA=0.001

for scene in "${SCENES[@]}"; do
    echo "=========================================="
    echo "训练: $scene (lambda=$LAMBDA)"
    echo "=========================================="
    
    mask_lr_final=$(python -c "print(0.00008 * $LAMBDA / 0.001)")
    
    python train.py \
      -s data/nerf_synthetic/$scene \
      --eval \
      --lod 0 \
      --voxel_size 0.001 \
      --update_init_factor 4 \
      --iterations 30_000 \
      -m outputs/nerf_synthetic/$scene/$LAMBDA \
      --lmbda $LAMBDA \
      --mask_lr_final $mask_lr_final \
      2>&1 | tee logs/train_${scene}_${LAMBDA}.log
    
    echo "✓ $scene 训练完成"
done

echo "=========================================="
echo "所有训练完成!"
echo "=========================================="
EOF

chmod +x batch_train.sh
./batch_train.sh
```

### 4. 训练参数说明

```
重要参数解析：

-s, --source_path
  数据集路径
  示例: data/nerf_synthetic/chair

-m, --model_path
  模型保存路径
  示例: outputs/nerf_synthetic/chair

--eval
  启用评估模式

--lod
  细节层级（Level of Detail）
  默认: 0
  较高值可加快训练但降低质量

--voxel_size
  体素大小（控制锚点密度）
  默认: 0.001
  较小值 = 更密集的锚点 = 更高质量但更大的模型

--update_init_factor
  初始更新因子
  默认: 16 (Synthetic), 4 (Real)

--iterations
  训练迭代次数
  示例: 30_000 (Synthetic), 7_000 (Real)

--lmbda
  压缩强度参数
  范围: 0.0005 - 0.003
  较大值 = 更多压缩但质量下降

--mask_lr_final
  掩码学习率最终值
  计算: 0.00008 * lmbda / 0.001
```

### 5. 实时监控训练

```bash
# 方式1: 查看日志文件
tail -f chair_train.log

# 方式2: 监控硬件使用
watch -n 1 nvidia-smi

# 方式3: 查看输出目录
ls -lh outputs/nerf_synthetic/chair/

# 方式4: 检查模型大小变化
watch -n 5 'find outputs/nerf_synthetic/chair -name "*.ply" -exec ls -lh {} \;'
```

---

## 评估和压缩

### 1. 评估模型质量

```bash
cd /Users/chen/Documents/Web_Scan/HAC-plus-main

# 验证评估代码
python << 'EOF'
import os
import json
from pathlib import Path
from utils.image_utils import psnr
import numpy as np
from PIL import Image

def evaluate_scene(output_path, test_images_path):
    """简单的评估函数"""
    print(f"\n评估场景: {output_path}")
    
    renders = sorted(Path(output_path).glob('**/render_*.png'))
    gts = sorted(Path(test_images_path).glob('*.jpg'))
    
    if len(renders) != len(gts):
        print(f"⚠ 警告: 渲染数 ({len(renders)}) ≠ 真值数 ({len(gts)})")
    
    psnrs = []
    for render_path, gt_path in zip(renders[:5], gts[:5]):  # 仅前5张用于快速检查
        render = np.array(Image.open(render_path)).astype(np.float32) / 255.0
        gt = np.array(Image.open(gt_path)).astype(np.float32) / 255.0
        
        if render.shape != gt.shape:
            continue
        
        p = psnr(torch.from_numpy(render).unsqueeze(0), 
                 torch.from_numpy(gt).unsqueeze(0))
        psnrs.append(p.item())
    
    if psnrs:
        print(f"  ✓ 平均 PSNR: {np.mean(psnrs):.2f} dB")
    else:
        print(f"  ✗ 无法计算 PSNR")

# evaluate_scene('./outputs/nerf_synthetic/chair/test', './data/nerf_synthetic/chair/test')
EOF
```

### 2. 压缩和编解码

```bash
# 步骤 1: 生成压缩配置
python << 'EOF'
# 使用 arithmetic 模块进行熵编码
# 参考 utils/entropy_models.py

import torch
from utils.entropy_models import EntropyModel

# 配置压缩参数
compression_config = {
    'quantize_bits': 8,      # 量化位数
    'entropy_coding': True,   # 启用熵编码
    'use_context': True,      # 使用上下文
}

print("压缩配置:")
for key, value in compression_config.items():
    print(f"  {key}: {value}")
EOF

# 步骤 2: 执行压缩
python << 'EOF'
import os
from pathlib import Path
import subprocess

model_path = './outputs/nerf_synthetic/chair/0.001'
ply_file = os.path.join(model_path, 'point_cloud.ply')

# 使用 GPCC 进行点云压缩
compressed_file = ply_file.replace('.ply', '.draco')

if os.path.exists(ply_file):
    print(f"原始文件: {ply_file}")
    orig_size = os.path.getsize(ply_file)
    print(f"原始大小: {orig_size / (1024**2):.2f} MB")
    
    # 使用 tmc3 压缩
    cmd = f"tmc3 --input_file {ply_file} --output_file {compressed_file}"
    print(f"\n执行压缩: {cmd}")
    # os.system(cmd)
    
    # 检查压缩后的大小
    if os.path.exists(compressed_file):
        compressed_size = os.path.getsize(compressed_file)
        print(f"压缩后大小: {compressed_size / (1024**2):.2f} MB")
        compression_ratio = orig_size / compressed_size
        print(f"压缩比: {compression_ratio:.2f}x")
else:
    print(f"✗ 模型文件不存在: {ply_file}")
EOF
```

### 3. 性能报告生成

```bash
# 创建评估脚本
cat > evaluate_all.py << 'EOF'
import os
import json
from pathlib import Path
import subprocess

SCENES = ['chair', 'drums', 'ficus', 'hotdog', 'lego', 'materials', 'mic', 'ship']
LAMBDA = 0.001

results = {}

for scene in SCENES:
    print(f"\n评估: {scene}")
    
    model_path = f"outputs/nerf_synthetic/{scene}/{LAMBDA}"
    
    if os.path.exists(model_path):
        # 查找最佳模型
        ply_files = list(Path(model_path).glob('point_cloud/iteration_*/point_cloud.ply'))
        if ply_files:
            latest_ply = max(ply_files, key=lambda p: int(p.parent.name.split('_')[-1]))
            size_mb = os.path.getsize(latest_ply) / (1024**2)
            print(f"  模型文件: {latest_ply.name}")
            print(f"  模型大小: {size_mb:.2f} MB")
            
            results[scene] = {
                'size_mb': size_mb,
                'model_path': str(latest_ply)
            }

# 生成报告
with open('evaluation_report.json', 'w') as f:
    json.dump(results, f, indent=2)

print("\n✓ 评估报告已保存到 evaluation_report.json")
EOF

python evaluate_all.py
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

# 解决方案
# 1. 重新安装 PyTorch
conda remove torch torchvision torchaudio pytorch-cuda -y
conda install pytorch=2.2 torchvision=0.17 torchaudio=2.2 pytorch-cuda=12.1 -c pytorch -c nvidia

# 2. 检查驱动
nvidia-smi

# 3. 重启容器/环境
conda deactivate
conda activate HAC_env
```

### 问题 2: 子模块编译失败

```bash
# 诊断步骤
cd submodules/diff-gaussian-rasterization
python setup.py build_ext --inplace 2>&1 | tee build.log

# 查看错误信息
tail -100 build.log

# 解决方案：清理并重新编译
cd submodules
for dir in diff-gaussian-rasterization gridencoder simple-knn arithmetic; do
    cd $dir
    rm -rf build dist *.egg-info
    python setup.py install
    cd ..
done
```

### 问题 3: 数据加载错误

```bash
# 诊断步骤
python << 'EOF'
import os
from pathlib import Path

scene_path = './data/nerf_synthetic/chair'

print(f"检查: {scene_path}")
print(f"  存在: {os.path.exists(scene_path)}")
print(f"  images: {os.path.isdir(os.path.join(scene_path, 'images'))}")
print(f"  sparse: {os.path.isdir(os.path.join(scene_path, 'sparse'))}")

images = list(Path(scene_path).glob('images/*'))
print(f"  图像数: {len(images)}")

cameras = os.path.join(scene_path, 'sparse/0/cameras.bin')
print(f"  cameras.bin: {os.path.exists(cameras)}")
EOF

# 解决方案
# 1. 验证数据下载完整性
find data/nerf_synthetic/chair -type f | wc -l

# 2. 重新下载损坏的数据集
# 从官方源重新下载
```

### 问题 4: 内存不足

```bash
# 诊断步骤
nvidia-smi
nvidia-smi --query-gpu=memory.free --format=csv,nounits

# 解决方案 1: 减小 batch size
# 在 train.py 中修改或使用参数

# 解决方案 2: 增加体素大小（减少锚点数）
python train.py -s data/... --voxel_size 0.002  # 从 0.001 增加到 0.002

# 解决方案 3: 使用梯度累积
# 在 OptimizationParams 中配置

# 解决方案 4: 减少迭代次数用于测试
python train.py -s data/... --iterations 5_000
```

### 问题 5: 训练速度太慢

```bash
# 诊断步骤
# 检查 GPU 使用率
watch -n 1 'nvidia-smi | grep -E "Processes|python"'

# 解决方案
# 1. 增加 voxel_size（更粗糙的锚点）
# 2. 启用 LOD（细节层级）
python train.py -s data/... --lod 1 --lod 2

# 3. 减少特征维度
# 在 arguments 中修改 feat_dim 参数

# 4. 使用 torch.compile() 加速
# 在 train.py 中添加
model = torch.compile(model)
```

### 问题 6: 输出文件权限错误

```bash
# 诊断
ls -la outputs/

# 解决方案
chmod -R 755 outputs/
mkdir -p outputs/{nerf_synthetic,mipnerf360,blending}
chmod -R 777 outputs/
```

---

## 性能优化

### 1. GPU 优化配置

```bash
# 创建优化配置文件
cat > optimize_config.py << 'EOF'
# HAC++ GPU 优化配置

OPTIMIZATION_TIPS = {
    "环境变量": {
        "CUDA_LAUNCH_BLOCKING": "0",     # 异步 CUDA 启动
        "OMP_NUM_THREADS": "8",          # OpenMP 线程数
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
    },
    "PyTorch 配置": {
        "torch.backends.cudnn.benchmark": True,    # 启用 cuDNN 自优化
        "torch.backends.cudnn.deterministic": False,
    },
    "训练参数": {
        "批大小": "自适应（根据 GPU 内存）",
        "混合精度": "FP16 + FP32",
        "梯度检查点": "启用（节省显存）",
    }
}

# 使用示例
import torch
torch.cuda.empty_cache()
torch.backends.cudnn.benchmark = True
EOF

python optimize_config.py
```

### 2. 内存优化

```bash
# 清理 GPU 缓存
python << 'EOF'
import torch
import gc

# 清理 Python 垃圾
gc.collect()

# 清理 GPU 缓存
torch.cuda.empty_cache()

# 检查显存
print(f"分配显存: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
print(f"保留显存: {torch.cuda.memory_reserved() / 1024**3:.2f} GB")
EOF
```

### 3. 多 GPU 训练

```bash
# 数据并行训练
CUDA_VISIBLE_DEVICES=0,1,2,3 python train.py \
  -s data/nerf_synthetic/chair \
  -m outputs/chair_multi_gpu \
  --iterations 30_000

# 检查 GPU 使用
nvidia-smi
```

### 4. 混合精度训练

```bash
# 在 train.py 中添加
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

with autocast():
    loss = compute_loss(...)
    
scaler.scale(loss).backward()
scaler.step(optimizer)
scaler.update()
```

---

## 完整工作流示例

### 从零开始的完整流程

```bash
#!/bin/bash

# ========== 1. 环境配置 ==========
echo "步骤 1: 环境配置"
cd /Users/chen/Documents/Web_Scan/HAC-plus-main
conda env create --file environment.yml -y
conda activate HAC_env

# ========== 2. 编译子模块 ==========
echo "步骤 2: 编译子模块"
cd submodules
for dir in */; do
    cd "$dir"
    python setup.py install 2>&1 | tail -5
    cd ..
done
cd ..

# ========== 3. 准备数据 ==========
echo "步骤 3: 准备数据"
mkdir -p data/nerf_synthetic
# 下载数据集...

# ========== 4. 测试训练 ==========
echo "步骤 4: 运行测试训练"
python train.py \
  -s data/nerf_synthetic/chair \
  --iterations 1_000 \
  -m outputs/quick_test \
  2>&1 | head -50

# ========== 5. 完整训练 ==========
echo "步骤 5: 完整训练"
python train.py \
  -s data/nerf_synthetic/chair \
  --eval \
  --iterations 30_000 \
  -m outputs/chair_final \
  --lmbda 0.001

# ========== 6. 评估 ==========
echo "步骤 6: 评估结果"
ls -lh outputs/chair_final/point_cloud/

echo "✓ 完整工作流完成!"
```

### 验证清单

```markdown
## 部署前验证清单

- [ ] conda 环境已创建且激活
- [ ] Python 版本 >= 3.10
- [ ] PyTorch CUDA 可用
- [ ] 子模块编译成功
- [ ] tmc3 已安装并在 PATH 中
- [ ] 数据集已下载并验证
- [ ] 输出目录有写权限
- [ ] 有足够的磁盘空间（>200 GB）
- [ ] GPU 显存 >= 8 GB（推荐 24 GB）
- [ ] 网络连接正常（用于 logging）

## 首次运行检查

1. [ ] 运行最小化测试 (--iterations 100)
2. [ ] 验证渲染输出
3. [ ] 检查日志无错误
4. [ ] 监控 GPU 使用率
5. [ ] 验证模型保存
```

---

## 资源链接

- [HAC++ GitHub 仓库](https://github.com/YihangChen-ee/HAC-plus/)
- [论文 (TPAMI'25)](https://arxiv.org/pdf/2501.12255)
- [项目主页](https://yihangchen-ee.github.io/project_hac++/)
- [MPEG PCC TMC3](https://github.com/MPEGGroup/mpeg-pcc-tmc13)

---

## 快速参考命令

```bash
# 激活环境
conda activate HAC_env

# 单场景训练
python train.py -s data/nerf_synthetic/chair -m outputs/chair --iterations 30_000

# 批量训练
python batch_train.sh

# 监控训练
tail -f outputs/chair/logs/train.log

# 检查 GPU
nvidia-smi

# 清理缓存
rm -rf outputs/*/point_cloud/iteration_*/

# 查看模型大小
du -sh outputs/*/point_cloud/
```

---

**最后更新**: 2025 年 4 月
**文档版本**: 1.0
**HAC++ 版本**: Latest (TPAMI'25)
