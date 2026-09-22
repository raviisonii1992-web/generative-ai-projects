"""CppLift Gradio UI: convert Python snippets and small repos to C++."""

from __future__ import annotations

import io
import os
import shlex
import shutil
import sys
import traceback
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

import re
import time

from compiler import (
    format_command,
    project_build_commands,
    snippet_compile_command,
    snippet_run_command,
    system_report,
)
from converter import (
    LAST_USAGE,
    PROVIDERS,
    collect_python_tree,
    convert_repo,
    convert_snippet,
    extract_zip,
    keep_working_models,
    parse_repo_files,
    repair_cpp,
    sanitize_cpp_source,
    write_repo,
)
from runner import kill_active, stream_command
from research import (
    format_cost_line,
    remember_repair,
    token_bar_markdown,
)
from model_catalog import (
    SUGGESTION_CATEGORIES,
    OLLAMA_PROVIDER,
    aa_dashboard_html,
    abort_ollama_pull,
    apply_installed_ollama,
    fetch_aa_leaderboard,
    fetch_all_provider_models,
    iter_ollama_pull,
    local_choice_labels,
    local_panel_html,
    model_is_installed,
    parse_local_choice,
    probe_ollama,
    suggestions_html,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parents[1] / ".env")
load_dotenv(ROOT / ".env", override=True)
GENERATED = ROOT / "generated"
SAMPLE_PYTHON = '''import time

def calculate(iterations, param1, param2):
    result = 1.0
    for i in range(1, iterations + 1):
        j = i * param1 - param2
        result -= 1 / j
        j = i * param1 + param2
        result += 1 / j
    return result

start_time = time.time()
result = calculate(50_000_000, 4, 1) * 4
end_time = time.time()

print(f"Result: {result:.12f}")
print(f"Execution Time: {(end_time - start_time):.6f} seconds")
'''

THEME = gr.themes.Soft(
    primary_hue="slate",
    secondary_hue="slate",
    neutral_hue="slate",
).set(
    body_background_fill="#ffffff",
    body_background_fill_dark="#0b0f19",
    block_background_fill="#ffffff",
    block_background_fill_dark="#111827",
    block_border_width="0px",
    block_shadow="none",
    button_primary_background_fill="#111827",
    button_primary_background_fill_hover="#000000",
    button_primary_text_color="#ffffff",
)

