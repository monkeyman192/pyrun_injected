# Some extra functions required on top of what pymem provides.

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)


class LPVOID_CHECKED(ctypes._SimpleCData):
    _type_ = "P"

    def _check_retval_(retval):
        if retval is None:
            raise ctypes.WinError(ctypes.get_last_error())
        return retval


HANDLE_CHECKED = LPVOID_CHECKED  # not file handles

kernel32.OpenProcess.restype = HANDLE_CHECKED
kernel32.OpenProcess.argtypes = (
    wintypes.DWORD,  # dwDesiredAccess
    wintypes.BOOL,  # bInheritHandle
    wintypes.DWORD,
)  # dwProcessId

kernel32.GetLastError.restype = wintypes.DWORD

kernel32.GetModuleFileNameW.argtypes = [
    wintypes.HMODULE,  # hModule
    wintypes.LPWSTR,  # lpFilename
    wintypes.DWORD,  # nSize
]
kernel32.GetModuleFileNameW.restype = wintypes.DWORD
