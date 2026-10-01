"""IPython magic for running scripts in genuinely fresh child sessions."""

from __future__ import annotations

import os
import pty
import shlex
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path

from IPython.core.magic import Magics, line_magic, magics_class
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText


EXIT_QUIT = 0
EXIT_RESTART = 42

_CHILD_STARTUP = "child_startup.py"
_CHILD_CAPTURE = "child_capture.py"

FRESHRUN_HELP = """\
Usage:
    %freshrun
    %freshrun --project PATH
    %freshrun [%run args...] script.py [script args...]
    %freshrun --project PATH [%run args...] script.py [script args...]
    %freshrun --help

Note: %freshrun accepts all %run args, except -m which is not supported.

Start a genuinely fresh, interactive IPython child session.

With no arguments:
    Start a fresh child session without running a script.

With --project PATH:
    Start a fresh child session with PATH as its project root.
    This is useful when starting a blank child session for a project.

With a script:
    Start a fresh child session and run the script.
    The script's directory is used as the project root.

With --project PATH and a script:
    Start a fresh child session and use PATH as the project root instead
    of the script's directory.

Inside the child:
    %freshrun
        Replace the current child with another fresh child.

    %freshrun [%run args...] script.py [script args...]
        Replace the current child and run the specified script.

    Alt+Enter
        Repeat the last %freshrun command immediately.

    PageUp / Alt+Up
        Recall the last %freshrun command without executing it.

    Ctrl+D (twice), 'exit' or 'quit'
        Return to the parent IPython session.

Use %freshrun? or %freshrun --help to display this documentation.
"""

def _run_fresh_child(command, env):
    """Run an interactive child through a private pseudo-terminal."""
    if not sys.stdin.isatty():
        return subprocess.run(command, env=env)
    inherited_env = os.environ
    env_command = ["env"]
    for key in inherited_env:
        if key not in env:
            env_command.extend(["-u", key])
    for key, value in env.items():
        if inherited_env.get(key) != value:
            env_command.append(f"{key}={value}")
    env_command.extend(command)
    status = pty.spawn(env_command)
    return subprocess.CompletedProcess(
        command,
        os.waitstatus_to_exitcode(status),
    )

