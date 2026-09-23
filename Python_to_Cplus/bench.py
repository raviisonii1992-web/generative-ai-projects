"""Top-5 model ranking, run stats, and the performance chart."""

from __future__ import annotations

import csv
import html
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from converter import PROVIDERS
from model_catalog import OLLAMA_PROVIDER, fetch_aa_leaderboard, probe_ollama

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
LOG_PATH = GENERATED / "run_log.jsonl"

LANGUAGES = ["Python", "C", "C++", "Rust", "Go", "Java", "JavaScript", "TypeScript"]
HIGHLIGHT = {
    "Python": "python",
    "C": "c",
    "C++": "cpp",
    "Rust": "rust",
    "Go": "go",
    "Java": "java",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
}
SOURCE_FILE = {
    "Python": "main.py",
    "C": "main.c",
    "C++": "main.cpp",
    "Rust": "main.rs",
    "Go": "main.go",
    "Java": "Main.java",
    "JavaScript": "main.js",
    "TypeScript": "main.ts",
}

# Presets for "rank by". Order is accuracy, latency, output tokens, cost per run.
RANK_FACTORS = {
    "Balanced": (40, 25, 20, 15),
    "Output tokens": (10, 15, 60, 15),
    "Cost per run": (20, 10, 10, 60),
    "Latency": (15, 60, 10, 15),
    "Accuracy": (70, 10, 10, 10),
}

# accuracy 0-100, latency seconds, tokens, $ / run. Used when the leaderboard has no row.
_QUALITY = {
    "gpt-5": (90, 2.2, 2000, 0.035),
    "gpt-4.1": (84, 1.6, 1800, 0.012),
    "gpt-4o": (80, 1.4, 1600, 0.010),
    "claude-sonnet": (88, 2.0, 1900, 0.018),
    "claude-haiku": (76, 0.8, 1400, 0.004),
    "gemini-2.5-pro": (86, 2.4, 2100, 0.008),
    "gemini-2.5-flash": (78, 0.9, 1500, 0.001),
    "gemini": (74, 1.0, 1500, 0.001),
    "grok-4": (82, 1.5, 1700, 0.012),
    "qwen2.5-coder": (80, 6.0, 1800, 0.0),
    "deepseek-coder": (83, 8.0, 2000, 0.0),
    "llama3.2": (62, 4.0, 1600, 0.0),
    "gpt-oss": (70, 9.0, 1800, 0.0),
}

_CREATOR = (
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("google", "Google Gemini"),
    ("deepmind", "Google Gemini"),
    ("xai", "xAI Grok"),
    ("groq", "Groq"),
)


def keyed_cloud_providers() -> list[str]:
    ready = []
    for name, spec in PROVIDERS.items():
        env = spec.get("env")
        if env and os.getenv(env, "").strip():
            ready.append(name)
    return ready


def _quality(model: str) -> tuple[float, float, float, float]:
    low = (model or "").lower()
    for key, row in _QUALITY.items():
        if key in low:
            return row
    return (65.0, 2.0, 1800.0, 0.01)


def _provider_for_creator(creator: str) -> str:
    low = (creator or "").lower()
    for needle, name in _CREATOR:
        if needle in low:
            return name
    return ""


def _norm(values: list[float], higher_better: bool) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    out = []
    for value in values:
        score = (value - lo) / (hi - lo)
        out.append(score if higher_better else 1.0 - score)
    return out


