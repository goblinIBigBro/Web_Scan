#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${GSPL_ENV_NAME:-gspl}"
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
  numpy=1.26.* pillow=10.* plyfile=1.1.* tqdm matplotlib pyyaml

python -m pip install --upgrade pip setuptools wheel packaging
python -m pip install \
  "lightning[pytorch-extra]==2.3.*" \
  "pytorch-lightning==2.3.*" \
  "jsonargparse[signatures]" \
  "bitsandbytes==0.45.*" \
  wandb tensorboard \
  "viser==0.2.3" \
  "mediapy==1.2.2" \
  "opencv-python-headless==4.10.*" \
  "splines==0.3.0"

export CUDA_HOME
export FORCE_CUDA=1
export TORCH_CUDA_ARCH_LIST
export MAX_JOBS
export OMP_NUM_THREADS
export PATH="${CUDA_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

install_cuda_extension() {
  local label="$1"
  local local_dir="$2"
  local git_url="$3"
  local source_ref="${git_url}"

  if [ -f "${local_dir}/setup.py" ] || [ -f "${local_dir}/pyproject.toml" ]; then
    source_ref="${local_dir}"
    echo "Installing ${label} from local source: ${local_dir}"
  else
    echo "Installing ${label} from pinned git source: ${git_url}"
  fi

  python -m pip install --no-build-isolation -v "${source_ref}"
}

install_cuda_extension \
  "diff-gaussian-rasterization" \
  "${ROOT_DIR}/submodules/diff-gaussian-rasterization" \
  "git+https://github.com/graphdeco-inria/diff-gaussian-rasterization.git@59f5f77e3ddbac3ed9db93ec2cfe99ed6c5d121d"

install_cuda_extension \
  "simple-knn" \
  "${ROOT_DIR}/submodules/simple-knn" \
  "git+https://github.com/yzslab/simple-knn.git@44f764299fa305faf6ec5ebd99939e0508331503"

install_cuda_extension \
  "gsplat" \
  "${ROOT_DIR}/submodules/gsplat" \
  "git+https://github.com/yzslab/gsplat.git@c27a44d4ad72ece2c32f99702083ac3d911d4ced"

python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
PY
