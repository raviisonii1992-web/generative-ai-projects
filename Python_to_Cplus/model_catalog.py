"""On-demand provider model lists and Artificial Analysis leaderboard."""

from __future__ import annotations

import html
import json
import os
import platform
import shutil
import subprocess
import threading
from collections.abc import Iterator
from typing import Any

import httpx

from converter import MODEL_LIFECYCLE, PROVIDERS, is_retired_model, keep_working_models, make_client
from research import set_context_tokens

AA_LEADERBOARD_URL = "https://artificialanalysis.ai/leaderboards/models"
AA_ENDPOINTS = (
    ("https://artificialanalysis.ai/api/v2/data/llms/models", {"prompt_length": "medium"}),
    ("https://artificialanalysis.ai/api/v2/language/models/free", {"prompt_type": "medium_coding"}),
    ("https://artificialanalysis.ai/api/v2/language/models", {"prompt_type": "medium_coding"}),
)


def _aa_key(override: str | None = None) -> str:
    return (
        (override or "").strip()
        or os.getenv("ARTIFICIAL_ANALYSIS_API_KEY", "").strip()
        or os.getenv("AA_API_KEY", "").strip()
    )


def _ssl_verify() -> bool | str:
    val = os.getenv("AA_SSL_VERIFY") or os.getenv("SSL_VERIFY")
    if val is not None and val.strip().lower() in ("0", "false", "no", "off"):
        return False
    bundle = (
        os.getenv("SSL_CERT_FILE")
        or os.getenv("REQUESTS_CA_BUNDLE")
        or os.getenv("CURL_CA_BUNDLE")
    )
    if bundle and os.path.isfile(bundle):
        return bundle
    return True

def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def parse_aa_models(payload: dict) -> list[dict]:
    items = payload.get("data") or payload.get("models") or []
    if isinstance(items, dict):
        items = items.get("data") or items.get("models") or []
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ev = item.get("evaluations") or {}
        pricing = item.get("pricing") or {}
        creator = item.get("model_creator") or {}
        if isinstance(creator, dict):
            creator_name = creator.get("name") or ""
        else:
            creator_name = str(creator or "")
        intel = _num(ev.get("artificial_analysis_intelligence_index") or item.get("intelligence_index"))
        coding = _num(ev.get("artificial_analysis_coding_index") or item.get("coding_index"))
        rows.append(
            {
                "model": item.get("name") or item.get("slug") or "",
                "creator": creator_name,
                "intelligence": intel,
                "coding": coding,
                "math": _num(ev.get("artificial_analysis_math_index")),
                "speed": _num(item.get("median_output_tokens_per_second")),
                "ttft": _num(item.get("median_time_to_first_token_seconds")),
                "in_price": _num(pricing.get("price_1m_input_tokens")),
                "out_price": _num(pricing.get("price_1m_output_tokens")),
            }
        )
    rows.sort(
        key=lambda r: (
            r["coding"] is None,
            -(r["coding"] or 0),
            r["intelligence"] is None,
            -(r["intelligence"] or 0),
        )
    )
    return rows


def fetch_aa_leaderboard(api_key: str | None = None) -> list[dict]:
    key = _aa_key(api_key)
    if not key:
        raise ValueError(
            "No Artificial Analysis key. Create one at https://artificialanalysis.ai "
            "and set ARTIFICIAL_ANALYSIS_API_KEY, or paste it in Scores key on Models."
        )
    last = ""
    verify = _ssl_verify()
    with httpx.Client(timeout=45.0, verify=verify) as client:
        for url, params in AA_ENDPOINTS:
            try:
                response = client.get(url, headers={"x-api-key": key}, params=params)
            except (httpx.ConnectError, httpx.RequestError) as exc:
                if "CERTIFICATE_VERIFY_FAILED" in str(exc) or "certificate verify failed" in str(exc):
                    raise RuntimeError(
                        f"SSL verification failed when connecting to Artificial Analysis ({url}). "
                        "This occurs behind corporate proxies, VPNs, or antivirus with HTTPS inspection. "
                        "Add 'SSL_VERIFY=false' or 'SSL_CERT_FILE=path/to/cert.pem' to your .env file."
                    ) from exc
                raise
            if response.status_code == 200:
                rows = parse_aa_models(response.json())
                if rows:
                    return rows
                last = f"{url} returned no models"
                continue
            last = f"{url} → HTTP {response.status_code}: {response.text[:240]}"
    raise RuntimeError(last or "Artificial Analysis request failed.")


