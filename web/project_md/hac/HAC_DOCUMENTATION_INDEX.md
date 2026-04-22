# HAC++ 调试文档索引

## 📚 文档列表

### 核心文档

| 文件 | 描述 | 适用场景 |
|------|------|---------|
| [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md) | **完整调试文档** - 详细的分步指南 | 全面了解、完整部署 |
| [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md) | **快速参考卡** - 命令速查表 | 快速查找、日常使用 |

### 可执行脚本

| 脚本 | 功能 | 使用方法 |
|------|------|---------|
| `setup_and_test.sh` | 一键部署 + 快速测试 | `bash HAC-plus-main/setup_and_test.sh` |
| `batch_train.sh` | 批量训练多个场景 | `bash HAC-plus-main/batch_train.sh [dataset] [lambda]` |
| `diagnose.py` | 系统诊断工具 | `python HAC-plus-main/diagnose.py` |

---

## 🚀 快速开始（3步）

### 步骤 1: 一键部署
```bash
cd /Users/chen/Documents/Web_Scan/HAC-plus-main
bash setup_and_test.sh
```

### 步骤 2: 准备数据
```bash
# 下载 Synthetic NeRF 数据集
mkdir -p data/nerf_synthetic
# 解压到 data/nerf_synthetic/chair, data/nerf_synthetic/lego 等
```

### 步骤 3: 运行训练
```bash
# 激活环境
conda activate HAC_env

# 单场景训练
python train.py -s data/nerf_synthetic/chair -m outputs/chair --iterations 30_000

# 或使用批量训练
bash batch_train.sh nerf_synthetic 0.001 30000
```

---

## 📖 使用场景指南

### "我想快速验证安装是否正确"
→ 运行: `python HAC-plus-main/diagnose.py`

### "我想完整了解项目的每一步"
→ 阅读: [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md)

### "我想快速查找某个命令或参数"
→ 查看: [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md)

### "我想自动化部署整个环境"
→ 运行: `bash HAC-plus-main/setup_and_test.sh`

### "我想批量训练多个场景"
→ 运行: `bash HAC-plus-main/batch_train.sh`

### "我的训练出了问题"
→ 按顺序:
1. 运行诊断: `python HAC-plus-main/diagnose.py`
2. 查看错误: [常见问题排查](#常见问题排查)
3. 查看详细指南: [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md)

---

## 🔧 常见问题排查

### CUDA 错误
```bash
# 检查 GPU
nvidia-smi

# 重装 PyTorch
conda remove torch torchvision torchaudio -y
conda install pytorch=2.2 pytorch-cuda=12.1 -c pytorch -c nvidia
```

→ 详见: [HAC_PLUS_DEBUG_GUIDE.md - 问题1](./HAC_PLUS_DEBUG_GUIDE.md#问题-1-cuda-不可用)

### 数据加载失败
```bash
# 检查数据结构
ls -la data/nerf_synthetic/chair/
# 应该包含: images/ 和 sparse/0/
```

→ 详见: [HAC_PLUS_DEBUG_GUIDE.md - 问题3](./HAC_PLUS_DEBUG_GUIDE.md#问题-3-数据加载错误)

### 显存不足
```bash
# 增加 voxel_size 或减少迭代数
python train.py -s data/... --voxel_size 0.002 --iterations 10_000
```

→ 详见: [HAC_PLUS_DEBUG_GUIDE.md - 问题4](./HAC_PLUS_DEBUG_GUIDE.md#问题-4-内存不足)

### 训练太慢
```bash
# 启用 LOD (细节层级)
python train.py -s data/... --lod 1
```

→ 详见: [HAC_PLUS_DEBUG_GUIDE.md - 问题5](./HAC_PLUS_DEBUG_GUIDE.md#问题-5-训练速度太慢)

---

## 📊 典型性能数据

| 数据集 | 场景 | 模型大小 | PSNR | 速度 |
|--------|------|---------|------|------|
| Synthetic NeRF | chair | 11 MB | 33.34 dB | ~4h |
| MipNeRF360 | bicycle | 27.5 MB | 28.34 dB | ~8h |
| Tanks & Temples | train | 28 MB | 27.92 dB | ~12h |

→ 详见: [HAC_QUICK_REFERENCE.md - 性能基准](./HAC_QUICK_REFERENCE.md#性能基准参考值)

---

## 📋 完整工作流

```
1. 环境部署
   └─> bash setup_and_test.sh
   
2. 下载数据
   └─> data/nerf_synthetic/{scene}/
   
3. 运行训练
   ├─> 单场景: python train.py -s data/... -m outputs/...
   └─> 批量: bash batch_train.sh
   
4. 评估结果
   ├─> 查看日志: tail -f logs/*.log
   ├─> 查看模型: ls -lh outputs/*/point_cloud/
   └─> 运行诊断: python diagnose.py
   
5. 压缩编码
   └─> (使用 tmc3)
```

---

## 🎯 训练参数推荐

### 质量优先（最高质量）
```bash
--voxel_size 0.0005 --lmbda 0.0005 --iterations 50_000
```
结果: 高质量但文件大

### 平衡配置（推荐）
```bash
--voxel_size 0.001 --lmbda 0.001 --iterations 30_000
```
结果: 质量与大小的平衡

### 速度优先（快速测试）
```bash
--voxel_size 0.002 --lmbda 0.002 --iterations 10_000
```
结果: 快速训练但质量一般

→ 详见: [HAC_QUICK_REFERENCE.md - 配置预设](./HAC_QUICK_REFERENCE.md#配置预设)

---

## 🆘 获取帮助

### 问题排查步骤
1. **运行诊断**: `python diagnose.py` 检查系统状态
2. **查看快速参考**: [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md#常见错误速查)
3. **搜索完整指南**: [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md#常见问题排查)
4. **查看日志**: `tail -f logs/*.log`

### 关键命令速查
```bash
# 激活环境
conda activate HAC_env

# 系统诊断
python diagnose.py

# 一键部署
bash setup_and_test.sh

# 单场景训练
python train.py -s data/nerf_synthetic/chair -m outputs/test --iterations 100

# 查看帮助
python train.py --help
```

---

## 📚 外部资源

- [HAC++ GitHub](https://github.com/YihangChen-ee/HAC-plus/)
- [论文 (TPAMI'25)](https://arxiv.org/pdf/2501.12255)
- [项目主页](https://yihangchen-ee.github.io/project_hac++/)
- [PyTorch 文档](https://pytorch.org/docs/stable/index.html)
- [CUDA 文档](https://docs.nvidia.com/cuda/)

---

## 📝 文档更新日志

- **2025-04-22** v1.0 - 初版发布
  - 完整调试指南
  - 快速参考卡
  - 自动化脚本
  - 诊断工具

---

## ✅ 准备清单

在开始训练前，请确认：

- [ ] Conda 环境已创建：`conda env list | grep HAC_env`
- [ ] 子模块已编译：运行 `python -c "from scene import Scene"` 无错误
- [ ] 数据已下载：`ls data/nerf_synthetic/chair`
- [ ] GPU 可用：`nvidia-smi` 显示设备信息
- [ ] 输出目录有权限：`mkdir -p outputs/test`
- [ ] 磁盘空间充足：至少 200GB

完成以上检查后，您可以按照 [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md) 的步骤进行训练。

---

**💡 提示**: 收藏此索引文件，方便快速查找所有文档和脚本！

