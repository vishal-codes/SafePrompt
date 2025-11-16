#!/usr/bin/env bash
set -euo pipefail

export BASE_MODEL="meta-llama/Llama-3.2-3B-Instruct"
export NUM_THREADS="${NUM_THREADS:-4}"
export HF_TOKEN="${HF_TOKEN:-hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}"           
export HF_LOCAL_ONLY="${HF_LOCAL_ONLY:-false}"
export HF_HOME="$HOME/.cache/huggingface"

export ADAPTER_REPO="chinu-codes/llama-3.2-3b-pii-redactor-lora"
export SEQ_LEN=256          # keep memory predictable
export MAX_NEW_TOKENS=64
export TORCH_NUM_THREADS=2  
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export TOKENIZERS_PARALLELISM=false
export PYTORCH_NO_CUDA=1    # force CPU path
export MALLOC_ARENA_MAX=2   # reduce glibc heap overhead


uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