CSS = """
.gradio-container {
  max-width: 90vw !important;
  width: 90vw !important;
  margin: 0 auto !important;
  padding: 0 12px 32px !important;
}
.hf-bar {
  align-items: center !important;
  border-bottom: 1px solid #e5e7eb;
  margin: 0 -12px 18px -12px;
  padding: 8px 12px 0;
  background: #fff;
}
.hf-brand {
  min-width: 110px;
}
.hf-brand h1 {
  font-size: 1.2rem !important;
  letter-spacing: -0.04em;
  margin: 0 0 8px !important;
  font-weight: 800 !important;
  color: #0b0f19 !important;
}
.hf-brand p { display: none !important; }
.hf-nav {
  margin: 0 !important;
  padding: 0 !important;
  background: transparent !important;
}
.hf-nav > .form, .hf-nav > .block, .hf-nav fieldset {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
.hf-nav .wrap {
  display: flex !important;
  flex-wrap: nowrap !important;
  align-items: stretch;
  justify-content: flex-start;
  gap: 4px 18px !important;
  overflow: hidden;
}
.hf-nav label {
  display: inline-flex !important;
  align-items: center;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  padding: 12px 2px 10px !important;
  background: transparent !important;
  box-shadow: none !important;
  cursor: pointer;
  font-size: 15px !important;
  font-weight: 500 !important;
  color: #4b5563 !important;
  white-space: nowrap;
}
.hf-nav label:hover {
  color: #0b0f19 !important;
}
.hf-nav input {
  appearance: none !important;
  -webkit-appearance: none !important;
  width: 0 !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  position: absolute !important;
  opacity: 0 !important;
}
.hf-nav label:has(input:checked) {
  background: transparent !important;
  color: #0b0f19 !important;
  font-weight: 700 !important;
  border-bottom-color: #ffd21e !important;
}
.source-nav { margin: 2px 0 8px !important; }
.page-kicker {
  color: #6b7280 !important;
  font-size: 0.95rem !important;
  margin: 0 0 14px !important;
}
.model-bar, .workspace, .local-panel {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 4px 8px 8px;
  margin-bottom: 12px;
}
.model-bar .form, .model-bar .block {
  background: transparent !important;
  box-shadow: none !important;
}
.toolbar-actions button, .run-actions button { white-space: nowrap; }
.hint { font-size: 13px !important; color: #6b7280 !important; background: transparent !important; }
body[data-app-theme="dark"] .hf-bar {
  background: #0b0f19;
  border-bottom-color: #1f2937;
}
body[data-app-theme="dark"] .hf-brand h1 { color: #f9fafb !important; }
body[data-app-theme="dark"] .hf-nav label { color: #9ca3af !important; }
body[data-app-theme="dark"] .hf-nav label:hover,
body[data-app-theme="dark"] .hf-nav label:has(input:checked) { color: #f9fafb !important; }
body[data-app-theme="dark"] .model-bar,
body[data-app-theme="dark"] .workspace,
body[data-app-theme="dark"] .local-panel {
  background: #111827;
  border-color: #1f2937;
}
body[data-app-theme="dark"] .page-kicker,
body[data-app-theme="dark"] .hint { color: #9ca3af; }
.snippet-code {
  height: 52vh !important;
  max-height: 52vh !important;
  min-height: 420px !important;
  overflow: hidden !important;
}
.snippet-code .cm-editor,
.snippet-code .cm-scroller,
.snippet-code .monaco-editor,
.snippet-code .ace_editor,
.snippet-code textarea,
.snippet-code pre {
  height: 52vh !important;
  max-height: 52vh !important;
  min-height: 420px !important;
}
.snippet-code .cm-scroller,
.snippet-code .monaco-scrollable-element,
.snippet-code .ace_scrollbar,
.snippet-code textarea {
  overflow: auto !important;
}
.aa-dash { font-size: 14px; color: inherit; }
.aa-dash h3, .aa-dash p, .aa-dash li { color: inherit; }
.aa-dash a { color: #1d4ed8; }
.aa-err { color: #b91c1c; }
.aa-cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 16px; }
.aa-card {
  background: #f1f5f9;
  color: #0f172a;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  min-width: 180px;
  flex: 1;
}
.aa-rank { font-size: 12px; color: #475569; }
.aa-name { font-weight: 700; margin: 4px 0; color: #0f172a; }
.aa-meta { font-size: 12px; color: #334155; }
.aa-kpis { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; font-size: 12px; }
.aa-kpis span {
  background: #e2e8f0;
  color: #0f172a;
  padding: 2px 6px;
  border-radius: 6px;
}
.aa-table-wrap { overflow: auto; max-height: 420px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; }
.aa-table { width: 100%; border-collapse: collapse; font-size: 13px; color: #0f172a; }
.aa-table th { position: sticky; top: 0; background: #334155; color: #fff; text-align: left; padding: 8px; }
.aa-table td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; color: #0f172a; }
.aa-table tr:nth-child(even) { background: #f8fafc; }
.aa-table tr:nth-child(odd) { background: #fff; }
.aa-note { font-size: 12px; color: #475569; }

body[data-app-theme="dark"] .aa-dash a { color: #93c5fd; }
body[data-app-theme="dark"] .aa-err { color: #fca5a5; }
body[data-app-theme="dark"] .aa-card {
  background: #1e293b;
  color: #f1f5f9;
  border-color: #475569;
}
body[data-app-theme="dark"] .aa-rank { color: #94a3b8; }
body[data-app-theme="dark"] .aa-name { color: #f8fafc; }
body[data-app-theme="dark"] .aa-meta { color: #cbd5e1; }
body[data-app-theme="dark"] .aa-kpis span {
  background: #334155;
  color: #f1f5f9;
}
body[data-app-theme="dark"] .aa-table-wrap { border-color: #475569; background: #0f172a; }
body[data-app-theme="dark"] .aa-table { color: #e2e8f0; }
body[data-app-theme="dark"] .aa-table th { background: #020617; color: #f8fafc; }
body[data-app-theme="dark"] .aa-table td { border-bottom-color: #334155; color: #e2e8f0; }
body[data-app-theme="dark"] .aa-table tr:nth-child(even) { background: #1e293b; }
body[data-app-theme="dark"] .aa-table tr:nth-child(odd) { background: #0f172a; }
body[data-app-theme="dark"] .aa-note { color: #94a3b8; }

.local-setup { font-size: 14px; color: inherit; margin: 4px 0 8px; }
.local-setup p { margin: 0 0 10px; }
.local-win {
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 14px 16px;
  margin-top: 8px;
  min-height: 88px;
}
.local-win-title { font-weight: 700; margin-bottom: 10px; color: #f8fafc; }
.local-bar {
  height: 12px;
  background: #1e293b;
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid #334155;
}
.local-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #2563eb, #22c55e);
  width: 0%;
}
.local-pct { margin-top: 8px; font-size: 13px; color: #cbd5e1; }
.local-idle { background: #f8fafc; color: #334155; border-color: #cbd5e1; }
.local-ready {
  background: #ecfdf5;
  color: #065f46;
  border-color: #6ee7b7;
}
.local-ready code { background: #d1fae5; padding: 1px 6px; border-radius: 4px; }
.local-err {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}
.local-stopped {
  background: #fffbeb;
  color: #92400e;
  border-color: #fcd34d;
}
body[data-app-theme="dark"] .local-idle { background: #1e293b; color: #cbd5e1; border-color: #475569; }
body[data-app-theme="dark"] .local-ready { background: #064e3b; color: #d1fae5; border-color: #10b981; }
body[data-app-theme="dark"] .local-ready code { background: #065f46; }
body[data-app-theme="dark"] .local-err { background: #7f1d1d; color: #fecaca; border-color: #f87171; }
body[data-app-theme="dark"] .local-stopped { background: #78350f; color: #fde68a; border-color: #fbbf24; }
"""

THEME_JS = """
(mode) => {
  const dark = mode === "Dark";
  document.documentElement.classList.toggle("dark", dark);
  document.body.classList.toggle("dark", dark);
  document.body.setAttribute("data-app-theme", dark ? "dark" : "light");
  document.querySelectorAll(".gradio-container").forEach((el) => {
    el.classList.toggle("dark", dark);
  });
}
"""

