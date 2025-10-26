# SafePrompt

**SafePrompt** is a tiny, practical system for **LLM-assisted redaction**. It takes any user text and returns the **same text** with only sensitive values replaced by placeholders like `[EMAIL]`, `[PHONE]`, `[SSN]`, `[IP]`, etc. The output is always wrapped in a strict contract: `<safe>…</safe>`.

This repo includes:

* a **CPU-only FastAPI backend** that loads your **LoRA adapters** from Hugging Face and serves `/redact`
* a **Chrome extension (MV3)** with a right-click context menu to redact any selected text on a page
* Jupyter notebooks to **fine-tune** and **publish adapters** to Hugging Face

> Hugging Face adapters: **`chinu-codes/safe-prompt-llama-3_2-3b-lora`**
> [https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora](https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora)

---

## Why this exists

1. Redaction is often a **pre-processing** step before prompts hit your primary LLM.
2. Regex alone misses edge cases; LLMs alone can hallucinate. We combine both:

   * the model learns to mask values and keep **context unchanged**
   * optional **validator “seatbelts”** (regex) enforce masking for critical entities
3. Minimal UX: right-click, redact, paste (or auto-replace where possible).

---

## What it returns

Always exactly **one block**:

```text
<safe>…redacted version of the input…</safe>
```

Examples:

```
Input:  Hi, I am Vishal Shinde. Email me at vvs@example.com and call +1 415 555 0199.
Output: <safe>Hi, I am [FIRSTNAME] [LASTNAME]. Email me at [EMAIL] and call [PHONE]</safe>
```

```
Input:  My SSN is 123-45-6789. Do not store it.
Output: <safe>My SSN is [SSN]. Do not store it.</safe>
```

The model **does not answer questions** in the input; it only redacts and mirrors the text.

---

## Project structure

```
vishal-codes-safeprompt/
├── README.md
├── backend/
│   └── app.py                      # CPU-only FastAPI server
├── extension/
│   ├── manifest.json               # MV3 manifest
│   └── background.js               # context menu + clipboard/replace logic
└── model/
    ├── fine_tune_llama_safe_prompt.ipynb   # training notebook (LoRA)
    └── hf_uploader.ipynb                   # publish adapters + handler to HF
```

Repo tree and file roles are derived from the attached repo snapshot. 

---

## Quickstart (local, CPU-only)

### 0) Requirements

* Python 3.11 (conda recommended)
* No GPU required (we run on CPU)
* A Hugging Face account + token with `read` access (for the base model + adapters)

### 1) Create an environment and install deps

```bash
conda create -n safeprompt-api python=3.11 -y
conda activate safeprompt-api

# Torch CPU + app deps
conda install pytorch cpuonly -c pytorch -y
pip install \
  fastapi uvicorn[standard] httpx python-dotenv \
  transformers==4.57.1 peft==0.17.1 accelerate==1.11.0 safetensors>=0.4.5 \
  huggingface-hub==0.36.0
```

### 2) Log in to Hugging Face (to download base model + adapters)

```bash
huggingface-cli login
huggingface-cli whoami  # should print your username
```

### 3) Start the backend

```bash
cd backend
uvicorn app:app --host 127.0.0.1 --port 8000
```

Health check: open [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 4) Test redaction

```bash
curl -s -X POST http://127.0.0.1:8000/redact \
  -H "Content-Type: application/json" \
  -d '{"text":"Hi, I am Alice Johnson. Email alice@example.com and call 415-555-0199."}'
# -> <safe>Hi, I am [FIRSTNAME] [LASTNAME]. Email [EMAIL] and call [PHONE]</safe>
```

---

## Chrome extension (MV3)

1. Open `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → choose the `extension/` folder
3. On any web page:

   * select text, right-click → **“Redact with SafePrompt”**
   * the extension posts the selection to `http://127.0.0.1:8000/redact`
   * it tries to **replace** the selection in inputs/`contentEditable`; if not possible, it **copies** the `<safe>…</safe>` result (or opens a tab with it)

Notes:

* Some pages (e.g., `chrome://`, Chrome Web Store, PDFs) block script injection; the extension falls back to a new tab with the result.
* The extension expects the backend running on `127.0.0.1:8000`.

---

## Configuration

You can adjust the backend via environment variables:

| Variable            | Default                                     | Meaning                                             |
| ------------------- | ------------------------------------------- | --------------------------------------------------- |
| `ADAPTER_REPO`      | `chinu-codes/safe-prompt-llama-3_2-3b-lora` | HF repo containing LoRA adapters (+ custom handler) |
| `SEQ_LEN`           | `256`                                       | Max input tokens (smaller ⇒ lower RAM/latency)      |
| `MAX_NEW_TOKENS`    | `64`                                        | Generation ceiling for the redacted span            |
| `VALIDATE_MODE`     | `enforce`                                   | `off` | `warn` | `enforce` (see validators)         |
| `TORCH_NUM_THREADS` | `4`                                         | CPU threads for Torch                               |

