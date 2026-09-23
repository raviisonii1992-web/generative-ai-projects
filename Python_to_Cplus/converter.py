"""LLM-backed Python → C++ conversion for snippets and small repos."""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from pathlib import Path

from datetime import date

from openai import OpenAI

from compiler import detect_compiler, project_build_commands, snippet_compile_command, snippet_run_command, toolchain_for
from research import lookup_repairs

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
        "models": ["gemini-3.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.1-flash-lite"],
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

# Hidden from the dropdown when retired_on <= today. Convert still remaps if someone types the old id.
MODEL_LIFECYCLE = {
    "gemini-2.5-flash-lite": {
        "retired_on": "2026-09-22",
        "use_instead": "gemini-3.5-flash-lite",
        "how": "Google closed this id for new API users. Set Provider to **Google Gemini** and Model to **gemini-3.5-flash-lite** (same lite/fast class).",
    },
    "gemini-2.0-flash-lite": {
        "retired_on": "2026-01-01",
        "use_instead": "gemini-3.5-flash-lite",
        "how": "Use **gemini-3.5-flash-lite** under Google Gemini.",
    },
    "gpt-5-codex": {
        "retired_on": "2026-09-01",
        "use_instead": "gpt-5-mini",
        "how": "OpenAI retired this Codex id. Set Provider to **OpenAI** and Model to **gpt-5-mini** or **gpt-4.1** for Python→C++.",
    },
}

MODEL_ALIASES = {k: v["use_instead"] for k, v in MODEL_LIFECYCLE.items()}


def model_id_bare(model: str) -> str:
    name = (model or "").strip()
    if name.startswith("models/"):
        name = name[7:]
    return name


def is_retired_model(model: str, when: date | None = None) -> bool:
    when = when or date.today()
    spec = MODEL_LIFECYCLE.get(model_id_bare(model))
    if not spec:
        return False
    return date.fromisoformat(spec["retired_on"]) <= when


def keep_working_models(ids: list[str], when: date | None = None) -> tuple[list[str], list[dict]]:
    """Drop ids retired as of `when` (default: today). Returns (kept, dropped_info)."""
    when = when or date.today()
    kept: list[str] = []
    dropped: list[dict] = []
    seen: set[str] = set()
    for mid in ids:
        bare = model_id_bare(mid)
        if not bare or bare in seen:
            continue
        seen.add(bare)
        spec = MODEL_LIFECYCLE.get(bare)
        if spec and date.fromisoformat(spec["retired_on"]) <= when:
            dropped.append({"id": bare, **spec})
            continue
        kept.append(bare)
    return kept, dropped


def canonical_model_id(model: str) -> str:
    name = model_id_bare(model)
    spec = MODEL_LIFECYCLE.get(name)
    if spec and is_retired_model(name):
        return spec["use_instead"]
    return name


PORTABLE_INCLUDE_RULES = """
Use only ISO C++ headers (<iostream>, <vector>, <string>, <chrono>, …).
Never include <bits/stdc++.h> or other GCC-only headers. Apple Clang and MSVC do not provide them.
Never write `using namespace std;` or `using std::next` / `using std::prev`.
Those collide with linked-list fields named next/prev (std::next / std::prev).
Always qualify the standard library with std:: (std::cout, std::vector, …).
Do not `#define int long long` (that breaks `int main`).
Do not include conio.h, windows.h, iostream.h, or ext/pb_ds.
"""

