from __future__ import annotations

import ctypes
import os.path as op
import struct
import sys
from ctypes import wintypes
from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import NamedTuple

import pymem
import pymem.process
import pymem.ressources.kernel32

import pyrun_injected.dll
from pyrun_injected._win32utils import kernel32
from pyrun_injected.exceptions import FileInjectionError, InjectionError, StringInjectionError

CWD = op.dirname(__file__)

logger = getLogger(__name__)

# Check to see if we're running on 32 or 64 bit python and get the approriate pointer type.
if ctypes.sizeof(ctypes.c_void_p) == 8:
    PTR_TYPE = ctypes.c_uint64  # ctypes pointer type
    SPTR_TYPE = "Q"  # struct pointer type
else:
    PTR_TYPE = ctypes.c_uint32  # ctypes pointer type
    SPTR_TYPE = "L"  # struct pointer type

# Check the python version. If less than 3.10, have a flag so that we don't try and pass in some values to the
# SyntaxError constructor.
if sys.version_info >= (3, 10):
    FULL_SYNTAX_ERROR = True
else:
    FULL_SYNTAX_ERROR = False


class StringType(NamedTuple):
    value: str
    is_file: bool


class SyntaxErrorData(ctypes.Structure):
    _fields_ = [
        ("p_error_msg", PTR_TYPE),  # char*
        ("msg_length", ctypes.c_size_t),  # size_t
        ("lineno", ctypes.c_int32),
        ("end_lineno", ctypes.c_int32),  # For python 3.9 this will be -1
        ("offset", ctypes.c_int32),
        ("end_offset", ctypes.c_int32),  # For python 3.9 this will be -1
    ]
    p_error_msg: int
    msg_length: int
    lineno: int
    end_lineno: int
    offset: int
    end_offset: int


class ErrorData(ctypes.Structure):
    _fields_ = [
        ("p_error_msg", PTR_TYPE),  # char*
        ("msg_length", ctypes.c_size_t),  # size_t
        ("bad_string_idx", ctypes.c_uint32),
        ("p_syntax_error_data", PTR_TYPE),  # SyntaxErrorData*
    ]
    p_error_msg: int
    msg_length: int
    bad_string_idx: int
    p_syntax_error_data: int


class RunData(ctypes.Structure):
    _fields_ = [
        ("count", ctypes.c_uint32),
        ("p_strings", PTR_TYPE),
        ("p_error", PTR_TYPE),  # ErrorData*
    ]
    count: int
    p_strings: int
    p_error: int


PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
PROCESS_CREATE_THREAD = 0x0002
MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x0004
INFINITE = -1

WCHAR_SIZE = ctypes.sizeof(wintypes.WCHAR)


def get_thread_ret(tid: int):
    res = wintypes.DWORD(0)
    succeeded = pymem.ressources.kernel32.GetExitCodeThread(tid, ctypes.byref(res))
    if succeeded:
        return res.value
    else:
        return None


def write_to_mem(handle: int, data: bytes | str) -> int:
    size = (len(data) + 1) * WCHAR_SIZE
    addr = pymem.ressources.kernel32.VirtualAllocEx(handle, None, size, MEM_COMMIT, PAGE_READWRITE)
    pymem.ressources.kernel32.WriteProcessMemory(handle, addr, data, size, None)
    return addr


def run_in_thread(pid: int, func, addr: int, return_val: bool = False) -> int:
    """Run the specified funtion by address in a remote thread under the provided process id."""
    func_addr = ctypes.cast(func, ctypes.c_void_p).value
    tid = pymem.ressources.kernel32.CreateRemoteThread(pid, None, 0, func_addr, addr, 0, None)
    pymem.ressources.kernel32.WaitForSingleObject(tid, INFINITE)
    err = kernel32.GetLastError()
    ret = None
    if err:
        logger.error(f"Error running {func} in a thread: {err}")
    if return_val:
        ret = get_thread_ret(tid)
    if tid is not None:
        pymem.ressources.kernel32.CloseHandle(tid)
    if ret is None:
        return -1
    else:
        return ret


