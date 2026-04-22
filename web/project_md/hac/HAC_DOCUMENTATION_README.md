# HAC++ 完整调试文档 - 使用指南

## 📌 概览

为了帮助你快速上手 HAC++ 的部署和调试，我已创建了一套完整的文档和自动化脚本。这份指南将带你了解所有资源及其使用方法。

---

## 📁 文件位置和用途

### 📄 主要文档（在 `/web/` 目录下）

#### 1. **HAC_DOCUMENTATION_INDEX.md** ⭐ 推荐首先阅读
- **位置**: `/Users/chen/Documents/Web_Scan/web/HAC_DOCUMENTATION_INDEX.md`
- **内容**: 所有文档的索引和快速导航
- **用途**: 快速了解全局结构，找到需要的文档
- **阅读时间**: 5分钟

#### 2. **HAC_PLUS_DEBUG_GUIDE.md** ⭐ 最详细的指南
- **位置**: `/Users/chen/Documents/Web_Scan/web/HAC_PLUS_DEBUG_GUIDE.md`
- **内容**: 完整的分步调试指南
- **章节**:
  - 环境配置
  - 项目初始化
  - 数据准备
  - 训练调试
  - 评估和压缩
  - 常见问题排查（6个详细解决方案）
  - 性能优化
  - 完整工作流示例
- **用途**: 从零开始部署 HAC++
- **阅读时间**: 30分钟（完整阅读）

#### 3. **HAC_QUICK_REFERENCE.md** ⚡ 快速查询
- **位置**: `/Users/chen/Documents/Web_Scan/web/HAC_QUICK_REFERENCE.md`
- **内容**: 命令和参数速查表
- **包含**:
  - 关键命令速查
  - 参数速查表
  - 常见错误速查
  - GPU 显存需求
  - 性能基准数据
  - 配置预设
- **用途**: 日常开发时快速查找
- **查询时间**: 1-2分钟

---

### 🔧 自动化脚本（在 `HAC-plus-main/` 目录下）

#### 1. **setup_and_test.sh** - 一键部署
```bash
位置: /Users/chen/Documents/Web_Scan/HAC-plus-main/setup_and_test.sh
用途: 自动完成所有部署步骤
功能:
  ✓ 检查系统环境
  ✓ 创建 Conda 环境
  ✓ 编译 CUDA 子模块
  ✓ 验证 Python 导入
  ✓ 创建必要目录
  ✓ 可选：运行快速测试

使用方法:
  bash setup_and_test.sh

预期时间: 15-30分钟（取决于网络和编译）
```

#### 2. **batch_train.sh** - 批量训练
```bash
位置: /Users/chen/Documents/Web_Scan/HAC-plus-main/batch_train.sh
用途: 自动训练多个场景
功能:
  ✓ 支持多个数据集：nerf_synthetic, mipnerf360, blending
  ✓ 参数自动计算
  ✓ 进度跟踪
  ✓ 自动生成报告
  ✓ 错误恢复

使用方法:
  bash batch_train.sh [dataset] [lambda] [iterations]

示例:
  bash batch_train.sh nerf_synthetic 0.001 30000
  bash batch_train.sh mipnerf360 0.001 30000

支持的数据集:
  - nerf_synthetic (8 scenes)
  - mipnerf360 (9 scenes)
  - blending (2 scenes)
```

#### 3. **diagnose.py** - 系统诊断工具
```bash
位置: /Users/chen/Documents/Web_Scan/HAC-plus-main/diagnose.py
用途: 诊断系统和项目配置
功能:
  ✓ 系统环境检查
  ✓ PyTorch/CUDA 检查
  ✓ Conda 环境检查
  ✓ GPU 性能检查
  ✓ TMC3 GPCC 检查
  ✓ 项目结构验证
  ✓ Python 模块检查
  ✓ 数据集完整性检查
  ✓ 生成诊断报告

使用方法:
  python diagnose.py

输出:
  - 控制台报告（彩色输出）
  - diagnostic_report.json（详细报告）

用途:
  - 首次部署前验证
  - 排查问题时诊断
  - 检查依赖和配置
```

---

