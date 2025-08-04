#define PY_SSIZE_T_CLEAN
#include <stdio.h>
#include <Python.h>

typedef struct {
    uint32_t count;
    char** strings;
} StringArray;


__declspec(dllexport) void run_file(const char* filename) {
    // Run a single file within python.
    FILE* fp;
    errno_t err;
    PyConfig config;
    PyGILState_STATE gstate;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_file");
    Py_InitializeFromConfig(&config);

    err = fopen_s(&fp, filename, "rb");
    if (err == 0) {
        gstate = PyGILState_Ensure();
        // Run the file with python.
        PyRun_SimpleFile(fp, filename);
        PyGILState_Release(gstate);

        fclose(fp);
    }

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
}


__declspec(dllexport) int run_multifile(StringArray* filenames) {
    // Run multiple files sequentially within python.
    uint32_t count = filenames->count;
    FILE* fp;
    errno_t err;
    PyConfig config;
    PyGILState_STATE gstate;
    int retval = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_multifile");
    Py_InitializeFromConfig(&config);

    gstate = PyGILState_Ensure();
    // Run each file.
    for (uint32_t i = 0; i < count; i++) {
        err = fopen_s(&fp, filenames->strings[i], "rb");
        if (err == 0) {
            PyRun_SimpleFile(fp, filenames->strings[i]);
            fclose(fp);
        } else {
            if (retval == 0) {
                retval = i + 1;
            }
        }
    }
    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
    return retval;
}


__declspec(dllexport) void run_string(const char* string) {
    // Run a single string within python.
    PyConfig config;
    PyGILState_STATE gstate;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_string");
    Py_InitializeFromConfig(&config);

    gstate = PyGILState_Ensure();
    // Run the string with python.
    PyRun_SimpleString(string);
    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
}


__declspec(dllexport) void run_multistring(StringArray* strings) {
    // Run multiple strings sequentially within python.
    uint32_t count = strings->count;
    PyConfig config;
    PyGILState_STATE gstate;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_multistring");
    Py_InitializeFromConfig(&config);

    gstate = PyGILState_Ensure();
    // Run each string.
    for (uint32_t i = 0; i < count; i++) {
        PyRun_SimpleString(strings->strings[i]);
    }
    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
}

static PyModuleDef_Slot pyrun_injected_module_slots[] = {
    {0, NULL}
};

static struct PyModuleDef pyrun_injected_module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "pyrun_injected",
    .m_doc = "Run python files or code in python injected into an external process",
    .m_size = 0,  // non-negative
    .m_slots = pyrun_injected_module_slots,
};

PyMODINIT_FUNC
PyInit_dll(void) {
    return PyModuleDef_Init(&pyrun_injected_module);
}

int main(int argc, char *argv[])
{
    return 0;
}