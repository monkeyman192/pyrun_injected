#define PY_SSIZE_T_CLEAN
#include <stdio.h>
#include <Python.h>
#include <traceback.h>

typedef struct {
    char* error_msg;         // The actual error message we get from the traceback.
    size_t msg_length;     // The length of the error message in bytes.
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


__declspec(dllexport) int run_file(const char* filename) {
    // Run a single file within python.
    FILE* fp;
    errno_t err;
    PyConfig config;
    PyGILState_STATE gstate;
    int ret = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_file");
    Py_InitializeFromConfig(&config);

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


__declspec(dllexport) int run_string(const char* string) {
    // Run a single string within python.
    PyConfig config;
    PyGILState_STATE gstate;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_string");
    Py_InitializeFromConfig(&config);

    gstate = PyGILState_Ensure();
    // Run the string with python.
    int res = PyRun_SimpleString(string);

    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }

    return res;
}

uint8_t handle_exception(PyObject* exec_result, RunData* data, uint32_t idx) {
    const char* err_msg;
    // Handle the exception raised by executing python code.
    if (exec_result != NULL) {
        return 0;
    }
    PyObject *ptype, *pvalue, *ptraceback;
    PyErr_Fetch(&ptype, &pvalue, &ptraceback);
    if (ptype) {
        PyErr_NormalizeException(&ptype, &pvalue, &ptraceback);
        if (ptraceback != NULL) {
            PyException_SetTraceback(pvalue, ptraceback);
        }

        // Extract traceback info
        PyTracebackObject* ptracebackObj = (PyTracebackObject*)ptraceback;
        if (ptracebackObj) {
            PyObject *mod, *list, *string;
            PyObject *err_obj;
            // Use the python `traceback` module to actually get the exception stack trace that ocurred.
            mod  = PyImport_ImportModule("traceback");
            list = PyObject_CallMethod(mod, "format_exception", "OOO", ptype, pvalue, ptraceback);
            if (list) {
                // If we have one, format it and then assign all the info to the error struct.
                string = PyUnicode_FromString("\n");
                err_obj = PyUnicode_Join(string, list);
                err_msg = PyUnicode_AsUTF8(err_obj);
                data->error->error_msg = (char*)err_msg;
                data->error->msg_length = strlen(err_msg);
                data->error->bad_string_idx = idx;
            }
            Py_XDECREF(list);
            Py_XDECREF(mod);
            Py_XDECREF(string);
        }
        Py_XDECREF(ptracebackObj);
    }
    PyErr_Restore(ptype, pvalue, ptraceback);
    Py_XDECREF(ptype);
    Py_XDECREF(pvalue);
    Py_XDECREF(ptraceback);
    return 1;
}

__declspec(dllexport) int run_data(RunData* data) {
    // Run multiple strings sequentially within python.
    uint32_t count = data->count;
    PyConfig config;
    PyGILState_STATE gstate;
    FILE* fp;
    errno_t err;
    int retval = 0;

    // Configure python.
    PyConfig_InitPythonConfig(&config);
    PyConfig_SetBytesString(&config, &config.program_name, "run_data");
    Py_InitializeFromConfig(&config);

    gstate = PyGILState_Ensure();

    // Set up some state dictionaries for when the code runs.
    PyObject *main_module = PyImport_AddModule("__main__");
    PyObject *global_dict = PyModule_GetDict(main_module);
    PyObject *local_dict;

    // Run each string.
    for (uint32_t i = 0; i < count; i++) {
        StringData sd = data->strings[i];
        const char* py_data = sd.string_value;

        // New local dict for each file/string being run.
        local_dict = PyModule_GetDict(main_module);

        if (sd.is_file) {
            err = fopen_s(&fp, py_data, "rb");
            if (err == 0) {
                // Set the "__file__" attribute to the locals so that it knows itself.
                PyObject *filename_obj = PyUnicode_DecodeFSDefault(py_data);
                PyDict_SetItemString(local_dict, "__file__", filename_obj);
                PyObject* res = PyRun_File(fp, py_data, Py_file_input, global_dict, local_dict);
                uint8_t exit_early = handle_exception(res, data, i);
                Py_XDECREF(filename_obj);
                Py_XDECREF(res);
                fclose(fp);
                if (exit_early) {
                    retval = 1;
                    break;
                }
            } else {
                // Can't find the file.
                // We'll set the error message and finish.
                data->error->error_msg = (char*)"File doesn't exist or cannot be found";
                data->error->msg_length = strlen(data->error->error_msg);
                data->error->bad_string_idx = i;
                retval = 1;
                break;
            }
        } else {
            PyObject* res = PyRun_String(py_data, Py_file_input, global_dict, local_dict);
            uint8_t exit_early = handle_exception(res, data, i);
            Py_XDECREF(res);
            if (exit_early) {
                retval = 1;
                break;
            }
        }
    }

    Py_XDECREF(main_module);
    Py_XDECREF(global_dict);
    Py_XDECREF(local_dict);

    PyGILState_Release(gstate);

    if (Py_FinalizeEx() < 0) {
        exit(120);
    }

    return retval;
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