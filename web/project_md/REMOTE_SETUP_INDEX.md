# 远程 SSH 环境配置 — 快速导航

> **最后更新**：2026 年 4 月  
> **适用版本**：Web_Scan 所有算法（包含 8 个 3D Gaussian Splatting 项目）  
> **核心特性**：一键环境验证、清晰的参数配置指南、完整的故障排除

---

## 🎯 快速选择：我应该读哪份文档？

### 情景 1: 使用 Gaussian Splatting Lightning、HAC-plus、FCGS、ContextGS、CompGS、reduced-3dgs 或 MEGS-2

👉 **阅读**：[REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)

**特点**：
- Python 3.10 + PyTorch 2.2.* + CUDA 12.1/11.8
- 支持命令行参数直接传入
- 包含环境检测脚本

**快速命令**：
```bash
# HAC-plus 训练示例
python train.py -s /data/scene -m /output/result --iterations 30000 --eval

# Gaussian Splatting Lightning 训练示例
python main.py fit --data.path /data/scene --output /output/result --logger none

# FCGS 压缩示例
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output

# ContextGS 训练示例
python train.py -s /data/scene -m /output/result --iterations 30000 --eval

# reduced-3dgs 训练示例
python train.py -s /data/scene -m /output/result --iterations 30000 --eval

# CompGS 训练示例（YAML 配置）
python Train.py --config Configs/my_training.yaml

# MEGS-2 训练示例
python train.py -s /data/scene -m /output/result --iterations 30000 --eval --imp_metric indoor
```

---

### 情景 2: 使用 Scaffold-GS

👉 **阅读**：[REMOTE_SETUP_GUIDE_OLD.md](REMOTE_SETUP_GUIDE_OLD.md)

**特点**：
- Python 3.7.13 + PyTorch 1.12.1 + CUDA 11.6
- 使用命令行参数

**快速命令**：
```bash
# Scaffold-GS 训练示例
python train.py -s /data/scene -m /output/result --iterations 30000 --eval
```

---

## 📋 算法速查表

| 算法 | 文档 | 环境 | Python | PyTorch | CUDA | 参数方式 |
|------|------|------|--------|---------|------|---------|
| **Gaussian Splatting Lightning** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | 命令行 |
| **HAC-plus** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | 命令行 |
| **FCGS** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 11.8 | 命令行 |
| **ContextGS** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | 命令行 |
| **reduced-3dgs** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | 命令行 |
| **CompGS** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | YAML 配置 |
| **MEGS-2** | [NEW](REMOTE_SETUP_GUIDE_NEW.md) | 新版 | 3.10 | 2.2.* | 12.1 | 命令行 |
| **Scaffold-GS** | [OLD](REMOTE_SETUP_GUIDE_OLD.md) | 旧版 | 3.7.13 | 1.12.1 | 11.6 | 命令行 |

---

## 🔍 环境验证（一键检查）

### 自动检测并验证

在远程主机上运行：

```bash
# 下载验证脚本（如果尚未有）
curl -o remote_verify_setup.sh https://your_repo/web/tools/remote_verify_setup.sh

# 自动检测环境版本并验证
bash remote_verify_setup.sh

# 或手动指定版本
bash remote_verify_setup.sh new   # 新版（Python 3.10 + PyTorch 2.2）
bash remote_verify_setup.sh contextgs   # ContextGS（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
bash remote_verify_setup.sh compgs   # CompGS（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
bash remote_verify_setup.sh reduced-3dgs   # reduced-3dgs（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
bash remote_verify_setup.sh megs2   # MEGS-2（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
bash remote_verify_setup.sh gaussian-splatting-lightning   # GSL（Python 3.10 + PyTorch 2.2 + CUDA 12.1 + RTX 4090）
bash remote_verify_setup.sh old   # 旧版（Python 3.7 + PyTorch 1.12）
```

**验证成功标志**：
```
✓ 环境配置正确，可以开始训练
```

---

## 📖 文档导航

### 详细配置指南

| 文档 | 适用范围 | 内容 |
|------|---------|------|
| [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md) | Gaussian Splatting Lightning、HAC-plus、FCGS、ContextGS、CompGS、reduced-3dgs、MEGS-2 | 环境部署、参数配置、训练启动、故障排除 |
| [REMOTE_SETUP_GUIDE_OLD.md](REMOTE_SETUP_GUIDE_OLD.md) | Scaffold-GS | 环境部署、参数配置、训练启动、故障排除 |