def _candidates(mode: str, aa_key: str) -> tuple[list[dict], str]:
    if mode == "Local":
        probe = probe_ollama()
        names = list(probe.get("models") or [])[:5]
        if not names:
            names = list(PROVIDERS.get(OLLAMA_PROVIDER, {}).get("models") or [])[:5]
        rows = []
        for name in names:
            acc, lat, tok, cost = _quality(name)
            rows.append(
                {
                    "model": name,
                    "provider": OLLAMA_PROVIDER,
                    "accuracy": acc,
                    "latency": lat,
                    "tokens": tok,
                    "cost": cost,
                    "note": "Installed locally." if name in (probe.get("models") or []) else "Suggested local model.",
                }
            )
        note = "Ollama is running." if probe.get("running") else "Ollama is not running. Start it with `ollama serve`."
        return rows, note

    keyed = keyed_cloud_providers()
    if not keyed:
        return [], "No cloud API key in the environment. Add one to `.env`, or switch to Local."
    rows: list[dict] = []
    note = "Ranked from built-in estimates (no Artificial Analysis key)."
    try:
        board = fetch_aa_leaderboard(aa_key)
        for item in board:
            provider = _provider_for_creator(item.get("creator") or "")
            if provider not in keyed:
                continue
            acc = item.get("coding")
            if acc is None:
                acc = item.get("intelligence")
            if acc is None:
                acc = _quality(item.get("model") or "")[0]
            lat = item.get("ttft") if item.get("ttft") is not None else _quality(item.get("model") or "")[1]
            price = (item.get("in_price") or 0) * 0.0005 + (item.get("out_price") or 0) * 0.0015
            rows.append(
                {
                    "model": item.get("model") or "",
                    "provider": provider,
                    "accuracy": float(acc),
                    "latency": float(lat or 1),
                    "tokens": 1600.0,
                    "cost": float(price),
                    "note": item.get("creator") or provider,
                }
            )
            if len(rows) >= 8:
                break
        if rows:
            note = "Ranked from Artificial Analysis for providers with a key in `.env`."
    except Exception as exc:
        note = f"Leaderboard unavailable ({exc}). Using built-in estimates for keyed providers."
    if len(rows) < 5:
        have = {r["model"] for r in rows}
        for provider in keyed:
            for model in PROVIDERS.get(provider, {}).get("models") or []:
                if model in have:
                    continue
                acc, lat, tok, cost = _quality(model)
                rows.append(
                    {
                        "model": model,
                        "provider": provider,
                        "accuracy": acc,
                        "latency": lat,
                        "tokens": tok,
                        "cost": cost,
                        "note": provider,
                    }
                )
                have.add(model)
                if len(rows) >= 8:
                    break
    return rows, note


def rank_top5(mode: str, aa_key: str, w_acc: float, w_lat: float, w_tok: float, w_cost: float):
    raw, note = _candidates(mode, aa_key)
    if not raw:
        return f"<p>{html.escape(note)}</p>", [], note
    weights = [max(0.0, float(w or 0)) for w in (w_acc, w_lat, w_tok, w_cost)]
    total = sum(weights) or 1.0
    weights = [w / total for w in weights]
    acc_n = _norm([r["accuracy"] for r in raw], True)
    lat_n = _norm([r["latency"] for r in raw], False)
    tok_n = _norm([r["tokens"] for r in raw], False)
    cost_n = _norm([r["cost"] for r in raw], False)
    for row, a, b, c, d in zip(raw, acc_n, lat_n, tok_n, cost_n):
        row["score"] = 100.0 * (weights[0] * a + weights[1] * b + weights[2] * c + weights[3] * d)
    raw.sort(key=lambda r: -r["score"])
    top = raw[:5]
    cards = (
        "<p class='rank-note'><strong>Top "
        f"{len(top)}</strong> · accuracy {weights[0]:.0%}, latency {weights[1]:.0%}, "
        f"tokens {weights[2]:.0%}, cost {weights[3]:.0%}. {html.escape(note)}</p>"
    )
    labels = [f"{r['provider']} · {r['model']}" for r in top]
    return cards, labels, top


def pick_label(label: str, top: list[dict]):
    for row in top or []:
        if f"{row['provider']} · {row['model']}" == label:
            return row["provider"], row["model"]
    return None, None


_DOT = ["#10a37f", "#1a73e8", "#ea4335", "#f9ab00", "#9334e6", "#12b5cb", "#e8710a", "#202124"]


def _fmt_acc(value: float) -> str:
    if value <= 1:
        return f"{value:.0%}"
    return f"{value:.0f}"


def _tip(row: dict, extra: str = "") -> str:
    bits = [f"<b>{html.escape(str(row.get('model') or '—'))}</b>"]
    provider = row.get("provider") or ""
    if provider:
        bits.append(html.escape(str(provider)))
    if extra:
        bits.append(html.escape(extra))
    if row.get("score") is not None:
        bits.append(f"Score {float(row['score']):.0f}")
    if row.get("accuracy") is not None:
        bits.append(f"Accuracy {_fmt_acc(float(row['accuracy']))}")
    if row.get("latency") is not None:
        bits.append(f"Latency {float(row['latency']):.2f}s")
    if row.get("tokens") is not None:
        bits.append(f"Tokens {float(row['tokens']):.0f}")
    if row.get("cost") is not None:
        bits.append(f"Cost ${float(row['cost']):.4f}")
    note = row.get("note") or ""
    if note and note != provider:
        bits.append(html.escape(str(note)))
    return "<br>".join(bits)


