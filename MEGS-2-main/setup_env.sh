#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${MEGS2_ENV_NAME:-MEGS2}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.1}"
TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"
MAX_JOBS="${MAX_JOBS:-4}"
OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v mamba >/dev/null 2>&1; then
  CONDA_FRONTEND=mamba
else
  CONDA_FRONTEND=conda
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "conda is required. Source your conda profile first, for example:"
  echo "source /root/autodl-tmp/miniforge3/etc/profile.d/conda.sh"
  exit 1
fi

eval "$(conda shell.bash hook)"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  echo "Reusing conda environment: ${ENV_NAME}"
else
  "${CONDA_FRONTEND}" create -y -n "${ENV_NAME}" python=3.10 pip
fi

conda activate "${ENV_NAME}"

"${CONDA_FRONTEND}" install -y -c pytorch -c nvidia -c conda-forge \
  pytorch=2.2.2 torchvision=0.17.2 torchaudio=2.2.2 pytorch-cuda=12.1 \
  numpy=1.26.* pillow=10.* plyfile=1.1.* tqdm

python -m pip install --upgrade pip setuptools wheel

export CUDA_HOME
export FORCE_CUDA=1
export TORCH_CUDA_ARCH_LIST
export MAX_JOBS
export OMP_NUM_THREADS
export PATH="${CUDA_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

for module_dir in \
  "${ROOT_DIR}/submodules/diff-gaussian-rasterization" \
  "${ROOT_DIR}/submodules/diff-gaussian-rasterization_ms" \
  "${ROOT_DIR}/submodules/diff-gaussian-rasterization_ms_light" \
  "${ROOT_DIR}/submodules/simple-knn"; do
  if [ ! -d "${module_dir}" ]; then
    echo "Missing CUDA extension source: ${module_dir}"
    echo "Restore submodules before running this script."
    exit 1
  fi
done

python -m pip install --no-build-isolation -v "${ROOT_DIR}/submodules/diff-gaussian-rasterization"
python -m pip install --no-build-isolation -v "${ROOT_DIR}/submodules/diff-gaussian-rasterization_ms"
python -m pip install --no-build-isolation -v "${ROOT_DIR}/submodules/diff-gaussian-rasterization_ms_light"
python -m pip install --no-build-isolation -v "${ROOT_DIR}/submodules/simple-knn"

python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
PY
