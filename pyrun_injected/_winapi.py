import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32.dll', use_last_error=True)

SIZE_T = ctypes.c_size_t
LPSIZE_T = ctypes.POINTER(SIZE_T)
LPSECURITY_ATTRIBUTES = wintypes.LPVOID
LPTHREAD_START_ROUTINE = wintypes.LPVOID

class BOOL_CHECKED(ctypes._SimpleCData):
    _type_ = "l"
    def _check_retval_(retval):
        if retval == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return retval

class LPVOID_CHECKED(ctypes._SimpleCData):
    _type_ = "P"
    def _check_retval_(retval):
        if retval is None:
            raise ctypes.WinError(ctypes.get_last_error())
        return retval

HANDLE_CHECKED = LPVOID_CHECKED  # not file handles

kernel32.OpenProcess.restype = HANDLE_CHECKED
kernel32.OpenProcess.argtypes = (
    wintypes.DWORD, # dwDesiredAccess
    wintypes.BOOL,  # bInheritHandle
    wintypes.DWORD) # dwProcessId

kernel32.VirtualAllocEx.restype = LPVOID_CHECKED
kernel32.VirtualAllocEx.argtypes = (
    wintypes.HANDLE, # hProcess
    wintypes.LPVOID, # lpAddress
    SIZE_T,          # dwSize
    wintypes.DWORD,  # flAllocationType
    wintypes.DWORD)  # flProtect

kernel32.VirtualFreeEx.argtypes = (
    wintypes.HANDLE, # hProcess
    wintypes.LPVOID, # lpAddress
    SIZE_T,          # dwSize
    wintypes.DWORD)  # dwFreeType

kernel32.WriteProcessMemory.restype = BOOL_CHECKED
kernel32.WriteProcessMemory.argtypes = (
    wintypes.HANDLE,  # hProcess
    wintypes.LPVOID,  # lpBaseAddress
    wintypes.LPCVOID, # lpBuffer
    SIZE_T,           # nSize
    LPSIZE_T)         # lpNumberOfBytesWritten _Out_

kernel32.ReadProcessMemory.restype = BOOL_CHECKED
kernel32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,  # hProcess
    wintypes.LPCVOID, # lpBaseAddress
    wintypes.LPVOID,  # lpBuffer
    SIZE_T,           # nSize
    LPSIZE_T)           # lpNumberOfBytesRead _Out_

kernel32.CreateRemoteThread.restype = HANDLE_CHECKED
kernel32.CreateRemoteThread.argtypes = (
    wintypes.HANDLE,        # hProcess
    LPSECURITY_ATTRIBUTES,  # lpThreadAttributes
    SIZE_T,                 # dwStackSize
    LPTHREAD_START_ROUTINE, # lpStartAddress
    wintypes.LPVOID,        # lpParameter
    wintypes.DWORD,         # dwCreationFlags
    wintypes.LPDWORD)       # lpThreadId _Out_

kernel32.WaitForSingleObject.argtypes = (
    wintypes.HANDLE, # hHandle
    wintypes.DWORD)  # dwMilliseconds

kernel32.CloseHandle.argtypes = (
    wintypes.HANDLE,) # hObject

kernel32.GetLastError.restype = wintypes.DWORD

kernel32.GetExitCodeThread.argtypes = (
    wintypes.HANDLE,  # hThread
    wintypes.LPDWORD,  # lpExitCode
)
kernel32.GetExitCodeThread.restype = BOOL_CHECKED

kernel32.GetModuleHandleExA.argtypes = (
    wintypes.LPCSTR,
)
kernel32.GetModuleHandleExA.restype = wintypes.HMODULE

kernel32.GetModuleFileNameW.argtypes = [
    wintypes.HMODULE,  # hModule
    wintypes.LPWSTR,   # lpFilename
    wintypes.DWORD     # nSize
]
kernel32.GetModuleFileNameW.restype = wintypes.DWORD