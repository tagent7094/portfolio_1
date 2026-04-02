"""Smart rate limiting + batch sizing for LLM providers.

Handles:
- RPM (requests per minute) for cloud providers
- Context window limits for all providers
- Automatic batch size calculation
- Token estimation from text
- Adaptive throttling on 429 errors
"""

from __future__ import annotations

import sys
import time
import threading
from collections import deque
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════
# Provider specs: RPM limits, context windows, tokens/char ratio
# ══════════════════════════════════════════════════════════════

@dataclass
class ProviderSpec:
    """Rate and capacity specs for a provider/model combo."""
    rpm: int                    # requests per minute (0 = unlimited / local)
    context_window: int         # max tokens in context
    max_output_tokens: int      # max output tokens
    chars_per_token: float      # approximate chars per token (for estimation)
    is_local: bool = False      # local models have no RPM limit
    burst_limit: int = 0        # max concurrent requests (0 = no limit)


# Known specs per provider + model family
PROVIDER_SPECS: dict[str, dict[str, ProviderSpec]] = {
    "anthropic": {
        "_default": ProviderSpec(rpm=50, context_window=200000, max_output_tokens=8192, chars_per_token=4.0),
        "claude-opus-4-6": ProviderSpec(rpm=20, context_window=200000, max_output_tokens=32000, chars_per_token=4.0),
        "claude-sonnet-4-6": ProviderSpec(rpm=50, context_window=200000, max_output_tokens=16000, chars_per_token=4.0),
        "claude-haiku-4-5-20251001": ProviderSpec(rpm=100, context_window=200000, max_output_tokens=8192, chars_per_token=4.0),
    },
    "openai": {
        "_default": ProviderSpec(rpm=60, context_window=128000, max_output_tokens=4096, chars_per_token=4.0),
        "gpt-4o": ProviderSpec(rpm=60, context_window=128000, max_output_tokens=16384, chars_per_token=4.0),
        "gpt-4o-mini": ProviderSpec(rpm=200, context_window=128000, max_output_tokens=16384, chars_per_token=4.0),
        "o1": ProviderSpec(rpm=20, context_window=200000, max_output_tokens=32768, chars_per_token=4.0),
        "o3-mini": ProviderSpec(rpm=60, context_window=200000, max_output_tokens=16384, chars_per_token=4.0),
    },
    "gemini": {
        "_default": ProviderSpec(rpm=15, context_window=1000000, max_output_tokens=8192, chars_per_token=4.0),
        "gemini-2.5-flash": ProviderSpec(rpm=30, context_window=1000000, max_output_tokens=65536, chars_per_token=4.0),
        "gemini-2.5-pro": ProviderSpec(rpm=5, context_window=1000000, max_output_tokens=65536, chars_per_token=4.0),
        "gemini-2.0-flash": ProviderSpec(rpm=60, context_window=1000000, max_output_tokens=8192, chars_per_token=4.0),
    },
    "nvidia": {
        "_default": ProviderSpec(rpm=30, context_window=32000, max_output_tokens=4096, chars_per_token=4.0),
    },
    "lmstudio": {
        "_default": ProviderSpec(rpm=0, context_window=8192, max_output_tokens=2048, chars_per_token=4.0, is_local=True),
    },
    "ollama": {
        "_default": ProviderSpec(rpm=0, context_window=8192, max_output_tokens=2048, chars_per_token=4.0, is_local=True),
    },
}


def get_spec(provider: str, model: str = "") -> ProviderSpec:
    """Get the spec for a provider/model combo."""
    provider_specs = PROVIDER_SPECS.get(provider, PROVIDER_SPECS.get("lmstudio", {}))
    return provider_specs.get(model, provider_specs.get("_default", ProviderSpec(
        rpm=30, context_window=8192, max_output_tokens=2048, chars_per_token=4.0,
    )))


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    """Estimate token count from text length."""
    return max(1, int(len(text) / chars_per_token))


# ══════════════════════════════════════════════════════════════
# Rate Limiter — sliding window RPM tracker
# ══════════════════════════════════════════════════════════════

class RateLimiter:
    """Thread-safe sliding window rate limiter.

    Tracks request timestamps and blocks when RPM is exceeded.
    Adapts on 429 errors by reducing effective RPM.
    """

    def __init__(self, rpm: int, provider: str = "", model: str = ""):
        self.rpm = rpm
        self.effective_rpm = rpm
        self.provider = provider
        self.model = model
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_waits = 0
        self._backoff_until = 0.0

    def wait_if_needed(self):
        """Block until we can make a request within RPM limits."""
        if self.rpm <= 0:
            return  # No rate limit (local models)

        with self._lock:
            now = time.time()

            # Check backoff from 429
            if now < self._backoff_until:
                wait = self._backoff_until - now
                print(f"\033[33m[RateLimiter:{self.provider}]\033[0m Backoff: waiting {wait:.1f}s", file=sys.stderr, flush=True)
                time.sleep(wait)
                now = time.time()

            # Clean old timestamps (outside 60s window)
            while self._timestamps and self._timestamps[0] < now - 60:
                self._timestamps.popleft()

            # If at limit, wait until oldest request exits the window
            if len(self._timestamps) >= self.effective_rpm:
                wait = self._timestamps[0] + 60 - now + 0.1
                if wait > 0:
                    self._total_waits += 1
                    print(f"\033[33m[RateLimiter:{self.provider}]\033[0m RPM limit ({self.effective_rpm}/min) — waiting {wait:.1f}s ({self._total_requests} total requests)", file=sys.stderr, flush=True)
                    time.sleep(wait)

            self._timestamps.append(time.time())
            self._total_requests += 1

    def report_429(self):
        """Called when a 429 error is received — reduce effective RPM and backoff."""
        with self._lock:
            self.effective_rpm = max(1, int(self.effective_rpm * 0.7))
            self._backoff_until = time.time() + 30  # 30s backoff
            print(f"\033[31m[RateLimiter:{self.provider}]\033[0m 429 received! Reducing RPM to {self.effective_rpm}, backing off 30s", file=sys.stderr, flush=True)

    def report_success(self):
        """Called on successful request — slowly recover RPM."""
        with self._lock:
            if self.effective_rpm < self.rpm:
                self.effective_rpm = min(self.rpm, self.effective_rpm + 1)

    def stats(self) -> dict:
        return {
            "provider": self.provider,
            "rpm_limit": self.rpm,
            "effective_rpm": self.effective_rpm,
            "total_requests": self._total_requests,
            "total_waits": self._total_waits,
            "current_window": len(self._timestamps),
        }


