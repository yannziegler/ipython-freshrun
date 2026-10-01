# ipython-freshrun

Run Python scripts and/or use REPL in a genuinely fresh, interactive IPython session.

`ipython-freshrun` provides the `%freshrun` IPython magic. It starts a new blank-slate IPython child session or launches a script in a completely new IPython child process. When running a script, it leaves that child process interactive after the script finishes, and provides convenient shortcuts for repeating or replacing the current session, as well as user-friendly mechanisms to inspect the variables created during the execution, whether successful (return) or not (an exception was raised).

The main motivation is to make it easy and reliable to repeatedly run a script from an absolutely clean Python process, while still being able to inspect its resulting state interactively using all the bells and whistles of IPython.

If running a full script repeatedly is not what you need, `ipython-freshrun` also provides `%freshimport`, which only reloads the modules from your current project. It ensures that all modules, classes, functions or any other module-level objects are fully reloaded in the current session.

`freshrun` is currently maintained by Yann Ziegler. The proof-of-concept and initial version were designed by Yann Ziegler and written by ChatGPT (due to a lack of knowledge on IPython low-level mechanisms and strong time constraints, if you ask). This project was inspired by Jeanne's creative way of using IPython.

## Features

### %freshrun

- Run a Python script in a completely fresh IPython process every time with `%freshrun my_script.py`.
- ...or simply start a fresh interactive child without running a script with `%freshrun`.
- Invoke a `%freshrun` command directly from inside a child without having to go back to the parent IPython session (automatic child replacement).
- Keep the child IPython session interactive after the script finishes.
- Repeat the most recent `%freshrun` command with **Alt+Enter**.
- Recall the most recent `%freshrun` command with **Page Up** or **Alt+Up**.
- Preserve normal IPython `%run` argument handling.
- Support IPython's `-d` / `--pdb` debugging mode.
- When running a script (with or without `-d`), capture both its globals and the final locals from `main()` (or another entry-point function) and make them available in the current namespace.
- Capture locals from the Python call chain when an exception occurs (including `KeyboardInterrupt`) and store them in a dedicated `_exception_locals` dictionary for in-depth inspection.
- After an exception has occurred, pull locals from specific functions or methods directly into the current namespace for easy inspection with `%pull`.
- Similarly, inject all entries from any dictionary into the current namespace with `%inject`.
- All of this, while keeping the parent IPython session intact and only replacing the child sessions.

### %freshimport

- Reload all the modules previously loaded in the current IPython namespace (excluding system-level and environment modules) with `%freshimport`.
- Either set your local project folder when starting a child session with `%freshrun --project ~/my_project` or let `freshrun` discover it from your script location with `%freshrun my_script.py`...
- ...then discover and import/reload all your project modules with `%freshimport --all`.
- Increase the verbosity of `%freshimport` with `-v` or `-vv` to see how many and which Python objects were actually reloaded.

_**Note:**_`ipython-freshrun` is an **IPython extension**. It is intended for terminal IPython use and does not provide Jupyter-specific functionality.


## Incentive: Why use a fresh process?

A normal `%run` leaves the Python process itself untouched.

That means state created by previous executions can remain in the process:

- imported modules remain in `sys.modules`;
- global state can survive;
- singleton objects can remain alive;
- library state can persist;
- background threads or other resources may remain;
- module-level initialization may not happen again in the same way.

 `%freshrun` starts a new Python interpreter instead.

Conceptually:

```
Parent IPython
      │
      │  %freshrun example.py
      ▼
Fresh Python process
      │
      ├── Fresh IPython
      ├── Run example.py
      └── Remain interactive
```

When you exit that child, control returns to the original parent IPython session.

### Interactive child sessions

The child session uses a custom prompt showing the script that was launched:

```
[example.py] In [1]:
```

After the script finishes, the child is a normal interactive IPython session.

You can inspect variables, call functions, import modules, and continue working normally.

For example, given:

```
# example.py

def main():
    x = 10
    y = 20
    result = x + y

if __name__ == "__main__":
    main()
```

running:

```
%freshrun example.py
```

leaves the child with the values from `main()` available:

