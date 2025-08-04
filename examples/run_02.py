import sys
import ctypes
import ctypes.wintypes
import platform
import traceback

try:
    import run_01
    err = None
except Exception:
    err = traceback.format_exc()

kernel32 = ctypes.WinDLL('kernel32')
kernel32.GetModuleFileNameW.argtypes = [
    ctypes.wintypes.HMODULE,  # hModule
    ctypes.wintypes.LPWSTR,   # lpFilename
    ctypes.wintypes.DWORD     # nSize
]
kernel32.GetModuleFileNameW.restype = ctypes.wintypes.DWORD

buffer = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
bytes_copied = kernel32.GetModuleFileNameW(sys.dllhandle, buffer, ctypes.wintypes.MAX_PATH)

with open(f"output{platform.python_version()}.txt", "w") as f:
    f.write(f"Called from {buffer.value}\n")
    try:
        f.write(f"run_01.CONSTANT: {str(run_01.CONSTANT)}")
    except Exception:
        f.write("NO CONSTANT")
    f.write("\n")
