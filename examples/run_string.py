import subprocess
import time
from pyrun_injected.dllinject import pyRunner

notepad = subprocess.Popen(['notepad.exe'])
time.sleep(1)
print(f"Running on pid {notepad.pid}. Press ctrl + C to stop.")
injected = pyRunner(notepad.pid)
string = """import platform
with open("output.txt", "w") as f:
    f.write(f"hello from {platform.python_version()}")
"""
injected.run_strings([string])
notepad.kill()