# Web_Scan - 3D高斯溅射算法集成平台

![Python](https://img.shields.io/badge/Python-3.7.13+-blue.svg) ![PyTorch](https://img.shields.io/badge/PyTorch-1.12.1%2B-red.svg) ![License](https://img.shields.io/badge/License-MIT-green.svg)

## 📋 项目概述

**Web_Scan** 是一个集成了**10种先进3D高斯溅射(3D Gaussian Splatting)算法**的web平台，提供统一的训练、可视化、评估和压缩工作流。

### 核心特性

- 🚀 **多算法集成** - 支持10个主流算法，通过能力驱动的适配器模式自动适配
- 🌐 **Web界面** - 零依赖网页操作，支持图片上传、实时预览、交互式渲染
- 🔗 **远程SSH训练** - 一键下发远程训练任务，自动结果回传
- ⚡ **自动数据处理** - 内置COLMAP SfM处理，支持无头GPU自动化
- 📊 **实时监控** - 任务状态、训练指标、性能统计实时显示
- 📦 **模型快速加载** - 支持PLY快速加载和场景包导出

---

## 🧬 集成算法

| 算法 | 功能 | 性质 |
|------|------|------|
| **HAC++** | 增强型上下文压缩，100×压缩目标 | 新版（Python 3.10 + PyTorch 2.2） |
| **FCGS** | 秒级无优化快速压缩 | 新版 |
| **ContextGS** | 锚点上下文模型，15×压缩 | 新/旧版均支持 |
| **CompGS** | 率失真优化压缩 | 新/旧版均支持 |
| **GaussianPro** | 渐进传播策略，处理纹理缺失场景 | 新版 |
| **GSLightning** | PyTorch Lightning多GPU/多节点实现 | 新版 |
| **MEGS-2** | 内存高效溅射，100×压缩 | 新版 |
| **reduced-3dgs** | 内存足迹缩减，27×压缩 + 1.7×加速 | 新/旧版均支持 |
| **Scaffold-GS** | 结构化大规模场景渲染 | 新/旧版均支持 |
| **AtomGS** | 原子化高斯分解 | 新版 |

---

## 📁 项目结构

```
Web_Scan/
├── web/                                  # Web应用核心代码
│   ├── index.html                       # 主页面入口
│   ├── styles.css                       # 样式表
│   ├── src/                             # 前端源码
│   │   ├── core/app.js                 # 应用状态机 + 主逻辑
│   │   ├── api/server-client.js        # API客户端
│   │   ├── ui/control-panel.js         # 控制面板
│   │   ├── loaders/scene-manifest-loader.js  # 场景加载
│   │   └── renderers/                  # 多渲染器支持
│   ├── server/                          # 后端API服务
│   │   ├── api_server.py               # Flask API服务器
│   │   ├── adapter_registry.py         # 算法适配器注册
│   │   └── remote_executor.py          # 远程SSH执行引擎
│   ├── tools/                           # 工具脚本集
│   │   ├── export_scene_package.py     # 导出场景包
│   │   ├── materialize_model_output.py # 物化输出模型
│   │   ├── remote_verify_setup.sh      # 远程环境验证
│   │   └── test_*.py                   # 单元测试
│   ├── config/                          # 配置文件
│   ├── scenes/                          # 场景示例库
│   ├── viewers/                         # 渲染器实现
│   ├── project_md/                      # 远程配置指南
│   │   ├── REMOTE_SETUP_INDEX.md       # 配置导航入口
│   │   ├── REMOTE_SETUP_GUIDE_NEW.md   # 新版(Python 3.10+)
│   │   └── REMOTE_SETUP_GUIDE_OLD.md   # 旧版(Python 3.7.13)
│   ├── WEB_TRAINING_MANUAL_ZH.md       # 中文完整操作手册
│   ├── WEB_TRAINING_MANUAL_EN.md       # 英文操作手册
│   └── README.md                        # Web应用快速开始
│
├── AtomGS-main/                         # AtomGS算法实现
├── CompGS-main/                         # CompGS算法实现
├── ContextGS-main/                      # ContextGS算法实现
├── FCGS-main/                           # FCGS算法实现
├── GaussianPro-version1.0/              # GaussianPro算法实现
├── HAC-plus-main/                       # HAC++算法实现（推荐新手）
├── gaussian-splatting-lightning-main/   # GSLightning实现
├── MEGS-2-main/                         # MEGS-2算法实现
├── reduced-3dgs-main/                   # reduced-3dgs实现
├── Scaffold-GS-main/                    # Scaffold-GS实现
│
└── 文档根目录/
    ├── WEB_TRAINING_MANUAL_ZH.md        # 操作手册（中文）
    ├── PLY_QUICK_LOAD_GUIDE.md          # PLY快速加载指南
    ├── change.md                        # 更新日志
    └── REMOTE_SETUP_IMPLEMENTATION_REPORT.md  # 配置完成报告
```

---

## 🚀 快速开始（5分钟）

### 1️⃣ 前置要求
- **Python 3.8+**（推荐 3.10+ 或 3.7.13）
- **PyTorch 1.12.1+**（推荐 2.2+）
- **CUDA 11.8+**（本地训练）或 **SSH访问权限**（远程训练）

### 2️⃣ 安装依赖
```bash
# 克隆仓库
git clone <repository-url>
cd Web_Scan

# 安装Python依赖
python3 -m pip install paramiko flask numpy

# （可选）本地训练需要安装PyTorch
python3 -m pip install torch torchvision -f https://download.pytorch.org/whl/cu118/torch_stable.html
```

### 3️⃣ 启动服务器
```bash
# 启动Web API服务（默认: 127.0.0.1:8080）
python3 web/server/api_server.py --host 127.0.0.1 --port 8080

# 输出示例:
# Starting API server on http://127.0.0.1:8080
# Press CTRL+C to quit
```

### 4️⃣ 打开Web界面
在浏览器中访问：
```
http://127.0.0.1:8080/web/
```

### 5️⃣ 第一次上传测试
1. 选择 **Data → New Image Upload**
2. 拖放或选择 3-5 张照片
3. 选择算法（如 **HAC++**）和操作模板（如 **Render**）
4. 点击 **Remote Precheck** 测试连接
5. 点击 **Train** 启动训练

---

## 📖 完整操作手册

### 五步工作流

```
┌─────────────────────────────────────────────────────────────────┐
│ 第1步：数据准备                                                  │
│ ├─ 选择数据来源：新上传图片 或 复用远程数据集                  │
│ ├─ 上传照片到本地服务（Web拖放或选择文件）                     │
│ └─ 配置COLMAP处理（自动/手动/跳过）                            │
│                                                                   │
│ 第2步：自动物化                                                 │
│ ├─ 服务端自动运行COLMAP SfM处理                                │
│ ├─ 生成稀疏点云和相机参数                                       │
│ └─ 创建训练workspace，准备上传至远程                           │
│                                                                   │
│ 第3步：远程下发训练                                             │
│ ├─ 上传workspace至远程服务器（SFTP）                           │
│ ├─ SSH连接远程服务器，下发训练命令                             │
│ ├─ 监控远程任务执行（日志、进度、指标）                        │
│ └─ 支持任务暂停/继续/取消                                      │
│                                                                   │
│ 第4步：结果回传                                                 │
│ ├─ 训练完成后自动从远程下载输出                                │
│ ├─ 解析和物化模型文件（PLY格式）                               │
│ └─ 结果存储至本地 output_dir                                   │
│                                                                   │
│ 第5步：交互式渲染                                               │
│ ├─ 前端轮询任务状态，自动加载结果                              │
│ ├─ PLY查看器实时交互式渲染                                      │
│ ├─ 显示FPS、顶点数、迭代进度                                   │
│ └─ 导出场景包供其他应用使用                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 📚 详细文档指南

| 需求 | 文档 | 位置 |
|------|------|------|
| **第一次使用** | WEB_TRAINING_MANUAL_ZH.md | [web/](web/WEB_TRAINING_MANUAL_ZH.md) |
| **远程环境配置** | REMOTE_SETUP_INDEX.md | [web/project_md/](web/project_md/REMOTE_SETUP_INDEX.md) |
| **Python 3.10 + PyTorch 2.2** | REMOTE_SETUP_GUIDE_NEW.md | [web/project_md/](web/project_md/REMOTE_SETUP_GUIDE_NEW.md) |
| **Python 3.7.13 + PyTorch 1.12.1** | REMOTE_SETUP_GUIDE_OLD.md | [web/project_md/](web/project_md/REMOTE_SETUP_GUIDE_OLD.md) |
| **快速加载PLY** | PLY_QUICK_LOAD_GUIDE.md | [根目录](PLY_QUICK_LOAD_GUIDE.md) |
| **英文版手册** | WEB_TRAINING_MANUAL_EN.md | [web/](web/WEB_TRAINING_MANUAL_EN.md) |

---

## 🔧 核心功能详解

### 1. 数据上传与COLMAP处理

**本地工作流**
```bash
# 用户上传图片 → 服务端自动：
1. 创建workspace目录
2. 运行COLMAP feature_extractor（提特征点）
3. 运行COLMAP sequential_matcher（匹配特征）
4. 运行COLMAP mapper（SfM重建）
5. 运行COLMAP image_undistorter（去畸变）
6. 生成稀疏点云供训练使用
```

**远程自动COLMAP**
```bash
# 新上传数据 + 自动COLMAP 时，远程执行：
xvfb-run -a image_undistorter 
# （无显示器环境，使用Xvfb虚拟显示 + VirtualGL加速）

# 复用已有远程数据集时：
# 跳过COLMAP，直接使用已有sparse/undistorted
```

### 2. 远程SSH训练

**支持的操作**
- **Render** - 训练+渲染（输出PLY）
- **Compress** - 训练+压缩（有些算法）
- **Decompress** - 解压缩模型
- **Evaluate** - 评估模型质量（PSNR/SSIM/LPIPS）
- 自定义operation（通过adapter注册）

**SSH认证**
```python
# 当前支持用户名/密码认证
ssh_client = paramiko.SSHClient()
ssh_client.connect(
    hostname=host,
    port=port,
    username=user,
    password=passwd
)
```

### 3. 实时任务监控

**前端轮询周期**
- 初始：1秒轮询
- 正在运行：2秒轮询
- 完成/失败：停止轮询

**显示指标**
```
前端指标（从渲染器读取）
├─ FPS        - 渲染帧率
├─ Vertices   - 点云顶点数
└─ Progress   - 迭代进度

后端指标（从训练日志解析）
├─ Algo FPS   - 训练速度
├─ Loss       - 训练损失
├─ PSNR       - 图像质量
└─ Iter       - 当前迭代数
```

**日志与历史**
```
logs/
├─ <job_id>.log         # 完整训练日志（实时更新）
└─ <job_id>_metrics.csv # 指标历史表（迭代→Loss/PSNR）
```

### 4. PLY快速加载

无需重新训练，直接加载已有PLY文件：
```bash
# 方式1：Web界面
Data → Quick Load PLY → 选择本地PLY文件

# 方式2：API接口
curl -X POST http://127.0.0.1:8080/api/load-ply \
  -F "ply_file=@scene.ply"

# 输出：
{
  "status": "success",
  "scene_id": "ply_cache_1234567890",
  "viewer_url": "http://127.0.0.1:8080/viewer?scene=ply_cache_1234567890"
}
```

---

## 🛠️ 常见问题与解决方案

### Q1: 上传文件后找不到上传的数据

**症状**: "Failed to fetch" 或上传后数据消失

**解决方案**:
```bash
# 清除浏览器缓存
# 快捷键：Ctrl+Shift+Delete (Windows) 或 Cmd+Shift+Delete (Mac)

# 强制刷新页面
# 快捷键：Ctrl+R (Windows) 或 Cmd+R (Mac)

# 检查服务器是否正常运行
python3 web/server/api_server.py --host 127.0.0.1 --port 8080
```

### Q2: "SSH连接失败"

**症状**: Remote Precheck 失败，显示 `WGSC-STEP4-SSH-AUTH-001`

**检查清单**:
```bash
# 1. 测试SSH连接
ssh -i <key_file> user@remote_host -p 22

# 2. 验证远程Python环境
ssh user@remote_host "python3 --version"

# 3. 验证算法环境是否已配置
ssh user@remote_host "conda activate gs-env && python3 -c 'import torch; print(torch.cuda.is_available())'"

# 4. 检查远程存储空间
ssh user@remote_host "df -h /path/to/workspace"
```

### Q3: COLMAP处理失败

**症状**: 物化阶段报错 `colmap` failed

**常见原因和解决**:
```bash
# 原因1: COLMAP未安装或不在PATH
# 解决:
apt-get install -y colmap  # Ubuntu/Debian
brew install colmap        # macOS

# 原因2: 图片质量不足（无足够特征点）
# 解决: 上传至少5-8张图片，避免模糊/重复

# 原因3: 本地机器无GPU
# 解决: 使用CPU COLMAP（较慢）或跳过COLMAP，复用已有数据集
```

### Q4: 远程训练速度很慢

**症状**: 每次迭代耗时数秒，无法完成

**优化方法**:
```bash
# 1. 检查GPU利用率
ssh user@remote_host "nvidia-smi -lms 500"  # 每500ms更新一次

# 2. 减小图片分辨率（配置中）
# 在web/config/ 或 WEB_TRAINING_MANUAL_ZH.md 中查看

# 3. 减少高斯数量初始化
# 某些算法支持 --num_gp 参数

# 4. 使用更快的算法（如FCGS）替代压缩算法

# 5. 并行多个任务会争抢显存
```

### Q5: PLY文件加载后无法渲染

**症状**: 查看器显示空白或加载符号一直转

**检查**:
```bash
# 1. 确认PLY文件格式（ASCII/二进制）
file scene.ply

# 2. 确认PLY文件包含顶点和法向
# 应该包含 "element vertex" 和 "property float nx/ny/nz"

# 3. 检查文件大小（超过1GB可能太大）
ls -lh scene.ply

# 4. 尝试通过API直接加载
curl -X POST http://127.0.0.1:8080/api/load-ply \
  -F "ply_file=@scene.ply" -v
```

### Q6: 如何选择合适的算法?

**选择指南**:
```
┌─────────────────────────────────────────────────┐
│ 使用场景 → 推荐算法                            │
├─────────────────────────────────────────────────┤
│ 第一次使用？ → HAC++（完整功能+稳定）         │
│ 需要快速？ → FCGS（秒级压缩无优化）            │
│ 需要高压缩率？ → ContextGS/CompGS/HAC++        │
│ 大规模场景？ → Scaffold-GS                      │
│ 纹理缺失场景？ → GaussianPro                    │
│ 内存紧张？ → reduced-3dgs/MEGS-2                │
│ PyTorch Lightning多GPU？ → GSLightning          │
└─────────────────────────────────────────────────┘
```

---

## 📊 系统要求与性能

### 本地训练配置推荐

| 配置 | 最小要求 | 推荐配置 |
|------|---------|---------|
| **GPU** | NVIDIA 2GB VRAM | NVIDIA 24GB+ (RTX4090/A100) |
| **CPU** | 4核 | 16核+ |
| **内存** | 8GB | 32GB+ |
| **存储** | 50GB | 500GB+ (SSD) |
| **OS** | Ubuntu 18.04+ | Ubuntu 20.04+ |

### 远程服务器推荐配置

```
HAC++ / FCGS / ContextGS / CompGS:
├─ Python: 3.10 + PyTorch 2.2
├─ GPU: NVIDIA A100 / RTX4090 / RTX6000
├─ 磁盘: 1TB 高速SSD
└─ 并发任务: 2-4个

reduced-3dgs / MEGS-2:
├─ Python: 3.7.13 + PyTorch 1.12.1
├─ GPU: NVIDIA 16GB+ (V100/RTX3090)
└─ 内存: 64GB+

Scaffold-GS:
├─ Python: 3.7.13 + PyTorch 1.12.1
├─ GPU: 多个GPU（支持分布式）
└─ 磁盘: 2TB+（大场景）
```

---

## 🔗 API参考

### 上传与数据处理

**POST /api/upload**
```json
{
  "files": [multipart file array],
  "auto_colmap": true,
  "workspace_id": "my_scene_001"
}
→ Response: { "workspace_id": "...", "status": "uploading" }
```

**POST /api/materialize**
```json
{
  "workspace_id": "my_scene_001",
  "run_colmap": true
}
→ Response: { "status": "materializing", "task_id": "..." }
```

### 训练与执行

**POST /api/train**
```json
{
  "workspace_id": "my_scene_001",
  "algorithm": "HAC++",
  "operation": "render",
  "ssh_config": {
    "host": "remote.server.com",
    "user": "username",
    "password": "passwd"
  },
  "auto_colmap": true,
  "parameters": { "iterations": 30000 }
}
→ Response: { "job_id": "...", "status": "pending" }
```

**GET /api/poll?job_id=...**
```json
→ Response: { 
  "status": "training",  // running|training|rendering|completed|failed
  "progress": 45,
  "log_tail": "...",
  "metrics": { "loss": 0.05, "psnr": 28.3 }
}
```

### 结果与可视化

**GET /api/load-ply**
```json
{
  "job_id": "..." // 自动从job output目录查找PLY
}
→ Response: { "scene_id": "...", "viewer_url": "..." }
```

**POST /api/export-scene**
```json
{
  "job_id": "...",
  "format": "ply_package"  // 导出完整场景包
}
→ Response: { "package_path": "..." }
```

---

## 💡 最佳实践

### 1. 数据准备
- ✅ 上传至少**8-12张高质量照片**（高分辨率，清晰，无运动模糊）
- ✅ 拍摄方式：环绕物体 360°，或走过场景获取多视图
- ✅ 避免：反光表面、重复纹理、动态物体、极端曝光

### 2. 参数配置
- ✅ 首次运行用**默认参数**，观察效果
- ✅ 对于小场景：**iteration 7000-15000**
- ✅ 对于大场景：**iteration 30000+**
- ✅ 启用**COLMAP预处理**（改善SfM质量）

### 3. 远程训练管理
- ✅ **一次性上传多个任务**，后台并行处理
- ✅ **定期检查日志**，及时发现问题
- ✅ **备份重要结果**（从remote_output下载）
- ✅ **清理旧任务**，释放服务器存储

### 4. 性能优化
- ✅ 调整**分辨率**（resolution_scale: 0.5-1.0）
- ✅ 启用**compression** operation（如果算法支持）
- ✅ 使用**已有COLMAP数据集**复用（跳过重复处理）

---

## 📝 更新日志

参见 [change.md](change.md) 了解最新更新：
- ✅ 2026-04-30: 远程SSH环境配置指南完成（7个算法）
- ✅ 2026-04-28: PLY快速加载接口集成
- ✅ 2026-04-25: 文件上传bug修复，支持复用远程数据集
- ✅ 2026-04-20: 远程无头COLMAP自动配置

---

## 📞 获取帮助

### 自助排查

1. 查看 [WEB_TRAINING_MANUAL_ZH.md](web/WEB_TRAINING_MANUAL_ZH.md) 第6-8章（常见问题）
2. 查看 [REMOTE_SETUP_INDEX.md](web/project_md/REMOTE_SETUP_INDEX.md) 的算法速查表
3. 运行远程验证脚本：
   ```bash
   bash web/tools/remote_verify_setup.sh
   ```

### 获取技术支持

**信息清单**（反馈时请提供）：
- [ ] Web应用版本（查看页面底部或浏览器控制台）
- [ ] 错误信息/错误码（如 `WGSC-STEP4-SSH-AUTH-001`）
- [ ] 服务器日志（`tail -f logs/*.log`）
- [ ] 系统环境（OS、Python版本、PyTorch版本、GPU型号）
- [ ] 复现步骤（具体操作序列）

---

## 📜 许可证

本项目遵循 MIT 许可证。各个算法实现项目有各自的许可证，使用前请参考相应文件夹内的 LICENSE 文件。

---

## 🙏 致谢

感谢所有算法原作者及贡献者。特别感谢以下项目：
- 3D Gaussian Splatting (original authors)
- COLMAP (image-based 3D reconstruction)
- PyTorch (deep learning framework)

---

**最后更新**: 2026年5月18日（完整项目版本 v1.0）  
**项目版本**: ✅ 稳定版本 - 8个算法已配置、所有文档已完善  
**推荐起点**: [WEB_TRAINING_MANUAL_ZH.md](web/WEB_TRAINING_MANUAL_ZH.md) 或 [web/START_HERE.md](web/START_HERE.md)