## 🚀 快速开始（5分钟）

### 方式 A: 完全自动化（推荐新手）
```bash
# 1. 进入项目目录
cd /Users/chen/Documents/Web_Scan/HAC-plus-main

# 2. 运行一键部署
bash setup_and_test.sh

# 3. 按照提示操作（选择是否进行快速测试）
# 完成！现在可以准备数据并开始训练了
```

### 方式 B: 逐步配置（推荐进阶用户）
```bash
# 1. 阅读完整指南
cat ../web/HAC_PLUS_DEBUG_GUIDE.md | less

# 2. 按照指南逐步执行命令
# 这样可以理解每一步的作用

# 3. 遇到问题时查看快速参考
cat ../web/HAC_QUICK_REFERENCE.md | less
```

### 方式 C: 问题排查
```bash
# 1. 运行诊断工具
python diagnose.py

# 2. 根据输出结果查看对应的文档章节
# 例如：如果 CUDA 显示错误，查看 HAC_PLUS_DEBUG_GUIDE.md 中的"问题1"

# 3. 查看快速参考表中的常见错误速查
```

---

## 📊 典型工作流

### 完整的训练流程示例：

```
[Day 1] 部署阶段
├─ 运行: bash setup_and_test.sh
├─ 等待编译完成 (~20 分钟)
└─ 验证: python diagnose.py

[Day 2] 准备数据阶段
├─ 下载 Synthetic NeRF 数据集
├─ 解压到 data/nerf_synthetic/
└─ 验证: ls data/nerf_synthetic/chair/images/

[Day 3] 训练阶段
├─ 快速测试 (100 iterations, 5分钟):
│  python train.py -s data/nerf_synthetic/chair \
│    -m outputs/test --iterations 100
│
└─ 完整训练 (30000 iterations, 4小时):
   python train.py -s data/nerf_synthetic/chair \
     -m outputs/chair --iterations 30_000

[Day 4] 评估和批量训练
├─ 查看结果: ls -lh outputs/chair/point_cloud/
├─ 批量训练所有场景:
│  bash batch_train.sh nerf_synthetic 0.001 30000
└─ 生成报告: cat logs/training_summary_*.txt
```

---

## 🎯 文档使用建议

### 根据你的角色选择文档：

**👨‍💻 我是新手，想快速上手**
1. 阅读: [HAC_DOCUMENTATION_INDEX.md](./HAC_DOCUMENTATION_INDEX.md) (5分钟)
2. 运行: `bash setup_and_test.sh` (20分钟)
3. 参考: [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md)

**🔬 我是研究人员，需要完整理解**
1. 阅读: [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md) (30分钟)
2. 运行: 逐步执行指南中的命令
3. 参考: 根据需要查看快速参考

**🐛 我遇到了问题，需要排查**
1. 运行: `python diagnose.py`
2. 查看: [HAC_PLUS_DEBUG_GUIDE.md](./HAC_PLUS_DEBUG_GUIDE.md) 中的对应问题
3. 参考: [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md) 中的错误速查表

