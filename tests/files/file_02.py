import ctypes
import os.path as op
import platform

import file_01

cwd = op.dirname(__file__)

with open(op.join(cwd, "output.txt"), "w") as f:
    f.write(f"Called from {platform.python_version()}\n")
    f.write(f"A pointer is {ctypes.sizeof(ctypes.c_void_p)} bytes\n")
    f.write(f"file_01.CONSTANT: {str(file_01.CONSTANT)}\n")
