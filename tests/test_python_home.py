"""The injected interpreter must be able to find its own standard library.

Regression test: ``Py_InitializeFromConfig`` was called with ``program_name``
set but ``home`` left as NULL, so CPython had to auto-detect its prefix inside
the target process. Where that detection fails the remote thread faults
(0xC0000005) and no diagnostic is surfaced.
"""

import os.path as op

import pymem

import pyrun_injected.dllinject as dllinject


def test_injected_interpreter_finds_its_standard_library(tmp_path, notepad: pymem.Pymem):
    """Importing stdlib modules must work in the injected process."""
    string = (
        # `json` and `platform` are pure stdlib packages living under <prefix>\Lib, so
        # importing them only succeeds once the injected interpreter knows its own prefix
        # (PyConfig.home). This import is the pivot of the whole test.
        "import json, platform, sys\n"
        # A relative filename on purpose: it lands in the target process' current working
        # directory, which `run_in_directory` below points at `tmp_path`.
        "open('home_output.txt', 'w').write(json.dumps({\n"
        # Recorded for diagnosis only -- sys.prefix is layout dependent, so it is not asserted.
        "    'prefix': sys.prefix,\n"
        "    'version': platform.python_version(),\n"
        "}))\n"
    )
    # The snippet writes a file and nothing else. The target is a GUI process with no
    # console, so anything printed there would be invisible to the host; a filesystem
    # side effect is the only observable it can check.
    injected = dllinject.pyRunner(notepad)
    injected.run_data(
        [dllinject.StringType(string, False)],
        run_in_directory=tmp_path,
        inject_sys_path=True,
    )
    assert op.exists(op.join(tmp_path, "home_output.txt"))