### 工具和脚本

| 工具 | 位置 | 用途 |
|------|------|------|
| `remote_verify_setup.sh` | [web/tools/](../tools/) | 一键环境验证脚本 |
| `diagnose.py` | 各算法目录 | 项目诊断工具（部分算法提供） |

---

## 🚀 典型工作流

### 新建远程服务器配置（第一次）

```
1. SSH 连接到远程主机
   ssh user@host -p port

2. 克隆/复制项目代码
   git clone ... 或 cp -r ...

3. 根据算法类型选择部署：

   【新版算法】
   cd HAC-plus-main
   conda env create --file environment.yml
   conda activate HAC_env
   git submodule update --init --recursive

   【ContextGS】
   cd ContextGS-main
   conda env create --file environment.yml
   conda activate contextgs
   export CUDA_HOME=/usr/local/cuda-12.1
   export TORCH_CUDA_ARCH_LIST=8.9

   【reduced-3dgs】
   cd reduced-3dgs-main
   conda env create --file environment.yml
   conda activate gaussian_splatting
   export CUDA_HOME=/usr/local/cuda-12.1
   export TORCH_CUDA_ARCH_LIST=8.9

   【MEGS-2】
   cd MEGS-2-main
   conda env create --file environment.yml
   conda activate MEGS2
   export CUDA_HOME=/usr/local/cuda-12.1
   export TORCH_CUDA_ARCH_LIST=8.9

   【Gaussian Splatting Lightning】
   cd gaussian-splatting-lightning-main
   conda env create --file environment.yml
   conda activate gspl
   export CUDA_HOME=/usr/local/cuda-12.1
   export TORCH_CUDA_ARCH_LIST=8.9

   【旧版算法】
   cd Scaffold-GS-main
   conda env create --file environment.yml
   conda activate scaffold_gs

4. 验证环境
   bash remote_verify_setup.sh

5. 在本地 Web_Scan 应用中配置远程服务器
   - Remote Host: host
   - Remote Port: port
   - Remote Activate Command: source ~/.bashrc && conda activate HAC_env
   - ...
```

---

## 📝 快速参数参考

### 新版算法（HAC-plus）

```bash
# 快速测试
python train.py -s /workspace/data/chair -m /output/test --iterations 100

# 标准训练
python train.py -s /workspace/data/scene -m /output/full \
  --iterations 30_000 --eval --voxel_size 0.001 --lmbda 0.001
```

**关键参数**：
- `-s` / `--source_path`：数据集路径
- `-m` / `--model_path`：输出目录
- `--iterations`：训练迭代数（默认 30000）
- `--voxel_size`：体素大小（控制质量和速度）
- `--lmbda`：压缩强度

---

### 新版算法（FCGS）

```bash
# 平衡模式
python encode_single_scene.py --lmd 4e-4 \
  --ply_path_from input.ply --bit_path_to output --determ 1

# 高质量模式
python encode_single_scene.py --lmd 1e-4 \
  --ply_path_from input.ply --bit_path_to output_hq --determ 1
```

**关键参数**：
- `--lmd`：压缩强度（1e-4=高质量, 4e-4=平衡, 16e-4=高压缩）
- `--ply_path_from`：输入 PLY 文件
- `--bit_path_to`：输出比特流目录
- `--determ`：确定性模式（1=启用）

---

### CompGS（新版环境 + YAML 配置）

```yaml
# 编辑 Configs/my_training.yaml
dataset:
  root: /workspace/data/scene
  image_folder: images

training:
  max_iterations: 30000
  save_directory: /output/scene
  save_interval: 10000
  lambda_weight: 0.001
```

```bash
# 启动训练
python Train.py --config Configs/my_training.yaml
```

---

### Gaussian Splatting Lightning / ContextGS / reduced-3dgs / MEGS-2 / 旧版命令行算法