def write_string_data(hproc, strings: list[StringType], allocated_addrs: list[int]) -> int:
    count = len(strings)
    addresses = []
    string_data_values = []
    for string_data in strings:
        addr = write_to_mem(hproc, string_data.value.encode())
        # Add the address and then the bool value
        string_data_values.append(addr)
        string_data_values.append(int(string_data.is_file))
        addresses.append(addr)
    # Write the array of StringData to memory
    struct_data_data = struct.pack(f"<{2 * count}{SPTR_TYPE}", *string_data_values)
    allocated_addrs.extend(addresses)
    struct_data_addr = write_to_mem(hproc, struct_data_data)
    allocated_addrs.append(struct_data_addr)
    # Write some memory for the SytaxErrorData struct to be written to.
    syntaxerror_data_len = ctypes.sizeof(SyntaxErrorData)
    syntaxerror_data_addr = write_to_mem(hproc, struct.pack(f"<{syntaxerror_data_len}x"))
    allocated_addrs.append(syntaxerror_data_addr)
    # Write some memory for the ErrorData struct to be written to.
    # Write it as 4x the size of a pointer since this is what the struct will end up looking like.
    error_data_addr = write_to_mem(hproc, struct.pack(f"<4{SPTR_TYPE}x", 0, 0, 0, syntaxerror_data_addr))
    allocated_addrs.append(error_data_addr)
    # Then pack this up with the count and write this to memory.
    fmt = f"<3{SPTR_TYPE}"  # write the count as a uint32/64 because struct isn't smart enough I think...
    data = struct.pack(fmt, count, struct_data_addr, error_data_addr)
    final_addr = write_to_mem(hproc, data)
    allocated_addrs.append(final_addr)
    return final_addr


def func_addr(func_name: bytes, local_handle: int, lib_handle: int):
    return lib_handle + pymem.ressources.kernel32.GetProcAddress(local_handle, func_name) - local_handle


