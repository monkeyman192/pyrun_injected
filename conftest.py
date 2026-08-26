import subprocess
import time
from typing import Generator

import pymem
import pytest


@pytest.fixture
def notepad() -> Generator[pymem.Pymem, None, None]:
    notepad = subprocess.Popen(['notepad.exe'])
    time.sleep(1)
    pm = pymem.Pymem("notepad.exe")
    try:
        yield pm
    finally:
        notepad.kill()
