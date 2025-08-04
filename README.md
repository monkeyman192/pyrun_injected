# pyrun_injected

Run python files and scripts in python which has been injected into another process.

## Why?

The usual way of running python scripts with an injected python dll wasn't able to be run on python 3.12 and above.

It seems that this was because the `PyRun_SimpleString` command needs to be run in the same thread as the `Py_InitializeFromConfig` and `Py_FinalizeEx` calls. Using the windows API it doesn't seem possible to execute multiple commands in the same thread.

`pyrun_injected` fixes this by calling all the necessary functions in one function so that we can call this function and have everything run in the same thread.

Finally, because we are writing this from scratch, we can add some extra functionality into the API for added flexibility.

## c API

`pyrun_injected` provides 4 functions which are useful for calling:

### `void pyrun_injected.dll.run_file(const char* filename)`:

Run the specified file name in the injected process.

### `int pyrun_injected.dll.run_multifile(StringArray* filenames)`:

Run the specified list of file names in the injected process.

This will return 0 if everything went well. If the return value is greater than 0 it is the index of the file which failed starting at 1 (to avoid clashing with the case of 0 being "everything went fine").

### `void pyrun_injected.dll.run_string(const char* string)`:

Run the specified string in the injected process.

### `void pyrun_injected.dll.run_multistring(StringArray* strings)`:

Run the specified list of strings in the injected process.

`StringArray` is defined as follows:

```c
typedef struct {
    uint32_t count;
    char** strings;
} StringArray;
```

We pass in a struct like this rather than having multiple arguments because the Windows API only allows us to pass in one argument.

## python API

The python API provides a single class which simplifies injecting and calling strings and files in python.

### `pyrun_injected.dllinject.pyRunner(pid: int)`:

Initialise this class with the pid of the process you want to inject python and `pyrun_injected` into.

Once initialised, this class provides two methods for running python code:

`pyRunner.run_files(filepaths: list[str])` and ``pyRunner.run_strings(strings: list[str])`

Both of these functions take a list of strings as arguments. The first being strings which represent filepaths to files to be run in the specified process, and the latter being strings which are interpreted as python code to be executed.

Note: It's important that all python code which is to be run which requires any other piece of code be run together. Once the code finalises after running the strings or files any data will not be persisted.

## Example usage

```py
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
```

The above will start notepad, and then inject python and run the string in it. You should see the `output.txt` file be produced with the version of python used.
