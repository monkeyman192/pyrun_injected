#define PY_SSIZE_T_CLEAN
#include <stdio.h>
#include <Python.h>
#include <traceback.h>
#include <wchar.h>
#include <windows.h>

typedef struct {
    char *error_msg;            // The SyntaxError message
    size_t msg_length;          // The length of the SyntaxError message in bytes.
    int32_t lineno;             // The line number.
    int32_t end_lineno;         // The end line number.
    int32_t offset;             // The offset in the line.
    int32_t end_offset;         // The end offset in the line.
} SyntaxErrorData;

typedef struct {
    char* error_msg;                        // The actual error message we get from the traceback.
    size_t msg_length;                      // The length of the error message in bytes.
    uint32_t bad_string_idx;                // The index of the string that had the issue.
    SyntaxErrorData* syntax_error_data;     // SyntaxError data. Only set if the exception was a syntax error.

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

// The prefix CPython must use inside the target process. PyConfig_InitPythonConfig
// leaves `home` as NULL, which asks CPython to auto-detect its prefix. Inside an
// injected process that detection can fail and the interpreter then cannot even
// find `encodings`. The host knows which python3XX.dll it injected, so it supplies
// the prefix up front via set_python_home().
static wchar_t g_python_home[MAX_PATH] = {0};

__declspec(dllexport) int set_python_home(const char *home) {
    // Set the directory used as CPython's prefix (PyConfig.home) inside the target process.
    // The value is copied, so the caller may free `home` as soon as this returns.
    if (home == NULL || home[0] == '\0') {
        return 1;
    }
    if (MultiByteToWideChar(CP_UTF8, 0, home, -1, g_python_home, MAX_PATH) == 0) {
        g_python_home[0] = L'\0';
        return 1;
    }
    return 0;
}

static int set_config_home(PyConfig *config) {
    // Point config->home at the prefix of the interpreter this module is bound to.
    // Returns non-zero on success.
    wchar_t dll_name[32];
    wchar_t path[MAX_PATH];
    wchar_t *slash;
    HMODULE hmod;

    if (g_python_home[0]) {
        // An explicit value from the host takes precedence.
        return !PyStatus_Exception(PyConfig_SetString(config, &config->home, g_python_home));
    }

    // Otherwise fall back to the directory of the python3XX.dll we are linked against.
    // It cannot be derived from this module's own path: the .pyd is installed into
    // site-packages, while the interpreter's prefix is where python3XX.dll lives.
    // Not finding it is not fatal -- home stays NULL and we keep the previous behaviour.
#ifdef Py_DEBUG
    swprintf(dll_name, 32, L"python%d%d_d.dll", PY_MAJOR_VERSION, PY_MINOR_VERSION);
#else
    swprintf(dll_name, 32, L"python%d%d.dll", PY_MAJOR_VERSION, PY_MINOR_VERSION);
#endif
    hmod = GetModuleHandleW(dll_name);
    if (hmod == NULL || GetModuleFileNameW(hmod, path, MAX_PATH) == 0) {
        return 0;
    }
    slash = wcsrchr(path, L'\\');
    if (slash == NULL) {
        return 0;
    }
    *slash = L'\0';
    return !PyStatus_Exception(PyConfig_SetString(config, &config->home, path));
}

__declspec(dllexport) int run_file(const char *filename) {
    // Run a single file within python.
    FILE *fp;
    errno_t err;
    PyConfig config;
    PyStatus status;
    PyGILState_STATE gstate;
    int ret = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);

    status = PyConfig_SetBytesString(&config, &config.program_name, "run_file");
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 1;
    }

    // CPython cannot reliably detect its prefix from inside the target process.
    set_config_home(&config);
    config.install_signal_handlers = 0;

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        return 1;
    }

    err = fopen_s(&fp, filename, "rb");
    if (err == 0) {
        gstate = PyGILState_Ensure();
        // Run the file with python.
        ret = PyRun_SimpleFile(fp, filename);
        PyGILState_Release(gstate);

        fclose(fp);
    } else {
        ret = 1;
    }

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
    return ret;
}