def aa_dashboard_html(rows: list[dict] | None = None, error: str | None = None) -> str:
    intro = (
        '<div class="aa-dash">'
        "<h3>Model performance</h3>"
        "<p>Independent scores from "
        f'<a href="{AA_LEADERBOARD_URL}" target="_blank" rel="noopener">Artificial Analysis</a> '
        "(intelligence, coding, speed, price). Use this to pick a convert model. "
        "Nothing is fetched until you click <b>Load Artificial Analysis leaderboard</b>.</p>"
    )
    if error:
        return intro + f'<p class="aa-err">{error}</p></div>'
    if not rows:
        return (
            intro
            + "<p>Click <b>Load Artificial Analysis leaderboard</b> for a live table. "
            "Optional: set <code>ARTIFICIAL_ANALYSIS_API_KEY</code>.</p></div>"
        )
    top = rows[:12]
    cards = "".join(
        f'<div class="aa-card"><div class="aa-rank">#{i}</div>'
        f'<div class="aa-name">{r["model"]}</div>'
        f'<div class="aa-meta">{r["creator"] or "—"}</div>'
        f'<div class="aa-kpis">'
        f'<span>Coding {_fmt(r["coding"])}</span>'
        f'<span>IQ {_fmt(r["intelligence"])}</span>'
        f'<span>{_fmt(r["speed"])} tok/s</span>'
        f"</div></div>"
        for i, r in enumerate(top, 1)
    )
    body = "".join(
        "<tr>"
        f'<td>{i}</td><td>{r["model"]}</td><td>{r["creator"] or "—"}</td>'
        f'<td>{_fmt(r["intelligence"])}</td><td>{_fmt(r["coding"])}</td>'
        f'<td>{_fmt(r["math"])}</td><td>{_fmt(r["speed"])}</td>'
        f'<td>{_fmt(r["ttft"], 2)}</td>'
        f'<td>{_fmt(r["in_price"], 2)}</td><td>{_fmt(r["out_price"], 2)}</td>'
        "</tr>"
        for i, r in enumerate(rows[:50], 1)
    )
    return (
        intro
        + f'<div class="aa-cards">{cards}</div>'
        + "<p class=\"aa-note\">Sorted by coding index, then intelligence. Prices are USD / 1M tokens. "
        "Source: Artificial Analysis.</p>"
        + "<div class=\"aa-table-wrap\"><table class=\"aa-table\"><thead><tr>"
        "<th>#</th><th>Model</th><th>Creator</th><th>Intelligence</th><th>Coding</th>"
        "<th>Math</th><th>tok/s</th><th>TTFT (s)</th><th>$ in</th><th>$ out</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div></div>"
    )


def _filter_ids(provider: str, ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    skip = (
        "embed",
        "whisper",
        "tts",
        "dall-e",
        "moderation",
        "transcribe",
        "audio",
        "image",
        "realtime",
        "search",
        "codex",
        "davinci",
        "babbage",
        "deprecated",
    )
    for raw in ids:
        mid = (raw or "").strip()
        if mid.startswith("models/"):
            mid = mid[7:]
        low = mid.lower()
        if not mid or mid in seen or any(s in low for s in skip):
            continue
        if is_retired_model(mid):
            continue
        if provider == "OpenAI" and not any(
            low.startswith(p) for p in ("gpt-", "o1", "o3", "o4", "chatgpt")
        ):
            continue
        if provider == "Google Gemini" and "gemini" not in low:
            continue
        if provider == "Anthropic" and "claude" not in low:
            continue
        if provider == "xAI Grok" and "grok" not in low:
            continue
        seen.add(mid)
        out.append(mid)
    out.sort()
    return out


def _capture_context(model_id: str, obj: Any) -> None:
    n = None
    if isinstance(obj, dict):
        for key in ("context_window", "context_length", "max_model_len", "max_input_tokens"):
            raw = obj.get(key)
            if raw:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    continue
                break
        meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
        if n is None:
            raw = meta.get("context_length") or meta.get("max_context")
            if raw:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    n = None
    else:
        for attr in ("context_window", "max_model_len", "max_input_tokens"):
            raw = getattr(obj, attr, None)
            if raw:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    continue
                break
    if n:
        set_context_tokens(model_id, n)


def _compat_ids(provider: str, api_key: str | None) -> list[str]:
    client = make_client(provider, api_key)
    ids = []
    for item in client.models.list():
        mid = getattr(item, "id", "") or ""
        _capture_context(mid, item)
        ids.append(mid)
    return _filter_ids(provider, ids)


def _anthropic_ids(api_key: str | None) -> list[str]:
    key = (api_key or "").strip() or os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("No Anthropic API key")
    response = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        timeout=30.0,
    )
    response.raise_for_status()
    ids = []
    for item in response.json().get("data") or []:
        mid = item.get("id", "")
        _capture_context(mid, item)
        ids.append(mid)
    return _filter_ids("Anthropic", ids)


