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
    primary_hue="zinc",
    secondary_hue="zinc",
    neutral_hue="zinc",
).set(
    body_background_fill="#f4f4f5",
    body_background_fill_dark="#09090b",
    block_background_fill="transparent",
    block_background_fill_dark="#16161a",
    block_border_width="0px",
    block_shadow="none",
    button_primary_background_fill="#ffe14a",
    button_primary_background_fill_hover="#ffd21e",
    button_primary_text_color="#111111",
    button_primary_background_fill_dark="#ffe14a",
    button_primary_background_fill_hover_dark="#ffd21e",
    button_primary_text_color_dark="#111111",
)

CSS = """
html, body {
  height: 100%;
  margin: 0;
  overflow: hidden;
}
.gradio-container {
  max-width: 100% !important;
  width: 100% !important;
  height: 100dvh !important;
  max-height: 100dvh !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  background: #09090b !important;
  color: #f4f4f5;
  overflow: hidden !important;
}
footer, .built-with { display: none !important; }
.app.fillable,
.app.fillable > .wrap,
.app.fillable > .wrap > .contain,
.app.fillable > .wrap > .contain > .column {
  height: 100dvh !important;
  max-height: 100dvh !important;
  min-height: 0 !important;
  overflow: hidden !important;
  padding: 0 !important;
  margin: 0 !important;
  box-sizing: border-box !important;
}
.studio {
  display: grid !important;
  grid-template-columns: clamp(10.5rem, 18vw, 15rem) minmax(0, 1fr) !important;
  grid-template-rows: minmax(0, 1fr) !important;
  align-items: stretch !important;
  gap: 0 !important;
  height: 100dvh !important;
  max-height: 100dvh !important;
  min-height: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow: hidden !important;
  background: #09090b;
}
.rail {
  grid-column: 1 !important;
  grid-row: 1 !important;
  width: auto !important;
  min-width: 0 !important;
  max-width: none !important;
  height: 100% !important;
  min-height: 0 !important;
  max-height: 100% !important;
  background: #101012 !important;
  border-right: 1px solid #24242a !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  padding: clamp(8px, 1.2dvh, 18px) clamp(6px, 0.8vw, 12px) !important;
  gap: 6px !important;
}
.main {
  grid-column: 2 !important;
  grid-row: 1 !important;
  min-width: 0 !important;
  width: auto !important;
  max-width: 100% !important;
  height: 100% !important;
  max-height: 100% !important;
  min-height: 0 !important;
  background: #09090b !important;
  padding: 0 !important;
  gap: 0 !important;
  flex-wrap: nowrap !important;
  flex-direction: column !important;
  overflow: hidden !important;
  display: flex !important;
}
.stage {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  min-width: 0 !important;
  height: auto !important;
  overflow: auto !important;
  padding: clamp(8px, 1.2vh, 16px) clamp(8px, 1.2vw, 18px) 8px !important;
  gap: 10px !important;
  background: transparent !important;
  border: none !important;
  flex-wrap: nowrap !important;
}
.stage .row, .composer .row {
  flex-wrap: wrap !important;
  min-width: 0 !important;
  width: 100% !important;
}
.stage .row > *, .composer .row > * {
  flex: 1 1 min(100%, 18rem) !important;
  min-width: 0 !important;
  max-width: 100% !important;
}
.composer {
  flex: 0 1 auto !important;
  width: auto !important;
  min-width: 0 !important;
  min-height: 0 !important;
  max-height: min(46dvh, 100%) !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  margin: 0 clamp(8px, 1vw, 14px) clamp(8px, 1vh, 12px) !important;
  background: #16161a !important;
  border: 1px solid #2c2c34 !important;
  border-radius: 20px !important;
  padding: 10px 12px 8px !important;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.45);
}
.composer .form, .composer .block, .stage .form, .stage .block,
.rail .form, .rail .block {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
.rail > * {
  max-width: 100% !important;
  min-width: 0 !important;
}
.brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 2px 8px 12px;
  border-bottom: 1px solid #24242a;
  margin-bottom: 8px;
}
.brand-name, .brand-sub {
  overflow-wrap: anywhere;
  min-width: 0;
}
.brand-glyph {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: #ffe14a;
  color: #111;
  font-weight: 800;
  font-size: 13px;
  display: grid;
  place-items: center;
  letter-spacing: -0.05em;
  flex: 0 0 auto;
}
.brand-name {
  font-weight: 800;
  font-size: 17px;
  letter-spacing: -0.04em;
  color: #fafafa;
  line-height: 1.1;
}
.brand-sub { font-size: 12px; color: #a1a1aa; margin-top: 2px; }
.rail-foot {
  margin-top: auto;
  color: #71717a !important;
  font-size: 12px !important;
  padding: 8px 8px 0 !important;
}
.hf-nav { margin: 0 !important; padding: 0 !important; background: transparent !important; }
.hf-nav > .form, .hf-nav > .block, .hf-nav fieldset {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
.rail-nav .wrap {
  display: grid !important;
  grid-template-columns: 1fr !important;
  align-items: stretch !important;
  gap: 4px !important;
}
.hf-nav label {
  display: flex !important;
  align-items: center;
  border: none !important;
  border-radius: 12px !important;
  padding: clamp(6px, 0.8vh, 10px) clamp(8px, 0.6vw, 12px) !important;
  background: transparent !important;
  box-shadow: none !important;
  cursor: pointer;
  font-size: clamp(12px, 0.9vw, 14px) !important;
  font-weight: 550 !important;
  color: #a1a1aa !important;
  white-space: normal !important;
}
.hf-nav label:hover { color: #fafafa !important; background: #1a1a1f !important; }
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
  background: #232228 !important;
  color: #fafafa !important;
  font-weight: 700 !important;
  box-shadow: inset 3px 0 0 #ffe14a !important;
}
.source-nav { margin: 0 0 6px !important; height: auto !important; min-height: 36px !important; overflow: visible !important; }
.source-nav .wrap {
  flex-direction: row !important;
  flex-wrap: wrap !important;
  gap: 6px !important;
  margin-bottom: 4px !important;
}
.source-nav label {
  border-radius: 999px !important;
  padding: 6px 14px !important;
  background: #101012 !important;
  border: 1px solid #2c2c34 !important;
  font-size: 13px !important;
}
.source-nav label:has(input:checked) {
  background: #ffe14a !important;
  color: #111 !important;
  box-shadow: none !important;
  border-color: #ffe14a !important;
}
.stage-title {
  color: #fafafa !important;
  font-size: 1.35rem !important;
  font-weight: 750 !important;
  letter-spacing: -0.04em;
  margin: 0 !important;
}
.stage-title p, .stage-kicker {
  color: #a1a1aa !important;
  font-size: 0.92rem !important;
  font-weight: 450 !important;
  margin: 2px 0 8px !important;
}
.workspace {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
.composer-actions {
  flex-wrap: wrap !important;
  gap: 6px !important;
  width: 100% !important;
  min-width: 0 !important;
}
.composer-actions > * {
  flex: 1 1 8rem !important;
  min-width: 0 !important;
  max-width: 100% !important;
}
.composer-actions button { white-space: normal !important; border-radius: 999px !important; min-width: 0 !important; }
.composer-actions button.primary {
  background: #ffe14a !important;
  color: #111111 !important;
  border: none !important;
  font-weight: 750 !important;
}
.composer-actions button.primary:hover { background: #ffd21e !important; }
.composer-actions button.stop {
  border-radius: 999px !important;
}
.hint { font-size: 13px !important; color: #a1a1aa !important; background: transparent !important; }
.composer textarea, .composer input, .stage textarea, .stage input {
  border-radius: 12px !important;
}
.stage .block > label span,
.composer .block > label span {
  background: transparent !important;
  color: #d4d4d8 !important;
  border: none !important;
  padding: 0 !important;
  font-weight: 600 !important;
}
.snippet-code {
  height: clamp(7rem, 28dvh, 34rem) !important;
  max-height: 32dvh !important;
  min-height: 0 !important;
  overflow: hidden !important;
  border: 1px solid #2c2c34 !important;
  border-radius: 16px !important;
}
.snippet-code .cm-editor,
.snippet-code .cm-scroller,
.snippet-code .monaco-editor,
.snippet-code .ace_editor,
.snippet-code textarea,
.snippet-code pre {
  height: clamp(7rem, 28dvh, 34rem) !important;
  max-height: 32dvh !important;
  min-height: 0 !important;
}
.output-card textarea {
  height: clamp(3rem, 12dvh, 8rem) !important;
  min-height: 0 !important;
  max-height: 14dvh !important;
}
.snippet-code .cm-scroller,
.snippet-code .monaco-scrollable-element,
.snippet-code .ace_scrollbar,
.snippet-code textarea {
  overflow: auto !important;
}
.aa-dash { font-size: 14px; color: inherit; }
.aa-dash h3, .aa-dash p, .aa-dash li { color: inherit; }
.aa-dash a { color: #93c5fd; }
.aa-err { color: #fca5a5; }
.aa-cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 16px; }
.aa-card {
  background: #1c1c22;
  color: #f4f4f5;
  border: 1px solid #2c2c34;
  border-radius: 14px;
  padding: 12px 14px;
  min-width: 180px;
  flex: 1;
}
.aa-rank { font-size: 12px; color: #a1a1aa; }
.aa-name { font-weight: 700; margin: 4px 0; color: #fafafa; }
.aa-meta { font-size: 12px; color: #d4d4d8; }
.aa-kpis { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; font-size: 12px; }
.aa-kpis span {
  background: #27272a;
  color: #f4f4f5;
  padding: 2px 6px;
  border-radius: 6px;
}
.aa-table-wrap { overflow: auto; max-height: 420px; border: 1px solid #2c2c34; border-radius: 12px; background: #101012; }
.aa-table { width: 100%; border-collapse: collapse; font-size: 13px; color: #e4e4e7; }
.aa-table th { position: sticky; top: 0; background: #18181b; color: #fafafa; text-align: left; padding: 8px; }
.aa-table td { padding: 6px 8px; border-bottom: 1px solid #27272a; color: #e4e4e7; }
.aa-table tr:nth-child(even) { background: #16161a; }
.aa-table tr:nth-child(odd) { background: #101012; }
.aa-note { font-size: 12px; color: #a1a1aa; }

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
.local-idle { background: #1c1c22; color: #d4d4d8; border-color: #3f3f46; }
.local-ready {
  background: #052e16;
  color: #d1fae5;
  border-color: #166534;
}
.local-ready code { background: #14532d; padding: 1px 6px; border-radius: 4px; }
.local-err {
  background: #450a0a;
  color: #fecaca;
  border-color: #991b1b;
}
.local-stopped {
  background: #451a03;
  color: #fde68a;
  border-color: #b45309;
}
body[data-app-theme="light"] .local-idle { background: #f8fafc; color: #334155; border-color: #cbd5e1; }
body[data-app-theme="light"] .local-ready { background: #ecfdf5; color: #065f46; border-color: #6ee7b7; }
body[data-app-theme="light"] .local-ready code { background: #d1fae5; }
body[data-app-theme="light"] .local-err { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
body[data-app-theme="light"] .local-stopped { background: #fffbeb; color: #92400e; border-color: #fcd34d; }

body[data-app-theme="light"] .gradio-container,
body[data-app-theme="light"] .studio,
body[data-app-theme="light"] .main { background: #f4f4f5 !important; color: #18181b; }
body[data-app-theme="light"] .rail {
  background: #ffffff !important;
  border-right-color: #e4e4e7 !important;
}
body[data-app-theme="light"] .brand-mark { border-bottom-color: #e4e4e7; }
body[data-app-theme="light"] .brand-name { color: #18181b; }
body[data-app-theme="light"] .brand-sub,
body[data-app-theme="light"] .rail-foot,
body[data-app-theme="light"] .stage-kicker,
body[data-app-theme="light"] .hint { color: #52525b !important; }
body[data-app-theme="light"] .stage-title { color: #18181b !important; }
body[data-app-theme="light"] .hf-nav label { color: #3f3f46 !important; }
body[data-app-theme="light"] .hf-nav label:hover { color: #18181b !important; background: #f4f4f5 !important; }
body[data-app-theme="light"] .hf-nav label:has(input:checked) {
  background: #f4f4f5 !important;
  color: #18181b !important;
}
body[data-app-theme="light"] .source-nav label {
  background: #fff !important;
  border-color: #e4e4e7 !important;
  color: #3f3f46 !important;
}
body[data-app-theme="light"] .source-nav label:has(input:checked) {
  background: #ffe14a !important;
  color: #111 !important;
}
body[data-app-theme="light"] .composer {
  background: #ffffff !important;
  border-color: #e4e4e7 !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
}
body[data-app-theme="light"] .aa-dash a { color: #1d4ed8; }
body[data-app-theme="light"] .aa-card {
  background: #f4f4f5;
  color: #18181b;
  border-color: #e4e4e7;
}
body[data-app-theme="light"] .aa-name { color: #18181b; }
body[data-app-theme="light"] .aa-table-wrap { background: #fff; border-color: #e4e4e7; }
body[data-app-theme="light"] .aa-table { color: #18181b; }
body[data-app-theme="light"] .aa-table td { color: #18181b; border-bottom-color: #e4e4e7; }
body[data-app-theme="light"] .aa-table tr:nth-child(odd) { background: #fff; }
body[data-app-theme="light"] .aa-table tr:nth-child(even) { background: #fafafa; }

@media (max-width: 860px) {
  .studio {
    flex-direction: column !important;
  }
  .rail {
    width: 100% !important;
    min-width: 100% !important;
    max-width: 100% !important;
    flex: 0 0 auto !important;
    min-height: auto !important;
    max-height: none !important;
    border-right: none !important;
    border-bottom: 1px solid #24242a !important;
  }
  .rail-nav .wrap {
    flex-direction: row !important;
    flex-wrap: wrap !important;
  }
}
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

LOAD_JS = """
() => {
  document.body.setAttribute("data-app-theme", "dark");
  document.documentElement.classList.add("dark");
  document.body.classList.add("dark");
}
"""

BRAND_HTML = """
<div class="brand-mark">
  <div class="brand-glyph">C++</div>
  <div>
    <div class="brand-name">CppLift</div>
    <div class="brand-sub">Every model. One bar.</div>
  </div>