PROGRAM_TIMER_RE = re.compile(r"Execution Time:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def resolved_models(provider: str, prefer: str | None = None) -> tuple[list[str], str | None]:
    models, _dropped = keep_working_models(PROVIDERS.get(provider, {}).get("models", []))
    value = models[0] if models else None
    if prefer and models:
        for mid in models:
            if mid == prefer or mid.startswith(prefer + ":"):
                return models, mid
        stem = prefer.split(":")[0]
        for mid in models:
            if mid.split(":")[0] == stem:
                return models, mid
    return models, value


def models_for(provider: str, prefer: str | None = None):
    models, value = resolved_models(provider, prefer)
    return gr.Dropdown(choices=models, value=value)


def key_placeholder(provider: str) -> str:
    spec = PROVIDERS.get(provider, {})
    env = spec.get("env")
    if not env:
        return "Ollama does not need a cloud API key"
    if os.getenv(env, ""):
        return f"{env} is already set in the environment (paste here only to override)"
    return f"Paste {env} or set it in a .env file"


def refresh_live_models(provider: str, api_key: str):
    status = fetch_all_provider_models(provider, api_key)
    models, chosen = resolved_models(provider)
    return gr.Dropdown(choices=models, value=chosen), status, token_bar_markdown(chosen or "", LAST_USAGE)


def token_info_for(model: str):
    return token_bar_markdown(model, LAST_USAGE)


def first_cloud_provider() -> str:
    for name in PROVIDERS:
        if name != OLLAMA_PROVIDER:
            return name
    return next(iter(PROVIDERS))


def _local_select_update(probe: dict):
    labels, default = local_choice_labels(probe)
    return gr.update(choices=labels, value=default)


def switch_source_tab(tab: str, provider: str):
    """Cloud vs Local extras. Provider and Model stay on the shared bar."""
    if tab == "Local":
        probe = probe_ollama()
        if probe.get("models"):
            apply_installed_ollama(probe["models"])
        models, chosen = resolved_models(OLLAMA_PROVIDER)
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=OLLAMA_PROVIDER),
            gr.Dropdown(choices=models, value=chosen),
            gr.update(placeholder=key_placeholder(OLLAMA_PROVIDER)),
            token_bar_markdown(chosen or "", LAST_USAGE),
            _local_select_update(probe),
            local_panel_html(probe, phase="idle"),
        )
    name = provider if provider != OLLAMA_PROVIDER else first_cloud_provider()
    models, chosen = resolved_models(name)
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(value=name),
        gr.Dropdown(choices=models, value=chosen),
        gr.update(placeholder=key_placeholder(name)),
        token_bar_markdown(chosen or "", LAST_USAGE),
        gr.update(),
        "",
    )


def on_provider_change(provider: str):
    local = provider == OLLAMA_PROVIDER
    if local:
        probe = probe_ollama()
        if probe.get("models"):
            apply_installed_ollama(probe["models"])
        models, chosen = resolved_models(provider)
        return (
            gr.Dropdown(choices=models, value=chosen),
            gr.Textbox(placeholder=key_placeholder(provider)),
            token_bar_markdown(chosen or "", LAST_USAGE),
            gr.update(value="Local"),
            gr.update(visible=False),
            gr.update(visible=True),
            _local_select_update(probe),
            local_panel_html(probe, phase="idle"),
        )
    models, chosen = resolved_models(provider)
    return (
        gr.Dropdown(choices=models, value=chosen),
        gr.Textbox(placeholder=key_placeholder(provider)),
        token_bar_markdown(chosen or "", LAST_USAGE),
        gr.update(value="Cloud"),
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(),
        "",
    )


def download_and_use_local(choice: str):
    mid = parse_local_choice(choice)
    probe = probe_ollama()
    empty = (gr.update(), gr.update(), gr.update())
    if not mid:
        yield gr.update(visible=True), gr.update(), local_panel_html(probe, error="Select a model first."), *empty
        return
    if not probe.get("binary") or not probe.get("running"):
        yield gr.update(visible=True), _local_select_update(probe), local_panel_html(probe, phase="idle"), *empty
        return

    if model_is_installed(mid, probe.get("models") or []):
        apply_installed_ollama(probe["models"])
        yield (
            gr.update(visible=True),
            _local_select_update(probe),
            local_panel_html(probe, ready_model=mid),
            gr.update(value=OLLAMA_PROVIDER),
            models_for(OLLAMA_PROVIDER, prefer=mid),
            gr.update(placeholder=key_placeholder(OLLAMA_PROVIDER)),
        )
        return

    last_pct = -1.0
    last_t = 0.0
    stopped = False
    yield (
        gr.update(visible=True),
        gr.update(),
        local_panel_html(probe, phase="download", model_id=mid, percent=0, detail="starting…"),
        *empty,
    )
    error = ""
    try:
        for event in iter_ollama_pull(mid):
            if event.get("stopped"):
                stopped = True
                break
            if event.get("error"):
                error = event["error"]
                break
            now = time.perf_counter()
            pct = event.get("percent")
            if pct is None:
                pct = last_pct if last_pct >= 0 else 0
            if event.get("done") or now - last_t > 0.35 or abs(pct - last_pct) >= 1:
                last_t = now
                last_pct = pct
                yield (
                    gr.update(visible=True),
                    gr.update(),
                    local_panel_html(
                        probe,
                        phase="download",
                        model_id=mid,
                        percent=pct,
                        detail=event.get("detail") or event.get("status") or "",
                    ),
                    *empty,
                )
            if event.get("done"):
                break
    except GeneratorExit:
        abort_ollama_pull(clean=True)
        raise
    if stopped:
        note = abort_ollama_pull(clean=True)
        fresh = probe_ollama()
        yield (
            gr.update(visible=True),
            _local_select_update(fresh),
            local_panel_html(fresh, phase="stopped", model_id=mid, detail=note),
            *empty,
        )
        return
    if error:
        yield gr.update(visible=True), _local_select_update(probe), local_panel_html(probe, error=error), *empty
        return

    fresh = probe_ollama()
    ids = fresh.get("models") or [mid]
    if mid not in ids and not model_is_installed(mid, ids):
        ids = [mid] + ids
    apply_installed_ollama(ids)
    yield (
        gr.update(visible=True),
        _local_select_update(fresh),
        local_panel_html(fresh, ready_model=mid),
        gr.update(value=OLLAMA_PROVIDER),
        models_for(OLLAMA_PROVIDER, prefer=mid),
        gr.update(placeholder=key_placeholder(OLLAMA_PROVIDER)),
    )


