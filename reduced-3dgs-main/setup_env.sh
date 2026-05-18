#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${REDUCED_3DGS_ENV_NAME:-gaussian_splatting}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.1}"
TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda was not found in PATH. Install Miniconda/Anaconda or source conda.sh first." >&2
  exit 1
fi

eval "$(conda shell.bash hook)"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "Conda environment '$ENV_NAME' already exists; reusing it."
else
  conda create -y -n "$ENV_NAME" python=3.10 pip
fi

conda activate "$ENV_NAME"
export CUDA_HOME
export TORCH_CUDA_ARCH_LIST
export FORCE_CUDA=1

python -m pip install --upgrade pip setuptools wheel ninja

conda install -y -c pytorch -c nvidia \
  pytorch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 pytorch-cuda=12.1

conda install -y -c conda-forge \
  "numpy=1.26.*" "pillow=10.*" "plyfile=1.1.*" "pandas=2.2.*" tqdm urllib3=2.2.1

python -m pip install nvtx

if [ ! -d submodules/diff-gaussian-rasterization ] || [ ! -d submodules/simple-knn ]; then
  echo "Missing Reduced-3DGS CUDA submodules." >&2
  echo "Restore submodules/diff-gaussian-rasterization and submodules/simple-knn before running this script." >&2
  echo "Expected CUDA_HOME=$CUDA_HOME and TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST for RTX 4090 builds." >&2
  exit 1
fi

python -m pip install --no-build-isolation submodules/diff-gaussian-rasterization
python -m pip install --no-build-isolation submodules/simple-knn

python - <<'PY'
import torch

print("python/torch environment ready")
print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
PY