</div>
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
        gr.update(visible=name == "Snippet"),
        gr.update(visible=name == "Repo"),
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

    with gr.Blocks(title="CppLift", css=CSS, theme=THEME, fill_width=True, js=LOAD_JS) as ui:
        with gr.Row(elem_classes=["studio"]):
            with gr.Column(elem_classes=["rail"], scale=0, min_width=120):
                gr.HTML(BRAND_HTML)
                section = gr.Radio(
                    ["Snippet", "Repo", "System", "Scores", "Suggest"],
                    value="Snippet",
                    show_label=False,
                    container=False,
                    elem_classes=["hf-nav", "rail-nav"],
                )
                theme_toggle = gr.Dropdown(
                    ["Light", "Dark"],
                    value="Dark",
                    label="Appearance",
                    container=True,
                )
                gr.Markdown(
                    "Python in. C++ out. Pick a model in the bar and generate.",
                    elem_classes=["rail-foot"],
                )

            with gr.Column(elem_classes=["main"]):
                with gr.Column(elem_classes=["stage"]):
                    with gr.Group(visible=True, elem_classes=["workspace"]) as snippet_panel:
                        gr.Markdown(
                            "### Snippet\nPaste Python, generate C++, then compile on this machine.",
                            elem_classes=["stage-title"],
                        )
                        with gr.Row(equal_height=True):
                            python_box = gr.Code(
                                value=SAMPLE_PYTHON,
                                language="python",
                                label="Python",
                                lines=18,
                                elem_classes=["snippet-code"],
                            )
                            cpp_box = gr.Code(
                                language="cpp",
                                label="C++",
                                lines=18,
                                elem_classes=["snippet-code"],
                            )
                        with gr.Row():
                            py_out = gr.Textbox(label="Python output", lines=6, elem_classes=["output-card"])
                            cpp_out = gr.Textbox(label="C++ compile / run log", lines=6, elem_classes=["output-card"])
                        compare_md = gr.Markdown(
                            "Timing, tokens, latency, and estimated $ appear here after convert, compile, or compare.",
                            elem_classes=["stage-kicker"],
                        )
                        convert_status = gr.Markdown(
                            "Convert a snippet to generate C++.",
                            elem_classes=["stage-kicker"],
                        )

                    with gr.Group(visible=False, elem_classes=["workspace"]) as repo_panel:
                        gr.Markdown(
                            "### Repo\nPoint at a small Python project. CppLift writes C++ under `generated/cpp_project`.",
                            elem_classes=["stage-title"],
                        )
                        with gr.Row():
                            repo_path = gr.Textbox(
                                label="Local folder path",
                                placeholder="/path/to/my_python_project",
                                scale=3,
                            )
                            repo_zip = gr.File(label="Or upload a .zip", file_types=[".zip"], type="filepath", scale=2)
                        with gr.Row():
                            repo_preview = gr.Textbox(label="Generated C++ preview", lines=16, scale=3)
                            with gr.Column(scale=2):
                                repo_dir = gr.Textbox(label="Output folder")
                                repo_log = gr.Textbox(label="Status / build log", lines=12)

                    with gr.Group(visible=False, elem_classes=["workspace"]) as system_panel:
                        gr.Markdown(
                            "### System\nToolchain detected on this machine. Edit flags if you need a different compile.",
                            elem_classes=["stage-title"],
                        )
                        sys_box = gr.Textbox(value=report, label="System report", lines=16)
                        with gr.Row():
                            compile_box = gr.Textbox(value=default_compile, label="Snippet compile command")
                            run_box = gr.Textbox(value=default_run, label="Snippet run command")
                        refresh_btn = gr.Button("Re-scan this machine")

                    with gr.Group(visible=False, elem_classes=["workspace"]) as aa_panel:
                        gr.Markdown(
                            "### Scores\nIndependent scores from [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models). "
                            "Nothing is downloaded until you load the leaderboard.",
                            elem_classes=["stage-title"],
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

                    with gr.Group(visible=False, elem_classes=["workspace"]) as suggest_panel:
                        gr.Markdown(
                            "### Suggest\nPick a job. Uses Artificial Analysis ranks when loaded; otherwise built-in picks.",
                            elem_classes=["stage-title"],
                        )
                        with gr.Row():
                            suggest_cat = gr.Dropdown(
                                SUGGESTION_CATEGORIES,
                                value=SUGGESTION_CATEGORIES[0],
                                label="Category",
                                scale=3,
                            )
                            suggest_btn = gr.Button("Get suggestions", variant="primary", scale=1)
                        suggest_html = gr.HTML(value=suggestions_html(SUGGESTION_CATEGORIES[0]))

                with gr.Group(visible=True, elem_classes=["composer"]) as model_bar:
                    source_tab = gr.Radio(
                        ["Cloud", "Local"],
                        value="Cloud",
                        show_label=False,
                        elem_classes=["hf-nav", "source-nav"],
                    )
                    with gr.Row():
                        provider = gr.Dropdown(providers, value=first_provider, label="Provider", scale=2)
                        model = gr.Dropdown(first_models, value=first_models[0], label="Model", scale=3)
                        api_key = gr.Textbox(
                            label="API key",
                            type="password",
                            placeholder=key_placeholder(first_provider),
                            scale=3,
                        )
                    token_bar = gr.Markdown(token_bar_markdown(first_models[0]), elem_classes=["hint"])
                    with gr.Group(visible=True) as cloud_panel:
                        fetch_models_btn = gr.Button("Refresh catalog", scale=0, min_width=0)
                        fetch_models_log = gr.Markdown(elem_classes=["hint"])
                    with gr.Group(visible=False, elem_classes=["local-panel"]) as local_panel:
                        local_html = gr.HTML()
                        local_select = gr.Radio(
                            label="Suggested local models",
                            choices=[],
                            value=None,
                        )
                        with gr.Row(elem_classes=["composer-actions"]):
                            pull_local_btn = gr.Button("Download & use", variant="primary")
                            stop_pull_btn = gr.Button("Stop download & clean", variant="stop")
                    with gr.Row(visible=True, elem_classes=["composer-actions"]) as snippet_actions:
                        convert_btn = gr.Button("Convert to C++", variant="primary", scale=1, min_width=0)
                        run_py_btn = gr.Button("Run Python", scale=1, min_width=0)
                        run_cpp_btn = gr.Button("Compile & run", scale=1, min_width=0)
                        compare_btn = gr.Button("Compare both", scale=1, min_width=0)
                        stop_run_btn = gr.Button("Stop", variant="stop", scale=1, min_width=0)
                        repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats", scale=2, min_width=0)
                    with gr.Row(visible=False, elem_classes=["composer-actions"]) as repo_actions:
                        convert_repo_btn = gr.Button("Convert repo to C++", variant="primary", scale=1, min_width=0)
                        build_repo_btn = gr.Button("Build & run", scale=1, min_width=0)
                        stop_repo_btn = gr.Button("Stop run", variant="stop", scale=1, min_width=0)
                        repo_repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats", scale=2, min_width=0)

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
        refresh_btn.click(refresh_system, outputs=[sys_box, compile_box, run_box])
        load_aa_btn.click(load_aa_dashboard, inputs=aa_key_box, outputs=[aa_html, aa_state])
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
            outputs=[
                model_bar,
                snippet_panel,
                snippet_actions,
                repo_panel,
                repo_actions,
                system_panel,
                aa_panel,
                suggest_panel,
            ],
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