def stop_local_download():
    note = abort_ollama_pull(clean=True)
    probe = probe_ollama()
    return (
        gr.update(visible=True),
        _local_select_update(probe),
        local_panel_html(probe, phase="stopped", detail=note),
        gr.update(),
        gr.update(),
        gr.update(),
    )


def refresh_system():
    return (
        system_report(),
        format_command(snippet_compile_command()),
        format_command(snippet_run_command()),
    )


def load_aa_dashboard(aa_key: str):
    try:
        rows = fetch_aa_leaderboard(aa_key)
        return aa_dashboard_html(rows), rows
    except Exception as exc:
        return aa_dashboard_html(error=str(exc)), []


def show_cached_suggestions(category: str, cached_rows: list | None):
    return suggestions_html(category, cached_rows or None)


def load_suggestions(category: str, aa_key: str, cached_rows: list | None):
    if category == "Local (Ollama)":
        return suggestions_html(category), cached_rows or []
    rows = cached_rows or []
    err = None
    if not rows:
        try:
            rows = fetch_aa_leaderboard(aa_key)
        except Exception as exc:
            err = str(exc)
            rows = []
    return suggestions_html(category, rows or None, err), rows


def show_section(name: str):
    need_model = name in ("Snippet", "Repo")
    return (
        gr.update(visible=need_model),
        gr.update(visible=name == "Snippet"),
        gr.update(visible=name == "Repo"),
        gr.update(visible=name == "System"),
        gr.update(visible=name == "Scores"),
        gr.update(visible=name == "Suggest"),
    )