OLLAMA_HOST = "http://localhost:11434"
OLLAMA_PROVIDER = "Ollama (local)"
# (model id, roughly-needed RAM GB, why)
RECOMMENDED_LOCAL_MODELS = [
    ("llama3.2", 4, "Small general model if this machine is short on RAM."),
    ("qwen2.5-coder", 8, "Best default for Python → C++ on a laptop."),
    ("deepseek-coder-v2", 16, "Stronger coding model; larger download."),
    ("gpt-oss:20b", 24, "Large local model — only if you have plenty of RAM."),
]


def _ram_gb() -> float | None:
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)
            return int(out.strip()) / (1024**3)
        if system == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / (1024**2)
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys / (1024**3)
    except Exception:
        return None
    return None


def _install_ollama_help() -> str:
    system = platform.system()
    link = '<a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a>'
    if system == "Darwin":
        return f"Install Ollama from {link} or run <code>brew install ollama</code>."
    if system == "Windows":
        return f"Install Ollama from {link} or run <code>winget install Ollama.Ollama</code>."
    return (
        f"Install with <code>curl -fsSL https://ollama.com/install.sh | sh</code> or see {link}."
    )


def _ollama_ids() -> list[str]:
    response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
    response.raise_for_status()
    ids = [item.get("name", "") for item in response.json().get("models") or []]
    return _filter_ids(OLLAMA_PROVIDER, ids)


def probe_ollama() -> dict[str, Any]:
    binary = shutil.which("ollama") or ""
    version = ""
    if binary:
        try:
            version = subprocess.check_output(
                [binary, "--version"], text=True, timeout=5, stderr=subprocess.STDOUT
            ).strip()
        except Exception:
            version = ""
    running = False
    models: list[str] = []
    error = ""
    try:
        models = _ollama_ids()
        running = True
    except Exception as exc:
        error = str(exc)
    ram = _ram_gb()
    return {
        "binary": binary,
        "version": version,
        "running": running,
        "models": models,
        "error": error,
        "ram_gb": ram,
    }


def apply_installed_ollama(models: list[str]) -> None:
    if models:
        PROVIDERS[OLLAMA_PROVIDER]["models"] = models


def model_is_installed(model_id: str, installed: list[str]) -> bool:
    mid = (model_id or "").strip()
    return any(p == mid or p.startswith(mid + ":") or mid.startswith(p.split(":")[0]) for p in installed)


def parse_local_choice(label: str) -> str:
    text = (label or "").strip()
    if " · " in text:
        return text.split(" · ", 1)[0].strip()
    return text.split()[0] if text else ""


def local_choice_labels(probe: dict[str, Any]) -> tuple[list[str], str]:
    ram = probe.get("ram_gb")
    installed = probe.get("models") or []
    labels: list[str] = []
    default = ""
    suggested = ""
    seen: set[str] = set()
    for mid, min_gb, note in RECOMMENDED_LOCAL_MODELS:
        have = model_is_installed(mid, installed)
        fits = ram is None or ram >= min_gb - 0.5
        if have:
            tag = "already on this machine"
        elif fits:
            tag = "suggested for this machine"
        else:
            tag = f"needs ~{min_gb}+ GB RAM"
        label = f"{mid} · {note} [{tag}]"
        labels.append(label)
        seen.add(mid.split(":")[0])
        if have and not default:
            default = label
        if fits and not suggested:
            suggested = label
    for mid in installed:
        key = mid.split(":")[0]
        if key in seen or mid in seen:
            continue
        seen.add(key)
        labels.append(f"{mid} · already on this machine [installed]")
        if not default:
            default = labels[-1]
    return labels, default or suggested or (labels[0] if labels else "")