```bash
# Gaussian Splatting Lightning 基础训练（Python 3.10 + PyTorch 2.2 + CUDA 12.1）
python main.py fit --data.path /workspace/data/scene --output /output/result --logger none

# ContextGS 基础训练（Python 3.10 + PyTorch 2.2 + CUDA 12.1）
python train.py -s /workspace/data/scene -m /output/result --eval

# reduced-3dgs 基础训练（Python 3.10 + PyTorch 2.2 + CUDA 12.1）
python train.py -s /workspace/data/scene -m /output/result --eval

# MEGS-2 基础训练（Python 3.10 + PyTorch 2.2 + CUDA 12.1）
python train.py -s /workspace/data/scene -m /output/result \
  --iterations 30000 --eval --test_iterations 7000 --imp_metric indoor

# Scaffold-GS 仍使用旧版环境，但参数形式类似
python train.py -s /workspace/data/scene -m /output/result --iterations 30000 --eval
```

---

## ✅ SSH 前置检查清单

**在配置远程服务器前，请确认**：

- [ ] SSH 连接可用：`ssh user@host -p port echo "OK"`
- [ ] GPU 驱动正常：`nvidia-smi` 显示 GPU
- [ ] 磁盘空间充足：`df -h` 显示 ≥ 200GB
- [ ] Conda 已安装：`conda --version`
- [ ] 项目代码已获取（克隆或复制）

**环境检查**：
- [ ] ContextGS 运行 `bash remote_verify_setup.sh contextgs`
- [ ] CompGS 运行 `bash remote_verify_setup.sh compgs`
- [ ] reduced-3dgs 运行 `bash remote_verify_setup.sh reduced-3dgs`
- [ ] MEGS-2 运行 `bash remote_verify_setup.sh megs2`
- [ ] Gaussian Splatting Lightning 运行 `bash remote_verify_setup.sh gaussian-splatting-lightning`
- [ ] HAC-plus/FCGS 运行 `bash remote_verify_setup.sh new`
- [ ] 旧版算法运行 `bash remote_verify_setup.sh old`
- [ ] 所有检查项显示 ✓ PASS

---

## 🆘 常见问题

### Q: 我不确定应该使用哪份文档

**A**: 查看 [算法速查表](#-算法速查表)。如果你使用 **Gaussian Splatting Lightning、HAC-plus、FCGS、ContextGS、CompGS、reduced-3dgs 或 MEGS-2**，选择 **NEW** 文档。Scaffold-GS 选择 **OLD** 文档。

---

### Q: 我的远程服务器已经有 Python 3.7，能否安装新版（Python 3.10）？

**A**: 可以。Conda 支持多个并行的 Python 环境。你可以：
```bash
# 为新版算法创建独立环境
conda create -n HAC_env python=3.10 -y
conda activate HAC_env
# 然后按照 REMOTE_SETUP_GUIDE_NEW.md 继续安装
```

---

### Q: CompGS 和其他算法有什么区别？

**A**: 
- **CompGS**：已经迁移到新版 Python 3.10 / CUDA 12.1 环境，但参数仍通过修改 YAML 配置文件传入
- **多数其他新版算法**：参数通过命令行传入

详见 [REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md) 的 CompGS 部分。

---

### Q: 验证脚本显示"CUDA 版本不匹配"怎么办？

**A**: 参考对应文档的 [故障排除](#) 部分，或运行：
```bash
python -c "import torch; print(torch.version.cuda)"
nvidia-smi  # 查看驱动支持的最高 CUDA 版本
```

详细解决方案见各文档的 **Q2: RuntimeError: CUDA driver version is insufficient** 部分。

---

## 📞 文档和支持

- **新版算法指南**：[REMOTE_SETUP_GUIDE_NEW.md](REMOTE_SETUP_GUIDE_NEW.md)
- **旧版算法指南**：[REMOTE_SETUP_GUIDE_OLD.md](REMOTE_SETUP_GUIDE_OLD.md)
- **验证脚本**：[web/tools/remote_verify_setup.sh](../tools/remote_verify_setup.sh)

---

## 📚 关联文档

- **Web 应用训练手册**：[WEB_TRAINING_MANUAL_ZH.md](../WEB_TRAINING_MANUAL_ZH.md)
- **HAC-plus 快速参考**：[project_md/hac/HAC_QUICK_REFERENCE.md](hac/HAC_QUICK_REFERENCE.md)
- **FCGS 快速参考**：[project_md/fcgs/FCGS_QUICK_REFERENCE.md](fcgs/FCGS_QUICK_REFERENCE.md)

---

**祝你配置顺利！有问题？参考对应文档的故障排除章节。** 🚀