SNIPPET_SYSTEM = """
You convert Python into high-performance C++.
Respond only with C++ source. No markdown fences unless the code itself needs them.
Occasional comments are allowed. The program must produce identical output as fast as possible.
Write a complete compilable program (includes, main, etc.).
""" + PORTABLE_INCLUDE_RULES

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
""" + PORTABLE_INCLUDE_RULES

FILE_RE = re.compile(
    r"===== FILE:\s*(.+?) =====\s*\n(.*?)===== END FILE =====",
    re.DOTALL,
)

MAX_REPO_CHARS = 80_000
MAX_FILES = 40

LAST_USAGE: dict = {
    "model": "",
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "elapsed_s": None,
}


def _set_usage(model: str, usage: object | None, elapsed_s: float | None, prompt_est: int = 0, completion_est: int = 0) -> None:
    pt = getattr(usage, "prompt_tokens", None) if usage is not None else None
    ct = getattr(usage, "completion_tokens", None) if usage is not None else None
    LAST_USAGE.update(
        {
            "model": model,
            "prompt_tokens": int(pt or prompt_est or 0),
            "completion_tokens": int(ct or completion_est or 0),
            "elapsed_s": elapsed_s,
        }
    )


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


_GCC_INCLUDE_RE = re.compile(
    r'^[ \t]*#[ \t]*include[ \t]*[<"](?:bits/[^>"\n]+|ext/pb_ds/[^>"\n]+)[>"][ \t]*$',
    re.MULTILINE,
)
_LEGACY_OR_HOST_INCLUDE_RE = re.compile(
    r'^[ \t]*#[ \t]*include[ \t]*[<"](?:iostream\.h|fstream\.h|iomanip\.h|conio\.h|'
    r'windows\.h|bits/stdc\+\+\.h)[>"][ \t]*$',
    re.MULTILINE,
)
_PORTABLE_HEADERS = """\
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <list>
#include <map>
#include <memory>
#include <numeric>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stack>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
"""
_WIN_MINMAX_GUARD = """\
#ifdef min
#undef min
#endif
#ifdef max
#undef max
#endif
"""

_USING_NAMESPACE_STD_RE = re.compile(
    r'^[ \t]*using[ \t]+namespace[ \t]+std[ \t]*;[ \t]*$',
    re.MULTILINE,
)
_USING_STD_NEXT_PREV_RE = re.compile(
    r'^[ \t]*using[ \t]+std::(?:next|prev)[ \t]*;[ \t]*$',
    re.MULTILINE,
)
_STD_USINGS = """\
using std::cerr;
using std::cin;
using std::cout;
using std::deque;
using std::endl;
using std::fixed;
using std::function;
using std::map;
using std::max;
using std::min;
using std::move;
using std::optional;
using std::pair;
using std::queue;
using std::set;
using std::setprecision;
using std::stack;
using std::string;
using std::to_string;
using std::unique_ptr;
using std::unordered_map;
using std::unordered_set;
using std::vector;
"""
_DEFINE_INT_LL_RE = re.compile(
    r'^[ \t]*#[ \t]*define[ \t]+int[ \t]+long[ \t]+long[ \t]*$',
    re.MULTILINE,
)
_PRAGMA_GCC_RE = re.compile(r'^[ \t]*#[ \t]*pragma[ \t]+GCC[ \t].*$', re.MULTILINE)
_VOID_MAIN_RE = re.compile(r'\bvoid\s+main\s*\(', re.MULTILINE)


def sanitize_cpp_source(text: str) -> str:
    """Fix contest-style / GCC-only model output so Apple Clang and MSVC can compile it."""
    if not text:
        return text
    text = strip_fences(text)
    text = (
        text.replace("\ufeff", "")
        .replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    if _GCC_INCLUDE_RE.search(text) or _LEGACY_OR_HOST_INCLUDE_RE.search(text):
        text = _GCC_INCLUDE_RE.sub(_PORTABLE_HEADERS.rstrip(), text, count=1)
        text = _GCC_INCLUDE_RE.sub("", text)
        text = _LEGACY_OR_HOST_INCLUDE_RE.sub(_PORTABLE_HEADERS.rstrip(), text, count=1)
        text = _LEGACY_OR_HOST_INCLUDE_RE.sub("", text)
    text = _USING_NAMESPACE_STD_RE.sub(_STD_USINGS.rstrip(), text)
    text = _USING_STD_NEXT_PREV_RE.sub("", text)
    text = _DEFINE_INT_LL_RE.sub("", text)
    text = _PRAGMA_GCC_RE.sub("", text)
    text = _VOID_MAIN_RE.sub("int main(", text)
    if "_PORTABLE_MINMAX_GUARD" not in text:
        text = (
            "#define _PORTABLE_MINMAX_GUARD\n"
            + _WIN_MINMAX_GUARD
            + "\n"
            + text
        )
    return text


REPAIR_SYSTEM = """
You repair C++ so it compiles with the user's compiler. Return only complete C++ source.
Keep the same program behavior and printed output.
""" + PORTABLE_INCLUDE_RULES


def repair_cpp(
    provider: str,
    model: str,
    api_key: str | None,
    source: str,
    compile_error: str,
    compile_cmd: str,
) -> str:
    """One-shot LLM fix after a failed compile (contest headers, name clashes, missing braces)."""
    client = make_client(provider, api_key)
    model = canonical_model_id(model)
    memory = lookup_repairs(compile_error)
    mem_block = f"\n{memory}\n" if memory else ""
    user = f"""The C++ below failed to compile.

Compile command:
{compile_cmd}

Compiler output:
{compile_error[-8000:]}
{mem_block}
C++ source:
```cpp
{source}
```

Return a full compilable translation unit. No markdown fences.
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REPAIR_SYSTEM},
            {"role": "user", "content": user},
        ],
        **_reasoning_kw(model),
    )
    content = (response.choices[0].message.content or "").strip()
    return sanitize_cpp_source(strip_fences(content))


def snippet_system(src_lang: str, dst_lang: str) -> str:
    base = (
        f"You convert {src_lang} into {dst_lang}. "
        f"Reply with {dst_lang} source only. No markdown fences. "
        "Write a complete program with the same behavior, as fast as possible."
    )
    if dst_lang == "C++":
        return base + PORTABLE_INCLUDE_RULES
    return base


def snippet_user_prompt(source: str, src_lang: str = "Python", dst_lang: str = "C++") -> str:
    tool = toolchain_for(dst_lang)
    return (
        f"Port this {src_lang} to {dst_lang}.\n"
        f"Compile: {tool.get('compile') or 'not required'}\n"
        f"Run: {tool.get('run') or 'n/a'}\n\n"
        f"{source}"
    )


def convert_snippet(
    provider: str,
    model: str,
    api_key: str | None,
    source: str,
    src_lang: str = "Python",
    dst_lang: str = "C++",
):
    client = make_client(provider, api_key)
    model = canonical_model_id(model)
    messages = [
        {"role": "system", "content": snippet_system(src_lang, dst_lang)},
        {"role": "user", "content": snippet_user_prompt(source, src_lang, dst_lang)},
    ]
    started = time.perf_counter()
    kwargs = {"model": model, "messages": messages, "stream": True, **_reasoning_kw(model)}
    try:
        stream = client.chat.completions.create(**kwargs, stream_options={"include_usage": True})
    except TypeError:
        stream = client.chat.completions.create(**kwargs)
    except Exception:
        stream = client.chat.completions.create(**kwargs)
    acc = ""
    usage = None
    clean = sanitize_cpp_source if dst_lang == "C++" else strip_fences
    for chunk in stream:
        usage = getattr(chunk, "usage", None) or usage
        delta = ""
        if chunk.choices:
            delta = chunk.choices[0].delta.content or ""
        if delta:
            acc += delta
            yield clean(acc)
    _set_usage(model, usage, time.perf_counter() - started, len(source) // 4, len(acc) // 4)
    if acc:
        yield clean(acc)


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
        if Path(rel).suffix.lower() in {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"}:
            content = sanitize_cpp_source(content)
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
    model = canonical_model_id(model)
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
