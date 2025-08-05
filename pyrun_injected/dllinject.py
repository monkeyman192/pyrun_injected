# Mush of this code is initially taken from https://stackoverflow.com/a/17524073 with heavy modifications.

import ctypes
from ctypes import wintypes
import struct
import sys
from typing import Union

import pyrun_injected.dll
from pyrun_injected._winapi import kernel32


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
    succeeded = kernel32.GetExitCodeThread(tid, ctypes.byref(res))
    if succeeded:
        return res.value
    else:
        return None


def write_to_mem(handle: int, data: Union[bytes, str]) -> int:
    size = (len(data) + 1) * WCHAR_SIZE
    addr = kernel32.VirtualAllocEx(handle, None, size, MEM_COMMIT, PAGE_READWRITE)
    kernel32.WriteProcessMemory(handle, addr, data, size, None)
    return addr


def run_in_thread(pid: int, func, addr: int, return_val: bool = False) -> int:
    tid = kernel32.CreateRemoteThread(pid, None, 0, func, addr, 0, None)
    kernel32.WaitForSingleObject(tid, INFINITE)
    err = kernel32.GetLastError()
    ret = None
    if err:
        print(f"Error running {func} in a thread: {err}")
    if return_val:
        ret = get_thread_ret(tid)
    if tid is not None:
        kernel32.CloseHandle(tid)
    return ret or -1


def write_multistrings(hproc, strings: list[str], allocated_addrs: list[int]) -> int:
    count = len(strings)
    addresses = []
    for string in strings:
        addr = write_to_mem(hproc, string.encode())
        addresses.append(addr)
    # Write the array of pointers to memory
    char_p_data = struct.pack(f"<{count}Q", *addresses)
    allocated_addrs.extend(addresses)
    char_p_addr = write_to_mem(hproc, char_p_data)
    allocated_addrs.append(char_p_addr)
    # Then pack this up with the count and write this to memory.
    fmt = "<QQ"  # write the count as a uint64 because struct isn't smart enough I think...
    data = struct.pack(fmt, count, char_p_addr)
    final_addr = write_to_mem(hproc, data)
    allocated_addrs.append(final_addr)
    return final_addr


class pyRunner:
    hproc: int

    def __init__(self, pid: int):
        self.allocated_addrs: list[int] = []
        self.hproc = kernel32.OpenProcess(
            PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE,
            False,
            pid,
        )
        if self.hproc is None:
            raise ValueError(f"Unable to open process with pid {pid}")

        self._inject_python_dll()
        self._inject_runpy_injected_dll()

    def _inject_python_dll(self):
        # Inject python dll into remote process.
        buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        kernel32.GetModuleFileNameW(sys.dllhandle, buffer, wintypes.MAX_PATH)
        py_dllpath = buffer.value
        addr = write_to_mem(self.hproc, py_dllpath)
        self.allocated_addrs.append(addr)
        run_in_thread(self.hproc, kernel32.LoadLibraryW, addr)

    def _inject_runpy_injected_dll(self):
        # Inject runpy_injected pyd into remote process.
        pystring_dllpath = pyrun_injected.dll.__file__
        addr = write_to_mem(self.hproc, pystring_dllpath)
        self.allocated_addrs.append(addr)
        run_in_thread(self.hproc, kernel32.LoadLibraryW, addr)
        self.pystring_dll = ctypes.PyDLL(pystring_dllpath)

    def cleanup(self):
        for addr in self.allocated_addrs:
            if addr is not None:
                kernel32.VirtualFreeEx(self.hproc, addr, 0, MEM_RELEASE)
        if self.hproc is not None:
            kernel32.CloseHandle(self.hproc)

    def run_files(self, filepaths: list[str]):
        """Run the specified files within the remote process."""
        ran_string = -1
        if len(filepaths) == 1:
            # Do the simpler method of just writing the one string
            if addr := write_to_mem(self.hproc, filepaths[0].encode()):
                self.allocated_addrs.append(addr)
                ran_string = run_in_thread(
                    self.hproc, self.pystring_dll.run_file, addr, True
                )
        else:
            code_addr = write_multistrings(self.hproc, filepaths, self.allocated_addrs)
            ran_string = run_in_thread(
                self.hproc, self.pystring_dll.run_multifile, code_addr, True
            )
        self.cleanup()
        if ran_string == 0:
            # In this case, no error. Just return.
            return
        elif ran_string > 0:
            raise ValueError(
                f"There was an error running the file {filepaths[ran_string - 1]}"
            )

    def run_strings(self, strings: list[str]):
        """Run the provided strings within the remote process."""
        if len(strings) == 1:
            if addr := write_to_mem(self.hproc, strings[0].encode()):
                self.allocated_addrs.append(addr)
                ran_string = run_in_thread(
                    self.hproc, self.pystring_dll.run_string, addr, True
                )
        else:
            code_addr = write_multistrings(self.hproc, strings, self.allocated_addrs)
            ran_string = run_in_thread(
                self.hproc, self.pystring_dll.run_multistring, code_addr, True
            )
            print(f"String ran successfully? {ran_string == 0}")
        self.cleanup()