```
In [1]: x
Out[1]: 10

In [2]: y
Out[2]: 20

In [3]: result
Out[3]: 30
```

This makes `%freshrun` particularly useful for developing conventional scripts while retaining an interactive environment for inspecting their state.

When `%freshrun` is used without a script, the child displays:

```
[fresh] In [1]:
```

No script is executed in this case, but the child otherwise behaves like a normal fresh IPython session.

`%freshimport` has a behaviour similar to `%freshrun`, but is limited to modules reloading. It triggers a full reload of current user modules (or of all project-level modules with `--all`), while keeping the current session alive and preserving the current namespace (apart from reloaded modules of course). Even if their internal mechanisms are quite different, you may think about `%freshimport` as a fine-grained version of `%freshrun` for modules only.

---

# Setup

## Installation

### PyPI

Install from PyPI with:

```bash
python -m pip install ipython-freshrun
```

Or install the development version from a local checkout:

```
python -m pip install -e .
```

The package requires a recent Python and IPython installation.

### Conda

**Note: `ipython-freshrun` is *not* yet available on conda-forge.**

In a near future, you should be able to install it using:

```bash
conda install -c conda-forge ipython-freshrun
```

## Loading the extension

Start IPython and load the extension with:

```
%load_ext freshrun
```

After loading it, the `%freshrun` magic becomes available:

```
%freshrun my_script.py
```

You can verify that the extension is loaded with:

```
%lsmagic
```

and look for `freshrun` in the list of line magics.

### Loading automatically

If you use `freshrun` regularly, you can configure IPython to load it every time IPython starts.

First, create the default IPython profile if you do not already have one:

```
ipython profile create
```

This normally creates:

```
~/.ipython/profile_default/
```

Edit:

```
~/.ipython/profile_default/ipython_config.py
```

and add:

```
c.InteractiveShellApp.extensions.append("freshrun")
```

If the file already contains an `extensions` setting, append to the existing list rather than replacing it. For example:

```
c.InteractiveShellApp.extensions = [
    "some_other_extension",
    "freshrun",
]
```

After restarting IPython, `%freshrun` should be available automatically.

You can find the profile being used by IPython with:

```
ipython locate profile default
```

If you use a different profile, put the setting in that profile's `ipython_config.py` instead.

---

# Documentation

## `%freshrun`

The basic syntax is:

```
%freshrun
%freshrun --project ~/my_project
%freshrun [--project ~/my_project] my_script.py [args...]
%freshrun --help
```
To display the command documentation, you may also use, following IPython convention:

```
%freshrun?
```

With no arguments, `%freshrun` starts a completely fresh, interactive IPython child without running any script:

```
%freshrun
```

The child is a normal interactive IPython session. It uses a generic prompt:

```
[fresh] In [1]:
```

You can use this mode when you simply want a clean Python/IPython process without initially running a script.

Alternatively, you may provide a project path, which will be used by `%freshimport` (see next subsection):

```
%freshrun --project ~/my_project
```

When a script is specified, it is executed in a newly created IPython process.

For example:

```
%freshrun example.py
```

or:

```
%freshrun example.py foo bar "another argument"
```

The script is executed in a newly created IPython process.

When the script terminates normally, the child IPython session remains open and interactive.

This is different from simply executing:

```
%run example.py
```

because `%run` executes inside the current IPython process, whereas `%freshrun` deliberately creates a new Python/IPython process. `%freshrun` accepts the relevant `%run`-style arguments, however, such as `%freshrun -d example.py` (see below for debugging with `freshrun`). Please note that `%freshrun -m` is an exception here, it is not supported intentionally due to `freshrun`'s internal mechanisms.


## `%freshimport`

`%freshimport` has a behaviour similar to `%freshrun`, but is limited to modules reloading. Even if their internal mechanisms are quite different, you may think about `%freshimport` as a fine-grained version of `%freshrun` for modules only.

```
%freshimport
```

triggers a full reload of user modules which are already loaded in the current namespace, while keeping the current session alive and preserving other objects in the namespace.