# Global rate limiter instances (one per provider)
_limiters: dict[str, RateLimiter] = {}
_limiter_lock = threading.Lock()


def get_rate_limiter(provider: str, model: str = "") -> RateLimiter:
    """Get or create a rate limiter for a provider."""
    key = provider
    with _limiter_lock:
        if key not in _limiters:
            spec = get_spec(provider, model)
            _limiters[key] = RateLimiter(spec.rpm, provider, model)
        return _limiters[key]


# ══════════════════════════════════════════════════════════════
# Smart Batcher — calculates optimal batch size
# ══════════════════════════════════════════════════════════════

@dataclass
class BatchPlan:
    """Result of batch size calculation."""
    batch_size: int                # how many items per batch
    estimated_tokens_per_item: int # token estimate per item
    total_batches: int             # how many batches needed
    estimated_time_minutes: float  # estimated total time
    context_utilization: float     # 0-1 how much of context window is used
    rpm_limited: bool              # True if RPM is the bottleneck, False if context is
    reason: str                    # human-readable explanation


def calculate_batch_plan(
    items: list[str],
    prompt_template_chars: int,
    provider: str,
    model: str = "",
    max_output_tokens: int = 2000,
) -> BatchPlan:
    """Calculate optimal batch size based on context window + RPM.

    For cloud providers: balances context utilization with RPM to maximize throughput.
    For local providers: maximizes context utilization (RPM irrelevant).

    Args:
        items: List of text items to process
        prompt_template_chars: Size of the prompt template (without the items)
        provider: LLM provider name
        model: Model name
        max_output_tokens: Expected max output tokens per request
    """
    spec = get_spec(provider, model)
    n_items = len(items)

    if n_items == 0:
        return BatchPlan(1, 0, 0, 0, 0, False, "No items")

    # Estimate tokens per item
    avg_item_chars = sum(len(item) for item in items) / n_items
    tokens_per_item = estimate_tokens(str(avg_item_chars), spec.chars_per_token)
    template_tokens = estimate_tokens("x" * prompt_template_chars, spec.chars_per_token)

    # Available context for items (minus template + output reserve)
    available_context = spec.context_window - template_tokens - max_output_tokens - 500  # 500 token safety margin
    available_context = max(available_context, 1000)

    # Max items that fit in one context window
    max_by_context = max(1, int(available_context / max(tokens_per_item, 1)))

    if spec.is_local:
        # Local model: no RPM limit, maximize context utilization
        batch_size = min(max_by_context, n_items)
        total_batches = max(1, (n_items + batch_size - 1) // batch_size)
        # Estimate ~10s per request for local models
        est_time = total_batches * 10 / 60
        context_util = min(1.0, (tokens_per_item * batch_size) / available_context)

        return BatchPlan(
            batch_size=batch_size,
            estimated_tokens_per_item=tokens_per_item,
            total_batches=total_batches,
            estimated_time_minutes=round(est_time, 1),
            context_utilization=round(context_util, 2),
            rpm_limited=False,
            reason=f"Local model: {batch_size} items/batch (context={spec.context_window} tokens, {context_util:.0%} utilized)",
        )
    else:
        # Cloud model: balance context and RPM
        # Strategy: fit as many items as possible per request to minimize total requests
        # But don't exceed RPM when sending requests

        batch_size = min(max_by_context, n_items)
        total_batches = max(1, (n_items + batch_size - 1) // batch_size)

        # Time estimate based on RPM
        if spec.rpm > 0:
            requests_per_min = min(spec.rpm, total_batches)
            est_time = total_batches / requests_per_min
        else:
            est_time = total_batches * 3 / 60  # ~3s per request assumed

        context_util = min(1.0, (tokens_per_item * batch_size) / available_context)
        rpm_limited = total_batches > spec.rpm

        return BatchPlan(
            batch_size=batch_size,
            estimated_tokens_per_item=tokens_per_item,
            total_batches=total_batches,
            estimated_time_minutes=round(est_time, 1),
            context_utilization=round(context_util, 2),
            rpm_limited=rpm_limited,
            reason=f"Cloud ({provider}): {batch_size} items/batch, {total_batches} requests, RPM={spec.rpm} ({'RPM-limited' if rpm_limited else 'context-limited'})",
        )


def log_batch_plan(plan: BatchPlan):
    """Print batch plan to stderr."""
    color = "\033[33m" if plan.rpm_limited else "\033[36m"
    print(f"{color}[BatchPlan]\033[0m {plan.reason}", file=sys.stderr, flush=True)
    print(f"{color}[BatchPlan]\033[0m   batch_size={plan.batch_size}, batches={plan.total_batches}, est={plan.estimated_time_minutes}min, ctx_util={plan.context_utilization:.0%}", file=sys.stderr, flush=True)
