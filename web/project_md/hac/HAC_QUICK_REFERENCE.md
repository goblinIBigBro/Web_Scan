# HAC++ 快速参考卡

## 关键命令速查

### 环境设置（5分钟）
```bash
cd HAC-plus-main
conda env create --file environment.yml
conda activate HAC_env
cd submodules && (unzip *.zip 2>/dev/null; for d in */; do cd "$d" && python setup.py install > /dev/null 2>&1 && cd ..; done)
cd ..
```

### 快速测试（2分钟）
```bash
python train.py -s data/nerf_synthetic/chair --iterations 100 -m outputs/test 2>&1 | tail -20
```

### 完整训练
```bash
python train.py \
  -s data/nerf_synthetic/chair \
  --eval --lod 0 --voxel_size 0.001 \
  --iterations 30_000 -m outputs/chair \
  --lmbda 0.001 --mask_lr_final 0.00008
```

---

## 参数速查表

| 参数 | 默认值 | 说明 | 调整建议 |
|------|--------|------|---------|
| `-s` | 必需 | 数据源路径 | 指向场景目录 |
| `-m` | 必需 | 模型输出路径 | 指向输出目录 |
| `--iterations` | 30_000 | 训练迭代数 | 测试用 1_000, 完整 30_000 |
| `--voxel_size` | 0.001 | 体素大小 | 质量↑ 速度↓: 0.0005; 质量↓ 速度↑: 0.002 |
| `--lmbda` | 0.001 | 压缩强度 | 压缩多: 0.003; 保质量: 0.0005 |
| `--lod` | 0 | 细节层级 | 0(最高质量) 到 2 |
| `--eval` | 不启用 | 启用评估模式 | 训练时启用 |
| `--mask_lr_final` | 0.0001 | 掩码学习率 | 计算: 0.00008 * lambda / 0.001 |

---

## 常见错误速查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `CUDA not available` | GPU 驱动问题 | `nvidia-smi` 检查; 重装 PyTorch |
| `Failed to import scene` | 数据路径错误 | 检查 `images/` 和 `sparse/0/` 是否存在 |
| `Out of memory` | 显存不足 | 增大 `--voxel_size` (0.002) 或减少迭代数 |
| `No module named 'lpips'` | 依赖缺失 | `pip install lpips` |
| `tmc3 not found` | GPCC 未安装 | 编译 MPEG PCC 并添加到 PATH |

---

## GPU 显存需求

| 场景 | 最小显存 | 推荐显存 | 训练时间 |
|------|---------|--------|---------|
| Synthetic (chair) | 8 GB | 24 GB | ~4 小时 |
| Real (bicycle) | 16 GB | 48 GB | ~8 小时 |
| 高分辨率 | 24 GB | 80 GB | ~12 小时 |

---

## 输出文件结构

```
outputs/
└── chair/
    └── 0.001/
        ├── chkpnt0.pth          # 检查点
        ├── point_cloud/
        │   └── iteration_*/
        │       └── point_cloud.ply  # 最终模型
        ├── logs/
        │   ├── train.log
        │   ├── metrics.json
        │   └── config.json
        └── test/                # 评估结果
            ├── render_000.png
            ├── render_001.png
            └── metrics.txt
```

---

## 性能基准（参考值）

| 数据集 | 场景 | 模型大小 | PSNR | 压缩比 |
|--------|------|---------|------|--------|
| Synthetic NeRF | chair | 11.02 MB | 33.34 dB | 122.5x |
| MipNeRF360 | bicycle | 27.5 MB | 28.34 dB | 31x |
| Tanks & Temples | train | 28.0 MB | 27.92 dB | 17x |

---

## 调试技巧

### 1. 查看实时进度
```bash
tail -f outputs/chair/logs/train.log | grep -E "Iteration|PSNR|Loss"
```

### 2. 监控 GPU
```bash
watch -n 1 nvidia-smi
```

### 3. 比较模型大小
```bash
du -sh outputs/*/point_cloud/iteration_*/
```

### 4. 找到最佳模型
```bash
ls -tSr outputs/*/point_cloud/iteration_*/point_cloud.ply | head -1
```

### 5. 批量清理
```bash
find outputs -name "*.png" -delete  # 删除渲染
find outputs -name "*.jpg" -delete  # 删除中间结果
```

---

## 配置预设

### 质量优先
```bash
--voxel_size 0.0005 --lmbda 0.0005 --iterations 50_000
```

### 速度优先
```bash
--voxel_size 0.002 --lmbda 0.002 --iterations 10_000
```

### 平衡配置
```bash
--voxel_size 0.001 --lmbda 0.001 --iterations 30_000
```

---

## 数据集下载链接

- **Synthetic NeRF**: https://drive.google.com/drive/folders/128yBriW1IG_3NJ5Rp7APL5xYV5c2D8Z5
- **MipNeRF360**: https://jonbarron.info/mipnerf360/
- **Tanks & Temples**: https://www.tanksandtemples.org/
- **Deep Blending**: https://github.com/DeepLearningVision/BlendedNeRF

---

## 一键部署脚本

```bash
# 保存为 setup.sh，运行: bash setup.sh
#!/bin/bash
set -e

echo "🔧 HAC++ 一键部署"
conda env create --file environment.yml -y
conda activate HAC_env

echo "📦 编译子模块..."
cd submodules
for dir in diff-gaussian-rasterization gridencoder simple-knn arithmetic; do
    [[ -f "$dir/setup.py" ]] && (cd "$dir" && python setup.py install -q && cd .. && echo "  ✓ $dir")
done
cd ..

echo "📁 创建目录..."
mkdir -p data outputs logs

echo "✓ 部署完成! 运行: python train.py -s data/nerf_synthetic/chair -m outputs/test"
```

---

**提示**: 保存此文件为 `HAC_QUICK_REFERENCE.md`，在需要时快速查阅！
