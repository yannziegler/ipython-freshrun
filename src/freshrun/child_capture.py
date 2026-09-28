"""Run the requested script and capture main()/exception locals."""

import os
import sys
import time

# _MODULE_INTERNALS = {
#     "__name__",
#     "__doc__",
#     "__package__",
#     "__loader__",
#     "__spec__",
#     "__builtins__",
# }

_script_to_watch = os.path.abspath(SCRIPT_PATH)
_script_directory = os.path.dirname(_script_to_watch)
_home_directory = os.path.expanduser("~")

if os.path.abspath(_script_directory) == os.path.abspath(_home_directory):
    _application_root = None
else:
    _application_root = _script_directory

_main_locals = {}
_script_globals = {}
_exception_locals = {}

_debug_mode = RUN_DEBUG_MODE

# Identity of the exception currently being tracked.
# The same exception produces exception events as it propagates through
# multiple frames. We only want to capture the traceback once.
_exception_identity = None


def _is_application_frame(frame):
    filename = frame.f_code.co_filename

    if filename.startswith("<") and filename.endswith(">"):
        return False

    filename = os.path.abspath(filename)

    if filename == _script_to_watch:
        return True

    if _application_root is None:
        return False

    try:
        return os.path.commonpath(
            [_application_root, filename]
        ) == _application_root
    except ValueError:
        return False


def _frame_name(frame):
    if frame.f_code.co_name == "<module>":
        return os.path.splitext(
            os.path.basename(_script_to_watch)
        )[0]

    filename = os.path.abspath(
        frame.f_globals.get(
            "__file__",
            frame.f_code.co_filename,
        )
    )

    if filename == _script_to_watch:
        module_name = os.path.splitext(
            os.path.basename(filename)
        )[0]
    else:
        relative = os.path.relpath(
            filename,
            _application_root,
        )

        module_path = os.path.splitext(relative)[0]

        if module_path.endswith("__init__"):
            module_path = os.path.dirname(module_path)

        module_name = module_path.replace(
            os.sep,
            ".",
        )

    function_name = getattr(
        frame.f_code,
        "co_qualname",
        frame.f_code.co_name,
    )

    return f"{module_name}.{function_name}"


def _is_main_frame(frame):
    code = frame.f_code

    # Explicit main() function.
    if code.co_name == "main":
        return _is_application_frame(frame)

    # Script executed entirely at module level.
    if code.co_name == "<module>":
        return (
            os.path.abspath(code.co_filename)
            == _script_to_watch
        )

    return False


def _copy_frame_locals(frame):
    if frame.f_code.co_name == "<module>":
        return {
            name: value
            for name, value in frame.f_locals.items()
            if not (
                name.startswith("__")
                and name.endswith("__")
            )
        }

    return dict(frame.f_locals)

_main_code = None

def _capture_main(frame, event, arg):
    global _exception_identity, _main_code

    # Only trace frames belonging to the script being executed.
    # if os.path.abspath(code.co_filename) != _script_to_watch:
    #     return None
    #if not _is_application_frame(frame):
    #    # return _capture_main
    #    return None

    # code = frame.f_code

    if event == "call":
        # A function called directly by the script's module-level code
        # is the script's entry point, regardless of its name.
        caller = frame.f_back

        if (
            _main_code is None
            and caller is not None
            and caller.f_code.co_name == "<module>"
            and os.path.abspath(caller.f_code.co_filename)
            == _script_to_watch
            and os.path.abspath(frame.f_code.co_filename)
            == _script_to_watch
        ):
            _main_code = frame.f_code

        return _capture_main

    # -----------------------------------------------------------------------
    # Exception event
    # -----------------------------------------------------------------------
    # if event == "exception":
        # tb = arg[2]

        # while tb is not None:
        #     current_frame = tb.tb_frame

        #     if _is_application_frame(current_frame):
        #         # _exception_locals[
        #         #     _frame_name(current_frame)
        #         # ] = dict(current_frame.f_locals)
        #         _exception_locals[
        #             _frame_name(current_frame)
        #         ] = _copy_frame_locals(current_frame)

        #     tb = tb.tb_next

        # return _capture_main

    if event == "exception":
        # print(
        #     "TRACE EXCEPTION:",
        #     type(event).__name__,
        #     repr(arg),
        #     "frame:",
        #     frame.f_code.co_filename,
        #     frame.f_code.co_name,
        # )

        if not _is_application_frame(frame):
            return _capture_main

        exception = arg[1]

        # if exception is _exception_identity:
        if (
            exception is _exception_identity
            and not isinstance(exception, KeyboardInterrupt)
        ):
            return _capture_main

        _exception_identity = exception
        _exception_locals.clear()

        # -------------------------------------------------------------------
        # IMPORTANT:
        #
        # Walk the actual Python frame chain:
        #
        #     frame
        #       ↓ f_back
        #     caller
        #       ↓ f_back
        #     caller
        #       ↓ f_back
        #     main
        #
        # This is different from walking traceback.tb_next.
        # -------------------------------------------------------------------

        current_frame = frame

        while current_frame is not None:
            current_code = current_frame.f_code

            # filename = os.path.abspath(
            #     current_code.co_filename
            # )

            # Only collect frames belonging to the script being run.
            if _is_application_frame(current_frame):
                locals_copy = _copy_frame_locals(current_frame)
                # if current_code.co_name != "<module>":
                # _exception_locals[
                #     _frame_name(current_frame)
                # ] = dict(
                #     current_frame.f_locals
                # )
                _exception_locals[
                    _frame_name(current_frame)
                ] = locals_copy

                if (
                    _main_code is not None
                    and current_frame.f_code is _main_code
                ):
                #if current_code.co_name == "main":
                    _main_locals.clear()
                    _main_locals.update(locals_copy)

                    _main_locals.update({
                        key: value
                        for key, value in frame.f_globals.items()
                        if key not in _main_locals
                    })
                    break

            current_frame = current_frame.f_back

        return _capture_main

    # -----------------------------------------------------------------------
    # Return from main()
    # -----------------------------------------------------------------------
    
    if event == "return":
        #if _main_code is not None and frame.f_code is _main_code:
       # The module frame contains the actual globals created by the
       # script. _copy_frame_locals() removes Python/IPython dunder
       # machinery, so don't use frame.f_globals here.
       if (
           frame.f_code.co_name == "<module>"
           and os.path.abspath(frame.f_code.co_filename)
           == _script_to_watch
       ):
           _script_globals.clear()
           _script_globals.update(
               _copy_frame_locals(frame)
           )
       elif _main_code is not None and frame.f_code is _main_code:
            _main_locals.clear()
            _main_locals.update(_copy_frame_locals(frame))

       return _capture_main

    # if event == "return" and _is_main_frame(frame):
    #     _main_locals.clear()
    #     _main_locals.update(
    #         _copy_frame_locals(frame)
    #     )

    #     return _capture_main

    # -----------------------------------------------------------------------
    # Continue tracing this frame.
    # -----------------------------------------------------------------------

    return _capture_main