The backend is **CPU-only** by default and loads adapters with:

* `device_map="cpu"`, `low_cpu_mem_usage=True`
* `torch.float16` for weight loading; if your CPU build errors on f16 ops, set `DTYPE` in `app.py` to `torch.float32` (uses more RAM).

---

## Validator “seatbelts” (optional but recommended)

Inside `backend/app.py` you’ll find pluggable validators:

```python
DETECTORS = [
    Detector("email", re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b"), "[EMAIL]"),
    Detector("phone", re.compile(r"\b(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}\b"), "[PHONE]"),
    # Add more: SSN, IPv4, credit cards, etc.
]
```

* `VALIDATE_MODE=enforce` (default): any leaked value is **replaced** with the placeholder
* `VALIDATE_MODE=warn`: leaks are **logged** but output is unchanged (good for evaluation)
* `VALIDATE_MODE=off`: LLM output is returned as-is

Add more detectors as you need (e.g., SSN, PAN, IP, IBAN, API keys).

---

## API

### `GET /health`

```json
{ "status": "ok", "device": "cpu", "threads": 4 }
```

### `POST /redact`

* **Body**: `{"text": "…raw input…"}` (+ optional `max_new_tokens`, `validate_mode`)
* **Returns**: `text/plain` — exactly one `<safe>…</safe>` block
* **Behavior**: mirrors the input text but replaces only **sensitive values** with placeholders

---

## Training summary

* **Base model**: `meta-llama/Llama-3.2-3B-Instruct` (instruct-tuned Llama 3.2, 3B)
* **Dataset**: `ai4privacy/pii-masking-200k` (English slice for SFT)

  * We format each example to a **strict chat template** where the assistant reply is **exactly** `<safe>{target_text}</safe>`.
* **Objective**: **completion-only loss** after the `<safe>` token (labels = `-100` before `<safe>`).
* **Method**: **LoRA** adapters (`r=16, α=32, dropout=0.05`) on attention projections (`q/k/v/o`).
* **Artifacts**: adapters saved to `./outputs/safe-prompt-3b-lora` and uploaded to:
  [https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora](https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora)

> The published HF repo includes a **custom `handler.py`** and `requirements.txt` so it can be used with **Hugging Face Inference Endpoints** (server-side) if you decide to host it later. Locally, we load the adapters directly in `backend/app.py`.

---

## Using the Hugging Face adapters

You can consume the published adapters in your own code:

```python
from transformers import AutoTokenizer
from peft import AutoPeftModelForCausalLM
from transformers import pipeline
import torch

repo_id = "chinu-codes/safe-prompt-llama-3_2-3b-lora"
base_id = "meta-llama/Llama-3.2-3B-Instruct"

tok = AutoTokenizer.from_pretrained(base_id, use_fast=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

model = AutoPeftModelForCausalLM.from_pretrained(
    repo_id, torch_dtype=torch.float16, device_map="cpu", low_cpu_mem_usage=True
).eval()

gen = pipeline("text-generation", model=model, tokenizer=tok)
```

If you later enable a **Hosted Inference Endpoint** on HF, the included `handler.py` accepts the standard payload:

```json
{ "inputs": "raw text to redact" }
```

…and returns a single `<safe>…</safe>` string.

---

## Performance notes

* **CPU-only** works for short prompts; reduce `SEQ_LEN` (e.g., 256) and `MAX_NEW_TOKENS` (e.g., 64) for better latency.
* If you hit OS “Killed” during load on small RAM systems:

  * keep `low_cpu_mem_usage=True`
  * set `DTYPE=torch.float32` only if your CPU build can’t use f16 loading (needs more RAM)
  * as a future enhancement, you can **merge adapters** and run a **GGUF** quantized model with `llama.cpp` locally.

---

## Security & privacy

* **Do not treat this as bullet-proof anonymization.** It’s a redaction helper; review output before sharing regulated data.
* The extension uses your **local** backend (no external calls). Clipboard operations stay on your machine.
* Consider disabling logs or setting `VALIDATE_MODE=enforce` in production to reduce accidental leaks to logs.

---


## Acknowledgements

* Adapters & handler published at: **[https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora](https://huggingface.co/chinu-codes/safe-prompt-llama-3_2-3b-lora)**
* Dataset: **ai4privacy/pii-masking-200k**
* Thanks to the open-source ecosystem: **Transformers, PEFT, Accelerate, FastAPI, Chrome MV3**.

---

## License
MIT.