def local_panel_html(
    probe: dict[str, Any],
    *,
    phase: str = "idle",
    model_id: str = "",
    percent: float | None = None,
    detail: str = "",
    error: str = "",
    ready_model: str = "",
) -> str:
    ram = probe.get("ram_gb")
    ram_s = f"{ram:.0f} GB RAM" if isinstance(ram, (int, float)) else "RAM unknown"
    installed = probe.get("models") or []
    have_s = ", ".join(f"<code>{html.escape(m)}</code>" for m in installed) or "none yet"

    if not probe.get("binary"):
        head = (
            f"<p>Ollama is not installed ({html.escape(ram_s)}). "
            f"{_install_ollama_help()}</p>"
        )
    elif not probe.get("running"):
        head = (
            f"<p>Ollama is installed at <code>{html.escape(probe.get('binary') or '')}</code>, "
            f"but the server is not running ({html.escape(ram_s)}). "
            "Start it with <code>ollama serve</code>, then click <strong>Run locally</strong> again.</p>"
        )
    else:
        head = (
            f"<p>This machine: <strong>{html.escape(ram_s)}</strong>. "
            f"Already downloaded: {have_s}.</p>"
            "<p>Select a model below. If it is not on disk yet, CppLift will download it, "
            "then switch Provider to <strong>Ollama (local)</strong>.</p>"
        )

    window = ""
    if error:
        window = (
            '<div class="local-win local-err">'
            f"<strong>Download failed</strong><p>{html.escape(error)}</p></div>"
        )
    elif ready_model:
        window = (
            '<div class="local-win local-ready">'
            "<strong>Ready to use.</strong>"
            f"<p>Provider is now <code>{html.escape(OLLAMA_PROVIDER)}</code>, "
            f"model <code>{html.escape(ready_model)}</code>.</p>"
            "<p>Open <strong>Snippet</strong> and click <strong>Convert to C++</strong>. "
            "No cloud API key is required.</p></div>"
        )
    elif phase == "download":
        pct = 0 if percent is None else max(0, min(100, percent))
        bar = f"{pct:.0f}%"
        extra = f" · {html.escape(detail)}" if detail else ""
        window = (
            '<div class="local-win">'
            f'<div class="local-win-title">Downloading <code>{html.escape(model_id)}</code></div>'
            '<div class="local-bar"><div class="local-bar-fill" '
            f'style="width:{pct:.1f}%"></div></div>'
            f'<div class="local-pct">{html.escape(bar)}{extra}</div></div>'
        )
    elif phase == "stopped":
        extra = f"<p>{detail}</p>" if detail else ""
        window = (
            '<div class="local-win local-stopped">'
            "<strong>Download stopped and cleaned.</strong>"
            f"{extra}"
            "<p>Pick another model, or click <strong>Download &amp; use</strong> to start again.</p>"
            "</div>"
        )
    elif phase == "idle":
        window = (
            '<div class="local-win local-idle">'
            "Select a suggested model, then click <strong>Download &amp; use</strong>. "
            "You can <strong>Stop download &amp; clean</strong> at any time."
            "</div>"
        )

    return f'<div class="local-setup">{head}{window}</div>'


_pull_lock = threading.Lock()
_pull_stop = threading.Event()
_pull_client: httpx.Client | None = None
_pull_model = ""
_pull_last_note = ""


