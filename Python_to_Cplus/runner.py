"""Run compilers and binaries, streaming combined stdout/stderr."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path


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
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    elapsed = time.perf_counter() - start
    yield "".join(chunks), True, proc.returncode, elapsed