def _read_child_program(filename: str) -> str:
    """Read one of the Python programs used inside a fresh child."""
    return (
        resources.files("freshrun")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def _extract_project_argument(
    args: list[str],
) -> tuple[Path | None, list[str]]:
    """
    Extract freshrun's --project PATH option.

    The option is removed from the arguments subsequently passed to the
    %run-compatible script machinery.
    """
    args = list(args)
    project_root: Path | None = None
    remaining: list[str] = []
    i = 0

    while i < len(args):
        arg = args[i]

        if arg == "--project":
            if i + 1 >= len(args):
                raise ValueError("--project requires a path")

            project_root = Path(
                os.path.abspath(
                    os.path.expanduser(args[i + 1])
                )
            ).resolve()

            i += 2
            continue

        if arg.startswith("--project="):
            project_root = Path(
                os.path.abspath(
                    os.path.expanduser(arg.split("=", 1)[1])
                )
            ).resolve()
            i += 1
            continue

        remaining.append(arg)
        i += 1

    return project_root, remaining


def _find_script_argument(args: list[str]) -> str | None:
    """
    Find the script file in a %run-style argument list.

    This is used only to determine which file should be monitored for
    main(). The complete argument list is still passed unchanged to %run.

    Examples handled include:

        script.py
        -d script.py
        -i script.py
        -n script.py
        script.py arg1 arg2
        -- script.py

    %run -m module is deliberately not supported because there is no
    physical script file whose main() can be identified reliably.
    """

    if "-m" in args:
        return None

    options_with_arguments = {"-N", "-b"}

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--":
            if i + 1 < len(args):
                return args[i + 1]
            return None

        if arg in options_with_arguments:
            i += 2
            continue

        if arg.startswith("-"):
            i += 1
            continue

        return arg

    return None


def _print_freshrun_status(script_name: str | None) -> None:
    print_formatted_text(
        FormattedText([
            (
                "bold fg:#00afff",
                " ↻ Starting new child session from scratch...",
            ),
        ])
    )


def _print_freshrun_helper(script_name: str | None) -> None:
    del script_name

    print_formatted_text(
        FormattedText([
            ("", " > "),
            ("bold fg:#ffd700", "Alt+Enter"),
            ("", " to re-run last %freshrun command immediately\n"),
            ("", " > "),
            ("bold fg:#ffd700", "PageUp"),
            ("", "/"),
            ("bold fg:#ffd700", "Alt+Up"),
            ("", " to display last %freshrun command and wait\n"),
            ("", " > "),
            ("fg:#aaaaaa", "Ctrl+D"),
            ("", " (twice), '"),
            ("fg:#aaaaaa", "exit"),
            ("", "' or '"),
            ("fg:#aaaaaa", "quit"),
            ("", "' to go back to your parent session"),
        ])
    )


@magics_class
class FreshRunMagics(Magics):
    """IPython magics for fresh interactive script execution."""

    def __init__(self, shell):
        super().__init__(shell)

        # Most recent complete %freshrun command.
        self.last_freshrun: str | None = None

        self._install_parent_shortcut()

    def _install_parent_shortcut(self) -> None:
        """Install the parent Alt+Enter and history shortcuts."""

        shell = self.shell

        if not hasattr(shell, "pt_app"):
            return

        try:
            key_bindings = shell.pt_app.key_bindings
        except Exception:
            return

        # Alt+Enter = execute the last %freshrun command immediately.

        @key_bindings.add("escape", "enter")
        def _(event):
            if not self.last_freshrun:
                print(
                    "\nNo previous %freshrun command yet.\n"
                    "Run %freshrun <script> first."
                )
                return

            event.current_buffer.text = ("%freshrun " + self.last_freshrun)
            event.current_buffer.validate_and_handle()

        # Page Up / Alt+Up = find the most recent %freshrun command in
        # history without executing it.

        @key_bindings.add("escape", "up", eager=True)
        def _(event):
            buffer = event.current_buffer
            buffer.load_history_if_not_yet_loaded()
            history = buffer.history.get_strings()

            for index in range(len(history) - 1, -1, -1):
                if history[index].lstrip().startswith("%freshrun "):
                    buffer.go_to_history(index)
                    return

    @line_magic
    def freshrun(self, line: str) -> None:
        """
        Run a script in a genuinely fresh, interactive IPython child.

        The child remains alive after the script terminates.

        Inside the child:

            Alt+Enter
                Repeat the current fresh run.

            %freshrun other.py
                Throw away this child and start another fresh one.

        A conventional script such as:

            def main():
                x = 1
                y = 2

            if __name__ == "__main__":
                main()

        leaves x and y available in the interactive child after main()
        returns.

        Top-level scripts work normally as well.
        """

        args = shlex.split(line)

        if "--help" in args or "-h" in args:
            print(FRESHRUN_HELP)
            return

        try:
            explicit_project_root, run_args = _extract_project_argument(args)
        except ValueError as exc:
            print(f"%freshrun: {exc}")
            return

        script_path = _find_script_argument(args)

        if run_args and script_path is None:
            print(
                "%freshrun currently requires a script file "
                "(%run -m is not supported)."
            )
            return

        if script_path is not None:
            script_path = os.path.abspath(
                os.path.expanduser(script_path)
            )

            if not os.path.isfile(script_path):
                print(f"Script not found: {script_path}")
                return

        if explicit_project_root is not None:
            if not explicit_project_root.is_dir():
                print(
                    f"Project directory not found: "
                    f"{explicit_project_root}"
                )
                return

        if args:
            # Remember the complete command so Alt+Enter can reproduce it.
            self.last_freshrun = shlex.join(args)

        with tempfile.TemporaryDirectory(
            prefix="ipython-freshrun-"
        ) as tmp:

            request_file = os.path.join(tmp, "request.txt")
            startup_file = os.path.join(tmp, "startup.py")
            capture_file = os.path.join(tmp, "capture.py")

            # The child programs are now ordinary package files rather than
            # source embedded in this module.
            startup_code = _read_child_program(_CHILD_STARTUP)

            capture_template = _read_child_program(_CHILD_CAPTURE)

            with open(startup_file, "w", encoding="utf-8") as f:
                f.write(startup_code)

            current_args = args
            first_child = True

            while True:
                # ----------------------------------------------------------
                # Remove any stale restart request.
                # ----------------------------------------------------------

                try:
                    os.unlink(request_file)
                except FileNotFoundError:
                    pass

                try:
                    explicit_project_root, run_args = _extract_project_argument(
                        current_args
                    )
                except ValueError as exc:
                    print(f"%freshrun: {exc}")
                    break

                script_path = _find_script_argument(run_args)

                # A script establishes the project root automatically.
                # An explicit --project overrides it.
                if explicit_project_root is not None:
                    project_root = explicit_project_root
                elif script_path is not None:
                    project_root = Path(
                        os.path.abspath(
                            os.path.expanduser(script_path)
                        )
                    ).resolve().parent

                    # Never infer $HOME as a project root. This would make the entire
                    # user's environment look like project code.
                    if project_root == Path.home().resolve():
                        project_root = None
                else:
                    project_root = None

                # ----------------------------------------------------------
                # Bare %freshrun: start a fresh child without a script.
                # ----------------------------------------------------------

                if not run_args:
                    env = os.environ.copy()
                    env["FRESHRUN_REQUEST"] = request_file

                    if project_root is None:
                        env.pop("FRESHRUN_PROJECT_ROOT", None)
                    else:
                        env["FRESHRUN_PROJECT_ROOT"] = str(project_root)

                    env.pop("FRESH_SCRIPT_NAME", None)
                    env.pop("FRESH_RUN_ARGUMENTS", None)

                    _print_freshrun_status("fresh")
                    if first_child:
                        _print_freshrun_helper("fresh")
                    print()

                    command = (
                        f"exec(open({startup_file!r}, encoding='utf-8').read())"
                    )

                    proc = _run_fresh_child(
                        [
                            sys.executable,
                            "-m",
                            "IPython",
                            "--no-banner",
                            "-i",
                            "-c",
                            command,
                        ],
                        env,
                    )
                else:
                    # current_script = _find_script_argument(current_args)
                    current_script = script_path
                    run_arguments = shlex.join(current_args)

                    if current_script is None:
                        print("Could not determine the script to monitor.")
                        break

                    current_script = os.path.abspath(
                        os.path.expanduser(current_script)
                    )
                    script_name = os.path.basename(current_script)

                    # ------------------------------------------------------
                    # Generate capture code.
                    # ------------------------------------------------------

                    capture_code = capture_template.replace(
                        "SCRIPT_PATH",
                        repr(current_script),
                    ).replace(
                        "RUN_ARGUMENTS",
                        repr(run_arguments),
                    ).replace(
                        "RUN_DEBUG_MODE",
                        repr("-d" in current_args),
                    )

                    with open(capture_file, "w", encoding="utf-8") as f:
                        f.write(capture_code)

                    # ------------------------------------------------------
                    # Environment passed to the child.
                    # ------------------------------------------------------

                    env = os.environ.copy()
                    env["FRESHRUN_REQUEST"] = request_file
                    env["FRESH_SCRIPT_NAME"] = script_name
                    env["FRESH_RUN_ARGUMENTS"] = run_arguments

                    # ------------------------------------------------------
                    # Tell the user what is about to happen.
                    # ------------------------------------------------------

                    if project_root is None:
                        env.pop("FRESHRUN_PROJECT_ROOT", None)
                    else:
                        env["FRESHRUN_PROJECT_ROOT"] = str(project_root)

                    _print_freshrun_status(script_name)

                    if first_child:
                        _print_freshrun_helper(script_name)
                        print_formatted_text(
                            FormattedText([
                                ("",
                                 " Note: locals from main will be copied"
                                 " in the current session after return.\n",
                                ),
                                ("", " Variable"),
                                ("bold", " _exception_locals "),
                                ("",
                                 "will be populated if an exception is raised.",
                                ),
                            ])
                        )

                    print()

                    # ------------------------------------------------------
                    # Start a completely new Python/IPython process.
                    # ------------------------------------------------------

                    command = (
                        "import os; "
                        "FRESH_SCRIPT_NAME = "
                        "os.environ['FRESH_SCRIPT_NAME']; "
                        "FRESH_RUN_ARGUMENTS = "
                        "os.environ['FRESH_RUN_ARGUMENTS']; "
                        f"exec(open({startup_file!r}, "
                        f"encoding='utf-8').read()); "
                        f"exec(open({capture_file!r}, "
                        f"encoding='utf-8').read())"
                    )

                    proc = _run_fresh_child(
                        [
                            sys.executable,
                            "-m",
                            "IPython",
                            "--no-banner",
                            "-i",
                            "-c",
                            command,
                        ],
                        env,
                    )

                # ----------------------------------------------------------
                # Normal child termination.
                # ----------------------------------------------------------

                if proc.returncode != EXIT_RESTART:
                    break

                # ----------------------------------------------------------
                # The child requested another fresh child.
                # ----------------------------------------------------------

                try:
                    with open(request_file, "r", encoding="utf-8") as f:
                        requested = f.read().strip()
                except OSError as exc:
                    print(f"Could not read restart request: {exc}")
                    break

                try:
                    current_args = shlex.split(requested)
                except ValueError as exc:
                    print(f"Invalid %freshrun command: {exc}")
                    break

                # An empty request means a bare %freshrun.
                first_child = False
                self.last_freshrun = shlex.join(current_args)

        print("\nReturned to parent IPython.")

    # Set the docstring for use with %freshrun?
    freshrun.__doc__ = FRESHRUN_HELP
