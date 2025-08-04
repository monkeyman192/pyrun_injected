import subprocess
import time
from pyrun_injected.dllinject import pyRunner

notepad = subprocess.Popen(['notepad.exe'])
time.sleep(1)
print(f"Running on pid {notepad.pid}. Press ctrl + C to stop.")
injected = pyRunner(notepad.pid)
injected.run_files(["run_00.py", "run_01.py", "run_02.py"])
notepad.kill()