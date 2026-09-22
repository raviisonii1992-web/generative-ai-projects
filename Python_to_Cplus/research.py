"""Compile-error memory and token/cost estimates for CppLift."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
MEMORY_PATH = GENERATED / "repair_memory.json"

# Known context windows (tokens). Live fetch can override.
MODEL_CONTEXT: dict[str, int] = {
    "gpt-5": 400_000,
    "gpt-5-mini": 400_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4o": 128_000,
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-haiku-4-5": 200_000,
    "gemini-3.5-flash-lite": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-3.1-flash-lite": 1_000_000,
    "grok-4": 256_000,
    "grok-4-fast-non-reasoning": 256_000,
    "openai/gpt-oss-120b": 131_072,
    "qwen/qwen3-32b": 131_072,
    "llama-3.3-70b-versatile": 131_072,
    "qwen/qwen3-coder-30b-a3b-instruct": 131_072,
    "deepseek/deepseek-chat": 64_000,
    "qwen2.5-coder": 32_768,
    "deepseek-coder-v2": 128_000,
    "gpt-oss:20b": 32_768,
    "llama3.2": 128_000,
}

# USD per 1M tokens (input, output). Local Ollama = 0.
_PRICE = (
    ("gpt-5-mini", (0.25, 2.0)),
    ("gpt-5", (5.0, 15.0)),
    ("gpt-4.1-mini", (0.4, 1.6)),
    ("gpt-4.1", (2.0, 8.0)),
    ("gpt-4o", (2.5, 10.0)),
    ("claude-haiku", (0.8, 4.0)),
    ("claude-sonnet", (3.0, 15.0)),
    ("gemini", (0.10, 0.40)),
    ("grok", (3.0, 15.0)),
    ("qwen", (0.15, 0.60)),
    ("deepseek", (0.28, 0.42)),
    ("llama", (0.0, 0.0)),
    ("gpt-oss", (0.0, 0.0)),
)


def context_tokens(model: str) -> int | None:
    name = (model or "").strip()
    if name in MODEL_CONTEXT:
        return MODEL_CONTEXT[name]
    stem = name.split(":")[0]
    if stem in MODEL_CONTEXT:
        return MODEL_CONTEXT[stem]
    for key, value in MODEL_CONTEXT.items():
        if key in name or name.startswith(key):
            return value
    return None


def set_context_tokens(model: str, n: int) -> None:
    if model and n and n > 0:
        MODEL_CONTEXT[(model or "").strip()] = int(n)


def _is_local(model: str) -> bool:
    low = (model or "").lower()
    return any(
        s in low
        for s in ("llama3", "qwen2.5-coder", "deepseek-coder", "gpt-oss:", "gemma")
    ) and "/" not in low


def lookup_price(model: str) -> tuple[float, float]:
    if _is_local(model):
        return 0.0, 0.0
    low = (model or "").lower()
    for key, pair in _PRICE:
        if key in low:
            return pair
    return 1.0, 3.0


def format_cost_line(model: str, prompt_tokens: int, completion_tokens: int, elapsed_s: float | None) -> str:
    pin, pout = lookup_price(model)
    cost = (prompt_tokens / 1e6) * pin + (completion_tokens / 1e6) * pout
    lat = f"{elapsed_s:.2f} s" if elapsed_s is not None else "—"
    total = prompt_tokens + completion_tokens
    if pin == 0 and pout == 0:
        money = "$0 (local)"
    else:
        money = f"~${cost:.4f} est."
    return (
        f"**Tokens consumed:** {total:,} ({prompt_tokens:,} in / {completion_tokens:,} out) · "
        f"**Latency:** {lat} · **Cost:** {money}"
    )


def token_bar_markdown(model: str, last: dict | None = None) -> str:
    ctx = context_tokens(model)
    ctx_s = f"{ctx:,} context" if ctx else "context unknown — click Refresh to fetch"
    if last and (last.get("prompt_tokens") or last.get("completion_tokens")):
        return f"`{model}` · {ctx_s} · " + format_cost_line(
            last.get("model") or model,
            int(last.get("prompt_tokens") or 0),
            int(last.get("completion_tokens") or 0),
            last.get("elapsed_s"),
        )
    return f"`{model}` · **{ctx_s} tokens**. Last conversion tokens appear here after Convert."


def _error_key(text: str) -> str:
    for line in (text or "").splitlines():
        if "error:" in line.lower() or "fatal" in line.lower():
            return line.strip()[:180]
    return (text or "").strip()[:180]


def remember_repair(compile_error: str, fixed_cpp: str) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    if MEMORY_PATH.is_file():
        try:
            items = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []
    items.append(
        {
            "key": _error_key(compile_error),
            "error": (compile_error or "")[-1500:],
            "fix_tail": (fixed_cpp or "")[-2500:],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    MEMORY_PATH.write_text(json.dumps(items[-40:], indent=2), encoding="utf-8")


def lookup_repairs(compile_error: str) -> str:
    if not MEMORY_PATH.is_file():
        return ""
    try:
        items = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    key = _error_key(compile_error).lower()
    hits = []
    for item in reversed(items):
        prev = (item.get("key") or "").lower()
        if prev and (prev in key or key in prev or prev[:32] in key):
            hits.append(item.get("fix_tail") or "")
        if len(hits) >= 2:
            break
    if not hits:
        return ""
    return "Previous successful repairs for a similar compiler error:\n\n" + "\n---\n".join(hits)