def _capture_exception_locals_from_exception(exception):
    _exception_locals.clear()
    _main_locals.clear()

    traceback = exception.__traceback__

    if traceback is None:
        return

    # Find the innermost application frame.
    innermost_frame = None
    tb = traceback

    while tb is not None:
        frame = tb.tb_frame

        if _is_application_frame(frame):
            innermost_frame = frame

        tb = tb.tb_next

    if innermost_frame is None:
        return

    # Walk the actual Python caller chain.
    current_frame = innermost_frame

    while current_frame is not None:
        code = current_frame.f_code

        if _is_application_frame(current_frame):
            function_name = _frame_name(current_frame)
            locals_copy = _copy_frame_locals(current_frame)

            _exception_locals[function_name] = locals_copy

            if code.co_name == "main":
                _main_locals.update(locals_copy)
                break

        current_frame = current_frame.f_back


class _ExceptionCaptureTB:

    def __init__(self, real_tb):
        self._real_tb = real_tb
        self.exception = None
        self.traceback = None

    def __getattr__(self, name):
        return getattr(self._real_tb, name)

    def __call__(
        self,
        etype,
        value,
        tb,
        tb_offset=0,
        **kwargs,
    ):

        # Capture the exception and traceback that IPython's debugger
        # reports after the debugged program terminates.
        self.exception = value
        self.traceback = tb

        # Immediately delegate to IPython's normal traceback formatter.
        # Nothing about ipdb is changed.
        return self._real_tb(
            etype,
            value,
            tb,
            tb_offset=tb_offset,
            **kwargs,
        )


shell = get_ipython()

if not _debug_mode:
    # -----------------------------------------------------------------------
    # Normal mode
    #
    # We use sys.settrace(), NOT sys.setprofile().
    #
    # sys.settrace() produces Python-level "exception" events and therefore gives
    # us access to the traceback associated with the exception.
    #
    # We also capture the final locals of main() on its return.
    # -----------------------------------------------------------------------

    # Install our trace function, restoring the previous one afterwards.
    _old_trace = sys.gettrace()
    sys.settrace(_capture_main)

    try:
        # _t0 = time.perf_counter()
        shell.run_line_magic("run", RUN_ARGUMENTS)
        # print()
        # print(
        #     f"[%freshrun: running time is {time.perf_counter() - _t0:.3f}s]"
        # )
    finally:
        sys.settrace(_old_trace)
else:
    # -----------------------------------------------------------------------
    # Let ipdb have exclusive control of tracing. IPython's %run -d
    # catches the final exception and passes it to InteractiveTB. Proxy
    # InteractiveTB only long enough to retain that exception/traceback.
    # -----------------------------------------------------------------------

    real_tb = shell.InteractiveTB
    capture_tb = _ExceptionCaptureTB(real_tb)
    shell.InteractiveTB = capture_tb

    try:
        shell.run_line_magic("run", RUN_ARGUMENTS)
    finally:
        shell.InteractiveTB = real_tb

    if capture_tb.traceback is not None:
        _capture_exception_locals_from_exception(capture_tb.exception)


# ---------------------------------------------------------------------------
# Export main() locals.
#
# In normal mode, _main_locals was captured by _capture_main.
# In debug mode, _main_locals was recovered from the exception traceback.
#
# %run has already exposed top-level variables in the IPython namespace.
# ---------------------------------------------------------------------------

#if _main_locals:
#    shell.user_ns.update(_main_locals)

#shell.user_ns["_script_locals"] = dict(_main_locals)

script_locals = dict(_script_globals)
script_locals.update(_main_locals)

if script_locals:
    shell.user_ns.update(script_locals)

shell.user_ns["_script_locals"] = script_locals

# ---------------------------------------------------------------------------
# Export the complete exception call chain.
# ---------------------------------------------------------------------------

if _exception_locals:
    shell.user_ns["_exception_locals"] = dict(_exception_locals)

    print()
    print("[%freshrun: exception locals() captured in _exception_locals]")
    print("You can use %pull <function/method name in _exception_locals> " \
          "to populate the namespace with the locals from any of the " \
          "function/method which were visited when the exception occured:")
    print("  " + " → ".join(_exception_locals.keys()))
else:
    print()
    print("[%freshrun: locals() captured in _script_locals and added to current namespace]")