When used jointly with `%freshrun my_script.py`, `%freshimport` distinguishes between actual user modules and system-level (or other non-user modules) using the script path and assuming that it points to a project folder where the modules reside (unless the script is in the user home directory, to avoid spurious reloading of modules from environments or other projects stored by the user in its home directory).

As mentioned above, you can explicitly define your project folder when starting a child IPython session using `%freshrun --project ~/my_project my_script.py`.

Once the project folder is known, you can force the discovery and import of all project-level modules using:
```
%freshimport --all
```

_**Beware:**_ reloading modules in Python is not a trivial task and `%freshimport` is still an experimental command. Please report any unexpected behaviour.


## `main()` locals

When a conventional script contains:

```
import my_module

A = 'global'

def main():
    x = 42
    s = "hello"

if __name__ == "__main__":
    main()
```

`%freshrun` captures the script global variables, as well as the final local variables from the entry-point function (usually `main()`, but not necessarily).

Those variables are copied into the child IPython namespace after return.

The complete captured dictionary is also available as:

```
_script_locals
```

For example:

```
In [1]: _script_locals
Out[1]: {
    'my_module': <module 'my_module' from 'my_module.py'>,
    'A': 'global',
    'main': <function __main__.main(argv)>,
    'x': 42,
    's': 'hello'
    }
```

The capture is specifically concerned with the script being executed. It does not attempt to serialize arbitrary Python objects between processes; the objects remain in the child process where they were created.


## Exception locals

When the executed script raises an exception, `%freshrun` captures locals from the relevant exception call chain.

The resulting dictionary is available as:

```
_exception_locals
```

For example, a script might contain:

```
from my_module import deep

## Defined in my_module:
# def deep():
#     z = 3
#     raise RuntimeError("something went wrong")

def inner():
    y = 2
    deep()

def main():
    x = 1
    inner()

if __name__ == "__main__":
    main()
```

After the exception, `_exception_locals` can contain entries corresponding to the functions in the call chain:

```
{
    'my_script.my_module.deep': {
        'z': 3,
    },
    'my_script.inner': {
        'y': 2,
    },
    'my_script.main': {
        'argv': ['my_script.py'],
        'x': 1,
    },
    'my_script': {
        'deep': <function my_module.deep()
        'inner': <function __main__.inner()>,
        'main': <function __main__.main(argv)>,
    },

}
```

The exact contents naturally depend on the state of the frames at the time of the exception.

A short notification is printed when exception locals have been captured:

```
[%freshrun: exception locals() captured in _exception_locals]
  my_script.my_module.deep → my_script.inner → my_script.main → my_script
```

You can check this again later simply by displaying `_exception_locals.keys()`.

_**Tips:**_ if you would like to inspect your script variables up to a certain location in your code without having to use a full-fledged debugger (see below), you may simply raise an exception at the location of your choice and take advantage of `%freshrun` exception handling. You can even interrupt your script with a `KeyboardInterrupt` (Ctrl+C) at any time and populate your current namespace with all the preserved locals for further manual inspection or processing (see next subsection).


## `%inject` and `%pull`

The `%inject` magic copies all entries from a dictionary into the current IPython namespace:

```
%inject my_dict
```
or
```
%inject {'a': 1, 'b': 2}
```

For example, if `my_dict` contains `{"x": 10, "y": 20}`, both `x` and `y` become directly available in the session.

The `%pull` magic populates the current namespace using an entry from the `_exception_locals` dictionary (see above for exceptions handling). For a given function or method name as listed in `_exception_locals.keys()`, an entry corresponds to all the locals of that function or method when the exception occurred. For example, if `_exception_locals` has a key `my_script.my_module.my_func`,

```
%pull my_script.my_module.my_func
```

makes all the locals from `my_script.my_module.my_func` (before the exception was raised) directly available in the current IPython child session.

Note the strict equivalence between:
```
%pull my_script.my_module.my_func
```
and
```
%inject _exception_locals['my_script.my_module.my_func']
```

Thus, `%pull` may be seen as a handy alias for `%inject` when the intent is to populate the namespace with locals from a given function or method once an exception has been raised.

Both magics are available in the parent IPython session and fresh child sessions, but only `%inject` may be useful in the parent (of course, because `_exception_locals` is only set after an exception occurs in a child).


