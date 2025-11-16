import re
from typing import List
from .models import generate_safe, SAFE_OPEN, SAFE_CLOSE
from .config import settings

PLACEHOLDER_RE = re.compile(r"\[([A-Za-z0-9_]+)\]")

def extract_placeholders(text: str) -> List[str]:
    return [m.group(1) for m in PLACEHOLDER_RE.finditer(text or "")]

def redact(text: str, max_new_tokens: int | None = None):
    safe_text, inner, latency_ms = generate_safe(
        text,
        max_new_tokens or settings.MAX_NEW_TOKENS,
    )
    return {
        "safe_text": safe_text,
        "redacted_text": inner,
        "placeholders": extract_placeholders(inner),
        "latency_ms": latency_ms,
    }