class pyRunner:
    hproc: int

    def __init__(self, pm: pymem.Pymem):
        self.pm = pm
        self.allocated_addrs: list[int] = []
        self.hproc = kernel32.OpenProcess(
            PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE,
            False,
            pm.process_id,
        )
        if self.hproc is None:
            raise ValueError(f"Unable to open process with pid {pm.process_id}")

        self._inject_python_dll()
        self._inject_runpy_injected_dll()
        self.set_python_home(self.python_home)

    def _inject_python_dll(self):
        # Inject python dll into the remote process.
        buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        kernel32.GetModuleFileNameW(sys.dllhandle, buffer, wintypes.MAX_PATH)
        py_dllpath = buffer.value
        # CPython cannot reliably detect its own prefix inside the target process, so
        # remember it here: this is the directory of the interpreter dll we are about
        # to inject, which is exactly what PyConfig.home has to be.
        self.python_home = op.dirname(py_dllpath)
        self.python_lib_h = pymem.process.inject_dll_from_path(self.pm.process_handle, py_dllpath)
        self.py_handle = pymem.ressources.kernel32.GetModuleHandleW(op.basename(py_dllpath))

    def _inject_runpy_injected_dll(self):
        # Inject runpy_injected pyd into the remote process.
        pyrun_dll = pyrun_injected.dll.__file__
        self.pystring_dll = ctypes.PyDLL(pyrun_dll)
        self.pyrun_lib_h = pymem.process.inject_dll_from_path(self.pm.process_handle, pyrun_dll)
        self.pyrun_handle = pymem.ressources.kernel32.GetModuleHandleW(op.basename(pyrun_dll))

    def _cleanup(self):
        for addr in self.allocated_addrs:
            if addr is not None:
                pymem.ressources.kernel32.VirtualFreeEx(self.hproc, addr, 0, MEM_RELEASE)
        if self.hproc is not None:
            pymem.ressources.kernel32.CloseHandle(self.hproc)

    def set_python_home(self, home: str) -> None:
        """Set the prefix (``PyConfig.home``) the injected interpreter will use.

        ``PyConfig_InitPythonConfig`` leaves ``home`` as NULL, which makes CPython
        auto-detect its prefix. Inside an injected process that detection can fail, so
        the value is supplied explicitly instead.

        Parameters
        ----------
        home
            The Python installation prefix inside the target process.
        """
        addr = write_to_mem(self.hproc, home.encode("utf-8"))
        self.allocated_addrs.append(addr)
        set_home_addr = func_addr(b"set_python_home", self.pyrun_handle, self.pyrun_lib_h)
        if run_in_thread(self.hproc, set_home_addr, addr, True) != 0:
            logger.error(f"Unable to set the python home to {home!r}")

    def run_data(
        self,
        strings: list[StringType],
        run_in_directory: PathLike[str] | str | None = None,
        inject_sys_path: bool = False,
    ):
        """Run the provided strings within the remote process.

        Parameters
        ----------
        strings
            A list of the ``StringType`` objects which will all be run sequentially.
        run_in_directory
            If not None, the value will be passed into following code which will be injected and run before
            any other code:

            .. code-block:: py
                import os
                os.chdir({run_in_directory})
        inject_sys_path
            If True, the following code will be run before any other code (including the above):

            .. code-block:: py
                import sys
                sys.path.append({run_in_directory})
            Note: This requires ``run_in_directory`` to be not None so that the value may be used.
        """
        additional_indexes = 0
        if run_in_directory is not None:
            # If we receive a Path instance, convert to a string for injection.
            if isinstance(run_in_directory, Path):
                run_in_directory = str(run_in_directory)
            # Add an extra string to be run which changes the current working directory.
            cwd_change = f"""import os
os.chdir({run_in_directory!r})
"""
            strings = [StringType(cwd_change, False), *strings]
            additional_indexes += 1
            if inject_sys_path:
                sys_path_str = f"""import sys
sys.path.append({run_in_directory!r})
"""
                strings = [StringType(sys_path_str, False), *strings]
                additional_indexes += 1
        code_addr = write_string_data(self.hproc, strings, self.allocated_addrs)
        run_data_addr = func_addr(b"run_data", self.pyrun_handle, self.pyrun_lib_h)
        ran_string = run_in_thread(self.hproc, run_data_addr, code_addr, True)

        # Check whether there was an exception and raise it right at the end if there was.
        exception_type = None
        error_msg = None
        exception_arg = None
        if ran_string != 0:
            # Read the error data out of memory.
            rd = RunData()
            self.pm.read_ctype(code_addr, rd)
            ed = ErrorData()
            self.pm.read_ctype(rd.p_error, ed)
            sed = SyntaxErrorData()
            self.pm.read_ctype(ed.p_syntax_error_data, sed)
            if ed.msg_length:
                error_msg = self.pm.read_string(ed.p_error_msg, ed.msg_length)
                bad_index = int(ed.bad_string_idx)
                bad_string = strings[bad_index]
                if sed.msg_length:
                    SE_error_msg = str(self.pm.read_string(sed.p_error_msg, sed.msg_length))
                    if bad_string.is_file:
                        filename = bad_string.value
                    else:
                        filename = None
                        error_msg += f" in string at index {bad_index - additional_indexes}"
                    if FULL_SYNTAX_ERROR:
                        exception_arg = (
                            filename,
                            sed.lineno,
                            sed.offset,
                            SE_error_msg,
                            sed.end_lineno,
                            sed.end_offset,
                        )
                    else:
                        exception_arg = (filename, sed.lineno, sed.offset, SE_error_msg)
                    exception_type = SyntaxError
                else:
                    if bad_string.is_file:
                        exception_arg = bad_string.value
                        exception_type = FileInjectionError
                    else:
                        exception_arg = bad_index - additional_indexes
                        exception_type = StringInjectionError
            else:
                exception_arg = ran_string
                error_msg = None
                exception_type = InjectionError
            # If we have an error allocated somewhere, then release that memory using a function exposed by
            # the dll.
            if ed.p_error_msg != 0 or sed.p_error_msg != 0:
                fr_addr = func_addr(b"free_resource", self.pyrun_handle, self.pyrun_lib_h)
                if ed.p_error_msg != 0:
                    if (ran_cleanup := run_in_thread(self.hproc, fr_addr, ed.p_error_msg, True)) != 0:
                        logger.error(f"Unable to cleanup memory for error string: 0x{ran_cleanup:X}")
                if sed.p_error_msg != 0:
                    if (ran_cleanup := run_in_thread(self.hproc, fr_addr, sed.p_error_msg, True)) != 0:
                        logger.error(f"Unable to cleanup memory for SyntaxError string: 0x{ran_cleanup:X}")

        self._cleanup()
        if exception_type:
            raise exception_type(error_msg, exception_arg)  # type: ignore