## Debugging with `-d`

`%freshrun` supports IPython's debug form:

```
%freshrun -d example.py
```

The arguments are passed through to IPython's `%run` machinery.

This allows the normal IPython debugger (`ipdb`) workflow to be used inside the fresh child.

For example:

```
%freshrun -d example.py
```

The fresh child is still a separate IPython process; the debugger operates inside that child.

The debug path intentionally leaves tracing under IPython/IPDB's control rather than installing the normal `sys.settrace()` capture mechanism at the same time.

---

# Keyboard shortcuts

`freshrun` provides several terminal IPython shortcuts.

## Alt+Enter

In the **parent IPython session**, Alt+Enter immediately executes the most recent `%freshrun` command again.

For example:

```
%freshrun example.py
```

After the child exits, pressing **Alt+Enter** starts another fresh child using the same command.

In a **fresh child**, Alt+Enter immediately repeats the current fresh run, replacing the current child with another fresh child.

This is useful when repeatedly testing a script from a clean process.

If the child was started with a bare `%freshrun`, Alt+Enter starts another fresh child without running a script.


## Page Up / Alt+Up

In the parent session:

- **Page Up** recalls the most recent `%freshrun` command from history.
- **Alt+Up** also searches for the most recent `%freshrun` command.

The command is placed into the input buffer but is **not executed**.

Inside a fresh child, Page Up and Alt+Up place the current `%freshrun` command into the input buffer.

This provides a convenient way to edit the command before executing it.


## Exiting the child

The child is an ordinary interactive IPython process.

You can leave it with:
```
exit
```
or:
```
quit
```

You can also use the normal terminal EOF shortcut:
```
Ctrl+D
```

Depending on the terminal/IPython EOF behavior, Ctrl+D may need to be pressed twice.

After the child terminates, `%freshrun` returns to the original parent IPython session.

The parent session is not replaced.

---

# Restarting from inside a child

A child can launch another fresh child directly, either with or without a script:

```
%freshrun
```
or
```
%freshrun other.py
```

The first form replaces the current child with another completely fresh child without running a script. The second replaces it with a fresh child running `other.py`.

The current child does not spawn a nested permanent hierarchy.

Instead, it writes a restart request and terminates with a dedicated exit status. The parent `%freshrun` process detects the request and starts another fresh IPython child.

Conceptually:

```
Parent IPython
    │
    └── Child A
          │
          │ %freshrun other.py
          ▼
        Child A exits
          │
          ▼
        Child B
```

This keeps the process tree manageable while still allowing the currently running fresh session to request a completely new one.

---

# Freshness model

The important distinction is between the **parent** and **child** processes.

Suppose you start:

```
IPython A
```

and execute:

```
%freshrun example.py
```

The extension starts:

```
IPython B
```

The script executes in B.

Anything created by the script belongs to B, not A.

When B exits, A is still the original process it was before `%freshrun` was invoked.

This is the core reason for using a separate process rather than attempting to emulate a fresh interpreter by clearing variables or unloading modules.

---

# How it works

The extension consists of three logical components.

## Parent extension

The parent extension registers the `%freshrun` magic with IPython.

It:

1. Parses the `%freshrun` command.
2. Determines the script being executed.
3. Creates a temporary working area.
4. Creates a restart-request file.
5. Starts a new IPython subprocess.
6. Passes the required state through environment variables.
7. Waits for the child.
8. Detects the special restart exit status.
9. Reads any restart request.
10. Starts the next fresh child when requested.

The parent process remains untouched throughout.

## Child startup

The child startup code configures the new IPython instance.

It:

- installs the custom prompt;
- installs the child keyboard shortcuts;
- registers the child version of `%freshrun`.

The child `%freshrun` magic communicates a new request to the parent and terminates the child with the special restart status.

## Child capture

The capture code runs the requested script through IPython's `%run` implementation.

In normal mode it temporarily installs a `sys.settrace()` function to:

- identify frames belonging to the target script;
- capture `main()` locals when `main()` returns;
- capture locals from the exception call chain.

In debug mode it allows IPython's debugger to control tracing and temporarily wraps the IPython traceback handler so that the final exception and traceback can be recovered afterward.

