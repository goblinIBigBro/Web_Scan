# FCGS 文档索引

## 📚 文档列表

### 核心文档

| 文件 | 描述 | 适用场景 |
|------|------|---------|
| [FCGS_DEBUG_GUIDE.md](./FCGS_DEBUG_GUIDE.md) | **完整调试文档** - 详细的分步指南 | 全面了解、完整部署 |
| [FCGS_QUICK_REFERENCE.md](./FCGS_QUICK_REFERENCE.md) | **快速参考卡** - 命令速查表 | 快速查找、日常使用 |

### 可执行脚本

| 脚本 | 功能 | 使用方法 |
|------|------|---------|
| `setup_and_test.sh` | 一键部署 + 快速测试 | `bash FCGS-main/setup_and_test.sh` |
| `batch_compress.sh` | 批量压缩 PLY 文件 | `bash FCGS-main/batch_compress.sh [input_dir] [lambda]` |
| `diagnose.py` | 系统诊断工具 | `python FCGS-main/diagnose.py` |

---

## 🚀 快速开始（3步）

### 步骤 1: 一键部署
```bash
cd /Users/chen/Documents/Web_Scan/FCGS-main
bash setup_and_test.sh
```

### 步骤 2: 准备数据
```bash
# 将 .ply 文件放到数据目录
mkdir -p data/ply_files
cp your_point_cloud.ply data/ply_files/
```

### 步骤 3: 运行压缩
```bash
# 激活环境
conda activate FCGS_env

# 单文件压缩
python encode_single_scene.py \
  --lmd 4e-4 \
  --ply_path_from data/ply_files/point_cloud.ply \
  --bit_path_to outputs/compressed \
  --determ 1

# 或批量压缩
bash batch_compress.sh data/ply_files 4e-4
```

---

## 📖 使用场景指南

### "我想快速验证安装是否正确"
→ 运行: `python FCGS-main/diagnose.py`

### "我想完整了解项目的每一步"
→ 阅读: [FCGS_DEBUG_GUIDE.md](./FCGS_DEBUG_GUIDE.md)

### "我想快速查找某个命令或参数"
→ 查看: [FCGS_QUICK_REFERENCE.md](./FCGS_QUICK_REFERENCE.md)

### "我想自动化部署整个环境"
→ 运行: `bash FCGS-main/setup_and_test.sh`

### "我想批量压缩多个 PLY 文件"
→ 运行: `bash FCGS-main/batch_compress.sh`

