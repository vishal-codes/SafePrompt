import os
import time
import torch
from typing import Tuple
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from .config import settings

# Always CPU 
DEVICE = torch.device("cpu")
DTYPE = torch.float32
torch.set_num_threads(settings.NUM_THREADS)

# Llama 3.2 special tokens (strings). 
START, END, EOT = "<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"
SAFE_OPEN, SAFE_CLOSE = "<safe>", "</safe>"

SYSTEM_RULE = (
    "You are a redactor. Return the EXACT input text with only PII spans replaced by dataset placeholders. "
    "Do NOT change any other words, punctuation, or casing. If unsure, keep. "
    "Wrap the final output inside <safe> and </safe>."
)

_tokenizer = None
_model = None


def load_model() -> Tuple[AutoTokenizer, PeftModel]:
    global _tokenizer, _model
    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    auth_token = settings.HF_TOKEN or True  

    _tokenizer = AutoTokenizer.from_pretrained(
        settings.BASE_MODEL,
        use_fast=False,
        token=settings.HF_TOKEN,
        local_files_only=settings.HF_LOCAL_ONLY,
    )
    if _tokenizer.pad_token is None and _tokenizer.eos_token is not None:
        _tokenizer.pad_token = _tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        settings.BASE_MODEL,
        torch_dtype=DTYPE,
        device_map=None,            # CPU
        low_cpu_mem_usage=True,
        attn_implementation="eager",
        token=auth_token,
        local_files_only=settings.HF_LOCAL_ONLY,
    )
    base.to(DEVICE)
    base.config.use_cache = True
    base.eval()

    _model = PeftModel.from_pretrained(
        base, settings.ADAPTER_REPO,
        is_trainable=False,
        token=auth_token,
        local_files_only=settings.HF_LOCAL_ONLY,
    )
    _model.to(DEVICE, dtype=DTYPE)
    _model.eval()

    return _tokenizer, _model


def build_prompt(user_text: str, tok: AutoTokenizer) -> str:
    bos = tok.bos_token or "<|begin_of_text|>"
    return (
        f"{bos}"
        f"{START}system{END}\n{SYSTEM_RULE}\n{EOT}"
        f"{START}user{END}\n{user_text}\n{EOT}"
        f"{START}assistant{END}\n{SAFE_OPEN}"
    )


@torch.no_grad()
def generate_safe(user_text: str, max_new_tokens: int) -> Tuple[str, str, int]:
    """
    Returns: safe_text ("<safe>…</safe>"), redacted_text (inside tags), latency_ms
    """
    tok, model = load_model()
    prompt = build_prompt(user_text, tok)

    inputs = tok(
        prompt,
        return_tensors="pt",
        padding=False,
        truncation=True,
        max_length=settings.SEQ_LEN,
    )

    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    t0 = time.time()
    out = model.generate(
        **inputs,
        max_new_tokens=int(max_new_tokens),
        do_sample=settings.DO_SAMPLE,
        eos_token_id=tok.eos_token_id,
        pad_token_id=tok.pad_token_id,
    )
    latency_ms = int((time.time() - t0) * 1000)

    decoded = tok.decode(out[0], skip_special_tokens=True)
    s = decoded.rfind(SAFE_OPEN)
    if s != -1:
        s += len(SAFE_OPEN)
        e = decoded.find(SAFE_CLOSE, s)
        inner = decoded[s:e if e != -1 else None].strip()
    else:
        # Fallback: take tail beyond prompt
        inner = decoded[len(prompt):].strip()

    return f"{SAFE_OPEN}{inner}{SAFE_CLOSE}", inner, latency_ms