def delete_ollama_model(model_id: str) -> bool:
    mid = (model_id or "").strip()
    if not mid:
        return False
    names = [mid]
    if ":" not in mid:
        names.append(f"{mid}:latest")
    ok = False
    for name in names:
        try:
            response = httpx.request(
                "DELETE",
                f"{OLLAMA_HOST}/api/delete",
                json={"model": name, "name": name},
                timeout=30.0,
            )
            if response.status_code < 400:
                ok = True
        except Exception:
            pass
        binary = shutil.which("ollama")
        if binary:
            try:
                subprocess.run(
                    [binary, "rm", "-f", name],
                    check=False,
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
    return ok


def abort_ollama_pull(*, clean: bool = True) -> str:
    global _pull_client, _pull_model, _pull_last_note
    with _pull_lock:
        mid = _pull_model
        client = _pull_client
        _pull_stop.set()
        _pull_client = None
        _pull_model = ""
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    if not mid and client is None:
        return _pull_last_note or "Nothing was downloading."
    parts = ["Download stopped."]
    if clean and mid:
        if delete_ollama_model(mid):
            parts.append(f"Removed incomplete <code>{html.escape(mid)}</code> from this machine.")
        else:
            parts.append(
                f"No complete <code>{html.escape(mid)}</code> was installed. "
                "The interrupted pull will not be used."
            )
    elif mid:
        parts.append(f"Left <code>{html.escape(mid)}</code> as-is.")
    _pull_last_note = " ".join(parts)
    return _pull_last_note


def iter_ollama_pull(model_id: str) -> Iterator[dict[str, Any]]:
    global _pull_client, _pull_model
    payload = {"model": model_id, "name": model_id, "stream": True}
    timeout = httpx.Timeout(3600.0, connect=10.0)
    _pull_stop.clear()
    _pull_last_note = ""
    client = httpx.Client(timeout=timeout)
    with _pull_lock:
        _pull_client = client
        _pull_model = model_id
    try:
        with client.stream("POST", f"{OLLAMA_HOST}/api/pull", json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                yield {"done": True, "error": body or f"HTTP {resp.status_code}"}
                return
            try:
                for line in resp.iter_lines():
                    if _pull_stop.is_set():
                        yield {"done": True, "stopped": True}
                        return
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        yield {"status": line, "done": False}
                        continue
                    err = data.get("error")
                    if err:
                        yield {"done": True, "error": str(err)}
                        return
                    status = str(data.get("status") or "")
                    total = data.get("total") or 0
                    completed = data.get("completed") or 0
                    pct = None
                    detail = status
                    if total:
                        pct = 100.0 * float(completed) / float(total)
                        detail = f"{completed / (1024**3):.2f} / {total / (1024**3):.2f} GB · {status}"
                    done = status.lower() == "success"
                    yield {"done": done, "status": status, "percent": pct, "detail": detail}
                    if done:
                        return
            except (httpx.HTTPError, RuntimeError, OSError):
                if _pull_stop.is_set():
                    yield {"done": True, "stopped": True}
                    return
                raise
    finally:
        with _pull_lock:
            if _pull_client is client:
                _pull_client = None
            if not _pull_stop.is_set():
                _pull_model = ""
        try:
            client.close()
        except Exception:
            pass
    if _pull_stop.is_set():
        yield {"done": True, "stopped": True}
        return
    yield {"done": True, "status": "success", "percent": 100.0, "detail": "Download complete"}


def _openrouter_ids(api_key: str | None) -> list[str]:
    headers = {}
    key = (api_key or "").strip() or os.getenv("OPENROUTER_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    response = httpx.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=45.0)
    response.raise_for_status()
    ids = []
    for item in response.json().get("data") or []:
        mid = item.get("id", "")
        _capture_context(mid, item)
        ids.append(mid)
    return _filter_ids("OpenRouter", ids)


def fetch_provider_models(provider: str, api_key: str | None = None) -> list[str]:
    if provider == "Anthropic":
        return _anthropic_ids(api_key)
    if provider == "Ollama (local)":
        return _ollama_ids()
    if provider == "OpenRouter":
        try:
            return _compat_ids(provider, api_key)
        except Exception:
            return _openrouter_ids(api_key)
    return _compat_ids(provider, api_key)


def fetch_all_provider_models(current_provider: str, ui_key: str | None) -> str:
    """Update PROVIDERS[*]['models'] with ids still valid as of today. Opt-in only."""
    from datetime import date

    today = date.today()
    today_s = today.isoformat()
    lines = [f"Checked **{today_s}**. Retired ids are removed from the Model list."]
    how: list[str] = []
    seen_drop: set[str] = set()

    for name, spec in PROVIDERS.items():
        key = ui_key if name == current_provider else None
        try:
            ids = fetch_provider_models(name, key)
            kept, dropped = keep_working_models(ids, today)
            if kept:
                spec["models"] = kept
                lines.append(f"- **{name}**: {len(kept)} working model(s)")
            else:
                fallback, extra_drop = keep_working_models(spec.get("models") or [], today)
                spec["models"] = fallback
                dropped.extend(extra_drop)
                lines.append(
                    f"- **{name}**: catalog empty after retirement filter; kept {len(fallback)} built-in working id(s)"
                )
            for item in dropped:
                if item["id"] in seen_drop:
                    continue
                seen_drop.add(item["id"])
                how.append(
                    f"- `{item['id']}` retired {item['retired_on']} → use **`{item['use_instead']}`**. {item['how']}"
                )
        except Exception as exc:
            fallback, dropped = keep_working_models(spec.get("models") or [], today)
            spec["models"] = fallback
            lines.append(f"- **{name}**: kept {len(fallback)} working built-in id(s) — {exc}")
            for item in dropped:
                if item["id"] in seen_drop:
                    continue
                seen_drop.add(item["id"])
                how.append(
                    f"- `{item['id']}` retired {item['retired_on']} → use **`{item['use_instead']}`**. {item['how']}"
                )

    if how:
        lines.append("\n### Retired — how to keep the same kind of model")
        lines.extend(how)
    else:
        lines.append("\nNo known retired ids were in today's catalogs.")
    return "\n".join(lines)


SUGGESTION_CATEGORIES = [
    "Coding / Python → C++",
    "General intelligence",
    "Math / reasoning",
    "Speed (tokens/sec)",
    "Low latency (TTFT)",
    "Lowest cost",
    "Local (Ollama)",
]

_CREATOR_TO_APP = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "deepmind": "Google Gemini",
    "xai": "xAI Grok",
    "spacexai": "xAI Grok",
    "groq": "Groq",
}

_FALLBACK = {
    "Coding / Python → C++": [
        ("Claude Sonnet (latest)", "Anthropic", "Strong at code ports; good first pick for this app."),
        ("GPT-4.1 / GPT-4o", "OpenAI", "Reliable C++ structure and complete programs."),
        ("Gemini 2.5 Pro", "Google Gemini", "Long context if you convert a small repo."),
        ("Qwen coder (OpenRouter / Ollama)", "OpenRouter", "Cheaper or local coding specialist."),
    ],
    "General intelligence": [
        ("Latest Claude Opus / Sonnet", "Anthropic", "High overall AA intelligence index."),
        ("Latest GPT flagship", "OpenAI", "Broad reasoning and instruction following."),
        ("Gemini Pro class", "Google Gemini", "Strong multimodal and long-context generalist."),
    ],
    "Math / reasoning": [
        ("Reasoning models (o-series / high-effort Claude / Gemini)", "OpenAI", "Better for algorithmic correctness than tiny flash models."),
    ],
    "Speed (tokens/sec)": [
        ("Flash / Haiku / Groq-hosted", "Groq", "Fast tokens; quality is usually lower than Pro/Sonnet."),
    ],
    "Low latency (TTFT)": [
        ("Flash / Haiku / Groq", "Groq", "Smaller models start answering sooner."),
    ],
    "Lowest cost": [
        ("Mini / Flash / Haiku / OpenRouter open models", "OpenRouter", "Use for drafts; verify compile."),
        ("Ollama local", "Ollama (local)", "No API bill; quality depends on the pulled model."),
    ],
    "Local (Ollama)": [
        ("qwen2.5-coder", "Ollama (local)", "Best built-in default for this app."),
        ("deepseek-coder-v2", "Ollama (local)", "Code-focused local alternative."),
        ("llama3.2", "Ollama (local)", "General local chat; weaker at large C++ ports."),
    ],
}


def _app_provider(creator: str) -> str:
    low = (creator or "").lower()
    for needle, name in _CREATOR_TO_APP.items():
        if needle in low:
            return name
    return creator or "—"


def _sort_rows(category: str, rows: list[dict]) -> list[dict]:
    scored = [r for r in rows if r.get("model")]

    def key_coding(r):
        return (r["coding"] is None, -(r["coding"] or 0), -(r["intelligence"] or 0))

    def key_intel(r):
        return (r["intelligence"] is None, -(r["intelligence"] or 0))

    def key_math(r):
        return (r["math"] is None, -(r["math"] or 0), -(r["intelligence"] or 0))

    def key_speed(r):
        return (r["speed"] is None, -(r["speed"] or 0))

    def key_ttft(r):
        return (r["ttft"] is None, r["ttft"] or 1e9)

    def key_cost(r):
        blended = None
        if r["in_price"] is not None and r["out_price"] is not None:
            blended = r["in_price"] + r["out_price"]
        elif r["in_price"] is not None:
            blended = r["in_price"]
        return (blended is None, blended or 1e9)

    fn = {
        "Coding / Python → C++": key_coding,
        "General intelligence": key_intel,
        "Math / reasoning": key_math,
        "Speed (tokens/sec)": key_speed,
        "Low latency (TTFT)": key_ttft,
        "Lowest cost": key_cost,
    }.get(category, key_coding)
    scored.sort(key=fn)
    return scored


def _fallback_html(category: str, note: str = "") -> str:
    items = _FALLBACK.get(category) or _FALLBACK["Coding / Python → C++"]
    cards = "".join(
        f'<div class="aa-card"><div class="aa-name">{name}</div>'
        f'<div class="aa-meta">In this app: {prov}</div>'
        f"<p>{why}</p></div>"
        for name, prov, why in items
    )
    extra = f'<p class="aa-err">{note}</p>' if note else ""
    return (
        f'<div class="aa-dash"><h3>Best for: {category}</h3>'
        "<p>Built-in picks for this converter. Load Artificial Analysis for live ranks.</p>"
        f"{extra}<div class=\"aa-cards\">{cards}</div></div>"
    )


def suggestions_html(category: str, rows: list[dict] | None = None, error: str | None = None) -> str:
    if category == "Local (Ollama)":
        local = PROVIDERS.get("Ollama (local)", {}).get("models") or []
        extra = "".join(f"<li><code>{m}</code></li>" for m in local)
        return _fallback_html(category) + f"<p>Currently listed in the app:</p><ul>{extra}</ul>"

    if not rows:
        return _fallback_html(category, error or "")

    ranked = _sort_rows(category, rows)[:8]
    metric_label = {
        "Coding / Python → C++": "coding",
        "General intelligence": "intelligence",
        "Math / reasoning": "math",
        "Speed (tokens/sec)": "speed",
        "Low latency (TTFT)": "ttft",
        "Lowest cost": "in_price",
    }.get(category, "coding")
    cards = []
    for i, r in enumerate(ranked, 1):
        prov = _app_provider(r.get("creator") or "")
        score = _fmt(r.get(metric_label), 2 if metric_label in {"ttft", "in_price"} else 1)
        cards.append(
            f'<div class="aa-card"><div class="aa-rank">#{i}</div>'
            f'<div class="aa-name">{r["model"]}</div>'
            f'<div class="aa-meta">{r.get("creator") or "—"} · in this app: {prov}</div>'
            f'<div class="aa-kpis"><span>{metric_label} {score}</span>'
            f'<span>coding {_fmt(r.get("coding"))}</span>'
            f'<span>IQ {_fmt(r.get("intelligence"))}</span></div></div>'
        )
    why = {
        "Coding / Python → C++": "Ranked by Artificial Analysis coding index. Best starting point for Convert to C++.",
        "General intelligence": "Ranked by Intelligence Index.",
        "Math / reasoning": "Ranked by math index.",
        "Speed (tokens/sec)": "Higher output tok/s. Faster replies, not always better C++.",
        "Low latency (TTFT)": "Lower time-to-first-token.",
        "Lowest cost": "Lower input $/1M tokens (output shown in the full leaderboard).",
    }.get(category, "")
    err = f'<p class="aa-err">{error}</p>' if error else ""
    return (
        f'<div class="aa-dash"><h3>Best for: {category}</h3><p>{why} '
        f'Source: <a href="{AA_LEADERBOARD_URL}" target="_blank" rel="noopener">Artificial Analysis</a>.</p>'
        f"{err}<div class=\"aa-cards\">{''.join(cards)}</div></div>"
    )
