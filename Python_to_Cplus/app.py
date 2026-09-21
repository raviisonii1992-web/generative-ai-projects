"""Gradio UI: Python → C++ conversion for snippets and small repos."""

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
    PROVIDERS,
    collect_python_tree,
    convert_repo,
    convert_snippet,
    extract_zip,
    parse_repo_files,
    write_repo,
)
from runner import stream_command

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

CSS = """
.gradio-container { max-width: 1400px !important; }
.convert-btn button { font-weight: 700; }
"""

PROGRAM_TIMER_RE = re.compile(r"Execution Time:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def models_for(provider: str):
    models = PROVIDERS.get(provider, {}).get("models", [])
    value = models[0] if models else None
    return gr.Dropdown(choices=models, value=value)


def key_placeholder(provider: str) -> str:
    spec = PROVIDERS.get(provider, {})
    env = spec.get("env")
    if not env:
        return "Ollama does not need a cloud API key"
    if os.getenv(env, ""):
        return f"{env} is already set in the environment (paste here only to override)"
    return f"Paste {env} or set it in a .env file"


def refresh_system():
    return (
        system_report(),
        format_command(snippet_compile_command()),
        format_command(snippet_run_command()),
    )


def parse_cmd(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Compile/run command is empty.")
    posix = os.name != "nt"
    return shlex.split(text, posix=posix)


def run_python_timed(code: str) -> tuple[str, float, bool]:
    buffer = io.StringIO()
    old = sys.stdout
    sys.stdout = buffer
    start = time.perf_counter()
    ok = True
    try:
        exec(code, {"__builtins__": __builtins__})
        text = buffer.getvalue() or "(no stdout)"
    except Exception:
        ok = False
        text = traceback.format_exc()
    finally:
        sys.stdout = old
    return text, time.perf_counter() - start, ok


def run_python(code: str) -> str:
    text, wall, _ok = run_python_timed(code)
    return f"{text.rstrip()}\n\n[wall time {wall:.4f}s]"


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
    return f"""### Timing comparison

| | Python | C++ |
|---|---|---|
| Wall clock (process) | {_fmt(py_wall)} | {_fmt(cpp_wall)} |
| Program timer (`Execution Time`) | {_fmt(py_prog)} | {_fmt(cpp_prog)} |
| Compile | — | {_fmt(compile_s)} |
| C++ repeats | — | {repeats} |
| Speedup (Python ÷ C++) | {speedup_cell} | |

Wall clock includes interpreter / process startup. The program timer is the `Execution Time` line if the code prints one. Speedup uses the program timer when both sides print it, otherwise wall clock.{extra}
"""


def compile_and_run_snippet(cpp: str, compile_text: str, run_text: str, repeats: float = 1):
    if not (cpp or "").strip():
        yield "No C++ to compile. Convert Python first.", "Convert Python first."
        return
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "main.cpp").write_text(cpp, encoding="utf-8")
    try:
        compile_cmd = parse_cmd(compile_text)
        run_cmd = parse_cmd(run_text)
    except ValueError as exc:
        yield str(exc), str(exc)
        return

    header = f"$ {format_command(compile_cmd)}\n"
    compile_log = ""
    compile_s = None
    code = 1
    for compile_log, done, code, compile_s in stream_command(compile_cmd, cwd=GENERATED, timeout=180):
        yield header + compile_log, "Compiling…"
        if done:
            break
    log = header + (compile_log or "")
    if code:
        yield log + f"\nCompile failed (exit {code})", "Compile failed."
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
            yield log + chunk, f"Running C++ ({i + 1}/{n})…"
            if done:
                break
        log += chunk or ""
        if rc:
            yield log + f"\nRun failed (exit {rc})", "Run failed."
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
    yield log or "(no stdout)", md


def compare_snippet(python_code: str, cpp: str, compile_text: str, run_text: str, repeats: float):
    if not (python_code or "").strip():
        yield "Paste Python first.", "No C++ yet.", "Paste Python first."
        return
    if not (cpp or "").strip():
        yield "", "Convert to C++ first.", "Convert to C++ first."
        return

    py_text, py_wall, py_ok = run_python_timed(python_code)
    py_shown = f"{py_text.rstrip()}\n\n[wall time {py_wall:.4f}s]"
    yield py_shown, "Compiling C++…", "Python finished. Compiling C++…"
    if not py_ok:
        yield py_shown, "", "Python raised an exception; C++ was not run."
        return

    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "main.cpp").write_text(cpp, encoding="utf-8")
    try:
        compile_cmd = parse_cmd(compile_text)
        run_cmd = parse_cmd(run_text)
    except ValueError as exc:
        yield py_shown, str(exc), str(exc)
        return

    cpp_log = f"$ {format_command(compile_cmd)}\n"
    compile_s = None
    code = 1
    chunk = ""
    for chunk, done, code, compile_s in stream_command(compile_cmd, cwd=GENERATED, timeout=180):
        yield py_shown, cpp_log + chunk, "Compiling…"
        if done:
            break
    cpp_log += chunk or ""
    if code:
        yield py_shown, cpp_log + f"\nCompile failed (exit {code})", "Compile failed."
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
            yield py_shown, cpp_log + chunk, f"Running C++ ({i + 1}/{n})…"
            if done:
                break
        cpp_log += chunk or ""
        if rc:
            yield py_shown, cpp_log + f"\nRun failed (exit {rc})", "Run failed."
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
    yield py_shown, cpp_log, md