---

# Limitations

## `%run -m` is not supported

The extension currently requires a physical script file:

```
%freshrun script.py
```

rather than:

```
%freshrun -m package.module
```

The locals-capture mechanism relies on identifying frames belonging to a particular script file.


## Only the target script is monitored

Frame capture is restricted to frames whose filename matches the script being executed.

This prevents unrelated library frames from being included in `_exception_locals`.


## Locals are copied, not serialized

The child and parent are separate processes.

The captured `main()` locals are copied within the child IPython namespace; they are not sent back to the parent process.

Consequently, the objects remain owned by the fresh child process and are lost after you leave the child.


## Fresh imports/reloading is limited to project

When reloading modules with `%freshimport`, only user-level modules currently loaded in the namespace and not part of the system or local environment are reloaded.

Similarly, when a project path has been provided with `%freshrun --project ./path/to/my/project` or deduced from the current script path, only project-level modules are reloaded or imported with `%freshimport --all`.


## Terminal IPython

The extension is designed around terminal IPython and its prompt-toolkit interface.

It is not intended to provide a Jupyter Notebook interface.

---

# Typical workflow

## Running a script

A common development workflow looks like this:

```
%freshrun my_program.py
```

The program runs in a clean interpreter.

After it finishes:

```
x
result
```

can be inspected interactively.

If you change the source code, press:

```
Alt+Enter
```

to run it again from a new process.

If you need to switch to another script:

```
%freshrun another_program.py --some-option
```

If the program fails, inspect:

```
_exception_locals
```

to examine the locals captured from the exception call chain.

You may want to pull locals into your current namespace using

```
%pull some_key_in_exception_locals
```

If you modified one of your modules in the meantime and don't want to start a new, empty session (which would mean losing all the current namespace), you may only reload your modules using

```
%freshimport
```

and keep working interactively.

For debugging:

```
%freshrun -d my_program.py
```

When finished, exit the child and return to the original IPython session.

## Starting a blank-slate session

You can also start with a completely clean interactive child:

```
%freshrun
```

This is useful when you want a fresh interpreter but do not want to run a script immediately. You can then work interactively as with any usual IPython REPL. This approach is very similar to leaving IPython entirely and launching it again, with the main difference being that your main session always remains alive.

Another significant advantage of using `freshrun`, even without running a script, is the capability to use `%freshimport` magic, which will let you update modules that you have manually imported, without having to care about partial auto-reloading.

Once you are done, you can leave the child session and come back to your parent session or start another blank-slate session from inside the child with Alt+Enter (or using `%freshrun` again), or even directly replace the current child session with any other `%freshrun` command, as described in the previous subsection.

---

# Development

Clone the repository and install it in editable mode:

```
git clone https://github.com/yannziegler/ipython-freshrun
cd ipython-freshrun
python -m pip install -e ".[dev]"
```

Run the test suite with:

```
pytest
```

The tests should focus primarily on observable behavior, particularly process isolation, command parsing, argument forwarding, restart behavior, locals capture, and debugger behavior.

---

# Project structure

The implementation deliberately keeps the parent and child programs separate:

```
src/freshrun/
├── __init__.py
├── freshrun.py
├── freshimport.py
├── child_startup.py
└── child_capture.py
└── tools.py
```

### `freshrun.py`

Contains the parent IPython extension and `%freshrun` implementation.

### `freshimport.py`

Contains the additional `%freshimport` magic.

### `child_startup.py`

Contains the code executed when a new fresh IPython process starts.

It is kept as an ordinary `.py` file so that the child IPython behavior can be edited and maintained independently.

### `child_capture.py`

Contains the script execution and locals-capture logic.

It is also a normal `.py` file rather than an embedded Python string.

The two child files are packaged as resources and copied to the temporary execution area when a fresh child is started.

### `tools.py`

Contains the magic commands `%inject` and `%pull`.

---

# Tools used

- Coding: Emacs with Spacemacs config
- ChatGPT: initial code writing

---

# Licence

This software is licensed under the [EUPL](LICENSE).

---

# Acknowledgements

Many thanks to all the current and future beta-testers!
