# FCGS 快速参考卡

## 关键命令速查

### 环境设置（5分钟）
```bash
cd FCGS-main
conda env create --file environment.yml
conda activate FCGS_env
git submodule update --init --recursive
```

### 快速测试（1分钟）
```bash
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output --determ 1
```

### 完整压缩流程
```bash
# 压缩
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output --determ 1

# 解压
python decode_single_scene.py --lmd 4e-4 --bit_path_from output --ply_path_to restored.ply

# 验证质量
python decode_single_scene_validate.py --lmd 4e-4 --bit_path_from output --ply_path_to restored.ply --source_path images
```

---

## 参数速查表

| 参数 | 类型 | 说明 | 使用建议 |
|------|------|------|---------|
| `--lmd` | float | 压缩强度参数 | 1e-4(高质量), 4e-4(平衡), 16e-4(高压缩) |
| `--ply_path_from` | path | 输入 PLY 文件路径 | 指向原始点云文件 |
| `--bit_path_to` | path | 输出比特流目录 | 存放压缩后的 .bin 文件 |
| `--bit_path_from` | path | 输入比特流目录 | 解压时指定来源 |
| `--ply_path_to` | path | 输出 PLY 文件路径 | 解压时的保存位置 |
| `--determ` | 0/1 | 确定性模式 | 1(推荐) 或 0 |
| `--source_path` | path | 源图像目录 | 用于 PSNR 评估 |

---

## Lambda 值对照表

| Lambda | 使用场景 | 文件大小 | 保真度 | 场景 |
|--------|---------|--------|--------|------|
| 1e-4 | 最高质量 | 最大 | 最高 | 专业应用 |
| 2e-4 | 高质量 | 较大 | 很高 | 存档 |
| **4e-4** | **平衡** | **中等** | **很好** | **推荐** |
| 8e-4 | 良好压缩 | 较小 | 良好 | 网络传输 |
| 16e-4 | 最大压缩 | 最小 | 一般 | 快速预览 |

---

## 常见错误速查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `CUDA not available` | GPU 驱动问题 | 运行 `nvidia-smi` 检查；重装 PyTorch |
| `No such file or directory` | PLY 文件路径错误 | 检查文件是否存在：`ls -la input.ply` |
| `tmc3 not found` | GPCC 未安装 | 编译 MPEG PCC 并添加到 PATH |
| `Permission denied` | 输出目录权限 | `mkdir -p output && chmod 755 output` |
| `Invalid PLY format` | PLY 文件损坏 | 使用 `plyfile` 验证；重新下载 |
| `Dimension mismatch` | PLY 属性不匹配 | 检查 PLY 文件是否是有效的 3DGS 格式 |

---

## 工作流速查

### 单文件压缩
```bash
python encode_single_scene.py \
  --lmd 4e-4 \
  --ply_path_from input.ply \
  --bit_path_to output \
  --determ 1
```

### 单文件解压
```bash
python decode_single_scene.py \
  --lmd 4e-4 \
  --bit_path_from output \
  --ply_path_to restored.ply
```

### 质量验证
```bash
python decode_single_scene_validate.py \
  --lmd 4e-4 \
  --bit_path_from output \
  --ply_path_to restored.ply \
  --source_path images
```

### 批量压缩
```bash
for file in *.ply; do
  python encode_single_scene.py \
    --lmd 4e-4 \
    --ply_path_from "$file" \
    --bit_path_to "output/${file%.ply}" \
    --determ 1
done
```

---

## GPU 显存需求

| 点云规模 | 最小显存 | 推荐显存 |
|---------|---------|--------|
| 小 (<100M) | 4 GB | 8 GB |
| 中 (100M-500M) | 8 GB | 16 GB |
| 大 (>500M) | 16 GB | 32 GB+ |

---

## 性能基准（参考值）

| 操作 | 时间 | 特点 |
|------|------|------|
| 压缩 (单个点云) | 1-3 秒 | 快速，无需优化 |
| 解压 | <1 秒 | 非常快 |
| 验证/评估 | 5-10 秒 | 包含 PSNR 计算 |

---

## 配置预设

### 最高质量
```bash
--lmd 1e-4 --determ 1
```

### 推荐配置
```bash
--lmd 4e-4 --determ 1
```

### 最大压缩
```bash
--lmd 16e-4 --determ 1
```

---

## 文件结构

```
FCGS-main/
├── data/
│   └── ply_files/          # 存放输入的 PLY 文件
├── outputs/
│   └── {scene_name}_compressed/   # 压缩后的比特流
├── logs/                   # 日志文件
├── encode_single_scene.py  # 压缩脚本
├── decode_single_scene.py  # 解压脚本
├── decode_single_scene_validate.py  # 验证脚本
└── model/                  # 模型核心代码
```

---

## 一键操作清单

```bash
# 部署
conda env create --file environment.yml && conda activate FCGS_env

# 压缩
python encode_single_scene.py --lmd 4e-4 --ply_path_from input.ply --bit_path_to output --determ 1

# 解压
python decode_single_scene.py --lmd 4e-4 --bit_path_from output --ply_path_to output.ply

# 验证
python decode_single_scene_validate.py --lmd 4e-4 --bit_path_from output --ply_path_to output.ply --source_path images

# 监控
nvidia-smi
```

---

**提示**: 保存此文件以便快速查询！
