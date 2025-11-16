# SafePrompt

SafePrompt redacts PII in text by replacing only the sensitive spans with placeholders like `[FIRSTNAME]`, `[EMAIL]`, `[IPV4]`. It keeps everything else identical. The model’s final answer is always wrapped in `<safe> ... </safe>` so downstream code can trust the contract.

* **Model adapter**: [`chinu-codes/llama-3.2-3b-pii-redactor-lora`](https://huggingface.co/chinu-codes/llama-3.2-3b-pii-redactor-lora)
* **Base model**: `meta-llama/Llama-3.2-3B-Instruct`
* **Backend**: FastAPI, CPU-only inference with Transformers + PEFT
* **Extension**: Chrome MV3 right-click to redact selected text

---

## Project structure

```
SafePrompt/
├─ backend/
│  ├─ run.sh
│  └─ app/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ main.py
│     ├─ models.py
│     ├─ schemas.py
│     └─ service.py
├─ extension/
│   ├─ background.js
│   └─ manifest.json
└── model/
    └─ SafePrompt.ipynb  
```

Repo tree and file roles match the current codebase. 

---

## Quick start

### 1) Backend on CPU

Requirements: Python 3.10+, internet for the first run to download weights.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Set your Hugging Face token if the base model is gated:

```bash
export HF_TOKEN="hf_...your_token..."
```

Start the server with safe CPU defaults:

```bash
export BASE_MODEL="meta-llama/Llama-3.2-3B-Instruct"
export ADAPTER_REPO="chinu-codes/llama-3.2-3b-pii-redactor-lora"

# CPU hygiene
export SEQ_LEN=256
export MAX_NEW_TOKENS=64
export TORCH_NUM_THREADS=2
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export TOKENIZERS_PARALLELISM=false
export PYTORCH_NO_CUDA=1

uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Health check:

```bash
curl -s http://127.0.0.1:8000/health
```

Redaction:

```bash
curl -s -X POST http://127.0.0.1:8000/redact \
  -H "Content-Type: application/json" \
  -d '{"text":"Hi, I am Vishal Shinde. Email vishal@example.com and call +1 415 555 0199."}' | jq
```

Example response:

```json
{
  "safe_text": "<safe>Hi, I am [FIRSTNAME] [LASTNAME]. Email [EMAIL]</safe>",
  "redacted_text": "Hi, I am [FIRSTNAME] [LASTNAME]. Email [EMAIL]",
  "placeholders": ["FIRSTNAME","LASTNAME","EMAIL"],
  "base_model": "meta-llama/Llama-3.2-3B-Instruct",
  "adapter_repo": "chinu-codes/llama-3.2-3b-pii-redactor-lora",
  "seq_len": 256,
  "max_new_tokens": 64,
  "latency_ms": 1234
}
```

**Offline runs later:** once weights are cached locally you can set `HF_LOCAL_ONLY=true`.

#### Low-RAM tip

On laptops with 8–12 GB RAM, add a small swap file to avoid OOM during model load:

```bash
sudo fallocate -l 12G /swapfile2 || sudo dd if=/dev/zero of=/swapfile2 bs=1M count=12288 status=progress
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2
echo '/swapfile2 none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

### 2) Chrome extension (MV3)

1. Open `chrome://extensions`
2. Enable Developer mode
3. Load unpacked → choose the `extension/` folder
4. Select text on any page → right-click → **Redact with SafePrompt**

The extension posts to `http://127.0.0.1:8000/redact` and copies the redacted text to your clipboard. If injection is blocked, it opens a new tab with the result. The background script is already wired to the new JSON shape. 

---

## How it works

* The backend builds a short chat prompt that instructs the model to mirror the input and replace only PII spans with placeholders.
* The model replies inside `<safe> ... </safe>`.
* The API returns both `safe_text` and the inner `redacted_text`, plus a list of placeholders.

---

## Configuration

You can control behaviour with environment variables:

| Variable            | Default                                      | Purpose                                |
| ------------------- | -------------------------------------------- | -------------------------------------- |
| `BASE_MODEL`        | `meta-llama/Llama-3.2-3B-Instruct`           | Base model                             |
| `ADAPTER_REPO`      | `chinu-codes/llama-3.2-3b-pii-redactor-lora` | LoRA adapter repo                      |
| `SEQ_LEN`           | `512` (I used 256 on CPU)                    | Context length                         |
| `MAX_NEW_TOKENS`    | `96` (I used 64 on CPU)                      | Generation cap                         |
| `HF_TOKEN`          | empty                                        | HF token if base is gated              |
| `HF_LOCAL_ONLY`     | `false`                                      | Set to `true` after cache is populated |
| `TORCH_NUM_THREADS` | `2`                                          | Torch threads                          |
| `OMP_NUM_THREADS`   | `2`                                          | OpenMP threads                         |
| `MKL_NUM_THREADS`   | `2`                                          | MKL threads                            |

Values above match the backend code and scripts in this repo. 

---

## API

* `GET /health`
  Returns status, device, threads and model ids.

* `POST /redact`
  Request:

  ```json
  { "text": "raw input", "max_new_tokens": 64 }
  ```

  Response:

  ```json
  {
    "safe_text": "<safe>...</safe>",
    "redacted_text": "...",
    "placeholders": ["EMAIL","FIRSTNAME"],
    "base_model": "...",
    "adapter_repo": "...",
    "seq_len": 256,
    "max_new_tokens": 64,
    "latency_ms": 1234
  }
  ```

---

## Results

Small eval on 300 samples from the dataset:

* Exact match rate: ~0.67
* Placeholder micro-F1: ~0.90
* Formatting error rate: ~0.00

```I report both strict exact match and span-level F1. The exact match is intentionally harsh for redaction, as multiple placeholder choices can be equally safe. My span-level micro-F1 is around 0.90, with a 0.00 formatting error rate, which I believe better reflects utility and safety. In other words, even when the string isn't an exact character-for-character match, the PII is still correctly replaced, and the text is preserved.```

---

## Notes and limits

* English only for this adapter.
* If unsure, the model keeps the original span as designed.
* Very long inputs should be chunked client-side.
* Please handle personal data responsibly.

---

## Acknowledgements

* Base: `meta-llama/Llama-3.2-3B-Instruct`
* Dataset: `ai4privacy/pii-masking-200k`
* Adapter: [`chinu-codes/llama-3.2-3b-pii-redactor-lora`](https://huggingface.co/chinu-codes/llama-3.2-3b-pii-redactor-lora)

---

## Licence

MIT for the code in this repo. Follow the licences and usage terms of the base model and dataset.

---