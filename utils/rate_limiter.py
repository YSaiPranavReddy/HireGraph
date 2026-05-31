"""
utils/rate_limiter.py — Groq API rate-limit aware retry logic

Groq free tier limits (as of 2025):
  llama-3.1-8b-instant   : 30 req/min, 20,000 TPM
  llama-3.3-70b-versatile: 30 req/min,  6,000 TPM

Strategy:
  - Retry up to 5 times on 429 / rate-limit errors
  - Exponential backoff starting at 5s, capped at 60s
  - Parse retry-after header from Groq's error message when available
  - All other exceptions are re-raised immediately (no silent swallowing)
"""

import time
import re
import logging
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger("hiregraph.rate_limiter")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if this exception is a Groq 429 / RESOURCE_EXHAUSTED."""
    msg = str(exc).lower()
    return (
        "429" in msg
        or "rate_limit" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
        or "retry_after" in msg
    )

# Public alias — used by critique.py for cross-model fallback logic
is_rate_limit_error = _is_rate_limit_error


def _parse_retry_after(exc: Exception) -> float:
    """
    Try to extract the retry-after delay (seconds) from Groq's error message.
    Falls back to 0 if not found (caller will use its own backoff).
    """
    msg = str(exc)
    # Groq embeds: "retryDelay': '26s'" or "Please retry in 26.8s"
    patterns = [
        r"retry[_\s]?after['\"\s:]+([0-9.]+)",
        r"retry in ([0-9.]+)s",
        r"retryDelay['\"\s:]+([0-9.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return 0.0


# ---------------------------------------------------------------------------
# Core retry function
# ---------------------------------------------------------------------------

def safe_invoke(llm, messages, max_retries: int = 5, base_wait: float = 5.0) -> Any:
    """
    Call llm.invoke(messages) with automatic retry on rate-limit errors.

    Args:
        llm:         LangChain LLM instance
        messages:    list of BaseMessage objects
        max_retries: max retry attempts (default 5)
        base_wait:   initial wait in seconds before first retry (default 5s)

    Returns:
        LLM response object

    Raises:
        The original exception after all retries are exhausted,
        or immediately for non-rate-limit errors.
    """
    last_exc = None

    for attempt in range(max_retries + 1):
        try:
            return llm.invoke(messages)

        except Exception as exc:
            if not _is_rate_limit_error(exc):
                # Not a rate-limit — re-raise immediately, no retry
                raise

            last_exc = exc

            if attempt == max_retries:
                # Exhausted retries
                break

            # Calculate wait time: prefer Groq's suggested delay, else exponential
            groq_wait    = _parse_retry_after(exc)
            backoff_wait = base_wait * (2 ** attempt)        # 5, 10, 20, 40, 60...
            wait_secs    = max(groq_wait, backoff_wait, 1.0)
            wait_secs    = min(wait_secs, 90.0)              # cap at 90s

            logger.warning(
                f"[Rate Limiter] 429 hit (attempt {attempt + 1}/{max_retries}). "
                f"Waiting {wait_secs:.1f}s before retry..."
            )
            print(
                f"  [Rate Limit] Attempt {attempt + 1}/{max_retries} — "
                f"waiting {wait_secs:.1f}s (Groq suggested: {groq_wait:.0f}s)..."
            )
            time.sleep(wait_secs)

    raise last_exc


# ---------------------------------------------------------------------------
# Decorator (optional — use safe_invoke directly in agents instead)
# ---------------------------------------------------------------------------

def with_rate_limit_retry(max_retries: int = 5, base_wait: float = 5.0):
    """
    Decorator that wraps a function returning llm.invoke() result with retry.
    Usage:

        @with_rate_limit_retry()
        def call_llm(llm, messages):
            return llm.invoke(messages)
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if not _is_rate_limit_error(exc):
                        raise
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    groq_wait = _parse_retry_after(exc)
                    wait_secs = max(groq_wait, base_wait * (2 ** attempt), 1.0)
                    wait_secs = min(wait_secs, 90.0)
                    print(f"  [Rate Limit] {fn.__name__} attempt {attempt+1}/{max_retries} — waiting {wait_secs:.1f}s...")
                    time.sleep(wait_secs)
            raise last_exc
        return wrapper
    return decorator
