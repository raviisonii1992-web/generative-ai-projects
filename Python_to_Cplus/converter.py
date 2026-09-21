"""LLM-backed Python → C++ conversion for snippets and small repos."""

from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

from openai import OpenAI

from compiler import detect_compiler, project_build_commands, snippet_compile_command, snippet_run_command

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".tox",
}

PROVIDERS = {
    "OpenAI": {
        "env": "OPENAI_API_KEY",
        "base_url": None,
        "models": ["gpt-5", "gpt-4.1", "gpt-4o", "gpt-5-mini", "gpt-4.1-mini"],
    },
    "Anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/",
        "models": ["claude-sonnet-4-5-20250929", "claude-haiku-4-5"],
    },
    "Google Gemini": {
        "env": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.1-flash-lite"],
    },
    "xAI Grok": {
        "env": "GROK_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-4", "grok-4-fast-non-reasoning"],
    },
    "Groq": {
        "env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["openai/gpt-oss-120b", "qwen/qwen3-32b", "llama-3.3-70b-versatile"],
    },
    "OpenRouter": {
        "env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "qwen/qwen3-coder-30b-a3b-instruct",
            "openai/gpt-oss-120b",
            "deepseek/deepseek-chat",
        ],
    },
    "Ollama (local)": {
        "env": None,
        "base_url": "http://localhost:11434/v1",
        "models": ["qwen2.5-coder", "deepseek-coder-v2", "gpt-oss:20b", "llama3.2"],
        "default_key": "ollama",
    },
}

SNIPPET_SYSTEM = """
You convert Python into high-performance C++.
Respond only with C++ source. No markdown fences unless the code itself needs them.
Occasional comments are allowed. The program must produce identical output as fast as possible.
Write a complete compilable program (includes, main, etc.).
"""

REPO_SYSTEM = """
You convert a Python project into a compilable C++ project for the user's machine.
Respond ONLY with files in this exact format (repeat the pair for every file):

===== FILE: relative/path =====
<file contents>
===== END FILE =====

Required files:
- CMakeLists.txt that builds an executable named `app` from all C++ sources
- C++ sources under src/ (entry point src/main.cpp)
- README.md with how to build on this machine

Match Python behavior. Prefer a fast native implementation. Do not emit Python files.
Do not wrap the whole reply in a markdown code fence.
"""

FILE_RE = re.compile(
    r"===== FILE:\s*(.+?) =====\s*\n(.*?)===== END FILE =====",
    re.DOTALL,
)

MAX_REPO_CHARS = 80_000
MAX_FILES = 40


def make_client(provider: str, api_key: str | None) -> OpenAI:
    spec = PROVIDERS[provider]
    key = (api_key or "").strip() or os.getenv(spec["env"] or "", "") or spec.get("default_key") or ""
    if spec["env"] and not key:
        raise ValueError(
            f"No API key for {provider}. Paste a key in the UI or set {spec['env']} in a .env file."
        )
    kwargs = {"api_key": key or "ollama"}
    if spec["base_url"]:
        kwargs["base_url"] = spec["base_url"]
    return OpenAI(**kwargs)


def _reasoning_kw(model: str) -> dict:
    if model.startswith("gpt-5"):
        return {"reasoning_effort": "high"}
    return {}


def strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:cpp|c\+\+|cxx)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def snippet_user_prompt(python_code: str) -> str:
    compile_cmd = snippet_compile_command()
    run_cmd = snippet_run_command()
    detected = detect_compiler()
    return f"""
Port this Python code to C++ with the fastest implementation that produces identical output.

System information:
{json.dumps(detected["system_info"], indent=2, default=str)}

The C++ will be saved as main.cpp and compiled with:
{compile_cmd}
then run with:
{run_cmd}

Respond only with C++ code.

Python:
```python
{python_code}
```
"""


def convert_snippet(provider: str, model: str, api_key: str | None, python_code: str):
    client = make_client(provider, api_key)
    messages = [
        {"role": "system", "content": SNIPPET_SYSTEM},
        {"role": "user", "content": snippet_user_prompt(python_code)},
    ]
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        **_reasoning_kw(model),
    )
    acc = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            acc += delta
            yield strip_fences(acc)


def collect_python_tree(root: Path) -> tuple[str, list[str]]:
    files: list[tuple[str, str]] = []
    total = 0
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if total + len(text) > MAX_REPO_CHARS:
            files.append((rel, f"# truncated; original size {len(text)} bytes\n"))
            break
        files.append((rel, text))
        total += len(text)
        if len(files) >= MAX_FILES:
            break
    blob = "\n\n".join(f"### {rel}\n```python\n{body}\n```" for rel, body in files)
    return blob, [rel for rel, _ in files]


def extract_zip(zip_path: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    children = [p for p in dest.iterdir() if p.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return dest


def repo_user_prompt(python_blob: str, file_list: list[str]) -> str:
    detected = detect_compiler()
    cmds = project_build_commands(Path("generated_cpp"))
    return f"""
Port this Python project to a native C++ project.

Python files included:
{json.dumps(file_list, indent=2)}

System information:
{json.dumps(detected["system_info"], indent=2, default=str)}

Preferred compiler: {detected["compiler"]} ({detected["family"]})
CMake available: {detected["cmake"]}
Suggested configure: {cmds.get("configure")}
Suggested build: {cmds.get("build")}

Python sources:
{python_blob}
"""


def parse_repo_files(reply: str) -> dict[str, str]:
    files = {}
    for match in FILE_RE.finditer(reply):
        rel = match.group(1).strip().lstrip("./")
        if ".." in Path(rel).parts:
            continue
        files[rel] = match.group(2).strip("\n") + "\n"
    if files:
        return files
    # Fallback: treat the whole reply as a single translation unit.
    return {"src/main.cpp": strip_fences(reply) + "\n"}


def write_repo(files: dict[str, str], dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if "CMakeLists.txt" not in files:
        sources = [r for r in files if r.endswith((".cpp", ".cc", ".cxx"))]
        src_list = "\n  ".join(sources) or "src/main.cpp"
        (dest / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(python_port LANGUAGES CXX)\n"
            "set(CMAKE_CXX_STANDARD 17)\n"
            "set(CMAKE_CXX_STANDARD_REQUIRED ON)\n"
            f"add_executable(app\n  {src_list}\n)\n",
            encoding="utf-8",
        )
    return dest


def convert_repo(provider: str, model: str, api_key: str | None, python_blob: str, file_list: list[str]):
    client = make_client(provider, api_key)
    messages = [
        {"role": "system", "content": REPO_SYSTEM},
        {"role": "user", "content": repo_user_prompt(python_blob, file_list)},
    ]
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        **_reasoning_kw(model),
    )
    acc = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            acc += delta
            yield acc
