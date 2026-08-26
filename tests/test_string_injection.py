import os.path as op
import platform
from pathlib import Path

import pymem
import pytest

import pyrun_injected.dllinject as dllinject
from pyrun_injected.exceptions import StringInjectionError

PYTHON_VERSION = platform.python_version()


def test_injection(tmp_path: Path, notepad: pymem.Pymem):
    string = """
import platform
open("string_output.txt", "w").write(f"Hello from {platform.python_version()}")
"""

    injected = dllinject.pyRunner(notepad)
    injected.run_data(
        [dllinject.StringType(string, False)],
        run_in_directory=tmp_path,
        inject_sys_path=True,
    )

    assert op.exists(op.join(tmp_path, "string_output.txt"))
    with open(op.join(tmp_path, "string_output.txt")) as f:
        data = f.read()
        assert data == f"Hello from {PYTHON_VERSION}"


def test_injection_with_exception(tmp_path: Path, notepad: pymem.Pymem):
    string = """a = 1/0"""

    injected = dllinject.pyRunner(notepad)
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(StringInjectionError) as exc:
        injected.run_data(
            [dllinject.StringType(string, False)],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert "The string provided at index 0 had the following exception:" in str(exc.value)
    assert "ZeroDivisionError" in str(exc.value)


def test_multi_injection_with_exception(tmp_path: Path, notepad: pymem.Pymem):
    string1 = "m = 1234"
    string2 = "a = m/0"
    string3 = """
import platform
open("string_output.txt", "w").write(f"Hello from {platform.python_version()}")
    """

    injected = dllinject.pyRunner(notepad)
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(StringInjectionError) as exc:
        injected.run_data(
            [
                dllinject.StringType(string1, False),
                dllinject.StringType(string2, False),
                dllinject.StringType(string3, False),
            ],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert "The string provided at index 1 had the following exception:" in str(exc.value)
    assert "ZeroDivisionError" in str(exc.value)

    assert not op.exists(op.join(tmp_path, "string_output.txt"))


def test_injection_with_SyntaxError(tmp_path: Path, notepad: pymem.Pymem):
    string1 = "m = 1234"
    string2 = "this is not valid python"
    string3 = "a = m/0"

    injected = dllinject.pyRunner(notepad)
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(SyntaxError) as exc:
        injected.run_data(
            [
                dllinject.StringType(string1, False),
                dllinject.StringType(string2, False),
                dllinject.StringType(string3, False),
            ],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert "invalid syntax in string at index 1 (line 1)" in str(exc.value)
    assert "this is not valid python" in str(exc.value.text)

    assert not op.exists(op.join(tmp_path, "string_output.txt"))
