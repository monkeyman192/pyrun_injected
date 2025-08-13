import ctypes
import os.path as op
import struct
import sys
from ctypes import wintypes
from typing import NamedTuple, Optional, Union

import pymem
import pymem.process
import pymem.ressources

import pyrun_injected.dll
from pyrun_injected._win32utils import kernel32

CWD = op.dirname(__file__)


class StringType(NamedTuple):
    value: str
    is_file: bool


class ErrorData(ctypes.Structure):
    _fields_ = [
        ("p_error_msg", ctypes.c_uint64),  # char*
        ("msg_length", ctypes.c_uint32),
        ("bad_string_idx", ctypes.c_uint32),
    ]
    p_error_msg: int
    msg_length: int
    bad_string_idx: int


class RunData(ctypes.Structure):
    _fields_ = [
        ("count", ctypes.c_uint32),
        ("p_strings", ctypes.c_uint64),
        ("p_error", ctypes.c_uint64),  # ErrorData*
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


def write_to_mem(handle: int, data: Union[bytes, str]) -> int:
    size = (len(data) + 1) * WCHAR_SIZE
    addr = pymem.ressources.kernel32.VirtualAllocEx(handle, None, size, MEM_COMMIT, PAGE_READWRITE)
    pymem.ressources.kernel32.WriteProcessMemory(handle, addr, data, size, None)
    return addr


def run_in_thread(pid: int, func, addr: int, return_val: bool = False) -> int:
    func_addr = ctypes.cast(func, ctypes.c_void_p).value
    tid = pymem.ressources.kernel32.CreateRemoteThread(pid, None, 0, func_addr, addr, 0, None)
    pymem.ressources.kernel32.WaitForSingleObject(tid, INFINITE)
    err = kernel32.GetLastError()
    ret = None
    if err:
        print(f"Error running {func} in a thread: {err}")
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
    struct_data_data = struct.pack(f"<{2 * count}Q", *string_data_values)
    allocated_addrs.extend(addresses)
    struct_data_addr = write_to_mem(hproc, struct_data_data)
    allocated_addrs.append(struct_data_addr)
    # Write some meory for the ErrorData struct to be written to.
    error_data_addr = write_to_mem(hproc, struct.pack("<QQ", 0, 0))
    allocated_addrs.append(error_data_addr)
    # Then pack this up with the count and write this to memory.
    fmt = "<QQQ"  # write the count as a uint64 because struct isn't smart enough I think...
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

    def _inject_python_dll(self):
        # Inject python dll into the remote process.
        buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        kernel32.GetModuleFileNameW(sys.dllhandle, buffer, wintypes.MAX_PATH)
        py_dllpath = buffer.value
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

    def run_data(
        self,
        strings: list[StringType],
        run_in_directory: Optional[str] = None,
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
        if run_in_directory is not None:
            # Add an extra string to be run which changes the current working directory.
            cwd_change = f"""import os
os.chdir({run_in_directory!r})
"""
            strings = [StringType(cwd_change, False), *strings]
            if inject_sys_path:
                sys_path_str = f"""import sys
sys.path.append({run_in_directory!r})
"""
                strings = [StringType(sys_path_str, False), *strings]
        code_addr = write_string_data(self.hproc, strings, self.allocated_addrs)
        run_data_addr = func_addr(b"run_data", self.pyrun_handle, self.pyrun_lib_h)
        ran_string = run_in_thread(self.hproc, run_data_addr, code_addr, True)
        if ran_string != 0:
            # Read the error data out of memory.
            rd = RunData()
            self.pm.read_ctype(code_addr, rd)
            ed = ErrorData()
            self.pm.read_ctype(rd.p_error, ed)
            print(ed.msg_length)
            error_msg = self.pm.read_string(ed.p_error_msg, ed.msg_length)
            bad_string_idx = ed.bad_string_idx
            print(f"There was an exception running {strings[bad_string_idx]}:")
            print(error_msg)

        self._cleanup()
