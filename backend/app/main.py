import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .schemas import RedactIn, RedactOut, HealthOut
from .models import load_model, DEVICE
from .service import redact as redact_service

log = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="PII Redactor (LoRA) — CPU",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    try:
        load_model()
        log.info("Model and tokenizer loaded.")
    except Exception as e:
        log.exception("Failed to load model: %s", e)
        raise

@app.get("/health", response_model=HealthOut)
def health():
    return HealthOut(
        status="ok",
        device=str(DEVICE),
        threads=settings.NUM_THREADS,
        base_model=settings.BASE_MODEL,
        adapter_repo=settings.ADAPTER_REPO,
    )

@app.post("/redact", response_model=RedactOut)
def redact(req: RedactIn):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    try:
        out = redact_service(req.text, req.max_new_tokens)
        return RedactOut(
            safe_text=out["safe_text"],
            redacted_text=out["redacted_text"],
            placeholders=out["placeholders"],
            base_model=settings.BASE_MODEL,
            adapter_repo=settings.ADAPTER_REPO,
            seq_len=settings.SEQ_LEN,
            max_new_tokens=int(req.max_new_tokens or settings.MAX_NEW_TOKENS),
            latency_ms=out["latency_ms"],
        )
    except Exception as e:
        log.exception("Redaction failed: %s", e)
        raise HTTPException(status_code=500, detail="Redaction failed")
