"""Run compilers and binaries, streaming combined stdout/stderr."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

_lock = threading.Lock()
_active: list[subprocess.Popen] = []


def kill_active() -> str:
    """Stop Python/C++ subprocesses so the user can edit and run again."""
    with _lock:
        procs = list(_active)
    stopped = 0
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
            stopped += 1
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
    if stopped:
        return "Stopped. You can change the program and run again."
    return "Nothing was running."


def stream_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: float = 180,
    env: dict | None = None,
) -> Iterator[tuple[str, bool, int | None, float]]:
    """
    Yield (log_so_far, finished, returncode, elapsed_seconds).
    returncode is None until finished is True.
    """
    start = time.perf_counter()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        yield str(exc), True, 127, time.perf_counter() - start
        return
    except OSError as exc:
        yield str(exc), True, 1, time.perf_counter() - start
        return

    with _lock:
        _active.append(proc)

    chunks: list[str] = []
    deadline = start + timeout
    try:
        while True:
            if time.perf_counter() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                elapsed = time.perf_counter() - start
                chunks.append(f"\nTimed out after {timeout:.0f}s.")
                yield "".join(chunks), True, -1, elapsed
                return
            if proc.stdout is None:
                break
            line = proc.stdout.readline()
            if line:
                chunks.append(line)
                yield "".join(chunks), False, None, time.perf_counter() - start
                continue
            if proc.poll() is not None:
                rest = proc.stdout.read()
                if rest:
                    chunks.append(rest)
                break
            time.sleep(0.04)
    except GeneratorExit:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        raise
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        with _lock:
            if proc in _active:
                _active.remove(proc)

    elapsed = time.perf_counter() - start
    yield "".join(chunks), True, proc.returncode, elapsed
