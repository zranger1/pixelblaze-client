#!/usr/bin/env python3
"""Unit tests for `_newJsContext` — the lazy, race-free MiniRacer factory.

No Pixelblaze required. Two properties are under test, and both are things that
actually broke:

1. **Laziness.** Importing the library must not load libmini_racer.so (~80ms) or
   initialize V8 (~60ms more). Only pattern compilation and pixelmap evaluation
   need a JS engine; every other `pb` command used to pay for one regardless.

2. **Thread safety of the first construction.** V8's one-time global setup is
   not thread-safe. Two threads reaching it together trip
   `Check failed: !IsConfigurablePoolInitialized()` and V8 aborts the *process*
   with SIGTRAP — no Python exception, nothing to catch. `pb <cmd> --ip all`
   fans out over a thread pool, so it hit this about half the time.

Because the failure kills the interpreter, the concurrency test runs in a
subprocess and asserts on its exit status. A regression here shows up as a
negative returncode (-5 / SIGTRAP), not an assertion failure.

    python3 -m pytest pixelblaze/test_js_context.py
"""

import subprocess
import sys
import textwrap

import pytest


def _run(source: str) -> subprocess.CompletedProcess:
    """Run a snippet in a clean interpreter and hand back the result."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_importing_the_library_does_not_load_v8():
    """`import pixelblaze` must not drag in py_mini_racer."""
    result = _run(
        """
        import sys
        import pixelblaze
        assert "py_mini_racer" not in sys.modules, (
            "importing pixelblaze loaded py_mini_racer; the JS engine must stay lazy"
        )
        print("lazy")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "lazy" in result.stdout


def test_context_is_built_only_on_demand():
    """Asking for a context loads the engine — and it evaluates JavaScript."""
    result = _run(
        """
        import sys
        from pixelblaze.pixelblaze import _newJsContext
        assert "py_mini_racer" not in sys.modules, "loaded too early"
        ctx = _newJsContext()
        assert "py_mini_racer" in sys.modules, "should have loaded on demand"
        assert ctx.eval("6*7") == 42
        print("on-demand")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "on-demand" in result.stdout


@pytest.mark.parametrize("run", range(4))
def test_concurrent_first_use_does_not_abort_the_process(run):
    """Eight threads racing to build the first context must not kill V8.

    Repeated, because the unguarded version failed intermittently — a single
    green run proved nothing. The eval is deliberately non-trivial: the race
    window only opens wide enough to lose when V8 has real work to do.
    """
    result = _run(
        """
        from concurrent.futures import ThreadPoolExecutor
        from pixelblaze.pixelblaze import _newJsContext

        # Enough work that the threads are genuinely inside V8 together.
        program = "function f(n){var s=0;for(var i=0;i<n;i++){s+=i%7}return s}"

        def go(i):
            ctx = _newJsContext()
            ctx.eval(program)
            return ctx.call("f", 20000)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(go, range(8)))
        assert len(results) == 8 and all(r == results[0] for r in results), results
        print("survived")
        """
    )
    assert result.returncode == 0, (
        f"V8 aborted during concurrent first use (returncode {result.returncode}); "
        f"stderr:\n{result.stderr}"
    )
    assert "survived" in result.stdout