def convert_snippet_ui(python_code, provider, model, api_key):
    if not (python_code or "").strip():
        yield "Paste Python on the left first."
        return
    try:
        result = ""
        for result in convert_snippet(provider, model, api_key, python_code):
            yield result
    except Exception as exc:
        yield f"Conversion failed: {exc}"


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
        yield f"Repo conversion failed: {exc}", "", traceback.format_exc()


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
    first_models = PROVIDERS[first_provider]["models"]

    with gr.Blocks(title="Python → C++", css=CSS, theme=gr.themes.Soft()) as ui:
        gr.Markdown(
            "# Python → C++\n"
            "Paste a snippet, or point at a small Python repo. "
            "The app inspects this machine, chooses a compile command, and asks a model to emit matching C++."
        )
        with gr.Row():
            provider = gr.Dropdown(providers, value=first_provider, label="Provider")
            model = gr.Dropdown(first_models, value=first_models[0], label="Model")
            api_key = gr.Textbox(
                label="API key (optional if already in .env)",
                type="password",
                placeholder=key_placeholder(first_provider),
            )
        provider.change(models_for, inputs=provider, outputs=model)
        provider.change(
            lambda p: gr.Textbox(placeholder=key_placeholder(p)),
            inputs=provider,
            outputs=api_key,
        )

        with gr.Tabs():
            with gr.Tab("System & compile command"):
                gr.Markdown(
                    "Detected OS, CPU, and toolchain. Edit the commands if you want different flags."
                )
                sys_box = gr.Textbox(value=report, label="System report", lines=18)
                compile_box = gr.Textbox(value=default_compile, label="Snippet compile command")
                run_box = gr.Textbox(value=default_run, label="Snippet run command")
                refresh_btn = gr.Button("Re-scan this machine")
                refresh_btn.click(refresh_system, outputs=[sys_box, compile_box, run_box])

            with gr.Tab("Snippet"):
                with gr.Row():
                    python_box = gr.Code(
                        value=SAMPLE_PYTHON, language="python", label="Python", lines=22
                    )
                    cpp_box = gr.Code(language="cpp", label="C++", lines=22)
                with gr.Row():
                    convert_btn = gr.Button("Convert to C++", variant="primary", elem_classes=["convert-btn"])
                    run_py_btn = gr.Button("Run Python")
                    run_cpp_btn = gr.Button("Compile & run C++")
                    compare_btn = gr.Button("Run both & compare")
                    repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats")
                with gr.Row():
                    py_out = gr.Textbox(label="Python output", lines=8)
                    cpp_out = gr.Textbox(label="C++ compile / run log", lines=8)
                compare_md = gr.Markdown("Timing appears here after **Compile & run C++** or **Run both & compare**.")
                convert_btn.click(
                    convert_snippet_ui,
                    inputs=[python_box, provider, model, api_key],
                    outputs=cpp_box,
                )
                run_py_btn.click(run_python, inputs=python_box, outputs=py_out)
                run_cpp_btn.click(
                    compile_and_run_snippet,
                    inputs=[cpp_box, compile_box, run_box, repeats],
                    outputs=[cpp_out, compare_md],
                )
                compare_btn.click(
                    compare_snippet,
                    inputs=[python_box, cpp_box, compile_box, run_box, repeats],
                    outputs=[py_out, cpp_out, compare_md],
                )

            with gr.Tab("Python repo"):
                gr.Markdown(
                    "Upload a `.zip` or type a folder path. "
                    "The model writes a CMake (or direct compile) C++ tree under `generated/cpp_project` "
                    "using this machine's compiler."
                )
                repo_path = gr.Textbox(
                    label="Local Python repo path",
                    placeholder="/path/to/my_python_project",
                )
                repo_zip = gr.File(label="Or upload a .zip", file_types=[".zip"], type="filepath")
                convert_repo_btn = gr.Button("Convert repo to C++", variant="primary")
                build_repo_btn = gr.Button("Build & run generated C++ project")
                repo_repeats = gr.Slider(1, 5, value=3, step=1, label="C++ repeats")
                repo_preview = gr.Textbox(label="Generated C++ preview", lines=18)
                repo_dir = gr.Textbox(label="Output folder")
                repo_log = gr.Textbox(label="Status / build log", lines=12)
                convert_repo_btn.click(
                    convert_repo_ui,
                    inputs=[repo_path, repo_zip, provider, model, api_key],
                    outputs=[repo_preview, repo_dir, repo_log],
                )
                build_repo_btn.click(
                    build_repo, inputs=[repo_dir, repo_repeats], outputs=repo_log
                )

    return ui


if __name__ == "__main__":
    build_ui().launch()
