#!/usr/bin/env bash
# ensure_activate_hac.sh: init conda/mamba hooks and attempt to activate 'hac' env

echo "=== ensure_activate_hac.sh: start ==="

# Try conda shell hook if conda exists
if command -v conda >/dev/null 2>&1; then
  echo "Found conda at: $(command -v conda)"
  eval "$(conda shell.bash hook)" 2>/dev/null || true
  if [ -f "$HOME/.bashrc" ]; then
    echo "Sourcing $HOME/.bashrc"
    # shellcheck disable=SC1090
    source "$HOME/.bashrc" || true
  fi
  # Try common conda.sh locations
  if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh" || true
  elif [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
    source "/root/miniconda3/etc/profile.d/conda.sh" || true
  fi
else
  echo "conda not found in PATH"
fi

# Try mamba shell hook
if command -v mamba >/dev/null 2>&1; then
  echo "Found mamba at: $(command -v mamba)"
  eval "$(mamba shell hook --shell bash)" 2>/dev/null || true
else
  echo "mamba not found in PATH"
fi

echo "Attempting to activate environment 'hac'..."
ACTIVATED=false
if command -v conda >/dev/null 2>&1; then
  if conda activate hac 2>/dev/null; then
    echo "Activated 'hac' via conda."
    ACTIVATED=true
  fi
fi
if [ "$ACTIVATED" = "false" ] && command -v mamba >/dev/null 2>&1; then
  if mamba activate hac 2>/dev/null; then
    echo "Activated 'hac' via mamba."
    ACTIVATED=true
  fi
fi

if [ "$ACTIVATED" = "false" ]; then
  echo "Activation failed. Fallback options:"
  echo "  - Use: conda run -n hac <cmd>"
  echo "  - Or:  mamba run -n hac <cmd>"
  ENV_PY="$HOME/miniconda3/envs/hac/bin/python"
  if [ ! -x "$ENV_PY" ]; then
    ENV_PY="/root/miniconda3/envs/hac/bin/python"
  fi
  if [ -x "$ENV_PY" ]; then
    echo "Env python appears to be: $ENV_PY"
    echo "You can run diagnostics with:"
    echo "  $ENV_PY -c \"import sys,torch; print(sys.executable, torch.__version__, torch.version.cuda, torch.cuda.is_available())\""
  fi
fi

echo "Diagnostics (current shell):"
which python || true
python -c "import sys; print(sys.executable)" 2>/dev/null || true
python -c "import torch; print('torch', getattr(torch,'__version__',None), 'cuda', getattr(torch,'version',None) and torch.version.cuda, 'available', torch.cuda.is_available())" 2>/dev/null || true
echo "=== ensure_activate_hac.sh: end ==="
