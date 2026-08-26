import ctypes
import os.path as op
import platform
import shutil
from pathlib import Path

import pymem
import pytest

import pyrun_injected.dllinject as dllinject
from pyrun_injected.exceptions import FileInjectionError, StringInjectionError

PYTHON_VERSION = platform.python_version()
POINTER_BYTES = ctypes.sizeof(ctypes.c_void_p)
CWD = op.dirname(__file__)
FILE_DIR = op.join(CWD, "files")


def test_injection(tmp_path: Path, notepad: pymem.Pymem):
    injected = dllinject.pyRunner(notepad)
    shutil.copyfile(op.join(FILE_DIR, "file_01.py"), op.join(tmp_path, "file_01.py"))
    string = """
import platform
with open("string_output.txt", "w") as f:
    f.write(f"Hello from {platform.python_version()}")
"""
    injected.run_data(
        [
            dllinject.StringType(op.join(tmp_path, "file_01.py"), True),
            dllinject.StringType(string, False),
        ],
        run_in_directory=tmp_path,
        inject_sys_path=True,
    )

    assert op.exists(op.join(tmp_path, "string_output.txt"))
    with open(op.join(tmp_path, "string_output.txt")) as f:
        data = f.read()
        assert data == f"Hello from {PYTHON_VERSION}"


def test_injection_with_string_exception(tmp_path: Path, notepad: pymem.Pymem):
    injected = dllinject.pyRunner(notepad)
    shutil.copyfile(op.join(FILE_DIR, "file_01.py"), op.join(tmp_path, "file_01.py"))
    shutil.copyfile(op.join(FILE_DIR, "file_02.py"), op.join(tmp_path, "file_02.py"))
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(StringInjectionError) as exc:
        injected.run_data(
            [
                dllinject.StringType(op.join(tmp_path, "file_01.py"), True),
                dllinject.StringType("a = 1 / 0", False),
                dllinject.StringType(op.join(tmp_path, "file_02.py"), True),
            ],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert "The string provided at index 1 had the following exception:" in str(exc.value)
    assert "ZeroDivisionError" in str(exc.value)

    assert not op.exists(op.join(tmp_path, "output.txt"))


def test_injection_with_file_exception(tmp_path: Path, notepad: pymem.Pymem):
    injected = dllinject.pyRunner(notepad)
    shutil.copyfile(op.join(FILE_DIR, "file_01.py"), op.join(tmp_path, "file_01.py"))
    shutil.copyfile(op.join(FILE_DIR, "file_03.py"), op.join(tmp_path, "file_03.py"))
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(FileInjectionError) as exc:
        injected.run_data(
            [
                dllinject.StringType(op.join(tmp_path, "file_01.py"), True),
                dllinject.StringType("a = 1 / 2", False),
                dllinject.StringType(op.join(tmp_path, "file_03.py"), True),
            ],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert f"There was an exception running the file {op.join(tmp_path, 'file_03.py')}:" in str(exc.value)
    assert "ZeroDivisionError" in str(exc.value)

    assert not op.exists(op.join(tmp_path, "output.txt"))


def test_injection_with_SyntaxError(tmp_path: Path, notepad: pymem.Pymem):
    injected = dllinject.pyRunner(notepad)
    shutil.copyfile(op.join(FILE_DIR, "file_01.py"), op.join(tmp_path, "file_01.py"))
    shutil.copyfile(op.join(FILE_DIR, "file_04.py"), op.join(tmp_path, "file_04.py"))
    # Check we get the right exception raised and the message is correct.
    with pytest.raises(SyntaxError) as exc:
        injected.run_data(
            [
                dllinject.StringType(op.join(tmp_path, "file_01.py"), True),
                dllinject.StringType("a = 1 / 2", False),
                dllinject.StringType(op.join(tmp_path, "file_04.py"), True),
            ],
            run_in_directory=tmp_path,
            inject_sys_path=True,
        )
    assert "invalid syntax (file_04.py, line 1)" in str(exc.value)
    assert "This file has a syntax error" in str(exc.value.text)

    assert not op.exists(op.join(tmp_path, "output.txt"))