__declspec(dllexport) int run_string(const char *string) {
    // Run a single string within python.
    PyConfig config;
    PyStatus status;
    PyGILState_STATE gstate;
    int res = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);

    status = PyConfig_SetBytesString(&config, &config.program_name, "run_string");
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return 1;
    }

    // CPython cannot reliably detect its prefix from inside the target process.
    set_config_home(&config);
    config.install_signal_handlers = 0;

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        return 1;
    }

    gstate = PyGILState_Ensure();
    // Run the string with python.
    res = PyRun_SimpleString(string);

    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }

    return res;
}

static void set_error_msg(RunData *data, const char *msg, uint32_t idx) {
    // Set the error message details.
    data->error->error_msg = _strdup(msg);
    data->error->msg_length = strlen(msg);
    data->error->bad_string_idx = idx;
}


static void extract_syntax_error_info(PyObject *pvalue, RunData *data, uint32_t idx) {
    // Handle syntax errors.
    // First, extract some attributes from the object.
    PyObject *msg_attr = PyObject_GetAttrString(pvalue, "msg");
    PyObject *lineno_attr = PyObject_GetAttrString(pvalue, "lineno");
    PyObject *end_lineno_attr = PyObject_GetAttrString(pvalue, "end_lineno");
    PyObject *offset_attr = PyObject_GetAttrString(pvalue, "offset");
    PyObject *end_offset_attr = PyObject_GetAttrString(pvalue, "end_offset");
    PyObject *text_attr = PyObject_GetAttrString(pvalue, "text");

    // Then coerce them into the right types if they are defined.
    const char *msg = (msg_attr && msg_attr != Py_None) ? PyUnicode_AsUTF8(msg_attr) : NULL;
    long lineno = (lineno_attr && lineno_attr != Py_None) ? PyLong_AsLong(lineno_attr) : -1;
    long end_lineno = (end_lineno_attr && end_lineno_attr != Py_None) ? PyLong_AsLong(end_lineno_attr) : -1;
    long offset = (offset_attr && offset_attr != Py_None) ? PyLong_AsLong(offset_attr) : -1;
    long end_offset = (end_offset_attr && end_offset_attr != Py_None) ? PyLong_AsLong(end_offset_attr) : -1;
    const char *text = (text_attr && text_attr != Py_None) ? PyUnicode_AsUTF8(text_attr) : NULL;

    if (msg != NULL) {
        set_error_msg(data, msg, idx);
    }
    if (text != NULL) {
        data->error->syntax_error_data->error_msg = _strdup(text);
        data->error->syntax_error_data->msg_length = strlen(text);
    }
    data->error->syntax_error_data->lineno = (int32_t)lineno;
    data->error->syntax_error_data->end_lineno = (int32_t)end_lineno;
    data->error->syntax_error_data->offset = (int32_t)offset;
    data->error->syntax_error_data->end_offset = (int32_t)end_offset;

    Py_XDECREF(msg_attr);
    Py_XDECREF(lineno_attr);
    Py_XDECREF(offset_attr);
    Py_XDECREF(text_attr);
}


