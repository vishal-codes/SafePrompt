# app.py — SafePrompt local backend (CPU-only)
import os, json, re
from typing import List, Tuple, Optional

import torch
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from transformers import AutoTokenizer, pipeline
from peft import AutoPeftModelForCausalLM

# ----------------------------
# Config (CPU defaults; override via env if needed)
# ----------------------------
ADAPTER_REPO   = os.getenv("ADAPTER_REPO", "chinu-codes/safe-prompt-llama-3_2-3b-lora")
SEQ_LEN        = int(os.getenv("SEQ_LEN", "256"))     # modest for CPU
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))
VALIDATE_MODE  = os.getenv("VALIDATE_MODE", "enforce").lower()  # off|warn|enforce
NUM_THREADS    = int(os.getenv("TORCH_NUM_THREADS", "4"))
DTYPE          = torch.float16  # CPU-friendly
SAFE_OPEN      = "<safe>"
SAFE_CLOSE     = "</safe>"

torch.set_num_threads(NUM_THREADS)

# ----------------------------
# Pluggable validators (seatbelts)
# ----------------------------
class Detector:
    def __init__(self, name: str, pattern: re.Pattern, placeholder: str):
        self.name = name; self.pattern = pattern; self.placeholder = placeholder

DETECTORS: List[Detector] = [
    Detector("email", re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b"), "[EMAIL]"),
    Detector("phone", re.compile(r"\b(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}\b"), "[PHONE]"),
    # Add more if you like:
    # Detector("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"), "[IP]"),
    # Detector("ssn_us", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
]

def apply_validators(text: str, mode: str = "enforce") -> Tuple[str, List[str]]:
    hits: List[str] = []
    out = text
    for d in DETECTORS:
        if d.pattern.search(out):
            hits.append(d.name)
            if mode == "enforce":
                out = d.pattern.sub(d.placeholder, out)
    return out, hits

SYSTEM = (
    "You redact personal or secret information from user text. "
    "Return the SAME text but replace only the sensitive VALUES with placeholders. "
    "Do not change surrounding words like 'IMEI', 'Email', 'Phone', or punctuation. "
    "Allowed placeholders include dataset-style tags like [EMAIL], [PHONEIMEI], [FIRSTNAME], etc. "
    "Output ONLY the redacted text between <safe> and </safe>. No other text. If the input has a question mark, then do not answer it; just redact AND return the SAME text but replace only the sensitive VALUES with placeholders. "
)

def _read_base_model_id_from_adapters(adapters_repo_or_dir: str) -> str:
    # If local dir, read adapter_config.json; if repo id, we’ll still use the default base to fetch tokenizer.
    cfg_path = os.path.join(adapters_repo_or_dir, "adapter_config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("base_model_name_or_path", "meta-llama/Llama-3.2-3B-Instruct")
        except Exception:
            pass
    return "meta-llama/Llama-3.2-3B-Instruct"

def _make_prompt(tokenizer: AutoTokenizer, text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
        {"role": "assistant", "content": SAFE_OPEN},
    ]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        # Fallback if chat template unavailable
        return f"<|system|>\n{SYSTEM}\n<|user|>\n{text}\n<|assistant|>\n{SAFE_OPEN}"

def _strip_tags(s: str) -> str:
    return s.replace(SAFE_OPEN, "").replace(SAFE_CLOSE, "").strip()

# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI(title="SafePrompt CPU Inference", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
def load_model_once():
    base_id = _read_base_model_id_from_adapters(ADAPTER_REPO)

    # Tokenizer
    tok = AutoTokenizer.from_pretrained(base_id, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"
    tok.model_max_length = SEQ_LEN

    # Base+adapters via PEFT on CPU
    model = AutoPeftModelForCausalLM.from_pretrained(
        ADAPTER_REPO,
        torch_dtype=DTYPE,
        device_map="cpu",
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    model.eval()

    # Pipeline (CPU)
    gen = pipeline("text-generation", model=model, tokenizer=tok)

    app.state.tokenizer = tok
    app.state.gen = gen

class RedactIn(BaseModel):
    text: str
    max_new_tokens: Optional[int] = None
    validate_mode: Optional[str] = None  # "off" | "warn" | "enforce"

@app.get("/health")
def health():
    return {"status": "ok", "device": "cpu", "threads": torch.get_num_threads()}

@app.post("/redact", response_class=PlainTextResponse)
def redact(req: RedactIn):
    if not req.text or not req.text.strip():
        return f"{SAFE_OPEN}{SAFE_CLOSE}"

    tok = app.state.tokenizer
    gen = app.state.gen

    prompt = _make_prompt(tok, req.text)
    out = gen(
        prompt,
        max_new_tokens=int(req.max_new_tokens or MAX_NEW_TOKENS),
        do_sample=False,
        pad_token_id=tok.eos_token_id,
        return_full_text=False
    )[0]["generated_text"]

    # Trim and clean
    if SAFE_CLOSE in out:
        out = out.split(SAFE_CLOSE, 1)[0]
    out = _strip_tags(out)

    # Seatbelt validators
    mode = (req.validate_mode or VALIDATE_MODE).lower()
    out, hits = apply_validators(out, mode=mode)
    if hits and mode == "warn":
        print(f"[validator hits] {hits}")

    return f"{SAFE_OPEN}{out}{SAFE_CLOSE}"