def _span(lo: float, hi: float) -> tuple[float, float]:
    if hi == lo:
        return lo - 1, hi + 1
    pad = (hi - lo) * 0.12
    return lo - pad, hi + pad


def pareto_scatter(rows: list[dict]) -> str:
    """Small quality-vs-cost chart. Hover a dot for every metric."""
    points = [r for r in (rows or []) if (r.get("model") or "").strip()][:5]
    if not points:
        return (
            "<div class='oa-chart'><div class='oa-chart-title'>Quality vs cost</div>"
            "<p class='oa-empty-note'>Show top 5 to plot the five models.</p></div>"
        )
    xs = [math.log10(max(float(p.get("cost") or 0), 1e-4)) for p in points]
    ys = [float(p.get("accuracy") or 0) for p in points]
    lo_x, hi_x = _span(min(xs), max(xs))
    lo_y, hi_y = _span(min(ys), max(ys))
    lo_y = max(0, lo_y)

    def pct(cost: float, quality: float) -> tuple[float, float]:
        lx = math.log10(max(cost, 1e-4))
        x = (lx - lo_x) / (hi_x - lo_x) * 100
        y = (quality - lo_y) / (hi_y - lo_y) * 100
        return max(2, min(98, x)), max(4, min(96, y))

    ordered = sorted(points, key=lambda p: (max(float(p.get("cost") or 0), 1e-4), -float(p.get("accuracy") or 0)))
    frontier: list[dict] = []
    best_q = -1e9
    for point in ordered:
        q = float(point.get("accuracy") or 0)
        if q >= best_q - 1e-9:
            frontier.append(point)
            best_q = q
    band_x, band_y = pct(
        sorted(float(p.get("cost") or 0) for p in points)[len(points) // 2],
        sorted(float(p.get("accuracy") or 0) for p in points)[len(points) // 2],
    )
    svg = [
        "<svg class='oa-svg' viewBox='0 0 100 100' preserveAspectRatio='none'>",
        f"<rect x='0' y='{100 - band_y:.1f}' width='{band_x:.1f}' height='{band_y:.1f}' fill='#d9f5d6'/>",
    ]
    if len(frontier) >= 2:
        poly = " ".join(
            f"{pct(float(p.get('cost') or 0), float(p.get('accuracy') or 0))[0]:.1f},"
            f"{100 - pct(float(p.get('cost') or 0), float(p.get('accuracy') or 0))[1]:.1f}"
            for p in frontier
        )
        svg.append(f"<polyline fill='none' stroke='#71717a' stroke-dasharray='1.2 1.2' stroke-width='0.6' points='{poly}'/>")
    svg.append("</svg>")

    seen: list[str] = []
    dots = []
    for point in points:
        provider = str(point.get("provider") or "")
        if provider not in seen:
            seen.append(provider)
        color = _DOT[seen.index(provider) % len(_DOT)]
        x, y = pct(float(point.get("cost") or 0), float(point.get("accuracy") or 0))
        short = html.escape(str(point.get("model") or "")[:22])
        dots.append(
            f"<span class='oa-dot' style='left:{x:.1f}%;bottom:{y:.1f}%;background:{color}'>"
            f"<span class='oa-name'>{short}</span>"
            f"<span class='oa-tip'>{_tip(point)}</span></span>"
        )
    legend = "".join(
        f"<span><i style='background:{_DOT[i % len(_DOT)]}'></i>{html.escape(name[:16])}</span>"
        for i, name in enumerate(seen)
    )
    return (
        "<div class='oa-chart'>"
        "<div class='oa-chart-title'>Quality vs cost <span>top 5 · hover for metrics</span></div>"
        f"<div class='oa-plot'>{''.join(svg)}{''.join(dots)}</div>"
        f"<div class='oa-legend'>{legend}</div></div>"
    )


def chart_svg(rows: list[dict], metric: str) -> str:
    """Line chart of one KPI. Hover a point for every metric on that run."""
    metric = metric if metric in ("accuracy", "latency", "tokens", "cost") else "accuracy"
    if not rows:
        return (
            "<div class='oa-chart oa-line'><div class='oa-chart-title'>Runs</div>"
            "<p class='oa-empty-note'>Evaluate on Models. Hover a point for every metric.</p></div>"
        )
    models: list[str] = []
    for row in rows:
        if row["model"] not in models:
            models.append(row["model"])
    runs = [int(r["run"]) for r in rows]
    vals = [float(r[metric]) for r in rows]
    lo_x, hi_x = min(runs), max(runs)
    lo_y, hi_y = _span(min(vals), max(vals))

    def pct(run: int, value: float) -> tuple[float, float]:
        x = 50 if hi_x == lo_x else (run - lo_x) / (hi_x - lo_x) * 100
        y = (value - lo_y) / (hi_y - lo_y) * 100
        return max(2, min(98, x)), max(4, min(96, y))

    svg = ["<svg class='oa-svg' viewBox='0 0 100 100' preserveAspectRatio='none'>"]
    dots = []
    legend = []
    for i, model in enumerate(models):
        color = _DOT[i % len(_DOT)]
        pts = sorted((r for r in rows if r["model"] == model), key=lambda r: r["run"])
        coords = [pct(int(r["run"]), float(r[metric])) for r in pts]
        poly = " ".join(f"{x:.1f},{100 - y:.1f}" for x, y in coords)
        svg.append(f"<polyline fill='none' stroke='{color}' stroke-width='0.8' points='{poly}'/>")
        for row, (x, y) in zip(pts, coords):
            dots.append(
                f"<span class='oa-dot' style='left:{x:.1f}%;bottom:{y:.1f}%;background:{color}'>"
                f"<span class='oa-tip'>{_tip(row, 'Run ' + str(row['run']))}</span></span>"
            )
        legend.append(f"<span><i style='background:{color}'></i>{html.escape(model[:18])}</span>")
    svg.append("</svg>")
    return (
        "<div class='oa-chart oa-line'>"
        f"<div class='oa-chart-title'>{html.escape(metric)} by run <span>hover for all metrics</span></div>"
        f"<div class='oa-plot'>{''.join(svg)}{''.join(dots)}</div>"
        f"<div class='oa-legend'>{''.join(legend)}</div></div>"
    )


def summarize(rows: list[dict]) -> str:
    if not rows:
        return "No runs yet."
    by: dict[str, list[dict]] = {}
    for row in rows:
        by.setdefault(row["model"], []).append(row)
    lines = ["### Model-centric", ""]
    best_name = ""
    best_key = None
    for model, items in by.items():
        acc = [float(r["accuracy"]) for r in items]
        lat = [float(r["latency"]) for r in items]
        tok = [float(r["tokens"]) for r in items]
        cost = [float(r["cost"]) for r in items]
        mean_acc = sum(acc) / len(acc)
        mean_lat = sum(lat) / len(lat)
        mean_tok = sum(tok) / len(tok)
        mean_cost = sum(cost) / len(cost)
        var = sum((a - mean_acc) ** 2 for a in acc) / len(acc)
        n = len(items)
        per_min = 60.0 / mean_lat if mean_lat else 0
        lines.append(
            f"- **{model}** · accuracy mean {mean_acc:.0%} (var {var:.3f}) · "
            f"latency {mean_lat:.2f}s · tokens {mean_tok:.0f} · ${mean_cost:.4f}/run"
        )
        lines.append(
            f"  - business: ${mean_cost * n:.4f} for {n} runs · throughput {per_min:.1f} runs/min"
        )
        key = (mean_acc, -mean_lat, -mean_cost)
        if best_key is None or key > best_key:
            best_key = key
            best_name = model
    lines += ["", f"**Best after these runs:** {best_name} (higher accuracy, then lower time and cost)."]
    return "\n".join(lines)


def export_runs(rows: list[dict]) -> str:
    GENERATED.mkdir(parents=True, exist_ok=True)
    path = GENERATED / "bench_runs.csv"
    fields = ["model", "provider", "run", "accuracy", "latency", "tokens", "cost"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow(row)
    return str(path)


def append_log(entry: dict) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(), **entry}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
