"""Pick a C++ compiler and flags from the local machine."""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path

from system_info import retrieve_system_info


def _which(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return ""


def detect_compiler() -> dict:
    """Return compiler path, family, and default flags for this OS."""
    info = retrieve_system_info()
    sysname = platform.system()
    compilers = info.get("toolchain", {}).get("compilers", {})
    cpu = info.get("cpu", {})
    jobs = cpu.get("cores_logical") or os.cpu_count() or 4

    if sysname == "Windows":
        if compilers.get("msvc_cl") and _which("cl"):
            compiler = _which("cl")
            family = "msvc"
            flags = ["/std:c++17", "/O2", "/DNDEBUG", "/EHsc"]
        elif _which("clang++"):
            compiler = _which("clang++")
            family = "clang"
            flags = ["-std=c++17", "-O3", "-march=native", "-DNDEBUG"]
        elif _which("g++"):
            compiler = _which("g++")
            family = "gcc"
            flags = ["-std=c++17", "-O3", "-march=native", "-DNDEBUG"]
        else:
            compiler = "cl"
            family = "msvc"
            flags = ["/std:c++17", "/O2", "/DNDEBUG", "/EHsc"]
    else:
        if _which("clang++"):
            compiler = _which("clang++")
            family = "clang"
        elif _which("g++"):
            compiler = _which("g++")
            family = "gcc"
        elif _which("c++"):
            compiler = _which("c++")
            family = "c++"
        else:
            compiler = "clang++" if sysname == "Darwin" else "g++"
            family = "clang" if sysname == "Darwin" else "gcc"
        flags = ["-std=c++17", "-O3", "-march=native", "-DNDEBUG"]
        if family == "clang" and sysname == "Darwin":
            flags = ["-std=c++17", "-O3", "-march=native", "-DNDEBUG"]

    return {
        "compiler": compiler,
        "family": family,
        "flags": flags,
        "jobs": int(jobs),
        "cmake": bool(shutil.which("cmake")),
        "ninja": bool(shutil.which("ninja")),
        "make": bool(shutil.which("make")),
        "system_info": info,
        "os": sysname,
    }


def snippet_compile_command(cpp_file: str = "main.cpp", exe: str | None = None) -> list[str]:
    detected = detect_compiler()
    exe = exe or ("main.exe" if detected["os"] == "Windows" else "main")
    if detected["family"] == "msvc":
        return [detected["compiler"], *detected["flags"], str(cpp_file), f"/Fe{exe}"]
    return [detected["compiler"], *detected["flags"], str(cpp_file), "-o", exe]


def snippet_run_command(exe: str | None = None) -> list[str]:
    detected = detect_compiler()
    if exe is None:
        exe = "main.exe" if detected["os"] == "Windows" else "main"
    if detected["os"] == "Windows":
        return [str(exe)]
    return [f"./{exe}" if not str(exe).startswith(("/", "./")) else str(exe)]


def project_build_commands(project_dir: str | Path) -> dict:
    """CMake when available, otherwise a single compiler invocation."""
    detected = detect_compiler()
    project_dir = Path(project_dir)
    build_dir = project_dir / "build"
    jobs = str(detected["jobs"])
    exe_name = "app.exe" if detected["os"] == "Windows" else "app"

    if detected["cmake"]:
        generator = []
        if detected["ninja"]:
            generator = ["-G", "Ninja"]
        configure = [
            shutil.which("cmake") or "cmake",
            "-S",
            str(project_dir),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            *generator,
        ]
        build = [
            shutil.which("cmake") or "cmake",
            "--build",
            str(build_dir),
            "--config",
            "Release",
            "-j",
            jobs,
        ]
        if detected["os"] == "Windows" and not detected["ninja"]:
            run = [str(build_dir / "Release" / "app.exe")]
        else:
            run = [str(build_dir / ("app.exe" if detected["os"] == "Windows" else "app"))]
        return {
            "configure": configure,
            "build": build,
            "run": run,
            "kind": "cmake",
            "detected": detected,
        }

    sources = sorted(str(p) for p in project_dir.rglob("*.cpp") if "build" not in p.parts)
    exe = str(project_dir / exe_name)
    if detected["family"] == "msvc":
        compile_cmd = [detected["compiler"], *detected["flags"], *sources, f"/Fe{exe}"]
    else:
        compile_cmd = [detected["compiler"], *detected["flags"], *sources, "-o", exe]
    return {
        "configure": [],
        "build": compile_cmd,
        "run": [exe],
        "kind": "direct",
        "detected": detected,
    }


def format_command(cmd: list[str]) -> str:
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def system_report() -> str:
    detected = detect_compiler()
    info = detected["system_info"]
    snippet = snippet_compile_command()
    run = snippet_run_command()
    lines = [
        f"OS: {info['os']['system']} {info['os']['arch']} ({info['os'].get('target_triple') or 'unknown triple'})",
        f"CPU: {info['cpu'].get('brand') or 'unknown'} | logical cores: {info['cpu'].get('cores_logical')}",
        f"SIMD: {', '.join(info['cpu'].get('simd') or []) or 'n/a'}",
        f"Package managers: {', '.join(info.get('package_managers') or []) or 'none detected'}",
        "",
        "Compilers:",
        json.dumps(info["toolchain"]["compilers"], indent=2),
        "",
        "Build tools:",
        json.dumps(info["toolchain"]["build_tools"], indent=2),
        "",
        f"Selected compiler: {detected['compiler']} ({detected['family']})",
        f"Snippet compile: {format_command(snippet)}",
        f"Snippet run:     {format_command(run)}",
    ]
    if not _which("clang++", "g++", "c++", "cl"):
        lines += [
            "",
            "No C++ compiler was found on PATH.",
            _install_hint(info),
        ]
    return "\n".join(lines)


def _install_hint(info: dict) -> str:
    sysname = info["os"]["system"]
    pms = info.get("package_managers") or []
    if sysname == "Darwin":
        return "Install Apple Command Line Tools: xcode-select --install\nOptional: brew install llvm cmake ninja"
    if sysname == "Windows":
        if "winget" in pms:
            return "Install a compiler, for example:\n  winget install -e --id Microsoft.VisualStudio.2022.BuildTools\n  or winget install LLVM.LLVM"
        return "Install Visual Studio Build Tools, LLVM, or MinGW-w64 and reopen the terminal."
    if "apt" in pms:
        return "sudo apt update && sudo apt install -y build-essential cmake ninja-build"
    if "dnf" in pms:
        return "sudo dnf install -y gcc-c++ cmake ninja-build"
    if "pacman" in pms:
        return "sudo pacman -S --needed base-devel cmake ninja"
    return "Install g++ or clang++ plus cmake using your OS package manager."