def parse_cmd(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Compile/run command is empty.")
    posix = os.name != "nt"
    return shlex.split(text, posix=posix)


def run_python_process(code: str, timeout: float = 600):
    GENERATED.mkdir(parents=True, exist_ok=True)
    src = GENERATED / "_snippet.py"
    src.write_text(code, encoding="utf-8")
    return stream_command([sys.executable, "-u", str(src)], cwd=GENERATED, timeout=timeout)


def run_python(code: str):
    if not (code or "").strip():
        yield "Paste Python first."
        return
    text = ""
    elapsed = 0.0
    rc: int | None = 1
    for text, done, rc, elapsed in run_python_process(code):
        suffix = ""
        if done:
            suffix = f"\n\n[wall time {elapsed:.4f}s]"
            if rc not in (0, None):
                suffix += "  (stopped or failed)" if rc and rc < 0 else f"  (exit {rc})"
        yield (text or "") + suffix


def _program_timer(text: str) -> float | None:
    match = PROGRAM_TIMER_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _fmt(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 0.001:
        return f"{seconds * 1e6:.0f} µs"
    if seconds < 1:
        return f"{seconds * 1000:.2f} ms"
    return f"{seconds:.4f} s"


def timing_markdown(
    py_wall: float | None,
    py_prog: float | None,
    compile_s: float | None,
    cpp_runs: list[float],
    cpp_prog: float | None,
    note: str = "",
) -> str:
    cpp_wall = min(cpp_runs) if cpp_runs else None
    py_ref = py_prog if py_prog is not None else py_wall
    cpp_ref = cpp_prog if cpp_prog is not None else cpp_wall
    speedup = None
    if py_ref and cpp_ref and cpp_ref > 0:
        speedup = py_ref / cpp_ref
    repeats = ", ".join(_fmt(x) for x in cpp_runs) if cpp_runs else "—"
    speedup_cell = f"**{speedup:.1f}×**" if speedup else "—"
    extra = f"\n\n{note}" if note else ""
    cost = ""
    if LAST_USAGE.get("prompt_tokens") or LAST_USAGE.get("completion_tokens"):
        cost = "\n\n" + format_cost_line(
            LAST_USAGE.get("model") or "",
            int(LAST_USAGE.get("prompt_tokens") or 0),
            int(LAST_USAGE.get("completion_tokens") or 0),
            LAST_USAGE.get("elapsed_s"),
        )
    return f"""### Timing comparison

| | Python | C++ |
|---|---|---|
| Wall clock (process) | {_fmt(py_wall)} | {_fmt(cpp_wall)} |
| Program timer (`Execution Time`) | {_fmt(py_prog)} | {_fmt(cpp_prog)} |
| Compile | — | {_fmt(compile_s)} |
| C++ repeats | — | {repeats} |
| Speedup (Python ÷ C++) | {speedup_cell} | |

Wall clock includes interpreter / process startup. The program timer is the `Execution Time` line if the code prints one. Speedup uses the program timer when both sides print it, otherwise wall clock.{cost}{extra}
"""


def _compile_main_cpp(compile_cmd: list[str]):
    header = f"$ {format_command(compile_cmd)}\n"
    compile_log = ""
    compile_s = None
    code = 1
    for compile_log, done, code, compile_s in stream_command(compile_cmd, cwd=GENERATED, timeout=180):
        yield header + compile_log, done, code, compile_s
        if done:
            return


MAX_REPAIR_PASSES = 4


def _maybe_repair_cpp(cpp, compile_log, compile_cmd, provider, model, api_key):
    if not provider or not model:
        return cpp, False, ""
    try:
        fixed = repair_cpp(
            provider,
            model,
            api_key,
            cpp,
            compile_log,
            format_command(compile_cmd),
        )
    except Exception as exc:
        return cpp, False, f"\nAuto-repair failed: {exc}"
    if not (fixed or "").strip() or fixed.strip() == (cpp or "").strip():
        return cpp, False, "\nAuto-repair did not change the source."
    return sanitize_cpp_source(fixed), True, ""


def _compile_with_feedback(cleaned, compile_cmd, provider, model, api_key):
    """Compile; on failure send compiler output back to the LLM until it compiles or retries run out."""
    last_error = ""
    log = ""
    compile_s = None
    code = 1
    for attempt in range(MAX_REPAIR_PASSES + 1):
        (GENERATED / "main.cpp").write_text(cleaned, encoding="utf-8")
        status = "Compiling…" if attempt == 0 else f"Recompiling after repair {attempt}/{MAX_REPAIR_PASSES}…"
        for log, done, code, compile_s in _compile_main_cpp(compile_cmd):
            yield cleaned, log, compile_s, code, status, False
            if done:
                break
        if code == 0:
            if attempt and last_error:
                remember_repair(last_error, cleaned)
            yield cleaned, log, compile_s, 0, "Compile succeeded.", True
            return
        last_error = log
        if attempt >= MAX_REPAIR_PASSES or not provider:
            yield cleaned, log, compile_s, code, "Compile failed.", True
            return
        yield (
            cleaned,
            log + f"\nCompile failed. Sending the error back to the model "
            f"(repair {attempt + 1}/{MAX_REPAIR_PASSES})…",
            compile_s,
            code,
            "Repairing C++…",
            False,
        )
        cleaned, repaired, note = _maybe_repair_cpp(
            cleaned, log, compile_cmd, provider, model, api_key
        )
        if not repaired:
            yield cleaned, log + (note or ""), compile_s, code, "Compile failed.", True
            return


def compile_and_run_snippet(
    cpp: str,
    compile_text: str,
    run_text: str,
    repeats: float = 1,
    provider: str = "",
    model: str = "",
    api_key: str = "",
):
    if not (cpp or "").strip():
        yield "No C++ to compile. Convert Python first.", "Convert Python first.", cpp or ""
        return
    GENERATED.mkdir(parents=True, exist_ok=True)
    cleaned = sanitize_cpp_source(cpp)
    (GENERATED / "main.cpp").write_text(cleaned, encoding="utf-8")
    try:
        compile_cmd = parse_cmd(compile_text)
        run_cmd = parse_cmd(run_text)
    except ValueError as exc:
        yield str(exc), str(exc), cleaned
        return

    log = ""
    compile_s = None
    code = 1
    for cleaned, log, compile_s, code, status, finished in _compile_with_feedback(
        cleaned, compile_cmd, provider, model, api_key
    ):
        yield log, status, cleaned
        if finished:
            break
    if code:
        yield log + f"\nCompile failed (exit {code}) after error-feedback repairs.", "Compile failed.", cleaned
        return

    n = max(1, int(repeats or 1))
    run_times: list[float] = []
    last_out = ""
    for i in range(n):
        run_header = f"\n\n$ {format_command(run_cmd)}   # run {i + 1}/{n}\n"
        log += run_header
        chunk = ""
        rc = 1
        elapsed = 0.0
        for chunk, done, rc, elapsed in stream_command(run_cmd, cwd=GENERATED, timeout=180):
            yield log + chunk, f"Running C++ ({i + 1}/{n})…", cleaned
            if done:
                break
        log += chunk or ""
        if rc:
            yield log + f"\nRun failed (exit {rc})", "Run failed.", cleaned
            return
        run_times.append(elapsed)
        last_out = chunk or ""

    md = timing_markdown(
        py_wall=None,
        py_prog=None,
        compile_s=compile_s,
        cpp_runs=run_times,
        cpp_prog=_program_timer(last_out),
        note="Python column is empty until you use **Run both & compare**.",
    )
    yield log or "(no stdout)", md, cleaned


def compare_snippet(
    python_code: str,
    cpp: str,
    compile_text: str,
    run_text: str,
    repeats: float,
    provider: str = "",
    model: str = "",
    api_key: str = "",
):
    if not (python_code or "").strip():
        yield "Paste Python first.", "No C++ yet.", "Paste Python first.", cpp or ""
        return
    if not (cpp or "").strip():
        yield "", "Convert to C++ first.", "Convert to C++ first.", cpp or ""
        return

    py_text = ""
    py_wall = 0.0
    py_ok = True
    cleaned = sanitize_cpp_source(cpp)
    for py_text, done, rc, py_wall in run_python_process(python_code):
        py_shown = py_text or ""
        if done:
            py_shown = f"{py_shown.rstrip()}\n\n[wall time {py_wall:.4f}s]"
            py_ok = rc == 0
        yield py_shown, "Running Python…", "Running Python… Stop anytime.", cleaned
        if done:
            break
    py_shown = f"{(py_text or '').rstrip()}\n\n[wall time {py_wall:.4f}s]"
    if not py_ok:
        yield py_shown, "", "Python did not finish successfully; C++ was not run.", cleaned
        return
    yield py_shown, "Compiling C++…", "Python finished. Compiling C++…", cleaned

    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "main.cpp").write_text(cleaned, encoding="utf-8")
    try:
        compile_cmd = parse_cmd(compile_text)
        run_cmd = parse_cmd(run_text)
    except ValueError as exc:
        yield py_shown, str(exc), str(exc), cleaned
        return

    cpp_log = ""
    compile_s = None
    code = 1
    for cleaned, cpp_log, compile_s, code, status, finished in _compile_with_feedback(
        cleaned, compile_cmd, provider, model, api_key
    ):
        yield py_shown, cpp_log, status, cleaned
        if finished:
            break
    if code:
        yield py_shown, cpp_log + f"\nCompile failed (exit {code}) after error-feedback repairs.", "Compile failed.", cleaned
        return

    n = max(1, int(repeats or 1))
    run_times: list[float] = []
    last_out = ""
    for i in range(n):
        cpp_log += f"\n\n$ {format_command(run_cmd)}   # run {i + 1}/{n}\n"
        chunk = ""
        rc = 1
        elapsed = 0.0
        for chunk, done, rc, elapsed in stream_command(run_cmd, cwd=GENERATED, timeout=180):
            yield py_shown, cpp_log + chunk, f"Running C++ ({i + 1}/{n})…", cleaned
            if done:
                break
        cpp_log += chunk or ""
        if rc:
            yield py_shown, cpp_log + f"\nRun failed (exit {rc})", "Run failed.", cleaned
            return
        run_times.append(elapsed)
        last_out = chunk or ""

    md = timing_markdown(
        py_wall=py_wall,
        py_prog=_program_timer(py_text),
        compile_s=compile_s,
        cpp_runs=run_times,
        cpp_prog=_program_timer(last_out),
    )
    yield py_shown, cpp_log, md, cleaned


def format_llm_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "model_not_found" in low or "deprecated" in low or "does not exist" in low or "no longer available" in low or "not_found" in low:
        return (
            "This is not a converter bug. The provider rejected the **model id** "
            "(missing, renamed, or deprecated). "
            "`gpt-5-codex` is retired — use `gpt-4.1` / `gpt-4o` / `gpt-5-mini`. "
            "`gemini-2.5-flash-lite` is retired for new Google users — use `gemini-3.5-flash-lite`. "
            f"Provider message:\n{text}"
        )
    return f"Conversion failed: {exc}"


def convert_snippet_ui(python_code, provider, model, api_key):
    if not (python_code or "").strip():
        yield "Paste Python on the left first.", "Paste Python first.", token_bar_markdown(model, LAST_USAGE)
        return
    try:
        result = ""
        yield "", "Converting…", token_bar_markdown(model, LAST_USAGE)
        for result in convert_snippet(provider, model, api_key, python_code):
            yield result, "Converting…", token_bar_markdown(model, LAST_USAGE)
        cost = format_cost_line(
            LAST_USAGE.get("model") or model,
            int(LAST_USAGE.get("prompt_tokens") or 0),
            int(LAST_USAGE.get("completion_tokens") or 0),
            LAST_USAGE.get("elapsed_s"),
        )
        yield result, f"**Done.** C++ conversion finished.\n\n{cost}", token_bar_markdown(model, LAST_USAGE)
    except Exception as exc:
        yield format_llm_error(exc), "Conversion failed.", token_bar_markdown(model, LAST_USAGE)


def _repo_source_dir(repo_path: str, zip_file) -> Path:
    if zip_file:
        dest = GENERATED / "python_upload" / Path(str(zip_file)).stem
        dest.mkdir(parents=True, exist_ok=True)
        return extract_zip(str(zip_file), dest)
    path = Path(repo_path or "").expanduser()
    if not path.is_dir():
        raise ValueError("Enter a local folder path, or upload a .zip of the Python repo.")
    return path


def convert_repo_ui(repo_path, zip_file, provider, model, api_key):
    try:
        root = _repo_source_dir(repo_path, zip_file)
        blob, files = collect_python_tree(root)
        if not files:
            yield "No .py files found in that repo.", "", ""
            return
        acc = ""
        for acc in convert_repo(provider, model, api_key, blob, files):
            yield acc, "", "Streaming model output…"
        dest = GENERATED / "cpp_project"
        if dest.exists():
            shutil.rmtree(dest)
        parsed = parse_repo_files(acc)
        write_repo(parsed, dest)
        cmds = project_build_commands(dest)
        configure = format_command(cmds["configure"]) if cmds["configure"] else "(not needed)"
        summary = (
            f"Wrote {len(parsed)} file(s) to {dest}\n"
            f"Python files used: {', '.join(files)}\n\n"
            f"Configure: {configure}\n"
            f"Build:     {format_command(cmds['build'])}\n"
            f"Run:       {format_command(cmds['run'])}\n"
        )
        preview = "\n\n".join(f"// --- {rel} ---\n{body}" for rel, body in list(parsed.items())[:8])
        yield preview, str(dest), summary
    except Exception as exc:
        yield f"Repo conversion failed: {format_llm_error(exc)}", "", traceback.format_exc()


def build_repo(project_dir: str, repeats: float = 1):
    dest = Path(project_dir or GENERATED / "cpp_project")
    if not dest.is_dir():
        yield "No generated C++ project yet."
        return
    cmds = project_build_commands(dest)
    log = ""
    try:
        if cmds["configure"]:
            log += f"$ {format_command(cmds['configure'])}\n"
            chunk = ""
            code = 1
            for chunk, done, code, _elapsed in stream_command(cmds["configure"], timeout=180):
                yield log + chunk
                if done:
                    break
            log += chunk or ""
            if code:
                yield log + f"\nConfigure failed (exit {code})"
                return
            log += "\n\n"

        build_cwd = dest if cmds["kind"] == "direct" else None
        log += f"$ {format_command(cmds['build'])}\n"
        chunk = ""
        code = 1
        for chunk, done, code, _elapsed in stream_command(cmds["build"], cwd=build_cwd, timeout=300):
            yield log + chunk
            if done:
                break
        log += chunk or ""
        if code:
            yield log + f"\nBuild failed (exit {code})"
            return

        n = max(1, int(repeats or 1))
        run_times: list[float] = []
        last_out = ""
        for i in range(n):
            log += f"\n\n$ {format_command(cmds['run'])}   # run {i + 1}/{n}\n"
            chunk = ""
            rc = 1
            elapsed = 0.0
            for chunk, done, rc, elapsed in stream_command(cmds["run"], cwd=dest, timeout=180):
                yield log + chunk
                if done:
                    break
            log += chunk or ""
            if rc:
                yield log + f"\nRun failed (exit {rc})"
                return
            run_times.append(elapsed)
            last_out = chunk or ""

        md = timing_markdown(
            py_wall=None,
            py_prog=None,
            compile_s=None,
            cpp_runs=run_times,
            cpp_prog=_program_timer(last_out),
            note="Repo mode times the generated binary only.",
        )
        yield log + "\n\n" + md
    except FileNotFoundError as exc:
        yield f"Build tool not found: {exc}\nInstall a C++ compiler (see System tab)."


def build_ui():
    report, default_compile, default_run = refresh_system()
    providers = list(PROVIDERS.keys())
    first_provider = providers[0]
    first_models, _ = keep_working_models(PROVIDERS[first_provider]["models"])

    with gr.Blocks(title="CppLift", css=CSS, theme=THEME, fill_width=True) as ui:
        with gr.Row(elem_classes=["hf-bar"], equal_height=True):
            gr.Markdown("# CppLift", elem_classes=["hf-brand"])
            section = gr.Radio(
                ["Snippet", "Repo", "System", "Scores", "Suggest"],
                value="Snippet",
                show_label=False,
                container=False,
                elem_classes=["hf-nav"],
                scale=4,
            )
            theme_toggle = gr.Dropdown(
                ["Light", "Dark"],
                value="Light",
                show_label=False,
                container=False,
                scale=0,
                min_width=96,
            )
        gr.Markdown(
            "Convert Python to C++, compile on this machine, and compare runtimes.",
            elem_classes=["page-kicker"],
        )

        with gr.Group(visible=True, elem_classes=["model-bar"]) as model_bar:
            with gr.Row():
                provider = gr.Dropdown(providers, value=first_provider, label="Provider", scale=2)
                model = gr.Dropdown(first_models, value=first_models[0], label="Model", scale=3)
                api_key = gr.Textbox(
                    label="API key",
                    type="password",
                    placeholder=key_placeholder(first_provider),
                    scale=3,
                )
            token_bar = gr.Markdown(token_bar_markdown(first_models[0]))
            source_tab = gr.Radio(
                ["Cloud", "Local"],
                value="Cloud",
                show_label=False,
                elem_classes=["hf-nav", "source-nav"],
            )
            with gr.Group(visible=True) as cloud_panel:
                fetch_models_btn = gr.Button("Refresh catalog", scale=0, min_width=140)
                fetch_models_log = gr.Markdown(elem_classes=["hint"])
            with gr.Group(visible=False, elem_classes=["local-panel"]) as local_panel:
                local_html = gr.HTML()
                local_select = gr.Radio(
                    label="Suggested local models",
                    choices=[],
                    value=None,
                )
                with gr.Row():
                    pull_local_btn = gr.Button("Download & use", variant="primary")
                    stop_pull_btn = gr.Button("Stop download & clean", variant="stop")

        fetch_models_btn.click(
            refresh_live_models,
            inputs=[provider, api_key],
            outputs=[model, fetch_models_log, token_bar],
        )
        source_tab.change(
            switch_source_tab,
            inputs=[source_tab, provider],
            outputs=[
                cloud_panel,
                local_panel,
                provider,
                model,
                api_key,
                token_bar,
                local_select,
                local_html,
            ],
        )
        pull_evt = pull_local_btn.click(
            download_and_use_local,
            inputs=local_select,
            outputs=[local_panel, local_select, local_html, provider, model, api_key],
        )
        stop_pull_btn.click(
            stop_local_download,
            outputs=[local_panel, local_select, local_html, provider, model, api_key],
            cancels=[pull_evt],
        )
        theme_toggle.change(fn=None, inputs=theme_toggle, js=THEME_JS)
        provider.change(
            on_provider_change,
            inputs=provider,
            outputs=[
                model,
                api_key,
                token_bar,
                source_tab,
                cloud_panel,
                local_panel,
                local_select,
                local_html,
            ],
        )
        model.change(token_info_for, inputs=model, outputs=token_bar)
        aa_state = gr.State([])

        with gr.Group(visible=True, elem_classes=["workspace"]) as snippet_panel:
            with gr.Row(equal_height=True):
                python_box = gr.Code(
                    value=SAMPLE_PYTHON,
                    language="python",
                    label="Python",
                    lines=22,
                    elem_classes=["snippet-code"],
                )
                cpp_box = gr.Code(
                    language="cpp",
                    label="C++",
                    lines=22,
                    elem_classes=["snippet-code"],
                )
            with gr.Row(elem_classes=["run-actions"]):
                convert_btn = gr.Button("Convert to C++", variant="primary", scale=0, min_width=140)
                run_py_btn = gr.Button("Run Python", scale=0, min_width=120)
                run_cpp_btn = gr.Button("Compile & run", scale=0, min_width=130)
                compare_btn = gr.Button("Compare both", scale=0, min_width=130)
                stop_run_btn = gr.Button("Stop", variant="stop", scale=0, min_width=90)
                repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats", scale=1, min_width=180)
            with gr.Row():
                py_out = gr.Textbox(label="Python output", lines=8)
                cpp_out = gr.Textbox(label="C++ compile / run log", lines=8)
            compare_md = gr.Markdown("Timing, tokens, latency, and estimated $ appear here after convert, compile, or compare.")
            convert_status = gr.Markdown("Convert a snippet to generate C++.")

        with gr.Group(visible=False, elem_classes=["workspace"]) as repo_panel:
            gr.Markdown("Point at a small Python project. CppLift writes C++ under `generated/cpp_project`.")
            with gr.Row():
                repo_path = gr.Textbox(
                    label="Local folder path",
                    placeholder="/path/to/my_python_project",
                    scale=3,
                )
                repo_zip = gr.File(label="Or upload a .zip", file_types=[".zip"], type="filepath", scale=2)
            with gr.Row():
                convert_repo_btn = gr.Button("Convert repo to C++", variant="primary")
                build_repo_btn = gr.Button("Build & run")
                stop_repo_btn = gr.Button("Stop run", variant="stop")
                repo_repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats")
            with gr.Row():
                repo_preview = gr.Textbox(label="Generated C++ preview", lines=16, scale=3)
                with gr.Column(scale=2):
                    repo_dir = gr.Textbox(label="Output folder")
                    repo_log = gr.Textbox(label="Status / build log", lines=12)

        with gr.Group(visible=False, elem_classes=["workspace"]) as system_panel:
            gr.Markdown("Toolchain detected on this machine. Edit flags if you need a different compile.")
            sys_box = gr.Textbox(value=report, label="System report", lines=16)
            with gr.Row():
                compile_box = gr.Textbox(value=default_compile, label="Snippet compile command")
                run_box = gr.Textbox(value=default_run, label="Snippet run command")
            refresh_btn = gr.Button("Re-scan this machine")
            refresh_btn.click(refresh_system, outputs=[sys_box, compile_box, run_box])

        with gr.Group(visible=False, elem_classes=["workspace"]) as aa_panel:
            gr.Markdown(
                "Independent scores from [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models). "
                "Nothing is downloaded until you load the leaderboard."
            )
            with gr.Row():
                aa_key_box = gr.Textbox(
                    label="Artificial Analysis API key",
                    type="password",
                    placeholder="Paste x-api-key, or leave blank if already in .env",
                    scale=3,
                )
                load_aa_btn = gr.Button("Load leaderboard", variant="primary", scale=1)
            aa_html = gr.HTML(value=aa_dashboard_html())
            load_aa_btn.click(load_aa_dashboard, inputs=aa_key_box, outputs=[aa_html, aa_state])

        with gr.Group(visible=False, elem_classes=["workspace"]) as suggest_panel:
            gr.Markdown("Pick a job. Uses Artificial Analysis ranks when loaded; otherwise built-in picks.")
            with gr.Row():
                suggest_cat = gr.Dropdown(
                    SUGGESTION_CATEGORIES,
                    value=SUGGESTION_CATEGORIES[0],
                    label="Category",
                    scale=3,
                )
                suggest_btn = gr.Button("Get suggestions", variant="primary", scale=1)
            suggest_html = gr.HTML(value=suggestions_html(SUGGESTION_CATEGORIES[0]))
            suggest_btn.click(
                load_suggestions,
                inputs=[suggest_cat, aa_key_box, aa_state],
                outputs=[suggest_html, aa_state],
            )
            suggest_cat.change(
                show_cached_suggestions,
                inputs=[suggest_cat, aa_state],
                outputs=suggest_html,
            )

        section.change(
            show_section,
            inputs=section,
            outputs=[model_bar, snippet_panel, repo_panel, system_panel, aa_panel, suggest_panel],
        )

        convert_evt = convert_btn.click(
            convert_snippet_ui,
            inputs=[python_box, provider, model, api_key],
            outputs=[cpp_box, convert_status, token_bar],
        )
        run_py_evt = run_py_btn.click(run_python, inputs=python_box, outputs=py_out)
        run_cpp_evt = run_cpp_btn.click(
            compile_and_run_snippet,
            inputs=[cpp_box, compile_box, run_box, repeats, provider, model, api_key],
            outputs=[cpp_out, compare_md, cpp_box],
        )
        compare_evt = compare_btn.click(
            compare_snippet,
            inputs=[python_box, cpp_box, compile_box, run_box, repeats, provider, model, api_key],
            outputs=[py_out, cpp_out, compare_md, cpp_box],
        )
        stop_run_btn.click(
            kill_active,
            outputs=py_out,
            cancels=[convert_evt, run_py_evt, run_cpp_evt, compare_evt],
        )
        convert_repo_evt = convert_repo_btn.click(
            convert_repo_ui,
            inputs=[repo_path, repo_zip, provider, model, api_key],
            outputs=[repo_preview, repo_dir, repo_log],
        )
        build_repo_evt = build_repo_btn.click(
            build_repo, inputs=[repo_dir, repo_repeats], outputs=repo_log
        )
        stop_repo_btn.click(
            kill_active,
            outputs=repo_log,
            cancels=[convert_repo_evt, build_repo_evt],
        )

    return ui


if __name__ == "__main__":
    build_ui().launch()