uint8_t handle_exception(PyObject *exec_result, RunData *data, uint32_t idx) {
    // Handle the exception raised by executing python code.
    if (exec_result != NULL) {
        return 0;
    }

    PyObject *ptype, *pvalue, *ptraceback;
    PyErr_Fetch(&ptype, &pvalue, &ptraceback);

    if (ptype != NULL) {
        PyErr_NormalizeException(&ptype, &pvalue, &ptraceback);

        if (ptraceback != NULL) {
            PyException_SetTraceback(pvalue, ptraceback);
        }

        // If the exception was a syntax error, we need to handle it differently:
        if (PyErr_GivenExceptionMatches(ptype, PyExc_SyntaxError)) {
            extract_syntax_error_info(pvalue, data, idx);
        } else {
            // Extract traceback info.
            // Use the python `traceback` module to actually get the exception stack trace that ocurred.
            PyObject *mod  = PyImport_ImportModule("traceback");
            if (mod != NULL) {
                PyObject *list = PyObject_CallMethod(mod, "format_exception", "OOO", ptype, pvalue, ptraceback);
                if (list != NULL) {
                    // If we have one, format it and then assign all the info to the error struct.
                    PyObject *sep = PyUnicode_FromString("\n");
                    if (sep != NULL) {
                        PyObject* err_obj = PyUnicode_Join(sep, list);
                        if (err_obj != NULL) {
                            const char* err_msg = PyUnicode_AsUTF8(err_obj);
                            if (err_msg != NULL) {
                                set_error_msg(data, err_msg, idx);
                            }
                            Py_XDECREF(err_obj);
                        }
                        Py_XDECREF(sep);
                    }
                    Py_XDECREF(list);
                }
                Py_XDECREF(mod);
            } else {
                PyErr_Clear();
            }
        }
    }
    PyErr_Restore(ptype, pvalue, ptraceback);
    return 1;
}

__declspec(dllexport) int run_data(RunData *data) {
    // Run multiple strings sequentially within python.
    // *This* is the function you would want to call as it handles any exceptions that occur.
    uint32_t count = data->count;
    PyConfig config;
    PyStatus status;
    PyGILState_STATE gstate;
    FILE *fp;
    errno_t err;
    int retval = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);

    status = PyConfig_SetBytesString(&config, &config.program_name, "run_data");
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        set_error_msg(data, status.err_msg ? status.err_msg : "Failed to configure the interpreter", 0);
        return 1;
    }

    // CPython cannot reliably detect its prefix from inside the target process.
    set_config_home(&config);
    config.install_signal_handlers = 0;

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        set_error_msg(data, status.err_msg ? status.err_msg : "Py_InitializeFromConfig failed", 0);
        return 1;
    }

    gstate = PyGILState_Ensure();

    // Set up some state dictionaries for when the code runs.
    PyObject *main_module = PyImport_AddModule("__main__");
    PyObject *global_dict = PyModule_GetDict(main_module);
    PyObject *local_dict = NULL;

    // Run each string.
    for (uint32_t idx = 0; idx < count; idx++) {
        StringData sd = data->strings[idx];
        const char *py_data = sd.string_value;

        // New local dict for each file/string being run.
        local_dict = PyModule_GetDict(main_module);

        // Flag to check whether we want to exit early (ie. end the loop and stop processing strings/files).
        uint8_t exit_early = 0;

        if (sd.is_file) {
            err = fopen_s(&fp, py_data, "rb");
            if (err == 0) {
                // Set the "__file__" attribute to the locals so that it knows itself.
                PyObject *filename_obj = PyUnicode_DecodeFSDefault(py_data);
                if (filename_obj != NULL) {
                    PyDict_SetItemString(local_dict, "__file__", filename_obj);
                    PyObject* res = PyRun_FileEx(fp, py_data, Py_file_input, global_dict, local_dict, 1);
                    exit_early = handle_exception(res, data, idx);
                    Py_XDECREF(res);
                }
                Py_XDECREF(filename_obj);
                fclose(fp);
                if (exit_early) {
                    retval = 1;
                    break;
                }
            } else {
                // Can't find the file.
                // We'll set the error message and finish.
                set_error_msg(data, "File doesn't exist or cannot be found", idx);
                retval = 1;
                break;
            }
        } else {
            PyObject *res = PyRun_String(py_data, Py_file_input, global_dict, local_dict);
            exit_early = handle_exception(res, data, idx);
            Py_XDECREF(res);
            if (exit_early) {
                retval = 1;
                break;
            }
        }
    }
    Py_XDECREF(local_dict);
    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }
    return retval;
}


__declspec(dllexport) int free_resource(void *obj) {
    // Free some resource which was allocated by this c code.
    free(obj);
    return 0;
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
    return 1;
}