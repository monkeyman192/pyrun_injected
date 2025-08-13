import os.path as op
import subprocess
import time

import pymem

import pyrun_injected.dllinject as dllinject

cwd = op.dirname(__file__)

notepad = subprocess.Popen(['notepad.exe'])
time.sleep(1)
print(f"Running on pid {notepad.pid}. Press ctrl + C to stop.")

pm = pymem.Pymem("notepad.exe")

injected = dllinject.pyRunner(pm)
injected.run_data(
    [
        dllinject.StringType(op.join(cwd, "run_02.py"), True)
    ],
    run_in_directory=cwd,
    inject_sys_path=True,
)
notepad.kill()