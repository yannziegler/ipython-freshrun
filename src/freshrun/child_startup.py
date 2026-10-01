"""Startup program installed into every fresh IPython child."""

import os
import sys

from IPython.core.magic import Magics, magics_class, line_magic
from IPython.terminal.prompts import Prompts
from pygments.token import Token

from freshrun.tools import InjectPullMagics
from freshrun.freshimport import FreshImportMagics
from freshrun.freshrun import FRESHRUN_HELP


EXIT_QUIT = 0
EXIT_RESTART = 42

# ---------------------------------------------------------------------------
# Child prompt
# ---------------------------------------------------------------------------

shell = get_ipython()

_project_root = os.environ.get("FRESHRUN_PROJECT_ROOT")
if _project_root:
    shell.user_ns["_freshrun_project_root"] = _project_root

_FRESH_SCRIPT_NAME = os.environ.get("FRESH_SCRIPT_NAME")
_FRESH_RUN_ARGUMENTS = os.environ.get("FRESH_RUN_ARGUMENTS")
_CHILD_FRESHRUN_COMMAND = (
    "%freshrun " + _FRESH_RUN_ARGUMENTS
    if _FRESH_RUN_ARGUMENTS
    else "%freshrun"
)

class FreshChildPrompts(Prompts):

    def in_prompt_tokens(self):
        return [
            (
                Token.Prompt,
                f"[{_FRESH_SCRIPT_NAME or 'freshrun'}] ",
            ),
            (
                Token.PromptNum,
                f"In [{self.shell.execution_count}]: ",
            ),
        ]

shell.prompts = FreshChildPrompts(shell)


# ---------------------------------------------------------------------------
# Keyboard shortcut
#
# Alt+Enter = repeat the current fresh run.
#
# prompt_toolkit represents Alt+Enter as Escape followed by Enter.
# ---------------------------------------------------------------------------

def _install_fresh_shortcut():
    if not hasattr(shell, "pt_app"):
        return

    try:
        key_bindings = shell.pt_app.key_bindings
    except Exception:
        return

    child_command = _CHILD_FRESHRUN_COMMAND

    # -----------------------------------------------------------------------
    # Alt+Enter = immediately repeat the current fresh run.
    # -----------------------------------------------------------------------

    @key_bindings.add("escape", "enter")
    def _(event):
        event.current_buffer.text = child_command
        event.current_buffer.validate_and_handle()

    # -----------------------------------------------------------------------
    # Page Up / Alt+Up = recall this child's %freshrun command.
    # -----------------------------------------------------------------------

    @key_bindings.add("escape", "up", eager=True)
    @key_bindings.add("pageup", eager=True)
    def _(event):
        event.current_buffer.text = child_command
        event.current_buffer.cursor_position = len(child_command)


_install_fresh_shortcut()


# ---------------------------------------------------------------------------
# Child magics
# ---------------------------------------------------------------------------

@magics_class
class FreshChildMagics(Magics):

    @line_magic
    def freshrun(self, line):
        """Replace this child by a completely fresh child."""

        line = line.strip()

        if line in ("--help", "-h"):
            print(FRESHRUN_HELP)
            return

        request_file = os.environ.get("FRESHRUN_REQUEST")

        if not request_file:
            print("Not running inside a %freshrun child.")
            return

        # Plain text only: no serialization of Python objects.
        with open(request_file, "w", encoding="utf-8") as f:
            f.write(line)

        sys.stdout.flush()
        sys.stderr.flush()

        # SystemExit would be intercepted by IPython.
        os._exit(EXIT_RESTART)

    # Set the docstring for use with %freshrun?
    freshrun.__doc__ = FRESHRUN_HELP

shell.register_magics(FreshChildMagics)
shell.register_magics(FreshImportMagics)
shell.register_magics(InjectPullMagics)