### "我的压缩出了问题"
→ 按顺序:
1. 运行诊断: `python FCGS-main/diagnose.py`
2. 检查 PLY 文件: `python FCGS-main/diagnose.py --check-ply /path/to/file.ply`
3. 查看错误: [常见问题排查](#常见问题排查)
4. 查看详细指南: [FCGS_DEBUG_GUIDE.md](./FCGS_DEBUG_GUIDE.md)

---

## 🔧 常见问题排查

### CUDA 错误
```bash
# 检查 GPU
nvidia-smi

# 重装 PyTorch
conda remove torch torchvision torchaudio -y
conda install pytorch=2.2 pytorch-cuda=11.8 -c pytorch -c nvidia
```

→ 详见: [FCGS_DEBUG_GUIDE.md - 问题1](./FCGS_DEBUG_GUIDE.md#问题-1-cuda-不可用)

### PLY 文件加载失败
```bash
# 验证 PLY 文件
python diagnose.py --check-ply /path/to/file.ply

# 检查文件格式
python -c "from plyfile import PlyFile; PlyFile('/path/to/file.ply')"
```

→ 详见: [FCGS_DEBUG_GUIDE.md - 问题2](./FCGS_DEBUG_GUIDE.md#问题-2-ply-文件加载失败)

### 内存不足
```bash
# 清理 GPU 缓存
python -c "import torch; torch.cuda.empty_cache()"

# 对于大型点云，FCGS 通常需要 > 8GB 显存
```

→ 详见: [FCGS_DEBUG_GUIDE.md - 问题4](./FCGS_DEBUG_GUIDE.md#问题-4-内存不足)

---

## 📊 典型性能数据

| 点云规模 | 压缩时间 | 解压时间 | 压缩比（@λ=4e-4） |
|---------|---------|---------|------------------|
| 100K 点 | <1s | <1s | 10x |
| 1M 点 | 1-2s | <1s | 8x |
| 10M 点 | 2-3s | 1s | 6x |

**FCGS 的关键优势**: 快速无需优化的压缩，比其他方法快 10 倍！

→ 详见: [FCGS_QUICK_REFERENCE.md - 性能基准](./FCGS_QUICK_REFERENCE.md#性能基准参考值)

---

## 📋 完整工作流

```
1. 环境部署
   └─> bash setup_and_test.sh
   
2. 准备 PLY 文件
   └─> data/ply_files/{scene}.ply
   
3. 运行压缩
   ├─> 单文件: python encode_single_scene.py ...
   └─> 批量: bash batch_compress.sh
   
4. 评估结果
   ├─> 查看日志: tail -f logs/*.log
   ├─> 检查大小: ls -lh outputs/*/
   └─> 验证质量: python decode_single_scene_validate.py ...
   
5. 解压验证
   ├─> 解压: python decode_single_scene.py ...
   └─> 评估: python decode_single_scene_validate.py ...
```

---

## 🎯 Lambda 参数推荐

| 使用场景 | Lambda | 特点 |
|---------|--------|------|
| 最高质量 | 1e-4 | 高保真，文件大 |
| **推荐** | **4e-4** | **平衡配置** |
| 高压缩 | 8e-4 | 中等质量，文件小 |
| 最大压缩 | 16e-4 | 最小文件，质量一般 |

---

## 🆘 获取帮助

### 问题排查步骤
1. **运行诊断**: `python diagnose.py` 检查系统状态
2. **检查 PLY**: `python diagnose.py --check-ply /path/to/file.ply`
3. **查看快速参考**: [FCGS_QUICK_REFERENCE.md](./FCGS_QUICK_REFERENCE.md#常见错误速查)
4. **搜索完整指南**: [FCGS_DEBUG_GUIDE.md](./FCGS_DEBUG_GUIDE.md#常见问题排查)
5. **查看日志**: `tail -f logs/*.log`

### 关键命令速查
```bash
# 激活环境
conda activate FCGS_env

# 系统诊断
python diagnose.py

# 检查 PLY 文件
python diagnose.py --check-ply file.ply

# 一键部署
bash setup_and_test.sh

# 单文件压缩
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output --determ 1

# 批量压缩
bash batch_compress.sh data/ply_files 4e-4

# 解压缩
python decode_single_scene.py --lmd 4e-4 --bit_path_from output --ply_path_to restored.ply

# 验证质量
python decode_single_scene_validate.py --lmd 4e-4 --bit_path_from output --ply_path_to restored.ply --source_path images
```

---

## 📚 外部资源

- [FCGS GitHub](https://github.com/YihangChen-ee/FCGS/)
- [论文 (ICLR'25)](https://openreview.net/pdf?id=DCandSZ2F1)
- [Arxiv](https://arxiv.org/pdf/2410.08017)
- [项目主页](https://yihangchen-ee.github.io/project_fcgs/)
- [DL3DV-GS-960P 数据集](https://huggingface.co/datasets/DL3DV/DL3DV-GS-960P)
- [PyTorch 文档](https://pytorch.org/docs/stable/index.html)

---

## 📝 文档更新日志

- **2025-04-22** v1.0 - 初版发布
  - 完整调试指南
  - 快速参考卡
  - 自动化脚本
  - 诊断工具

---

## ✅ 准备清单

在开始使用前，请确认：

- [ ] Conda 环境已创建：`conda env list | grep FCGS_env`
- [ ] PyTorch CUDA 可用：运行诊断无错误
- [ ] 子模块已更新：`git submodule update --init --recursive`
- [ ] PLY 文件已准备：`ls data/ply_files/*.ply`
- [ ] 输出目录有权限：`mkdir -p outputs`
- [ ] 磁盘空间充足：至少 50GB（用于中等大小点云）

完成以上检查后，您可以按照 [FCGS_DEBUG_GUIDE.md](./FCGS_DEBUG_GUIDE.md) 的步骤进行压缩。

---

**💡 提示**: 这套文档系统专为 FCGS 无需优化的快速压缩设计。与 HAC++ 等其他方法不同，FCGS 只需一次前馈传递，无需迭代优化！

