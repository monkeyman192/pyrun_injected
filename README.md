# pyrun-injected

Run python files and scripts in python which has been injected into another process.

## Why?

The usual way of running python scripts with an injected python dll wasn't able to be run on python 3.12 and above.

It seems that this was because the `PyRun_SimpleString` command needs to be run in the same thread as the `Py_InitializeFromConfig` and `Py_FinalizeEx` calls. Using the windows API it doesn't seem possible to execute multiple commands in the same thread.

`pyrun-injected` fixes this by calling all the necessary functions in one function so that we can call this function and have everything run in the same thread.

Finally, because we are writing this from scratch, we can add some extra functionality into the API for added flexibility.

To this end `pyrun-injected` uses `PyRun_String` and `PyRun_File` under the hood instead of `PyRun_SimpleString` and `PyRun_SimpleFile` so that we may get back any exception which is raised by calling the code, thus giving us better visibility on what went wrong if something did.

## c API

`pyrun-injected` provides 3 functions which are useful for calling:

### `int pyrun_injected.dll.run_file(const char* filename)`:

Run the specified file name in the injected process.
This will return 0 on success, and 1 on failure.

### `int pyrun_injected.dll.run_string(const char* string)`:

Run the specified string in the injected process.
This will return 0 on success, and 1 on failure.

### `int pyrun_injected.dll.run_data(RunData* data)`:

Run a sequence of strings and/or files sequentially within a single session.
This will return 0 on success, and 1 on failure.
On failure, `RunData->error` will have the stacktrace written into it. See below for details.

`RunData` and associated structs are defined as follows:

```c
typedef struct {
    char* error_msg;         // The actual error message we get from the traceback.
    size_t msg_length;       // The length of the error message in bytes.
    uint32_t bad_string_idx; // The index of the string that had the issue.
} ErrorData;

typedef struct {
    const char* string_value;
    uint8_t is_file;
} StringData;

typedef struct {
    uint32_t count;      // Total size of strings field.
    StringData* strings; // The actual string data to be run.
    ErrorData* error;    // Error data (if an error occurs).
} RunData;
```

We pass in a struct like this rather than having multiple arguments because the Windows API only allows us to pass in one argument.

## python API

The python API provides a single class which simplifies injecting and calling strings and files in python.

### `pyrun_injected.dllinject.pyRunner(pm: pymem.Pymem)`:

This function takes an instance of a `Pymem` class as it's only constructor argument. This is because we use pymem a lot internally.
The running python version and `pyrun-injected` will both be injected into this process.

Once initialised, this class provides just one method for running code:

```py
def run_data(
    self,
    strings: list[StringType],
    run_in_directory: Optional[str] = None,
    inject_sys_path: bool = False,
):
```

where `StringType` is a `NamedTuple` defined as such:

```py
class StringType(NamedTuple):
    value: str
    is_file: bool
```

This function allows you to pass in a mix of filepaths and strings to be run in the specified order.
It is strongly recommended that filepaths are provided as absolute paths, unless all are in a specifi directory, in which case that path should be passed in to this function as the `run_in_directory` argument.

Note: It's important that all python code which is to be run which requires any other piece of code be run together. Once the code finalises after running the strings or files any data will not be persisted.

## Example usage

```py
import subprocess
import time
from pyrun_injected.dllinject import pyRunner, StringType
import pymem
import os.path as op

cwd = op.dirname(__file__)

notepad = subprocess.Popen(['notepad.exe'])
time.sleep(1)
print(f"Running on pid {notepad.pid}. Press ctrl + C to stop.")
pm = pymem.Pymem("notepad.exe")
injected = pyRunner(pm)
string = """import platform
with open("output.txt", "w") as f:
    f.write(f"hello from {platform.python_version()}")
"""
injected.run_data([StringType(string, False)], run_in_directory=cwd)
notepad.kill()
```

The above will start notepad, and then inject python and run the string in it. You should see the `output.txt` file be produced in the same directory as the file with the version of python used.