**⚡ 我只需要快速查找某个命令或参数**
1. 查看: [HAC_QUICK_REFERENCE.md](./HAC_QUICK_REFERENCE.md#关键命令速查)
2. 参考: 快速参考表

**🤖 我想自动化部署和训练**
1. 使用: `setup_and_test.sh` 部署
2. 使用: `batch_train.sh` 训练
3. 参考: 脚本中的选项和参数

---

## 📋 验证清单

在开始使用前，请确认以下事项：

```
环境验证:
  [ ] Python 版本 >= 3.10
  [ ] Conda 已安装
  [ ] GPU 驱动正常 (nvidia-smi 有输出)
  [ ] 磁盘空间 >= 200GB

文档检查:
  [ ] HAC_DOCUMENTATION_INDEX.md 已找到
  [ ] HAC_PLUS_DEBUG_GUIDE.md 已找到
  [ ] HAC_QUICK_REFERENCE.md 已找到

脚本检查:
  [ ] setup_and_test.sh 存在且可执行
  [ ] batch_train.sh 存在且可执行
  [ ] diagnose.py 存在且可执行

初始化:
  [ ] 运行过 python diagnose.py
  [ ] 运行过 bash setup_and_test.sh
  [ ] 项目环境已激活: conda activate HAC_env
```

---

## 🔗 文档导航树

```
HAC++ 文档系统
│
├─ 📌 快速导航
│  └─ HAC_DOCUMENTATION_INDEX.md ⭐
│     └─ 包含所有文档的索引和导航
│
├─ 📚 详细指南
│  └─ HAC_PLUS_DEBUG_GUIDE.md ⭐⭐
│     ├─ 环境配置
│     ├─ 项目初始化
│     ├─ 数据准备
│     ├─ 训练调试
│     ├─ 评估和压缩
│     ├─ 常见问题排查
│     ├─ 性能优化
│     └─ 完整工作流
│
├─ ⚡ 快速查询
│  └─ HAC_QUICK_REFERENCE.md
│     ├─ 命令速查表
│     ├─ 参数速查表
│     ├─ 错误速查表
│     ├─ 性能基准
│     └─ 配置预设
│
└─ 🔧 自动化脚本
   ├─ setup_and_test.sh → 一键部署
   ├─ batch_train.sh → 批量训练
   └─ diagnose.py → 系统诊断
```

---

## 💬 常见问题

**Q: 我应该从哪里开始？**
A: 如果是第一次，按这个顺序：
1. 阅读 HAC_DOCUMENTATION_INDEX.md
2. 运行 bash setup_and_test.sh
3. 查看 HAC_QUICK_REFERENCE.md

**Q: 如果部署失败了怎么办？**
A: 按这个步骤排查：
1. 运行 python diagnose.py
2. 查看输出的错误信息
3. 在 HAC_PLUS_DEBUG_GUIDE.md 的"常见问题"中查找对应问题
4. 按照解决方案操作

**Q: 我可以跳过某些步骤吗？**
A: 不建议。部署步骤是相互依赖的。但如果你已经有可用的环境，可以：
1. 跳过环境创建
2. 直接准备数据
3. 开始训练

**Q: 脚本支持哪些操作系统？**
A: 脚本已在 macOS 和 Linux 上测试。Windows 用户需要：
- 使用 WSL2
- 或手动执行脚本中的命令

**Q: 如何更新或修改文档？**
A: 所有文档都是 Markdown 格式，可以：
1. 在任何文本编辑器中打开
2. 添加你自己的笔记
3. 分享给团队成员

---

## 📞 获取支持

### 自助排查：
1. **运行诊断**: `python diagnose.py`
2. **查看日志**: `tail -f logs/*.log`
3. **查文档**: 在对应的文档中搜索错误信息
4. **查参考**: 快速参考表中的错误速查

### 查看外部资源：
- [HAC++ GitHub](https://github.com/YihangChen-ee/HAC-plus/)
- [论文](https://arxiv.org/pdf/2501.12255)
- [项目主页](https://yihangchen-ee.github.io/project_hac++/)

---

## 📈 后续步骤

完成部署后，你可以：

1. **快速测试**: 用最少的数据和迭代验证设置
2. **单场景训练**: 训练一个完整的场景
3. **批量训练**: 使用 batch_train.sh 训练多个场景
4. **性能优化**: 根据 HAC_PLUS_DEBUG_GUIDE.md 中的优化技巧调整参数
5. **压缩评估**: 使用 TMC3 进行压缩并评估压缩比

---

## ✨ 总结

你现在拥有：
- ✅ 完整的调试指南（HAC_PLUS_DEBUG_GUIDE.md）
- ✅ 快速参考卡（HAC_QUICK_REFERENCE.md）
- ✅ 文档索引（HAC_DOCUMENTATION_INDEX.md）
- ✅ 一键部署脚本（setup_and_test.sh）
- ✅ 批量训练脚本（batch_train.sh）
- ✅ 诊断工具（diagnose.py）

🎉 **现在就可以开始 HAC++ 之旅了！**

---

**最后更新**: 2025-04-22
**文档版本**: 1.0
**HAC++ 版本**: Latest (TPAMI'25)

